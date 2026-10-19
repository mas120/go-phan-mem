"""Sao lưu an toàn & ghi nhật ký các thao tác xoá leftover.

Trước khi xoá một nhánh registry, `export_registry_key` xuất nhánh đó ra file
`.reg` kèm timestamp (nằm trong thư mục `backups/`) để có thể khôi phục nếu
cần. Mọi thao tác xoá (registry / file) đều được ghi vào `backups/history.jsonl`
(JSON Lines) gồm thời gian, ứng dụng, danh sách đường dẫn đã xoá và kết quả.

CHỈ dùng thư viện chuẩn Python, không thêm dependency.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Thư mục gốc chứa `backups/`:
# - Chạy từ mã nguồn: cấp trên của package `uninstaller_lib/`.
# - Đóng gói PyInstaller (onefile): cạnh file `.exe`, để backup KHÔNG bị mất khi
#   thư mục tạm `_MEIPASS` bị dọn sau khi thoát (G1).
BASE_DIR = (Path(sys.executable).resolve().parent
            if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parent.parent)
BACKUP_DIR = BASE_DIR / "backups"
HISTORY_FILE = BACKUP_DIR / "history.jsonl"

# Số bản sao lưu .reg giữ lại tối đa; vượt mức này sẽ tự xoá bản cũ nhất.
MAX_BACKUP_KEEP = 50

# Không mở cửa sổ console con khi chạy reg.exe (kể cả khi gọi từ GUI).
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def _safe_name(name: str) -> str:
    """Chuẩn hoá tên dùng làm tên file (bỏ ký tự bất hợp lệ trên Windows)."""
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "").strip()).strip("._")
    return s or "app"


def _stamp() -> str:
    """Chuỗi thời gian duy nhất cho tên file backup (giảm khả năng trùng)."""
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]


def _ensure_backup_dir() -> None:
    """Tạo thư mục backups/ và file history.jsonl nếu chưa tồn tại."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if not HISTORY_FILE.exists():
        HISTORY_FILE.write_text("", encoding="utf-8")


# Đảm bảo backups/ và history.jsonl có mặt ngay khi module được import.
_ensure_backup_dir()


def _mtime(path: Path) -> float:
    """mtime của file (0.0 nếu không đọc được) — dùng để sắp xếp backup."""
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def list_backup_files() -> list[Path]:
    """Danh sách file .reg trong backups/, mới nhất đứng trước."""
    try:
        files = list(BACKUP_DIR.glob("*.reg"))
    except OSError:
        return []
    return sorted(files, key=_mtime, reverse=True)


def list_backup_info() -> list[dict]:
    """Danh sách backup kèm thời gian để hiển thị trên UI (mới nhất đứng trước).

    Mỗi mục là dict ``{"name": str, "path": Path, "time": str, "mtime": float}``;
    ``time`` là chuỗi ``dd/mm/YYYY HH:MM:SS`` (rỗng nếu không đọc được mtime).
    """
    info = []
    for f in list_backup_files():
        ts = _mtime(f)
        text = datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M:%S") if ts else ""
        info.append({"name": f.name, "path": f, "time": text, "mtime": ts})
    return info


def prune_backups(max_keep: int = MAX_BACKUP_KEEP) -> int:
    """Xoay vòng backup: giữ tối đa `max_keep` file .reg gần nhất.

    File .reg cũ hơn mức cho phép bị xoá; history.jsonl cũng được cắt còn tối
    đa `max_keep` dòng gần nhất. Chỉ thao tác bên trong thư mục backups/.
    Trả về số file .reg đã xoá (0 nếu không có gì để xoá).
    """
    try:
        files = sorted(BACKUP_DIR.glob("*.reg"), key=_mtime)  # cũ -> mới
    except OSError:
        return 0
    removed = 0
    if max_keep > 0:
        for f in files[:-max_keep]:
            try:
                f.unlink()
                removed += 1
            except OSError:
                continue
    try:
        if max_keep > 0 and HISTORY_FILE.exists():
            lines = HISTORY_FILE.read_text(encoding="utf-8").splitlines()
            if len(lines) > max_keep:
                HISTORY_FILE.write_text(
                    "\n".join(lines[-max_keep:]) + "\n", encoding="utf-8")
    except OSError:
        pass
    return removed


def clear_backups() -> int:
    """Xoá toàn bộ file .reg và làm trống history.jsonl.

    Trả về số file .reg đã xoá. Không raise để không phá vỡ luồng UI.
    """
    removed = 0
    try:
        for f in BACKUP_DIR.glob("*.reg"):
            try:
                f.unlink()
                removed += 1
            except OSError:
                continue
    except OSError:
        return removed
    try:
        HISTORY_FILE.write_text("", encoding="utf-8")
    except OSError:
        pass
    return removed


def export_registry_key(reg_path: str, app_name: str) -> tuple[bool, str]:
    """Xuất một nhánh registry ra file .reg kèm timestamp (sao lưu trước khi xoá).

    Dùng `subprocess.run(["reg", "export", ...], creationflags=CREATE_NO_WINDOW)`.
    Với nhánh HKLM mà lệnh đầu thất bại, tự thử lại với `/reg:32` và `/reg:64`
    để sao lưu được cả các subkey nằm ở view 32-bit (WOW6432Node).
    Trả về (ok, message): ok=True + đường dẫn file .reg đã ghi; ok=False + text lỗi.
    """
    try:
        _ensure_backup_dir()
        path = (reg_path or "").strip()
        if not path:
            return False, "Đường dẫn registry rỗng."
        leaf = path.replace("/", "\\").split("\\")[-1]
        name = _safe_name(app_name) or _safe_name(leaf)
        dest = BACKUP_DIR / f"{name}_{_stamp()}.reg"

        def _export(flag=None):
            cmd = ["reg", "export", path, str(dest), "/y"]
            if flag:
                cmd.append(flag)
            return subprocess.run(
                cmd,
                creationflags=CREATE_NO_WINDOW,
                capture_output=True, text=True, shell=False, timeout=30)

        proc = _export()
        # Nhánh HKLM có thể chỉ nằm ở view 32-bit (WOW6432Node): thử lại với
        # /reg:32 và /reg:64 để đảm bảo sao lưu được kể cả các subkey 32-bit.
        if proc.returncode != 0 and path.upper().startswith("HKLM\\"):
            for flag in ("/reg:32", "/reg:64"):
                proc = _export(flag)
                if proc.returncode == 0:
                    break
        if proc.returncode == 0:
            # Tự xoay vòng: chỉ giữ tối đa MAX_BACKUP_KEEP bản .reg gần nhất.
            prune_backups()
            return True, str(dest)
        msg = (proc.stderr or "").strip() or f"exit code {proc.returncode}"
        return False, f"reg export thất bại: {msg}"
    except Exception as exc:  # noqa: BLE001 - không để lỗi sao lưu chặn thao tác xoá
        return False, str(exc)


def restore_backup(reg_file) -> tuple[bool, str]:
    """Khôi phục một nhánh registry từ file .reg (gọi ``reg import``).

    Dùng ``subprocess.run(["reg", "import", <file>], creationflags=CREATE_NO_WINDOW)``
    (timeout 60s). Các giá trị trong file sẽ được ghi/ghi đè vào registry.
    Trả về (ok, message): ok=True + thông báo thành công; ok=False + text lỗi.
    """
    try:
        path = Path(reg_file)
        if not path.is_file():
            return False, f"Không tìm thấy file backup: {path}"
        proc = subprocess.run(
            ["reg", "import", str(path)],
            creationflags=CREATE_NO_WINDOW,
            capture_output=True, text=True, shell=False, timeout=60)
        if proc.returncode == 0:
            return True, f"Đã khôi phục: {path.name}"
        msg = ((proc.stderr or "").strip() or (proc.stdout or "").strip()
               or f"exit code {proc.returncode}")
        return False, f"reg import thất bại: {msg}"
    except Exception as exc:  # noqa: BLE001 - trả lỗi thân thiện về UI
        return False, str(exc)


def create_restore_point(
        description: str = "App Uninstaller Backup") -> tuple[bool, str]:
    """Tạo System Restore Point (PowerShell ``Checkpoint-Computer``).

    Gọi ``powershell`` với ``Checkpoint-Computer -RestorePointType
    APPLICATION_UNINSTALL`` (CREATE_NO_WINDOW, timeout 60s). Mọi ngoại lệ được
    bắt an toàn để KHÔNG làm crash app khi máy tắt System Restore hoặc thiếu
    quyền Admin. Kết quả được ghi vào ``backups/history.jsonl`` qua
    ``log_action("restore_point", ...)``.
    Trả về (ok: bool, message: str).
    """
    desc = (description or "").strip() or "App Uninstaller Backup"
    # Loại ký tự nguy hiểm có thể phá vỡ chuỗi PowerShell.
    safe_desc = re.sub(r'["`$]', "", desc)[:120] or "App Uninstaller Backup"
    script = (
        "$ErrorActionPreference='Stop'; "
        f"Checkpoint-Computer -Description \"{safe_desc}\" "
        "-RestorePointType 'APPLICATION_UNINSTALL'"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-Command", script],
            creationflags=CREATE_NO_WINDOW,
            capture_output=True, text=True, shell=False, timeout=60)
    except Exception as exc:  # noqa: BLE001 - không để lỗi restore point chặn app
        msg = f"Không tạo được Restore Point: {exc}"
        log_action("restore_point", desc, [], [msg])
        return False, msg

    if proc.returncode == 0:
        ok, msg = True, f"Đã tạo Restore Point: {desc}."
    else:
        err = ((proc.stderr or "").strip() or (proc.stdout or "").strip()
               or f"exit code {proc.returncode}")
        ok, msg = False, f"Không tạo được Restore Point: {err}"
    log_action("restore_point", desc, [], [msg])
    return ok, msg


def log_action(action: str, app_name: str,
               targets: list[dict], results: list[str]) -> None:
    """Ghi một dòng JSONL vào backups/history.jsonl.

    Ghi lại thời gian, hành động (action), tên ứng dụng, danh sách đường dẫn
    file/registry đã xoá (targets) và kết quả tương ứng (results).
    Không bao giờ raise để không phá vỡ luồng xoá.
    """
    try:
        _ensure_backup_dir()
        record = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "action": action,
            "app": app_name,
            "targets": targets or [],
            "results": results or [],
        }
        with HISTORY_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:  # noqa: BLE001 - ghi nhật ký không được phá vỡ luồng
        print(f"[backup] Không ghi được history.jsonl: {exc}", file=sys.stderr)
