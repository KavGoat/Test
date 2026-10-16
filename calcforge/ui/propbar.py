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
SHAPE = "callout_shape"
HIGHLIGHT = "highlight"
CUTOUT = "cutout"
MEASURE = "measure"
UNITS = "units"
TOTALS = "totals"


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


def _number(spin, width: int):
    spin.setFixedWidth(width)
    spin.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
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
    from .panels import _line_style_icon, fill_hatch_combo
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
        SHAPE, HATCH, HIGHLIGHT, CUTOUT, SYMBOL, UNITS, MEASURE, FONT, TOTALS)}

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

    # -- Line: colour, %, style, (cloud intensity), width, (radius) ---------
    put(STROKE, label("Line:"))
    w.stroke_button = ColorButton(style.stroke, True, "Line colour")
    w.stroke_button.colorChanged.connect(w._style_stroke)
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
    big_pattern_dropdown(w.dash_combo)
    for name in DASH_ARRAYS:
        w.dash_combo.addItem(_line_style_icon(name, _bar_ink(), 1), name.title(), name)
    w.dash_combo.currentIndexChanged.connect(
        lambda index: w._style_dash(w.dash_combo.itemData(index)) if index >= 0 else None)
    put(DASH, w.dash_combo)
    cloud_mark = QLabel()
    cloud_mark.setObjectName("cloudSizeMark")
    cloud_mark.setPixmap(icon("cloud", 18).pixmap(18, 18))
    cloud_mark.setToolTip("Cloud size")
    w._cloud_mark = cloud_mark
    put(CLOUD, cloud_mark)
    w.cloud_spin = _number(QDoubleSpinBox(), 66)
    w.cloud_spin.setObjectName("cloudSize")
    w.cloud_spin.setRange(0.1, 20.0)
    w.cloud_spin.setDecimals(2)
    w.cloud_spin.setSingleStep(0.25)
    w.cloud_spin.setValue(w.default_cloud_size)
    w.cloud_spin.setToolTip("Size: how big the cloud's scallops are")
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

    # -- Start ▾ End ▾ Auto ▾ ----------------------------------------------
    w.arrow_start_combo = _end_combo(arrow_combo(), "Start: ")
    w.arrow_end_combo = _end_combo(arrow_combo(), "End: ")
    for word, control, attribute in (("Start:", w.arrow_start_combo, "arrow_start"),
                                     ("End:", w.arrow_end_combo, "arrow_end")):
        control.currentIndexChanged.connect(
            lambda _i, name=attribute, box=control: w._style_line_ending(name, box.currentData()))
        word_action = put(ARROW_SIZE, label(word))
        if attribute == "arrow_start":
            w.arrow_start_label_action = word_action
        put(ARROW_SIZE, control)
    w.arrow_size_spin = ValueCombo(
        END_SIZES, lambda v: f"{v * 100:g}%", 0.25, 4.0, editable=False,
        first=("Auto", 1.0), width=64)
    w.arrow_size_spin.setObjectName("arrowSize")
    w.arrow_size_spin.setToolTip("End size: how big the line ends are — Auto sizes "
                                 "them from the line width")
    w.arrow_size_spin.setValue(style.arrow_size)
    w.arrow_size_spin.valueChanged.connect(w._style_arrow_size)
    put(ARROW_SIZE, w.arrow_size_spin)

    # -- Fill: colour, % -----------------------------------------------------
    put(FILL, label("Fill:"))
    w.fill_button = ColorButton("", True, "Fill colour")
    w.fill_button.colorChanged.connect(w._style_fill)
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
    w.hatch_combo.setToolTip("Hatch pattern, drawn over the fill in its own colour")
    w.hatch_combo.currentIndexChanged.connect(
        lambda _index: w._style_hatch(w.hatch_combo.currentData()))
    put(HATCH, w.hatch_combo)

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
    w.units_button.setToolTip("Units: what the measurements on this page are written in")
    w.units_button.popup_panel = _build_units_panel(w)
    w.units_button.about_to_show = w._fill_units_panel
    put(UNITS, w.units_button)
    w.caption_button = _IconOnlyPopupCombo(44)
    w.caption_button.setObjectName("measureCaption")
    w.caption_button.setIconSize(QSize(20, 20))
    w.caption_button.set_face(picture=_caption_icon())
    w.caption_button.setToolTip("Caption: whether the value is written on the drawing")
    caption_menu = QMenu(w.caption_button)
    caption_menu.setObjectName("captionMenu")
    caption_menu.setProperty("cf_context", "propbar.caption")
    w.caption_show_action = caption_menu.addAction("Show Caption")
    w.caption_show_action.setCheckable(True)
    w.caption_show_action.toggled.connect(lambda on: w._measure_setting(
        "show_label", on, "Caption"))
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
    w.font_family_combo.setFixedWidth(128)
    w.font_family_combo.currentFontChanged.connect(lambda font: w._style_change(
        FONT, lambda s: setattr(s, "font_family", font.family()), "Font"))
    put(FONT, w.font_family_combo)
    w.font_spin = ValueCombo(FONT_SIZES, lambda v: f"{v:g}", 3.0, 96.0, editable=True,
                             width=56)
    w.font_spin.setObjectName("fontSize")
    w.font_spin.setToolTip("Font size, in points")
    w.font_spin.setValue(style.font_size)
    w.font_spin.valueChanged.connect(w._style_font)
    put(FONT, w.font_spin)
    w.text_colour_button = ColorButton(style.text_color, label="Text colour")
    w.text_colour_button.colorChanged.connect(lambda value: w._style_change(
        FONT, lambda s: setattr(s, "text_color", value), "Text colour"))
    put(FONT, w.text_colour_button)
    w.font_style_button = PopupCombo("Style", 62)
    w.font_style_button.setObjectName("fontStyle")
    w.font_style_button.setToolTip("Font style: bold, italic, underline; alignment")
    w.font_style_button.popup_panel = _build_font_style_panel(w)
    put(FONT, w.font_style_button)

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
    count_button.clicked.connect(w.choose_count_subject)
    w._count_widgets = [bar.addWidget(count_button)]
    return bar


def _end_combo(combo: QComboBox, what: str) -> QComboBox:
    """An arrow_combo shown closed as only its picture, as Revu's are."""
    shown = IconCombo(60)
    shown.setProperty("what", what)
    shown.setObjectName(f"lineEnd{what.strip(': ')}")
    shown.setIconSize(QSize(30, 16))
    for index in range(combo.count()):
        picture = combo.itemIcon(index)
        if what.startswith("Start"):
            picture = _mirrored(picture)       # Revu's start ends point back: ◀—
        shown.addItem(picture, combo.itemText(index), combo.itemData(index))
    view = shown.view()
    view.setMinimumWidth(150)
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
    w.dash_scale_spin = QDoubleSpinBox()
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
    w.hatch_colour_button.colorChanged.connect(lambda value: w._style_change(
        HATCH, lambda s: setattr(s, "hatch_color", value), "Hatch colour"))
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
    w.hatch_opacity_spin = QSpinBox()
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
    """Revu's Style ▾: "Font Style: B I U", and CalcForge's alignment."""
    from .stylecaps import FONT
    panel = _panel(w, "fontStylePopup")
    row = QHBoxLayout(panel)
    row.setContentsMargins(10, 6, 10, 6)
    row.setSpacing(4)
    row.addWidget(QLabel("Font Style:"))
    w.font_buttons = {}
    for name, text in (("bold", "B"), ("italic", "I"), ("underline", "U")):
        button = QToolButton()
        button.setObjectName(f"fontStyle_{name}")
        button.setText(text)
        face = button.font()
        face.setBold(name == "bold")
        face.setItalic(name == "italic")
        face.setUnderline(name == "underline")
        button.setFont(face)
        button.setCheckable(True)
        button.setAutoRaise(True)
        button.setToolTip(name.capitalize())
        button.toggled.connect(lambda on, field=name: w._style_change(
            FONT, lambda s: setattr(s, field, on), "Font style"))
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
    """Revu's Units ▾: the length and area units — here the page's, so every
    measurement on the page is written in them."""
    from .dialogs import REAL_UNIT_NAMES
    panel = _panel(w, "unitsPopup")
    form = QFormLayout(panel)
    form.setContentsMargins(10, 8, 10, 8)
    w.units_length_combo = QComboBox()
    w.units_length_combo.setObjectName("unitsLength")
    for unit in REAL_UNIT_NAMES:
        w.units_length_combo.addItem(unit, unit)
    w.units_area_combo = QComboBox()
    w.units_area_combo.setObjectName("unitsArea")
    for unit in ("mm", "cm", "m", "km", "in", "ft", "yd", "mi"):
        w.units_area_combo.addItem(f"sq {unit}", f"{unit}^2")
    w.units_length_combo.activated.connect(lambda _i: w._units_chosen())
    w.units_area_combo.activated.connect(lambda _i: w._units_chosen())
    form.addRow("Length:", w.units_length_combo)
    form.addRow("Area:", w.units_area_combo)
    note = QLabel("For every measurement on this page")
    note.setObjectName("unitsNote")
    form.addRow(note)
    w.units_popup = panel
    return panel


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
    from ..items.text import CalloutItem, _TextBase
    from .stylecaps import FILL, STROKE
    shown = set()
    if active is None or not supported:
        return shown
    if isinstance(active, CalloutItem):
        shown.add(SHAPE)
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
    # a dimension is a drawing's dimension, not a take-off: Revu gives it a
    # caption but no Units or Totals
    takeoff = [i for i in items if not (isinstance(i, MeasureItem) and i.kind == DIMENSION)]
    if items and takeoff == items and all(isinstance(i, (MeasureItem, CountItem)) for i in items):
        shown.add(TOTALS)

    return shown


def totals(items: list) -> list:
    """(name, total) for each kind of quantity among *items*, as Revu's
    Totals ▾ adds them up: "Area = 12.50 m²"."""
    from ..core.units import format_quantity
    from ..items.measure import ANGLE, AREA, VOLUME, CountItem, MeasureItem
    sums: dict = {}
    counts = 0
    for item in items:
        if isinstance(item, CountItem):
            counts += 1
            continue
        if not isinstance(item, MeasureItem) or item.value is None:
            continue
        name = {AREA: "Area", VOLUME: "Volume", ANGLE: "Angle"}.get(item.kind, "Length")
        try:
            sums[name] = item.value if name not in sums else sums[name] + item.value
        except Exception:  # noqa: BLE001 - units that do not add (a page left unscaled)
            continue
    rows = [(name, format_quantity(total, 2, "fixed")) for name, total in sums.items()]
    if counts:
        rows.append(("Count", str(counts)))
    return rows


def refresh_icons(window) -> None:
    """Redraw the bar's own pictures in the theme's ink."""
    if not hasattr(window, "caption_button"):
        return
    window.caption_button.set_face(picture=_caption_icon())
    window.fit_text_button.setIcon(_fit_icon())
    for index, kind in enumerate(("box", "cloud")):
        window.callout_shape_combo.setItemIcon(index, _shape_icon(kind))
    window.highlight_button.setIcon(icon("highlighter", 20))
    window.cutout_button.setIcon(icon("cutout_polygon", 20))
    window._cloud_mark.setPixmap(icon("cloud", 18).pixmap(18, 18))
    from .widgets import arrow_combo
    fresh = arrow_combo()
    for combo in (window.arrow_start_combo, window.arrow_end_combo):
        for index in range(min(combo.count(), fresh.count())):
            picture = fresh.itemIcon(index)
            combo.setItemIcon(index, _mirrored(picture) if combo is window.arrow_start_combo
                              else picture)
