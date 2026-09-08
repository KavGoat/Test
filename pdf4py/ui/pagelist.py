"""The page strip down the side, in the spirit of PDF4QT's Page Master.

Thumbnails are rendered lazily. A two hundred page drawing set costs a second a
sheet to draw, so rendering the lot up front would leave the window dead for
minutes; instead every page starts as a blank sheet of the right shape and the
ones actually on screen are filled in a few at a time while the app stays live.
"""
from __future__ import annotations

import time

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem

from ..document import PdfDocument
from .images import to_pixmap

THUMBNAIL_EDGE = 132

# How long to spend drawing thumbnails before handing the window back, and how
# long to leave it alone before the next pass. A budget rather than a count:
# one sheet of a drawing set can cost as much as fifty pages of a report.
BATCH_BUDGET_S = 0.05
BATCH_PAUSE_MS = 10

STYLE = """
QListWidget { background: #f2f3f5; border: none; }
QListWidget::item { border: 1px solid transparent; border-radius: 3px; padding: 3px; }
QListWidget::item:selected { background: #dce9fb; border-color: #1a73e8; color: #10233d; }
QListWidget::item:hover:!selected { background: #e6e8ec; }
"""

PAGE_EDGE = QColor("#9aa0a6")
PLACEHOLDER_FILL = QColor("#ffffff")
BROKEN_FILL = QColor("#e8e2e2")


def framed(pixmap: QPixmap) -> QPixmap:
    """A page thumbnail is white on white without an edge drawn round it."""
    painter = QPainter(pixmap)
    painter.setPen(QPen(PAGE_EDGE, 1))
    painter.drawRect(0, 0, pixmap.width() - 1, pixmap.height() - 1)
    painter.end()
    return pixmap


def blank(width: float, height: float, fill: QColor = PLACEHOLDER_FILL) -> QPixmap:
    """An empty sheet of the page's shape, to stand in until it is drawn."""
    scale = THUMBNAIL_EDGE / max(width, height, 1.0)
    pixmap = QPixmap(max(int(width * scale), 1), max(int(height * scale), 1))
    pixmap.fill(fill)
    return framed(pixmap)


class PageList(QListWidget):
    """One thumbnail per page; picking one shows it on the canvas."""

    page_chosen = Signal(int)

    def __init__(self, document: PdfDocument, parent=None):
        super().__init__(parent)
        self.document = document
        self._drawn: set[int] = set()
        self.setViewMode(QListWidget.IconMode)
        self.setIconSize(QSize(THUMBNAIL_EDGE, THUMBNAIL_EDGE))
        self.setGridSize(QSize(THUMBNAIL_EDGE + 22, THUMBNAIL_EDGE + 28))
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSpacing(4)
        self.setUniformItemSizes(True)
        self.setStyleSheet(STYLE)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.currentRowChanged.connect(self._chosen)

        self._painter = QTimer(self)
        self._painter.setSingleShot(True)
        self._painter.setInterval(BATCH_PAUSE_MS)
        self._painter.timeout.connect(self._draw_a_few)
        self.verticalScrollBar().valueChanged.connect(lambda _: self._painter.start())

    # ------------------------------------------------------------- filling in

    def reload(self, current: int = 0) -> None:
        """Rebuild the strip, with every page a blank sheet for now."""
        blocked = self.blockSignals(True)
        self.clear()
        self._drawn.clear()
        for index in range(self.document.page_count):
            self.addItem(self._placeholder(index))
        self.blockSignals(blocked)
        if self.count():
            self.setCurrentRow(min(max(current, 0), self.count() - 1))
        self._painter.start()

    def insert_row(self, index: int) -> None:
        """Add one page to the strip without redrawing the other 199."""
        self.blockSignals(True)
        self.insertItem(index, self._placeholder(index))
        self._drawn = {row + 1 if row >= index else row for row in self._drawn}
        self._renumber()
        self.blockSignals(False)
        self._painter.start()

    def remove_row(self, index: int) -> None:
        self.blockSignals(True)
        self.takeItem(index)
        self._drawn = {row - 1 if row > index else row
                       for row in self._drawn if row != index}
        self._renumber()
        self.blockSignals(False)
        self._painter.start()

    def refresh_thumbnail(self, index: int) -> None:
        """The page changed, so its thumbnail is stale."""
        self._drawn.discard(index)
        self._painter.start()

    def showEvent(self, event):
        super().showEvent(event)
        self._painter.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._painter.start()

    # ------------------------------------------------------------------ inside

    def _placeholder(self, index: int) -> QListWidgetItem:
        width, height = self.document.page_size(index)
        item = QListWidgetItem(str(index + 1))
        item.setIcon(blank(width, height))
        item.setTextAlignment(Qt.AlignHCenter | Qt.AlignBottom)
        return item

    def _renumber(self) -> None:
        for row in range(self.count()):
            self.item(row).setText(str(row + 1))

    def _visible_rows(self) -> list[int]:
        """The rows on screen, plus a little either side to scroll into."""
        if not self.count():
            return []
        first = self.indexAt(self.viewport().rect().topLeft()).row()
        last = self.indexAt(self.viewport().rect().bottomLeft()).row()
        if first < 0:
            first = 0
        if last < 0:
            last = min(self.count() - 1, first + 12)
        return list(range(max(first - 2, 0), min(last + 3, self.count())))

    def _draw_a_few(self) -> None:
        deadline = time.monotonic() + BATCH_BUDGET_S
        for row in self._visible_rows():
            if row in self._drawn:
                continue
            self._draw(row)             # always at least one, however slow
            if time.monotonic() >= deadline:
                self._painter.start()   # come back for the rest
                return

    def _draw(self, row: int) -> None:
        self._drawn.add(row)
        item = self.item(row)
        if item is None:
            return
        raster = self.document.render_thumbnail(row, THUMBNAIL_EDGE)
        if raster is None:                      # a page MuPDF cannot draw
            width, height = self.document.page_size(row)
            item.setIcon(blank(width, height, BROKEN_FILL))
            return
        item.setIcon(framed(to_pixmap(raster)))

    def _chosen(self, row: int) -> None:
        if row >= 0:
            self.page_chosen.emit(row)
