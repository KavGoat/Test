"""A worksheet region as a QGraphicsObject.

Kept independent of the view so the same item can live on a MarkForge page
later: it only needs a ``Region`` and the ``Worksheet`` it belongs to.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QGraphicsObject

from ..editor import MathEditor
from ..engine.evaluator import BUILTIN_CONSTANTS
from ..engine.model import Row
from ..worksheet import Region, Worksheet
from .layout import LBox, Layouter, RowInfo, Style, absolute_rows

PAD_X = 4.0  # text starts 4px into the region (SMath SVG)
PAD_TOP = 4.0
PAD_BOTTOM = 4.0
MIN_H = 24.0
FRAME = QColor("#808080")
SELECTION = QColor(0, 120, 200, 77)
SELECTION_BORDER = QColor("#3399ff")
TIP_BG = QColor("#ffffe1")
TEXT_FAMILIES = ["Arial", "Liberation Sans", "Arimo", "DejaVu Sans"]


class RegionItem(QGraphicsObject):
    changed = Signal()

    def __init__(self, region: Region, worksheet: Worksheet, style: Style):
        super().__init__()
        self.region = region
        self.worksheet = worksheet
        self.style = style
        self.focused = False
        self.selected_region = False
        self._layout: Optional[LBox] = None
        self._rows: dict = {}
        self._size = (20.0, MIN_H)
        self._baseline = PAD_TOP + 11.4
        self._result_unit_rect: Optional[QRectF] = None
        self.setPos(region.x, region.y)
        self.setFlag(QGraphicsObject.ItemIsSelectable, False)
        self.relayout()

    # -- geometry ------------------------------------------------------------------
    @property
    def editor(self) -> MathEditor:
        return self.region.editor

    def boundingRect(self) -> QRectF:
        w, h = self._size
        extra = 0.0
        if self.focused and self.region.error is not None:
            extra = 40.0
        return QRectF(-1, -1, max(w, 1) + 2 + (160 if extra else 0), h + 2 + extra)

    def frame_rect(self) -> QRectF:
        w, h = self._size
        return QRectF(0, 0, w, h)

    def _var_kind(self, name: str) -> str:
        """Built-in constants are bold unless the worksheet redefines them."""
        if name in BUILTIN_CONSTANTS and not self.worksheet.context.has(name):
            return "builtin_const"
        return "user"

    def relayout(self) -> None:
        self.prepareGeometryChange()
        if self.region.kind == "text":
            self._layout_text()
            return
        err = self.region.error
        lay = Layouter(self.style, var_kind=self._var_kind, error_node=getattr(err, "node", None) or _src_node(err),
                       user_funcs=frozenset(n for n, _ in self.worksheet.context.funcs))
        root = lay.row(self.editor.root)
        parts = [root]
        self._result_unit_rect = None
        if self.editor.evaluate:
            unit_row = self.editor.unit
            unit_box = lay.row(unit_row) if (not unit_row.is_empty() or (self.focused and self.editor.in_unit)) else None
            if self.region.display is not None:
                res = lay.result(self.region.display, 1.0, unit_box=unit_box,
                                 show_placeholder=self.focused and unit_box is None and _no_unit(self.region.display))
                res.x = root.w + 1
                parts.append(res)
            else:
                ph = lay.placeholder()
                ph.x = root.w + 2
                parts.append(ph)
                if unit_box is not None:
                    unit_box.x = ph.x + ph.w + 3
                    parts.append(unit_box)
                elif self.focused:
                    ph2 = lay.placeholder()
                    ph2.x = ph.x + ph.w + 3
                    parts.append(ph2)
        whole = LBox(children=parts)
        whole.w = max(p.x + p.w for p in parts)
        whole.asc = max(p.asc for p in parts)
        whole.desc = max(p.desc for p in parts)
        base = max(PAD_TOP + whole.asc, PAD_TOP + 11.4)
        whole.x, whole.y = PAD_X, base
        self._baseline = base
        self._layout = whole
        self._rows = absolute_rows(whole, lay.rows)
        h = max(MIN_H, base + whole.desc + PAD_BOTTOM)
        self._size = (whole.w + PAD_X * 2, h)
        self.update()

    def _text_font(self) -> QFont:
        from .layout import _family

        f = QFont(_family(TEXT_FAMILIES))
        f.setPointSizeF(10)
        return f

    def _layout_text(self) -> None:
        m = QFontMetricsF(self._text_font())
        lines = (self.editor.text or "").split("\n")
        w = max(m.horizontalAdvance(ln) for ln in lines) if lines else 0
        self._size = (max(w + 2 * PAD_X + 2, 12), max(MIN_H, len(lines) * m.lineSpacing() + 2 * PAD_TOP))
        self._layout = None
        self.update()

    # -- painting ---------------------------------------------------------------------
    def paint(self, p: QPainter, option, widget=None) -> None:
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        r = self.frame_rect()
        if self.focused:
            p.fillRect(r.adjusted(1, 1, -1, -1), Qt.white)
            p.setPen(QPen(FRAME, 1))
            p.drawRect(r.adjusted(0.5, 0.5, -0.5, -0.5))
        if self.selected_region:
            p.fillRect(r, SELECTION)
            p.setPen(QPen(SELECTION_BORDER, 1))
            p.drawRect(r.adjusted(0.5, 0.5, -0.5, -0.5))
        if self.region.kind == "text":
            self._paint_text(p)
            return
        if self._layout is not None:
            self._layout.paint(p, self._layout.x, self._layout.y)
        if self.focused:
            self._paint_selection(p)
            self._paint_cursor(p)
            if self.region.error is not None:
                self._paint_error_tip(p)

    def _paint_text(self, p: QPainter) -> None:
        f = self._text_font()
        m = QFontMetricsF(f)
        p.setFont(f)
        p.setPen(Qt.black)
        y = PAD_TOP + m.ascent()
        lines = (self.editor.text or "").split("\n")
        for ln in lines:
            p.drawText(QPointF(PAD_X + 1, y), ln)
            y += m.lineSpacing()
        if self.focused:
            pos = self.editor.text_pos
            before = self.editor.text[:pos]
            li = before.count("\n")
            col = before.split("\n")[-1]
            x = PAD_X + 1 + m.horizontalAdvance(col)
            top = PAD_TOP + li * m.lineSpacing()
            p.setPen(QPen(Qt.black, 1.5))
            p.drawLine(QPointF(x, top + 1), QPointF(x, top + m.height()))

    def _row_info(self, row: Row) -> Optional[RowInfo]:
        return self._rows.get(id(row))

    def _paint_cursor(self, p: QPainter) -> None:
        ed = self.editor
        info = self._row_info(ed.row)
        if info is None:
            return
        pos = min(ed.pos, len(info.slots) - 1)
        x = info.slots[pos] if info.slots else info.x
        start = ed.operand_start(ed.row, ed.pos) if ed.row.items else ed.pos
        x0 = info.slots[min(start, len(info.slots) - 1)] if info.slots else x
        if not ed.row.items:
            # empty row: the cursor sits on the placeholder square
            x0, x = info.x, info.x + 7
        underline_y = info.base + info.desc + 0.5
        top = info.base - info.asc
        p.setPen(QPen(Qt.black, 1))
        if x0 < x:
            p.drawLine(QPointF(x0, underline_y), QPointF(x, underline_y))
        p.drawLine(QPointF(x, top), QPointF(x, underline_y))

    def _paint_selection(self, p: QPainter) -> None:
        sel = self.editor.selection
        if not sel:
            return
        r, a, b = sel
        info = self._row_info(r)
        if info is None or not info.slots:
            return
        x0 = info.slots[min(a, len(info.slots) - 1)]
        x1 = info.slots[min(b, len(info.slots) - 1)]
        p.fillRect(QRectF(x0, info.base - info.asc, x1 - x0, info.asc + info.desc), SELECTION)

    def _paint_error_tip(self, p: QPainter) -> None:
        msg = self.region.error.message
        f = QFont(self._text_font())
        f.setPixelSize(11)
        m = QFontMetricsF(f)
        w = min(200.0, m.horizontalAdvance(msg) + 4)
        rect = QRectF(0, self._size[1] + 2, w, m.height() + 3)
        p.fillRect(rect, TIP_BG)
        p.setPen(QPen(Qt.black, 1))
        p.drawRect(rect.adjusted(0.5, 0.5, -0.5, -0.5))
        p.setFont(f)
        p.drawText(rect.adjusted(2, 1, -2, -1), Qt.AlignLeft | Qt.AlignVCenter, msg)

    # -- hit testing ----------------------------------------------------------------
    def place_cursor(self, pt: QPointF) -> None:
        """Put the editor cursor at the slot nearest a click (region coords)."""
        if self.region.kind == "text":
            f = QFontMetricsF(self._text_font())
            lines = self.editor.text.split("\n")
            li = max(0, min(len(lines) - 1, int((pt.y() - PAD_TOP) // f.lineSpacing())))
            col = 0
            for k in range(len(lines[li]) + 1):
                if f.horizontalAdvance(lines[li][:k]) + PAD_X + 1 <= pt.x() + 3:
                    col = k
            self.editor.text_pos = sum(len(l) + 1 for l in lines[:li]) + col
            return
        best = None
        for info in self._rows.values():
            top, bot = info.base - info.asc, info.base + info.desc
            if not info.slots:
                continue
            left, right = info.slots[0], info.slots[-1]
            dy = 0 if top <= pt.y() <= bot else min(abs(pt.y() - top), abs(pt.y() - bot))
            dx = 0 if left - 2 <= pt.x() <= right + 2 else min(abs(pt.x() - left), abs(pt.x() - right))
            # prefer the innermost (smallest) row containing the point
            area = (right - left) * (bot - top)
            key = (dy + dx, area)
            if best is None or key < best[0]:
                best = (key, info)
        if best is None:
            return
        info = best[1]
        k = min(range(len(info.slots)), key=lambda i: abs(info.slots[i] - pt.x()))
        self.editor.set_cursor(info.row, k)

    def cursor_scene_pos(self) -> QPointF:
        info = self._row_info(self.editor.row) if self.region.kind == "math" else None
        if info is None:
            return self.mapToScene(QPointF(0, self._size[1]))
        pos = min(self.editor.pos, len(info.slots) - 1)
        return self.mapToScene(QPointF(info.slots[pos] if info.slots else info.x, info.base + info.desc + 2))

    def result_unit_hit(self, pt: QPointF) -> bool:
        """True when a click lands on the result part (after the = sign)."""
        if not self.editor.evaluate or self._layout is None:
            return False
        root_info = self._row_info(self.editor.root)
        if root_info is None or not root_info.slots:
            return False
        return pt.x() > root_info.slots[-1]


def _no_unit(d) -> bool:
    return getattr(d, "unit", None) is None


def _src_node(err):
    if err is None:
        return None
    src = getattr(err, "src", None)
    if src is None:
        return None

    class _N:
        pass

    n = _N()
    n.src = src
    return n
