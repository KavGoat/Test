"""The interactive page canvas: tools, selection, editing and navigation."""
from __future__ import annotations

import json
import math
import os
import re
from typing import Optional

from PySide6.QtCore import (QEvent, QMimeData, QPoint, QPointF, QRectF, Qt,
                            QTimer, Signal)
from PySide6.QtGui import (QColor, QCursor, QKeyEvent, QMouseEvent, QPainter,
                           QPen, QPolygonF, QTextCursor, QTransform,
                           QWheelEvent)
from PySide6.QtWidgets import (QApplication, QCompleter, QGraphicsProxyWidget,
                               QGraphicsView, QLineEdit)

from ..core.document import MM_TO_PT
from ..core.spreadsheet import make_ref, parse_clipboard_grid
from ..core.units import parse_unit
from ..items.base import HANDLE_CURSORS, MarkupItem, build_item
from ..items.contents import ContentsItem
from ..items.mathitem import LINE_STEP, MathItem
from .scene import PageFrame, detach
from ..items.measure import CALIBRATE, DIMENSION, CountItem, MeasureItem
from ..items.media import ImageItem
from ..items.plotitem import PlotItem
from ..items.shapes import PolyItem, RectItem
from ..items.tableitem import TableItem
from ..items.text import CalloutItem, NoteItem, StampItem, TextItem, _TextBase
from . import preferences
from .commands import PageEditCommand
from .tools import (ANCHOR, CLICK, DRAG, FREE, NONE, POLY, SNAPSHOT,
                    TOOL_MAP, Tool)

MIN_ZOOM = 0.08
MAX_ZOOM = 16.0
CLICK_SLOP = 3.0
# How near the pointer has to be, in view pixels, to catch a drawn point.
SNAP_REACH = 9.0
# The shapes drawn to a size somebody cares about, and so worth measuring,
# asking an exact size for, and writing that size on.
SIZED_SHAPES = ("rect", "ellipse")
CELLS_MIME = "application/x-calcforge-cells"
FREE_MIN_STEP = 1.2


class PageView(QGraphicsView):
    """Displays one :class:`~calcforge.ui.scene.PageScene` and edits it."""

    toolFinished = Signal(str)
    statusMessage = Signal(str)
    cursorMoved = Signal(QPointF)
    zoomChanged = Signal(float)
    selectionChanged = Signal()
    itemActivated = Signal(object)
    cellChanged = Signal(object)
    documentEdited = Signal()
    pageChanged = Signal(int)

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.tool_key = "select"
        self.sticky_tool = False
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing |
                            QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAlignment(Qt.AlignCenter)

        self._mode = "idle"
        self._draft: Optional[MarkupItem] = None
        self._press_scene = QPointF()
        self._press_view = QPoint()
        self._handle_item: Optional[MarkupItem] = None
        self._handle_key = ""
        self._move_items: list[tuple[MarkupItem, QPointF]] = []
        self._snapshot: list[dict] = []
        # The selection marquee, in scene coordinates: two corners while it is
        # a rectangle, every corner while it is a lasso.
        self._marquee: list = []
        self._keep_selection = False
        self._space_pan = False
        self._pan_origin = QPoint()
        self._zoom = 1.0

        self.active_table: Optional[TableItem] = None
        self._cell_editor: Optional[QLineEdit] = None
        self._cell_proxy: Optional[QGraphicsProxyWidget] = None
        self._editing_cell: Optional[tuple[int, int]] = None
        self._unit_editor: Optional[QLineEdit] = None
        self._unit_proxy: Optional[QGraphicsProxyWidget] = None
        self._unit_target: tuple = (None, -1)
        # While a formula is being typed: the cell being pointed at, and where
        # its reference sits in the text so the next arrow key can replace it.
        self._pointing: Optional[tuple[int, int]] = None
        self._point_span: Optional[tuple[int, int]] = None
        self._completions = None
        self._completing = False
        self._live_timer = None
        self._fill_origin: Optional[tuple[int, int]] = None
        self._draw_origin: Optional[QPointF] = None
        # Ctrl held when a drag starts leaves the originals where they were.
        self._copy_on_move = False
        self._copied = False
        self._snap_marker: Optional[QPointF] = None
        # Held while a tool set's tool is in hand: something to place, or
        # properties for the next thing drawn.
        self._pending_stamp = None
        self._pending_properties: Optional[dict] = None
        self._label_editor: Optional[QLineEdit] = None
        self._label_proxy: Optional[QGraphicsProxyWidget] = None
        self._label_item = None
        self._editing_item = None

        self._last_scene_pos = QPointF(60, 60)
        # Where the next thing typed, inserted or pasted will go, and
        # what a callout is about to point at.
        self._pending_anchor: Optional[QPointF] = None
        self._shown_page = 0
        for bar in (self.verticalScrollBar(), self.horizontalScrollBar()):
            bar.valueChanged.connect(self._note_visible_page)
        self.count_subject = "Count"
        self.count_symbol = "circle"
        self.stamp_text = "APPROVED"

    # ------------------------------------------------------------------
    # basics
    # ------------------------------------------------------------------
    def document(self):
        return self.window.document

    def page(self):
        """The page being worked on — the one the view is looking at."""
        frame = self.frame()
        return frame.page if frame is not None else None

    def frame(self):
        """The page frame the current gesture belongs to."""
        window = self.window
        pages = window.document.pages
        index = max(0, min(window.current_index, len(pages) - 1))
        return pages[index].frame if pages else None

    def frame_at(self, scene_pos: QPointF):
        """The page under a point on the canvas."""
        scene = self.scene()
        return scene.frame_at(scene_pos) if scene is not None else None

    def to_page(self, scene_pos: QPointF, frame=None) -> QPointF:
        """A canvas point in the coordinates of *frame*'s page."""
        frame = frame or self.frame()
        return frame.mapFromScene(scene_pos) if frame is not None else scene_pos

    def from_page(self, page_pos: QPointF, frame=None) -> QPointF:
        frame = frame or self.frame()
        return frame.mapToScene(page_pos) if frame is not None else page_pos

    def push_command(self, command) -> None:
        self.window.undo_stack.push(command)

    def after_undo(self) -> None:
        self.close_label_editor(commit=False)
        self.close_unit_editor(commit=False)
        self.close_cell_editor(commit=False)
        self.active_table = None
        self.window.recalculate()
        self.documentEdited.emit()
        self.selectionChanged.emit()

    def begin_snapshot(self, frames=None) -> None:
        """Remember what the affected pages look like before a gesture.

        On a canvas that scrolls through the whole document, a gesture is not
        necessarily about the page the chrome calls current: the selection can
        span two pages, and a region can still be being edited on the page
        above the one now on screen. So the pages actually involved are the
        ones recorded, and only those that really changed reach the undo stack.
        """
        if frames is None:
            frames = self.involved_frames()
        self._snapshot = [(frame, frame.serialize_items()) for frame in frames]

    def involved_frames(self, *items) -> list:
        """Every page a gesture starting now could plausibly change.

        *items* names anything the caller is about to work on but that the view
        does not know about yet — the region it is one line away from opening
        for editing, say.
        """
        scene = self.scene()
        if scene is None:
            return []
        frames: list = []

        def remember(frame):
            if isinstance(frame, PageFrame) and frame not in frames:
                frames.append(frame)

        remember(self.frame())
        remember(getattr(self._editing_item, "parentItem", lambda: None)())
        if self.active_table is not None:
            remember(self.active_table.parentItem())
        for item in scene.selectedItems():
            remember(item.parentItem())
        for item in items:
            if item is not None:
                remember(item.parentItem())
        return frames

    def all_frames(self) -> list:
        scene = self.scene()
        return list(scene.frames) if scene is not None else []

    def commit_snapshot(self, text: str, coalesce: bool = False) -> None:
        """Record an edit for undo, and leave the document consistent.

        Reading order decides what resolves, so *moving* a calculation changes
        the answers just as much as retyping it does. Recalculating here means
        every committed gesture leaves the page showing the truth, rather than
        each gesture having to remember to ask for it.
        """
        if not self._snapshot:
            return
        changed = [(frame, before) for frame, before in self._snapshot
                   if frame.serialize_items() != before]
        if not changed:
            return
        self.window.recalculate()
        stack = self.window.undo_stack
        if len(changed) > 1:
            stack.beginMacro(text)
        for frame, before in changed:
            self.push_command(PageEditCommand(frame, before, frame.serialize_items(),
                                              text, on_apply=self.after_undo,
                                              coalesce=coalesce))
        if len(changed) > 1:
            stack.endMacro()
        self.documentEdited.emit()

    # ------------------------------------------------------------------
    # tools
    # ------------------------------------------------------------------
    def current_tool(self) -> Tool:
        return TOOL_MAP.get(self.tool_key, TOOL_MAP["select"])

    def set_tool(self, key: str) -> None:
        if self._mode == "lasso":
            self.cancel_marquee()
        if self._draft is not None:
            self.cancel_draft()
        self.close_unit_editor()
        self.close_cell_editor()
        self.tool_key = key if key in TOOL_MAP else "select"
        tool = self.current_tool()
        self.setCursor(self._cursor_for_tool(tool))
        self.statusMessage.emit(tool.hint or tool.label)
        if key != "select":
            self.deactivate_table()

    def _cursor_for_tool(self, tool: Tool) -> QCursor:
        if tool.key == "select":
            return QCursor(Qt.ArrowCursor)
        if tool.key == "pan":
            return QCursor(Qt.OpenHandCursor)
        if tool.mode in (DRAG, POLY, FREE):
            return QCursor(Qt.CrossCursor)
        return QCursor(Qt.PointingHandCursor)

    def finish_tool(self) -> None:
        if not self.sticky_tool:
            self._pending_properties = None
        if not self.sticky_tool and self.tool_key not in ("select", "pan"):
            self.set_tool("select")
            self.toolFinished.emit("select")

    # ------------------------------------------------------------------
    # zoom & navigation
    # ------------------------------------------------------------------
    def zoom(self) -> float:
        return self._zoom

    def set_zoom(self, factor: float, anchor_mouse: bool = False) -> None:
        factor = max(MIN_ZOOM, min(factor, MAX_ZOOM))
        if abs(factor - self._zoom) < 1e-6:
            return
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse if anchor_mouse
                                     else QGraphicsView.AnchorViewCenter)
        self._zoom = factor
        self.setTransform(QTransform().scale(factor, factor))
        self.zoomChanged.emit(factor)

    def zoom_in(self) -> None:
        self.set_zoom(self._zoom * 1.25)

    def zoom_out(self) -> None:
        self.set_zoom(self._zoom / 1.25)

    def page_scene_rect(self) -> Optional[QRectF]:
        """Where the current page sits on the canvas."""
        frame = self.frame()
        return frame.mapRectToScene(frame.page_rect()) if frame is not None else None

    def fit_page(self) -> None:
        rect = self.page_scene_rect()
        if rect is None or rect.width() <= 0 or rect.height() <= 0:
            return
        padded = rect.adjusted(-12, -12, 12, 12)
        available = self.viewport().rect()
        self.set_zoom(min(available.width() / padded.width(),
                          available.height() / padded.height()))
        self.centerOn(rect.center())

    def fit_width(self) -> None:
        rect = self.page_scene_rect()
        if rect is None or rect.width() <= 0:
            return
        self.set_zoom(max(self.viewport().width() - 26, 40) / rect.width())
        self.centerOn(rect.center().x(),
                      self.mapToScene(self.viewport().rect().center()).y())

    def go_to_page_top(self, index: int, animate: bool = False) -> None:
        """Scroll so page *index* starts at the top of the window."""
        scene = self.scene()
        if scene is None or not scene.frames:
            return
        index = max(0, min(index, len(scene.frames) - 1))
        frame = scene.frames[index]
        rect = frame.mapRectToScene(frame.page_rect())
        self.centerOn(rect.center().x(),
                      rect.top() + self.mapToScene(
                          self.viewport().rect()).boundingRect().height() / 2 - 12)

    def _note_visible_page(self, _value: int = 0) -> None:
        """Scrolling past a page boundary makes that page the current one."""
        index = self.visible_page_index()
        if index != self._shown_page:
            self._shown_page = index
            self.pageChanged.emit(index)

    def visible_page_index(self) -> int:
        """The page the reader is looking at: the one covering the middle."""
        scene = self.scene()
        if scene is None or not scene.frames:
            return 0
        middle = self.mapToScene(self.viewport().rect().center())
        return scene.index_at(middle)

    def zoom_to_selection(self) -> None:
        items = self.scene().selectedItems() if self.scene() else []
        if not items:
            return
        rect = items[0].sceneBoundingRect()
        for item in items[1:]:
            rect = rect.united(item.sceneBoundingRect())
        rect = rect.adjusted(-20, -20, 20, 20)
        available = self.viewport().rect()
        self.set_zoom(min(available.width() / max(rect.width(), 1),
                          available.height() / max(rect.height(), 1)))
        self.centerOn(rect.center())

    def wheelEvent(self, event: QWheelEvent) -> None:
        """A notch of the wheel zooms at the pointer, as Bluebeam does.

        Shift scrolls sideways, and Ctrl zooms whichever way the wheel is set,
        because that is what Ctrl does everywhere else. A trackpad sends
        pixelDelta and means panning by it, so two-finger scrolling still
        scrolls smoothly however the wheel is set. Whoever prefers the wheel
        to scroll can say so in the preferences.
        """
        pixels = event.pixelDelta()
        notches = event.angleDelta().y()
        if event.modifiers() & Qt.ShiftModifier:
            step = pixels.y() or pixels.x() or notches
            bar = self.horizontalScrollBar()
            bar.setValue(bar.value() - step)
            event.accept()
            return
        zooming = (event.modifiers() & Qt.ControlModifier
                   or (preferences.current().wheel_zooms() and pixels.isNull()))
        if zooming:
            delta = notches or pixels.y()
            if delta:
                self.set_zoom(self._zoom * (1.0015 ** delta), anchor_mouse=True)
            event.accept()
            return
        if not pixels.isNull():
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - pixels.x())
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - pixels.y())
            event.accept()
            return
        super().wheelEvent(event)

    # ------------------------------------------------------------------
    # snapping
    # ------------------------------------------------------------------
    def snap(self, point: QPointF, force: bool = False) -> QPointF:
        """Snap a point given in page coordinates."""
        settings = self.document().settings
        if not (settings.snap_to_grid or force):
            return point
        step = max(settings.grid_mm, 0.5) * MM_TO_PT
        return QPointF(round(point.x() / step) * step, round(point.y() / step) * step)

    def snap_scene(self, scene_pos: QPointF, frame=None) -> QPointF:
        """Snap a canvas point to what is already drawn, then to the grid.

        A corner of something beats the grid: lining a markup up with the
        thing it is about is what the pointer is usually trying to do. The
        grid belongs to the page, not to the canvas, so a point is taken into
        page coordinates to be snapped and brought back again.
        """
        caught = self.snap_to_item(scene_pos)
        if caught is not None:
            return caught
        frame = frame or self.frame_at(scene_pos) or self.frame()
        if frame is None:
            return self.snap(scene_pos)
        return frame.mapToScene(self.snap(frame.mapFromScene(scene_pos)))

    def snap_targets(self, frame, ignore=()) -> list:
        """The points on a page worth lining something up with.

        Corners, edge midpoints and centres of everything boxed, and every
        vertex of everything drawn as a line — including the lines that came
        in on a PDF page, once they are markups on it.
        """
        points: list[QPointF] = []
        skip = set(ignore)
        for item in frame.markups():
            if item in skip or not item.isVisible():
                continue
            points += self.points_of(item)
        return points

    @staticmethod
    def points_of(item) -> list:
        """One markup's own interesting points, in scene coordinates."""
        vertices = getattr(item, "points", None)
        if vertices:
            return [item.mapToScene(point) for point in vertices]
        rect = item.local_rect().normalized()
        if rect.isEmpty():
            return []
        return [item.mapToScene(corner) for corner in (
            rect.topLeft(), rect.topRight(), rect.bottomLeft(), rect.bottomRight(),
            rect.center(),
            QPointF(rect.center().x(), rect.top()),
            QPointF(rect.center().x(), rect.bottom()),
            QPointF(rect.left(), rect.center().y()),
            QPointF(rect.right(), rect.center().y()))]

    def snap_moved(self, items: list, delta: QPointF) -> QPointF:
        """Nudge a move so a corner of what is dragged lands on a drawn point."""
        self._snap_marker = None
        if not self.document().settings.snap_to_items or not items:
            return delta
        item, origin = items[0]
        frame = item.parentItem()
        if frame is None:
            return delta
        targets = self.snap_targets(frame, ignore={i for i, _ in items})
        if not targets:
            return delta
        shift = frame.mapToScene(origin + delta) - frame.mapToScene(item.pos())
        reach = SNAP_REACH / max(self._zoom, 0.05)
        best = None
        best_distance = reach
        for point in self.points_of(item):
            moved = point + shift
            for target in targets:
                distance = math.hypot(target.x() - moved.x(), target.y() - moved.y())
                if distance < best_distance:
                    best_distance = distance
                    best = (target - moved, target)
        if best is None:
            return delta
        offset, marker = best
        self._snap_marker = QPointF(marker)
        return delta + offset

    def snap_to_item(self, scene_pos: QPointF, ignore=()) -> Optional[QPointF]:
        """The nearest interesting point of another markup, if one is close."""
        self._snap_marker = None
        if not self.document().settings.snap_to_items:
            return None
        frame = self.frame_at(scene_pos) or self.frame()
        if frame is None:
            return None
        reach = SNAP_REACH / max(self._zoom, 0.05)
        best = None
        best_distance = reach
        for point in self.snap_targets(frame, ignore):
            distance = math.hypot(point.x() - scene_pos.x(), point.y() - scene_pos.y())
            if distance < best_distance:
                best, best_distance = point, distance
        if best is not None:
            self._snap_marker = QPointF(best)
        return best

    @staticmethod
    def constrain(anchor: QPointF, point: QPointF) -> QPointF:
        """Hold a line to 0°, 45° or 90° from where it started.

        The angles a drawing is actually made of, and the ones Shift gives you
        in every other drawing tool.
        """
        delta = point - anchor
        length = math.hypot(delta.x(), delta.y())
        if length < 1e-6:
            return QPointF(point)
        angle = math.radians(round(math.degrees(math.atan2(delta.y(), delta.x())) / 45.0) * 45.0)
        return QPointF(anchor.x() + math.cos(angle) * length,
                       anchor.y() + math.sin(angle) * length)

    # ------------------------------------------------------------------
    # mouse
    # ------------------------------------------------------------------
    def editing_rect(self) -> Optional[QRectF]:
        item = self._editing_item
        return item.sceneBoundingRect() if item is not None else None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        scene_pos = self.mapToScene(event.position().toPoint())
        self._press_scene = scene_pos
        self._press_view = event.position().toPoint()

        if self._label_editor is not None and event.button() == Qt.LeftButton:
            proxy = self._label_proxy
            if proxy is not None and proxy.sceneBoundingRect().contains(scene_pos):
                super().mousePressEvent(event)
                return
            self.close_label_editor(commit=True)

        # A click away from the little unit box finishes it, the way clicking
        # off any other in-place editor does.
        if self._unit_editor is not None and event.button() == Qt.LeftButton:
            proxy = self._unit_proxy
            if proxy is not None and proxy.sceneBoundingRect().contains(scene_pos):
                super().mousePressEvent(event)
                return
            self.close_unit_editor(commit=True)

        # While a region is being edited the pointer belongs to its text: a
        # click inside places the caret, a drag selects, a click outside
        # finishes the edit. Its own handles are the exception — a callout's
        # arrow is inside its bounding box, so grabbing it would otherwise put
        # the caret in the text instead of moving the arrow.
        if self._editing_item is not None and event.button() == Qt.LeftButton:
            item = self._editing_item
            grabbed = (item.handle_at(item.mapFromScene(scene_pos))
                       if self.editable(item) else None)
            rect = self.editing_rect()
            if grabbed is None and rect is not None and rect.contains(scene_pos):
                super().mousePressEvent(event)
                return
            self.end_item_edit()
            if grabbed and item.scene() is not None:
                item.setSelected(True)
                self._handle_item = item
                self._handle_key = grabbed
                self._mode = "resize"
                self.begin_snapshot(self.involved_frames(item))
                event.accept()
                return

        if event.button() == Qt.MiddleButton or self._space_pan or self.tool_key == "pan":
            self._mode = "pan"
            self._pan_origin = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.RightButton:
            if self._mode == "draw_poly":
                self.finish_poly()
                event.accept()
                return
            super().mousePressEvent(event)
            return

        if self._pending_stamp is not None and event.button() == Qt.LeftButton:
            if self.place_pending_stamp(scene_pos):
                event.accept()
                return

        tool = self.current_tool()
        if tool.mode == NONE and tool.key == "select":
            self._press_select(event, scene_pos)
            return
        self._press_draw(event, scene_pos, tool)

    def _press_select(self, event: QMouseEvent, scene_pos: QPointF) -> None:
        # 1. an active spreadsheet takes clicks inside its own frame
        if self.active_table is not None:
            local = self.active_table.mapFromScene(scene_pos)
            if self.active_table.fill_handle_rect().contains(local):
                self.close_cell_editor()
                self._mode = "table_fill"
                # The whole selected block is what is dragged from, as in
                # Excel: two numbers carry a series on, one is copied.
                self._fill_origin = self.active_table.selection()
                self.begin_snapshot()
                event.accept()
                return
            border = self.active_table.border_at(local)
            if border is not None:
                self._mode = "table_resize"
                self._handle_key = f"{border[0]}:{border[1]}"
                self.begin_snapshot()
                event.accept()
                return
            gutter = self.active_table.gutter_at(local)
            if gutter is not None:
                self._select_table_band(gutter)
                event.accept()
                return
            cell = self.active_table.cell_at(local)
            if cell is not None and self._cell_editor is not None \
                    and self.pointing_allowed():
                # Clicking another cell while writing a formula refers to it
                # instead of abandoning what is being typed.
                self.point_at(*cell)
                self._mode = "idle"
                event.accept()
                return
            if cell is not None:
                self.close_cell_editor()
                table = self.active_table
                table.current = cell
                if not (event.modifiers() & Qt.ShiftModifier):
                    table.anchor = cell
                table.update()
                self._mode = "table_select"
                self.cellChanged.emit(table)
                event.accept()
                return

        # 2. a resize handle on an already-selected item
        for item in self.scene().selectedItems():
            if not isinstance(item, MarkupItem) or not self.editable(item):
                continue
            key = item.handle_at(item.mapFromScene(scene_pos))
            if key:
                self._handle_item = item
                self._handle_key = key
                self._mode = "resize"
                self.begin_snapshot()
                event.accept()
                return

        item = self.markup_at(scene_pos)
        if isinstance(item, ContentsItem) and not item.isSelected():
            # A contents line behaves like a link: one click follows it. Select
            # the block first if you want to move or resize it.
            row = item.row_at(item.mapFromScene(scene_pos))
            if row is not None:
                self.scene().clearSelection()
                item.setSelected(True)
                self.selectionChanged.emit()
                self.window.go_to_bookmark(*row)
                self._mode = "idle"
                event.accept()
                return
        if item is None:
            if self._mode == "lasso":
                # Another corner of the lasso.
                self._marquee.append(QPointF(scene_pos))
                self.viewport().update()
                event.accept()
                return
            self.deactivate_table()
            self._keep_selection = bool(event.modifiers() & Qt.ControlModifier)
            if not self._keep_selection:
                self.scene().clearSelection()
                self.selectionChanged.emit()
            if event.modifiers() & Qt.ShiftModifier:
                # Shift on bare paper draws a shape around what you want, a
                # corner at a time. Without it, a click is only ever a click.
                self._mode = "lasso"
                self._marquee = [QPointF(scene_pos), QPointF(scene_pos)]
                self.statusMessage.emit(
                    "Lasso: click each corner · double-click or Enter to "
                    "select what is inside · Esc to cancel")
                self.viewport().update()
                event.accept()
                return
            self._mode = "rubber"
            self._marquee = [QPointF(scene_pos), QPointF(scene_pos)]
            self.viewport().update()
            event.accept()
            return

        control = bool(event.modifiers() & Qt.ControlModifier)
        family = self.group_of(item)
        if event.modifiers() & Qt.ShiftModifier:
            wanted = not item.isSelected()
            for member in family:
                member.setSelected(wanted)
        elif control:
            # Ctrl adds to the selection and arms a copy; it does not take
            # anything out of it, because Ctrl-dragging what you just clicked
            # is the whole point.
            for member in family:
                member.setSelected(True)
        elif not item.isSelected():
            self.scene().clearSelection()
            for member in family:
                member.setSelected(True)
        self.selectionChanged.emit()

        if not self.editable(item):
            self._mode = "idle"
            event.accept()
            return
        self._mode = "move"
        self._copy_on_move = control
        self._copied = False
        self._move_items = [(other, other.pos()) for other in self.scene().selectedItems()
                            if isinstance(other, MarkupItem) and self.editable(other)]
        self.begin_snapshot(self.all_frames())
        event.accept()

    def settle_pages(self, items: list) -> None:
        """Hand each dragged markup to the page it was dropped on.

        On a canvas that scrolls through the whole document, dragging a markup
        onto the next page should put it on that page — which means changing
        which page owns it, while it stays exactly where it was dropped.
        """
        scene = self.scene()
        if scene is None:
            return
        for item in items:
            frame = scene.frame_at(item.sceneBoundingRect().center())
            if frame is None or item.parentItem() is frame:
                continue
            position = item.scenePos()
            item.setParentItem(frame)
            item.setPos(frame.mapFromScene(position))
            item.refresh(self.document().workspace, frame.page)

    def _select_table_band(self, gutter: tuple[str, int]) -> None:
        table = self.active_table
        kind, index = gutter
        if kind == "col":
            table.current = (0, index)
            table.anchor = (table.sheet.rows - 1, index)
        else:
            table.current = (index, 0)
            table.anchor = (index, table.sheet.cols - 1)
        table.update()
        self.cellChanged.emit(table)

    def _press_draw(self, event: QMouseEvent, scene_pos: QPointF, tool: Tool) -> None:
        frame = self.frame_at(scene_pos) or self.frame()
        point = self.snap_scene(scene_pos, frame)
        if self._mode == "draw_click":
            # The second click of a click-click drawing.
            self._mode = "idle"
            self._update_draft(scene_pos, event.modifiers())
            self.finish_draft(scene_pos, clicked=True)
            event.accept()
            return
        if tool.mode == ANCHOR:
            # A callout is two clicks: what it points at, then where its words
            # go. There is no box to drag out — it comes at a sensible size
            # and grows as it is written into, which is what Bluebeam does and
            # what saves the fiddling.
            if self._pending_anchor is None:
                self._pending_anchor = QPointF(point)
                self.statusMessage.emit(
                    f"{tool.label}: now click where the words go · Esc to start again")
                self.viewport().update()
                event.accept()
                return
            self.place_callout(tool, point)
            event.accept()
            return
        if tool.mode == CLICK:
            self.begin_snapshot()
            item = self.create_item(tool, point)
            if item is not None:
                self.commit_snapshot(f"Add {tool.label.lower()}")
            self.finish_tool()
            event.accept()
            return

        if tool.mode == POLY:
            if self._mode != "draw_poly":
                self.begin_snapshot()
                self._draft = tool.factory()
                self._prepare_draft(self._draft)
                self._draft.setPos(frame.mapFromScene(point))
                self._draft.points = [QPointF(0, 0), QPointF(0, 0)]
                frame.add_markup(self._draft)
                self._mode = "draw_poly"
                self.statusMessage.emit(
                    f"{tool.label}: click to add points · double-click or Enter to finish · Esc to cancel")
            else:
                local = self._draft.mapFromScene(point)
                if event.modifiers() & Qt.ShiftModifier and len(self._draft.points) >= 2:
                    local = self.constrain(self._draft.points[-2], local)
                # Qt has to be told before the shape changes, not after, or the
                # scene keeps indexing the item by a rectangle it no longer has.
                self._draft.prepareGeometryChange()
                self._draft.points[-1] = local
                self._draft.points.append(QPointF(local))
                if tool.max_points and len(self._draft.points) - 1 >= tool.max_points:
                    self.finish_poly()
            event.accept()
            return

        self.begin_snapshot()
        self._draw_origin = QPointF(point)
        self._draft = tool.factory()
        self._prepare_draft(self._draft)
        self._draft.setPos(frame.mapFromScene(point))
        if isinstance(self._draft, (PolyItem, MeasureItem)):
            self._draft.points = [QPointF(0, 0), QPointF(0, 0)]
        else:
            self._draft.set_local_rect(QRectF(0, 0, 1, 1))
        frame.add_markup(self._draft)
        self._mode = "draw_free" if tool.mode == FREE else "draw_drag"
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        scene_pos = self.mapToScene(event.position().toPoint())
        self._last_scene_pos = scene_pos
        self.cursorMoved.emit(scene_pos)
        if self._pending_anchor is not None or self._pending_stamp is not None:
            self.viewport().update()          # the leader, or the preview, follows

        if self._editing_item is not None and self._mode == "idle":
            super().mouseMoveEvent(event)       # dragging selects text
            return

        if self._mode == "pan":
            delta = event.position().toPoint() - self._pan_origin
            self._pan_origin = event.position().toPoint()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return

        if self._mode in ("rubber", "lasso") and self._marquee:
            self._marquee[-1] = QPointF(scene_pos)
            self.viewport().update()
            event.accept()
            return

        if self._mode == "move":
            delta = scene_pos - self._press_scene
            control = bool(event.modifiers() & Qt.ControlModifier)
            if self._copy_on_move and not self._copied and not self._is_a_click(scene_pos):
                self._leave_copies_behind()
            if event.modifiers() & Qt.ShiftModifier:
                held = self.constrain(QPointF(0, 0), delta)
                delta = QPointF(held.x(), held.y())
            # Ctrl taken hold of after the drag started means "leave the
            # snapping alone for a moment"; Ctrl held from the start means
            # "copy", and snapping carries on as usual.
            free = control and not self._copy_on_move
            if free:
                self._snap_marker = None
            else:
                delta = self.snap_moved(self._move_items, delta)
            for item, origin in self._move_items:
                target = origin + delta
                # Copying takes the arrow along: what is being dragged out is
                # a new callout, and its arrow belongs to it. Moving leaves the
                # arrow pointing at whatever it was pointing at.
                self._place(item, target if free else self.snap(target),
                            keep_leader=not self._copy_on_move)
            event.accept()
            return

        if self._mode == "resize" and self._handle_item is not None:
            local = self._handle_item.mapFromScene(self.snap(scene_pos))
            self._handle_item.move_handle(self._handle_key, local,
                                          bool(event.modifiers() & Qt.ShiftModifier))
            if isinstance(self._handle_item, MeasureItem):
                self._handle_item.refresh(page=self.page())
            event.accept()
            return

        if self._mode == "table_resize" and self.active_table is not None:
            kind, index = self._handle_key.split(":")
            index = int(index)
            table = self.active_table
            local = table.mapFromScene(scene_pos)
            table.prepareGeometryChange()
            if kind == "col":
                table.sheet.col_widths[index] = max(local.x() - table.column_x(index), 14.0)
            else:
                table.sheet.row_heights[index] = max(local.y() - table.row_y(index), 10.0)
            table.update()
            event.accept()
            return

        if self._mode == "table_select" and self.active_table is not None:
            cell = self.active_table.cell_at(self.active_table.mapFromScene(scene_pos))
            if cell is not None and cell != self.active_table.anchor:
                self.active_table.anchor = cell
                self.active_table.update()
                self.cellChanged.emit(self.active_table)
            event.accept()
            return

        if self._mode == "table_fill" and self.active_table is not None:
            cell = self.active_table.cell_at(self.active_table.mapFromScene(scene_pos))
            if cell is not None:
                self.active_table.anchor = cell
                self.active_table.update()
            event.accept()
            return

        if self._mode in ("draw_drag", "draw_click", "draw_poly", "draw_free") \
                and self._draft is not None:
            self._update_draft(scene_pos, event.modifiers())
            event.accept()
            return

        self._update_hover_cursor(scene_pos)
        super().mouseMoveEvent(event)

    def _update_draft(self, scene_pos: QPointF, modifiers) -> None:
        draft = self._draft
        point = self.snap_scene(scene_pos)
        local = draft.mapFromScene(point)
        draft.prepareGeometryChange()
        if self._mode == "draw_free":
            if modifiers & Qt.ShiftModifier:
                # Shift draws a straight stroke from where the pen went down,
                # held to 0°, 45° or 90° like every other tool.
                start = draft.points[0] if draft.points else QPointF(0, 0)
                draft.points = [QPointF(start), self.constrain(start, local)]
            elif not draft.points or _far_enough(draft.points[-1], local):
                draft.points.append(local)
        elif self._mode == "draw_poly":
            if modifiers & Qt.ShiftModifier and len(draft.points) >= 2:
                local = self.constrain(draft.points[-2], local)
            draft.points[-1] = local
        elif isinstance(draft, (PolyItem, MeasureItem)):
            if modifiers & Qt.ShiftModifier:
                local = self.constrain(QPointF(0, 0), local)
            draft.points[-1] = local
        else:
            # Worked out where the drawing started rather than from the draft's
            # own corner, so that dragging up or left squares off the same way
            # as dragging down or right.
            origin = self._draw_origin or self._press_scene
            corner = QPointF(point)
            if modifiers & Qt.ShiftModifier:
                dx, dy = corner.x() - origin.x(), corner.y() - origin.y()
                side = max(abs(dx), abs(dy))
                corner = QPointF(origin.x() + (side if dx >= 0 else -side),
                                 origin.y() + (side if dy >= 0 else -side))
            rect = QRectF(origin, corner).normalized()
            parent = draft.parentItem()
            top_left = parent.mapFromScene(rect.topLeft()) if parent is not None \
                else rect.topLeft()
            draft.setPos(top_left)
            draft.set_local_rect(QRectF(0, 0, rect.width(), rect.height()))
        if isinstance(draft, MeasureItem):
            draft.refresh(page=self.page())
        draft.update()

    def _leave_copies_behind(self) -> None:
        """Ctrl-drag: put a copy of each item back where it started.

        The copies stay put and the originals travel, so what ends up under
        the pointer is what was picked up — which is what every drawing
        program does, and it keeps the selection meaning the same thing.
        """
        self._copied = True
        self._copied_groups: dict[str, str] = {}
        scene = self.scene()
        for item, origin in self._move_items:
            frame = item.parentItem()
            if frame is None:
                continue
            data = item.serialize()
            data["uid"] = os.urandom(8).hex()
            if data.get("group"):
                data["group"] = self._copied_groups.setdefault(
                    data["group"], os.urandom(6).hex())
            copy = build_item(data)
            if copy is None:
                continue
            if isinstance(copy, ImageItem):
                copy.load_from_document(self.document())
            copy.setPos(origin)
            frame.add_markup(copy)
            copy.setSelected(False)
        if scene is not None:
            self.window.recalculate()
        self.statusMessage.emit(f"Copied {len(self._move_items)} markup(s)")

    @staticmethod
    def _place(item, position: QPointF, keep_leader: bool = True) -> None:
        """Move an item, keeping a callout's arrow pointing where it pointed."""
        mover = getattr(item, "move_keeping_leader", None)
        if keep_leader and callable(mover):
            mover(position)
        else:
            item.setPos(position)

    def _update_hover_cursor(self, scene_pos: QPointF) -> None:
        if self.tool_key != "select":
            return
        for item in self.scene().selectedItems():
            if isinstance(item, MarkupItem) and self.editable(item):
                key = item.handle_at(item.mapFromScene(scene_pos))
                if key:
                    self.setCursor(HANDLE_CURSORS.get(key, Qt.SizeAllCursor))
                    return
        if self.active_table is not None:
            local = self.active_table.mapFromScene(scene_pos)
            border = self.active_table.border_at(local)
            if border is not None:
                self.setCursor(Qt.SplitHCursor if border[0] == "col" else Qt.SplitVCursor)
                return
            if self.active_table.fill_handle_rect().contains(local):
                self.setCursor(Qt.CrossCursor)
                return
        item = self.markup_at(scene_pos)
        self.setCursor(Qt.SizeAllCursor if item is not None and self.editable(item)
                       else Qt.ArrowCursor)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        scene_pos = self.mapToScene(event.position().toPoint())

        if self._editing_item is not None and self._mode == "idle":
            super().mouseReleaseEvent(event)
            return

        if self._mode == "pan":
            self._mode = "idle"
            self.setCursor(self._cursor_for_tool(self.current_tool()))
            event.accept()
            return

        if self._mode == "rubber":
            if self._is_a_click(scene_pos):
                # A click on bare paper only clears the selection, which the
                # press already did. Dragging is what draws a marquee, and
                # Shift is what starts a lasso.
                self._mode = "idle"
                self.cancel_marquee()
                event.accept()
                return
            # select_in_marquee reads the mode to know what shape it is, so
            # it is left alone until then.
            self.select_in_marquee()
            event.accept()
            return

        if self._mode == "lasso":
            event.accept()
            return

        if self._mode == "move":
            self._mode = "idle"
            self._snap_marker = None
            self.settle_pages([item for item, _ in self._move_items])
            self.commit_snapshot("Copy markup" if self._copied else "Move markup")
            self._copy_on_move = False
            self._copied = False
            event.accept()
            return

        if self._mode == "resize":
            self._mode = "idle"
            item = self._handle_item
            self._handle_item = None
            if item is not None:
                item.refresh(self.document().workspace, self.page())
            self.commit_snapshot("Resize markup")
            self.selectionChanged.emit()
            event.accept()
            return

        if self._mode == "table_resize":
            self._mode = "idle"
            self.commit_snapshot("Resize column")
            event.accept()
            return

        if self._mode == "table_select":
            self._mode = "idle"
            event.accept()
            return

        if self._mode == "table_fill":
            self._mode = "idle"
            self._apply_fill()
            event.accept()
            return

        if self._mode == "draw_drag":
            if self._is_a_click(scene_pos):
                # Bluebeam draws either way: press and drag, or click once for
                # the first point and again for the second. A click used to
                # finish the markup then and there, which is where a measure
                # tool got its 120 pt measurement from nowhere.
                self._mode = "draw_click"
                self.statusMessage.emit(
                    f"{self.current_tool().label}: click again to finish · "
                    "Shift constrains · Esc to cancel")
                event.accept()
                return
            self._mode = "idle"
            self.finish_draft(scene_pos)
            event.accept()
            return

        if self._mode == "draw_click":
            event.accept()
            return

        if self._mode == "draw_free":
            self._mode = "idle"
            self.finish_draft(scene_pos)
            event.accept()
            return

        if self._mode == "draw_poly":
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        scene_pos = self.mapToScene(event.position().toPoint())
        if self._mode == "draw_poly":
            self.finish_poly()
            event.accept()
            return
        if self._mode == "lasso":
            self.select_in_marquee()
            event.accept()
            return
        # Already editing this region: let the editor select a word.
        rect = self.editing_rect()
        if rect is not None and rect.contains(scene_pos):
            super().mouseDoubleClickEvent(event)
            return
        item = self.markup_at(scene_pos)
        if item is None:
            super().mouseDoubleClickEvent(event)
            return
        if isinstance(item, TableItem):
            self.activate_table(item)
            cell = item.cell_at(item.mapFromScene(scene_pos))
            if cell is not None:
                item.current = item.anchor = cell
                self.open_cell_editor()
            event.accept()
            return
        if isinstance(item, MathItem) and not item.locked:
            # Double-clicking the answer changes the unit it is shown in, the
            # way SMath has a unit slot beside every result. Anywhere else on
            # the line edits the line.
            row = item.result_at(item.mapFromScene(scene_pos))
            if row >= 0 and self.open_unit_editor(item, row):
                event.accept()
                return
        if isinstance(item, ContentsItem):
            row = item.row_at(item.mapFromScene(scene_pos))
            if row is not None:
                self.window.go_to_bookmark(*row)
                event.accept()
                return
        if isinstance(item, PlotItem) and not item.locked:
            self.window.edit_plot(item)
            event.accept()
            return
        if isinstance(item, (MathItem, _TextBase)) and not item.locked:
            self.begin_item_edit(item)
            self.place_caret(item, scene_pos)
            event.accept()
            return
        if isinstance(item, NoteItem) and not item.locked:
            # A note is a folded-up comment; double-clicking is how you read
            # and change what it says.
            self.begin_snapshot(self.involved_frames(item))
            if self.edit_note(item):
                self.commit_snapshot("Edit note")
            event.accept()
            return
        if isinstance(item, (PolyItem, MeasureItem)) and not item.locked:
            if (getattr(item, "uses_vertex_handles", True)
                    and hasattr(item, "insert_point") and len(item.points) > 2):
                self.begin_snapshot(self.involved_frames(item))
                item.insert_point(item.mapFromScene(scene_pos))
                item.refresh(self.document().workspace, self.page())
                self.commit_snapshot("Add vertex")
                event.accept()
                return
        # A measurement with nowhere to add a vertex is one to type on: a
        # dimension carries its own words.
        if isinstance(item, MeasureItem) and not item.locked:
            if self.open_label_editor(item):
                event.accept()
                return
        self.itemActivated.emit(item)
        event.accept()

    # ------------------------------------------------------------------
    # item creation
    # ------------------------------------------------------------------
    # -- typing on a measurement -------------------------------------------
    def open_label_editor(self, item) -> bool:
        """Type a measurement's own text where the text sits.

        A dimension carries whatever the author wants on it, and asking for
        that in a dialog put the words somewhere other than where they were
        going to appear. The caret goes where the text goes, and it starts
        empty, so a dimension says nothing until something is typed into it.
        """
        if not isinstance(item, MeasureItem) or item.locked:
            return False
        self.close_label_editor(commit=False)
        editor = QLineEdit()
        editor.setText(item.custom_label)
        editor.setPlaceholderText(item.measured_text or "text for this dimension")
        editor.setAlignment(Qt.AlignCenter)
        editor.setStyleSheet(
            "QLineEdit { border: 2px solid #1971c2; background: #ffffff; "
            "padding: 0 3px; }")
        font = item.style.font()
        font.setPointSizeF(max(item.style.font_size, 6.0))
        editor.setFont(font)
        proxy = self.scene().addWidget(editor)
        proxy.setZValue(10_000)
        centre = item.mapToScene(item._label_anchor() + item.label_offset)
        width = max(int(item.style.font_size * 12), 90)
        height = max(int(item.style.font_size * 2.0), 18)
        editor.setFixedSize(width, height)
        proxy.setPos(centre - QPointF(width / 2, height / 2))
        editor.selectAll()
        editor.setFocus(Qt.OtherFocusReason)
        editor.returnPressed.connect(lambda: self.close_label_editor(commit=True))
        self._label_editor = editor
        self._label_proxy = proxy
        self._label_item = item
        self.statusMessage.emit(
            "Type what this dimension should say — Enter to finish, empty for "
            "the measured value")
        return True

    def close_label_editor(self, commit: bool = True) -> None:
        if self._label_editor is None:
            return
        text = self._label_editor.text().strip()
        item = self._label_item
        proxy = self._label_proxy
        self._label_editor = None
        self._label_proxy = None
        self._label_item = None
        if proxy is not None:
            widget = proxy.widget()
            if widget is not None:
                widget.clearFocus()
            proxy.clearFocus()
            if proxy.scene() is not None:
                proxy.scene().removeItem(proxy)
            proxy.deleteLater()
        if commit and item is not None and item.custom_label != text:
            self.begin_snapshot(self.involved_frames(item))
            item.custom_label = text
            item.refresh(page=self.page())
            self.commit_snapshot("Dimension text")
            self.selectionChanged.emit()
        self.setFocus(Qt.OtherFocusReason)

    # -- tools taken from a tool set ---------------------------------------
    def set_pending_properties(self, payload: Optional[dict]) -> None:
        """The next markup drawn wears these properties."""
        self._pending_properties = dict(payload) if payload else None

    def set_pending_stamp(self, entry) -> None:
        """The next click puts this markup down, exactly as it was kept."""
        self._pending_stamp = entry
        self.set_tool("select")
        self.setCursor(Qt.CrossCursor)

    def clear_pending_tool(self) -> None:
        had = self._pending_stamp is not None or self._pending_properties is not None
        self._pending_stamp = None
        self._pending_properties = None
        if had:
            self.setCursor(self._cursor_for_tool(self.current_tool()))
        return had

    def pending_payloads(self) -> list:
        """What a held tool would put down: one markup, or a whole group."""
        from . import toolsets

        entry = self._pending_stamp
        if entry is None:
            return []
        if entry.payload.get("type") == toolsets.GROUP:
            return [dict(part) for part in entry.payload.get("items", [])]
        return [dict(entry.payload)]

    def pending_extent(self) -> QRectF:
        """How big the held tool is, so it can be centred on the pointer."""
        boxes = QRectF()
        for data in self.pending_payloads():
            rect = data.get("rect")
            width, height = (float(rect[2]), float(rect[3])) if rect else (120.0, 40.0)
            box = QRectF(float(data.get("x", 0.0)), float(data.get("y", 0.0)),
                         width, height)
            boxes = box if boxes.isNull() else boxes.united(box)
        return boxes

    def place_pending_stamp(self, scene_pos: QPointF) -> bool:
        """Put a kept markup — or a whole group — down under the pointer."""
        entry = self._pending_stamp
        if entry is None:
            return False
        frame = self.frame_at(scene_pos) or self.frame()
        if frame is None:
            return False
        payloads = self.pending_payloads()
        if not payloads:
            self._pending_stamp = None
            return False
        origin = self._pending_origin(frame, scene_pos)
        group_name = os.urandom(6).hex() if len(payloads) > 1 else ""
        self.begin_snapshot([frame])
        self.scene().clearSelection()
        placed = []
        for data in payloads:
            data["uid"] = os.urandom(8).hex()
            if group_name:
                data["group"] = group_name
            item = build_item(data)
            if item is None:
                continue
            if isinstance(item, ImageItem):
                item.load_from_document(self.document())
            item.setPos(origin + QPointF(float(data.get("x", 0.0)),
                                         float(data.get("y", 0.0))))
            frame.add_markup(item)
            item.setSelected(True)
            placed.append(item)
        self.window.recalculate()
        self.commit_snapshot(f"Place {entry.label}")
        self.selectionChanged.emit()
        self._pending_stamp = None
        self.setCursor(self._cursor_for_tool(self.current_tool()))
        self.statusMessage.emit(f"{entry.label} placed" if len(placed) == 1
                                else f"{entry.label} placed — {len(placed)} markups")
        self.viewport().update()
        return bool(placed)

    def _pending_origin(self, frame, scene_pos: QPointF) -> QPointF:
        """Where the held tool's top-left goes: centred on the pointer."""
        local = frame.mapFromScene(self.snap_scene(scene_pos, frame))
        extent = self.pending_extent()
        return QPointF(local.x() - extent.width() / 2 - extent.left(),
                       local.y() - extent.height() / 2 - extent.top())

    def _prepare_draft(self, item: MarkupItem) -> None:
        item.author = self.document().settings.default_author or self.document().author
        self.window.apply_default_style(item)
        if self._pending_properties:
            # Drawn with a tool taken from a set: its properties win over both
            # the toolbar and the saved default, because it was asked for.
            from . import toolsets
            toolsets.apply_properties(item, self._pending_properties)

    def create_item(self, tool: Tool, point: QPointF) -> Optional[MarkupItem]:
        item = tool.factory() if tool.factory else None
        if item is None:
            return None
        self._prepare_draft(item)
        if isinstance(item, CountItem):
            item.subject = self.count_subject
            item.symbol = self.count_symbol
            item.index = self.next_count_index(self.count_subject)
        if isinstance(item, NoteItem):
            if self.window.interactive_prompts and not self.edit_note(item):
                return None
        frame = self.frame_at(point) or self.frame()
        frame.add_markup(item, frame.mapFromScene(point))
        self.scene().clearSelection()
        item.setSelected(True)
        self.selectionChanged.emit()
        return item

    def place_callout(self, tool: Tool, point: QPointF) -> None:
        """Put a callout down at *point*, pointing at what was clicked first.

        The box arrives at a size that holds a line or two and grows from
        there, so the second click is the last thing you have to do before
        typing.
        """
        anchor = self._pending_anchor
        self._pending_anchor = None
        self.begin_snapshot()
        item = tool.factory()
        self._prepare_draft(item)
        frame = self.frame_at(point) or self.frame()
        frame.add_markup(item, frame.mapFromScene(point))
        if anchor is not None:
            item.tip = item.mapFromScene(anchor)
        item.refresh(self.document().workspace, self.page())
        self.scene().clearSelection()
        item.setSelected(True)
        self.selectionChanged.emit()
        self.commit_snapshot(f"Add {tool.label.lower()}")
        self.finish_tool()
        self.begin_item_edit(item)

    def edit_note(self, note) -> bool:
        """Ask for a note's text. False when the author changed their mind."""
        from PySide6.QtWidgets import QInputDialog

        text, accepted = QInputDialog.getMultiLineText(
            self, "Note", "Comment:", note.comment)
        if not accepted:
            return False
        note.comment = text
        note.touch()
        note.update()
        return True

    def next_count_index(self, subject: str) -> int:
        highest = 0
        for page in self.document().pages:
            frame = page.frame
            if frame is None:
                continue
            for item in frame.markups():
                if isinstance(item, CountItem) and item.subject == subject:
                    highest = max(highest, item.index)
        return highest + 1

    def _is_a_click(self, scene_pos: QPointF, origin: Optional[QPointF] = None) -> bool:
        """True when the pointer never really left where the drawing started.

        The origin has to be passed in for the second click of a click-click
        drawing: by then the last press is that second click, and everything
        looks like a click compared with itself.
        """
        origin = origin if origin is not None else self._press_scene
        return (abs(scene_pos.x() - origin.x()) < CLICK_SLOP
                and abs(scene_pos.y() - origin.y()) < CLICK_SLOP)

    def finish_draft(self, scene_pos: QPointF, clicked: bool = False) -> None:
        draft = self._draft
        self._draft = None
        if draft is None:
            return
        tool = self.current_tool()
        origin = self._draw_origin or self._press_scene
        self._draw_origin = None
        # A drawing finished by a second click is the size the two clicks made
        # it, however small; only a stray tap gets a default size.
        degenerate = self._is_a_click(scene_pos, origin)
        tiny = not clicked and degenerate

        # Two clicks in the same spot mean the drawing was thought better of,
        # not that a measurement of some invented length should appear.
        if clicked and degenerate:
            detach(draft)
            self.finish_tool()
            return

        if isinstance(draft, (PolyItem, MeasureItem)):
            if tool.mode == FREE and len(draft.points) < 2:
                detach(draft)
                self.finish_tool()
                return
            if tiny:
                width, _height = self._default_size(draft)
                draft.points[-1] = QPointF(width, 0)
            draft.prepareGeometryChange()
        elif isinstance(draft, MathItem):
            # A calculation sizes itself around what is typed into it.
            pass
        else:
            rect = draft.local_rect()
            if tiny or rect.width() < 6 or rect.height() < 6:
                draft.set_local_rect(QRectF(0, 0, *self._default_size(draft)))

        if isinstance(draft, StampItem):
            draft.text = self.stamp_text
            from ..items.text import STAMP_PRESETS
            colour = STAMP_PRESETS.get(self.stamp_text.upper(), draft.style.stroke)
            draft.style.stroke = colour
            draft.style.fill = colour
            draft.style.text_color = colour
        if isinstance(draft, ImageItem):
            if not self.window.load_image_into(draft):
                detach(draft)
                self.finish_tool()
                return
        if isinstance(draft, RectItem) and draft.kind in SIZED_SHAPES:
            draft.refresh(page=self.page())
        if isinstance(draft, MeasureItem):
            if draft.kind == CALIBRATE:
                detach(draft)
                length = math.hypot(draft.points[-1].x(), draft.points[-1].y())
                self.window.calibrate_scale(length)
                self.finish_tool()
                return
            draft.refresh(page=self.page())

        draft.refresh(self.document().workspace, self.page())
        self.scene().clearSelection()
        draft.setSelected(True)
        self.selectionChanged.emit()

        if isinstance(draft, CalloutItem) and self._pending_anchor is not None:
            # Point the leader at whatever was clicked before the box was drawn.
            target = draft.mapFromScene(self._pending_anchor)
            box = draft.local_rect()
            elbow = QPointF((target.x() + box.center().x()) / 2,
                            (target.y() + box.center().y()) / 2)
            draft.leader = [QPointF(target), elbow]
            self._pending_anchor = None

        if tool.mode == SNAPSHOT:
            # The marquee is not a markup: it says which part of the page to
            # take a copy of, and then it goes.
            region = draft.mapRectToParent(draft.local_rect().normalized())
            frame = draft.parentItem()
            detach(draft)
            self.forget_snapshot()
            # The tool is put away first: finishing it writes its own message
            # into the status bar, which would wipe out what the snapshot has
            # to say about what it took.
            self.finish_tool()
            self.window.take_snapshot(frame, region)
            return

        # Tools that ask a question do it now, while the markup is still fresh.
        note_scale = False
        if isinstance(draft, RectItem) and draft.kind in SIZED_SHAPES:
            self.window.prompt_rectangle_size(draft)
        elif isinstance(draft, TableItem):
            self.window.prompt_table_size(draft)
        elif isinstance(draft, PlotItem):
            self.window.edit_plot(draft, fresh=True)
        elif isinstance(draft, MeasureItem):
            if draft.kind != DIMENSION:
                note_scale = True
        self.commit_snapshot(f"Add {tool.label.lower()}")

        if isinstance(draft, MeasureItem) and draft.kind == DIMENSION \
                and self.window.interactive_prompts:
            self.open_label_editor(draft)
        elif isinstance(draft, (MathItem, TextItem, CalloutItem)):
            self.begin_item_edit(draft)
        elif isinstance(draft, TableItem):
            self.activate_table(draft)
        self.finish_tool()
        # Last word, so returning to the select tool does not wipe the notice.
        if note_scale:
            self.window.note_missing_scale()

    @staticmethod
    def _default_size(item: MarkupItem) -> tuple[float, float]:
        if isinstance(item, PlotItem):
            return 300.0, 200.0
        if isinstance(item, TableItem):
            return item.sheet.total_width(), item.sheet.total_height()
        if isinstance(item, MathItem):
            return 300.0, 90.0
        if isinstance(item, StampItem):
            return 190.0, 58.0
        if isinstance(item, (TextItem, CalloutItem)):
            return 170.0, 44.0
        if isinstance(item, ImageItem):
            return 220.0, 160.0
        return 120.0, 80.0

    def finish_poly(self) -> None:
        draft = self._draft
        self._mode = "idle"
        self._draft = None
        if draft is None:
            return
        tool = self.current_tool()
        if draft.points and len(draft.points) > tool.min_points:
            draft.points.pop()            # drop the live preview point
        draft.prepareGeometryChange()
        if len(draft.points) < tool.min_points:
            detach(draft)
            self.statusMessage.emit(f"{tool.label} needs at least {tool.min_points} points")
            self.finish_tool()
            return
        draft.refresh(self.document().workspace, self.page())
        self.scene().clearSelection()
        draft.setSelected(True)
        self.commit_snapshot(f"Add {tool.label.lower()}")
        self.selectionChanged.emit()
        self.finish_tool()
        if isinstance(draft, MeasureItem) and draft.kind != DIMENSION:
            self.window.note_missing_scale()

    def forget_snapshot(self) -> None:
        """Drop the undo snapshot taken for a gesture that changes nothing."""
        self._snapshot = []

    def cancel_draft(self) -> None:
        if self._draft is not None:
            detach(self._draft)
            self._draft = None
        self._mode = "idle"

    # ------------------------------------------------------------------
    # item editing
    # ------------------------------------------------------------------
    @staticmethod
    def style_line_height(item) -> float:
        """A sensible minimum row height for an empty region."""
        return item.style.font_size * 1.9

    def editing_item(self):
        return self._editing_item

    def is_editing(self) -> bool:
        """True when a keystroke belongs to something being typed into.

        A region, a cell, or a table with the cursor in it: in all three the
        keyboard is writing, and a tool key would be a letter of somebody's
        sentence rather than a request to change tool.
        """
        return (self._editing_item is not None or self._cell_editor is not None
                or self._unit_editor is not None or self._label_editor is not None
                or self.active_table is not None)

    @staticmethod
    def place_caret(item, scene_pos: QPointF) -> None:
        """Put the caret where the pointer is, rather than at the start.

        Only for text boxes, where what is displayed and what is edited are the
        same layout.  A calculation is displayed typeset and edited as source, so
        a point on the fraction bar means nothing in the source text — there the
        caret goes to the end of the line, which is at least predictable.
        """
        editor = getattr(item, "_editor", None)
        if editor is None or isinstance(item, MathItem):
            return
        try:
            local = editor.mapFromScene(scene_pos)
            position = editor.document().documentLayout().hitTest(local, Qt.FuzzyHit)
        except Exception:
            return
        if position >= 0:
            cursor = editor.textCursor()
            cursor.setPosition(position)
            editor.setTextCursor(cursor)

    def begin_item_edit(self, item) -> None:
        if self._mode == "lasso":
            self.cancel_marquee()
        # The region may be on a page other than the one on screen — somebody
        # can scroll while a calculation is open — so its own page is what has
        # to be recorded, not whichever the chrome calls current.
        self.begin_snapshot(self.involved_frames(item))
        self.scene().clearSelection()
        item.setSelected(True)
        if isinstance(item, MathItem) and not getattr(item, "_enter_wired", False):
            item.enterPressed.connect(self._open_next_line)
            item._enter_wired = True
        item.begin_edit()
        self._editing_item = item
        if isinstance(item, MathItem) and not getattr(item, "_live_wired", False):
            # Wired once per region: a QTextDocument outlives one edit, and
            # asking Qt to disconnect something it never held prints a warning.
            editor = getattr(item, "_editor", None)
            if editor is not None:
                editor.document().contentsChanged.connect(self._note_live_edit)
                item._live_wired = True

    def _note_live_edit(self) -> None:
        """Work the line out again shortly, so its answer keeps up with it."""
        if self._live_timer is None:
            self._live_timer = QTimer(self)
            self._live_timer.setSingleShot(True)
            self._live_timer.setInterval(500)
            self._live_timer.timeout.connect(self._recalculate_while_typing)
        self._live_timer.start()

    def _recalculate_while_typing(self) -> None:
        """Update the answers beside what is being typed.

        Through a whole-document pass, never by evaluating this region on its
        own: a region evaluated against a workspace that already holds this
        pass's definitions turns its own definitions into checks.
        """
        item = self._editing_item
        editor = getattr(item, "_editor", None) if item is not None else None
        if not isinstance(item, MathItem) or editor is None:
            return
        text = editor.toPlainText()
        if text == item.source:
            return
        item.source = text
        self.window.recalculate()

    # -- completing a name or a unit ---------------------------------------
    #
    # Typing into a calculation offers what could come next: the units, and
    # every name this document has defined. Nothing is chosen for you —
    # Tab takes what is highlighted, the arrows move the highlight, Escape
    # puts the list away — because a unit that arrives by itself is a unit
    # nobody asked for.
    def completion_word(self) -> tuple[str, int]:
        """The word being typed at the caret, and where it starts."""
        item = self._editing_item
        editor = getattr(item, "_editor", None) if item is not None else None
        if editor is None:
            return "", 0
        cursor = editor.textCursor()
        text = editor.toPlainText()
        at = cursor.position()
        start = at
        while start > 0 and (text[start - 1].isalnum() or text[start - 1] in "_"):
            start -= 1
        word = text[start:at]
        if word and word[0].isdigit():
            return "", at            # part of a number, not a name
        return word, start

    def completion_words(self, prefix: str) -> list[str]:
        """Units and defined names starting with *prefix*, units first."""
        from ..core.units import UNIT_MENU

        workspace = self.document().workspace
        names = sorted(set(workspace.variables) | set(workspace.functions)
                       | set(workspace.table_names()))
        units: list[str] = []
        for group in UNIT_MENU.values():
            units += [unit for unit in group if unit not in units]
        wanted = [word for word in units if word.startswith(prefix)]
        wanted += [word for word in names if word.startswith(prefix)
                   and word not in wanted]
        if not wanted:                      # nothing exact: try ignoring case
            lowered = prefix.lower()
            wanted = [word for word in units + names
                      if word.lower().startswith(lowered)]
        return wanted[:40]

    def show_completions(self) -> None:
        """Offer what could follow what is being typed, if anything could."""
        word, _start = self.completion_word()
        if len(word) < 1:
            self.hide_completions()
            return
        words = self.completion_words(word)
        if not words or words == [word]:
            self.hide_completions()
            return
        popup = self._completer_popup()
        popup.clear()
        popup.addItems(words)
        popup.setCurrentRow(0)
        popup.resize(200, min(len(words), 8) * 18 + 6)
        item = self._editing_item
        editor = getattr(item, "_editor", None)
        anchor = editor.mapToScene(editor.boundingRect().bottomLeft())
        popup.move(self.mapFromScene(anchor) + QPoint(0, 2))
        popup.show()
        popup.raise_()
        self._completing = True

    def _completer_popup(self):
        if self._completions is None:
            from PySide6.QtWidgets import QListWidget
            popup = QListWidget(self.viewport())
            popup.setObjectName("completionList")
            popup.setFocusPolicy(Qt.NoFocus)
            popup.setUniformItemSizes(True)
            popup.itemClicked.connect(lambda _entry: self.accept_completion())
            self._completions = popup
        return self._completions

    def completions_showing(self) -> bool:
        """Whether the list is up.

        Kept as a flag of its own rather than asking the widget: a child of a
        window that has not been shown is never "visible" as far as Qt is
        concerned, and whether the list is offering anything is not the same
        question as whether pixels are on a screen.
        """
        return self._completing and self._completions is not None

    def hide_completions(self) -> None:
        self._completing = False
        self._live_timer = None
        if self._completions is not None:
            self._completions.hide()

    def move_completion(self, step: int) -> None:
        popup = self._completions
        if not self.completions_showing() or not popup.count():
            return
        popup.setCurrentRow((popup.currentRow() + step) % popup.count())

    def accept_completion(self) -> bool:
        """Put the highlighted word in, in place of what was being typed."""
        popup = self._completions
        if not self.completions_showing() or popup.currentItem() is None:
            return False
        chosen = popup.currentItem().text()
        word, start = self.completion_word()
        item = self._editing_item
        editor = getattr(item, "_editor", None) if item is not None else None
        if editor is None:
            return False
        cursor = editor.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(start + len(word), QTextCursor.KeepAnchor)
        cursor.insertText(chosen)
        editor.setTextCursor(cursor)
        self.hide_completions()
        self.statusMessage.emit(f"{chosen} — Tab accepted it")
        return True

    def _open_next_line(self) -> None:
        """Enter in a one-line calculation opens the next one just below it."""
        item = self._editing_item
        if not isinstance(item, MathItem):
            return
        origin = QPointF(item.pos())
        # Commit first: the region only knows how tall it is once what was typed
        # into it has been laid out, and a tall fraction needs more room below.
        self.end_item_edit()
        height = item.local_rect().height() if item.scene() is not None else 0.0
        below = origin + QPointF(0, max(height, self.style_line_height(item)) + LINE_STEP)
        self.begin_snapshot(self.involved_frames(item))
        following = MathItem("")
        following.style = item.style.copy()
        following.digits = item.digits
        following.number_format = item.number_format
        following.show_definition_results = item.show_definition_results
        following.show_comments = item.show_comments
        following.author = item.author
        following.layer = item.layer
        frame = item.parentItem() or self.frame()
        frame.add_markup(following, self.snap(below))
        self.scene().clearSelection()
        following.setSelected(True)
        self.commit_snapshot("Add calculation")
        self.begin_item_edit(following)

    def end_item_edit(self) -> None:
        self.hide_completions()
        if self._live_timer is not None:
            self._live_timer.stop()
        item = getattr(self, "_editing_item", None)
        if item is None:
            return
        self._editing_item = None
        if isinstance(item, MathItem):
            item.end_edit()
            self.window.recalculate()
        else:
            item.end_edit()
        # A region left completely empty is an invisible click target; drop it.
        if self._is_empty(item):
            detach(item)
            self.window.recalculate()
        self.commit_snapshot("Edit text")
        self.documentEdited.emit()

    @staticmethod
    def _is_empty(item) -> bool:
        if isinstance(item, MathItem):
            return not item.source.strip()
        if isinstance(item, CalloutItem):
            # A callout points at something, so it says something even before
            # a word is typed in it. Dropping it the moment the pointer left
            # the box was how reaching for its arrow made it disappear.
            return False
        if isinstance(item, _TextBase):
            return not item.text().strip()
        return False

    @staticmethod
    def editable(item) -> bool:
        """False when the markup itself is locked, or the layer under it is."""
        from PySide6.QtWidgets import QGraphicsItem as _GraphicsItem
        return bool(item.flags() & _GraphicsItem.ItemIsMovable) and not item.locked

    def text_clipboard(self, action: str) -> bool:
        """Copy, cut or paste inside the region being edited; False if none is."""
        item = self._editing_item
        editor = getattr(item, "_editor", None) if item is not None else None
        if editor is None:
            return False
        cursor = editor.textCursor()
        clipboard = QApplication.clipboard()
        if action == "paste":
            cursor.insertText(clipboard.text())
            editor.setTextCursor(cursor)
            return True
        if not cursor.hasSelection():
            return True                      # nothing selected: swallow, do nothing
        clipboard.setText(cursor.selectedText())
        if action == "cut":
            cursor.removeSelectedText()
            editor.setTextCursor(cursor)
        return True

    def insert_symbol(self, text: str) -> bool:
        """Type a maths symbol into whatever is being edited; False if nothing is.

        A symbol that opens a bracket — the root sign — brings its closing
        bracket with it and leaves the caret between the two, because
        ``√(`` on its own is a syntax error waiting to happen.
        """
        closing = ")" if text.endswith("(") else ""
        item = self._editing_item
        editor = getattr(item, "_editor", None) if item is not None else None
        if editor is not None:
            cursor = editor.textCursor()
            cursor.insertText(text + closing)
            if closing:
                cursor.movePosition(QTextCursor.Left, QTextCursor.MoveAnchor,
                                    len(closing))
            editor.setTextCursor(cursor)
            return True
        if self._cell_editor is not None:
            self._cell_editor.insert(text + closing)
            if closing:
                self._cell_editor.setCursorPosition(
                    self._cell_editor.cursorPosition() - len(closing))
            return True
        return False

    # ------------------------------------------------------------------
    # the unit a result is shown in
    # ------------------------------------------------------------------
    def open_unit_editor(self, item: MathItem, index: int) -> bool:
        """Type the unit a printed result should be shown in, SMath-style.

        The box opens over the answer itself, offering the units it could be
        converted to and the names already defined, so the unit can be picked
        with the arrow keys rather than remembered.
        """
        if item.locked or not (0 <= index < len(item.rows)):
            return False
        self.close_unit_editor(commit=False)
        rect = item.result_rect(index)
        if rect.isEmpty():
            return False
        editor = QLineEdit()
        editor.setText(item.display_unit_of(index))
        editor.setStyleSheet(
            "QLineEdit { border: 2px solid #1971c2; background: #ffffff; "
            "color: #1246a0; padding: 0 2px; }")
        font = item.style.font()
        font.setPointSizeF(max(item.style.font_size, 6.0))
        editor.setFont(font)
        editor.setCompleter(self._unit_completer(editor))
        proxy = self.scene().addWidget(editor)
        proxy.setZValue(10_000)
        proxy.setPos(item.mapToScene(rect.topLeft()))
        editor.setFixedSize(int(max(rect.width() + 24, 80)), int(max(rect.height(), 16)))
        editor.selectAll()
        editor.setFocus(Qt.OtherFocusReason)
        editor.returnPressed.connect(lambda: self.close_unit_editor(commit=True))
        self._unit_editor = editor
        self._unit_proxy = proxy
        self._unit_target = (item, index)
        self.statusMessage.emit(
            "Type the unit to show this result in — Enter to accept, "
            "Esc to leave it alone, empty to let it choose")
        return True

    def _unit_completer(self, parent) -> QCompleter:
        """Units to convert to, and the names this document already knows."""
        from ..core.units import UNIT_MENU

        words: list[str] = []
        for group in UNIT_MENU.values():
            words += [unit for unit in group if unit not in words]
        workspace = self.window.document.workspace
        words += sorted(set(workspace.variables) | set(workspace.functions))
        completer = QCompleter(words, parent)
        completer.setCaseSensitivity(Qt.CaseSensitive)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        completer.setFilterMode(Qt.MatchStartsWith)
        return completer

    def close_unit_editor(self, commit: bool = True) -> None:
        if self._unit_editor is None:
            return
        text = self._unit_editor.text().strip()
        item, index = self._unit_target
        proxy = self._unit_proxy
        self._unit_editor = None
        self._unit_proxy = None
        self._unit_target = (None, -1)
        if proxy is not None:
            widget = proxy.widget()
            if widget is not None:
                widget.clearFocus()
            proxy.clearFocus()
            if proxy.scene() is not None:
                proxy.scene().removeItem(proxy)
            proxy.deleteLater()
        if not commit or item is None:
            return
        if text and not _is_a_unit(text):
            self.statusMessage.emit(f"“{text}” is not a unit I know")
            return
        self.begin_snapshot(self.involved_frames(item))
        if item.set_display_unit(index, text):
            self.window.recalculate()
            self.commit_snapshot("Change result unit")
            self.statusMessage.emit(f"Result shown in {text}" if text
                                    else "Result shown in the unit it reads best in")
        self.setFocus(Qt.OtherFocusReason)

    def group_of(self, item) -> list:
        """Everything grouped with *item* — itself alone when it is not grouped.

        A group is a shared name rather than a container: the markups stay
        where they are in the page, and clicking one takes hold of all of them.
        """
        name = getattr(item, "group", "")
        if not name:
            return [item]
        scene = self.scene()
        if scene is None:
            return [item]
        family = [other for other in scene.markups()
                  if getattr(other, "group", "") == name and self.editable(other)]
        return family or [item]

    def markup_at(self, scene_pos: QPointF) -> Optional[MarkupItem]:
        for item in self.scene().items(scene_pos):
            if isinstance(item, MarkupItem):
                if item.layer and not self.window.layer_visible(item.layer):
                    continue
                return item
        return None

    # ------------------------------------------------------------------
    # spreadsheet interaction
    # ------------------------------------------------------------------
    def activate_table(self, table: TableItem) -> None:
        if self.active_table is table:
            return
        self.deactivate_table()
        self.active_table = table
        table.set_chrome(True)
        self.scene().clearSelection()
        table.setSelected(True)
        self.cellChanged.emit(table)
        self.statusMessage.emit(
            "Spreadsheet: type to edit · Enter/Tab to move · Ctrl+D fills down · Esc to leave")

    def deactivate_table(self) -> None:
        self.close_cell_editor()
        if self.active_table is not None:
            self.active_table.set_chrome(False)
            self.active_table = None
            self.cellChanged.emit(None)

    def open_cell_editor(self, initial: Optional[str] = None) -> None:
        table = self.active_table
        if table is None or table.locked:
            return
        self.close_cell_editor()
        row, col = table.current
        self.begin_snapshot()
        editor = QLineEdit()
        editor.setText(initial if initial is not None else table.sheet.raw(row, col))
        # The editor sits on the paper, so it takes the paper's colours rather
        # than the interface's: black on white whatever theme the window is in.
        # Left to the palette, dark mode would put white text on white paper.
        editor.setStyleSheet(
            "QLineEdit { border: 2px solid #1971c2; background: #ffffff; "
            "color: #111318; selection-background-color: #a5d8ff; "
            "selection-color: #111318; padding: 0 2px; }")
        # And it lines up the way the cell does — a number stays on the right
        # while it is being typed, rather than jumping across on Enter.
        editor.setAlignment(table.editor_alignment(row, col, editor.text()))
        font = table.style.font()
        font.setPointSizeF(max(table.style.font_size, 6.0))
        editor.setFont(font)
        proxy = self.scene().addWidget(editor)
        proxy.setZValue(10_000)
        rect = table.cell_rect(row, col)
        proxy.setGeometry(QRectF(table.mapToScene(rect.topLeft()),
                                 rect.size().expandedTo(rect.size())))
        proxy.setPos(table.mapToScene(rect.topLeft()))
        editor.setFixedSize(int(max(rect.width(), 60)), int(max(rect.height(), 16)))
        editor.selectAll() if initial is None else editor.setCursorPosition(len(editor.text()))
        editor.setFocus(Qt.OtherFocusReason)
        editor.returnPressed.connect(lambda: self.close_cell_editor(move=(1, 0)))
        editor.textEdited.connect(self._typed_in_cell)
        self._cell_editor = editor
        self._cell_proxy = proxy
        self._editing_cell = (row, col)
        self.stop_pointing()

    def _typed_in_cell(self, _text: str) -> None:
        """Anything typed by hand ends the reference the arrows were building."""
        if self._point_span is not None:
            self.stop_pointing()

    # -- pointing at cells while writing a formula -------------------------
    #
    # After "=" — and after every operator, bracket and comma in the formula —
    # a reference can go next. While that is true the arrow keys and the
    # pointer stop moving the cursor and start choosing the cell to refer to,
    # which is how a formula gets written in every spreadsheet.
    POINTABLE = "=+-*/^(,:<>&%"

    def pointing_allowed(self) -> bool:
        """True when what is being typed is a formula waiting for a reference."""
        editor = self._cell_editor
        if editor is None:
            return False
        text = editor.text()
        if not text.startswith("="):
            return False
        if self._point_span is not None:
            return True
        before = text[:editor.cursorPosition()].rstrip()
        return bool(before) and before[-1] in self.POINTABLE

    def point_at(self, row: int, col: int) -> None:
        """Put a reference to that cell into the formula being typed."""
        editor = self._cell_editor
        table = self.active_table
        if editor is None or table is None:
            return
        row = max(0, min(row, table.sheet.rows - 1))
        col = max(0, min(col, table.sheet.cols - 1))
        reference = make_ref(row, col)
        text = editor.text()
        start = end = editor.cursorPosition()
        if self._point_span is not None:
            first, last = self._point_span
            # Only replace what is still the reference this put there; if the
            # text has moved on underneath, the new one is inserted instead.
            if 0 <= first <= last <= len(text) and _looks_like_a_ref(text[first:last]):
                start, end = first, last
        editor.setText(text[:start] + reference + text[end:])
        editor.setCursorPosition(start + len(reference))
        self._point_span = (start, start + len(reference))
        self._pointing = (row, col)
        table.pointing = (row, col)
        table.update()

    def stop_pointing(self) -> None:
        """The reference is finished; the arrows go back to moving the caret."""
        self._point_span = None
        self._pointing = None
        if self.active_table is not None:
            self.active_table.pointing = None
            self.active_table.update()

    def close_cell_editor(self, commit: bool = True,
                          move: Optional[tuple[int, int]] = None) -> None:
        if self._cell_editor is None:
            return
        text = self._cell_editor.text()
        self.stop_pointing()
        cell = self._editing_cell
        proxy = self._cell_proxy
        self._cell_editor = None
        self._cell_proxy = None
        self._editing_cell = None
        if proxy is not None:
            # Focus must leave the proxy before it is removed, otherwise Qt
            # spins trying to hand focus on to a widget that is going away.
            widget = proxy.widget()
            if widget is not None:
                widget.clearFocus()
            proxy.clearFocus()
            if proxy.scene() is not None:
                proxy.scene().removeItem(proxy)
            proxy.deleteLater()
        if commit and cell is not None and self.active_table is not None:
            table = self.active_table
            if table.sheet.raw(*cell) != text:
                table.set_cell(cell[0], cell[1], text)
                self.window.recalculate()
                self.commit_snapshot("Edit cell")
            if move:
                table.move_current(*move)
                self.cellChanged.emit(table)
        self.setFocus(Qt.OtherFocusReason)

    def _apply_fill(self) -> None:
        table = self.active_table
        if table is None or self._fill_origin is None:
            return
        source = self._fill_origin
        self._fill_origin = None
        target = table.selection()
        if target == source:
            return
        filled = table.sheet.fill_series(source, target)
        if filled:
            self.window.recalculate()
            self.commit_snapshot("Fill")
            self.cellChanged.emit(table)
            self.statusMessage.emit(f"Filled {filled} cell(s)")

    # -- cell clipboard ----------------------------------------------------
    def copy_cells(self) -> bool:
        """Copy the selected cells as TSV, plus a full-fidelity private copy."""
        table = self.active_table
        if table is None:
            return False
        r0, c0, r1, c1 = table.selection()
        mime = QMimeData()
        mime.setText(table.sheet.region_text(r0, c0, r1, c1, raw=True))
        mime.setData(CELLS_MIME, json.dumps(
            table.sheet.region_payload(r0, c0, r1, c1)).encode("utf-8"))
        QApplication.clipboard().setMimeData(mime)
        count = (r1 - r0 + 1) * (c1 - c0 + 1)
        self.statusMessage.emit(f"Copied {count} cell(s)")
        return True

    def cut_cells(self) -> bool:
        table = self.active_table
        if table is None or not self.copy_cells():
            return False
        self.begin_snapshot()
        for row, col in table.selected_cells():
            table.sheet.set_raw(row, col, "")
        self.window.recalculate()
        self.commit_snapshot("Cut cells")
        return True

    def clipboard_cell_size(self) -> tuple[int, int]:
        """How many rows and columns are on the clipboard, spreadsheet-wise."""
        mime = QApplication.clipboard().mimeData()
        rows: list = []
        if mime.hasFormat(CELLS_MIME):
            try:
                rows = json.loads(
                    bytes(mime.data(CELLS_MIME)).decode("utf-8")).get("rows", [])
            except ValueError:
                rows = []
        if not rows:
            rows = parse_clipboard_grid(mime.text())
        return len(rows), max((len(line) for line in rows), default=0)

    def clipboard_is_a_block(self) -> bool:
        """True when the clipboard holds more than the one cell."""
        height, width = self.clipboard_cell_size()
        return height > 1 or width > 1

    def paste_cells(self) -> bool:
        """Paste into the active table, from CalcForge or from a spreadsheet."""
        table = self.active_table
        if table is None or table.locked:
            return False
        # A block of cells is a block wherever the reader happens to be: if a
        # cell is open for editing it is abandoned, not filled with the lot.
        if self._cell_editor is not None:
            if not self.clipboard_is_a_block():
                return False
            self.close_cell_editor(commit=False)
        mime = QApplication.clipboard().mimeData()
        row, col = table.current
        self.begin_snapshot()
        if mime.hasFormat(CELLS_MIME):
            try:
                payload = json.loads(bytes(mime.data(CELLS_MIME)).decode("utf-8"))
            except ValueError:
                payload = None
            if payload:
                height = len(payload.get("rows", []))
                width = max((len(line) for line in payload.get("rows", [])), default=0)
                table.sheet.grow_to_fit(row, col, height, width)
                table.sheet.paste_payload(payload, row, col)
                self._finish_paste(table, row, col, height, width)
                return True
        text = mime.text()
        if not text:
            return False
        lines = text.replace("\r\n", "\n").split("\n")
        table.sheet.grow_to_fit(row, col, len(lines),
                                max((len(l.split("\t")) for l in lines), default=1))
        height, width = table.sheet.paste_text(text, row, col)
        self._finish_paste(table, row, col, height, width)
        return True

    def _finish_paste(self, table, row: int, col: int, height: int, width: int) -> None:
        table.anchor = (min(row + max(height, 1) - 1, table.sheet.rows - 1),
                        min(col + max(width, 1) - 1, table.sheet.cols - 1))
        table.prepareGeometryChange()
        self.window.recalculate()
        self.commit_snapshot("Paste cells")
        self.cellChanged.emit(table)
        self.statusMessage.emit(f"Pasted {height}×{width} cell(s)")

    def fill_down(self) -> None:
        table = self.active_table
        if table is None:
            return
        r0, c0, r1, c1 = table.selection()
        if r1 <= r0:
            return
        self.begin_snapshot()
        for col in range(c0, c1 + 1):
            table.sheet.fill((r0, col), [(row, col) for row in range(r0 + 1, r1 + 1)])
        self.window.recalculate()
        self.commit_snapshot("Fill down")

    def fill_right(self) -> None:
        table = self.active_table
        if table is None:
            return
        r0, c0, r1, c1 = table.selection()
        if c1 <= c0:
            return
        self.begin_snapshot()
        for row in range(r0, r1 + 1):
            table.sheet.fill((row, c0), [(row, col) for col in range(c0 + 1, c1 + 1)])
        self.window.recalculate()
        self.commit_snapshot("Fill right")

    # ------------------------------------------------------------------
    # keyboard
    # ------------------------------------------------------------------
    def busy_typing(self) -> bool:
        """True while words are being typed into something on the page.

        A shortcut that acts on the document has no business firing while a
        sentence is being written: Ctrl+B belongs to the text under the caret,
        not to the bookmarks.
        """
        return (self._editing_item is not None or self.active_table is not None
                or self._cell_editor is not None or self._unit_editor is not None
                or getattr(self, "_label_editor", None) is not None)

    def idle_on_canvas(self) -> bool:
        """True when a keystroke should be read as "start something here".

        A lasso with only its first point down counts as idle: that is what one
        click on bare paper leaves behind, and a click on bare paper followed
        by typing is how most things get written on a page.
        """
        quiet = self._mode == "idle" or (self._mode == "lasso"
                                         and len(self._marquee) <= 2)
        return (self._editing_item is None and self.active_table is None
                and self._cell_editor is None and quiet
                and self.tool_key in ("select", "pan"))

    def pointer_scene_pos(self) -> QPointF:
        """Where the pointer last was, in canvas coordinates.

        Everything that has to land somewhere — a paste, something typed, a
        tool put down — lands here. There is no separate insertion point to
        set first and remember afterwards: what you are pointing at is where
        it goes, which is the one rule that needs no explaining.
        """
        return QPointF(self._last_scene_pos)

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        """Whatever floats above the page: marquee, previews, leaders."""
        super().drawForeground(painter, rect)
        if self._marquee:
            self._draw_marquee(painter)
        self._draw_group_boxes(painter)
        if self._pending_stamp is not None:
            self._draw_pending_preview(painter)
        if self._snap_marker is not None:
            self._draw_snap_marker(painter, self._snap_marker)
        if self._pending_anchor is not None:
            self._draw_pending_leader(painter, self._pending_anchor)

    def _draw_pending_preview(self, painter: QPainter) -> None:
        """Show what is about to be put down, under the pointer.

        A tool held in the hand is invisible until it lands otherwise, and a
        group of markups is impossible to place well when you cannot see how
        big it is or where its top-left will fall.
        """
        entry = self._pending_stamp
        if entry is None:
            return
        frame = self.frame_at(self._last_scene_pos) or self.frame()
        if frame is None:
            return
        origin = self._pending_origin(frame, self._last_scene_pos)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setOpacity(0.55)
        for data in self.pending_payloads():
            item = build_item(dict(data, uid="preview"))
            if item is None:
                continue
            if isinstance(item, ImageItem):
                item.load_from_document(self.document())
            at = frame.mapToScene(origin + QPointF(float(data.get("x", 0.0)),
                                                   float(data.get("y", 0.0))))
            painter.save()
            painter.translate(at)
            item.paint_content(painter)
            painter.restore()
        painter.setOpacity(1.0)
        box = self.pending_extent()
        top_left = frame.mapToScene(origin + box.topLeft())
        pen = QPen(QColor(11, 107, 203, 170))
        pen.setWidthF(0)
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(top_left, box.size()))
        painter.restore()

    # -- selecting with a marquee ------------------------------------------
    def marquee_polygon(self):
        """The marquee as a polygon, whichever shape it is."""
        if len(self._marquee) < 2:
            return QPolygonF()
        if self._mode == "rubber":
            rect = QRectF(self._marquee[0], self._marquee[-1]).normalized()
            return QPolygonF([rect.topLeft(), rect.topRight(),
                              rect.bottomRight(), rect.bottomLeft()])
        return QPolygonF(self._marquee)

    def marquee_crosses(self) -> bool:
        """True when the marquee also takes what it merely touches.

        Dragging right, as the drawing is read, takes only what is wholly
        inside; dragging back the other way takes anything it crosses. That is
        how every CAD program does it, and the two are worth telling apart.
        """
        return (self._mode == "rubber" and len(self._marquee) >= 2
                and self._marquee[-1].x() < self._marquee[0].x())

    def select_in_marquee(self) -> None:
        """Select what the marquee caught, then put it away."""
        polygon = self.marquee_polygon()
        crossing = self.marquee_crosses()
        self._marquee = []
        self._mode = "idle"
        self.viewport().update()
        if polygon.size() < 3:
            self.selectionChanged.emit()
            return
        area = polygon.boundingRect()
        scene = self.scene()
        for item in scene.items(area) if scene is not None else []:
            if not isinstance(item, MarkupItem) or not self.editable(item):
                continue
            box = item.sceneBoundingRect()
            if crossing:
                caught = polygon.intersects(QPolygonF(box))
            else:
                caught = all(polygon.containsPoint(corner, Qt.OddEvenFill)
                             for corner in (box.topLeft(), box.topRight(),
                                            box.bottomRight(), box.bottomLeft()))
            if caught:
                for member in self.group_of(item):
                    member.setSelected(True)
        self.selectionChanged.emit()

    def cancel_marquee(self) -> None:
        self._marquee = []
        self._mode = "idle"
        self.viewport().update()

    def _draw_marquee(self, painter: QPainter) -> None:
        """The marquee itself: solid to take what is inside, dashed to cross."""
        if self._mode == "lasso" and len(self._marquee) <= 2:
            return          # one click down: nothing to show yet
        polygon = self.marquee_polygon()
        if polygon.size() < 2:
            return
        crossing = self.marquee_crosses()
        colour = QColor("#2f9e44") if crossing else QColor("#1971c2")
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(colour)
        pen.setWidthF(0)
        if crossing or self._mode == "lasso":
            pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        fill = QColor(colour)
        fill.setAlpha(28)
        painter.setBrush(fill)
        if self._mode == "rubber":
            painter.drawRect(QRectF(self._marquee[0], self._marquee[-1]).normalized())
        else:
            painter.drawPolygon(polygon)
        painter.restore()

    def _draw_group_boxes(self, painter: QPainter) -> None:
        """One box around each selected group, rather than one per member.

        A group is one thing to click and move, so it should look like one
        thing when it is picked up; the members' own outlines say nothing that
        the group's does not.
        """
        families: dict = {}
        for item in self.scene().selectedItems() if self.scene() else []:
            name = getattr(item, "group", "")
            if name:
                families.setdefault(name, []).append(item)
        if not families:
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(QColor(11, 107, 203, 190))
        pen.setWidthF(0)
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(QColor(11, 107, 203, 12))
        margin = 5.0 / max(self._zoom, 0.05)
        for members in families.values():
            box = members[0].sceneBoundingRect()
            for item in members[1:]:
                box = box.united(item.sceneBoundingRect())
            painter.drawRect(box.adjusted(-margin, -margin, margin, margin))
        painter.restore()

    def _draw_pending_leader(self, painter: QPainter, anchor: QPointF) -> None:
        """The callout's arrow, drawn the moment it is placed.

        Clicking what a callout points at used to leave nothing behind but the
        same faint cross that marks any insert point, so there was no telling
        whether the click had registered or what it had done. The arrow head
        is drawn where it will be, with the leader trailing to the pointer.
        """
        from ..items.base import arrow_path

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        colour = QColor(self.window.default_style.stroke or "#e8590c")
        pen = QPen(colour)
        pen.setWidthF(max(self.window.default_style.width, 1.0))
        painter.setPen(pen)
        target = self._draft_leader_target()
        if target is not None:
            painter.drawLine(anchor, target)
            angle = math.atan2(anchor.y() - target.y(), anchor.x() - target.x())
        else:
            angle = -math.pi / 4
        painter.setBrush(colour)
        painter.drawPath(arrow_path(anchor, angle,
                                    max(pen.widthF() * 4.5, 9.0), "arrow"))
        painter.restore()

    def _draft_leader_target(self) -> Optional[QPointF]:
        """Where the pending leader is heading: the box, or the pointer."""
        draft = self._draft
        if draft is not None and draft.scene() is not None:
            return draft.mapToScene(draft.local_rect().center())
        return QPointF(self._last_scene_pos)

    def _draw_snap_marker(self, painter: QPainter, point: QPointF) -> None:
        """A small square where the pointer has caught hold of something."""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        arm = 4.5 / max(self._zoom, 0.05)
        pen = QPen(QColor("#e8590c"))
        pen.setWidthF(0)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(point.x() - arm, point.y() - arm, arm * 2, arm * 2))
        painter.restore()

    def typing_position(self) -> QPointF:
        """Where a region opened by typing should appear, in page coordinates."""
        anchor = QPointF(self._last_scene_pos)
        frame = self.frame_at(anchor) or self.frame()
        if frame is None:
            return QPointF(self._last_scene_pos)
        point = frame.mapFromScene(anchor)
        if not frame.page_rect().contains(point):
            left, top, _width, _height = frame.page.setup.content_rect_pt
            point = QPointF(left, top)
        return self.snap(point)

    def typing_frame(self):
        """The page a region opened by typing belongs to."""
        return self.frame_at(self._last_scene_pos) or self.frame()

    def event(self, event) -> bool:
        """Take Tab before Qt spends it moving the focus.

        Qt treats Tab as "go to the next widget" and never lets it reach
        keyPressEvent, but on a canvas Tab is how a completion is accepted and
        how the next cell is reached. It is only taken when something is
        actually being typed into; otherwise it moves the focus as it always
        did.
        """
        if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Tab,
                                                               Qt.Key_Backtab):
            if self._editing_item is not None or self._cell_editor is not None:
                event.accept()
                self.keyPressEvent(event)
                if event.isAccepted():
                    return True
        return super().event(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        modifiers = event.modifiers()

        # While a region or a cell is being edited every key belongs to it —
        # arrows move the caret, not the markup — apart from Escape, which
        # finishes the edit.
        if self._unit_editor is not None:
            if key == Qt.Key_Escape:
                self.close_unit_editor(commit=False)
                event.accept()
                return
            super().keyPressEvent(event)
            return

        if self._label_editor is not None:
            if key == Qt.Key_Escape:
                self.close_label_editor(commit=False)
                event.accept()
                return
            super().keyPressEvent(event)
            return

        if self._editing_item is not None and self._cell_editor is None:
            # The completion list takes the keys that drive it, and nothing
            # else: everything it does not use goes on to the text.
            if self.completions_showing():
                if key == Qt.Key_Escape:
                    self.hide_completions()
                    event.accept()
                    return
                if key in (Qt.Key_Tab, Qt.Key_Backtab):
                    if self.accept_completion():
                        event.accept()
                        return
                if key in (Qt.Key_Down, Qt.Key_Up):
                    self.move_completion(1 if key == Qt.Key_Down else -1)
                    event.accept()
                    return
            elif key in (Qt.Key_Tab, Qt.Key_Backtab):
                # Tab with nothing offered asks for the list.
                self.show_completions()
                if self.completions_showing() and self.accept_completion():
                    event.accept()
                    return

        if self._editing_item is not None or self._cell_editor is not None:
            if key == Qt.Key_Escape:
                if self._cell_editor is not None:
                    self.close_cell_editor(commit=False)
                else:
                    self.end_item_edit()
                event.accept()
                return
            # Pasting a block of cells into an open cell would put the whole
            # sheet into that one box. It goes across the cells instead; a
            # single cell still pastes into the text being typed.
            if (self._cell_editor is not None and key == Qt.Key_V
                    and modifiers & Qt.ControlModifier
                    and self.clipboard_is_a_block()):
                self.paste_cells()
                event.accept()
                return
            # An arrow key in the middle of a formula chooses the cell to refer
            # to rather than moving the caret, the way it does in Excel.
            arrows = {Qt.Key_Left: (0, -1), Qt.Key_Right: (0, 1),
                      Qt.Key_Up: (-1, 0), Qt.Key_Down: (1, 0)}
            if (self._cell_editor is not None and key in arrows
                    and not (modifiers & Qt.ControlModifier)
                    and self.pointing_allowed()):
                start = self._pointing or self._editing_cell or (0, 0)
                step = arrows[key]
                self.point_at(start[0] + step[0], start[1] + step[1])
                event.accept()
                return
            # Typing a value and pressing an arrow puts it in and moves on,
            # which is how a column of numbers gets entered in Excel.
            if (self._cell_editor is not None and key in (Qt.Key_Up, Qt.Key_Down)
                    and not (modifiers & Qt.ControlModifier)):
                self.close_cell_editor(move=(-1 if key == Qt.Key_Up else 1, 0))
                event.accept()
                return
            if self._cell_editor is not None and key in (Qt.Key_Tab, Qt.Key_Backtab):
                self.close_cell_editor(move=(0, -1 if key == Qt.Key_Backtab else 1))
                event.accept()
                return
            super().keyPressEvent(event)
            if self._editing_item is not None and self._cell_editor is None:
                if event.text().isalnum() or event.text() == "_":
                    self.show_completions()
                elif key in (Qt.Key_Backspace, Qt.Key_Delete):
                    self.show_completions()
                else:
                    self.hide_completions()
            return

        if key == Qt.Key_Space and not event.isAutoRepeat():
            self._space_pan = True
            self.setCursor(Qt.OpenHandCursor)
            event.accept()
            return

        if key == Qt.Key_Escape:
            if self.clear_pending_tool():
                self.statusMessage.emit("Put the tool back")
                event.accept()
                return
            if self._pending_anchor is not None:
                self._pending_anchor = None
                self.statusMessage.emit("Callout cancelled")
                event.accept()
                return
            if self._mode == "lasso":
                self.cancel_marquee()
            elif self._mode in ("draw_poly", "draw_click"):
                self.cancel_draft()
            elif getattr(self, "_editing_item", None) is not None:
                self.end_item_edit()
            elif self._cell_editor is not None:
                self.close_cell_editor(commit=False)
            elif self.active_table is not None:
                self.deactivate_table()
            else:
                self.set_tool("select")
                self.toolFinished.emit("select")
            event.accept()
            return

        if self.active_table is not None and self._cell_editor is None:
            if self._table_key(event):
                return

        if key in (Qt.Key_Return, Qt.Key_Enter) and self._mode == "draw_poly":
            self.finish_poly()
            event.accept()
            return

        if key in (Qt.Key_Return, Qt.Key_Enter) and self._mode == "lasso":
            self.select_in_marquee()
            event.accept()
            return

        if key in (Qt.Key_Delete, Qt.Key_Backspace) and self.scene().selectedItems():
            self.window.delete_selection()
            event.accept()
            return

        # A bare keystroke on the canvas only does something if it is bound:
        # '"' starts text, '\\' starts maths, tool keys pick their tool.
        if self.idle_on_canvas():
            # The number keys reach for My Tools, before anything else is
            # asked about the keystroke: 1 to 9 are the first nine things in it.
            if event.text().isdigit() and event.text() != "0":
                if self.window.activate_my_tool(int(event.text())):
                    event.accept()
                    return
            if self.window.run_typed_binding(event.text(), modifiers,
                                             self.from_page(self.typing_position(),
                                                            self.typing_frame())):
                event.accept()
                return
            if event.text() and event.text().isprintable():
                event.accept()          # unbound: deliberately nothing happens
                return

        if key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            step = 1.0 if modifiers & Qt.ShiftModifier else 0.25 * MM_TO_PT * 4
            delta = {Qt.Key_Left: QPointF(-step, 0), Qt.Key_Right: QPointF(step, 0),
                     Qt.Key_Up: QPointF(0, -step), Qt.Key_Down: QPointF(0, step)}[key]
            items = [i for i in self.scene().selectedItems()
                     if isinstance(i, MarkupItem) and self.editable(i)]
            if items:
                self.begin_snapshot(self.all_frames())
                for item in items:
                    self._place(item, item.pos() + delta)
                self.settle_pages(items)
                self.commit_snapshot("Nudge markup")
                event.accept()
                return
            # Nothing selected: the arrows scroll the document, as they would
            # in anything else you read.
            self.scroll_by(delta * 3)
            event.accept()
            return

        if self.navigation_key(event):
            return

        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # getting about
    # ------------------------------------------------------------------
    def scroll_by(self, delta: QPointF) -> None:
        """Scroll the canvas by *delta*, given in scene units."""
        self.horizontalScrollBar().setValue(
            self.horizontalScrollBar().value() + int(delta.x() * self._zoom))
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().value() + int(delta.y() * self._zoom))

    def navigation_key(self, event: QKeyEvent) -> bool:
        """Page Up/Down, Home and End, as every document reader binds them.

        Ctrl makes Page Up/Down jump a whole page rather than a screenful, and
        Ctrl+Home and Ctrl+End go to the ends of the document.
        """
        key = event.key()
        control = bool(event.modifiers() & Qt.ControlModifier)
        bar = self.verticalScrollBar()
        screen = max(bar.pageStep(), 1)
        if key == Qt.Key_PageDown:
            bar.setValue(bar.value() + screen)   # Ctrl+PgDn is a window action
            event.accept()
            return True
        if key == Qt.Key_PageUp:
            bar.setValue(bar.value() - screen)
            event.accept()
            return True
        if key == Qt.Key_Home:
            bar.setValue(bar.minimum() if control
                         else int(self._page_top_value(self.visible_page_index())))
            event.accept()
            return True
        if key == Qt.Key_End:
            if control:
                bar.setValue(bar.maximum())
            else:
                bar.setValue(int(self._page_top_value(self.visible_page_index())
                                 + self.page_height_in_view()) - screen)
            event.accept()
            return True
        return False

    def _page_top_value(self, index: int) -> float:
        scene = self.scene()
        if scene is None or not scene.frames:
            return float(self.verticalScrollBar().value())
        index = max(0, min(index, len(scene.frames) - 1))
        frame = scene.frames[index]
        top = frame.mapRectToScene(frame.page_rect()).top()
        return (top - scene.sceneRect().top()) * self._zoom

    def page_height_in_view(self) -> float:
        frame = self.frame()
        return frame.page.height_pt * self._zoom if frame is not None else 0.0

    def _table_key(self, event: QKeyEvent) -> bool:
        table = self.active_table
        key = event.key()
        modifiers = event.modifiers()
        extend = bool(modifiers & Qt.ShiftModifier)
        moves = {Qt.Key_Left: (0, -1), Qt.Key_Right: (0, 1), Qt.Key_Up: (-1, 0),
                 Qt.Key_Down: (1, 0)}
        if key in moves:
            table.move_current(*moves[key], extend=extend)
            self.cellChanged.emit(table)
            event.accept()
            return True
        if key == Qt.Key_Tab:
            table.move_current(0, 1)
            self.cellChanged.emit(table)
            event.accept()
            return True
        if key == Qt.Key_Backtab:
            table.move_current(0, -1)
            self.cellChanged.emit(table)
            event.accept()
            return True
        if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_F2):
            self.open_cell_editor()
            event.accept()
            return True
        if key in (Qt.Key_Delete, Qt.Key_Backspace):
            self.begin_snapshot()
            for row, col in table.selected_cells():
                table.sheet.set_raw(row, col, "")
            self.window.recalculate()
            self.commit_snapshot("Clear cells")
            event.accept()
            return True
        if key == Qt.Key_D and modifiers & Qt.ControlModifier:
            self.fill_down()
            event.accept()
            return True
        if key == Qt.Key_R and modifiers & Qt.ControlModifier:
            self.fill_right()
            event.accept()
            return True
        if key == Qt.Key_Home:
            table.current = table.anchor = (0, 0)
            table.update()
            self.cellChanged.emit(table)
            event.accept()
            return True
        text = event.text()
        if text and text.isprintable() and not (modifiers & Qt.ControlModifier):
            self.open_cell_editor(initial=text)
            event.accept()
            return True
        return False

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._space_pan = False
            self.setCursor(self._cursor_for_tool(self.current_tool()))
            event.accept()
            return
        super().keyReleaseEvent(event)

    def focusOutEvent(self, event) -> None:
        if getattr(self, "_editing_item", None) is not None:
            self.end_item_edit()
        super().focusOutEvent(event)

    # ------------------------------------------------------------------
    # context menu
    # ------------------------------------------------------------------
    def contextMenuEvent(self, event) -> None:
        scene_pos = self.mapToScene(event.pos())
        item = self.markup_at(scene_pos)
        if item is not None and not item.isSelected():
            self.scene().clearSelection()
            item.setSelected(True)
            self.selectionChanged.emit()
        menu = self.window.build_context_menu(item, scene_pos)
        menu.exec(event.globalPos())


def _looks_like_a_ref(text: str) -> bool:
    """A1, or BC24 — what point_at writes into a formula."""
    return bool(re.fullmatch(r"[A-Z]{1,3}\d{1,5}", text))


def _is_a_unit(text: str) -> bool:
    """True when pint can make sense of what was typed."""
    try:
        return parse_unit(text) is not None
    except Exception:                        # noqa: BLE001 - anything pint throws
        return False


def _far_enough(a: QPointF, b: QPointF) -> bool:
    return math.hypot(b.x() - a.x(), b.y() - a.y()) >= FREE_MIN_STEP
