"""A table of contents drawn from the document's bookmarks."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from ..core.typography import page_font
from .base import MarkupItem, Style, register_item


@register_item
class ContentsItem(MarkupItem):
    """The bookmarks, printed on the page as a contents list.

    It reads the document's bookmarks rather than keeping a list of its own,
    so it can never say something different from the bookmarks panel or from
    the outline of the exported PDF. Each row remembers where it was drawn, so
    a click can follow it and the exported PDF can carry a link on it.
    """

    TYPE = "contents"
    NAME = "Contents"
    ROTATABLE = False

    def __init__(self, rect: Optional[QRectF] = None):
        super().__init__()
        self._rect = QRectF(rect) if rect else QRectF(0, 0, 300, 160)
        self.title = "Contents"
        self.show_page_numbers = True
        self.leader_dots = True
        self.row_height = 15.0
        self.style = Style(stroke="#c6ccd6", fill="#ffffff", fill_opacity=1.0,
                           width=0.6, font_size=9.5, text_color="#111318",
                           padding=8.0)
        self.layer = "Markups"
        # Filled in as it paints: one (rect, page index, y) per row, for the
        # click that follows a row and for the link in the exported PDF.
        self.rows: list[tuple[QRectF, int, float]] = []

    # -- geometry ----------------------------------------------------------
    def local_rect(self) -> QRectF:
        return QRectF(self._rect)

    def set_local_rect(self, rect: QRectF) -> None:
        self.prepareGeometryChange()
        self._rect = QRectF(rect)
        self.geometryChanged.emit()

    def entries(self) -> list:
        """(bookmark, page index) for everything that still points somewhere."""
        document = self.document()
        return document.contents_entries() if document is not None else []

    def document(self):
        scene = self.scene()
        return getattr(scene, "document", None) if scene is not None else None

    def row_at(self, local_pos: QPointF) -> Optional[tuple[int, float]]:
        """The page and place a row points at, for a click on that row."""
        for rect, index, y in self.rows:
            if rect.contains(local_pos):
                return index, y
        return None

    # -- painting ----------------------------------------------------------
    def paint_content(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self._rect.normalized()
        painter.setBrush(self.style.brush())
        painter.setPen(self.style.pen() if self.style.stroke and self.style.width > 0
                       else QPen(Qt.NoPen))
        painter.drawRect(rect)

        pad = self.style.padding
        size = self.style.font_size
        ink = QColor(self.style.text_color)
        y = rect.top() + pad
        self.rows = []

        if self.title:
            painter.setFont(page_font("", size * 1.15, bold=True))
            painter.setPen(QPen(ink))
            painter.drawText(QRectF(rect.left() + pad, y, rect.width() - 2 * pad,
                                    size * 1.6),
                             Qt.AlignLeft | Qt.AlignVCenter, self.title)
            y += size * 1.9
            rule = QPen(QColor(198, 204, 214))
            rule.setWidthF(0.6)
            painter.setPen(rule)
            painter.drawLine(QPointF(rect.left() + pad, y - size * 0.4),
                             QPointF(rect.right() - pad, y - size * 0.4))

        painter.setFont(page_font("", size))
        entries = self.entries()
        if not entries:
            painter.setPen(QPen(QColor(140, 148, 160)))
            painter.drawText(QRectF(rect.left() + pad, y, rect.width() - 2 * pad,
                                    size * 2.2),
                             Qt.AlignLeft | Qt.AlignTop,
                             "No bookmarks yet — add one from the bookmarks panel")
            return

        metrics = painter.fontMetrics()
        for mark, index in entries:
            if y + self.row_height > rect.bottom() - pad:
                break
            left = rect.left() + pad + mark.level * size * 1.2
            number = str(index + 1)
            number_width = metrics.horizontalAdvance(number) + 4 if self.show_page_numbers else 0
            row = QRectF(rect.left() + pad, y, rect.width() - 2 * pad, self.row_height)
            painter.setPen(QPen(ink))
            painter.drawText(QRectF(left, y, row.width() - number_width, self.row_height),
                             Qt.AlignLeft | Qt.AlignVCenter, mark.title)
            if self.show_page_numbers:
                painter.drawText(row, Qt.AlignRight | Qt.AlignVCenter, number)
                if self.leader_dots:
                    text_width = metrics.horizontalAdvance(mark.title)
                    start = left + text_width + 4
                    end = row.right() - number_width - 2
                    if end > start:
                        dots = QPen(QColor(180, 188, 200))
                        dots.setWidthF(0.5)
                        dots.setStyle(Qt.DotLine)
                        painter.setPen(dots)
                        middle = y + self.row_height * 0.72
                        painter.drawLine(QPointF(start, middle), QPointF(end, middle))
            self.rows.append((row, index, mark.y))
            y += self.row_height

    def summary(self) -> str:
        return self.comment or f"Contents — {len(self.entries())} entries"

    # -- serialisation -----------------------------------------------------
    def serialize(self) -> dict:
        data = self.base_dict()
        data.update({
            "rect": [self._rect.x(), self._rect.y(),
                     self._rect.width(), self._rect.height()],
            "title": self.title,
            "show_page_numbers": self.show_page_numbers,
            "leader_dots": self.leader_dots,
            "row_height": self.row_height,
        })
        return data

    def deserialize(self, data: dict) -> None:
        rect = data.get("rect", [0, 0, 300, 160])
        self._rect = QRectF(*rect)
        self.title = data.get("title", "Contents")
        self.show_page_numbers = bool(data.get("show_page_numbers", True))
        self.leader_dots = bool(data.get("leader_dots", True))
        self.row_height = float(data.get("row_height", 15.0))
        self.load_base(data)
