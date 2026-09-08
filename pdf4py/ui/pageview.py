"""The page canvas: one page, its markups on top, and the tools that edit them.

Markups are drawn as their own items rather than baked into the page image, so
each one can be picked up, resized and reshaped the way PDF4QT's editor lets you
work on an annotation. The scene is always 1:1 with the screen — zooming
re-renders the page rather than scaling the view — which is what keeps text
crisp and lets the edit handles stay the same size at every zoom.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QPainter, QPen, QPixmap, QPolygonF,
                           QTransform)
from PySide6.QtWidgets import (QGraphicsItem, QGraphicsPixmapItem, QGraphicsPathItem,
                               QGraphicsRectItem, QGraphicsScene, QGraphicsView)
from PySide6.QtGui import QPainterPath

from ..document import DocumentError, Markup, PdfDocument
from .images import to_pixmap
from .textedit import InlineText

SELECT = "select"
RECTANGLE = "rectangle"

MIN_ZOOM = 0.1
MAX_ZOOM = 8.0
ZOOM_STEP = 1.25

# How long the scaled-up picture stands in for the page before it is redrawn
# properly. Long enough that a roll of the wheel is one redraw rather than ten,
# short enough that it is never a blurred page you are waiting on.
SETTLE_MS = 120

# A drag shorter than this is a mis-click, not a rectangle.
MIN_RECTANGLE_POINTS = 3.0

PAPER_MARGIN = 24
CANVAS_COLOUR = QColor("#5a5f66")
SELECTION_COLOUR = QColor("#1a73e8")
GROUP_COLOUR = QColor("#7a4fd6")
DRAFT_COLOUR = QColor("#d62828")
CALLOUT_COLOUR = QColor("#e08000")
BROKEN_PAGE_COLOUR = QColor("#e8e2e2")

HANDLE_SIZE = 8.0

# A markup smaller than this has no room for an editor inside it.
MIN_EDITOR_SIZE = 40.0
NOTE_EDITOR_WIDTH = 180.0
NOTE_EDITOR_HEIGHT = 70.0
EDITOR_POINT_SIZE = 10.0

# The eight resize handles, as the corner of the rectangle each one drags.
CORNERS = (("nw", 0.0, 0.0), ("n", 0.5, 0.0), ("ne", 1.0, 0.0),
           ("e", 1.0, 0.5), ("se", 1.0, 1.0), ("s", 0.5, 1.0),
           ("sw", 0.0, 1.0), ("w", 0.0, 0.5))

HANDLE_CURSORS = {"nw": Qt.SizeFDiagCursor, "se": Qt.SizeFDiagCursor,
                  "ne": Qt.SizeBDiagCursor, "sw": Qt.SizeBDiagCursor,
                  "n": Qt.SizeVerCursor, "s": Qt.SizeVerCursor,
                  "e": Qt.SizeHorCursor, "w": Qt.SizeHorCursor}


class MarkupItem(QGraphicsPixmapItem):
    """One annotation, drawn from its own appearance and free to be dragged."""

    def __init__(self, view: "PageView", markup: Markup, pixmap: QPixmap,
                 position: QPointF, limit: QRectF):
        super().__init__(pixmap)
        self._view = view
        self.markup = markup
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
        self.setToolTip(self._tooltip())
        self._hovered = False

    def _tooltip(self) -> str:
        what = [f"{self.subtype} markup"]
        if len(self._view.group_of(self.xref)) > 1:
            what.append("in a group — it moves with the rest")
        if self.markup.callout:
            what.append("callout — drag the orange points to reshape it")
        if self.markup.editable_text:
            what.append("double-click to edit the text")
        return "\n".join(what)

    # Keep the markup on the page: a drag that leaves it is a lost annotation.
    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene() is not None:
            size = self.boundingRect()
            x = min(max(value.x(), self.limit.left()), self.limit.right() - size.width())
            y = min(max(value.y(), self.limit.top()), self.limit.bottom() - size.height())
            return QPointF(x, y)
        if change == QGraphicsItem.ItemSelectedHasChanged:
            self._view.selection_changed()
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
            selected = self.isSelected()
            grouped = len(self._view.group_of(self.xref)) > 1
            colour = GROUP_COLOUR if selected and grouped else SELECTION_COLOUR
            pen = QPen(colour, 1.0, Qt.SolidLine if selected else Qt.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.boundingRect().adjusted(0.5, 0.5, -0.5, -0.5))

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self._view.commit_moves()

    def mouseDoubleClickEvent(self, event):
        if self.markup.editable_text:
            self._view.edit_text(self.xref)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class HandleItem(QGraphicsRectItem):
    """A grab point: a corner of a markup, or a bend in a callout's leader."""

    def __init__(self, view: "PageView", markup: Markup, role: str,
                 position: QPointF, colour: QColor):
        half = HANDLE_SIZE / 2
        super().__init__(QRectF(-half, -half, HANDLE_SIZE, HANDLE_SIZE))
        self._view = view
        self.markup = markup
        self.role = role
        self.setPos(position)
        self.setBrush(QBrush(QColor("#ffffff")))
        pen = QPen(colour, 1.4)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setZValue(40)
        self.setCursor(HANDLE_CURSORS.get(role, Qt.CrossCursor))
        self.setAcceptedMouseButtons(Qt.LeftButton)

    # The handle drives the drag itself: letting the scene move it would drag
    # the handle away from the markup instead of reshaping the markup.
    def mousePressEvent(self, event):
        self._view.begin_handle_drag(self)
        event.accept()

    def mouseMoveEvent(self, event):
        self._view.drag_handle(event.scenePos())
        event.accept()

    def mouseReleaseEvent(self, event):
        self._view.finish_handle_drag(event.scenePos())
        event.accept()


class PageView(QGraphicsView):
    """Shows one page of the document and edits the markups on it."""

    edited = Signal()
    message = Signal(str)
    selection = Signal()
    text_edit_requested = Signal(int)

    def __init__(self, document: PdfDocument, parent=None):
        super().__init__(parent)
        self.document = document
        self.index = 0
        self.zoom = 1.0
        self.mode = SELECT
        self._page_item: Optional[QGraphicsPixmapItem] = None
        self._draft: Optional[QGraphicsRectItem] = None
        self._preview: Optional[QGraphicsItem] = None
        self._handles: list[HandleItem] = []
        self._groups: dict[int, list[int]] = {}
        self._editor: Optional[InlineText] = None
        self._drawn_zoom = 1.0
        self._anchor: Optional[tuple[QPointF, QPointF]] = None
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(SETTLE_MS)
        self._settle.timeout.connect(self._redraw_at_zoom)
        self._dragging: Optional[HandleItem] = None
        self._origin = QPointF()
        self._syncing = False
        self.setScene(QGraphicsScene(self))
        self.setBackgroundBrush(QBrush(CANVAS_COLOUR))
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setAlignment(Qt.AlignCenter)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.NoAnchor)

    # ---------------------------------------------------------------- drawing

    def show_page(self, index: int, keep: int = 0) -> None:
        """Rebuild the scene for ``index``, or empty it if there is no page."""
        scene = self.scene()
        self._clear_handles()
        self._editor = None
        scene.clear()
        self._page_item = None
        self._draft = self._preview = None
        if self.document.is_empty:
            self.index = 0
            scene.setSceneRect(QRectF(0, 0, 1, 1))
            return
        self.index = min(max(index, 0), self.document.page_count - 1)
        self._drawn_zoom = self.zoom

        raster = self.document.render_page(self.index, self.zoom)
        if raster is None:
            page = self._unreadable_page()
            self.message.emit(f"Page {self.index + 1} could not be drawn.")
        else:
            page = to_pixmap(raster)
        self._page_item = scene.addPixmap(page)
        self._page_item.setZValue(0)
        bounds = QRectF(0, 0, page.width(), page.height())
        frame = scene.addRect(bounds, QPen(QColor("#2f3640")), QBrush(Qt.NoBrush))
        frame.setZValue(1)
        scene.setSceneRect(bounds.adjusted(-PAPER_MARGIN, -PAPER_MARGIN,
                                           PAPER_MARGIN, PAPER_MARGIN))
        if raster is None:
            return

        movable = self.mode == SELECT
        self._groups = {}
        # One walk of the page draws every markup: asking for them one at a
        # time re-walks the annotation list for each and turns quadratic.
        drawn_markups = self.document.markups_with_rasters(self.index, self.zoom)
        self._groups = self._group_map([markup for markup, _ in drawn_markups])
        for markup, drawn in drawn_markups:
            if drawn is None:
                continue
            item = MarkupItem(self, markup, to_pixmap(drawn),
                              QPointF(drawn.x, drawn.y), bounds)
            item.setFlag(QGraphicsItem.ItemIsMovable, movable)
            item.setFlag(QGraphicsItem.ItemIsSelectable, movable)
            scene.addItem(item)
            if markup.xref == keep:
                item.setSelected(True)

    def refresh(self, keep: int = 0) -> None:
        self.show_page(self.index, keep)

    def _unreadable_page(self) -> QPixmap:
        """A page that will not render still needs to take up its own space."""
        width, height = self.document.page_size(self.index)
        pixmap = QPixmap(max(int(width * self.zoom), 1), max(int(height * self.zoom), 1))
        pixmap.fill(BROKEN_PAGE_COLOUR)
        return pixmap

    @staticmethod
    def _group_map(markups: list[Markup]) -> dict[int, list[int]]:
        """Which markups move together, worked out once per page.

        The leader of a group carries no mark of its own — the members point at
        it — so membership has to be read from the whole page at once rather
        than from any single markup.
        """
        by_leader: dict[int, list[int]] = {}
        for markup in markups:
            # A leader files itself under itself, so the list it ends up with
            # holds the whole group — unless its members point off the page,
            # in which case there is no group to speak of.
            by_leader.setdefault(markup.leader or markup.xref, []).append(markup.xref)
        groups: dict[int, list[int]] = {}
        for members in by_leader.values():
            if len(members) > 1:
                for xref in members:
                    groups[xref] = members
        return groups

    def group_of(self, xref: int) -> list[int]:
        """Every markup that moves when this one does, itself included."""
        return self._groups.get(xref, [xref])

    def markup_items(self) -> list[MarkupItem]:
        return [item for item in self.scene().items() if isinstance(item, MarkupItem)]

    def selected_items(self) -> list[MarkupItem]:
        return [item for item in self.markup_items() if item.isSelected()]

    # ------------------------------------------------------------------- zoom

    def set_zoom(self, zoom: float, keep: int = 0) -> None:
        zoom = min(max(zoom, MIN_ZOOM), MAX_ZOOM)
        if abs(zoom - self.zoom) < 1e-6:
            return                      # no redraw for a zoom that did not move
        self.zoom = zoom
        self._settle.stop()
        self.setTransform(QTransform())
        self.refresh(keep)

    def zoom_in(self) -> None:
        self.zoom_by(ZOOM_STEP, self.viewport().rect().center())

    def zoom_out(self) -> None:
        self.zoom_by(1 / ZOOM_STEP, self.viewport().rect().center())

    def zoom_by(self, factor: float, anchor) -> None:
        """Zoom about a point in the viewport, leaving what is under it still.

        Re-rendering a large sheet takes long enough that doing it on every
        click of the wheel is a stutter, so the picture already on screen is
        scaled at once — which is instant, and slightly soft — and the page is
        redrawn properly once the wheel stops. The point under the pointer is
        held throughout, across the scaling and across the redraw.
        """
        if self.document.is_empty:
            return
        anchor = QPointF(anchor)
        page_point = self.mapToScene(anchor.toPoint()) / self._drawn_zoom
        zoom = min(max(self.zoom * factor, MIN_ZOOM), MAX_ZOOM)
        if abs(zoom - self.zoom) < 1e-6:
            return
        self.zoom = zoom
        self._anchor = (page_point, anchor)
        self._scale_preview()
        self._settle.start()

    def _scale_preview(self) -> None:
        """Stand the page up at the new zoom by scaling what is already drawn."""
        scale = self.zoom / self._drawn_zoom
        self.setTransform(QTransform.fromScale(scale, scale))
        self._hold_anchor()

    def _redraw_at_zoom(self) -> None:
        """Draw the page properly at the zoom the wheel left it on."""
        selected = self.selected_items()
        self.setTransform(QTransform())
        self.refresh(selected[0].xref if len(selected) == 1 else 0)
        self._hold_anchor()
        self._anchor = None

    def _hold_anchor(self) -> None:
        """Put the page point that was under the pointer back under it."""
        if self._anchor is None:
            return
        page_point, viewport_point = self._anchor
        target = QPointF(page_point.x() * self._drawn_zoom,
                         page_point.y() * self._drawn_zoom)
        drift = self.mapFromScene(target) - viewport_point.toPoint()
        self.horizontalScrollBar().setValue(
            self.horizontalScrollBar().value() + drift.x())
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().value() + drift.y())

    def zoom_to_fit(self, index: Optional[int] = None) -> float:
        """The zoom at which a page fits the viewport."""
        if self.document.is_empty:
            return self.zoom
        width, height = self.document.page_size(self.index if index is None else index)
        available = self.viewport().size()
        margin = 2 * PAPER_MARGIN + 4
        return min((available.width() - margin) / max(width, 1.0),
                   (available.height() - margin) / max(height, 1.0))

    def fit_page(self) -> None:
        self.set_zoom(self.zoom_to_fit())

    def show_fitted(self, index: int) -> None:
        """Show a page at the zoom that fits it, drawing it only once.

        Setting the zoom and then showing the page would render it twice, which
        on a large drawing sheet is a second of the user's time for nothing.
        """
        self.index = index
        self.zoom = min(max(self.zoom_to_fit(index), MIN_ZOOM), MAX_ZOOM)
        self.show_page(index)

    # ------------------------------------------------------------------ tools

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        selectable = mode == SELECT
        for item in self.markup_items():
            item.setFlag(QGraphicsItem.ItemIsMovable, selectable)
            item.setFlag(QGraphicsItem.ItemIsSelectable, selectable)
            if not selectable:
                item.setSelected(False)
        self.setDragMode(QGraphicsView.RubberBandDrag if selectable
                         else QGraphicsView.NoDrag)
        self.viewport().setCursor(Qt.ArrowCursor if selectable else Qt.CrossCursor)

    # -------------------------------------------------------------- selection

    def selection_changed(self) -> None:
        """Keep a group whole, and put the handles on what is selected."""
        if self._syncing:
            return
        self._syncing = True
        try:
            chosen = self.selected_items()
            if len(chosen) == 1:
                # A markup in a group never moves alone.
                members = set(self.group_of(chosen[0].xref))
                if len(members) > 1:
                    for item in self.markup_items():
                        if item.xref in members:
                            item.setSelected(True)
                    chosen = self.selected_items()
            self._place_handles(chosen)
        finally:
            self._syncing = False
        self.selection.emit()

    def _clear_handles(self) -> None:
        for handle in self._handles:
            if handle.scene() is not None:
                self.scene().removeItem(handle)
        self._handles = []

    def _place_handles(self, chosen: list[MarkupItem]) -> None:
        """Handles belong to one markup at a time — a group moves, it does not
        reshape."""
        self._clear_handles()
        if len(chosen) != 1 or self.mode != SELECT:
            return
        item = chosen[0]
        if item.markup.resizable and len(self.group_of(item.xref)) == 1:
            box = item.sceneBoundingRect()
            for role, fx, fy in CORNERS:
                self._add_handle(item.markup, role,
                                 QPointF(box.left() + box.width() * fx,
                                         box.top() + box.height() * fy),
                                 SELECTION_COLOUR)
        for number, (x, y) in enumerate(item.markup.callout):
            self._add_handle(item.markup, f"callout{number}",
                             QPointF(x * self.zoom, y * self.zoom), CALLOUT_COLOUR)

    def _add_handle(self, markup: Markup, role: str, position: QPointF,
                    colour: QColor) -> None:
        handle = HandleItem(self, markup, role, position, colour)
        self.scene().addItem(handle)
        self._handles.append(handle)

    # ------------------------------------------------------------------ edits

    def edit_text(self, xref: int) -> None:
        """Open an editor on the page, over the markup, at the size it is."""
        item = next((one for one in self.markup_items() if one.xref == xref), None)
        if item is None or not item.markup.editable_text:
            return
        self.close_editor()
        box = item.sceneBoundingRect()
        if box.width() < MIN_EDITOR_SIZE or box.height() < MIN_EDITOR_SIZE:
            # A sticky note is an icon barely bigger than the cursor, so its
            # words get a box of their own beside it rather than inside it.
            box = QRectF(box.left(), box.top(), NOTE_EDITOR_WIDTH * self.zoom,
                         NOTE_EDITOR_HEIGHT * self.zoom)
        self._editor = InlineText(item.markup.text, box, EDITOR_POINT_SIZE * self.zoom,
                                  lambda text, x=xref: self._text_edited(x, text))
        self.scene().addItem(self._editor)
        self._editor.take_focus()

    @property
    def editing(self) -> bool:
        return self._editor is not None

    def close_editor(self) -> None:
        if self._editor is not None:
            editor, self._editor = self._editor, None
            if editor.scene() is not None:
                self.scene().removeItem(editor)

    def _text_edited(self, xref: int, text: Optional[str]) -> None:
        self.close_editor()
        if text is None:
            self.message.emit("Text left as it was.")
            return
        if self.document.set_text(self.index, xref, text):
            self.refresh(xref)
            self.message.emit("Text updated.")
            self.edited.emit()
        else:
            self.message.emit("This markup's text cannot be changed.")

    def commit_moves(self) -> None:
        """Write every finished drag back into the document."""
        moved = [(item, item.pos() - item.home) for item in self.markup_items()
                 if item.pos() != item.home]
        if not moved:
            return
        # One step, so undo takes a whole group back rather than one markup of
        # it at a time.
        shifts = {item.xref: (shift.x() / self.zoom, shift.y() / self.zoom)
                  for item, shift in moved}
        if not self.document.move_markups(self.index, shifts):
            for item, _ in moved:
                item.setPos(item.home)
            self.message.emit("This markup cannot be moved.")
            return
        for item, _ in moved:
            item.home = QPointF(item.pos())
        count = len(moved)
        self.message.emit(f"Moved {count} markup{'s' if count > 1 else ''}.")
        self._place_handles(self.selected_items())
        self.edited.emit()

    def begin_handle_drag(self, handle: HandleItem) -> None:
        self._dragging = handle
        self._preview = None

    def drag_handle(self, scene_point: QPointF) -> None:
        if self._dragging is None:
            return
        point = self._clamp(scene_point)
        if self._preview is not None:
            self.scene().removeItem(self._preview)
            self._preview = None
        pen = QPen(CALLOUT_COLOUR if self._dragging.role.startswith("callout")
                   else SELECTION_COLOUR, 1.2, Qt.DashLine)
        pen.setCosmetic(True)
        if self._dragging.role.startswith("callout"):
            path = QPainterPath()
            path.addPolygon(QPolygonF(self._callout_preview(self._dragging, point)))
            self._preview = QGraphicsPathItem(path)
            self._preview.setPen(pen)
        else:
            self._preview = QGraphicsRectItem(self._resize_preview(self._dragging, point))
            self._preview.setPen(pen)
            self._preview.setBrush(Qt.NoBrush)
        self._preview.setZValue(35)
        self.scene().addItem(self._preview)

    def finish_handle_drag(self, scene_point: QPointF) -> None:
        handle, self._dragging = self._dragging, None
        if self._preview is not None:
            self.scene().removeItem(self._preview)
            self._preview = None
        if handle is None:
            return
        point = self._clamp(scene_point)
        if handle.role.startswith("callout"):
            points = [(p.x() / self.zoom, p.y() / self.zoom)
                      for p in self._callout_preview(handle, point)]
            ok = self.document.set_callout(self.index, handle.markup.xref, points)
            self.message.emit("Callout reshaped." if ok
                              else "This callout cannot be reshaped.")
        else:
            box = self._resize_preview(handle, point)
            ok = self.document.resize_markup(self.index, handle.markup.xref,
                                             (box.left() / self.zoom, box.top() / self.zoom,
                                              box.right() / self.zoom, box.bottom() / self.zoom))
            self.message.emit("Markup resized." if ok
                              else "This markup cannot be resized.")
        if ok:
            self.refresh(handle.markup.xref)
            self.edited.emit()

    def _resize_preview(self, handle: HandleItem, point: QPointF) -> QRectF:
        """The rectangle the markup would take, with this handle at ``point``."""
        markup = handle.markup
        box = QRectF(QPointF(markup.x0 * self.zoom, markup.y0 * self.zoom),
                     QPointF(markup.x1 * self.zoom, markup.y1 * self.zoom))
        role = handle.role
        if "n" in role:
            box.setTop(point.y())
        if "s" in role:
            box.setBottom(point.y())
        if "w" in role:
            box.setLeft(point.x())
        if "e" in role:
            box.setRight(point.x())
        return box.normalized()

    def _callout_preview(self, handle: HandleItem, point: QPointF) -> list[QPointF]:
        """The leader line with the dragged point moved to ``point``."""
        markup = handle.markup
        moved = int(handle.role.removeprefix("callout"))
        return [point if number == moved else QPointF(x * self.zoom, y * self.zoom)
                for number, (x, y) in enumerate(markup.callout)]

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
                try:
                    self.document.add_rectangle(self.index, (points.left(), points.top(),
                                                             points.right(), points.bottom()))
                except DocumentError as exc:
                    self.message.emit(str(exc))
                    return
                self.refresh()
                self.message.emit("Rectangle added.")
                self.edited.emit()
            else:
                self.message.emit("Drag to draw a rectangle.")
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            step = ZOOM_STEP if event.angleDelta().y() > 0 else 1 / ZOOM_STEP
            self.zoom_by(step, event.position())
            event.accept()
            return
        super().wheelEvent(event)

    def _clamp(self, point: QPointF) -> QPointF:
        """Keep a dragged point inside the page."""
        if self._page_item is None:
            return point
        bounds = self._page_item.boundingRect()
        return QPointF(min(max(point.x(), bounds.left()), bounds.right()),
                       min(max(point.y(), bounds.top()), bounds.bottom()))
