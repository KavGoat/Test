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
from ..page import is_field
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
    if name == "line" and len(args) >= 3:
        # SMath stores a line block as line(s1, ..., sn, n, 1): the last two
        # operands are its size, not statements (shown or evaluated they
        # made the block's value 1 and drew "1 1" under the statements)
        try:
            if int(args[-2].text) == len(args) - 2 and int(args[-1].text) == 1:
                args = args[:-2]
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
    elif isinstance(n, A.Call) and n.name == "line":
        # SMath's form: the statements, then the block's size (n rows, 1 column)
        for a in n.args:
            ast_to_rpn(a, out)
        e("operand", str(len(n.args)))
        e("operand", "1")
        e("function", "line", args=len(n.args) + 2)
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
    ident = root.find(f"{{{NS}}}settings/{{{NS}}}identity")
    if ident is not None:
        for key in ("id", "revision"):
            el = ident.find(f"{{{NS}}}{key}")
            if el is not None and el.text:
                ws.metadata["_" + key] = el.text.strip()
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
    _load_page_model(ws, root)
    layers = root.findall(f"{{{NS}}}regions")
    content = [g for g in layers if g.get("type", "content") == "content"] or [root]
    for group in content:
        _load_regions(ws, group)
    for kind in ("header", "footer"):
        for group in (g for g in layers if g.get("type") == kind):
            layer = Worksheet()
            layer.metadata = ws.metadata
            _load_regions(layer, group)
            getattr(ws.page, kind).extend(layer.regions)
    ws.calculate()
    return ws


def _load_regions(ws, group) -> None:
    # area regions nest their contents; evaluation order is by position anyway
    for reg in group.iter(f"{{{NS}}}region"):
        x = float(reg.get("left", "0"))
        y = float(reg.get("top", "0"))
        before = len(ws.regions)
        math = reg.find(f"{{{NS}}}math")
        text = reg.findall(f"{{{NS}}}text")
        plot = reg.find(f"{{{NS}}}plot")
        area = reg.find(f"{{{NS}}}area")
        picture = reg.find(f"{{{NS}}}picture")
        if picture is not None:
            raw = picture.find(f"{{{NS}}}raw")
            if raw is not None and raw.text:
                import base64

                r = ws.add_region(x, y)
                r.special = "picture"
                r.image = base64.b64decode(raw.text)
                r.image_format = raw.get("format", "png")
                r.pic_w = float(reg.get("width", "0") or 0)
                r.pic_h = float(reg.get("height", "0") or 0)
        elif area is not None:
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
            ops = list(inp) if inp is not None else []
            if len(ops) == 1 and is_field(ops[0].text or ""):
                # a header/footer field such as \[TITLE]\ or \[PAGENUM[0]]\
                region = ws.add_region(x, y)
                region.field_code = ops[0].text
                _load_format(region, reg)
                continue
            node = rpn_to_ast(list(inp)) if inp is not None else A.Placeholder()
            ed = MathEditor(Row(ast_to_items(node)))
            res = math.find(f"{{{NS}}}result")
            # SMath's → (symbolic evaluation) is not replicated: such a region
            # opens as its expression alone (symbolic(...) does the work here)
            if res is not None and res.get("action") != "symbolic":
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
            _load_math_options(region, math, ws)
        elif text:
            chosen = next((t for t in text if t.get("lang") == "eng"), text[-1])
            lines = _rich_lines(chosen)
            ed = MathEditor()
            ed._to_text("\n".join("".join(t for t, _ in runs) for runs in lines))
            region = ws.add_region(x, y, ed)
            styles = [st for runs in lines for _, st in runs]
            if styles and all(st == styles[0] for st in styles):
                # one style for the whole region
                region.bold = styles[0].get("bold", False)
                region.italic = styles[0].get("italic", False)
                region.underline = styles[0].get("underline", False)
            else:
                region.line_runs = lines
            region.text_width = float(chosen.get("width", "0") or 0)
            _load_format(region, reg)
            if chosen.get("fontFamily"):
                region.font_family = chosen.get("fontFamily")
            if chosen.get("fontSize"):
                region.font_size = float(chosen.get("fontSize"))
            continue
        if len(ws.regions) > before:
            _load_format(ws.regions[-1], reg)


_STYLE_KEYS = {"font-weight": ("bold", "bold"), "font-style": ("italic", "italic"),
               "text-decoration": ("underline", "underline")}


def _css(style: str, base: dict) -> dict:
    out = dict(base)
    for part in (style or "").split(";"):
        if ":" not in part:
            continue
        k, v = (t.strip().lower() for t in part.split(":", 1))
        if k in _STYLE_KEYS:
            name, on = _STYLE_KEYS[k]
            out[name] = on in v
    return out


def _rich_lines(text_el) -> list:
    """SMath text as lines of styled runs: <content><p style><span style>..<br/>
    (0.99+) or the older <p bold="true">..</p>.  Whitespace from the XML's
    indentation collapses as in HTML."""
    import re as _re

    paras = text_el.findall(f"{{{NS}}}content/{{{NS}}}p") or text_el.findall(f"{{{NS}}}p")
    lines: list = []
    for p in paras:
        base = {"bold": p.get("bold") == "true", "italic": p.get("italic") == "true",
                "underline": p.get("underline") == "true"}
        base = _css(p.get("style", ""), base)
        cur: list = []

        def add(t, st):
            t = _re.sub(r"\s+", " ", t or "")
            if t:
                cur.append([t, st])

        def walk(el, st):
            nonlocal cur
            add(el.text, st)
            for c in el:
                tag = _tag(c)
                if tag == "br":
                    lines.append(cur)
                    cur = []
                else:
                    walk(c, _css(c.get("style", ""), st))
                add(c.tail, st)

        walk(p, base)
        lines.append(cur)
    # trim the spaces the indentation left at line ends, drop empty runs
    out = []
    for runs in lines:
        while runs and not runs[0][0].lstrip():
            runs.pop(0)
        while runs and not runs[-1][0].rstrip():
            runs.pop()
        if runs:
            runs[0][0] = runs[0][0].lstrip()
            runs[-1][0] = runs[-1][0].rstrip()
        out.append([(t, st) for t, st in runs if t])
    return out or [[]]


def _load_page_model(ws, root) -> None:
    from ..page import from_hundredths

    pm = root.find(f"{{{NS}}}settings/{{{NS}}}pageModel")
    if pm is None:
        return
    page = ws.page
    page.page_model_attrs = dict(pm.attrib)
    page.print_grid = pm.get("printGrid") == "true"
    page.print_background = pm.get("printBackgroundImages", "true") != "false"
    paper = pm.find(f"{{{NS}}}paper")
    if paper is not None:
        page.paper_id = paper.get("id", page.paper_id)
        page.orientation = paper.get("orientation", page.orientation)
        w, h = from_hundredths(paper.get("width", "827")), from_hundredths(paper.get("height", "1169"))
        if page.orientation.lower() == "landscape" and w < h:
            w, h = h, w
        page.paper_w, page.paper_h = w, h
    m = pm.find(f"{{{NS}}}margins")
    if m is not None:
        page.margin_l = from_hundredths(m.get("left", "39"))
        page.margin_r = from_hundredths(m.get("right", "39"))
        page.margin_t = from_hundredths(m.get("top", "39"))
        page.margin_b = from_hundredths(m.get("bottom", "39"))
    for kind in ("header", "footer"):
        el = pm.find(f"{{{NS}}}{kind}")
        if el is not None:
            setattr(page, f"{kind}_text", el.text or "")
            setattr(page, f"{kind}_attrs", dict(el.attrib))
    img = pm.find(f"{{{NS}}}backgrounds/{{{NS}}}image")
    if img is not None and img.text:
        import base64

        page.background = base64.b64decode(img.text)
        page.background_full_page = img.get("fullPage") == "true"
        page.background_size = img.get("size", "stretch")


def save_sm(ws: Worksheet, path) -> None:
    import uuid

    # as SMath Studio: a worksheet gets an id once, and each save is a new revision
    ws.metadata.setdefault("_id", str(uuid.uuid4()))
    try:
        ws.metadata["_revision"] = str(int(ws.metadata.get("_revision", "0")) + 1)
    except ValueError:
        ws.metadata["_revision"] = "1"
    with open(path, "wb") as fh:
        fh.write(dumps(ws).encode("utf-8"))


def dumps(ws: Worksheet, calculate: bool = True) -> str:
    """The worksheet as .sm XML text (calculate=False keeps the regions'
    current results, e.g. when copying regions to the clipboard).  The layout
    is SMath Studio's: <worksheet> with <settings> (calculation, metadata,
    page model) and <regions type="content">, plus the header/footer layers."""
    ET.register_namespace("", NS)
    root = ET.Element(f"{{{NS}}}worksheet")
    settings = ET.SubElement(root, f"{{{NS}}}settings", {"ppi": "96"})
    if ws.metadata.get("_id"):
        ident = ET.SubElement(settings, f"{{{NS}}}identity")
        ET.SubElement(ident, f"{{{NS}}}id").text = ws.metadata["_id"]
        ET.SubElement(ident, f"{{{NS}}}revision").text = ws.metadata.get("_revision", "1")
    if any(v for k, v in ws.metadata.items() if not k.startswith("_")):
        meta = ET.SubElement(settings, f"{{{NS}}}metadata", {"lang": "eng"})
        for key in ("title", "author", "description", "company", "keywords"):
            if ws.metadata.get(key):
                ET.SubElement(meta, f"{{{NS}}}{key}").text = ws.metadata[key]
    calc = ET.SubElement(settings, f"{{{NS}}}calculation")
    ET.SubElement(calc, f"{{{NS}}}precision").text = str(ws.format.decimals)
    ET.SubElement(calc, f"{{{NS}}}exponentialThreshold").text = str(ws.format.threshold)
    ET.SubElement(calc, f"{{{NS}}}trailingZeros").text = "true" if ws.format.trailing_zeros else "false"
    ET.SubElement(calc, f"{{{NS}}}fractions").text = "decimal"
    _save_page_model(ws, settings)
    if calculate:
        ws.calculate()
    content = ET.SubElement(root, f"{{{NS}}}regions", {"type": "content"})
    for k, r in enumerate(ws.ordered()):
        _save_region(ws, content, r, k)
    for kind in ("header", "footer"):
        layer = getattr(ws.page, kind)
        if layer:
            group = ET.SubElement(root, f"{{{NS}}}regions", {"type": kind})
            for k, r in enumerate(layer):
                _save_region(ws, group, r, k)
    tree = ET.ElementTree(root)
    ET.indent(tree)
    body = ET.tostring(root, encoding="unicode")
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<?application progid="SMath Studio Desktop" version="0.99.7822.147"?>\n' + body)


def _save_page_model(ws, settings) -> None:
    import base64

    from ..page import to_hundredths

    page = ws.page
    attrs = dict(page.page_model_attrs) or {"active": "false", "viewMode": "2", "printGrid": "false",
                                            "printAreas": "true", "simpleEqualsOnly": "false",
                                            "printBackgroundImages": "true"}
    attrs["printGrid"] = "true" if page.print_grid else "false"
    attrs["printBackgroundImages"] = "true" if page.print_background else "false"
    pm = ET.SubElement(settings, f"{{{NS}}}pageModel", attrs)
    w, h = page.paper_w, page.paper_h
    if page.orientation.lower() == "landscape":
        w, h = h, w
    ET.SubElement(pm, f"{{{NS}}}paper", {"id": page.paper_id, "orientation": page.orientation,
                                         "width": str(to_hundredths(w)), "height": str(to_hundredths(h))})
    ET.SubElement(pm, f"{{{NS}}}margins", {"left": str(to_hundredths(page.margin_l)),
                                           "right": str(to_hundredths(page.margin_r)),
                                           "top": str(to_hundredths(page.margin_t)),
                                           "bottom": str(to_hundredths(page.margin_b))})
    for kind in ("header", "footer"):
        el = ET.SubElement(pm, f"{{{NS}}}{kind}", getattr(page, f"{kind}_attrs") or
                           {"alignment": "Center", "color": "#a9a9a9"})
        el.text = getattr(page, f"{kind}_text") or None
    if page.background:
        bg = ET.SubElement(pm, f"{{{NS}}}backgrounds")
        ET.SubElement(bg, f"{{{NS}}}image", {"fullPage": "true" if page.background_full_page else "false",
                                             "size": page.background_size}).text = \
            base64.b64encode(page.background).decode("ascii")


def _css_of(st: dict) -> str:
    parts = []
    if st.get("bold"):
        parts.append("font-weight: bold;")
    if st.get("italic"):
        parts.append("font-style: italic;")
    if st.get("underline"):
        parts.append("text-decoration: underline;")
    return " ".join(parts)


def _save_text(r, reg) -> None:
    attrs = {"lang": "eng"}
    if r.text_width:
        attrs["width"] = f"{r.text_width:g}"
    if r.font_family:
        attrs["fontFamily"] = r.font_family
    attrs["fontSize"] = f"{r.font_size:g}"
    t = ET.SubElement(reg, f"{{{NS}}}text", attrs)
    content = ET.SubElement(t, f"{{{NS}}}content")
    own = {"bold": r.bold, "italic": r.italic, "underline": r.underline}
    p = ET.SubElement(content, f"{{{NS}}}p")
    if _css_of(own):
        p.set("style", _css_of(own))
    last = None  # element whose tail takes the next plain text

    def put(text, style):
        nonlocal last
        if style and _css_of(style) and style != own:
            span = ET.SubElement(p, f"{{{NS}}}span", {"style": _css_of(style)})
            span.text = text
            last = span
        elif last is None:
            p.text = (p.text or "") + text
        else:
            last.tail = (last.tail or "") + text

    lines = r.editor.text.split("\n")
    for i, line in enumerate(lines):
        if i:
            last = ET.SubElement(p, f"{{{NS}}}br")
        runs = r.line_runs[i] if i < len(r.line_runs) else None
        if runs is None or "".join(t for t, _ in runs) != line:
            runs = [(line, None)]
        for text, style in runs:
            put(text, style)


def _save_region(ws, parent, r, k) -> None:
    attrs = {"id": str(k), "left": str(int(r.x)), "top": str(int(r.y)), "color": r.color}
    if r.special == "picture":
        import base64

        attrs.update(width=str(int(r.pic_w)), height=str(int(r.pic_h)))
        reg = ET.SubElement(parent, f"{{{NS}}}region", attrs)
        pic = ET.SubElement(reg, f"{{{NS}}}picture")
        ET.SubElement(pic, f"{{{NS}}}raw", {"format": r.image_format, "encoding": "base64"}).text = \
            base64.b64encode(r.image).decode("ascii")
        return
    attrs.update(bgColor=r.bg_color, fontSize=f"{r.font_size:g}")
    if r.font_family and r.kind != "text":
        attrs["fontFamily"] = r.font_family
    if r.border:
        attrs["border"] = "true"
    if not r.enabled:
        attrs["enabled"] = "false"
    reg = ET.SubElement(parent, f"{{{NS}}}region", attrs)
    if r.field_code:
        math = ET.SubElement(reg, f"{{{NS}}}math")
        inp = ET.SubElement(math, f"{{{NS}}}input")
        ET.SubElement(inp, f"{{{NS}}}e", {"type": "operand"}).text = r.field_code
        return
    if r.kind == "plot":
        _save_plot(r, reg)
        return
    if r.special:
        for key in ("left", "width", "height"):
            reg.attrib.pop(key, None)
        a = {"single": "true"} if r.special == "separator" else {
            "collapsed": "true" if r.collapsed else "false", "height": f"{r.area_height:g}"}
        ET.SubElement(reg, f"{{{NS}}}area", a)
        return
    if r.kind == "text":
        _save_text(r, reg)
        return
    math = ET.SubElement(reg, f"{{{NS}}}math", _math_options(r, ws))
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
    st.points = plot.get("render", "lines") == "points"
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
    attrs = {"type": "2d", "render": "points" if st.points else "lines",
             "scale_x": repr(st.scale_x), "scale_y": repr(st.scale_y),
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


_OPTIMIZE = {"none": "0", "symbolic": "1", "numeric": "2"}


def _math_options(r, ws) -> dict:
    """Right-click menu settings of a math region, as SMath writes them on
    <math> (decimalPlaces="5" significantDigitsMode="true" trailingZeros="true"
    optimize="2" were read from SMath's own files; the rest follow suit)."""
    out = {}
    if r.optimization:
        out["optimize"] = _OPTIMIZE[r.optimization]
    f, base = r.fmt, ws.format
    if f is not None:
        if f.decimals != base.decimals:
            out["decimalPlaces"] = str(f.decimals)
        if f.significant != base.significant:
            out["significantDigitsMode"] = "true" if f.significant else "false"
        if f.trailing_zeros != base.trailing_zeros:
            out["trailingZeros"] = "true" if f.trailing_zeros else "false"
        if f.threshold != base.threshold:
            out["exponentialThreshold"] = str(f.threshold)
        if f.fractions != base.fractions:
            out["fractions"] = f.fractions
        if f.mixed:
            out["mixedNumbers"] = "true"
        if f.half_even != base.half_even:
            out["roundingMode"] = "halfToEven" if f.half_even else "awayFromZero"
    if not r.show_input:
        out["displayInput"] = "false"
    if r.ignore_units:
        out["ignoreUnits"] = "true"
    return out


def _load_math_options(region, math, ws) -> None:
    import dataclasses

    g = math.get
    opt = {v: k for k, v in _OPTIMIZE.items()}.get(g("optimize", ""))
    if opt:
        region.optimization = opt
    kw = {}
    if g("decimalPlaces"):
        kw["decimals"] = int(g("decimalPlaces"))
    if g("significantDigitsMode"):
        kw["significant"] = g("significantDigitsMode") == "true"
    if g("trailingZeros"):
        kw["trailing_zeros"] = g("trailingZeros") == "true"
    if g("exponentialThreshold"):
        kw["threshold"] = int(g("exponentialThreshold"))
    if g("fractions"):
        kw["fractions"] = g("fractions")
    if g("mixedNumbers"):
        kw["mixed"] = g("mixedNumbers") == "true"
    if g("roundingMode"):
        kw["half_even"] = g("roundingMode") == "halfToEven"
    if kw:
        region.fmt = dataclasses.replace(ws.format, **kw)
    region.show_input = g("displayInput", "true") != "false"
    region.ignore_units = g("ignoreUnits") == "true"


def _load_format(region, reg) -> None:
    region.color = reg.get("color", "#000000")
    region.bg_color = reg.get("bgColor", "#ffffff")
    region.border = reg.get("border", "false") == "true"
    try:
        region.font_size = float(reg.get("fontSize", "10"))
        region.font_family = reg.get("fontFamily", "")
    except ValueError:
        pass
