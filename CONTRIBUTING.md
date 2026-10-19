# Hướng dẫn đóng góp (Contributing)

Cảm ơn bạn đã quan tâm tới **App Uninstaller**! Tài liệu này tóm tắt kiến trúc dự
án và các quy tắc cần tuân thủ để bản đóng góp được chấp nhận nhanh chóng.

Trước khi tham gia, vui lòng đọc [Quy tắc ứng xử](CODE_OF_CONDUCT.md).

---

## 1. Kiến trúc — tách lớp BẮT BUỘC

Dự án chia thành **hai tầng tách bạch**: phần lõi (không biết giao diện) và phần
giao diện người dùng.

```
app-uninstaller/
 ├─ uninstaller_lib/      ← LÕI: toàn bộ logic hệ thống (không có UI)
 │   ├─ models.py         → AppInfo (dữ liệu tối giản)
 │   ├─ enumerator.py     → quét registry (HKLM 64/32-bit + HKCU) + winget
 │   ├─ uninstall.py      → chạy lệnh gỡ, quyền admin, suy luận lệnh im lặng
 │   ├─ leftover.py       → quét & xoá leftover registry/file còn sót
 │   ├─ backup.py         → sao lưu .reg + ghi nhật ký history.jsonl
 │   └─ updater.py        → kiểm tra & tải bản cập nhật từ GitHub Releases
 ├─ main.py              ← UI: tkinter (chỉ thư viện chuẩn)
 ├─ main_qt.py           ← UI: PySide6/Qt (dark mode)
 ├─ launcher.py          ← vỏ .exe: nạp app_core.zip qua zipimport
 ├─ build.py             ← đóng gói .exe + app_core.zip
 └─ test_leftover.py     ← test không cần framework
```

**Quy tắc tách lớp (bắt buộc):**

- `uninstaller_lib/` chứa **mọi** logic hệ thống và **CẤM import tkinter/PySide6**.
  Lõi không được biết gì về giao diện.
- `main.py` / `main_qt.py` chỉ chứa mã giao diện + threading; **mọi** thao tác hệ
  thống phải gọi qua API của `uninstaller_lib`.
- `launcher.py` là vỏ nạp: **chỉ thư viện chuẩn**, không chứa logic nghiệp vụ.
- Nếu cần thêm năng lực mới: viết vào `uninstaller_lib/` trước, rồi mới gọi từ UI.

## 2. Quy tắc thư viện

- **Lõi (`uninstaller_lib/`, `launcher.py`, `build.py`, `make_icon.py`,
  `test_leftover.py`) CHỈ dùng thư viện chuẩn Python.** Tuyệt đối không thêm
  dependency bên ngoài vào tầng lõi.
- Chỉ **UI Qt** (`main_qt.py`) được phép dùng `PySide6`. Đây là dependency tùy chọn,
  khai báo trong `requirements.txt`; UI tkinter không cần cài gì thêm.
- `PyInstaller` chỉ dùng khi đóng gói (`requirements-build.txt`), không phải
  dependency runtime.
- Dự án **Windows-only** (dùng `winreg`, `ctypes.windll`, `subprocess`, …), không
  cần đảm bảo chạy đa nền tảng.

## 3. Quy tắc an toàn dữ liệu (BẤT BIẾN — không được nới lỏng)

Đây là phần quan trọng nhất khi sửa `leftover.py`:

- Không xoá thư mục `<root>\<publisher>` cấp 1; luôn tách khớp theo *name* và
  *publisher*.
- Cấm `target.startswith(candidate)`; chỉ cho `cand == target` hoặc
  (`len(target) >= 4` và `cand.startswith(target)`).
- `_is_safe_to_delete()` là **lớp chặn cuối**: chặn ổ gốc, `Windows` /
  `System32` / `SysWOW64` / `drivers`, mọi root quét (kể cả
  `%LOCALAPPDATA%\Programs`, `%PROGRAMDATA%`) và `<root>\<publisher>` cấp 1.
- Leftover luôn là **gợi ý**: UI phải để người dùng duyệt và xác nhận trước khi
  xoá; checkbox mặc định chỉ tích mục `entry`.
- Mọi thay đổi liên quan tới xoá/xoá registry **phải giữ hoặc bổ sung test** trong
  `test_leftover.py`.

## 4. Chạy thử & kiểm thử

Yêu cầu: Python 3.10+ trên Windows.

```bash
# Chạy bản tkinter (không cần cài thêm)
python main.py

# Chạy bản Qt (cần PySide6)
pip install -r requirements.txt
python main_qt.py
```

**Chạy toàn bộ test (không cần pytest):**

```bash
python test_leftover.py
```

Test này tự kiểm tra các bất biến an toàn, API MSI, suy luận lệnh im lặng, độ tin
cậy leftover, so sánh phiên bản và gói lõi cập nhật. **Mọi PR phải chạy qua lệnh
này mà không lỗi.**

Có thể kiểm tra nhanh cú pháp toàn bộ file `.py` giống CI:

```powershell
Get-ChildItem -Recurse -Filter *.py | ForEach-Object { python -m py_compile $_.FullName }
```

## 5. Cập nhật bộ nhớ ngữ cảnh (AI_CONTEXT.md)

Khi thêm/đổi/xoá class, hàm công khai hoặc field trong `uninstaller_lib/` hay
`main.py`, hãy tái tạo lại các khối tài liệu tự động trong `AI_CONTEXT.md` bằng:

```bash
python update_context.py
```

Script này chỉ dùng `ast` (không tốn token AI, không chạy app) và ghi lại nội dung
giữa các cặp marker `<!-- AUTO:start:models/api/main -->`. Nếu bạn chạm tới API ở
tầng lõi mà quên bước này, hãy chạy nó và commit `AI_CONTEXT.md` kèm theo.

## 6. Đóng gói (để kiểm tra trước khi phát hành)

```bash
pip install -r requirements-build.txt
python build.py              # vỏ .exe (UI tkinter) + dist/app_core.zip
python build.py --ui qt      # vỏ .exe chạy UI PySide6
python build.py --core-only  # CHỈ tạo dist/app_core.zip (cập nhật siêu nhẹ)
```

## 7. Quy trình gửi Pull Request

1. **Fork** kho và tạo nhánh từ `main` với tên gợi ý, ví dụ:
   `fix/leftover-recycle-bin`, `feat/qt-detail-panel`.
2. Giữ commit **nhỏ, rõ ràng**; mô tả *vì sao* thay vì chỉ *cái gì*.
3. Đảm bảo:
   - `python test_leftover.py` chạy sạch.
   - Cú pháp toàn bộ `.py` hợp lệ (`py_compile`).
   - Nếu đổi API lõi: đã chạy `python update_context.py`.
   - Giữ đúng tách lớp và quy tắc "chỉ thư viện chuẩn ở core".
4. Mở Pull Request, mô tả rõ thay đổi và cách kiểm chứng. CI (`ci.yml`) sẽ tự chạy
   trên `windows-latest`.
5. Sẵn sàng chỉnh sửa theo phản hồi review.

Cảm ơn bạn đã đóng góp! 🎉
