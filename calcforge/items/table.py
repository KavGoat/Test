"""A table on a page: a little spreadsheet, drawn as page drawing.

Its cells are a sheet of the document's workbook (sheet/docbook.py), so its
formulas read other tables and the document's variables, and the equations
read its values. Like an equation it is part of the page as CalcForge draws
it (the calc layer), editable only in CalcForge, and it always prints.

On screen only, while it is open for its cells, it shows Excel's row and
column headings, the selection and the fill handle; while it is open or
picked up, its name on a tab above it.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem

from ..core.typography import page_font
from ..sheet.numfmt import format_value
from ..sheet.refs import col_letters
from ..sheet.style import Border, Style
from ..sheet.values import BLANK, ErrorValue, Qty
from .base import MarkupItem, register_item

DEFAULT_FONT = "Calibri"
DEFAULT_SIZE = 11.0
PAD = 2.0                       # points between a cell's edge and its text
HEADING_H = 12.0                # the column letters' strip (screen only)
ROWNUM_W = 22.0                 # the row numbers' strip (screen only)
TAB_H = 13.0                    # the name tab above the headings
EXCEL_GREEN = QColor("#217346")
SELECTION = QColor(33, 115, 70, 38)
HEADING_BG = QColor("#f3f3f3")
HEADING_ON = QColor("#d2d2d2")
GRIDLINE = QColor("#d4d4d4")

_BORDER_WIDTH = {"hair": 0.25, "thin": 0.75, "medium": 1.5, "thick": 2.25,
                 "dashed": 0.75, "dotted": 0.75, "double": 0.75}
THIN = Border("thin", "#000000")


def cell_font(st: Style) -> QFont:
    font = page_font(st.font or DEFAULT_FONT, st.size or DEFAULT_SIZE, st.bold, st.italic,
                     bool(st.underline))
    if st.strike:
        font.setStrikeOut(True)
    return font


def border_pen(b: Border) -> QPen:
    pen = QPen(QColor(b.color or "#000000"), _BORDER_WIDTH.get(b.style, 0.75))
    pen.setCapStyle(Qt.SquareCap)
    if b.style == "dashed":
        pen.setDashPattern([4, 2])
    elif b.style == "dotted":
        pen.setDashPattern([1, 1.5])
    return pen


@register_item
class TableItem(MarkupItem):
    """A table: cells with Excel's formulas, formats and units."""

    TYPE = "table"
    NAME = "Table"
    ROTATABLE = False
    IS_CALC = True
    region = None                    # it is not an equation
    opened = False                   # open for its cells (not part of the record)
    SHEET_KIND = "table"             # what the workbook calls it (a sheet section: "sheet")
    #: the rows and columns painted: (top, bottom, left, right), or None for all
    _range: Optional[tuple] = None

    def __init__(self, rows: int = 4, cols: int = 3):
        super().__init__()
        self.sheet = None
        self._book = None
        self._data: Optional[dict] = None
        self._new_size = (max(1, rows), max(1, cols))
        self._edges = None
        # set by the window while the table is open (ui/tableedit.py)
        self.selection: Optional[tuple] = None      # (top, left, bottom, right)
        self.active: Optional[tuple] = None         # (row, col)
        self.overlay = None                          # callable(painter): reference colours...
        self._turn_while_open = None                 # its rotation, while shown upright to type in
        self.setZValue(-0.5)

    # -- the sheet behind it ---------------------------------------------------------
    def _page_frame(self):
        frame = self.parentItem()
        return frame if frame is not None and hasattr(frame, "page") \
            and hasattr(frame, "document") else None

    @property
    def name(self) -> str:
        if self.sheet is not None:
            return self.sheet.name
        return (self._data or {}).get("name", "Table")

    def _attach(self) -> None:
        frame = self._page_frame()
        if frame is None or self.scene() is None:
            self._detach()
            return
        if self.sheet is not None:
            self._place()
            return
        from ..sheet.docbook import book_for
        from ..sheet.store import load_sheet

        book = book_for(frame.document)
        if book.later is None:
            from PySide6.QtCore import QTimer
            book.later = lambda run: QTimer.singleShot(0, run)
        data, self._data = self._data, None
        sheet = book.attach(self.uid, (data or {}).get("name"), self.SHEET_KIND)
        self._book = book
        self.sheet = sheet
        if data is not None:
            load_sheet(sheet, data)
            wanted = data.get("name")
            if wanted and wanted != sheet.name and book.workbook.sheet(wanted) is None:
                sheet.name = wanted
        elif sheet.size is None:
            self._start_empty(sheet)
        book.listeners.append(self._values_changed)
        # (its size was already right: edges() reads the record until now,
        # and Qt must not be told of a geometry change in the middle of
        # putting the item on its page)
        self._edges = None
        self._place()

    def _start_empty(self, sheet) -> None:
        """A new table: its size, and thin borders on every cell (the user's
        choice, 2026-10-09)."""
        wb = sheet.workbook
        rows, cols = self._new_size
        with wb.transaction("New table"):
            sheet.size = (rows, cols)
            wb.border_block(sheet, 0, 0, rows - 1, cols - 1, "all", THIN)

    def _detach(self) -> None:
        if self.sheet is None:
            return
        from ..sheet.store import sheet_to_dict

        self._data = sheet_to_dict(self.sheet)
        book = self._book
        if self._values_changed in book.listeners:
            book.listeners.remove(self._values_changed)
        book.detach(self.uid)
        self.sheet = None
        self._book = None

    def _place(self) -> None:
        frame = self._page_frame()
        if frame is None or self._book is None:
            return
        from .calc import unturned_px

        # a page turned since it was written turns its markups with it: the
        # table's place in reading order is where it is on the page as written
        turn = self._turn_while_open if self._turn_while_open is not None else self.rotation()
        turns = int(round(turn / 90.0)) % 4
        x, y = unturned_px(frame, self.pos().x(), self.pos().y(), turns)
        self._book.place(self.uid, frame.page.uid, x, y)

    def _values_changed(self, keys: set) -> None:
        sheet = self.sheet
        if sheet is None:
            return
        sid = sheet.id
        if ("layout", sid) in keys:
            self._edges = None
            self.prepareGeometryChange()
            self.update()
            return
        if any(k[0] == sid for k in keys):
            self.update()

    def itemChange(self, change, value):
        result = super().itemChange(change, value)
        if change in (QGraphicsItem.ItemParentHasChanged, QGraphicsItem.ItemSceneHasChanged):
            self._attach()
        elif change == QGraphicsItem.ItemPositionHasChanged:
            self._place()
        return result

    def show_upright(self, view_turn: float = 0.0) -> None:
        """While it is open for its cells it reads the right way up, whatever
        the page has been turned to (as an equation does); leave_upright
        turns it back."""
        if self._turn_while_open is None:
            self._turn_while_open = self.rotation()
        if (self._turn_while_open - view_turn) % 360:
            self.setRotation(-view_turn)

    def leave_upright(self) -> None:
        if self._turn_while_open is None:
            return
        turn, self._turn_while_open = self._turn_while_open, None
        if self.rotation() != turn:
            self.setRotation(turn)

    def layout_changed(self) -> None:
        """Rows or columns resized, inserted or deleted."""
        self._edges = None
        self.prepareGeometryChange()
        self.update()

    # -- geometry ----------------------------------------------------------------------
    @property
    def size(self) -> tuple:
        if self.sheet is not None and self.sheet.size:
            return self.sheet.size
        if self._data and self._data.get("size"):
            return tuple(self._data["size"])
        return self._new_size

    def edges(self) -> tuple:
        """(x of each column edge, y of each row edge), from 0."""
        if self._edges is None:
            rows, cols = self.size
            sheet = self.sheet
            if sheet is not None:
                width, height = sheet.width, sheet.height
            else:
                data = self._data or {}
                dw = float(data.get("default_width", 48.0))
                dh = float(data.get("default_height", 15.0))
                widths = {int(k): float(v) for k, v in data.get("widths", {}).items()}
                heights = {int(k): float(v) for k, v in data.get("heights", {}).items()}
                hc, hr = set(data.get("hidden_cols", [])), set(data.get("hidden_rows", []))
                width = lambda c: 0.0 if c in hc else widths.get(c, dw)
                height = lambda r: 0.0 if r in hr else heights.get(r, dh)
            xs, ys = [0.0], [0.0]
            for c in range(cols):
                xs.append(xs[-1] + width(c))
            for r in range(rows):
                ys.append(ys[-1] + height(r))
            if sheet is None:
                return xs, ys
            self._edges = (xs, ys)
        return self._edges

    def local_rect(self) -> QRectF:
        xs, ys = self.edges()
        return QRectF(0, 0, xs[-1], ys[-1])

    def set_local_rect(self, rect: QRectF) -> None:
        """Dragging an edge or corner adds or removes rows and columns
        (the user's choice); the table's top-left stays put."""
        rect = rect.normalized()
        if self.sheet is None:
            return
        if rect.topLeft() != QPointF(0, 0):
            self.setPos(self.mapToParent(rect.topLeft()))
            rect.translate(-rect.topLeft())
        rows, cols = self.size
        new_rows = _count_fitting(rect.height(), self.sheet.height, rows, self.sheet.default_height)
        new_cols = _count_fitting(rect.width(), self.sheet.width, cols, self.sheet.default_width)
        self.resize_table(new_rows, new_cols)

    def resize_table(self, rows: int, cols: int) -> None:
        sheet = self.sheet
        old_rows, old_cols = self.size
        if (rows, cols) == (old_rows, old_cols) or sheet is None:
            return
        wb = sheet.workbook
        with wb.transaction("Resize table"):
            wb.set_size(sheet, rows, cols)
            # new rows and columns look like the last ones (as an Excel table grows)
            for r in range(old_rows, rows):
                for c in range(cols):
                    src = sheet.cells.get((old_rows - 1, min(c, old_cols - 1)))
                    wb._set_state(sheet, r, c, ("", src.style if src else 0, None))
            for c in range(old_cols, cols):
                for r in range(min(rows, old_rows)):
                    src = sheet.cells.get((r, old_cols - 1))
                    wb._set_state(sheet, r, c, ("", src.style if src else 0, None))
        self.layout_changed()

    def cell_at(self, local: QPointF) -> Optional[tuple]:
        """(row, col) under a point in the table's own coordinates."""
        xs, ys = self.edges()
        if not (0 <= local.x() < xs[-1] and 0 <= local.y() < ys[-1]):
            return None
        import bisect

        col = max(0, bisect.bisect_right(xs, local.x()) - 1)
        row = max(0, bisect.bisect_right(ys, local.y()) - 1)
        return min(row, len(ys) - 2), min(col, len(xs) - 2)

    def cell_rect(self, row: int, col: int, merged: bool = True) -> QRectF:
        xs, ys = self.edges()
        rows, cols = self.size
        row, col = max(0, min(row, rows - 1)), max(0, min(col, cols - 1))
        if merged and self.sheet is not None:
            m = self.sheet.merge_at(row, col)
            if m is not None:
                return QRectF(xs[m[1]], ys[m[0]], xs[min(m[3], cols - 1) + 1] - xs[m[1]],
                              ys[min(m[2], rows - 1) + 1] - ys[m[0]])
        return QRectF(xs[col], ys[row], xs[col + 1] - xs[col], ys[row + 1] - ys[row])

    def block_rect(self, top, left, bottom, right) -> QRectF:
        return self.cell_rect(top, left, False).united(self.cell_rect(bottom, right, False))

    def chrome_rect(self) -> QRectF:
        r = self.local_rect()
        return r.adjusted(-ROWNUM_W, -(HEADING_H + TAB_H), 16, 4)

    def tab_rect(self) -> QRectF:
        """The name tab above the table (screen only)."""
        font = page_font("", 8.0)
        width = QFontMetricsF(font).horizontalAdvance(self.name) + 10
        top = -(HEADING_H + TAB_H) if self.opened else -TAB_H
        return QRectF(-ROWNUM_W if self.opened else 0, top, max(width, 30.0), TAB_H)

    def boundingRect(self) -> QRectF:
        return self.chrome_rect().adjusted(-2, -2, 2, 2)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        if self.opened:
            path.addRect(self.chrome_rect())
        else:
            path.addRect(self.local_rect().adjusted(-2, -2, 2, 2))
            if self.isSelected():
                path.addRect(self.tab_rect())
        return path

    # -- drawing ----------------------------------------------------------------------------
    def _style(self, row, col) -> Style:
        sheet = self.sheet
        if sheet is None:
            return Style()
        cell = sheet.cells.get((row, col))
        return sheet.workbook.styles.get(cell.style if cell else 0)

    def _looks(self, row, col) -> dict:
        """What conditional formatting makes of a cell ({} when nothing)."""
        sheet = self.sheet
        if sheet is None or not sheet.cond_rules:
            return {}
        from ..sheet.condfmt import looks_for
        return looks_for(sheet).look(row, col)

    def _shown_style(self, row, col) -> Style:
        """The cell's style with its conditional formats on."""
        st = self._style(row, col)
        fmt = self._looks(row, col).get("format")
        if not fmt:
            return st
        from dataclasses import replace as _replace
        fields = {k: v for k, v in fmt.items() if hasattr(st, k)}
        if "underline" in fields and fields["underline"] is True:
            fields["underline"] = "single"
        return _replace(st, **fields)

    def _gridlines_shown(self, printing: bool) -> bool:
        return self.sheet.show_gridlines and not printing

    def paint_content(self, painter: QPainter) -> None:
        sheet = self.sheet
        if sheet is None:
            return
        xs, ys = self.edges()
        rows, cols = self.size
        r0, r1, c0, c1 = self._range or (0, rows - 1, 0, cols - 1)
        r1, c1 = min(r1, rows - 1), min(c1, cols - 1)
        frame = self._page_frame()
        printing = bool(getattr(frame, "print_mode", False))
        merges = [m for m in sheet.merges if m[0] < rows and m[1] < cols]
        covered = {}
        for m in merges:
            for r in range(m[0], min(m[2], rows - 1) + 1):
                for c in range(m[1], min(m[3], cols - 1) + 1):
                    covered[(r, c)] = m
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, False)
        # fills
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                m = covered.get((r, c))
                if m is not None and (r, c) != (m[0], m[1]):
                    continue
                st = self._shown_style(r, c)
                look = self._looks(r, c) if sheet.cond_rules else {}
                fill = st.fill if (look.get("format") or {}).get("fill") else (look.get("scale") or st.fill)
                if fill:
                    painter.fillRect(self.cell_rect(r, c), QColor(fill))
                bar = look.get("bar")
                if bar is not None:
                    rect = self.cell_rect(r, c).adjusted(1, 1.5, -1, -1.5)
                    rect.setWidth(rect.width() * bar[0])
                    from PySide6.QtGui import QLinearGradient
                    grad = QLinearGradient(rect.topLeft(), rect.topRight())
                    grad.setColorAt(0, QColor(bar[1]))
                    end = QColor(bar[1])
                    end.setAlpha(60)
                    grad.setColorAt(1, end)
                    painter.fillRect(rect, grad)
        # gridlines, on screen only (Excel's default)
        if self._gridlines_shown(printing):
            pen = QPen(GRIDLINE, 0)
            pen.setCosmetic(True)
            painter.setPen(pen)
            for c in range(c0, c1 + 2):
                painter.drawLine(QPointF(xs[c], ys[r0]), QPointF(xs[c], ys[r1 + 1]))
            for r in range(r0, r1 + 2):
                painter.drawLine(QPointF(xs[c0], ys[r]), QPointF(xs[c1 + 1], ys[r]))
            # no gridlines inside merged cells
            for m in merges:
                rect = self.cell_rect(m[0], m[1])
                st = self._style(m[0], m[1])
                painter.fillRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), QColor(st.fill) if st.fill else QColor("white"))
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        # text
        for (r, c), cell in list(sheet.cells.items()):
            if r >= rows or c >= cols or cell.value is BLANK:
                continue
            if self._range is not None and not (r0 <= r <= r1) and \
                    not any(m[0] <= r1 and m[2] >= r0 for m in [covered.get((r, c))] if m):
                continue
            m = covered.get((r, c))
            if m is not None and (r, c) != (m[0], m[1]):
                continue
            self._paint_text(painter, r, c, cell, rows, cols, covered)
        # borders
        painter.setRenderHint(QPainter.Antialiasing, False)
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                m = covered.get((r, c))
                st = self._style(m[0], m[1]) if m else self._style(r, c)
                rect = QRectF(xs[c], ys[r], xs[c + 1] - xs[c], ys[r + 1] - ys[r])
                own = self._style(r, c)
                for side, a, b in (("top", rect.topLeft(), rect.topRight()),
                                   ("bottom", rect.bottomLeft(), rect.bottomRight()),
                                   ("left", rect.topLeft(), rect.bottomLeft()),
                                   ("right", rect.topRight(), rect.bottomRight())):
                    border = getattr(own, side)
                    if m is not None:
                        inside = (side == "top" and r > m[0]) or (side == "bottom" and r < m[2]) or \
                                 (side == "left" and c > m[1]) or (side == "right" and c < m[3])
                        if inside:
                            continue
                        border = border or getattr(st, side)
                    if border is None:
                        continue
                    _draw_border(painter, border, a, b, side)
        painter.restore()

    def _paint_text(self, painter, r, c, cell, rows, cols, covered) -> None:
        sheet = self.sheet
        st = self._shown_style(r, c)
        shown = format_value(cell.value, st.number_format, st.unit)
        text = shown.text
        if not text:
            return
        rect = self.cell_rect(r, c)
        icon = self._looks(r, c).get("icon") if sheet.cond_rules else None
        if icon is not None:
            # an icon set's icon at the cell's left, the text beside it
            painter.save()
            painter.setFont(page_font("", 9.0))
            painter.setPen(QColor(icon[1]))
            painter.drawText(QRectF(rect.left() + 1, rect.top(), 11, rect.height()),
                             Qt.AlignCenter, icon[0])
            painter.restore()
            rect = rect.adjusted(11, 0, 0, 0)
        font = cell_font(st)
        metrics = QFontMetricsF(font)
        value = cell.value
        numeric = isinstance(value, (float, Qty)) and not isinstance(value, bool)
        align = st.h_align
        if align == "general":
            align = "right" if numeric else ("center" if isinstance(value, (bool, ErrorValue)) else "left")
        indent = st.indent * 7.5
        inner = rect.adjusted(PAD + (indent if align == "left" else 0), 0,
                              -PAD - (indent if align == "right" else 0), 0)
        colour = QColor(shown.color or st.color or "#000000")
        painter.setFont(font)
        painter.setPen(colour)
        v = {"top": Qt.AlignTop, "center": Qt.AlignVCenter}.get(st.v_align, Qt.AlignBottom)
        if st.rotation:
            self._paint_turned(painter, rect, text, st, v)
            return
        if st.wrap:
            h = {"left": Qt.AlignLeft, "center": Qt.AlignHCenter, "right": Qt.AlignRight,
                 "justify": Qt.AlignJustify}.get(align, Qt.AlignLeft)
            painter.save()
            painter.setClipRect(rect)
            painter.drawText(inner, h | v | Qt.TextWordWrap, text)
            painter.restore()
            return
        width = metrics.horizontalAdvance(text)
        if numeric and width > inner.width() and not st.shrink:
            # Excel: a number that doesn't fit shows ####
            n = max(1, int(inner.width() / max(metrics.horizontalAdvance("#"), 0.1)))
            text, width, align = "#" * n, metrics.horizontalAdvance("#") * n, "center"
        if st.shrink and width > inner.width() and width > 0:
            font.setPixelSize(max(1, int(font.pixelSize() * inner.width() / width)))
            painter.setFont(font)
            metrics = QFontMetricsF(font)
            width = metrics.horizontalAdvance(text)
        if align == "fill" and width > 0:
            text = text * max(1, int(inner.width() / width))
            align = "left"
        clip = QRectF(rect)
        if not numeric and width > inner.width():
            # text runs on into empty neighbours, as in Excel
            xs, _ys = self.edges()
            if align in ("left", "centerAcross"):
                k = c + 1
                while k < cols and self._empty(r, k) and clip.width() < width + 2 * PAD:
                    clip.setRight(xs[k + 1])
                    k += 1
            elif align == "right":
                k = c - 1
                while k >= 0 and self._empty(r, k) and clip.width() < width + 2 * PAD:
                    clip.setLeft(xs[k])
                    k -= 1
            elif align == "center":
                k, j = c + 1, c - 1
                while (k < cols or j >= 0) and clip.width() < width + 2 * PAD:
                    grown = False
                    if k < cols and self._empty(r, k):
                        clip.setRight(xs[k + 1])
                        k += 1
                        grown = True
                    if j >= 0 and self._empty(r, j):
                        clip.setLeft(xs[j])
                        j -= 1
                        grown = True
                    if not grown:
                        break
        if align == "left":
            x = inner.left()
        elif align == "right":
            x = inner.right() - width
        else:
            x = rect.center().x() - width / 2
        if v == Qt.AlignTop:
            y = rect.top() + PAD / 2 + metrics.ascent()
        elif v == Qt.AlignVCenter:
            y = rect.center().y() + (metrics.ascent() - metrics.descent()) / 2
        else:
            y = rect.bottom() - PAD / 2 - metrics.descent()
        painter.save()
        painter.setClipRect(clip)
        painter.drawText(QPointF(x, y), text)
        painter.restore()

    def _paint_turned(self, painter, rect, text, st, v) -> None:
        painter.save()
        painter.setClipRect(rect)
        painter.translate(rect.center())
        angle = 90 if st.rotation == 255 else st.rotation
        painter.rotate(-angle)
        span = max(rect.width(), rect.height()) * 2
        painter.drawText(QRectF(-span / 2, -span / 2, span, span), Qt.AlignCenter, text)
        painter.restore()

    def _empty(self, r, c) -> bool:
        cell = self.sheet.cells.get((r, c))
        return cell is None or cell.value is BLANK or cell.value == ""

    def paint(self, painter: QPainter, option, widget=None) -> None:
        super().paint(painter, option, widget)
        frame = self._page_frame()
        if getattr(frame, "print_mode", False) or self.sheet is None:
            return
        painter.save()
        self._paint_marks(painter)
        painter.restore()
        painter.save()
        if self.opened:
            self._paint_chrome(painter)
            self._paint_selection(painter)
            if self.overlay is not None:
                self.overlay(painter)
        if self.opened or self.isSelected():
            self._paint_tab(painter)
        painter.restore()

    circles: list = ()            # Circle Invalid Data: cells to ring (screen only)

    def _paint_marks(self, painter) -> None:
        """On screen only: comment triangles, filter buttons, the list
        drop-down on the active cell, invalid-data circles."""
        sheet = self.sheet
        rows, cols = self.size
        painter.setRenderHint(QPainter.Antialiasing, True)
        for (r, c), cell in sheet.cells.items():
            if cell.comment and r < rows and c < cols:
                rect = self.cell_rect(r, c)
                path = QPainterPath()
                path.moveTo(rect.topRight())
                path.lineTo(rect.topRight() + QPointF(-4, 0))
                path.lineTo(rect.topRight() + QPointF(0, 4))
                path.closeSubpath()
                painter.fillPath(path, QColor("#d9480f"))
        flt = sheet.filter
        if flt is not None:
            t, l, b, r = flt["range"]
            for c in range(l, min(r, cols - 1) + 1):
                box = self.filter_button(c)
                on = c in flt.get("criteria", {})
                painter.setPen(QPen(QColor("#8c8c8c"), 0))
                painter.setBrush(QColor("#ffffff"))
                painter.drawRect(box)
                painter.setPen(Qt.NoPen)
                painter.setBrush(EXCEL_GREEN if on else QColor("#444444"))
                mid = box.center()
                if on:              # a funnel: this column is filtered
                    tri = QPainterPath()
                    tri.moveTo(mid + QPointF(-3, -2.5))
                    tri.lineTo(mid + QPointF(3, -2.5))
                    tri.lineTo(mid + QPointF(0.7, 0.5))
                    tri.lineTo(mid + QPointF(0.7, 3))
                    tri.lineTo(mid + QPointF(-0.7, 3))
                    tri.lineTo(mid + QPointF(-0.7, 0.5))
                    tri.closeSubpath()
                    painter.drawPath(tri)
                else:
                    tri = QPainterPath()
                    tri.moveTo(mid + QPointF(-2.5, -1))
                    tri.lineTo(mid + QPointF(2.5, -1))
                    tri.lineTo(mid + QPointF(0, 1.8))
                    tri.closeSubpath()
                    painter.drawPath(tri)
        if self.opened and self.active is not None and self.list_button() is not None:
            box = self.list_button()
            painter.setPen(QPen(QColor("#8c8c8c"), 0))
            painter.setBrush(QColor("#f3f3f3"))
            painter.drawRect(box)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#444444"))
            mid = box.center()
            tri = QPainterPath()
            tri.moveTo(mid + QPointF(-2.5, -1))
            tri.lineTo(mid + QPointF(2.5, -1))
            tri.lineTo(mid + QPointF(0, 1.8))
            tri.closeSubpath()
            painter.drawPath(tri)
        if self.opened and self.active is not None:
            # a dynamic array's block: Excel's thin blue frame while one of its
            # cells is the active one
            block = sheet.workbook.spill_block(sheet, *self.active)
            if block is not None:
                pen = QPen(QColor("#2f75b5"), 1.0)
                pen.setCosmetic(True)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(self.block_rect(*block))
        if self.circles:
            pen = QPen(QColor("#e03131"), 1.2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            for r, c in self.circles:
                if r < rows and c < cols:
                    painter.drawEllipse(self.cell_rect(r, c).adjusted(-3, -2, 3, 2))

    def filter_button(self, col: int) -> QRectF:
        """The AutoFilter drop-down of a column (in the filter's first row)."""
        top = self.sheet.filter["range"][0]
        rect = self.cell_rect(top, col, merged=False)
        s = min(11.0, rect.height() - 2)
        return QRectF(rect.right() - s - 1, rect.bottom() - s - 1, s, s)

    def list_button(self) -> Optional[QRectF]:
        """The drop-down beside the active cell when it has a list to pick from."""
        from ..sheet.validation import at
        rule = at(self.sheet, *self.active)
        if rule is None or rule.get("type") != "list" or not rule.get("dropdown", True):
            return None
        rect = self.cell_rect(*self.active)
        s = min(12.0, rect.height())
        return QRectF(rect.right() + 1, rect.bottom() - s, s, s)

    def paint_handles(self, painter: QPainter) -> None:
        if not self.opened:
            super().paint_handles(painter)

    def _paint_tab(self, painter) -> None:
        rect = self.tab_rect()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(EXCEL_GREEN, 0))
        painter.setBrush(QColor("white"))
        path = QPainterPath()
        path.addRoundedRect(rect, 2, 2)
        painter.drawPath(path)
        painter.setFont(page_font("", 8.0, True))
        painter.setPen(EXCEL_GREEN)
        painter.drawText(rect, Qt.AlignCenter, self.name)

    def _paint_chrome(self, painter) -> None:
        xs, ys = self.edges()
        rows, cols = self.size
        sel = self.selection
        font = page_font("", 8.0)
        painter.setFont(font)
        painter.setRenderHint(QPainter.Antialiasing, False)
        grid = QPen(QColor("#bdbdbd"), 0)
        grid.setCosmetic(True)
        painter.setBrush(Qt.NoBrush)
        for c in range(cols):
            cell = QRectF(xs[c], -HEADING_H, xs[c + 1] - xs[c], HEADING_H)
            on = sel is not None and sel[1] <= c <= sel[3]
            painter.fillRect(cell, HEADING_ON if on else HEADING_BG)
            painter.setPen(grid)
            painter.drawRect(cell)
            painter.setPen(EXCEL_GREEN if on else QColor("#444444"))
            painter.drawText(cell, Qt.AlignCenter, col_letters(c))
        for r in range(rows):
            cell = QRectF(-ROWNUM_W, ys[r], ROWNUM_W, ys[r + 1] - ys[r])
            on = sel is not None and sel[0] <= r <= sel[2]
            painter.fillRect(cell, HEADING_ON if on else HEADING_BG)
            painter.setPen(grid)
            painter.drawRect(cell)
            painter.setPen(EXCEL_GREEN if on else QColor("#444444"))
            painter.drawText(cell, Qt.AlignCenter, str(r + 1))
        corner = QRectF(-ROWNUM_W, -HEADING_H, ROWNUM_W, HEADING_H)
        painter.fillRect(corner, HEADING_BG)
        painter.setPen(grid)
        painter.drawRect(corner)

    def _paint_selection(self, painter) -> None:
        sel = self.selection
        if sel is None:
            return
        top, left, bottom, right = sel
        rows, cols = self.size
        bottom, right = min(bottom, rows - 1), min(right, cols - 1)
        box = self.block_rect(top, left, bottom, right)
        painter.setRenderHint(QPainter.Antialiasing, False)
        path = QPainterPath()
        path.addRect(box)
        if self.active is not None:
            hole = QPainterPath()
            hole.addRect(self.cell_rect(*self.active))
            path = path.subtracted(hole)
        painter.fillPath(path, SELECTION)
        pen = QPen(EXCEL_GREEN, 2)
        pen.setCosmetic(True)
        pen.setJoinStyle(Qt.MiterJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(box)
        handle = self.fill_handle_rect()
        if handle is not None:
            painter.fillRect(handle, EXCEL_GREEN)
            white = QPen(QColor("white"), 1)
            white.setCosmetic(True)
            painter.setPen(white)
            painter.drawRect(handle)

    def fill_handle_rect(self) -> Optional[QRectF]:
        if self.selection is None:
            return None
        top, left, bottom, right = self.selection
        rows, cols = self.size
        box = self.block_rect(top, left, min(bottom, rows - 1), min(right, cols - 1))
        s = 3.2
        return QRectF(box.right() - s / 2, box.bottom() - s / 2, s, s)

    # -- the record ---------------------------------------------------------------------------
    def serialize(self) -> dict:
        from ..sheet.store import sheet_to_dict

        data = self.base_dict()
        if self._turn_while_open is not None:
            data["rotation"] = self._turn_while_open      # as it lies on the page
        if self.sheet is not None:
            data["table"] = sheet_to_dict(self.sheet)
        elif self._data is not None:
            data["table"] = self._data
        else:
            data["table"] = {"name": None, "size": list(self._new_size), "cells": [], "styles": [{}],
                             "new": True}
        return data

    def deserialize(self, data: dict) -> None:
        table = data.get("table") or {}
        if table.get("new"):
            self._new_size = tuple(table.get("size") or (4, 3))
            self._data = None
        else:
            self._data = table
        self.load_base(data)

    def summary(self) -> str:
        rows, cols = self.size
        return f"{self.name} — {rows} × {cols}"

    def display_name(self) -> str:
        return self.label or self.name


def _count_fitting(length: float, size, current: int, default: float) -> int:
    """How many rows (or columns) a length holds: the existing ones at their
    sizes, new ones at the default size; at least one."""
    total, n = 0.0, 0
    while True:
        step = size(n) if n < current else default
        if step <= 0:
            n += 1
            continue
        if total + step / 2 > length and n >= 1:
            return n
        total += step
        n += 1
        if n > 5000:
            return n


def _draw_border(painter, border: Border, a: QPointF, b: QPointF, side: str) -> None:
    pen = border_pen(border)
    painter.setPen(pen)
    if border.style == "double":
        off = 0.75
        d = QPointF(0, off) if side in ("top", "bottom") else QPointF(off, 0)
        painter.drawLine(a - d, b - d)
        painter.drawLine(a + d, b + d)
    else:
        painter.drawLine(a, b)
