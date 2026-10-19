"""The Properties toolbar, as Revu 21's (the user's screenshots, 2026-10-15
and 2026-10-16: "The Properties toolbar is still really wide and not exactly
like Bluebeam for sizes, thickness, hatches, styles").

Revu's bar reads, left to right, whatever the markup:

    [type ▾]  Line: colour, %, style, width   Start/End ▾ Auto ▾
    Fill: colour, %   Shape ▾   Hatch ▾   highlight   Units ▾  Caption ▾
    Font: family ▾, size ▾, colour, Style ▾   Totals: Area = … ▾

Each control is only as wide as what it shows: the opacities are "100%"
boxes, the width a "1.00 pt" box (arrows before the number, the number at the
right), the line style and the hatch samples with no names, the line ends
their pictures, the font size a "12 ▾" list of Revu's sizes. Bold, italic and
underline — and CalcForge's alignment — are behind Style ▾, as Revu's are.

CalcForge's own extras that Revu's bar does not carry are kept, behind the
type ▾ at the start: the Subject, how many markups are picked, the dash
spacing, the hatch's colour, scale and opacity, and Set as Default.

The window's handlers (``MainWindow._style_*``) do the changing; this module
builds the controls, puts them on the bar in Revu's order and says which are
shown for what.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFontComboBox, QFormLayout,
                               QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu, QSpinBox,
                               QStyle, QStyleOptionComboBox, QStylePainter, QToolBar,
                               QToolButton, QVBoxLayout, QWidget, QWidgetAction)

from .icons import drawn_icon, icon

#: Revu's font sizes (the Properties toolbar's size list).
FONT_SIZES = (6, 7, 8, 9, 10, 11, 12, 14, 16, 18, 20, 22, 24, 26, 28, 36, 48, 72)
#: Revu's line-end sizes: Auto, then a share of it.
END_SIZES = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 4.0)

# Groups of controls beyond the style fields (stylecaps): shown by what the
# markup is rather than by what its style has.
#: Revu's cloud intensities on the bar's ≋ list (the Properties panel's
#: Size takes any value between 0.1 and 20).
CLOUD_SIZES = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0)

SHAPE = "callout_shape"
HIGHLIGHT = "highlight"
CUTOUT = "cutout"
MEASURE = "measure"
UNITS = "units"
TOTALS = "totals"
AUTO_FONT = "font_auto"      # Revu's "A": the words sized to fit the box
END_FILL = "end_fill"        # Revu's line-end colour swatch, after End ▾ Auto ▾
NOTE = "note"                # a note's Color, opacity and Icon ▾ (Revu's)
LINE_SPACING = "line_spacing"  # words in a box: Revu's Line Spacing ▾

#: Revu's Line Spacing list: Single, 1.15, 1.5 and Double; any other multiple
#: can be typed in.
LINE_SPACINGS = (1.0, 1.15, 1.5, 2.0)


def spacing_words(value: float) -> str:
    """A line spacing as the list shows it: 1.0, 1.15, 1.5, 2.0."""
    return f"{value:.1f}" if abs(value * 10 - round(value * 10)) < 1e-9 else f"{value:g}"


def _ink() -> str:
    from .icons import INK
    return INK


# ---------------------------------------------------------------------------
# the controls
# ---------------------------------------------------------------------------

class ValueCombo(QComboBox):
    """A number picked from a short list or typed in — Revu's "12 ▾" font
    size and its "Auto ▾" line-end size. Speaks a spin box's value(),
    setValue() and valueChanged, so the window keeps one way of setting it."""

    valueChanged = Signal(float)

    def __init__(self, presets, fmt, minimum: float, maximum: float,
                 editable: bool = True, first: Optional[tuple] = None,
                 width: int = 56, parent=None):
        super().__init__(parent)
        self._fmt = fmt
        self._minimum, self._maximum = minimum, maximum
        self._value = None
        self._custom = -1
        self.setEditable(editable)
        if first is not None:
            self.addItem(first[0], float(first[1]))
        for value in presets:
            self.addItem(fmt(value), float(value))
        self.setFixedWidth(width)
        self.setMaxVisibleItems(18)
        self.activated.connect(self._picked)
        if editable:
            self.lineEdit().editingFinished.connect(self._typed)
            self.setInsertPolicy(QComboBox.NoInsert)
        from .widgets import checked_list
        checked_list(self)                 # Revu's ✓ on the size picked

    def showPopup(self) -> None:
        from .widgets import fit_the_list
        fit_the_list(self)
        super().showPopup()

    def minimum(self) -> float:
        return self._minimum

    def maximum(self) -> float:
        return self._maximum

    def value(self) -> float:
        return float(self._value if self._value is not None else self.itemData(0) or 0.0)

    def setValue(self, value: float) -> None:
        value = min(max(float(value), self._minimum), self._maximum)
        changed = self._value is None or abs(value - self._value) > 1e-9
        self._value = value
        self._show(value)
        if changed:
            self.valueChanged.emit(value)

    def _show(self, value: float) -> None:
        for index in range(self.count()):
            if index == self._custom:
                continue
            data = self.itemData(index)
            if data is not None and abs(float(data) - value) < 1e-9:
                self.setCurrentIndex(index)
                if self.isEditable():
                    self.setEditText(self.itemText(index))
                return
        if self.isEditable():
            self.setEditText(self._fmt(value))
            return
        # a value not on the list (set in the Properties panel): shown as
        # one more entry at the end
        if self._custom < 0:
            self.addItem("", value)
            self._custom = self.count() - 1
        self.setItemText(self._custom, self._fmt(value))
        self.setItemData(self._custom, value)
        self.setCurrentIndex(self._custom)

    def _picked(self, index: int) -> None:
        data = self.itemData(index)
        if data is not None:
            self.setValue(float(data))

    def _typed(self) -> None:
        text = self.currentText().strip().rstrip("%").replace("pt", "").strip()
        try:
            value = float(text)
        except ValueError:
            self._show(self.value())
            return
        if self.currentText().strip().endswith("%"):
            value /= 100.0
        self.setValue(value)


class IconCombo(QComboBox):
    """A list that shows, closed, only the picture of what is picked: Revu's
    line-end and callout-shape boxes. The names are in the open list and the
    tooltip."""

    def __init__(self, width: int = 58, parent=None):
        super().__init__(parent)
        self.setFixedWidth(width)
        self.currentIndexChanged.connect(lambda _i: self.setToolTip(
            f"{self.property('what') or ''}{self.currentText()}"))

    def showPopup(self) -> None:
        from .widgets import fit_the_list
        fit_the_list(self)                 # as wide as its rows, no wider
        super().showPopup()

    def paintEvent(self, _event) -> None:
        painter = QStylePainter(self)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        current = self.itemIcon(self.currentIndex()) if self.currentIndex() >= 0 else QIcon()
        option.currentText = ""
        option.currentIcon = QIcon()
        painter.drawComplexControl(QStyle.CC_ComboBox, option)
        field = self.style().subControlRect(QStyle.CC_ComboBox, option,
                                            QStyle.SC_ComboBoxEditField, self)
        if not current.isNull():
            size = self.iconSize().boundedTo(field.size())
            x = field.x() + (field.width() - size.width()) // 2
            y = field.y() + (field.height() - size.height()) // 2
            current.paint(painter, x, y, size.width(), size.height())


class CloudSizeCombo(ValueCombo):
    """Revu's cloud intensity ▾: closed, its ≋ picture; open, each size's
    scallops drawn. A size set elsewhere (the Properties panel's Size) shows
    as one more entry at the end, as the line-end sizes do."""

    def __init__(self, parent=None):
        super().__init__(CLOUD_SIZES, lambda v: f"Size {v:g}", 0.1, 20.0, editable=False,
                         width=52, parent=parent)
        self.setIconSize(QSize(40, 14))
        self.face = _cloud_waves_icon()
        self.view().setMinimumWidth(130)
        self.refresh_icons()
        self.setToolTip("Cloud intensity: how big the scallops are")

    def refresh_icons(self) -> None:
        self.face = _cloud_waves_icon()
        for index in range(self.count()):
            data = self.itemData(index)
            if data is not None:
                self.setItemIcon(index, _scallop_icon(float(data)))

    def _show(self, value: float) -> None:
        super()._show(value)
        if self._custom >= 0:
            self.setItemIcon(self._custom, _scallop_icon(float(self.itemData(self._custom))))

    def paintEvent(self, _event) -> None:
        painter = QStylePainter(self)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        option.currentText = ""
        option.currentIcon = QIcon()
        painter.drawComplexControl(QStyle.CC_ComboBox, option)
        field = self.style().subControlRect(QStyle.CC_ComboBox, option,
                                            QStyle.SC_ComboBoxEditField, self)
        size = QSize(22, 18).boundedTo(field.size())
        self.face.paint(painter, field.x() + (field.width() - size.width()) // 2,
                        field.y() + (field.height() - size.height()) // 2,
                        size.width(), size.height())


class LineSpacingCombo(ValueCombo):
    """Revu's Line Spacing ▾ on the bar: closed, its picture; open, 1.0,
    1.15, 1.5 and 2.0, a spacing set elsewhere (the Properties panel's) as
    one more entry, and Other… for any multiple."""

    OTHER = "Other…"

    def __init__(self, parent=None):
        super().__init__(LINE_SPACINGS, spacing_words, 0.1, 10.0, editable=False,
                         width=46, parent=parent)
        self.setIconSize(QSize(20, 20))
        self.face = _line_spacing_icon()
        self.addItem(self.OTHER, None)
        self.view().setMinimumWidth(90)
        self.setToolTip("Line spacing: how far apart the lines are, as a multiple of "
                        "the font's own — 1.0 Single, 1.15, 1.5, 2.0 Double, or Other…")
        self.dialog = None

    def refresh_icons(self) -> None:
        self.face = _line_spacing_icon()
        self.update()

    def _show(self, value: float) -> None:
        # a spacing not on the list goes before Other…, not after it
        other = self.findText(self.OTHER)
        if other >= 0 and self._custom < 0 and not any(
                abs(float(v) - value) < 1e-9 for v in LINE_SPACINGS):
            self.insertItem(other, "", value)
            self._custom = other
        super()._show(value)

    def _picked(self, index: int) -> None:
        if self.itemText(index) == self.OTHER:
            self._show(self.value())
            self.ask()
            return
        super()._picked(index)

    def ask(self):
        """Other…: any multiple, from a small dialog."""
        from PySide6.QtWidgets import QInputDialog
        from .release import done_with
        dialog = QInputDialog(self.window())
        dialog.setObjectName("lineSpacingOther")
        dialog.setWindowTitle("Line Spacing")
        dialog.setLabelText("Line spacing, as a multiple of the font's own\n"
                            "(1 is Single, 2 is Double):")
        dialog.setInputMode(QInputDialog.DoubleInput)
        dialog.setDoubleRange(self.minimum(), self.maximum())
        dialog.setDoubleDecimals(2)
        dialog.setDoubleStep(0.05)
        dialog.setDoubleValue(self.value())
        dialog.accepted.connect(lambda: self.setValue(dialog.doubleValue()))
        dialog.finished.connect(lambda _result: done_with(dialog))
        self.dialog = dialog
        if getattr(self.window(), "interactive_prompts", True):
            dialog.exec()
        else:
            dialog.open()                  # the tests answer it
        return dialog

    def paintEvent(self, _event) -> None:
        painter = QStylePainter(self)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        option.currentText = ""
        option.currentIcon = QIcon()
        painter.drawComplexControl(QStyle.CC_ComboBox, option)
        field = self.style().subControlRect(QStyle.CC_ComboBox, option,
                                            QStyle.SC_ComboBoxEditField, self)
        size = QSize(20, 20).boundedTo(field.size())
        self.face.paint(painter, field.x() + (field.width() - size.width()) // 2,
                        field.y() + (field.height() - size.height()) // 2,
                        size.width(), size.height())


class PopupCombo(QComboBox):
    """Looks like a list box (Revu's "Units ▾", "Style ▾", "Totals: … ▾" and
    the markup's type ▾) and opens a menu or a small panel of its own."""

    def __init__(self, text: str = "", width: int = 0, parent=None):
        super().__init__(parent)
        self.addItem(text)
        self.popup_menu: Optional[QMenu] = None
        self.popup_panel: Optional[QFrame] = None
        self.about_to_show = None
        if width:
            self.setFixedWidth(width)
        else:
            self.setSizeAdjustPolicy(QComboBox.AdjustToContents)

    def set_face(self, text: str = None, picture: QIcon = None) -> None:
        if text is not None and self.itemText(0) != text:
            self.setItemText(0, text)
        if picture is not None:
            self.setItemIcon(0, picture)

    def showPopup(self) -> None:
        if self.about_to_show is not None:
            self.about_to_show()
        where = self.mapToGlobal(self.rect().bottomLeft())
        if self.popup_menu is not None:
            self.popup_menu.popup(where)
        elif self.popup_panel is not None:
            self.popup_panel.adjustSize()
            self.popup_panel.move(where)
            self.popup_panel.show()

    def hidePopup(self) -> None:
        # also called as the combo is hidden — including while the window is
        # being taken down, when the menu or panel may already be gone
        from shiboken6 import isValid
        for popup in (self.popup_menu, self.popup_panel):
            try:
                if popup is not None and isValid(popup) and popup.isVisible():
                    popup.hide()
            except RuntimeError:
                pass

    def wheelEvent(self, event) -> None:
        event.ignore()                     # one item: nothing to scroll through


class _IconOnlyPopupCombo(PopupCombo):
    """The type ▾ and caption ▾: a picture and the arrow."""

    def __init__(self, width: int, parent=None):
        super().__init__("", width, parent)

    paintEvent = IconCombo.paintEvent


def _panel(owner, name: str) -> QFrame:
    panel = QFrame(owner, Qt.Popup)
    panel.setObjectName(name)
    panel.setFrameShape(QFrame.StyledPanel)
    return panel


HATCH_TIP = "Hatch pattern, drawn over the fill in its own colour"


def hatch_tip(combo) -> None:
    """The hatch list's tooltip: the pattern's name, as the line list's is —
    or, with none, what the list is for. Kept in step however the list was
    set, so it never names a pattern the markup no longer has."""
    combo.setToolTip(combo.currentText() if combo.currentData() else HATCH_TIP)


def _framed(button):
    """A colour button framed as Revu's are, its colour a square inside."""
    button.setProperty("revuSwatch", True)
    button.setIconSize(QSize(14, 14))
    return button


def _number(spin, width: int):
    spin.setFixedWidth(width)
    spin.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return _typed_on_enter(spin)


def fit_numbers(bar) -> None:
    """Size every number box on the bar to its widest value, and no more.

    Fixed widths cut "100%" off in the fill-opacity box (the user,
    2026-10-17): what the box needs is its frame and arrows, as the style
    draws them, plus the widest text it can show — its minimum or maximum
    with prefix and suffix — plus the line edit's own margins.
    """
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QAbstractSpinBox, QStyleOptionSpinBox
    for spin in bar.findChildren(QAbstractSpinBox):
        spin.ensurePolished()
        option = QStyleOptionSpinBox()
        option.initFrom(spin)
        option.rect = QRect(0, 0, 200, max(spin.sizeHint().height(), 20))
        option.frame = spin.hasFrame()
        option.buttonSymbols = spin.buttonSymbols()
        option.subControls = (QStyle.SC_SpinBoxFrame | QStyle.SC_SpinBoxEditField
                              | QStyle.SC_SpinBoxUp | QStyle.SC_SpinBoxDown)
        field = spin.style().subControlRect(QStyle.CC_SpinBox, option,
                                            QStyle.SC_SpinBoxEditField, spin)
        chrome = option.rect.width() - field.width()
        metrics = spin.fontMetrics()
        texts = [spin.prefix() + spin.textFromValue(value) + spin.suffix()
                 for value in (spin.minimum(), spin.maximum())] \
            if hasattr(spin, "textFromValue") else [spin.text()]
        widest = max(metrics.horizontalAdvance(text) for text in texts)
        # the line edit's text margins (2 px a side) and its cursor
        spin.setFixedWidth(chrome + widest + 8)
    # and the number lists — the font size, the line-end sizes — the same way
    for combo in bar.findChildren(ValueCombo):
        if isinstance(combo, (CloudSizeCombo, LineSpacingCombo)):
            continue                       # closed, it shows its picture only
        combo.ensurePolished()
        option = QStyleOptionComboBox()
        option.initFrom(combo)
        option.rect = QRect(0, 0, 200, max(combo.sizeHint().height(), 20))
        option.editable = combo.isEditable()
        field = combo.style().subControlRect(QStyle.CC_ComboBox, option,
                                             QStyle.SC_ComboBoxEditField, combo)
        chrome = option.rect.width() - field.width()
        metrics = combo.fontMetrics()
        texts = [combo.itemText(i) for i in range(combo.count())]
        if combo.isEditable():
            texts.append(combo._fmt(88.8))  # a typed size with a decimal: "35.1"
        widest = max(metrics.horizontalAdvance(text) for text in texts)
        combo.setFixedWidth(chrome + widest + 8)


def _typed_on_enter(spin):
    """A number typed into the box applies on Enter or on leaving it, as
    Revu's do — one undo step, and no half-typed "2." drawn on the way. The
    arrows and the wheel still apply at once."""
    spin.setKeyboardTracking(False)
    return spin


# ---------------------------------------------------------------------------
# icons drawn for the bar
# ---------------------------------------------------------------------------

def _caption_icon() -> QIcon:
    def draw(painter: QPainter) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(QColor(_ink()), 1.2)
        painter.setPen(pen)
        painter.drawRoundedRect(QRectF(2.5, 2.5, 15, 15), 2, 2)
        for y, (a, b) in zip((6.5, 9.5, 12.5, 15.0), ((5, 15), (6, 14), (5, 15), (7, 13))):
            painter.drawLine(QPointF(a, y), QPointF(b, y))
    return drawn_icon(draw, 20, 20)


def _fit_icon() -> QIcon:
    """Fit to text: four arrows pointing in."""
    def draw(painter: QPainter) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor(_ink()), 1.3))
        painter.drawRect(QRectF(2.5, 2.5, 15, 15))
        for corner, inner in ((QPointF(4, 4), QPointF(8.5, 8.5)),
                              (QPointF(16, 16), QPointF(11.5, 11.5))):
            painter.drawLine(corner, inner)
        painter.drawPolyline(QPolygonF([QPointF(8.5, 5.5), QPointF(8.5, 8.5), QPointF(5.5, 8.5)]))
        painter.drawPolyline(QPolygonF([QPointF(11.5, 14.5), QPointF(11.5, 11.5),
                                        QPointF(14.5, 11.5)]))
    return drawn_icon(draw, 20, 20)


def _auto_font_icon() -> QIcon:
    """Revu's Auto font size: an A in a box whose corners open outwards."""
    def draw(painter: QPainter) -> None:
        from PySide6.QtGui import QFont
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor(_ink()), 1.3))
        for x, y, dx, dy in ((2.5, 2.5, 1, 1), (17.5, 2.5, -1, 1),
                             (2.5, 17.5, 1, -1), (17.5, 17.5, -1, -1)):
            painter.drawPolyline(QPolygonF([QPointF(x, y + 4 * dy), QPointF(x, y),
                                            QPointF(x + 4 * dx, y)]))
        font = QFont()
        font.setBold(True)
        font.setPixelSize(12)
        painter.setFont(font)
        painter.drawText(QRectF(0, 0, 20, 20), Qt.AlignCenter, "A")
    return drawn_icon(draw, 20, 20)


def _line_spacing_icon() -> QIcon:
    """Line spacing: three lines beside a two-headed arrow, as Revu's."""
    def draw(painter: QPainter) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor(_ink()), 1.3))
        for y in (4.5, 10.0, 15.5):
            painter.drawLine(QPointF(9.0, y), QPointF(18.0, y))
        painter.drawLine(QPointF(4.0, 3.0), QPointF(4.0, 17.0))
        painter.drawPolyline(QPolygonF([QPointF(1.5, 5.5), QPointF(4.0, 3.0),
                                        QPointF(6.5, 5.5)]))
        painter.drawPolyline(QPolygonF([QPointF(1.5, 14.5), QPointF(4.0, 17.0),
                                        QPointF(6.5, 14.5)]))
    return drawn_icon(draw, 20, 20)


def line_spacing_combo(value: float = 1.0, parent=None) -> "ValueCombo":
    """The Properties panel's Line Spacing: 1.0, 1.15, 1.5, 2.0, or any
    multiple typed in (the bar's is LineSpacingCombo)."""
    combo = ValueCombo(LINE_SPACINGS, spacing_words, 0.1, 10.0, editable=True,
                       width=86, parent=parent)
    picture = _line_spacing_icon()
    for index in range(combo.count()):
        combo.setItemIcon(index, picture)
    combo.setToolTip("Line spacing: how far apart the lines are, as a multiple "
                     "of the font's own — 1.0 Single, 1.15, 1.5, 2.0 Double, "
                     "or type any other")
    combo.blockSignals(True)
    combo.setValue(value)
    combo.blockSignals(False)
    return combo


def _scallop_path(left: float, right: float, y: float, radius: float):
    """A run of a cloud's scallops along y, each *radius* high."""
    from PySide6.QtGui import QPainterPath
    path = QPainterPath()
    step = radius * 2
    x = left
    path.moveTo(x, y)
    while x + step <= right + 0.01:
        path.arcTo(QRectF(x, y - radius, step, step), 180, -180)
        x += step
    return path


def _cloud_waves_icon() -> QIcon:
    """Revu's ≋ for the cloud's intensity list: three rows of scallops."""
    def draw(painter: QPainter) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor(_ink()), 1.1))
        for y in (6.0, 11.0, 16.0):
            painter.drawPath(_scallop_path(1.0, 21.0, y, 2.5))
    return drawn_icon(draw, 22, 18)


def _scallop_icon(size: float) -> QIcon:
    """One cloud intensity, drawn: scallops as big as that size makes them."""
    def draw(painter: QPainter) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor(_ink()), 1.2))
        radius = max(1.5, min(1.5 + size, 6.5))
        painter.drawPath(_scallop_path(2.0, 38.0, 4.0 + radius, radius))
    return drawn_icon(draw, 40, 14)


def note_icon_picture(key: str) -> QIcon:
    """A note's icon as its Icon ▾ list shows it: drawn as on the page."""
    from ..items.text import paint_note_icon

    def draw(painter: QPainter) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        paint_note_icon(painter, QRectF(1, 1, 18, 18), key, QColor("#ffe066"),
                        QColor("#b8860b"))
    return drawn_icon(draw, 20, 20)


def _shape_icon(kind: str) -> QIcon:
    def draw(painter: QPainter) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor(_ink()), 1.2))
        if kind == "cloud":
            from .icons import _cloud
            _cloud(painter, _ink(), QRectF(3, 4, 20, 12))
        else:
            painter.drawRect(QRectF(4.5, 4.5, 17, 11))
    return drawn_icon(draw, 26, 20)


# ---------------------------------------------------------------------------
# building it
# ---------------------------------------------------------------------------

def build(window) -> QToolBar:
    """The Properties toolbar ("Style" in older layouts), its controls set on
    *window* under the names the rest of the window uses."""
    from ..items.base import DASH_ARRAYS
    from ..items.measure import CountItem
    from ..items.text import STAMP_PRESETS
    from .mainwindow import _bar_ink
    from .panels import fill_hatch_combo, fill_line_style_combo
    from .stylecaps import (ARROW_SIZE, CLOUD, CORNER, DASH, FILL, FILL_OPACITY, FONT,
                            HATCH, OPACITY, STROKE, SYMBOL, WIDTH)
    from .widgets import ColorButton, PatternCombo, UnboundedSpin, arrow_combo, \
        big_pattern_dropdown

    w = window
    style = w.default_style
    bar = QToolBar("Properties")
    bar.setObjectName("toolbar_style")
    w._style_widgets = {key: [] for key in (
        STROKE, OPACITY, DASH, CLOUD, WIDTH, CORNER, ARROW_SIZE, FILL, FILL_OPACITY,
        SHAPE, HATCH, HIGHLIGHT, CUTOUT, SYMBOL, UNITS, MEASURE, FONT, AUTO_FONT,
        TOTALS, END_FILL, NOTE, LINE_SPACING)}

    w._style_action = {}

    def put(field: str, widget):
        action = bar.addWidget(widget)
        w._style_widgets[field].append(action)
        w._style_action[widget] = action
        return action

    def label(text: str) -> QLabel:
        return QLabel(text)

    # -- the markup's type, and everything of CalcForge's behind its ▾ ------
    w.style_kind_menu = _IconOnlyPopupCombo(46)
    w.style_kind_menu.setObjectName("styleKindMenu")
    w.style_kind_menu.setIconSize(QSize(22, 22))
    w.style_kind_menu.setToolTip("Subject and how many markups are selected, and more")
    w._style_kind_action = bar.addWidget(w.style_kind_menu)
    _build_more_panel(w)
    w.style_kind_menu.popup_panel = w.style_more_popup
    w.style_kind_menu.about_to_show = w._fill_style_more_popup

    # -- a note's: Color, opacity, Icon ▾ (Revu's note has no line or fill) --
    from ..items.text import NOTE_ICONS
    put(NOTE, label("Colour:"))
    w.note_colour_button = ColorButton("#ffe066", False, "Note colour")
    w.note_colour_button.setObjectName("noteColour")
    w.note_colour_button.setToolTip("Note colour")
    w.note_colour_button.colorChanged.connect(w._style_note_colour)
    _framed(w.note_colour_button)
    put(NOTE, w.note_colour_button)
    w.note_opacity_spin = _number(QSpinBox(), 60)
    w.note_opacity_spin.setObjectName("noteOpacity")
    w.note_opacity_spin.setRange(0, 100)
    w.note_opacity_spin.setSuffix("%")
    w.note_opacity_spin.setToolTip("Opacity of the note")
    w.note_opacity_spin.setValue(100)
    w.note_opacity_spin.valueChanged.connect(w._style_note_opacity)
    put(NOTE, w.note_opacity_spin)
    put(NOTE, label("Icon:"))
    w.note_icon_combo = IconCombo(52)
    w.note_icon_combo.setObjectName("noteIcon")
    w.note_icon_combo.setProperty("what", "Icon: ")
    w.note_icon_combo.setIconSize(QSize(20, 20))
    for key, words in NOTE_ICONS:
        w.note_icon_combo.addItem(note_icon_picture(key), words, key)
    from .widgets import checked_list
    checked_list(w.note_icon_combo)
    w.note_icon_combo.setCurrentIndex(max(w.note_icon_combo.findData("Note"), 0))
    w.note_icon_combo.currentIndexChanged.connect(
        lambda _i: w._style_note_icon(w.note_icon_combo.currentData()))
    put(NOTE, w.note_icon_combo)

    # -- Line: colour, %, style, (cloud intensity), width, (radius) ---------
    put(STROKE, label("Line:"))
    w.stroke_button = ColorButton(style.stroke, True, "Line colour")
    w.stroke_button.setObjectName("lineColour")
    w.stroke_button.colorChanged.connect(w._style_stroke)
    _framed(w.stroke_button)
    put(STROKE, w.stroke_button)
    w.opacity_spin = _number(QSpinBox(), 60)
    w.opacity_spin.setObjectName("overallOpacity")
    w.opacity_spin.setRange(0, 100)
    w.opacity_spin.setSuffix("%")
    w.opacity_spin.setToolTip("Opacity: the whole markup — line, fill and hatch together")
    w.opacity_spin.setValue(int(style.opacity * 100))
    w.opacity_spin.valueChanged.connect(w._style_opacity)
    put(OPACITY, w.opacity_spin)
    w.dash_combo = PatternCombo()
    w.dash_combo.setObjectName("lineStyleBar")
    big_pattern_dropdown(w.dash_combo)
    # Revu's: Manage… at the top, then every line style drawn — for a cloud,
    # drawn as its scallops
    fill_line_style_combo(w.dash_combo, _bar_ink(), 1)
    w.dash_combo.currentIndexChanged.connect(
        lambda index: w._style_dash(w.dash_combo.itemData(index)) if index >= 0 else None)
    put(DASH, w.dash_combo)
    # Revu's cloud intensity ▾, after the line style
    w.cloud_spin = CloudSizeCombo()
    w.cloud_spin.setObjectName("cloudSize")
    w.cloud_spin.setValue(w.default_cloud_size)
    w.cloud_spin.valueChanged.connect(w._style_cloud)
    put(CLOUD, w.cloud_spin)
    w.width_spin = _number(QDoubleSpinBox(), 80)
    w.width_spin.setObjectName("lineWidth")
    w.width_spin.setRange(0.0, 40.0)
    w.width_spin.setSingleStep(0.25)
    w.width_spin.setDecimals(2)
    w.width_spin.setSuffix(" pt")
    w.width_spin.setValue(style.width)
    w.width_spin.setToolTip("Line width")
    w.width_spin.valueChanged.connect(w._style_width)
    put(WIDTH, w.width_spin)
    put(CORNER, label("Radius:"))
    w.corner_spin = _number(QDoubleSpinBox(), 76)
    w.corner_spin.setObjectName("cornerRadius")
    w.corner_spin.setRange(0.0, 200.0)
    w.corner_spin.setDecimals(1)
    w.corner_spin.setSuffix(" pt")
    w.corner_spin.setValue(style.corner_radius)
    w.corner_spin.setToolTip("Corner radius: 0 is square")
    w.corner_spin.valueChanged.connect(lambda value: w._style_change(
        CORNER, lambda s: setattr(s, "corner_radius", value), "Corner radius"))
    put(CORNER, w.corner_spin)

    # -- Start ▾ Auto ▾  End ▾ Auto ▾ — each end its own size, as Revu's ----
    w.arrow_start_combo = _end_combo(arrow_combo(), "Start: ")
    w.arrow_end_combo = _end_combo(arrow_combo(), "End: ")

    def end_size(what: str) -> ValueCombo:
        box = ValueCombo(END_SIZES, lambda v: f"{v * 100:g}%", 0.25, 4.0, editable=False,
                         first=("Auto", 1.0), width=64)
        box.setToolTip(f"{what} size: how big the line's {what.lower()} is — Auto "
                       "sizes it from the line width")
        return box
    w.arrow_start_size_spin = end_size("Start")
    w.arrow_start_size_spin.setObjectName("arrowStartSize")
    w.arrow_start_size_spin.setValue(style.start_size())
    w.arrow_start_size_spin.valueChanged.connect(w._style_arrow_start_size)
    w.arrow_size_spin = end_size("End")
    w.arrow_size_spin.setObjectName("arrowSize")
    w.arrow_size_spin.setValue(style.arrow_size)
    w.arrow_size_spin.valueChanged.connect(w._style_arrow_size)
    for word, control, size, attribute in (
            ("Start:", w.arrow_start_combo, w.arrow_start_size_spin, "arrow_start"),
            ("End:", w.arrow_end_combo, w.arrow_size_spin, "arrow_end")):
        control.currentIndexChanged.connect(
            lambda _i, name=attribute, box=control: w._style_line_ending(name, box.currentData()))
        word_action = put(ARROW_SIZE, label(word))
        if attribute == "arrow_start":
            w.arrow_start_label_action = word_action
        put(ARROW_SIZE, control)
        put(ARROW_SIZE, size)
    # Revu's line-end colour, after End ▾ Auto ▾: what a filled end is
    # filled with (the Properties panel's Fill Color on a line)
    w.end_fill_button = ColorButton(style.stroke, True, "Line-end colour")
    w.end_fill_button.setObjectName("lineEndFill")
    w.end_fill_button.setToolTip("Line-end colour: what a filled end — Closed, Round, "
                                 "Square, Diamond — is filled with")
    w.end_fill_button.colorChanged.connect(w._style_end_fill)
    _framed(w.end_fill_button)
    put(END_FILL, w.end_fill_button)

    # -- Fill: colour, % -----------------------------------------------------
    put(FILL, label("Fill:"))
    w.fill_button = ColorButton("", True, "Fill colour")
    w.fill_button.setObjectName("fillColour")
    w.fill_button.colorChanged.connect(w._style_fill)
    _framed(w.fill_button)
    put(FILL, w.fill_button)
    w.fill_opacity_spin = _number(QSpinBox(), 60)
    w.fill_opacity_spin.setObjectName("fillOpacity")
    w.fill_opacity_spin.setRange(0, 100)
    w.fill_opacity_spin.setSuffix("%")
    w.fill_opacity_spin.setToolTip(
        "Fill opacity: how solid the fill is (not the line or the hatch)")
    w.fill_opacity_spin.setValue(int(style.fill_opacity * 100))
    w.fill_opacity_spin.valueChanged.connect(w._style_fill_opacity)
    put(FILL_OPACITY, w.fill_opacity_spin)

    # -- a callout's Shape ▾ and Fit to text --------------------------------
    put(SHAPE, label("Shape:"))
    w.callout_shape_combo = IconCombo(52)
    w.callout_shape_combo.setObjectName("calloutShapeBar")
    w.callout_shape_combo.setProperty("what", "Shape: ")
    w.callout_shape_combo.setIconSize(QSize(26, 20))
    w.callout_shape_combo.addItem(_shape_icon("box"), "Rectangle", "box")
    w.callout_shape_combo.addItem(_shape_icon("cloud"), "Cloud", "cloud")
    from .widgets import checked_list
    checked_list(w.callout_shape_combo)
    w.callout_shape_combo.currentIndexChanged.connect(
        lambda _i: w._style_callout_shape(w.callout_shape_combo.currentData()))
    put(SHAPE, w.callout_shape_combo)
    w.fit_text_button = QToolButton()
    w.fit_text_button.setObjectName("fitToText")
    w.fit_text_button.setIcon(_fit_icon())
    w.fit_text_button.setToolTip("Fit to text: the box shrinks or grows to its words (Alt+Z)")
    w.fit_text_button.clicked.connect(lambda: w.act_autosize.trigger())
    put(SHAPE, w.fit_text_button)

    # -- Hatch ▾ ---------------------------------------------------------------
    put(HATCH, label("Hatch:"))
    w.hatch_combo = PatternCombo()
    w.hatch_combo.SAMPLE_WIDTH = 30
    w.hatch_combo.setProperty("blankNone", True)
    w.hatch_combo.setObjectName("hatchPattern")
    big_pattern_dropdown(w.hatch_combo)
    fill_hatch_combo(w.hatch_combo, _bar_ink())
    w.hatch_combo.currentIndexChanged.connect(lambda _index: hatch_tip(w.hatch_combo))
    hatch_tip(w.hatch_combo)
    w.hatch_combo.currentIndexChanged.connect(
        lambda _index: w._style_hatch(w.hatch_combo.currentData()))
    put(HATCH, w.hatch_combo)
    # the hatch's own colour, beside it, as the Properties panel has it (the
    # user, 2026-10-17: a Sketch to Scale rectangle's hatch had no colour on
    # the bar). The type ▾ panel keeps its Hatch colour too.
    w.hatch_bar_colour_button = ColorButton(style.hatch_color, label="Hatch colour")
    w.hatch_bar_colour_button.setObjectName("hatchColourBar")
    w.hatch_bar_colour_button.setToolTip("Hatch colour: the colour of the hatch's lines")
    w.hatch_bar_colour_button.colorChanged.connect(w._style_hatch_colour)
    _framed(w.hatch_bar_colour_button)
    put(HATCH, w.hatch_bar_colour_button)

    # -- Highlight, and a cut-out in an area ---------------------------------
    w.highlight_button = QToolButton()
    w.highlight_button.setObjectName("styleHighlight")
    w.highlight_button.setCheckable(True)
    w.highlight_button.setIcon(icon("highlighter", 20))
    w.highlight_button.setToolTip("Highlight: what is under the markup shows through it, "
                                  "as through a highlighter")
    w.highlight_button.toggled.connect(w._style_highlight)
    put(HIGHLIGHT, w.highlight_button)
    w.cutout_button = QToolButton()
    w.cutout_button.setObjectName("styleCutout")
    w.cutout_button.setIcon(icon("cutout_polygon", 20))
    w.cutout_button.setToolTip("Add a cut-out: draw a hole to take out of this area")
    w.cutout_button.clicked.connect(lambda: w.select_tool("cutout_polygon"))
    put(CUTOUT, w.cutout_button)

    # -- a count's symbol ------------------------------------------------------
    put(SYMBOL, label("Symbol:"))
    w.symbol_combo = QComboBox()
    w.symbol_combo.setObjectName("countSymbol")
    w.symbol_combo.addItems(list(CountItem.SYMBOLS))
    w.symbol_combo.setToolTip("Count symbol")
    w.symbol_combo.currentTextChanged.connect(w._style_symbol)
    put(SYMBOL, w.symbol_combo)

    # -- Units ▾ and Caption ▾ for a measurement ------------------------------
    w.units_button = PopupCombo("Units", 64)
    w.units_button.setObjectName("measureUnits")
    w.units_button.setToolTip("Units: what this measurement is written in — "
                              "the page's, or its own")
    w.units_button.popup_panel = _build_units_panel(w)
    w.units_button.about_to_show = w._fill_units_panel
    put(UNITS, w.units_button)
    w.caption_button = _IconOnlyPopupCombo(44)
    w.caption_button.setObjectName("measureCaption")
    w.caption_button.setIconSize(QSize(20, 20))
    w.caption_button.set_face(picture=_caption_icon())
    w.caption_button.setToolTip("Caption: whether it is written on the drawing, "
                                "and which values")
    caption_menu = QMenu(w.caption_button)
    caption_menu.setObjectName("captionMenu")
    caption_menu.setProperty("cf_context", "propbar.caption")
    w.caption_show_action = caption_menu.addAction("Show Caption")
    w.caption_show_action.setCheckable(True)
    w.caption_show_action.toggled.connect(lambda on: w._measure_setting(
        "show_label", on, "Caption"))
    caption_menu.addSeparator()
    # Revu's caption values: what the measurement can show beside its own —
    # an area its perimeter, and with a depth its volume and wall area
    from ..items.measure import CAPTION_PARTS
    w.caption_part_actions = {}
    for part, words in CAPTION_PARTS:
        action = caption_menu.addAction(words)
        action.setCheckable(True)
        action.setObjectName(f"caption_{part}")
        action.toggled.connect(lambda on, p=part: w._caption_part(p, on))
        w.caption_part_actions[part] = action
    caption_menu.addSeparator()
    w.caption_inline_action = caption_menu.addAction("Inline Text")
    w.caption_inline_action.setCheckable(True)
    w.caption_inline_action.setToolTip("The text in line with the measurement's line")
    w.caption_inline_action.toggled.connect(lambda on: w._measure_setting(
        "label_angle", None if on else 0.0, "Text angle"))
    w.caption_button.popup_menu = caption_menu
    w.caption_button.about_to_show = w._fill_caption_menu
    put(MEASURE, w.caption_button)

    # -- Font: family, size ▾, colour, Style ▾ ------------------------------
    put(FONT, label("Font:"))
    w.font_family_combo = QFontComboBox()
    w.font_family_combo.setObjectName("fontFamily")
    # narrow enough that a length's bar, line-end colour and all, still fits 1280
    w.font_family_combo.setFixedWidth(104)
    w.font_family_combo.currentFontChanged.connect(lambda font: w._style_change(
        FONT, lambda s: setattr(s, "font_family", font.family()), "Font"))
    put(FONT, w.font_family_combo)
    w.font_spin = ValueCombo(FONT_SIZES, lambda v: f"{v:g}", 1.0, 144.0, editable=True,
                             width=58)
    w.font_spin.setObjectName("fontSize")
    w.font_spin.setToolTip("Font size, in points")
    w.font_spin.setValue(style.font_size)
    w.font_spin.valueChanged.connect(w._style_font)
    put(FONT, w.font_spin)
    w.font_auto_button = QToolButton()
    w.font_auto_button.setObjectName("fontAuto")
    w.font_auto_button.setCheckable(True)
    w.font_auto_button.setIcon(_auto_font_icon())
    w.font_auto_button.setToolTip("Auto: the font size set to the largest that fits "
                                  "the box, and kept so as the words or the box change")
    w.font_auto_button.toggled.connect(w._style_font_auto)
    put(AUTO_FONT, w.font_auto_button)
    w.text_colour_button = ColorButton(style.text_color, label="Text colour")
    w.text_colour_button.setObjectName("textColour")
    _framed(w.text_colour_button)
    w.text_colour_button.colorChanged.connect(lambda value: w._style_change(
        FONT, lambda s: setattr(s, "text_color", value), "Text colour"))
    put(FONT, w.text_colour_button)
    w.font_style_button = PopupCombo("Style", 62)
    w.font_style_button.setObjectName("fontStyle")
    w.font_style_button.setToolTip("Font style: bold, italic, underline, strikethrough; "
                                   "alignment")
    w.font_style_button.popup_panel = _build_font_style_panel(w)
    put(FONT, w.font_style_button)
    # Revu's Line Spacing ▾, for words in a box
    w.line_spacing_combo = LineSpacingCombo()
    w.line_spacing_combo.setObjectName("lineSpacing")
    w.line_spacing_combo.blockSignals(True)
    w.line_spacing_combo.setValue(style.line_spacing)
    w.line_spacing_combo.blockSignals(False)
    w.line_spacing_combo.valueChanged.connect(w._style_line_spacing)
    put(LINE_SPACING, w.line_spacing_combo)

    # -- Totals: … ▾ ----------------------------------------------------------
    put(TOTALS, label("Totals:"))
    w.totals_button = PopupCombo("")
    w.totals_button.setObjectName("measureTotals")
    w.totals_button.setMinimumWidth(110)
    w.totals_button.setToolTip("The selected measurements added up")
    w.totals_button.popup_menu = QMenu(w.totals_button)
    w.totals_button.popup_menu.setObjectName("totalsMenu")
    w.totals_button.popup_menu.setProperty("cf_data", True)      # the totals themselves
    put(TOTALS, w.totals_button)

    w.style_bar = bar
    fit_numbers(bar)
    # a table's own controls, on the same bar while it is open
    from .tablebar import TableControls
    w.table_controls = TableControls(w)
    # The stamp's wording and the count's subject only mean anything while
    # those tools are in hand, and reading "APPROVED" across the top of the
    # window while drawing a rectangle is just noise. Both come and go with
    # the tool they belong to.
    w.stamp_combo = QComboBox()
    w.stamp_combo.addItems(list(STAMP_PRESETS))
    w.stamp_combo.setEditable(True)
    w.stamp_combo.setToolTip("What the stamp says")
    w.stamp_combo.currentTextChanged.connect(
        lambda text: setattr(w.view, "stamp_text", text))
    w.stamp_label = QLabel(" Stamp ")
    w._stamp_widgets = [bar.addWidget(w.stamp_label), bar.addWidget(w.stamp_combo)]
    count_button = QToolButton()
    count_button.setText("Count subject…")
    count_button.setToolTip("What the Count tool counts and its symbol; markers "
                            "count as Count until you set a subject, as in Revu")
    count_button.clicked.connect(w.choose_count_subject)
    w._count_widgets = [bar.addWidget(count_button)]
    return bar


def _end_combo(combo: QComboBox, what: str) -> QComboBox:
    """An arrow_combo shown closed as only its picture, as Revu's are."""
    from .widgets import checked_list
    shown = IconCombo(60)
    shown.setProperty("what", what)
    shown.setObjectName(f"lineEnd{what.strip(': ')}")
    shown.setIconSize(QSize(30, 16))
    for index in range(combo.count()):
        picture = combo.itemIcon(index)
        if what.startswith("Start"):
            picture = _mirrored(picture)       # Revu's start ends point back: ◀—
        shown.addItem(picture, combo.itemText(index), combo.itemData(index))
    # Revu's list (the user's shot of End ▾): the pictures alone, a ✓ on the
    # one in use; each name is its tooltip
    checked_list(shown, pictures=True, picture=QSize(42, 20))
    return shown


def _mirrored(picture: QIcon) -> QIcon:
    """A line end drawn for the start of a line: pointing the other way."""
    from PySide6.QtGui import QTransform
    flipped = QIcon()
    for size in picture.availableSizes() or [QSize(42, 20)]:
        pixmap = picture.pixmap(size)
        flipped.addPixmap(pixmap.transformed(QTransform().scale(-1, 1)))
    return flipped


def _build_more_panel(w) -> None:
    """Behind the type ▾: the Subject and count (Revu's), then CalcForge's
    extras the bar has no room for, and Set as Default."""
    from .widgets import ColorButton, UnboundedSpin
    from .stylecaps import DASH, HATCH
    panel = _panel(w, "subjectPopup")
    form = QFormLayout(panel)
    form.setContentsMargins(10, 8, 10, 10)
    w.style_kind_label = QLabel("")
    w.style_kind_label.setObjectName("styleKind")
    font = w.style_kind_label.font()
    font.setBold(True)
    w.style_kind_label.setFont(font)
    form.addRow(w.style_kind_label)
    w.subject_field = QLineEdit()
    w.subject_field.setObjectName("subjectField")
    w.subject_field.setMinimumWidth(200)
    w.subject_field.editingFinished.connect(w._subject_typed)
    form.addRow("Subject:", w.subject_field)
    w.selected_count_label = QLabel("0")
    form.addRow("Markups:", w.selected_count_label)
    w.dash_scale_spin = _typed_on_enter(QDoubleSpinBox())
    w.dash_scale_spin.setObjectName("dashSpacing")
    w.dash_scale_spin.setRange(0.1, 50.0)
    w.dash_scale_spin.setDecimals(2)
    w.dash_scale_spin.setSingleStep(0.25)
    w.dash_scale_spin.setValue(w.default_style.dash_scale)
    w.dash_scale_spin.setPrefix("× ")
    w.dash_scale_spin.setToolTip("Dash spacing: how long the dashes and gaps are, "
                                 "whatever the thickness")
    w.dash_scale_spin.valueChanged.connect(lambda value: w._style_change(
        DASH, lambda s: setattr(s, "dash_scale", value), "Dash spacing"))
    form.addRow("Dash spacing:", w.dash_scale_spin)
    w.hatch_colour_button = ColorButton(w.default_style.hatch_color, label="Hatch colour")
    w.hatch_colour_button.setObjectName("hatchColour")
    w.hatch_colour_button.colorChanged.connect(w._style_hatch_colour)
    form.addRow("Hatch colour:", w.hatch_colour_button)
    w.hatch_scale_spin = UnboundedSpin()
    w.hatch_scale_spin.setObjectName("hatchScale")
    w.hatch_scale_spin.setMinimumWidth(84)
    w.hatch_scale_spin.setSuffix(" %")
    w.hatch_scale_spin.setValue(100)
    w.hatch_scale_spin.setToolTip("Hatch scale, as Bluebeam's: 100 as drawn, 50 half, "
                                  "200 twice")
    w.hatch_scale_spin.valueChanged.connect(lambda value: w._style_change(
        HATCH, lambda s: setattr(s, "hatch_scale", value / 100.0), "Hatch scale"))
    form.addRow("Hatch scale:", w.hatch_scale_spin)
    w.hatch_opacity_spin = _typed_on_enter(QSpinBox())
    w.hatch_opacity_spin.setObjectName("hatchOpacity")
    w.hatch_opacity_spin.setRange(0, 100)
    w.hatch_opacity_spin.setSuffix(" %")
    w.hatch_opacity_spin.setToolTip(
        "Hatch opacity: how solid the hatch lines are (not the fill or the line)")
    w.hatch_opacity_spin.setValue(int(w.default_style.hatch_opacity * 100))
    w.hatch_opacity_spin.valueChanged.connect(w._style_hatch_opacity)
    form.addRow("Hatch opacity:", w.hatch_opacity_spin)
    w.default_button = QToolButton()
    w.default_button.setObjectName("setAsDefault")
    w.default_button.setText("Set as Default")
    w.default_button.setToolTip(
        "Use the selected markup's compatible style for new markups of this kind")
    w.default_button.setEnabled(False)
    w.default_button.clicked.connect(w.set_selected_as_default)
    form.addRow("", w.default_button)
    w.style_more_popup = panel
    w._style_more_form = form


def _build_font_style_panel(w) -> QFrame:
    """Revu's Style ▾: "Font Style: B I U S", and CalcForge's alignment."""
    from .stylecaps import FONT
    panel = _panel(w, "fontStylePopup")
    row = QHBoxLayout(panel)
    row.setContentsMargins(10, 6, 10, 6)
    row.setSpacing(4)
    row.addWidget(QLabel("Font Style:"))
    w.font_buttons = {}
    for name, text in (("bold", "B"), ("italic", "I"), ("underline", "U"),
                       ("strikethrough", "S")):
        button = QToolButton()
        button.setObjectName(f"fontStyle_{name}")
        button.setText(text)
        face = button.font()
        face.setBold(name == "bold")
        face.setItalic(name == "italic")
        face.setUnderline(name == "underline")
        face.setStrikeOut(name == "strikethrough")
        button.setFont(face)
        button.setCheckable(True)
        button.setAutoRaise(True)
        button.setToolTip(name.capitalize())
        button.toggled.connect(lambda on, field=name: w._style_change(
            FONT, lambda s: s.set_font_style(field, on), "Font style"))
        w.font_buttons[name] = button
        row.addWidget(button)
    w.text_align_combo = QComboBox()
    w.text_align_combo.setObjectName("textAlign")
    w.text_align_combo.addItems(["left", "center", "right", "justify"])
    w.text_align_combo.setToolTip("Text alignment")
    w.text_align_combo.currentTextChanged.connect(lambda value: w._style_change(
        FONT, lambda s: setattr(s, "align", value), "Text alignment"))
    w._align_label = QLabel("Align:")
    row.addSpacing(8)
    row.addWidget(w._align_label)
    row.addWidget(w.text_align_combo)
    w.font_style_popup = panel
    return panel


def _build_units_panel(w) -> QFrame:
    """Revu's Units ▾: the units this measurement is written in — its
    length, area and volume — each the page's unless one of its own is
    picked. The value an equation reads is the same whatever is shown."""
    from ..items.measure import AREA_UNITS, LENGTH_UNITS, VOLUME_UNITS
    panel = _panel(w, "unitsPopup")
    form = QFormLayout(panel)
    form.setContentsMargins(10, 8, 10, 8)
    w.units_combos = {}
    for key, words, units in (("length", "Length:", LENGTH_UNITS),
                              ("area", "Area:", AREA_UNITS),
                              ("volume", "Volume:", VOLUME_UNITS)):
        combo = QComboBox()
        combo.setObjectName(f"units{key.title()}")
        combo.addItem("Page", "")              # the page's, worked out as it is shown
        for unit in units:
            combo.addItem(_unit_words(unit), unit)
        combo.activated.connect(lambda _i, k=key: w._units_chosen(k))
        form.addRow(words, combo)
        w.units_combos[key] = combo
    w.units_length_combo = w.units_combos["length"]
    w.units_area_combo = w.units_combos["area"]
    w.units_volume_combo = w.units_combos["volume"]
    w._units_form = form
    note = QLabel("For the selected measurements")
    note.setObjectName("unitsNote")
    form.addRow(note)
    w.units_note = note
    w.units_popup = panel
    return panel


def _unit_words(unit: str) -> str:
    """A unit as Revu's list writes it: sq m, cu m."""
    if unit.endswith("^2"):
        return f"sq {unit[:-2]}"
    if unit.endswith("^3"):
        return f"cu {unit[:-2]}"
    return unit


# ---------------------------------------------------------------------------
# what is shown for what
# ---------------------------------------------------------------------------

def kind_icon(window, item, tool_key: str = "") -> QIcon:
    """The picture of the markup's type, from the tool that draws it."""
    from .tools import TOOL_MAP
    key = tool_key
    if item is not None and not key:
        styles = getattr(window, "markup_styles", None)
        key = styles.tool_for_item(item) if styles is not None else ""
    tool = TOOL_MAP.get(key or "")
    return icon(tool.icon if tool is not None else "select", 22)


def extras_shown(items: list, active, supported: set) -> set:
    """The groups beyond the style fields that this markup (or this tool's
    next markup) has."""
    from ..items.measure import AREA, DIMENSION, VOLUME, CountItem, MeasureItem
    from ..items.text import CalloutItem, TextItem, TypewriterItem, _TextBase
    from .stylecaps import FILL, FONT, STROKE
    shown = set()
    if active is None or not supported:
        return shown
    if isinstance(active, CalloutItem):
        shown.add(SHAPE)
    if isinstance(active, (TextItem, CalloutItem)) and not isinstance(active, TypewriterItem) \
            and FONT in supported:
        shown.add(AUTO_FONT)              # Revu's "A": the words sized to the box
    if isinstance(active, _TextBase) and FONT in supported:
        shown.add(LINE_SPACING)           # Revu's Line Spacing ▾
    always_highlights = getattr(active, "kind", "") in ("highlight", "highlighter")
    if supported & {STROKE, FILL} and not isinstance(active, (_TextBase, CountItem)) \
            and not always_highlights \
            and getattr(active, "TYPE", "") not in ("link", "calc_block"):
        shown.add(HIGHLIGHT)
    if isinstance(active, MeasureItem) and active.kind in (AREA, VOLUME):
        shown.add(CUTOUT)
    if isinstance(active, MeasureItem) and active.kind != "calibrate":
        shown.add(MEASURE)
        if active.kind != DIMENSION:
            shown.add(UNITS)
    if sketched(active):
        # Revu's Sketch to Scale shapes (the user's shot of one): Add a
        # cut-out, Units ▾, Caption ▾ and Totals: Area = … ▾, as an area's
        shown |= {CUTOUT, UNITS, MEASURE}
    # a dimension is a drawing's dimension, not a take-off: Revu gives it a
    # caption but no Units or Totals
    takeoff = [i for i in items if not (isinstance(i, MeasureItem) and i.kind == DIMENSION)]
    if items and takeoff == items and all(isinstance(i, (MeasureItem, CountItem)) or sketched(i)
                                          for i in items):
        shown.add(TOTALS)
    if not items and sketched(active):
        shown.add(TOTALS)                 # Revu's: Area = 0 sq m, for the tool too

    return shown


def sketched(item) -> bool:
    """A Sketch to Scale rectangle or ellipse: drawn to a real size."""
    from ..items.shapes import RectItem
    return isinstance(item, RectItem) and bool(getattr(item, "to_scale", False))


def totals(items: list) -> list:
    """(name, total) for each kind of quantity among *items*, as Revu's
    Totals ▾ adds them up: "Area = 12.50 m²"."""
    from ..core.units import format_quantity
    from ..items.measure import ANGLE, AREA, VOLUME, CountItem, MeasureItem
    sums: dict = {}
    counts = 0
    unscaled = False
    for item in items:
        if isinstance(item, CountItem):
            counts += 1
            continue
        if sketched(item):
            # a Sketch to Scale shape's area, on a page with a scale
            area = item.area_value()
            if area is None:
                unscaled = True
                continue
            try:
                sums["Area"] = area if "Area" not in sums else sums["Area"] + area
            except Exception:  # noqa: BLE001 - areas in units that do not add
                pass
            continue
        if not isinstance(item, MeasureItem) or item.value is None:
            continue
        name = {AREA: "Area", VOLUME: "Volume", ANGLE: "Angle"}.get(item.kind, "Length")
        try:
            sums[name] = item.value if name not in sums else sums[name] + item.value
        except Exception:  # noqa: BLE001 - units that do not add (a page left unscaled)
            continue
    rows = [(name, format_quantity(total, 2, "fixed")) for name, total in sums.items()]
    if unscaled and "Area" not in sums:
        rows.append(("Area", "Scale Not Set"))
    if counts:
        rows.append(("Count", str(counts)))
    return rows


def refresh_icons(window) -> None:
    """Redraw the bar's own pictures in the theme's ink."""
    if not hasattr(window, "caption_button"):
        return
    window.caption_button.set_face(picture=_caption_icon())
    window.fit_text_button.setIcon(_fit_icon())
    window.line_spacing_combo.refresh_icons()
    for index, kind in enumerate(("box", "cloud")):
        window.callout_shape_combo.setItemIcon(index, _shape_icon(kind))
    window.highlight_button.setIcon(icon("highlighter", 20))
    window.cutout_button.setIcon(icon("cutout_polygon", 20))
    window.font_auto_button.setIcon(_auto_font_icon())
    fit_numbers(window.style_bar)          # the theme's frames, and its font
    window.cloud_spin.refresh_icons()
    import shiboken6
    from .widgets import arrow_combo
    fresh = arrow_combo()
    for combo in (window.arrow_start_combo, window.arrow_end_combo):
        for index in range(min(combo.count(), fresh.count())):
            picture = fresh.itemIcon(index)
            combo.setItemIcon(index, _mirrored(picture) if combo is window.arrow_start_combo
                              else picture)
    # Only its pictures were wanted (drawn there and then). Left to the
    # collector, a list with no parent is a window of the application's,
    # freed whenever Python next collects — once while PySide was listing
    # the application's windows, a segmentation fault (every-command runs).
    shiboken6.delete(fresh)
