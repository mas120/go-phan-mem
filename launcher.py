"""launcher.py — Vỏ (shell) khởi chạy App Uninstaller.

Vai trò BẤT BIẾN của vỏ:
1. Xác định ``app_dir`` (thư mục chứa file ``.exe`` khi đóng gói).
2. Tự động áp dụng gói lõi đang chờ ``app_core.new.zip`` -> ``app_core.zip``
   TRƯỚC khi nạp module ứng dụng (siêu nhẹ: chỉ tải/hoán đổi vài trăm KB).
3. Nếu tồn tại ``app_core.zip`` cạnh ``.exe``, chèn vào ``sys.path[0]`` để Python
   nạp ``uninstaller_lib`` / ``main`` / ``main_qt`` trực tiếp từ ZIP (``zipimport``).
4. Chọn giao diện qua tham số ``--ui qt|tk`` / biến môi trường
   ``APP_UNINSTALLER_UI`` / mặc định theo cấu hình lúc build.

An toàn: nếu nạp từ ``app_core.zip`` lỗi (bản update hỏng), tự động khôi phục từ
``app_core.bak.zip``; nếu không có bản sao lưu thì bỏ ``app_core.zip`` khỏi
``sys.path`` để fallback về code gốc đóng gói sẵn trong ``_MEIPASS``.

CHỈ dùng thư viện chuẩn; KHÔNG import ``tkinter``.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

#: Giao diện mặc định khi build (đổi theo ``build.py --ui``).
DEFAULT_UI = "tk"

#: Đường dẫn gói lõi / bản chờ / bản sao lưu (khớp ``uninstaller_lib.updater``).
_CORE_ZIP = "app_core.zip"

# Thư mục script ở đầu sys.path để tìm ``uninstaller_lib`` khi chạy script.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


def _app_dir() -> Path:
    """Thư mục chứa file ``.exe`` (frozen) hoặc thư mục gốc project."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return _HERE


def _select_ui(argv) -> str:
    """Chọn giao diện: ``--ui qt|tk`` > ``APP_UNINSTALLER_UI`` > tên ``.exe`` > ``DEFAULT_UI``.

    Tên ``.exe`` đóng gói ``--ui qt`` là ``AppUninstallerQt`` nên khi đã frozen ta
    suy ra giao diện mặc định theo cấu hình lúc build.
    """
    chosen = ""
    args = list(argv)
    for i, arg in enumerate(args):
        if arg == "--ui" and i + 1 < len(args):
            chosen = args[i + 1]
            break
        if arg.startswith("--ui="):
            chosen = arg.split("=", 1)[1]
            break
    if not chosen:
        chosen = os.environ.get("APP_UNINSTALLER_UI") or ""
    if not chosen and getattr(sys, "frozen", False):
        if Path(sys.executable).stem.lower().endswith("qt"):
            chosen = "qt"
    if not chosen:
        chosen = DEFAULT_UI
    return "qt" if chosen.strip().lower() == "qt" else "tk"


def _insert_zip_path(zip_path: Path) -> None:
    """Chèn ``app_core.zip`` vào ``sys.path[0]`` (ưu tiên cao nhất)."""
    path = str(zip_path)
    while path in sys.path:
        sys.path.remove(path)
    sys.path.insert(0, path)


def _remove_zip_path(zip_path: Path) -> None:
    """Bỏ ``app_core.zip`` khỏi ``sys.path`` để fallback về code đóng gói."""
    path = str(zip_path)
    while path in sys.path:
        sys.path.remove(path)


def _purge_core_modules() -> None:
    """Xoá cache ``uninstaller_lib*`` để nạp lại đúng nguồn (ZIP hay bundled)."""
    for name in list(sys.modules):
        if name == "uninstaller_lib" or name.startswith("uninstaller_lib."):
            del sys.modules[name]


def _run_ui(ui: str) -> None:
    """Nạp module UI tương ứng và chạy ``main()`` của nó."""
    module_name = "main_qt" if ui == "qt" else "main"
    sys.modules.pop(module_name, None)
    module = importlib.import_module(module_name)
    module.main()


def _recover(app_dir: Path, updater_mod) -> bool:
    """Khôi phục lõi hỏng. Trả ``True`` nếu đã rollback (vẫn dùng ``app_core.zip``)."""
    if updater_mod is not None:
        try:
            if updater_mod.rollback_core_update(app_dir):
                return True
        except Exception:  # noqa: BLE001 - không để lỗi phục hồi chặn fallback
            pass
    _remove_zip_path(app_dir / _CORE_ZIP)
    return False


def main() -> int:
    """Điểm vào của vỏ: áp dụng cập nhật -> nạp lõi -> chạy UI (có fallback)."""
    app_dir = _app_dir()
    ui = _select_ui(sys.argv[1:])

    # Bước 1: áp dụng gói lõi đang chờ TRƯỚC khi nạp module ứng dụng.
    try:
        from uninstaller_lib import updater as _updater
    except Exception:  # noqa: BLE001 - thiếu lõi thì vẫn thử nạp trực tiếp
        _updater = None
    if _updater is not None:
        try:
            _updater.apply_pending_update(app_dir)
        except Exception:  # noqa: BLE001 - best-effort, không chặn khởi động
            pass

    # Bước 2: ưu tiên lõi ngoài ``app_core.zip`` (nếu có).
    core_zip = app_dir / _CORE_ZIP
    using_zip = core_zip.is_file()
    if using_zip:
        _insert_zip_path(core_zip)
    _purge_core_modules()

    # Bước 3: nạp & chạy UI, tự phục hồi nếu bản update hỏng.
    try:
        _run_ui(ui)
        return 0
    except Exception as first_error:  # noqa: BLE001
        if not using_zip:
            raise
        _recover(app_dir, _updater)
        _purge_core_modules()
        try:
            _run_ui(ui)
            return 0
        except Exception:  # noqa: BLE001 - fallback cũng lỗi -> báo lỗi gốc
            raise first_error


if __name__ == "__main__":
    raise SystemExit(main())
