"""2-D layout and painting of math regions, matching SMath Cloud's look.

Geometry is taken from the SVG SMath Cloud renders (10pt monospace text,
~2.5px padding around operators, a 24px tall single-line region, black
placeholder squares, the L-shaped cursor: an underline below the operand
being edited plus a vertical bar at the insertion point).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen

from ..engine import builtins
from ..engine.display import DComplex, DMatrix, DNum, DQuantity, DString, DUnit
from ..engine.model import (DIGITS, LETTERS, Abs, Box, Frac, Index, Matrix, Paren, Pow,
                            Program, Root, Row, Sqrt)

MONO_FAMILIES = ["Courier New", "Liberation Mono", "Cousine", "DejaVu Sans Mono", "Monospace"]
OP_FAMILIES = ["DejaVu Sans", "Arial", "Liberation Sans", "Sans Serif"]

BLACK = QColor("#000000")
UNIT_BLUE = QColor("#0000ff")
STRING_RED = QColor("#a31515")
ERROR_RED = QColor("#ff0000")
ERROR_FILL = QColor(255, 0, 0, 40)

OP_GLYPH = {"*": "·", "-": "−", "≔": "≔", "=": "=", "≡": "=", "∧": "∧", "∨": "∨",
            "⊕": "⊕", "¬": "¬", "±": "±", "←": "←"}
OP_PAD = 2.5


def _family(candidates):
    from PySide6.QtGui import QFontDatabase

    have = set(QFontDatabase.families())
    for c in candidates:
        if c in have:
            return c
    return candidates[-1]


class Style:
    def __init__(self, size_pt: float = 10.0):
        self.size_pt = size_pt
        self.mono = _family(MONO_FAMILIES)
        self.opfam = _family(OP_FAMILIES)

    def font(self, scale=1.0, italic=False, bold=False, op=False) -> QFont:
        f = QFont(self.opfam if op else self.mono)
        f.setPointSizeF(self.size_pt * scale)
        f.setItalic(italic)
        f.setBold(bold)
        return f


# ---------------------------------------------------------------------------
# Layout boxes
# ---------------------------------------------------------------------------

@dataclass
class LBox:
    w: float = 0.0
    asc: float = 0.0  # above baseline
    desc: float = 0.0  # below baseline
    x: float = 0.0  # position relative to parent baseline origin
    y: float = 0.0
    children: list = field(default_factory=list)

    @property
    def h(self) -> float:
        return self.asc + self.desc

    def paint(self, p: QPainter, ox: float, oy: float) -> None:
        for c in self.children:
            c.paint(p, ox + c.x, oy + c.y)


@dataclass
class LText(LBox):
    text: str = ""
    font: QFont = None
    color: QColor = None
    error: bool = False

    def paint(self, p, ox, oy):
        p.setFont(self.font)
        p.setPen(ERROR_RED if self.error else (self.color or BLACK))
        p.drawText(QPointF(ox, oy), self.text)


@dataclass
class LErrorSpan(LBox):
    """The rounded red outline SMath draws around the part in error."""

    def paint(self, p, ox, oy):
        p.save()
        p.setPen(QPen(ERROR_RED, 1))
        p.setBrush(ERROR_FILL)
        p.drawRoundedRect(QRectF(ox - 1.5, oy - self.asc - 1, self.w + 3, self.h + 2), 4, 4)
        p.restore()


@dataclass
class LRect(LBox):
    """Placeholder square (■) or a filled bar."""

    color: QColor = None
    error: bool = False

    def paint(self, p, ox, oy):
        r = QRectF(ox + 1, oy - self.asc + 1, self.w - 2, self.h - 1)
        if self.error:
            p.save()
            p.setPen(QPen(ERROR_RED, 1))
            p.setBrush(ERROR_FILL)
            p.drawRoundedRect(QRectF(ox - 1, oy - self.asc - 2, self.w + 2, self.h + 4), 3, 3)
            p.restore()
        p.fillRect(r, ERROR_RED if self.error else (self.color or BLACK))


@dataclass
class LPath(LBox):
    path: QPainterPath = None
    width: float = 1.0
    color: QColor = None

    def paint(self, p, ox, oy):
        p.save()
        p.translate(ox, oy)
        p.setPen(QPen(self.color or BLACK, self.width))
        p.setBrush(Qt.NoBrush)
        p.drawPath(self.path)
        p.restore()
        super().paint(p, ox, oy)


@dataclass
class RowInfo:
    """Where a model row was placed, for cursor drawing and hit testing."""

    row: Row
    x: float
    base: float  # baseline y
    asc: float
    desc: float
    slots: list  # x of each cursor position 0..len(row)


class Layouter:
    """Lays out a region (math rows + result) into LBoxes."""

    def __init__(self, style: Style, var_kind=None, error_node=None, user_funcs=frozenset()):
        self.style = style
        self.var_kind = var_kind or (lambda name: "user")
        self.error_src = getattr(error_node, "src", None) if error_node is not None else None
        self.user_funcs = user_funcs
        self.rows: list[tuple[Row, LBox, list]] = []  # (row, box, slot offsets)

    # -- fonts / metrics ------------------------------------------------------
    def metrics(self, f: QFont) -> QFontMetricsF:
        return QFontMetricsF(f)

    def text(self, s: str, font: QFont, color=BLACK, error=False) -> LText:
        m = self.metrics(font)
        w = m.horizontalAdvance(s)
        return LText(w=w, asc=m.ascent() * 0.82, desc=m.descent() * 0.9, text=s, font=font,
                     color=color, error=error)

    def placeholder(self, scale=1.0, error=False) -> LRect:
        m = self.metrics(self.style.font(scale))
        h = m.ascent() * 0.62
        return LRect(w=m.horizontalAdvance("0") * 0.62 + 2, asc=h, desc=1, error=error)

    def hspace(self, w: float) -> LBox:
        return LBox(w=w)

    # -- rows -----------------------------------------------------------------
    def _in_error(self, r: Row, a: int, b: int) -> bool:
        if self.error_src is None:
            return False
        er, ea, eb = self.error_src
        return er is r and a >= ea and b <= max(eb, ea + 1) and eb > ea or (er is r and ea == eb == a and a == b)

    def row(self, r: Row, scale: float = 1.0, stop: Optional[int] = None, start: int = 0,
            register: bool = True) -> LBox:
        """Lay out items[start:stop] of a row; slots are indexed from ``start``."""
        n = len(r.items) if stop is None else stop
        items = r.items
        out = LBox()
        slots = [0.0] * (n - start + 1)
        pieces: list[tuple[int, int, LBox]] = []  # (start, end, box) absolute indices
        i = start
        prev_kind = None
        prev_unit = False
        while i < n:
            it = items[i]
            if isinstance(it, Box):
                if (isinstance(it, Frac) and it.rows[0].items[:1] == ["'"]
                        and prev_kind in ("num", "box", "ident")):
                    pieces.append((i, i, self.hspace(self.metrics(self.style.font(scale)).horizontalAdvance(" ") * 0.5)))
                prev = pieces[-1][2] if pieces else None
                special = self._call_display(it, prev, scale, r, i) if isinstance(it, Paren) else None
                pieces.append((i, i + 1, special or self.box(it, scale, pieces, r, i)))
                prev_kind = "box"
                prev_unit = False
                i += 1
                continue
            if it in DIGITS or (it == "." and i + 1 < n and items[i + 1] in DIGITS):
                j = i
                while j < n and isinstance(items[j], str) and (items[j] in DIGITS or items[j] == "."):
                    j += 1
                s = "".join(items[i:j])
                pieces.append((i, j, self.text(s, self.style.font(scale), error=self._in_error(r, i, j))))
                i = j
                prev_kind = "num"
                prev_unit = False
                continue
            if it == "'" or it in LETTERS:
                unit = it == "'"
                j = i + 1
                while j < n and isinstance(items[j], str) and (items[j] in LETTERS or items[j] in DIGITS or items[j] == ".") and items[j] not in "'\"":
                    j += 1
                name = "".join(items[i + 1 if unit else i:j])
                if unit and prev_kind in ("num", "box", "ident"):
                    pieces.append((i, i, self.hspace(self.metrics(self.style.font(scale)).horizontalAdvance(" ") * 0.5)))
                is_call = j < n and isinstance(items[j], Paren)
                ident = self.identifier(name, scale, unit=unit, call=is_call,
                                        error=self._in_error(r, i, j), lead=1 if unit else 0)
                ident.name = name
                pieces.append((i, j, ident))
                i = j
                prev_kind = "ident"
                prev_unit = unit
                continue
            if it == '"':
                j = i + 1
                while j < n and items[j] != '"':
                    j += 1
                s = "".join(x for x in items[i:j + 1] if isinstance(x, str))
                pieces.append((i, min(j + 1, n), self.text(s, self.style.font(scale), STRING_RED)))
                i = min(j + 1, n)
                prev_kind = "str"
                continue
            if it in ",;":
                b = self.text(",", self.style.font(scale))
                b.w += 3
                pieces.append((i, i + 1, b))
                i += 1
                prev_kind = "sep"
                continue
            # a product of two units is written with a space, not a dot (kg m)
            if it == "*" and prev_unit and i + 1 < n and items[i + 1] == "'":
                pieces.append((i, i + 1, self.hspace(self.metrics(self.style.font(scale)).horizontalAdvance(" ") * 0.6)))
                prev_kind = "op"
                i += 1
                continue
            unary = prev_kind in (None, "op", "sep") and it in "-+¬±"
            glyph = OP_GLYPH.get(it, it)
            if it == "≔":
                glyph = ":="
            bold = it == "≡"
            t = self.text(glyph, self.style.font(scale, bold=bold, op=it not in "!"), error=self._in_error(r, i, i + 1))
            pad_l = 0 if unary or it == "!" else OP_PAD
            pad_r = 0 if it == "!" else OP_PAD
            wrap = LBox(w=t.w + pad_l + pad_r, asc=t.asc, desc=t.desc, children=[t])
            t.x = pad_l
            pieces.append((i, i + 1, wrap))
            prev_kind = "op" if it != "!" else "num"
            prev_unit = False
            i += 1
        # assemble
        x = 0.0
        asc = self.metrics(self.style.font(scale)).ascent() * 0.82
        desc = self.metrics(self.style.font(scale)).descent() * 0.9
        written = [False] * len(slots)
        for a, b, box in pieces:
            box.x = x
            slots[a - start] = x
            written[a - start] = True
            if b - a > 1 and isinstance(box, LText):
                m = self.metrics(box.font)
                for k in range(a + 1, b):
                    slots[k - start] = x + m.horizontalAdvance(box.text[: k - a])
                    written[k - start] = True
            elif b - a > 1 and hasattr(box, "slot_map"):
                for k, sx in box.slot_map.items():
                    if a + k < b:
                        slots[a + k - start] = x + sx
                        written[a + k - start] = True
            x += box.w
            if b > a:
                slots[b - start] = x
                written[b - start] = True
            asc = max(asc, box.asc)
            desc = max(desc, box.desc)
            out.children.append(box)
        if n == start:
            ph = self.placeholder(scale, error=self._in_error(r, start, start))
            out.children.append(ph)
            x = ph.w
            asc = max(asc, ph.asc)
        for k in range(1, len(slots)):
            if not written[k]:
                slots[k] = slots[k - 1]
        if self.error_src is not None and self.error_src[0] is r and n > start:
            ea, eb = self.error_src[1], self.error_src[2]
            ea, eb = max(ea, start), min(max(eb, ea + 1), n)
            if ea < eb:
                span = LErrorSpan(w=slots[eb - start] - slots[ea - start], asc=asc, desc=desc)
                span.x = slots[ea - start]
                out.children.insert(0, span)
        out.w, out.asc, out.desc = x, asc, desc
        out.slots = slots
        if register:
            self.rows.append((r, out, slots))
        return out

    def _call_display(self, paren: Paren, prev, scale: float, r: Row, index: int):
        """Calls SMath draws specially: log(x,b) as log_b(x), det(M) as |M|."""
        name = getattr(prev, "name", None)
        inner = paren.rows[0]
        if name == "det":
            prev.children, prev.w = [], 0.0
            return self.bars(self.row(inner, scale), scale)
        if name == "log":
            commas = [k for k, it in enumerate(inner.items) if it in (",", ";")]
            if len(commas) != 1:
                return None
            c = commas[0]
            arg = self.row(inner, scale, stop=c, register=False)
            base = self.row(inner, scale * 0.8, start=c + 1, register=False)
            fence = self.fence(arg, "(", ")", scale)
            base.x = 0
            base.y = self.metrics(self.style.font(scale)).descent() + base.asc * 0.45
            fence.x = base.w + 1
            box = LBox(w=fence.x + fence.w, asc=fence.asc, desc=max(fence.desc, base.y + base.desc),
                       children=[base, fence])
            # one cursor row covering both parts: argument slots then base slots
            slots = [fence.x + arg.x + sx for sx in arg.slots] + [base.x + sx for sx in base.slots]
            self.rows.append((inner, box, slots))
            return box
        return None

    def identifier(self, name: str, scale: float, unit=False, call=False, error=False, lead=0) -> LBox:
        """A name; the part after the first '.' is a literal subscript."""
        base, dot, sub = name.partition(".")
        if unit:
            f = self.style.font(scale)
            color = UNIT_BLUE
        else:
            kind = self.var_kind(base + dot + sub)
            italic = kind == "user" or (call and name in self.user_funcs)
            bold = kind == "builtin_const"
            if call:
                italic = name in self.user_funcs or not builtins.known(name)
                bold = False
            f = self.style.font(scale, italic=italic, bold=bold)
            color = BLACK
        t = self.text(base, f, color, error)
        box = LBox(w=t.w, asc=t.asc, desc=t.desc, children=[t])
        slot_map = {}
        m = self.metrics(f)
        for k in range(1, len(base) + 1):
            slot_map[lead + k] = m.horizontalAdvance(base[:k])
        if dot:
            fs = QFont(f)
            fs.setPointSizeF(f.pointSizeF() * 0.8)
            s = self.text(sub, fs, color, error)
            s.x = t.w
            s.y = t.desc + s.asc * 0.35
            box.children.append(s)
            ms = self.metrics(fs)
            slot_map[lead + len(base) + 1] = t.w
            for k in range(1, len(sub) + 1):
                slot_map[lead + len(base) + 1 + k] = t.w + ms.horizontalAdvance(sub[:k])
            box.w = t.w + s.w
            box.desc = max(box.desc, s.y + s.desc)
        box.slot_map = {k: v for k, v in slot_map.items()}
        if call:
            box.w += 3  # SMath leaves a small gap before the bracket
        return box

    # -- boxes ------------------------------------------------------------------
    def box(self, b: Box, scale: float, pieces, parent_row: Row, index: int) -> LBox:
        if isinstance(b, Frac):
            return self.frac(b, scale)
        if isinstance(b, Pow):
            e = self.row(b.rows[0], scale * 0.9)
            prev = pieces[-1][2] if pieces else None
            lift = (prev.asc if prev is not None else self.metrics(self.style.font(scale)).ascent()) * 0.55
            e.y = -lift - e.desc * 0.3
            out = LBox(w=e.w + 1, asc=lift + e.asc, desc=0, children=[e])
            e.x = 1
            return out
        if isinstance(b, Index):
            e = self.row(b.rows[0], scale * 0.8)
            e.y = self.metrics(self.style.font(scale)).descent() + e.asc * 0.4
            return LBox(w=e.w, asc=0, desc=e.y + e.desc, children=[e])
        if isinstance(b, Paren):
            return self.fence(self.row(b.rows[0], scale), "(", ")", scale)
        if isinstance(b, Abs):
            return self.bars(self.row(b.rows[0], scale), scale)
        if isinstance(b, Sqrt):
            return self.radical(self.row(b.rows[0], scale), None, scale)
        if isinstance(b, Root):
            idx = self.row(b.rows[0], scale * 0.75)
            return self.radical(self.row(b.rows[1], scale), idx, scale)
        if isinstance(b, Matrix):
            return self.matrix([self.row(c, scale) for c in b.rows], b.nrows, b.ncols, scale)
        if isinstance(b, Program):
            return self.program(b, scale)
        return LBox()

    def axis(self, scale: float) -> float:
        return self.metrics(self.style.font(scale)).ascent() * 0.32

    def frac(self, b: Frac, scale: float) -> LBox:
        num = self.row(b.rows[0], scale)
        den = self.row(b.rows[1], scale)
        w = max(num.w, den.w) + 4
        ax = self.axis(scale)
        num.x = (w - num.w) / 2
        num.y = -ax - 2 - num.desc
        den.x = (w - den.w) / 2
        den.y = -ax + 2 + den.asc
        path = QPainterPath()
        path.moveTo(0, -ax)
        path.lineTo(w, -ax)
        out = LPath(w=w + 2, asc=ax + 2 + num.h, desc=-ax + 2 + den.h, path=path, children=[num, den])
        for c in (num, den):
            c.x += 1
        path.translate(1, 0)
        return out

    def fence(self, inner: LBox, left: str, right: str, scale: float) -> LBox:
        h = max(inner.h, self.metrics(self.style.font(scale)).height() * 0.9)
        fs = self.style.font(scale)
        fs.setPointSizeF(fs.pointSizeF() * max(1.0, h / (self.metrics(fs).height() * 0.9)))
        lt = self.text(left, self.style.font(scale) if inner.h <= h * 1.05 and h < 20 else fs)
        rt = self.text(right, lt.font)
        mid = (inner.asc - inner.desc) / 2
        tmid = (lt.asc - lt.desc) / 2
        lt.y = rt.y = mid - tmid
        lt.x = 0
        inner.x = lt.w + 1
        rt.x = inner.x + inner.w + 1
        return LBox(w=rt.x + rt.w, asc=max(inner.asc, lt.asc - lt.y), desc=max(inner.desc, lt.desc + lt.y),
                    children=[lt, inner, rt])

    def bars(self, inner: LBox, scale: float) -> LBox:
        path = QPainterPath()
        top, bot = -inner.asc - 1, inner.desc + 1
        path.moveTo(1.5, top)
        path.lineTo(1.5, bot)
        path.moveTo(inner.w + 5.5, top)
        path.lineTo(inner.w + 5.5, bot)
        inner.x = 3.5
        return LPath(w=inner.w + 7, asc=inner.asc + 1, desc=inner.desc + 1, path=path, children=[inner])

    def radical(self, inner: LBox, index: Optional[LBox], scale: float) -> LBox:
        lead = 8.0
        ix = 0.0
        if index is not None:
            ix = max(0.0, index.w - 4)
        top = -inner.asc - 3
        bot = inner.desc
        path = QPainterPath()
        x0 = ix
        path.moveTo(x0, bot - inner.h * 0.35)
        path.lineTo(x0 + 2.5, bot - inner.h * 0.45)
        path.lineTo(x0 + 5, bot)
        path.lineTo(x0 + lead, top)
        path.lineTo(x0 + lead + inner.w + 3, top)
        inner.x = x0 + lead + 1.5
        children = [inner]
        asc = inner.asc + 4
        if index is not None:
            index.x = 0
            index.y = bot - inner.h * 0.45 - index.desc - 1
            children.append(index)
            asc = max(asc, -(index.y - index.asc))
        return LPath(w=x0 + lead + inner.w + 4, asc=asc, desc=inner.desc + 1, path=path, children=children)

    def matrix(self, cells: list, nrows: int, ncols: int, scale: float) -> LBox:
        colw = [max(cells[i * ncols + j].w for i in range(nrows)) for j in range(ncols)]
        rowa = [max(cells[i * ncols + j].asc for j in range(ncols)) for i in range(nrows)]
        rowd = [max(cells[i * ncols + j].desc for j in range(ncols)) for i in range(nrows)]
        gapx, gapy = 12.0, 4.0
        total_h = sum(a + d for a, d in zip(rowa, rowd)) + gapy * (nrows - 1)
        ax = self.axis(scale)
        top = -total_h / 2 - ax
        y = top
        inner = LBox()
        for i in range(nrows):
            y += rowa[i]
            x = 0.0
            for j in range(ncols):
                c = cells[i * ncols + j]
                c.x = x + (colw[j] - c.w) / 2
                c.y = y
                inner.children.append(c)
                x += colw[j] + gapx
            y += rowd[i] + gapy
        inner.w = sum(colw) + gapx * (ncols - 1)
        inner.asc = -top
        inner.desc = total_h + top
        path = QPainterPath()
        t, b = -inner.asc - 2, inner.desc + 2
        path.moveTo(4, t)
        path.lineTo(1, t)
        path.lineTo(1, b)
        path.lineTo(4, b)
        rx = inner.w + 8
        path.moveTo(rx - 3, t)
        path.lineTo(rx, t)
        path.lineTo(rx, b)
        path.lineTo(rx - 3, b)
        inner.x = 4
        return LPath(w=rx + 2, asc=inner.asc + 2, desc=inner.desc + 2, path=path, children=[inner])

    def program(self, b: Program, scale: float) -> LBox:
        f = self.style.font(scale)
        lines: list[LBox] = []
        indent = self.metrics(f).horizontalAdvance("if") + 2
        if b.name == "if":
            rows = b.rows
            k = 0
            first = True
            while k < len(rows):
                if k == len(rows) - 1:
                    lines.append(self._kw_line("else", None, f))
                    lines.append(self._indented(self.row(rows[k], scale), indent))
                    break
                kw = "if" if first else "else if"
                lines.append(self._kw_line(kw, self.row(rows[k], scale), f))
                lines.append(self._indented(self.row(rows[k + 1], scale), indent))
                first = False
                k += 2
            out = self._stack(lines)
            out.first_line = lines[0]
            return out
        if b.name in ("while", "for"):
            head = self._kw_line(b.name, self.row(b.rows[0], scale), f)
            if b.name == "for" and len(b.rows) >= 3:
                rng = self.row(b.rows[1], scale)
                eq = self.text(" ∈ ", self.style.font(scale, op=True))
                head = self._hcat([head, eq, rng])
            body = self._bracket_block([self.row(r, scale) for r in b.rows[-1:]], scale)
            body.x = indent
            return self._stack([head, body])
        # line: vertical bar with rows stacked
        return self._bracket_block([self.row(r, scale) for r in b.rows], scale)

    def _kw_line(self, kw: str, content: Optional[LBox], f: QFont) -> LBox:
        t = self.text(kw, f)
        if content is None:
            return LBox(w=t.w, asc=t.asc, desc=t.desc, children=[t])
        content.x = t.w + self.metrics(f).horizontalAdvance(" ")
        return LBox(w=content.x + content.w, asc=max(t.asc, content.asc), desc=max(t.desc, content.desc),
                    children=[t, content])

    def _indented(self, b: LBox, indent: float) -> LBox:
        b.x = indent
        return LBox(w=indent + b.w, asc=b.asc, desc=b.desc, children=[b])

    def _hcat(self, boxes: list) -> LBox:
        x = 0.0
        out = LBox()
        for b in boxes:
            b.x = x
            x += b.w
            out.children.append(b)
            out.asc = max(out.asc, b.asc)
            out.desc = max(out.desc, b.desc)
        out.w = x
        return out

    def _stack(self, lines: list, gap: float = 3.0) -> LBox:
        """Lines top to bottom; the first line's baseline is the block's."""
        out = LBox()
        y = 0.0
        for k, ln in enumerate(lines):
            if k:
                y += lines[k - 1].desc + gap + ln.asc
            ln.y = y
            out.children.append(ln)
            out.w = max(out.w, ln.x + ln.w)
        out.asc = lines[0].asc if lines else 0
        out.desc = y + (lines[-1].desc if lines else 0)
        return out

    def _bracket_block(self, rows: list, scale: float) -> LBox:
        inner = self._stack(rows)
        inner.x = 6
        path = QPainterPath()
        path.moveTo(2, -inner.asc)
        path.lineTo(2, inner.desc)
        return LPath(w=inner.w + 8, asc=inner.asc, desc=inner.desc, path=path, width=1.5, children=[inner])

    # -- results -------------------------------------------------------------------
    def result(self, d, scale: float, unit_box: Optional[LBox] = None, show_placeholder=False) -> LBox:
        if isinstance(d, DQuantity):
            parts = [self.number_value(d.value, scale)]
            if unit_box is not None:
                sp = self.hspace(self.metrics(self.style.font(scale)).horizontalAdvance(" ") * 0.5)
                parts += [sp, unit_box]
            elif d.unit is not None:
                sp = self.hspace(self.metrics(self.style.font(scale)).horizontalAdvance(" ") * 0.5)
                parts += [sp, self.unit(d.unit, scale)]
                if show_placeholder:
                    parts.append(self.hspace(2))
            elif show_placeholder:
                parts += [self.hspace(2), self.placeholder(scale)]
            return self._hcat(parts)
        if isinstance(d, DMatrix):
            cells = [self.result(c, scale) for c in d.cells]
            m = self.matrix(cells, d.nrows, d.ncols, scale)
            if show_placeholder and unit_box is None:
                return self._hcat([m, self.hspace(2), self.placeholder(scale)])
            if unit_box is not None:
                return self._hcat([m, self.hspace(3), unit_box])
            return m
        if isinstance(d, DString):
            return self.text(f'"{d.text}"', self.style.font(scale), STRING_RED)
        return self.placeholder(scale)

    def number(self, fn, scale: float, show_sign=True) -> LBox:
        f = self.style.font(scale)
        parts = []
        if fn.negative and show_sign:
            m = self.text("−", self.style.font(scale, op=True))
            parts.append(m)
        parts.append(self.text(fn.mantissa, f))
        if fn.exponent is not None:
            parts.append(LBox(w=OP_PAD - 1))
            parts.append(self.text("·", self.style.font(scale, op=True)))
            parts.append(LBox(w=OP_PAD - 1))
            base = self.text("10", f)
            parts.append(base)
            e = self.text(("−" if fn.exponent < 0 else "") + str(abs(fn.exponent)), self.style.font(scale * 0.9))
            e.y = -base.asc * 0.6
            parts.append(LBox(w=e.w + 1, asc=base.asc * 0.6 + e.asc, children=[e]))
            e.x = 1
        return self._hcat(parts)

    def number_value(self, v, scale: float) -> LBox:
        if isinstance(v, DNum):
            return self.number(v.num, scale)
        if isinstance(v, DComplex):
            parts = []
            if v.re is not None:
                parts.append(self.number(v.re, scale))
                sign = "−" if v.im.negative else "+"
                t = self.text(sign, self.style.font(scale, op=True))
                parts.append(LBox(w=t.w + 2 * OP_PAD, asc=t.asc, desc=t.desc, children=[t]))
                t.x = OP_PAD
                coeff = self.number(v.im, scale, show_sign=False)
            else:
                coeff = self.number(v.im, scale, show_sign=True)
            if not (v.im.mantissa == "1" and v.im.exponent is None):
                parts.append(coeff)
                parts.append(self.text("·", self.style.font(scale, op=True)))
            elif v.re is None and v.im.negative:
                parts.append(self.text("−", self.style.font(scale, op=True)))
            parts.append(self.text("i", self.style.font(scale, bold=True)))
            return self._hcat(parts)
        return self.placeholder(scale)

    def _unit_power(self, p: float, base: LBox, s: float) -> LBox:
        """Exponent of a unit; non-integers are drawn as a small fraction (m^(1/2))."""
        from fractions import Fraction

        fr = Fraction(p).limit_denominator(24)
        f = self.style.font(s * 0.8)
        if fr.denominator == 1:
            e = self.text(str(fr.numerator), f, UNIT_BLUE)
            e.y = -base.asc * 0.6
            e.x = 1
            return LBox(w=e.w + 1, asc=base.asc * 0.6 + e.asc, children=[e])
        num = self.text(str(abs(fr.numerator)) if fr.numerator > 0 else "−" + str(abs(fr.numerator)), f, UNIT_BLUE)
        den = self.text(str(fr.denominator), f, UNIT_BLUE)
        w = max(num.w, den.w) + 2
        mid = -base.asc * 0.95
        num.x, num.y = (w - num.w) / 2 + 1, mid - 1.5 - num.desc
        den.x, den.y = (w - den.w) / 2 + 1, mid + 1.5 + den.asc
        path = QPainterPath()
        path.moveTo(1, mid)
        path.lineTo(w + 1, mid)
        return LPath(w=w + 2, asc=-(num.y - num.asc), desc=0, path=path, color=UNIT_BLUE,
                     children=[num, den])

    def unit(self, u: DUnit, scale: float) -> LBox:
        def product(xs, s):
            parts = []
            for k, (name, p) in enumerate(xs):
                if k:
                    parts.append(self.hspace(self.metrics(self.style.font(s)).horizontalAdvance(" ") * 0.6))
                t = self.text(name, self.style.font(s), UNIT_BLUE)
                parts.append(t)
                if p != 1:
                    parts.append(self._unit_power(p, t, s))
            if not parts:
                parts.append(self.text("1", self.style.font(s), UNIT_BLUE))
            return self._hcat(parts)

        num = product(u.num, scale)
        if not u.den:
            return num
        den = product(u.den, scale)
        w = max(num.w, den.w) + 2
        ax = self.axis(scale)
        num.x = (w - num.w) / 2 + 1
        num.y = -ax - 2 - num.desc
        den.x = (w - den.w) / 2 + 1
        den.y = -ax + 2 + den.asc
        path = QPainterPath()
        path.moveTo(1, -ax)
        path.lineTo(w + 1, -ax)
        return LPath(w=w + 2, asc=ax + 2 + num.h, desc=-ax + 2 + den.h, path=path, children=[num, den])


# ---------------------------------------------------------------------------
# helpers used by the region item
# ---------------------------------------------------------------------------

def absolute_rows(root_box: LBox, rows: list) -> dict:
    """Map id(row) -> RowInfo in region coordinates."""
    pos = {}

    def visit(b: LBox, ox: float, oy: float):
        pos[id(b)] = (ox, oy)
        for c in b.children:
            visit(c, ox + c.x, oy + c.y)

    visit(root_box, root_box.x, root_box.y)
    out = {}
    for r, box, slots in rows:
        if id(box) in pos:
            ox, oy = pos[id(box)]
            out[id(r)] = RowInfo(r, ox, oy, box.asc, box.desc, [ox + s for s in slots])
    return out
