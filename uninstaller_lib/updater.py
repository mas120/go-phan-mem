"""uninstaller_lib/updater.py — Kiểm tra & tải bản cập nhật từ GitHub Releases.

CHỈ dùng thư viện chuẩn (``urllib.request``, ``urllib.error``, ``json``, ``zipfile``,
``shutil``, ``sys``, ``os``, ``subprocess``, ``pathlib``). KHÔNG phụ thuộc giao diện
và KHÔNG import ``tkinter`` — tuân thủ quy tắc tách lớp của ``uninstaller_lib/``.

Hai cơ chế cập nhật:
- **Cập nhật lõi siêu nhẹ**: tải ``app_core.zip`` (chứa ``uninstaller_lib/`` +
  ``main.py``/``main_qt.py``) về cạnh ``.exe`` rồi hoán đổi — vỏ launcher nạp ZIP
  qua ``zipimport``, không cần tải lại toàn bộ ``.exe``.
- **Tải ``.exe`` đầy đủ**: fallback khi không có gói lõi.

Không hàm nào raise ra ngoài: mọi lỗi mạng/JSON/IO được chuyển thành giá trị
trả về an toàn để UI hiển thị.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from . import CORE_ZIP_NAME, GITHUB_REPO, __version__

#: Endpoint API lấy bản phát hành mới nhất (GitHub tự bỏ qua draft/prerelease).
_API_LATEST = "https://api.github.com/repos/{repo}/releases/latest"

#: GitHub yêu cầu User-Agent hợp lệ cho mọi request.
_USER_AGENT = "App-Uninstaller"

#: Kích thước mỗi khối khi tải file (256 KB).
_DOWNLOAD_CHUNK = 1024 * 256

#: Tên gói lõi mới tải về (chờ áp dụng) và bản sao lưu để rollback.
CORE_NEW_NAME = "app_core.new.zip"
CORE_BAK_NAME = "app_core.bak.zip"

#: Các file BẮT BUỘC phải có trong gói lõi để coi là hợp lệ.
_REQUIRED_MEMBER = "uninstaller_lib/__init__.py"
_ENTRY_MEMBERS = ("main.py", "main_qt.py")


# ----------------------------------------------------------- phiên bản
def parse_version(v: str) -> tuple[int, ...]:
    """Chuẩn hoá chuỗi phiên bản thành tuple số để so sánh chính xác.

    Bỏ tiền tố ``v``/``V`` và mọi ký tự không phải chữ số, rồi tách theo nhóm số.
    Ví dụ: ``"v1.2.3-beta.4"`` -> ``(1, 2, 3, 4)``; ``"1.0"`` -> ``(1, 0)``;
    chuỗi rỗng -> ``()``.
    """
    if not v:
        return ()
    text = str(v).strip().lstrip("vV")
    return tuple(int(part) for part in re.findall(r"\d+", text))


# ----------------------------------------------------------- đường dẫn
def get_app_dir() -> Path:
    """Thư mục chứa file ``.exe`` (khi đóng gói) hoặc thư mục gốc project.

    - Khi ``sys.frozen`` (PyInstaller): cạnh ``sys.executable``.
    - Khi chạy script: thư mục gốc project (cha của ``uninstaller_lib/``).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


# ----------------------------------------------------------- kiểm tra cập nhật
def _empty_result(error: str = "") -> dict:
    """Dict kết quả mặc định khi lỗi (đủ mọi khoá để UI dùng an toàn)."""
    return {
        "ok": False,
        "has_update": False,
        "current_version": "",
        "latest_version": "",
        "download_url": "",
        "release_url": "",
        "notes": "",
        "release_notes": "",  # tương thích ngược với UI hiện tại
        "asset_name": "",
        "error": error,
    }


def _pick_asset(assets) -> tuple[str, str]:
    """Chọn asset tải về: ưu tiên ``app_core.zip``, sau đó file ``.exe``.

    Trả về ``(url, tên_asset)`` hoặc ``("", "")`` nếu không có asset phù hợp.
    """
    entries = []
    for asset in assets or []:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name", ""))
        url = str(asset.get("browser_download_url") or "")
        if url:
            entries.append((name, url))
    # 1) Ưu tiên gói lõi app_core.zip (cập nhật siêu nhẹ).
    for name, url in entries:
        if name.lower() == CORE_ZIP_NAME.lower():
            return url, name
    # 2) Fallback: file .exe đầy đủ.
    for name, url in entries:
        if name.lower().endswith(".exe"):
            return url, name
    return "", ""


def check_for_updates(repo: str = GITHUB_REPO,
                      current_version: str = __version__,
                      timeout: int = 8) -> dict:
    """Kiểm tra GitHub Releases xem có bản mới hơn ``current_version`` không.

    Trả về dict: ``{"ok", "has_update", "current_version", "latest_version",
    "download_url", "release_url", "notes", "release_notes", "asset_name",
    "error"}`` (``release_notes`` giữ để tương thích ngược với UI).

    KHÔNG raise: mọi lỗi mạng/JSON đều trả ``ok=False`` kèm ``error``.
    """
    if not repo or "/" not in repo:
        return _empty_result("Chưa cấu hình GITHUB_REPO (dạng 'tài_khoản/repo').")
    url = _API_LATEST.format(repo=repo.strip())
    request = urllib.request.Request(
        url,
        headers={"User-Agent": _USER_AGENT,
                 "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return _empty_result("Không tìm thấy bản phát hành nào trên GitHub.")
        return _empty_result(f"GitHub trả lỗi HTTP {exc.code}.")
    except urllib.error.URLError as exc:
        return _empty_result(f"Không kết nối được GitHub: {exc.reason}")
    except ValueError:
        return _empty_result("Dữ liệu GitHub trả về không hợp lệ (JSON).")
    except Exception as exc:  # noqa: BLE001 - tuyệt đối không để lỗi lọt ra UI
        return _empty_result(f"Lỗi không xác định khi kiểm tra cập nhật: {exc}")

    if not isinstance(data, dict):
        return _empty_result("Dữ liệu GitHub trả về không hợp lệ.")

    tag = str(data.get("tag_name") or "").strip()
    latest = parse_version(tag)
    current = parse_version(current_version)
    notes = str(data.get("body") or "").strip()
    release_url = str(data.get("html_url") or "")
    download_url, asset_name = _pick_asset(data.get("assets"))
    # Không có asset đính kèm -> fallback sang zipball (mã nguồn) hoặc trang release.
    if not download_url:
        fallback = str(data.get("zipball_url") or "")
        if fallback:
            download_url, asset_name = fallback, "zipball"
        elif release_url:
            download_url, asset_name = release_url, "release"
    return {
        "ok": True,
        "has_update": bool(latest and current and latest > current),
        "current_version": str(current_version),
        "latest_version": tag,
        "download_url": download_url,
        "release_url": release_url,
        "notes": notes,
        "release_notes": notes,
        "asset_name": asset_name,
        "error": "",
    }


# ----------------------------------------------------------- gói lõi
def _safe_unlink(path: Path) -> None:
    """Xoá file best-effort, nuốt mọi lỗi IO."""
    try:
        path.unlink()
    except OSError:
        pass


def validate_core_zip(zip_path: Path) -> tuple[bool, str]:
    """Kiểm tra ``app_core.zip`` có hợp lệ để nạp/cập nhật lõi hay không.

    Kiểm tra: là file ZIP, không hỏng CRC (``testzip``), và chứa
    ``uninstaller_lib/__init__.py`` cùng ``main.py`` hoặc ``main_qt.py``.

    Trả về ``(True, "")`` khi hợp lệ, ngược lại ``(False, lý_do)``.
    """
    path = Path(zip_path)
    if not path.is_file():
        return False, f"Không tìm thấy gói lõi: {path}"
    if not zipfile.is_zipfile(path):
        return False, "Tệp không phải định dạng ZIP hợp lệ."
    try:
        with zipfile.ZipFile(path) as zf:
            bad = zf.testzip()
            if bad is not None:
                return False, f"Gói ZIP bị hỏng (CRC lỗi tại '{bad}')."
            names = {str(n).replace("\\", "/") for n in zf.namelist()}
    except (zipfile.BadZipFile, OSError) as exc:
        return False, f"Không đọc được gói ZIP: {exc}"
    if _REQUIRED_MEMBER not in names:
        return False, f"Gói thiếu thành phần bắt buộc '{_REQUIRED_MEMBER}'."
    if not any(entry in names for entry in _ENTRY_MEMBERS):
        return False, "Gói thiếu điểm khởi chạy 'main.py' hoặc 'main_qt.py'."
    return True, ""


def download_core_update(download_url: str,
                         target_dir: Path | None = None) -> tuple[bool, str]:
    """Tải gói lõi ``app_core.zip`` về ``target_dir`` dưới tên ``app_core.new.zip``.

    Mặc định ``target_dir`` là ``get_app_dir()`` (cạnh ``.exe``). Tải vào file
    ``.part`` rồi ``os.replace`` để tránh file dở dang, sau đó ``validate_core_zip``.

    Trả về ``(True, đường_dẫn_gói)`` khi hợp lệ, ngược lại ``(False, lý_do)``.
    """
    if not download_url:
        return False, "Bản phát hành không có URL tải về."
    base = Path(target_dir) if target_dir is not None else get_app_dir()
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, f"Không tạo được thư mục ứng dụng: {exc}"

    new_zip = base / CORE_NEW_NAME
    part = base / (CORE_NEW_NAME + ".part")
    request = urllib.request.Request(
        download_url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, \
                open(part, "wb") as fh:
            shutil.copyfileobj(response, fh, _DOWNLOAD_CHUNK)
        os.replace(part, new_zip)
    except (urllib.error.URLError, OSError) as exc:
        _safe_unlink(part)
        return False, f"Tải thất bại: {exc}"
    except Exception as exc:  # noqa: BLE001 - không để lỗi lọt ra UI
        _safe_unlink(part)
        return False, f"Tải thất bại: {exc}"

    ok, reason = validate_core_zip(new_zip)
    if not ok:
        _safe_unlink(new_zip)
        return False, f"Gói tải về không hợp lệ: {reason}"
    return True, str(new_zip)


def apply_pending_update(app_dir: Path | None = None) -> tuple[bool, str]:
    """Áp dụng gói lõi đang chờ (``app_core.new.zip``) thành ``app_core.zip``.

    Sao lưu ``app_core.zip`` hiện tại sang ``app_core.bak.zip`` rồi hoán đổi gói
    mới vào chỗ. Chỉ áp dụng khi gói chờ tồn tại VÀ hợp lệ.

    Trả về ``(True, đường_dẫn_core)`` khi thành công, ngược lại ``(False, lý_do)``.
    """
    base = Path(app_dir) if app_dir is not None else get_app_dir()
    new_zip = base / CORE_NEW_NAME
    if not new_zip.is_file():
        return False, "Không có bản cập nhật lõi nào đang chờ."
    ok, reason = validate_core_zip(new_zip)
    if not ok:
        _safe_unlink(new_zip)
        return False, f"Gói chờ không hợp lệ: {reason}"

    core = base / CORE_ZIP_NAME
    bak = base / CORE_BAK_NAME
    try:
        if core.is_file():
            os.replace(core, bak)
        os.replace(new_zip, core)
    except OSError as exc:
        # Cố khôi phục bản cũ nếu hoán đổi thất bại giữa chừng.
        if bak.is_file() and not core.is_file():
            try:
                os.replace(bak, core)
            except OSError:
                pass
        return False, f"Không áp dụng được cập nhật: {exc}"
    return True, str(core)


def rollback_core_update(app_dir: Path | None = None) -> bool:
    """Khôi phục lõi cũ từ ``app_core.bak.zip`` đè lên ``app_core.zip``.

    Trả về ``True`` nếu khôi phục thành công (có bản sao lưu và hoán đổi được).
    """
    base = Path(app_dir) if app_dir is not None else get_app_dir()
    bak = base / CORE_BAK_NAME
    core = base / CORE_ZIP_NAME
    if not bak.is_file():
        return False
    try:
        os.replace(bak, core)
    except OSError:
        return False
    return True


# ----------------------------------------------------------- tải .exe đầy đủ
def _default_download_dir() -> Path:
    """Thư mục Downloads của người dùng; fallback về thư mục tạm."""
    home = os.path.expanduser("~")
    downloads = Path(home) / "Downloads"
    if downloads.is_dir():
        return downloads
    return Path(tempfile.gettempdir())


def download_update(download_url: str,
                    dest_dir: Path | None = None) -> tuple[bool, str]:
    """Tải file ``.exe`` bản mới về ``dest_dir`` (mặc định: thư mục Downloads).

    Tải vào file ``.part`` rồi ``os.replace`` để tránh file dở dang.

    Trả về ``(True, đường_dẫn_file)`` khi thành công, ngược lại ``(False, lỗi)``.
    """
    if not download_url:
        return False, "Bản phát hành không có URL tải về."
    name = os.path.basename(download_url.split("?", 1)[0]) or "AppUninstaller_update.exe"
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name).lstrip(".") or "AppUninstaller_update.exe"
    target_dir = Path(dest_dir) if dest_dir is not None else _default_download_dir()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, f"Không tạo được thư mục tải về: {exc}"

    dest = target_dir / name
    tmp = target_dir / (name + ".part")
    request = urllib.request.Request(
        download_url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, \
                open(tmp, "wb") as fh:
            while True:
                chunk = response.read(_DOWNLOAD_CHUNK)
                if not chunk:
                    break
                fh.write(chunk)
        os.replace(tmp, dest)
    except (urllib.error.URLError, OSError) as exc:
        _safe_unlink(tmp)
        return False, f"Tải thất bại: {exc}"
    except Exception as exc:  # noqa: BLE001 - không để lỗi lọt ra UI
        _safe_unlink(tmp)
        return False, f"Tải thất bại: {exc}"
    return True, str(dest)


# ----------------------------------------------------------- khởi chạy lại
def restart_application() -> None:
    """Khởi chạy lại tiến trình hiện tại rồi thoát tiến trình cũ.

    - Đóng gói (``sys.frozen``): chạy lại ``sys.executable`` (file ``.exe``).
    - Chạy script: chạy lại ``[sys.executable] + sys.argv``.
    """
    if getattr(sys, "frozen", False):
        args = [sys.executable]
    else:
        args = [sys.executable] + list(sys.argv)
    subprocess.Popen(args)
    sys.exit(0)
