"""The interactive page canvas: tools, selection, editing and navigation."""
from __future__ import annotations

import math

import numpy  # noqa: F401  (loaded now: the first drag that snaps needs it at once)
import os
import re
from copy import deepcopy
from typing import Optional

from PySide6.QtCore import (QEvent, QObject, QPoint, QPointF, QRect, QRectF, Qt,
                            QTimer, Signal)
from PySide6.QtGui import (QBrush, QColor, QCursor, QKeyEvent,
                           QMouseEvent, QPainter, QPen, QPolygonF, QTextCursor,
                           QPixmap, QTransform, QWheelEvent)
from PySide6.QtWidgets import (QApplication, QGraphicsProxyWidget,
                               QGraphicsView, QGridLayout, QLabel,
                               QLineEdit, QWidget)

from ..core.document import MM_TO_PT
from ..items.calc import CalcBlockItem, CalcItem, CalcTextItem
from ..items.base import (HANDLE_SCREEN_PX, HANDLE_SIZE,
                          MarkupItem, build_item, cursor_for_handle, rename_groups)
from ..items.contents import ContentsItem
from .scene import DocumentScene, PageFrame, detach
from ..items.measure import (CALIBRATE, DIMENSION, CountItem,
                             MeasureItem)
from ..items.media import ImageItem
from ..items.shapes import PolyItem, RectItem
from ..items.text import CalloutItem, NoteItem, StampItem, TextItem, _TextBase
from . import preferences
from .commands import PageEditCommand
from .tools import (ANCHOR, CLICK, CLOUD, CLOUDY, ERASE, FREE, NONE, POLY,
                    SNAPSHOT,
                    TOOL_MAP, Tool)

# How far the insertion point steps down the page for one press of an arrow:
# a line of ordinary text, which is what it is placing.
LINE_STEP = 6.0

MIN_ZOOM = 0.08
MAX_ZOOM = 16.0
CLICK_SLOP = 3.0
# Qt's default wheel step is deliberately coarse for list widgets. On a
# drawing canvas that jumps past the detail somebody is trying to inspect, so
# angle-based mouse wheels use a quarter pixel per angle unit (30 px/notch).
WHEEL_SCROLL_FACTOR = 0.25
# How near the pointer has to be, in view pixels, to catch a drawn point.
#: What Ctrl+B, Ctrl+I and Ctrl+U do to the words being typed.
_FORMATTING_KEYS = {
    Qt.Key_B: lambda window: window.toggle_bold(),
    Qt.Key_I: lambda window: window.toggle_italic(),
    Qt.Key_U: lambda window: window.toggle_underline(),
}

SNAP_REACH = 9.0

# How many nearby straight runs are worth comparing for crossings. Every pair
# of them is tested, so this is what keeps a sheet with thousands of segments
# on it from turning one mouse move into a million comparisons. Around the
# pointer there are rarely more than a handful.
MOST_CROSSING_SIDES = 24

# A shape with more corners than this is a traced curve rather than something
# with sides anybody aims at, and its segments are not offered as crossings.
MOST_SIDES = 200
# The shapes drawn to a size somebody cares about, and so worth measuring,
# asking an exact size for, and writing that size on.
SIZED_SHAPES = ("rect", "ellipse")
CELLS_MIME = "application/x-calcforge-cells"
FREE_MIN_STEP = 1.2
_RESHAPE_CURSORS: dict[str, QCursor] = {}
_DRAWING_CURSORS: dict[str, QCursor] = {}


def _reshape_cursor(operation: str) -> QCursor:
    """A compact point-add, point-remove, or curve affordance."""
    kind = "curve" if operation in ("round", "curve") else operation
    if kind in _RESHAPE_CURSORS:
        return _RESHAPE_CURSORS[kind]
    pixmap = QPixmap(28, 28)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    outline = QPen(QColor("#ffffff"), 4.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    ink = QPen(QColor("#1971c2"), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    if kind == "curve":
        for pen in (outline, ink):
            painter.setPen(pen)
            painter.drawArc(QRectF(3, 5, 19, 17), 25 * 16, 125 * 16)
            painter.drawEllipse(QPointF(5, 20), 2.2, 2.2)
            painter.drawEllipse(QPointF(22, 8), 2.2, 2.2)
    else:
        painter.setPen(outline)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QPointF(9, 9), 5.0, 5.0)
        painter.setPen(ink)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QPointF(9, 9), 5.0, 5.0)
        painter.drawLine(QPointF(17, 20), QPointF(25, 20))
        if kind == "add":
            painter.drawLine(QPointF(21, 16), QPointF(21, 24))
    painter.end()
    cursor = QCursor(pixmap, 9, 9)
    _RESHAPE_CURSORS[kind] = cursor
    return cursor


def format_painter_cursor() -> QCursor:
    """The paint-brush pointer shown while Format Painter holds a look."""
    if "format_painter" not in _DRAWING_CURSORS:
        from . import icons

        pixmap = QPixmap(28, 28)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        # A white halo so the brush reads on a dark drawing as well as paper.
        halo = icons.cursor_pixmap("format_painter", 26)
        painter.drawPixmap(1, 1, halo)
        painter.end()
        _DRAWING_CURSORS["format_painter"] = QCursor(pixmap, 3, 25)
    return _DRAWING_CURSORS["format_painter"]


def excel_cursor(kind: str) -> QCursor:
    """Excel's own pointers over cells: the fat white plus over a cell
    ("cell"), the black arrow down a column heading ("col") and across a row
    heading ("row")."""
    key = "excel_" + kind
    if key in _DRAWING_CURSORS:
        return _DRAWING_CURSORS[key]
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, False)
    if kind == "cell":
        from PySide6.QtGui import QPainterPath
        plus = QPainterPath()
        arm, half = 7, 3                     # 7 px arms either side of a 7 px square
        c = 15
        plus.moveTo(c - half, c - half - arm)
        for dx, dy in ((2 * half, 0), (0, arm), (arm, 0), (0, 2 * half), (-arm, 0), (0, arm),
                       (-2 * half, 0), (0, -arm), (-arm, 0), (0, -2 * half), (arm, 0)):
            point = plus.currentPosition()
            plus.lineTo(point.x() + dx, point.y() + dy)
        plus.closeSubpath()
        painter.setPen(QPen(QColor("#000000"), 1))
        painter.setBrush(QColor("#ffffff"))
        painter.drawPath(plus)
        hot = (c, c)
    else:
        from PySide6.QtGui import QPolygonF
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor("#ffffff"), 1))
        painter.setBrush(QColor("#000000"))
        if kind == "col":                    # pointing down
            arrow = [(13, 2), (19, 2), (19, 14), (24, 14), (16, 24), (8, 14), (13, 14)]
            hot = (16, 24)
        else:                                # pointing right
            arrow = [(2, 13), (2, 19), (14, 19), (14, 24), (24, 16), (14, 8), (14, 13)]
            hot = (24, 16)
        painter.drawPolygon(QPolygonF([QPointF(x, y) for x, y in arrow]))
    painter.end()
    cursor = QCursor(pixmap, *hot)
    _DRAWING_CURSORS[key] = cursor
    return cursor


def drawing_cursor(icon_name: str) -> QCursor:
    """A precise crosshair carrying the icon of the active drawing gesture."""
    if icon_name in _DRAWING_CURSORS:
        return _DRAWING_CURSORS[icon_name]
    from . import icons

    pixmap = QPixmap(34, 34)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.drawPixmap(10, 0, icons.cursor_pixmap(icon_name, 22))
    for pen in (QPen(QColor("#ffffff"), 3.5),
                QPen(QColor("#1971c2"), 1.4)):
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(QPointF(1, 27), QPointF(11, 27))
        painter.drawLine(QPointF(6, 22), QPointF(6, 32))
    painter.end()
    cursor = QCursor(pixmap, 6, 27)
    _DRAWING_CURSORS[icon_name] = cursor
    return cursor


class _SizeEdit(QLineEdit):
    """A canvas size field: Escape cancels, Tab moves on, Enter places."""

    escapePressed = Signal()
    tabPressed = Signal(bool)          # True forwards, False backwards
    enterPressed = Signal()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.escapePressed.emit()
            event.accept()
            return
        if event.key() in (Qt.Key_Tab, Qt.Key_Backtab):
            forwards = (event.key() == Qt.Key_Tab
                        and not event.modifiers() & Qt.ShiftModifier)
            self.tabPressed.emit(forwards)
            event.accept()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.enterPressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def event(self, event) -> bool:
        # Tab must reach keyPressEvent rather than move focus off the canvas.
        if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Tab,
                                                                 Qt.Key_Backtab):
            self.keyPressEvent(event)
            return True
        return super().event(event)

    def focusInEvent(self, event) -> None:
        # The box shows the size the shape is at, so the first thing typed
        # into it means "make it this instead" — not "add these digits to the
        # end of what it already says".
        super().focusInEvent(event)
        self.selectAll()


_CLOUD_CURSOR = None


def cloud_cursor() -> QCursor:
    """A pointer carrying a small revision cloud, drawn once and kept."""
    global _CLOUD_CURSOR
    if _CLOUD_CURSOR is None:
        from . import icons

        pixmap = icons.cursor_pixmap("cloud", 24)
        # Hot spot at the middle, because the cloud is drawn around the point.
        _CLOUD_CURSOR = QCursor(pixmap, 12, 12)
    return _CLOUD_CURSOR


def _with_a_halo(pixmap: QPixmap) -> QPixmap:
    """The drawing with a thin white edge round it, to read over dark ink."""
    white = QPixmap(pixmap.size())
    white.fill(Qt.transparent)
    tint = QPainter(white)
    tint.drawPixmap(0, 0, pixmap)
    tint.setCompositionMode(QPainter.CompositionMode_SourceIn)
    tint.fillRect(white.rect(), QColor("#ffffff"))
    tint.end()
    out = QPixmap(pixmap.size())
    out.fill(Qt.transparent)
    painter = QPainter(out)
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
        painter.drawPixmap(dx, dy, white)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return out


_ARROW_LEADER_CURSOR = None


def arrow_leader_cursor() -> QCursor:
    """The Callout drawing as the pointer, its arrowhead the point clicked.

    Adding an arrow leader is saying where the arrow points, so the tip of
    the drawn arrow is the pointer's hot spot — not a crosshair off to one
    side with the arrow pointing somewhere else.
    """
    global _ARROW_LEADER_CURSOR
    if _ARROW_LEADER_CURSOR is None:
        from . import icons

        size = 32
        pixmap = _with_a_halo(icons.cursor_pixmap("callout", size))
        # The icon's arrowhead ends at (4, 20.5) of 24.
        _ARROW_LEADER_CURSOR = QCursor(pixmap, round(4 * size / 24), round(20.5 * size / 24))
    return _ARROW_LEADER_CURSOR


_CLOUD_CALLOUT_CURSOR = None


def cloud_callout_cursor() -> QCursor:
    """The Cloud+ drawing — note, leader and cloud — as the pointer.

    What is being drawn is a cloud with a note on it, so the pointer says so
    rather than showing a bare cloud. The hot spot is the middle of its
    cloud, where the cloud is drawn round.
    """
    global _CLOUD_CALLOUT_CURSOR
    if _CLOUD_CALLOUT_CURSOR is None:
        from . import icons

        pixmap = _with_a_halo(icons.cursor_pixmap("cloud_callout", 32))
        # The icon's cloud sits at (1.5–13.5, 13–21.5) of 24: its middle.
        _CLOUD_CALLOUT_CURSOR = QCursor(pixmap, round(7.5 * 32 / 24), round(17.2 * 32 / 24))
    return _CLOUD_CALLOUT_CURSOR


def typing_somewhere_else() -> bool:
    """True when the keyboard belongs to a box somebody is typing into.

    Panels are full of fields, and taking the focus off one mid-word would
    lose the word. So the page only takes the keyboard back when nothing is
    being typed anywhere.
    """
    from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QComboBox,
                                   QLineEdit, QPlainTextEdit, QTextEdit)

    widget = QApplication.focusWidget()
    if widget is None:
        return False
    typers = (QLineEdit, QPlainTextEdit, QTextEdit, QAbstractSpinBox, QComboBox)
    while widget is not None:
        if isinstance(widget, typers):
            return True
        widget = widget.parentWidget()
    return False



class _Glide(QObject):
    """A wheel notch glides rather than jumps (the user, 2026-10-01: "jittery,
    it needs to be ultra smooth"). Each notch moves where the view is going;
    every frame the view covers a share of what is left — the same share per
    millisecond whatever the frame rate — so a quick spin of the wheel is one
    continuous movement and a single notch eases in and out of its 30 px.
    Anything else that moves the view (the scroll bar, a key, a pan) wins
    straight away: the glide notices and lets go."""

    #: how quickly what is left is covered: ~95% of it in 3 x this
    EASE_MS = 38.0

    def __init__(self, view):
        super().__init__(view)
        from PySide6.QtCore import QElapsedTimer, QTimer
        self.view = view
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.setInterval(7)
        self.timer.timeout.connect(self._step)
        self.clock = QElapsedTimer()
        self.axes = {}        # bar -> [where it is going, where it is (float), what was set]
        # A zoom glides the same way: [zoom it is going to, the point it is
        # about (view pixels), the zoom last set] — or None.
        self.zooming = None

    def zoom_by(self, factor: float, at) -> None:
        """Zoom by *factor* about *at* (a point of the view), gliding."""
        view = self.view
        state = self.zooming
        if state is None or abs(view.zoom() - state[2]) > 1e-9:
            state = self.zooming = [view.zoom(), None, view.zoom(), None]
        state[0] = min(max(state[0] * factor, MIN_ZOOM), MAX_ZOOM)
        if state[1] is None or QPointF(at) != state[1]:
            # the canvas point under the pointer, exactly, kept there all the way
            state[1] = QPointF(at)
            state[3] = view.viewportTransform().inverted()[0].map(QPointF(at))
        view.zooming_by_hand()
        # where it is going is known now: have it drawn on the way there
        view.expect_zoom(state[0], state[1], state[3])
        if not self.timer.isActive():
            self.clock.start()
            self.timer.start()

    def by(self, bar, distance: float) -> None:
        state = self.axes.get(bar)
        if state is None or bar.value() != state[2]:
            state = [float(bar.value()), float(bar.value()), bar.value()]
            self.axes[bar] = state
        state[0] = min(max(state[0] + distance, bar.minimum()), bar.maximum())
        if not self.timer.isActive():
            self.clock.start()
            self.timer.start()

    def finish(self) -> None:
        """Arrive now: wherever every glide was going."""
        state, self.zooming = self.zooming, None
        if state is not None and abs(self.view.zoom() - state[2]) <= 1e-9:
            self.view.set_zoom(state[0], at=state[1], keep=state[3])
        for bar, state in list(self.axes.items()):
            if bar.value() == state[2]:
                bar.setValue(round(state[0]))
        self.axes.clear()
        self.timer.stop()

    def _zoom_step(self, share: float) -> None:
        import math
        view, state = self.view, self.zooming
        if abs(view.zoom() - state[2]) > 1e-9:
            self.zooming = None                # zoomed some other way: it wins
            return
        target, at, _set, keep = state
        apart = math.log(target / view.zoom())
        here = target if abs(apart) * (1.0 - share) < 0.002 else \
            view.zoom() * math.exp(apart * share)
        view.zooming_by_hand()
        view.set_zoom(here, at=at, keep=keep)
        state[2] = view.zoom()
        if here == target or abs(view.zoom() - target) < 1e-9:
            self.zooming = None

    def _step(self) -> None:
        import math
        from .markuplayer import busy
        busy()
        elapsed = max(self.clock.restart(), 1)
        share = 1.0 - math.exp(-elapsed / self.EASE_MS)
        if self.zooming is not None:
            self._zoom_step(share)
        for bar, state in list(self.axes.items()):
            if bar.value() != state[2]:
                del self.axes[bar]              # something else moved it: it wins
                continue
            target, here, _set = state
            here += (target - here) * share
            if abs(target - here) < 0.5:
                here = target
            state[1] = here
            state[2] = round(here)
            bar.setValue(state[2])
            if here == target:
                del self.axes[bar]
        if not self.axes and self.zooming is None:
            self.timer.stop()

class PageView(QGraphicsView):
    """Displays one :class:`~calcforge.ui.scene.PageScene` and edits it."""

    toolFinished = Signal(str)
    statusMessage = Signal(str)
    cursorMoved = Signal(QPointF)
    zoomChanged = Signal(float)
    selectionChanged = Signal()
    itemActivated = Signal(object)
    documentEdited = Signal()
    pageChanged = Signal(int)

    def __init__(self, window):
        super().__init__()
        self.window = window
        # Equations: the one being typed into, the red cross, SMath's keys.
        from .calcedit import CalcEditing
        self.calc = CalcEditing(self)
        # Tables: the one open for its cells, its selection, Excel's keys.
        from .tableedit import TableEditing
        self.tables = TableEditing(self)
        # a spreadsheet page's headings, kept in view as Excel keeps them
        from .sheetheadings import SheetHeadings
        self.sheet_headings = SheetHeadings(self)
        self.glide = _Glide(self)
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
        # Whether Shift was down when a handle drag started, for the handles
        # where that decides what the drag is rather than how it behaves.
        self._handle_shift: Optional[bool] = None
        self._handle_key = ""
        self._group_handle_key = ""
        self._group_resize_box = QRectF()
        self._group_resize_items = []
        self._move_items: list[tuple[MarkupItem, QPointF]] = []
        self._move_original_data: dict[str, dict] = {}
        self._shift_click_selection = None
        self._snapshot: list[dict] = []
        # The selection marquee, in scene coordinates: two corners while it is
        # a rectangle, every corner while it is a lasso.
        self._marquee: list = []
        self._keep_selection = False
        self._space_pan = False
        self._pan_origin = QPoint()
        self._zoom = 1.0
        self.scroll_mode = "continuous"

        self._live_timer = None
        self._draw_origin: Optional[QPointF] = None
        # Ctrl held when a drag starts leaves the originals where they were.
        self._copy_on_move = False
        self._copied = False
        self._snap_marker: Optional[QPointF] = None
        # What that marker is sitting on, in words.
        self._snap_caught = ""
        # The levels and uprights the pointer is currently lined up with,
        # drawn right across the page so it is obvious what it caught.
        self._snap_guides: list = []
        # Held while a tool set's tool is in hand: something to place, or
        # properties for the next thing drawn.
        self._pending_stamp = None
        self._pending_properties: Optional[dict] = None
        self._label_editor: Optional[QLineEdit] = None
        self._label_proxy: Optional[QGraphicsProxyWidget] = None
        self._label_item = None
        self._size_editor: Optional[QWidget] = None
        self._size_proxy: Optional[QGraphicsProxyWidget] = None
        self._size_width: Optional[QLineEdit] = None
        self._size_height: Optional[QLineEdit] = None
        self._size_rotation: Optional[QLineEdit] = None
        self._size_current: Optional[QLineEdit] = None
        self._size_unit = "mm"
        self._typed_size = False
        self._typed_w: Optional[float] = None
        self._typed_h: Optional[float] = None
        self._typed_rotation: Optional[float] = None
        self._editing_item = None
        # What the region being typed into said when the answers were last
        # worked out.

        self._last_scene_pos = QPointF(60, 60)
        self._insertion_point: Optional[QPointF] = None
        # Where the next thing typed, inserted or pasted will go, and
        # what a callout is about to point at.
        # Whether Ctrl is down, as this view saw it. Kept as well as asking
        # the application, because the view hears the press first and because
        # a key held down is state, not an event.
        self._control_held = False
        self._shift_held = False
        self._pending_anchor: Optional[QPointF] = None
        # The cloud a cloud call-out has already drawn, waiting for its words.
        self._pending_cloud = None
        # An existing text box/callout waiting for the user to drag the region
        # of a new cloud leader. Nothing changes until that drag lands.
        self._pending_cloud_leader = None
        # And the note waiting for a click to say where its new arrow points.
        self._pending_arrow_leader = None
        # How far the page is turned on screen, in degrees. This is a way of
        # looking at the document, not a change to it: nothing is saved, and
        # what prints is unaffected.
        self._view_turn = 0
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

    def page_of(self, item):
        """The page a markup is actually on.

        A measurement means what it means on its own page: its own scale, not
        the scale of whatever page the view happens to be looking at. Reading
        the view's page is why a dimension's value used to change while its
        text was being dragged and come right again on release.
        """
        frame = item.parentItem() if item is not None else None
        page = getattr(frame, "page", None)
        return page if page is not None else self.page()

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

        Every committed gesture leaves the page consistent — the takeoff list
        added up again, the panels showing what is actually selected — rather
        than each gesture having to remember to ask for it.
        """
        # Equations moved by the gesture are calculated now it is over.
        from ..calc.docsheet import sheet_for
        sheet_for(self.window.document).settle()
        # An equation left past the bottom of its page goes to the next one
        # (decision 11) — in the same undo step as what put it there.
        overflow = self.calc.take_overflow()
        if overflow:
            # One undo step for the lot. Pages may be added, and a page
            # added or restored rebuilds the page frames, so this is recorded
            # as a change to the document's structure — from how the pages
            # were when the gesture began to how they are once the equations
            # have gone on — rather than as page edits that would be left
            # pointing at frames that no longer exist.
            before = self.window._structure_snapshot()
            by_uid = {entry["uid"]: entry for entry in before["pages"]}
            for frame, items in (self._snapshot or []):
                entry = by_uid.get(frame.page.uid)
                if entry is not None:
                    entry["items"] = items
            self._snapshot = []
            self.calc.push_to_next_pages(overflow)
            self.window.record_structure_change(before, text)
            self.documentEdited.emit()
            return
        # A spreadsheet whose cells now reach past its last page grows a page
        # (the user's choice) — in the same undo step as what made it grow.
        from . import sheetpages
        short = sheetpages.short_runs(self.window) if self.window.scene is not None else []
        if short:
            before = self.window._structure_snapshot()
            by_uid = {entry["uid"]: entry for entry in before["pages"]}
            for frame, items in (self._snapshot or []):
                entry = by_uid.get(frame.page.uid)
                if entry is not None:
                    entry["items"] = items
            self._snapshot = []
            sheetpages.add_run_pages(self.window, short)
            self.window.record_structure_change(before, text)
            self.documentEdited.emit()
            return
        self._commit_snapshot(text, coalesce)

    def frame_for_page(self, page_uid: str):
        """The frame on the canvas now for the page with that id."""
        scene = self.scene()
        for frame in getattr(scene, "frames", ()) or ():
            if getattr(frame.page, "uid", None) == page_uid:
                return frame
        return None

    def _commit_snapshot(self, text: str, coalesce: bool) -> None:
        if not self._snapshot:
            return
        changed = []
        for frame, before in self._snapshot:
            after = frame.serialize_items()
            if after != before:
                changed.append((frame, before, after))
        if not changed:
            return
        stack = self.window.undo_stack
        if len(changed) > 1:
            stack.beginMacro(text)
        for frame, before, after in changed:
            self.push_command(PageEditCommand(frame, before, after,
                                              text, on_apply=self.after_undo,
                                              coalesce=coalesce, find_frame=self.frame_for_page))
        if len(changed) > 1:
            stack.endMacro()
        self.documentEdited.emit()

    # ------------------------------------------------------------------
    # tools
    # ------------------------------------------------------------------
    def current_tool(self) -> Tool:
        return TOOL_MAP.get(self.tool_key, TOOL_MAP["select"])

    def set_tool(self, key: str) -> None:
        if key != self.tool_key:
            self._pending_anchor = None
            self._pending_cloud = None
        # With the Viewport tool out, every viewport already on the page is
        # shown, so a new one can be drawn beside them rather than over them.
        for frame in getattr(self.scene(), "frames", []) or []:
            if frame.show_all_viewports != (key == "viewport"):
                frame.show_all_viewports = key == "viewport"
                frame.update()
        self.forget_snap()
        self.close_size_editor()
        if self._pending_arrow_leader is not None:
            self.cancel_arrow_leader()
        if self._pending_cloud_leader is not None:
            self.cancel_cloud_leader()
        if self._mode == "lasso":
            self.cancel_marquee()
        if self._draft is not None:
            self.cancel_draft()
        self.tool_key = key if key in TOOL_MAP else "select"
        self._preview_key = None            # the preview belongs to the old tool
        tool = self.current_tool()
        self.setCursor(self._cursor_for_tool(tool))
        self.statusMessage.emit(tool.hint or tool.label)

    def begin_arrow_leader(self, item) -> None:
        """Arm a click that says where a new arrow leader points.

        A leader is about the thing it points at, so the first thing to say
        about one is where that is. Putting it down at a guessed spot beside
        the note and leaving it to be dragged there means every leader is two
        gestures and the first one is wrong.
        """
        if item is None or item.scene() is None or not self.editable(item):
            return
        if self.tool_key != "select":
            self.set_tool("select")
            self.toolFinished.emit("select")
        self._pending_arrow_leader = item
        self._mode = "idle"
        # A new leader for a call-out: the pointer is the call-out, arrow and
        # all, not a bare arrow — and the arrow's tip is where it will point.
        self.setCursor(arrow_leader_cursor())
        self.statusMessage.emit(
            "Click what the arrow should point at · Esc to cancel")
        self.viewport().update()

    def cancel_arrow_leader(self) -> None:
        """Put down an unplaced arrow leader without changing the document."""
        self._pending_arrow_leader = None
        self.setCursor(self._cursor_for_tool(self.current_tool()))
        self.viewport().update()

    def begin_cloud_leader(self, item) -> None:
        """Arm a drag that chooses the region for a new cloud leader."""
        if item is None or item.scene() is None or not self.editable(item):
            return
        if self.tool_key != "select":
            self.set_tool("select")
            self.toolFinished.emit("select")
        self._pending_cloud_leader = item
        self._mode = "idle"
        self._marquee = []
        # What comes next is a cloud drawn round a region, joined to the note:
        # the pointer is the Cloud+ drawing for as long as that is what a
        # drag does.
        self.setCursor(cloud_callout_cursor())
        self.statusMessage.emit(
            "Drag around the area for the cloud leader · Esc to cancel")
        self.viewport().update()

    def cancel_cloud_leader(self) -> None:
        """Put down an unplaced cloud leader without changing the document."""
        self._pending_cloud_leader = None
        self._marquee = []
        if self._mode == "cloud_leader":
            self._mode = "idle"
            self.forget_snapshot()
        self.setCursor(self._cursor_for_tool(self.current_tool()))
        self.viewport().update()

    def setCursor(self, cursor) -> None:
        """The pointer goes on the viewport, where the canvas is. One set
        there (by a table, say) overrides any set on the view itself, and the
        pointer then stayed the cross wherever it went (2026-10-10)."""
        self.viewport().setCursor(cursor)

    def unsetCursor(self) -> None:
        self.viewport().unsetCursor()

    def cursor(self):
        return self.viewport().cursor()

    def _cursor_for_tool(self, tool: Tool) -> QCursor:
        if tool.key == "select":
            return QCursor(Qt.ArrowCursor)
        if tool.key == "pan":
            return QCursor(Qt.OpenHandCursor)
        if tool.key == "cloud_callout":
            # Cloud+ is a cloud with a note on it, and says so.
            return cloud_callout_cursor()
        if tool.mode in (CLOUDY, CLOUD):
            return cloud_cursor()
        # Every other tool — callouts, click-placed notes and stamps, the
        # snapshot region — is a precise crosshair carrying its own icon.
        return drawing_cursor(tool.icon)

    def finish_tool(self) -> None:
        self.forget_snap()
        if self.tool_key == "count":
            self.statusMessage.emit(
                "Count: click to place the next marker — Esc to finish")
            return
        if not self.sticky_tool:
            self._pending_properties = None
        if not self.sticky_tool and self.tool_key not in ("select", "pan"):
            self.set_tool("select")
            self.toolFinished.emit("select")
        else:
            # A tool kept in hand goes back to its own cursor, whatever a
            # gesture within it changed the pointer to.
            self.setCursor(self._cursor_for_tool(self.current_tool()))

    # ------------------------------------------------------------------
    # zoom & navigation
    # ------------------------------------------------------------------
    def zoom(self) -> float:
        return self._zoom

    def setScene(self, scene) -> None:
        super().setScene(scene)
        self._update_desk_margin()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_desk_margin()
        self.sheet_headings.refresh_soon()

    def _update_desk_margin(self) -> None:
        """Keep enough off-page desk to centre a page edge or corner."""
        scene = self.scene()
        if not isinstance(scene, DocumentScene):
            return
        scale = max(getattr(self, "_zoom", 1.0), MIN_ZOOM)
        scene.set_desk_margin(self.viewport().width() / (2.0 * scale) + 12.0,
                              self.viewport().height() / (2.0 * scale) + 12.0)

    def set_zoom(self, factor: float, anchor_mouse: bool = False,
                 at: Optional[QPointF] = None,
                 keep: Optional[QPointF] = None) -> None:
        """Zoom to *factor*, keeping one point of the page where it is.

        Which point: the one under the pointer when the wheel is turned, and
        the middle of the view otherwise. Qt has ``AnchorUnderMouse`` for
        this, and it depends on the view believing the pointer is over it —
        which it does not while a menu has been open, while the window is
        being scrolled by other means, or in anything driving the view
        without a real pointer. So the anchoring is done here: note where the
        point is on the page, scale, then scroll until it is back under the
        same pixel. That holds however the zoom was asked for.

        *keep* is the point of the canvas to keep under *at*, when the caller
        knows it better than the nearest pixel does: a gliding zoom sets a
        dozen zooms about one point, and re-reading it each time to the pixel
        let it wander.
        """
        factor = max(MIN_ZOOM, min(factor, MAX_ZOOM))
        if abs(factor - self._zoom) < 1e-6:
            return
        if at is None and anchor_mouse:
            at = self.mapFromGlobal(QCursor.pos())
            if not self.viewport().rect().contains(
                    self.viewport().mapFromParent(at)):
                at = None
        keep_view = QPointF(at) if at is not None else QPointF(
            self.viewport().rect().center())
        keep_scene = QPointF(keep) if keep is not None else \
            self.mapToScene(keep_view.toPoint())

        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self._zooming = True
        self._zoom = factor
        self.apply_view_transform()
        self._update_desk_margin()
        # Where that page point landed, and how far it has to come back.
        landed = self.viewportTransform().map(keep_scene)
        drift = landed - keep_view
        self.horizontalScrollBar().setValue(
            self.horizontalScrollBar().value() + round(drift.x()))
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().value() + round(drift.y()))
        self._zooming = False
        self.zoomChanged.emit(factor)

    def apply_view_transform(self) -> None:
        """Set the view's transform. Only the zoom lives here.

        The turn does not: rotating the view rotates its scrollbars with it,
        so the vertical bar starts moving the page sideways. The pages are
        turned on the canvas instead, which leaves the canvas the shape it
        always was and the scrollbars pointing the way they scroll.
        """
        self.setTransform(QTransform().scale(self._zoom, self._zoom))

    # -- turning the page on screen ----------------------------------------
    def view_turn(self) -> int:
        return self._view_turn

    def rotate_view(self, clockwise: bool = True) -> int:
        """Turn the page on screen a quarter turn, for reading it sideways.

        Bluebeam keeps this apart from rotating the page, and so does this: a
        drawing that came in the wrong way up is read by turning the view, and
        nothing about the document changes — not the paper, not the markups,
        not what prints. It is not on the undo stack for the same reason.
        """
        self._view_turn = (self._view_turn + (90 if clockwise else -90)) % 360
        self.turn_the_pages()
        self.fit_page()
        self.statusMessage.emit(
            "View turned back upright" if not self._view_turn
            else f"View turned {self._view_turn}° — the page itself is unchanged")
        return self._view_turn

    def turn_the_pages(self) -> None:
        """Lay the pages out at the reading angle they are being viewed at."""
        scene = self.scene()
        if scene is not None and hasattr(scene, "set_reading_turn"):
            scene.set_reading_turn(self._view_turn)
        self.viewport().update()

    def reset_view_rotation(self) -> None:
        if not self._view_turn:
            return
        self._view_turn = 0
        self.turn_the_pages()
        self.fit_page()
        self.statusMessage.emit("View turned back upright")

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

        Shift scrolls sideways. Ctrl does the opposite of whatever the wheel
        is doing here: with the wheel scrolling, Ctrl zooms; with the wheel
        zooming, Ctrl scrolls; and in page-by-page mode, where the plain wheel
        turns pages, Ctrl zooms. It used to zoom in every case, which left no
        way at all to scroll with the wheel once zoom was the preference — the
        setting turned one of the two gestures off rather than swapping them.

        A trackpad sends pixelDelta and means panning by it, so two-finger
        scrolling still scrolls smoothly however the wheel is set, and Ctrl
        inverts that too.
        """
        if self.calc.wheel(event, self.mapToScene(event.position().toPoint())):
            return
        pixels = event.pixelDelta()
        notches = event.angleDelta().y()
        if event.modifiers() & Qt.ShiftModifier:
            raw = pixels.y() or pixels.x()
            bar = self.horizontalScrollBar()
            if raw:
                bar.setValue(bar.value() - raw)          # a trackpad: already smooth
            else:
                self.glide.by(bar, -notches * WHEEL_SCROLL_FACTOR)
            event.accept()
            return
        if (self.scroll_mode == "page"
                and not event.modifiers() & Qt.ControlModifier):
            delta = (pixels.y() if not pixels.isNull() else notches)
            if delta:
                step = -1 if delta > 0 else 1
                self.window.go_to_page(self.window.current_index + step)
            event.accept()
            return
        # What the wheel would do here if nothing were held, then Ctrl turns
        # that round. In page-by-page mode the plain wheel turns pages and
        # never zooms, whatever the preference says, so Ctrl there is a zoom.
        unmodified_zooms = (preferences.current().wheel_zooms()
                            and pixels.isNull()
                            and self.scroll_mode != "page")
        zooming = unmodified_zooms != bool(event.modifiers() & Qt.ControlModifier)
        if zooming:
            delta = notches or pixels.y()
            if delta:
                # Where the wheel was turned is where the zoom happens; the
                # event knows, so it does not have to be asked for again.
                # A notch glides there, as a notch of scrolling does: a jump
                # of a fifth at a time is a zoom that lurches (2026-10-02).
                self.glide.zoom_by(1.0015 ** delta, event.position())
            event.accept()
            return
        if not pixels.isNull():
            # A trackpad: one scroll for both directions, or Qt repaints a
            # third of the window on every event instead of shifting what is
            # drawn — the lag of two-finger scrolling on a Mac (2026-10-01).
            self.scroll_both(pixels.x(), pixels.y())
            event.accept()
            return
        if notches:
            self.glide.by(self.verticalScrollBar(), -notches * WHEEL_SCROLL_FACTOR)
        event.accept()

    #: How long after the last notch of a zoom the page is drawn afresh.
    ZOOM_SETTLES_MS = 140

    def zooming_by_hand(self) -> None:
        """A zoom on the wheel is under way: until it has stopped for a
        moment, the page is drawn from what is already drawn, scaled, and
        nothing new is asked for. Asking at every notch had the render
        processes drawing a dozen zooms nobody would see, every frame drew
        what arrived of them, and the one wanted came last — a zoom that
        repainted and stuttered all the way (the user, 2026-10-02)."""
        from ..io import pdftiles
        pdftiles.TILES.hold(self.ZOOM_SETTLES_MS / 1000.0)
        timer = getattr(self, "_zoom_settled", None)
        if timer is None:
            timer = self._zoom_settled = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._zoom_has_settled)
        timer.start(self.ZOOM_SETTLES_MS + 15)

    def expect_zoom(self, zoom: float, at: QPointF, keep: QPointF) -> None:
        """The view is gliding to *zoom* with canvas point *keep* under view
        point *at*: what it will show there is drawn now, so it is sharp
        when it lands rather than a moment after."""
        scene = self.scene()
        if scene is None or zoom <= 0:
            return
        size = self.viewport().size()
        seen = QRectF(keep.x() - at.x() / zoom, keep.y() - at.y() / zoom,
                      size.width() / zoom, size.height() / zoom)
        ratio = max(float(self.viewport().devicePixelRatioF()), 1.0)
        for frame in getattr(scene, "frames", ()):
            box = frame.mapRectToScene(frame.page_rect())
            if box.intersects(seen):
                frame.expect(zoom * ratio, frame.mapRectFromScene(seen))

    def _zoom_has_settled(self) -> None:
        from ..io import pdftiles
        if pdftiles.TILES.held():
            self._zoom_settled.start(10)
            return
        self.viewport().update()

    _scroll_batch = None
    gpu = False

    def use_the_graphics_card(self, on: bool = True) -> bool:
        """Draw the canvas with OpenGL, or with the processor. Says which.

        On a high-density screen a scroll moves millions of pixels; on the
        processor that is the stutter of scrolling on a Mac (the user's video,
        2026-10-01), on the graphics card it is nothing. Where no OpenGL
        context can be made — a remote desktop, a headless test — it stays on
        the processor."""
        if bool(on) == self.gpu:
            return self.gpu
        if on:
            from PySide6.QtGui import QOpenGLContext, QSurfaceFormat
            probe = QOpenGLContext()
            if not probe.create():
                return False
            from PySide6.QtOpenGLWidgets import QOpenGLWidget
            surface = QOpenGLWidget()
            shape = QSurfaceFormat()
            shape.setSamples(4)                       # smooth markup edges
            surface.setFormat(shape)
            self.setViewport(surface)
            # GL repaints the whole view each frame: there is no scroll blit
            self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
            self.gpu = True
        else:
            self.setViewport(QWidget())
            self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
            self.gpu = False
        viewport = self.viewport()
        viewport.setMouseTracking(True)
        viewport.setAcceptDrops(self.acceptDrops())
        return self.gpu

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        if self._scroll_batch is not None:
            self._scroll_batch[0] += dx
            self._scroll_batch[1] += dy
            return
        super().scrollContentsBy(dx, dy)

    def scroll_both(self, dx: int, dy: int) -> None:
        """Move the view by (dx, dy) as one scroll. Set across and then down,
        it was two scrolls in one frame, and Qt gave up shifting what was
        already drawn and painted a third of the window again on every step
        of a pan (2026-10-01)."""
        self._scroll_batch = [0, 0]
        try:
            across, down = self.horizontalScrollBar(), self.verticalScrollBar()
            across.setValue(across.value() - dx)
            down.setValue(down.value() - dy)
        finally:
            moved_x, moved_y = self._scroll_batch
            self._scroll_batch = None
        if moved_x or moved_y:
            super().scrollContentsBy(moved_x, moved_y)

    def finish_scrolling(self) -> None:
        """Put the view where the wheel was taking it, now."""
        self.glide.finish()

    # ------------------------------------------------------------------
    # snapping
    # ------------------------------------------------------------------
    def snapping_off_now(self) -> bool:
        """Whether Ctrl is being held to let go of the grid, right now.

        Ctrl means "leave it exactly where I am pointing" everywhere a point
        is taken from the pointer — drawing, resizing, measuring, calibrating
        the page scale. It used to mean that only while a markup was being
        moved, so the one place it is needed most, putting the two ends of a
        calibration on the two ends of a printed dimension, was the one place
        it did not work.

        The live modifier state is read rather than passed down from the
        event: every one of those paths goes through :meth:`snap` or
        :meth:`snap_scene`, and threading a flag through all of them would
        leave one of them out.

        Ctrl held from the start of a drag means "copy" instead, and there
        snapping carries on as usual.
        """
        if self._copy_on_move:
            return False
        if self._control_held:
            return True
        return bool(QApplication.keyboardModifiers() & Qt.ControlModifier)

    def _held_modifiers(self, event_modifiers=Qt.NoModifier):
        """Which modifier keys are down, as this view has seen them.

        The application's own answer misses keys sent to the view directly,
        which is how a test drives it and how a key held before the window
        was focused arrives.
        """
        held = event_modifiers
        if self._control_held:
            held |= Qt.ControlModifier
        if self._shift_held:
            held |= Qt.ShiftModifier
        return held

    def snap(self, point: QPointF, force: bool = False) -> QPointF:
        """Snap a point given in page coordinates."""
        settings = self.document().settings
        if self.snapping_off_now() and not force:
            return point
        if not (settings.snap_to_grid or force):
            return point
        from .calcedit import GRID_PT          # SMath's grid: one for everything
        step = GRID_PT
        return QPointF(round(point.x() / step) * step, round(point.y() / step) * step)

    def snap_scene(self, scene_pos: QPointF, frame=None, ignore=()) -> QPointF:
        """Snap a canvas point to what is drawn, then to a line-up, then to
        the grid.

        In that order, because that is the order they are worth. A corner of
        something beats everything: lining a markup up with the thing it is
        about is what the pointer is usually trying to do. Level with a corner
        comes next. The grid is the last resort, and only when it is switched
        on — it used to be applied whatever the switch said, because the two
        halves of this were doing their own thing.
        """
        if not preferences.current().snap_while_drawing or self.snapping_off_now():
            self.forget_snap()
            return QPointF(scene_pos)
        # The moving draft is not a target: its previous endpoint otherwise
        # catches the next move, making second-point placement sticky.
        ignore = set(ignore)
        if self._draft is not None:
            ignore.add(self._draft)
        caught = self.snap_to_item(scene_pos, ignore)
        if caught is not None:
            return caught
        frame = frame or self.frame_at(scene_pos) or self.frame()
        lined_up = self.snap_to_alignment(scene_pos, frame, ignore)
        if lined_up is not None:
            return lined_up
        if frame is None:
            return self.snap(scene_pos)
        return frame.mapToScene(self.snap(frame.mapFromScene(scene_pos)))

    def forget_snap(self) -> None:
        """Nothing is caught: take the marker off."""
        self._invalidate_snap_overlay(self._snap_marker, self._snap_guides)
        self._snap_marker = None
        self._snap_caught = ""
        self._snap_guides = []

    def _invalidate_snap_overlay(self, marker=None, guides=()) -> None:
        """Repaint the full length of old/new guides, not only the draft's bounds."""
        viewport = self.viewport()
        if marker is not None:
            point = self.mapFromScene(marker)
            viewport.update(QRect(point.x() - 8, point.y() - 8, 17, 17))
        for direction, value in guides:
            if direction == "across":
                y = self.mapFromScene(QPointF(0, value)).y()
                viewport.update(QRect(0, y - 3, viewport.width(), 7))
            else:
                x = self.mapFromScene(QPointF(value, 0)).x()
                viewport.update(QRect(x - 3, 0, 7, viewport.height()))

    def snap_to_alignment(self, scene_pos: QPointF, frame,
                          ignore=()) -> Optional[QPointF]:
        """Line the pointer up with a level or an upright already on the page.

        Not a point to land on — a line to sit on. Level with the top of that
        rectangle, or directly under the end of that line. The guide is drawn
        so it is obvious which one has been caught.
        """
        if frame is None:
            return None
        across, down = self.alignment_lines(frame, ignore)
        across, down = list(across), list(down)
        if self.document().settings.snap_to_pdf_alignment:
            nearest = self._pdf_alignment_near(frame, scene_pos)
            across += nearest[0]
            down += nearest[1]
        if not across and not down:
            return None
        reach = SNAP_REACH / max(self._zoom, 0.05)
        x, y = scene_pos.x(), scene_pos.y()
        guides: list = []
        nearest_y = min((value for value in across), key=lambda v: abs(v - y),
                        default=None)
        nearest_x = min((value for value in down), key=lambda v: abs(v - x),
                        default=None)
        if nearest_y is not None and abs(nearest_y - y) <= reach:
            y = nearest_y
            guides.append(("across", nearest_y))
        if nearest_x is not None and abs(nearest_x - x) <= reach:
            x = nearest_x
            guides.append(("down", nearest_x))
        if not guides:
            return None
        self._invalidate_snap_overlay(self._snap_marker, self._snap_guides)
        self._snap_marker = QPointF(x, y)
        self._snap_guides = guides
        self._invalidate_snap_overlay(self._snap_marker, self._snap_guides)
        caught = ("level and in line with what is drawn" if len(guides) > 1
                  else "level with what is drawn" if guides[0][0] == "across"
                  else "in line with what is drawn")
        if caught != self._snap_caught:
            self.statusMessage.emit(f"Snapped {caught}")
        self._snap_caught = caught
        return QPointF(x, y)

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
        return [point for point, _ in PageView.named_points_of(item)]

    @staticmethod
    def is_drawing(item) -> bool:
        """Whether this came in on a PDF page rather than being drawn here.

        The line work read out of an imported drawing is worth catching hold
        of — the end of a beam, the corner of a column — but it is not worth
        lining new markups up against, because a drawing is already full of
        lines and every one of them would offer a guide.
        """
        return bool(getattr(item, "from_drawing", False))

    @staticmethod
    def named_points_of(item) -> list:
        """The points on one markup worth catching, each with a word for it.

        Every corner and every end, and the middle of every side — of a box,
        and of each side of a drawn shape too. A polygon's edge midpoints
        used to be missing entirely, which is why the middle of a polygon
        side could not be caught the way the middle of a rectangle side can.
        """
        vertices = getattr(item, "points", None)
        if vertices:
            named = []
            last = len(vertices) - 1
            closed = bool(getattr(item, "closed", False))
            for index, point in enumerate(vertices):
                if index in (0, last) and not closed:
                    what = "end"
                else:
                    what = "point"
                named.append((item.mapToScene(point), what))
            # The middle of each side. A run of freehand ink has hundreds of
            # points and no sides anybody aims at, so it is left out.
            if len(vertices) <= 60 and not getattr(item, "smooth", False):
                sides = len(vertices) if closed else len(vertices) - 1
                for index in range(max(sides, 0)):
                    start = vertices[index]
                    end = vertices[(index + 1) % len(vertices)]
                    middle = QPointF((start.x() + end.x()) / 2,
                                     (start.y() + end.y()) / 2)
                    named.append((item.mapToScene(middle), "middle"))
            return named
        rect = item.local_rect().normalized()
        if rect.isEmpty():
            return []
        corners = ((rect.topLeft(), "corner"), (rect.topRight(), "corner"),
                   (rect.bottomLeft(), "corner"), (rect.bottomRight(), "corner"),
                   (rect.center(), "centre"),
                   (QPointF(rect.center().x(), rect.top()), "middle"),
                   (QPointF(rect.center().x(), rect.bottom()), "middle"),
                   (QPointF(rect.left(), rect.center().y()), "middle"),
                   (QPointF(rect.right(), rect.center().y()), "middle"))
        return [(item.mapToScene(point), what) for point, what in corners]

    @staticmethod
    def content_points_of(item) -> list:
        """What is worth catching on an imported drawing: corners and ends.

        Only those. A drawing's own line work is what a measurement is taken
        off, so its ends and its corners matter and the middles of its
        segments do not — there are thousands of them and none of them mean
        anything.
        """
        vertices = getattr(item, "points", None)
        if vertices:
            last = len(vertices) - 1
            closed = bool(getattr(item, "closed", False))
            named = []
            for index, point in enumerate(vertices):
                what = "end" if (index in (0, last) and not closed) else "corner"
                named.append((item.mapToScene(point), what))
            return named
        rect = item.local_rect().normalized()
        if rect.isEmpty():
            return []
        return [(item.mapToScene(corner), "corner") for corner in
                (rect.topLeft(), rect.topRight(),
                 rect.bottomLeft(), rect.bottomRight())]

    @staticmethod
    def _nearby_snap_items(frame, point, reach):
        # Keep page order (including equal-distance snap tie-breaking). This
        # list lives for one pointer event only, so edits/undo/page rotation
        # never need to invalidate cached geometry.
        return [item for item in frame.markups() + frame.pdf_snap_items(point, reach) if item.isVisible()
                and item.sceneBoundingRect().adjusted(
                    -reach, -reach, reach, reach).contains(point)]

    def named_snap_targets(self, frame, ignore=(), near=None, reach=0.0,
                           _nearby=None) -> list:
        """Every point worth catching hold of, and what each of them is.

        Two sources, each with its own switch: the markups drawn here, and
        the line work that came in on the page. Either can be turned off
        without touching the other.
        """
        settings = self.document().settings
        found: list = []
        skip = set(ignore)
        items = (_nearby if _nearby is not None else
                 self._nearby_snap_items(frame, near, reach) if near is not None
                 else frame.markups())
        for item in items:
            if item in skip or not item.isVisible():
                continue
            if self.is_drawing(item):
                if settings.snap_to_content:
                    for point, what in self.content_points_of(item):
                        found.append((point, what, item))
            elif settings.snap_to_items:
                for point, what in self.named_points_of(item):
                    found.append((point, what, item))
        return found

    @staticmethod
    def sides_of(item) -> list:
        """One markup's straight runs, in scene coordinates.

        What a crossing is made of. Freehand ink is left out: a run of
        hundreds of tiny segments crosses everything and means none of it.
        """
        if getattr(item, "smooth", False):
            return []
        vertices = getattr(item, "points", None)
        if vertices:
            if len(vertices) < 2 or len(vertices) > MOST_SIDES:
                return []
            placed = [item.mapToScene(point) for point in vertices]
            sides = list(zip(placed, placed[1:]))
            if getattr(item, "closed", False):
                sides.append((placed[-1], placed[0]))
            return sides
        rect = item.local_rect().normalized()
        if rect.isEmpty():
            return []
        corners = [item.mapToScene(corner) for corner in
                   (rect.topLeft(), rect.topRight(),
                    rect.bottomRight(), rect.bottomLeft())]
        return list(zip(corners, corners[1:])) + [(corners[-1], corners[0])]

    def crossings_near(self, frame, scene_pos: QPointF, reach: float,
                       ignore=(), _nearby=None) -> list:
        """Where drawn lines cross each other, close to the pointer.

        The point a drawing is most often aimed at and the one there is no
        vertex for: two grid lines meeting, a beam arriving at a column. Only
        the segments actually passing near the pointer are considered — a
        sheet holds thousands of them, and comparing every pair against every
        other would cost more than the whole gesture.
        """
        settings = self.document().settings
        skip = set(ignore)
        near: list = []
        items = (_nearby if _nearby is not None else
                 self._nearby_snap_items(frame, scene_pos, reach))
        for item in items:
            if item in skip or not item.isVisible():
                continue
            if self.is_drawing(item):
                if not settings.snap_to_content:
                    continue
            elif not settings.snap_to_items:
                continue
            for start, end in self.sides_of(item):
                if _passes_near(start, end, scene_pos, reach):
                    near.append((start, end, item))
                    if len(near) >= MOST_CROSSING_SIDES:
                        break
            if len(near) >= MOST_CROSSING_SIDES:
                break
        found: list = []
        for index, (start, end, item) in enumerate(near):
            for other_start, other_end, other in near[index + 1:]:
                if other is item:
                    continue           # a shape does not cross itself usefully
                where = _crossing(start, end, other_start, other_end)
                if where is not None and _within(where, scene_pos, reach):
                    found.append((where, "crossing", item))
        return found

    def _pdf_alignment_near(self, frame, scene_pos: QPointF) -> tuple:
        """The PDF vertex levels and uprights nearest the pointer, in scene.

        Looked up page-locally by bisection, then turned into scene values.
        Only the neighbours either side are returned, which is all the
        nearest-guide choice needs.
        """
        import bisect
        loader = getattr(frame, "pdf_alignment_axes", None)
        if loader is None:
            return ([], [])
        xs, ys = loader()
        if not xs and not ys:
            return ([], [])
        local = frame.mapFromScene(scene_pos)
        across, down = [], []
        transform = frame.sceneTransform()
        upright = abs(transform.m12()) < 1e-9 and abs(transform.m21()) < 1e-9

        def neighbours(values, value):
            at = bisect.bisect_left(values, value)
            return [values[i] for i in (at - 1, at) if 0 <= i < len(values)]

        for x in neighbours(xs, local.x()):
            point = frame.mapToScene(QPointF(x, local.y()))
            (down if upright else across).append(point.x() if upright else point.y())
        for y in neighbours(ys, local.y()):
            point = frame.mapToScene(QPointF(local.x(), y))
            (across if upright else down).append(point.y() if upright else point.x())
        return (across, down)

    def alignment_lines(self, frame, ignore=()) -> tuple:
        """The levels and the uprights worth lining a new markup up with.

        Only from what has been drawn here. An imported drawing is left out:
        it is already full of lines, and every one of them would offer a
        guide, which is no guide at all.
        """
        settings = self.document().settings
        if not (settings.snap_to_items and settings.snap_to_alignment):
            return ([], [])
        across: list = []
        down: list = []
        skip = set(ignore)
        for item in frame.markups():
            if item in skip or not item.isVisible() or self.is_drawing(item):
                continue
            for point, _what in self.named_points_of(item):
                across.append(point.y())
                down.append(point.x())
        return (across, down)

    def snap_moved(self, items: list, delta: QPointF) -> QPointF:
        """Nudge a move so a corner of what is dragged lands on a drawn point."""
        self._invalidate_snap_overlay(self._snap_marker, self._snap_guides)
        self._snap_marker = None
        self._snap_guides = []
        if not self.document().settings.snap_to_items or not items:
            return delta
        item, origin = items[0]
        frame = item.parentItem()
        if frame is None:
            return delta
        # What can be snapped to does not change during a drag: gathered once
        # per gesture, as arrays. Gathered on every move it was a third of the
        # cost of dragging on a sheet with ink on it (Calcs.pdf, 2026-10-01).
        import numpy as np
        moving = tuple(sorted(id(i) for i, _ in items))
        cached = self.__dict__.get("_snap_gesture")
        if cached is None or cached[0] != (id(frame), moving):
            found = self.snap_targets(frame, ignore={i for i, _ in items})
            targets = (np.array([(p.x(), p.y()) for p in found], dtype=float)
                       if found else np.zeros((0, 2)))
            own = self.points_of(item)
            mine = (np.array([(p.x(), p.y()) for p in own], dtype=float)
                    if own else np.zeros((0, 2)))
            start = frame.mapToScene(item.pos())
            cached = ((id(frame), moving), targets, mine,
                      (start.x(), start.y()))
            self._snap_gesture = cached
        _key, targets, mine, (sx, sy) = cached
        if not len(targets) or not len(mine):
            return delta
        here = frame.mapToScene(origin + delta)
        # the item's points where they were when first gathered, carried to
        # where this move puts it
        moved = mine + np.array([here.x() - sx, here.y() - sy])
        reach = SNAP_REACH / max(self._zoom, 0.05)
        apart = targets[None, :, :] - moved[:, None, :]
        distance = np.hypot(apart[..., 0], apart[..., 1])
        at = np.unravel_index(int(np.argmin(distance)), distance.shape)
        if distance[at] >= reach:
            return delta
        offset_x, offset_y = apart[at]
        target_x, target_y = targets[at[1]]
        offset, marker = QPointF(float(offset_x), float(offset_y)), QPointF(float(target_x), float(target_y))
        self._snap_marker = QPointF(marker)
        self._invalidate_snap_overlay(self._snap_marker)
        return delta + offset

    def snap_to_item(self, scene_pos: QPointF, ignore=()) -> Optional[QPointF]:
        """The nearest interesting point of another markup, if one is close."""
        self._invalidate_snap_overlay(self._snap_marker, self._snap_guides)
        self._snap_marker = None
        self._snap_caught = ""
        self._snap_guides = []
        frame = self.frame_at(scene_pos) or self.frame()
        if frame is None:
            return None
        reach = SNAP_REACH / max(self._zoom, 0.05)
        best = None
        best_distance = reach
        nearby = self._nearby_snap_items(frame, scene_pos, reach)
        candidates = self.named_snap_targets(frame, ignore, scene_pos, reach, nearby)
        candidates += self.crossings_near(frame, scene_pos, reach, ignore, nearby)
        # The body of an edge is a target too, not just its corners and middle.
        # Project onto the segment in scene coordinates so rotated callouts
        # behave the same way as upright ones.
        settings = self.document().settings
        skip = set(ignore)
        for item in nearby:
            if item in skip or not item.isVisible():
                continue
            if self.is_drawing(item) or not settings.snap_to_items:
                continue
            for start, end in self.sides_of(item):
                delta = end - start
                length2 = delta.x() ** 2 + delta.y() ** 2
                if length2 <= 1e-12:
                    continue
                offset = scene_pos - start
                t = max(0.0, min(1.0, (offset.x() * delta.x() + offset.y() * delta.y()) / length2))
                point = start + delta * t
                if _within(point, scene_pos, reach):
                    candidates.append((point, "edge", item))
        for point, what, item in candidates:
            if what == "edge" and best is not None and best[1] != "edge":
                continue
            distance = math.hypot(point.x() - scene_pos.x(),
                                  point.y() - scene_pos.y())
            if distance < best_distance:
                best, best_distance = (point, what, item), distance
        if best is not None:
            point, what, item = best
            self._snap_marker = QPointF(point)
            self._invalidate_snap_overlay(self._snap_marker)
            caught = (f"crossing at {item.display_name().lower()}"
                      if what == "crossing"
                      else f"{what} of {item.display_name().lower()}")
            if caught != self._snap_caught:
                # Only when it changes: the pointer crossing the same corner
                # a hundred times should not write the same line a hundred
                # times over whatever else the status bar was saying.
                self.statusMessage.emit(f"Snapped to the {caught}")
            self._snap_caught = caught
            return QPointF(point)
        return None

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

    def click_into_viewport(self, scene_pos: QPointF) -> None:
        """Show the frame of the viewport clicked into; hide every other.

        Viewports are not markups and their frames would only clutter the
        drawing, so one is shown while it is being worked in, as in Bluebeam.
        """
        scene = self.scene()
        for frame in getattr(scene, "frames", []) or []:
            spot = frame.mapFromScene(scene_pos)
            inside = frame.page.viewport_at(spot.x(), spot.y()) \
                if frame.page_rect().contains(spot) else None
            frame.set_active_viewport(inside)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._pointer_down = event.button() == Qt.LeftButton
        scene_pos = self.mapToScene(event.position().toPoint())
        self._press_scene = scene_pos
        self._press_view = event.position().toPoint()
        if event.button() == Qt.LeftButton:
            self.click_into_viewport(scene_pos)
            block = self.open_block()
            if block is not None and not block.scene_box().adjusted(
                    -4, -4, 4, 4).contains(scene_pos):
                self.close_block()

        if self.tables.mouse_press(event, scene_pos):
            event.accept()
            return

        if self.calc.mouse_press(event, scene_pos):
            event.accept()
            return

        if (self._pending_arrow_leader is not None
                and event.button() == Qt.LeftButton):
            item, self._pending_arrow_leader = self._pending_arrow_leader, None
            self.setCursor(self._cursor_for_tool(self.current_tool()))
            if item.scene() is not None:
                self.begin_snapshot(self.involved_frames(item))
                self.window.finish_arrow_leader(item, self.snap_scene(scene_pos))
            self.viewport().update()
            event.accept()
            return

        if (self._pending_cloud_leader is not None
                and event.button() == Qt.LeftButton):
            point = self.snap_scene(scene_pos)
            self._mode = "cloud_leader"
            self._marquee = [QPointF(point), QPointF(point)]
            self.begin_snapshot(self.involved_frames(self._pending_cloud_leader))
            event.accept()
            return

        if self._size_editor is not None and event.button() == Qt.LeftButton:
            proxy = self._size_proxy
            if proxy is not None and proxy.sceneBoundingRect().contains(scene_pos):
                super().mousePressEvent(event)
                return
            self.close_size_editor()

        if self._label_editor is not None and event.button() == Qt.LeftButton:
            proxy = self._label_proxy
            if proxy is not None and proxy.sceneBoundingRect().contains(scene_pos):
                super().mousePressEvent(event)
                return
            self.close_label_editor(commit=True)

        # Drawing a shape round what you want: every click is a corner of it,
        # whatever it lands on. Without this a click that happened to fall on
        # a markup selected that markup instead, so a shape could only be
        # drawn across bare paper — which is not where the things you want to
        # select are.
        if self._mode == "lasso" and event.button() == Qt.LeftButton:
            self._add_lasso_point(scene_pos)
            event.accept()
            return

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
                self._handle_shift = self._latched_shift(item, grabbed, event)
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

        # The format painter is held between clicks: while it is, a left click
        # on a markup gives that markup the held look and nothing else happens.
        if (event.button() == Qt.LeftButton and self.window.holding_a_format()
                and self.tool_key == "select"):
            target = self.markup_at(scene_pos)
            if target is not None and self.editable(target):
                self.window.paint_format_onto(target)
                event.accept()
                return
            # On bare paper, a drag round several markups paints them all;
            # the selection is left as it was.
            self._mode = "rubber"
            self._paint_by_box = True
            self._marquee = [QPointF(scene_pos), QPointF(scene_pos)]
            self.viewport().update()
            event.accept()
            return

        if self._pending_stamp is not None and event.button() == Qt.LeftButton:
            if self.place_pending_stamp(scene_pos):
                event.accept()
                return

        tool = self.current_tool()
        if tool.mode == NONE and tool.key == "select":
            self._press_select(event, scene_pos)
            return
        if tool.mode == ERASE:
            self._mode = "erase"
            self.begin_snapshot()
            self.erase_at(scene_pos)
            event.accept()
            return
        self._press_draw(event, scene_pos, tool)

    ERASER_REACH = 7.0

    def erase_at(self, scene_pos: QPointF) -> None:
        """Rub out freehand ink under the pointer.

        Only ink: a pen stroke or a highlight is drawn by hand and rubbed out
        by hand, which is what an eraser means. A rectangle or a dimension is
        a thing you drew on purpose, and it is deleted, not erased — so the
        eraser passes straight over it rather than quietly destroying work
        that took a decision to make.
        """
        reach = self.ERASER_REACH / max(self._zoom, 0.05)
        frame = self.frame_at(scene_pos) or self.frame()
        if frame is None:
            return
        for item in list(frame.markups()):
            if not (isinstance(item, PolyItem) and item.kind in ("ink", "highlighter")):
                continue
            if not self.editable(item):
                continue
            local = item.mapFromScene(scene_pos)
            if item.build_path().intersects(
                    QRectF(local.x() - reach, local.y() - reach, reach * 2, reach * 2)):
                detach(item)

    def _press_select(self, event: QMouseEvent, scene_pos: QPointF) -> None:
        # 1. a selected group owns one outer resize box. Check it before the
        # modifier-specific reshape paths so Shift can release its ratio.
        grouped = self._selected_group()
        if grouped is not None:
            members, box = grouped
            key = self._group_handle_at(scene_pos, box)
            if key:
                self._group_handle_key = key
                self._group_resize_box = QRectF(box)
                self._group_resize_items = [
                    (member, member.mapToScene(QPointF(0, 0)),
                     QTransform(member.transform()))
                    for member in members]
                # a measurement's own points, as the gesture found them
                self._group_resize_points = {
                    id(member): [QPointF(p) for p in member.points]
                    for member in members if isinstance(member, MeasureItem)}
                self._mode = "group_resize"
                self.begin_snapshot(self.all_frames())
                event.accept()
                return

        # 3. Shift on a dimension's number takes hold of the number itself,
        # so it can be pulled off the line onto a leader without having to
        # find the small handle first.
        if event.modifiers() & Qt.ShiftModifier:
            for item in self.scene().selectedItems():
                if not isinstance(item, MeasureItem) or not self.editable(item):
                    continue
                if item.label_at(item.mapFromScene(scene_pos)):
                    self._handle_item = item
                    self._handle_key = "lbl"
                    self._handle_shift = True
                    self._mode = "resize"
                    self.begin_snapshot()
                    self.statusMessage.emit(
                        "Drag the value where you want it — it keeps a leader "
                        "back to the line")
                    event.accept()
                    return

        # 4. reshaping an outline: Shift or Ctrl over one of its points or
        # one of its sides. This comes before both the handles and the
        # selection, because with a key held it is the only thing the click
        # can have meant.
        # Only a click reshapes. Pressed and dragged, the same keys mean what
        # they mean for any drag — Shift keeps it straight, Ctrl copies — so
        # what the click would do is kept until the button comes up.
        self._pending_reshape = None
        target = self.shaping_target(scene_pos, event.modifiers())
        if target is not None:
            if self.markup_at(scene_pos) is target[0]:
                self._pending_reshape = (QPointF(scene_pos), event.modifiers())
            else:
                # Not on the shape itself — off a curve's old chord, say — so
                # nothing is there to drag: the click can only mean this.
                self.reshape_at(scene_pos, event.modifiers())
                self._mode = "idle"
                event.accept()
                return

        # 5. a resize handle on an already-selected item
        for item in self.scene().selectedItems():
            if not isinstance(item, MarkupItem) or not self.editable(item):
                continue
            if item.group:
                continue
            key = item.handle_at(item.mapFromScene(scene_pos))
            if key:
                self._handle_item = item
                self._handle_key = key
                self._handle_shift = self._latched_shift(item, key, event)
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
                    "Click each corner · click the first corner again, or "
                    "Enter, to select what is inside · Esc to cancel")
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
            self._shift_click_selection = (family, wanted)
            # Keep an already-selected item held until release. A Shift drag
            # means constrain the selection, while a Shift click still toggles
            # it off once Qt proves that no drag happened.
            if wanted:
                for member in family:
                    member.setSelected(True)
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

        if isinstance(item, CalloutItem):
            cloud_index = item.cloud_at(item.mapFromScene(scene_pos))
            if cloud_index >= 0:
                self._handle_item = item
                self._handle_key = f"l{cloud_index}"
                self._handle_shift = False
                self._mode = "resize"
                self.begin_snapshot()
                event.accept()
                return

        self._mode = "move"
        # Bluebeam's rule: Ctrl held when the drag *starts* makes it a copy.
        # Ctrl pressed once a move is under way turns snapping off instead.
        self._copy_on_move = control
        self._ctrl_from_the_press = control
        self._copied = False
        from ..items.calc import with_block_members
        self._moved_yet = False
        self._snap_gesture = None              # gathered afresh for each drag
        self._move_items = [(other, other.pos()) for other in
                            with_block_members(self.scene().selectedItems())
                            if isinstance(other, MarkupItem) and self.editable(other)]
        from ..items.calc import blocks_holding
        self._held_in_blocks = blocks_holding(self.scene(), self._move_items)
        self._move_original_data = {
            other.uid: deepcopy(other.serialize()) for other, _ in self._move_items}
        self.begin_snapshot(self.all_frames())
        event.accept()

    def rescale_where_they_landed(self, items: list) -> None:
        """Read each moved measurement at the scale where it was dropped.

        A measurement finished inside a viewport is at the viewport's scale;
        dragged out of it, the page's — and the number on it changes as it
        crosses, the way Bluebeam's does.
        """
        for item in items:
            refresh = getattr(item, "refresh", None)
            if not callable(refresh) or not (isinstance(item, MeasureItem)
                                             or getattr(item, "kind", "") in ("rect", "ellipse")):
                continue
            page = self.page_of(item)
            if page is not None:
                refresh(page=page)

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
            frame = scene.frame_at(self.markup_box(item).center())
            if frame is None or item.parentItem() is frame:
                continue
            if getattr(item, "IS_CALC", False) and not getattr(item, "SHEET_PAGE_OK", False) \
                    and getattr(frame.page, "sheet", None) is not None:
                # equations and tables do not go on spreadsheet pages
                self.statusMessage.emit("Equations and tables don't go on spreadsheet pages")
                continue
            position = item.scenePos()
            item.setParentItem(frame)
            item.setPos(frame.mapFromScene(position))
            item.refresh(page=frame.page)
        for item in items:
            if isinstance(item, CalcItem):
                item.snap_to_grid()
                self.calc.note_overflow(item)
            elif isinstance(item, CalcTextItem):
                # Calculation text sits on the equations' grid (decision 22)
                from .calcedit import snap
                where = item.pos()
                item.setPos(QPointF(snap(where.x()), snap(where.y())))


    def _add_poly_point(self, event: QMouseEvent, point: QPointF, tool: Tool) -> None:
        """Another corner on the shape being clicked out."""
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

    def _press_draw(self, event: QMouseEvent, scene_pos: QPointF, tool: Tool) -> None:
        frame = self.frame_at(scene_pos) or self.frame()
        scale_tools = {"rect", "ellipse", "measure_length", "measure_polylength",
                       "measure_area", "measure_volume"}
        if (self._mode == "idle" and tool.key in scale_tools
                and self.window.interactive_prompts
                and not self.page().scale.is_calibrated()):
            original_tool = tool.key
            self.window.calibrate_dialog()
            # Cancel consumes this first click; choosing point calibration has
            # deliberately changed tools, so its first point is the next click.
            if (not self.page().scale.is_calibrated()
                    or self.current_tool().key != original_tool):
                event.accept()
                return
        point = self.snap_scene(scene_pos, frame)
        if self._mode == "draw_click":
            # The second click of a click-click drawing.
            self._mode = "idle"
            self.close_size_editor()
            self._update_draft(scene_pos, event.modifiers())
            self.finish_draft(scene_pos, clicked=True)
            event.accept()
            return
        if self._mode == "draw_poly" and self._draft is not None:
            # Already collecting corners — from a POLY tool, or from a cloud
            # that was clicked rather than dragged. Every click after the
            # first is another corner, whatever started it: a cloud call-out
            # used to fall through to the call-out branch here and take the
            # second corner for the place its words went.
            self._add_poly_point(event, point, tool)
            event.accept()
            return

        if tool.mode in (CLOUDY, CLOUD) and self._pending_anchor is None:
            # One gesture, two shapes. Drag and it is a rectangle round the
            # area; click and let go and it starts collecting corners, so the
            # cloud goes round whatever shape the revision actually is. Enter
            # or a right-click closes it. Two tools for that was one tool too
            # many, and picking the wrong one meant starting again.
            self.begin_snapshot()
            self._draft = RectItem("cloud")
            self._prepare_draft(self._draft)
            self._draft.setPos(frame.mapFromScene(point))
            self._draft.set_local_rect(QRectF(0, 0, 0, 0))
            frame.add_markup(self._draft)
            self._mode = "draw_drag"
            self.statusMessage.emit(
                f"{tool.label}: drag a cloud round it, or click each corner "
                "· Esc to cancel")
            event.accept()
            return

        if tool.mode in (ANCHOR, CLOUD):
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
            self.begin_snapshot()
            self._draft = tool.factory()
            self._prepare_draft(self._draft)
            self._draft.setPos(frame.mapFromScene(point))
            self._draft.points = [QPointF(0, 0), QPointF(0, 0)]
            frame.add_markup(self._draft)
            self._mode = "draw_poly"
            self.statusMessage.emit(
                f"{tool.label}: click to add points · double-click or Enter to finish · Esc to cancel")
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
        self._typed_size = False
        self._typed_w = self._typed_h = self._typed_rotation = None
        if isinstance(self._draft, RectItem) and self._draft.kind in SIZED_SHAPES:
            # Bluebeam's size bar appears the moment the shape starts, and
            # rides the corner for a drag as well as a click-click.
            self.open_size_editor(self._draft)
        event.accept()

    # The modes that only make sense while a button is held down. If the
    # button comes up somewhere the view never hears about — a menu opening
    # mid-drag, a window losing focus, a dialog stealing the release — the mode
    # would stay set for ever and the pointer would keep the four-way arrow
    # with nothing selected and no way back. So each move checks.
    HELD_MODES = ("move", "resize", "group_resize", "rubber", "lasso", "pan", "erase",
                  "table_select", "table_resize", "table_fill", "draw_drag",
                  "draw_free")

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        scene_pos = self.mapToScene(event.position().toPoint())
        self._last_scene_pos = scene_pos
        self.cursorMoved.emit(scene_pos)
        if self.tables.mouse_move(event, scene_pos):
            event.accept()
            return
        if self.calc.mouse_move(event, scene_pos):
            event.accept()
            return
        if event.buttons() == Qt.NoButton and self._mode in self.HELD_MODES:
            self._release_stale_mode()
        if (self._pending_anchor is not None or self._pending_stamp is not None
                or self._pending_arrow_leader is not None
                or self.current_tool().mode == CLICK):
            self.viewport().update()          # the leader, or the preview, follows

        if self._mode == "idle" and self.current_tool().mode not in (NONE, ERASE):
            # Nothing is being drawn yet, so nothing calls the snapping code —
            # which is why the first point of a line never showed a marker and
            # every point after it did. Working it out on the way past costs
            # nothing and means the marker is there from the first click.
            self.snap_scene(scene_pos)
            self.viewport().update()

        if self._mode == "erase":
            self.erase_at(scene_pos)
            event.accept()
            return

        if self._editing_item is not None and self._mode == "idle":
            super().mouseMoveEvent(event)       # dragging selects text
            return

        if self._mode == "pan":
            delta = event.position().toPoint() - self._pan_origin
            self._pan_origin = event.position().toPoint()
            self.scroll_both(delta.x(), delta.y())
            event.accept()
            return

        if self._mode in ("rubber", "lasso") and self._marquee:
            self._marquee[-1] = QPointF(scene_pos)
            self.viewport().update()
            event.accept()
            return

        if self._mode == "move":
            # A click that trembles is still a click: nothing moves (and so
            # nothing read out of the file is taken over) until the pointer
            # has really left where it was pressed.
            if not self._moved_yet and self._is_a_click(scene_pos):
                event.accept()
                return
            self._moved_yet = True
            delta = scene_pos - self._press_scene
            if any(isinstance(i, CalcItem) for i, _ in self._move_items) \
                    and not self._is_a_click(scene_pos):
                self.setCursor(self.calc.move_cursor())    # WebSMath's, while dragging
            control = bool(event.modifiers() & Qt.ControlModifier)
            if not control:
                self._ctrl_from_the_press = False
            if self._copy_on_move and not self._copied and not self._is_a_click(scene_pos):
                self._leave_copies_behind()
            if event.modifiers() & Qt.ShiftModifier:
                # Shift locks the move to straight lines: across, down or at
                # forty-five degrees.
                held = self.constrain(QPointF(0, 0), delta)
                delta = QPointF(held.x(), held.y())
            # Ctrl pressed during the move lets it go anywhere, unsnapped. The
            # Ctrl that started a copy is still that copy's, until let go.
            free = control and not getattr(self, "_ctrl_from_the_press", False)
            if free:
                self._snap_marker = None
            else:
                delta = self.snap_moved(self._move_items, delta)
            # A calculation block carries its equations by one step, whole
            # steps of SMath's grid (where its equations land), so they keep
            # their places in it.
            lead = next(((i, o) for i, o in self._move_items
                         if isinstance(i, CalcBlockItem)), None)
            if lead is not None and not free:
                from .calcedit import snap as onto_the_grid
                delta = QPointF(onto_the_grid(delta.x()), onto_the_grid(delta.y()))
                free = True
            held = getattr(self, "_held_in_blocks", {}) if not self._copy_on_move else {}
            for item, origin in self._move_items:
                target = origin + delta
                # Copying takes the arrow along: what is being dragged out is
                # a new callout, and its arrow belongs to it. Moving leaves the
                # arrow pointing at whatever it was pointing at.
                # One call-out on its own keeps pointing where it pointed;
                # moved with others — a group, a selection — its arrow comes
                # along, or the group leaves its leaders behind (the user's
                # video, 2026-10-01).
                self._place(item, target if free else self.snap(target),
                            keep_leader=not self._copy_on_move
                            and len(self._move_items) == 1)
                if id(item) in held:
                    from ..items.calc import stay_in_block
                    stay_in_block(item, held[id(item)])
            event.accept()
            return

        if self._mode == "group_resize" and self._group_resize_items:
            self._resize_selected_group(
                scene_pos, release_ratio=bool(event.modifiers() & Qt.ShiftModifier))
            event.accept()
            return

        if self._mode == "resize" and self._handle_item is not None:
            # A point being dragged snaps to what is already drawn, exactly as
            # it did while it was first put down. Only the grid applied here,
            # so a line could be drawn onto a corner and then never edited
            # back onto one.
            caught = self.snap_scene(scene_pos, self._handle_item.parentItem(),
                                     ignore={self._handle_item})
            local = self._handle_item.mapFromScene(caught)
            keep_ratio = bool(event.modifiers() & Qt.ShiftModifier)
            if self._handle_shift is not None:
                # A dimension's control dot does one thing or the other, and
                # which it is was settled when the drag started. Reading Shift
                # again on every move means letting go of it half way through
                # changes what the drag is doing, which is not something
                # anybody asks for.
                keep_ratio = self._handle_shift
            if getattr(self._handle_item, "keep_aspect", False):
                # Images and snapshots protect their proportions by default;
                # Shift is the deliberate exception that releases the lock.
                keep_ratio = not keep_ratio
            self._handle_item.move_handle(self._handle_key, local,
                                          keep_ratio)
            if isinstance(self._handle_item, MeasureItem):
                self._handle_item.refresh(page=self.page_of(self._handle_item))
            event.accept()
            return


        if self._mode == "cloud_leader" and self._marquee:
            self._marquee[-1] = self.snap_scene(scene_pos)
            self.viewport().update()
            event.accept()
            return

        if self._mode in ("draw_drag", "draw_click", "draw_poly", "draw_free") \
                and self._draft is not None:
            self._update_draft(scene_pos, event.modifiers())
            event.accept()
            return

        self._update_hover_cursor(scene_pos, event.modifiers())
        super().mouseMoveEvent(event)

    def viewportEvent(self, event) -> bool:
        kind = event.type()
        if kind == QEvent.Wheel or (kind == QEvent.MouseMove and event.buttons()):
            # the page's markup squares are drawn when the hand is still
            from .markuplayer import busy
            busy()
        if kind == QEvent.Leave:
            self.forget_snap()
            self.viewport().update()
        return super().viewportEvent(event)

    def escape_everything(self) -> str:
        """One press of Escape, back to a blank slate.

        Escape used to peel one layer at a time, which reads well on paper and
        badly in the hand: half-way out of a call-out, with a tool still held
        and something still selected, is not a state anybody meant to be in,
        and if one of the layers failed to lift there was no way back at all.
        So it unwinds the lot in one go — every held tool, every half-drawn
        markup, every open editor, the selection and the tool — and says which
        of them it actually put down.
        """
        undone = []
        self.forget_snap()
        if self.calc.editing():
            self.calc.leave()
            undone.append("the equation")
        if self.open_block() is not None:
            self.close_block()
            undone.append("the calculation block")
        if self.calc.cross is not None:
            self.calc.clear_cross()
        if self.clear_pending_tool():
            undone.append("the held tool")
        if self._pending_anchor is not None:
            self._pending_anchor = None
            undone.append("the call-out")
        if self._insertion_point is not None:
            self._insertion_point = None
            undone.append("the insertion point")
        self._pending_cloud = None
        if self._pending_arrow_leader is not None:
            self.cancel_arrow_leader()
            undone.append("the arrow leader")
        if self._pending_cloud_leader is not None:
            self.cancel_cloud_leader()
            undone.append("the cloud leader")
        if self._mode in ("rubber", "lasso") and self._marquee:
            self.cancel_marquee()
            undone.append("the selection box")
        if self._draft is not None:
            self.cancel_draft()
            undone.append("the markup being drawn")
        if getattr(self, "_editing_item", None) is not None:
            self.end_item_edit()
            undone.append("the words being typed")
        if self._label_editor is not None:
            self.close_label_editor(commit=False)
        if self.scene() is not None and self.scene().selectedItems():
            self.scene().clearSelection()
            undone.append("the selection")
        if self._mode != "idle":
            self._release_stale_mode()
        else:
            self.setCursor(Qt.ArrowCursor)
        if self.tool_key != "select":
            self.set_tool("select")
            self.toolFinished.emit("select")
        self.window.put_the_format_painter_down()
        # Qt's mouse ownership is independent of our tool mode. A release
        # lost to another window must not leave an item capturing later input.
        scene = self.scene()
        released = set()
        while scene is not None and scene.mouseGrabberItem() is not None:
            grabber = scene.mouseGrabberItem()
            if id(grabber) in released:
                break
            released.add(id(grabber))
            grabber.ungrabMouse()
        grabber = QWidget.mouseGrabber()
        if grabber is self or (grabber is not None and self.isAncestorOf(grabber)):
            grabber.releaseMouse()
        self.viewport().update()
        message = "Back to nothing selected" if not undone else (
            "Cancelled " + ", ".join(undone))
        self.statusMessage.emit(message)
        return message

    def _become_a_drawn_cloud(self, scene_pos: QPointF) -> None:
        """Swap the rectangle being dragged for a cloud drawn corner by corner."""
        draft = self._draft
        frame = draft.parentItem()
        at = draft.pos()
        style = draft.style
        detach(draft)
        cloud = PolyItem("cloud")
        cloud.style = style
        self._prepare_draft(cloud)
        cloud.setPos(at)
        cloud.points = [QPointF(0, 0), QPointF(0, 0)]
        frame.add_markup(cloud)
        self._draft = cloud
        self._mode = "draw_poly"
        self.statusMessage.emit(
            f"{self.current_tool().label}: click each corner · Enter or "
            "right-click to close it · Esc to cancel")

    def _release_stale_mode(self) -> None:
        """Come back to rest after a drag whose release went missing."""
        mode = self._mode
        if mode == "group_resize":
            for item, old_origin, old_transform in self._group_resize_items:
                item.setTransform(old_transform)
                parent = item.parentItem()
                if parent is not None:
                    correction = (parent.mapFromScene(old_origin)
                                  - parent.mapFromScene(
                                      item.mapToScene(QPointF(0, 0))))
                    item.setPos(item.pos() + correction)
                item.update()
            self.forget_snapshot()
        if mode == "cloud_leader":
            self._pending_cloud_leader = None
            self._marquee = []
            self.forget_snapshot()
        self._mode = "idle"
        self._move_items = []
        self._move_original_data = {}
        self._shift_click_selection = None
        self._handle_item = None
        self._handle_key = ""
        self._handle_shift = None
        self._group_resize_items = []
        self._group_handle_key = ""
        self.forget_snap()
        if mode in ("rubber", "lasso"):
            self._marquee = []
        if mode in ("draw_drag", "draw_free") and self._draft is not None:
            self.cancel_draft()
        self.setCursor(self._cursor_for_tool(self.current_tool()))
        self.viewport().update()

    def _update_draft(self, scene_pos: QPointF, modifiers,
                      final: bool = False) -> None:
        draft = self._draft
        freehand = self._mode == "draw_free"
        # Freehand is sampled from the hand, not marched point-by-point across
        # the grid. Only the first press and final release are intentional
        # endpoints and therefore snap targets.
        point = (self.snap_scene(scene_pos) if not freehand or final
                 else QPointF(scene_pos))
        if freehand and not final:
            self.forget_snap()
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
            parent = draft.parentItem()
            typed_w = getattr(self, "_typed_w", None)
            typed_h = getattr(self, "_typed_h", None)
            if parent is not None and (typed_w is not None or typed_h is not None):
                # A typed width or height holds; the other still follows the
                # pointer, in whichever direction it is being dragged.
                start = parent.mapFromScene(origin)
                end = parent.mapFromScene(corner)
                if typed_w is not None:
                    way = 1.0 if end.x() >= start.x() else -1.0
                    end.setX(start.x() + way * typed_w)
                if typed_h is not None:
                    way = 1.0 if end.y() >= start.y() else -1.0
                    end.setY(start.y() + way * typed_h)
                local = QRectF(start, end).normalized()
                draft.setRotation(0.0)
                draft.setPos(local.topLeft())
                draft.set_local_rect(QRectF(0, 0, local.width(), local.height()))
            else:
                rect = QRectF(origin, corner).normalized()
                top_left = parent.mapFromScene(rect.topLeft()) if parent is not None \
                    else rect.topLeft()
                draft.setRotation(0.0)
                draft.setPos(top_left)
                draft.set_local_rect(QRectF(0, 0, rect.width(), rect.height()))
            turned = getattr(self, "_typed_rotation", None)
            if turned and hasattr(draft, "set_item_rotation"):
                draft.set_item_rotation(turned, zero_snap=0.0)
        if isinstance(draft, MeasureItem):
            draft.refresh(page=self.page())
        self.follow_size_editor()
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
            data = deepcopy(self._move_original_data.get(item.uid,
                                                         item.serialize()))
            data["uid"] = os.urandom(8).hex()
            rename_groups(data, self._copied_groups)
            copy = build_item(data)
            if copy is None:
                continue
            if hasattr(copy, "load_from_document"):
                copy.load_from_document(self.document())
            copy.setPos(origin)
            frame.add_markup(copy)
            copy.setSelected(False)
        if scene is not None:
            self.statusMessage.emit(f"Copied {len(self._move_items)} markup(s)")

    @staticmethod
    def _place(item, position: QPointF, keep_leader: bool = True) -> None:
        """Move an item, keeping a callout's arrow pointing where it pointed."""
        mover = getattr(item, "move_keeping_leader", None)
        if keep_leader and callable(mover):
            mover(position)
        else:
            item.setPos(position)

    # -- editing a shape's control points ----------------------------------
    @staticmethod
    def has_an_outline(item) -> bool:
        """Whether this shape has corners and sides to do anything with.

        A polygon, a polyline, a line, a cloud — and a rectangle, which is
        four corners and four sides like the rest of them. Freehand ink has
        hundreds of points and no corners anybody means; an ellipse has none
        at all.
        """
        from ..items.shapes import PolyItem, RectItem

        if isinstance(item, PolyItem):
            return item.uses_vertex_handles and item.kind not in ("ink",
                                                                  "highlighter")
        return isinstance(item, RectItem) and item.has_corners()

    def shaping_target(self, scene_pos: QPointF, modifiers) -> Optional[tuple]:
        """What holding Shift or Ctrl here would do to a shape's outline.

        Shift over a point takes it away, and over a length of line puts one
        in. Ctrl over a point rounds the corner off, and over a length of line
        bends it into an arc. Which one it is depends only on where the
        pointer is, so there is nothing to pick from a menu first.

        Says (item, what, index) — or nothing, when neither key is held or
        the pointer is not over a shape that can be reshaped this way.
        """
        shift = bool(modifiers & Qt.ShiftModifier)
        control = bool(modifiers & Qt.ControlModifier)
        if not (shift or control) or self.tool_key != "select":
            return None
        for item in self.scene().selectedItems():
            if not (self.has_an_outline(item) and self.editable(item)):
                continue
            local = item.mapFromScene(scene_pos)
            reach = SNAP_REACH / max(self.zoom(), 0.05)
            vertex = self._point_near(item, local, reach)
            if vertex is not None:
                if shift and len(item.corner_points()) > 2:
                    return (item, "delete", vertex)
                if control:
                    return (item, "round", vertex)
                continue
            segment = self._segment_near(item, local, reach)
            if segment is not None:
                return (item, "add" if shift else "curve", segment)
        return None

    @staticmethod
    def _point_near(item, local: QPointF, reach: float) -> Optional[int]:
        for index, point in enumerate(item.corner_points()):
            if math.hypot(point.x() - local.x(), point.y() - local.y()) <= reach:
                return index
        return None

    @staticmethod
    def _segment_near(item, local: QPointF, reach: float) -> Optional[int]:
        from ..items.shapes import _segment_distance

        best, nearest = None, reach
        for index in range(item.segment_count()):
            start, end = item.segment_ends(index)
            gap = _segment_distance(start, end, local)
            if gap <= nearest:
                best, nearest = index, gap
        return best

    def swap_for_a_polygon(self, item):
        """Put a polygon in a rectangle's place, and say which one.

        A rectangle with a point taken out of it, or a fifth one put in, or
        one corner rounded off, is not a rectangle any more — so at that
        moment it stops being one. Nothing about it moves or changes colour;
        it simply becomes the shape that can hold what was asked for. Anything
        that is already a polygon comes back as it went in.
        """
        from ..items.shapes import PolyItem, RectItem

        if not isinstance(item, RectItem):
            return item
        frame = item.parentItem()
        if frame is None:
            return item
        shape = PolyItem.from_rectangle(item)
        was_selected = item.isSelected()
        frame.remove_markup(item)
        frame.add_markup(shape)
        if was_selected:
            self.scene().clearSelection()
            shape.setSelected(True)
        return shape

    def reshape_at(self, scene_pos: QPointF, modifiers) -> bool:
        """Do whatever the held key promised. True when something happened."""
        target = self.shaping_target(scene_pos, modifiers)
        if target is None:
            return False
        item, what, index = target
        self.begin_snapshot(self.involved_frames(item))
        item = self.swap_for_a_polygon(item)
        local = item.mapFromScene(scene_pos)
        if what == "delete":
            item.delete_point(index)
            said = "Point taken out"
        elif what == "add":
            item.insert_point(local)
            said = "Point added"
        elif what == "round":
            item.round_corner(index)
            said = ("Corner rounded off" if item.is_rounded(index)
                    else "Corner sharpened")
        else:
            item.curve_segment(index)
            said = ("Curved into an arc" if item.is_curved(index)
                    else "Straightened out")
        self.commit_snapshot(said)
        self.statusMessage.emit(said)
        self.viewport().update()
        return True

    def _update_hover_cursor(self, scene_pos: QPointF,
                             event_modifiers=Qt.NoModifier) -> None:
        """Say what the pointer would do here, before it is pressed."""
        if self.tool_key != "select":
            return
        headings = getattr(self, "sheet_headings", None)
        hit = headings.hit(self.mapFromScene(scene_pos)) if headings is not None else None
        if hit is not None:
            self.setCursor(excel_cursor(hit[1][0]))     # down a column, across a row
            return
        if getattr(self.window, "_held_style", None) is not None:
            # A format is held: the brush stays in hand wherever it goes.
            self.setCursor(format_painter_cursor())
            return
        if self._pending_arrow_leader is not None:
            self.setCursor(arrow_leader_cursor())
            return
        if self._pending_cloud_leader is not None:
            self.setCursor(cloud_callout_cursor())
            return
        grouped = self._selected_group()
        if grouped is not None:
            _members, box = grouped
            key = self._group_handle_at(scene_pos, box)
            if key:
                self.setCursor(cursor_for_handle(key))
                return
        shaping = self.shaping_target(
            scene_pos, self._held_modifiers(event_modifiers))
        if shaping is not None:
            what = shaping[1]
            self.setCursor(_reshape_cursor(what))
            self.statusMessage.emit({
                "delete": "Click to take this point out",
                "add": "Click to put a point in here",
                "round": "Click to round this corner off, or sharpen it",
                "curve": "Click to bend this into an arc, or straighten it",
            }[what])
            return
        # An equation: WebSMath's pointer — the arrow over it, SMath's move
        # cursor on the band along its frame (selected equations' handles
        # aside, which the loop below still offers)
        pointer = self.tables.hover_cursor(scene_pos)
        if pointer is None:
            pointer = self.calc.hover_cursor(scene_pos)
        if pointer is not None:
            self.setCursor(pointer)
            return
        # Words being typed: an I-beam over them, as in anything else that
        # holds text.
        editing = self._editing_item
        if editing is not None and editing.scene() is not None:
            if editing.handle_at(editing.mapFromScene(scene_pos)) is None:
                rect = self.editing_rect()
                if rect is not None and rect.contains(scene_pos):
                    self.setCursor(Qt.IBeamCursor)
                    return
        for item in self.scene().selectedItems():
            if isinstance(item, MarkupItem) and self.editable(item):
                if item.group:
                    continue
                key = item.handle_at(item.mapFromScene(scene_pos))
                if key:
                    self.setCursor(cursor_for_handle(key))
                    if key[:1] in ("b", "w", "z") and key[1:].isdigit():
                        self.statusMessage.emit({"b": "Move break",
                                                 "w": "Break width",
                                                 "z": "Break height"}[key[0]])
                    return
        # A table's column and row edges, which are grabbable only while it is
        # open for typing into. The gutters carrying A/B/C and 1/2/3 are what
        # a border is measured from, and they appear only then — turning them
        # on for a table that is merely picked out would shift the table by
        # the width of a gutter under the pointer that had just selected it.
        item = self.markup_at(scene_pos)
        if item is None:
            from ..items.sheetpage import SheetRunItem
            run = next((i for i in self.scene().items(scene_pos) if isinstance(i, SheetRunItem)
                        and i.local_rect().contains(i.mapFromScene(scene_pos))), None)
            # a spreadsheet page's cells: Excel's white plus, open or not yet;
            # the print area's edges and the page breaks to drag
            edge = self.tables.edge_cursor(run, scene_pos) if run is not None else None
            self.setCursor(edge or (excel_cursor("cell") if run is not None else Qt.ArrowCursor))
        elif not self.editable(item):
            self.setCursor(Qt.ForbiddenCursor)     # locked, or part of the page
        else:
            self.setCursor(Qt.SizeAllCursor)

    refresh_on_release = False
    _pointer_down = False

    def pointer_is_down(self) -> bool:
        """Whether a press on the canvas is still held (and Qt agrees: a
        release that went elsewhere, to a menu say, does not leave the panels
        waiting for one that never comes)."""
        from PySide6.QtGui import QGuiApplication
        return self._pointer_down and bool(QGuiApplication.mouseButtons() & Qt.LeftButton)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._pointer_down = False
        try:
            scene_pos = self.mapToScene(event.position().toPoint())
            if self.tables.mouse_release(event, scene_pos):
                event.accept()
                return
            if self.calc._select_drag is not None:
                self.calc.mouse_release(event, scene_pos)
                event.accept()
                return
            self._mouse_release(event)
            # A click (not a drag) on an equation puts the cursor in it.
            self.calc.mouse_release(event, scene_pos)
        finally:
            if self.refresh_on_release:
                self.refresh_on_release = False
                self.selectionChanged.emit()

    def _mouse_release(self, event: QMouseEvent) -> None:
        scene_pos = self.mapToScene(event.position().toPoint())
        self.forget_snap()
        self.viewport().update()

        if self._mode == "cloud_leader":
            item = self._pending_cloud_leader
            start = self._marquee[0] if self._marquee else scene_pos
            finish = self.snap_scene(scene_pos)
            rect = QRectF(start, finish).normalized()
            if rect.width() < CLICK_SLOP and rect.height() < CLICK_SLOP:
                rect = QRectF(finish.x() - 40, finish.y() - 25, 80, 50)
            self._pending_cloud_leader = None
            self._marquee = []
            self._mode = "idle"
            if item is not None and item.scene() is not None:
                self.window.finish_cloud_leader(item, rect)
            else:
                self.forget_snapshot()
            self.setCursor(self._cursor_for_tool(self.current_tool()))
            self.viewport().update()
            event.accept()
            return

        if self._editing_item is not None and self._mode == "idle":
            super().mouseReleaseEvent(event)
            return

        if self._mode == "pan":
            self._mode = "idle"
            self.setCursor(self._cursor_for_tool(self.current_tool()))
            event.accept()
            return

        if self._mode == "erase":
            self._mode = "idle"
            self.commit_snapshot("Erase")
            self.finish_tool()
            event.accept()
            return

        if self._mode == "rubber" and getattr(self, "_paint_by_box", False):
            self._paint_by_box = False
            caught = [] if self._is_a_click(scene_pos) else self.caught_by_marquee()
            self._marquee = []
            self._mode = "idle"
            self.viewport().update()
            if caught:
                self.window.paint_format_onto_all(caught)
            event.accept()
            return

        if self._mode == "rubber":
            if self._is_a_click(scene_pos):
                # A click on bare paper only clears the selection, which the
                # press already did, unless the optional insertion point is
                # enabled. Dragging still draws a marquee.
                # In Calc mode SMath's red cross is the insertion point (it
                # was placed on the press); one marker, never two.
                if preferences.current().insertion_point and not self.calc.calc_mode():
                    frame = self.frame_at(scene_pos)
                    if frame is not None:
                        self._insertion_point = self.snap_scene(scene_pos, frame)
                        self.statusMessage.emit(
                            "Insertion point set · Up/Down moves it · Esc clears it")
                self._mode = "idle"
                self.cancel_marquee()
                self.viewport().update()
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

        pending = getattr(self, "_pending_reshape", None)
        self._pending_reshape = None
        if pending is not None and self._mode in ("move", "resize") \
                and self._is_a_click(scene_pos):
            # Clicked, not dragged: put everything back as it was pressed and
            # do the reshaping the click asked for.
            if self._mode == "move":
                for item, origin in self._move_items:
                    item.setPos(origin)          # a click's jitter is not a move
            self._mode = "idle"
            self._snap_marker = None
            self._handle_item = None
            self._shift_click_selection = None
            self._copy_on_move = False
            self._copied = False
            self.commit_snapshot("Move markup")  # nothing changed: records nothing
            self.reshape_at(*pending)
            self.selectionChanged.emit()
            event.accept()
            return

        if self._mode == "move":
            self._mode = "idle"
            self._snap_marker = None
            if self._is_a_click(scene_pos) and self._shift_click_selection:
                family, wanted = self._shift_click_selection
                for member in family:
                    member.setSelected(wanted)
                self.selectionChanged.emit()
            self._shift_click_selection = None
            from ..items.calc import keep_blocks_whole
            said = keep_blocks_whole(self.scene(), self._move_items)
            if said:
                self.statusMessage.emit(said)
            self.settle_pages([item for item, _ in self._move_items])
            self.rescale_where_they_landed([item for item, _ in self._move_items])
            self.commit_snapshot("Copy markup" if self._copied else "Move markup")
            self._copy_on_move = False
            self._copied = False
            self._move_original_data = {}
            self._update_hover_cursor(scene_pos, event.modifiers())
            event.accept()
            return

        if self._mode == "group_resize":
            self._mode = "idle"
            items = [entry[0] for entry in self._group_resize_items]
            self._group_resize_items = []
            self._group_handle_key = ""
            self.settle_pages(items)
            self.commit_snapshot("Resize group")
            self.selectionChanged.emit()
            self._update_hover_cursor(scene_pos, event.modifiers())
            event.accept()
            return

        if self._mode == "resize":
            self._mode = "idle"
            item = self._handle_item
            self._handle_item = None
            if item is not None:
                item.refresh(page=self.page_of(item) or self.page())
                from ..items.calc import CalcBlockItem, keep_block_resize
                if isinstance(item, CalcBlockItem):
                    said = keep_block_resize(item)
                    if said:
                        self.statusMessage.emit(said)
            self.commit_snapshot("Resize markup")
            self.selectionChanged.emit()
            self._update_hover_cursor(scene_pos, event.modifiers())
            event.accept()
            return

        if self._mode == "table_resize":
            self._mode = "idle"
            self.commit_snapshot("Resize column")
            self._update_hover_cursor(scene_pos, event.modifiers())
            event.accept()
            return

        if self._mode == "table_select":
            self._mode = "idle"
            event.accept()
            return

        if self._mode == "draw_drag" and self.current_tool().mode in (CLOUDY, CLOUD) \
                and self._is_a_click(scene_pos) and isinstance(self._draft, RectItem):
            # Clicked, not dragged: this cloud is being drawn corner by corner.
            self._become_a_drawn_cloud(scene_pos)
            event.accept()
            return

        if self._mode == "draw_drag":
            if self._is_a_click(scene_pos):
                # Bluebeam draws either way: press and drag, or click once for
                # the first point and again for the second. A click used to
                # finish the markup then and there, which is where a measure
                # tool got its 120 pt measurement from nowhere.
                self._mode = "draw_click"
                if (isinstance(self._draft, RectItem)
                        and self._draft.kind in SIZED_SHAPES
                        and self._size_editor is None):
                    self.open_size_editor(self._draft)
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
            self._update_draft(scene_pos, event.modifiers(), final=True)
            self._mode = "idle"
            self.finish_draft(scene_pos)
            self.forget_snap()
            self.viewport().update()
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
        # A table: double-clicked, it opens for its cells (Markup mode), or
        # the cell double-clicked is edited (it was already open).
        if self.tables.mouse_double_click(event, scene_pos):
            event.accept()
            return
        # A chart: its dialog (type, titles, axes, series, error bars, trendlines)
        if event.button() == Qt.LeftButton:
            hit = self.markup_at(scene_pos)
            if getattr(hit, "TYPE", "") == "chart" and self.editable(hit):
                from .chartdialog import edit_chart
                edit_chart(self.window, hit)
                event.accept()
                return
        # A closed calculation block opens, as a text box does, and the
        # double-click goes on to what is under it inside.
        if event.button() == Qt.LeftButton:
            from ..items.calc import CalcBlockItem
            block = self.markup_at(scene_pos)
            if isinstance(block, CalcBlockItem) and not block.opened:
                self.open_block(block)
                if self.calc.calc_item_at(scene_pos) is None:
                    inside = self.markup_at(scene_pos)
                    if inside is None or inside is block:
                        if self.calc.calc_mode():
                            frame = self.frame_at(scene_pos)
                            if frame is not None:
                                self.calc.place_cross(frame, frame.mapFromScene(scene_pos))
                        event.accept()
                        return
        # An equation: the cursor goes where it was double-clicked, as a
        # single click puts it (SMath's automatic unit is not editable).
        if event.button() == Qt.LeftButton:
            equation = self.calc.calc_item_at(scene_pos)
            if equation is not None and self.editable(equation):
                self.calc.focus(equation, scene_pos)
                event.accept()
                return
        # Already editing this text: let the editor select a word.
        rect = self.editing_rect()
        if rect is not None and rect.contains(scene_pos):
            super().mouseDoubleClickEvent(event)
            return
        item = self.markup_at(scene_pos)
        if item is None:
            super().mouseDoubleClickEvent(event)
            return
        if getattr(item, "TYPE", "") == "link":
            self.window.follow_link(item)
            event.accept()
            return
        if isinstance(item, ContentsItem):
            row = item.row_at(item.mapFromScene(scene_pos))
            if row is not None:
                self.window.go_to_bookmark(*row)
                event.accept()
                return
        if isinstance(item, _TextBase) and not item.locked:
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
                item.refresh(page=self.page())
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
            item.refresh(page=self.page_of(item))
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
        """The complete bounds of the exact markup or group being held."""
        boxes = QRectF()
        for data in self.pending_payloads():
            item = build_item(data)
            if item is not None:
                box = item.mapRectToParent(item.local_rect().normalized())
            else:
                rect = data.get("rect")
                width, height = ((float(rect[2]), float(rect[3])) if rect
                                 else (120.0, 40.0))
                box = QRectF(float(data.get("x", 0.0)),
                             float(data.get("y", 0.0)), width, height)
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
        # Fresh names for every group in the tool, keeping the arrangement it
        # was kept in: a tool made of a group inside a group comes down as
        # one, and putting the same tool down twice gives two of them rather
        # than one group of ten markups.
        renamed: dict = {}
        for data in payloads:
            for step in (data.get("group_path") or []):
                renamed.setdefault(str(step), os.urandom(6).hex())
        group_name = os.urandom(6).hex() if len(payloads) > 1 \
            and not entry.payload.get("ungrouped") else ""
        self.begin_snapshot([frame])
        self.scene().clearSelection()
        placed = []
        for data in payloads:
            data["uid"] = os.urandom(8).hex()
            path = [renamed[str(step)] for step in (data.get("group_path") or [])]
            if not path and group_name:
                path = [group_name]
            elif group_name and path:
                path = [path[0]] + path[1:]
            data["group_path"] = path
            data["group"] = path[0] if path else ""
            item = build_item(data)
            if item is None:
                continue
            if hasattr(item, "load_from_document"):
                item.load_from_document(self.document())
            item.setPos(origin + QPointF(float(data.get("x", 0.0)),
                                         float(data.get("y", 0.0))))
            frame.add_markup(item)
            item.setSelected(True)
            placed.append(item)
        self._onto_the_calc_grid(placed)
        self.commit_snapshot(f"Place {entry.label}")
        self.selectionChanged.emit()
        self._pending_stamp = None
        self.setCursor(self._cursor_for_tool(self.current_tool()))
        self.statusMessage.emit(f"{entry.label} placed" if len(placed) == 1
                                else f"{entry.label} placed — {len(placed)} markups")
        self.viewport().update()
        return bool(placed)

    def _onto_the_calc_grid(self, placed: list) -> None:
        """Equations, Calculation text and blocks put down from a tool set
        land on SMath's grid, as if typed there; the first one's step moves
        the rest with it, so what was kept together stays in step."""
        from ..items.calc import CalcBlockItem
        from .calcedit import snap
        lead = next((i for i in placed if isinstance(i, (CalcItem, CalcTextItem, CalcBlockItem))),
                    None)
        if lead is None:
            return
        where = lead.pos()
        step = QPointF(snap(where.x()) - where.x(), snap(where.y()) - where.y())
        for item in placed:
            if isinstance(item, (CalcItem, CalcTextItem, CalcBlockItem)):
                item.setPos(item.pos() + step)
        sheet_for_items = [i for i in placed if isinstance(i, CalcItem)]
        if sheet_for_items:
            from ..calc.docsheet import sheet_for
            sheet_for(self.document()).settle()

    def _pending_origin(self, frame, scene_pos: QPointF) -> QPointF:
        """Offset an exact tool-set item from its bottom-left pointer anchor."""
        local = frame.mapFromScene(self.snap_scene(scene_pos, frame))
        extent = self.pending_extent()
        return QPointF(local.x() - extent.left(), local.y() - extent.bottom())

    def _prepare_draft(self, item: MarkupItem) -> None:
        item.author = self.document().settings.default_author or self.document().author
        if isinstance(item, RectItem) and item.kind == "marquee":
            # A region being chosen is not a markup and wears no markup style.
            return
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
        cloud = self._pending_cloud
        self._pending_anchor = None
        self._pending_cloud = None
        self.begin_snapshot()
        item = tool.factory()
        self._prepare_draft(item)
        # The size the preview showed, so the box that lands is the box that
        # was drawn under the pointer — and the leader meets it in the same
        # place, rather than shifting when the click goes down.
        width, height = self._default_size(item)
        item.set_local_rect(QRectF(0, 0, width, height))
        frame = self.frame_at(point) or self.frame()
        local = frame.mapFromScene(point)
        frame.add_markup(item, QPointF(local.x(), local.y() - height / 2))
        if cloud:
            # A cloud call-out points with its cloud, so the leader it was
            # built with is the cloud leader and not an arrow beside it.
            item.leaders = []
            item.set_cloud([item.mapFromScene(corner) for corner in cloud])
        elif anchor is not None:
            item.tip = item.mapFromScene(anchor)
        item.refresh(page=self.page())
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
        self.close_size_editor()
        draft = self._draft
        self._draft = None
        if draft is None:
            return
        tool = self.current_tool()
        origin = self._draw_origin or self._press_scene
        self._draw_origin = None
        # A drawing finished by a second click is the size the two clicks made
        # it, however small; only a stray tap gets a default size.
        typed = bool(getattr(self, "_typed_size", False))
        degenerate = self._is_a_click(scene_pos, origin) and not typed
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
        else:
            rect = draft.local_rect()
            if not typed and (tiny or rect.width() < 6 or rect.height() < 6):
                draft.set_local_rect(QRectF(0, 0, *self._default_size(draft)))
        self._typed_size = False
        self._typed_w = self._typed_h = self._typed_rotation = None

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
            if tiny:
                # A click-placed image hangs above the pointer from its
                # bottom-left, matching snapshots, groups and kept tools.
                draft.setPos(draft.pos()
                             + QPointF(0, -draft.local_rect().normalized().height()))
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

        if tool.key == "cutout_ellipse" and self.take_out_of_an_area(draft, tool):
            return

        if tool.mode == CLOUD:
            self.hand_the_cloud_to_the_note(draft, tool)
            return

        if tool.mode == SNAPSHOT:
            # The marquee is not a markup: it says which part of the page to
            # take a copy of, and then it goes. Handle it before the normal
            # new-markup selection step so worksheet items explicitly
            # selected before Snapshot remain selected for capture filtering.
            region = draft.mapRectToParent(draft.local_rect().normalized())
            frame = draft.parentItem()
            detach(draft)
            self.forget_snapshot()
            # The tool is put away first: finishing it writes its own message
            # into the status bar, which would wipe out what the snapshot has
            # to say about what it took.
            self.finish_tool()
            if tool.key == "whiteout":
                self.window.whiteout_region(frame, region)
            elif tool.key == "crop":
                self.window.crop_page_region(frame, region)
            elif tool.key == "viewport":
                self.window.add_viewport(frame, region)
            else:
                self.window.take_snapshot(frame, region)
            return

        draft.refresh(page=self.page())
        self.scene().clearSelection()
        draft.setSelected(True)
        self.selectionChanged.emit()

        if isinstance(draft, CalloutItem) and self._pending_anchor is not None:
            # Point the leader at whatever was clicked before the box was
            # drawn. Where it bends is the leader's own business — it comes
            # square out of the side facing what it points at — so nothing is
            # set here but the arrow head.
            draft.tip = draft.mapFromScene(self._pending_anchor)
            self._pending_anchor = None

        # Tools that ask a question do it now, while the markup is still fresh.
        note_scale = False
        # A rectangle or ellipse is sized in the bar beside the corner while
        # it is drawn; nothing more is asked once it is down.
        if getattr(draft, "TYPE", "") == "link":
            self.window.edit_link(draft)
        if isinstance(draft, MeasureItem):
            if draft.kind != DIMENSION:
                note_scale = True
        self.commit_snapshot(f"Add {tool.label.lower()}")

        if isinstance(draft, MeasureItem) and draft.kind == DIMENSION \
                and self.window.interactive_prompts:
            self.open_label_editor(draft)
        elif isinstance(draft, (TextItem, CalloutItem)):
            self.begin_item_edit(draft)
        self.finish_tool()
        # Last word, so returning to the select tool does not wipe the notice.
        if note_scale:
            self.window.note_missing_scale()

    @staticmethod
    def _default_size(item: MarkupItem) -> tuple[float, float]:
        if isinstance(item, StampItem):
            return 190.0, 58.0
        if isinstance(item, (TextItem, CalloutItem)):
            return 170.0, 44.0
        if isinstance(item, ImageItem):
            return 220.0, 160.0
        return 120.0, 80.0

    def hand_the_cloud_to_the_note(self, draft, tool: Tool) -> None:
        """The cloud is drawn; now the note it belongs to.

        Its corners are remembered, the draft is thrown away, and the next
        click says where the words go — the note carries the cloud, so what
        lands is one markup rather than a cloud and a note that happen to be
        side by side.
        """
        if isinstance(draft, PolyItem):
            corners = [draft.mapToScene(point) for point in draft.points]
        else:
            box = draft.mapRectToScene(draft.local_rect().normalized())
            corners = [box.topLeft(), box.topRight(),
                       box.bottomRight(), box.bottomLeft()]
        detach(draft)
        self.forget_snapshot()
        self._pending_cloud = corners
        self._pending_anchor = QPointF(corners[0])
        # The cloud is done; what comes next is placing the words.
        self.setCursor(drawing_cursor("callout"))
        self.statusMessage.emit(
            f"{tool.label}: now click where the words go · Esc to cancel")
        self.viewport().update()

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
        if tool.key == "cutout_polygon" and self.take_out_of_an_area(draft, tool):
            return
        if tool.mode == CLOUD:
            # A cloud call-out clicked out corner by corner: the shape is
            # settled, and the note that carries it comes next.
            self.hand_the_cloud_to_the_note(draft, tool)
            return
        draft.refresh(page=self.page())
        self.scene().clearSelection()
        draft.setSelected(True)
        self.commit_snapshot(f"Add {tool.label.lower()}")
        self.selectionChanged.emit()
        self.finish_tool()

    def take_out_of_an_area(self, draft, tool: Tool) -> bool:
        """Turn a drawn shape into a hole in the area measurement under it.

        A cut-out is not a markup of its own: it belongs to the measurement it
        came out of, so moving that measurement takes its holes with it and
        the total always says what is left. False when there was no area
        measurement under it to belong to, and the caller carries on.
        """
        ring = [draft.mapToScene(point) for point in self._draft_ring(draft)]
        if len(ring) < 3:
            return False
        centre = QPointF(sum(p.x() for p in ring) / len(ring),
                         sum(p.y() for p in ring) / len(ring))
        target = self.area_under(centre, ignore=draft)
        if target is None:
            detach(draft)
            self.statusMessage.emit(
                f"{tool.label}: draw it inside an area measurement")
            self.finish_tool()
            return True
        hole = [target.mapFromScene(point) for point in ring]
        target.prepareGeometryChange()
        target.cutouts.append(hole)
        detach(draft)
        target.refresh(page=self.page())
        target.touch()
        target.update()
        self.scene().clearSelection()
        target.setSelected(True)
        self.commit_snapshot(f"Add {tool.label.lower()}")
        self.selectionChanged.emit()
        # A measurement says what is left; a plain shape has no total to say.
        left = getattr(target, "value_text", "") or getattr(target, "size_text", "")
        self.statusMessage.emit(f"Taken out: {left}" if left
                                else f"Taken out of the {target.NAME.lower()}")
        self.finish_tool()
        return True

    @staticmethod
    def _draft_ring(draft) -> list:
        """The drawn shape as a ring of points, whatever it was drawn with."""
        points = list(getattr(draft, "points", []) or [])
        if points:
            return points
        rect = draft.local_rect().normalized()
        if rect.width() <= 0 or rect.height() <= 0:
            return []
        if getattr(draft, "kind", "") == "ellipse":
            # An ellipse as a ring of points: near enough for an area, and it
            # keeps holes to one shape everywhere else in the code.
            steps = 48
            centre, rx, ry = rect.center(), rect.width() / 2, rect.height() / 2
            return [QPointF(centre.x() + math.cos(2 * math.pi * i / steps) * rx,
                            centre.y() + math.sin(2 * math.pi * i / steps) * ry)
                    for i in range(steps)]
        return [rect.topLeft(), rect.topRight(), rect.bottomRight(), rect.bottomLeft()]

    def area_under(self, scene_pos: QPointF, ignore=None):
        """The closed shape that point falls inside, if any.

        A hole used to belong only to an area or volume measurement, so
        cutting one out of a rectangle, a circle or a plain polygon was not
        possible even though all of them enclose something and all of them are
        drawn round things that have holes in. Every closed shape answers with
        its own ring now, and the topmost one under the point owns the hole.
        """
        frame = self.frame_at(scene_pos) or self.frame()
        if frame is None:
            return None
        for item in reversed(frame.ordered_markups()):
            if item is ignore or not self.editable(item):
                continue
            ring = QPolygonF(item.outline_ring())
            if ring.size() >= 3 and ring.containsPoint(item.mapFromScene(scene_pos),
                                                       Qt.OddEvenFill):
                return item
        return None

    def forget_snapshot(self) -> None:
        """Drop the undo snapshot taken for a gesture that changes nothing."""
        self._snapshot = []

    def cancel_draft(self) -> None:
        self.close_size_editor()
        if self._draft is not None:
            detach(self._draft)
            self._draft = None
        self._mode = "idle"
        self.forget_snap()

    def open_size_editor(self, draft: RectItem) -> None:
        """The Bluebeam size bar: Width, Height and Rotation beside the corner.

        A compact dark bar that rides the corner being dragged. It reports the
        live size as the pointer moves, with the Width value selected so that
        typing a number replaces it; Tab moves to Height and on to Rotation,
        Enter places the shape. A typed width holds while the height still
        follows the pointer, and the other way about.
        """
        self.close_size_editor()
        panel = QWidget()
        panel.setObjectName("canvasSizeEntry")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        panel.setStyleSheet(
            "QWidget#canvasSizeEntry { background:#45484f; border:1px solid #2a2c31;"
            " border-radius:2px; }"
            "QLabel { color:#f1f3f5; background:transparent; font-size:11px; }"
            "QLabel[role='caption'] { color:#dfe3e8; }"
            "QLineEdit { background:#5b5f67; color:#ffffff; border:1px solid #6d727b;"
            " border-radius:1px; padding:0 3px; min-width:46px; max-width:62px;"
            " font-size:11px; selection-background-color:#1971c2;"
            " selection-color:#ffffff; }"
            "QLineEdit:focus { border-color:#4dabf7; }")
        grid = QGridLayout(panel)
        grid.setContentsMargins(5, 2, 5, 4)
        grid.setHorizontalSpacing(3)
        grid.setVerticalSpacing(0)
        scale = self._draft_scale()
        unit = scale.display_unit if scale.is_calibrated() else "mm"
        ellipse = draft.kind == "ellipse"
        fields = []
        for column, (caption, suffix, tip) in enumerate((
                ("Width", unit, "Horizontal diameter" if ellipse else "Width"),
                ("Height", unit, "Vertical diameter" if ellipse else "Height"),
                ("Rotation", "°", "Rotation in degrees"))):
            label = QLabel(caption)
            label.setProperty("role", "caption")
            grid.addWidget(label, 0, column * 2, 1, 2)
            box = _SizeEdit()
            box.setToolTip(tip)
            box.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            grid.addWidget(box, 1, column * 2)
            grid.addWidget(QLabel(suffix), 1, column * 2 + 1)
            fields.append(box)
        width, height, rotation = fields
        rotation.setText("0.00")
        proxy = self.scene().addWidget(panel)
        proxy.setZValue(20_000)
        # A tooltip belongs to the screen, not to the paper. Ignoring the view
        # transform keeps it upright and the same size whatever the zoom is
        # and whichever way the page has been turned for reading.
        from PySide6.QtWidgets import QGraphicsItem

        proxy.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        proxy.setRotation(0.0)
        self._size_editor = panel
        self._size_proxy = proxy
        self._size_width = width
        self._size_height = height
        self._size_rotation = rotation
        self._size_unit = unit
        self._typed_size = False
        self._typed_w = self._typed_h = None
        self._typed_rotation = None
        for box in fields:
            box.textEdited.connect(lambda _text, edited=box: self._size_typed(edited))
            box.escapePressed.connect(self.escape_everything)
            box.tabPressed.connect(lambda forwards, at=box: self._size_tab(at, forwards))
            box.enterPressed.connect(self.place_sized_draft)
        self.place_size_editor()
        self.follow_size_editor()
        self._size_current = width
        width.setFocus(Qt.OtherFocusReason)
        width.selectAll()
        self.statusMessage.emit(
            "Type a width, Tab for height and rotation, Enter or click to place "
            "· Esc to cancel")

    def _size_tab(self, current, forwards: bool) -> None:
        fields = [self._size_width, self._size_height, self._size_rotation]
        if current not in fields:
            return
        step = 1 if forwards else -1
        target = fields[(fields.index(current) + step) % len(fields)]
        self._size_current = target
        target.setFocus(Qt.TabFocusReason)
        target.selectAll()

    def place_size_editor(self) -> None:
        """Put the size bar just past the corner being dragged."""
        draft = self._draft
        proxy = self._size_proxy
        if proxy is None or not isinstance(draft, RectItem):
            return
        corner = self.mapFromScene(self._drag_corner(draft))
        proxy.setPos(self.mapToScene(corner + QPoint(14, 12)))

    def _drag_corner(self, draft) -> QPointF:
        """The shape's corner that is bottom-right *on screen*, in scene points.

        Not the one the item calls bottom-right: with the page turned for
        reading, that corner is somewhere else entirely, and the entry ends up
        beside a corner the pointer is nowhere near.
        """
        rect = draft.local_rect().normalized()
        corners = [rect.topLeft(), rect.topRight(), rect.bottomRight(), rect.bottomLeft()]
        best, furthest = None, None
        for corner in corners:
            scene_point = draft.mapToScene(corner)
            on_screen = self.mapFromScene(scene_point)
            reach = on_screen.x() + on_screen.y()
            if furthest is None or reach > furthest:
                best, furthest = scene_point, reach
        return best if best is not None else draft.mapToScene(rect.bottomRight())

    def follow_size_editor(self) -> None:
        """Ride the corner, and report the live size in the fields not typed in.

        The field with the keyboard keeps its value selected, so the next
        number typed replaces it rather than landing on the end of it.
        """
        self.place_size_editor()
        draft = self._draft
        if self._size_editor is None or not isinstance(draft, RectItem):
            return
        page = self.page()
        if page is None:
            return
        draft.refresh(page=page)
        scale = self._draft_scale()
        digits = max(scale.precision, 0) if scale.is_calibrated() else 2
        for box, value, typed in ((self._size_width, draft.width_value, self._typed_w),
                                  (self._size_height, draft.height_value, self._typed_h)):
            if box is None or value is None or typed is not None:
                continue
            was = box.blockSignals(True)
            box.setText(f"{float(value.magnitude):.{digits}f}")
            if box is self._size_current:
                box.selectAll()
            box.blockSignals(was)

    @staticmethod
    def _size_with_default_unit(text: str, unit: str) -> str:
        stripped = text.strip()
        if re.fullmatch(r"[+]?(?:\d+(?:\.\d*)?|\.\d+)", stripped):
            return f"{stripped} {unit}"
        return stripped

    def _draft_scale(self):
        """The scale the shape being drawn is measured at — its viewport's."""
        page = self.page()
        if page is None:
            from ..core.document import PageScale
            return PageScale()
        draft = self._draft
        scale_on = getattr(draft, "scale_on", None)
        if callable(scale_on):
            return scale_on(page)
        return page.scale

    def _points_for(self, text: str, down: bool = False) -> Optional[float]:
        """A typed length as page points, in the page's scale; None if unreadable.

        *down* reads it at the page's Y scale, for a height.
        """
        from ..core.units import parse_unit

        page = self.page()
        quantity = parse_unit(self._size_with_default_unit(text, self._size_unit))
        if quantity is None or page is None:
            return None
        scale = self._draft_scale()
        try:
            if scale.is_calibrated():
                points = float((quantity / scale.length(1.0))
                               .to("dimensionless").magnitude)
                if down:
                    points /= getattr(scale, "y_factor", 1.0) or 1.0
            else:
                points = float(quantity.to("mm").magnitude) * MM_TO_PT
        except Exception:                                  # noqa: BLE001
            return None
        return points if points > 0 else None

    def _size_typed(self, box) -> None:
        """A field was typed into: hold that value and redraw the shape."""
        text = box.text().strip()
        if box is self._size_rotation:
            try:
                self._typed_rotation = float(text) if text else None
            except ValueError:
                self._typed_rotation = None
        else:
            points = self._points_for(text, down=box is not self._size_width) \
                if text else None
            if box is self._size_width:
                self._typed_w = points
            else:
                self._typed_h = points
            draft = self._draft
            if (isinstance(draft, RectItem) and draft.kind == "ellipse"
                    and box is self._size_width and points is not None
                    and not self._size_height.isModified()):
                # One diameter typed is a circle until the other is given.
                self._typed_h = self._points_for(text, down=True)
        self._typed_size = any(value is not None for value in
                               (self._typed_w, self._typed_h, self._typed_rotation))
        if self._draft is not None:
            self._update_draft(self._last_scene_pos, Qt.NoModifier)
            self.viewport().update()

    def place_sized_draft(self) -> None:
        """Enter in the size bar: put the shape down at the size it shows."""
        if self._draft is None or self._mode not in ("draw_drag", "draw_click"):
            return
        at = QPointF(self._last_scene_pos)
        self._update_draft(at, Qt.NoModifier)
        self._mode = "idle"
        self.close_size_editor()
        self.finish_draft(at, clicked=True)

    def close_size_editor(self) -> None:
        proxy = self._size_proxy
        self._size_editor = None
        self._size_proxy = None
        self._size_width = None
        self._size_height = None
        self._size_rotation = None
        if proxy is not None:
            widget = proxy.widget()
            if widget is not None:
                widget.clearFocus()
            if proxy.scene() is not None:
                proxy.scene().removeItem(proxy)
            proxy.deleteLater()
        if self.hasFocus() is False:
            self.setFocus(Qt.OtherFocusReason)

    def editing_item(self):
        return self._editing_item

    def text_editor(self):
        """The live text editor under the caret, if the caret is in words.

        A text box, a call-out and a maths line all put a QGraphicsTextItem on
        the page while they are being typed into; anything that wants to act
        on the run of characters picked out — emboldening it, say — needs that
        editor rather than the markup it belongs to.
        """
        item = self._editing_item
        if item is None:
            return None
        editor = getattr(item, "_editor", None)
        if editor is None or not hasattr(editor, "textCursor"):
            return None
        return editor

    def is_editing(self) -> bool:
        """True when a keystroke belongs to something being typed into.

        A region, a cell, or a table with the cursor in it: in all three the
        keyboard is writing, and a tool key would be a letter of somebody's
        sentence rather than a request to change tool.
        """
        return (self._editing_item is not None
                or self._label_editor is not None
                or self.calc.editing())


    def begin_item_edit(self, item) -> None:
        if self._mode == "lasso":
            self.cancel_marquee()
        if self._editing_item is not None and self._editing_item is not item:
            # One caret at a time. Opening a second region without settling the
            # first left the first one's editor on the page, still showing a
            # caret, with nothing able to close it.
            self.end_item_edit()
        # The text may be on a page other than the one on screen — somebody
        # can scroll while a note is open — so its own page is what has to be
        # recorded, not whichever the chrome calls current.
        self.begin_snapshot(self.involved_frames(item))
        # Somebody else's text, opened: drawn here while it is typed in, and
        # given back to its file if it is closed without a change.
        self._edit_was_theirs = (item.serialize() if getattr(item, "still_theirs", False)
                                 else None)
        self.scene().clearSelection()
        item.setSelected(True)
        item.begin_edit()
        self._editing_item = item


    def place_caret(self, item, scene_pos: QPointF) -> None:
        """Put the caret where the words were clicked.

        Qt's own layout knows which character is under a point, and for a text
        box that is the right answer — it is a real document laid out where it
        is shown. Handing the click to the editor and hoping is not: the editor
        sits at the item's origin, so a click measured against the page lands
        somewhere else entirely.
        """
        editor = getattr(item, "_editor", None)
        if editor is None:
            return

        local = editor.mapFromScene(scene_pos)
        document = editor.document()
        layout = document.documentLayout() if document is not None else None
        if layout is None:
            return
        at = layout.hitTest(local, Qt.FuzzyHit)
        if at < 0:
            return
        cursor = editor.textCursor()
        cursor.setPosition(at)
        editor.setTextCursor(cursor)
        item.update()

    def end_item_edit(self) -> None:
        item = getattr(self, "_editing_item", None)
        if item is None:
            return
        self._editing_item = None
        item.end_edit()
        before, self._edit_was_theirs = self._edit_was_theirs, None
        if before is not None and item.scene() is not None \
                and _as_written(item.serialize()) == _as_written(before):
            item.still_theirs = True             # untouched: the file draws it again
            item.their_box = tuple(before.get("their_box") or ())
            item.sync_their_look()
            item.modified = before.get("modified", item.modified)
            self.scene().update()
        # A text box left completely empty is an invisible click target; drop it.
        elif self._is_empty(item):
            detach(item)
        self.commit_snapshot("Edit text")
        self.documentEdited.emit()

    @staticmethod
    def _is_empty(item) -> bool:
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
        """False when the markup is locked, or has been made part of the page."""
        from PySide6.QtWidgets import QGraphicsItem as _GraphicsItem
        if getattr(item, "SHEET_RUN", False):
            return True                # a spreadsheet page's cells: never picked up, always typed in
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

    def _selected_group(self):
        """The one complete selected group and its visible scene rectangle."""
        selected = [item for item in self.scene().selectedItems()
                    if isinstance(item, MarkupItem)] if self.scene() else []
        names = {item.group for item in selected if item.group}
        if len(names) != 1 or any(not item.group for item in selected):
            return None
        members = self.group_of(selected[0])
        if set(members) != set(selected):
            return None
        box = self.markup_box(members[0])
        for member in members[1:]:
            box = box.united(self.markup_box(member))
        return members, box

    def _group_handle_at(self, scene_pos: QPointF, box: QRectF) -> str:
        reach = HANDLE_SIZE / max(self.zoom(), 0.05)
        points = {"nw": box.topLeft(), "ne": box.topRight(),
                  "se": box.bottomRight(), "sw": box.bottomLeft()}
        return next((key for key, point in points.items()
                     if abs(point.x() - scene_pos.x()) <= reach
                     and abs(point.y() - scene_pos.y()) <= reach), "")

    def _resize_selected_group(self, scene_pos: QPointF,
                               release_ratio: bool = False) -> None:
        """Scale every member from one outer corner-handle gesture."""
        old = self._group_resize_box.normalized()
        if old.width() <= 0 or old.height() <= 0:
            return
        point = self.snap_scene(
            scene_pos, ignore={entry[0] for entry in self._group_resize_items})
        key = self._group_handle_key
        if key == "se":
            sx = (point.x() - old.left()) / old.width()
            sy = (point.y() - old.top()) / old.height()
        elif key == "nw":
            sx = (old.right() - point.x()) / old.width()
            sy = (old.bottom() - point.y()) / old.height()
        elif key == "ne":
            sx = (point.x() - old.left()) / old.width()
            sy = (old.bottom() - point.y()) / old.height()
        else:  # sw
            sx = (old.right() - point.x()) / old.width()
            sy = (point.y() - old.top()) / old.height()
        sx, sy = max(sx, 0.05), max(sy, 0.05)
        if not release_ratio:
            factor = sx if abs(sx - 1.0) >= abs(sy - 1.0) else sy
            sx = sy = factor

        width, height = old.width() * sx, old.height() * sy
        left = old.right() - width if "w" in key else old.left()
        top = old.bottom() - height if "n" in key else old.top()
        new_box = QRectF(left, top, width, height)
        for item, old_origin, old_transform in self._group_resize_items:
            x = new_box.left() + (old_origin.x() - old.left()) * sx
            y = new_box.top() + (old_origin.y() - old.top()) * sy
            wanted = QPointF(x, y)
            points = getattr(self, "_group_resize_points", {}).get(id(item))
            if points is not None:
                # A measurement is stretched by its points, not by a transform:
                # what it measures changes with it, and its words stay the
                # size they are (the user, 2026-10-01: the value didn't update).
                item.prepareGeometryChange()
                item.points = [QPointF(p.x() * sx, p.y() * sy) for p in points]
                item.refresh(page=item.parentItem().page
                             if hasattr(item.parentItem(), "page") else None)
            else:
                transform = QTransform(old_transform)
                transform.scale(sx, sy)
                item.setTransform(transform)
            parent = item.parentItem()
            if parent is not None:
                correction = (parent.mapFromScene(wanted)
                              - parent.mapFromScene(item.mapToScene(QPointF(0, 0))))
                item.setPos(item.pos() + correction)
            item.touch()
            item.update()
        self.viewport().update()

    @staticmethod
    def _latched_shift(item, key: str, event) -> Optional[bool]:
        """Shift as it was when the drag began, for the handles it decides.

        A dimension's control dot does one of two different things depending on
        whether Shift is down — it pulls the line off what it measures, or it
        takes the value away onto a leader. That is settled at the press;
        everywhere else Shift keeps meaning whatever it means moment to moment.
        """
        if key == "lbl" and isinstance(item, MeasureItem) and item.is_dimensioned():
            return bool(event.modifiers() & Qt.ShiftModifier)
        return None

    _opened_block = None
    _moved_yet = False
    _edit_was_theirs = None

    def open_block(self, block=None):
        """The calculation block open for editing (None if none); with
        *block*, open that one (closing any other) and return it."""
        current = self._opened_block
        if current is not None and (current.scene() is None or not current.opened):
            current = self._opened_block = None
        if block is None:
            return current
        if current is not None and current is not block:
            self.close_block()
        self.calc.leave()
        block.set_opened(True)
        block.setSelected(False)
        self._opened_block = block
        self.selectionChanged.emit()
        self.statusMessage.emit("Calculation block open: click an equation to edit it, "
                                "or the page inside it to start one · click outside "
                                "or Esc to close it")
        return block

    def close_block(self) -> None:
        block, self._opened_block = self._opened_block, None
        if block is not None:
            if block.scene() is not None and self.calc.item in block.members():
                self.calc.leave()
            block.set_opened(False)

    def markup_at(self, scene_pos: QPointF) -> Optional[MarkupItem]:
        from ..items.calc import closed_block_of
        for item in self.scene().items(scene_pos):
            if isinstance(item, MarkupItem):
                if getattr(item, "SHEET_RUN", False):
                    continue               # a spreadsheet page's cells: the page, not a markup on it
                block = closed_block_of(item)
                if block is not None:
                    return block           # a closed block is one thing
                if item.flattened:
                    # Flattened is part of the page, the way it is on a
                    # Bluebeam PDF. It was already unselectable, but it went on
                    # answering the question "what is under the pointer", so it
                    # stood in front of whatever was actually being reached
                    # for and nothing behind it could be picked up.
                    continue
                return item
        return None

    def insert_symbol(self, text: str) -> bool:
        """Type a symbol into whatever is being written; False if nothing is.

        A symbol that opens a bracket — the root sign — brings its closing
        bracket with it and leaves the caret between the two, because ``√(``
        on its own is half of something.
        """
        if self.calc.insert_symbol(text):
            return True                        # into an equation, with its maths meaning
        closing = ")" if text.endswith("(") else ""
        item = self._editing_item
        editor = getattr(item, "_editor", None) if item is not None else None
        if editor is None:
            return False
        cursor = editor.textCursor()
        cursor.insertText(text + closing)
        if closing:
            cursor.movePosition(QTextCursor.Left, QTextCursor.MoveAnchor,
                                len(closing))
        editor.setTextCursor(cursor)
        return True

    def busy_typing(self) -> bool:
        """True while words are being typed into something on the page.

        A shortcut that acts on the document has no business firing while a
        sentence is being written: Ctrl+B belongs to the text under the caret,
        not to the bookmarks.
        """
        return (self._editing_item is not None
                or getattr(self, "_label_editor", None) is not None)

    def idle_on_canvas(self) -> bool:
        """True when a keystroke should be read as "start something here".

        A lasso with only its first point down counts as idle: that is what one
        click on bare paper leaves behind, and a click on bare paper followed
        by typing is how most things get written on a page.
        """
        quiet = self._mode == "idle" or (self._mode == "lasso"
                                         and len(self._marquee) <= 2)
        return (self._editing_item is None and quiet
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
        self.tables.paint_insert_preview(painter)
        self.tables.view_moved()
        if self._marquee:
            if self._mode == "cloud_leader":
                self._draw_cloud_leader_preview(painter)
            else:
                self._draw_marquee(painter)
        self._draw_group_boxes(painter)
        self.calc.draw_cross(painter)
        if self._pending_stamp is not None:
            self._draw_pending_preview(painter)
        else:
            self._draw_tool_preview(painter)
        if (preferences.current().insertion_point
                and self._insertion_point is not None
                and not self.calc.calc_mode()):
            # (in Calc mode the red cross is the insertion point)
            self._draw_insertion_point(painter, self._insertion_point)
        if getattr(self, "_search_marks", None):
            self._draw_search_marks(painter)
        if self._snap_guides:
            self._draw_snap_guides(painter, rect)
        if self._snap_marker is not None:
            self._draw_snap_marker(painter, self._snap_marker)
        if self._pending_anchor is not None:
            self._draw_pending_leader(painter, self._pending_anchor)
        if self._pending_arrow_leader is not None:
            self._draw_arrow_leader_preview(painter)

    def set_search_marks(self, marks) -> None:
        """Outline where the Search panel found words: [(scene rect, current)]."""
        self._search_marks = list(marks)
        self.viewport().update()

    def _draw_search_marks(self, painter: QPainter) -> None:
        painter.save()
        for box, current in self._search_marks:
            colour = QColor("#f08c00" if current else "#fab005")
            fill = QColor(colour)
            fill.setAlpha(90 if current else 45)
            pen = QPen(colour)
            pen.setWidthF(2.0 if current else 1.0)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(fill)
            painter.drawRect(box.adjusted(-1, -1, 1, 1))
        painter.restore()

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
            if hasattr(item, "load_from_document"):
                item.load_from_document(self.document())
            at = frame.mapToScene(origin + QPointF(float(data.get("x", 0.0)),
                                                   float(data.get("y", 0.0))))
            painter.save()
            painter.translate(at)
            item.paint_visible(painter)
            painter.restore()
        # No box round it. The drawing under the pointer says where it will
        # land and how big it is; a dashed rectangle on top of that says
        # nothing the drawing has not already said, and gets in the way of
        # lining the thing up with what is under it.
        painter.restore()

    def _draw_tool_preview(self, painter: QPainter) -> None:
        """Show a click-placed tool under the pointer before it is put down.

        A tool you drag out shows itself as you drag. One that lands on a
        single click — a note, a count marker, a stamp — used to be invisible
        until it was already on the page, which is a poor moment to find out
        how big it is or where its corner falls.
        """
        tool = self.current_tool()
        if tool.mode != CLICK or self._mode != "idle":
            return
        if tool.factory is None or self.window.view.busy_typing():
            return
        item = self._preview_item(tool)
        if item is None:
            return
        frame = self.frame_at(self._last_scene_pos) or self.frame()
        if frame is None:
            return
        point = self.snap_scene(self._last_scene_pos, frame)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setOpacity(0.5)
        painter.translate(point)
        try:
            item.paint_visible(painter)
        except Exception:
            pass
        painter.restore()

    def _preview_item(self, tool: Tool):
        """One item of the tool's kind, made once and kept for the preview."""
        if getattr(self, "_preview_key", None) != tool.key:
            item = tool.factory()
            if item is None:
                return None
            self.window.apply_default_style(item)
            if self._pending_properties:
                from . import toolsets
                toolsets.apply_properties(item, self._pending_properties)
            if isinstance(item, CountItem):
                item.subject = self.count_subject
                item.symbol = self.count_symbol
            if isinstance(item, StampItem):
                item.text = self.stamp_text
            self._preview_key = tool.key
            self._preview_cache = item
        return getattr(self, "_preview_cache", None)

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

    CLOSING_REACH = 9.0

    def _add_lasso_point(self, scene_pos: QPointF) -> None:
        """One more corner — or the first one again, which closes the shape."""
        if not self._marquee:
            self._marquee = [QPointF(scene_pos)]
        first = self._marquee[0]
        reach = self.CLOSING_REACH / max(self.zoom(), 0.05)
        enough = len(self._marquee) > 3
        if enough and math.hypot(scene_pos.x() - first.x(),
                                 scene_pos.y() - first.y()) <= reach:
            self.select_in_marquee()
            return
        self._marquee.append(QPointF(scene_pos))
        self.viewport().update()

    def caught_by_marquee(self) -> list:
        """The markups the marquee takes: wholly inside, or crossed when
        dragged right to left."""
        polygon = self.marquee_polygon()
        crossing = self.marquee_crosses()
        if polygon.size() < 3:
            return []
        area = polygon.boundingRect()
        scene = self.scene()
        found = []
        for item in scene.items(area) if scene is not None else []:
            if not isinstance(item, MarkupItem) or not self.editable(item):
                continue
            box = self.markup_box(item)
            if crossing:
                caught = polygon.intersects(QPolygonF(box))
            else:
                caught = all(polygon.containsPoint(corner, Qt.OddEvenFill)
                             for corner in (box.topLeft(), box.topRight(),
                                            box.bottomRight(), box.bottomLeft()))
            if caught:
                found.append(item)
        return found

    def select_in_marquee(self) -> None:
        """Select what the marquee caught, then put it away."""
        caught = self.caught_by_marquee()
        self._marquee = []
        self._mode = "idle"
        self.viewport().update()
        for item in caught:
            for member in self.group_of(item):
                member.setSelected(True)
        self.selectionChanged.emit()

    @staticmethod
    def markup_box(item) -> QRectF:
        """What a markup *is*, in scene coordinates — not the room round it.

        ``sceneBoundingRect`` includes the margin a markup keeps for its
        handles and its rotation grip, which is drawing room, not the markup.
        Anything that asks "is this inside that" — a marquee, the box drawn
        round a group, which page a markup sits on — wants this instead, or a
        rectangle dragged neatly round a rectangle would fail to catch it.
        """
        rect = item.local_rect().normalized()
        if rect.width() <= 0 or rect.height() <= 0:
            return item.sceneBoundingRect()
        return item.mapRectToScene(rect)

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
        half = HANDLE_SCREEN_PX / max(self._zoom, 0.05) / 2
        for members in families.values():
            box = self.markup_box(members[0])
            for item in members[1:]:
                box = box.united(self.markup_box(item))
            painter.drawRect(box.adjusted(-margin, -margin, margin, margin))
            painter.setBrush(QColor("#ffffff"))
            for point in (box.topLeft(), box.topRight(),
                          box.bottomRight(), box.bottomLeft()):
                painter.drawRect(QRectF(point.x() - half, point.y() - half,
                                        half * 2, half * 2))
            painter.setBrush(QColor(11, 107, 203, 12))
        painter.restore()

    def _draw_cloud_leader_preview(self, painter: QPainter) -> None:
        """Show the cloud region and its connection while it is dragged.

        Not a drawing of one: the real thing. A copy of the note is given the
        cloud that the drag has reached and asked to paint its own leader, so
        the cloud, the corner it joins at, the hinge and the side it leaves by
        are the same code that lands. Drawing a straight line from the middle
        of the note instead put a leader through the words and into the box —
        which is not where one goes, and is not where the one that landed
        went either, so it jumped the moment the drag ended.
        """
        item = self._pending_cloud_leader
        if item is None or len(self._marquee) < 2:
            return
        rect = QRectF(self._marquee[0], self._marquee[-1]).normalized()
        if rect.width() < 1 or rect.height() < 1:
            return
        preview = self._a_copy_leading_to(item, cloud=rect)
        if preview is None:
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.translate(item.mapToScene(QPointF(0, 0)))
        preview.paint_leader(painter)
        painter.restore()

    def _draw_arrow_leader_preview(self, painter: QPainter) -> None:
        """Show where the new arrow would point, before the click lands."""
        item = self._pending_arrow_leader
        if item is None or item.scene() is None:
            return
        preview = self._a_copy_leading_to(
            item, point=self.snap_scene(self._last_scene_pos))
        if preview is None:
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.translate(item.mapToScene(QPointF(0, 0)))
        preview.paint_leader(painter)
        painter.restore()

    def _a_copy_leading_to(self, item, point: Optional[QPointF] = None,
                           cloud: Optional[QRectF] = None):
        """A copy of *item* with one more leader on it, for drawing a preview.

        A copy, so nothing is added to the document until the click lands, and
        the item itself rather than a sketch of one, so what is shown is what
        will be there. It is never put in a scene: it is only ever asked to
        paint, in the item's own coordinates.
        """
        from ..items.text import CalloutItem

        try:
            data = item.serialize()
            preview = CalloutItem()
            preview.deserialize(data)
            if cloud is not None:
                box = QRectF(item.mapFromScene(cloud.topLeft()),
                             item.mapFromScene(cloud.bottomRight())).normalized()
                preview.add_cloud_leader([box.topLeft(), box.topRight(),
                                          box.bottomRight(), box.bottomLeft()])
            else:
                preview.add_leader(item.mapFromScene(point))
            return preview
        except Exception:                              # noqa: BLE001
            return None

    def _draw_pending_leader(self, painter: QPainter, anchor: QPointF) -> None:
        """The call-out as it will be, drawn while it is being placed.

        Not a drawing of one: the real thing. A call-out is built where the
        click would put it, told what it points at, and asked to paint its
        own leader — so the hinge, the side it leaves by and the arrow head
        are not merely similar to what lands, they are the same code. Drawing
        a straight line to the pointer instead is why the leader used to have
        no hinge and then jump the moment the click landed.
        """
        preview = self._pending_callout()
        if preview is None:
            return
        box = preview.mapRectToScene(preview.local_rect())
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.translate(box.topLeft())
        preview.paint_leader(painter)
        # And the box the words will go in. It lands at a set size and grows
        # as it is written into, so showing that size is the whole answer to
        # "where will it be and how big".
        if self._draft is None:
            painter.setOpacity(0.45)
            painter.setBrush(QBrush(QColor(255, 255, 255)))
            pen = preview.style.pen()
            painter.setPen(pen)
            painter.drawRoundedRect(preview.local_rect(), 2.0, 2.0)
            painter.setOpacity(1.0)
        painter.restore()

    def _pending_callout(self):
        """The call-out that would land if the click came now.

        Made and thrown away every time the pointer moves, which costs
        nothing and means the preview cannot drift out of step with what is
        actually placed.
        """
        from ..items.text import CalloutItem

        anchor = self._pending_anchor
        if anchor is None:
            return None
        box = self._pending_callout_box()
        if box is None:
            return None
        item = CalloutItem("")
        self.window.apply_default_style(item)
        item.set_local_rect(QRectF(0, 0, box.width(), box.height()))
        item.setPos(box.topLeft())
        if self._pending_cloud:
            # A cloud call-out: the cloud is what points, so no arrow head,
            # and the line runs to the cloud rather than to a tip.
            item.leaders = []
            item.set_cloud([item.mapFromScene(corner)
                            for corner in self._pending_cloud])
        else:
            item.tip = item.mapFromScene(anchor)
        return item

    def _pending_callout_box(self) -> Optional[QRectF]:
        """Where the note would land if it were clicked down now.

        The pointer owns the middle of the left edge, which is also the anchor
        used when the click places the actual text box.
        """
        from ..items.text import CalloutItem

        if self._draft is not None:
            return self._draft.mapRectToScene(self._draft.local_rect())
        at = QPointF(self._last_scene_pos)
        width, height = self._default_size(CalloutItem())
        return QRectF(at.x(), at.y() - height / 2, width, height)

    def _draw_snap_guides(self, painter: QPainter, rect: QRectF) -> None:
        """The level or the upright the pointer has lined itself up with.

        Drawn right across the view, the way every drawing program draws
        them, because a short stub near the pointer does not say *what* it
        has lined up with.
        """
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, False)
        pen = QPen(QColor(232, 89, 12, 150))
        pen.setWidthF(0.8 / max(self._zoom, 0.05))
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        for which, value in self._snap_guides:
            if which == "across":
                painter.drawLine(QPointF(rect.left(), value),
                                 QPointF(rect.right(), value))
            else:
                painter.drawLine(QPointF(value, rect.top()),
                                 QPointF(value, rect.bottom()))
        painter.restore()

    def _draw_snap_marker(self, painter: QPainter, point: QPointF) -> None:
        """Where the pointer has caught hold.

        A small blue target gives snap feedback without the persistent-looking
        orange placement square that was mistaken for part of the markup.
        What it caught is said in the status bar rather than written over the
        drawing.
        """
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        scale = max(self._zoom, 0.05)
        arm = 5.0 / scale
        colour = QColor("#1971c2")
        pen = QPen(colour)
        pen.setWidthF(1.6 / scale)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(point, arm, arm)
        inner = arm * 0.45
        painter.drawLine(QPointF(point.x() - inner, point.y()),
                         QPointF(point.x() + inner, point.y()))
        painter.drawLine(QPointF(point.x(), point.y() - inner),
                         QPointF(point.x(), point.y() + inner))
        painter.restore()

    def _draw_insertion_point(self, painter: QPainter, point: QPointF) -> None:
        """Draw the optional remembered home for the next thing typed.

        A small crosshair, and nothing more. It marks a spot on a drawing that
        already has plenty on it, so it has to be findable without being one
        more thing in the way: two short strokes the same length, drawn at a
        fixed size on screen so it neither disappears when the page is zoomed
        out nor grows into a marker when it is zoomed in.
        """
        painter.save()
        scale = max(self._zoom, 0.05)
        arm = 5.0 / scale
        pen = QPen(QColor("#1971c2"))
        pen.setWidthF(1.2 / scale)
        painter.setPen(pen)
        painter.drawLine(QPointF(point.x() - arm, point.y()),
                         QPointF(point.x() + arm, point.y()))
        painter.drawLine(QPointF(point.x(), point.y() - arm),
                         QPointF(point.x(), point.y() + arm))
        painter.restore()

    def typing_position(self) -> QPointF:
        """Where a region opened by typing should appear, in page coordinates."""
        anchor = QPointF(self._insertion_point if (
            preferences.current().insertion_point
            and self._insertion_point is not None) else self._last_scene_pos)
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
        anchor = self._insertion_point if (
            preferences.current().insertion_point
            and self._insertion_point is not None) else self._last_scene_pos
        return self.frame_at(anchor) or self.frame()

    def half_way_through_something(self) -> bool:
        """True while a gesture is waiting on the next click or key.

        Half-placed call-outs, a held stamp or look, a shape being clicked
        out: all of them need a key press to finish or to cancel, and all of
        them are stranded if the keyboard is somewhere else.

        Words being typed count too. A click on a toolbar button or a panel
        takes the keyboard with it while the caret is still in the text — so
        Backspace, Escape and Enter all went to whatever was clicked and
        looked like keys that had simply stopped working.
        """
        return (self._editing_item is not None
                or self._pending_anchor is not None
                or self._pending_cloud is not None
                or self._pending_cloud_leader is not None
                or self._pending_arrow_leader is not None
                or self._pending_stamp is not None
                or self._pending_properties is not None
                or self._draft is not None
                or self._mode in ("draw_poly", "draw_click"))

    def enterEvent(self, event) -> None:
        """Take the keyboard back when the pointer comes back to the page.

        Leaving the window half-way through placing a call-out used to leave
        it stranded: the keyboard had gone to a panel, so Escape went there
        too and there was no way to cancel. Coming back over the page takes
        the focus back, and Escape means what it says again.
        """
        if self.half_way_through_something() and not typing_somewhere_else():
            self.setFocus(Qt.MouseFocusReason)
        super().enterEvent(event)

    def event(self, event) -> bool:
        """Take Tab before Qt spends it moving the focus.

        Qt treats Tab as "go to the next widget" and never lets it reach
        keyPressEvent, but on a canvas Tab is how a completion is accepted and
        how the next cell is reached. It is only taken when something is
        actually being typed into; otherwise it moves the focus as it always
        did.
        """
        if event.type() == QEvent.ShortcutOverride and self.tables.wants_shortcut(event):
            event.accept()
            return True
        if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Tab,
                                                               Qt.Key_Backtab):
            if self.tables.is_open():
                event.accept()
                self.keyPressEvent(event)
                return True
            if self._editing_item is not None or self.calc.editing():
                event.accept()
                self.keyPressEvent(event)
                if event.isAccepted():
                    return True
        return super().event(event)

    def give_the_keys_back_to_the_caret(self) -> None:
        """Point the scene's focus at whatever is being typed into.

        A click on a toolbar button takes the keyboard away from the page, and
        Qt drops the scene's focus with it. The keys the button has no use for
        come back here — and without this they would arrive with nothing in the
        scene to receive them, which is how Backspace, "=" and Enter came to
        look like keys that had stopped working.
        """
        item = self._editing_item
        editor = getattr(item, "_editor", None) if item is not None else None
        if editor is None or editor.scene() is not self.scene():
            return
        scene = self.scene()
        if scene is None or scene.focusItem() is editor:
            return
        if not scene.hasFocus():
            scene.setFocus(Qt.OtherFocusReason)
        editor.setFocus(Qt.OtherFocusReason)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        modifiers = event.modifiers()
        if key == Qt.Key_Control:
            self._control_held = True
            self._snap_marker = None
            self.viewport().update()
        if key == Qt.Key_Shift:
            self._shift_held = True
        if key in (Qt.Key_Control, Qt.Key_Shift) and self.tool_key == "select":
            # What the pointer would do has just changed under it.
            self._update_hover_cursor(self._last_scene_pos)

        # An open table takes Excel's keys (tableedit.py).
        if self.tables.key_press(event):
            event.accept()
            return

        # An equation being typed into takes SMath's keys; on bare paper in
        # Calc mode, typing starts one (calcedit.py).
        if self.calc.key_press(event):
            event.accept()
            return

        # While words are being typed every key belongs to them — arrows move
        # the caret, not the markup — apart from Escape, which finishes it.
        if self._label_editor is not None:
            if key == Qt.Key_Escape:
                self.close_label_editor(commit=False)
                event.accept()
                return
            super().keyPressEvent(event)
            return

        if self._editing_item is not None:
            self.give_the_keys_back_to_the_caret()
            if key == Qt.Key_Escape:
                # All the way back, not just out of the words: this branch
                # used to end the edit and stop there, which left the markup
                # still selected and the tool still held — half-way out, which
                # is not a state anybody presses Escape to reach.
                self.escape_everything()
                event.accept()
                return
            # Bold, italic and underline, on the keys they have in every
            # program there has ever been. Whatever command those keys carry
            # outside a markup, inside one they belong to the words: the
            # editor has no handling of its own for them, so without this the
            # keys would be swallowed and nothing at all would happen.
            if modifiers & Qt.ControlModifier and key in _FORMATTING_KEYS:
                if _FORMATTING_KEYS[key](self.window):
                    event.accept()
                    return
            # And everything else is a letter of what is being written. It
            # goes down to the scene, which hands it to the caret; nothing
            # below here may look at it, because a markup being typed into
            # owns every key that is not Escape.
            super().keyPressEvent(event)
            return

        if key == Qt.Key_Space and not event.isAutoRepeat():
            self._space_pan = True
            self.setCursor(Qt.OpenHandCursor)
            event.accept()
            return

        if key == Qt.Key_Escape:
            self.escape_everything()
            event.accept()
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
        # '"' starts typing a text box; tool keys pick their tool.
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
            # And nothing else. A letter on bare paper used to open a text
            # markup and put the letter in it, which meant every letter was
            # spoken for: a tool key that had not been bound yet, or a
            # keystroke meant for something that had just lost the focus,
            # started writing instead of doing nothing. Writing begins
            # deliberately with '"', which is on the shortcut list where it
            # can be changed.
            if event.text() and event.text().isprintable():
                event.accept()
                return

        if key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            if (preferences.current().insertion_point
                    and self._insertion_point is not None
                    and not self.scene().selectedItems()):
                # All four arrows move it. Left and Right used to fall through
                # to the nudge-or-scroll path and do nothing at all, so the
                # insertion point could be moved down a page but never along
                # a line, which is half a caret.
                step = 1.0 if modifiers & Qt.ShiftModifier else LINE_STEP
                across = 1.0 if modifiers & Qt.ShiftModifier else 0.25 * MM_TO_PT * 4
                move = {Qt.Key_Up: QPointF(0, -step), Qt.Key_Down: QPointF(0, step),
                        Qt.Key_Left: QPointF(-across, 0),
                        Qt.Key_Right: QPointF(across, 0)}[key]
                self._insertion_point += move
                self.follow_off_screen(QRectF(self._insertion_point, self._insertion_point)
                                       .adjusted(-12, -12, 12, 12))
                self.viewport().update()
                self.statusMessage.emit("Insertion point moved")
                event.accept()
                return
            step = 1.0 if modifiers & Qt.ShiftModifier else 0.25 * MM_TO_PT * 4
            delta = {Qt.Key_Left: QPointF(-step, 0), Qt.Key_Right: QPointF(step, 0),
                     Qt.Key_Up: QPointF(0, -step), Qt.Key_Down: QPointF(0, step)}[key]
            from ..items.calc import CalcBlockItem, with_block_members
            items = [i for i in with_block_members(self.scene().selectedItems())
                     if isinstance(i, MarkupItem) and self.editable(i)]
            if any(isinstance(i, (CalcItem, CalcTextItem, CalcBlockItem)) for i in items):
                # equations and Calculation text live on SMath's grid: a nudge
                # is one grid step
                from .calcedit import GRID_PT
                delta = QPointF(math.copysign(GRID_PT, delta.x()) if delta.x() else 0.0,
                                math.copysign(GRID_PT, delta.y()) if delta.y() else 0.0)
            if items:
                self.begin_snapshot(self.all_frames())
                origins = [(item, QPointF(item.pos())) for item in items]
                for item in items:
                    self._place(item, item.pos() + delta, keep_leader=len(items) == 1)
                from ..items.calc import keep_blocks_whole
                said = keep_blocks_whole(self.scene(), origins)
                if said:
                    self.statusMessage.emit(said)
                self.settle_pages(items)
                self.commit_snapshot("Nudge markup")
                box = items[0].sceneBoundingRect()
                for item in items[1:]:
                    box = box.united(item.sceneBoundingRect())
                self.follow_off_screen(box)
                event.accept()
                return
            # Nothing is selected and there is no insertion point, so there is
            # nothing for an arrow key to move. It used to scroll the document
            # here, the way a reader does — but this is a drawing, and a key
            # that quietly slid the page under the pointer moved what the next
            # click would land on. Scrolling is the wheel, the scrollbars and
            # the space bar; the arrows only ever move something.
            event.accept()
            return

        if self.navigation_key(event):
            return

        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # getting about
    # ------------------------------------------------------------------
    def follow_off_screen(self, box: QRectF) -> None:
        """Scroll only as far as it takes to keep *box* on screen.

        The arrows do not scroll the page. The one thing they may do is follow
        what they are moving: the caret, or the markup being nudged, walking
        off the edge of the view is the one time the view has to come with it,
        and then only by the amount that brings it back inside.
        """
        seen = self.mapToScene(self.viewport().rect()).boundingRect()
        if seen.contains(box):
            return
        dx = dy = 0.0
        if box.left() < seen.left():
            dx = box.left() - seen.left()
        elif box.right() > seen.right():
            dx = box.right() - seen.right()
        if box.top() < seen.top():
            dy = box.top() - seen.top()
        elif box.bottom() > seen.bottom():
            dy = box.bottom() - seen.bottom()
        if dx or dy:
            self.scroll_by(QPointF(dx, dy))

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


    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Control:
            self._control_held = False
        if event.key() == Qt.Key_Shift:
            self._shift_held = False
        if event.key() in (Qt.Key_Control, Qt.Key_Shift) \
                and self.tool_key == "select" and self._mode == "idle":
            self._update_hover_cursor(self._last_scene_pos)
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._space_pan = False
            self.setCursor(self._cursor_for_tool(self.current_tool()))
            event.accept()
            return
        super().keyReleaseEvent(event)

    def focusOutEvent(self, event) -> None:
        """Losing the keyboard is not the same as finishing the line.

        This used to close whatever was being typed the moment the focus went
        anywhere else, and the focus goes somewhere else for all sorts of
        reasons that have nothing to do with being finished: a right-click menu
        opening over the very expression being edited, a click on a toolbar
        button, another window coming forward. The caret vanished, and from
        then on Backspace, Escape, "=" and Enter all went somewhere that had no
        use for them — keys that had apparently stopped working.

        So the line stays open. It is finished by the things that mean
        finished: clicking somewhere else on the page, Escape, turning the
        page, or starting to type into something else.
        """
        # A key held when the focus left is not held any more as far as this
        # view can tell, and believing otherwise leaves snapping off and the
        # pointer promising something it will not do.
        self._control_held = False
        self._shift_held = False
        super().focusOutEvent(event)

    # ------------------------------------------------------------------
    # context menu
    # ------------------------------------------------------------------
    def contextMenuEvent(self, event) -> None:
        # A shape being clicked out corner by corner is closed by a right
        # click, which is what the cloud tool's own tooltip has always
        # promised — "Enter or a right-click closes it". It opened a context
        # menu over the half-drawn shape instead.
        if self._mode == "draw_poly" and self._draft is not None:
            self.finish_poly()
            event.accept()
            return
        if self._mode == "lasso":
            self.select_in_marquee()
            event.accept()
            return
        scene_pos = self.mapToScene(event.pos())
        table = self.tables.item
        if table is not None and table.chrome_rect().contains(table.mapFromScene(scene_pos)):
            self.tables.context_menu(event.globalPos())
            event.accept()
            return
        item = self.markup_at(scene_pos)
        run = self.tables.table_at(scene_pos) if item is None else None
        if getattr(run, "SHEET_RUN", False):
            # a spreadsheet page's cells: its own menu, on the cell clicked
            cell = run.cell_at(run.mapFromScene(scene_pos))
            if cell is not None:
                self.tables.open(run, cell)
                self.tables.context_menu(event.globalPos())
            event.accept()
            return
        if item is not None and not item.isSelected():
            self.scene().clearSelection()
            item.setSelected(True)
            self.selectionChanged.emit()
        menu = self.window.build_context_menu(item, scene_pos)
        menu.exec(event.globalPos())


def _as_written(data: dict) -> dict:
    """A markup's record, leaving out who draws it and when it was touched."""
    return {k: v for k, v in data.items()
            if k not in ("still_theirs", "modified", "their_box")}


def _far_enough(a: QPointF, b: QPointF) -> bool:
    return math.hypot(b.x() - a.x(), b.y() - a.y()) >= FREE_MIN_STEP


def _within(point: QPointF, of: QPointF, reach: float) -> bool:
    return math.hypot(point.x() - of.x(), point.y() - of.y()) <= reach


def _passes_near(start: QPointF, end: QPointF, point: QPointF,
                 reach: float) -> bool:
    """Whether a segment comes within *reach* of a point."""
    across = end.x() - start.x()
    down = end.y() - start.y()
    length = across * across + down * down
    if length < 1e-12:
        return _within(start, point, reach)
    along = ((point.x() - start.x()) * across
             + (point.y() - start.y()) * down) / length
    along = max(0.0, min(1.0, along))
    return _within(QPointF(start.x() + across * along,
                           start.y() + down * along), point, reach)


def _crossing(one_start: QPointF, one_end: QPointF,
              two_start: QPointF, two_end: QPointF) -> Optional[QPointF]:
    """Where two segments cross, or None when they do not.

    Where they actually cross, not where the lines through them would: two
    grid lines that stop short of each other do not meet, and offering the
    point they would have met at puts a measurement somewhere nothing is.
    """
    one_x = one_end.x() - one_start.x()
    one_y = one_end.y() - one_start.y()
    two_x = two_end.x() - two_start.x()
    two_y = two_end.y() - two_start.y()
    denominator = one_x * two_y - one_y * two_x
    if abs(denominator) < 1e-9:
        return None                                    # parallel, or a point
    gap_x = two_start.x() - one_start.x()
    gap_y = two_start.y() - one_start.y()
    along_one = (gap_x * two_y - gap_y * two_x) / denominator
    along_two = (gap_x * one_y - gap_y * one_x) / denominator
    if not (0.0 <= along_one <= 1.0 and 0.0 <= along_two <= 1.0):
        return None
    return QPointF(one_start.x() + one_x * along_one,
                   one_start.y() + one_y * along_one)
