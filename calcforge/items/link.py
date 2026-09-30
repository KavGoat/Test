"""A link: a region of the page that goes somewhere when it is clicked.

Bluebeam's Link tool. The region can go to a page of this document, to a
particular view of one (a page and how far down it), to a file, or to a web
address. It is written into a saved or exported PDF as a real link
annotation, so it works in every viewer. On screen it is a faint dashed
outline so it can be found and edited; it is never printed.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from .base import MarkupItem, Style, register_item

PAGE = "page"
VIEW = "view"
FILE = "file"
WEB = "web"
KINDS = (PAGE, VIEW, FILE, WEB)


@register_item
class LinkItem(MarkupItem):
    TYPE = "link"
    NAME = "Link"
    ROTATABLE = False

    def __init__(self, rect: Optional[QRectF] = None):
        super().__init__()
        self._rect = QRectF(rect) if rect else QRectF(0, 0, 120, 30)
        self.style = Style(stroke="#1971c2", fill="", width=0.0)
        self.kind = PAGE
        self.target_page = 0          # zero-based, for PAGE and VIEW
        self.target_y = 0.0           # how far down the page, for VIEW
        self.address = ""             # the file path or web address

    def local_rect(self) -> QRectF:
        return QRectF(self._rect)

    def set_local_rect(self, rect: QRectF) -> None:
        self.prepareGeometryChange()
        self._rect = QRectF(rect)
        self.geometryChanged.emit()

    def describe(self) -> str:
        if self.kind == PAGE:
            return f"Page {self.target_page + 1}"
        if self.kind == VIEW:
            return f"Page {self.target_page + 1}, {self.target_y:.0f} pt down"
        return self.address or "(nowhere yet)"

    def summary(self) -> str:
        return self.comment or f"Link to {self.describe()}"

    def paint_content(self, painter: QPainter) -> None:
        frame = self.parentItem()
        if getattr(frame, "print_mode", False):
            return                     # a link is for clicking, not for paper
        painter.save()
        pen = QPen(QColor(self.style.stroke or "#1971c2"))
        pen.setCosmetic(True)
        pen.setWidthF(1.0)
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        fill = QColor(self.style.stroke or "#1971c2")
        fill.setAlpha(18)
        painter.setBrush(fill)
        painter.drawRect(self._rect.normalized())
        painter.restore()

    def serialize(self) -> dict:
        data = self.base_dict()
        data.update({"rect": [self._rect.x(), self._rect.y(),
                              self._rect.width(), self._rect.height()],
                     "kind": self.kind, "target_page": self.target_page,
                     "target_y": self.target_y, "address": self.address})
        return data

    def deserialize(self, data: dict) -> None:
        self.load_base(data)
        self._rect = QRectF(*data.get("rect", [0, 0, 120, 30]))
        kind = data.get("kind", PAGE)
        self.kind = kind if kind in KINDS else PAGE
        self.target_page = int(data.get("target_page", 0) or 0)
        self.target_y = float(data.get("target_y", 0.0) or 0.0)
        self.address = str(data.get("address", "") or "")
