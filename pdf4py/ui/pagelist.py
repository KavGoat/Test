"""The page strip down the side, in the spirit of PDF4QT's Page Master."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem

from ..document import PdfDocument
from .images import to_pixmap

THUMBNAIL_EDGE = 132

STYLE = """
QListWidget { background: #f2f3f5; border: none; }
QListWidget::item { border: 1px solid transparent; border-radius: 3px; padding: 3px; }
QListWidget::item:selected { background: #dce9fb; border-color: #1a73e8; color: #10233d; }
QListWidget::item:hover:!selected { background: #e6e8ec; }
"""


def framed(pixmap: QPixmap) -> QPixmap:
    """A page thumbnail is white on white without an edge drawn round it."""
    painter = QPainter(pixmap)
    painter.setPen(QPen(QColor("#9aa0a6"), 1))
    painter.drawRect(0, 0, pixmap.width() - 1, pixmap.height() - 1)
    painter.end()
    return pixmap


class PageList(QListWidget):
    """One thumbnail per page; picking one shows it on the canvas."""

    page_chosen = Signal(int)

    def __init__(self, document: PdfDocument, parent=None):
        super().__init__(parent)
        self.document = document
        self.setViewMode(QListWidget.IconMode)
        self.setIconSize(QSize(THUMBNAIL_EDGE, THUMBNAIL_EDGE))
        self.setGridSize(QSize(THUMBNAIL_EDGE + 22, THUMBNAIL_EDGE + 28))
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSpacing(4)
        self.setUniformItemSizes(True)
        self.setStyleSheet(STYLE)
        self.currentRowChanged.connect(self._chosen)

    def reload(self, current: int = 0) -> None:
        """Rebuild every thumbnail — cheap enough for the sizes this app opens."""
        blocked = self.blockSignals(True)
        self.clear()
        for index in range(self.document.page_count):
            item = QListWidgetItem(f"{index + 1}")
            item.setIcon(self._thumbnail(index))
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignBottom)
            self.addItem(item)
        self.blockSignals(blocked)
        if self.count():
            self.setCurrentRow(min(max(current, 0), self.count() - 1))

    def refresh_thumbnail(self, index: int) -> None:
        item = self.item(index)
        if item is not None:
            item.setIcon(self._thumbnail(index))

    def _thumbnail(self, index: int) -> QPixmap:
        return framed(to_pixmap(self.document.render_thumbnail(index, THUMBNAIL_EDGE)))

    def _chosen(self, row: int) -> None:
        if row >= 0:
            self.page_chosen.emit(row)
