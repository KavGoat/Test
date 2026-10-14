"""Text region — rich text annotations and labels."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QTextDocument

from .base import PageItem
from ..core.document import Region
from ..core.typography import sans_family


class TextItem(PageItem):
    """A text annotation on the page."""

    def __init__(self, region: Region, parent=None):
        super().__init__(region, parent)
        self.text = region.data.get("text", "")
        self.font_size = region.data.get("font_size", 10.0)
        self.bold = region.data.get("bold", False)
        self.italic = region.data.get("italic", False)
        self.color = QColor(region.data.get("color", "#000000"))
        self.bg_color = QColor(region.data.get("bg_color", "#ffffff"))
        self.bg_color.setAlpha(0)
        self.editing = False
        self._doc = QTextDocument()
        self._doc.setPlainText(self.text)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.bg_color.alpha() > 0:
            painter.fillRect(self.rect(), self.bg_color)
        font = QFont(sans_family(), int(self.font_size))
        font.setPixelSize(int(self.font_size))
        font.setBold(self.bold)
        font.setItalic(self.italic)
        painter.setFont(font)
        painter.setPen(QPen(self.color))
        painter.drawText(
            self.rect().adjusted(4, 2, -4, -2),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
            self.text,
        )
        if self.editing:
            painter.setPen(QPen(QColor(0, 120, 215), 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.rect().adjusted(-1, -1, 1, 1))
        self.paint_selection(painter)

    def set_text(self, text: str):
        self.text = text
        self.region.data["text"] = text
        self._doc.setPlainText(text)
        self.update()

    def start_edit(self):
        self.editing = True
        self.update()

    def end_edit(self):
        self.editing = False
        self.region.data["text"] = self.text
        self.update()
