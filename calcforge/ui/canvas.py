"""Worksheet canvas — QGraphicsView/Scene matching SMath Studio's page layout."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import (
    QPainter, QPen, QColor, QBrush, QWheelEvent, QMouseEvent,
    QKeyEvent,
)
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsRectItem,
    QGraphicsItem,
)

from ..core.document import Document, Page, Region, PageSettings
from ..items.base import PageItem
from ..items.calculation import CalculationItem
from ..items.text import TextItem
from ..items.plot import PlotItem


PAGE_GAP = 20.0
PAGE_SHADOW = 4.0


def _create_item(region: Region) -> Optional[PageItem]:
    creators = {
        "calculation": CalculationItem,
        "text": TextItem,
        "plot": PlotItem,
    }
    cls = creators.get(region.type)
    if cls:
        return cls(region)
    return None


class PageBackground(QGraphicsRectItem):
    """White page rectangle with drop shadow, matching SMath Studio."""

    def __init__(self, page: Page, y_offset: float):
        w = page.settings.width
        h = page.settings.height
        super().__init__(0, y_offset, w, h)
        self.page = page
        self.y_offset = y_offset
        self.setPen(QPen(QColor(180, 180, 180), 0.5))
        self.setBrush(QBrush(QColor(255, 255, 255)))
        self.setZValue(-100)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

    def paint(self, painter: QPainter, option, widget=None):
        shadow_rect = QRectF(
            PAGE_SHADOW, self.y_offset + PAGE_SHADOW,
            self.page.settings.width, self.page.settings.height,
        )
        painter.fillRect(shadow_rect, QColor(190, 190, 190))
        page_rect = QRectF(0, self.y_offset,
                           self.page.settings.width, self.page.settings.height)
        painter.fillRect(page_rect, QColor(255, 255, 255))
        painter.setPen(QPen(QColor(180, 180, 180), 0.5))
        painter.drawRect(page_rect)
        if self.page.settings.grid_visible:
            gs = self.page.settings.grid_spacing
            painter.setPen(QPen(QColor(220, 220, 230), 0.3))
            x = gs
            while x < self.page.settings.width:
                painter.drawLine(QPointF(x, self.y_offset),
                                 QPointF(x, self.y_offset + self.page.settings.height))
                x += gs
            y = gs
            while y < self.page.settings.height:
                painter.drawLine(QPointF(0, self.y_offset + y),
                                 QPointF(self.page.settings.width, self.y_offset + y))
                y += gs


class DocumentScene(QGraphicsScene):
    """Scene holding all pages and their items."""

    region_selected = Signal(object)
    region_double_clicked = Signal(object)
    page_clicked = Signal(int, QPointF)

    def __init__(self, document: Document, parent=None):
        super().__init__(parent)
        self.document = document
        self._page_bgs: list[PageBackground] = []
        self._items: dict[str, PageItem] = {}
        self.setBackgroundBrush(QBrush(QColor(190, 195, 200)))
        self.rebuild()

    def rebuild(self):
        self.clear()
        self._page_bgs.clear()
        self._items.clear()
        y = 0.0
        for page in self.document.pages:
            bg = PageBackground(page, y)
            self.addItem(bg)
            self._page_bgs.append(bg)
            for region in page.regions:
                item = _create_item(region)
                if item:
                    item.setPos(region.x, y + region.y)
                    self.addItem(item)
                    self._items[region.id] = item
            y += page.settings.height + PAGE_GAP

    def page_y_offset(self, page_index: int) -> float:
        y = 0.0
        for i, page in enumerate(self.document.pages):
            if i == page_index:
                return y
            y += page.settings.height + PAGE_GAP
        return y

    def add_region_item(self, region: Region) -> Optional[PageItem]:
        item = _create_item(region)
        if item:
            y_off = self.page_y_offset(region.page_index)
            item.setPos(region.x, y_off + region.y)
            self.addItem(item)
            self._items[region.id] = item
        return item

    def remove_region_item(self, region_id: str):
        item = self._items.pop(region_id, None)
        if item:
            self.removeItem(item)

    def get_item(self, region_id: str) -> Optional[PageItem]:
        return self._items.get(region_id)

    def page_at_scene_pos(self, pos: QPointF) -> int:
        y = 0.0
        for i, page in enumerate(self.document.pages):
            if y <= pos.y() < y + page.settings.height:
                return i
            y += page.settings.height + PAGE_GAP
        return len(self.document.pages) - 1


class DocumentCanvas(QGraphicsView):
    """Worksheet view — click to create math regions, like SMath Studio."""

    tool_changed = Signal(str)

    def __init__(self, scene: DocumentScene, parent=None):
        super().__init__(scene, parent)
        self._scene = scene
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self._current_tool = "select"
        self._panning = False
        self._pan_start = QPointF()

    @property
    def current_tool(self) -> str:
        return self._current_tool

    @current_tool.setter
    def current_tool(self, tool: str):
        self._current_tool = tool
        self.tool_changed.emit(tool)
        if tool == "select":
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.setCursor(Qt.CursorShape.CrossCursor)

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
        else:
            super().wheelEvent(event)

    def zoom_fit_page(self):
        if not self._scene.document.pages:
            return
        page = self._scene.document.pages[0]
        self.fitInView(
            QRectF(0, 0, page.settings.width, page.settings.height),
            Qt.AspectRatioMode.KeepAspectRatio,
        )

    def zoom_fit_width(self):
        if not self._scene.document.pages:
            return
        page = self._scene.document.pages[0]
        vw = self.viewport().width()
        scale = vw / page.settings.width
        self.resetTransform()
        self.scale(scale, scale)

    def keyPressEvent(self, event: QKeyEvent):
        focused = self._scene.focusItem()
        if focused and isinstance(focused, PageItem) and getattr(focused, 'editing', False):
            super().keyPressEvent(event)
            return
        if event.key() == Qt.Key.Key_Escape:
            self.current_tool = "select"
            self._scene.clearSelection()
        elif event.key() == Qt.Key.Key_Delete:
            for item in self._scene.selectedItems():
                if isinstance(item, PageItem):
                    page = self._scene.document.pages[item.region.page_index]
                    page.remove_region(item.region.id)
                    self._scene.remove_region_item(item.region.id)
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton and
            event.modifiers() & Qt.KeyboardModifier.AltModifier
        ):
            self._panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(
                int(self.horizontalScrollBar().value() - delta.x()))
            self.verticalScrollBar().setValue(
                int(self.verticalScrollBar().value() - delta.y()))
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._panning:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        scene_pos = self.mapToScene(event.position().toPoint())
        item = self._scene.itemAt(scene_pos, self.transform())
        if isinstance(item, PageItem):
            item.setFocus()
            item.start_edit()
            event.accept()
            return
        if isinstance(item, PageBackground) or item is None:
            page_idx = self._scene.page_at_scene_pos(scene_pos)
            y_off = self._scene.page_y_offset(page_idx)
            region = Region(
                type="calculation",
                x=scene_pos.x(),
                y=scene_pos.y() - y_off,
                width=100, height=24,
                page_index=page_idx,
                data={"lines": [""]},
            )
            page = self._scene.document.pages[page_idx]
            page.add_region(region)
            new_item = self._scene.add_region_item(region)
            self._scene.document.modified = True
            if new_item:
                new_item.setFocus()
                new_item.start_edit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
