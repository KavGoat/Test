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

PAGE_WIDTH = 760.0  # separators and areas run across the page
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
        if self.focused and (self.region.error is not None or getattr(self, "_plot_error", None)):
            extra = 40.0
        return QRectF(-1, -1, max(w, 1) + 2 + (160 if extra else 0), h + 2 + extra)

    def frame_rect(self) -> QRectF:
        w, h = self._size
        return QRectF(0, 0, w, h)

    def _var_kind(self, name: str) -> str:
        """Built-in constants are bold unless the worksheet redefines them."""
        if name in BUILTIN_CONSTANTS and name not in self.worksheet.index.vars:
            return "builtin_const"
        return "user"

    def relayout(self) -> None:
        self.prepareGeometryChange()
        if self.style.size_pt != self.region.font_size:
            self.style = Style(self.region.font_size)
        if self.region.special:
            h = 9.0 if self.region.special == "separator" or self.region.collapsed else self.region.area_height
            self._size = (PAGE_WIDTH, max(9.0, h))
            self._layout = None
            self.update()
            return
        if self.region.kind == "text":
            self._layout_text()
            return
        if self.region.plot is not None:
            self._layout_plot()
            return
        err = self.region.error
        lay = Layouter(self.style, var_kind=self._var_kind, error_node=getattr(err, "node", None) or _src_node(err),
                       user_funcs=frozenset(n for n, _ in self.worksheet.index.funcs))
        root = lay.row(self.editor.root)
        parts = [root]
        self._result_unit_rect = None
        if self.editor.evaluate:
            # result = number, SMath's automatic unit (it only bridges what the
            # desired unit leaves out; not editable), then the desired-unit box:
            # what was typed there, or while editing an empty black box
            unit_row = self.editor.unit
            if self.region.display is not None:
                res = lay.result(self.region.display, 1.0)
            else:
                res = lay.placeholder()
            res.x = root.w + (1 if self.region.display is not None else 2)
            parts.append(res)
            box = None
            if not unit_row.is_empty() or (self.focused and self.editor.in_unit):
                box = lay.row(unit_row)
            elif self.focused:
                box = lay.placeholder()
            if box is not None:
                gap = 3 if (self.region.display is None or getattr(self.region.display, "unit", None) is None) else 3
                box.x = res.x + res.w + gap
                parts.append(box)
                self._result_unit_rect = QRectF(box.x - 2, -max(box.asc, 12), box.w + 6, max(box.asc, 12) + box.desc + 4)
        if (not self.region.show_input and not self.focused and self.editor.evaluate
                and self.region.display is not None and len(parts) > 1):
            # right-click > Display input data off: only the result is shown
            parts = parts[1:]
            parts[0].x = 0
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

    # -- plots -------------------------------------------------------------------------
    def plot_rect(self) -> QRectF:
        st = self.region.plot
        return QRectF(0, 0, st.width, st.height)

    def _layout_plot(self) -> None:
        st = self.region.plot
        err = self.region.error
        lay = Layouter(self.style, var_kind=self._var_kind, error_node=getattr(err, "node", None) or _src_node(err),
                       user_funcs=frozenset(n for n, _ in self.worksheet.index.funcs))
        root = lay.row(self.editor.root)
        base = st.height + 6 + max(root.asc, 11.4)
        root.x, root.y = PAD_X, base
        self._layout = root
        self._rows = absolute_rows(root, lay.rows)
        self._baseline = base
        self._size = (max(st.width, root.w + 2 * PAD_X), max(base + root.desc + PAD_BOTTOM, st.height + MIN_H))
        self._plot_cache = None
        self.update()

    def _plot_lines(self):
        """Sampled curves, cached until the view or the worksheet changes."""
        from ..plot import sample

        st = self.region.plot
        key = (st.width, st.height, st.ppu_x, st.ppu_y, st.pan_x, st.pan_y,
               id(self.region.plot_ctx), tuple(id(c) for c in self.region.curves))
        cache = getattr(self, "_plot_cache", None)
        if cache is not None and cache[0] == key:
            return cache[1]
        curves = []
        self._plot_error = None
        for node in self.region.curves:
            lines, e = sample(node, self.region.plot_ctx, self.worksheet.evaluator, st)
            curves.append(lines)
            if e is not None and self._plot_error is None:
                self._plot_error = e
        self._plot_cache = (key, curves)
        return curves

    def _paint_plot(self, p: QPainter) -> None:
        from PySide6.QtGui import QPolygonF

        from ..plot import CURVE_COLORS, GRID_COLOR, LABEL_COLOR, axis_layout

        st = self.region.plot
        rect = self.plot_rect()
        p.save()
        p.setRenderHint(QPainter.Antialiasing, False)
        p.fillRect(rect, Qt.white)
        p.setClipRect(rect.adjusted(1, 1, -1, -1))
        ax = axis_layout(st)
        ox, oy = st.origin
        if st.grid:
            p.setPen(QPen(QColor(GRID_COLOR), 1))
            for v in ax["grid_x"]:
                x = round(st.to_px(v, 0)[0]) + 0.5
                p.drawLine(QPointF(x, 0), QPointF(x, st.height))
            for v in ax["grid_y"]:
                y = round(st.to_px(0, v)[1]) + 0.5
                p.drawLine(QPointF(0, y), QPointF(st.width, y))
        f = QFont(self._text_font())
        f.setPointSizeF(8)
        p.setFont(f)
        p.setPen(QColor(LABEL_COLOR))
        for v, label in ax["label_x"]:
            x = round(st.to_px(v, 0)[0])
            p.drawText(QPointF(x + 1, st.height - 2), label)
        for v, label in ax["label_y"]:
            y = round(st.to_px(0, v)[1])
            p.drawText(QPointF(1, y + 10), label)
        if st.axes:
            p.setPen(QPen(Qt.black, 1))
            p.drawLine(QPointF(0, round(oy) + 0.5), QPointF(st.width, round(oy) + 0.5))
            p.drawLine(QPointF(round(ox) + 0.5, 0), QPointF(round(ox) + 0.5, st.height))
            fa = QFont(self._text_font())
            fa.setPointSizeF(10)
            p.setFont(fa)
            p.drawText(QPointF(st.width - 11, oy + 12), "x")
            p.drawText(QPointF(ox + 1, 12), "y")
        p.setRenderHint(QPainter.Antialiasing, True)
        for k, lines in enumerate(self._plot_lines()):
            p.setPen(QPen(QColor(CURVE_COLORS[k % len(CURVE_COLORS)]), 1))
            for line in lines:
                if st.points:
                    for x, y in line[:: max(1, len(line) // 60)]:
                        p.drawEllipse(QPointF(x, y), 1.5, 1.5)
                elif len(line) > 1:
                    p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in line]))
                elif line:
                    p.drawEllipse(QPointF(*line[0]), 1.5, 1.5)
        p.restore()
        p.setPen(QPen(Qt.black, 1))
        p.drawRect(rect.adjusted(0.5, 0.5, -0.5, -0.5))
        if self.focused:
            # resize handle in the corner
            p.fillRect(QRectF(st.width - 5, st.height - 5, 5, 5), Qt.black)

    def _text_font(self) -> QFont:
        from .layout import _family

        reg = self.region
        f = QFont(_family(TEXT_FAMILIES))
        f.setPointSizeF(reg.font_size)
        f.setBold(reg.bold)
        f.setItalic(reg.italic)
        f.setUnderline(reg.underline)
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
        if self.region.special:
            self._paint_special(p)
            return
        if self.region.bg_color.lower() != "#ffffff":
            p.fillRect(r, QColor(self.region.bg_color))
        if self.region.border:
            p.setPen(QPen(Qt.black, 1))
            p.drawRect(r.adjusted(0.5, 0.5, -0.5, -0.5))
        if getattr(self.region, "check_failed", False):
            # the independent double-check disagrees with this result
            p.save()
            p.setPen(QPen(QColor("#ff8c00"), 2, Qt.DashLine))
            p.drawRect(r.adjusted(0, 0, -1, -1))
            p.restore()
        if not self.region.enabled:
            # evaluation disabled: SMath marks the region with a small square
            p.fillRect(QRectF(r.right() - 5, r.top(), 5, 5), QColor("#808080"))
        if self.focused:
            p.fillRect(r.adjusted(1, 1, -1, -1), QColor(self.region.bg_color))
            p.setPen(QPen(FRAME, 1))
            p.drawRect(r.adjusted(0.5, 0.5, -0.5, -0.5))
        if self.selected_region:
            p.fillRect(r, SELECTION)
            p.setPen(QPen(SELECTION_BORDER, 1))
            p.drawRect(r.adjusted(0.5, 0.5, -0.5, -0.5))
        if self.region.kind == "text":
            self._paint_text(p)
            return
        if self.region.plot is not None:
            self._paint_plot(p)
        if self._layout is not None:
            self._layout.paint(p, self._layout.x, self._layout.y)
        if self.focused:
            self._paint_selection(p)
            self._paint_cursor(p)
            if self.region.error is not None or getattr(self, "_plot_error", None) is not None:
                self._paint_error_tip(p)

    def _paint_special(self, p: QPainter) -> None:
        """Separator: one line across the page.  Area: a line at the top with
        a collapse arrow and one at the bottom (one line when collapsed)."""
        w, h = self._size
        p.setPen(QPen(QColor("#808080") if not self.focused else Qt.black, 1))
        p.drawLine(QPointF(0, 4.5), QPointF(w, 4.5))
        if self.region.special == "area":
            path_col = QColor("#404040")
            p.setBrush(path_col)
            from PySide6.QtGui import QPolygonF

            if self.region.collapsed:
                tri = [QPointF(1, 1), QPointF(7, 4.5), QPointF(1, 8)]
            else:
                tri = [QPointF(0, 1), QPointF(8, 1), QPointF(4, 8)]
                p.drawLine(QPointF(0, h - 0.5), QPointF(w, h - 0.5))
            p.drawPolygon(QPolygonF(tri))
            p.setBrush(Qt.NoBrush)

    def toggle_hit(self, pt: QPointF) -> bool:
        return self.region.special == "area" and pt.x() < 10 and pt.y() < 10

    def _paint_text(self, p: QPainter) -> None:
        f = self._text_font()
        m = QFontMetricsF(f)
        p.setFont(f)
        p.setPen(QColor(self.region.color))
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
        """SMath's cursor: a vertical bar at the insertion point and a line
        under the whole name/number (or sub-expression) being edited."""
        ed = self.editor
        info = self._row_info(ed.row)
        if info is None:
            return
        n = len(info.slots) - 1
        x = info.slots[min(ed.pos, n)] if info.slots else info.x
        urow, ua, ub = ed.underline()
        uinfo = self._row_info(urow) or info
        if uinfo.slots:
            x0, x1 = uinfo.slots[min(ua, len(uinfo.slots) - 1)], uinfo.slots[min(ub, len(uinfo.slots) - 1)]
        else:
            x0 = x1 = x
        if not ed.row.items:
            # empty row: the cursor sits after the placeholder square
            x0, x = info.x, info.x + 7
            x1 = x
        underline_y = uinfo.base + uinfo.desc + 0.5
        top = info.base - info.asc
        if ed.in_subscript():
            # in a subscript the bar and underline drop to the subscript's
            # line (SMath Cloud: bar 11-24 instead of 4-19 at 10pt)
            top += info.asc * 0.55
            underline_y += info.asc * 0.4
        p.setPen(QPen(Qt.black, 1))
        if x1 > x0:
            p.drawLine(QPointF(x0, underline_y), QPointF(x1, underline_y))
        p.drawLine(QPointF(x, top), QPointF(x, max(underline_y, info.base + info.desc + 0.5)))

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
        msg = (self.region.error or self._plot_error).message
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
    def slot_at(self, pt: QPointF):
        """(row, index) of the cursor position nearest pt, or None."""
        best = None
        for info in self._rows.values():
            if not info.slots:
                continue
            top, bot = info.base - info.asc, info.base + info.desc
            left, right = info.slots[0], info.slots[-1]
            dy = 0 if top <= pt.y() <= bot else min(abs(pt.y() - top), abs(pt.y() - bot))
            dx = 0 if left - 2 <= pt.x() <= right + 2 else min(abs(pt.x() - left), abs(pt.x() - right))
            key = (dy + dx, (right - left) * (bot - top))
            if best is None or key < best[0]:
                best = (key, info)
        if best is None:
            return None
        info = best[1]
        k = min(range(len(info.slots)), key=lambda i: abs(info.slots[i] - pt.x()))
        return info.row, k

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
        if self.result_unit_hit(pt) and self.editor.unit.is_empty():
            # a click on the black box starts the desired unit
            self.editor.set_cursor(self.editor.unit, 0)
            return
        hit = self.slot_at(pt)
        if hit is not None:
            self.editor.set_cursor(*hit)

    def cursor_scene_pos(self) -> QPointF:
        info = self._row_info(self.editor.row) if self.region.kind == "math" else None
        if info is None:
            return self.mapToScene(QPointF(0, self._size[1]))
        pos = min(self.editor.pos, len(info.slots) - 1)
        return self.mapToScene(QPointF(info.slots[pos] if info.slots else info.x, info.base + info.desc + 2))

    def result_unit_hit(self, pt: QPointF) -> bool:
        """True when a click lands on the desired-unit box (the only part of
        a result that can be edited)."""
        if not self.editor.evaluate or self._layout is None or self._result_unit_rect is None:
            return False
        r = self._result_unit_rect.translated(self._layout.x, self._baseline)
        return r.contains(pt)


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
