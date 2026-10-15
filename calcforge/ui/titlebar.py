"""One line at the top, as Revu's: the application's icon, the menus, the
Markup | Calc switch and Search, and the window's own minimise, maximise and
close buttons — no system title bar above it (the user, 2026-10-15: "don't
have a separate top bar, it should be in the same line as the minimise
buttons").

The window draws no frame of its own, so the menu row does what a title bar
does: dragged where there is no menu, it moves the window (the system's own
move, so Windows still snaps it to the screen's edges and halves); double-
clicked, it maximises or restores. The window's edges resize it.

On macOS the menus stay in the system's menu bar and the window keeps its
native frame.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, QObject, QPointF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QWidget

#: Whether windows draw their own title row.
OWN_TITLE_BAR = sys.platform != "darwin"

#: How far in from the window's edge a press resizes it, in pixels.
EDGE = 5


class _WindowButton(QToolButton):
    """Minimise, maximise/restore or close, drawn as Windows draws them."""

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setObjectName(f"titleButton_{kind}")
        self.setFixedSize(QSize(46, 30))
        self.setFocusPolicy(Qt.NoFocus)
        self.setAutoRaise(True)
        self.setToolTip({"min": "Minimise", "max": "Maximise", "close": "Close"}[kind])
        self.hover = False

    def enterEvent(self, event):
        self.hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event):
        painter = QPainter(self)
        ink = self.palette().windowText().color()
        if self.hover:
            if self.kind == "close":
                painter.fillRect(self.rect(), QColor("#c42b1c"))
                ink = QColor("#ffffff")
            else:
                shade = QColor(ink)
                shade.setAlpha(28)
                painter.fillRect(self.rect(), shade)
        pen = QPen(ink, 1.0)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setRenderHint(QPainter.Antialiasing, self.kind == "close")
        cx, cy = self.width() / 2.0, self.height() / 2.0
        if self.kind == "min":
            painter.drawLine(QPointF(cx - 5, cy + 0.5), QPointF(cx + 5, cy + 0.5))
        elif self.kind == "max":
            window = self.window()
            if window is not None and window.isMaximized():
                painter.drawRect(int(cx - 5), int(cy - 3), 8, 8)
                painter.drawLine(QPointF(cx - 3, cy - 5.5), QPointF(cx + 5.5, cy - 5.5))
                painter.drawLine(QPointF(cx + 5.5, cy - 5.5), QPointF(cx + 5.5, cy + 3))
            else:
                painter.drawRect(int(cx - 5), int(cy - 5), 10, 10)
        else:
            painter.drawLine(QPointF(cx - 5, cy - 5), QPointF(cx + 5, cy + 5))
            painter.drawLine(QPointF(cx + 5, cy - 5), QPointF(cx - 5, cy + 5))
        painter.end()


class WindowButtons(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.setObjectName("windowButtons")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.minimise = _WindowButton("min", self)
        self.maximise = _WindowButton("max", self)
        self.close_button = _WindowButton("close", self)
        self.minimise.clicked.connect(lambda: window.window().showMinimized())
        self.maximise.clicked.connect(lambda: toggle_maximised(window.window()))
        self.close_button.clicked.connect(lambda: window.window().close())
        for button in (self.minimise, self.maximise, self.close_button):
            row.addWidget(button)


def toggle_maximised(window) -> None:
    if window.isMaximized():
        window.showNormal()
    else:
        window.showMaximized()


def app_badge(window) -> QLabel:
    """The application's icon at the left of the menu row."""
    from .icons import app_icon
    badge = QLabel(window)
    badge.setObjectName("titleIcon")
    badge.setPixmap(app_icon().pixmap(18, 18))
    badge.setContentsMargins(8, 0, 6, 0)
    badge.setToolTip("CalcForge")
    return badge


class _MovesTheWindow(QObject):
    """The menu row as a title bar: drag where there is no menu, double-click."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind not in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick):
            return False
        if event.button() != Qt.LeftButton:
            return False
        bar = self.window.menuBar()
        if watched is bar and bar.actionAt(event.position().toPoint()) is not None:
            return False                             # a menu: it opens
        top = self.window.window()
        if kind == QEvent.MouseButtonDblClick:
            toggle_maximised(top)
            return True
        handle = top.windowHandle()
        if handle is not None:
            handle.startSystemMove()
            return True
        return False


def _edges_at(window, pos) -> Qt.Edges:
    if window.isMaximized() or window.isFullScreen():
        return Qt.Edges()
    edges = Qt.Edges()
    rect = window.rect()
    if pos.x() <= EDGE:
        edges |= Qt.LeftEdge
    if pos.x() >= rect.width() - EDGE:
        edges |= Qt.RightEdge
    if pos.y() <= EDGE:
        edges |= Qt.TopEdge
    if pos.y() >= rect.height() - EDGE:
        edges |= Qt.BottomEdge
    return edges


def _key(edges) -> int:
    return int(getattr(edges, "value", edges))


_CURSORS = {
    _key(Qt.LeftEdge): Qt.SizeHorCursor, _key(Qt.RightEdge): Qt.SizeHorCursor,
    _key(Qt.TopEdge): Qt.SizeVerCursor, _key(Qt.BottomEdge): Qt.SizeVerCursor,
    _key(Qt.LeftEdge | Qt.TopEdge): Qt.SizeFDiagCursor,
    _key(Qt.RightEdge | Qt.BottomEdge): Qt.SizeFDiagCursor,
    _key(Qt.RightEdge | Qt.TopEdge): Qt.SizeBDiagCursor,
    _key(Qt.LeftEdge | Qt.BottomEdge): Qt.SizeBDiagCursor,
}


class _ResizesTheWindow(QObject):
    """The window's edges: the pointer shows the way, a drag resizes."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window

    def eventFilter(self, watched, event):
        if watched is not self.window:
            return False
        kind = event.type()
        if kind == QEvent.MouseMove and not event.buttons():
            edges = _edges_at(self.window, event.position().toPoint())
            if _key(edges) in _CURSORS:
                self.window.setCursor(_CURSORS[_key(edges)])
            else:
                self.window.unsetCursor()
            return False
        if kind == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            edges = _edges_at(self.window, event.position().toPoint())
            handle = self.window.windowHandle()
            if _key(edges) and handle is not None:
                handle.startSystemResize(edges)
                return True
        return False


def install(window) -> None:
    """Give *window* (a MainWindow) its own title row."""
    if not OWN_TITLE_BAR:
        return
    window.setWindowFlag(Qt.FramelessWindowHint, True)
    window.setMouseTracking(True)
    bar = window.menuBar()
    bar.setCornerWidget(app_badge(window), Qt.TopLeftCorner)
    corner = bar.cornerWidget(Qt.TopRightCorner)
    if corner is not None and corner.layout() is not None:
        window.window_buttons = WindowButtons(window)
        corner.layout().addWidget(window.window_buttons)
        corner.layout().setContentsMargins(0, 0, 0, 0)
    window._title_mover = _MovesTheWindow(window)
    bar.installEventFilter(window._title_mover)
    for widget in (corner, bar.cornerWidget(Qt.TopLeftCorner)):
        if widget is not None:
            widget.installEventFilter(window._title_mover)
    window._edge_resizer = _ResizesTheWindow(window)
    window.installEventFilter(window._edge_resizer)
    _keep_edges(window)


def _keep_edges(window) -> None:
    """Room round the window for its edges, except when it fills the screen."""
    margin = 0 if window.isMaximized() or window.isFullScreen() else EDGE - 1
    window.setContentsMargins(margin, margin, margin, margin)


def window_state_changed(window) -> None:
    if not OWN_TITLE_BAR or not window.windowFlags() & Qt.FramelessWindowHint:
        return
    _keep_edges(window)
    buttons = getattr(window, "window_buttons", None)
    if buttons is not None:
        buttons.maximise.setToolTip("Restore Down" if window.isMaximized() else "Maximise")
        buttons.maximise.update()
