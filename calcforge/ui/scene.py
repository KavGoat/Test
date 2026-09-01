"""The graphics scene that draws one page and holds its markups."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsScene

from ..core.document import MM_TO_PT, Document, Page
from ..items.base import MarkupItem, build_item
from ..items.media import ImageItem

PAPER = QColor("#ffffff")
MARGIN_PEN = QColor(120, 160, 220, 120)
GRID_PEN = QColor(180, 195, 210, 110)
GRID_PEN_MAJOR = QColor(150, 170, 195, 150)


class PageScene(QGraphicsScene):
    """One page: paper, optional PDF background, guides and markup items."""

    itemsChanged = Signal()
    selectionInfoChanged = Signal()

    def __init__(self, page: Page, document: Document):
        super().__init__()
        self.page = page
        self.document = document
        self.workspace = document.workspace
        self._background: Optional[QPixmap] = None
        self.print_mode = False
        self.update_scene_rect()
        self.setBackgroundBrush(QBrush(QColor("#8b9099")))
        self.selectionChanged.connect(self.selectionInfoChanged.emit)

    # -- geometry ----------------------------------------------------------
    def update_scene_rect(self) -> None:
        self.setSceneRect(QRectF(0, 0, self.page.width_pt, self.page.height_pt))

    def page_rect(self) -> QRectF:
        return QRectF(0, 0, self.page.width_pt, self.page.height_pt)

    # -- background --------------------------------------------------------
    def load_background(self) -> None:
        data = self.document.asset(self.page.background_key)
        if not data:
            self._background = None
            return
        pixmap = QPixmap()
        pixmap.loadFromData(QByteArray(data))
        self._background = pixmap if not pixmap.isNull() else None

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        page_rect = self.page_rect()
        painter.fillRect(page_rect, PAPER)
        if self._background is None and self.page.background_key:
            self.load_background()
        if self._background is not None:
            painter.save()
            painter.setOpacity(self.page.background_opacity)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.drawPixmap(page_rect, self._background, QRectF(self._background.rect()))
            painter.restore()
        if not self.print_mode:
            self._draw_grid(painter, rect)
            self._draw_margins(painter)
        self._draw_running_text(painter)

    def _draw_grid(self, painter: QPainter, rect: QRectF) -> None:
        settings = self.document.settings
        if not settings.show_grid:
            return
        step = max(settings.grid_mm, 1.0) * MM_TO_PT
        page_rect = self.page_rect()
        area = rect.intersected(page_rect)
        if area.isEmpty():
            return
        painter.save()
        minor = QPen(GRID_PEN)
        minor.setWidthF(0.3)
        major = QPen(GRID_PEN_MAJOR)
        major.setWidthF(0.6)
        index = int(area.left() / step)
        x = index * step
        while x <= area.right():
            painter.setPen(major if index % 5 == 0 else minor)
            painter.drawLine(QPointF(x, area.top()), QPointF(x, area.bottom()))
            x += step
            index += 1
        index = int(area.top() / step)
        y = index * step
        while y <= area.bottom():
            painter.setPen(major if index % 5 == 0 else minor)
            painter.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            y += step
            index += 1
        painter.restore()

    def _draw_margins(self, painter: QPainter) -> None:
        if not self.document.settings.show_margins:
            return
        x, y, width, height = self.page.setup.content_rect_pt
        pen = QPen(MARGIN_PEN)
        pen.setWidthF(0.6)
        pen.setStyle(Qt.DashLine)
        painter.save()
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(x, y, width, height))
        painter.restore()

    def _draw_running_text(self, painter: QPainter) -> None:
        settings = self.document.settings
        index = self.document.index_of(self.page)
        left, top, width, height = self.page.setup.content_rect_pt
        from ..core.typography import page_font
        font = page_font("", 8.0)
        painter.save()
        painter.setFont(font)
        painter.setPen(QPen(QColor(90, 96, 106)))
        if settings.show_header:
            box = QRectF(left, top - 18, width, 14)
            self._draw_three(painter, box, settings.header_left, settings.header_center,
                             settings.header_right, index)
            pen = QPen(QColor(190, 196, 206))
            pen.setWidthF(0.5)
            painter.setPen(pen)
            painter.drawLine(QPointF(left, top - 4), QPointF(left + width, top - 4))
            painter.setPen(QPen(QColor(90, 96, 106)))
        if settings.show_footer:
            box = QRectF(left, top + height + 5, width, 14)
            self._draw_three(painter, box, settings.footer_left, settings.footer_center,
                             settings.footer_right, index)
            pen = QPen(QColor(190, 196, 206))
            pen.setWidthF(0.5)
            painter.setPen(pen)
            painter.drawLine(QPointF(left, top + height + 3),
                             QPointF(left + width, top + height + 3))
        painter.restore()

    def _draw_three(self, painter: QPainter, box: QRectF, left: str, center: str,
                    right: str, index: int) -> None:
        if left:
            painter.drawText(box, Qt.AlignLeft | Qt.AlignVCenter,
                             self.document.expand_fields(left, index))
        if center:
            painter.drawText(box, Qt.AlignHCenter | Qt.AlignVCenter,
                             self.document.expand_fields(center, index))
        if right:
            painter.drawText(box, Qt.AlignRight | Qt.AlignVCenter,
                             self.document.expand_fields(right, index))

    # -- items -------------------------------------------------------------
    def markups(self) -> list[MarkupItem]:
        return [item for item in self.items() if isinstance(item, MarkupItem)]

    def ordered_markups(self) -> list[MarkupItem]:
        """Reading order: top to bottom, then left to right."""
        return sorted(self.markups(), key=lambda i: (round(i.pos().y(), 1), round(i.pos().x(), 1)))

    def add_markup(self, item: MarkupItem, position: Optional[QPointF] = None) -> MarkupItem:
        if position is not None:
            item.setPos(position)
        if not item.zValue():
            item.setZValue(self.next_z())
        if isinstance(item, ImageItem):
            item.load_from_document(self.document)
        self.addItem(item)
        item.refresh(self.workspace, self.page)
        self.itemsChanged.emit()
        return item

    def remove_markup(self, item: MarkupItem) -> None:
        self.removeItem(item)
        self.itemsChanged.emit()

    def next_z(self) -> float:
        markups = self.markups()
        return (max((i.zValue() for i in markups), default=0.0) + 1.0) if markups else 1.0

    def serialize_items(self) -> list[dict]:
        return [item.serialize() for item in sorted(self.markups(), key=lambda i: i.zValue())]

    def load_items(self, data: list[dict]) -> None:
        for item in self.markups():
            self.removeItem(item)
        for entry in data:
            item = build_item(entry)
            if item is None:
                continue
            if isinstance(item, ImageItem):
                item.load_from_document(self.document)
            self.addItem(item)
        self.refresh_items()

    def refresh_items(self) -> None:
        for item in self.ordered_markups():
            item.refresh(self.workspace, self.page)

    def assets_used(self) -> set[str]:
        used: set[str] = set()
        for item in self.markups():
            used |= item.assets_used()
        if self.page.background_key:
            used.add(self.page.background_key)
        return used

    # -- rendering ---------------------------------------------------------
    def render_page(self, painter: QPainter, target: QRectF, for_print: bool = True) -> None:
        """Draw the whole page into *target*, hiding editing chrome."""
        previous = self.print_mode
        self.print_mode = for_print
        selected = self.selectedItems()
        chrome: list[tuple] = []
        for item in self.markups():
            if hasattr(item, "show_chrome"):
                chrome.append((item, item.show_chrome))
                item.show_chrome = False
            item.setSelected(False)
        hidden = [item for item in self.markups() if not item.printable and for_print]
        for item in hidden:
            item.setVisible(False)
        self.render(painter, target, self.page_rect(), Qt.IgnoreAspectRatio)
        for item in hidden:
            item.setVisible(True)
        for item, value in chrome:
            item.show_chrome = value
        for item in selected:
            item.setSelected(True)
        self.print_mode = previous

    def render_image(self, dpi: float = 150.0, for_print: bool = True) -> QImage:
        scale = dpi / 72.0
        width = max(int(self.page.width_pt * scale), 1)
        height = max(int(self.page.height_pt * scale), 1)
        image = QImage(width, height, QImage.Format_ARGB32)
        image.fill(Qt.white)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.render_page(painter, QRectF(0, 0, width, height), for_print)
        painter.end()
        return image
