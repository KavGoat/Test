"""Small reusable widgets."""
from __future__ import annotations


import shiboken6
from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QAbstractScrollArea, QLayout, QAbstractSpinBox, QComboBox,
                               QHBoxLayout, QSlider, QStyledItemDelegate,
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
        combo.setItemData(combo.count() - 1, ARROW_NAMES.get(kind, kind), Qt.ToolTipRole)
    checked_list(combo, pictures=True, picture=QSize(42, 20))
    return combo


# ---------------------------------------------------------------------------
# lists as Revu's: a tick on what is picked, nothing cut short
# ---------------------------------------------------------------------------
#: The width of the tick's column at the left of every list (Revu's ✓).
CHECK_COLUMN = 22


def _paint_row_background(painter, option) -> QColor:
    """A list row's ground — the picked or hovered row lit — and the colour
    its words are written in."""
    from PySide6.QtWidgets import QStyle
    if option.state & QStyle.State_Selected:
        painter.fillRect(option.rect, option.palette.highlight())
        return option.palette.highlightedText().color()
    if option.state & QStyle.State_MouseOver:
        painter.fillRect(option.rect, option.palette.alternateBase())
    return option.palette.text().color()


def _paint_tick(painter, option, colour: QColor) -> None:
    """Revu's ✓ in the left column, on the entry that is the current one."""
    pen = QPen(colour, 1.5)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setRenderHint(QPainter.Antialiasing, True)
    middle = option.rect.center().y()
    left = option.rect.left() + 7
    painter.drawPolyline(QPolygonF([QPointF(left, middle), QPointF(left + 3, middle + 3),
                                    QPointF(left + 9, middle - 4)]))


def is_current(combo, index) -> bool:
    """Whether the list row is the combo's own current entry (the one ticked)."""
    return combo is not None and index.row() == combo.currentIndex()


class CheckedListDelegate(QStyledItemDelegate):
    """One row of a short Revu list: the ✓ on the current entry, then its
    picture alone (*pictures*, the line ends — the name is the tooltip) or
    its words (the sizes, Auto…400%), each row as wide as it needs."""

    def __init__(self, combo, pictures: bool = False, picture: QSize = QSize(42, 20)):
        super().__init__(combo)
        self.combo = combo
        self.pictures = pictures
        self.picture = QSize(picture)

    def _words(self, index) -> str:
        return str(index.data(Qt.DisplayRole) or "")

    def row_width(self, option, index) -> int:
        icon = index.data(Qt.DecorationRole)
        has_icon = isinstance(icon, QIcon) and not icon.isNull()
        if self.pictures:
            return CHECK_COLUMN + self.picture.width() + 14
        width = CHECK_COLUMN + option.fontMetrics.horizontalAdvance(self._words(index)) + 18
        if has_icon:
            width += self.combo.iconSize().width() + 6
        return width

    def sizeHint(self, option, index):
        if index.data(Qt.AccessibleDescriptionRole) == "separator":
            return QSize(10, 7)
        high = max(option.fontMetrics.height() + 8, 22)
        if self.pictures:
            high = max(high, self.picture.height() + 6)
        else:
            icon = index.data(Qt.DecorationRole)
            if isinstance(icon, QIcon) and not icon.isNull():
                high = max(high, self.combo.iconSize().height() + 6)
        return QSize(self.row_width(option, index), high)

    def paint(self, painter, option, index):
        if index.data(Qt.AccessibleDescriptionRole) == "separator":
            painter.save()
            painter.setPen(option.palette.mid().color())
            y = option.rect.center().y()
            painter.drawLine(option.rect.left() + 4, y, option.rect.right() - 4, y)
            painter.restore()
            return
        painter.save()
        ink = _paint_row_background(painter, option)
        if is_current(self.combo, index):
            _paint_tick(painter, option, ink)
        icon = index.data(Qt.DecorationRole)
        x = option.rect.left() + CHECK_COLUMN
        if isinstance(icon, QIcon) and not icon.isNull():
            size = self.picture if self.pictures else self.combo.iconSize()
            top = option.rect.top() + (option.rect.height() - size.height()) // 2
            icon.paint(painter, QRect(x, top, size.width(), size.height()))
            x += size.width() + 6
        if not self.pictures:
            painter.setPen(ink)
            painter.drawText(QRect(x, option.rect.top(), option.rect.right() - x,
                                   option.rect.height()),
                             Qt.AlignVCenter | Qt.AlignLeft, self._words(index))
        painter.restore()


def checked_list(combo, pictures: bool = False, picture: QSize = QSize(42, 20)) -> None:
    """Give *combo*'s open list Revu's look: a ✓ on the current entry, and
    pictures only when *pictures* (the names then their tooltips)."""
    combo.setItemDelegate(CheckedListDelegate(combo, pictures, picture))
    for index in range(combo.count()):
        if combo.itemData(index, Qt.ToolTipRole) is None and combo.itemText(index):
            combo.setItemData(index, combo.itemText(index), Qt.ToolTipRole)


def fit_the_list(combo) -> None:
    """The open list as wide as its widest row — nothing cut short (the
    user's Revu: "Long Dash Dot Dot" whole) — and never narrower than the box."""
    from PySide6.QtWidgets import QStyleOptionViewItem
    view = combo.view()
    delegate = view.itemDelegate()
    option = QStyleOptionViewItem()
    option.initFrom(view)
    option.font = view.font()
    option.fontMetrics = view.fontMetrics()
    model = combo.model()
    widest = 0
    for row in range(combo.count()):
        index = model.index(row, combo.modelColumn())
        widest = max(widest, delegate.sizeHint(option, index).width())
    bar = view.verticalScrollBar().sizeHint().width() \
        if combo.count() > combo.maxVisibleItems() else 0
    frame = 2 * view.frameWidth() + 2 * view.spacing() + 4
    view.setMinimumWidth(max(widest + bar + frame, combo.width()))


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


def shown_unit(unit: str) -> str:
    """A unit as a person reads it: m², kN·m — never m^2 or kN*m."""
    return (unit or "").replace("^2", "²").replace("^3", "³").replace("*", "·")


def typed_unit(text: str) -> str:
    """What was picked or typed in a unit box, in the form units are kept in."""
    return (text or "").strip().replace("²", "^2").replace("³", "^3").replace("·", "*")


class UnitCombo(QComboBox):
    """Editable unit picker grouped by physical quantity.

    It shows units as they are written — m², m³, kN·m — the way the values
    beside them read (novice finding 26: "m^2" beside "149.34 m²"), and
    hands back the form they are kept in: ``currentText()`` and
    :attr:`unitChanged` give "m^2"."""

    unitChanged = Signal(str)

    def __init__(self, value: str = ""):
        super().__init__()
        from ..core.units import UNIT_MENU
        self.setEditable(True)
        self.addItem("")
        for group, units in UNIT_MENU.items():
            self.insertSeparator(self.count())
            for unit in units:
                self.addItem(shown_unit(unit))
        self.setCurrentText(value)
        self.setMinimumContentsLength(8)
        self.currentTextChanged.connect(
            lambda text: self.unitChanged.emit(typed_unit(text)))

    def currentText(self) -> str:                      # noqa: N802 (Qt's name)
        return typed_unit(super().currentText())

    def shownText(self) -> str:                         # noqa: N802
        """What the box shows: m²."""
        return super().currentText()

    def setCurrentText(self, text: str) -> None:       # noqa: N802 (Qt's name)
        super().setCurrentText(shown_unit(text))


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


#: Looked up once: the wheel filter sees every event the application has.
_WHEEL = QEvent.Wheel

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
        if event.type() != _WHEEL or not isinstance(watched, self.WATCHED):
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
    # not uniform: each row as wide as its own name (a uniform size took
    # the first's, Manage…, and cut the long names short), and the line
    # under Manage… a thin row, as Revu's is
    view.setUniformItemSizes(False)
    combo.setView(view)
    # The combo's own delegate draws icons at the closed box's small size;
    # this one draws each pattern at full size, with its name, and ticks the
    # one the markup has.
    view.setItemDelegate(_BigPatternDelegate(view, combo))
    combo.setIconSize(closed)
    combo.setMaxVisibleItems(14)
    combo.setMinimumContentsLength(8)
    view.setMinimumWidth(300)


def fit_pattern_list(combo) -> None:
    """Widen a big pattern list's open list to its longest name, so no name
    is cut short ("Long Dash Dot Do…" was)."""
    if isinstance(combo.view().itemDelegate(), _BigPatternDelegate):
        fit_the_list(combo)


class _BigPatternDelegate(QStyledItemDelegate):
    """One row of a big pattern list: the pattern 150 × 34, then its name."""

    SWATCH = QSize(150, 34)
    #: the words start after Revu's ✓ column
    WORDS = CHECK_COLUMN + 6

    def __init__(self, view, combo=None):
        super().__init__(view)
        self.combo = combo

    def sizeHint(self, option, index):
        if index.data(Qt.AccessibleDescriptionRole) == "separator":
            return QSize(10, 7)
        # as wide as its own name needs (the user's Revu shows "Long Dash
        # Dot Dot" whole), and at least as wide as it always was
        words = option.fontMetrics.horizontalAdvance(str(index.data(Qt.DisplayRole) or ""))
        wide = max(self.SWATCH.width() + 160, self.WORDS + words + 20 + self.SWATCH.width() + 8)
        return QSize(wide, self.SWATCH.height() + 6)

    def paint(self, painter, option, index):
        if index.data(Qt.AccessibleDescriptionRole) == "separator":
            painter.save()
            painter.setPen(option.palette.mid().color())
            y = option.rect.center().y()
            painter.drawLine(option.rect.left() + 4, y, option.rect.right() - 4, y)
            painter.restore()
            return
        painter.save()
        text_colour = _paint_row_background(painter, option)
        if is_current(self.combo, index):
            _paint_tick(painter, option, text_colour)     # Revu's ✓
        # Revu's list: the name at the left, the pattern drawn at the right
        swatch = option.rect.adjusted(0, 3, -8, -3)
        swatch.setLeft(swatch.right() - self.SWATCH.width())
        icon = index.data(Qt.DecorationRole)
        if icon is not None:
            # the list's own background: the samples are drawn in the theme's ink
            painter.fillRect(swatch, option.palette.base())
            icon.paint(painter, swatch)
        painter.setPen(text_colour)
        words = option.rect.adjusted(self.WORDS, 0, -(self.SWATCH.width() + 16), 0)
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

    def showPopup(self) -> None:
        fit_the_list(self)                 # every name whole
        super().showPopup()
        # Revu's list opens at its top, Manage… showing, while the one in
        # use is in the first screenful (it opened on the one in use, with
        # Manage… scrolled off above it)
        if 0 <= self.currentIndex() < self.maxVisibleItems() - 2:
            self.view().scrollToTop()

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
