# App Uninstaller

[![Release](https://img.shields.io/github/v/release/mas120/go-phan-mem?label=release&sort=semver)](https://github.com/mas120/go-phan-mem/releases)
[![License: MIT](https://img.shields.io/github/license/mas120/go-phan-mem?label=license)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](#yêu-cầu)
[![Platform](https://img.shields.io/badge/platform-Windows-0078D6)](#yêu-cầu)
[![CI](https://github.com/mas120/go-phan-mem/actions/workflows/ci.yml/badge.svg)](https://github.com/mas120/go-phan-mem/actions/workflows/ci.yml)

Ứng dụng gỡ cài đặt ứng dụng trên **Windows** và dọn dẹp phần còn sót (leftover),
viết bằng **Python — chỉ dùng thư viện chuẩn ở tầng lõi**. Có hai giao diện:

- `main.py` — **tkinter** (chỉ thư viện chuẩn, không cần cài gì thêm).
- `main_qt.py` — **PySide6/Qt** hiện đại, dark mode, đa luồng chuẩn Qt
  (QThread + Signal).

> Ý tưởng thiết kế và bố cục lấy cảm hứng từ
> [Bulk Crap Uninstaller](https://github.com/Klocman/Bulk-Crap-Uninstaller).

## Ảnh chụp màn hình

<!-- Thêm ảnh vào assets/ rồi bỏ comment dòng dưới (placeholder hiện tại). -->
<!-- ![Giao diện App Uninstaller](assets/screenshot.png) -->

> _Ảnh chụp màn hình sẽ được bổ sung tại `assets/screenshot.png`._

---

## Tính năng chính

- **Liệt kê ứng dụng đã cài** từ registry (HKLM 64/32-bit + HKCU), bổ sung nguồn
  **Winget** (`winget list`) cho app UWP / MS Store.
- **Tìm kiếm / lọc** theo tên hoặc nhà phát hành; sắp xếp theo từng cột.
- **Gỡ cài đặt** bằng trình gỡ chuẩn của ứng dụng (kèm UAC khi cần).
- **Gỡ im lặng thông minh**: dùng `QuietUninstallString` nếu có; nếu không, tự suy
  luận cho MSI (`/X /qn /norestart`), Inno Setup (`/VERYSILENT …`), NSIS (`/S`),
  Squirrel/Electron (`Update.exe --uninstall -s`), InstallShield (`/S`) và WiX
  Burn (`/quiet /norestart`). Chỉ chèn cờ khi nhận diện rõ loại bộ cài.
- **Gỡ MSI qua Windows Installer API** (`MsiConfigureProductEx`), tự fallback về
  `msiexec` khi cần.
- **Phát hiện app "mồ côi" / hỏng trình gỡ** → gợi ý chuyển sang **Gỡ cưỡng bức**
  (tự chạy luồng quét & dọn leftover).
- **Quét leftover**: file/registry còn sót sau khi gỡ, có **nhãn độ tin cậy**
  `[Cao]` / `[Trung bình]` và nút **"Chọn mức Cao"**. File/thư mục được chuyển vào
  **Recycle Bin** (khôi phục được) thay vì xoá vĩnh viễn.
- **Backup tự động + khôi phục trong app**: xuất `.reg` trước khi xoá registry, ghi
  nhật ký `backups/history.jsonl`, và có nút "Khôi phục Backup" (`reg import`).
- **System Restore Point**: tạo điểm khôi phục trước khi gỡ/dọn (chạy nền, không
  đơ UI).
- **Gỡ batch**: chọn nhiều ứng dụng rồi gỡ lần lượt, tránh xung đột `msiexec`.
- **Ước lượng dung lượng** thư mục cài đặt khi thiếu `EstimatedSize`.
- **Kiểm tra cập nhật** từ GitHub Releases + **cập nhật lõi siêu nhẹ** (tải
  `app_core.zip`, áp dụng và tự khởi động lại).

---

## Tải bản `.exe` (khuyến nghị cho người dùng)

Không cần cài Python. Truy cập mục **Releases** và tải file phù hợp:

1. Mở trang **[Releases](https://github.com/mas120/go-phan-mem/releases)**.
2. Tải bản mới nhất:
   - `AppUninstaller.exe` — vỏ chạy giao diện **tkinter**.
   - `AppUninstallerQt.exe` — vỏ chạy giao diện **PySide6/Qt**.
   - `app_core.zip` — gói lõi dùng cho **cập nhật siêu nhẹ** (không bắt buộc khi
     cài mới).
3. Đặt `.exe` ở thư mục bạn muốn (thư mục `backups/` sẽ được tạo cạnh `.exe`).
4. Mở `.exe` — Windows sẽ hỏi quyền **Administrator (UAC)** một lần.

> Kiến trúc **tách vỏ**: `.exe` là vỏ nạp (`launcher.py`), nạp lõi `app_core.zip`
> cạnh nó qua `zipimport`. Vì vậy **cập nhật chỉ cần thay `app_core.zip`** (vài
> chục KB) thay vì tải lại cả `.exe`. Nếu gói lõi lỗi, vỏ tự rollback/fallback
> (không bị "brick").

---

## Chạy từ mã nguồn

### Yêu cầu

- **Windows 10/11**
- **Python 3.10+**

### Giao diện tkinter (không cần cài thêm)

```bash
python main.py
```

### Giao diện Qt (đẹp hơn, cần PySide6)

```bash
pip install -r requirements.txt
python main_qt.py
```

(Gõ `python` thay vì `py` nếu máy chỉ có `py` launcher.)

### Kiểm tra phiên bản mà không mở giao diện

```bash
python main.py --version
python main_qt.py --version
```

### Chạy test

```bash
python test_leftover.py
```

---

## Đóng gói thành file `.exe` (`build.py`)

Ứng dụng được đóng gói **tách vỏ**: một file `.exe` (vỏ `launcher.py`, kèm icon và
manifest tự xin quyền Administrator) + gói lõi `app_core.zip`.

```bash
pip install -r requirements-build.txt   # cài PyInstaller (chỉ dùng khi build)
python build.py                          # đóng gói vỏ (UI mặc định: tkinter)
python build.py --ui qt                  # đóng gói vỏ chạy UI PySide6
python build.py --core-only              # CHỈ tạo nhanh dist/app_core.zip
```

Kết quả nằm trong `dist/`: `.exe` + `app_core.zip`. Ghi chú:

- `python build.py --onedir` — xuất dạng thư mục (khởi động nhanh hơn).
- `python build.py --console` — giữ cửa sổ console để xem lỗi khi gỡ rối.
- `python build.py --clean-temp` — xoá `build/` + file `*.spec` sau khi build.
- Sau khi build, công cụ in **dung lượng (MB) + SHA-256** của `.exe` và **dung
  lượng (KB) + SHA-256** của `app_core.zip`.
- Bản `--ui qt` tự loại các module Qt nặng không dùng và `tkinter`/`unittest`/
  `pydoc`/`pdb`; bản `--ui tk` loại `PySide6`.
- Icon tự sinh bằng `python make_icon.py` (chỉ thư viện chuẩn) nếu chưa có.

---

## Cấu trúc dự án

```
app-uninstaller/
 ├─ uninstaller_lib/          → LÕI: toàn bộ logic (không phụ thuộc UI)
 │   ├─ models.py             → AppInfo (dữ liệu tối giản)
 │   ├─ enumerator.py         → quét registry (HKLM 64/32-bit + HKCU) + winget
 │   ├─ uninstall.py          → chạy lệnh gỡ, quyền admin, suy luận lệnh im lặng
 │   ├─ leftover.py           → quét & xoá leftover registry/file còn sót
 │   ├─ backup.py             → sao lưu .reg + ghi nhật ký history.jsonl
 │   └─ updater.py            → kiểm tra & tải bản cập nhật từ GitHub Releases
 ├─ .github/
 │   └─ workflows/
 │       ├─ ci.yml            → CI: py_compile + test_leftover.py (mọi push/PR)
 │       └─ release.yml       → build + phát hành khi push tag v*
 ├─ assets/
 │   └─ app.ico               → icon ứng dụng (sinh bởi make_icon.py)
 ├─ main.py                   → giao diện tkinter
 ├─ main_qt.py                → giao diện PySide6/Qt (dark mode)
 ├─ launcher.py               → vỏ .exe: nạp app_core.zip (zipimport)
 ├─ app.manifest              → manifest .exe (requireAdministrator / DPI)
 ├─ make_icon.py              → sinh icon .ico (chỉ thư viện chuẩn)
 ├─ build.py                  → đóng gói tách vỏ: .exe + dist/app_core.zip
 ├─ test_leftover.py          → test không cần framework
 ├─ update_context.py         → tái tạo AI_CONTEXT.md từ mã nguồn (ast)
 ├─ requirements.txt
 ├─ requirements-build.txt
 ├─ README.md
 ├─ CONTRIBUTING.md
 ├─ CODE_OF_CONDUCT.md
 └─ LICENSE
```

Mỗi lần build tạo ra trong `dist/`: vỏ `.exe` + `app_core.zip`. Khi phát hành, đính
kèm cả hai lên GitHub Release (vỏ cho người mới, `app_core.zip` cho cập nhật nhẹ).

---

## Ghi chú

- Nên chạy bằng quyền **Administrator** để gỡ được các ứng dụng đòi quyền cao (UI
  app sẽ tự hiện UAC prompt, hoặc mở lại app bằng "Run as administrator").
- Một số mục trong registry là component hệ thống / bản cập nhật Windows — app đã
  tự động lọc bỏ.
- Ứng dụng chỉ gỡ khi trình gỡ cung cấp `UninstallString`; nếu mất lệnh gỡ (app
  "mồ côi"), app sẽ báo và không gỡ để tránh phá hỏng hệ thống.
- Dữ liệu leftover luôn là "gợi ý": bạn phải duyệt và xác nhận trước khi xoá.

## Đóng góp

Mọi đóng góp đều được chào đón! Vui lòng đọc [CONTRIBUTING.md](CONTRIBUTING.md)
trước khi mở Pull Request và tuân thủ [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Giấy phép

Phát hành theo giấy phép [MIT](LICENSE).
