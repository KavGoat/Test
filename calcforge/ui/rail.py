"""The strips of panel icons down either edge of the window.

Bluebeam puts every panel behind one narrow column of icons: pages,
bookmarks, tool chest, and the rest. Clicking an icon opens that panel;
clicking it again closes it; and dragging an icon from one edge to the other
moves the panel to that side. Nothing is hidden in a menu three levels down,
and nothing takes up room until it is asked for.

This does the same. The panels themselves are ordinary docks — they can still
be floated, pinned and rolled up — but which ones are open, and on which side,
is decided here.
"""
from __future__ import annotations

from PySide6.QtCore import QMimeData, QPoint, QSettings, Qt, Signal
from PySide6.QtGui import QDrag, QPainter, QPen, QColor
from PySide6.QtWidgets import (QSizePolicy, QToolBar, QToolButton, QVBoxLayout,
                               QWidget)

SIDES_KEY = "panels/sides"
MIME = "application/x-calcforge-panel"

LEFT = "left"
RIGHT = "right"

AREAS = {LEFT: Qt.LeftDockWidgetArea, RIGHT: Qt.RightDockWidgetArea}


class RailButton(QToolButton):
    """One panel's icon, which can be dragged to the other side."""

    def __init__(self, name: str, label: str, icon, rail: "PanelRail"):
        super().__init__(rail)
        self.panel_name = name
        self.rail = rail
        self.setObjectName("railButton")
        self.setIcon(icon)
        self.setToolTip(label)
        self.setCheckable(True)
        self.setAutoRaise(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedSize(30, 30)
        self._press: QPoint | None = None

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._press = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """Far enough from where it was pressed, this becomes a drag."""
        if self._press is None or not (event.buttons() & Qt.LeftButton):
            super().mouseMoveEvent(event)
            return
        if (event.pos() - self._press).manhattanLength() < 12:
            super().mouseMoveEvent(event)
            return
        data = QMimeData()
        data.setData(MIME, self.panel_name.encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(data)
        drag.setPixmap(self.icon().pixmap(24, 24))
        self._press = None
        self.setDown(False)
        drag.exec(Qt.MoveAction)


class PanelRail(QWidget):
    """A column of panel icons down one edge of the window."""

    toggled = Signal(str, bool)          # panel name, wanted open
    moved = Signal(str, str)             # panel name, side it was dropped on

    def __init__(self, side: str, parent=None):
        super().__init__(parent)
        self.side = side
        self.setObjectName("panelRail")
        self.setAcceptDrops(True)
        self.setFixedWidth(36)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 6, 3, 6)
        layout.setSpacing(2)
        layout.addStretch(1)
        self._layout = layout
        self.buttons: dict[str, RailButton] = {}
        self._highlight = False

    def add(self, name: str, label: str, icon) -> RailButton:
        button = RailButton(name, label, icon, self)
        button.clicked.connect(
            lambda checked, key=name: self.toggled.emit(key, checked))
        self._layout.insertWidget(self._layout.count() - 1, button)
        self.buttons[name] = button
        return button

    def take(self, name: str) -> None:
        button = self.buttons.pop(name, None)
        if button is not None:
            self._layout.removeWidget(button)
            button.setParent(None)
            button.deleteLater()

    def show_open(self, name: str, open_now: bool) -> None:
        button = self.buttons.get(name)
        if button is not None and button.isChecked() != open_now:
            button.blockSignals(True)
            button.setChecked(open_now)
            button.blockSignals(False)

    # -- taking a panel from the other side --------------------------------
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(MIME):
            event.acceptProposedAction()
            self._highlight = True
            self.update()

    def dragLeaveEvent(self, event) -> None:
        self._highlight = False
        self.update()

    def dropEvent(self, event) -> None:
        self._highlight = False
        self.update()
        if not event.mimeData().hasFormat(MIME):
            return
        name = bytes(event.mimeData().data(MIME)).decode("utf-8")
        event.acceptProposedAction()
        self.moved.emit(name, self.side)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self._highlight:
            return
        painter = QPainter(self)
        pen = QPen(QColor("#1971c2"))
        pen.setWidthF(2.0)
        painter.setPen(pen)
        painter.drawRect(self.rect().adjusted(1, 1, -2, -2))


class RailBar(QToolBar):
    """The toolbar that carries a rail, so it sits at the window's own edge.

    Docks live inside the toolbar areas, so a rail put in the middle of the
    window would end up between the panels and the page rather than hard
    against the frame — which is not where Bluebeam's is, and not where the
    hand goes looking for it.
    """

    def __init__(self, rail: PanelRail, parent=None):
        super().__init__(parent)
        self.setObjectName(f"rail_{rail.side}")
        self.setMovable(False)
        self.setFloatable(False)
        self.setContentsMargins(0, 0, 0, 0)
        self.addWidget(rail)
        self.rail = rail


def load_sides(default: dict[str, str]) -> dict[str, str]:
    """Which side each panel was last on."""
    settings = QSettings("CalcForge", "CalcForge")
    stored = settings.value(SIDES_KEY, None)
    sides = dict(default)
    if isinstance(stored, dict):
        for name, side in stored.items():
            if name in sides and side in (LEFT, RIGHT):
                sides[name] = side
    return sides


def save_sides(sides: dict[str, str]) -> None:
    QSettings("CalcForge", "CalcForge").setValue(SIDES_KEY, dict(sides))
