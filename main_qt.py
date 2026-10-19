# -*- coding: utf-8 -*-
"""
main_qt.py — Giao diện PySide6 (QtWidgets / QtCore / QtGui) cho App Uninstaller (Windows).

- Dark Mode hiện đại, đa luồng chuẩn Qt (QThread + Signal).
- Bảng dữ liệu: QTableView + QAbstractTableModel + QSortFilterProxyModel.
- Hộp thoại leftover phân nhóm bằng QTreeWidget (kèm backup registry + ghi log).

Chạy:   python main_qt.py
Yêu cầu: pip install PySide6

Chỉ nói chuyện với uninstaller_lib qua API contracts (AI_CONTEXT.md);
KHÔNG sửa bất kỳ logic hệ thống nào.
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime

from uninstaller_lib import (
    APP_NAME,
    __version__,
    about_text,
    print_version,
    backup,
    enumerator,
    leftover,
    uninstall,
    updater,
)

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QSortFilterProxyModel,
    QThread,
    Qt,
    Signal,
    QObject,
    QTimer,
    qVersion,
)
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableView,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

# ==== Hằng số & cấu hình hiển thị ====

#: Các cột hiển thị trên bảng dữ liệu.
COLUMNS = ["Tên ứng dụng", "Phiên bản", "Nhà phát hành", "Dung lượng", "Ngày cài", "Nguồn"]

#: Tooltip cho tiêu đề từng cột (E2) — hiện khi rê chuột lên header.
COLUMN_TIPS = [
    "Tên hiển thị của ứng dụng",
    "Phiên bản đã cài đặt",
    "Nhà phát hành",
    "Dung lượng ước tính (EstimatedSize từ registry)",
    "Ngày cài đặt",
    "Nguồn dữ liệu: Registry / MSI / Winget",
]

#: Nhãn nhóm dùng cho hộp thoại leftover, ánh xạ từ giá trị ``kind``.
GROUP_NAMES = {
    "registry": "Registry",
    "files": "File / Thư mục",
    "entry": "Mục gỡ cài đặt (Uninstall Entry)",
}

#: Nhãn hiển thị cho cột Nguồn, ánh xạ từ giá trị ``source``.
SOURCE_LABELS = {
    "registry": "Registry",
    "msi": "MSI",
    "winget": "Winget",
}

#: Danh sách lựa chọn bộ lọc Nguồn: (nhãn, giá trị nguồn thô).
SOURCE_FILTERS = [
    ("Tất cả", ""),
    ("Registry", "registry"),
    ("MSI", "msi"),
    ("Winget", "winget"),
]

# ==== Stylesheet dark mode ====
STYLESHEET = """
QMainWindow, QWidget {
    background-color: #1e1e22; color: #e6e6e6;
    font-family: 'Segoe UI', 'Inter', 'Helvetica Neue', sans-serif; font-size: 13px;
}
QLineEdit, QComboBox {
    background-color: #2a2b30; color: #e6e6e6; border: 1px solid #3c3d42;
    border-radius: 6px; padding: 6px 8px; selection-background-color: #4f8ef7;
}
QLineEdit:focus, QComboBox:focus { border: 1px solid #4f8ef7; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background-color: #2a2b30; color: #e6e6e6; selection-background-color: #4f8ef7;
    border: 1px solid #3c3d42; outline: none;
}
QPushButton {
    background-color: #2a2b30; color: #e6e6e6; border: 1px solid #3c3d42;
    border-radius: 6px; padding: 6px 12px; font-weight: 600;
}
QPushButton:hover { background-color: #343640; border-color: #4f8ef7; }
QPushButton:pressed { background-color: #3d3f47; }
QPushButton:disabled { color: #6a6c72; background-color: #242529; border-color: #2f3034; }
QPushButton#primary { background-color: #2d6cdf; border-color: #2d6cdf; color: #ffffff; }
QPushButton#primary:hover { background-color: #3a7ae0; border-color: #3a7ae0; }
QPushButton#danger { background-color: #cb2431; border-color: #cb2431; color: #ffffff; }
QPushButton#danger:hover { background-color: #da3b47; border-color: #da3b47; }
QTableView {
    background-color: #1f2024; alternate-background-color: #24252a; color: #e6e6e6;
    border: 1px solid #3c3d42; gridline-color: #2c2d31; border-radius: 8px;
    selection-background-color: #2d4d8c; selection-color: #ffffff;
}
QTableView::item { padding: 4px; }
QHeaderView::section {
    background-color: #26272c; color: #b9bcc2; padding: 6px; border: none;
    border-right: 1px solid #303136; border-bottom: 1px solid #3c3d42; font-weight: 600;
}
QHeaderView::section:hover { background-color: #2d2f35; }
QTreeWidget {
    background-color: #1f2024; alternate-background-color: #24252a; color: #e6e6e6;
    border: 1px solid #3c3d42; border-radius: 8px;
}
QTreeWidget::item { padding: 4px; }
QTreeWidget::item:selected { background-color: #2d4d8c; color: #ffffff; }
QTreeWidget::item:hover { background-color: #2a2c33; }
QStatusBar { background-color: #26272c; color: #b9bcc2; border-top: 1px solid #303136; }
QProgressBar {
    background-color: #2a2b30; border: 1px solid #3c3d42; border-radius: 6px;
    text-align: center; color: #e6e6e6;
}
QProgressBar::chunk { background-color: #4f8ef7; border-radius: 5px; }
QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar::handle:vertical { background: #40424a; border-radius: 6px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #4f8ef7; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0px; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 2px; }
QScrollBar::handle:horizontal { background: #40424a; border-radius: 6px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: #4f8ef7; }
QToolTip { background-color: #2a2b30; color: #e6e6e6; border: 1px solid #3c3d42; padding: 4px 6px; }
QPlainTextEdit {
    background-color: #191a1e; color: #c8cbd0; border: 1px solid #2f3034;
    border-radius: 6px; font-family: 'Cascadia Code', 'Consolas', 'Menlo', monospace;
}
QDialog { background-color: #1e1e22; }
QMenu { background-color: #26272c; color: #e6e6e6; border: 1px solid #3c3d42; }
QMenu::item { padding: 6px 24px; }
QMenu::item:selected { background-color: #4f8ef7; color: #ffffff; }
QMenu::separator { height: 1px; background: #303136; margin: 4px 8px; }
QCheckBox { spacing: 6px; }
QLabel { color: #e6e6e6; }
"""


# ==== Model dữ liệu cho bảng ====

class AppsTableModel(QAbstractTableModel):
    """Model nền cho danh sách AppInfo.

    - ``DisplayRole``: văn bản hiển thị (dùng ``size_text`` / ``date_text``).
    - ``UserRole``: khoá sắp xếp thô (size dùng ``estimate_size_kb``, ngày dùng
      ``install_date`` YYYYMMDD) và giá trị ``source`` để lọc.
    """

    def __init__(self, apps=None, parent=None):
        super().__init__(parent)
        self._apps = list(apps or [])

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._apps)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if index.row() >= len(self._apps):
            return None
        app = self._apps[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            return self._display(app, col)
        if role == Qt.ItemDataRole.UserRole:
            return self._sort_key(app, col)
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._tooltip(app)
        if role == Qt.ItemDataRole.TextAlignmentRole and col == 3:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        return None

    def _display(self, app, col) -> str:
        if col == 0:
            return app.name or ""
        if col == 1:
            return app.version or ""
        if col == 2:
            return app.publisher or ""
        if col == 3:
            return app.size_text
        if col == 4:
            return app.date_text
        if col == 5:
            return SOURCE_LABELS.get(app.source, app.source or "")
        return ""

    def _sort_key(self, app, col):
        if col == 0:
            return (app.name or "").casefold()
        if col == 1:
            return (app.version or "").casefold()
        if col == 2:
            return (app.publisher or "").casefold()
        if col == 3:
            return int(app.estimate_size_kb or 0)
        if col == 4:
            try:
                return int(app.install_date or "0")
            except ValueError:
                return 0
        if col == 5:
            return (app.source or "").casefold()
        return ""

    def _tooltip(self, app) -> str:
        lines = [app.name or ""]
        if app.publisher:
            lines.append(f"Nhà phát hành: {app.publisher}")
        if app.version:
            lines.append(f"Phiên bản: {app.version}")
        if app.install_date:
            lines.append(f"Ngày cài: {app.date_text}")
        if app.install_location:
            lines.append(f"Đường dẫn: {app.install_location}")
        if app.uninstall_string:
            lines.append(f"Lệnh gỡ: {app.uninstall_string}")
        if app.registry_key:
            lines.append(f"Registry: {app.registry_key}")
        return "\n".join(lines)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal:
            if role == Qt.ItemDataRole.DisplayRole:
                return COLUMNS[section] if section < len(COLUMNS) else ""
            if role == Qt.ItemDataRole.ToolTipRole:
                return COLUMN_TIPS[section] if section < len(COLUMN_TIPS) else None
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return str(section + 1)
        return None

    def app_at(self, row):
        if 0 <= row < len(self._apps):
            return self._apps[row]
        return None

    def set_apps(self, apps):
        self.beginResetModel()
        self._apps = list(apps or [])
        self.endResetModel()


class AppProxyModel(QSortFilterProxyModel):
    """Proxy lọc + sắp xếp cho bảng.

    - Lọc real-time theo Tên và Nhà phát hành (``_search``).
    - Lọc theo Nguồn (``_source``).
    - Sắp xếp theo ``UserRole`` (số cho cột Dung lượng / Ngày cài).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSortRole(Qt.ItemDataRole.UserRole)
        self.setDynamicSortFilter(True)
        self._search = ""
        self._source = ""

    def set_search_text(self, text):
        self._search = (text or "").strip().casefold()
        self.invalidateFilter()

    def set_source_filter(self, source):
        self._source = (source or "").casefold()
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent):
        if parent.isValid():
            return True
        model = self.sourceModel()
        if model is None:
            return True
        if self._search:
            name = (model.data(model.index(row, 0), Qt.ItemDataRole.DisplayRole) or "").casefold()
            publisher = (model.data(model.index(row, 2), Qt.ItemDataRole.DisplayRole) or "").casefold()
            if self._search not in name and self._search not in publisher:
                return False
        if self._source:
            source = (model.data(model.index(row, 5), Qt.ItemDataRole.UserRole) or "").casefold()
            if source != self._source:
                return False
        return True

    def lessThan(self, left, right):
        model = left.model()
        if model is None:
            return super().lessThan(left, right)
        lv = model.data(left, Qt.ItemDataRole.UserRole)
        rv = model.data(right, Qt.ItemDataRole.UserRole)
        if isinstance(lv, bool) or isinstance(rv, bool):
            return str(lv).casefold() < str(rv).casefold()
        if isinstance(lv, (int, float)) and isinstance(rv, (int, float)):
            return lv < rv
        left_text = "" if lv is None else str(lv)
        right_text = "" if rv is None else str(rv)
        return left_text.casefold() < right_text.casefold()


# ==== Người lao động (worker) chạy trên QThread, giao tiếp bằng Signal ====

class EnumerateWorker(QObject):
    """Quét toàn bộ registry trên nền, trả về danh sách AppInfo."""

    done = Signal(list)
    error = Signal(str)

    def run(self):
        try:
            apps = enumerator.enumerate_apps()
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))
            return
        self.done.emit(apps or [])


class UninstallWorker(QObject):
    """Gỡ cài đặt lần lượt nhiều ứng dụng (tuần tự) trên nền.

    Mỗi app: ``uninstall.run_uninstall(app, quiet)`` rồi ``proc.wait()``
    (tránh xung đột tiến trình cài đặt, vd msiexec).
    """

    started = Signal(int, int, str)              # index, total, name
    item_done = Signal(int, int, str, bool, str)  # index, total, name, ok, message
    failed = Signal(str)
    done = Signal(list)                          # list[dict]  kết quả tổng hợp

    def __init__(self, jobs):
        super().__init__()
        #: jobs: list[(AppInfo, quiet: bool)]
        self._jobs = jobs or []

    def run(self):
        results = []
        total = len(self._jobs)
        for i, (app, quiet) in enumerate(self._jobs, start=1):
            self.started.emit(i, total, app.name)
            ok = False
            message = ""
            try:
                ok, message, proc = uninstall.run_uninstall(app, quiet=quiet)
                if proc is not None:
                    proc.wait()
            except Exception as exc:  # noqa: BLE001
                ok, message, proc = False, str(exc), None
            results.append({"name": app.name, "ok": ok, "message": message,
                            "app": app})
            self.item_done.emit(i, total, app.name, ok, message or "")
        self.done.emit(results)


class RestorePointWorker(QObject):
    """Tạo System Restore Point trên nền (Nhóm II)."""

    done = Signal(bool, str)   # (ok, message)

    def run(self):
        try:
            ok, msg = backup.create_restore_point()
        except Exception as exc:  # noqa: BLE001
            ok, msg = False, str(exc)
        self.done.emit(bool(ok), str(msg))


class UpdateCheckWorker(QObject):
    """Kiểm tra bản cập nhật GitHub Releases trên nền (Nhóm V)."""

    done = Signal(object)   # dict kết quả từ updater.check_for_updates()

    def run(self):
        try:
            result = updater.check_for_updates()
        except Exception as exc:  # noqa: BLE001 - không để lỗi chặn UI
            result = {"ok": False, "has_update": False, "latest_version": "",
                      "release_url": "", "download_url": "", "release_notes": "",
                      "error": str(exc)}
        self.done.emit(result)


class UpdateDownloadWorker(QObject):
    """Tải file .exe bản mới về máy trên nền (Nhóm V)."""

    done = Signal(bool, str)   # (ok, file_path_or_error)

    def __init__(self, download_url):
        super().__init__()
        self._download_url = download_url

    def run(self):
        try:
            ok, msg = updater.download_update(self._download_url)
        except Exception as exc:  # noqa: BLE001
            ok, msg = False, str(exc)
        self.done.emit(bool(ok), str(msg))


class CoreUpdateWorker(QObject):
    """Tải gói lõi app_core.zip + áp dụng trên nền (cập nhật nhẹ, Tách vỏ)."""

    done = Signal(bool, str)   # (ok, message)

    def __init__(self, download_url):
        super().__init__()
        self._download_url = download_url

    def run(self):
        try:
            ok, msg = updater.download_core_update(self._download_url)
            if ok:
                ok, msg = updater.apply_pending_update()
        except Exception as exc:  # noqa: BLE001
            ok, msg = False, str(exc)
        self.done.emit(bool(ok), str(msg))


class LeftoverScanWorker(QObject):
    """Quét leftover cho một ứng dụng trên nền."""

    done = Signal(object, list)   # (AppInfo, list[dict])
    error = Signal(str)

    def __init__(self, app):
        super().__init__()
        self._app = app

    def run(self):
        try:
            found = leftover.scan_leftovers(self._app)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))
            return
        self.done.emit(self._app, found or [])


class LeftoverDeleteWorker(QObject):
    """Xoá các leftover đã chọn trên nền.

    - Registry / Uninstall Entry: ``leftover.delete_registry_key`` (tự sao lưu
      .reg + ghi log bên trong).
    - File / Thư mục: ``leftover.delete_path`` (tự kill tiến trình kẹt + ghi log).
    """

    progress = Signal(int, int, str)  # index, total, path
    done = Signal(list, list)         # targets, results
    error = Signal(str)

    def __init__(self, app_name, items):
        super().__init__()
        self._app_name = app_name or ""
        #: items: list[(kind, path)]
        self._items = items or []

    def run(self):
        targets = [{"kind": k, "path": p} for k, p in self._items]
        results = []
        n = len(self._items)
        for i, (kind, path) in enumerate(self._items, start=1):
            detail = ""
            try:
                if kind in ("registry", "entry"):
                    ok, err = leftover.delete_registry_key(path, self._app_name)
                else:
                    ok, err = leftover.delete_path(path, self._app_name)
                status = "OK" if ok else "FAIL"
                results.append(f"{status}{detail}: {path} ({err})" if err else f"{status}{detail}: {path}")
            except Exception as exc:  # noqa: BLE001
                ok = False
                results.append(f"FAIL: {path} ({exc})")
            self.progress.emit(i, n, path)

        self.done.emit(targets, results)


# ==== Cửa sổ chính ====

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._apps = []             # toàn bộ AppInfo đã quét
        self._threads = []          # giữ tham chiếu các QThread đang chạy
        self._workers = []          # giữ tham chiếu worker (chống GC)
        self._busy = False
        self._pending_rescan = False
        self._is_admin = uninstall.is_admin()

        self.setWindowTitle(f"{APP_NAME} (Qt) {__version__}")
        self.resize(1200, 720)

        self._build_actions()
        self._build_ui()
        self._build_menubar()
        self._apply_styles()
        self._connect_signals()
        self._update_actions()

        QTimer.singleShot(0, self.refresh)

    # ---- Actions (dùng chung cho toolbar + context menu) ----

    def _build_actions(self):
        self.action_refresh = QAction("Làm mới", self)
        self.action_refresh.setShortcut(QKeySequence.StandardKey.Refresh)
        self.action_search = QAction("Tìm kiếm", self)
        self.action_search.setShortcut(QKeySequence.StandardKey.Find)      # Ctrl+F (E2)
        self.action_uninstall = QAction("Gỡ cài đặt", self)
        self.action_uninstall.setShortcut(QKeySequence("Del"))
        self.action_quiet = QAction("Gỡ im lặng", self)
        self.action_batch = QAction("Gỡ hàng loạt", self)
        self.action_leftover = QAction("Quét Leftover", self)
        self.action_open_folder = QAction("Mở thư mục cài đặt", self)
        self.action_admin = QAction("Nâng quyền Admin", self)
        self.action_backups = QAction("Mở thư mục Backups", self)
        self.action_restore_backup = QAction("Khôi phục Backup", self)
        self.action_clear_backups = QAction("Dọn lịch sử Backup", self)
        self.action_restore_point = QAction("Tạo Restore Point", self)
        self.action_update = QAction("Kiểm tra cập nhật…", self)

        self.action_refresh.triggered.connect(self.refresh)
        self.action_search.triggered.connect(self._focus_search)
        self.action_uninstall.triggered.connect(self.uninstall_selected)
        self.action_quiet.triggered.connect(self.uninstall_quiet_selected)
        self.action_batch.triggered.connect(self.uninstall_batch)
        self.action_leftover.triggered.connect(self.scan_leftover)
        self.action_open_folder.triggered.connect(self.open_install_folder)
        self.action_backups.triggered.connect(self.open_backups_folder)
        self.action_restore_backup.triggered.connect(self.open_backup_manager)
        self.action_clear_backups.triggered.connect(self.clear_backup_history)
        self.action_restore_point.triggered.connect(self.create_restore_point)
        self.action_update.triggered.connect(self.check_updates)
        self.action_admin.triggered.connect(self.raise_admin)

        # Đăng ký action với cửa sổ để phím tắt (Del, Ctrl+F, F5…) luôn hoạt động
        # kể cả khi menu ngữ cảnh chưa mở (E2).
        for act in (self.action_refresh, self.action_search, self.action_uninstall,
                    self.action_quiet, self.action_batch, self.action_leftover):
            self.addAction(act)

    def _focus_search(self):
        """Đưa tiêu điểm vào ô tìm kiếm và bôi đen nội dung (Ctrl+F)."""
        self.search_box.setFocus()
        self.search_box.selectAll()

    def _build_menubar(self):
        """Thanh menu: Trợ giúp -> Giới thiệu (G2) + Kiểm tra cập nhật (Nhóm V)."""
        help_menu = self.menuBar().addMenu("Trợ giúp")
        self.action_about = QAction("Giới thiệu", self)
        self.action_about.triggered.connect(self.show_about)
        help_menu.addAction(self.action_about)
        help_menu.addAction(self.action_update)

    def show_about(self):
        """Hiện hộp thoại Giới thiệu (tên + phiên bản) — G2."""
        QMessageBox.about(
            self, "Giới thiệu",
            f"{about_text()}\n\nPython {sys.version.split()[0]}\nQt {qVersion()}")

    # ---- Xây dựng UI ----

    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # --- Thanh công cụ ---
        toolbar = QFrame()
        bar = QHBoxLayout(toolbar)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(6)

        self.btn_refresh = self._button("Làm mới", "Quét lại danh sách ứng dụng", self.refresh)
        self.btn_uninstall = self._button("Gỡ cài đặt", "Gỡ ứng dụng đang chọn", self.uninstall_selected, danger=True)
        self.btn_quiet = self._button("Gỡ im lặng", "Gỡ bằng lệnh im lặng (build_quiet_command)", self.uninstall_quiet_selected)
        self.btn_batch = self._button("Gỡ hàng loạt", "Gỡ lần lượt các ứng dụng đã chọn", self.uninstall_batch)
        self.btn_leftover = self._button("Quét Leftover", "Quét rác cho ứng dụng đang chọn", self.scan_leftover, primary=True)
        self.btn_open_folder = self._button("Mở thư mục", "Mở thư mục cài đặt", self.open_install_folder)
        self.btn_backups = self._button("Mở Backups", "Mở thư mục backups/ (khôi phục .reg)", self.open_backups_folder)
        self.btn_restore_backup = self._button("Khôi phục Backup", "Chọn file .reg và khôi phục về registry", self.open_backup_manager, primary=True)
        self.btn_clear_backups = self._button("Dọn Backups", "Xoá toàn bộ .reg + history.jsonl", self.clear_backup_history)
        self.btn_restore_point = self._button("Tạo Restore Point", "Tạo Điểm Khôi Phục Hệ Thống (System Restore Point)", self.create_restore_point)

        bar.addWidget(self.btn_refresh)
        bar.addWidget(self.btn_uninstall)
        bar.addWidget(self.btn_quiet)
        bar.addWidget(self.btn_batch)
        bar.addWidget(self.btn_leftover)
        bar.addWidget(self.btn_open_folder)
        bar.addWidget(self.btn_backups)
        bar.addWidget(self.btn_restore_backup)
        bar.addWidget(self.btn_clear_backups)
        bar.addWidget(self.btn_restore_point)

        if not self._is_admin:
            self.btn_admin = self._button("Nâng quyền Admin", "Chạy lại với quyền Administrator (UAC)", self.raise_admin)
            bar.addWidget(self.btn_admin)

        bar.addStretch(1)
        bar.addWidget(QLabel("Tìm kiếm:"))
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Theo Tên / Nhà phát hành…")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setMinimumWidth(220)
        bar.addWidget(self.search_box)

        bar.addWidget(QLabel("Nguồn:"))
        self.source_combo = QComboBox()
        for label, value in SOURCE_FILTERS:
            self.source_combo.addItem(label, value)
        bar.addWidget(self.source_combo)

        root.addWidget(toolbar)

        # --- Bảng dữ liệu ---
        self.model = AppsTableModel(parent=self)
        self.proxy = AppProxyModel(self)
        self.proxy.setSourceModel(self.model)

        self.table_view = QTableView()
        self.table_view.setModel(self.proxy)
        self.table_view.setSortingEnabled(True)
        self.table_view.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.horizontalHeader().setSortIndicatorShown(True)
        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_view.setColumnWidth(0, 280)
        self.table_view.setColumnWidth(1, 110)
        self.table_view.setColumnWidth(2, 170)
        self.table_view.setColumnWidth(3, 110)
        self.table_view.setColumnWidth(4, 110)

        self.count_label = QLabel("Chưa có dữ liệu")
        self.count_label.setObjectName("count")

        # --- Nhật ký ---
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(600)
        self.log_view.setFixedHeight(150)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.table_view)
        splitter.addWidget(self.log_view)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)

        root.addWidget(self.count_label)
        root.addWidget(splitter, 1)
        self.setCentralWidget(central)

        # --- Panel chi tiết app đang chọn (E1) ---
        self._build_detail_dock()

        # --- Status bar + progress ---
        self.progress = QProgressBar()
        self.progress.setFixedWidth(220)
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)
        self.statusBar().showMessage("Sẵn sàng.")

    def _build_detail_dock(self):
        """Dock bên phải hiển thị chi tiết app đang chọn (E1)."""
        dock = QDockWidget("Chi tiết ứng dụng", self)
        dock.setObjectName("detailDock")
        dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea
                             | Qt.DockWidgetArea.LeftDockWidgetArea)

        container = QWidget()
        form = QFormLayout(container)
        form.setContentsMargins(10, 10, 10, 10)
        form.setSpacing(6)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        #: key -> QLabel giá trị, dùng lại trong `_update_detail`.
        self._detail_values = {}
        for key, label in (
            ("name", "Tên"),
            ("version", "Phiên bản"),
            ("publisher", "Nhà phát hành"),
            ("size", "Dung lượng"),
            ("date", "Ngày cài"),
            ("source", "Nguồn"),
            ("location", "Vị trí cài"),
            ("uninstall", "Lệnh gỡ"),
            ("quiet", "Lệnh gỡ im lặng"),
            ("product", "Product code (MSI)"),
            ("registry", "Registry key"),
        ):
            value = QLabel("—")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value.setStyleSheet("color:#c8cbd0;")
            self._detail_values[key] = value
            form.addRow(f"{label}:", value)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(container)
        dock.setWidget(scroll)
        dock.setMinimumWidth(300)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.detail_dock = dock
        self._update_detail()

    def _update_detail(self, *_args):
        """Cập nhật panel chi tiết theo app đang chọn (rỗng nếu không chọn)."""
        if not hasattr(self, "_detail_values"):
            return
        apps = self._selected_apps()
        app = apps[0] if apps else None
        values = self._detail_values
        if app is None:
            for lbl in values.values():
                lbl.setText("—")
            return
        values["name"].setText(app.name or "—")
        values["version"].setText(app.version or "—")
        values["publisher"].setText(app.publisher or "—")
        values["size"].setText(app.size_text or "—")
        values["date"].setText(app.date_text or "—")
        values["source"].setText(SOURCE_LABELS.get(app.source, app.source or "—"))
        values["location"].setText(app.install_location or "—")
        values["uninstall"].setText(app.uninstall_string or "—")
        values["quiet"].setText(app.quiet_uninstall_string or "—")
        values["product"].setText(app.product_code or "—")
        values["registry"].setText(app.registry_key or "—")

    # ---- Tiện ích chung ----

    def _button(self, text, tip, slot, primary=False, danger=False):
        btn = QPushButton(text)
        btn.setToolTip(tip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if primary:
            btn.setObjectName("primary")
        elif danger:
            btn.setObjectName("danger")
        if slot is not None:
            btn.clicked.connect(slot)
        return btn

    def _apply_styles(self):
        self.setStyleSheet(STYLESHEET)

    def _connect_signals(self):
        self.search_box.textChanged.connect(self.proxy.set_search_text)
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        self.table_view.customContextMenuRequested.connect(self._show_context_menu)
        if self.table_view.selectionModel() is not None:
            self.table_view.selectionModel().selectionChanged.connect(self._update_actions)
            self.table_view.selectionModel().selectionChanged.connect(self._update_detail)

    def _on_source_changed(self, index):
        self.proxy.set_source_filter(self.source_combo.itemData(index) or "")
        self._update_count_label()

    def _update_count_label(self):
        total = self.proxy.rowCount()
        visible = len(self._apps)
        if total != visible:
            self.count_label.setText(f"Hiển thị {total} / {visible} ứng dụng")
        else:
            self.count_label.setText(f"{visible} ứng dụng")

    def _status(self, text):
        self.statusBar().showMessage(text)

    def _log(self, text):
        self.log_view.appendPlainText(f"[{datetime.now().strftime('%H:%M:%S')}] {text}")

    # ---- Trạng thái nút / action ----

    def _update_actions(self, *_args):
        busy = self._busy
        has_sel = bool(self.table_view.selectionModel()
                       and self.table_view.selectionModel().hasSelection())

        self.btn_refresh.setEnabled(not busy)
        for b in (self.btn_uninstall, self.btn_quiet, self.btn_batch,
                  self.btn_leftover, self.btn_open_folder):
            b.setEnabled((not busy) and has_sel)
        self.btn_backups.setEnabled(not busy)
        self.btn_restore_backup.setEnabled(not busy)
        self.btn_clear_backups.setEnabled(not busy)
        self.btn_restore_point.setEnabled(not busy)
        if hasattr(self, "btn_admin"):
            self.btn_admin.setEnabled(not busy)

        self.action_refresh.setEnabled(not busy)
        for a in (self.action_uninstall, self.action_quiet, self.action_batch,
                  self.action_leftover, self.action_open_folder):
            a.setEnabled((not busy) and has_sel)
        self.action_admin.setEnabled(not busy)
        self.action_backups.setEnabled(not busy)
        self.action_restore_backup.setEnabled(not busy)
        self.action_clear_backups.setEnabled(not busy)
        self.action_restore_point.setEnabled(not busy)
        self.action_update.setEnabled(not busy)

    # ---- Lấy các app đang chọn (qua proxy) ----

    def _selected_apps(self):
        apps = []
        seen = set()
        model = self.model
        for index in self.table_view.selectionModel().selectedRows():
            src = self.proxy.mapToSource(index)
            app = model.app_at(src.row())
            if app is not None and id(app) not in seen:
                seen.add(id(app))
                apps.append(app)
        return apps

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        menu.addAction(self.action_refresh)
        menu.addSeparator()
        menu.addAction(self.action_uninstall)
        menu.addAction(self.action_quiet)
        menu.addAction(self.action_batch)
        menu.addAction(self.action_leftover)
        menu.addAction(self.action_open_folder)
        menu.addSeparator()
        menu.addAction(self.action_backups)
        menu.addAction(self.action_restore_backup)
        menu.addAction(self.action_clear_backups)
        menu.addAction(self.action_restore_point)
        if not self._is_admin:
            menu.addSeparator()
            menu.addAction(self.action_admin)
        menu.exec(self.table_view.viewport().mapToGlobal(pos))

    # ---- Đa luồng: chạy worker trên QThread ----

    def _start_worker(self, worker):
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(thread.quit)
        worker.done.connect(worker.deleteLater)
        if hasattr(worker, "error"):
            worker.error.connect(thread.quit)
            worker.error.connect(worker.deleteLater)
        if hasattr(worker, "failed"):
            worker.failed.connect(thread.quit)
            worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda t=thread: self._on_thread_finished(t))
        # Giữ tham chiếu worker để tránh bị GC (PySide6 không giữ Python ref qua
        # signal connection); dọn dẹp khi thread kết thúc.
        self._workers.append(worker)
        self._threads.append(thread)
        self._busy = True
        self._update_actions()
        thread.start()

    def _on_thread_finished(self, thread):
        if thread in self._threads:
            self._threads.remove(thread)
        if not self._threads:
            self._busy = False
            self.progress.hide()
            self._workers.clear()
            if self._pending_rescan:
                self._pending_rescan = False
                QTimer.singleShot(0, self.refresh)
            else:
                self._update_actions()

    # ---- Hành động: Làm mới (quét registry) ----

    def refresh(self):
        if self._busy:
            return
        self._status("Đang quét registry…")
        self._log("Bắt đầu quét danh sách ứng dụng.")
        worker = EnumerateWorker()
        worker.done.connect(self._on_scan_done)
        worker.error.connect(self._on_worker_error)
        self._start_worker(worker)

    def _on_scan_done(self, apps):
        self._apps = list(apps or [])
        self.model.set_apps(self._apps)
        self._update_count_label()
        self._update_detail()
        self._status(f"Đã tải {len(self._apps)} ứng dụng.")
        self._log(f"Quét xong: {len(self._apps)} ứng dụng.")
        self._update_actions()

    def _on_worker_error(self, message):
        self._status("Lỗi: " + str(message))
        self._log("Lỗi: " + str(message))
        QMessageBox.critical(self, "Lỗi", str(message))
        self._update_actions()

    def _confirm(self, title, text, default_no=True):
        buttons = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        default = QMessageBox.StandardButton.No if default_no else QMessageBox.StandardButton.Yes
        return (QMessageBox.question(self, title, text, buttons, default)
                == QMessageBox.StandardButton.Yes)

    def _running_note(self, apps) -> str:
        """Đoạn cảnh báo nếu app trong ``apps`` đang chạy (E3); rỗng nếu không.

        Chỉ chạy ``tasklist`` MỘT lần cho mọi app (qua ``list_running_images``).
        """
        try:
            images = leftover.list_running_images()
        except Exception:  # noqa: BLE001 - không để lỗi dò tiến trình chặn UI
            return ""
        lines = []
        for app in apps:
            procs = leftover.find_running_processes(app, images)
            if procs:
                lines.append(f"• {app.name}: {', '.join(procs)}")
        if not lines:
            return ""
        return ("\n\n⚠ Ứng dụng đang chạy:\n" + "\n".join(lines)
                + "\nNên ĐÓNG chúng trước khi tiếp tục để tránh lỗi.")

    # ---- Hành động: Gỡ cài đặt ----

    def uninstall_selected(self):
        apps = self._selected_apps()
        if not apps:
            QMessageBox.information(self, "Gỡ cài đặt", "Vui lòng chọn một ứng dụng.")
            return
        app = apps[0]
        # Nhóm I: kiểm tra trình gỡ; nếu mất/hỏng -> đề xuất Force Uninstall.
        ready, reason = uninstall.check_uninstaller_status(app)
        if not ready:
            self._status(f"Trình gỡ của \"{app.name}\" không khả dụng: {reason}")
            if self._ask_force_uninstall(app, reason):
                self._scan_leftover_for(app)
            return
        if not app.can_uninstall:
            QMessageBox.warning(self, "Gỡ cài đặt", f"\"{app.name}\" không có lệnh gỡ chuẩn.")
            return
        text = (f"Gỡ cài đặt \"{app.name}\" {app.version or ''}?\n\n"
                "Thao tác này không thể hoàn tác." + self._running_note([app]))
        if self._confirm("Xác nhận gỡ cài đặt", text):
            self._run_uninstall_jobs([(app, False)])

    def _ask_force_uninstall(self, app, reason):
        """Hỏi người dùng chuyển sang chế độ Force Uninstall (Nhóm I).

        Trả về True nếu người dùng đồng ý quét & dọn leftover trực tiếp.
        """
        reason = (reason or "không rõ nguyên nhân").strip()
        text = (f"Trình gỡ cài đặt gốc không khả dụng ({reason}).\n\n"
                f"Bạn có muốn chuyển sang chế độ Quét & Dọn sạch Leftover "
                f"(Force Uninstall) cho ứng dụng \"{app.name}\" không?")
        return self._confirm("Gỡ cưỡng bức (Force Uninstall)", text)

    def uninstall_quiet_selected(self):
        apps = self._selected_apps()
        if not apps:
            QMessageBox.information(self, "Gỡ im lặng", "Vui lòng chọn một ứng dụng.")
            return
        app = apps[0]
        if not app.can_uninstall:
            QMessageBox.warning(self, "Gỡ im lặng", f"\"{app.name}\" không có lệnh gỡ chuẩn.")
            return
        cmd = uninstall.build_quiet_command(app)
        text = (f"Gỡ im lặng \"{app.name}\" {app.version or ''}?\n\n"
                f"Lệnh sẽ chạy:\n{cmd or '(không suy luận được, dùng lệnh mặc định)'}"
                + self._running_note([app]))
        if self._confirm("Xác nhận gỡ im lặng", text):
            self._run_uninstall_jobs([(app, True)])

    def uninstall_batch(self):
        apps = [a for a in self._selected_apps() if a.can_uninstall]
        if not apps:
            QMessageBox.information(self, "Gỡ hàng loạt",
                                    "Không có ứng dụng nào được chọn (hoặc có lệnh gỡ chuẩn).")
            return
        names = "\n".join(f"• {a.name} {a.version or ''}".strip() for a in apps[:15])
        if len(apps) > 15:
            names += f"\n… và {len(apps) - 15} ứng dụng khác"
        text = (f"Gỡ lần lượt {len(apps)} ứng dụng:\n{names}\n\n"
                "Chạy tuần tự (proc.wait()) để tránh xung đột msiexec. Tiếp tục?"
                + self._running_note(apps))
        if self._confirm("Xác nhận gỡ hàng loạt", text):
            self._run_uninstall_jobs([(a, False) for a in apps])

    def _run_uninstall_jobs(self, jobs):
        worker = UninstallWorker(jobs)
        worker.started.connect(self._on_uninstall_started)
        worker.item_done.connect(self._on_uninstall_item)
        worker.done.connect(self._on_uninstall_done)
        worker.failed.connect(self._on_worker_error)
        self.progress.setRange(1, len(jobs))
        self.progress.setValue(0)
        self.progress.show()
        self._start_worker(worker)

    def _on_uninstall_started(self, index, total, name):
        self.progress.setValue(index)
        self._status(f"Đang gỡ ({index}/{total}): {name} …")
        self._log(f"Bắt đầu gỡ ({index}/{total}): {name}")

    def _on_uninstall_item(self, index, total, name, ok, message):
        tag = "OK" if ok else "FAIL"
        self._status(f"{tag} — {name} ({index}/{total}). {message or ''}".rstrip())
        self._log(f"Kết thúc ({index}/{total}): {name} → {tag}. {message or ''}".rstrip())

    def _on_uninstall_done(self, results):
        ok_count = sum(1 for r in results if r["ok"])
        fails = [r for r in results if not r["ok"]]
        self._log(f"Hoàn tất gỡ hàng loạt: {ok_count}/{len(results)} thành công.")
        if fails:
            detail = "\n".join(f"• {r['name']}: {r['message'] or 'lỗi không xác định'}" for r in fails[:10])
            QMessageBox.warning(self, "Gỡ cài đặt",
                                f"{ok_count}/{len(results)} thành công.\n\n" + detail)
        else:
            QMessageBox.information(self, "Gỡ cài đặt", f"Đã gỡ {ok_count} ứng dụng.")
        if ok_count:
            self._pending_rescan = True
            # Sau khi gỡ, xả cache `winget list` để refresh phản ánh app đã gỡ (D3).
            enumerator.clear_winget_cache()
        # Nhóm I: nếu CHỈ một app được gỡ và thất bại -> đề xuất Force Uninstall.
        if len(results) == 1 and fails and fails[0].get("app") is not None:
            failed = fails[0]
            if self._ask_force_uninstall(failed["app"],
                                         failed["message"] or "trình gỡ báo lỗi"):
                self._scan_leftover_for(failed["app"])

    # ---- Hành động: Quét leftover ----

    def scan_leftover(self):
        apps = self._selected_apps()
        if not apps:
            QMessageBox.information(self, "Quét Leftover", "Vui lòng chọn một ứng dụng.")
            return
        self._scan_leftover_for(apps[0])

    def _scan_leftover_for(self, app):
        """Quét leftover cho một app cụ thể (dùng cho nút và Force Uninstall)."""
        if app is None:
            return
        self._status(f"Đang quét leftover cho \"{app.name}\" …")
        self._log(f"Quét leftover cho \"{app.name}\".")
        worker = LeftoverScanWorker(app)
        worker.done.connect(self._on_leftover_done)
        worker.error.connect(self._on_worker_error)
        self._start_worker(worker)

    def _on_leftover_done(self, app, leftovers):
        self._status(f"Quét xong leftover cho \"{app.name}\": {len(leftovers)} mục.")
        self._log(f"Leftover \"{app.name}\": {len(leftovers)} mục.")
        if not leftovers:
            QMessageBox.information(self, "Leftover",
                                    f"Không tìm thấy leftover cho \"{app.name}\".")
            return
        dlg = LeftoverDialog(app, leftovers, self)
        dlg.exec()

    # ---- Hành động: Mở thư mục cài đặt ----

    def open_install_folder(self):
        apps = self._selected_apps()
        if not apps:
            QMessageBox.information(self, "Mở thư mục", "Vui lòng chọn một ứng dụng.")
            return
        app = apps[0]
        folder = app.install_location or self._guess_folder(app)
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, "Mở thư mục",
                                f"Không xác định được thư mục cài đặt của \"{app.name}\".")
            return
        try:
            os.startfile(folder)
            self._status(f"Đã mở: {folder}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Mở thư mục", f"{folder}\n\n{exc}")

    @staticmethod
    def _guess_folder(app):
        """Dò tìm nhanh thư mục từ uninstall_string khi install_location trống."""
        if not app.uninstall_string:
            return ""
        match = re.search(r'"([A-Za-z]:[\\/][^"]+)"', app.uninstall_string)
        if match:
            path = match.group(1)
            if os.path.isdir(path):
                return path
            parent = os.path.dirname(path)
            return parent if os.path.isdir(parent) else ""
        return ""

    # ---- Hành động: Backup (mở thư mục / dọn lịch sử) ----

    def open_backups_folder(self):
        """Mở thư mục backups/ và hướng dẫn khôi phục file .reg."""
        try:
            os.startfile(str(backup.BACKUP_DIR))
        except Exception as exc:  # noqa: BLE001 - luôn phải báo lỗi cho UI
            QMessageBox.warning(
                self, "Backups", f"Không mở được thư mục backups:\n{exc}")
            return
        QMessageBox.information(
            self, "Khôi phục từ backup",
            "Đã mở thư mục backups/.\n\n"
            "• Mỗi lần xoá registry, app xuất 1 file .reg (kèm timestamp).\n"
            "• Khôi phục: bấm nút 'Khôi phục Backup' (chọn file rồi Khôi phục), "
            "hoặc double-click file .reg.\n"
            "• history.jsonl ghi lại các thao tác đã xoá.")
        self._status("Đã mở thư mục backups.")

    def clear_backup_history(self):
        """Xoá toàn bộ .reg + làm trống history.jsonl (có cảnh báo)."""
        if not self._confirm(
                "Dọn lịch sử backup",
                "Xoá toàn bộ file .reg và lịch sử history.jsonl trong thư mục "
                "backups/?\n\nSau thao tác này sẽ KHÔNG thể khôi phục các nhánh "
                "registry đã sao lưu. Tiếp tục?"):
            return
        removed = backup.clear_backups()
        QMessageBox.information(
            self, "Đã dọn",
            f"Đã xoá {removed} file .reg và làm trống history.jsonl.")
        self._log(f"Dọn backups: xoá {removed} file .reg.")

    def open_backup_manager(self):
        """Mở hộp thoại liệt kê backup (.reg + thời gian) và khôi phục trực tiếp."""
        dlg = BackupDialog(self)
        dlg.exec()
        if dlg.restored_count:
            self._log(f"Đã khôi phục {dlg.restored_count} file backup.")
            self.refresh()

    # ---- Hành động: Tạo System Restore Point ----

    def create_restore_point(self):
        """Tạo System Restore Point trên nền (Nhóm II)."""
        if not self._confirm(
                "Tạo Restore Point",
                "Tạo Điểm Khôi Phục Hệ Thống (System Restore Point) ngay bây giờ?\n\n"
                "Thao tác này cần quyền Administrator và có thể mất vài chục giây."):
            return
        self._status("Đang tạo System Restore Point…")
        self._log("Bắt đầu tạo System Restore Point.")
        worker = RestorePointWorker()
        worker.done.connect(self._on_restore_point_done)
        self._start_worker(worker)

    def _on_restore_point_done(self, ok, message):
        self._status(message)
        self._log(("OK: " if ok else "LỖI: ") + message)
        if ok:
            QMessageBox.information(self, "Restore Point", message)
        else:
            QMessageBox.warning(self, "Restore Point", message)

    # ---- Hành động: Kiểm tra cập nhật (Nhóm V) ----

    def check_updates(self):
        """Kiểm tra bản mới trên GitHub Releases (QThread + Signal)."""
        self._status("Đang kiểm tra cập nhật…")
        self._log("Kiểm tra cập nhật từ GitHub Releases.")
        worker = UpdateCheckWorker()
        worker.done.connect(self._on_updates_checked)
        self._start_worker(worker)

    def _on_updates_checked(self, result):
        result = result or {}
        if not result.get("ok"):
            self._status("Không kiểm tra được cập nhật.")
            self._log("Lỗi kiểm tra cập nhật: " + str(result.get("error")))
            QMessageBox.warning(
                self, "Kiểm tra cập nhật",
                "Không kiểm tra được cập nhật:\n"
                + str(result.get("error") or "lỗi không xác định"))
            return
        if not result.get("has_update"):
            self._status(f"Bạn đang dùng bản mới nhất ({__version__}).")
            self._log(f"Đang ở bản mới nhất ({__version__}).")
            QMessageBox.information(
                self, "Kiểm tra cập nhật",
                f"Bạn đang dùng bản mới nhất ({__version__}).")
            return

        latest = result.get("latest_version") or "?"
        current = result.get("current_version") or __version__
        notes = (result.get("notes") or result.get("release_notes") or "").strip()
        if len(notes) > 800:
            notes = notes[:800] + "…"
        download_url = result.get("download_url") or ""
        release_url = result.get("release_url") or ""
        body = (f"Phiên bản hiện tại: {current}\n"
                f"Phiên bản mới nhất: {latest}\n\n"
                + (f"Ghi chú phát hành:\n{notes}\n\n" if notes else ""))
        self._status(f"Có bản mới {latest}.")
        self._log(f"Có bản mới: {latest}.")

        # Có gói lõi app_core.zip -> cập nhật nhẹ + khởi động lại (Tách vỏ).
        if download_url.lower().endswith(".zip"):
            if self._confirm(
                    "Có bản cập nhật mới",
                    body + "Bạn có muốn tự động tải gói cập nhật nhẹ "
                           "(app_core.zip) và khởi động lại ứng dụng ngay không?"):
                self._status("Đang tải gói cập nhật nhẹ…")
                self._log("Tải gói lõi app_core.zip.")
                worker = CoreUpdateWorker(download_url)
                worker.done.connect(self._on_core_update_done)
                self._start_worker(worker)
                return
            self._open_release_page(release_url)
            return

        # Gói .exe đầy đủ: hỏi mở trang tải về, hoặc tải trực tiếp.
        if release_url and self._confirm(
                "Có bản cập nhật mới",
                body + "Mở trang tải về trên trình duyệt?"):
            self._open_release_page(release_url)
            return
        if not download_url:
            QMessageBox.information(
                self, "Cập nhật",
                body + "Bản phát hành không kèm gói tải trực tiếp. "
                       "Hãy mở trang tải về để tải thủ công.")
            return
        if self._confirm("Tải trực tiếp",
                         f"Tải bản mới về máy?\n\n{os.path.basename(download_url)}"):
            self._status("Đang tải bản cập nhật…")
            self._log(f"Tải bản cập nhật: {os.path.basename(download_url)}")
            worker = UpdateDownloadWorker(download_url)
            worker.done.connect(self._on_update_downloaded)
            self._start_worker(worker)

    def _open_release_page(self, release_url):
        """Mở trang GitHub Release bằng trình duyệt mặc định (nếu có URL)."""
        if not release_url:
            QMessageBox.information(self, "Cập nhật",
                                    "Không có URL trang phát hành để mở.")
            return
        try:
            os.startfile(release_url)
            self._status(f"Đã mở trang tải về: {release_url}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Cập nhật",
                                f"Không mở được trang tải về:\n{exc}")

    def _on_core_update_done(self, ok, message):
        if not ok:
            self._status("Cập nhật lõi thất bại.")
            self._log("Lỗi cập nhật lõi: " + str(message))
            QMessageBox.warning(self, "Cập nhật",
                                f"Cập nhật lõi thất bại:\n{message}")
            return
        self._status("Đã áp dụng gói cập nhật nhẹ.")
        self._log("Đã áp dụng gói lõi; khởi động lại ứng dụng.")
        QMessageBox.information(
            self, "Cập nhật",
            "Đã tải và áp dụng gói cập nhật nhẹ.\n"
            "Ứng dụng sẽ khởi động lại ngay bây giờ.")
        updater.restart_application()

    def _on_update_downloaded(self, ok, message):
        if ok:
            self._status(f"Đã tải bản mới: {message}")
            self._log(f"Đã tải bản mới về: {message}")
            QMessageBox.information(
                self, "Cập nhật",
                f"Đã tải bản mới về:\n{message}\n\n"
                "Hãy đóng ứng dụng và chạy file này để cập nhật.")
        else:
            self._status("Tải bản cập nhật thất bại.")
            self._log("Lỗi tải cập nhật: " + str(message))
            QMessageBox.warning(self, "Cập nhật", f"Tải thất bại:\n{message}")

    # ---- Hành động: Nâng quyền Admin ----

    def raise_admin(self):
        ok = uninstall.relaunch_as_admin()
        if ok:
            QMessageBox.information(self, "Nâng quyền",
                                    "Đang khởi động lại với quyền Administrator (UAC)…")
            QTimer.singleShot(800, self.close)
        else:
            QMessageBox.warning(self, "Nâng quyền",
                                "Không thể nâng quyền. Hãy chạy lại bằng run-admin.bat.")


# ==== Hộp thoại Leftover ====

class LeftoverDialog(QDialog):
    """Hiển thị leftover phân nhóm theo cây (Registry / File-Thư mục / Entry).

    - Checkbox mặc định chỉ tích nhóm ``entry``.
    - Khi xác nhận: sao lưu registry, xoá mục, ghi log qua backup.py.
    """

    KIND_TAG = {
        "registry": "Registry key",
        "files": "File / Thư mục",
        "entry": "Uninstall Entry",
    }

    #: Nhãn độ tin cậy (Nhóm II), ánh xạ từ giá trị ``confidence``.
    CONF_TAG = {
        "high": "Cao",
        "medium": "Trung bình",
    }

    def __init__(self, app, leftovers, parent=None):
        super().__init__(parent)
        self._app = app
        self._items = list(leftovers or [])
        self._deleting = False

        self.setWindowTitle(f"Leftover — {app.name}")
        self.resize(820, 580)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Dòng tiêu đề + chọn/bỏ hết
        head = QHBoxLayout()
        title = QLabel(f"Leftover cho:&nbsp;&nbsp;<b>{app.name}</b> {app.version or ''}")
        title.setTextFormat(Qt.TextFormat.RichText)
        head.addWidget(title)
        head.addStretch(1)
        self.select_all_btn = QPushButton("Chọn tất cả")
        self.select_none_btn = QPushButton("Bỏ hết")
        self.select_high_btn = QPushButton("Chọn mức Cao")
        self.select_high_btn.setToolTip("Tích các mục có độ tin cậy Cao (vẫn phải xác nhận trước khi xoá)")
        head.addWidget(self.select_all_btn)
        head.addWidget(self.select_none_btn)
        head.addWidget(self.select_high_btn)
        layout.addLayout(head)

        # Cây phân nhóm
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Mục", "Đường dẫn"])
        self.tree.setColumnWidth(0, 220)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tree.setUniformRowHeights(True)
        layout.addWidget(self.tree, 1)

        hint = QLabel("Chỉ các mục được TÍCH chọn sẽ bị xoá. Registry được sao lưu thành file "
                      ".reg kèm timestamp trước khi xoá; File/Thư mục được chuyển vào "
                      "Recycle Bin (có thể khôi phục). Mọi thao tác đều được ghi vào "
                      "backups/history.jsonl.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8f8f96;")
        layout.addWidget(hint)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel
                                        | QDialogButtonBox.StandardButton.Ok, self)
        self.ok_btn = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_btn.setText("Xoá các mục đã chọn")
        self.ok_btn.setObjectName("danger")
        layout.addWidget(self.buttons)

        # Dựng cây (thiết lập trạng thái checkbox mặc định).
        self._populate()

        self.select_all_btn.clicked.connect(lambda: self._set_all_checked(True))
        self.select_none_btn.clicked.connect(lambda: self._set_all_checked(False))
        self.select_high_btn.clicked.connect(self._set_high_checked)
        self.buttons.clicked.connect(self._on_button_clicked)

    def _populate(self):
        grouped = {}
        for item in self._items:
            kind = item.get("kind", "files")
            grouped.setdefault(kind, []).append(item)
        for kind in ("registry", "files", "entry"):
            items = grouped.get(kind)
            if not items:
                continue
            group = QTreeWidgetItem([f"{GROUP_NAMES.get(kind, kind)} ({len(items)})"])
            group.setFlags(group.flags() | Qt.ItemFlag.ItemIsAutoTristate)
            group.setData(0, Qt.ItemDataRole.UserRole, None)
            for item in items:
                path = item.get("path", "")
                conf = item.get("confidence", "")
                conf_txt = self.CONF_TAG.get(conf)
                label = self.KIND_TAG.get(kind, kind)
                if conf_txt:
                    label += f"  [{conf_txt}]"
                leaf = QTreeWidgetItem([label, path])
                leaf.setFlags(leaf.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                leaf.setData(0, Qt.ItemDataRole.UserRole,
                             {"kind": kind, "path": path, "confidence": conf})
                # Mặc định chỉ tích "entry".
                leaf.setCheckState(0, Qt.CheckState.Checked if kind == "entry"
                                   else Qt.CheckState.Unchecked)
                group.addChild(leaf)
            self.tree.addTopLevelItem(group)
        self.tree.expandAll()

    def _set_all_checked(self, checked):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self._for_each_leaf(lambda leaf: leaf.setCheckState(0, state))

    def _set_high_checked(self):
        """Tích nhanh các mục có độ tin cậy 'high' (người dùng vẫn phải xác nhận)."""
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            for j in range(group.childCount()):
                leaf = group.child(j)
                data = leaf.data(0, Qt.ItemDataRole.UserRole)
                if data and data.get("confidence") == "high":
                    leaf.setCheckState(0, Qt.CheckState.Checked)

    def _for_each_leaf(self, func):
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            for j in range(group.childCount()):
                func(group.child(j))

    def _selected_items(self):
        selected = []
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            for j in range(group.childCount()):
                leaf = group.child(j)
                if leaf.checkState(0) == Qt.CheckState.Checked:
                    data = leaf.data(0, Qt.ItemDataRole.UserRole)
                    if data:
                        selected.append((data["kind"], data["path"]))
        return selected

    # ---- Confirm & xoá leftover ----

    def _on_button_clicked(self, button):
        if self._deleting:
            return
        role = self.buttons.buttonRole(button)
        if role == QDialogButtonBox.ButtonRole.RejectRole:
            self.reject()
            return
        selected = self._selected_items()
        if not selected:
            QMessageBox.information(self, "Leftover",
                                    "Bạn chưa tích chọn mục nào để xoá.")
            return
        preview = "\n".join(f"• {path}" for _, path in selected[:12])
        if len(selected) > 12:
            preview += f"\n… và {len(selected) - 12} mục nữa"
        # E3: cảnh báo nếu ứng dụng còn đang chạy.
        try:
            running = leftover.find_running_processes(self._app)
        except Exception:  # noqa: BLE001
            running = []
        running_note = (f"\n\n⚠ Ứng dụng đang chạy: {', '.join(running)}. "
                        "Nên đóng trước khi xoá leftover." if running else "")
        text = (f"Xoá {len(selected)} mục leftover của \"{self._app.name}\"?\n\n{preview}\n\n"
                "File/Thư mục sẽ được chuyển vào Recycle Bin (có thể khôi phục). "
                "Registry sẽ được sao lưu thành file .reg; mọi thao tác được ghi log."
                + running_note)
        ret = QMessageBox.question(
            self, "Xác nhận xoá leftover", text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if ret != QMessageBox.StandardButton.Yes:
            return
        self._start_deletion(selected)

    def _start_deletion(self, items):
        self._deleting = True
        self._lock_ui(True)
        self.status_label.setText(f"Đang xoá 0/{len(items)} …")
        worker = LeftoverDeleteWorker(self._app.name, items)
        worker.progress.connect(self._on_delete_progress)
        worker.done.connect(self._on_delete_done)
        worker.error.connect(self._on_delete_error)

        # Giữ tham chiếu thread + worker trên self để tránh bị Garbage Collect
        # trong lúc còn đang chạy (trước đây chỉ là biến cục bộ).
        self._thread = QThread(self)
        self._worker = worker
        worker.moveToThread(self._thread)
        self._thread.started.connect(worker.run)
        worker.done.connect(self._thread.quit)
        worker.done.connect(worker.deleteLater)
        worker.error.connect(self._thread.quit)
        worker.error.connect(worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _lock_ui(self, locked):
        self.tree.setEnabled(not locked)
        self.select_all_btn.setEnabled(not locked)
        self.select_none_btn.setEnabled(not locked)
        self.select_high_btn.setEnabled(not locked)
        self.ok_btn.setEnabled(not locked)

    def _on_delete_progress(self, index, total, path):
        self.status_label.setText(f"Đang xoá {index}/{total}: {path}")

    def _on_delete_done(self, targets, results):
        ok_count = sum(1 for r in results if r.startswith("OK"))
        self._deleting = False
        self._lock_ui(False)
        self.status_label.setText(f"Hoàn tất: {ok_count}/{len(results)} thành công.")
        detail = "\n".join(results[:40])
        if len(results) > 40:
            detail += f"\n… ({len(results) - 40} dòng nữa)"
        QMessageBox.information(
            self, "Xoá leftover",
            f"Đã xoá {ok_count}/{len(results)} mục.\n\n{detail}")
        self.accept()

    def _on_delete_error(self, message):
        self._deleting = False
        self._lock_ui(False)
        self.status_label.setText("Lỗi khi xoá leftover.")
        QMessageBox.critical(self, "Lỗi xoá leftover", str(message))


# ==== Hộp thoại khôi phục Backup ====

class BackupDialog(QDialog):
    """Danh sách file backup .reg (kèm thời gian) + khôi phục trực tiếp.

    - Liệt kê bằng ``backup.list_backup_info()`` (mới nhất đứng trước).
    - Khôi phục mục đang chọn bằng ``backup.restore_backup`` (gọi ``reg import``).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.restored_count = 0
        self._paths = []

        self.setWindowTitle("Khôi phục Backup")
        self.resize(680, 460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        layout.addWidget(QLabel("Chọn một file .reg rồi bấm \"Khôi phục\" (hoặc double-click):"))

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["File backup", "Thời gian"])
        self.tree.setColumnWidth(0, 430)
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self.tree, 1)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color:#8f8f96;")
        layout.addWidget(self.status_label)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        self.restore_btn = self.buttons.addButton("Khôi phục", QDialogButtonBox.ButtonRole.AcceptRole)
        self.restore_btn.setObjectName("primary")
        self.refresh_btn = self.buttons.addButton("Làm mới", QDialogButtonBox.ButtonRole.ActionRole)
        self.open_btn = self.buttons.addButton("Mở thư mục", QDialogButtonBox.ButtonRole.ActionRole)
        layout.addWidget(self.buttons)

        self.refresh_btn.clicked.connect(self.reload)
        self.open_btn.clicked.connect(self._open_folder)
        self.restore_btn.clicked.connect(self._restore)
        self.buttons.rejected.connect(self.reject)
        self.tree.itemDoubleClicked.connect(lambda *_: self._restore())

        self.reload()

    def reload(self):
        self.tree.clear()
        self._paths = []
        infos = backup.list_backup_info()
        for info in infos:
            item = QTreeWidgetItem([info["name"], info["time"]])
            self.tree.addTopLevelItem(item)
            self._paths.append(info["path"])
        self.status_label.setText(
            f"{len(infos)} file backup." if infos else "Chưa có file backup nào.")

    def _selected_path(self):
        items = self.tree.selectedItems()
        if not items:
            return None
        index = self.tree.indexOfTopLevelItem(items[0])
        return self._paths[index] if 0 <= index < len(self._paths) else None

    def _restore(self):
        path = self._selected_path()
        if path is None:
            QMessageBox.information(self, "Khôi phục Backup",
                                    "Hãy chọn một file backup để khôi phục.")
            return
        ret = QMessageBox.question(
            self, "Xác nhận khôi phục",
            f"Khôi phục file:\n{path.name}\n\n"
            "Các giá trị trong file sẽ được ghi/ghi đè vào registry. Tiếp tục?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if ret != QMessageBox.StandardButton.Yes:
            return
        ok, msg = backup.restore_backup(path)
        self.status_label.setText(msg)
        if ok:
            self.restored_count += 1
            QMessageBox.information(self, "Đã khôi phục", msg)
        else:
            QMessageBox.critical(self, "Lỗi khôi phục", msg)

    def _open_folder(self):
        try:
            os.startfile(str(backup.BACKUP_DIR))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Backups",
                                f"Không mở được thư mục backups:\n{exc}")


# ==== Entry point ====

def main():
    if "--version" in sys.argv or "-V" in sys.argv:
        print_version()
        return
    QApplication.setStyle("Fusion")
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setStyleSheet(STYLESHEET)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
