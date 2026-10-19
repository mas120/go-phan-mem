"""Quét và dọn leftover (file + registry còn sót) sau khi gỡ cài đặt app.

Phương pháp heuristic (kiểu Revo Uninstaller):
- Registry: so sánh tên key con của HKCU\\Software, HKLM\\Software (view 64 & 32-bit),
  tối đa 2 cấp, với tên app / nhà phát hành.
- File: tìm theo tên app / publisher trong Program Files, ProgramData, AppData
  (Local/Roaming/LocalLow), Desktop và Start Menu.

Tất cả kết quả đều là "gợi ý" — GUI bắt buộc người dùng duyệt và xác nhận trước khi xoá.
"""
import os
import re
import stat
import shutil
import ctypes
import subprocess
import time
import winreg

# Sao lưu an toàn & ghi nhật ký thao tác xoá (backup.py — chỉ thư viện chuẩn).
from . import backup

# Cờ SHFileOperationW: xoá → Recycle Bin (FO_DELETE + FOF_ALLOWUNDO), ẩn UI.
_FO_DELETE = 0x0003
_FOF_SILENT = 0x0004
_FOF_NOCONFIRMATION = 0x0010
_FOF_ALLOWUNDO = 0x0040          # cho phép khôi phục từ Recycle Bin
_FOF_NOERRORUI = 0x0400


class _SHFILEOPSTRUCTW(ctypes.Structure):
    """Cấu trúc SHFILEOPSTRUCTW cho ``SHFileOperationW`` (thùng rác Windows)."""

    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("wFunc", ctypes.c_uint),
        ("pFrom", ctypes.c_wchar_p),
        ("pTo", ctypes.c_wchar_p),
        ("fFlags", ctypes.c_uint16),
        ("fAnyOperationsAborted", ctypes.c_int),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", ctypes.c_wchar_p),
    ]

# Các root "Software" cần quét: (tên hiển thị, hive, subkey, access_view)
_SOFTWARE_ROOTS = [
    ("HKCU", winreg.HKEY_CURRENT_USER, r"Software", 0),
    ("HKLM", winreg.HKEY_LOCAL_MACHINE, r"Software", winreg.KEY_WOW64_64KEY),
    ("HKLM", winreg.HKEY_LOCAL_MACHINE, r"Software", winreg.KEY_WOW64_32KEY),
]

# Các tiến trình hệ thống Windows tuyệt đối không được phép kill (bảo vệ an toàn).
_PROTECTED_IMAGES = {
    "explorer.exe", "cmd.exe", "python.exe", "svchost.exe",
    "conhost.exe", "csrss.exe", "smss.exe", "wininit.exe",
    "winlogon.exe", "services.exe", "lsass.exe", "dwm.exe",
    "taskhost.exe", "taskhostw.exe", "dllhost.exe", "spoolsv.exe",
    "fontdrvhost.exe", "runtimebroker.exe", "sihost.exe",
    "startmenuexperiencehost.exe", "powershell.exe", "powershell_ise.exe",
    "wmiprvse.exe", "searchindexer.exe", "securityhealthservice.exe",
    "securityhealthsystray.exe", "systemsettings.exe",
}

# Cờ tạo tiến trình con mà không hiện cửa sổ console (Windows).
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def _tokenize(text: str) -> str:
    """Đưa tên về chữ + số thường, bỏ ký tự đặc biệt, dùng để so sánh."""
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _is_match(candidate: str, targets) -> bool:
    """So khớp tương đối giữa 1 tên (folder/key) và danh sách tên chuẩn.

    An toàn: chỉ trả về True khi khớp chính xác (`cand == t`), hoặc khi tên
    chuẩn đủ dài (`len(t) >= 4`) và tên cần so sánh bắt đầu bằng tên chuẩn.
    Không dùng `t.startswith(cand)` để tránh false positive với thư mục tên ngắn.
    """
    cand = _tokenize(candidate)
    if not cand:
        return False
    for t in targets:
        if not t:
            continue
        if cand == t:
            return True
        if len(t) >= 4 and cand.startswith(t):
            return True
    return False


def _match_confidence(candidate: str, targets) -> str | None:
    """Mức độ tin cậy của một tên so với danh sách tên chuẩn.

    Dùng ĐÚNG quy tắc của ``_is_match`` (KHÔNG nới lỏng):
    - `"high"`   khi khớp chính xác `cand == t`.
    - `"medium"` khi khớp tiền tố `len(t) >= 4 and cand.startswith(t)`.
    - `None`     khi không khớp.

    Vì vậy giá trị trả về khác ``None`` khi và chỉ khi ``_is_match`` trả ``True``.
    """
    cand = _tokenize(candidate)
    if not cand:
        return None
    best = None
    for t in targets:
        if not t:
            continue
        if cand == t:
            return "high"
        if len(t) >= 4 and cand.startswith(t):
            best = "medium"
    return best


def _scan_registry(app) -> list:
    """Tìm các key leftover dưới các root Software (tối đa 2 cấp).

    An toàn: KHÔNG đưa key cấp 1 trùng với `publisher` vào kết quả. Chỉ mở key
    publisher ra để quét cấp 2 bên trong; cấp 2 & cấp 1 chỉ thêm subkey khớp
    với `app.name`.
    """
    name_t = _tokenize(app.name)
    pub_t = _tokenize(app.publisher)
    found = []
    for hname, hive, subkey, access in _SOFTWARE_ROOTS:
        try:
            with winreg.OpenKey(hive, subkey, 0, access | winreg.KEY_READ) as root:
                index = 0
                while True:
                    try:
                        kname = winreg.EnumKey(root, index)
                    except OSError:
                        break
                    index += 1
                    if not kname:
                        continue
                    path = f"{hname}\\{subkey}\\{kname}"
                    name_hit = bool(name_t) and _is_match(kname, [name_t])
                    pub_hit = bool(pub_t) and _is_match(kname, [pub_t])
                    if not (name_hit or pub_hit):
                        continue

                    # Cấp 1: chỉ thêm khi khớp với tên app, không thêm key publisher.
                    if name_hit and path not in found:
                        found.append(path)

                    # Quét cấp 2 bên trong (kiểu Publisher\\AppName):
                    # chỉ thêm subkey khớp với tên app.
                    try:
                        with winreg.OpenKey(root, kname) as child_root:
                            j = 0
                            while True:
                                try:
                                    cname = winreg.EnumKey(child_root, j)
                                except OSError:
                                    break
                                j += 1
                                if name_t and _is_match(cname, [name_t]):
                                    cpath = f"{path}\\{cname}"
                                    if cpath not in found:
                                        found.append(cpath)
                    except OSError:
                        pass
        except OSError:
            pass
    return found


def _all_file_roots() -> list:
    """Tất cả thư mục gốc quét leftover (kể cả chưa tồn tại).

    Dùng cho chốt an toàn ``_is_safe_to_delete`` để bảo vệ tuyệt đối các root
    mới (``%LOCALAPPDATA%\\Programs``, ``%PROGRAMDATA%``) ngay cả khi chúng
    chưa có trên đĩa.
    """
    roots = []
    for var in ("LOCALAPPDATA", "APPDATA", "PROGRAMDATA",
                "PROGRAMFILES", "PROGRAMFILES(X86)"):
        val = os.environ.get(var, "").strip()
        if val:
            roots.append(val)
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if local:
        roots.append(os.path.join(local, "Programs"))
    user = os.environ.get("USERPROFILE", "").strip()
    pub = os.environ.get("PUBLIC", "").strip()
    if user:
        roots.append(os.path.join(user, "Desktop"))
        roots.append(os.path.join(user, "AppData", "LocalLow"))
        roots.append(os.path.join(user, "AppData", "Roaming",
                                  "Microsoft", "Windows", "Start Menu", "Programs"))
    if pub:
        roots.append(os.path.join(pub, "Desktop"))
        roots.append(os.path.join(pub, "Microsoft", "Windows",
                                  "Start Menu", "Programs"))
    return roots


def _file_roots() -> list:
    """Các thư mục gốc cần quét leftover (chỉ trả về thư mục tồn tại)."""
    return [r for r in _all_file_roots() if r and os.path.isdir(r)]


def _is_safe_to_delete(path: str, publisher: str = "") -> bool:
    """Chặn xoá các đường dẫn là thư mục hệ thống / ổ đĩa gốc / root.

    Lớp bảo vệ cuối cùng: nếu đường dẫn trùng với một trong các thư mục gốc
    (Program Files, ProgramData, AppData, Desktop, Start Menu,
    ``%LOCALAPPDATA%\\Programs``...) hoặc thư mục hệ thống (Windows, System32,
    SysWOW64, System\\drivers), trả về False để không bao giờ tự ý xoá.

    Nếu truyền ``publisher``, chặn thêm thư mục ``<root>\\<publisher>`` cấp 1
    (luật an toàn BẤT BIẾN: không xoá thư mục publisher cấp 1).
    """
    if not path:
        return False
    try:
        norm = os.path.normpath(path)
        norm_l = norm.lower()
        # Là gốc ổ đĩa (vd C:\) -> không cho xoá.
        drive, tail = os.path.splitdrive(norm)
        if drive and not tail.rstrip("\\/"):
            return False

        blocked = set()
        for r in _all_file_roots():
            blocked.add(os.path.normpath(r).lower())
        windir = os.environ.get("WINDIR", r"C:\Windows").strip()
        blocked.add(os.path.normpath(windir).lower())
        blocked.add(os.path.normpath(os.path.join(windir, "System32")).lower())
        blocked.add(os.path.normpath(os.path.join(windir, "SysWOW64")).lower())
        blocked.add(os.path.normpath(os.path.join(windir, "System", "drivers")).lower())

        if norm_l in blocked:
            return False

        # Cấm xoá thẳng thư mục <root>\<publisher> cấp 1.
        pub_t = _tokenize(publisher)
        if pub_t:
            parent = os.path.normpath(os.path.dirname(norm)).lower()
            if parent in blocked and _tokenize(os.path.basename(norm)) == pub_t:
                return False
        return True
    except Exception:
        return False


# Giới hạn độ sâu quét leftover (F2): root (0) -> con (1) -> cháu (2).
# Các root như `Program Files` có thể rất rộng/sâu — không quét quá sâu để tránh chậm.
_SCAN_MAX_DEPTH = 2
# Giới hạn số mục liệt kê mỗi thư mục khi quét (chống thư mục khổng lồ).
_DIR_LIST_LIMIT = 5000


def _scan_files(app) -> list:
    """Tìm thư mục/file leftover theo tên app & publisher (an toàn).

    KHÔNG bao giờ thêm thẳng thư mục `<root>\\<publisher>` vào kết quả. Chỉ kiểm
    tra các đường dẫn con (`<root>\\<app.name>`, `<root>\\<publisher>\\<app.name>`)
    và quét bên trong thư mục publisher để tìm thư mục con khớp với app.name.

    Độ sâu quét bị giới hạn bởi ``_SCAN_MAX_DEPTH`` (F2) để không quét quá sâu
    trong các root lớn như ``Program Files``.
    """
    name_t = _tokenize(app.name)
    pub_t = _tokenize(app.publisher)
    found = []
    roots = _file_roots()

    # Đường dẫn trực tiếp: <root>\\<name>, <root>\\<publisher>\\<name>.
    # KHÔNG thêm <root>\\<publisher> trực tiếp.
    direct = [app.name]
    if app.publisher:
        direct.append(os.path.join(app.publisher, app.name))
    for root in roots:
        for rel in direct:
            if not rel:
                continue
            p = os.path.normpath(os.path.join(root, rel))
            if (os.path.lexists(p) and _is_safe_to_delete(p, app.publisher)
                    and p not in found):
                found.append(p)

    # Quét con trong các root, giới hạn độ sâu + số mục mỗi thư mục (F2).
    for root in roots:
        _scan_dir(root, 0, name_t, pub_t, found, app.publisher)

    # Shortcut (.lnk) còn sót trong Start Menu / Desktop (Nhóm II).
    _scan_shortcuts(name_t, found)

    # Thư mục cài đặt (InstallLocation) có thể còn sót.
    if app.install_location:
        p = os.path.normpath(app.install_location)
        if (os.path.lexists(p) and _is_safe_to_delete(p, app.publisher)
                and p not in found):
            found.append(p)

    return found


def _shortcut_roots() -> list:
    """Thư mục chứa shortcut (Start Menu Programs + Desktop) đang tồn tại."""
    roots = []
    appdata = os.environ.get("APPDATA", "").strip()
    progdata = os.environ.get("PROGRAMDATA", "").strip()
    user = os.environ.get("USERPROFILE", "").strip()
    pub = os.environ.get("PUBLIC", "").strip()
    if appdata:
        roots.append(os.path.join(appdata, "Microsoft", "Windows",
                                  "Start Menu", "Programs"))
    if progdata:
        roots.append(os.path.join(progdata, "Microsoft", "Windows",
                                  "Start Menu", "Programs"))
    if user:
        roots.append(os.path.join(user, "Desktop"))
    if pub:
        roots.append(os.path.join(pub, "Desktop"))
    return [r for r in roots if r and os.path.isdir(r)]


def _scan_shortcuts(name_t: str, found: list) -> None:
    """Tìm file shortcut ``.lnk`` có tên (bỏ đuôi) khớp ``app.name``.

    Quét Start Menu Programs (của người dùng + toàn máy) và Desktop, giới hạn
    độ sâu ``_SCAN_MAX_DEPTH`` và số mục mỗi thư mục ``_DIR_LIST_LIMIT``.
    Kết quả trả về dưới dạng đường dẫn file ``.lnk`` (kind ``"files"``).
    """
    if not name_t:
        return
    for root in _shortcut_roots():
        stack = [(root, 0)]
        while stack:
            current, depth = stack.pop()
            try:
                entries = os.listdir(current)
            except OSError:
                continue
            for entry in entries[:_DIR_LIST_LIMIT]:
                child = os.path.normpath(os.path.join(current, entry))
                if entry.lower().endswith(".lnk"):
                    stem = entry[:-4]
                    if _is_match(stem, [name_t]) and child not in found:
                        found.append(child)
                elif os.path.isdir(child) and depth < _SCAN_MAX_DEPTH:
                    stack.append((child, depth + 1))


def _scan_dir(path: str, depth: int, name_t: str, pub_t: str, found: list,
              publisher: str = "") -> None:
    """Quét con của ``path`` tới độ sâu tối đa ``_SCAN_MAX_DEPTH`` (F2).

    An toàn: KHÔNG bao giờ thêm thư mục mức 1 trùng ``publisher`` vào kết quả —
    chỉ mở nó ra để tìm thư mục con khớp ``app.name`` (giữ nguyên luật bất biến
    xoá `<root>\\<publisher>`). ``depth`` là độ sâu của ``path`` so với root
    (root = 0); không bao giờ quét quá ``_SCAN_MAX_DEPTH`` cấp con.
    """
    if depth >= _SCAN_MAX_DEPTH:
        return
    try:
        entries = os.listdir(path)
    except OSError:
        return
    for entry in entries[:_DIR_LIST_LIMIT]:
        child = os.path.normpath(os.path.join(path, entry))
        if child in found:
            continue
        entry_t = _tokenize(entry)
        # Chỉ thêm khi entry khớp với tên app (không thêm thư mục publisher).
        if (name_t and entry_t and _is_match(entry, [name_t])
                and os.path.lexists(child)
                and _is_safe_to_delete(child, publisher)):
            found.append(child)
        # Quét bên trong thư mục publisher: tìm thư mục con khớp app.name.
        if (pub_t and entry_t == pub_t and os.path.isdir(child)
                and _is_safe_to_delete(child, publisher)
                and depth + 1 < _SCAN_MAX_DEPTH):
            _scan_dir(child, depth + 1, name_t, pub_t, found, publisher)


def find_uninstall_entry(app) -> list:
    """Đường dẫn các entry gỡ còn tồn tại trong registry (HKLM view 64/32, HKCU)."""
    # App winget: registry_key chứa app_id chứ không phải nhánh registry còn
    # sót, nên không có uninstall entry để tìm — trả về rỗng ngay.
    if getattr(app, "source", "") == "winget":
        return []
    sub = (app.registry_key or "").replace("/", "\\").lstrip("\\")
    if not sub:
        return []
    keys = []
    for hname, hive, access in (
            ("HKLM", winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),
            ("HKLM", winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
            ("HKCU", winreg.HKEY_CURRENT_USER, 0)):
        try:
            with winreg.OpenKey(hive, sub, 0, access | winreg.KEY_READ):
                keys.append(f"{hname}\\{sub}")
        except OSError:
            pass
    return keys


def _has_ancestor_named(path: str, pub_t: str) -> bool:
    """True nếu ``path`` nằm trong một thư mục tổ tiên khớp ``pub_t``.

    Dùng cho mục tin cậy "medium": leftover nằm trong thư mục con của
    ``<root>\\<publisher>``.
    """
    if not pub_t:
        return False
    current = os.path.dirname(os.path.normpath(path))
    while current and current != os.path.dirname(current):
        if _tokenize(os.path.basename(current)) == pub_t:
            return True
        current = os.path.dirname(current)
    return False


def _item_confidence(kind: str, path: str, name_t: str, pub_t: str,
                     install_norm: str) -> str:
    """Mức tin cậy của một mục leftover: ``"high"`` hoặc ``"medium"``.

    - ``"high"``: ``kind == "entry"``; trùng khớp chính xác ``install_location``;
      hoặc tên folder/key/shortcut khớp tuyệt đối (``cand == t``).
    - ``"medium"``: khớp tiền tố, hoặc nằm trong thư mục con của
      ``<root>\\<publisher>``.
    """
    if kind == "entry":
        return "high"
    if install_norm:
        try:
            if os.path.normcase(os.path.normpath(path)) == install_norm:
                return "high"
        except (OSError, ValueError):
            pass
    leaf = os.path.basename(os.path.normpath(path))
    if leaf.lower().endswith(".lnk"):
        leaf = leaf[:-4]
    conf = _match_confidence(leaf, [name_t])
    if conf == "high":
        return "high"
    if _has_ancestor_named(path, pub_t):
        return "medium"
    return conf or "medium"


def scan_leftovers(app) -> list:
    """Quét toàn bộ leftover.

    Trả về list các dict ``{"kind": "registry"|"files"|"entry", "path": "...",
    "confidence": "high"|"medium"}``. Hai khóa ``kind``/``path`` được giữ nguyên
    (tương thích ngược 100% với các UI hiện có); ``confidence`` là thông tin bổ
    sung để UI ưu tiên hiển thị/duyệt mục tin cậy cao trước.
    """
    items = []
    seen = set()
    name_t = _tokenize(app.name)
    pub_t = _tokenize(app.publisher)
    install_norm = ""
    if getattr(app, "install_location", ""):
        try:
            install_norm = os.path.normcase(
                os.path.normpath(app.install_location))
        except (OSError, ValueError):
            install_norm = ""

    def add(kind, path):
        norm = path.replace("/", "\\")
        key = (kind, norm.lower())
        if norm and key not in seen:
            seen.add(key)
            items.append({
                "kind": kind,
                "path": norm,
                "confidence": _item_confidence(
                    kind, norm, name_t, pub_t, install_norm),
            })

    for p in _scan_registry(app):
        add("registry", p)
    for p in _scan_files(app):
        add("files", p)
    for p in find_uninstall_entry(app):
        add("entry", p)
    return items
# --------------------------------------------------------------------------
# Xoá an toàn
# --------------------------------------------------------------------------
def _delete_key_recursive(hive, subpath: str, access: int):
    """Xoá một registry key kèm toàn bộ key con (từ dưới lên).

    Dùng `DeleteKeyEx` với cùng `access` (KEY_WOW64_64KEY / KEY_WOW64_32KEY)
    khi `OpenKey` để tránh lỗi "không tìm thấy key" ở view khác tiến trình Python.
    """
    try:
        with winreg.OpenKey(hive, subpath, 0,
                            access | winreg.KEY_READ | winreg.KEY_WRITE) as key:
            # Gom toàn bộ key con TRƯỚC khi xoá (xoá sẽ thay đổi thứ tự liệt kê).
            children = []
            index = 0
            while True:
                try:
                    child = winreg.EnumKey(key, index)
                except OSError:
                    break
                children.append(child)
                index += 1
            for child in children:
                child_path = f"{subpath}\\{child}"
                _delete_key_recursive(hive, child_path, access)
        winreg.DeleteKeyEx(hive, subpath, access, 0)
        return None
    except OSError as exc:
        return f"Không thể xoá registry '{subpath}': {exc}"


def delete_registry_key(path: str, app_name: str = ""):
    """Xoá key registry (cả subtree) theo 'HKCU\\...' hoặc 'HKLM\\...'.

    Trước khi xoá, tự động sao lưu nhánh registry ra file .reg (backup.py) rồi
    mới gọi `_delete_key_recursive`; kết quả được ghi vào backups/history.jsonl.
    Với HKLM, thử xoá trên cả 2 view 64-bit và 32-bit: key tồn tại ở view nào
    thì xoá ở view đó (trả về thành công nếu xoá được ít nhất 1 view).
    Trả về (ok: bool, err: str).
    """
    parts = path.replace("/", "\\").split("\\")
    hive_name = parts[0].upper()
    if hive_name == "HKCU":
        hive = winreg.HKEY_CURRENT_USER
    elif hive_name == "HKLM":
        hive = winreg.HKEY_LOCAL_MACHINE
    else:
        return False, f"Không nhận diện hive '{parts[0]}'."
    sub = "\\".join(parts[1:])

    # Sao lưu an toàn TRƯỚC khi xoá (best-effort, không chặn thao tác xoá).
    name = app_name or parts[-1]
    backup_ok, backup_msg = backup.export_registry_key(path, name)

    views = ([winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY]
             if hive_name == "HKLM" else [0])
    err = ""
    found = False
    for access in views:
        err_this = _delete_key_recursive(hive, sub, access)
        if not err_this:
            found = True
        else:
            err = err_this
    if found:
        ok, err = True, ""
    else:
        ok, err = False, err

    # Ghi nhật ký thao tác xoá (best-effort, không chặn kết quả xoá).
    results = ["OK" if ok else f"LỖI: {err}"]
    if not backup_ok:
        results.append(f"[SAO LƯU] {backup_msg}")
    backup.log_action("delete_registry", name,
                      [{"kind": "registry", "path": path}], results)
    return ok, err


def _force_remove(func, path, _exc_info):
    """Bỏ thuộc tính read-only rồi gọi lại func (dùng cho xoá file/thư mục)."""
    try:
        os.chmod(path, stat.S_IWRITE)
    except OSError:
        pass
    try:
        func(path)
    except OSError:
        raise


def kill_processes_in_dir(folder_path: str) -> list[str]:
    """Buộc dừng các tiến trình trùng tên với file `.exe` trong folder_path.

    Chỉ áp dụng khi `folder_path` là một thư mục đang tồn tại: duyệt toàn bộ
    file `.exe` bên trong (kể cả thư mục con), gọi `taskkill /F /IM <tên> /T` với
    cờ CREATE_NO_WINDOW để xoá mọi tiến trình trùng tên. Các tiến trình hệ thống
    Windows (trong _PROTECTED_IMAGES) KHÔNG bao giờ bị kill.
    Trả về danh sách tên file `.exe` (kèm đuôi) đã dừng thành công.
    """
    if not folder_path or not os.path.isdir(folder_path):
        return []
    exes = []
    for root, _dirs, files in os.walk(folder_path):
        for fname in files:
            if fname.lower().endswith(".exe"):
                exes.append(fname)
    stopped = []
    for fname in sorted(set(exes)):
        if fname.lower() in _PROTECTED_IMAGES:
            continue
        proc = subprocess.run(
            ["taskkill", "/F", "/IM", fname, "/T"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_CREATE_NO_WINDOW,
        )
        if proc.returncode == 0:
            stopped.append(fname)
    return stopped


# Giới hạn số file quét khi dò tên .exe của một ứng dụng (tránh quét cây quá lớn).
_CANDIDATE_SCAN_LIMIT = 4000


def _candidate_exe_names(app) -> set:
    """Tập tên file ``.exe`` (chữ thường) có thể thuộc về ứng dụng.

    Dò trong ``install_location`` (giới hạn ``_CANDIDATE_SCAN_LIMIT`` file) và bổ
    sung tên ``.exe`` trích từ ``uninstall_string``.
    """
    names = set()
    loc = (app.install_location or "").strip()
    if loc and os.path.isdir(loc):
        count = 0
        for root, _dirs, files in os.walk(loc):
            for fname in files:
                if fname.lower().endswith(".exe"):
                    names.add(fname.lower())
                    count += 1
            if count >= _CANDIDATE_SCAN_LIMIT:
                break
    us = getattr(app, "uninstall_string", "") or ""
    match = (re.search(r'"([^"]+\.exe)"', us, re.IGNORECASE)
             or re.search(r"([^\s\"']+\.exe)", us, re.IGNORECASE))
    if match:
        base = os.path.basename(match.group(1)).lower()
        if base:
            names.add(base)
    return names


def list_running_images() -> set:
    """Tập tên image (chữ thường) của mọi tiến trình đang chạy (qua ``tasklist``).

    Trả về set rỗng nếu không gọi được ``tasklist``. Dùng làm đầu vào cho
    ``find_running_processes`` để chỉ chạy ``tasklist`` MỘT lần cho nhiều app.
    """
    images = set()
    try:
        proc = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", creationflags=_CREATE_NO_WINDOW, timeout=15)
    except (OSError, FileNotFoundError, subprocess.TimeoutExpired):
        return images
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if len(line) < 3 or not line.startswith('"'):
            continue
        end = line.find('"', 1)
        if end > 1:
            images.add(line[1:end].lower())
    return images


def find_running_processes(app, running_images: set | None = None) -> list[str]:
    """Tên các tiến trình của ``app`` đang chạy (để cảnh báo trước khi gỡ/dọn).

    Chỉ xét file ``.exe`` thuộc ``install_location`` / ``uninstall_string`` của
    app, đối chiếu với tiến trình đang chạy. Các tiến trình hệ thống trong
    ``_PROTECTED_IMAGES`` bị loại trừ.
    Trả về danh sách tên ``.exe`` (đã sắp xếp); rỗng nếu app không chạy.
    """
    candidates = _candidate_exe_names(app)
    if not candidates:
        return []
    images = running_images if running_images is not None else list_running_images()
    return sorted(
        n for n in candidates if n in images and n not in _PROTECTED_IMAGES)


def move_to_recycle_bin(path: str) -> tuple[bool, str]:
    """Đưa một file/thư mục vào Recycle Bin (thùng rác) thay vì xoá vĩnh viễn.

    Dùng ``SHFileOperationW`` (``FO_DELETE`` + ``FOF_ALLOWUNDO``) — chỉ thư viện
    chuẩn qua ``ctypes``, không thêm dependency. Người dùng có thể khôi phục mục
    đã xoá nhầm từ Recycle Bin.
    Trả về (ok, err): ok=True nếu mã lỗi = 0 và thao tác không bị huỷ.
    """
    if not path or not os.path.lexists(path):
        return False, f"Không tìm thấy: {path}"
    try:
        # pFrom bắt buộc kết thúc bằng 2 ký tự NUL; ctypes tự thêm 1 NUL nên
        # truyền thêm "\0" để tổng cộng là 2 (đúng đặc tả SHFileOperationW).
        op = _SHFILEOPSTRUCTW()
        op.wFunc = _FO_DELETE
        op.pFrom = os.path.abspath(path) + "\0"
        op.pTo = None
        op.fFlags = (_FOF_ALLOWUNDO | _FOF_NOCONFIRMATION
                     | _FOF_SILENT | _FOF_NOERRORUI)
        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        if result != 0:
            return False, f"SHFileOperationW lỗi (code {result})"
        if op.fAnyOperationsAborted:
            return False, "Thao tác đưa vào Recycle Bin bị huỷ."
        return True, ""
    except Exception as exc:  # noqa: BLE001 - trả lỗi thân thiện về UI
        return False, str(exc)


def _attempt_remove(path: str):
    """Xoá file/thư mục vĩnh viễn (kể cả read-only). Ném ngoại lệ nếu thất bại."""
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path, onerror=_force_remove)
    else:
        _force_remove(os.remove, path, None)


# Giới hạn số mục quét khi ước lượng "xoá dở dang" (tránh quét cây quá lớn).
_AUDIT_LIMIT = 5000


def _snapshot_paths(path: str) -> list[str]:
    """Liệt kê ``path`` + toàn bộ mục con (giới hạn ``_AUDIT_LIMIT``).

    Dùng để phát hiện xoá dở dang: sau khi xoá lỗi, đối chiếu các mục còn tồn tại
    với ảnh chụp này để biết đã xoá được bao nhiêu / còn lại bao nhiêu.
    """
    if not os.path.isdir(path) or os.path.islink(path):
        return [path]
    paths = [path]
    for root, dirs, files in os.walk(path):
        for name in dirs + files:
            paths.append(os.path.join(root, name))
            if len(paths) >= _AUDIT_LIMIT:
                return paths
    return paths


def _permanent_remove(path: str) -> tuple[bool, str]:
    """Xoá vĩnh viễn file/thư mục; kèm kill tiến trình + retry khi bị khoá.

    Nếu lần xoá đầu gặp ``PermissionError`` (file/thư mục đang bị khoá bởi tiến
    trình khác), tự động dừng các tiến trình trùng tên file ``.exe`` trong thư mục
    (``kill_processes_in_dir``), đợi 0.5 giây rồi thử xoá lại lần thứ hai.
    Trả về (ok, err).
    """
    try:
        _attempt_remove(path)
        return True, ""
    except PermissionError:
        kill_processes_in_dir(path)
        time.sleep(0.5)
        try:
            _attempt_remove(path)
            return True, ""
        except Exception as exc:  # noqa: BLE001 - trả lỗi về UI
            return False, str(exc)
    except Exception as exc:  # noqa: BLE001 - trả lỗi về UI
        return False, str(exc)


def _remove_path(path: str) -> tuple[bool, str, str]:
    """Đưa path vào Recycle Bin; nếu thất bại thì xoá vĩnh viễn (kèm kill/retry).

    Trả về (ok: bool, err: str, method: str) với method ∈ {"recycle", "permanent"}.
    Khi xoá vĩnh viễn bị bỏ dở (rmtree dừng giữa chừng), `err` mô tả rõ số mục
    đã xoá / còn lại để ghi nhật ký "xoá dở dang".
    """
    recycle_ok, _recycle_err = move_to_recycle_bin(path)
    if recycle_ok:
        return True, "", "recycle"

    # Đường dẫn đã không còn tồn tại -> báo lỗi rõ (không tính là xoá thành công).
    if not path or not os.path.lexists(path):
        return False, f"Không tìm thấy: {path}", "permanent"

    # Recycle Bin thất bại (read-only, đang bị khoá...) → thử xoá vĩnh viễn.
    # Chụp danh sách mục TRƯỚC khi xoá để phát hiện xoá dở dang nếu rmtree bỏ dở.
    snapshot = _snapshot_paths(path)
    ok, err = _permanent_remove(path)
    if ok:
        return True, "", "permanent"

    # Xoá lỗi: kiểm tra thực tế còn lại bao nhiêu mục trong snapshot.
    remaining = [p for p in snapshot if os.path.lexists(p)]
    if not remaining:
        # Thực tế đã xoá hết dù báo lỗi → coi như thành công.
        return True, "", "permanent"
    if len(remaining) < len(snapshot):
        done = len(snapshot) - len(remaining)
        sample = "; ".join((os.path.basename(p) or p) for p in remaining[:3])
        err = (f"Xoá dở dang: đã xoá {done}/{len(snapshot)} mục; "
               f"còn lại {len(remaining)} mục ({sample}). Chi tiết: {err}")
    return False, err, "permanent"


def delete_path(path: str, app_name: str = ""):
    """Xoá một file hoặc thư mục (kể cả read-only). Trả về (ok, err).

    Mặc định đưa mục vào **Recycle Bin** (``move_to_recycle_bin``) để có thể
    khôi phục nếu xoá nhầm; nếu Recycle Bin thất bại mới xoá vĩnh viễn. Khi gặp
    ``PermissionError``, tự động dừng các tiến trình trùng tên file ``.exe``
    trong thư mục rồi thử xoá lại. Ghi nhật ký thao tác xoá vào
    backups/history.jsonl (kèm cách xoá: Recycle Bin / vĩnh viễn).
    """
    ok, err, method = _remove_path(path)
    name = app_name or os.path.basename(os.path.normpath(path))
    how = "Recycle Bin" if method == "recycle" else "xoá vĩnh viễn"
    result = "OK" if ok else f"LỖI: {err}"
    backup.log_action("delete_path", name,
                      [{"kind": "files", "path": path}],
                      [f"{result} ({how})"])
    return ok, err