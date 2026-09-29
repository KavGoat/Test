"""Read and write SMath Studio worksheets (*.sm).

The format is XML; a math region stores its expression in reverse Polish
notation (``<e type="operand">L</e><e type="operand">3</e>...
<e type="operator" args="2">:</e>``), an evaluation's unit in ``<contract>``
and the last result in ``<result>``.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from ..editor import MathEditor
from ..engine import ast as A
from ..engine.display import display_text
from ..engine.model import Abs, Frac, Index, Matrix, Paren, Pow, Program, Root, Row, Sqrt
from ..engine.parser import parse_row
from ..worksheet import Worksheet

NS = "http://smath.info/schemas/worksheet/1.0"


def _tag(el) -> str:
    return el.tag.split("}")[-1]


# ---------------------------------------------------------------------------
# RPN -> AST
# ---------------------------------------------------------------------------

def rpn_to_ast(elements) -> A.Node:
    stack: list = []
    for e in elements:
        t = e.get("type")
        text = (e.text or "").strip()
        args = int(e.get("args", "0") or 0)
        if t == "operand":
            if e.get("style") == "unit":
                stack.append(A.UnitRef(text))
            elif e.get("style") == "string" or (text.startswith('"') and text.endswith('"')):
                stack.append(A.Str(text.strip('"')))
            elif text and (text[0].isdigit() or text[0] == "."):
                stack.append(A.Num(text))
            else:
                stack.append(A.Var(text))
        elif t == "operator":
            if args == 1:
                a = stack.pop()
                stack.append(A.Unary(text, a))
            else:
                b, a = stack.pop(), stack.pop()
                if text == ":":
                    stack.append(A.Define(a, b))
                elif text == "&":
                    stack.append(A.BinOp("∧", a, b))
                elif text == "|":
                    stack.append(A.BinOp("∨", a, b))
                else:
                    stack.append(A.BinOp(text, a, b))
        elif t == "bracket":
            stack.append(A.Group(stack.pop()))
        elif t == "function":
            items = [stack.pop() for _ in range(args)][::-1] if args else []
            stack.append(A.Call(text, items))
        else:
            raise ValueError(f"unknown element {t}")
    if not stack:
        return A.Placeholder()
    return stack[-1]


# ---------------------------------------------------------------------------
# AST -> editor Row
# ---------------------------------------------------------------------------

PREC = {"≔": 0, "=": 0, "∨": 1, "⊕": 1, "∧": 2, "<": 3, ">": 3, "≤": 3, "≥": 3, "≠": 3, "≡": 3,
        "+": 4, "-": 4, "±": 4, "*": 5, "/": 6, "^": 7}


def _prec(n: A.Node) -> int:
    if isinstance(n, A.BinOp):
        return PREC.get(n.op, 5)
    if isinstance(n, A.Unary):
        return 4 if n.op in "-+" else 8
    if isinstance(n, A.Define):
        return 0
    return 9


def _chars(s: str) -> list:
    return list(s)


def ast_to_items(n: A.Node, parent_prec: int = 0) -> list:
    items = _node_items(n)
    if isinstance(n, (A.BinOp, A.Unary)) and _prec(n) < parent_prec and not (
            isinstance(n, A.BinOp) and n.op == "/"):
        return [Paren(Row(items))]
    return items


def _row(n: A.Node, prec: int = 0) -> Row:
    return Row(ast_to_items(n, prec))


def _node_items(n: A.Node) -> list:
    if isinstance(n, A.Num):
        return _chars(n.text)
    if isinstance(n, A.Var):
        return _chars(n.name)
    if isinstance(n, A.UnitRef):
        return ["'"] + _chars(n.name)
    if isinstance(n, A.Str):
        return ['"'] + _chars(n.text) + ['"']
    if isinstance(n, A.Placeholder):
        return []
    if isinstance(n, A.Group):
        return [Paren(_row(n.inner))]
    if isinstance(n, A.Define):
        return ast_to_items(n.target) + ["≔"] + ast_to_items(n.value)
    if isinstance(n, A.Unary):
        if n.op == "!":
            return ast_to_items(n.arg, 8) + ["!"]
        return [n.op] + ast_to_items(n.arg, 5)
    if isinstance(n, A.BinOp):
        p = _prec(n)
        if n.op == "/":
            return [Frac(_row(n.left), _row(n.right))]
        if n.op == "^":
            return ast_to_items(n.left, 8) + [Pow(_row(n.right))]
        right = ast_to_items(n.right, p + (1 if n.op in "-" else 0))
        # number·unit written without the dot in SMath files
        if n.op == "*" and isinstance(n.right, A.UnitRef) and isinstance(n.left, (A.Num, A.BinOp)):
            return ast_to_items(n.left, p) + right
        return ast_to_items(n.left, p) + [n.op] + right
    if isinstance(n, A.Call):
        return _call_items(n)
    if isinstance(n, A.IndexOp):
        return ast_to_items(n.base, 8) + [Index(Row(_join_args(n.indices)))]
    if isinstance(n, A.MatrixLit):
        return [Matrix(n.nrows, n.ncols, [_row(c) for c in n.cells])]
    return []


def _join_args(args) -> list:
    out = []
    for k, a in enumerate(args):
        if k:
            out.append(",")
        out += ast_to_items(a)
    return out


def _call_items(n: A.Call) -> list:
    name, args = n.name, n.args
    if name == "sqrt" and len(args) == 1:
        return [Sqrt(_row(args[0]))]
    if name == "nthroot" and len(args) == 2:
        return [Root(_row(args[1]), _row(args[0]))]
    if name == "abs" and len(args) == 1:
        return [Abs(_row(args[0]))]
    if name == "el" and len(args) in (2, 3):
        return ast_to_items(args[0], 8) + [Index(Row(_join_args(args[1:])))]
    if name == "mat" and len(args) >= 3:
        try:
            r, c = int(args[-2].text), int(args[-1].text)
            cells = args[:-2]
            if len(cells) == r * c:
                return [Matrix(r, c, [_row(x) for x in cells])]
        except (AttributeError, ValueError):
            pass
    if name in ("if", "line", "while", "for") and args:
        return [Program(name, *[_row(a) for a in args])]
    return _chars(name) + [Paren(Row(_join_args(args)))]


# ---------------------------------------------------------------------------
# AST -> RPN
# ---------------------------------------------------------------------------

def ast_to_rpn(n: A.Node, out: list) -> None:
    def e(t, text, **attrs):
        el = ET.Element(f"{{{NS}}}e", {"type": t, **{k: str(v) for k, v in attrs.items()}})
        el.text = text
        out.append(el)

    if isinstance(n, A.Num):
        e("operand", n.text)
    elif isinstance(n, A.Var):
        e("operand", n.name)
    elif isinstance(n, A.UnitRef):
        e("operand", n.name, style="unit")
    elif isinstance(n, A.Str):
        e("operand", f'"{n.text}"', style="string")
    elif isinstance(n, A.Placeholder):
        e("operand", "#")
    elif isinstance(n, A.Group):
        ast_to_rpn(n.inner, out)
        e("bracket", "(")
    elif isinstance(n, A.Define):
        ast_to_rpn(n.target, out)
        ast_to_rpn(n.value, out)
        e("operator", ":", args=2)
    elif isinstance(n, A.Evaluate):
        ast_to_rpn(n.expr, out)
    elif isinstance(n, A.Unary):
        ast_to_rpn(n.arg, out)
        e("operator", n.op, args=1)
    elif isinstance(n, A.BinOp):
        ast_to_rpn(n.left, out)
        ast_to_rpn(n.right, out)
        op = {"∧": "&", "∨": "|"}.get(n.op, n.op)
        e("operator", op, args=2)
    elif isinstance(n, A.Call):
        for a in n.args:
            ast_to_rpn(a, out)
        e("function", n.name, args=len(n.args))
    elif isinstance(n, A.IndexOp):
        ast_to_rpn(n.base, out)
        for a in n.indices:
            ast_to_rpn(a, out)
        e("function", "el", args=1 + len(n.indices))
    elif isinstance(n, A.MatrixLit):
        for c in n.cells:
            ast_to_rpn(c, out)
        e("operand", str(n.nrows))
        e("operand", str(n.ncols))
        e("function", "mat", args=len(n.cells) + 2)


# ---------------------------------------------------------------------------
# files
# ---------------------------------------------------------------------------

def load_sm(path) -> Worksheet:
    return _from_root(ET.parse(str(path)).getroot())


def loads(text: str) -> Worksheet:
    """Worksheet from .sm XML text (for embedding in other documents)."""
    return _from_root(ET.fromstring(text))


def _from_root(root) -> Worksheet:
    ws = Worksheet()
    meta = root.find(f"{{{NS}}}settings/{{{NS}}}metadata[@lang='eng']")
    if meta is None:
        meta = root.find(f"{{{NS}}}settings/{{{NS}}}metadata")
    if meta is not None:
        for child in meta:
            if child.text:
                ws.metadata[_tag(child)] = child.text
    calc = root.find(f"{{{NS}}}settings/{{{NS}}}calculation")
    if calc is not None:
        p = calc.find(f"{{{NS}}}precision")
        t = calc.find(f"{{{NS}}}exponentialThreshold")
        if p is not None and p.text:
            ws.format.decimals = int(p.text)
        if t is not None and t.text:
            ws.format.threshold = int(t.text)
        tz = calc.find(f"{{{NS}}}trailingZeros")
        if tz is not None and tz.text:
            ws.format.trailing_zeros = tz.text.strip().lower() == "true"
    # area regions nest their contents; evaluation order is by position anyway
    for reg in root.iter(f"{{{NS}}}region"):
        x = float(reg.get("left", "0"))
        y = float(reg.get("top", "0"))
        before = len(ws.regions)
        math = reg.find(f"{{{NS}}}math")
        text = reg.findall(f"{{{NS}}}text")
        plot = reg.find(f"{{{NS}}}plot")
        area = reg.find(f"{{{NS}}}area")
        if area is not None:
            if area.get("single") == "true":
                ws.add_special("separator", y)
            else:
                nested = [float(c.get("top", "0")) + float(c.get("height", "24"))
                          for c in reg.iter(f"{{{NS}}}region") if c is not reg]
                height = float(area.get("height", "0")) or (max(nested) - y + 9 if nested else 90.0)
                a = ws.add_special("area", y, height)
                a.collapsed = area.get("collapsed") == "true"
        elif plot is not None and plot.get("type", "2d") == "2d":
            _load_plot(ws, reg, plot, x, y)
        elif math is not None:
            inp = math.find(f"{{{NS}}}input")
            node = rpn_to_ast(list(inp)) if inp is not None else A.Placeholder()
            ed = MathEditor(Row(ast_to_items(node)))
            if math.find(f"{{{NS}}}result") is not None:
                ed.root.append("=")
                ed.evaluate = True
                contract = math.find(f"{{{NS}}}contract")
                if contract is not None and len(contract):
                    ed.unit = Row(ast_to_items(rpn_to_ast(list(contract))))
            MathEditor._fix_parents(ed.root)
            MathEditor._fix_parents(ed.unit)
            ed.set_cursor(ed.root, len(ed.expression_items()))
            region = ws.add_region(x, y, ed)
            region.enabled = reg.get("enabled", "true") != "false"
        elif text:
            chosen = next((t for t in text if t.get("lang") == "eng"), text[-1])
            paras = ["".join(p.itertext()) for p in chosen.findall(f"{{{NS}}}p")]
            ed = MathEditor()
            ed._to_text("\n".join(paras))
            region = ws.add_region(x, y, ed)
            p0 = chosen.find(f"{{{NS}}}p")
            if p0 is not None:
                region.bold = p0.get("bold") == "true"
                region.italic = p0.get("italic") == "true"
                region.underline = p0.get("underline") == "true"
        if len(ws.regions) > before:
            _load_format(ws.regions[-1], reg)
    ws.calculate()
    return ws


def save_sm(ws: Worksheet, path) -> None:
    with open(path, "wb") as fh:
        fh.write(dumps(ws).encode("utf-8"))


def dumps(ws: Worksheet, calculate: bool = True) -> str:
    """The worksheet as .sm XML text (calculate=False keeps the regions'
    current results, e.g. when copying regions to the clipboard)."""
    ET.register_namespace("", NS)
    root = ET.Element(f"{{{NS}}}regions")
    settings = ET.SubElement(root, f"{{{NS}}}settings")
    calc = ET.SubElement(settings, f"{{{NS}}}calculation")
    ET.SubElement(calc, f"{{{NS}}}precision").text = str(ws.format.decimals)
    ET.SubElement(calc, f"{{{NS}}}exponentialThreshold").text = str(ws.format.threshold)
    ET.SubElement(calc, f"{{{NS}}}trailingZeros").text = "true" if ws.format.trailing_zeros else "false"
    ET.SubElement(calc, f"{{{NS}}}fractions").text = "decimal"
    if ws.metadata:
        meta = ET.SubElement(settings, f"{{{NS}}}metadata", {"lang": "eng"})
        for key in ("title", "author", "description", "company", "keywords"):
            if ws.metadata.get(key):
                ET.SubElement(meta, f"{{{NS}}}{key}").text = ws.metadata[key]
    if calculate:
        ws.calculate()
    for k, r in enumerate(ws.ordered()):
        attrs = {"id": str(k), "left": str(int(r.x)), "top": str(int(r.y)), "color": r.color,
                 "bgColor": r.bg_color, "fontSize": f"{r.font_size:g}"}
        if r.border:
            attrs["border"] = "true"
        if not r.enabled:
            attrs["enabled"] = "false"
        reg = ET.SubElement(root, f"{{{NS}}}region", attrs)
        if r.kind == "plot":
            _save_plot(r, reg)
            continue
        if r.special:
            for k in ("left", "width", "height"):
                reg.attrib.pop(k, None)
            a = {"single": "true"} if r.special == "separator" else {
                "collapsed": "true" if r.collapsed else "false", "height": f"{r.area_height:g}"}
            ET.SubElement(reg, f"{{{NS}}}area", a)
            continue
        if r.kind == "text":
            t = ET.SubElement(reg, f"{{{NS}}}text", {"lang": "eng"})
            for line in r.editor.text.split("\n"):
                pattrs = {k: "true" for k in ("bold", "italic", "underline") if getattr(r, k)}
                ET.SubElement(t, f"{{{NS}}}p", pattrs).text = line
            continue
        math = ET.SubElement(reg, f"{{{NS}}}math")
        inp = ET.SubElement(math, f"{{{NS}}}input")
        try:
            node = parse_row(r.expression_row())
        except Exception:
            node = A.Placeholder()
        els: list = []
        ast_to_rpn(node, els)
        inp.extend(els)
        if r.editor.evaluate:
            if not r.editor.unit.is_empty():
                c = ET.SubElement(math, f"{{{NS}}}contract")
                cels: list = []
                try:
                    ast_to_rpn(parse_row(r.editor.unit), cels)
                except Exception:
                    pass
                c.extend(cels)
            res = ET.SubElement(math, f"{{{NS}}}result", {"action": "numeric"})
            if r.display is not None:
                txt = display_text(r.display).split(" ")[0].replace("·10^", "E")
                ET.SubElement(res, f"{{{NS}}}e", {"type": "operand"}).text = txt
    tree = ET.ElementTree(root)
    ET.indent(tree)
    body = ET.tostring(root, encoding="unicode")
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<?application progid="SMath Studio Desktop" version="1.0"?>\n' + body)


# ---------------------------------------------------------------------------
# plots
# ---------------------------------------------------------------------------

def _load_plot(ws: Worksheet, reg, plot, x: float, y: float) -> None:
    from ..plot import PX_PER_SCALE

    region = ws.add_plot(x, y)
    st = region.plot
    st.width = max(60.0, float(reg.get("width", "309")) - 9)
    st.height = max(40.0, float(reg.get("height", "207")) - 7)
    st.ppu_x = float(plot.get("scale_x", "1.6347")) * PX_PER_SCALE
    st.ppu_y = float(plot.get("scale_y", "1.6347")) * PX_PER_SCALE
    st.pan_x = float(plot.get("transpose_x", "0"))
    st.pan_y = float(plot.get("transpose_y", "0"))
    st.grid = plot.get("grid", "true") != "false"
    st.axes = plot.get("axes", "true") != "false"
    inp = plot.find(f"{{{NS}}}input")
    if inp is None or not len(inp):
        return
    node = rpn_to_ast(list(inp))
    exprs = [node]
    if isinstance(node, A.Call) and node.name == "sys" and len(node.args) >= 3:
        exprs = node.args[:-2]
    box = region.editor.root.items[0]
    box.rows = [Row(ast_to_items(e)) for e in exprs]
    MathEditor._fix_parents(region.editor.root)
    region.editor.set_cursor(box.rows[-1], len(box.rows[-1]))


def _save_plot(r, reg) -> None:
    st = r.plot
    reg.set("width", str(int(st.width + 9)))
    reg.set("height", str(int(st.height + 7)))
    attrs = {"type": "2d", "render": "lines", "scale_x": repr(st.scale_x), "scale_y": repr(st.scale_y),
             "scale_z": repr(st.scale_x), "rotate_x": "0", "rotate_y": "0", "rotate_z": "0",
             "transpose_x": repr(st.pan_x), "transpose_y": repr(st.pan_y), "transpose_z": "0"}
    if not st.grid:
        attrs["grid"] = "false"
    if not st.axes:
        attrs["axes"] = "false"
    plot = ET.SubElement(reg, f"{{{NS}}}plot", attrs)
    inp = ET.SubElement(plot, f"{{{NS}}}input")
    nodes = []
    for row in r.plot_rows():
        try:
            nodes.append(parse_row(row))
        except Exception:
            nodes.append(A.Placeholder())
    els: list = []
    if len(nodes) == 1:
        ast_to_rpn(nodes[0], els)
    else:
        for n in nodes:
            ast_to_rpn(n, els)
        for v in (str(len(nodes)), "1"):
            e = ET.Element(f"{{{NS}}}e", {"type": "operand"})
            e.text = v
            els.append(e)
        e = ET.Element(f"{{{NS}}}e", {"type": "function", "preserve": "true", "args": str(len(nodes) + 2)})
        e.text = "sys"
        els.append(e)
    inp.extend(els)


def _load_format(region, reg) -> None:
    region.color = reg.get("color", "#000000")
    region.bg_color = reg.get("bgColor", "#ffffff")
    region.border = reg.get("border", "false") == "true"
    try:
        region.font_size = float(reg.get("fontSize", "10"))
    except ValueError:
        pass
