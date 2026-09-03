"""Dock panels with a title bar you can actually use.

Qt's own dock title bar gives you float and close. An engineer working in one
arrangement all day wants a third thing: to pin a panel where it is, so a
stray drag cannot tear it off the side of the window. That is what this adds,
along with a layout that is remembered between sessions.
"""
from __future__ import annotations

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtGui import QIcon, QPainter, QPen, QPixmap, QColor, QPolygonF
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtWidgets import (QDockWidget, QHBoxLayout, QLabel, QSizePolicy,
                               QToolButton, QWidget)

PINNED_KEY = "panels/pinned"
COLLAPSED_KEY = "panels/collapsed"


def _icon(name: str, size: int = 14) -> QIcon:
    """Small monochrome glyphs for the title-bar buttons, in the theme's ink."""
    from .icons import INK

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
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
    painter.end()
    return QIcon(pixmap)


class DockTitleBar(QWidget):
    """Title, pin, float and close — in that order, like every other tool."""

    def __init__(self, dock: "PanelDock"):
        super().__init__(dock)
        self.dock = dock
        self.setObjectName("dockTitleBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(9, 3, 4, 3)
        layout.setSpacing(2)

        self.label = QLabel(dock.windowTitle())
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
        self.float_button.clicked.connect(
            lambda: dock.setFloating(not dock.isFloating()))
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
        return button

    def refresh_icons(self) -> None:
        """Redraw the buttons after a theme change."""
        self.float_button.setIcon(_icon("float"))
        self.close_button.setIcon(_icon("close"))
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


class PanelDock(QDockWidget):
    """A dock that can be pinned in place, hidden, and put back."""

    pinnedChanged = Signal(bool)
    collapsedChanged = Signal(bool)

    def __init__(self, title: str, widget: QWidget, name: str, parent=None):
        super().__init__(title, parent)
        self.setObjectName(name)
        self.setWidget(widget)
        self.setAllowedAreas(Qt.AllDockWidgetAreas)
        self._pinned = False
        self._collapsed = False
        self._restore_size = None
        # No floor of its own: the splitter can squeeze it away to nothing and
        # the reader can drag it back.
        widget.setMinimumSize(0, 0)
        self.setMinimumSize(0, 0)
        self._bar = DockTitleBar(self)
        self.setTitleBarWidget(self._bar)
        self.set_pinned(False)

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

    def toggle_pinned(self) -> None:
        self.set_pinned(not self._pinned)

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
    settings = QSettings("CalcForge", "CalcForge")
    settings.setValue(PINNED_KEY,
                      [dock.objectName() for dock in docks if dock.pinned])
    settings.setValue(COLLAPSED_KEY,
                      [dock.objectName() for dock in docks if dock.collapsed])


def load_panel_state(docks: list[PanelDock]) -> None:
    settings = QSettings("CalcForge", "CalcForge")
    pinned = _names(settings.value(PINNED_KEY, []))
    collapsed = _names(settings.value(COLLAPSED_KEY, []))
    for dock in docks:
        dock.set_pinned(dock.objectName() in pinned)
        dock.set_collapsed(dock.objectName() in collapsed)
