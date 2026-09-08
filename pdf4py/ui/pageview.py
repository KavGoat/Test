"""The page canvas: one page, its markups on top, and the two tools.

Markups are drawn as their own items rather than baked into the page image, so
each one can be picked up and dragged the way PDF4QT's editor lets you move an
annotation around.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (QGraphicsItem, QGraphicsPixmapItem, QGraphicsRectItem,
                               QGraphicsScene, QGraphicsView)

from ..document import Markup, PdfDocument
from .images import to_pixmap

SELECT = "select"
RECTANGLE = "rectangle"

MIN_ZOOM = 0.1
MAX_ZOOM = 8.0
ZOOM_STEP = 1.25

# A drag shorter than this is a mis-click, not a rectangle.
MIN_RECTANGLE_POINTS = 3.0

PAPER_MARGIN = 24
CANVAS_COLOUR = QColor("#5a5f66")
SELECTION_COLOUR = QColor("#1a73e8")
HOVER_COLOUR = QColor("#1a73e8")
DRAFT_COLOUR = QColor("#d62828")


class MarkupItem(QGraphicsPixmapItem):
    """One annotation, drawn from its own appearance and free to be dragged."""

    def __init__(self, view: "PageView", markup: Markup, pixmap, position: QPointF,
                 limit: QRectF):
        super().__init__(pixmap)
        self._view = view
        self.xref = markup.xref
        self.subtype = markup.subtype
        self.limit = limit
        self.setPos(position)
        self.home = QPointF(position)
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable
                      | QGraphicsItem.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.SizeAllCursor)
        self.setZValue(10)
        self.setToolTip(f"{markup.subtype} markup — drag to move")
        self._hovered = False

    # Keep the markup on the page: a drag that leaves it is a lost annotation.
    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene() is not None:
            size = self.boundingRect()
            x = min(max(value.x(), self.limit.left()), self.limit.right() - size.width())
            y = min(max(value.y(), self.limit.top()), self.limit.bottom() - size.height())
            return QPointF(x, y)
        return super().itemChange(change, value)

    def hoverEnterEvent(self, event):
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def paint(self, painter: QPainter, option, widget=None):
        # Painted by hand rather than through the base class: Qt's selection
        # marker follows the opaque pixels, which for a hollow markup such as a
        # rectangle outline is almost nothing.
        painter.drawPixmap(0, 0, self.pixmap())
        if self.isSelected() or self._hovered:
            colour = SELECTION_COLOUR if self.isSelected() else HOVER_COLOUR
            pen = QPen(colour, 1.0, Qt.SolidLine if self.isSelected() else Qt.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.boundingRect().adjusted(0.5, 0.5, -0.5, -0.5))

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        moved = self.pos() - self.home
        if not moved.isNull():
            self._view.commit_move(self, moved)


class PageView(QGraphicsView):
    """Shows one page of the document and edits the markups on it."""

    edited = Signal()
    message = Signal(str)

    def __init__(self, document: PdfDocument, parent=None):
        super().__init__(parent)
        self.document = document
        self.index = 0
        self.zoom = 1.0
        self.mode = SELECT
        self._page_item: Optional[QGraphicsPixmapItem] = None
        self._draft: Optional[QGraphicsRectItem] = None
        self._origin = QPointF()
        self.setScene(QGraphicsScene(self))
        self.setBackgroundBrush(QBrush(CANVAS_COLOUR))
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setAlignment(Qt.AlignCenter)
        self.setDragMode(QGraphicsView.NoDrag)

    # ---------------------------------------------------------------- drawing

    def show_page(self, index: int) -> None:
        """Rebuild the scene for ``index``, or empty it if there is no page."""
        scene = self.scene()
        scene.clear()
        self._page_item = None
        self._draft = None
        if self.document.is_empty:
            self.index = 0
            scene.setSceneRect(QRectF(0, 0, 1, 1))
            return
        self.index = min(max(index, 0), self.document.page_count - 1)

        page = to_pixmap(self.document.render_page(self.index, self.zoom))
        self._page_item = scene.addPixmap(page)
        self._page_item.setZValue(0)
        bounds = QRectF(0, 0, page.width(), page.height())
        frame = scene.addRect(bounds, QPen(QColor("#2f3640")), QBrush(Qt.NoBrush))
        frame.setZValue(1)
        scene.setSceneRect(bounds.adjusted(-PAPER_MARGIN, -PAPER_MARGIN,
                                           PAPER_MARGIN, PAPER_MARGIN))

        for markup in self.document.markups(self.index):
            raster = self.document.render_markup(self.index, markup.xref, self.zoom)
            if raster is None:
                continue
            item = MarkupItem(self, markup, to_pixmap(raster),
                              QPointF(raster.x, raster.y), bounds)
            item.setFlag(QGraphicsItem.ItemIsMovable, self.mode == SELECT)
            item.setFlag(QGraphicsItem.ItemIsSelectable, self.mode == SELECT)
            scene.addItem(item)

    def refresh(self) -> None:
        self.show_page(self.index)

    # ------------------------------------------------------------------- zoom

    def set_zoom(self, zoom: float) -> None:
        self.zoom = min(max(zoom, MIN_ZOOM), MAX_ZOOM)
        self.refresh()

    def zoom_in(self) -> None:
        self.set_zoom(self.zoom * ZOOM_STEP)

    def zoom_out(self) -> None:
        self.set_zoom(self.zoom / ZOOM_STEP)

    def fit_page(self) -> None:
        if self.document.is_empty:
            return
        width, height = self.document.page_size(self.index)
        available = self.viewport().size()
        margin = 2 * PAPER_MARGIN + 4
        self.set_zoom(min((available.width() - margin) / max(width, 1.0),
                          (available.height() - margin) / max(height, 1.0)))

    # ------------------------------------------------------------------ tools

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        selectable = mode == SELECT
        for item in self.scene().items():
            if isinstance(item, MarkupItem):
                item.setFlag(QGraphicsItem.ItemIsMovable, selectable)
                item.setFlag(QGraphicsItem.ItemIsSelectable, selectable)
                if not selectable:
                    item.setSelected(False)
        self.viewport().setCursor(Qt.ArrowCursor if selectable else Qt.CrossCursor)

    def commit_move(self, item: MarkupItem, moved: QPointF) -> None:
        """Write a finished drag back into the document."""
        if self.document.move_markup(self.index, item.xref,
                                     moved.x() / self.zoom, moved.y() / self.zoom):
            item.home = QPointF(item.pos())
            self.message.emit(f"Moved the {item.subtype.lower()} markup.")
            self.edited.emit()
        else:
            item.setPos(item.home)
            self.message.emit(f"This {item.subtype.lower()} markup cannot be moved.")

    # ------------------------------------------------------------------ events

    def mousePressEvent(self, event):
        if self.mode == RECTANGLE and event.button() == Qt.LeftButton \
                and self._page_item is not None:
            self._origin = self._clamp(self.mapToScene(event.position().toPoint()))
            pen = QPen(DRAFT_COLOUR, 1.0, Qt.DashLine)
            pen.setCosmetic(True)
            self._draft = self.scene().addRect(QRectF(self._origin, self._origin), pen)
            self._draft.setZValue(20)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._draft is not None:
            corner = self._clamp(self.mapToScene(event.position().toPoint()))
            self._draft.setRect(QRectF(self._origin, corner).normalized())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._draft is not None:
            box = self._draft.rect()
            self.scene().removeItem(self._draft)
            self._draft = None
            points = QRectF(box.x() / self.zoom, box.y() / self.zoom,
                            box.width() / self.zoom, box.height() / self.zoom)
            if points.width() >= MIN_RECTANGLE_POINTS and points.height() >= MIN_RECTANGLE_POINTS:
                self.document.add_rectangle(self.index, (points.left(), points.top(),
                                                         points.right(), points.bottom()))
                self.refresh()
                self.message.emit("Rectangle added.")
                self.edited.emit()
            else:
                self.message.emit("Drag to draw a rectangle.")
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            self.zoom_in() if event.angleDelta().y() > 0 else self.zoom_out()
            return
        super().wheelEvent(event)

    def _clamp(self, point: QPointF) -> QPointF:
        """Keep a drawn corner inside the page."""
        if self._page_item is None:
            return point
        bounds = self._page_item.boundingRect()
        return QPointF(min(max(point.x(), bounds.left()), bounds.right()),
                       min(max(point.y(), bounds.top()), bounds.bottom()))
