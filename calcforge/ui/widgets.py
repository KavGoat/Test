"""Small reusable widgets."""
from __future__ import annotations


from PySide6.QtCore import QEvent, QObject, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractSpinBox, QColorDialog, QComboBox,
                               QGridLayout, QHBoxLayout, QLabel, QMenu, QSlider,
                               QToolButton, QWidget, QWidgetAction)

from ..items.base import PALETTE
from .icons import colour_icon


class ColorButton(QToolButton):
    """A swatch button with a palette pop-up and a 'more colours' escape hatch."""

    colorChanged = Signal(str)

    def __init__(self, colour: str = "#e03131", allow_none: bool = False,
                 label: str = ""):
        super().__init__()
        self._colour = colour
        self.allow_none = allow_none
        self.setPopupMode(QToolButton.InstantPopup)
        self.setToolTip(label or "Colour")
        self.setAutoRaise(True)
        self.setIconSize(QSize(18, 18))
        self._build_menu()
        self._refresh()

    def _build_menu(self) -> None:
        menu = QMenu(self)
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setContentsMargins(6, 6, 6, 6)
        grid.setSpacing(3)
        for index, colour in enumerate(PALETTE):
            button = QToolButton()
            button.setIcon(colour_icon(colour))
            button.setIconSize(QSize(18, 18))
            button.setAutoRaise(True)
            button.setToolTip(colour)
            button.clicked.connect(lambda _checked=False, c=colour: self._choose(c, menu))
            grid.addWidget(button, index // 6, index % 6)
        action = QWidgetAction(menu)
        action.setDefaultWidget(grid_widget)
        menu.addAction(action)
        menu.addSeparator()
        if self.allow_none:
            menu.addAction("No colour", lambda: self._choose("", menu))
        menu.addAction("More colours…", self._pick_custom)
        self.setMenu(menu)

    def _choose(self, colour: str, menu: QMenu) -> None:
        menu.hide()
        self.set_color(colour)
        self.colorChanged.emit(colour)

    def _pick_custom(self) -> None:
        chosen = QColorDialog.getColor(QColor(self._colour or "#ffffff"), self,
                                       "Choose a colour")
        if chosen.isValid():
            self.set_color(chosen.name())
            self.colorChanged.emit(self._colour)

    def color(self) -> str:
        return self._colour

    def set_color(self, colour: str) -> None:
        self._colour = colour or ""
        self._refresh()

    def _refresh(self) -> None:
        if not self._colour:
            pixmap = QPixmap(18, 18)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setPen(QColor(160, 165, 175))
            painter.drawRect(1, 1, 15, 15)
            painter.setPen(QColor(200, 60, 60))
            painter.drawLine(2, 15, 15, 2)
            painter.end()
            self.setIcon(QIcon(pixmap))
        else:
            self.setIcon(colour_icon(self._colour))


class LabeledSlider(QWidget):
    """A slider with a percentage read-out, used for opacity."""

    valueChanged = Signal(float)

    def __init__(self, minimum: int = 0, maximum: int = 100, value: int = 100):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(minimum, maximum)
        self.slider.setValue(value)
        self.readout = QLabel(f"{value}%")
        self.readout.setMinimumWidth(34)
        self.readout.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.readout)
        self.slider.valueChanged.connect(self._changed)

    def _changed(self, value: int) -> None:
        self.readout.setText(f"{value}%")
        self.valueChanged.emit(value / 100.0)

    def set_value(self, fraction: float) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(int(round(fraction * 100)))
        self.readout.setText(f"{int(round(fraction * 100))}%")
        self.slider.blockSignals(False)


class UnitCombo(QComboBox):
    """Editable unit picker grouped by physical quantity."""

    def __init__(self, value: str = ""):
        super().__init__()
        from ..core.units import UNIT_MENU
        self.setEditable(True)
        self.addItem("")
        for group, units in UNIT_MENU.items():
            self.insertSeparator(self.count())
            for unit in units:
                self.addItem(unit)
        self.setCurrentText(value)
        self.setMinimumContentsLength(8)


def keep_the_wheel_with_the_scroller(application) -> None:
    """Install the filter below on *application*, once.

    Called from the window rather than from start-up, so it is in force
    however the application came to exist — including under a test harness
    that builds its own.
    """
    if getattr(application, "_wheel_filter", None) is not None:
        return
    application._wheel_filter = WheelBelongsToTheScroller(application)
    application.installEventFilter(application._wheel_filter)


class WheelBelongsToTheScroller(QObject):
    """Stop a dropdown or a spinner eating the wheel while a panel is scrolled.

    Rolling down the properties panel with the pointer happening to pass over
    a font box used to change the font. Nobody means that. Qt's own rule is
    the right one and it is only a line: a combo, a spinner or a slider takes
    the wheel when it has been clicked into, and passes it up to whatever is
    scrolling when it has not.

    Installed once, on the application, so every one of them behaves the same
    and no new one has to remember.
    """

    WATCHED = (QComboBox, QAbstractSpinBox, QSlider)

    def eventFilter(self, watched, event):
        if event.type() != QEvent.Wheel or not isinstance(watched, self.WATCHED):
            return False
        if watched.hasFocus():
            return False                  # clicked into: the wheel is its own
        # Not focused: hand it on. The scroll area above it will take it.
        event.ignore()
        return True
