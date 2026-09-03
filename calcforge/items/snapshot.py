"""Snapshots: a piece of a page, kept as drawing rather than as pixels."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QByteArray, QDataStream, QIODevice, QRectF, Qt
from PySide6.QtGui import QPainter, QPicture

from .base import MarkupItem, Style, register_item


@register_item
class SnapshotItem(MarkupItem):
    """A copy of part of a page, taken as lines and kept as lines.

    Bluebeam's snapshot brings the drawing across, not a photograph of it, and
    that is the whole point of taking one: it can be scaled up on the page it
    lands on, printed at full resolution, and read at any zoom. So what is
    stored is the drawing itself — every line, every letter and every image
    that was under the marquee, recorded as the instructions that drew them.

    It is its own kind of markup rather than an image with a different name.
    A snapshot has a source: which page it came from and which part of it, and
    those are worth keeping and worth showing in its properties.
    """

    TYPE = "snapshot"
    NAME = "Snapshot"

    def __init__(self, rect: Optional[QRectF] = None):
        super().__init__()
        self._rect = QRectF(rect) if rect else QRectF(0, 0, 200, 150)
        self.asset_key = ""
        self.keep_aspect = True
        # What it is a copy of, for its properties and its summary.
        self.source_page = 0
        self.source_rect = QRectF(self._rect)
        self.style = Style(stroke="", fill="", width=0.0)
        self._picture: Optional[QPicture] = None

    # -- the recording -----------------------------------------------------
    def set_picture(self, picture: QPicture) -> None:
        self._picture = picture
        self.update()

    def picture(self) -> Optional[QPicture]:
        return self._picture

    def load_from_document(self, document) -> None:
        data = document.asset(self.asset_key)
        if not data:
            return
        picture = QPicture()
        picture.setData(bytes(data))
        self._picture = picture
        self.update()

    def assets_used(self) -> set[str]:
        return {self.asset_key} if self.asset_key else set()

    # -- geometry ----------------------------------------------------------
    def local_rect(self) -> QRectF:
        return QRectF(self._rect)

    def set_local_rect(self, rect: QRectF) -> None:
        self._rect = QRectF(rect)

    def natural_size(self) -> QRectF:
        """The size the snapshot was taken at — what it looks right at."""
        return QRectF(self.source_rect).normalized()

    # -- painting ----------------------------------------------------------
    def paint_content(self, painter: QPainter) -> None:
        rect = self._rect.normalized()
        if self._picture is None or self._picture.isNull():
            painter.fillRect(rect, Qt.lightGray)
            painter.drawText(rect, Qt.AlignCenter, "snapshot missing")
        else:
            taken = self.natural_size()
            painter.save()
            painter.setOpacity(self.style.opacity)
            painter.setClipRect(rect)
            painter.translate(rect.topLeft())
            if taken.width() > 0 and taken.height() > 0:
                painter.scale(rect.width() / taken.width(),
                              rect.height() / taken.height())
            # The recording draws from its own origin, so nothing else has to
            # be worked out here: it lands where the snapshot is.
            painter.drawPicture(0, 0, self._picture)
            painter.restore()
        if self.style.stroke and self.style.width > 0:
            painter.setPen(self.style.pen())
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect)

    def summary(self) -> str:
        if self.comment:
            return self.comment
        if self.source_page:
            return f"Snapshot from page {self.source_page}"
        return "Snapshot"

    # -- serialisation -----------------------------------------------------
    def serialize(self) -> dict:
        data = self.base_dict()
        taken = self.source_rect
        data.update({
            "asset": self.asset_key,
            "keep_aspect": self.keep_aspect,
            "source_page": self.source_page,
            "source_rect": [taken.x(), taken.y(), taken.width(), taken.height()],
            "rect": [self._rect.x(), self._rect.y(),
                     self._rect.width(), self._rect.height()],
        })
        return data

    def deserialize(self, data: dict) -> None:
        self.asset_key = data.get("asset") or data.get("asset_key") or ""
        self.keep_aspect = bool(data.get("keep_aspect", True))
        self._rect = QRectF(*data.get("rect", [0, 0, 200, 150]))
        self.source_page = int(data.get("source_page", 0) or 0)
        taken = data.get("source_rect")
        self.source_rect = QRectF(*taken) if taken else QRectF(self._rect)
        self.load_base(data)
