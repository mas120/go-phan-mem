"""Data model mô tả một ứng dụng đã cài đặt."""
from dataclasses import dataclass


@dataclass
class AppInfo:
    """Thông tin một ứng dụng đã cài đặt, thu thập từ registry.

    Mọi trường đều có giá trị mặc định, chỉ name là bắt buộc.
    """

    name: str
    version: str = ""
    publisher: str = ""
    install_date: str = ""
    install_location: str = ""
    estimate_size_kb: int = 0
    uninstall_string: str = ""
    quiet_uninstall_string: str = ""
    registry_key: str = ""
    system_component: bool = False
    source: str = "registry"
    product_code: str = ""

    @property
    def size_text(self) -> str:
        """Chuyển EstimatedSize (tính bằng KB) thành chuỗi dễ đọc."""
        if not self.estimate_size_kb:
            return ""
        kb = self.estimate_size_kb
        if kb >= 1024 * 1024:
            return f"{kb / (1024 * 1024):.2f} GB"
        if kb >= 1024:
            return f"{kb / 1024:.1f} MB"
        return f"{kb} KB"

    @property
    def date_text(self) -> str:
        """Chuyển InstallDate (YYYYMMDD) thành DD/MM/YYYY."""
        s = (self.install_date or "").strip()
        if len(s) == 8 and s.isdigit():
            return f"{s[6:8]}/{s[4:6]}/{s[0:4]}"
        return self.install_date

    @property
    def can_uninstall(self) -> bool:
        """Có lệnh gỡ chuẩn hay không (registry / MSI / winget)."""
        return bool(self.uninstall_string) or bool(self.product_code) or self.source == "winget"
