"""Test nhanh cho leftover.py: quét app thật + test an toàn hàm xoá."""
import os
import sys
import winreg
import tempfile
import shutil
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from uninstaller_lib import leftover
from uninstaller_lib.enumerator import enumerate_apps


def test_scan_real_app():
    apps = enumerate_apps()
    print("Tổng số app:", len(apps))
    # Tìm một app tiêu biểu (Chrome/Brave/Firefox/Edge...) để thử quét leftover
    target = None
    for a in apps:
        if any(k in a.name.lower() for k in ("chrome", "brave", "firefox",
                                              "edge", "git", "foxit", "capcut")):
            target = a
            break
    if target is None and apps:
        target = apps[0]

    if target is None:
        print("Không tìm thấy app — bỏ qua test scan.")
        return

    print("Quét leftover cho:", target.name, "| publisher:", target.publisher)
    items = leftover.scan_leftovers(target)
    print("Số leftover tìm được:", len(items))
    for it in items[:25]:
        print(f"  [{it['kind']}] {it['path']}")


def test_delete_functions():
    # 1) Invalid hive -> trả lỗi, không xoá gì
    ok, err = leftover.delete_registry_key("XYZ\\foo\\bar")
    print("delete_registry_key(hive lạ):", ok, "|", err)
    assert not ok

    # 2) Xoá key không tồn tại -> trả lỗi
    ok, err = leftover.delete_registry_key(r"HKCU\Software\AppUninstaller__khong_ton_tai__")
    print("delete_registry_key(không tồn tại):", ok, "|", err)
    assert not ok

    # 3) Tạo key tạm trong HKCU rồi xoá thật (an toàn, tự dọn)
    base = r"Software\AppUninstaller_test_tmp"
    sub = base + r"\child1"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, sub):
        pass
    ok, err = leftover.delete_registry_key(f"HKCU\\{base}")
    print("delete_registry_key(key tạm):", ok, "|", err)
    assert ok, err
    # xác nhận đã xoá hẳn
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, base):
            print("FAIL: key tạm vẫn còn!")
            assert False
    except OSError:
        print("OK: key tạm đã bị xoá sạch.")

    # 4) Xoá file không tồn tại -> trả lỗi
    ok, err = leftover.delete_path(os.path.join(tempfile.gettempdir(),
                                                "__app_uninstaller_khong_ton_tai__"))
    print("delete_path(không tồn tại):", ok, "|", err)
    assert not ok

    # 5) Tạo file tạm + thư mục tạm rồi xoá thật (an toàn)
    dirp = os.path.join(tempfile.gettempdir(), "app_uninstaller_test_dir")
    os.makedirs(dirp, exist_ok=True)
    f = os.path.join(dirp, "a.txt")
    with open(f, "w") as fh:
        fh.write("x")
    ok, err = leftover.delete_path(dirp)
    print("delete_path(thư mục tạm):", ok, "|", err)
    assert ok, err
    assert not os.path.exists(dirp)
    print("OK: thư mục tạm đã bị xoá sạch.")

    print("\nTẤT CẢ TEST AN TOÀN ĐỀU PASS")


def test_is_match():
    """Test luật so khớp tên `_is_match` (case Office / Java / NVIDIA)."""
    from uninstaller_lib.leftover import _is_match

    # (candidate, targets) — targets đã được _tokenize (chữ+số thường, không dấu).
    must_match = [
        ("Office16", ["office16"]),                    # khớp chính xác
        ("microsoftoffice16", ["microsoftoffice"]),    # thư mục có hậu tố
        ("Microsoft Office", ["microsoftoffice"]),     # tên chuẩn có khoảng trắng
        ("Java", ["java"]),
        ("JavaUpdate", ["java"]),
        ("NVIDIA Corporation", ["nvidia"]),
        ("nvidialocal", ["nvidia"]),
    ]
    must_not_match = [
        ("Microsoft", ["microsoftoffice"]),  # tên ngắn KHÔNG khớp tên chuẩn dài
        ("foobar", ["foo"]),                 # target < 4 ký tự -> cấm khớp tiền tố
        ("jav", ["java"]),                   # candidate ngắn hơn target
        ("", ["java"]),                      # candidate rỗng
    ]
    for cand, targets in must_match:
        assert _is_match(cand, targets), f"phải khớp: {cand!r} vs {targets}"
    for cand, targets in must_not_match:
        assert not _is_match(cand, targets), f"KHÔNG được khớp: {cand!r} vs {targets}"
    print(f"test_is_match: PASS ({len(must_match) + len(must_not_match)} case)")


def test_is_safe_to_delete():
    """Test chốt chặn cuối `_is_safe_to_delete` (mock root + thư mục hệ thống)."""
    from uninstaller_lib.leftover import _is_safe_to_delete

    # 1) Rỗng + gốc ổ đĩa -> PHẢI chặn.
    assert not _is_safe_to_delete("")
    drive_root = os.environ.get("SystemDrive", "C:") + "\\"
    assert not _is_safe_to_delete(drive_root), f"KHÔNG được xoá gốc ổ đĩa: {drive_root}"

    # 2) Thư mục hệ thống thật -> PHẢI chặn.
    windir = os.environ.get("WINDIR", r"C:\Windows")
    for bad in (windir,
                os.path.join(windir, "System32"),
                os.path.join(windir, "SysWOW64"),
                os.path.join(windir, "System", "drivers")):
        assert not _is_safe_to_delete(bad), f"KHÔNG được xoá: {bad}"

    # 3) Mock một "root quét": root -> chặn; thư mục con hợp lệ -> cho phép.
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "FakeRoot")
        app = os.path.join(root, "SomeApp")
        os.makedirs(app)
        old = os.environ.get("PROGRAMFILES")
        os.environ["PROGRAMFILES"] = root  # _file_roots() đọc env lúc gọi
        try:
            assert not _is_safe_to_delete(root), "root quét phải bị chặn"
            assert _is_safe_to_delete(app), "thư mục con hợp lệ phải được phép xoá"
        finally:
            if old is None:
                os.environ.pop("PROGRAMFILES", None)
            else:
                os.environ["PROGRAMFILES"] = old

    # 4) Root mới (Nhóm II): %LOCALAPPDATA%\Programs và %PROGRAMDATA% -> PHẢI chặn.
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if local:
        la_prog = os.path.join(local, "Programs")
        assert not _is_safe_to_delete(la_prog), \
            f"KHÔNG được xoá root mới: {la_prog}"
    progdata = os.environ.get("PROGRAMDATA", "").strip()
    if progdata:
        assert not _is_safe_to_delete(progdata), \
            f"KHÔNG được xoá root mới: {progdata}"

    # 5) <root>\<publisher> cấp 1 -> PHẢI chặn (khi biết publisher); con vẫn cho phép.
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "FakeData")
        pubdir = os.path.join(root, "Contoso")
        child = os.path.join(pubdir, "MyApp")
        os.makedirs(child)
        old = os.environ.get("PROGRAMDATA")
        os.environ["PROGRAMDATA"] = root
        try:
            assert not _is_safe_to_delete(root), "root mới phải bị chặn"
            assert not _is_safe_to_delete(pubdir, publisher="Contoso"), \
                "<root>\\<publisher> cấp 1 phải bị chặn"
            assert _is_safe_to_delete(child, publisher="Contoso"), \
                "thư mục con của publisher vẫn được phép xoá"
        finally:
            if old is None:
                os.environ.pop("PROGRAMDATA", None)
            else:
                os.environ["PROGRAMDATA"] = old

    print("test_is_safe_to_delete: PASS")


def test_msi_api():
    """Test Windows Installer API (chỉ ĐỌC — KHÔNG gỡ cài đặt gì)."""
    from uninstaller_lib import uninstall

    # 1) Liệt kê sản phẩm MSI đã cài (có thể rỗng trên máy sạch).
    products = uninstall.list_msi_products()
    print(f"test_msi_api: tìm thấy {len(products)} gói MSI.")
    for pc in products[:3]:
        assert uninstall.msi_product_installed(pc), f"phải đang cài: {pc}"

    # 2) GUID không tồn tại -> không cài.
    bogus = "{00000000-0000-0000-0000-000000000000}"
    assert not uninstall.msi_product_installed(bogus)

    # 3) Chuẩn hoá product code: thêm ngoặc, chặn chuỗi rác.
    assert uninstall._normalize_product_code(
        "00000000-0000-0000-0000-000000000000") == bogus
    assert uninstall._normalize_product_code("khong-phai-guid") == ""

    # 4) uninstall_msi với GUID không tồn tại -> báo lỗi, KHÔNG tạo job.
    ok, _msg, proc = uninstall.uninstall_msi(bogus)
    assert not ok and proc is None

    print("test_msi_api: PASS")


def test_build_quiet_command():
    """Test suy luận lệnh gỡ im lặng (MSI, Inno, NSIS, Squirrel, InstallShield,
    WiX Burn, chuỗi có ngoặc kép, chuỗi không nhận diện được)."""
    from uninstaller_lib.models import AppInfo
    from uninstaller_lib import uninstall

    tmp = tempfile.mkdtemp(prefix="au_quiet_")
    try:
        def write_exe(name, blob=b""):
            path = os.path.join(tmp, name)
            with open(path, "wb") as fh:
                fh.write(blob)
            return path

        # 1) MSI theo product_code -> MsiExec /X + /qn /norestart
        msi = AppInfo(name="MSI App",
                      product_code="{12345678-1234-1234-1234-1234567890AB}")
        cmd = uninstall.build_quiet_command(msi)
        assert "MsiExec.exe /X" in cmd and "/qn" in cmd and "/norestart" in cmd, cmd

        # 2) QuietUninstallString có sẵn -> trả nguyên văn
        q = AppInfo(name="Q", quiet_uninstall_string="myquiet.exe /silent")
        assert uninstall.build_quiet_command(q) == "myquiet.exe /silent"

        # 3) Inno Setup (chữ ký trong file) -> /VERYSILENT ...
        inno = write_exe("inno.exe", b"\x00\x00 Inno Setup Setup Data \x00")
        a = AppInfo(name="Inno App", uninstall_string=f'"{inno}"')
        cmd = uninstall.build_quiet_command(a)
        assert cmd.endswith("/VERYSILENT /SUPPRESSMSGBOXES /NORESTART"), cmd

        # 4) NSIS (chữ ký Nullsoft) -> /S
        nsis = write_exe("nsis.exe", b"blah Nullsoft Install System blah")
        a = AppInfo(name="NSIS App", uninstall_string=f'"{nsis}"')
        cmd = uninstall.build_quiet_command(a)
        assert cmd.endswith("/S"), cmd

        # 5) Squirrel / Electron (Update.exe + --uninstall) -> thêm -s (không nhân đôi)
        update = write_exe("Update.exe", b"squirrel")
        a = AppInfo(name="Squirrel App", uninstall_string=f'"{update}" --uninstall')
        cmd = uninstall.build_quiet_command(a)
        assert "--uninstall" in cmd and cmd.endswith("-s"), cmd
        a2 = AppInfo(name="Squirrel App",
                     uninstall_string=f'"{update}" --uninstall -s')
        assert uninstall.build_quiet_command(a2).count("-s") == 1

        # 6) WiX Burn Bootstrapper (.exe + /uninstall) -> /quiet /norestart
        burn = write_exe("setup_burn.exe", b"wix burn")
        a = AppInfo(name="Burn App", uninstall_string=f'"{burn}" /uninstall')
        cmd = uninstall.build_quiet_command(a)
        assert "/quiet" in cmd and "/norestart" in cmd, cmd

        # 7) InstallShield (đường dẫn chứa InstallShield) -> /S
        isdir = os.path.join(tmp, "InstallShield Installation Information")
        os.makedirs(isdir, exist_ok=True)
        isur = os.path.join(isdir, "setup.exe")
        with open(isur, "wb") as fh:
            fh.write(b"is")
        a = AppInfo(name="IS App", uninstall_string=f'"{isur}"')
        cmd = uninstall.build_quiet_command(a)
        assert cmd.endswith("/S"), cmd

        # 8) Chuỗi có ngoặc kép + msiexec /I -> đổi /X + /qn /norestart
        a = AppInfo(
            name="MSI quoted",
            uninstall_string='"C:\\Windows\\System32\\msiexec.exe" '
                             '/I{11111111-2222-3333-4444-555555555555}')
        cmd = uninstall.build_quiet_command(a)
        assert "/X{11111111-2222-3333-4444-555555555555}" in cmd, cmd
        assert cmd.endswith("/qn /norestart"), cmd

        # 9) Không nhận diện được -> rỗng (KHÔNG chèn cờ mù quáng)
        unknown = write_exe("unknown.exe", b"nothing here")
        a = AppInfo(name="Unknown", uninstall_string=f'"{unknown}"')
        assert uninstall.build_quiet_command(a) == ""

        # 10) Trỏ tới file .exe không tồn tại -> rỗng
        a = AppInfo(name="Missing", uninstall_string=r'"C:\nope\nope.exe" /S')
        assert uninstall.build_quiet_command(a) == ""
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("test_build_quiet_command: PASS")


def test_check_uninstaller_status():
    """Test phát hiện app mồ côi / hỏng trình gỡ (Force Uninstall)."""
    from uninstaller_lib.models import AppInfo
    from uninstaller_lib import uninstall

    tmp = tempfile.mkdtemp(prefix="au_status_")
    try:
        exe = os.path.join(tmp, "uninstall.exe")
        with open(exe, "wb") as fh:
            fh.write(b"x")

        # winget -> sẵn sàng
        ok, msg = uninstall.check_uninstaller_status(AppInfo(name="W", source="winget"))
        assert ok and msg == "OK", (ok, msg)

        # MSI GUID hợp lệ -> sẵn sàng
        ok, msg = uninstall.check_uninstaller_status(
            AppInfo(name="M", product_code="{12345678-1234-1234-1234-1234567890AB}"))
        assert ok, msg

        # file .exe trích từ UninstallString tồn tại -> sẵn sàng
        ok, msg = uninstall.check_uninstaller_status(
            AppInfo(name="R", uninstall_string=f'"{exe}" /S'))
        assert ok, msg

        # thiếu UninstallString -> KHÔNG sẵn sàng, nêu rõ lý do
        ok, msg = uninstall.check_uninstaller_status(AppInfo(name="No"))
        assert not ok and "UninstallString" in msg, msg

        # file gỡ đã bị xoá -> KHÔNG sẵn sàng, kèm đường dẫn
        missing = os.path.join(tmp, "gone.exe")
        ok, msg = uninstall.check_uninstaller_status(
            AppInfo(name="Gone", uninstall_string=f'"{missing}"'))
        assert not ok and "đã bị xoá" in msg, msg

        # lệnh msiexec (Windows Installer có sẵn) -> sẵn sàng
        ok, msg = uninstall.check_uninstaller_status(
            AppInfo(name="MSIX",
                    uninstall_string='"C:\\Windows\\System32\\msiexec.exe" /X{GUID}'))
        assert ok, msg
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("test_check_uninstaller_status: PASS")


def test_scan_leftovers_confidence():
    """Test phân loại độ tin cậy (confidence) của `scan_leftovers` (Nhóm II)."""
    from uninstaller_lib.models import AppInfo
    from uninstaller_lib.leftover import _match_confidence

    # _match_confidence dùng đúng luật _is_match (không nới lỏng).
    assert _match_confidence("Office16", ["office16"]) == "high"
    assert _match_confidence("microsoftoffice16", ["microsoftoffice"]) == "medium"
    assert _match_confidence("Microsoft", ["microsoftoffice"]) is None
    assert _match_confidence("foobar", ["foo"]) is None
    assert _match_confidence("", ["java"]) is None

    tmp = tempfile.mkdtemp(prefix="au_conf_")
    try:
        app = AppInfo(name="ZZUninstallerConfTest", install_location=tmp,
                      publisher="ZzVendor")
        items = leftover.scan_leftovers(app)
        for it in items:
            assert "kind" in it and "path" in it, it
            assert it["confidence"] in ("high", "medium"), it
        target = [it for it in items
                  if os.path.normcase(os.path.normpath(it["path"]))
                  == os.path.normcase(os.path.normpath(tmp))]
        assert target, "install_location phải xuất hiện trong leftover"
        assert target[0]["confidence"] == "high", target[0]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("test_scan_leftovers_confidence: PASS")


def test_parse_version():
    """Test chuẩn hoá & so sánh phiên bản cho tính năng kiểm tra cập nhật."""
    from uninstaller_lib.updater import parse_version

    assert parse_version("v1.2.3") == (1, 2, 3)
    assert parse_version("1.2.3") == (1, 2, 3)
    assert parse_version("V2.0") == (2, 0)
    assert parse_version("1.2.3-beta.4") == (1, 2, 3, 4)
    assert parse_version("") == ()
    assert parse_version("không-phải-số") == ()
    # So sánh đúng thứ tự số (không so chuỗi: "1.10" > "1.9").
    assert parse_version("v1.10.0") > parse_version("1.9.9")
    assert parse_version("1.0.0") > parse_version("v0.9.9")
    assert parse_version("1.0.0") == parse_version("v1.0.0")
    print("test_parse_version: PASS")


def test_core_update_zip():
    """Test gói lõi: validate_core_zip + apply_pending_update + rollback_core_update."""
    from uninstaller_lib import updater

    def write_zip(path, members):
        with zipfile.ZipFile(path, "w") as zf:
            for name, content in members.items():
                zf.writestr(name, content)
        return path

    with tempfile.TemporaryDirectory() as tmp:
        # 1) validate: file không phải ZIP -> thất bại
        not_zip = os.path.join(tmp, "not.zip")
        with open(not_zip, "wb") as fh:
            fh.write(b"khong phai zip")
        ok, reason = updater.validate_core_zip(not_zip)
        assert not ok and reason, (ok, reason)

        # 2) validate: thiếu điểm khởi chạy -> thất bại
        incomplete = write_zip(os.path.join(tmp, "incomplete.zip"),
                               {"uninstaller_lib/__init__.py": "x = 1\n"})
        ok, reason = updater.validate_core_zip(incomplete)
        assert not ok and "main" in reason, (ok, reason)

        # 3) validate: hợp lệ (có lib + main.py)
        good = write_zip(os.path.join(tmp, "good.zip"), {
            "uninstaller_lib/__init__.py": "x = 1\n",
            "main.py": "print('hi')\n",
        })
        ok, reason = updater.validate_core_zip(good)
        assert ok, reason

        # 4) apply khi không có gói chờ -> thất bại
        ok, _msg = updater.apply_pending_update(tmp)
        assert not ok

        # 5) apply: có app_core.zip cũ + app_core.new.zip -> backup cái cũ
        core = os.path.join(tmp, updater.CORE_ZIP_NAME)
        with open(core, "wb") as fh:
            fh.write(b"OLD-CORE")
        write_zip(os.path.join(tmp, updater.CORE_NEW_NAME), {
            "uninstaller_lib/__init__.py": "y = 2\n",
            "main_qt.py": "print('qt')\n",
        })
        ok, msg = updater.apply_pending_update(tmp)
        assert ok, msg
        with open(core, "rb") as fh:
            assert fh.read() != b"OLD-CORE", "app_core.zip phải được thay bằng gói mới"
        bak = os.path.join(tmp, updater.CORE_BAK_NAME)
        with open(bak, "rb") as fh:
            assert fh.read() == b"OLD-CORE", "phải sao lưu bản cũ vào app_core.bak.zip"
        assert not os.path.exists(os.path.join(tmp, updater.CORE_NEW_NAME))

        # 6) rollback: khôi phục bản cũ từ backup
        assert updater.rollback_core_update(tmp) is True
        with open(core, "rb") as fh:
            assert fh.read() == b"OLD-CORE", "rollback phải khôi phục bản cũ"
        assert not os.path.exists(bak)

        # 7) rollback khi không có backup -> False
        assert updater.rollback_core_update(tmp) is False
    print("test_core_update_zip: PASS")


if __name__ == "__main__":
    test_is_match()
    test_is_safe_to_delete()
    test_msi_api()
    test_build_quiet_command()
    test_check_uninstaller_status()
    test_scan_leftovers_confidence()
    test_parse_version()
    test_core_update_zip()
    test_scan_real_app()
    test_delete_functions()
