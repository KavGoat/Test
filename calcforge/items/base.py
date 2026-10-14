"""Base class for all page items (regions)."""
from __future__ import annotations

from typing import Optional
from PySide6.QtCore import QRectF, QPointF, Qt
from PySide6.QtGui import QPainter, QPen, QColor, QBrush
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QStyleOptionGraphicsItem, QWidget

from ..core.document import Region


class PageItem(QGraphicsRectItem):
    """Base graphics item for anything on a page."""

    HANDLE_SIZE = 6.0

    def __init__(self, region: Region, parent=None):
        super().__init__(parent)
        self.region = region
        self.setRect(QRectF(0, 0, region.width, region.height))
        self.setPos(region.x, region.y)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not region.locked)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self._resizing = False
        self._resize_handle = -1

    def sync_from_region(self):
        self.setPos(self.region.x, self.region.y)
        self.setRect(QRectF(0, 0, self.region.width, self.region.height))

    def sync_to_region(self):
        pos = self.pos()
        self.region.x = pos.x()
        self.region.y = pos.y()
        rect = self.rect()
        self.region.width = rect.width()
        self.region.height = rect.height()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.sync_to_region()
        return super().itemChange(change, value)

    def paint_selection(self, painter: QPainter):
        if not self.isSelected():
            return
        pen = QPen(QColor(0, 120, 215), 1.0, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.rect())
        hs = self.HANDLE_SIZE
        handles = self._handle_rects()
        painter.setPen(QPen(QColor(0, 120, 215), 1.0))
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        for hr in handles:
            painter.drawRect(hr)

    def _handle_rects(self) -> list[QRectF]:
        r = self.rect()
        hs = self.HANDLE_SIZE
        return [
            QRectF(r.left() - hs / 2, r.top() - hs / 2, hs, hs),
            QRectF(r.center().x() - hs / 2, r.top() - hs / 2, hs, hs),
            QRectF(r.right() - hs / 2, r.top() - hs / 2, hs, hs),
            QRectF(r.right() - hs / 2, r.center().y() - hs / 2, hs, hs),
            QRectF(r.right() - hs / 2, r.bottom() - hs / 2, hs, hs),
            QRectF(r.center().x() - hs / 2, r.bottom() - hs / 2, hs, hs),
            QRectF(r.left() - hs / 2, r.bottom() - hs / 2, hs, hs),
            QRectF(r.left() - hs / 2, r.center().y() - hs / 2, hs, hs),
        ]
