"""Liệt kê các ứng dụng đã cài đặt từ registry Windows.

Registry là nguồn dữ liệu mà chính "Add/Remove Programs" (hoặc
Settings > Apps) của Windows dùng. Quét cả hệ 64-bit, 32-bit và HKCU.
"""
import os
import re
import subprocess
import threading
import winreg

from .models import AppInfo

# Danh sách (hive, subkey, access_view) cần quét.
# KEY_WOW64_64KEY  -> view 64-bit
# KEY_WOW64_32KEY  -> view 32-bit
# KEY_WOW64_64KEY / KEY_WOW64_32KEY trên đường dẫn chuẩn đã bao phủ cả nhánh
# 64-bit và 32-bit; không cần liệt kê tường minh nhánh WOW6432Node (tránh trùng).
_UNINSTALL_ROOTS = [
    (winreg.HKEY_LOCAL_MACHINE,
     r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
     winreg.KEY_WOW64_64KEY),
    (winreg.HKEY_LOCAL_MACHINE,
     r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
     winreg.KEY_WOW64_32KEY),
    (winreg.HKEY_CURRENT_USER,
     r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
     winreg.KEY_WOW64_64KEY),
    (winreg.HKEY_CURRENT_USER,
     r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
     winreg.KEY_WOW64_32KEY),
]

# Khoá đánh dấu entry là bản cập nhật / component hệ thống (ẩn khỏi danh sách app).
_SKIP_VALUE_NAMES = {"ParentDisplayName", "ParentKeyName"}

# CHỈ đọc những value thực sự dùng để lọc và dựng AppInfo (F1).
# Tránh liệt kê TOÀN BỘ value của mỗi key — vốn chậm khi có 200+ app (mỗi key
# còn nhiều value lớn như DisplayIcon, ModifyPath, URLInfoAbout... không dùng tới).
_WANTED_VALUES = (
    "DisplayName",
    "DisplayVersion",
    "Publisher",
    "InstallDate",
    "InstallLocation",
    "EstimatedSize",
    "UninstallString",
    "QuietUninstallString",
    "WindowsInstaller",
    "SystemComponent",
    "ReleaseType",
    "ParentDisplayName",
    "ParentKeyName",
)

# Key con dạng GUID chuẩn của Windows Installer (MSI): {XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}.
_GUID_RE = re.compile(
    r"^\{[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\}$"
)

# Cờ dùng chung cho mọi lệnh winget (list/uninstall) — tránh prompt chấp nhận nguồn (D1).
_WINGET_FLAG = "--accept-source-agreements"

# Giới hạn ước lượng dung lượng thư mục cài đặt (Nhóm I): đủ nhanh để quét toàn
# hệ thống mà không làm chậm khi có nhiều app thiếu EstimatedSize.
_ESTIMATE_MAX_DEPTH = 2        # độ sâu thư mục tối đa (root → con → cháu)
_ESTIMATE_MAX_ENTRIES = 1500   # số mục tối đa đếm được mỗi thư mục cài đặt

# Cache kết quả `winget list` cho phiên hiện tại (D3): tránh chờ ~8s mỗi lần refresh.
# None = chưa cache; list = đã cache (có thể rỗng nếu winget chạy được nhưng 0 app).
_winget_cache = None
_winget_lock = threading.Lock()


def _to_int(value, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _is_system_or_drive_root(path: str) -> bool:
    """True nếu ``path`` là ổ đĩa gốc hoặc thư mục hệ thống (Windows/System32)."""
    norm = os.path.normcase(os.path.normpath(path))
    _drive, tail = os.path.splitdrive(norm)
    if not tail.strip("\\/"):
        return True  # gốc ổ đĩa (C:\)
    root = os.environ.get("SystemRoot") or os.environ.get("WINDIR")
    if root:
        base = os.path.normcase(os.path.normpath(root))
        for sysdir in (base, os.path.join(base, "system32"),
                       os.path.join(base, "syswow64")):
            if norm == os.path.normcase(os.path.normpath(sysdir)):
                return True
    return False


def estimate_location_size_kb(install_location: str) -> int:
    """Ước lượng dung lượng thư mục cài đặt (KB) khi thiếu EstimatedSize.

    Chỉ dùng thư viện chuẩn (``os.scandir``). Giới hạn độ sâu tối đa 2 cấp và
    tối đa 1500 mục để quét toàn hệ thống không bị chậm; bỏ qua nếu
    ``install_location`` trùng thư mục hệ thống hoặc ổ đĩa gốc.

    Trả về: số KB (int); 0 nếu không đọc được hoặc không hợp lệ.
    """
    loc = (install_location or "").strip().strip('"')
    if not loc:
        return 0
    try:
        root = os.path.abspath(os.path.expandvars(loc))
    except (OSError, ValueError):
        return 0
    if not os.path.isdir(root) or _is_system_or_drive_root(root):
        return 0

    total = 0
    count = 0
    stack = [(root, 0)]
    while stack and count < _ESTIMATE_MAX_ENTRIES:
        current, depth = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    if count >= _ESTIMATE_MAX_ENTRIES:
                        break
                    count += 1
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if depth < _ESTIMATE_MAX_DEPTH:
                                stack.append((entry.path, depth + 1))
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total // 1024


def _read_values(entry) -> dict:
    """Đọc CHỈ các value cần thiết của một registry key (F1).

    Thay vì ``EnumValue`` toàn bộ value (tốn kém khi có 200+ app — mỗi key còn
    nhiều value lớn không dùng tới), chỉ truy vấn đúng những tên trong
    ``_WANTED_VALUES`` bằng ``QueryValueEx``. Value thiếu bị bỏ qua an toàn.
    """
    data = {}
    for name in _WANTED_VALUES:
        try:
            value, _ = winreg.QueryValueEx(entry, name)
        except OSError:
            continue
        data[name] = value
    return data


def _is_hidden(data: dict) -> bool:
    """Bộ lọc: bỏ qua component hệ thống và các bản cập nhật Windows."""
    if str(data.get("SystemComponent", "0")).strip().lower() in ("1", "true"):
        return True
    release = str(data.get("ReleaseType", "")).strip().lower()
    if release and release in {"update", "hotfix", "security update", "driver update"}:
        return True
    if any(str(data.get(k, "")).strip() for k in _SKIP_VALUE_NAMES):
        return True
    return False


def _enumerate_view(hive, subkey, access) -> list:
    """Quét một view cụ thể của một root key Uninstall."""
    found = []
    try:
        with winreg.OpenKey(hive, subkey, 0, access | winreg.KEY_READ) as root:
            index = 0
            while True:
                try:
                    key_name = winreg.EnumKey(root, index)
                except OSError:
                    break
                index += 1

                try:
                    with winreg.OpenKey(root, key_name) as entry:
                        data = _read_values(entry)
                except OSError:
                    continue

                if _is_hidden(data):
                    continue

                display_name = str(data.get("DisplayName", "")).strip()
                if not display_name:
                    continue

                # Nhận diện gói MSI: key con dạng GUID hoặc cờ WindowsInstaller=1.
                is_msi = (_GUID_RE.match(key_name) is not None
                          or str(data.get("WindowsInstaller", "")).strip() == "1")
                uninstall = str(data.get("UninstallString", "") or "").strip()
                if is_msi and not uninstall:
                    # MsiExec.exe /X{GUID} là lệnh gỡ chuẩn của Windows Installer.
                    uninstall = f"MsiExec.exe /X{key_name}"

                location = str(data.get("InstallLocation", "") or "")
                app = AppInfo(
                    name=display_name,
                    version=str(data.get("DisplayVersion", "") or ""),
                    publisher=str(data.get("Publisher", "") or ""),
                    install_date=str(data.get("InstallDate", "") or ""),
                    install_location=location,
                    estimate_size_kb=_to_int(data.get("EstimatedSize", 0)),
                    uninstall_string=uninstall,
                    quiet_uninstall_string=str(data.get("QuietUninstallString", "") or ""),
                    registry_key=f"{subkey}\\{key_name}",
                    system_component=str(data.get("SystemComponent", "")) == "1",
                    source="msi" if is_msi else "registry",
                    product_code=key_name if is_msi else "",
                )
                # Nhóm I: thiếu EstimatedSize -> ước lượng nhanh từ thư mục cài
                # đặt (giới hạn độ sâu + số mục để không làm chậm quét hệ thống).
                if not app.estimate_size_kb and app.install_location:
                    app.estimate_size_kb = estimate_location_size_kb(app.install_location)
                found.append(app)
    except OSError:
        # key không tồn tại hoặc không truy cập được -> bỏ qua.
        pass
    return found


def _enumerate_winget(existing_names: set[str]) -> list:
    """Quét các ứng dụng từ winget mà registry chưa liệt kê (UWP / MS Store...).

    Kết quả `winget list` được **cache cho phiên hiện tại** (D3) để không phải
    chờ ~8s mỗi lần refresh — gọi `clear_winget_cache()` để buộc quét lại.
    Nếu máy không có winget, lệnh lỗi hoặc quá thời gian chờ thì trả về danh
    sách rỗng (bỏ qua an toàn) và KHÔNG cache để còn thử lại lần sau.
    """
    apps = []
    for name, app_id, version in _get_winget_rows():
        if name.lower() in existing_names:
            continue
        base_id = normalize_winget_id(app_id)
        if not base_id:
            continue
        apps.append(AppInfo(
            name=name,
            version=version,
            source="winget",
            uninstall_string=f'winget uninstall --id "{base_id}" {_WINGET_FLAG}',
            quiet_uninstall_string=(f'winget uninstall --id "{base_id}" --silent '
                                    f'{_WINGET_FLAG}'),
            registry_key=base_id,
        ))
    return apps


def normalize_winget_id(app_id: str) -> str:
    """Chuẩn hoá app_id của winget: bỏ hậu tố ``|arch|version`` (D2).

    Ví dụ ``"Microsoft.App|x64|1.2"`` -> ``"Microsoft.App"``. Trả về chuỗi đã
    ``strip`` (rỗng nếu đầu vào rỗng).
    """
    return (app_id or "").split("|", 1)[0].strip()


def clear_winget_cache() -> None:
    """Xoá cache `winget list` để lần quét kế tiếp chạy lại winget (D3)."""
    global _winget_cache
    with _winget_lock:
        _winget_cache = None


def _get_winget_rows() -> list:
    """Trả về ``[(name, app_id, version)]`` từ `winget list` (đã cache — D3)."""
    global _winget_cache
    with _winget_lock:
        if _winget_cache is not None:
            return _winget_cache
    rows = _run_winget_list()
    if rows is not None:
        with _winget_lock:
            _winget_cache = rows
        return rows
    return []


def _run_winget_list():
    """Chạy `winget list --accept-source-agreements` và parse bảng kết quả.

    Trả về list ``[(name, app_id, version)]`` nếu chạy được; trả ``None`` nếu
    không có winget / lệnh lỗi / quá thời gian chờ (để caller KHÔNG cache lại).
    """
    try:
        proc = subprocess.run(
            ["winget", "list", _WINGET_FLAG],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, FileNotFoundError, subprocess.TimeoutExpired):
        # Không có winget hoặc quá thời gian chờ -> bỏ qua an toàn.
        return None

    if proc.returncode != 0:
        return None

    rows = []
    lines = (proc.stdout or "").splitlines()
    header_line = ""
    header_index = -1
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("Name") and "Id" in s:
            header_line = line
            header_index = i
            break
    if not header_line:
        return rows

    # Xác định vị trí các cột từ dòng tiêu đề (winget dùng bảng có cột cố định).
    columns = []
    for token in ("Name", "Id", "Version", "Available", "Source"):
        idx = header_line.find(token)
        if idx >= 0:
            columns.append(idx)
    columns.sort()
    if not columns:
        return rows

    for line in lines[header_index + 1:]:
        stripped = line.strip()
        if not stripped or set(stripped) <= {"-"}:
            continue
        fields = []
        for i, pos in enumerate(columns):
            end = columns[i + 1] if i + 1 < len(columns) else len(line)
            fields.append(line[pos:end].strip())
        if not fields:
            continue
        name = fields[0]
        app_id = fields[1] if len(fields) > 1 else ""
        version = fields[2] if len(fields) > 2 else ""
        if not name or not app_id:
            continue
        rows.append((name, app_id, version))
    return rows


def enumerate_apps(refresh_winget: bool = False) -> list:
    """Quét toàn bộ registry và trả về danh sách AppInfo (đã sắp xếp).

    ``refresh_winget=True`` sẽ xoá cache `winget list` và chạy lại winget; mặc
    định dùng cache của phiên hiện tại (D3) để không phải chờ ~8s mỗi lần refresh.
    """
    if refresh_winget:
        clear_winget_cache()

    apps = []
    for hive, subkey, access in _UNINSTALL_ROOTS:
        apps.extend(_enumerate_view(hive, subkey, access))

    # Khử trùng lặp giữa view 32/64-bit (nếu cùng app đăng ký ở cả hai).
    seen = set()
    unique = []
    for app in apps:
        key = (app.name.lower(), app.version, app.uninstall_string)
        if key in seen:
            continue
        seen.add(key)
        unique.append(app)

    unique.sort(key=lambda a: a.name.lower())

    # Bổ sung các ứng dụng winget / MS Store (UWP) chưa có trong registry.
    existing_names = {app.name.lower() for app in unique}
    unique.extend(_enumerate_winget(existing_names))
    unique.sort(key=lambda a: a.name.lower())
    return unique
