"""build.py — Đóng gói App Uninstaller thành file .exe bằng PyInstaller (G1).

Đóng gói TÁCH VỎ (Launcher + lõi):
- Vỏ `.exe` (entry `launcher.py`) chỉ chứa bộ nạp + thư viện nền; lõi ứng dụng
  (`uninstaller_lib/` + `main.py`/`main_qt.py`) nằm trong `dist/app_core.zip`,
  nạp động qua `zipimport`. Cập nhật chỉ cần thay `app_core.zip` (vài chục KB).

Đặc điểm:
- `--onefile` (mặc định): một file .exe duy nhất.
- `--windowed`: ẩn cửa sổ console (ứng dụng GUI).
- Nhúng `app.manifest` -> luôn xin quyền Administrator (UAC) khi chạy.
- Nhúng `assets/app.ico` (tự sinh bằng `make_icon.py` nếu chưa có).
- Loại bỏ module nặng không dùng (giảm dung lượng + tăng tốc giải nén):
    * `--ui qt`: bỏ QtWebEngine/QtQml/QtQuick/Qt3D/QtMultimedia/QtNetwork/QtSql
      cùng `tkinter`, `unittest`, `pydoc`, `pdb`.
    * `--ui tk`: bỏ `PySide6` (tránh gom nhầm nếu máy có cài PySide6).
- Ép `--hidden-import` cho toàn bộ thư viện chuẩn mà lõi dùng + UI được chọn
  (vì vỏ nạp UI động nên PyInstaller không tự phát hiện được).
- Sau khi build THÀNH CÔNG: in dung lượng (MB) + SHA-256 của `.exe`, rồi tự động
  gọi `build_core_zip` để sinh kèm `dist/app_core.zip`.

Cách dùng:
    pip install -r requirements-build.txt
    python build.py                 # đóng gói vỏ (UI mặc định: tkinter)
    python build.py --ui qt         # đóng gói vỏ chạy UI PySide6
    python build.py --onedir        # xuất thư mục thay vì 1 file (nhẹ khởi động)
    python build.py --console       # giữ cửa sổ console (để xem lỗi)
    python build.py --clean-temp    # xoá `build/` + `*.spec` sau khi build thành công
    python build.py --core-only     # CHỈ tạo nhanh dist/app_core.zip (không PyInstaller)

Kết quả nằm trong `dist/`.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ICON = ROOT / "assets" / "app.ico"
MANIFEST = ROOT / "app.manifest"
LAUNCHER = ROOT / "launcher.py"

#: Module nặng của PySide6/Python KHÔNG dùng cho bản Qt -> loại để giảm dung lượng.
QT_EXCLUDES = [
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtNetwork",
    "PySide6.QtSql",
    "tkinter",
    "unittest",
    "pydoc",
    "pdb",
]

#: Bản tkinter: loại PySide6 để tránh gom nhầm khi máy có cài sẵn.
TK_EXCLUDES = ["PySide6"]


def _excludes_for(ui: str) -> list[str]:
    """Danh sách module cần loại trừ theo giao diện đóng gói."""
    return list(QT_EXCLUDES if ui == "qt" else TK_EXCLUDES)


#: Thư viện chuẩn mà `uninstaller_lib/` dùng — ép PyInstaller gom đủ vào vỏ `.exe`.
#: (Vỏ `launcher.py` nạp UI động qua `importlib` nên phải khai báo tường minh.)
_BASE_HIDDEN = [
    "winreg",
    "ctypes",
    "subprocess",
    "threading",
    "dataclasses",
    "ast",
    "urllib.request",
    "zipfile",
    "shutil",
    "json",
    "uninstaller_lib.enumerator",
    "uninstaller_lib.uninstall",
    "uninstaller_lib.leftover",
    "uninstaller_lib.backup",
    "uninstaller_lib.models",
    "uninstaller_lib.updater",
]

#: Module UI + thư viện nền tương ứng (chỉ gom UI được chọn).
TK_HIDDEN = ["main", "tkinter", "tkinter.ttk", "tkinter.messagebox", "tkinter.filedialog"]
QT_HIDDEN = ["main_qt", "PySide6"]


def _hidden_imports_for(ui: str) -> list[str]:
    """Danh sách `--hidden-import` theo giao diện (vỏ + lõi + thư viện nền)."""
    return list(_BASE_HIDDEN) + list(QT_HIDDEN if ui == "qt" else TK_HIDDEN)

try:
    from uninstaller_lib import APP_NAME, CORE_ZIP_NAME, __version__
except ImportError:  # pragma: no cover - chỉ xảy ra khi chạy sai thư mục
    APP_NAME, CORE_ZIP_NAME, __version__ = "App Uninstaller", "app_core.zip", "0.0.0"

# Tên exe mặc định theo giao diện (entry luôn là `launcher.py` — vỏ nạp động).
UIS = {
    "tk": {"name": "AppUninstaller"},
    "qt": {"name": "AppUninstallerQt"},
}


def _version_tuple(version: str) -> tuple[int, int, int, int]:
    """'1.2.3-beta' -> (1, 2, 3, 0) cho FixedFileInfo."""
    parts = []
    for piece in version.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple((parts + [0, 0, 0, 0])[:4])


def _write_version_file(path: Path, exe_name: str) -> Path:
    """Sinh file version-resource cho PyInstaller (`--version-file`)."""
    v = ", ".join(str(n) for n in _version_tuple(__version__))
    content = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({v}), prodvers=({v}),
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', '{APP_NAME}'),
        StringStruct('FileDescription', '{exe_name}'),
        StringStruct('FileVersion', '{__version__}'),
        StringStruct('InternalName', '{exe_name}'),
        StringStruct('OriginalFilename', '{exe_name}.exe'),
        StringStruct('ProductName', '{APP_NAME}'),
        StringStruct('ProductVersion', '{__version__}')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _ensure_assets() -> None:
    """Đảm bảo có icon và manifest trước khi build."""
    if not MANIFEST.exists():
        sys.exit(f"Thiếu manifest: {MANIFEST}")
    if not ICON.exists():
        print(f"Chưa có icon, đang tạo: {ICON} ...")
        from make_icon import build_icon
        build_icon(ICON)


def _file_sha256(path: Path, chunk_size: int = 1 << 20) -> str:
    """Tính mã băm SHA-256 của một file (đọc theo khối để không tốn RAM)."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(chunk_size), b""):
            digest.update(block)
    return digest.hexdigest()


def _find_output(exe_name: str, onefile: bool) -> Path | None:
    """Trả về đường dẫn file .exe trong `dist/` (onefile hoặc onedir)."""
    if onefile:
        candidates = [ROOT / "dist" / f"{exe_name}.exe"]
    else:
        candidates = [
            ROOT / "dist" / exe_name / f"{exe_name}.exe",
            ROOT / "dist" / f"{exe_name}.exe",
        ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _report_output(exe_name: str, onefile: bool) -> None:
    """In dung lượng (MB) + SHA-256 của file .exe vừa tạo (kiểm tra toàn vẹn)."""
    exe = _find_output(exe_name, onefile)
    if exe is None:
        print(f"\nKhông tìm thấy file .exe trong: {ROOT / 'dist'}", file=sys.stderr)
        return
    size_mb = exe.stat().st_size / (1024 * 1024)
    digest = _file_sha256(exe)
    print("\n" + "-" * 60)
    print(f"File     : {exe}")
    print(f"Dung lượng: {size_mb:.2f} MB")
    print(f"SHA-256  : {digest}")
    print("-" * 60)


def build_core_zip(output_dir: Path | None = None) -> Path:
    """Đóng gói lõi ứng dụng thành ``app_core.zip`` (dùng cho cập nhật siêu nhẹ).

    Gồm toàn bộ file ``.py`` trong ``uninstaller_lib/`` cùng ``main.py`` và
    ``main_qt.py``, giữ đúng cấu trúc thư mục (``uninstaller_lib/...``) để vỏ
    ``launcher.py`` nạp được qua ``zipimport``.

    In ra dung lượng (KB) + SHA-256. Trả về đường dẫn file ZIP.
    """
    out_dir = Path(output_dir) if output_dir is not None else ROOT / "dist"
    out_dir.mkdir(parents=True, exist_ok=True)

    members = sorted((ROOT / "uninstaller_lib").glob("*.py"))
    for extra in (ROOT / "main.py", ROOT / "main_qt.py"):
        if extra.is_file():
            members.append(extra)

    core_zip = out_dir / CORE_ZIP_NAME
    with zipfile.ZipFile(core_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in members:
            arcname = str(path.relative_to(ROOT)).replace("\\", "/")
            zf.write(path, arcname=arcname)

    print("\n" + "-" * 60)
    print(f"Gói lõi   : {core_zip}")
    print(f"Dung lượng: {core_zip.stat().st_size / 1024:.1f} KB ({len(members)} file .py)")
    print(f"SHA-256   : {_file_sha256(core_zip)}")
    print("-" * 60)
    return core_zip


def _cleanup_temp() -> None:
    """Xoá thư mục tạm `build/` và các file `*.spec` sau khi build thành công."""
    build_dir = ROOT / "build"
    if build_dir.exists():
        shutil.rmtree(build_dir, ignore_errors=True)
        print(f"Đã xoá thư mục tạm: {build_dir}")
    for spec in ROOT.glob("*.spec"):
        try:
            spec.unlink()
            print(f"Đã xoá file spec: {spec}")
        except OSError as exc:  # pragma: no cover - best-effort
            print(f"Không xoá được {spec}: {exc}", file=sys.stderr)


def build(ui: str, onefile: bool, console: bool, clean: bool, name: str,
          excludes: list[str] | None = None) -> int:
    _ensure_assets()
    cfg = UIS[ui]
    exe_name = name or cfg["name"]
    if excludes is None:
        excludes = _excludes_for(ui)
    version_file = _write_version_file(
        ROOT / "build" / "version_info.txt", exe_name)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile" if onefile else "--onedir",
        "--console" if console else "--windowed",
        "--name", exe_name,
        "--icon", str(ICON),
        "--manifest", str(MANIFEST),
        "--version-file", str(version_file),
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT),
    ]
    # Vỏ `launcher.py` nạp UI động -> PHẢI khai báo tường minh thư viện nền + UI.
    for module in _hidden_imports_for(ui):
        cmd += ["--hidden-import", module]
    for module in excludes:
        cmd += ["--exclude-module", module]
    if clean:
        cmd.append("--clean")
    cmd.append(str(LAUNCHER))

    print("Lệnh build:\n  " + " ".join(cmd) + "\n")
    return subprocess.call(cmd, cwd=str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Đóng gói App Uninstaller (PyInstaller).")
    parser.add_argument("--ui", choices=sorted(UIS), default="tk",
                        help="Giao diện đóng gói (mặc định: tk).")
    parser.add_argument("--name", default="", help="Tên file .exe (mặc định theo UI).")
    parser.add_argument("--onedir", action="store_true",
                        help="Xuất thư mục thay vì 1 file (khởi động nhanh hơn).")
    parser.add_argument("--console", action="store_true",
                        help="Giữ cửa sổ console (mặc định: ẩn — GUI).")
    parser.add_argument("--no-clean", action="store_true",
                        help="Không xoá cache build trước khi đóng gói.")
    parser.add_argument("--clean-temp", action="store_true",
                        help="Xoá thư mục `build/` và file `*.spec` sau khi build thành công.")
    parser.add_argument("--core-only", action="store_true",
                        help="Chỉ tạo nhanh dist/app_core.zip (cập nhật nhẹ, không gọi PyInstaller).")
    args = parser.parse_args()

    # `--core-only`: chỉ đóng gói gói lõi, bỏ qua PyInstaller (chưa tới 1 giây).
    if args.core_only:
        try:
            build_core_zip(ROOT / "dist")
        except OSError as exc:
            sys.exit(f"Không tạo được app_core.zip: {exc}")
        print(f"\nXong! Gói lõi ở: {ROOT / 'dist' / CORE_ZIP_NAME}")
        return 0

    if shutil.which("pyinstaller") is None:
        try:
            import PyInstaller  # noqa: F401
        except ImportError:
            sys.exit("Chưa cài PyInstaller. Chạy: pip install -r requirements-build.txt")

    exe_name = args.name or UIS[args.ui]["name"]
    code = build(ui=args.ui, onefile=not args.onedir, console=args.console,
                 clean=not args.no_clean, name=args.name)
    if code == 0:
        print(f"\nHoàn tất! Xem kết quả trong: {ROOT / 'dist'}")
        _report_output(exe_name, onefile=not args.onedir)
        # Tách vỏ: luôn sinh kèm gói lõi `app_core.zip` để phát hành cập nhật nhẹ.
        build_core_zip(ROOT / "dist")
        if args.clean_temp:
            _cleanup_temp()
    else:
        print(f"\nĐóng gói thất bại (mã {code}).", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
