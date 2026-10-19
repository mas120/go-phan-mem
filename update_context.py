"""update_context.py — Tự cập nhật Class/API/Type Hints vào AI_CONTEXT.md.

Chỉ dùng thư viện chuẩn `ast` (0 token, không tốn AI, không chạy app).
Chạy: `python update_context.py`

Thay nội dung giữa các cặp marker trong `AI_CONTEXT.md`:
  <!-- AUTO:start:models --> ... <!-- AUTO:end:models -->
  <!-- AUTO:start:api    --> ... <!-- AUTO:end:api    -->
  <!-- AUTO:start:main   --> ... <!-- AUTO:end:main   -->
"""
from __future__ import annotations

import ast
import copy
import sys
from pathlib import Path

if not hasattr(ast, "unparse"):
    sys.exit("Cần Python 3.9+ (ast.unparse).")

ROOT = Path(__file__).resolve().parent
CONTEXT_FILE = ROOT / "AI_CONTEXT.md"

# Hàm private nhưng là QUY TẮC BẢO VỆ an toàn dữ liệu -> vẫn phải liệt kê.
SAFETY_INTERNALS = {"_is_match", "_is_safe_to_delete"}

MARKERS = {
    "models": ("<!-- AUTO:start:models -->", "<!-- AUTO:end:models -->"),
    "api": ("<!-- AUTO:start:api -->", "<!-- AUTO:end:api -->"),
    "main": ("<!-- AUTO:start:main -->", "<!-- AUTO:end:main -->"),
}


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def first_doc_line(node) -> str:
    """Dòng mô tả đầu tiên (không rỗng) trong docstring."""
    doc = ast.get_docstring(node)
    if not doc:
        return ""
    lines = [ln.strip() for ln in doc.splitlines() if ln.strip()]
    return lines[0] if lines else ""


def return_note(node) -> str:
    """Câu 'Trả về ...' trong docstring (ưu tiên dòng bắt đầu bằng 'Trả về')."""
    doc = ast.get_docstring(node) or ""
    for line in doc.splitlines():
        s = line.strip()
        low = s.lower()
        if low.startswith("trả về"):
            return s[len("Trả về"):].lstrip(": ").strip() or s
        if low.startswith(("return", "returns")):
            return s
    return ""


def _arg_str(arg: ast.arg, default: ast.AST | None = None) -> str:
    s = arg.arg
    if arg.annotation is not None:
        s += f": {ast.unparse(arg.annotation)}"
    if default is not None:
        s += f" = {ast.unparse(default)}"
    return s


def build_params(fn: ast.FunctionDef, drop_self: bool = False) -> str:
    a = fn.args
    if drop_self and a.args and a.args[0].arg in ("self", "cls"):
        a = copy.copy(a)
        a.args = a.args[1:]
    pos = list(a.posonlyargs) + list(a.args)
    defs = [None] * (len(pos) - len(a.defaults)) + list(a.defaults or [])
    parts = [_arg_str(arg, d) for arg, d in zip(pos, defs)]

    if a.vararg is not None:
        head = f"*{a.vararg.arg}"
        if a.vararg.annotation is not None:
            head += f": {ast.unparse(a.vararg.annotation)}"
        parts.append(head)
    elif a.kwonlyargs:
        parts.append("*")
    for arg, d in zip(a.kwonlyargs, a.kw_defaults or []):
        parts.append(_arg_str(arg, d))
    if a.kwarg is not None:
        head = f"**{a.kwarg.arg}"
        if a.kwarg.annotation is not None:
            head += f": {ast.unparse(a.kwarg.annotation)}"
        parts.append(head)
    return ", ".join(parts)

def is_property(fn: ast.FunctionDef) -> bool:
    for d in fn.decorator_list:
        if isinstance(d, ast.Name) and d.id == "property":
            return True
        if isinstance(d, ast.Attribute) and d.attr == "property":
            return True
    return False


def func_bullet(fn: ast.FunctionDef, drop_self: bool = False, indent: str = "") -> list[str]:
    """Bullet `name(params) -> ret` + dòng mô tả + (tuỳ chọn) dòng Trả về."""
    core = f"`{fn.name}({build_params(fn, drop_self=drop_self)})`"
    if fn.returns is not None:
        core += f" -> `{ast.unparse(fn.returns)}`"
    desc = first_doc_line(fn)
    line = f"{indent}- {core}"
    if desc:
        line += f" — {desc}"
    out = [line]
    note = return_note(fn)
    if note and fn.returns is None and note.lower() not in desc.lower():
        out.append(f"{indent}    - Trả về: {note}")
    return out


def render_models() -> str:
    tree = parse(ROOT / "uninstaller_lib" / "models.py")
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "AppInfo")
    is_dc = any(isinstance(d, ast.Name) and d.id == "dataclass" for d in cls.decorator_list)
    fields = [n for n in cls.body if isinstance(n, ast.AnnAssign)]
    props = [m for m in cls.body if isinstance(m, ast.FunctionDef) and is_property(m)]

    head = f"- `class {cls.name}`"
    if is_dc:
        head += " (@dataclass)"
    doc = first_doc_line(cls)
    if doc:
        head += f" — {doc}"
    lines = [head]

    if fields:
        flds = []
        for f in fields:
            t = ast.unparse(f.target)
            if f.annotation is not None:
                t += f": {ast.unparse(f.annotation)}"
            if f.value is not None:
                t += f" = {ast.unparse(f.value)}"
            flds.append(t)
        lines.append(f"  - Fields: `{', '.join(flds)}`")

    for p in props:
        core = f"`@property {p.name}({build_params(p, drop_self=True)})`"
        if p.returns is not None:
            core += f" -> `{ast.unparse(p.returns)}`"
        pd = first_doc_line(p)
        lines.append(f"  - {core}" + (f" — {pd}" if pd else ""))
    return "\n".join(lines)


def render_api() -> str:
    blocks = []
    for rel in ("uninstaller_lib/enumerator.py",
                "uninstaller_lib/uninstall.py",
                "uninstaller_lib/leftover.py",
                "uninstaller_lib/backup.py",
                "uninstaller_lib/updater.py"):
        tree = parse(ROOT / rel)
        funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
        public = [f for f in funcs if not f.name.startswith("_")]
        safety = [f for f in funcs if f.name in SAFETY_INTERNALS]
        lines = [f"- `{rel}`"]
        for f in public:
            lines += func_bullet(f, indent="  ")
        if safety:
            lines.append("  - Safety (private nhưng QUAN TRỌNG):")
            for f in safety:
                lines += func_bullet(f, indent="    ")
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


def render_main() -> str:
    tree = parse(ROOT / "main.py")
    lines: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            bases = ", ".join(ast.unparse(b) for b in node.bases)
            head = f"- `class {node.name}` ({bases})"
            doc = first_doc_line(node)
            if doc:
                head += f" — {doc}"
            lines.append(head)
            methods = [m for m in node.body
                       if isinstance(m, ast.FunctionDef)
                       and (m.name == "__init__" or not m.name.startswith("_"))]
            for m in methods:
                lines += func_bullet(m, drop_self=True, indent="  ")
        elif isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            lines += func_bullet(node)
    return "\n".join(lines)

def replace_block(text: str, start: str, end: str, block: str) -> str:
    i = text.find(start)
    j = text.find(end)
    if i < 0 or j < 0 or j < i:
        sys.exit(f"Lỗi: thiếu marker '{start.strip()}' / '{end.strip()}' trong {CONTEXT_FILE.name}.")
    i += len(start)
    return text[:i] + "\n" + block + "\n" + text[j:]


def main() -> None:
    if not CONTEXT_FILE.exists():
        sys.exit(f"Không tìm thấy {CONTEXT_FILE}.")
    text = CONTEXT_FILE.read_text(encoding="utf-8")
    renderers = {"models": render_models, "api": render_api, "main": render_main}
    for key, (start, end) in MARKERS.items():
        text = replace_block(text, start, end, renderers[key]())
    CONTEXT_FILE.write_text(text, encoding="utf-8")
    print(f"Đã tái tạo 3 khối (models/api/main) trong {CONTEXT_FILE.name}.")


if __name__ == "__main__":
    main()

