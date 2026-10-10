"""Small reusable widgets."""
from __future__ import annotations


from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QPen
from PySide6.QtWidgets import (QAbstractScrollArea, QLayout, QAbstractSpinBox, QColorDialog, QComboBox,
                               QGridLayout, QHBoxLayout, QMenu, QSlider,
                               QToolButton, QWidget, QWidgetAction, QSpinBox,
                               QDoubleSpinBox)

from ..items.base import PALETTE
from .icons import colour_icon


def arrow_combo() -> QComboBox:
    """Line endings with the same geometry used on the drawing."""
    from ..items.base import ARROW_HEADS, arrow_path
    combo = QComboBox()
    combo.setIconSize(QSize(42, 20))
    for kind in ARROW_HEADS:
        pixmap = QPixmap(42, 20)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        colour = combo.palette().text().color()
        pen = QPen(colour, 1.3)
        pen.setJoinStyle(Qt.MiterJoin)
        pen.setMiterLimit(8)
        painter.setPen(pen)
        painter.drawLine(QPointF(3, 10), QPointF(31, 10))
        painter.setBrush(colour if kind in ("arrow", "dot", "square", "diamond")
                         else Qt.NoBrush)
        painter.drawPath(arrow_path(QPointF(31, 10), 0, 11, kind))
        painter.end()
        combo.addItem(QIcon(pixmap), kind)
    return combo


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
    """Editable percentage with step buttons (legacy class name)."""

    valueChanged = Signal(float)

    def __init__(self, minimum: int = 0, maximum: int = 100, value: int = 100):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.slider = QSpinBox()
        self.slider.setSuffix(" %")
        self.slider.setKeyboardTracking(False)
        self.slider.setRange(minimum, maximum)
        self.slider.setValue(value)
        layout.addWidget(self.slider, 1)
        self.slider.valueChanged.connect(self._changed)

    def _changed(self, value: int) -> None:
        self.valueChanged.emit(value / 100.0)

    def set_value(self, fraction: float) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(int(round(fraction * 100)))
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
        # A dropdown never changes under the wheel, focused or not: turning
        # the wheel over one cycled through its values without being asked.
        # Its open list still scrolls, since that is a different widget.
        if not isinstance(watched, QComboBox) and watched.hasFocus():
            return False                  # a clicked-into number box keeps it
        # Hand it on to whatever is scrolling underneath.
        parent = watched.parentWidget()
        while parent is not None and not isinstance(parent, QAbstractScrollArea):
            parent = parent.parentWidget()
        if parent is not None:
            from PySide6.QtWidgets import QApplication
            QApplication.sendEvent(parent.viewport(), event)
        event.accept()
        return True


class UnboundedSpin(QDoubleSpinBox):
    """A number box with no practical upper or lower limit.

    Shown compactly (``0.0001``, ``2.5``, ``1e+09``) rather than with a fixed
    number of decimals, and stepped by a tenth of its own size, so the arrows
    are as useful at 0.002 as at 20 000.
    """

    SMALLEST = 1e-12
    LARGEST = 1e15

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDecimals(15)
        self.setRange(self.SMALLEST, self.LARGEST)
        self.setKeyboardTracking(False)

    def textFromValue(self, value: float) -> str:
        return f"{value:.6g}"

    def valueFromText(self, text: str) -> float:
        cleaned = text.replace(self.suffix(), "").replace(",", "").strip()
        try:
            return min(max(float(cleaned), self.SMALLEST), self.LARGEST)
        except ValueError:
            return self.value()

    def validate(self, text: str, position: int):
        from PySide6.QtGui import QValidator
        cleaned = text.replace(self.suffix(), "").replace(",", "").strip()
        if cleaned in ("", ".", "-", "e", "E") or cleaned.lower().endswith(("e", "e-", "e+")):
            return QValidator.Intermediate, text, position
        try:
            return (QValidator.Acceptable if float(cleaned) > 0
                    else QValidator.Intermediate), text, position
        except ValueError:
            return QValidator.Invalid, text, position

    def stepBy(self, steps: int) -> None:
        value = self.value()
        factor = 1.1 ** steps
        self.setValue(min(max(value * factor, self.SMALLEST), self.LARGEST))


def big_pattern_dropdown(combo, closed=QSize(64, 20)) -> None:
    """A line-style or hatch picker whose list shows each pattern large.

    Small swatches of dashes and hatches all look alike, so the open list
    draws every pattern big, with its name beside it, like Bluebeam's.
    """
    from PySide6.QtWidgets import QListView
    view = QListView()
    view.setIconSize(QSize(150, 34))
    view.setSpacing(2)
    view.setUniformItemSizes(True)
    combo.setView(view)
    # The combo's own delegate draws icons at the closed box's small size;
    # this one draws each pattern at full size, with its name.
    view.setItemDelegate(_BigPatternDelegate(view))
    combo.setIconSize(closed)
    combo.setMaxVisibleItems(14)
    combo.setMinimumContentsLength(8)
    view.setMinimumWidth(300)


class _BigPatternDelegate(QStyledItemDelegateBase := __import__(
        "PySide6.QtWidgets", fromlist=["QStyledItemDelegate"]).QStyledItemDelegate):
    """One row of a big pattern list: the pattern 150 × 34, then its name."""

    SWATCH = QSize(150, 34)

    def sizeHint(self, option, index):
        return QSize(self.SWATCH.width() + 160, self.SWATCH.height() + 6)

    def paint(self, painter, option, index):
        from PySide6.QtWidgets import QStyle
        painter.save()
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
            text_colour = option.palette.highlightedText().color()
        else:
            if option.state & QStyle.State_MouseOver:
                painter.fillRect(option.rect, option.palette.alternateBase())
            text_colour = option.palette.text().color()
        swatch = option.rect.adjusted(6, 3, 0, -3)
        swatch.setWidth(self.SWATCH.width())
        # the list's own background: the samples are drawn in the theme's ink
        painter.fillRect(swatch, option.palette.base())
        icon = index.data(Qt.DecorationRole)
        if icon is not None:
            icon.paint(painter, swatch)
        painter.setPen(text_colour)
        words = option.rect.adjusted(self.SWATCH.width() + 16, 0, -4, 0)
        painter.drawText(words, Qt.AlignVCenter | Qt.AlignLeft,
                         str(index.data(Qt.DisplayRole) or ""))
        painter.restore()


class FlowLayout(QLayout):
    """A row of widgets that wraps onto more rows when the panel is narrow
    (Qt's own flow-layout example): buttons and options stay whole, however
    thin the panel is dragged."""

    def __init__(self, parent=None, spacing: int = 4):
        super().__init__(parent)
        self._items: list = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(spacing)

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._arrange(QRect(0, 0, width, 0), move=False)

    def setGeometry(self, rect) -> None:
        super().setGeometry(rect)
        self._arrange(rect, move=True)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        left, top, right, bottom = self.getContentsMargins()
        return size + QSize(left + right, top + bottom)

    def _arrange(self, rect, move: bool) -> int:
        left, top, right, bottom = self.getContentsMargins()
        area = rect.adjusted(left, top, -right, -bottom)
        x, y, line = area.x(), area.y(), 0
        gap = self.spacing()
        for item in self._items:
            if item.widget() is not None and not item.widget().isVisible() \
                    and item.widget().isHidden():
                continue
            hint = item.sizeHint()
            if x + hint.width() > area.right() + 1 and line > 0:
                x, y, line = area.x(), y + line + gap, 0
            if move:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + gap
            line = max(line, hint.height())
        return y + line - rect.y() + bottom


class ModeSwitch(QWidget):
    """Markup | Calc — the two modes side by side, the one on lit up.

    What typing on the page does depends on it, so it is where it can be
    seen at a glance rather than a word in the status bar. Speaks the little
    a checkable button does (isChecked/setChecked = Calc), so the window
    keeps one way to set it.
    """

    toggled = Signal(bool)

    def __init__(self, parent=None):
        from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QToolButton
        super().__init__(parent)
        self.setObjectName("modeSwitch")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 6, 0)
        lay.setSpacing(0)
        self.markup = QToolButton()
        self.markup.setText("Markup")
        self.markup.setObjectName("modeMarkup")
        self.markup.setToolTip("Markup mode: the markup tools' keys (F12 switches)")
        self.calc = QToolButton()
        self.calc.setText("Calc")
        self.calc.setObjectName("modeCalc")
        self.calc.setToolTip("Calc mode: typing on the page starts an equation, "
                             "as in SMath (F12 switches)")
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for button in (self.markup, self.calc):
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setFocusPolicy(Qt.NoFocus)
            button.setMinimumWidth(64)
            self._group.addButton(button)
            lay.addWidget(button)
        self.markup.setChecked(True)
        self.calc.toggled.connect(self.toggled.emit)

    # -- what a checkable button would say -----------------------------------------
    def isChecked(self) -> bool:
        return self.calc.isChecked()

    def setChecked(self, on: bool) -> None:
        (self.calc if on else self.markup).setChecked(True)

    def text(self) -> str:
        return "Calc" if self.calc.isChecked() else "Markup"

    def setText(self, _text: str) -> None:
        pass                                   # each side has its own word


class PatternCombo(QComboBox):
    """A line-style or hatch picker that shows, closed, only the sample —
    filling the box, no name and no room left over beside it, as Bluebeam's
    do (the user, 2026-10-01: "padding on the right of the word"). The name
    is the tooltip, and the open list shows every pattern big with its name."""

    SAMPLE_WIDTH = 72

    def __init__(self, parent=None):
        super().__init__(parent)
        self.currentIndexChanged.connect(lambda _i: self.setToolTip(self.currentText()))

    def sizeHint(self):
        from PySide6.QtWidgets import QStyle, QStyleOptionComboBox
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        arrow = self.style().subControlRect(QStyle.CC_ComboBox, option,
                                            QStyle.SC_ComboBoxArrow, self).width()
        return QSize(self.SAMPLE_WIDTH + max(arrow, 16) + 14, super().sizeHint().height())

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, event) -> None:
        from PySide6.QtWidgets import QStyle, QStyleOptionComboBox, QStylePainter
        painter = QStylePainter(self)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        icon = self.itemIcon(self.currentIndex()) if self.currentIndex() >= 0 else QIcon()
        option.currentText = ""
        option.currentIcon = QIcon()
        painter.drawComplexControl(QStyle.CC_ComboBox, option)
        field = self.style().subControlRect(QStyle.CC_ComboBox, option,
                                            QStyle.SC_ComboBoxEditField, self)
        field = field.adjusted(4, 3, -2, -3)
        if not icon.isNull() and field.width() > 4 and field.height() > 4:
            # the sample's middle, at its own scale, across the whole field
            picture = icon.pixmap(QSize(150, 34))
            ratio = picture.devicePixelRatio() or 1.0
            wide, high = picture.width() / ratio, picture.height() / ratio
            take = min(wide, field.width() * high / max(field.height(), 1))
            source = QRect(int((wide - take) / 2 * ratio), 0, int(take * ratio), picture.height())
            painter.drawPixmap(field, picture, source)
