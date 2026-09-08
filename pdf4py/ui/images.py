"""Turning the document's rasters into Qt images."""
from __future__ import annotations

from PySide6.QtGui import QImage, QPixmap

from ..document import Raster


def to_image(raster: Raster) -> QImage:
    fmt = QImage.Format_RGBA8888 if raster.alpha else QImage.Format_RGB888
    image = QImage(raster.samples, raster.width, raster.height, raster.stride, fmt)
    # QImage does not take a copy of the buffer, and the raster is about to go
    # out of scope, so hand back an image that owns its pixels.
    return image.copy()


def to_pixmap(raster: Raster) -> QPixmap:
    return QPixmap.fromImage(to_image(raster))
