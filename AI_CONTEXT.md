# AI_CONTEXT.md — App Uninstaller (Windows)
> Bộ nhớ ngữ cảnh siêu gọn cho phiên AI. Đọc file này trước; chỉ đọc thêm FILE được phép ở Phần 5.

## 1. Architecture & Constraints
- Mục đích: GUI gỡ cài đặt ứng dụng Windows + quét leftover (kiểu Revo Uninstaller).
- CHỈ dùng thư viện chuẩn Python (tkinter, winreg, ctypes, subprocess, threading, dataclasses, ast). CẤM thêm dependency ngoài.
- Windows-only (winreg, ctypes.windll, os.startfile, subprocess shell=True). KHÔNG portable.
- Entry: `python main.py` · Test: `python test_leftover.py` · Đóng gói `.exe`: `python build.py [--ui tk|qt] [--clean-temp]` · Kiểm tra phiên bản: `python main.py --version` · Tái tạo file này: `python update_context.py` · Vỏ cập nhật: `python launcher.py [--ui tk|qt]`.
- Phiên bản: nguồn DUY NHẤT `uninstaller_lib.__version__` (+ `APP_NAME`, `about_text()`); cả 2 UI và `build.py` đọc từ đây. Repo cập nhật: `uninstaller_lib.GITHUB_REPO` (dạng `tài_khoản/repo`, chỉ đổi ở 1 nơi). Tên gói lõi: `uninstaller_lib.CORE_ZIP_NAME` (`app_core.zip`).
- Cập nhật lõi siêu nhẹ (Tách vỏ Launcher): `launcher.py` là vỏ `.exe`; nạp lõi `app_core.zip` cạnh `.exe` qua `zipimport` (`sys.path[0]`), tự áp dụng `app_core.new.zip`→`app_core.zip` (sao lưu `app_core.bak.zip`) và tự rollback/fallback về code đóng gói trong `_MEIPASS` khi gói lỗi. Lõi = `uninstaller_lib/` + `main.py`/`main_qt.py`.
- Tách lớp BẮT BUỘC:
  - `uninstaller_lib/` = mọi logic hệ thống; CẤM import tkinter; không biết giao diện.
  - `main.py` = chỉ tkinter UI + threading; gọi API qua `uninstaller_lib`.
  - `launcher.py` = vỏ nạp: CHỈ thư viện chuẩn, không chứa logic nghiệp vụ; được phép import động `main`/`main_qt` và `uninstaller_lib.updater`.
- Leftover luôn là "gợi ý": GUI bắt buộc duyệt + confirm trước khi xoá; checkbox mặc định chỉ tích "entry".
- Rule an toàn dữ liệu = BẤT BIẾN (không nới lỏng):
  - Không xoá thư mục `<root>\<publisher>` cấp 1; luôn tách quét name vs publisher.
  - Cấm `t.startswith(cand)`; chỉ `cand == t` hoặc (`len(t) >= 4` và `cand.startswith(t)`).
  - `_is_safe_to_delete()` là lớp chặn cuối: ổ gốc, Windows/System32/SysWOW64/drivers, mọi root quét (kể cả `%LOCALAPPDATA%\Programs`, `%PROGRAMDATA%`), và `<root>\<publisher>` cấp 1 (khi biết publisher).

## 2. Data Models (`uninstaller_lib/models.py`)
<!-- AUTO:start:models -->
- `class AppInfo` (@dataclass) — Thông tin một ứng dụng đã cài đặt, thu thập từ registry.
  - Fields: `name: str, version: str = '', publisher: str = '', install_date: str = '', install_location: str = '', estimate_size_kb: int = 0, uninstall_string: str = '', quiet_uninstall_string: str = '', registry_key: str = '', system_component: bool = False, source: str = 'registry', product_code: str = ''`
  - `@property size_text()` -> `str` — Chuyển EstimatedSize (tính bằng KB) thành chuỗi dễ đọc.
  - `@property date_text()` -> `str` — Chuyển InstallDate (YYYYMMDD) thành DD/MM/YYYY.
  - `@property can_uninstall()` -> `bool` — Có lệnh gỡ chuẩn hay không (registry / MSI / winget).
<!-- AUTO:end:models -->

## 3. Module API Contracts (`uninstaller_lib/`)
<!-- AUTO:start:api -->
- `uninstaller_lib/enumerator.py`
  - `estimate_location_size_kb(install_location: str)` -> `int` — Ước lượng dung lượng thư mục cài đặt (KB) khi thiếu EstimatedSize.
  - `normalize_winget_id(app_id: str)` -> `str` — Chuẩn hoá app_id của winget: bỏ hậu tố ``|arch|version`` (D2).
  - `clear_winget_cache()` -> `None` — Xoá cache `winget list` để lần quét kế tiếp chạy lại winget (D3).
  - `enumerate_apps(refresh_winget: bool = False)` -> `list` — Quét toàn bộ registry và trả về danh sách AppInfo (đã sắp xếp).
- `uninstaller_lib/uninstall.py`
  - `is_admin()` -> `bool` — Kiểm tra quyền Administrator của tiến trình hiện tại.
  - `relaunch_as_admin()` -> `bool` — Khởi chạy lại tiến trình hiện tại với quyền Administrator (UAC).
  - `list_msi_products()` -> `list` — Danh sách product code (GUID) đã cài, qua ``MsiEnumProductsW``.
  - `msi_product_installed(product_code: str)` -> `bool` — Kiểm tra một gói MSI có đang được cài (qua ``MsiQueryProductStateW``).
  - `uninstall_msi(product_code: str, quiet: bool = True)` — Gỡ một gói MSI bằng Windows Installer API (``MsiConfigureProductExW``).
      - Trả về: (ok, message, proc) — proc là _MsiJob (có .wait()) hoặc None.
  - `build_quiet_command(app: AppInfo)` -> `str` — Suy luận lệnh gỡ im lặng cho app.
  - `check_uninstaller_status(app: AppInfo)` -> `tuple` — Kiểm tra ứng dụng có gỡ chuẩn được hay không (phục vụ Force Uninstall).
  - `run_uninstall(app: AppInfo, quiet: bool = False)` — Chạy lệnh gỡ cài đặt của một ứng dụng.
      - Trả về: (ok: bool, message: str, proc) — proc: Popen/_MsiJob nếu chạy được, None nếu lỗi.
- `uninstaller_lib/leftover.py`
  - `find_uninstall_entry(app)` -> `list` — Đường dẫn các entry gỡ còn tồn tại trong registry (HKLM view 64/32, HKCU).
  - `scan_leftovers(app)` -> `list` — Quét toàn bộ leftover.
  - `delete_registry_key(path: str, app_name: str = '')` — Xoá key registry (cả subtree) theo 'HKCU\...' hoặc 'HKLM\...'.
      - Trả về: (ok: bool, err: str).
  - `kill_processes_in_dir(folder_path: str)` -> `list[str]` — Buộc dừng các tiến trình trùng tên với file `.exe` trong folder_path.
  - `list_running_images()` -> `set` — Tập tên image (chữ thường) của mọi tiến trình đang chạy (qua ``tasklist``).
  - `find_running_processes(app, running_images: set | None = None)` -> `list[str]` — Tên các tiến trình của ``app`` đang chạy (để cảnh báo trước khi gỡ/dọn).
  - `move_to_recycle_bin(path: str)` -> `tuple[bool, str]` — Đưa một file/thư mục vào Recycle Bin (thùng rác) thay vì xoá vĩnh viễn.
  - `delete_path(path: str, app_name: str = '')` — Xoá một file hoặc thư mục (kể cả read-only). Trả về (ok, err).
  - Safety (private nhưng QUAN TRỌNG):
    - `_is_match(candidate: str, targets)` -> `bool` — So khớp tương đối giữa 1 tên (folder/key) và danh sách tên chuẩn.
    - `_is_safe_to_delete(path: str, publisher: str = '')` -> `bool` — Chặn xoá các đường dẫn là thư mục hệ thống / ổ đĩa gốc / root.
- `uninstaller_lib/backup.py`
  - `list_backup_files()` -> `list[Path]` — Danh sách file .reg trong backups/, mới nhất đứng trước.
  - `list_backup_info()` -> `list[dict]` — Danh sách backup kèm thời gian để hiển thị trên UI (mới nhất đứng trước).
  - `prune_backups(max_keep: int = MAX_BACKUP_KEEP)` -> `int` — Xoay vòng backup: giữ tối đa `max_keep` file .reg gần nhất.
  - `clear_backups()` -> `int` — Xoá toàn bộ file .reg và làm trống history.jsonl.
  - `export_registry_key(reg_path: str, app_name: str)` -> `tuple[bool, str]` — Xuất một nhánh registry ra file .reg kèm timestamp (sao lưu trước khi xoá).
  - `restore_backup(reg_file)` -> `tuple[bool, str]` — Khôi phục một nhánh registry từ file .reg (gọi ``reg import``).
  - `create_restore_point(description: str = 'App Uninstaller Backup')` -> `tuple[bool, str]` — Tạo System Restore Point (PowerShell ``Checkpoint-Computer``).
  - `log_action(action: str, app_name: str, targets: list[dict], results: list[str])` -> `None` — Ghi một dòng JSONL vào backups/history.jsonl.
- `uninstaller_lib/updater.py`
  - `parse_version(v: str)` -> `tuple[int, ...]` — Chuẩn hoá chuỗi phiên bản thành tuple số để so sánh chính xác.
  - `get_app_dir()` -> `Path` — Thư mục chứa file ``.exe`` (khi đóng gói) hoặc thư mục gốc project.
  - `check_for_updates(repo: str = GITHUB_REPO, current_version: str = __version__, timeout: int = 8)` -> `dict` — Kiểm tra GitHub Releases xem có bản mới hơn ``current_version`` không.
  - `validate_core_zip(zip_path: Path)` -> `tuple[bool, str]` — Kiểm tra ``app_core.zip`` có hợp lệ để nạp/cập nhật lõi hay không.
  - `download_core_update(download_url: str, target_dir: Path | None = None)` -> `tuple[bool, str]` — Tải gói lõi ``app_core.zip`` về ``target_dir`` dưới tên ``app_core.new.zip``.
  - `apply_pending_update(app_dir: Path | None = None)` -> `tuple[bool, str]` — Áp dụng gói lõi đang chờ (``app_core.new.zip``) thành ``app_core.zip``.
  - `rollback_core_update(app_dir: Path | None = None)` -> `bool` — Khôi phục lõi cũ từ ``app_core.bak.zip`` đè lên ``app_core.zip``.
  - `download_update(download_url: str, dest_dir: Path | None = None)` -> `tuple[bool, str]` — Tải file ``.exe`` bản mới về ``dest_dir`` (mặc định: thư mục Downloads).
  - `restart_application()` -> `None` — Khởi chạy lại tiến trình hiện tại rồi thoát tiến trình cũ.
<!-- AUTO:end:api -->
- Cơ chế BẤT BIẾN:
  - Quét registry: 4 root (HKLM + HKCU × view `KEY_WOW64_64KEY`/`KEY_WOW64_32KEY`); KHÔNG liệt kê nhánh `WOW6432Node` (tránh trùng).
  - Khử trùng app theo `(name.lower(), version, uninstall_string)`; lọc `SystemComponent`, `ReleaseType`, `Parent*Name`.
  - Xoá registry: `DeleteKeyEx` dùng đúng cờ `access` như `OpenKey`; gom hết key con trước khi xoá; HKLM thử cả 2 view.
  - Sao lưu an toàn (backup.py): trước khi xoá registry luôn chạy `backup.export_registry_key` (file `.reg` kèm timestamp trong `backups/`); mọi thao tác xoá file/registry ghi vào `backups/history.jsonl` qua `backup.log_action` (best-effort, không chặn xoá).
  - Lệnh gỡ: `Popen(cmd, shell=True, DEVNULL, CREATE_NO_WINDOW)` — KHÔNG `cmd /c`; worker gọi `proc.wait()`.
  - Gỡ MSI: ưu tiên Windows Installer API (`uninstall_msi`, `msi.dll` qua ctypes); chỉ dùng khi `product_code` là GUID và `UninstallString` rỗng/`msiexec`; fallback về shell `msiexec`.
  - Hàm xoá trả `(ok: bool, err: str)`; leftover là list dict `{"kind", "path", "confidence"}` với `confidence ∈ {"high","medium"}` (Nhóm II; 2 khóa `kind`/`path` giữ nguyên để tương thích ngược 100%).
  - `scan_leftovers` (Nhóm II): thêm `confidence` cho mỗi mục qua `_match_confidence(candidate, targets)` (dùng ĐÚNG luật `_is_match`, KHÔNG nới lỏng): `"high"` = `kind=="entry"` / trùng `install_location` / tên folder-key-shortcut khớp tuyệt đối (`cand == t`); `"medium"` = khớp tiền tố hoặc nằm trong `<root>\<publisher>`.
  - Phạm vi quét file (Nhóm II): root gồm thêm `%LOCALAPPDATA%\Programs` và `%PROGRAMDATA%`; quét thêm shortcut `.lnk` (Start Menu của user + toàn máy, Desktop) có tên bỏ đuôi khớp `app.name`. Giữ nguyên `_SCAN_MAX_DEPTH = 2` và `_DIR_LIST_LIMIT = 5000`.
  - `_is_safe_to_delete(path, publisher="")` (Nhóm II): dùng `_all_file_roots()` (mọi root kể cả chưa tồn tại) thay cho root hiện có; chặn thêm `<root>\<publisher>` cấp 1 khi truyền `publisher`.
  - `create_restore_point(description)` (backup.py, Nhóm II): gọi PowerShell `Checkpoint-Computer` (CREATE_NO_WINDOW, timeout 60s), bắt mọi lỗi an toàn và ghi `history.jsonl` qua `log_action("restore_point", ...)`.
  - Lệnh gỡ im lặng (`build_quiet_command`, Nhóm I): thứ tự ưu tiên QuietUninstallString → MSI → msiexec → nhận diện bộ cài theo tên file/cờ (Squirrel `Update.exe --uninstall` thêm `-s`; WiX Burn `.exe /uninstall` thêm `/quiet /norestart`; InstallShield thêm `/S`) → dò chữ ký file (Inno/NSIS). CHỈ chèn cờ khi nhận diện RÕ RÀNG; không nhận diện được -> trả `""` (CẤM chèn cờ mù quáng gây treo).
  - `check_uninstaller_status(app)` (Nhóm I): sẵn sàng khi nguồn `winget`, `product_code` GUID hợp lệ, lệnh `msiexec`, hoặc `.exe` trong `uninstall_string`/`quiet_uninstall_string` tồn tại; ngược lại trả `(False, lý do)` để UI đề xuất Force Uninstall. Giữ nguyên property `AppInfo.can_uninstall`.
  - `estimate_location_size_kb` (Nhóm I): chỉ `os.scandir`, giới hạn độ sâu 2 cấp + 1500 mục; bỏ qua thư mục hệ thống / ổ đĩa gốc; chỉ điền khi `EstimatedSize` thiếu (0).

## 4. UI & Threading Model (`main.py`)
<!-- AUTO:start:main -->
- `class UninstallerApp` (tk.Tk) — Cửa sổ chính của ứng dụng.
  - `__init__()` — Khởi tạo state + build UI, tự động quét registry lần đầu.
  - `show_about()` — Hiện hộp thoại Giới thiệu (tên + phiên bản) — G2.
  - `check_updates()` — Kiểm tra bản mới trên GitHub Releases (chạy trên worker thread).
  - `refresh()` — Xoá bảng, quét lại registry trên worker thread.
  - `open_backups_folder()` — Mở thư mục backups/ và hướng dẫn cách khôi phục file .reg.
  - `clear_backup_history()` — Xoá toàn bộ .reg + làm trống history.jsonl (kèm cảnh báo).
  - `manage_backups()` — Mở hộp thoại liệt kê backup (.reg + thời gian) và khôi phục trực tiếp.
  - `uninstall_selected()` — Gỡ cài đặt chuẩn cho app đang chọn (confirm trước).
  - `uninstall_quiet()` — Gỡ im lặng cho app đang chọn (confirm trước).
  - `uninstall_batch()` — Gỡ lần lượt toàn bộ app đang chọn qua worker thread.
  - `scan_leftovers()` — Quét leftover cho app đang chọn qua worker thread.
  - `create_restore_point()` — Tạo System Restore Point trên worker thread (Nhóm II).
- `main()` — Entry point: tạo cửa sổ chính và lặp mainloop.
<!-- AUTO:end:main -->
- State chính: `self.apps: list[AppInfo]` (toàn bộ đã quét), `self._displayed` (sau lọc search + nguồn + sort), `self.tree: ttk.Treeview` (cột `name|version|publisher|size|date`), `self.search_var: tk.StringVar`, `self.source_var: tk.StringVar` (lọc nguồn, map qua `_SOURCE_FILTERS`), `self.status: ttk.Label`, `self._sort_col`/`self._sort_asc`.
- Threading BẮT BUỘC:
  - Tác vụ nặng (quét registry, chạy trình gỡ, quét leftover) luôn trên `threading.Thread(..., daemon=True)`.
  - Cập nhật UI từ worker: CHỈ qua `self.after(0, callback)` (cấm chạm tkinter widget trong worker).
  - Gỡ batch: `proc.wait()` xong app này mới chạy app kế tiếp (tránh xung đột msiexec); sau cùng tự quét leftover.
  - Sort cột "size" theo số `estimate_size_kb`.
- Tích hợp 2 UI (Nhóm III — `main.py` + `main_qt.py`):
  - Force Uninstall: trước khi gỡ (và sau khi gỡ thất bại) gọi `uninstall.check_uninstaller_status(app)`; nếu không sẵn sàng -> hộp thoại đề xuất "Gỡ cưỡng bức", đồng ý thì chạy luồng quét leftover. (`main.py` `_ask_force_uninstall`; `main_qt.py` `uninstall_selected`/`_on_uninstall_done`/`_ask_force_uninstall`.)
  - Leftover dialog hiển thị nhãn `[Cao]`/`[Trung bình]` từ `item["confidence"]`; nút "Chọn mức Cao" tích nhanh mục `high` (mặc định vẫn chỉ tích `entry`; người dùng phải xác nhận trước khi xoá).
  - Nút/menu "Tạo Restore Point" gọi `backup.create_restore_point()` trên worker thread (Tk: `threading.Thread` + `self.after`; Qt: `RestorePointWorker` QThread + Signal).
  - Menu Trợ giúp → "Kiểm tra cập nhật…" gọi `updater.check_for_updates()` trên worker thread (Tk: `threading.Thread` + `self.after`; Qt: `UpdateCheckWorker` QThread + Signal). Có bản mới → hiện `current_version`/`latest_version` + `notes`.
  - Nếu `download_url` kết thúc `.zip` (có gói lõi): hỏi tự động cập nhật nhẹ → tải qua `updater.download_core_update` + `updater.apply_pending_update` + `updater.restart_application` trên worker thread (Tk: `_core_update_worker`; Qt: `CoreUpdateWorker`). Ngược lại: mở trang Release (`os.startfile(release_url)`, Tk `_open_release_page`) hoặc tải `.exe` đầy đủ (`updater.download_update`, Qt `UpdateDownloadWorker`). Bản mới nhất/lỗi mạng đều báo rõ.
- Giao diện Qt (`main_qt.py`) — Redesign UI/UX (giữ nguyên logic worker/QThread):
  - Thanh công cụ chia 2 nhóm: **Thao tác chính** (icon `QStyle` + accent đỏ cho "Gỡ cài đặt", xanh cho "Quét Leftover") và nhóm **"Hệ thống & Backup"** gom vào `QToolButton` dropdown (`_build_system_menu`: mở thư mục, backups, restore point, nâng quyền Admin).
  - QSS dark mode: bo góc `border-radius: 6px`, hiệu ứng `hover`/`pressed` cho button/toolbutton, `alternatingRowColors(True)` + padding ô bảng; ô dữ liệu trống hiển thị `—` xám mờ (`PLACEHOLDER`/`PLACEHOLDER_COLOR` qua `ForegroundRole` của `AppsTableModel`).
  - Dock "Chi tiết ứng dụng" dùng `QStackedWidget`: trang 0 hiện hướng dẫn khi chưa chọn app; trang 1 hiện tiêu đề đậm + form chi tiết (`_update_detail`).

## 5. Context Loading Rules (cho AI phiên sau)
- Bắt đầu phiên: đọc đúng file `AI_CONTEXT.md` này — đủ đáp ứng ~95% yêu cầu.
- Chỉ đọc thêm ĐÚNG 1 file theo bảng dưới; CẤM quét toàn repo khi không cần thiết.

| Loại yêu cầu | Chỉ đọc thêm 1 file |
| --- | --- |
| Sửa UI/dialog/sự kiện/threading (Tk) | `main.py` |
| Sửa UI Qt / sự kiện / QThread | `main_qt.py` |
| Sửa quét danh sách app / registry | `uninstaller_lib/enumerator.py` |
| Sửa lệnh gỡ cài đặt / quyền admin | `uninstaller_lib/uninstall.py` |
| Sửa quét/xoá leftover, an toàn dữ liệu | `uninstaller_lib/leftover.py` |
| Sửa sao lưu / ghi nhật ký leftover | `uninstaller_lib/backup.py` |
| Thêm/đổi field, property `AppInfo` | `uninstaller_lib/models.py` |
| Thêm import/export package | `uninstaller_lib/__init__.py` |
| Đóng gói `.exe` / manifest / icon | `build.py` (+ `app.manifest`, `make_icon.py`) |
| Kiểm tra cập nhật / GitHub Releases / vỏ Launcher | `uninstaller_lib/updater.py` + `launcher.py` (+ `.github/workflows/release.yml`) |
| Cập nhật Class/API trong file này | `python update_context.py` (không cần đọc) |
| Xem kế hoạch cải tiến / việc còn lại | `ROADMAP.md` |

- Nghi ngờ luật an toàn leftover: đọc thêm duy nhất `test_leftover.py`.
- Muốn biết "đã sửa gì / còn gì cần cải tiến": đọc `ROADMAP.md` (checklist A→V + ghi chú kỹ thuật).
- Sau khi sửa: `python -m py_compile <file>` + `python test_leftover.py`.
- CẤM: thêm dependency; đổi view registry / `CREATE_NO_WINDOW` / `_is_match` / `_is_safe_to_delete` / luật xoá `<root>\<publisher>`.

## 6. Đóng gói (.exe) — `build.py` (+ `app.manifest`, `make_icon.py`)
- Chạy: `python build.py [--ui tk|qt] [--onedir] [--console] [--no-clean] [--clean-temp] [--core-only]`; kết quả ở `dist/`.
- **Đóng gói TÁCH VỎ**: entry của `.exe` LUÔN là `launcher.py` (vỏ nạp động); lõi
  (`uninstaller_lib/` + `main.py`/`main_qt.py`) đi kèm `dist/app_core.zip`.
  Giao diện mặc định của bản `--ui qt` được suy ra từ tên `.exe` (`...Qt`).
- `build_core_zip(output_dir)`: gom mọi `.py` trong `uninstaller_lib/` + `main.py` +
  `main_qt.py` vào `app_core.zip` (`zipfile.ZIP_DEFLATED`, giữ cấu trúc
  `uninstaller_lib/...`), in dung lượng (KB) + SHA-256. `--core-only` chỉ chạy bước
  này (không gọi PyInstaller, chưa tới 1 giây) để đẩy bản cập nhật nhẹ.
- Nhúng BẮT BUỘC: `--icon assets/app.ico`, `--manifest app.manifest`
  (`requireAdministrator` + DPI `permonitorv2`), `--version-file build/version_info.txt`
  (sinh từ `uninstaller_lib.__version__` — nguồn DUY NHẤT của phiên bản).
- `--hidden-import` BẮT BUỘC (`_hidden_imports_for(ui)`): vỏ nạp UI động nên phải
  khai báo tường minh thư viện nền (`winreg`, `ctypes`, `subprocess`, `threading`,
  `dataclasses`, `ast`, `urllib.request`, `zipfile`, `shutil`, `json`, các module
  `uninstaller_lib.*`) + `main`+`tkinter*` (tk) hoặc `main_qt`+`PySide6` (qt).
- Loại module để giảm dung lượng: hàm `_excludes_for(ui)` + `QT_EXCLUDES`/`TK_EXCLUDES`.
  - `--ui qt`: bỏ QtWebEngine*/QtQml/QtQuick*/Qt3D*/QtMultimedia*/QtNetwork/QtSql +
    `tkinter`/`unittest`/`pydoc`/`pdb` (giảm mạnh `.exe`, nhanh giải nén `--onefile`).
  - `--ui tk`: chỉ bỏ `PySide6` (tránh gom nhầm khi máy có cài PySide6).
- Sau khi build THÀNH CÔNG: `_report_output` in dung lượng (MB) + SHA-256
  (`_file_sha256` dùng `hashlib`, đọc theo khối) của `.exe` trong `dist/`
  (qua `_find_output`), rồi tự động gọi `build_core_zip` sinh kèm `app_core.zip`.
  Cờ `--clean-temp` -> `_cleanup_temp` xoá `build/` + `*.spec`.
- KHÔNG đưa PyInstaller vào `requirements.txt` (chỉ là build-time);
  `build/` + `*.spec` chỉ là sản phẩm trung gian (xoá được).

## 7. Kiểm tra cập nhật & Tách vỏ Launcher — `uninstaller_lib/updater.py`, `launcher.py` (+ `.github/workflows/release.yml`)
- Cấu hình 1 nơi: `uninstaller_lib.GITHUB_REPO` (dạng `tài_khoản/repo`) và `uninstaller_lib.CORE_ZIP_NAME` (`app_core.zip`). Đổi chỉ đổi ở `__init__.py`.
- `get_app_dir() -> Path`: thư mục chứa `.exe` khi `sys.frozen` (cạnh `sys.executable`), ngược lại thư mục gốc project.
- `parse_version(v) -> tuple[int, ...]`: bỏ tiền tố `v`, tách nhóm số (khớp regex `\d+`) để so sánh
  đúng thứ tự số (`1.10 > 1.9`). Chuỗi rỗng/không số -> `()`.
- `check_for_updates(repo=GITHUB_REPO, current_version=__version__, timeout=8) -> dict`:
  gọi `https://api.github.com/repos/{repo}/releases/latest` kèm header `User-Agent: App-Uninstaller`
  + `Accept: application/vnd.github+json`; trả dict đủ khoá
  `{ok, has_update, current_version, latest_version, download_url, release_url, notes, release_notes, asset_name, error}`
  (`release_notes` giữ để tương thích ngược với UI). `has_update = parse_version(tag) > parse_version(current)`.
  Asset chọn theo thứ tự: `app_core.zip` (ưu tiên, cập nhật lõi) -> file `.exe` -> fallback `zipball_url`/`html_url`.
  KHÔNG raise: 404/lỗi mạng/JSON đều -> `ok=False` + `error`.
- `validate_core_zip(zip_path) -> (ok, lý_do)`: `zipfile.is_zipfile` + `testzip()` (CRC) + phải chứa
  `uninstaller_lib/__init__.py` và (`main.py` hoặc `main_qt.py`). KHÔNG raise.
- `download_core_update(download_url, target_dir=None) -> (ok, path_or_error)`: tải gói lõi về
  `app_core.new.zip` tại `get_app_dir()` (ghi `.part` rồi `os.replace`), validate; hỏng -> xoá file tạm.
- `apply_pending_update(app_dir=None) -> (ok, path_or_error)`: `app_core.new.zip` hợp lệ -> sao lưu
  `app_core.zip` cũ sang `app_core.bak.zip` rồi hoán đổi gói mới vào. `rollback_core_update(app_dir=None) -> bool`:
  khôi phục `app_core.bak.zip` đè `app_core.zip`. `restart_application()`: chạy lại tiến trình
  (`sys.executable`) với `PYINSTALLER_RESET_ENVIRONMENT=1` trong env con (PyInstaller onefile >= 6.9):
  bắt tiến trình mới tự giải nén `_MEI...` MỚI thay vì tái dùng thư mục tạm sẽ bị vỏ cũ xoá khi thoát
  (nếu không, tiến trình mới mất `base_library.zip` -> lỗi import muộn như `ssl`/`urllib`: "Không kết nối được GitHub").
- `download_update(download_url, dest_dir=None) -> (ok, path_or_error)`: tải `.exe` đầy đủ về
  `dest_dir` (mặc định `~/Downloads`, fallback thư mục tạm), ghi file `.part` rồi `os.replace`. KHÔNG raise.
- `launcher.py` (vỏ `.exe`): xác định `app_dir` -> `apply_pending_update` -> nếu có `app_core.zip` thì chèn
  `sys.path[0]` rồi purge cache `uninstaller_lib*` -> import động `main`/`main_qt` và gọi `main()`. Lỗi nạp lõi
  ZIP -> `rollback_core_update` hoặc bỏ ZIP khỏi `sys.path`, purge lại rồi chạy tiếp bằng code `_MEIPASS`.
  Chọn UI: `--ui qt|tk` > `APP_UNINSTALLER_UI` > `DEFAULT_UI` lúc build.
- CHỈ thư viện chuẩn (`urllib.request`, `urllib.error`, `json`, `zipfile`, `shutil`, `sys`, `os`, `subprocess`, `pathlib`);
  KHÔNG import `tkinter`.
- `.github/workflows/release.yml`: khi push tag `v*` trên `windows-latest` -> cài requirements,
  chạy `python test_leftover.py`, build `python build.py --clean-temp` + `python build.py --ui qt --clean-temp`,
  rồi tạo GitHub Release kèm `dist/AppUninstaller.exe` + `dist/AppUninstallerQt.exe` + `dist/app_core.zip`
  (`softprops/action-gh-release@v2`, `permissions: contents: write`).
- Tăng phiên bản để phát hành: sửa `__version__` trong `uninstaller_lib/__init__.py`, rồi
  `git tag vX.Y.Z && git push origin vX.Y.Z` -> workflow tự build & release.