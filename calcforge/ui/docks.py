"""Dock panels with a title bar you can actually use.

Qt's own dock title bar gives you float and close. An engineer working in one
arrangement all day wants a third thing: to pin a panel where it is, so a
stray drag cannot tear it off the side of the window. That is what this adds,
along with a layout that is remembered between sessions.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPainter, QPen, QColor, QPolygonF
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtWidgets import (QDockWidget, QHBoxLayout, QLabel, QSizePolicy,
                               QToolButton, QVBoxLayout, QWidget)

from ..settings import app_settings

PINNED_KEY = "panels/pinned"
COLLAPSED_KEY = "panels/collapsed"


def _icon(name: str, size: int = 14) -> QIcon:
    """Small monochrome glyphs for the title-bar buttons, in the theme's ink."""
    from .icons import INK, drawn_icon

    def draw(painter: QPainter) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.scale(size / 14.0, size / 14.0)
        pen = QPen(QColor(INK))
        pen.setWidthF(1.3)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        if name == "pin":
            painter.setBrush(QColor(INK))
            painter.drawPolygon(QPolygonF([QPointF(5, 2), QPointF(9, 2), QPointF(8.2, 6),
                                           QPointF(10, 8), QPointF(4, 8), QPointF(5.8, 6)]))
            painter.drawLine(QPointF(7, 8), QPointF(7, 12))
        elif name == "unpinned":
            painter.setBrush(Qt.NoBrush)
            painter.drawPolygon(QPolygonF([QPointF(5, 2), QPointF(9, 2), QPointF(8.2, 6),
                                           QPointF(10, 8), QPointF(4, 8), QPointF(5.8, 6)]))
            painter.drawLine(QPointF(7, 8), QPointF(7, 12))
        elif name == "collapse":
            painter.drawPolyline(QPolygonF([QPointF(4, 8.5), QPointF(7, 5.5),
                                            QPointF(10, 8.5)]))
        elif name == "expand":
            painter.drawPolyline(QPolygonF([QPointF(4, 5.5), QPointF(7, 8.5),
                                            QPointF(10, 5.5)]))
        elif name == "float":
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(2.5, 4.5, 7, 7))
            painter.drawPolyline(QPolygonF([QPointF(5.5, 2.5), QPointF(11.5, 2.5),
                                            QPointF(11.5, 8.5)]))
        else:                                   # close
            painter.drawLine(QPointF(3.5, 3.5), QPointF(10.5, 10.5))
            painter.drawLine(QPointF(10.5, 3.5), QPointF(3.5, 10.5))
    return drawn_icon(draw, size, size)


class _ElidedTitle(QLabel):
    """A panel's title that ends in … when the panel is too narrow for it.

    A plain label was cut off mid-letter by the buttons beside it when a
    narrow window squeezed the panels ("Thumbı", QA, 2026-10-15).
    """

    def minimumSizeHint(self) -> QSize:
        return QSize(0, super().minimumSizeHint().height())

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        rect = self.contentsRect()
        text = self.fontMetrics().elidedText(self.text(), Qt.ElideRight, rect.width())
        self.style().drawItemText(painter, rect, int(self.alignment()), self.palette(),
                                  self.isEnabled(), text, self.foregroundRole())
        painter.end()


class DockTitleBar(QWidget):
    """Title, pin, float and close — in that order, like every other tool."""

    def __init__(self, dock: "PanelDock"):
        super().__init__(dock)
        self.dock = dock
        self.setObjectName("dockTitleBar")
        # The title and its buttons on one line; a panel with a header of its
        # own (set_header) puts its buttons on a second line when the panel
        # is too narrow for them beside the title.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(9, 3, 4, 3)
        outer.setSpacing(2)
        layout = self._row = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        outer.addLayout(layout)
        self._under = QHBoxLayout()
        self._under.setContentsMargins(0, 0, 0, 0)
        self._under.setSpacing(2)
        outer.addLayout(self._under)
        self.header_title = None
        self.header_tools = None

        self.label = _ElidedTitle(dock.windowTitle())
        self.label.setObjectName("dockTitle")
        self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self.label)

        self.collapse = self._button("collapse", "Roll this panel up")
        self.collapse.setCheckable(True)
        self.collapse.toggled.connect(dock.set_collapsed)
        layout.addWidget(self.collapse)

        self.pin = self._button("pin", "Pin this panel where it is")
        self.pin.setCheckable(True)
        self.pin.toggled.connect(dock.set_pinned)
        layout.addWidget(self.pin)

        self.float_button = self._button("float", "Float this panel")
        self.float_button.clicked.connect(lambda: dock.float_on_purpose(not dock.isFloating()))
        layout.addWidget(self.float_button)

        self.close_button = self._button("close", "Hide this panel")
        self.close_button.clicked.connect(dock.close)
        layout.addWidget(self.close_button)

    def _button(self, name: str, tip: str) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName("dockButton")
        button.setIcon(_icon(name))
        button.setToolTip(tip)
        button.setAutoRaise(True)
        button.setFocusPolicy(Qt.NoFocus)
        # small and the same on every panel, as Revu's pin and close are
        button.setIconSize(QSize(14, 14))
        button.setFixedSize(QSize(20, 20))
        return button

    def minimumSizeHint(self) -> QSize:
        return QSize(0, 0)

    # -- a panel's own header ------------------------------------------------
    def set_header(self, title: QWidget, tools: QWidget) -> None:
        """A panel's own header in place of its plain title, as Revu's
        (the user, 2026-10-19): *title* is the panel's name as the menu of
        its commands ("Thumbnails ▾"), *tools* its buttons straight after
        it. Pin, float, roll up and close stay at the far right."""
        self.label.hide()
        self.header_title, self.header_tools = title, tools
        self._row.insertWidget(0, title)
        self._row.insertWidget(1, tools)
        self._row.insertStretch(2, 1)
        self._place_tools()

    def header_needs(self) -> int:
        """How wide the bar must be for the header's buttons to sit on the
        title's line."""
        margins = self.layout().contentsMargins()
        spacing = self._row.spacing()
        width = margins.left() + margins.right()
        width += self.header_title.sizeHint().width() + spacing
        width += self.header_tools.sizeHint().width() + spacing
        for button in (self.collapse, self.pin, self.float_button, self.close_button):
            if not button.isHidden():
                width += min(button.sizeHint().width(), button.maximumWidth()) + spacing
        return width

    def tools_on_the_title_line(self) -> bool:
        return self.header_tools is not None and self._row.indexOf(self.header_tools) >= 0

    def _place_tools(self) -> None:
        """The buttons beside the title when they fit, else on the line
        under it: never cut off, never over the pin and close."""
        tools = self.header_tools
        if tools is None:
            return
        beside = self.width() >= self.header_needs()
        if beside == self.tools_on_the_title_line():
            return
        if beside:
            self._under.removeWidget(tools)
            self._row.insertWidget(1, tools)
        else:
            self._row.removeWidget(tools)
            self._under.insertWidget(0, tools)
            if self._under.count() == 1:
                self._under.addStretch(1)
        tools.show()
        self.updateGeometry()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place_tools()

    def refresh_icons(self) -> None:
        """Redraw the buttons after a theme change."""
        self.float_button.setIcon(_icon("float"))
        self.close_button.setIcon(_icon("close"))
        refresh = getattr(self.header_tools, "refresh_icons", None)
        if refresh is not None:
            refresh()
        self.refresh()

    def mouseDoubleClickEvent(self, event) -> None:
        """Double-clicking the title rolls the panel up, as titles do."""
        self.dock.set_collapsed(not self.dock.collapsed)
        event.accept()

    def refresh(self) -> None:
        self.label.setText(self.dock.windowTitle())
        collapsed = self.dock.collapsed
        self.collapse.blockSignals(True)
        self.collapse.setChecked(collapsed)
        self.collapse.blockSignals(False)
        self.collapse.setIcon(_icon("expand" if collapsed else "collapse"))
        self.collapse.setToolTip("Unroll this panel" if collapsed
                                 else "Roll this panel up")
        pinned = self.dock.pinned
        self.pin.blockSignals(True)
        self.pin.setChecked(pinned)
        self.pin.blockSignals(False)
        self.pin.setIcon(_icon("pin" if pinned else "unpinned"))
        self.pin.setToolTip("Unpin this panel" if pinned
                            else "Pin this panel where it is")
        self.float_button.setEnabled(not pinned)


#: Where a panel may be docked.
PANEL_AREAS = Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea


class PanelDock(QDockWidget):
    """A dock that can be pinned in place, hidden, and put back."""

    pinnedChanged = Signal(bool)
    collapsedChanged = Signal(bool)

    def __init__(self, title: str, widget: QWidget, name: str, parent=None):
        super().__init__(title, parent)
        self.setObjectName(name)
        self.setWidget(widget)
        # Panels go on the left or the right, never along the top or the
        # bottom (the user, 2026-10-16: the Markups List alone has the bottom,
        # and it is not a dock)
        self.setAllowedAreas(PANEL_AREAS)
        #: floated with its float button: kept floating. Floated by a drag
        #: that ended away from both sides: put back (MainWindow).
        self.floated_on_purpose = False
        self._pinned = False
        self._collapsed = False
        self._restore_size = None
        # No floor of its own: the splitter can squeeze it away to nothing and
        # the reader can drag it back.
        widget.setMinimumSize(0, 0)
        widget.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumSize(0, 0)
        self._bar = DockTitleBar(self)
        self._bar.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setTitleBarWidget(self._bar)
        self.set_pinned(False)

    def set_header(self, title: QWidget, tools: QWidget) -> None:
        """The panel's own header on its title bar (DockTitleBar.set_header)."""
        self._bar.set_header(title, tools)

    def float_on_purpose(self, floating: bool) -> None:
        """The float button: out of its side as a window of its own, or back."""
        self.floated_on_purpose = bool(floating)
        self.setFloating(bool(floating))

    def minimumSizeHint(self) -> QSize:
        """Let the main-window splitter squeeze a dock fully out of view."""
        return QSize(0, 0)

    @property
    def pinned(self) -> bool:
        return self._pinned

    def set_pinned(self, pinned: bool) -> None:
        """Pinned means it stays put: no dragging it out, no floating it away."""
        self._pinned = bool(pinned)
        features = QDockWidget.DockWidgetClosable
        if not self._pinned:
            features |= QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable
        if self._pinned and self.isFloating():
            self.setFloating(False)
        self.setFeatures(features)
        self._bar.refresh()
        self.pinnedChanged.emit(self._pinned)

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool) -> None:
        """Roll the panel up to its title bar, or unroll it again.

        Better than dragging it down to nothing: the title bar stays, so there
        is something to take hold of to bring it back.
        """
        collapsed = bool(collapsed)
        if collapsed == self._collapsed:
            return
        body = self.widget()
        if collapsed:
            self._restore_size = self.size()
            if body is not None:
                body.hide()
            self.setMaximumHeight(self._bar.sizeHint().height() + 2)
        else:
            self.setMaximumHeight(16777215)
            if body is not None:
                body.show()
            if self._restore_size is not None:
                self.resize(self._restore_size)
        self._collapsed = collapsed
        self._bar.refresh()
        self.collapsedChanged.emit(collapsed)

    def showEvent(self, event) -> None:
        """Come back rolled up if that is how it was left.

        Qt gives a dock its height back when it is shown, which is after a
        restored arrangement has been applied — so a panel that was rolled up
        when the application closed used to open unrolled. The constraint is
        put back here, where being shown is the thing that took it away.
        """
        super().showEvent(event)
        if self._collapsed:
            body = self.widget()
            if body is not None:
                body.hide()
            self.setMaximumHeight(self._bar.sizeHint().height() + 2)


def _names(value) -> set[str]:
    """QSettings hands a one-item list back as a bare string."""
    if isinstance(value, str):
        value = [value] if value else []
    return set(value or [])


def save_panel_state(docks: list[PanelDock]) -> None:
    """Remember which panels are pinned and which are rolled up."""
    settings = app_settings()
    settings.setValue(PINNED_KEY,
                      [dock.objectName() for dock in docks if dock.pinned])
    settings.setValue(COLLAPSED_KEY,
                      [dock.objectName() for dock in docks if dock.collapsed])


def load_panel_state(docks: list[PanelDock]) -> None:
    settings = app_settings()
    pinned = _names(settings.value(PINNED_KEY, []))
    collapsed = _names(settings.value(COLLAPSED_KEY, []))
    for dock in docks:
        dock.set_pinned(dock.objectName() in pinned)
        dock.set_collapsed(dock.objectName() in collapsed)


def accent_colour() -> QColor:
    """Revu's blue, in the theme in force."""
    from ..app import current_theme
    from ..theme import _DARK_TOKENS, _LIGHT_TOKENS, DARK
    tokens = _DARK_TOKENS if current_theme() == DARK else _LIGHT_TOKENS
    return QColor(tokens["accent"])


#: How far a press may wander and still be a click, not a drag (pixels).
CLICK_SLOP = 4


class _EdgeBase(QWidget):
    """A panel edge as Revu has it: blue under the pointer, a click hides or
    brings back the panel, a drag resizes it (the user, 2026-10-18). A click
    is a press and release within CLICK_SLOP pixels; anything further is a
    drag. Its own widget, so it works the same on every platform, rather
    than hanging on QMainWindow's private separator (a double-click there
    did nothing on Windows)."""

    clicked = Signal(object)           # where, on the screen (a QPointF)
    dragStarted = Signal()
    dragMoved = Signal(int)            # pixels outward from the press, so far
    dragFinished = Signal(int)

    def __init__(self, side: str, parent=None):
        super().__init__(parent)
        self.side = side
        self.setAttribute(Qt.WA_Hover, True)
        self.setMouseTracking(True)
        self.setCursor(Qt.SplitHCursor)       # it still drags, as Revu's does
        self._hover = False
        self._pressed_at = None
        self._dragging = False

    # -- the look ------------------------------------------------------------
    def hovered(self) -> bool:
        return self._hover

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paint_resting(self, painter: QPainter) -> None:
        """How the edge looks with the pointer away."""

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        if self._hover or self._dragging:
            painter.fillRect(self.rect(), accent_colour())
        else:
            self.paint_resting(painter)
        painter.end()

    # -- click or drag ---------------------------------------------------------
    def _outward(self, event) -> int:
        moved = event.globalPosition().x() - self._pressed_at
        return int(moved if self.side == "left" else -moved)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        self._pressed_at = event.globalPosition().x()
        self._dragging = False
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._pressed_at is None:
            super().mouseMoveEvent(event)
            return
        outward = self._outward(event)
        if not self._dragging and abs(outward) > CLICK_SLOP:
            self._dragging = True
            self.dragStarted.emit()
        if self._dragging:
            self.dragMoved.emit(outward)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if self._pressed_at is None or event.button() != Qt.LeftButton:
            super().mouseReleaseEvent(event)
            return
        outward = self._outward(event)
        dragging, self._dragging, self._pressed_at = self._dragging, False, None
        self.update()
        event.accept()
        if dragging:
            self.dragFinished.emit(outward)
        else:
            self.clicked.emit(QPointF(event.globalPosition()))

    def mouseDoubleClickEvent(self, event) -> None:
        # the second click of a double-click is a click like the first (it
        # puts the panel back where it was); it arrives as this, not a press
        self.mousePressEvent(event)


class ColumnSeparator(_EdgeBase):
    """Over the edge between an open panel column and the canvas, where
    QMainWindow's own separator is: it takes the hover, the click and the
    drag (MainWindow._place_panel_separators keeps it there)."""

    WIDTH = 6

    def __init__(self, side: str, parent=None):
        super().__init__(side, parent)
        self.setObjectName(f"panelSeparator_{side}")
        self.setToolTip("Click to hide the panels · drag to resize them")


class PanelEdge(_EdgeBase):
    """The thin edge a hidden panel column leaves at the side of the canvas:
    a click on it, or a drag out from it, brings the column back. Shown only
    while that side has no panel open."""

    WIDTH = 6

    def __init__(self, side: str, parent=None):
        super().__init__(side, parent)
        self.setObjectName(f"panelEdge_{side}")
        self.setFixedWidth(self.WIDTH)
        self.setToolTip("Click, or drag, to bring the panels back")

    def paint_resting(self, painter: QPainter) -> None:
        painter.fillRect(self.rect(), self.palette().window())
        pen = QPen(self.palette().mid().color())
        pen.setWidth(1)
        painter.setPen(pen)
        x = self.width() - 1 if self.side == "left" else 0
        painter.drawLine(x, 0, x, self.height())
        middle = self.height() // 2
        for dy in (-8, -4, 0, 4, 8):                 # the grip, as a splitter's
            painter.drawPoint(self.width() // 2, middle + dy)
