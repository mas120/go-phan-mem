"""make_icon.py — Sinh `assets/app.ico` chỉ bằng thư viện chuẩn (G1).

Không dùng Pillow. Vẽ icon (thùng rác trắng trên nền xanh gradient) ở độ phân
giải cao rồi hạ mẫu để làm mượt cạnh (antialias), sau đó gói nhiều kích thước
vào một file `.ico` dạng BMP/DIB (32-bit RGBA) — tương thích rộng, PyInstaller
đọc được mà không cần thêm dependency.

Chạy: `python make_icon.py`  ->  tạo `assets/app.ico`.
"""
from __future__ import annotations

import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ICON_PATH = ROOT / "assets" / "app.ico"

# Kích thước lưu trong file .ico (lớn -> nhỏ).
SIZES = (256, 128, 64, 48, 32, 16)
# Kích thước "siêu mẫu" để render rồi hạ mẫu (bội số chung của mọi SIZES).
SUPER = 1024

# Màu nền gradient (trên -> dưới).
_BG_TOP = (66, 165, 245)      # #42A5F5
_BG_BOTTOM = (21, 101, 192)   # #1565C0


def _inside_round_rect(x, y, x0, y0, x1, y1, r) -> bool:
    """Kiểm tra điểm (x, y) có nằm trong hình chữ nhật bo góc không."""
    if x < x0 or x > x1 or y < y0 or y > y1:
        return False
    cx = min(max(x, x0 + r), x1 - r)
    cy = min(max(y, y0 + r), y1 - r)
    dx, dy = x - cx, y - cy
    return dx * dx + dy * dy <= r * r


def _rect(x, y, x0, y0, x1, y1) -> bool:
    return x0 <= x <= x1 and y0 <= y <= y1


def _glyph(x, y) -> bool:
    """Hình thùng rác trắng (toạ độ đơn vị 0..1). True = thuộc nét trắng."""
    # Quai (vòng) phía trên.
    handle = (_inside_round_rect(x, y, 0.415, 0.145, 0.585, 0.240, 0.035)
              and not _inside_round_rect(x, y, 0.455, 0.185, 0.545, 0.250, 0.02))
    # Nắp (thanh đặc).
    lid = _inside_round_rect(x, y, 0.230, 0.225, 0.770, 0.315, 0.045)
    # Thân (viền rỗng) + 3 khe dọc.
    body = (_inside_round_rect(x, y, 0.300, 0.325, 0.700, 0.830, 0.075)
            and not _inside_round_rect(x, y, 0.350, 0.380, 0.650, 0.785, 0.055))
    slat = any(_rect(x, y, sx, 0.420, sx + 0.040, 0.720)
               for sx in (0.415, 0.480, 0.545))
    return handle or lid or body or slat


def _render(super_size: int) -> bytes:
    """Render ảnh RGBA kích thước `super_size` (bytearray -> bytes)."""
    buf = bytearray(super_size * super_size * 4)
    top_r, top_g, top_b = _BG_TOP
    bot_r, bot_g, bot_b = _BG_BOTTOM
    for py in range(super_size):
        v = (py + 0.5) / super_size
        br = int(top_r + (bot_r - top_r) * v)
        bg = int(top_g + (bot_g - top_g) * v)
        bb = int(top_b + (bot_b - top_b) * v)
        row = py * super_size
        for px in range(super_size):
            u = (px + 0.5) / super_size
            i = (row + px) * 4
            if _inside_round_rect(u, v, 0.02, 0.02, 0.98, 0.98, 0.22):
                if _glyph(u, v):
                    buf[i] = buf[i + 1] = buf[i + 2] = 255
                else:
                    buf[i], buf[i + 1], buf[i + 2] = br, bg, bb
                buf[i + 3] = 255
            # Ngoài nền -> alpha 0 (trong suốt).
    return bytes(buf)


def _downsample(src: bytes, src_size: int, dst_size: int) -> bytes:
    """Hạ mẫu bằng trung bình cộng (giữ đúng màu ở cạnh — dùng alpha nhân trước)."""
    factor = src_size // dst_size
    n = factor * factor
    out = bytearray(dst_size * dst_size * 4)
    for y in range(dst_size):
        for x in range(dst_size):
            ar = ag = ab = aa = 0
            for yy in range(factor):
                rowbase = ((y * factor + yy) * src_size + x * factor) * 4
                for xx in range(factor):
                    i = rowbase + xx * 4
                    a = src[i + 3]
                    ar += src[i] * a
                    ag += src[i + 1] * a
                    ab += src[i + 2] * a
                    aa += a
            o = (y * dst_size + x) * 4
            if aa:
                out[o] = ar // aa
                out[o + 1] = ag // aa
                out[o + 2] = ab // aa
            out[o + 3] = aa // n
    return bytes(out)


def _dib(size: int, rgba: bytes) -> bytes:
    """Gói ảnh RGBA thành DIB 32-bit (BITMAPINFOHEADER + XOR bitmap + AND mask)."""
    header = struct.pack(
        "<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    # XOR bitmap: BGRA, hàng dưới trước (bottom-up).
    xor = bytearray()
    for y in range(size - 1, -1, -1):
        for x in range(size):
            i = (y * size + x) * 4
            xor += bytes((rgba[i + 2], rgba[i + 1], rgba[i], rgba[i + 3]))
    # AND mask (1 bit/pixel, mỗi hàng canh 4 byte): bit 1 = trong suốt.
    row_bytes = ((size + 31) // 32) * 4
    andmask = bytearray(row_bytes * size)
    for y in range(size):
        base = (size - 1 - y) * row_bytes
        for x in range(size):
            if rgba[(y * size + x) * 4 + 3] == 0:
                andmask[base + (x >> 3)] |= 0x80 >> (x & 7)
    return header + bytes(xor) + bytes(andmask)


def _ico(entries) -> bytes:
    """Gói danh sách (size, data) thành file .ico."""
    count = len(entries)
    head = struct.pack("<HHH", 0, 1, count)
    offset = 6 + 16 * count
    dir_entries = bytearray()
    blob = bytearray()
    for size, data in entries:
        w = 0 if size >= 256 else size
        h = 0 if size >= 256 else size
        dir_entries += struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32,
                                   len(data), offset)
        offset += len(data)
        blob += data
    return head + bytes(dir_entries) + bytes(blob)


def build_icon(path: Path = ICON_PATH) -> Path:
    """Render và ghi file .ico; trả về đường dẫn."""
    src = _render(SUPER)
    entries = []
    for size in SIZES:
        rgba = src if size == SUPER else _downsample(src, SUPER, size)
        entries.append((size, _dib(size, rgba)))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_ico(entries))
    return path


if __name__ == "__main__":
    p = build_icon()
    print(f"Đã tạo icon: {p} ({p.stat().st_size} bytes)")
