# ROADMAP — Theo dõi cải tiến App Uninstaller

> File này để **mốt đọc lại biết đã update chỗ nào và còn gì cần cải tiến**.
> Quy ước trạng thái: `[x]` đã làm · `[ ]` chưa làm · `[~]` đang làm.
> Mỗi mục ghi rõ **file đã sửa** để tra cứu nhanh (không cần quét cả repo).

## 0. Đã áp dụng (Polish Patch — phiên trước)
- [x] `enumerator.py`: `subprocess.run` đọc `winget list` thêm `encoding="utf-8", errors="replace"`.
- [x] `backup.py`: `export_registry_key` thử lại `/reg:32` & `/reg:64` cho nhánh HKLM.
- [x] `leftover.py`: `find_uninstall_entry` trả `[]` sớm cho app nguồn `winget`.
- [x] `main_qt.py`: chống GC worker (`self._worker`/`self._thread`), bỏ backup/kill/log trùng lặp.
- [x] `main.py`: dùng `build_quiet_command`, truyền `app.name` vào hàm xoá leftover.
- [x] `README.md` + `AI_CONTEXT.md`: cập nhật mô tả UI Qt, winget, gỡ im lặng, backup.
- [x] `ROADMAP.md`: file theo dõi tiến độ cải tiến (checklist A→G + ghi chú kỹ thuật).

## 1. Nhóm A — Sửa nhanh / nền tảng
- [x] **A1** — `requirements.txt`: thêm `PySide6>=6.6`. *(`requirements.txt`)*
- [x] **A2** — Gỡ MSI bằng `product_code` → `MsiExec.exe /X{GUID} /qn /norestart`.
      *(`uninstaller_lib/uninstall.py`: thêm `_msi_uninstall_command`, dùng trong
      `build_quiet_command` + `run_uninstall`; `main.py`: dùng `app.can_uninstall`)*
- [x] **A3** — `main.py`: thêm dropdown lọc theo Nguồn (đồng bộ Qt).
      *(`main.py`: `_SOURCE_FILTERS`, `self.source_var`, `_selected_source`, `_refresh_tree`)*

## 2. Nhóm B — Backup / restore
- [x] **B1** — Nút "Mở Backups" + hướng dẫn khôi phục `.reg`.
      *(`main.py` `open_backups_folder`; `main_qt.py` `open_backups_folder` + QAction + nút)*
- [x] **B2** — Nút "Dọn Backups" (xoá `.reg` + làm trống `history.jsonl`) kèm cảnh báo.
      *(`backup.py` `clear_backups()`; `main.py` `clear_backup_history`;
      `main_qt.py` `clear_backup_history` + QAction + nút)*
- [x] **B3** — Xoay vòng backup: giữ tối đa `MAX_BACKUP_KEEP = 50` bản gần nhất.
      *(`backup.py`: `MAX_BACKUP_KEEP`, `_mtime`, `list_backup_files`, `prune_backups`
      — gọi tự động sau khi `export_registry_key` thành công)*
- [x] **B4** (mới) — UI khôi phục trực tiếp: chọn file `.reg` trong danh sách → bấm "Khôi phục"
      (gọi `reg import`) thay vì chỉ mở thư mục. *(`backup.py` `restore_backup`; `main.py`
      `manage_backups`; `main_qt.py` `BackupDialog` + `open_backup_manager`)*
- [x] **B5** (mới) — Hiển thị danh sách backup + thời gian trong UI (dùng `list_backup_info`).
      *(`backup.py` `list_backup_info`; `main.py` `manage_backups`; `main_qt.py` `BackupDialog`)*

## 3. Nhóm C — An toàn leftover
- [x] **C1** — Test `_is_match` / `_is_safe_to_delete` (mock path hệ thống; case Office/Java/NVIDIA).
      *(`test_leftover.py`: `test_is_match` 11 case, `test_is_safe_to_delete` — mock root qua env PROGRAMFILES + thư mục hệ thống thật)*
- [x] **C2** — Chuyển xoá **file** qua Recycle Bin (giảm mất mát khi xoá nhầm).
      *(`leftover.py`: `move_to_recycle_bin` (SHFileOperationW + FOF_ALLOWUNDO),
      `_remove_path` (recycle → fallback xoá vĩnh viễn), `delete_path` ghi log kèm cách xoá)*
- [x] **C3** — Ghi log rõ mục "xoá dở dang" khi `rmtree` bỏ dở.
      *(`leftover.py`: `_snapshot_paths` + `_permanent_remove`; `_remove_path` đối chiếu
      snapshot để báo "đã xoá X/Y mục; còn lại ...")*

## 4. Nhóm D — Winget / parser
- [x] **D1** — Thêm `--accept-source-agreements` vào lệnh uninstall winget.
      *(`enumerator.py`: `_WINGET_FLAG` dùng cho cả `winget list` và chuỗi uninstall;
      `uninstall.py`: `_normalize_winget_command` đảm bảo cờ khi chạy)*
- [x] **D2** — Xử lý `app_id` dạng `Name|x64|1.2` trước khi ghép lệnh.
      *(`enumerator.py`: `normalize_winget_id`; `uninstall.py` dùng lại để chuẩn hoá
      `--id` khi chạy)*
- [x] **D3** — Cache kết quả `winget list` (1 lần/phiên) — bớt chờ 8s mỗi lần refresh.
      *(`enumerator.py`: `_winget_cache` + `_WINGET_FLAG`, `_get_winget_rows`,
      `clear_winget_cache`, `enumerate_apps(refresh_winget=False)`; 2 UI xả cache
      sau khi gỡ app)*

## 5. Nhóm E — UI / UX (Qt)
- [x] **E1** — Panel chi tiết app đang chọn (vị trí cài, size, publisher, lệnh gỡ, nguồn, MSI?).
      *(`main_qt.py`: `_build_detail_dock` (QDockWidget + QFormLayout) + `_update_detail`,
      cập nhật theo `selectionChanged`)*
- [x] **E2** — Phím tắt (Ctrl+F tìm kiếm, Delete gỡ) + tooltip cột.
      *(`main_qt.py`: `action_search` (Ctrl+F) + `_focus_search`, action gắn vào cửa sổ
      để phím tắt luôn chạy; `COLUMN_TIPS` + `headerData` ToolTipRole)*
- [x] **E3** — Cảnh báo "app đang chạy" trước khi gỡ / dọn leftover.
      *(`leftover.py`: `list_running_images`, `find_running_processes`, `_candidate_exe_names`;
      `main_qt.py`: `_running_note` chèn vào hộp xác nhận gỡ + `LeftoverDialog`)*

## 6. Nhóm F — Hiệu năng
- [x] **F1** — `enumerator`: chỉ đọc value cần thiết (tránh chậm khi 200+ app).
      *(`enumerator.py`: hằng `_WANTED_VALUES` (13 value dùng thật) + `_read_values`
      chuyển từ `EnumValue` toàn bộ sang `QueryValueEx` đúng value cần — bỏ qua value
      lớn không dùng như `DisplayIcon`/`ModifyPath`)*
- [x] **F2** — `_scan_files`: giới hạn độ sâu quét trong `Program Files`.
      *(`leftover.py`: hằng `_SCAN_MAX_DEPTH = 2`, `_DIR_LIST_LIMIT`, tách `_scan_dir`
      quét đệ quy có chặn độ sâu + số mục mỗi thư mục; giữ nguyên luật không thêm
      `<root>\<publisher>` và mọi chốt an toàn)*

## 7. Nhóm G — Đóng gói / phát hành
- [x] **G1** — PyInstaller `--onefile` + manifest `requireAdministrator` + icon.
      *(`build.py` đóng gói `--onefile --windowed` + `--icon assets/app.ico` +
      `--manifest app.manifest`; `app.manifest` (requireAdministrator/DPI/supportedOS);
      `make_icon.py` sinh `assets/app.ico` chỉ bằng thư viện chuẩn; `requirements-build.txt`;
      `backup.py` đổi `BACKUP_DIR` sang cạnh file `.exe` khi `sys.frozen`)*
- [x] **G2** — `--version` + hộp thoại About.
      *(`uninstaller_lib/__init__.py`: `__version__`, `APP_NAME`, `about_text()`;
      `main.py`: menu "Trợ giúp → Giới thiệu" + `--version`; `main_qt.py`: menu bar
      "Trợ giúp" + `QMessageBox.about` + `--version`; `build.py`: sinh
      `--version-file` từ `__version__` để `.exe` hiện đúng phiên bản)*

---

## 8. Nhóm H — MSI API (nâng cao)
- [x] **H1** — Gỡ gói MSI qua Windows Installer API (ổn định hơn shell `msiexec`).
      *(`uninstall.py`: `_load_msi`, `list_msi_products` (MsiEnumProductsW),
      `msi_product_installed` (MsiQueryProductStateW), `uninstall_msi`
      (MsiConfigureProductExW) + lớp `_MsiJob` (chạy nền, có `.wait()`);
      `run_uninstall` ưu tiên API rồi fallback về shell; `test_leftover.py`
      thêm `test_msi_api` — chỉ đọc, không gỡ)*

---

## 9. Nhóm I — Nhận diện bộ cài mở rộng + Force Uninstall + ước lượng dung lượng
- [x] **I1** — Mở rộng `build_quiet_command` nhận diện thêm bộ cài phổ biến.
      *(`uninstall.py`: `_extract_exe_token`, `_has_token_flag`, `_append_flags`,
      `_is_squirrel_uninstaller` (`Update.exe --uninstall` → `-s`),
      `_is_wix_burn_bootstrapper` (`.exe /uninstall` → `/quiet /norestart`),
      `_is_installshield_uninstaller` (→ `/S`); giữ nguyên MSI/Inno/NSIS; KHÔNG
      chèn cờ mù quáng khi không nhận diện được)*
- [x] **I2** — `check_uninstaller_status(app)` phát hiện app mồ côi / hỏng trình gỡ.
      *(`uninstall.py`: MSI GUID / winget / msiexec / `.exe` tồn tại → `(True,"OK")`;
      ngược lại `(False, lý do)` — giữ nguyên `AppInfo.can_uninstall`)*
- [x] **I3** — `estimate_location_size_kb(install_location)` ước lượng dung lượng khi
      thiếu `EstimatedSize`. *(`enumerator.py`: chỉ `os.scandir`, giới hạn
      `_ESTIMATE_MAX_DEPTH=2` + `_ESTIMATE_MAX_ENTRIES=1500`, bỏ qua
      `_is_system_or_drive_root`; `_enumerate_view` gọi khi `estimate_size_kb == 0`)*
- [x] **I4** — Test + đồng bộ. *(`test_leftover.py`: `test_build_quiet_command`
      (MSI/Inno/NSIS/Squirrel/InstallShield/WiX Burn/ngoặc kép/không nhận diện),
      `test_check_uninstaller_status`; cập nhật `AI_CONTEXT.md`/`ROADMAP.md`/`README.md`)*

---

## 10. Nhóm II — Phân loại độ tin cậy + mở rộng quét + System Restore
- [x] **II1** — Phân loại độ tin cậy cho leftover (`scan_leftovers` thêm trường
      `"confidence"`, giữ nguyên `"kind"`/`"path"`). *(`leftover.py`:
      `_match_confidence` (dùng đúng luật `_is_match`, không nới lỏng),
      `_item_confidence`, `_has_ancestor_named`; `scan_leftovers` gắn
      `"high"`/`"medium"`)*
- [x] **II2** — Mở rộng phạm vi quét an toàn. *(`leftover.py`: `_all_file_roots`
      thêm `%LOCALAPPDATA%\Programs` (đã có `%PROGRAMDATA%`); `_is_safe_to_delete`
      dùng `_all_file_roots` + chặn `<root>\<publisher>` cấp 1 qua tham số
      `publisher`; `_scan_shortcuts` quét `.lnk` trong Start Menu
      (user + toàn máy) & Desktop; giữ `_SCAN_MAX_DEPTH=2`, `_DIR_LIST_LIMIT=5000`)*
- [x] **II3** — Tạo System Restore Point. *(`backup.py`: `create_restore_point`
      gọi PowerShell `Checkpoint-Computer` qua `subprocess.run`
      (CREATE_NO_WINDOW, timeout 60s), bắt mọi lỗi an toàn, ghi `history.jsonl`
      qua `log_action("restore_point", ...)`)*
- [x] **II4** — Test + đồng bộ. *(`test_leftover.py`: `test_scan_leftovers_confidence`
      + mở rộng `test_is_safe_to_delete` kiểm tra `%LOCALAPPDATA%\Programs`,
      `%PROGRAMDATA%`, `<root>\<publisher>` cấp 1; cập nhật
      `AI_CONTEXT.md`/`ROADMAP.md`/`README.md`)*

---

## 11. Nhóm III — Tích hợp API mới lên giao diện (Tk + Qt)
- [x] **III1** — Force Uninstall khi trình gỡ gốc lỗi/mất. *(`main.py`:
      `_confirm_and_uninstall` gọi `check_uninstaller_status` trước + đề xuất khi
      gỡ lỗi, `_ask_force_uninstall`; `main_qt.py`: `uninstall_selected` +
      `_on_uninstall_done` (1 app lỗi) + `_ask_force_uninstall`; đồng ý thì chạy
      luồng quét leftover)*
- [x] **III2** — Hiển thị độ tin cậy trong hộp thoại leftover. *(`main.py`
      `_open_leftover_dialog`: nhãn `[Cao]`/`[Trung bình]` + nút "Chọn mức Cao"
      (`_check_high_confidence`); `main_qt.py` `LeftoverDialog`: `CONF_TAG` +
      `_populate` + `select_high_btn`/`_set_high_checked`; giữ luật mặc định chỉ
      tích `entry` + confirm trước khi xoá)*
- [x] **III3** — Nút "Tạo Restore Point". *(`main.py`: `create_restore_point` +
      `_restore_point_worker` (threading) + `_on_restore_point_done` + nút
      toolbar; `main_qt.py`: `action_restore_point` + `btn_restore_point` +
      `RestorePointWorker` (QThread/Signal) + `create_restore_point`/`_on_restore_point_done`)*
- [x] **III4** — Kiểm tra + đồng bộ. *(`python -m py_compile main.py main_qt.py`,
      `python test_leftover.py`, `python update_context.py`; cập nhật
      `AI_CONTEXT.md`/`ROADMAP.md`/`README.md`)*

---

## 12. Nhóm IV — Tối ưu & an toàn quy trình đóng gói `.exe`
- [x] **IV1** — Giảm dung lượng bản Qt + cô lập bản Tk. *(`build.py`: thêm hằng số
      `QT_EXCLUDES`/`TK_EXCLUDES` + `_excludes_for(ui)`; `--ui qt` chèn
      `--exclude-module` cho QtWebEngineCore/Widgets/Quick, QtQml, QtQuick,
      QtQuickWidgets, Qt3DCore, Qt3DRender, QtMultimedia(+Widgets), QtNetwork,
      QtSql, `tkinter`, `unittest`, `pydoc`, `pdb`; `--ui tk` loại `PySide6`)*
- [x] **IV2** — Dọn temp + băm kiểm tra. *(`build.py`: cờ `--clean-temp` xoá
      `build/` + `*.spec` sau khi build thành công (`_cleanup_temp`); in
      **dung lượng (MB) + SHA-256** (`hashlib`, đọc theo khối) của `.exe` trong
      `dist/` qua `_report_output`/`_file_sha256`/`_find_output`)*
- [x] **IV3** — Kiểm tra + chạy thử. *(`python -m py_compile build.py`;
      `python build.py --clean-temp` -> `dist/AppUninstaller.exe` 11.92 MB;
      `python build.py --ui qt --clean-temp` -> `dist/AppUninstallerQt.exe` 44.24 MB;
      xác nhận `FileVersion`/`ProductVersion = 1.0.0`, manifest
      `requireAdministrator` + `permonitorv2` nhúng trong `.exe`, icon nhúng OK)*

---

## 13. Nhóm V — Kiểm tra & Cập nhật phiên bản từ GitHub Releases
- [x] **V1** — Cấu hình repo 1 nơi. *(`uninstaller_lib/__init__.py`: thêm hằng số
      `GITHUB_REPO = "mas120/go-phan-mem"`)*
- [x] **V2** — Module cập nhật (chỉ thư viện chuẩn). *(`uninstaller_lib/updater.py`:
      `parse_version`; `check_for_updates` gọi GitHub API `/releases/latest`
      (User-Agent + Accept), trả dict 7 khoá + tự tìm asset `.exe`;
      `download_update` tải về `~/Downloads` (fallback temp) qua file `.part` ->
      `os.replace`; KHÔNG raise)*
- [x] **V3** — Tích hợp 2 giao diện. *(`main.py`: menu Trợ giúp → "Kiểm tra cập nhật…"
      + `check_updates`/`_check_updates_worker`/`_on_updates_checked`/`_download_update_worker`
      (`threading.Thread` + `self.after`); `main_qt.py`: `action_update` trong menu Trợ giúp
      + `UpdateCheckWorker`/`UpdateDownloadWorker` (QThread + Signal) + `check_updates`/
      `_on_updates_checked`/`_on_update_downloaded`. Có bản mới -> mở trang tải về
      (`os.startfile`) hoặc tải trực tiếp; hiện tóm tắt thay đổi + thông báo khi mới nhất/lỗi mạng)*
- [x] **V4** — GitHub Actions release. *(`.github/workflows/release.yml`: trigger tag `v*`,
      `windows-latest`, cài requirements, chạy `python test_leftover.py`, build Tk + Qt
      (`--clean-temp`), publish release kèm 2 file `.exe` qua `softprops/action-gh-release@v2`;
      `permissions: contents: write`)*
- [x] **V5** — Kiểm thử + đồng bộ. *(`test_leftover.py`: thêm `test_parse_version` +
      đăng ký trong `__main__`; `python -m py_compile ...`; `python test_leftover.py`;
      `python update_context.py` đã thêm `updater.py` vào khối AUTO api;
      cập nhật `AI_CONTEXT.md`/`ROADMAP.md`/`README.md`)*

---

## 14. Nhóm VI — Tách vỏ Launcher + cập nhật lõi siêu nhẹ
- [x] **VI1** — Vỏ khởi chạy. *(`launcher.py`: xác định `app_dir`; `apply_pending_update`
      trước; chèn `app_core.zip` vào `sys.path[0]` + purge cache `uninstaller_lib*` để
      `zipimport` nạp lõi ngoài; `try/except` tự `rollback_core_update` hoặc bỏ ZIP khỏi
      `sys.path` để fallback `_MEIPASS`; chọn UI `--ui` > `APP_UNINSTALLER_UI` > tên `.exe`
      `...Qt` > `DEFAULT_UI`)*
- [x] **VI2** — Lõi cập nhật. *(`uninstaller_lib/updater.py`: `get_app_dir`, `validate_core_zip`,
      `download_core_update` (`app_core.new.zip`), `apply_pending_update`
      (`app_core.bak.zip` + hoán đổi), `rollback_core_update`, `restart_application`;
      `check_for_updates` ưu tiên asset `app_core.zip` rồi `.exe`; `uninstaller_lib/__init__.py`
      thêm `CORE_ZIP_NAME`)*
- [x] **VI3** — Đóng gói tách vỏ. *(`build.py`: entry LUÔN là `launcher.py`; thêm
      `_BASE_HIDDEN`/`TK_HIDDEN`/`QT_HIDDEN` + `_hidden_imports_for(ui)` ép `--hidden-import`;
      `build_core_zip(output_dir)` gom `uninstaller_lib/*.py`+`main.py`+`main_qt.py` vào
      `dist/app_core.zip` (in KB + SHA-256); sau build thành công tự sinh kèm `app_core.zip`;
      cờ `--core-only` chỉ tạo nhanh ZIP, không cần PyInstaller)*
- [x] **VI4** — Giao diện cập nhật nhẹ. *(`main.py`: `_on_updates_checked` hiện
      current/latest + `notes`, hỏi tự động tải `app_core.zip` + `_core_update_worker`/
      `_on_core_update_done`/`_open_release_page` (threading + `self.after`);
      `main_qt.py`: `CoreUpdateWorker` (QThread/Signal) + `_on_core_update_done`/
      `_open_release_page`; đồng ý thì `download_core_update` → `apply_pending_update` →
      `restart_application`)*
- [x] **VI5** — Kiểm thử + đồng bộ. *(`test_leftover.py`: `test_core_update_zip`;
      `python -m py_compile build.py main.py main_qt.py launcher.py`; `python test_leftover.py`;
      `python build.py --core-only` -> `dist/app_core.zip` 58.0 KB (9 file .py) hợp lệ;
      `python update_context.py`; cập nhật `AI_CONTEXT.md`/`ROADMAP.md`/`README.md`)*

---

## Ghi chú kỹ thuật (để mốt không sửa nhầm)
- **Luật an toàn leftover BẤT BIẾN** (CẤM đổi): `_is_match`, `_is_safe_to_delete`,
  luật xoá `<root>\<publisher>`, view registry, `CREATE_NO_WINDOW`.
- **Xoá file/thư mục leftover** đi qua `move_to_recycle_bin` (`SHFileOperationW`
  + `FOF_ALLOWUNDO`, chỉ `ctypes`) trước; chỉ khi Recycle Bin thất bại mới xoá
  vĩnh viễn (`_attempt_remove`). Log `history.jsonl` ghi rõ "(Recycle Bin)" hoặc
  "(xoá vĩnh viễn)". Nếu xoá vĩnh viễn bị bỏ dở, `_remove_path` đối chiếu
  `_snapshot_paths` và báo "Xoá dở dang: đã xoá X/Y mục; còn lại ...".
- **Winget (D1–D3)** trong `enumerator.py`: mọi lệnh dùng cờ `_WINGET_FLAG`
  (`--accept-source-agreements`); `normalize_winget_id` bỏ hậu tố `|arch|ver`;
  `_get_winget_rows` cache kết quả `winget list` cho phiên (xoá bằng
  `clear_winget_cache()`; `enumerate_apps(refresh_winget=True)` buộc quét lại).
  Sau khi gỡ app, 2 UI gọi `clear_winget_cache()` để lần refresh kế tiếp chính xác.
- **Phát hiện app đang chạy (E3)** trong `leftover.py`: `list_running_images()`
  gọi `tasklist /FO CSV /NH` MỘT lần; `find_running_processes(app, images)` dò
  `.exe` trong `install_location` + `uninstall_string` rồi đối chiếu; loại trừ
  `_PROTECTED_IMAGES`. UI Qt (`main_qt.py`) dùng để cảnh báo trong hộp xác nhận.
- Backup API mới trong `uninstaller_lib/backup.py` (public):
  `list_backup_files() -> list[Path]`, `list_backup_info() -> list[dict]` (name/path/time/mtime),
  `restore_backup(reg_file) -> tuple[bool, str]` (gọi `reg import`),
  `prune_backups(max_keep=50) -> int`, `clear_backups() -> int`, hằng số `MAX_BACKUP_KEEP`.
- `main_qt.py` cần `PySide6` (đã khai báo ở `requirements.txt`).
- Sau khi sửa code: chạy `python -m py_compile <file>` và `python test_leftover.py`,
  rồi `python update_context.py` để đồng bộ `AI_CONTEXT.md`.
- **Hiệu năng (F1–F2)**:
  - `enumerator._read_values` CHỈ đọc 13 value trong `_WANTED_VALUES` bằng
    `QueryValueEx` (không dùng `EnumValue` quét toàn bộ key). Nếu sau này cần
    thêm field `AppInfo` mới, PHẢI thêm tên value tương ứng vào `_WANTED_VALUES`,
    nếu không field sẽ luôn rỗng.
  - `leftover._scan_files` quét qua `_scan_dir` với `_SCAN_MAX_DEPTH = 2`
    (root→con→cháu) và `_DIR_LIST_LIMIT = 5000` mục/thư mục. Luật an toàn
    `<root>\<publisher>` KHÔNG đổi: chỉ thêm thư mục con khớp `app.name`.
- **Đóng gói (G1)**: dùng `python build.py` (mặc định `--ui tk`, `--onefile`,
  `--windowed`). Manifest `app.manifest` nhúng `requireAdministrator` (đã kiểm tra
  có trong `.exe`) + DPI per-monitor. Icon `assets/app.ico` sinh bởi `make_icon.py`
  (ICO dạng BMP/DIB 32-bit, chỉ `struct`/`zlib` — KHÔNG cần Pillow).
  `backup.BACKUP_DIR` tự trỏ cạnh `.exe` khi chạy đóng gói (`sys.frozen`), nên
  backup KHÔNG bị mất trong thư mục tạm `_MEIPASS`. KHÔNG đưa PyInstaller vào
  `requirements.txt` (chỉ là build-time); nó nằm ở `requirements-build.txt`.
- Sau khi đóng gói, thư mục `build/` và `*.spec` là sản phẩm trung gian — có thể xoá.
- **Tối ưu đóng gói (IV1–IV2)** trong `build.py`: chèn `--exclude-module` theo UI
  qua `_excludes_for(ui)` (`QT_EXCLUDES` / `TK_EXCLUDES`). Bản `qt` bỏ
  QtWebEngine*/QtQml/QtQuick*/Qt3D*/QtMultimedia*/QtNetwork/QtSql + `tkinter`/
  `unittest`/`pydoc`/`pdb`; bản `tk` bỏ `PySide6` (tránh gom nhầm nếu máy có
  PySide6). Sau khi build in dung lượng (MB) + SHA-256 (`hashlib`, đọc theo khối)
  của `.exe`; cờ `--clean-temp` xoá `build/` + `*.spec`. LƯU Ý: đã loại
  `PySide6.QtNetwork` — nếu sau này UI Qt cần tính năng mạng thì PHẢI bỏ khỏi
  `QT_EXCLUDES`.
- **Phiên bản (G2)**: nguồn DUY NHẤT là `uninstaller_lib.__version__`.
  `main.py` / `main_qt.py` dùng `--version` và `about_text()`; `build.py` sinh
  Windows version-resource (`build/version_info.txt`) từ cùng giá trị. Khi tăng
  phiên bản, CHỈ sửa `__version__` trong `uninstaller_lib/__init__.py`.
- **MSI API (H1)** trong `uninstall.py` (chỉ `ctypes` + `msi.dll`, không thêm dep):
  - `run_uninstall` chỉ ưu tiên API khi `_prefer_msi_api(app)` khác rỗng, tức
    `product_code` là GUID hợp lệ VÀ `UninstallString` rỗng/`msiexec` (wrapper
    tuỳ biến thì tôn trọng, không dùng API).
  - `_MsiJob` chạy `MsiConfigureProductExW` trên thread nền, `wait()` chờ xong
    (tương thích `proc.wait()` của worker) → vẫn tự quét leftover sau khi gỡ.
  - Hằng số INSTALLSTATE/INSTALLUILEVEL đã ghi rõ; `INSTALLSTATE_ABSENT = 7`.
  - KHÔNG gọi `MsiConfigureProductEx` trong test (tránh gỡ thật) — `test_msi_api`
    chỉ đọc (`list_msi_products`, `msi_product_installed`, GUID giả).
- **Nhận diện bộ cài (I1–I2)** trong `uninstall.py`:
  - `_extract_exe_token` trích đường dẫn `.exe` KHÔNG kiểm tra tồn tại (khác
    `_extract_exe_path` coi như `None` nếu file đã mất) — dùng để báo "file gỡ
    đã bị xoá" trong `check_uninstaller_status`.
  - `build_quiet_command` CHỈ chèn cờ khi nhận diện rõ: Squirrel `Update.exe`
    + `--uninstall` → `-s`; WiX Burn `.exe` (không phải msiexec) + `/uninstall`
    → `/quiet /norestart`; InstallShield (`InstallShield` trong path hoặc
    `setup.exe` + `/f1`/`/s`) → `/S`. Dùng `_has_token_flag` để không nối trùng.
    Không nhận diện được → trả `""` (an toàn, tránh treo).
  - `check_uninstaller_status(app)` → `(bool, str)`: `True/OK` khi winget, GUID
    MSI hợp lệ, lệnh msiexec, hoặc `.exe` tồn tại. Giữ nguyên `can_uninstall`.
- **Ước lượng dung lượng (I3)** trong `enumerator.py`:
  - `estimate_location_size_kb` chỉ dùng `os.scandir`, tối đa 2 cấp + 1500 mục
    (`_ESTIMATE_MAX_DEPTH`, `_ESTIMATE_MAX_ENTRIES`); bỏ qua
    `_is_system_or_drive_root` (ổ đĩa gốc / Windows / System32 / SysWOW64).
  - Chỉ gọi trong `_enumerate_view` khi `EstimatedSize` thiếu (0) và có
    `InstallLocation`; không ảnh hưởng app đã có EstimatedSize.
- **Kiểm thử**: `python test_leftover.py` (nên đặt `PYTHONIOENCODING=utf-8` nếu
  console không phải UTF-8 để in tiếng Việt).
- **Phân loại độ tin cậy + mở rộng quét (II1–II2)** trong `leftover.py`:
  - `scan_leftovers` trả thêm `"confidence"` (`"high"`/`"medium"`) cho mỗi mục;
    KHÔNG đổi `"kind"`/`"path"` (tương thích ngược UI).
  - `_match_confidence` dùng ĐÚNG quy tắc `_is_match`: `"high"` khi `cand == t`,
    `"medium"` khi `len(t) >= 4 and cand.startswith(t)`, ngược lại `None`. CẤM
    nới lỏng (không thêm `t.startswith(cand)`).
  - `_item_confidence`: `entry` → high; trùng `install_location` → high; tên
    folder/key/shortcut (bỏ `.lnk`) khớp tuyệt đối → high; khớp tiền tố hoặc nằm
    trong `<root>\<publisher>` → medium.
  - `_all_file_roots()` là nguồn DUY NHẤT cho cả quét (`_file_roots` lọc tồn tại)
    lẫn chặn (`_is_safe_to_delete`); có thêm `%LOCALAPPDATA%\Programs`.
  - `_is_safe_to_delete(path, publisher="")` chặn thêm `<root>\<publisher>` cấp 1
    khi biết `publisher`; các call site trong `_scan_files`/`_scan_dir` truyền
    `app.publisher`.
  - `_scan_shortcuts` quét `.lnk` (Start Menu user + toàn máy, Desktop) tới
    `_SCAN_MAX_DEPTH`; kết quả trả về `kind: "files"`.
- **System Restore (II3)** trong `backup.py`: `create_restore_point` gọi
  PowerShell `Checkpoint-Computer -RestorePointType APPLICATION_UNINSTALL`
  (CREATE_NO_WINDOW, timeout 60s); mọi lỗi (System Restore tắt, thiếu quyền,
  giới hạn 1 lần/24h) trả `(False, msg)` chứ không raise; luôn ghi
  `history.jsonl` qua `log_action("restore_point", ...)`.
- **Tích hợp UI (III1–III3)** — 2 UI chỉ gọi API, KHÔNG chứa logic hệ thống:
  - Force Uninstall: dùng `uninstall.check_uninstaller_status(app)` -> nếu
    `(False, reason)` hoặc gỡ lỗi thì hỏi `_ask_force_uninstall`, đồng ý thì
    chạy luồng quét leftover cho đúng app đó. UI Qt truyền `app` trong kết quả
    `UninstallWorker` (thêm khóa `"app"`) để biết app nào lỗi.
  - Leftover dialog đọc `item["confidence"]` -> nhãn `[Cao]`/`[Trung bình]`;
    nút "Chọn mức Cao" chỉ tích mục `high`. Luật an toàn KHÔNG đổi: mặc định chỉ
    tích `entry`, mọi xoá đều phải qua confirm.
  - Restore Point chạy nền: Tk dùng `threading.Thread` + `self.after`;
    Qt dùng `RestorePointWorker(QObject)` + `Signal(bool, str)` qua
    `_start_worker` (đã giữ tham chiếu worker/thread chống GC).
- **Kiểm tra cập nhật (V1–V4)** — chỉ `updater.py` nói chuyện với mạng (thư viện
  chuẩn), UI chỉ hiển thị:
  - `GITHUB_REPO` là NGUỒN DUY NHẤT của repo; đổi repo chỉ sửa ở
    `uninstaller_lib/__init__.py`.
  - `parse_version` so sánh theo tuple số (`re.findall(r"\d+")`) — KHÔNG so chuỗi
    (để `1.10 > 1.9`). `check_for_updates` KHÔNG raise: 404 / lỗi mạng / JSON hỏng
    -> `ok=False` + `error`. `download_update` ghi `.part` rồi `os.replace`.
  - UI: menu Trợ giúp -> "Kiểm tra cập nhật…". Qt dùng `UpdateCheckWorker`
    (`Signal(object)` = dict) + `UpdateDownloadWorker` qua `_start_worker`.
  - `GITHUB_REPO` đã trỏ tới repo thật `mas120/go-phan-mem`; đổi repo khác chỉ sửa
    ở `uninstaller_lib/__init__.py`.
- **GitHub Actions release (V4)**: `.github/workflows/release.yml` trigger khi push
  tag `v*`; cần khớp `__version__` với tag để `check_for_updates` báo đúng. Action
  dùng `permissions: contents: write` + `GITHUB_TOKEN` để tạo Release.
- **Tách vỏ Launcher (VI1–VI5)** — `launcher.py` là entry `.exe`; lõi nằm trong
  `app_core.zip` nạp qua `zipimport`:
  - `launcher.py` KHÔNG chứa logic nghiệp vụ. Thứ tự: `apply_pending_update` →
    chèn `app_core.zip` vào `sys.path[0]` → purge `sys.modules` các module
    `uninstaller_lib*` → import động `main`/`main_qt` → `main.main()`.
  - Lỗi nạp lõi ZIP: `rollback_core_update` (nếu có `app_core.bak.zip`) hoặc bỏ ZIP
    khỏi `sys.path`, purge lại rồi chạy code đóng gói trong `_MEIPASS`.
  - Cập nhật mới = tải `app_core.zip` ghi thành `app_core.new.zip` cạnh `.exe`
    (KHÔNG ghi đè khi đang chạy); lần khởi động sau `apply_pending_update` hoán đổi
    (sao lưu bản cũ sang `app_core.bak.zip`).
  - `build.py` entry LUÔN là `launcher.py`; PHẢI giữ `--hidden-import`
    (`_hidden_imports_for(ui)`) vì UI được nạp động — thiếu là `.exe` hỏng lúc chạy.
  - Luôn build kèm `app_core.zip` (tự động sau build, hoặc `python build.py --core-only`).
    Khi phát hành: đính kèm `app_core.zip` vào GitHub Release; `check_for_updates`
    sẽ ưu tiên asset này.
