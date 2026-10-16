"""Small reusable widgets."""
from __future__ import annotations


import shiboken6
from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen
from PySide6.QtWidgets import (QAbstractScrollArea, QLayout, QAbstractSpinBox, QComboBox,
                               QHBoxLayout, QSlider,
                               QToolButton, QWidget, QDoubleSpinBox)

from .icons import colour_icon, drawn_icon


def arrow_combo() -> QComboBox:
    """Line ends as Bluebeam lists them (None, Open, Closed, …), each drawn
    with the same geometry used on the drawing; the item's data is its key."""
    from ..items.base import ARROW_HEADS, ARROW_NAMES, FILLED_HEADS, arrow_path
    combo = QComboBox()
    combo.setIconSize(QSize(42, 20))
    for kind in ARROW_HEADS:
        def draw(painter: QPainter, kind=kind) -> None:
            painter.setRenderHint(QPainter.Antialiasing)
            colour = combo.palette().text().color()
            pen = QPen(colour, 1.3)
            pen.setJoinStyle(Qt.MiterJoin)
            pen.setMiterLimit(8)
            painter.setPen(pen)
            painter.drawLine(QPointF(3, 10), QPointF(31, 10))
            painter.setBrush(colour if kind in FILLED_HEADS else Qt.NoBrush)
            painter.drawPath(arrow_path(QPointF(31, 10), 0, 11, kind))
        combo.addItem(drawn_icon(draw, 42, 20), ARROW_NAMES.get(kind, kind), kind)
    return combo


def set_arrow(combo: QComboBox, kind: str) -> None:
    """Show line end *kind* in an arrow_combo, without saying it changed."""
    combo.blockSignals(True)
    combo.setCurrentIndex(max(combo.findData(kind or "none"), 0))
    combo.blockSignals(False)


class ColorButton(QToolButton):
    """A swatch button opening Revu's colour picker: its palette, No Color,
    the eyedropper and More Colors (ui/colorpicker.py)."""

    colorChanged = Signal(str)

    def __init__(self, colour: str = "#e03131", allow_none: bool = False,
                 label: str = ""):
        super().__init__()
        self._colour = colour
        self.allow_none = allow_none
        self.setToolTip(label or "Colour")
        self.setAutoRaise(True)
        self.setIconSize(QSize(18, 18))
        self.clicked.connect(self._pick)
        self._refresh()

    def _pick(self) -> None:
        """Revu's colour picker under the swatch (ui/colorpicker.py)."""
        from .colorpicker import choose
        got = choose(self, self._colour, self.allow_none)
        if got is None or not shiboken6.isValid(self):
            return                 # left, or this button went while it was open
        self.set_color(got)
        self.colorChanged.emit(self._colour)

    def color(self) -> str:
        return self._colour

    def set_color(self, colour: str) -> None:
        self._colour = colour or ""
        self._refresh()

    def _refresh(self) -> None:
        if not self._colour:
            def draw(painter: QPainter) -> None:
                painter.setPen(QColor(160, 165, 175))
                painter.drawRect(1, 1, 15, 15)
                painter.setPen(QColor(200, 60, 60))
                painter.drawLine(2, 15, 15, 2)
            self.setIcon(drawn_icon(draw, 18, 18))
        else:
            self.setIcon(colour_icon(self._colour))


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


#: The object names of the places where the wheel never changes a value.
PROPERTIES = ("propertiesPanel", "toolbar_style")


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

    @staticmethod
    def _in_properties(widget) -> bool:
        parent = widget.parentWidget()
        while parent is not None:
            if parent.objectName() in PROPERTIES or type(parent).__name__ == "PropertiesPanel":
                return True
            parent = parent.parentWidget()
        return False

    def eventFilter(self, watched, event):
        if event.type() != QEvent.Wheel or not isinstance(watched, self.WATCHED):
            return False
        # A dropdown never changes under the wheel, focused or not: turning
        # the wheel over one cycled through its values without being asked.
        # Its open list still scrolls, since that is a different widget.
        # In the Properties panel and on the Properties toolbar not even a
        # clicked-into box takes it: a size, a rotation or an opacity changed
        # as the panel was scrolled past (the user, 2026-10-15)
        if not isinstance(watched, QComboBox) and watched.hasFocus() \
                and not self._in_properties(watched):
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
        # Revu's list: the name at the left, the pattern drawn at the right
        swatch = option.rect.adjusted(0, 3, -8, -3)
        swatch.setLeft(swatch.right() - self.SWATCH.width())
        icon = index.data(Qt.DecorationRole)
        if icon is not None:
            # the list's own background: the samples are drawn in the theme's ink
            painter.fillRect(swatch, option.palette.base())
            icon.paint(painter, swatch)
        painter.setPen(text_colour)
        words = option.rect.adjusted(12, 0, -(self.SWATCH.width() + 16), 0)
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
        from PySide6.QtWidgets import QButtonGroup, QToolButton
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
        if self.property("blankNone") and not self.currentData():
            icon = QIcon()                     # Revu's: an empty box for no hatch
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


def page_ranges(indexes) -> str:
    """[0, 1, 2, 4] as "1-3, 5"."""
    parts, run = [], []
    for index in sorted(set(indexes)):
        if run and index == run[-1] + 1:
            run.append(index)
            continue
        if run:
            parts.append(str(run[0] + 1) if len(run) == 1 else f"{run[0] + 1}-{run[-1] + 1}")
        run = [index]
    if run:
        parts.append(str(run[0] + 1) if len(run) == 1 else f"{run[0] + 1}-{run[-1] + 1}")
    return ", ".join(parts)


class PagesRange(QWidget):
    """Revu's Pages, shared by every dialog that has one (Set Scale, Flatten
    Markups, Delete, Extract and Crop Pages): All Pages, Current (n), Selected
    — only when pages are picked in Thumbnails — or Custom, with the range in
    a box beside it ("1-3, 5, 9"); typing into the box makes it Custom (the
    user, 2026-10-15). Read with the same parser as Colour Processing."""

    ALL, CURRENT, SELECTED, CUSTOM = "all", "current", "selected", "custom"

    def __init__(self, count: int, current: int = 0, selected=None,
                 default: str = CURRENT, parent=None):
        from PySide6.QtWidgets import QLineEdit
        super().__init__(parent)
        self.count = max(int(count), 1)
        self.current = min(max(int(current), 0), self.count - 1)
        self.selected = sorted(selected or [])
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.combo = QComboBox()
        self.combo.setObjectName("pagesChoice")
        self.combo.addItem("All Pages", self.ALL)
        self.combo.addItem(f"Current ({self.current + 1})", self.CURRENT)
        if self.selected:
            self.combo.addItem("Selected", self.SELECTED)
        self.combo.addItem("Custom", self.CUSTOM)
        self.range = QLineEdit()
        self.range.setObjectName("pagesRange")
        self.range.setPlaceholderText("1-3, 5")
        self.range.setToolTip("Pages and ranges, e.g. 1-3, 5, 9")
        row.addWidget(self.combo, 1)
        row.addWidget(self.range, 1)
        self.combo.currentIndexChanged.connect(self._fill)
        self.range.textEdited.connect(self._typed)
        self.choose(default)

    def which(self) -> str:
        return self.combo.currentData()

    def choose(self, which: str, text=None) -> None:
        """Pick All, Current, Selected or Custom (with *text* as its range).
        Selected falls back to Current when nothing is picked in Thumbnails."""
        index = self.combo.findData(which)
        self.combo.setCurrentIndex(index if index >= 0 else self.combo.findData(self.CURRENT))
        self._fill()
        if text is not None:
            self.range.setText(text)

    def set_custom(self, text: str) -> None:
        self.choose(self.CUSTOM, text)

    def _fill(self, *_args) -> None:
        which = self.which()
        if which == self.ALL:
            self.range.setText("1" if self.count == 1 else f"1-{self.count}")
        elif which == self.CURRENT:
            self.range.setText(str(self.current + 1))
        elif which == self.SELECTED:
            self.range.setText(page_ranges(self.selected))

    def _typed(self, _text: str) -> None:
        if self.which() != self.CUSTOM:
            was = self.combo.blockSignals(True)
            self.combo.setCurrentIndex(self.combo.findData(self.CUSTOM))
            self.combo.blockSignals(was)

    def page_indexes(self):
        """The chosen pages, from 0; None when the Custom range will not read."""
        which = self.which()
        if which == self.ALL:
            return list(range(self.count))
        if which == self.CURRENT:
            return [self.current]
        if which == self.SELECTED:
            return list(self.selected)
        from .colorprocess import parse_pages
        return parse_pages(self.range.text(), self.count)

    def pages(self) -> list:
        """The chosen pages, from 0; empty when the Custom range will not read."""
        return self.page_indexes() or []
