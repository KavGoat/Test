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
    SCALE_BOX = True               # Bluebeam's scale box round it

    def __init__(self, asset_key: str = "", rect: Optional[QRectF] = None):
        super().__init__()
        self.asset_key = asset_key
        self._rect = QRectF(rect) if rect else QRectF(0, 0, 200, 150)
        self.keep_aspect = True
        self.style = Style(stroke="", fill="", width=0.0)
        self._pixmap: Optional[QPixmap] = None
        # Revu's Crop Image: the part of the picture shown, as fractions of
        # it (x, y, width, height) — the whole of it until it is cropped. The
        # picture itself is kept whole, so a crop is never a loss.
        self.crop = QRectF(0, 0, 1, 1)

    def pixmap(self) -> Optional[QPixmap]:
        return self._pixmap

    def load_from_document(self, document) -> None:
        super().load_from_document(document)
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
            painter.drawPixmap(rect, self._pixmap, self.source_rect())
        else:
            painter.fillRect(rect, Qt.lightGray)
            painter.drawText(rect, Qt.AlignCenter, "image missing")
        painter.setOpacity(1.0)
        if self.style.stroke and self.style.width > 0:
            painter.setPen(self.style.pen())
            painter.setBrush(Qt.NoBrush)
            from .complexlines import draw_rect
            if not draw_rect(painter, rect, self.style):
                painter.drawRect(rect)

    def source_rect(self) -> QRectF:
        """The part of the picture drawn, in its own pixels."""
        whole = QRectF(self._pixmap.rect()) if self._pixmap is not None else QRectF(0, 0, 1, 1)
        crop = self.crop
        return QRectF(whole.width() * crop.x(), whole.height() * crop.y(),
                      whole.width() * crop.width(), whole.height() * crop.height())

    def is_cropped(self) -> bool:
        return self.crop != QRectF(0, 0, 1, 1)

    def crop_to(self, keep: QRectF) -> bool:
        """Revu's Crop Image: keep the part of the image under *keep* (in the
        image's own coordinates); the image's box becomes that part."""
        rect = self._rect.normalized()
        keep = QRectF(keep).normalized().intersected(rect)
        if keep.width() < 1 or keep.height() < 1 or rect.width() <= 0 or rect.height() <= 0:
            return False
        crop = self.crop
        fx = crop.width() / rect.width()
        fy = crop.height() / rect.height()
        self.crop = QRectF(crop.x() + (keep.left() - rect.left()) * fx,
                           crop.y() + (keep.top() - rect.top()) * fy,
                           keep.width() * fx, keep.height() * fy)
        self.prepareGeometryChange()
        self._rect = QRectF(keep)
        self.update()
        return True

    def assets_used(self) -> set[str]:
        return {self.asset_key} if self.asset_key else set()

    def serialize(self) -> dict:
        data = self.base_dict()
        data.update({"asset": self.asset_key, "keep_aspect": self.keep_aspect,
                     "rect": [self._rect.x(), self._rect.y(),
                              self._rect.width(), self._rect.height()]})
        if self.is_cropped():
            data["crop"] = [self.crop.x(), self.crop.y(), self.crop.width(), self.crop.height()]
        return data

    def deserialize(self, data: dict) -> None:
        # "asset_key" is what the attribute is called, and clipboard payloads
        # written by hand have used that spelling; the stored key is "asset".
        # Both are read, so neither an old file nor an old clipboard comes
        # back as a grey box saying the image is missing.
        self.asset_key = data.get("asset") or data.get("asset_key") or ""
        self.keep_aspect = bool(data.get("keep_aspect", True))
        self._rect = QRectF(*data.get("rect", [0, 0, 200, 150]))
        crop = data.get("crop")
        self.crop = QRectF(*crop) if crop and len(crop) == 4 else QRectF(0, 0, 1, 1)
        image_default = self.style
        self.load_base(data)
        # Clipboard image payloads contain no markup style. Generic
        # deserialisation used to replace the image's borderless default with
        # the red line default shared by drawn markups, putting a red frame
        # around every pasted photo.
        if "style" not in data:
            self.style = image_default
