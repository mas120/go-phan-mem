"""App Uninstaller - library package.

Package chứa toàn bộ logic (không phụ thuộc giao diện) để dễ test và
tái sử dụng khi nâng cấp sang PyQt/Electron sau này.
"""

import sys

# Thông tin phiên bản/ứng dụng dùng chung cho cả 2 giao diện + đóng gói (G2).
__version__ = "1.0.1"
APP_NAME = "App Uninstaller"

#: Repo GitHub (dạng "tài_khoản/repo") dùng cho tính năng kiểm tra cập nhật.
#: Chỉ cần đổi ở ĐÂY khi chuyển sang tài khoản/kho khác.
GITHUB_REPO = "mas120/go-phan-mem"

#: Tên gói lõi ứng dụng nằm CẠNH file .exe (ngoài vỏ launcher).
#: Vỏ `launcher.py` nạp `app_core.zip` qua ``zipimport`` để cập nhật siêu nhẹ
#: mà không phải tải lại toàn bộ .exe.
CORE_ZIP_NAME = "app_core.zip"


def about_text() -> str:
    """Nội dung hộp thoại Giới thiệu (dùng chung cho tkinter và Qt)."""
    return (
        f"{APP_NAME} {__version__}\n\n"
        "Gỡ cài đặt ứng dụng Windows và dọn leftover (file + registry).\n"
        "• Quét registry HKLM 64/32-bit + HKCU và winget\n"
        "• Gỡ im lặng thông minh (Inno / NSIS / MSI)\n"
        "• Sao lưu .reg trước khi xoá + khôi phục ngay trong app\n"
        "• Leftover file/thư mục chuyển vào Recycle Bin\n\n"
        "Chỉ dùng thư viện chuẩn Python · Windows-only"
    )


def print_version() -> None:
    """In ``Tên phiên bản`` ra stdout — dùng cho cờ ``--version``.

    Bản `.exe` đóng gói ở chế độ windowed không có console riêng; hàm này gắn
    vào console của tiến trình cha (nếu có) rồi mở lại ``CONOUT$`` để chữ vẫn
    hiện khi chạy từ cmd/PowerShell.
    """
    if getattr(sys, "frozen", False):
        try:
            import ctypes
            ctypes.windll.kernel32.AttachConsole(-1)  # ATTACH_PARENT_PROCESS
        except Exception:  # noqa: BLE001 - không có console cha là bình thường
            pass
        if sys.stdout is None:
            try:
                sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
            except OSError:
                pass
    print(f"{APP_NAME} {__version__}")
