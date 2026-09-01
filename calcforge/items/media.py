"""Raster image markups (screenshots, logos, imported PDF snippets)."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QPainter, QPixmap

from .base import MarkupItem, Style, register_item


@register_item
class ImageItem(MarkupItem):
    """An image stored as a document asset and drawn into a rectangle."""

    TYPE = "image"
    NAME = "Image"

    def __init__(self, asset_key: str = "", rect: Optional[QRectF] = None):
        super().__init__()
        self.asset_key = asset_key
        self._rect = QRectF(rect) if rect else QRectF(0, 0, 200, 150)
        self.keep_aspect = True
        self.style = Style(stroke="", fill="", width=0.0)
        self._pixmap: Optional[QPixmap] = None

    def set_pixmap(self, pixmap: QPixmap) -> None:
        self._pixmap = pixmap
        if not pixmap.isNull() and self.keep_aspect and self._rect.width() > 0:
            ratio = pixmap.height() / max(pixmap.width(), 1)
            self._rect.setHeight(self._rect.width() * ratio)
        self.update()

    def pixmap(self) -> Optional[QPixmap]:
        return self._pixmap

    def load_from_document(self, document) -> None:
        data = document.asset(self.asset_key)
        if data:
            pixmap = QPixmap()
            pixmap.loadFromData(QByteArray(data))
            self._pixmap = pixmap
            self.update()

    def local_rect(self) -> QRectF:
        return QRectF(self._rect)

    def set_local_rect(self, rect: QRectF) -> None:
        self._rect = QRectF(rect)

    def paint_content(self, painter: QPainter) -> None:
        rect = self._rect.normalized()
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setOpacity(self.style.opacity)
        if self._pixmap is not None and not self._pixmap.isNull():
            painter.drawPixmap(rect, self._pixmap, QRectF(self._pixmap.rect()))
        else:
            painter.fillRect(rect, Qt.lightGray)
            painter.drawText(rect, Qt.AlignCenter, "image missing")
        painter.setOpacity(1.0)
        if self.style.stroke and self.style.width > 0:
            painter.setPen(self.style.pen())
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect)

    def assets_used(self) -> set[str]:
        return {self.asset_key} if self.asset_key else set()

    def serialize(self) -> dict:
        data = self.base_dict()
        data.update({"asset": self.asset_key, "keep_aspect": self.keep_aspect,
                     "rect": [self._rect.x(), self._rect.y(),
                              self._rect.width(), self._rect.height()]})
        return data

    def deserialize(self, data: dict) -> None:
        self.asset_key = data.get("asset", "")
        self.keep_aspect = bool(data.get("keep_aspect", True))
        self._rect = QRectF(*data.get("rect", [0, 0, 200, 150]))
        self.load_base(data)
