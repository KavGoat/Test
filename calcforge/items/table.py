"""Table region — embedded spreadsheet on the page."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QBrush

from .base import PageItem
from ..core.document import Region
from ..core.spreadsheet import Table, SpreadsheetEvaluator, _col_letter
from ..core.evaluator import EvalContext
from ..core.typography import sans_family


class TableItem(PageItem):
    """A spreadsheet table region on the page."""

    def __init__(self, region: Region, parent=None):
        super().__init__(region, parent)
        table_data = region.data.get("table")
        if table_data:
            self.table = Table.from_dict(table_data)
        else:
            self.table = Table(rows=5, cols=4)
        self.editing = False
        self.edit_row = -1
        self.edit_col = -1
        self.selected_cells: set[tuple[int, int]] = set()
        self._header_height = 22.0
        self._update_size()

    def _update_size(self):
        w = sum(self.table.col_widths[:self.table.cols]) + 40
        h = self._header_height + sum(self.table.row_heights[:self.table.rows])
        self.region.width = w
        self.region.height = h
        self.setRect(QRectF(0, 0, w, h))

    def evaluate(self, ctx: EvalContext):
        evaluator = SpreadsheetEvaluator(self.table, ctx)
        evaluator.evaluate_all()
        if self.table.publish_columns:
            for (r, c), cell in self.table.cells.items():
                if cell.name and cell.value is not None:
                    from ..core.units import Quantity
                    if isinstance(cell.value, Quantity):
                        ctx.define(cell.name, cell.value)
                    else:
                        ctx.define(cell.name, Quantity(float(cell.value)))

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        painter.setPen(QPen(QColor(180, 180, 180), 0.5))
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.drawRect(r)

        hdr_font = QFont(sans_family(), 9)
        hdr_font.setPixelSize(9)
        hdr_font.setBold(True)
        cell_font = QFont(sans_family(), 10)
        cell_font.setPixelSize(10)
        row_num_w = 40.0
        x = row_num_w
        painter.setFont(hdr_font)
        painter.setPen(QPen(QColor(100, 100, 100)))
        for c in range(self.table.cols):
            cw = self.table.col_widths[c]
            cr = QRectF(x, 0, cw, self._header_height)
            painter.fillRect(cr, QColor(240, 240, 240))
            painter.setPen(QPen(QColor(180, 180, 180), 0.5))
            painter.drawRect(cr)
            painter.setPen(QPen(QColor(80, 80, 80)))
            painter.drawText(cr, Qt.AlignmentFlag.AlignCenter, _col_letter(c))
            x += cw

        y = self._header_height
        for row in range(self.table.rows):
            rh = self.table.row_heights[row]
            rr = QRectF(0, y, row_num_w, rh)
            painter.fillRect(rr, QColor(240, 240, 240))
            painter.setPen(QPen(QColor(180, 180, 180), 0.5))
            painter.drawRect(rr)
            painter.setPen(QPen(QColor(80, 80, 80)))
            painter.setFont(hdr_font)
            painter.drawText(rr, Qt.AlignmentFlag.AlignCenter, str(row + 1))

            x = row_num_w
            for col in range(self.table.cols):
                cw = self.table.col_widths[col]
                cell_rect = QRectF(x, y, cw, rh)
                if (row, col) in self.selected_cells:
                    painter.fillRect(cell_rect, QColor(0, 120, 215, 30))
                painter.setPen(QPen(QColor(220, 220, 220), 0.5))
                painter.drawRect(cell_rect)
                cell = self.table.get_cell(row, col)
                if cell.display:
                    painter.setFont(cell_font)
                    if cell.error:
                        painter.setPen(QPen(QColor(200, 0, 0)))
                    else:
                        painter.setPen(QPen(QColor(0, 0, 0)))
                    painter.drawText(
                        cell_rect.adjusted(4, 1, -2, -1),
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                        cell.display,
                    )
                x += cw
            y += rh

        if self.editing and self.edit_row >= 0 and self.edit_col >= 0:
            ex = row_num_w + sum(self.table.col_widths[:self.edit_col])
            ey = self._header_height + sum(self.table.row_heights[:self.edit_row])
            ew = self.table.col_widths[self.edit_col]
            eh = self.table.row_heights[self.edit_row]
            painter.setPen(QPen(QColor(0, 120, 215), 2.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(ex, ey, ew, eh))

        self.paint_selection(painter)

    def cell_at_pos(self, local_pos) -> tuple[int, int]:
        row_num_w = 40.0
        x = local_pos.x() - row_num_w
        y = local_pos.y() - self._header_height
        if x < 0 or y < 0:
            return -1, -1
        col = -1
        cx = 0
        for c in range(self.table.cols):
            if cx <= x < cx + self.table.col_widths[c]:
                col = c
                break
            cx += self.table.col_widths[c]
        row = -1
        ry = 0
        for r in range(self.table.rows):
            if ry <= y < ry + self.table.row_heights[r]:
                row = r
                break
            ry += self.table.row_heights[r]
        return row, col

    def save_data(self):
        self.region.data["table"] = self.table.to_dict()
