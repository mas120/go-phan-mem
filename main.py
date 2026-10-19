"""App Uninstaller — giao diện tkinter (entry point)."""
import os
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from uninstaller_lib.enumerator import clear_winget_cache, enumerate_apps
from uninstaller_lib.uninstall import (
    build_quiet_command,
    check_uninstaller_status,
    is_admin,
    run_uninstall,
)
from uninstaller_lib import (
    APP_NAME,
    __version__,
    about_text,
    print_version,
    backup,
    leftover,
    updater,
)

# Cấu hình cột của bảng danh sách ứng dụng.
_COLUMNS = {
    "name":      ("Tên ứng dụng",    280, True),
    "version":   ("Phiên bản",        95, False),
    "publisher": ("Nhà phát hành",   160, False),
    "size":      ("Dung lượng",       85, False),
    "date":      ("Ngày cài",         85, False),
}

# Các lựa chọn bộ lọc Nguồn: (nhãn, giá trị nguồn thô).
_SOURCE_FILTERS = [
    ("Tất cả", ""),
    ("Registry", "registry"),
    ("MSI", "msi"),
    ("Winget", "winget"),
]


class UninstallerApp(tk.Tk):
    """Cửa sổ chính của ứng dụng."""

    def __init__(self):
        """Khởi tạo state + build UI, tự động quét registry lần đầu."""
        super().__init__()
        self.title(f"{APP_NAME} {__version__}")
        self.geometry("950x600")
        self.minsize(760, 450)

        # Dữ liệu
        self.apps = []        # toàn bộ app đã quét
        self._displayed = []  # app đang hiển thị (sau khi lọc)
        self._sort_col = None  # cột đang sắp xếp
        self._sort_asc = True  # True tăng dần, False giảm dần

        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------- UI
    def _build_ui(self):
        # Menu bar: Trợ giúp -> Giới thiệu (G2) + Kiểm tra cập nhật.
        menubar = tk.Menu(self)
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Giới thiệu", command=self.show_about)
        help_menu.add_command(label="Kiểm tra cập nhật…", command=self.check_updates)
        menubar.add_cascade(label="Trợ giúp", menu=help_menu)
        self.config(menu=menubar)

        # Toolbar: tìm kiếm + nút chức năng
        toolbar = ttk.Frame(self, padding=(8, 6))
        toolbar.pack(fill=tk.X)

        ttk.Label(toolbar, text="Tìm kiếm:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search)
        ttk.Entry(toolbar, textvariable=self.search_var, width=36).pack(side=tk.LEFT, padx=6)

        ttk.Label(toolbar, text="Nguồn:").pack(side=tk.LEFT)
        self.source_var = tk.StringVar()
        self.source_var.set(_SOURCE_FILTERS[0][0])
        ttk.Combobox(toolbar, textvariable=self.source_var, state="readonly", width=12,
                     values=[label for label, _ in _SOURCE_FILTERS]).pack(side=tk.LEFT, padx=6)
        self.source_var.trace_add("write", self._on_search)

        ttk.Button(toolbar, text="Làm mới", command=self.refresh).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="Gỡ cài đặt", command=self.uninstall_selected).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="Gỡ im lặng", command=self.uninstall_quiet).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="Gỡ batch", command=self.uninstall_batch).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="Quét leftover", command=self.scan_leftovers).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="Mở Backups", command=self.open_backups_folder).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="Khôi phục Backup", command=self.manage_backups).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="Dọn Backups", command=self.clear_backup_history).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="Tạo Restore Point", command=self.create_restore_point).pack(side=tk.LEFT, padx=3)

        # Bảng danh sách ứng dụng
        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 6))

        columns = list(_COLUMNS.keys())
        self.tree = ttk.Treeview(frame, columns=columns, show="headings",
                                 selectmode="extended")
        for col, (text, width, stretch) in _COLUMNS.items():
            self.tree.heading(col, text=text,
                              command=lambda c=col: self._toggle_sort(c))
            self.tree.column(col, width=width, stretch=stretch,
                             anchor=tk.W if col == "name" else tk.CENTER)

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<Double-1>", lambda _e: self.uninstall_selected())
        self.tree.bind("<Button-3>", self._show_context_menu)

        # Status bar
        self.status = ttk.Label(self, text="Sẵn sàng.", anchor=tk.W, padding=(8, 4))
        self.status.pack(fill=tk.X)

    def show_about(self):
        """Hiện hộp thoại Giới thiệu (tên + phiên bản) — G2."""
        messagebox.showinfo("Giới thiệu", about_text())

    # ------------------------------------------------- kiểm tra cập nhật
    def check_updates(self):
        """Kiểm tra bản mới trên GitHub Releases (chạy trên worker thread)."""
        self.status.config(text="Đang kiểm tra cập nhật…")
        threading.Thread(target=self._check_updates_worker, daemon=True).start()

    def _check_updates_worker(self):
        try:
            result = updater.check_for_updates()
        except Exception as exc:  # noqa: BLE001 - không để lỗi chặn UI
            result = {"ok": False, "has_update": False, "latest_version": "",
                      "release_url": "", "download_url": "", "release_notes": "",
                      "error": str(exc)}
        self.after(0, lambda: self._on_updates_checked(result))

    def _on_updates_checked(self, result):
        if not result.get("ok"):
            self.status.config(text="Không kiểm tra được cập nhật.")
            messagebox.showwarning(
                "Kiểm tra cập nhật",
                "Không kiểm tra được cập nhật:\n"
                f"{result.get('error') or 'lỗi không xác định'}")
            return
        if not result.get("has_update"):
            self.status.config(text=f"Bạn đang dùng bản mới nhất ({__version__}).")
            messagebox.showinfo(
                "Kiểm tra cập nhật",
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
        self.status.config(text=f"Có bản mới {latest}.")

        # Có gói lõi app_core.zip -> cập nhật nhẹ + khởi động lại (Tách vỏ).
        if download_url.lower().endswith(".zip"):
            if messagebox.askyesno(
                    "Có bản cập nhật mới",
                    body + "Bạn có muốn tự động tải gói cập nhật nhẹ "
                           "(app_core.zip) và khởi động lại ứng dụng ngay không?"):
                self.status.config(text="Đang tải gói cập nhật nhẹ…")
                threading.Thread(
                    target=self._core_update_worker,
                    args=(download_url,), daemon=True).start()
                return
            self._open_release_page(release_url)
            return

        # Gói .exe đầy đủ: hỏi mở trang tải về, hoặc tải trực tiếp.
        if release_url and messagebox.askyesno(
                "Có bản cập nhật mới",
                body + "Mở trang tải về trên trình duyệt?"):
            self._open_release_page(release_url)
            return
        if not download_url:
            messagebox.showinfo(
                "Cập nhật",
                body + "Bản phát hành không kèm gói tải trực tiếp. "
                       "Hãy mở trang tải về để tải thủ công.")
            return
        if messagebox.askyesno(
                "Tải trực tiếp",
                f"Tải bản mới về máy?\n\n{os.path.basename(download_url)}"):
            self.status.config(text="Đang tải bản cập nhật…")
            threading.Thread(
                target=self._download_update_worker,
                args=(download_url,), daemon=True).start()

    def _open_release_page(self, release_url):
        """Mở trang GitHub Release bằng trình duyệt mặc định (nếu có URL)."""
        if not release_url:
            messagebox.showinfo("Cập nhật", "Không có URL trang phát hành để mở.")
            return
        try:
            os.startfile(release_url)  # noqa: B606 - chỉ chạy trên Windows
        except OSError as exc:
            messagebox.showwarning("Cập nhật", f"Không mở được trang tải về:\n{exc}")

    def _core_update_worker(self, download_url):
        """Tải gói lõi + áp dụng trên worker thread (cập nhật nhẹ, Tách vỏ)."""
        try:
            ok, msg = updater.download_core_update(download_url)
            if ok:
                ok, msg = updater.apply_pending_update()
        except Exception as exc:  # noqa: BLE001 - không để lỗi chặn UI
            ok, msg = False, str(exc)
        self.after(0, lambda: self._on_core_update_done(ok, msg))

    def _on_core_update_done(self, ok, msg):
        if not ok:
            self.status.config(text="Cập nhật lõi thất bại.")
            messagebox.showwarning("Cập nhật", f"Cập nhật lõi thất bại:\n{msg}")
            return
        self.status.config(text="Đã áp dụng gói cập nhật nhẹ.")
        messagebox.showinfo(
            "Cập nhật",
            "Đã tải và áp dụng gói cập nhật nhẹ.\n"
            "Ứng dụng sẽ khởi động lại ngay bây giờ.")
        updater.restart_application()

    def _download_update_worker(self, download_url):
        try:
            ok, msg = updater.download_update(download_url)
        except Exception as exc:  # noqa: BLE001
            ok, msg = False, str(exc)
        self.after(0, lambda: self._on_update_downloaded(ok, msg))

    def _on_update_downloaded(self, ok, msg):
        if ok:
            self.status.config(text=f"Đã tải bản mới: {msg}")
            messagebox.showinfo(
                "Cập nhật",
                f"Đã tải bản mới về:\n{msg}\n\n"
                "Hãy đóng ứng dụng và chạy file này để cập nhật.")
        else:
            self.status.config(text="Tải bản cập nhật thất bại.")
            messagebox.showwarning("Cập nhật", f"Tải thất bại:\n{msg}")

    # ---------------------------------------------------------- dữ liệu
    def refresh(self):
        """Xoá bảng, quét lại registry trên worker thread."""
        self.status.config(text="Đang quét registry…")
        self.apps = []
        self._displayed = []
        self._clear_tree()
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        try:
            apps = enumerate_apps()
        except Exception as exc:  # noqa: BLE001 - hiển thị lỗi cho người dùng
            self.after(0, lambda: self.status.config(text="Lỗi khi quét registry."))
            self.after(0, lambda: messagebox.showerror(
                "Lỗi", f"Không thể liệt kê ứng dụng:\n{exc}"))
            return
        self.after(0, lambda: self._set_apps(apps))

    def _set_apps(self, apps):
        self.apps = apps
        self._refresh_tree()
        admin_hint = "" if is_admin() else " (chạy với quyền Administrator nếu gỡ không được)"
        self.status.config(text=f"Tìm thấy {len(apps)} ứng dụng.{admin_hint}")

    # -------------------------------------------------------- hiển thị
    def _clear_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

    def _selected_source(self):
        """Giá trị nguồn thô tương ứng với nhãn đang chọn ('', 'registry'...)."""
        label = self.source_var.get()
        for text, value in _SOURCE_FILTERS:
            if text == label:
                return value
        return ""

    def _refresh_tree(self):
        self._clear_tree()
        self._displayed = []
        query = self.search_var.get().strip().lower()
        src = self._selected_source()
        items = []
        for app in self.apps:
            if query and (query not in app.name.lower()
                          and query not in app.publisher.lower()):
                continue
            if src and (app.source or "").lower() != src:
                continue
            items.append(app)
        self._displayed = self._sort_apps(items)
        for app in self._displayed:
            self.tree.insert("", "end", values=(
                app.name, app.version, app.publisher, app.size_text, app.date_text,
            ))

    def _sort_apps(self, apps):
        """Sắp xếp theo cột đang chọn. Cột 'size' dùng giá trị số (KB)."""
        if not self._sort_col:
            return apps
        col = self._sort_col
        if col == "size":
            key = lambda a: a.estimate_size_kb
        elif col == "version":
            key = lambda a: (a.version or "").lower()
        elif col == "publisher":
            key = lambda a: (a.publisher or "").lower()
        elif col == "date":
            key = lambda a: a.install_date or ""
        else:  # name
            key = lambda a: a.name.lower()
        return sorted(apps, key=key, reverse=not self._sort_asc)

    def _toggle_sort(self, col):
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True
        self._refresh_tree()

    def _show_context_menu(self, event):
        """Menu chuột phải trên một dòng ứng dụng."""
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return
        if row_id not in self.tree.selection():
            self.tree.selection_set(row_id)
        app = self._selected()
        if not app:
            return
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Gỡ cài đặt",
                         command=lambda: self._confirm_and_uninstall(app, quiet=False))
        menu.add_command(label="Gỡ im lặng",
                         command=lambda: self._confirm_and_uninstall(app, quiet=True))
        menu.add_command(label="Quét leftover",
                         command=lambda: self._scan_leftovers_for(app))
        menu.add_command(label="Mở thư mục cài đặt",
                         command=lambda: self._open_install_dir(app))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    @staticmethod
    def _open_install_dir(app):
        """Mở thư mục cài đặt bằng Explorer nếu đường dẫn tồn tại."""
        loc = (app.install_location or "").strip()
        if loc and os.path.isdir(loc):
            os.startfile(loc)  # noqa: B606 - chỉ chạy trên Windows
        else:
            messagebox.showinfo(
                "Thông báo",
                f"Không tìm thấy thư mục cài đặt hợp lệ cho '{app.name}'.")

    # ---------------------------------------------------- quản lý backups
    def open_backups_folder(self):
        """Mở thư mục backups/ và hướng dẫn cách khôi phục file .reg."""
        try:
            os.startfile(str(backup.BACKUP_DIR))  # noqa: B606 - chỉ chạy trên Windows
        except OSError as exc:
            messagebox.showerror("Lỗi", f"Không mở được thư mục backups:\n{exc}")
            return
        messagebox.showinfo(
            "Khôi phục từ backup",
            "Đã mở thư mục backups/.\n\n"
            "• Mỗi lần xoá registry, app xuất 1 file .reg (kèm timestamp).\n"
            "• Để khôi phục: bấm nút 'Khôi phục Backup' (chọn file rồi Khôi phục), "
            "hoặc double-click file .reg.\n"
            "• history.jsonl ghi lại các thao tác đã xoá (registry/file).")

    def clear_backup_history(self):
        """Xoá toàn bộ .reg + làm trống history.jsonl (kèm cảnh báo)."""
        if not messagebox.askyesno(
                "Dọn lịch sử backup",
                "Xoá toàn bộ file .reg và lịch sử history.jsonl trong thư mục "
                "backups/?\n\nSau thao tác này sẽ KHÔNG thể khôi phục các nhánh "
                "registry đã sao lưu. Tiếp tục?"):
            return
        removed = backup.clear_backups()
        messagebox.showinfo(
            "Đã dọn", f"Đã xoá {removed} file .reg và làm trống history.jsonl.")

    def manage_backups(self):
        """Mở hộp thoại liệt kê backup (.reg + thời gian) và khôi phục trực tiếp."""
        win = tk.Toplevel(self)
        win.title("Khôi phục Backup")
        win.geometry("640x420")
        win.minsize(480, 300)
        win.transient(self)

        ttk.Label(win, text="Chọn một file .reg rồi bấm 'Khôi phục' (hoặc double-click):",
                  padding=(8, 6)).pack(anchor=tk.W)

        frame = ttk.Frame(win)
        frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        tree = ttk.Treeview(frame, columns=("file", "time"), show="headings",
                            selectmode="browse")
        tree.heading("file", text="File backup")
        tree.heading("time", text="Thời gian")
        tree.column("file", width=400, anchor=tk.W)
        tree.column("time", width=170, anchor=tk.CENTER)
        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        status_label = ttk.Label(win, text="", anchor=tk.W, padding=(8, 4))
        status_label.pack(fill=tk.X)

        # Đường dẫn file tương ứng từng dòng (song song với thứ tự item).
        entries = []

        def reload():
            tree.delete(*tree.get_children())
            entries.clear()
            infos = backup.list_backup_info()
            for info in infos:
                tree.insert("", "end", values=(info["name"], info["time"]))
                entries.append(info["path"])
            status_label.config(
                text=f"{len(infos)} file backup." if infos
                else "Chưa có file backup nào.")

        def selected_path():
            sel = tree.selection()
            if not sel:
                return None
            index = tree.index(sel[0])
            return entries[index] if 0 <= index < len(entries) else None

        def restore():
            path = selected_path()
            if path is None:
                messagebox.showinfo("Thông báo", "Hãy chọn một file backup để khôi phục.")
                return
            if not messagebox.askyesno(
                    "Xác nhận khôi phục",
                    f"Khôi phục file:\n{path.name}\n\n"
                    "Các giá trị trong file sẽ được ghi/ghi đè vào registry. Tiếp tục?"):
                return
            ok, msg = backup.restore_backup(path)
            status_label.config(text=msg)
            if ok:
                messagebox.showinfo("Đã khôi phục", msg)
                self.refresh()
            else:
                messagebox.showerror("Lỗi khôi phục", msg)

        bar = ttk.Frame(win, padding=8)
        bar.pack(fill=tk.X)
        ttk.Button(bar, text="Làm mới", command=reload).pack(side=tk.LEFT, padx=3)
        ttk.Button(bar, text="Khôi phục", command=restore).pack(side=tk.RIGHT, padx=3)
        ttk.Button(bar, text="Đóng", command=win.destroy).pack(side=tk.RIGHT, padx=3)
        tree.bind("<Double-1>", lambda _e: restore())

        reload()

    def _on_search(self, *_):
        self._refresh_tree()
# --------------------------------------------------------- chọn app
    def _selected(self):
        apps = self._selected_apps()
        return apps[0] if apps else None

    def _selected_apps(self):
        selection = self.tree.selection()
        apps = []
        seen = set()
        for iid in selection:
            index = self.tree.index(iid)
            if 0 <= index < len(self._displayed):
                app = self._displayed[index]
                if id(app) not in seen:
                    seen.add(id(app))
                    apps.append(app)
        return apps

    def _confirm(self, app, quiet):
        """Hiện hộp xác nhận / cảnh báo. Trả về True nếu được phép gỡ."""
        if quiet:
            cmd = build_quiet_command(app)
            if not cmd:
                messagebox.showwarning(
                    "Không hỗ trợ",
                    f"'{app.name}' không suy luận được lệnh gỡ im lặng "
                    "(thiếu QuietUninstallString / bộ cài lạ). Hãy dùng 'Gỡ cài đặt'.")
                return False
            return messagebox.askyesno(
                "Xác nhận",
                f"Gỡ im lặng (ẩn cửa sổ trình gỡ):\n\n{app.name} {app.version}\n"
                f"Lệnh sẽ chạy:\n{cmd}")
        if not app.can_uninstall:
            messagebox.showwarning(
                "Không thể gỡ",
                f"'{app.name}' không có lệnh gỡ chuẩn (có thể là component "
                "hệ thống hoặc app đã gỡ). App sẽ không tự ý gỡ để tránh "
                "phá hỏng hệ thống.")
            return False
        return messagebox.askyesno(
            "Xác nhận gỡ cài đặt",
            f"Bạn có chắc muốn gỡ cài đặt:\n\n{app.name} {app.version}"
            f"{chr(10)}{app.publisher}?")

    def uninstall_selected(self):
        """Gỡ cài đặt chuẩn cho app đang chọn (confirm trước)."""
        self._confirm_and_uninstall(self._selected(), quiet=False)

    def uninstall_quiet(self):
        """Gỡ im lặng cho app đang chọn (confirm trước)."""
        self._confirm_and_uninstall(self._selected(), quiet=True)

    def _confirm_and_uninstall(self, app, quiet):
        """Xác nhận + chạy trình gỡ cho một ứng dụng cụ thể."""
        if not app:
            messagebox.showinfo("Thông báo", "Hãy chọn một ứng dụng trong danh sách.")
            return
        # Nhóm I: kiểm tra trình gỡ trước; nếu mất/hỏng -> đề xuất Force Uninstall.
        ready, reason = check_uninstaller_status(app)
        if not ready:
            self.status.config(
                text=f"Trình gỡ của '{app.name}' không khả dụng: {reason}")
            if self._ask_force_uninstall(app, reason):
                self._scan_leftovers_for(app)
            return
        if not self._confirm(app, quiet=quiet):
            return
        ok, msg, proc = run_uninstall(app, quiet=quiet)
        self.status.config(text=msg)
        messagebox.showinfo("Kết quả", msg)
        if ok:
            self._auto_scan_after_uninstall([(app, proc)])
        elif self._ask_force_uninstall(app, msg):
            self._scan_leftovers_for(app)

    def _ask_force_uninstall(self, app, reason):
        """Hỏi người dùng chuyển sang chế độ Force Uninstall (Nhóm I).

        Trả về True nếu người dùng đồng ý quét & dọn leftover trực tiếp.
        """
        reason = (reason or "không rõ nguyên nhân").strip()
        return messagebox.askyesno(
            "Gỡ cưỡng bức (Force Uninstall)",
            f"Trình gỡ cài đặt gốc không khả dụng ({reason}).\n\n"
            f"Bạn có muốn chuyển sang chế độ Quét & Dọn sạch Leftover "
            f"(Force Uninstall) cho ứng dụng '{app.name}' không?")

    # ------------------------------------------------------ gỡ hàng loạt
    def uninstall_batch(self):
        """Gỡ lần lượt toàn bộ app đang chọn qua worker thread."""
        apps = self._selected_apps()
        if not apps:
            messagebox.showinfo("Thông báo", "Hãy chọn ít nhất một ứng dụng.")
            return
        total = len(apps)
        if not messagebox.askyesno(
                "Gỡ hàng loạt",
                f"Bạn sắp gỡ cài đặt {total} ứng dụng:\n\n"
                + "\n".join(a.name for a in apps)
                + "\n\nTiếp tục?"):
            return
        self.status.config(text=f"Bắt đầu gỡ {total} ứng dụng…")
        threading.Thread(target=self._batch_worker, args=(apps,), daemon=True).start()

    def _batch_worker(self, apps):
        """Chạy gỡ lần lượt trên worker thread;

        Gọi `proc.wait()` để chờ trình gỡ hiện tại kết thúc hoàn toàn trước khi
        khởi chạy trình gỡ kế tiếp (tránh xung đột Windows Installer/msiexec).
        """
        ok = fail = 0
        msgs = []
        launched = []
        total = len(apps)
        for i, a in enumerate(apps, 1):
            if not a.can_uninstall:
                fail += 1
                msg = f"[BỎ QUA] {a.name}: không có lệnh gỡ chuẩn."
                msgs.append(msg)
                self.after(0, lambda m=msg, n=i: self.status.config(
                    text=f"[{n}/{total}] {m}"))
                continue
            _ok, msg, proc = run_uninstall(a)
            msgs.append(f"[{'OK' if _ok else 'LỖI'}] {a.name}: {msg}")
            if _ok:
                ok += 1
                launched.append((a, proc))
                # Đợi trình gỡ hiện tại kết thúc rồi mới chạy app kế tiếp.
                try:
                    proc.wait()
                except Exception:  # noqa: BLE001
                    pass
            else:
                fail += 1
            self.after(0, lambda m=f"[{i}/{total}] {msg}": self.status.config(
                text=m))

        text = f"Đã xử lý {total} ứng dụng:\nThành công: {ok}\nLỗi/Bỏ qua: {fail}\n\n" + \
               "\n".join(msgs)
        self.after(0, lambda: self.status.config(text=f"Xong: {ok} OK, {fail} lỗi."))
        self.after(0, lambda: messagebox.showinfo("Kết quả gỡ batch", text))
        self.after(0, lambda: self.refresh())
        self._auto_scan_after_uninstall(launched)

    # --------------------------------------------------------- quét leftover
    def scan_leftovers(self):
        """Quét leftover cho app đang chọn qua worker thread."""
        self._scan_leftovers_for(self._selected())

    def _scan_leftovers_for(self, app):
        if not app:
            messagebox.showinfo("Thông báo", "Hãy chọn một ứng dụng để quét leftover.")
            return
        self.status.config(text=f"Đang quét leftover cho {app.name}…")
        threading.Thread(target=self._scan_leftovers_worker, args=(app,), daemon=True).start()

    def _scan_leftovers_worker(self, app):
        try:
            items = leftover.scan_leftovers(app)
        except Exception as exc:  # noqa: BLE001
            self.after(0, lambda: self.status.config(text=f"Lỗi khi quét leftover: {exc}"))
            self.after(0, lambda: messagebox.showerror("Lỗi", str(exc)))
            return
        self.after(0, lambda: self._open_leftover_dialog(app, items))

    def _open_leftover_dialog(self, app, items):
        win = tk.Toplevel(self)
        win.title(f"Quét leftover — {app.name}")
        win.geometry("760x460")
        win.minsize(600, 340)
        win.transient(self)

        kind_names = {"registry": "Registry", "files": "File/Thư mục", "entry": "Uninstall entry"}
        conf_names = {"high": "Cao", "medium": "Trung bình"}

        if not items:
            ttk.Label(win, text="Không tìm thấy leftover phù hợp.", padding=12).pack(pady=20)
            ttk.Button(win, text="Đóng", command=win.destroy).pack()
            return

        ttk.Label(win, text=f"Tìm thấy {len(items)} mục. Chọn các mục muốn xoá:",
                  padding=(8, 6)).pack(anchor=tk.W)

        box = ttk.Frame(win)
        box.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        canvas = tk.Canvas(box)
        vsb = ttk.Scrollbar(box, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>",
                   lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        vars = []
        for item in items:
            # Mặc định chỉ tích "uninstall entry" (an toàn); registry/files để
            # người dùng tự duyệt và quyết định trước khi tích xoá.
            v = tk.BooleanVar(value=(item["kind"] == "entry"))
            vars.append(v)
            kind = kind_names.get(item["kind"], item["kind"])
            conf = conf_names.get(item.get("confidence", ""), "?")
            ttk.Checkbutton(inner, text=f"[{kind}] [{conf}] {item['path']}",
                            variable=v, wraplength=610).pack(anchor=tk.W, padx=4, pady=1)

        bar = ttk.Frame(win, padding=8)
        bar.pack(fill=tk.X)
        ttk.Button(bar, text="Chọn tất cả",
                   command=lambda: self._set_all_check(vars, True)).pack(side=tk.LEFT, padx=3)
        ttk.Button(bar, text="Bỏ chọn tất cả",
                   command=lambda: self._set_all_check(vars, False)).pack(side=tk.LEFT, padx=3)
        # Chọn nhanh các mục tin cậy Cao (người dùng vẫn phải bấm xác nhận xoá).
        ttk.Button(bar, text="Chọn mức Cao",
                   command=lambda: self._check_high_confidence(items, vars)
                   ).pack(side=tk.LEFT, padx=3)

        status_label = ttk.Label(bar, text="", anchor=tk.W)
        status_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)

        ttk.Button(bar, text="Xoá các mục đã chọn",
                   command=lambda: self._delete_leftover(app, items, vars, status_label)
                   ).pack(side=tk.RIGHT, padx=3)
        ttk.Button(bar, text="Đóng", command=win.destroy).pack(side=tk.RIGHT, padx=3)

    @staticmethod
    def _set_all_check(vars, value):
        for v in vars:
            v.set(value)

    @staticmethod
    def _check_high_confidence(items, vars):
        """Tích nhanh các mục có độ tin cậy 'high' (người dùng vẫn phải xác nhận)."""
        for item, v in zip(items, vars):
            if item.get("confidence") == "high":
                v.set(True)

    def create_restore_point(self):
        """Tạo System Restore Point trên worker thread (Nhóm II)."""
        if not messagebox.askyesno(
                "Tạo Restore Point",
                "Tạo Điểm Khôi Phục Hệ Thống (System Restore Point) ngay bây giờ?\n\n"
                "Thao tác này cần quyền Administrator và có thể mất vài chục giây."):
            return
        self.status.config(text="Đang tạo System Restore Point…")
        threading.Thread(target=self._restore_point_worker, daemon=True).start()

    def _restore_point_worker(self):
        try:
            ok, msg = backup.create_restore_point()
        except Exception as exc:  # noqa: BLE001 - không để lỗi chặn UI
            ok, msg = False, str(exc)
        self.after(0, lambda: self._on_restore_point_done(ok, msg))

    def _on_restore_point_done(self, ok, msg):
        self.status.config(text=msg)
        if ok:
            messagebox.showinfo("Restore Point", msg)
        else:
            messagebox.showwarning("Restore Point", msg)

    def _delete_leftover(self, app, items, vars, status_label):
        picked = [it for it, v in zip(items, vars) if v.get()]
        if not picked:
            status_label.config(text="Chưa chọn mục nào.")
            return
        if not messagebox.askyesno(
                "Xác nhận xoá leftover",
                f"Xoá {len(picked)} mục leftover của '{app.name}'?\n\n"
                "File/Thư mục sẽ được CHUYỂN VÀO RECYCLE BIN (có thể khôi phục).\n"
                "Registry được sao lưu thành file .reg trước khi xoá.\n"
                "Hãy chắc chắn các mục này thuộc về ứng dụng đã gỡ."):
            return
        ok = fail = 0
        msgs = []
        for it in picked:
            kind = it["kind"]
            if kind == "files":
                success, err = leftover.delete_path(it["path"], app.name)
            else:  # registry / entry
                success, err = leftover.delete_registry_key(it["path"], app.name)
            if success:
                ok += 1
            else:
                fail += 1
            msgs.append(f"[{'OK' if success else 'LỖI'}] {kind}: {it['path']} — {err}")
        text = f"Xoá leftover của {app.name}:\nThành công: {ok} | Lỗi: {fail}\n\n" + "\n".join(msgs)
        status_label.config(text=f"Xong: {ok} OK, {fail} lỗi.")
        messagebox.showinfo("Kết quả", text)

    # ------------------------------------------ tự quét leftover sau khi gỡ
    def _auto_scan_after_uninstall(self, launched):
        """Sau khi gỡ, chờ trình gỡ chạy xong rồi tự quét leftover cho từng app."""
        jobs = [(a, p) for a, p in launched if p is not None]
        if not jobs:
            return
        self.after(0, lambda: self.status.config(
            text="Đang chờ trình gỡ hoàn tất rồi quét leftover…"))
        threading.Thread(target=self._scan_after_uninstall_worker,
                         args=(jobs,), daemon=True).start()

    def _scan_after_uninstall_worker(self, jobs):
        results = []
        for app, proc in jobs:
            try:
                proc.wait()
            except Exception:  # noqa: BLE001 - không chặn được vẫn quét
                pass
            try:
                items = leftover.scan_leftovers(app)
            except Exception:  # noqa: BLE001 - không để lỗi scan làm hỏng luồng
                items = []
            results.append((app, items))
        self.after(0, lambda: self._show_after_uninstall_results(results))

    def _show_after_uninstall_results(self, results):
        # Sau khi gỡ, xả cache `winget list` để refresh phản ánh app đã gỡ (D3).
        clear_winget_cache()
        self.refresh()
        dialogs = [(a, items) for a, items in results if items]
        if not dialogs:
            names = ", ".join(a.name for a, _ in results)
            self.status.config(text=f"Sau khi gỡ: không tìm thấy leftover của {names}.")
            messagebox.showinfo(
                "Quét leftover",
                f"Không tìm thấy file/registry còn sót của:\n{names}")
            return
        self.status.config(
            text=f"Sau khi gỡ: tìm thấy leftover cho {len(dialogs)} ứng dụng.")
        for app, items in dialogs:
            self._open_leftover_dialog(app, items)


def main():
    """Entry point: tạo cửa sổ chính và lặp mainloop."""
    if "--version" in sys.argv or "-V" in sys.argv:
        print_version()
        return
    app = UninstallerApp()
    app.mainloop()


if __name__ == "__main__":
    main()

