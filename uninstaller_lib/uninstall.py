"""Các hàm chạy lệnh gỡ cài đặt với quyền xử lý đúng."""
import ctypes
import os
import re
import subprocess
import sys
import threading
from typing import Optional

from .models import AppInfo
from .enumerator import normalize_winget_id

# Không mở cửa sổ console con khi chạy cmd /c.
CREATE_NO_WINDOW = 0x08000000

# Cờ chấp nhận nguồn cho mọi lệnh winget (D1) — tránh prompt chặn tự động.
_WINGET_FLAG = "--accept-source-agreements"

# Dung lượng tối đa đọc từ đầu file .exe để dò chữ ký bộ cài (2 MB).
_SIGNATURE_SCAN_BYTES = 2 * 1024 * 1024


def is_admin() -> bool:
    """Kiểm tra quyền Administrator của tiến trình hiện tại."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        # Không xác định được -> coi như admin để tránh chặn người dùng.
        return True


def relaunch_as_admin() -> bool:
    """Khởi chạy lại tiến trình hiện tại với quyền Administrator (UAC).

    Dùng ShellExecuteW(None, "runas", sys.executable, ...) để xin nâng quyền;
    trả về True nếu lệnh được chấp nhận (giá trị trả về > 32).
    Caller nên thoát tiến trình hiện tại sau khi gọi thành công.
    """
    if is_admin():
        return True
    try:
        # Truyền lại script + tham số hiện tại cho tiến trình được nâng quyền.
        if getattr(sys, "frozen", False):
            params = subprocess.list2cmdline(sys.argv[1:])
        else:
            params = subprocess.list2cmdline(sys.argv)
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params, None, 1  # SW_SHOWNORMAL
        )
        return result > 32
    except Exception:
        return False


def _extract_exe_token(command: str) -> Optional[str]:
    """Trích chuỗi đường dẫn .exe từ câu lệnh gỡ (KHÔNG kiểm tra tồn tại).

    Ưu tiên token nằm trong cặp dấu nháy, rồi tới token `...exe` đầu tiên.
    """
    cmd = (command or "").strip()
    if not cmd:
        return None
    match = re.search(r'"([^"]+\.exe)"', cmd, re.IGNORECASE)
    if not match:
        match = re.search(r'([^\s"\'/]+\.exe)', cmd, re.IGNORECASE)
    if not match:
        return None
    return match.group(1)


def _extract_exe_path(command: str) -> Optional[str]:
    """Trích đường dẫn file .exe từ câu lệnh gỡ (có hoặc không có dấu nháy)."""
    path = _extract_exe_token(command)
    return path if path and os.path.isfile(path) else None


def _has_token_flag(command: str, *flags: str) -> bool:
    """Kiểm tra lệnh đã chứa BẤT KỲ cờ nào trong ``flags`` (khớp theo token).

    So khớp không phân biệt hoa thường trên từng token (tách bằng khoảng trắng)
    để tránh nối cờ im lặng trùng khi nhà phát hành đã thêm sẵn.
    """
    tokens = {tok.lower() for tok in (command or "").split()}
    return any(flag.lower() in tokens for flag in flags)


def _append_flags(command: str, *flags: str) -> str:
    """Nối thêm các cờ vào cuối lệnh (giữ nguyên phần lệnh gốc)."""
    return f"{command.rstrip()} {' '.join(flags)}".strip()


# --- Nhận diện bộ cài phổ biến khác (Nhóm I) ------------------------------
# CHỈ nhận diện khi có dấu hiệu RÕ RÀNG; nếu không chắc thì KHÔNG chèn cờ mù
# quáng (tránh làm treo tiến trình gỡ — dùng đúng cờ sai sẽ chờ vô hạn).

def _is_squirrel_uninstaller(exe_path: str, command: str) -> bool:
    """Squirrel / Electron Updater: ``Update.exe`` chạy kèm ``--uninstall``."""
    if os.path.basename(exe_path).lower() != "update.exe":
        return False
    return "--uninstall" in command.lower()


def _is_wix_burn_bootstrapper(exe_path: str, command: str) -> bool:
    """WiX Burn Bootstrapper: file .exe (không phải msiexec) với ``/uninstall``."""
    if os.path.basename(exe_path).lower() == "msiexec.exe":
        return False
    return "/uninstall" in command.lower()


def _is_installshield_uninstaller(exe_path: str, command: str) -> bool:
    """InstallShield: đường dẫn chứa ``InstallShield``, hoặc ``setup.exe`` kèm
    cờ đặc trưng ``/f1`` (file trả lời) hay ``/s`` (im lặng)."""
    low_path = exe_path.lower()
    if "installshield" in low_path:
        return True
    low_cmd = command.lower()
    if os.path.basename(low_path) == "setup.exe":
        return "/f1" in low_cmd or "/s " in low_cmd or low_cmd.rstrip().endswith("/s")
    return False


# --- Windows Installer API (msi.dll) --------------------------------------
# Gỡ gói MSI ổn định hơn bằng cách gọi thẳng API thay vì shell `msiexec`.
_INSTALLSTATE_ABSENT = 7          # INSTALLSTATE_ABSENT  -> gỡ cài đặt
_INSTALLSTATE_USABLE = (5, 8, 9, 10)  # ADVERTISED/LOCAL/SOURCE/DEFAULT -> đang cài
_INSTALLUILEVEL_DEFAULT = 1       # UI mặc định (gỡ có giao diện)
_INSTALLUILEVEL_NONE = 2          # không UI (gỡ im lặng)
_ERROR_SUCCESS = 0
_ERROR_NO_MORE_ITEMS = 259        # hết sản phẩm khi MsiEnumProducts
_PRODUCT_CODE_RE = re.compile(
    r"^\{[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\}$")

# Con trỏ DLL msi.dll (nạp một lần) + khoá bảo vệ khi nạp đa luồng.
_MSI_DLL = None
_MSI_DLL_LOCK = threading.Lock()


def _load_msi():
    """Nạp ``msi.dll`` (một lần) và khai báo argtypes cho các hàm dùng."""
    global _MSI_DLL
    with _MSI_DLL_LOCK:
        if _MSI_DLL is not None:
            return _MSI_DLL
        dll = ctypes.WinDLL("msi.dll")
        dll.MsiConfigureProductExW.argtypes = [
            ctypes.c_wchar_p, ctypes.c_int, ctypes.c_int, ctypes.c_wchar_p]
        dll.MsiConfigureProductExW.restype = ctypes.c_uint
        dll.MsiQueryProductStateW.argtypes = [ctypes.c_wchar_p]
        dll.MsiQueryProductStateW.restype = ctypes.c_int
        dll.MsiEnumProductsW.argtypes = [ctypes.c_uint, ctypes.c_wchar_p]
        dll.MsiEnumProductsW.restype = ctypes.c_uint
        _MSI_DLL = dll
        return dll


def _normalize_product_code(product_code: str) -> str:
    """Chuẩn hoá GUID sản phẩm MSI (bọc ``{}``); trả '' nếu không phải GUID."""
    pc = (product_code or "").strip()
    if not pc:
        return ""
    if not pc.startswith("{"):
        pc = f"{{{pc}}}"
    return pc if _PRODUCT_CODE_RE.match(pc) else ""


def list_msi_products() -> list:
    """Danh sách product code (GUID) đã cài, qua ``MsiEnumProductsW``.

    Trả về list rỗng nếu không dùng được Windows Installer (máy không có MSI,
    hoặc lỗi API). Không thay đổi gì trên hệ thống.
    """
    products = []
    try:
        dll = _load_msi()
    except OSError:
        return products
    buf = ctypes.create_unicode_buffer(39)  # GUID (38 ký tự) + NUL
    index = 0
    while True:
        try:
            rc = dll.MsiEnumProductsW(index, buf)
        except OSError:
            break
        if rc != _ERROR_SUCCESS:
            break
        products.append(buf.value)
        index += 1
    return products


def msi_product_installed(product_code: str) -> bool:
    """Kiểm tra một gói MSI có đang được cài (qua ``MsiQueryProductStateW``)."""
    pc = _normalize_product_code(product_code)
    if not pc:
        return False
    try:
        state = _load_msi().MsiQueryProductStateW(pc)
    except OSError:
        return False
    return state in _INSTALLSTATE_USABLE


class _MsiJob:
    """Job gỡ MSI chạy nền qua Windows Installer API.

    Cung cấp ``wait()`` giống ``subprocess.Popen`` để worker hiện tại chờ gỡ
    xong trước khi quét leftover / chạy app kế tiếp.
    """

    def __init__(self, product_code: str, quiet: bool):
        self.product_code = product_code
        self.quiet = quiet
        self.returncode = None
        self._error = None
        self._done = threading.Event()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name=f"msi-uninstall-{product_code}")
        self._thread.start()

    def _run(self):
        try:
            dll = _load_msi()
            level = _INSTALLUILEVEL_NONE if self.quiet else _INSTALLUILEVEL_DEFAULT
            self.returncode = dll.MsiConfigureProductExW(
                self.product_code, level, _INSTALLSTATE_ABSENT,
                "REBOOT=ReallySuppress")
        except Exception as exc:  # noqa: BLE001 - chuyển lỗi về wait()
            self._error = exc
            self.returncode = -1
        finally:
            self._done.set()

    def wait(self, timeout=None):
        """Chờ tới khi gỡ xong; trả mã lỗi MSI (0 = thành công)."""
        self._done.wait(timeout)
        return self.returncode


def uninstall_msi(product_code: str, quiet: bool = True):
    """Gỡ một gói MSI bằng Windows Installer API (``MsiConfigureProductExW``).

    Trả về (ok, message, proc) — proc là _MsiJob (có .wait()) hoặc None.
    """
    pc = _normalize_product_code(product_code)
    if not pc:
        return False, "Mã sản phẩm MSI không hợp lệ.", None
    try:
        if not msi_product_installed(pc):
            return False, f"Windows Installer không thấy sản phẩm {pc} đã cài.", None
    except OSError as exc:
        return False, f"Không dùng được Windows Installer API: {exc}", None
    mode = "im lặng" if quiet else "có giao diện"
    return (True, f"Đang gỡ bằng Windows Installer API ({mode}) — {pc}.",
            _MsiJob(pc, quiet))


def _prefer_msi_api(app: AppInfo) -> str:
    """Product code GUID nếu nên gỡ qua API MSI, ngược lại ''.

    Bỏ qua khi ``UninstallString`` là wrapper tuỳ biến (không phải msiexec) để
    tôn trọng quy trình riêng của nhà phát hành.
    """
    pc = _normalize_product_code(getattr(app, "product_code", ""))
    if not pc:
        return ""
    unset = (getattr(app, "uninstall_string", "") or "").lower()
    if unset and "msiexec" not in unset:
        return ""
    return pc


def _msi_uninstall_command(product_code: str, quiet: bool = False) -> str:
    """Lệnh gỡ chuẩn của Windows Installer từ product_code (GUID).

    Trả về ``MsiExec.exe /X{...}``; nếu quiet thì thêm ``/qn /norestart``.
    Product code từ registry thường là ``{GUID}``; nếu thiếu cặp ngoặc thì bọc lại.
    """
    pc = (product_code or "").strip()
    if not pc:
        return ""
    if not pc.startswith("{"):
        pc = f"{{{pc}}}"
    cmd = f"MsiExec.exe /X{pc}"
    if quiet:
        cmd += " /qn /norestart"
    return cmd


def _normalize_winget_command(command: str) -> str:
    """Chuẩn hoá lệnh gỡ winget: bỏ hậu tố id `|arch|ver` + thêm cờ nguồn (D1+D2).

    Chỉ tác động khi chuỗi lệnh là lệnh winget; giữ nguyên các lệnh khác.
    """
    if not command or "winget" not in command.lower():
        return command
    command = re.sub(
        r"(--id|-i)\s+\"([^\"]+)\"",
        lambda m: f'{m.group(1)} "{normalize_winget_id(m.group(2))}"',
        command, flags=re.IGNORECASE)
    if _WINGET_FLAG not in command:
        command = command.rstrip() + " " + _WINGET_FLAG
    return command


def build_quiet_command(app: AppInfo) -> str:
    """Suy luận lệnh gỡ im lặng cho app.

    1. Có sẵn `app.quiet_uninstall_string` -> trả về ngay chuỗi đó.
    2. Có `app.product_code` (gói MSI) -> dựng `MsiExec.exe /X{GUID} /qn /norestart`.
    3. `uninstall_string` chứa "msiexec" (không phân biệt hoa thường): đổi cờ
       `/I` thành `/X` (nếu có) và nối thêm `/qn /norestart`.
    4. `uninstall_string` trỏ tới file `.exe` tồn tại trên đĩa -> nhận diện bộ
       cài theo tên file/cờ đặc trưng RỒI mới đọc tối đa 2MB đầu để dò chữ ký:
       - Squirrel/Electron (`Update.exe` + `--uninstall`) -> thêm `-s`.
       - WiX Burn Bootstrapper (`.exe` + `/uninstall`) -> thêm `/quiet /norestart`.
       - InstallShield (`InstallShield` trong đường dẫn hoặc `setup.exe` kèm
         `/f1`/`/s`) -> thêm `/S` nếu chưa có cờ im lặng.
       - chứa b"Inno Setup"            -> thêm `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART`.
       - chứa b"Nullsoft" hoặc b"NSIS" -> thêm `/S`.
    5. Không nhận diện được -> trả về chuỗi rỗng "".

    Chỉ chèn cờ khi nhận diện RÕ RÀNG loại bộ cài; tránh chèn cờ mù quáng làm
    treo tiến trình gỡ.
    """
    if app.quiet_uninstall_string:
        return app.quiet_uninstall_string

    # Gói MSI: ưu tiên dùng product_code (GUID) để dựng lệnh gỡ chuẩn, ổn
    # định hơn việc đoán từ UninstallString (đôi khi là wrapper tuỳ biến).
    if app.product_code:
        return _msi_uninstall_command(app.product_code, quiet=True)

    uninstall = app.uninstall_string
    if not uninstall:
        return ""

    if "msiexec" in uninstall.lower():
        command = re.sub(r"(?i)/i\b", "/X", uninstall)
        return f"{command.rstrip()} /qn /norestart"

    exe_path = _extract_exe_path(uninstall)
    if exe_path is None:
        return ""

    # 4a. Nhận diện theo tên file / cờ đặc trưng (không cần đọc nội dung file).
    if _is_squirrel_uninstaller(exe_path, uninstall):
        base = uninstall.rstrip()
        if _has_token_flag(base, "-s", "--silent"):
            return base
        return _append_flags(base, "-s")

    if _is_wix_burn_bootstrapper(exe_path, uninstall):
        base = uninstall.rstrip()
        if not _has_token_flag(base, "/quiet", "-quiet", "/silent", "/passive"):
            base = _append_flags(base, "/quiet")
        if not _has_token_flag(base, "/norestart", "-norestart"):
            base = _append_flags(base, "/norestart")
        return base

    if _is_installshield_uninstaller(exe_path, uninstall):
        base = uninstall.rstrip()
        if _has_token_flag(base, "/s", "/silent", "-s"):
            return base
        return _append_flags(base, "/S")

    # 4b. Dò chữ ký bộ cài trong 2MB đầu của file .exe (Inno / NSIS).
    try:
        with open(exe_path, "rb") as fh:
            head = fh.read(_SIGNATURE_SCAN_BYTES)
    except OSError:
        return ""

    base = uninstall.rstrip()
    if b"Inno Setup" in head:
        return f"{base} /VERYSILENT /SUPPRESSMSGBOXES /NORESTART"
    if b"Nullsoft" in head or b"NSIS" in head:
        return f"{base} /S"
    return ""


def check_uninstaller_status(app: AppInfo) -> tuple:
    """Kiểm tra ứng dụng có gỡ chuẩn được hay không (phục vụ Force Uninstall).

    Sẵn sàng khi: nguồn ``winget``, ``product_code`` là GUID MSI hợp lệ, lệnh dựa
    trên ``msiexec`` (Windows Installer có sẵn), hoặc file ``.exe`` trích từ
    ``uninstall_string``/``quiet_uninstall_string`` thực sự tồn tại trên ổ đĩa.

    Trả về: (True, "OK") nếu trình gỡ sẵn sàng, hoặc (False, "<lý do cụ thể>")
    để tầng UI đề xuất chế độ "Gỡ cưỡng bức (Quét & dọn Leftover trực tiếp)".
    """
    if getattr(app, "source", "") == "winget":
        return True, "OK"

    if _normalize_product_code(getattr(app, "product_code", "")):
        return True, "OK"

    uninstall = (getattr(app, "uninstall_string", "") or "").strip()
    quiet = (getattr(app, "quiet_uninstall_string", "") or "").strip()

    if not uninstall and not quiet:
        return False, "Thiếu UninstallString trong registry."

    # Lệnh dựa trên msiexec: Windows Installer có sẵn trên mọi máy Windows.
    if "msiexec" in uninstall.lower() or "msiexec" in quiet.lower():
        return True, "OK"

    missing = None
    for command in (uninstall, quiet):
        if not command:
            continue
        token = _extract_exe_token(command)
        if token and os.path.isfile(token):
            return True, "OK"
        if token and missing is None:
            missing = token

    if missing:
        return False, f"File gỡ đã bị xoá: {missing}"
    first = uninstall or quiet
    return False, f"Không xác định được trình gỡ từ lệnh: {first}"



def run_uninstall(app: AppInfo, quiet: bool = False):
    """Chạy lệnh gỡ cài đặt của một ứng dụng.

    - quiet=True  dùng build_quiet_command() để tự suy luận lệnh gỡ im lặng
      (QuietUninstallString, hoặc suy ra từ msiexec / bộ cài Inno-NSIS);
      nếu vẫn rỗng thì báo "không hỗ trợ".
    - quiet=False dùng UninstallString (chuẩn, thường có UI).
    - Gói MSI có product_code (GUID): ưu tiên gỡ qua Windows Installer API
      (``uninstall_msi``) cho ổn định; nếu không dùng được thì fallback về shell.
    Trả về (ok: bool, message: str, proc) — proc: Popen/_MsiJob nếu chạy được, None nếu lỗi.
    """
    if quiet:
        command = build_quiet_command(app)
        mode = "im lặng"
        if not command and not _prefer_msi_api(app):
            return False, "Ứng dụng này không hỗ trợ gỡ cài đặt im lặng.", None
    else:
        command = app.uninstall_string
        mode = "thường"
        # Gói MSI có product_code nhưng thiếu UninstallString: tự dựng lệnh gỡ.
        if not command and app.product_code:
            command = _msi_uninstall_command(app.product_code)

    # Gói MSI: ưu tiên Windows Installer API (ổn định hơn shell msiexec).
    pc = _prefer_msi_api(app)
    if pc:
        ok, msg, job = uninstall_msi(pc, quiet=quiet)
        if ok:
            return ok, msg, job
        # API không dùng được (sản phẩm đã gỡ / lỗi) -> rơi xuống cách shell.

    if not command:
        return False, "Ứng dụng này không có lệnh gỡ cài đặt trong registry.", None

    # Lệnh winget: chuẩn hoá id (D2) + đảm bảo cờ chấp nhận nguồn (D1).
    if getattr(app, "source", "") == "winget":
        command = _normalize_winget_command(command)

    try:
        # Để Windows tự phân tích cú pháp chuỗi lệnh gốc (an toàn hơn cmd /c
        # khi UninstallString chứa nhiều cặp dấu nháy và tham số).
        proc = subprocess.Popen(
            command,
            shell=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
        )
    except Exception as exc:
        return False, f"Lỗi khi khởi chạy lệnh gỡ ({mode}): {exc}", None

    return True, f"Đã khởi chạy trình gỡ ({mode}) — PID {proc.pid}. Hoàn tất thao tác trong cửa sổ của trình gỡ.", proc
