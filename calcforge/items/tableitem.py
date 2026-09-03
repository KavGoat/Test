"""A spreadsheet placed on the page, sharing the document's variables."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetricsF, QPainter,
                           QPen, QPolygonF)

from ..core.spreadsheet import (Cell, CellError, CellFormat, Sheet, column_letter,
                                make_ref, parse_ref)
from ..core.units import Quantity
from .base import MarkupItem, Style, register_item

GUTTER_W = 24.0
GUTTER_H = 15.0
BORDER_GRAB = 3.0
NAME_TAG = "#2f7d4f"        # the green a published cell is tagged with


@register_item
class TableItem(MarkupItem):
    """Grid of cells with Excel-style formulas and unit-aware values."""

    TYPE = "table"
    NAME = "Table"
    ROTATABLE = False

    def __init__(self, rows: int = 6, cols: int = 4):
        super().__init__()
        self.sheet = Sheet(rows, cols)
        self.title = ""
        # A name the document can look values up in: bolts(d, A, B).
        self.table_name = ""
        self.show_chrome = False          # A/B/C and 1/2/3 gutters while editing
        self.publish_headers = False
        self.named_cells: dict[str, str] = {}
        # Write the variable name on any cell the document can read.
        self.show_names = True
        self.current: tuple[int, int] = (0, 0)
        self.anchor: tuple[int, int] = (0, 0)
        # The cell a half-written formula is pointing at, outlined while the
        # arrows or the pointer are choosing it.
        self.pointing: Optional[tuple[int, int]] = None
        self.style = Style(stroke="#adb5bd", fill="#ffffff", fill_opacity=1.0,
                           width=0.6, font_size=8.5, text_color="#111318", padding=3.0)
        self.header_fill = "#e9ecef"
        self.band_fill = "#f6f8fa"
        self.layer = "Calculations"

    # -- identity ----------------------------------------------------------
    def display_name(self) -> str:
        return self.label or (f"Table · {self.title}" if self.title else "Table")

    def summary(self) -> str:
        return self.comment or self.title or f"{self.sheet.rows}×{self.sheet.cols} cells"

    # -- geometry ----------------------------------------------------------
    def title_height(self) -> float:
        """Room above the grid for the title and the name it is read by."""
        if not self.title and not self.table_name:
            return 0.0
        return self.style.font_size + 8.0

    def gutter_size(self) -> tuple[float, float]:
        return (GUTTER_W, GUTTER_H) if self.show_chrome else (0.0, 0.0)

    def set_chrome(self, on: bool) -> None:
        """Show or hide the A/B/C and 1/2/3 gutters.

        The gutters are drawn above and to the left of the grid, so the item has
        to grow outwards rather than push its own cells down and right —
        otherwise activating a table would move every cell out from under the
        pointer that just double-clicked one.
        """
        on = bool(on)
        if on == self.show_chrome:
            return
        self.prepareGeometryChange()
        self.show_chrome = on
        shift = QPointF(-GUTTER_W, -GUTTER_H) if on else QPointF(GUTTER_W, GUTTER_H)
        self.setPos(self.pos() + shift)
        self.update()

    def grid_origin(self) -> QPointF:
        gw, gh = self.gutter_size()
        return QPointF(gw, gh + self.title_height())

    def local_rect(self) -> QRectF:
        gw, gh = self.gutter_size()
        return QRectF(0, 0,
                      gw + self.sheet.total_width(),
                      gh + self.title_height() + self.sheet.total_height())

    def set_local_rect(self, rect: QRectF) -> None:
        """Resizing the frame scales all column widths and row heights."""
        gw, gh = self.gutter_size()
        target_w = max(rect.width() - gw, 40.0)
        target_h = max(rect.height() - gh - self.title_height(), 20.0)
        current_w = self.sheet.total_width()
        current_h = self.sheet.total_height()
        if current_w > 0:
            factor = target_w / current_w
            for col in range(self.sheet.cols):
                self.sheet.col_widths[col] = max(self.sheet.col_width(col) * factor, 14.0)
        if current_h > 0:
            factor = target_h / current_h
            for row in range(self.sheet.rows):
                self.sheet.row_heights[row] = max(self.sheet.row_height(row) * factor, 10.0)
        self.prepareGeometryChange()
        self.update()

    def column_x(self, col: int) -> float:
        x = self.grid_origin().x()
        for index in range(col):
            x += self.sheet.col_width(index)
        return x

    def row_y(self, row: int) -> float:
        y = self.grid_origin().y()
        for index in range(row):
            y += self.sheet.row_height(index)
        return y

    def cell_rect(self, row: int, col: int) -> QRectF:
        return QRectF(self.column_x(col), self.row_y(row),
                      self.sheet.col_width(col), self.sheet.row_height(row))

    def range_rect(self, a: tuple[int, int], b: tuple[int, int]) -> QRectF:
        return self.cell_rect(min(a[0], b[0]), min(a[1], b[1])).united(
            self.cell_rect(max(a[0], b[0]), max(a[1], b[1])))

    def cell_at(self, point: QPointF) -> Optional[tuple[int, int]]:
        origin = self.grid_origin()
        if point.x() < origin.x() or point.y() < origin.y():
            return None
        x = origin.x()
        col = None
        for index in range(self.sheet.cols):
            width = self.sheet.col_width(index)
            if x <= point.x() < x + width:
                col = index
                break
            x += width
        y = origin.y()
        row = None
        for index in range(self.sheet.rows):
            height = self.sheet.row_height(index)
            if y <= point.y() < y + height:
                row = index
                break
            y += height
        if row is None or col is None:
            return None
        return row, col

    def border_at(self, point: QPointF) -> Optional[tuple[str, int]]:
        """Detect a column/row divider under the cursor, for resizing."""
        if not self.show_chrome:
            return None
        gw, gh = self.gutter_size()
        origin = self.grid_origin()
        if point.y() <= origin.y() and point.y() >= origin.y() - gh - 1:
            x = origin.x()
            for index in range(self.sheet.cols):
                x += self.sheet.col_width(index)
                if abs(point.x() - x) <= BORDER_GRAB:
                    return "col", index
        if point.x() <= origin.x() and point.x() >= 0:
            y = origin.y()
            for index in range(self.sheet.rows):
                y += self.sheet.row_height(index)
                if abs(point.y() - y) <= BORDER_GRAB:
                    return "row", index
        return None

    def gutter_at(self, point: QPointF) -> Optional[tuple[str, int]]:
        """Detect a click on a column letter or row number."""
        if not self.show_chrome:
            return None
        origin = self.grid_origin()
        if point.y() < origin.y() and point.x() >= origin.x():
            found = self.cell_at(QPointF(point.x(), origin.y() + 1))
            return ("col", found[1]) if found else None
        if point.x() < origin.x() and point.y() >= origin.y():
            found = self.cell_at(QPointF(origin.x() + 1, point.y()))
            return ("row", found[0]) if found else None
        return None

    # -- selection ---------------------------------------------------------
    def selection(self) -> tuple[int, int, int, int]:
        r0, c0 = self.current
        r1, c1 = self.anchor
        return min(r0, r1), min(c0, c1), max(r0, r1), max(c0, c1)

    def selected_cells(self) -> list[tuple[int, int]]:
        r0, c0, r1, c1 = self.selection()
        return [(r, c) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)]

    def move_current(self, drow: int, dcol: int, extend: bool = False) -> None:
        row = max(0, min(self.current[0] + drow, self.sheet.rows - 1))
        col = max(0, min(self.current[1] + dcol, self.sheet.cols - 1))
        self.current = (row, col)
        if not extend:
            self.anchor = self.current
        self.update()

    def current_ref(self) -> str:
        r0, c0, r1, c1 = self.selection()
        if (r0, c0) == (r1, c1):
            return make_ref(*self.current)
        return f"{make_ref(r0, c0)}:{make_ref(r1, c1)}"

    # -- data --------------------------------------------------------------
    def set_cell(self, row: int, col: int, raw: str) -> None:
        self.sheet.set_raw(row, col, raw)
        self.touch()
        self.contentChanged.emit()

    def cell_format(self, row: int, col: int) -> CellFormat:
        return self.sheet.cells.setdefault((row, col), Cell()).fmt

    def apply_format(self, cells: list[tuple[int, int]], **changes) -> None:
        for row, col in cells:
            fmt = self.cell_format(row, col)
            for key, value in changes.items():
                if hasattr(fmt, key):
                    setattr(fmt, key, value)
        self.update()

    def autofit_column(self, col: int) -> None:
        font = self.style.font()
        metrics = QFontMetricsF(font)
        header_font = QFont(font)
        header_font.setBold(True)
        header_metrics = QFontMetricsF(header_font)
        widest = 30.0
        for row in range(self.sheet.rows):
            text = self.sheet.display_text(row, col)
            if not text:
                continue
            chooser = header_metrics if (row == 0 and self.sheet.header_row) else metrics
            widest = max(widest, chooser.horizontalAdvance(text) + 10)
        self.sheet.col_widths[col] = min(widest, 320.0)
        self.prepareGeometryChange()
        self.update()

    # -- workspace ---------------------------------------------------------
    def refresh(self, workspace=None, page=None) -> None:
        if workspace is None:
            scene = self.scene()
            workspace = getattr(scene, "workspace", None) if scene is not None else None
        if workspace is None:
            return
        self.sheet.recalculate(workspace)
        self.publish(workspace)
        self.prepareGeometryChange()
        self.update()

    def declared_names(self) -> set[str]:
        """Variable names this table publishes."""
        names = set(self.named_cells)
        if self.table_name:
            names.add(self.table_name)
        if self.publish_headers:
            for col in range(self.sheet.cols):
                header = self.sheet.header_name(col)
                if header:
                    names.add(header)
        return names

    def name_for(self, row: int, col: int) -> str:
        """The variable a cell publishes, if any."""
        ref = f"{column_letter(col)}{row + 1}"
        for name, target in self.named_cells.items():
            if target.upper() == ref:
                return name
        return ""

    def set_cell_name(self, name: str, row: int, col: int) -> None:
        """Publish this cell as `name` — or, with an empty name, stop."""
        ref = f"{column_letter(col)}{row + 1}"
        for existing in [n for n, t in self.named_cells.items() if t.upper() == ref]:
            del self.named_cells[existing]
        if name:
            self.named_cells[name] = ref

    def publish(self, workspace) -> None:
        """Expose named cells (and optionally whole columns) as variables."""
        source = self.display_name()
        if self.table_name:
            from ..core.spreadsheet import LookupTable
            workspace.define_table(self.table_name,
                                   LookupTable(self.table_name, self.sheet, source))
        for name, ref in self.named_cells.items():
            value = self._value_for_ref(ref)
            if value is not None:
                workspace.define(name, value, source, ref)
        if self.publish_headers:
            for col in range(self.sheet.cols):
                name = self.sheet.header_name(col)
                if not name or name in self.named_cells:
                    continue
                values = self.sheet.column_values(col)
                if values:
                    workspace.define(name, values, source, f"column {column_letter(col)}")

    def _value_for_ref(self, ref: str):
        if ":" in ref:
            start, end = ref.split(":", 1)
            a, b = parse_ref(start), parse_ref(end)
            if not a or not b:
                return None
            values = []
            for row in range(min(a[0], b[0]), max(a[0], b[0]) + 1):
                for col in range(min(a[1], b[1]), max(a[1], b[1]) + 1):
                    value = self.sheet.value(row, col)
                    if value is not None and not isinstance(value, CellError):
                        values.append(value)
            return values or None
        position = parse_ref(ref)
        if not position:
            return None
        value = self.sheet.value(*position)
        return None if isinstance(value, CellError) else value

    # -- painting ----------------------------------------------------------
    def _paint_pointing(self, painter: QPainter) -> None:
        """Outline the cell a half-written formula is referring to."""
        row, col = self.pointing
        if not (0 <= row < self.sheet.rows and 0 <= col < self.sheet.cols):
            return
        painter.save()
        pen = QPen(QColor("#1971c2"))
        pen.setWidthF(1.4)
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(QColor(25, 113, 194, 28))
        painter.drawRect(self.cell_rect(row, col))
        painter.restore()

    def paint_content(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        rect = self.local_rect()
        origin = self.grid_origin()
        grid_rect = QRectF(origin.x(), origin.y(),
                           self.sheet.total_width(), self.sheet.total_height())

        painter.fillRect(grid_rect, QColor(self.style.fill or "#ffffff"))
        if self.title or self.table_name:
            self._paint_title(painter, rect)
        if self.show_chrome:
            self._paint_chrome(painter, origin)
        self._paint_backgrounds(painter)
        self._paint_grid(painter, grid_rect)
        self._paint_text(painter)
        if self.show_names:
            self._paint_names(painter)
        if self.show_chrome:
            self._paint_selection(painter)
        if self.pointing is not None:
            self._paint_pointing(painter)

    def _paint_title(self, painter: QPainter, rect: QRectF) -> None:
        """The title on the left, and the name it is looked up by on the right.

        A named table is read by that name from a calculation, so the name has
        to be visible on the table itself — otherwise the only way to find out
        what a sheet is called is to open its menu.
        """
        gw, gh = self.gutter_size()
        box = QRectF(gw, gh, rect.width() - gw, self.title_height())
        font = self.style.font()
        font.setBold(True)
        font.setPointSizeF(self.style.font_size * 1.1)
        painter.setFont(font)
        painter.setPen(QPen(QColor(self.style.text_color)))
        painter.drawText(box.adjusted(2, 0, -2, 0), Qt.AlignVCenter | Qt.AlignLeft,
                         self.title)
        if self.table_name:
            tag = self.style.font()
            tag.setPointSizeF(max(self.style.font_size * 0.95, 5.0))
            tag.setItalic(True)
            painter.setFont(tag)
            painter.setPen(QPen(QColor(NAME_TAG)))
            painter.drawText(box.adjusted(2, 0, -3, 0),
                             Qt.AlignVCenter | Qt.AlignRight,
                             f"{self.table_name}( )")

    def _paint_chrome(self, painter: QPainter, origin: QPointF) -> None:
        gw, gh = GUTTER_W, GUTTER_H
        from ..core.typography import set_size
        painter.setFont(set_size(self.style.font(), max(self.style.font_size * 0.85, 5.5)))
        header_brush = QBrush(QColor("#dee2e6"))
        pen = QPen(QColor("#adb5bd"), 0.5)
        r0, c0, r1, c1 = self.selection()
        for col in range(self.sheet.cols):
            box = QRectF(self.column_x(col), origin.y() - gh, self.sheet.col_width(col), gh)
            painter.fillRect(box, QBrush(QColor("#c3d4ea")) if c0 <= col <= c1 else header_brush)
            painter.setPen(pen)
            painter.drawRect(box)
            painter.setPen(QPen(QColor("#495057")))
            painter.drawText(box, Qt.AlignCenter, column_letter(col))
        for row in range(self.sheet.rows):
            box = QRectF(origin.x() - gw, self.row_y(row), gw, self.sheet.row_height(row))
            painter.fillRect(box, QBrush(QColor("#c3d4ea")) if r0 <= row <= r1 else header_brush)
            painter.setPen(pen)
            painter.drawRect(box)
            painter.setPen(QPen(QColor("#495057")))
            painter.drawText(box, Qt.AlignCenter, str(row + 1))
        corner = QRectF(origin.x() - gw, origin.y() - gh, gw, gh)
        painter.fillRect(corner, header_brush)
        painter.setPen(pen)
        painter.drawRect(corner)

    def _paint_names(self, painter: QPainter) -> None:
        """Tag every published cell with the name the document reads it by.

        Without this a table looks like any other grid, and there is no way to
        tell that D2 is the q_floor every calculation below is using.
        """
        from ..core.typography import set_size
        painter.save()
        painter.setFont(set_size(self.style.font(), max(self.style.font_size * 0.72, 4.5)))
        metrics = painter.fontMetrics()
        for name, ref in sorted(self.named_cells.items()):
            position = parse_ref(ref.split(":", 1)[0])
            if position is None:
                continue
            row, col = position
            if row >= self.sheet.rows or col >= self.sheet.cols:
                continue
            box = self.cell_rect(row, col)
            # A folded corner marks the cell; the tag sits above it.
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(NAME_TAG)))
            corner = QPolygonF([box.topRight() + QPointF(-5.0, 0.0),
                                box.topRight(),
                                box.topRight() + QPointF(0.0, 5.0)])
            painter.drawPolygon(corner)

            # The tag lives inside its own cell. Hanging it above the cell put
            # it over whatever was in the row before, which is worse than not
            # labelling it at all.
            width, height = self._tag_size(painter, name)
            width = min(width, box.width() - 2.0)
            height = min(height, box.height() - 2.0)
            tag = QRectF(box.left() + 1.0, box.top() + 1.0, max(width, 6.0),
                         max(height, 5.0))
            painter.setBrush(QBrush(QColor(NAME_TAG)))
            painter.drawRoundedRect(tag, 1.5, 1.5)
            painter.setPen(QPen(QColor("#ffffff")))
            painter.drawText(tag, Qt.AlignCenter, name)
        painter.restore()

    def _paint_backgrounds(self, painter: QPainter) -> None:
        painter.setPen(Qt.NoPen)
        for row in range(self.sheet.rows):
            if row == 0 and self.sheet.header_row:
                painter.fillRect(QRectF(self.column_x(0), self.row_y(0),
                                        self.sheet.total_width(), self.sheet.row_height(0)),
                                 QColor(self.header_fill))
            elif self.sheet.banded and row % 2 == 1:
                painter.fillRect(QRectF(self.column_x(0), self.row_y(row),
                                        self.sheet.total_width(), self.sheet.row_height(row)),
                                 QColor(self.band_fill))
        for (row, col), cell in self.sheet.cells.items():
            if row < self.sheet.rows and col < self.sheet.cols and cell.fmt.background:
                painter.fillRect(self.cell_rect(row, col), QColor(cell.fmt.background))

    def _paint_grid(self, painter: QPainter, grid_rect: QRectF) -> None:
        if self.sheet.grid_lines:
            pen = QPen(QColor(self.style.stroke or "#adb5bd"))
            pen.setWidthF(max(self.style.width, 0.2))
            painter.setPen(pen)
            x = grid_rect.left()
            for col in range(self.sheet.cols + 1):
                painter.drawLine(QPointF(x, grid_rect.top()), QPointF(x, grid_rect.bottom()))
                if col < self.sheet.cols:
                    x += self.sheet.col_width(col)
            y = grid_rect.top()
            for row in range(self.sheet.rows + 1):
                painter.drawLine(QPointF(grid_rect.left(), y), QPointF(grid_rect.right(), y))
                if row < self.sheet.rows:
                    y += self.sheet.row_height(row)
        # explicit per-cell borders drawn heavier
        heavy = QPen(QColor(self.style.text_color))
        heavy.setWidthF(max(self.style.width * 2.0, 0.9))
        painter.setPen(heavy)
        for (row, col), cell in self.sheet.cells.items():
            if row >= self.sheet.rows or col >= self.sheet.cols:
                continue
            fmt = cell.fmt
            box = self.cell_rect(row, col)
            if fmt.border_top:
                painter.drawLine(box.topLeft(), box.topRight())
            if fmt.border_bottom:
                painter.drawLine(box.bottomLeft(), box.bottomRight())
            if fmt.border_left:
                painter.drawLine(box.topLeft(), box.bottomLeft())
            if fmt.border_right:
                painter.drawLine(box.topRight(), box.bottomRight())

    def _paint_text(self, painter: QPainter) -> None:
        base_font = self.style.font()
        pad = self.style.padding
        for row in range(self.sheet.rows):
            for col in range(self.sheet.cols):
                text = self.sheet.display_text(row, col)
                if not text:
                    continue
                cell = self.sheet.cells.get((row, col))
                fmt = cell.fmt if cell else CellFormat()
                font = QFont(base_font)
                if fmt.bold or (row == 0 and self.sheet.header_row):
                    font.setBold(True)
                if fmt.italic:
                    font.setItalic(True)
                painter.setFont(font)
                colour = QColor(fmt.color) if fmt.color else QColor(self.style.text_color)
                if cell is not None and isinstance(cell.value, CellError):
                    colour = QColor("#c92a2a")
                painter.setPen(QPen(colour))
                box = self.cell_rect(row, col).adjusted(pad, 1, -pad, -1)
                # A published cell wears its name in the top-left corner; the
                # value steps aside for it rather than being written over it.
                box.setLeft(box.left() + self._name_inset(painter, row, col))
                painter.setClipRect(box.adjusted(-1, -1, 2, 2))
                _draw_with_scripts(painter, box, self._alignment(row, col, cell),
                                   text, font)
                painter.setClipping(False)

    def _name_inset(self, painter: QPainter, row: int, col: int) -> float:
        """How much room the published-name tag takes on the left of a cell."""
        if not self.show_names:
            return 0.0
        name = self.name_for(row, col)
        if not name:
            return 0.0
        return self._tag_size(painter, name)[0] + 3.0

    def _tag_size(self, painter: QPainter, name: str) -> tuple:
        from ..core.typography import set_size

        font = set_size(self.style.font(), max(self.style.font_size * 0.72, 4.5))
        metrics = QFontMetricsF(font)
        return metrics.horizontalAdvance(name) + 8.0, metrics.height() + 1.0

    def _alignment(self, row: int, col: int, cell) -> Qt.AlignmentFlag:
        fmt = cell.fmt if cell else CellFormat()
        if fmt.align == "left":
            horizontal = Qt.AlignLeft
        elif fmt.align == "center":
            horizontal = Qt.AlignHCenter
        elif fmt.align == "right":
            horizontal = Qt.AlignRight
        elif row == 0 and self.sheet.header_row:
            horizontal = Qt.AlignHCenter
        else:
            value = cell.value if cell else None
            numeric = isinstance(value, (int, float, Quantity)) and not isinstance(value, bool)
            horizontal = Qt.AlignRight if numeric else Qt.AlignLeft
        return horizontal | Qt.AlignVCenter

    def editor_alignment(self, row: int, col: int,
                         text: Optional[str] = None) -> Qt.AlignmentFlag:
        """How the cell editor should line its text up: the way the cell does.

        A number that is written on the right of its cell should be typed on
        the right of it too, rather than starting on the left and jumping
        across the moment Enter is pressed.
        """
        cell = self.sheet.cell(row, col)
        aligned = self._alignment(row, col, cell) & Qt.AlignHorizontal_Mask
        written = self.sheet.raw(row, col) if text is None else text
        if cell is None or cell.value is None:
            # Nothing worked out for this cell yet — go by what is written.
            fmt = cell.fmt if cell else None
            if fmt is None or fmt.align == "auto":
                try:
                    float((written or "").strip())
                except (TypeError, ValueError):
                    return Qt.AlignLeft
                return Qt.AlignRight
        return aligned

    def _paint_selection(self, painter: QPainter) -> None:
        r0, c0, r1, c1 = self.selection()
        box = self.range_rect((r0, c0), (r1, c1))
        painter.setBrush(QBrush(QColor(30, 110, 220, 28)))
        painter.setPen(Qt.NoPen)
        painter.drawRect(box)
        pen = QPen(QColor(21, 92, 200))
        pen.setWidthF(1.4)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(box)
        painter.setPen(QPen(QColor(21, 92, 200), 1.0))
        painter.drawRect(self.cell_rect(*self.current))
        # fill handle
        anchor = self.cell_rect(r1, c1).bottomRight()
        painter.setBrush(QBrush(QColor(21, 92, 200)))
        painter.drawRect(QRectF(anchor.x() - 2.5, anchor.y() - 2.5, 5, 5))

    def fill_handle_rect(self) -> QRectF:
        r0, c0, r1, c1 = self.selection()
        anchor = self.cell_rect(r1, c1).bottomRight()
        return QRectF(anchor.x() - 4, anchor.y() - 4, 8, 8)

    # -- serialisation -----------------------------------------------------
    def serialize(self) -> dict:
        data = self.base_dict()
        if self.show_chrome:
            # Store the position the table has when its gutters are hidden, so a
            # document saved mid-edit reopens with its cells in the same place.
            data["x"] = data["x"] + GUTTER_W
            data["y"] = data["y"] + GUTTER_H
        data.update({
            "sheet": self.sheet.to_dict(),
            "title": self.title,
            "table_name": self.table_name,
            "publish_headers": self.publish_headers,
            "named_cells": dict(self.named_cells),
            "show_names": self.show_names,
            "header_fill": self.header_fill,
            "band_fill": self.band_fill,
        })
        return data

    def deserialize(self, data: dict) -> None:
        self.sheet = Sheet.from_dict(data.get("sheet", {}))
        self.title = data.get("title", "")
        self.table_name = data.get("table_name", "")
        self.publish_headers = bool(data.get("publish_headers", False))
        self.named_cells = dict(data.get("named_cells", {}))
        self.show_names = bool(data.get("show_names", True))
        self.header_fill = data.get("header_fill", "#e9ecef")
        self.band_fill = data.get("band_fill", "#f6f8fa")
        self.load_base(data)


def _draw_with_scripts(painter: QPainter, box: QRectF, alignment, text: str,
                       font: QFont) -> None:
    """Draw *text* in *box*, with ``A_g`` and ``m^2`` set as scripts.

    A cell holds plain text, because that is what a formula reads and what a
    published name is written in. What is drawn is what an engineer means by
    it: the run after an underscore dropped, the run after a caret lifted,
    both a size smaller.
    """
    from ..core.typography import script_runs

    runs = script_runs(text)
    if not any(level for _run, level in runs):
        painter.drawText(box, alignment, text)
        return

    small = QFont(font)
    small.setPointSizeF(max(font.pointSizeF() * 0.68, 4.5))
    metrics = QFontMetricsF(font)
    small_metrics = QFontMetricsF(small)
    drop = metrics.xHeight() * 0.34
    lift = metrics.ascent() * 0.42

    widths = [(QFontMetricsF(small if level else font).horizontalAdvance(run))
              for run, level in runs]
    total = sum(widths)
    if alignment & Qt.AlignRight:
        x = box.right() - total
    elif alignment & Qt.AlignHCenter:
        x = box.center().x() - total / 2
    else:
        x = box.left()
    baseline = box.center().y() + metrics.ascent() / 2 - metrics.descent() / 2

    for (run, level), width in zip(runs, widths):
        if level == "sub":
            painter.setFont(small)
            painter.drawText(QPointF(x, baseline + drop), run)
        elif level == "super":
            painter.setFont(small)
            painter.drawText(QPointF(x, baseline - lift), run)
        else:
            painter.setFont(font)
            painter.drawText(QPointF(x, baseline), run)
        x += width
    painter.setFont(font)
