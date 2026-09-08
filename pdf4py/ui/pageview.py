"""The page canvas: continuous vertical scroll of all pages with markup overlays.

Pages are stacked vertically in a single scene with gaps between them, forming
one continuous scroll like a PDF reader. Markups are drawn as separate items so
each one can be picked up, resized and reshaped. Zooming re-renders pages
rather than scaling the view, keeping text crisp.
"""
from __future__ import annotations

import math
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

# Tool modes
SELECT = "select"
RECTANGLE = "rectangle"
LINE = "line"
ARROW = "arrow"
ELLIPSE = "ellipse"
POLYGON = "polygon"
CLOUD = "cloud"
INK = "ink"
HIGHLIGHT = "highlight"
TEXT = "text"
NOTE = "note"

ALL_MODES = (SELECT, RECTANGLE, LINE, ARROW, ELLIPSE, POLYGON, CLOUD,
             INK, HIGHLIGHT, TEXT, NOTE)

# Two-point tools: press-drag-release
TWO_POINT_MODES = {RECTANGLE, LINE, ARROW, ELLIPSE, CLOUD, HIGHLIGHT, TEXT}

MIN_ZOOM = 0.1
MAX_ZOOM = 8.0
ZOOM_STEP = 1.25

SETTLE_MS = 120

MIN_DRAW_POINTS = 3.0

PAGE_GAP = 20
PAPER_MARGIN = 24
CANVAS_COLOUR = QColor("#5a5f66")
SELECTION_COLOUR = QColor("#1a73e8")
GROUP_COLOUR = QColor("#7a4fd6")
DRAFT_COLOUR = QColor("#d62828")
CALLOUT_COLOUR = QColor("#e08000")
BROKEN_PAGE_COLOUR = QColor("#e8e2e2")

HANDLE_SIZE = 8.0

MIN_EDITOR_SIZE = 40.0
NOTE_EDITOR_WIDTH = 180.0
NOTE_EDITOR_HEIGHT = 70.0
EDITOR_POINT_SIZE = 10.0

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
        self.page_index = markup.page_index
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
    """Continuous-scroll view of all pages with markup editing."""

    edited = Signal()
    message = Signal(str)
    selection = Signal()
    page_changed = Signal(int)

    def __init__(self, document: PdfDocument, parent=None):
        super().__init__(parent)
        self.document = document
        self.index = 0
        self.zoom = 1.0
        self.mode = SELECT
        self._page_items: list[QGraphicsPixmapItem] = []
        self._page_rects: list[QRectF] = []
        self._draft: Optional[QGraphicsItem] = None
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
        self._origin_page = 0
        self._syncing = False
        # For ink drawing
        self._ink_points: list[QPointF] = []
        self._ink_path_item: Optional[QGraphicsPathItem] = None
        # For polygon drawing
        self._polygon_points: list[QPointF] = []
        self._polygon_preview: Optional[QGraphicsPathItem] = None
        self.setScene(QGraphicsScene(self))
        self.setBackgroundBrush(QBrush(CANVAS_COLOUR))
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

    def verticalScrollBar(self):
        return super().verticalScrollBar()

    # ---------------------------------------------------------------- drawing

    def show_page(self, index: int, keep: int = 0) -> None:
        """Rebuild the entire scene with all pages stacked vertically."""
        self._syncing = True
        scene = self.scene()
        self._clear_handles()
        self._editor = None
        scene.clear()
        self._page_items = []
        self._page_rects = []
        self._draft = None
        self._preview = None
        self._ink_points = []
        self._ink_path_item = None
        self._polygon_points = []
        self._polygon_preview = None

        if self.document.is_empty:
            self.index = 0
            scene.setSceneRect(QRectF(0, 0, 1, 1))
            self._syncing = False
            return

        self.index = min(max(index, 0), self.document.page_count - 1)
        self._drawn_zoom = self.zoom

        max_width = 0.0
        for i in range(self.document.page_count):
            w, h = self.document.page_size(i)
            max_width = max(max_width, w * self.zoom)

        y_offset = PAPER_MARGIN
        all_groups: dict[int, list[int]] = {}

        for page_idx in range(self.document.page_count):
            raster = self.document.render_page(page_idx, self.zoom)
            if raster is None:
                page_pixmap = self._unreadable_page(page_idx)
            else:
                page_pixmap = to_pixmap(raster)

            pw, ph = page_pixmap.width(), page_pixmap.height()
            x_offset = PAPER_MARGIN + (max_width - pw) / 2

            page_item = scene.addPixmap(page_pixmap)
            page_item.setPos(x_offset, y_offset)
            page_item.setZValue(0)
            self._page_items.append(page_item)

            page_bounds = QRectF(x_offset, y_offset, pw, ph)
            self._page_rects.append(page_bounds)

            frame = scene.addRect(page_bounds, QPen(QColor("#2f3640")), QBrush(Qt.NoBrush))
            frame.setZValue(1)

            if raster is not None:
                movable = self.mode == SELECT
                drawn_markups = self.document.markups_with_rasters(page_idx, self.zoom)
                page_markups = [m for m, _ in drawn_markups]
                page_groups = self._group_map(page_markups)
                all_groups.update(page_groups)

                for markup, drawn in drawn_markups:
                    if drawn is None:
                        continue
                    item = MarkupItem(self, markup, to_pixmap(drawn),
                                      QPointF(x_offset + drawn.x, y_offset + drawn.y),
                                      page_bounds)
                    item.setFlag(QGraphicsItem.ItemIsMovable, movable)
                    item.setFlag(QGraphicsItem.ItemIsSelectable, movable)
                    scene.addItem(item)
                    if markup.xref == keep:
                        item.setSelected(True)

            y_offset += ph + PAGE_GAP

        self._groups = all_groups

        total_height = y_offset - PAGE_GAP + PAPER_MARGIN
        total_width = max_width + 2 * PAPER_MARGIN
        scene.setSceneRect(QRectF(0, 0, total_width, total_height))

        target_index = self.index
        if target_index < len(self._page_rects):
            self._scroll_to_page(target_index)
        self.index = target_index
        self._syncing = False

    def refresh(self, keep: int = 0) -> None:
        self.show_page(self.index, keep)

    def _unreadable_page(self, page_idx: int) -> QPixmap:
        width, height = self.document.page_size(page_idx)
        pixmap = QPixmap(max(int(width * self.zoom), 1), max(int(height * self.zoom), 1))
        pixmap.fill(BROKEN_PAGE_COLOUR)
        return pixmap

    def _scroll_to_page(self, index: int) -> None:
        if 0 <= index < len(self._page_rects):
            rect = self._page_rects[index]
            self.ensureVisible(rect, 0, 50)

    @staticmethod
    def _group_map(markups: list[Markup]) -> dict[int, list[int]]:
        by_leader: dict[int, list[int]] = {}
        for markup in markups:
            by_leader.setdefault(markup.leader or markup.xref, []).append(markup.xref)
        groups: dict[int, list[int]] = {}
        for members in by_leader.values():
            if len(members) > 1:
                for xref in members:
                    groups[xref] = members
        return groups

    def group_of(self, xref: int) -> list[int]:
        return self._groups.get(xref, [xref])

    def markup_items(self) -> list[MarkupItem]:
        return [item for item in self.scene().items() if isinstance(item, MarkupItem)]

    def selected_items(self) -> list[MarkupItem]:
        return [item for item in self.markup_items() if item.isSelected()]

    def page_at_point(self, scene_point: QPointF) -> int:
        """Which page does a scene point fall on?"""
        for i, rect in enumerate(self._page_rects):
            if rect.contains(scene_point):
                return i
        if self._page_rects:
            best = 0
            best_dist = float("inf")
            for i, rect in enumerate(self._page_rects):
                dist = abs(scene_point.y() - rect.center().y())
                if dist < best_dist:
                    best_dist = dist
                    best = i
            return best
        return self.index

    def scene_to_page(self, scene_point: QPointF, page_idx: int
                      ) -> tuple[float, float]:
        """Convert scene coords to page coords (in display points)."""
        if 0 <= page_idx < len(self._page_rects):
            rect = self._page_rects[page_idx]
            return ((scene_point.x() - rect.x()) / self.zoom,
                    (scene_point.y() - rect.y()) / self.zoom)
        return scene_point.x() / self.zoom, scene_point.y() / self.zoom

    def page_to_scene(self, x: float, y: float, page_idx: int) -> QPointF:
        """Convert page coords to scene coords."""
        if 0 <= page_idx < len(self._page_rects):
            rect = self._page_rects[page_idx]
            return QPointF(rect.x() + x * self.zoom, rect.y() + y * self.zoom)
        return QPointF(x * self.zoom, y * self.zoom)

    # ------------------------------------------------------------------- zoom

    def set_zoom(self, zoom: float, keep: int = 0) -> None:
        zoom = min(max(zoom, MIN_ZOOM), MAX_ZOOM)
        if abs(zoom - self.zoom) < 1e-6:
            return
        self.zoom = zoom
        self._settle.stop()
        self.setTransform(QTransform())
        self.refresh(keep)

    def zoom_in(self) -> None:
        self.zoom_by(ZOOM_STEP, self.viewport().rect().center())

    def zoom_out(self) -> None:
        self.zoom_by(1 / ZOOM_STEP, self.viewport().rect().center())

    def zoom_by(self, factor: float, anchor) -> None:
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
        scale = self.zoom / self._drawn_zoom
        self.setTransform(QTransform.fromScale(scale, scale))
        self._hold_anchor()

    def _redraw_at_zoom(self) -> None:
        selected = self.selected_items()
        self.setTransform(QTransform())
        self.refresh(selected[0].xref if len(selected) == 1 else 0)
        self._hold_anchor()
        self._anchor = None

    def _hold_anchor(self) -> None:
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
        self.index = index
        self.zoom = min(max(self.zoom_to_fit(index), MIN_ZOOM), MAX_ZOOM)
        self.show_page(index)

    # ------------------------------------------------------------------ tools

    def set_mode(self, mode: str) -> None:
        self._finish_polygon()
        self._finish_ink()
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
        if self._syncing:
            return
        self._syncing = True
        try:
            chosen = self.selected_items()
            if len(chosen) == 1:
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
            page_scene = self.page_to_scene(x, y, item.page_index)
            self._add_handle(item.markup, f"callout{number}",
                             page_scene, CALLOUT_COLOUR)

    def _add_handle(self, markup: Markup, role: str, position: QPointF,
                    colour: QColor) -> None:
        handle = HandleItem(self, markup, role, position, colour)
        self.scene().addItem(handle)
        self._handles.append(handle)

    # ------------------------------------------------------------------ edits

    def edit_text(self, xref: int) -> None:
        item = next((one for one in self.markup_items() if one.xref == xref), None)
        if item is None or not item.markup.editable_text:
            return
        self.close_editor()
        box = item.sceneBoundingRect()
        if box.width() < MIN_EDITOR_SIZE or box.height() < MIN_EDITOR_SIZE:
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
        item = next((one for one in self.markup_items() if one.xref == xref), None)
        page_idx = item.page_index if item else self.index
        if self.document.set_text(page_idx, xref, text):
            self.refresh(xref)
            self.message.emit("Text updated.")
            self.edited.emit()
        else:
            self.message.emit("This markup's text cannot be changed.")

    def commit_moves(self) -> None:
        moved = [(item, item.pos() - item.home) for item in self.markup_items()
                 if item.pos() != item.home]
        if not moved:
            return
        by_page: dict[int, dict[int, tuple[float, float]]] = {}
        for item, shift in moved:
            page_idx = item.page_index
            by_page.setdefault(page_idx, {})[item.xref] = (
                shift.x() / self.zoom, shift.y() / self.zoom)
        all_ok = True
        for page_idx, shifts in by_page.items():
            if not self.document.move_markups(page_idx, shifts):
                all_ok = False
        if not all_ok:
            for item, _ in moved:
                item.setPos(item.home)
            self.message.emit("Some markups cannot be moved.")
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
        page_idx = handle.markup.page_index
        if handle.role.startswith("callout"):
            points = [self.scene_to_page(p, page_idx)
                      for p in self._callout_preview(handle, point)]
            ok = self.document.set_callout(page_idx, handle.markup.xref, points)
            self.message.emit("Callout reshaped." if ok
                              else "This callout cannot be reshaped.")
        else:
            box = self._resize_preview(handle, point)
            x0, y0 = self.scene_to_page(QPointF(box.left(), box.top()), page_idx)
            x1, y1 = self.scene_to_page(QPointF(box.right(), box.bottom()), page_idx)
            ok = self.document.resize_markup(page_idx, handle.markup.xref,
                                             (x0, y0, x1, y1))
            self.message.emit("Markup resized." if ok
                              else "This markup cannot be resized.")
        if ok:
            self.refresh(handle.markup.xref)
            self.edited.emit()

    def _resize_preview(self, handle: HandleItem, point: QPointF) -> QRectF:
        markup = handle.markup
        page_idx = markup.page_index
        tl = self.page_to_scene(markup.x0, markup.y0, page_idx)
        br = self.page_to_scene(markup.x1, markup.y1, page_idx)
        box = QRectF(tl, br)
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
        markup = handle.markup
        moved = int(handle.role.removeprefix("callout"))
        result = []
        for number, (x, y) in enumerate(markup.callout):
            if number == moved:
                result.append(point)
            else:
                result.append(self.page_to_scene(x, y, markup.page_index))
        return result

    # ------------------------------------------------------------------ events

    def _on_scroll(self) -> None:
        """Track which page is visible as the user scrolls."""
        if self._syncing:
            return
        center = self.mapToScene(self.viewport().rect().center())
        new_index = self.page_at_point(center)
        if new_index != self.index:
            self.index = new_index
            self.page_changed.emit(self.index)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or self.mode == SELECT:
            super().mousePressEvent(event)
            return

        scene_pos = self.mapToScene(event.position().toPoint())
        page_idx = self.page_at_point(scene_pos)

        if self.mode == NOTE:
            px, py = self.scene_to_page(scene_pos, page_idx)
            try:
                self.document.add_note(page_idx, (px, py))
            except DocumentError as exc:
                self.message.emit(str(exc))
                return
            self.refresh()
            self.message.emit("Note added.")
            self.edited.emit()
            return

        if self.mode == INK:
            self._origin_page = page_idx
            self._ink_points = [scene_pos]
            return

        if self.mode == POLYGON:
            if not self._polygon_points:
                self._origin_page = page_idx
            self._polygon_points.append(scene_pos)
            self._update_polygon_preview()
            return

        if self.mode in TWO_POINT_MODES:
            self._origin = self._clamp(scene_pos)
            self._origin_page = page_idx
            pen = QPen(DRAFT_COLOUR, 1.0, Qt.DashLine)
            pen.setCosmetic(True)
            if self.mode in (LINE, ARROW):
                path = QPainterPath()
                path.moveTo(self._origin)
                path.lineTo(self._origin)
                self._draft = QGraphicsPathItem(path)
                self._draft.setPen(pen)
            elif self.mode == ELLIPSE:
                self._draft = self.scene().addEllipse(
                    QRectF(self._origin, self._origin), pen)
            else:
                self._draft = self.scene().addRect(
                    QRectF(self._origin, self._origin), pen)
            if not isinstance(self._draft, QGraphicsRectItem) or self.mode in (LINE, ARROW, ELLIPSE):
                self.scene().addItem(self._draft)
            self._draft.setZValue(20)
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        scene_pos = self.mapToScene(event.position().toPoint())

        if self._ink_points:
            self._ink_points.append(scene_pos)
            self._update_ink_preview()
            return

        if self._draft is not None:
            corner = self._clamp(scene_pos)
            if self.mode in (LINE, ARROW):
                if self._draft.scene() is not None:
                    self.scene().removeItem(self._draft)
                path = QPainterPath()
                path.moveTo(self._origin)
                path.lineTo(corner)
                pen = QPen(DRAFT_COLOUR, 1.0, Qt.DashLine)
                pen.setCosmetic(True)
                self._draft = QGraphicsPathItem(path)
                self._draft.setPen(pen)
                self._draft.setZValue(20)
                self.scene().addItem(self._draft)
            elif self.mode == ELLIPSE and isinstance(self._draft, QGraphicsRectItem):
                pass
            elif isinstance(self._draft, QGraphicsRectItem):
                self._draft.setRect(QRectF(self._origin, corner).normalized())
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        # Ink: finish stroke
        if self._ink_points and event.button() == Qt.LeftButton:
            self._finish_ink()
            return

        # Two-point tools
        if self._draft is not None and event.button() == Qt.LeftButton:
            scene_pos = self.mapToScene(event.position().toPoint())
            corner = self._clamp(scene_pos)
            if self._draft.scene() is not None:
                self.scene().removeItem(self._draft)
            self._draft = None

            page_idx = self._origin_page
            ox, oy = self.scene_to_page(self._origin, page_idx)
            cx, cy = self.scene_to_page(corner, page_idx)

            try:
                if self.mode == RECTANGLE:
                    if abs(cx - ox) >= MIN_DRAW_POINTS and abs(cy - oy) >= MIN_DRAW_POINTS:
                        self.document.add_rectangle(page_idx, (ox, oy, cx, cy))
                        self.message.emit("Rectangle added.")
                    else:
                        self.message.emit("Drag to draw a rectangle.")
                        return
                elif self.mode == LINE:
                    dist = math.hypot(cx - ox, cy - oy)
                    if dist >= MIN_DRAW_POINTS:
                        self.document.add_line(page_idx, (ox, oy), (cx, cy))
                        self.message.emit("Line added.")
                    else:
                        self.message.emit("Drag to draw a line.")
                        return
                elif self.mode == ARROW:
                    dist = math.hypot(cx - ox, cy - oy)
                    if dist >= MIN_DRAW_POINTS:
                        self.document.add_line(page_idx, (ox, oy), (cx, cy),
                                               end_style="arrow")
                        self.message.emit("Arrow added.")
                    else:
                        self.message.emit("Drag to draw an arrow.")
                        return
                elif self.mode == ELLIPSE:
                    if abs(cx - ox) >= MIN_DRAW_POINTS and abs(cy - oy) >= MIN_DRAW_POINTS:
                        self.document.add_ellipse(page_idx, (ox, oy, cx, cy))
                        self.message.emit("Ellipse added.")
                    else:
                        self.message.emit("Drag to draw an ellipse.")
                        return
                elif self.mode == CLOUD:
                    if abs(cx - ox) >= MIN_DRAW_POINTS and abs(cy - oy) >= MIN_DRAW_POINTS:
                        self.document.add_cloud(page_idx, (ox, oy, cx, cy))
                        self.message.emit("Cloud added.")
                    else:
                        self.message.emit("Drag to draw a cloud.")
                        return
                elif self.mode == HIGHLIGHT:
                    if abs(cx - ox) >= MIN_DRAW_POINTS and abs(cy - oy) >= MIN_DRAW_POINTS:
                        self.document.add_highlight(page_idx, (ox, oy, cx, cy))
                        self.message.emit("Highlight added.")
                    else:
                        self.message.emit("Drag to highlight.")
                        return
                elif self.mode == TEXT:
                    if abs(cx - ox) >= MIN_DRAW_POINTS and abs(cy - oy) >= MIN_DRAW_POINTS:
                        self.document.add_freetext(page_idx, (ox, oy, cx, cy))
                        self.message.emit("Text box added.")
                    else:
                        self.message.emit("Drag to place a text box.")
                        return
            except DocumentError as exc:
                self.message.emit(str(exc))
                return

            self.refresh()
            self.edited.emit()
            return

        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.mode == POLYGON and self._polygon_points:
            self._finish_polygon()
            return
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            step = ZOOM_STEP if event.angleDelta().y() > 0 else 1 / ZOOM_STEP
            self.zoom_by(step, event.position())
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if self._polygon_points:
                self._cancel_polygon()
                return
            if self._ink_points:
                self._ink_points = []
                if self._ink_path_item and self._ink_path_item.scene():
                    self.scene().removeItem(self._ink_path_item)
                self._ink_path_item = None
                return
        super().keyPressEvent(event)

    # ---------------------------------------------------------- ink helpers

    def _update_ink_preview(self) -> None:
        if self._ink_path_item and self._ink_path_item.scene():
            self.scene().removeItem(self._ink_path_item)
        if len(self._ink_points) < 2:
            return
        path = QPainterPath()
        path.moveTo(self._ink_points[0])
        for pt in self._ink_points[1:]:
            path.lineTo(pt)
        pen = QPen(DRAFT_COLOUR, 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        pen.setCosmetic(True)
        self._ink_path_item = QGraphicsPathItem(path)
        self._ink_path_item.setPen(pen)
        self._ink_path_item.setZValue(20)
        self.scene().addItem(self._ink_path_item)

    def _finish_ink(self) -> None:
        if self._ink_path_item and self._ink_path_item.scene():
            self.scene().removeItem(self._ink_path_item)
        self._ink_path_item = None
        if len(self._ink_points) < 2:
            self._ink_points = []
            return
        page_idx = self._origin_page
        page_points = [self.scene_to_page(p, page_idx) for p in self._ink_points]
        self._ink_points = []
        try:
            self.document.add_ink(page_idx, [page_points])
            self.message.emit("Ink stroke added.")
            self.refresh()
            self.edited.emit()
        except DocumentError as exc:
            self.message.emit(str(exc))

    # ---------------------------------------------------------- polygon helpers

    def _update_polygon_preview(self) -> None:
        if self._polygon_preview and self._polygon_preview.scene():
            self.scene().removeItem(self._polygon_preview)
        if len(self._polygon_points) < 2:
            return
        path = QPainterPath()
        path.moveTo(self._polygon_points[0])
        for pt in self._polygon_points[1:]:
            path.lineTo(pt)
        pen = QPen(DRAFT_COLOUR, 1.0, Qt.DashLine)
        pen.setCosmetic(True)
        self._polygon_preview = QGraphicsPathItem(path)
        self._polygon_preview.setPen(pen)
        self._polygon_preview.setZValue(20)
        self.scene().addItem(self._polygon_preview)

    def _finish_polygon(self) -> None:
        if self._polygon_preview and self._polygon_preview.scene():
            self.scene().removeItem(self._polygon_preview)
        self._polygon_preview = None
        if len(self._polygon_points) < 3:
            self._polygon_points = []
            self.message.emit("A polygon needs at least 3 points.")
            return
        page_idx = self._origin_page
        page_points = [self.scene_to_page(p, page_idx) for p in self._polygon_points]
        self._polygon_points = []
        try:
            self.document.add_polygon(page_idx, page_points)
            self.message.emit("Polygon added.")
            self.refresh()
            self.edited.emit()
        except DocumentError as exc:
            self.message.emit(str(exc))

    def _cancel_polygon(self) -> None:
        if self._polygon_preview and self._polygon_preview.scene():
            self.scene().removeItem(self._polygon_preview)
        self._polygon_preview = None
        self._polygon_points = []
        self.message.emit("Polygon cancelled.")

    def _clamp(self, point: QPointF) -> QPointF:
        scene_rect = self.scene().sceneRect()
        return QPointF(min(max(point.x(), scene_rect.left()), scene_rect.right()),
                       min(max(point.y(), scene_rect.top()), scene_rect.bottom()))
