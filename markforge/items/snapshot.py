"""Snapshots: a piece of a page, kept as drawing rather than as pixels."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QByteArray, QDataStream, QIODevice, QRectF, Qt
from PySide6.QtGui import QPainter, QPicture

from .base import MarkupItem, Style, build_item, register_item


def picture_of(items, box: QRectF) -> QPicture:
    """Record *items* into a picture whose origin is *box*'s corner.

    The same recording the scene makes when a snapshot is taken, but from
    markups that belong to nothing — which is what a snapshot has to draw from
    when it is asked to change colour, long after the page it came off.
    """
    picture = QPicture()
    box = QRectF(box).normalized()
    if box.width() <= 0 or box.height() <= 0 or not items:
        return picture
    painter = QPainter()
    painter.begin(picture)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    painter.setClipRect(QRectF(0, 0, box.width(), box.height()))
    for item in sorted(items, key=lambda markup: markup.zValue()):
        painter.save()
        painter.translate(item.pos())
        painter.setTransform(item.transform(), True)
        item.paint_visible(painter)
        painter.restore()
    painter.end()
    return picture


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
        # What the recording was made of, in the snapshot's own coordinates.
        # A recording is a list of drawing commands and nothing can be asked of
        # it afterwards — not what colour a line is, let alone a different one
        # — so what it was taken of is kept beside it. That is what makes a
        # snapshot's colours changeable at all.
        self.source_items: list[dict] = []

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
        used = {self.asset_key} if self.asset_key else set()
        for payload in self.source_items:
            for key in ("asset", "asset_key"):
                if payload.get(key):
                    used.add(payload[key])
        return used

    # -- what it was taken of ---------------------------------------------
    def record(self, items, box: QRectF) -> None:
        """Keep the markups this was a recording of, in its own coordinates."""
        box = QRectF(box).normalized()
        kept = []
        for item in items:
            payload = item.serialize()
            payload["x"] = payload.get("x", 0.0) - box.left()
            payload["y"] = payload.get("y", 0.0) - box.top()
            kept.append(payload)
        self.source_items = kept

    def source_markups(self) -> list:
        """The markups it was taken of, built back from what was kept."""
        made = []
        for payload in self.source_items:
            try:
                item = build_item(dict(payload))
            except Exception:                          # noqa: BLE001
                continue
            if item is not None:
                made.append(item)
        return made

    def redraw_from(self, items) -> QPicture:
        """Record *items* again as this snapshot's picture, and hand it back."""
        taken = self.natural_size()
        picture = picture_of(items, QRectF(0, 0, taken.width(), taken.height()))
        self.source_items = [item.serialize() for item in items]
        self.set_picture(picture)
        return picture

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
            "source_items": self.source_items,
        })
        return data

    def deserialize(self, data: dict) -> None:
        self.asset_key = data.get("asset") or data.get("asset_key") or ""
        self.keep_aspect = bool(data.get("keep_aspect", True))
        self._rect = QRectF(*data.get("rect", [0, 0, 200, 150]))
        self.source_page = int(data.get("source_page", 0) or 0)
        taken = data.get("source_rect")
        self.source_rect = QRectF(*taken) if taken else QRectF(self._rect)
        self.source_items = list(data.get("source_items") or [])
        # A snapshot payload carries no markup style — it is a recording, not
        # something drawn with a pen. Generic deserialisation used to replace
        # the borderless default with the red line every drawn markup starts
        # with, which is where the outline nobody asked for came from and why
        # changing the default never removed it: the default was right, and it
        # was being thrown away on the way back in. Same fault as the one
        # pasted images had, and the same fix.
        snapshot_default = self.style
        self.load_base(data)
        if "style" not in data:
            self.style = snapshot_default
