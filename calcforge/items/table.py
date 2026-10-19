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

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem

from ..core.typography import page_font
from ..sheet.condfmt import looks_for
from ..sheet.numfmt import format_value, unit_runs
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


_FONTS: dict = {}
_PENS: dict = {}


def cell_font(st: Style) -> QFont:
    key = (st.font or DEFAULT_FONT, st.size or DEFAULT_SIZE, bool(st.bold), bool(st.italic),
           bool(st.underline), bool(st.strike))
    font = _FONTS.get(key)
    if font is None:
        font = page_font(key[0], key[1], key[2], key[3], key[4])
        if st.strike:
            font.setStrikeOut(True)
        _FONTS[key] = font
    return QFont(font)


_METRICS: dict = {}
_COLOURS: dict = {}
#: what a number too wide for its cell shows (TableItem._fitted), by value,
#: format, font and room
_FITTED: dict = {}


def _metrics(st: Style) -> QFontMetricsF:
    key = (st.font or DEFAULT_FONT, st.size or DEFAULT_SIZE, bool(st.bold), bool(st.italic),
           bool(st.underline), bool(st.strike))
    got = _METRICS.get(key)
    if got is None:
        got = _METRICS[key] = QFontMetricsF(cell_font(st))
    return got


def _colour(name: str) -> QColor:
    got = _COLOURS.get(name)
    if got is None:
        got = _COLOURS[name] = QColor(name)
    return got


def border_pen(b: Border) -> QPen:
    key = (b.style, b.color)
    pen = _PENS.get(key)
    if pen is None:
        pen = QPen(QColor(b.color or "#000000"), _BORDER_WIDTH.get(b.style, 0.75))
        pen.setCapStyle(Qt.SquareCap)
        if b.style == "dashed":
            pen.setDashPattern([4, 2])
        elif b.style == "dotted":
            pen.setDashPattern([1, 1.5])
        _PENS[key] = pen
    return pen


# A unit's power beside it, as the equations set it (calc/ui/layout.py): four
# fifths of the size, lifted by about half the capitals' height.
SUP_SIZE = 0.8
SUP_RISE = 0.55
_SUP_FONTS: dict = {}
_FONT_METRICS: dict = {}


def _font_metrics(font: QFont) -> QFontMetricsF:
    key = font.key()
    got = _FONT_METRICS.get(key)
    if got is None:
        got = _FONT_METRICS[key] = QFontMetricsF(font)
    return got


def _sup_font(font: QFont) -> QFont:
    key = font.key()
    got = _SUP_FONTS.get(key)
    if got is None:
        got = QFont(font)
        got.setPixelSize(max(1, int(round(font.pixelSize() * SUP_SIZE))))
        _SUP_FONTS[key] = got
    return got


class Drawn:
    """A cell's shown value as it is drawn: the number in the cell's ink,
    then its unit as an equation draws it — SMath's unit blue, its powers
    raised and smaller, products with a dot (kN·m, kN/m², m⁻¹) — once the
    entry is made (the user, 2026-10-15). Everything that measures the
    text (####, shrink to fit, the unit box) measures this, so it agrees
    with what is on the cell; printing and export draw the same."""

    __slots__ = ("runs", "font", "metrics", "width", "unit_left")

    def __init__(self, text: str, unit: Optional[str], font: QFont,
                 metrics: Optional[QFontMetricsF] = None, runs: Optional[list] = None):
        self.font = font
        self.metrics = metrics or _font_metrics(font)
        if runs is None:
            if unit and text.endswith(unit):
                runs = [(text[:len(text) - len(unit)], "")]
                runs += [(t, "sup" if raised else "unit") for t, raised in unit_runs(unit)]
            else:
                runs = [(text, "")]
        self.runs = runs
        width = 0.0
        self.unit_left = None
        for t, kind in runs:
            if kind and self.unit_left is None:
                self.unit_left = width
            width += self._advance(t, kind)
        self.width = width

    def _advance(self, t: str, kind: str) -> float:
        if kind == "sup":
            return _font_metrics(_sup_font(self.font)).horizontalAdvance(t)
        return self.metrics.horizontalAdvance(t)

    @property
    def rise(self) -> float:
        return self.metrics.capHeight() * SUP_RISE

    @property
    def ascent(self) -> float:
        a = self.metrics.ascent()
        if any(kind == "sup" for _t, kind in self.runs):
            a = max(a, self.rise + _font_metrics(_sup_font(self.font)).ascent())
        return a

    @property
    def descent(self) -> float:
        return self.metrics.descent()

    @property
    def plain(self) -> bool:
        return len(self.runs) == 1 and not self.runs[0][1]

    def repeated(self, n: int) -> "Drawn":
        return Drawn("", None, self.font, self.metrics, self.runs * max(1, n))

    def draw(self, painter: QPainter, x: float, y: float, ink: QColor) -> None:
        """At baseline *y* from *x*, the number in *ink*."""
        if self.plain:
            painter.drawText(QPointF(x, y), self.runs[0][0])
            return
        UNIT_BLUE = _unit_blue()
        font = self.font
        for t, kind in self.runs:
            if not t:
                continue
            if kind == "sup":
                painter.setFont(_sup_font(font))
                painter.setPen(UNIT_BLUE)
                painter.drawText(QPointF(x, y - self.rise), t)
            else:
                painter.setFont(font)
                painter.setPen(UNIT_BLUE if kind else ink)
                painter.drawText(QPointF(x, y), t)
            x += self._advance(t, kind)
        painter.setFont(font)
        painter.setPen(ink)


_UNIT_BLUE: list = []


def _unit_blue() -> QColor:
    """SMath's unit blue (ui/cellunits.py), found once: it was imported
    afresh for every number with a unit drawn."""
    if not _UNIT_BLUE:
        from ..ui.cellunits import UNIT_BLUE
        _UNIT_BLUE.append(UNIT_BLUE)
    return _UNIT_BLUE[0]


_LINES: dict = {}


def _line(text: str, unit: Optional[str], st: Style, metrics: QFontMetricsF) -> Drawn:
    """Drawn(text, unit, cell_font(st), metrics), made once for each text,
    unit and font: a screenful of cells was a thousand of them made afresh
    for every picture of the sheet drawn. (Its own copy of the font: the
    one a cell shrinks to fit is changed where it is drawn.)"""
    key = (text, unit, st.font or DEFAULT_FONT, st.size or DEFAULT_SIZE, bool(st.bold),
           bool(st.italic), bool(st.underline), bool(st.strike))
    got = _LINES.get(key)
    if got is None or got.metrics is not metrics:
        got = Drawn(text, unit, cell_font(st), metrics)
        if len(_LINES) > 20000:
            _LINES.clear()
        _LINES[key] = got
    return got


def drawn_value(shown, st: Style, font: Optional[QFont] = None) -> Drawn:
    """*shown* (format_value's) as the cell with style *st* draws it."""
    if font is None:
        return Drawn(shown.text, shown.unit, cell_font(st), _metrics(st))
    return Drawn(shown.text, shown.unit, font)


def shown_width(shown, st: Style) -> float:
    """How wide a cell's shown value is drawn (AutoFit, a column widened
    for a number typed in)."""
    return drawn_value(shown, st).width


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
        # told what part is being repainted (paint): only those rows are drawn
        self.setFlag(QGraphicsItem.ItemUsesExtendedStyleOption, True)

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
        from ..ui.tableedit import table_left
        table_left(self.uid)

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
        return looks_for(sheet).look(row, col)

    def _shown_style(self, row, col) -> Style:
        """The cell's style with its conditional formats on."""
        memo = self._shown_memo
        if memo is not None:
            got = memo.get((row, col))
            if got is None:
                got = memo[(row, col)] = self._work_out_style(row, col)
            return got
        return self._work_out_style(row, col)

    _shown_memo = None               # (row, col) -> shown style, while painting

    def _work_out_style(self, row, col) -> Style:
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
        self._shown_memo = {}
        try:
            self._paint_cells(painter, xs, ys, rows, cols, r0, r1, c0, c1, printing, merges, covered)
        finally:
            self._shown_memo = None
        from .nametags import paint_cell_tags
        paint_cell_tags(self, painter, r0, r1, c0, c1)

    def _paint_cells(self, painter, xs, ys, rows, cols, r0, r1, c0, c1, printing, merges,
                     covered) -> None:
        sheet = self.sheet
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, False)
        # Only the cells that can draw a fill or a border are walked: one
        # with nothing in it and no style has neither, unless conditional
        # formatting colours it or it is part of a merged cell. (Walking
        # every place of the grid in view was a thousand style look-ups for
        # a screenful of a mostly empty sheet.) Row by row, as before.
        held = set(sheet.positions_in(r0, c0, r1, c1))
        held.update(p for p in covered if r0 <= p[0] <= r1 and c0 <= p[1] <= c1)
        # an empty cell is coloured by a rule only inside the rule's ranges
        # (walking every place in view for the rules took a second a screen
        # on the user's seismic workbook)
        for rule in sheet.cond_rules:
            for t, l, b, r in rule.get("ranges", []):
                t, l, b, r = max(t, r0), max(l, c0), min(b, r1), min(r, c1)
                held.update((y, x) for y in range(t, b + 1) for x in range(l, r + 1))
        grid = sorted(held)
        # fills
        for r, c in grid:
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
        if self._range is None:
            places = list(sheet.cells)
        else:
            # the rows in view, every column (a long text runs over its
            # neighbours), and merged cells reaching down into view
            places = sorted(sheet.positions_in(r0, 0, r1, cols - 1))
            places += [(m[0], m[1]) for m in merges if m[0] < r0 <= m[2]]
        cells = sheet.cells
        for r, c in places:
            cell = cells.get((r, c))
            if cell is None or r >= rows or c >= cols or cell.value is BLANK:
                continue
            m = covered.get((r, c))
            if m is not None and (r, c) != (m[0], m[1]):
                continue
            cell_box = self.cell_rect(r, c)
            if cell_box.width() <= 0 or cell_box.height() <= 0:
                continue                # hidden: its text isn't drawn (QA, 2026-10-15)
            self._paint_text(painter, r, c, cell, rows, cols, covered)
        # borders
        painter.setRenderHint(QPainter.Antialiasing, False)
        lines = _BorderLines(painter)
        for r, c in grid:
            m = covered.get((r, c))
            own = self._style(r, c)
            if m is None and not (own.top or own.bottom or own.left or own.right):
                continue
            st = self._style(m[0], m[1]) if m else own
            rect = QRectF(xs[c], ys[r], xs[c + 1] - xs[c], ys[r + 1] - ys[r])
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
                lines.add(border, a, b, side)
        lines.flush()
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
        metrics = _metrics(st)
        value = cell.value
        numeric = isinstance(value, (float, Qty)) and not isinstance(value, bool)
        align = st.h_align
        if align == "general":
            align = "right" if numeric else ("center" if isinstance(value, (bool, ErrorValue)) else "left")
        indent = st.indent * 7.5
        inner = rect.adjusted(PAD + (indent if align == "left" else 0), 0,
                              -PAD - (indent if align == "right" else 0), 0)
        colour = _colour(shown.color or st.color or "#000000")
        painter.setFont(font)
        painter.setPen(colour)
        v = {"top": Qt.AlignTop, "center": Qt.AlignVCenter}.get(st.v_align, Qt.AlignBottom)
        line = _line(text, shown.unit, st, metrics)
        if st.rotation:
            self._paint_turned(painter, rect, line, st, v, colour)
            return
        if st.wrap:
            h = {"left": Qt.AlignLeft, "center": Qt.AlignHCenter, "right": Qt.AlignRight,
                 "justify": Qt.AlignJustify}.get(align, Qt.AlignLeft)
            painter.save()
            painter.setClipRect(rect, Qt.IntersectClip)
            if line.plain:
                painter.drawText(inner, h | v | Qt.TextWordWrap, text)
            else:
                self._paint_wrapped(painter, rect, inner, line, align, v, colour)
            painter.restore()
            return
        width = line.width
        if numeric and width > inner.width() and not st.shrink:
            text = self._fitted(value, st, metrics, inner.width())
            line = _line(text, shown.unit, st, metrics)
            width = line.width
        if numeric and width > inner.width() and not st.shrink:
            # Excel: a number that doesn't fit shows ####
            n = max(1, int(inner.width() / max(metrics.horizontalAdvance("#"), 0.1)))
            line, align = Drawn("#" * n, None, font, metrics), "center"
            width = line.width
        if st.shrink and width > inner.width() and width > 0:
            font.setPixelSize(max(1, int(font.pixelSize() * inner.width() / width)))
            painter.setFont(font)
            line = Drawn(text, shown.unit, font)
            metrics = line.metrics
            width = line.width
        if align == "fill" and width > 0:
            line = line.repeated(int(inner.width() / width))
            width = line.width
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
        y = self._baseline(rect, v, metrics)
        if x >= clip.left() and x + width <= clip.right() and \
                y - line.ascent >= clip.top() and y + line.descent <= clip.bottom():
            line.draw(painter, x, y, colour)       # well inside its cell: no clip needed
            return
        painter.save()
        painter.setClipRect(clip, Qt.IntersectClip)
        line.draw(painter, x, y, colour)
        painter.restore()

    @staticmethod
    def _baseline(rect: QRectF, v, metrics: QFontMetricsF) -> float:
        """Where a line of the cell's text sits, for its vertical alignment."""
        if v == Qt.AlignTop:
            return rect.top() + PAD / 2 + metrics.ascent()
        if v == Qt.AlignVCenter:
            return rect.center().y() + (metrics.ascent() - metrics.descent()) / 2
        return rect.bottom() - PAD / 2 - metrics.descent()

    def _paint_wrapped(self, painter, rect, inner, line: "Drawn", align, v, colour) -> None:
        """Wrapped text holding a quantity: on one line when it fits, else
        the number on one line and its unit under it (where Qt's word wrap
        broke "3 kN/m^2"), each line drawn as an unwrapped one is."""
        metrics = line.metrics
        if line.width <= inner.width():
            lines = [line]
        else:
            number = line.runs[0][0].rstrip()
            lines = [Drawn(number, None, line.font, metrics),
                     Drawn("", None, line.font, metrics, line.runs[1:])]
        step = metrics.lineSpacing()
        block = step * (len(lines) - 1)
        if v == Qt.AlignTop:
            y = rect.top() + PAD / 2 + metrics.ascent()
        elif v == Qt.AlignVCenter:
            y = rect.center().y() + (metrics.ascent() - metrics.descent()) / 2 - block / 2
        else:
            y = rect.bottom() - PAD / 2 - metrics.descent() - block
        for one in lines:
            if align == "right":
                x = inner.right() - one.width
            elif align == "center":
                x = inner.center().x() - one.width / 2
            else:
                x = inner.left()
            one.draw(painter, x, y, colour)
            y += step

    def unit_box_rect(self, r: int, c: int) -> Optional[tuple]:
        """SMath's unit box after a quantity's result (the user's choice,
        2026-10-11): (kind, rect in this item) — "box", the black placeholder
        just after the text when no output unit is set, or "unit", the unit
        part of the text when one is, and the box after a #### too — or None
        when the cell holds no quantity shown plainly (wrapped or turned).
        Measured as the value is drawn: the blue unit with its raised powers."""
        cell = self.sheet.cells.get((r, c)) if self.sheet is not None else None
        if cell is None or not isinstance(cell.value, Qty):
            return None
        st = self._shown_style(r, c)
        if st.wrap or st.rotation or st.shrink:
            return None
        shown = format_value(cell.value, st.number_format, st.unit)
        text = shown.text
        if not text:
            return None
        rect = self.cell_rect(r, c)
        metrics = _metrics(st)
        line = Drawn(text, shown.unit, cell_font(st), metrics)
        width = line.width
        align = st.h_align if st.h_align not in ("general", "fill", "centerAcross") else "right"
        indent = st.indent * 7.5
        inner = rect.adjusted(PAD + (indent if align == "left" else 0), 0,
                              -PAD - (indent if align == "right" else 0), 0)
        if width > inner.width():
            text = self._fitted(cell.value, st, metrics, inner.width())
            line = Drawn(text, shown.unit, cell_font(st), metrics)
            width = line.width
        hashes = width > inner.width()
        if hashes:
            # shown as ####: the box after the hashes all the same, so the
            # unit that would make it fit can still be typed (the user,
            # 2026-10-15); centred as the hashes are
            n = max(1, int(inner.width() / max(metrics.horizontalAdvance("#"), 0.1)))
            width = metrics.horizontalAdvance("#") * n
            align = "center"
        x = inner.left() if align == "left" else (
            inner.right() - width if align == "right" else rect.center().x() - width / 2)
        v = {"top": Qt.AlignTop, "center": Qt.AlignVCenter}.get(st.v_align, Qt.AlignBottom)
        y = self._baseline(rect, v, metrics)
        px = metrics.height() / 1.15
        if st.unit and line.unit_left is not None and not hashes:
            left = x + line.unit_left
            return "unit", QRectF(left, y - line.ascent, x + width - left,
                                  line.ascent + line.descent)
        # the box of SMath's "H" glyph (5 x 7 px at 10 pt, 3 px left
        # bearing), centred on the middle of the text's x-height
        w, h = px * 0.376, px * 0.526
        middle = y - metrics.xHeight() * 0.5
        return "box", QRectF(x + width + px * 0.225 + 1.0, middle - h / 2, w, h)

    @staticmethod
    def _fitted(value, st: Style, metrics: QFontMetricsF, room: float) -> str:
        """A number too wide for its cell as Excel's General shows it: fewer
        decimals, or 5E+09, so it fits (an explicit number format is kept,
        and shows ####). Measured with the cell's own font — on Linux
        Calibri falls back to the wider DejaVu Sans (QA, 2026-10-15). As in
        Excel each character of the number takes at least a digit's width
        (a default column shows 0.333333, not 0.3333333); a unit after it
        takes its own width."""
        # (worked out once for each value, look and width: finding the fit
        # measures the number a dozen times over, and a screenful of narrow
        # cells was most of the time a sheet took to draw)
        font_key = (st.font or DEFAULT_FONT, st.size or DEFAULT_SIZE, bool(st.bold),
                    bool(st.italic), bool(st.underline), bool(st.strike))
        key = None
        if _METRICS.get(font_key) is metrics:          # (measured with the cell's own font)
            key = (repr(value), st.number_format, st.unit, font_key, room)
            got = _FITTED.get(key)
            if got is not None:
                return got
        digit = metrics.horizontalAdvance("0")

        def width(text: str) -> float:
            number, space, unit = text.partition(" ")
            return sum(max(metrics.horizontalAdvance(ch), digit) for ch in number) + \
                (metrics.horizontalAdvance(space + unit) if space else 0.0)
        got = format_value(value, st.number_format, st.unit,
                           fit=lambda t: width(t) <= room).text
        if key is not None:
            if len(_FITTED) > 20000:
                _FITTED.clear()
            _FITTED[key] = got
        return got

    def _paint_turned(self, painter, rect, line: "Drawn", st, v, colour) -> None:
        painter.save()
        painter.setClipRect(rect, Qt.IntersectClip)
        painter.translate(rect.center())
        angle = 90 if st.rotation == 255 else st.rotation
        painter.rotate(-angle)
        if line.plain:
            span = max(rect.width(), rect.height()) * 2
            painter.drawText(QRectF(-span / 2, -span / 2, span, span), Qt.AlignCenter, line.runs[0][0])
        else:
            # centred on the cell's middle, where Qt's AlignCenter puts plain text
            metrics = line.metrics
            line.draw(painter, -line.width / 2, (metrics.ascent() - metrics.descent()) / 2, colour)
        painter.restore()

    def _empty(self, r, c) -> bool:
        cell = self.sheet.cells.get((r, c))
        return cell is None or cell.value is BLANK or cell.value == ""

    def _exposed_rows(self, option) -> Optional[tuple]:
        """The rows a repaint of part of the table needs, as _range: those
        under the part, every column (a long text runs over its neighbours),
        from the top of any merged cell reaching into them. None for all."""
        exposed = getattr(option, "exposedRect", None)
        if exposed is None or self.sheet is None or exposed.isEmpty():
            return None
        import bisect
        xs, ys = self.edges()
        rows, cols = self.size
        r0 = max(0, bisect.bisect_right(ys, exposed.top()) - 2)
        r1 = min(rows - 1, bisect.bisect_right(ys, exposed.bottom()) + 1)
        if r0 <= 0 and r1 >= rows - 1:
            return None
        r0 = min([r0] + [m[0] for m in self.sheet.merges if m[0] < r0 <= m[2]])
        return (r0, r1, 0, cols - 1)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        frame = self._page_frame()
        printing = bool(getattr(frame, "print_mode", False))
        # on screen, a repaint of part of the table draws only the rows
        # under it (a key typed or a cell picked repaints a few cells)
        self._range = None if printing else self._exposed_rows(option)
        try:
            super().paint(painter, option, widget)
        finally:
            self._range = None
        if self.sheet is not None and (printing or not (self.opened or self.isSelected())):
            # the table's name above its top-left corner (printed); while it
            # is picked or open its tab says it instead
            from . import nametags
            if nametags.shown(self):
                # on the same pixels live as in the page's squares
                from ..ui.markuplayer import align_with_squares
                painter.save()
                align_with_squares(painter, self)
                nametags.draw_tag(painter, QPointF(0, -0.8), self.name, nametags.OUTER_PT,
                                  above=True)
                painter.restore()
        if printing or self.sheet is None:
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
        if self._range is not None:
            places = sheet.positions_in(self._range[0], 0, self._range[1], cols - 1)
        else:
            places = list(sheet.cells)
        for r, c in places:
            cell = sheet.cells.get((r, c))
            if cell is not None and cell.comment and r < rows and c < cols:
                rect = self.cell_rect(r, c)
                path = QPainterPath()
                path.moveTo(rect.topRight())
                path.lineTo(rect.topRight() + QPointF(-4, 0))
                path.lineTo(rect.topRight() + QPointF(0, 4))
                path.closeSubpath()
                painter.fillPath(path, QColor("#d9480f"))
        # cells made global (calc sections): a purple dashed edge round them
        made = (sheet.page or {}).get("global_cells")
        if made:
            from ..ui.calcsections import BAND
            pen = QPen(BAND, 2.2, Qt.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            for t, l, b, r in made:
                if t < rows and l < cols:
                    painter.drawRect(self.block_rect(t, l, min(b, rows - 1), min(r, cols - 1)))
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
        marks = []          # hidden columns and rows: drawn over their neighbours
        for c in range(cols):
            cell = QRectF(xs[c], -HEADING_H, xs[c + 1] - xs[c], HEADING_H)
            if cell.width() <= 0:
                marks.append((cell, "col"))       # Excel's double line
                continue
            on = sel is not None and sel[1] <= c <= sel[3]
            painter.fillRect(cell, HEADING_ON if on else HEADING_BG)
            painter.setPen(grid)
            painter.drawRect(cell)
            painter.setPen(EXCEL_GREEN if on else QColor("#444444"))
            painter.drawText(cell, Qt.AlignCenter, col_letters(c))
        for r in range(rows):
            cell = QRectF(-ROWNUM_W, ys[r], ROWNUM_W, ys[r + 1] - ys[r])
            if cell.height() <= 0:
                marks.append((cell, "row"))
                continue
            on = sel is not None and sel[0] <= r <= sel[2]
            painter.fillRect(cell, HEADING_ON if on else HEADING_BG)
            painter.setPen(grid)
            painter.drawRect(cell)
            painter.setPen(EXCEL_GREEN if on else QColor("#444444"))
            painter.drawText(cell, Qt.AlignCenter, str(r + 1))
        for cell, axis in marks:
            hidden_mark(painter, cell, axis)
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
        if box.width() <= 0 or box.height() <= 0:
            return                      # all hidden: nothing to show (Excel)
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

    def restore_in_place(self, data: dict) -> bool:
        """Undo or redo: become the recorded table without being rebuilt,
        when it is this same table with only its cells, sizes or rules
        different (PageFrame.load_items). False when it must be rebuilt."""
        sheet = self.sheet
        table = data.get("table") or {}
        if sheet is None or data.get("type") != self.TYPE or table.get("new") \
                or "names" not in table:
            return False
        current = self.serialize()
        now = current.get("table") or {}
        if any(data.get(k) != v for k, v in current.items() if k != "table") or \
                any(k not in current for k in data):
            return False                   # moved, turned, restyled...: rebuilt
        if any(table.get(k) != now.get(k) for k in ("name", "kind", "names")):
            return False
        if table == now:
            return True
        from ..sheet.store import restore_sheet
        laid_out = restore_sheet(sheet, table, now)
        self._restored(laid_out)
        return True

    def _restored(self, laid_out: bool) -> None:
        """After restore_in_place: drawn again, and the open table's formula
        bar and selection shown afresh (as a rebuilt one is)."""
        if laid_out:
            self.layout_changed()
        self.update()
        scene = self.scene()
        for view in (scene.views() if scene is not None else ()):
            tables = getattr(view, "tables", None)
            if tables is not None and tables._item is self:
                tables._show_selection()

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


def hidden_mark(painter: QPainter, cell: QRectF, axis: str) -> None:
    """Excel's double line in the headings where a column (row) is hidden."""
    pen = QPen(QColor("#7a7a7a"), 0)
    pen.setCosmetic(True)
    painter.save()
    painter.setPen(pen)
    for d in (-0.9, 0.9):
        if axis == "col":
            x = cell.left() + d
            painter.drawLine(QPointF(x, cell.top()), QPointF(x, cell.bottom()))
        else:
            y = cell.top() + d
            painter.drawLine(QPointF(cell.left(), y), QPointF(cell.right(), y))
    painter.restore()


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


class _BorderLines:
    """Cell borders drawn in order, each run of solid lines with the same
    pen as one drawLines call (a table with every cell bordered drew
    thousands of lines one call at a time). Dashed, dotted and double lines
    are drawn one by one, as before: their dash patterns start afresh on
    each line."""

    __slots__ = ("painter", "pen", "lines")

    def __init__(self, painter):
        self.painter = painter
        self.pen = None
        self.lines = []

    def add(self, border: Border, a: QPointF, b: QPointF, side: str) -> None:
        if border.style in ("dashed", "dotted", "double"):
            self.flush()
            _draw_border(self.painter, border, a, b, side)
            return
        pen = border_pen(border)
        if pen is not self.pen:
            self.flush()
            self.pen = pen
        self.lines.append(QLineF(a, b))

    def flush(self) -> None:
        if self.lines:
            self.painter.setPen(self.pen)
            self.painter.drawLines(self.lines)
            self.lines = []
        self.pen = None


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
