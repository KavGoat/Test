"""Status stamps — APPROVED, FOR CONSTRUCTION, etc."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QBrush

from .base import PageItem
from ..core.document import Region
from ..core.typography import sans_family


STAMP_TEXTS = [
    "APPROVED",
    "FOR CONSTRUCTION",
    "AS BUILT",
    "PRELIMINARY",
    "DRAFT",
    "REVIEWED",
    "SUPERSEDED",
    "NOT FOR CONSTRUCTION",
    "VOID",
]


class StampItem(PageItem):
    """A status stamp annotation."""

    def __init__(self, region: Region, parent=None):
        super().__init__(region, parent)
        self.stamp_text = region.data.get("stamp_text", "APPROVED")
        self.stamp_color = QColor(region.data.get("stamp_color", "#cc0000"))
        self.rotation = region.data.get("rotation", -15)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.save()
        center = self.rect().center()
        painter.translate(center)
        painter.rotate(self.rotation)
        r = QRectF(-self.rect().width() / 2, -self.rect().height() / 2,
                    self.rect().width(), self.rect().height())
        pen = QPen(self.stamp_color, 3.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(r.adjusted(4, 4, -4, -4), 6, 6)
        font = QFont(sans_family(), 20)
        font.setPixelSize(20)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(r, Qt.AlignmentFlag.AlignCenter, self.stamp_text)
        painter.restore()
        self.paint_selection(painter)
