"""Modal dialogs: page setup, scale, PDF import, document properties and more."""
from __future__ import annotations

import html
import os
import re
from typing import Optional

from PySide6.QtCore import QEvent, QKeyCombination, Qt, Signal
from PySide6.QtGui import QFont, QKeySequence, QPalette
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QMenu,
                               QPlainTextEdit,
                               QDialog,
                               QDialogButtonBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton,
                               QRadioButton, QSpinBox, QStackedWidget, QStyle,
                               QStyledItemDelegate,
                               QTableWidget, QTableWidgetItem,
                               QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ..core.document import (PAGE_SIZES, PAPER_UNITS, PageScale, PageSetup)
from ..core.units import parse_unit, unit_text
from ..io import pdfio
from .widgets import PagesRange, UnitCombo, page_ranges  # noqa: F401


def _buttons(dialog: QDialog) -> QDialogButtonBox:
    box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)
    return box


# Revu's Page Setup — the media, the content resized onto it, a Preview and
# the Pages range — lives in pagesetup.py; the old name stays for what used it.
from .pagesetup import PageSetupDialog  # noqa: E402,F401


# The shared Pages control (Revu's All Pages / Current / Selected / Custom)
# lives in widgets.py; the old name stays for what used it.
PagesChooser = PagesRange


# Revu's Set Scale (the user, 2026-10-15: "page scale pop up doesn't look
# like" Bluebeam's). Its presets are the common metric, architectural and
# engineering scales; the ones somebody saves go at the top, each with a
# delete button. A preset is (name, paper length, paper unit, real length,
# real unit); a metric one is just its ratio.
FEET_INCHES = "ft' in\""
METRIC_SCALES = (1, 2, 5, 10, 20, 25, 50, 75, 100, 125, 150, 200, 250, 500, 1000,
                 1250, 2000, 2500, 5000)
ARCHITECTURAL_SCALES = (("1/32\" = 1'-0\"", 1 / 32), ("1/16\" = 1'-0\"", 1 / 16),
                        ("3/32\" = 1'-0\"", 3 / 32), ("1/8\" = 1'-0\"", 1 / 8),
                        ("3/16\" = 1'-0\"", 3 / 16), ("1/4\" = 1'-0\"", 1 / 4),
                        ("3/8\" = 1'-0\"", 3 / 8), ("1/2\" = 1'-0\"", 1 / 2),
                        ("3/4\" = 1'-0\"", 3 / 4), ("1\" = 1'-0\"", 1.0),
                        ("1 1/2\" = 1'-0\"", 1.5), ("3\" = 1'-0\"", 3.0),
                        ("6\" = 1'-0\"", 6.0), ("12\" = 1'-0\"", 12.0))
ENGINEERING_SCALES = (10, 20, 30, 40, 50, 60, 100, 200, 500, 1000)
PAPER_UNIT_NAMES = ("mm", "cm", "in", "pt")
REAL_UNIT_NAMES = ("mm", "cm", "m", "km", "in", "ft", FEET_INCHES, "yd", "mi")
METRIC_UNITS = ("mm", "cm", "m", "km")
# Revu's Precision: decimals for most units, fractions of an inch for
# feet-and-inches and inches.
DECIMAL_PRECISIONS = ("1", "0.1", "0.01", "0.001", "0.0001", "0.00001", "0.000001")
FRACTION_PRECISIONS = (1, 2, 4, 8, 16, 32, 64)
PRESETS_KEY = "scale/presets"


def builtin_presets() -> list:
    """Every preset Revu comes with: (name, paper, paper unit, real, real unit)."""
    presets = [(f"1:{n}", 1.0, "mm", float(n), "mm") for n in METRIC_SCALES]
    presets += [(name, inches, "in", 1.0, FEET_INCHES) for name, inches in ARCHITECTURAL_SCALES]
    presets += [(f"1\" = {n}'", 1.0, "in", float(n), "ft") for n in ENGINEERING_SCALES]
    return presets


def saved_scale_presets() -> list:
    """The scales saved with + Add Preset, newest first: [{name, paper, ...}]."""
    import json
    from ..settings import app_settings
    try:
        stored = json.loads(app_settings().value(PRESETS_KEY, "[]") or "[]")
    except (TypeError, ValueError):
        return []
    return [entry for entry in stored if isinstance(entry, dict) and entry.get("name")]


def store_scale_presets(presets: list) -> None:
    import json
    from ..settings import app_settings
    settings = app_settings()
    settings.setValue(PRESETS_KEY, json.dumps(presets))
    settings.sync()


def read_number(text: str) -> Optional[float]:
    """"2.5", "1/4" or "1 1/2" as a number; None if it is not one."""
    text = (text or "").strip()
    try:
        return float(text)
    except ValueError:
        pass
    match = re.fullmatch(r"(?:(\d+(?:\.\d*)?)\s+)?(\d+)\s*/\s*(\d+)", text)
    if not match or not int(match.group(3)):
        return None
    return float(match.group(1) or 0) + int(match.group(2)) / int(match.group(3))


def number_text(value: float) -> str:
    return f"{float(f'{value:.6g}'):g}"


_DELETE_ROLE = Qt.UserRole + 1


class _PresetDelegate(QStyledItemDelegate):
    """Draws the delete button at the right of a saved preset's row."""

    @staticmethod
    def _separator(index) -> bool:
        return index.data(Qt.AccessibleDescriptionRole) == "separator"

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        if self._separator(index):
            size.setHeight(9)
            return size
        size.setHeight(max(size.height() + 6, 24))
        size.setWidth(size.width() + 34)
        return size

    def paint(self, painter, option, index):
        if self._separator(index):
            painter.save()
            painter.setPen(option.palette.color(QPalette.Mid))
            middle = option.rect.center().y()
            painter.drawLine(option.rect.left() + 6, middle, option.rect.right() - 6, middle)
            painter.restore()
            return
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.color(QPalette.Highlight))
        painter.save()
        painter.setPen(option.palette.color(
            QPalette.HighlightedText if option.state & QStyle.State_Selected else QPalette.Text))
        painter.drawText(option.rect.adjusted(8, 0, -26, 0), Qt.AlignVCenter | Qt.AlignLeft,
                         index.data(Qt.DisplayRole) or "")
        if index.data(_DELETE_ROLE):
            font = painter.font()
            if font.pointSizeF() > 0:
                font.setPointSizeF(font.pointSizeF() + 1)
            elif font.pixelSize() > 0:
                font.setPixelSize(font.pixelSize() + 1)
            painter.setFont(font)
            painter.drawText(PresetCombo.delete_rect(option.rect), Qt.AlignCenter, "✕")
        painter.restore()


class PresetCombo(QComboBox):
    """The Scale dropdown: saved scales at the top, each with a delete
    button, then Revu's own, which cannot be deleted."""

    deleteRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("scalePreset")
        self.setItemDelegate(_PresetDelegate(self))
        self.view().viewport().installEventFilter(self)
        # a list of sixteen rows that scrolls, not one the height of the screen
        self.setStyleSheet("QComboBox { combobox-popup: 0; }")
        self.setMaxVisibleItems(16)
        self.setMinimumContentsLength(14)
        self.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)

    @staticmethod
    def delete_rect(rect):
        return rect.adjusted(rect.width() - 22, 0, 0, 0)

    def fill(self, saved: list) -> None:
        chosen = self.currentText()
        was = self.blockSignals(True)
        self.clear()
        for entry in saved:
            self.addItem(entry["name"], ("saved", entry))
            self.setItemData(self.count() - 1, True, _DELETE_ROLE)
            self.setItemData(self.count() - 1, "Saved preset — ✕ deletes it", Qt.ToolTipRole)
        for group in (METRIC_SCALES, ARCHITECTURAL_SCALES, ENGINEERING_SCALES):
            if self.count():
                self.insertSeparator(self.count())
            for preset in builtin_presets():
                kind = (METRIC_SCALES if preset[2] == "mm" else
                        ARCHITECTURAL_SCALES if preset[4] == FEET_INCHES else ENGINEERING_SCALES)
                if kind is group:
                    self.addItem(preset[0], ("builtin", preset))
        index = self.findText(chosen)
        self.setCurrentIndex(index if index >= 0 else self.findText("1:100"))
        self.blockSignals(was)

    def eventFilter(self, watched, event):
        # A click on a saved preset's ✕ deletes it rather than choosing it.
        if event.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
            view = self.view()
            index = view.indexAt(event.position().toPoint())
            if index.isValid() and index.data(_DELETE_ROLE) and \
                    self.delete_rect(view.visualRect(index)).contains(event.position().toPoint()):
                if event.type() == QEvent.MouseButtonRelease:
                    self.deleteRequested.emit(index.data(Qt.DisplayRole))
                return True
        return super().eventFilter(watched, event)


class _ScaleRow:
    """One scale, X or Y: Preset or Custom; a preset from the Scale
    dropdown, or [drawing length][unit] = [real-world length][unit] with
    Calibrate beside it."""

    def __init__(self, dialog: "ScaleDialog", axis: str, calibrate: bool):
        self.dialog = dialog
        self.axis = axis
        self.measured_pt: Optional[float] = None
        self.radios = QWidget()
        radios = QHBoxLayout(self.radios)
        radios.setContentsMargins(0, 0, 0, 0)
        self.preset_choice = QRadioButton("Preset")
        self.custom_choice = QRadioButton("Custom")
        self.group = QButtonGroup(self.radios)
        for button in (self.preset_choice, self.custom_choice):
            self.group.addButton(button)
            radios.addWidget(button)
        radios.addStretch(1)
        self.label = QLabel("Scale:")
        self.stack = QStackedWidget()
        self.preset = PresetCombo()
        self.preset.setObjectName(f"scalePreset{axis.upper()}")
        self.stack.addWidget(self.preset)
        custom = QWidget()
        equation = QHBoxLayout(custom)
        equation.setContentsMargins(0, 0, 0, 0)
        equation.setSpacing(4)
        self.page_length = QLineEdit("1")
        self.page_length.setObjectName(f"scalePageLength{axis.upper()}")
        self.page_length.setToolTip("The length on the drawing")
        self.page_unit = QComboBox()
        self.page_unit.addItems(PAPER_UNIT_NAMES)
        self.real_length = QLineEdit()
        self.real_length.setObjectName(f"scaleRealLength{axis.upper()}")
        self.real_length.setToolTip("The real-world length it stands for")
        # after Calibrate the box waits for the known length (F-36: it read
        # as "60.69 mm = [nothing] mm")
        self.real_length.setPlaceholderText("real length")
        self.real_unit = QComboBox()
        self.real_unit.addItems(REAL_UNIT_NAMES)
        for box in (self.page_length, self.real_length):
            box.setMaximumWidth(84)
            box.setMinimumWidth(56)
        equation.addWidget(self.page_length)
        equation.addWidget(self.page_unit)
        equation.addWidget(QLabel("="))
        equation.addWidget(self.real_length)
        equation.addWidget(self.real_unit)
        self.calibrate = QPushButton("Calibrate")
        self.calibrate.setToolTip(
            "Pick two points on the drawing to calibrate its scale: click one "
            "end of something you know the length of, then the other, then "
            "type that length")
        self.calibrate.clicked.connect(lambda: dialog.start_calibrating(axis))
        self.calibrate.setVisible(calibrate)
        equation.addWidget(self.calibrate)
        equation.addStretch(1)
        self.stack.addWidget(custom)
        self.preset_choice.toggled.connect(self._mode_changed)
        self.preset.currentIndexChanged.connect(lambda _i: dialog.scale_changed())
        self.real_unit.currentIndexChanged.connect(lambda _i: dialog.scale_changed())
        self.preset.deleteRequested.connect(dialog.delete_preset)

    # -- what it shows -----------------------------------------------------
    def widgets(self) -> tuple:
        return (self.radios, self.label, self.stack)

    def set_visible(self, on: bool) -> None:
        for widget in self.widgets():
            widget.setVisible(on)

    def is_custom(self) -> bool:
        return self.custom_choice.isChecked()

    def set_custom(self, on: bool) -> None:
        (self.custom_choice if on else self.preset_choice).setChecked(True)
        self._mode_changed()

    def _mode_changed(self, *_args) -> None:
        self.stack.setCurrentIndex(1 if self.is_custom() else 0)
        self.dialog.scale_changed()

    def show_scale(self, label: str, per_pt, display_unit: str, calibrated: bool) -> None:
        """Put *label*'s scale in the row: as its preset when it is one,
        otherwise as an equation."""
        index = self.preset.findText(label) if label else -1
        if not calibrated:
            self.preset.setCurrentIndex(max(self.preset.findText("1:100"), 0))
            self.set_custom(False)
            return
        if index >= 0:
            self.preset.setCurrentIndex(index)
            self.set_custom(False)
            return
        match = re.fullmatch(r"\s*([\d./ ]+?)\s*(mm|cm|in|pt)\s*=\s*([\d./ ]+?)\s*(.+?)\s*",
                             label or "")
        if match and match.group(4) in REAL_UNIT_NAMES:
            self.page_length.setText(match.group(1))
            self.page_unit.setCurrentText(match.group(2))
            self.real_length.setText(match.group(3))
            self.real_unit.setCurrentText(match.group(4))
        else:
            # a calibrated or older scale: one paper unit and what it stands for
            unit = display_unit if display_unit in REAL_UNIT_NAMES else "m"
            paper = "mm" if unit in METRIC_UNITS else "in"
            self.page_length.setText("1")
            self.page_unit.setCurrentText(paper)
            try:
                real = float((per_pt * PAPER_UNITS[paper]).to(
                    "ft" if unit == FEET_INCHES else unit).magnitude)
            except Exception:                             # noqa: BLE001
                real = 0.0
            self.real_length.setText(number_text(real) if real else "")
            self.real_unit.setCurrentText(unit)
        self.set_custom(True)

    def set_measured(self, measured_pt: float) -> None:
        """Calibrate's two points: the measured length on the left, the
        real one to be typed on the right."""
        self.measured_pt = measured_pt
        unit = self.page_unit.currentText() or "mm"
        if self.real_unit.currentText() not in METRIC_UNITS and unit == "mm":
            unit = "in"
        self.page_unit.setCurrentText(unit)
        self._measured_text = number_text(measured_pt / PAPER_UNITS[unit])
        self.page_length.setText(self._measured_text)
        self.real_length.clear()
        self.set_custom(True)
        self.real_length.setFocus()

    def real_unit_name(self) -> str:
        """The real-world unit this row is in, as the unit boxes write it."""
        if self.is_custom():
            return self.real_unit.currentText()
        data = self.preset.currentData()
        if not data:
            return "m"
        if data[0] == "saved":
            return data[1].get("real_unit", "m")
        return data[1][4]

    # -- the scale it says ---------------------------------------------------
    def scale(self) -> tuple[Optional[PageScale], str]:
        """(the scale, "") or (None, what is wrong with it)."""
        if not self.is_custom():
            data = self.preset.currentData()
            if not data:
                return None, "Choose a scale from the list."
            kind, preset = data
            if kind == "saved":
                return self._from_equation(preset.get("paper", 1.0), preset.get("paper_unit", "mm"),
                                           preset.get("real", 1.0), preset.get("real_unit", "mm"),
                                           preset["name"])
            name, paper, paper_unit, real, real_unit = preset
            if paper_unit == "mm" and real_unit == "mm":
                return PageScale.from_ratio(real / paper), ""
            return self._from_equation(paper, paper_unit, real, real_unit, name)
        page = read_number(self.page_length.text())
        if self.measured_pt and self.page_length.text() == getattr(self, "_measured_text", None):
            page = self.measured_pt / PAPER_UNITS[self.page_unit.currentText()]
        if not page or page <= 0:
            return None, "Enter the drawing length on the left, such as 1."
        text = self.real_length.text().strip()
        real = read_number(text)
        unit = self.real_unit.currentText()
        if real is None:
            # "10 m" or "10mm" typed whole, its unit with it
            try:
                quantity = parse_unit(text)
                valid = quantity is not None and quantity.check("[length]")
            except Exception:                             # noqa: BLE001
                valid = False
            if not valid:
                return None, ("Enter the real-world length with compatible units, "
                              "such as 10 mm or 2 m.")
            unit = unit_text(quantity.units, plain=False) or unit
            real = float(quantity.magnitude)
        if real <= 0:
            return None, "Enter the real-world length on the right, such as 50."
        shown = self.page_length.text().strip() if self.measured_pt is None or \
            self.page_length.text() != getattr(self, "_measured_text", None) else number_text(page)
        label = f"{shown} {self.page_unit.currentText()} = {number_text(real)} {unit}"
        return self._from_equation(page, self.page_unit.currentText(), real, unit, label)

    @staticmethod
    def _from_equation(paper, paper_unit, real, real_unit, label):
        try:
            scale = PageScale.from_equation(
                float(paper), paper_unit, float(real),
                "ft" if real_unit == FEET_INCHES else real_unit, label)
            scale.length(1.0).to("mm")
        except Exception:                                 # noqa: BLE001
            return None, f"“{real_unit}” is not a length unit."
        return scale, ""

    def equation(self) -> Optional[dict]:
        """This row's Custom scale as a preset to save."""
        scale, problem = self.scale()
        if scale is None or problem:
            return None
        page = read_number(self.page_length.text()) or 1.0
        if self.measured_pt and self.page_length.text() == getattr(self, "_measured_text", None):
            page = self.measured_pt / PAPER_UNITS[self.page_unit.currentText()]
        real_unit = self.real_unit.currentText()
        real = read_number(self.real_length.text())
        if real is None:
            quantity = parse_unit(self.real_length.text())
            real = float(quantity.magnitude)
            real_unit = unit_text(quantity.units, plain=False) or real_unit
        return {"name": scale.label, "paper": page, "paper_unit": self.page_unit.currentText(),
                "real": real, "real_unit": real_unit}

    # -- across a calibration ----------------------------------------------------
    def state(self) -> dict:
        return {"custom": self.is_custom(), "preset": self.preset.currentText(),
                "page": self.page_length.text(), "page_unit": self.page_unit.currentText(),
                "real": self.real_length.text(), "real_unit": self.real_unit.currentText()}

    def restore(self, state: dict) -> None:
        index = self.preset.findText(state.get("preset", ""))
        if index >= 0:
            self.preset.setCurrentIndex(index)
        self.page_length.setText(state.get("page", "1"))
        self.page_unit.setCurrentText(state.get("page_unit", "mm"))
        self.real_length.setText(state.get("real", ""))
        self.real_unit.setCurrentText(state.get("real_unit", "m"))
        self.set_custom(bool(state.get("custom")))


class ScaleDialog(QDialog):
    """Revu's Set Scale: the Pages it goes to; Preset (the Scale dropdown,
    saved scales at the top) or Custom ([drawing length][unit] =
    [real-world length][unit], with Calibrate); Separate Y Scale with a
    second scale for down the page; Precision, decimals or fractions; then
    + Add Preset, Apply Scale and Cancel (the user, 2026-10-15).

    Calibrate closes the dialog with PICK; the window hands over to the
    calibrate tool, and when the two points are picked it opens the dialog
    again with what was chosen and the measured length on the left.
    A viewport's scale uses the same dialog with its name above, and no
    pages or calibration of its own.
    """

    # Kept for the Page panel's ratio boxes.
    RATIOS = ["1:1", "1:5", "1:10", "1:20", "1:25", "1:50", "1:100", "1:200",
              "1:250", "1:500", "1:1000", "1:1250", "1:2500"]

    PICK = QDialog.Accepted + 10        # "let me point at two things instead"

    def __init__(self, scale: PageScale, measured_pt: Optional[float] = None, parent=None,
                 name: Optional[str] = None, *, count: int = 1, current: int = 0,
                 selected=None, state: Optional[dict] = None):
        super().__init__(parent)
        self.setWindowTitle("Set Scale" if name is None else "Viewport")
        self.old = scale
        self.measured_pt = measured_pt
        self.calibrating = ""
        self._result: Optional[PageScale] = None
        viewport = name is not None
        layout = QVBoxLayout(self)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        row = 0
        # A viewport is named and given a scale; it has no pages to choose.
        self.name = QLineEdit(name or "")
        self.name.setToolTip("What this region of the sheet is, e.g. Detail A")
        if viewport:
            grid.addWidget(QLabel("Name:"), row, 0)
            grid.addWidget(self.name, row, 1)
            row += 1
        else:
            self.name.hide()
        self.pages = PagesRange(count, current, selected)
        if not viewport:
            grid.addWidget(QLabel("Pages:"), row, 0)
            grid.addWidget(self.pages, row, 1)
            row += 1
        else:
            self.pages.hide()

        self.x_row = _ScaleRow(self, "x", calibrate=not viewport)
        self.y_row = _ScaleRow(self, "y", calibrate=not viewport)
        saved = saved_scale_presets()
        for scale_row in (self.x_row, self.y_row):
            scale_row.preset.fill(saved)
        self.x_row.radios.setObjectName("scaleModeX")
        grid.addWidget(self.x_row.radios, row, 1)
        row += 1
        grid.addWidget(self.x_row.label, row, 0)
        grid.addWidget(self.x_row.stack, row, 1)
        row += 1
        self.separate_y = QCheckBox("Separate Y Scale")
        self.separate_y.setToolTip("A different scale down the page than across it")
        grid.addWidget(self.separate_y, row, 1)
        row += 1
        grid.addWidget(self.y_row.radios, row, 1)
        row += 1
        grid.addWidget(self.y_row.label, row, 0)
        grid.addWidget(self.y_row.stack, row, 1)
        row += 1
        self.y_row.label.setText("Y Scale:")
        self.precision = QComboBox()
        self.precision.setObjectName("scalePrecision")
        self.precision.setToolTip("How finely measurements are written")
        self.precision.setMinimumContentsLength(9)
        grid.addWidget(QLabel("Precision:"), row, 0)
        grid.addWidget(self.precision, row, 1, Qt.AlignLeft)
        # The old name, for what still sets the X scale's preset by it.
        self.ratio = self.x_row.preset

        buttons = QHBoxLayout()
        self.add_preset = QPushButton("+ Add Preset")
        self.add_preset.setObjectName("scaleAddPreset")
        self.add_preset.setToolTip("Save this custom or calibrated scale to the "
                                   "top of the Preset list")
        self.add_preset.clicked.connect(self.save_preset)
        buttons.addWidget(self.add_preset)
        buttons.addStretch(1)
        self.apply_button = QPushButton("Apply Scale")
        self.apply_button.setObjectName("scaleApply")
        self.apply_button.setDefault(True)
        self.apply_button.clicked.connect(self.apply)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(self.apply_button)
        buttons.addWidget(cancel)
        layout.addSpacing(4)
        layout.addLayout(buttons)

        # what the page has now
        self._filling = True
        label = scale.label or ""
        both = re.fullmatch(r"X (.+), Y (.+)", label)
        self.x_row.show_scale(both.group(1) if both else label, scale.length_per_pt,
                              scale.display_unit, scale.is_calibrated())
        y_per_pt = scale.length_per_pt * scale.y_factor
        self.y_row.show_scale(both.group(2) if both else label, y_per_pt,
                              scale.display_unit, scale.is_calibrated())
        self.separate_y.setChecked(scale.is_calibrated() and scale.separate_y())
        self._precision_kind = None
        self._filling = False
        self.separate_y.toggled.connect(lambda _on: self.scale_changed())
        if state:
            self.restore(state)
        if measured_pt:
            row_measured = self.y_row if self.calibrating == "y" else self.x_row
            if not self.separate_y.isChecked():
                row_measured = self.x_row
            row_measured.set_measured(measured_pt)
        self.scale_changed()

    # -- keeping it in step ---------------------------------------------------
    def scale_changed(self) -> None:
        if getattr(self, "_filling", True):
            return
        separate = self.separate_y.isChecked()
        self.y_row.set_visible(separate)
        self.x_row.label.setText("X Scale:" if separate else "Scale:")
        self.add_preset.setEnabled(self.x_row.is_custom())
        self._fill_precision()
        self.adjustSize()

    def _wants_fraction(self) -> bool:
        """Revu writes feet-and-inches and inches to a fraction; everything
        else to decimals (of the X scale, when there are two)."""
        unit = self.x_row.real_unit_name()
        if not self.x_row.is_custom():
            data = self.x_row.preset.currentData()
            if data and data[0] == "saved" and data[1].get("fraction"):
                return True
        return unit in (FEET_INCHES, "in")

    def _fill_precision(self) -> None:
        fraction = self._wants_fraction()
        kind = "fraction" if fraction else "decimal"
        if kind == self._precision_kind:
            return
        self._precision_kind = kind
        self.precision.clear()
        if fraction:
            for denominator in FRACTION_PRECISIONS:
                self.precision.addItem("1" if denominator == 1 else f"1/{denominator}",
                                       ("fraction", denominator))
            wanted = self.old.fraction if getattr(self.old, "fraction", 0) else 16
            self.precision.setCurrentIndex(FRACTION_PRECISIONS.index(wanted)
                                           if wanted in FRACTION_PRECISIONS else 4)
        else:
            for places, text in enumerate(DECIMAL_PRECISIONS):
                self.precision.addItem(text, ("decimal", places))
            wanted = min(max(int(self.old.precision), 0), len(DECIMAL_PRECISIONS) - 1)
            self.precision.setCurrentIndex(wanted)

    def set_precision(self, text: str) -> bool:
        """Choose a Precision by what it says: "0.001", "1/8"."""
        index = self.precision.findText(text)
        if index < 0:
            return False
        self.precision.setCurrentIndex(index)
        return True

    # -- Calibrate, + Add Preset, the ✕ beside a saved one ------------------------------
    def start_calibrating(self, axis: str = "x") -> None:
        self.calibrating = axis
        self.done(self.PICK)

    def state(self) -> dict:
        """Everything chosen, to put back after calibrating."""
        return {"pages": self.pages.which(), "range": self.pages.range.text(),
                "separate_y": self.separate_y.isChecked(), "x": self.x_row.state(),
                "y": self.y_row.state(), "precision": self.precision.currentText(),
                "calibrating": self.calibrating}

    def restore(self, state: dict) -> None:
        self._filling = True
        self.pages.choose(state.get("pages", PagesRange.CURRENT), state.get("range"))
        self.separate_y.setChecked(bool(state.get("separate_y")))
        self.x_row.restore(state.get("x", {}))
        self.y_row.restore(state.get("y", {}))
        self.calibrating = state.get("calibrating", "")
        self._filling = False
        self.scale_changed()
        self.set_precision(state.get("precision", ""))

    def save_preset(self) -> Optional[dict]:
        """+ Add Preset: the custom or calibrated X scale, to the top of the list."""
        entry = self.x_row.equation()
        if entry is None:
            _scale, problem = self.x_row.scale()
            QMessageBox.warning(self, "Set Scale", problem or "Enter a custom scale first.")
            return None
        entry["fraction"] = self._chosen_fraction()
        presets = [p for p in saved_scale_presets() if p.get("name") != entry["name"]]
        store_scale_presets([entry] + presets)
        self._refill_presets()
        return entry

    def delete_preset(self, name: str) -> None:
        store_scale_presets([p for p in saved_scale_presets() if p.get("name") != name])
        self._refill_presets()

    def _refill_presets(self) -> None:
        saved = saved_scale_presets()
        for scale_row in (self.x_row, self.y_row):
            scale_row.preset.fill(saved)
        self.scale_changed()

    def _chosen_fraction(self) -> int:
        data = self.precision.currentData()
        return int(data[1]) if data and data[0] == "fraction" else 0

    # -- the answer ---------------------------------------------------------
    def apply(self) -> None:
        """Apply Scale: only once the scale and the pages both read."""
        if self.result_scale() is None:
            return
        if self.pages.isVisibleTo(self) and not self.page_indexes():
            QMessageBox.warning(self, "Set Scale",
                                "Enter pages to apply it to, such as 1-3, 5.")
            return
        self.accept()

    def page_indexes(self) -> Optional[list]:
        return self.pages.page_indexes()

    def result_scale(self) -> Optional[PageScale]:
        x_scale, problem = self.x_row.scale()
        if x_scale is None:
            QMessageBox.warning(self, "Set Scale", problem)
            return None
        scale = x_scale
        if self.separate_y.isChecked():
            y_scale, problem = self.y_row.scale()
            if y_scale is None:
                QMessageBox.warning(self, "Set Scale", problem)
                return None
            try:
                factor = float((y_scale.length(1.0) / x_scale.length(1.0))
                               .to("dimensionless").magnitude)
            except Exception:                             # noqa: BLE001
                factor = 1.0
            if abs(factor - 1.0) > 1e-9:
                scale.y_factor = factor
                scale.label = f"X {x_scale.label}, Y {y_scale.label}"
        # A metric preset is in the units the page already used, if metric;
        # anything else is in its own real-world unit.
        old_unit = self.old.display_unit
        if scale.label.startswith("1:") or scale.label.startswith("X 1:"):
            scale.display_unit = old_unit if old_unit in METRIC_UNITS else "m"
        if scale.display_unit == self.old.display_unit:
            scale.area_unit = self.old.area_unit
        else:
            scale.area_unit = f"{scale.display_unit}^2"
        data = self.precision.currentData() or ("decimal", self.old.precision)
        if data[0] == "fraction":
            scale.fraction = int(data[1])
            scale.precision = self.old.precision        # areas stay in decimals
        else:
            scale.fraction = 0
            scale.precision = int(data[1])
        self._result = scale
        return scale


def ratio_text(ratio: Optional[float]) -> str:
    """100 as "1:100"; a calibrated scale's odd ratio kept to four figures."""
    if not ratio:
        return "1:1"
    return f"1:{float(f'{ratio:.4g}'):g}"


def read_ratio(text: str) -> Optional[float]:
    """"1:100", "100" or "2:1" as the real-to-page ratio; None if unreadable."""
    parts = (text or "").replace(" ", "").split(":")
    try:
        if len(parts) == 2:
            page, real = float(parts[0]), float(parts[1])
            ratio = real / page if page else None
        elif len(parts) == 1:
            ratio = float(parts[0])
        else:
            return None
    except ValueError:
        return None
    return ratio if ratio and ratio > 0 else None


# Insert field…: MarkForge's fields and SMath's (its Insert > Field dialog, with
# its formats), as header/footer tokens.
FIELD_CHOICES = [
    ("Title", "{title}"), ("Project", "{project}"), ("Author", "{author}"),
    ("Company", "{company}"), ("Subject", "{subject}"), ("Keywords", "{keywords}"),
    ("Description", "{description}"), ("Revision", "{revision}"),
    ("Document id", "{id}"), ("File name", "{filename}"),
    ("Page number", "{page}"), ("Page number, 0001", "{page:0000}"),
    ("Number of pages", "{pages}"), ("Page n of m", "Page {page} of {pages}"),
    ("Date, DD.MM.YYYY", "{date:DD.MM.YYYY}"), ("Date, DD/MM/YYYY", "{date:DD/MM/YYYY}"),
    ("Date, YYYY-MM-DD", "{date:YYYY-MM-DD}"), ("Date, DD MMMM YYYY", "{date:DD MMMM YYYY}"),
    ("Time, HH:mm", "{time:HH:mm}"), ("Time, hh:mm tt", "{time:hh:mm tt}"),
]


class DocumentPropertiesDialog(QDialog):
    """Title block information, running headers and markup defaults."""

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Document Properties")
        self.document = document
        self.resize(900, 660)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs, 1)
        self.tabs = tabs

        info = QWidget()
        info_form = QFormLayout(info)
        self.title = QLineEdit(document.title)
        self.author = QLineEdit(document.author)
        self.subject = QLineEdit(document.subject)
        self.project = QLineEdit(document.project)
        # MarkForge's and SMath's properties in one place (decision 28).
        self.company = QLineEdit(document.company)
        self.keywords = QLineEdit(document.keywords)
        self.keywords.setToolTip("Also the PDF's own Keywords, which any reader shows")
        self.description = QPlainTextEdit(document.description)
        self.description.setObjectName("propertiesDescription")
        self.description.setMaximumHeight(90)
        for edit, tip in ((self.title, "Also the PDF's own Title"),
                          (self.author, "Also the PDF's own Author"),
                          (self.subject, "Also the PDF's own Subject")):
            edit.setToolTip(tip)
        info_form.addRow("Title", self.title)
        info_form.addRow("Project", self.project)
        info_form.addRow("Author", self.author)
        info_form.addRow("Company", self.company)
        info_form.addRow("Subject", self.subject)
        info_form.addRow("Keywords", self.keywords)
        info_form.addRow("Description", self.description)
        revision = QLabel(str(document.revision) if document.revision else "not saved yet")
        revision.setObjectName("propertiesRevision")
        revision.setToolTip("Goes up by one every time the document is saved, as in SMath")
        info_form.addRow("Revision", revision)
        ident = QLabel(document.doc_id or "given on the first save")
        ident.setTextInteractionFlags(Qt.TextSelectableByMouse)
        info_form.addRow("Document id", ident)
        note = QLabel("Title, author, subject and keywords also go into the PDF's own "
                      "properties. Every one of these can be a header or footer field.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#5a6270;")
        info_form.addRow(note)
        tabs.addTab(info, "Information")

        running = QWidget()
        running_form = QFormLayout(running)
        settings = document.settings
        self.show_header = QCheckBox("Show header")
        self.show_header.setToolTip("Show a header on every page")
        self.show_header.setChecked(settings.show_header)
        self.show_footer = QCheckBox("Show footer")
        self.show_footer.setToolTip("Show a footer on every page")
        self.show_footer.setChecked(settings.show_footer)
        running_form.addRow(self.show_header)
        self.header_fields = []
        for label, value in (("Header left", settings.header_left),
                             ("Header centre", settings.header_center),
                             ("Header right", settings.header_right)):
            edit = QLineEdit(value)
            running_form.addRow(label, edit)
            self.header_fields.append(edit)
        running_form.addRow(self.show_footer)
        self.footer_fields = []
        for label, value in (("Footer left", settings.footer_left),
                             ("Footer centre", settings.footer_center),
                             ("Footer right", settings.footer_right)):
            edit = QLineEdit(value)
            running_form.addRow(label, edit)
            self.footer_fields.append(edit)
        hint = QLabel("Fields: {title} {project} {author} {company} {subject} {keywords} "
                      "{description} {revision} {id} {page} {pages} {date} {time} {file} "
                      "{filename}. SMath's formats go after a colon: {date:DD.MM.YYYY}, "
                      "{time:HH:mm}, {page:0001}, {page:-1}.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#5a6270;")
        running_form.addRow(hint)
        # SMath's Insert > Field, into whichever slot was typed in last
        self._slot = self.header_fields[1]
        for edit in self.header_fields + self.footer_fields:
            edit.installEventFilter(self)
        insert_field = QPushButton("Insert field…")
        insert_field.setObjectName("insertField")
        insert_field.setToolTip("SMath's fields, with their formats, into the slot typed in last")
        field_menu = QMenu(insert_field)
        for label, token in FIELD_CHOICES:
            field_menu.addAction(label, lambda t=token: self.insert_field(t))
        insert_field.setMenu(field_menu)
        running_form.addRow("", insert_field)

        sections = QGroupBox("Sections")
        sections_layout = QVBoxLayout(sections)
        self.sections = QTableWidget(0, 9)
        self.sections.setObjectName("headerFooterSections")
        self.sections.setHorizontalHeaderLabels([
            "Pages", "Header", "Left", "Centre", "Right",
            "Footer", "Left", "Centre", "Right",
        ])
        self.sections.setToolTip(
            "The first matching page range overrides the all-page wording")
        self.sections.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.sections.horizontalHeader().setMinimumSectionSize(65)
        for column in range(9):
            self.sections.setColumnWidth(column, 80 if column in (0, 1, 5) else 120)
        for section in settings.header_footer_sections:
            self._add_running_section(section)
        section_buttons = QHBoxLayout()
        add_section = QPushButton("Add")
        add_section.setToolTip("Add a page range with its own header and footer")
        add_section.clicked.connect(self._add_running_section)
        remove_section = QPushButton("Remove")
        remove_section.setToolTip("Remove the selected section")
        remove_section.clicked.connect(self._remove_running_section)
        section_buttons.addWidget(add_section)
        section_buttons.addWidget(remove_section)
        section_buttons.addStretch(1)
        sections_layout.addWidget(self.sections)
        sections_layout.addLayout(section_buttons)
        running_form.addRow(sections)

        logo_box = QGroupBox("Logo")
        logo_form = QFormLayout(logo_box)
        self.logo_key = settings.logo_key
        self.logo_data: Optional[bytes] = None
        self.logo_name = QLabel()
        self.logo_name.setWordWrap(True)
        buttons = QHBoxLayout()
        choose = QPushButton("Choose image…")
        choose.clicked.connect(self._choose_logo)
        clear = QPushButton("Remove")
        clear.clicked.connect(self._clear_logo)
        buttons.addWidget(choose)
        buttons.addWidget(clear)
        buttons.addStretch(1)
        holder = QWidget()
        holder.setLayout(buttons)
        logo_form.addRow(holder)
        logo_form.addRow("Image", self.logo_name)
        self.logo_slot = QComboBox()
        for label, value in (("Header, left", "header_left"),
                             ("Header, centre", "header_center"),
                             ("Header, right", "header_right"),
                             ("Footer, left", "footer_left"),
                             ("Footer, centre", "footer_center"),
                             ("Footer, right", "footer_right")):
            self.logo_slot.addItem(label, value)
        index = self.logo_slot.findData(settings.logo_slot)
        self.logo_slot.setCurrentIndex(index if index >= 0 else 0)
        logo_form.addRow("Place it", self.logo_slot)
        self.logo_height = QDoubleSpinBox()
        self.logo_height.setRange(3, 60)
        self.logo_height.setSuffix(" mm")
        self.logo_height.setValue(settings.logo_height_mm)
        logo_form.addRow("Height", self.logo_height)
        running_form.addRow(logo_box)
        self._show_logo_name()
        tabs.addTab(running, "Header && footer")

        markup = QWidget()
        markup_form = QFormLayout(markup)
        self.default_author = QLineEdit(settings.default_author)
        self.default_author.setPlaceholderText("Stamped on new markups")
        markup_form.addRow("Author", self.default_author)
        tabs.addTab(markup, "Markups")

        grid = QWidget()
        grid_form = QFormLayout(grid)
        self.show_grid = QCheckBox("Show grid")
        self.show_grid.setChecked(settings.show_grid)
        self.snap = QCheckBox("Grid snap")
        self.snap.setToolTip("Snap to SMath's grid (9 px, 6.75 pt)")
        self.snap.setChecked(settings.snap_to_grid)
        self.show_margins = QCheckBox("Margin guides")
        self.show_margins.setToolTip("Show margin guides")
        self.show_margins.setChecked(settings.show_margins)
        grid_form.addRow(self.show_grid)
        grid_form.addRow(self.snap)
        grid_form.addRow(self.show_margins)
        tabs.addTab(grid, "Grid")

        layout.addWidget(_buttons(self))

    def eventFilter(self, watched, event) -> bool:
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.FocusIn and isinstance(watched, QLineEdit):
            self._slot = watched
        return super().eventFilter(watched, event)

    def insert_field(self, token: str) -> None:
        """Put *token* into the header/footer slot typed in last, at its caret."""
        self._slot.insert(token)
        self._slot.setFocus()

    def show_tab(self, name: str) -> None:
        """Open on a named tab, so a menu entry can go straight to it."""
        for index in range(self.tabs.count()):
            if name.lower() in self.tabs.tabText(index).replace("&", "").lower():
                self.tabs.setCurrentIndex(index)
                return

    def _show_logo_name(self) -> None:
        self.logo_name.setText(os.path.basename(getattr(self, "_logo_path", ""))
                               or ("in the document" if self.logo_key else "none"))

    def _add_running_section(self, section=None) -> None:
        """Add an editable page-range override to the manager."""
        if isinstance(section, bool):  # clicked(bool)
            section = None
        section = section or {}
        row = self.sections.rowCount()
        self.sections.insertRow(row)
        start = int(section.get("start", 1))
        end = int(section.get("end", min(len(self.document.pages), start)))
        self.sections.setItem(row, 0, QTableWidgetItem(
            str(start) if start == end else f"{start}-{end}"))
        keys = ("show_header", "header_left", "header_center", "header_right",
                "show_footer", "footer_left", "footer_center", "footer_right")
        defaults = self.document.settings.running_text(None)
        for column, key in enumerate(keys, 1):
            if key.startswith("show_"):
                item = QTableWidgetItem()
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if section.get(key, defaults[key])
                                   else Qt.Unchecked)
            else:
                item = QTableWidgetItem(str(section.get(key, defaults[key])))
            self.sections.setItem(row, column, item)

    def _remove_running_section(self) -> None:
        row = self.sections.currentRow()
        if row >= 0:
            self.sections.removeRow(row)

    def _running_sections(self) -> list[dict]:
        """Read and validate the section rows as one-based inclusive ranges."""
        result = []
        maximum = max(len(self.document.pages), 1)
        keys = ("show_header", "header_left", "header_center", "header_right",
                "show_footer", "footer_left", "footer_center", "footer_right")
        for row in range(self.sections.rowCount()):
            text = (self.sections.item(row, 0).text() or "").strip()
            indices = pdfio.parse_page_range(text, maximum)
            if not indices:
                continue
            section = {"start": min(indices) + 1, "end": max(indices) + 1}
            for column, key in enumerate(keys, 1):
                item = self.sections.item(row, column)
                section[key] = (item.checkState() == Qt.Checked if key.startswith("show_")
                                else item.text())
            result.append(section)
        return result

    def _choose_logo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a logo", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.svg *.tif *.tiff *.webp)")
        if not path:
            return
        try:
            with open(path, "rb") as handle:
                self.logo_data = handle.read()
        except OSError as error:
            QMessageBox.warning(self, "Logo", str(error))
            return
        self._logo_path = path
        self._show_logo_name()

    def _clear_logo(self) -> None:
        self.logo_key = ""
        self.logo_data = None
        self._logo_path = ""
        self._show_logo_name()

    def apply(self) -> None:
        document = self.document
        document.title = self.title.text()
        document.author = self.author.text()
        document.subject = self.subject.text()
        document.project = self.project.text()
        document.company = self.company.text()
        document.keywords = self.keywords.text()
        document.description = self.description.toPlainText()
        settings = document.settings
        settings.show_header = self.show_header.isChecked()
        settings.show_footer = self.show_footer.isChecked()
        settings.header_left, settings.header_center, settings.header_right = (
            field.text() for field in self.header_fields)
        settings.footer_left, settings.footer_center, settings.footer_right = (
            field.text() for field in self.footer_fields)
        settings.header_footer_sections = self._running_sections()
        settings.default_author = self.default_author.text()
        settings.show_grid = self.show_grid.isChecked()
        settings.snap_to_grid = self.snap.isChecked()
        settings.show_margins = self.show_margins.isChecked()
        if self.logo_data is not None:
            suffix = os.path.splitext(getattr(self, "_logo_path", ""))[1].lstrip(".")
            settings.logo_key = document.add_asset(self.logo_data, suffix or "png")
        else:
            settings.logo_key = self.logo_key
        settings.logo_slot = self.logo_slot.currentData()
        settings.logo_height_mm = self.logo_height.value()
        document.modified = True


class CountSubjectDialog(QDialog):
    """Pick what the count tool is counting."""

    def __init__(self, subject: str, symbol: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Count Tool")
        layout = QFormLayout(self)
        self.subject = QLineEdit(subject)
        self.subject.setPlaceholderText("Doors, sprinkler heads, columns…")
        layout.addRow("Counting", self.subject)
        self.symbol = QComboBox()
        from ..items.measure import CountItem
        self.symbol.addItems(list(CountItem.SYMBOLS))
        self.symbol.setCurrentText(symbol)
        layout.addRow("Symbol", self.symbol)
        layout.addRow(_buttons(self))


class RectangleSizeDialog(QDialog):
    """Type an exact real-world width and height for a box or an ellipse."""

    def __init__(self, width_text: str, height_text: str, unit: str, parent=None,
                 scaled: bool = True, sketch: bool = True, shape: str = "Rectangle"):
        super().__init__(parent)
        # named for what it sizes: an ellipse's is "Ellipse Size" (F-10)
        self.setWindowTitle(f"{shape} Size")
        layout = QVBoxLayout(self)
        name = shape.lower()
        if scaled:
            message = (f"This page has a scale, so the {name} can be set out at an "
                       "exact size. Leave these as they are to keep what you drew.")
        elif sketch:
            message = ("This page has no scale, so these are paper sizes. Give the "
                       f"page a scale to set the {name} out in real dimensions.")
        else:
            message = ("The size on the paper. Sketch to Scale's rectangle and "
                       "ellipse (Tools ▸ Sketch to Scale) are set out in real "
                       "dimensions instead.")
        note = QLabel(message)
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.width = QLineEdit(width_text)
        self.width.setPlaceholderText(f"e.g. 3 {unit}")
        self.height = QLineEdit(height_text)
        self.height.setPlaceholderText(f"e.g. 2 {unit}")
        form.addRow("Width", self.width)
        form.addRow("Height", self.height)
        layout.addLayout(form)
        layout.addWidget(_buttons(self))
        self.width.setFocus()
        self.width.selectAll()

    def values(self) -> tuple[str, str]:
        return self.width.text().strip(), self.height.text().strip()


class ArrayDialog(QDialog):
    """Move or copy the selection at exact spacing, any number of times."""

    def __init__(self, unit: str, scaled: bool, parent=None, across: Optional[str] = None):
        super().__init__(parent)
        self.setWindowTitle("Multiply")
        layout = QVBoxLayout(self)
        if scaled:
            message = ("This page has a scale, so distances are real distances. "
                       f"Type them with a unit, for example <b>3 {unit}</b>.")
        else:
            message = ("This page has no scale, so distances are measured on the "
                       "paper. Type them with a unit, for example <b>25 mm</b>.")
        note = QLabel(message)
        note.setWordWrap(True)
        layout.addWidget(note)

        form = QFormLayout()
        # out of the box, one copy just beside the original (*across*: the
        # selection's width and a little): 1 mm put it on top (QA F-31)
        self.dx = QLineEdit(across or f"1 {unit}")
        self.dy = QLineEdit("0")
        form.addRow("Across (x)", self.dx)
        form.addRow("Down (y)", self.dy)
        self.count = QSpinBox()
        self.count.setRange(1, 500)
        self.count.setValue(1)
        form.addRow("Times", self.count)
        layout.addLayout(form)

        self.duplicate = QRadioButton("Duplicate")
        self.duplicate.setToolTip("Leave the original in place and make copies")
        self.move = QRadioButton("Move")
        self.move.setToolTip("Move the original without making copies")
        self.duplicate.setChecked(True)
        layout.addWidget(self.duplicate)
        layout.addWidget(self.move)
        layout.addWidget(_buttons(self))

    def offsets(self) -> tuple[str, str, int, bool]:
        return (self.dx.text().strip(), self.dy.text().strip(),
                self.count.value(), self.duplicate.isChecked())


class ShortcutEdit(QLineEdit):
    """Press the keys you want; it records them.

    Two kinds of binding live in one box. A keystroke that produces a printable
    character with no Ctrl or Alt — ``m``, ``"``, ``7`` — is stored as that
    character, because those act when they are typed straight onto the page.
    Anything else — a key with Ctrl, Alt, Shift or Meta, an F-key up to F24,
    Insert, Delete, Home, End, Page Up and Down, an arrow — is stored as a key
    sequence. Backspace clears the box; Escape puts back what was there; Tab
    moves on.
    """

    changed = Signal()
    focused = Signal()

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._original = text
        self.setReadOnly(True)             # every key is captured, not typed
        self.prompt = "press a key"
        self.setClearButtonEnabled(False)

    def setPlaceholderText(self, text: str) -> None:
        self.prompt = text
        super().setPlaceholderText(text)

    def event(self, event) -> bool:
        # Every key belongs to this box while it has the focus: none of them
        # is the dialog's (Enter, F1) or the window's to act on.
        if event.type() == QEvent.ShortcutOverride:
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta,
                   Qt.Key_AltGr, Qt.Key_unknown, Qt.Key_CapsLock, Qt.Key_NumLock):
            return
        modifiers = event.modifiers() & ~Qt.KeypadModifier
        if key == Qt.Key_Escape and not modifiers:
            self.setText(self._original)
            self.changed.emit()
            return
        if key == Qt.Key_Backspace and not modifiers:
            self.setText("")
            self.changed.emit()
            return
        if key in (Qt.Key_Tab, Qt.Key_Backtab) and not modifiers & ~Qt.ShiftModifier:
            super().keyPressEvent(event)   # let the focus move on
            return
        chord = modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)
        text = event.text()
        # Shift with a letter or the space bar is a key of its own, Shift+M,
        # not the capital it types (it was recorded as "M", which M also
        # matches); a character that needs Shift to type, " or @, stays one
        shifted = bool(modifiers & Qt.ShiftModifier) and (
            key == Qt.Key_Space or (len(text) == 1 and text.isalpha()))
        if text and text.isprintable() and not text.isspace() and not chord \
                and not shifted:
            self.setText(text)
        else:
            sequence = QKeySequence(QKeyCombination(modifiers, Qt.Key(key)))
            self.setText(sequence.toString(QKeySequence.PortableText))
        self.changed.emit()

    def focusInEvent(self, event) -> None:
        self._original = self.text()
        # "press a key" in the box being set, not in seven hundred at once
        QLineEdit.setPlaceholderText(self, self.prompt)
        super().focusInEvent(event)
        self.focused.emit()

    def focusOutEvent(self, event) -> None:
        if self.objectName() == "shortcutEditor":
            QLineEdit.setPlaceholderText(self, "")
        super().focusOutEvent(event)


def _key_of(text: str) -> str:
    """A binding's key, spelt one way, for comparing two."""
    text = (text or "").strip()
    if not text:
        return ""
    return QKeySequence(text).toString(QKeySequence.PortableText).lower() or text.lower()


class ShortcutManagerDialog(QDialog):
    """Every command, and the key for it (the user, 2026-10-16: "Whatever
    features you add should show up in the shortcuts manager as a feature,
    and then the user can add whatever shortcuts they want").

    Grouped as the menus are, each with where it is offered. Click a
    command's key box and press the keys; the key works at once, and is
    remembered. A key that already does something where this one would act
    is said in the bar under the list, with the choice to give it to this
    command instead.
    """

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        from .shortcuts import SCOPE_NAMES
        self.setWindowTitle("Keyboard Shortcuts")
        self.setObjectName("shortcutManager")
        self.manager = manager
        self.window_ = parent
        self.resize(1040, 700)
        outer = QVBoxLayout(self)
        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)
        keys = QWidget()
        self.tabs.addTab(keys, "Shortcuts")
        self.tabs.addTab(_GesturesSheet(), "Mouse and canvas")
        layout = QVBoxLayout(keys)

        note = QLabel(
            "Every command is here, grouped as the menus are. Click a command's "
            "<b>Shortcut</b> box and <b>press the keys you want</b> — Ctrl, Alt, Shift "
            "or Meta with a key, F1–F24, Insert, Delete, Home, End, Page Up/Down, an "
            "arrow, or a single letter or digit. It works at once and is remembered. "
            "Backspace clears the box, Escape puts it back.<br>"
            "No key acts while you are typing into a text box, a cell or an equation; "
            "a single character acts when it is typed straight onto the page.")
        note.setWordWrap(True)
        layout.addWidget(note)

        search = QHBoxLayout()
        self.filter = QLineEdit()
        self.filter.setObjectName("shortcutSearch")
        self.filter.setPlaceholderText("Search commands by name, place or key…")
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(lambda _text: self._apply_filter())
        search.addWidget(self.filter, 3)
        search.addWidget(QLabel("Key:"))
        self.key_search = ShortcutEdit("")
        self.key_search.setObjectName("shortcutKeySearch")
        self.key_search.setPlaceholderText("press a key to find it")
        self.key_search.setToolTip("Press a key to list the commands on it")
        self.key_search.changed.connect(self._apply_filter)
        search.addWidget(self.key_search, 1)
        self.group_filter = QComboBox()
        self.group_filter.setObjectName("shortcutGroup")
        search.addWidget(self.group_filter)
        layout.addLayout(search)

        bindings = manager.bindings()
        self._by_id = {b.action_id: b for b in bindings}
        order = []
        for binding in bindings:
            if binding.category not in order:
                order.append(binding.category)
        self.group_filter.addItem("All groups", "")
        for category in order:
            self.group_filter.addItem(category, category)
        self.group_filter.currentIndexChanged.connect(lambda _i: self._apply_filter())

        places = self._places_of()
        self.table = QTableWidget(0, 5)
        self.table.setObjectName("shortcutTable")
        self.table.setHorizontalHeaderLabels(["Command", "Shortcut", "Default", "Acts",
                                              "Where"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setWordWrap(False)
        layout.addWidget(self.table, 1)

        self.editors: dict[str, ShortcutEdit] = {}
        self.rows: dict[str, int] = {}
        self._row_ids: dict[int, str] = {}
        self._headers: dict[str, int] = {}
        self._places: dict[str, str] = {}
        bold = QFont()
        bold.setBold(True)
        acts_tip = ("Where the key acts. One key may do two things only where they "
                    "can never both act: Calc and Markup mode, inside an equation and "
                    "outside it, or in an open table or spreadsheet and outside it.")
        self.table.setUpdatesEnabled(False)
        for category in order:
            row = self.table.rowCount()
            self.table.insertRow(row)
            header = QTableWidgetItem(category)
            header.setFont(bold)
            header.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 0, header)
            self.table.setSpan(row, 0, 1, 5)
            self._headers[category] = row
            for binding in (b for b in bindings if b.category == category):
                row = self.table.rowCount()
                self.table.insertRow(row)
                self.rows[binding.action_id] = row
                self._row_ids[row] = binding.action_id
                label = QTableWidgetItem("   " + binding.label)
                label.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                label.setToolTip(binding.label)
                self.table.setItem(row, 0, label)
                editor = ShortcutEdit(manager.sequence(binding.action_id))
                editor.setObjectName("shortcutEditor")
                QLineEdit.setPlaceholderText(editor, "")
                editor.changed.connect(lambda i=binding.action_id: self._edited(i))
                editor.focused.connect(lambda r=row: self.table.selectRow(r))
                self.table.setCellWidget(row, 1, editor)
                self.editors[binding.action_id] = editor
                default = QTableWidgetItem(binding.default or "—")
                default.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.table.setItem(row, 2, default)
                acts = QTableWidgetItem(SCOPE_NAMES.get(binding.scope, ""))
                acts.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                acts.setToolTip(acts_tip)
                self.table.setItem(row, 3, acts)
                where = " · ".join(places.get(binding.action_id, []))
                self._places[binding.action_id] = where
                place = QTableWidgetItem(where)
                place.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                place.setToolTip(where.replace(" · ", "\n"))
                self.table.setItem(row, 4, place)
        self.table.setUpdatesEnabled(True)
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.Interactive)
        head.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 330)
        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(3, 120)
        self.table.verticalHeader().setDefaultSectionSize(
            max(26, self.fontMetrics().height() + 14))

        # a key already in use, and what to do about it
        self.conflict = QWidget()
        self.conflict.setObjectName("shortcutConflict")
        bar = QHBoxLayout(self.conflict)
        bar.setContentsMargins(0, 0, 0, 0)
        self.conflict_text = QLabel("")
        self.conflict_text.setWordWrap(True)
        bar.addWidget(self.conflict_text, 1)
        self.reassign_button = QPushButton("Reassign")
        self.reassign_button.setToolTip("Take the key from the other command and give it "
                                        "to this one")
        self.reassign_button.clicked.connect(lambda _checked=False: self.reassign())
        bar.addWidget(self.reassign_button)
        self.keep_button = QPushButton("Cancel")
        self.keep_button.setToolTip("Leave the key where it was")
        self.keep_button.clicked.connect(lambda _checked=False: self.cancel_pending())
        bar.addWidget(self.keep_button)
        self.conflict.setVisible(False)
        layout.addWidget(self.conflict)
        self._pending = None            # (command, key, the commands it clashes with)

        self.warning = QLabel("")
        self.warning.setWordWrap(True)
        layout.addWidget(self.warning)

        buttons = QHBoxLayout()
        self.clear_button = QPushButton("Clear")
        self.clear_button.setToolTip("Take the selected command's key away")
        self.clear_button.clicked.connect(lambda: self._set_current(""))
        self.reset_button = QPushButton("Reset one")
        self.reset_button.setToolTip("Put the selected command's own key back")
        self.reset_button.clicked.connect(self._reset_row)
        self.reset_all_button = QPushButton("Reset all")
        self.reset_all_button.setToolTip("Put every command's own key back")
        self.reset_all_button.clicked.connect(self._reset_all)
        for button in (self.clear_button, self.reset_button, self.reset_all_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        self.count_label = QLabel("")
        buttons.addWidget(self.count_label)
        layout.addLayout(buttons)
        box = QDialogButtonBox(QDialogButtonBox.Close)
        box.rejected.connect(self.accept)
        box.accepted.connect(self.accept)
        outer.addWidget(box)
        self._check()
        self._apply_filter()

    # -- helpers -----------------------------------------------------------
    def _places_of(self) -> dict:
        commands = getattr(self.window_, "commands", None)
        if commands is None:
            return {}
        try:
            return commands.places_map()
        except Exception:  # noqa: BLE001 - the list still works without places
            return {}

    def _current_binding(self):
        action_id = self._row_ids.get(self.table.currentRow())
        return self._by_id.get(action_id) if action_id else None

    def _set_current(self, text: str) -> None:
        binding = self._current_binding()
        if binding is not None:
            self.editors[binding.action_id].setText(text)
            self._edited(binding.action_id)

    def _reset_row(self) -> None:
        binding = self._current_binding()
        if binding is not None:
            self._set_current(binding.default)

    def _reset_all(self) -> None:
        self.cancel_pending(revert=False)
        for binding in self.manager.bindings():
            if binding.action_id in self.editors:
                self.editors[binding.action_id].setText(binding.default)
        self._commit_all()

    def _apply_filter(self, *_args) -> None:
        needle = self.filter.text().strip().lower()
        wanted_key = _key_of(self.key_search.text())
        group = self.group_filter.currentData() or ""
        shown_in = {category: 0 for category in self._headers}
        shown = 0
        for action_id, row in self.rows.items():
            binding = self._by_id[action_id]
            key = self.editors[action_id].text()
            haystack = f"{binding.category} {binding.label} {key} " \
                       f"{self._places.get(action_id, '')}".lower()
            hide = (bool(needle) and not all(word in haystack for word in needle.split())) \
                or (bool(wanted_key) and _key_of(key) != wanted_key) \
                or (bool(group) and binding.category != group)
            self.table.setRowHidden(row, hide)
            if not hide:
                shown_in[binding.category] += 1
                shown += 1
        for category, row in self._headers.items():
            self.table.setRowHidden(row, shown_in[category] == 0)
        self.count_label.setText(f"{shown} of {len(self.rows)} commands")

    def assignments(self) -> dict[str, str]:
        return {action_id: editor.text().strip() for action_id, editor in self.editors.items()}

    def _others_on(self, action_id: str, text: str) -> list[str]:
        """The commands already on *text* where *action_id*'s key would act."""
        from .shortcuts import scopes_overlap
        wanted = _key_of(text)
        if not wanted:
            return []
        scope = self._by_id[action_id].scope
        return [other for other, editor in self.editors.items()
                if other != action_id and _key_of(editor.text()) == wanted
                and scopes_overlap(scope, self._by_id[other].scope)]

    # -- changing a key --------------------------------------------------------
    def _edited(self, action_id: str) -> None:
        """A key was pressed into *action_id*'s box (or cleared, or reset):
        it acts at once, unless another command has it there already."""
        editor = self.editors[action_id]
        text = editor.text().strip()
        if self._pending is not None and self._pending[0] != action_id:
            self.cancel_pending()
        others = self._others_on(action_id, text)
        if others:
            names = ", ".join(f"“{self._by_id[o].label}”" for o in others)
            mine = self._by_id[action_id].label
            self.conflict_text.setText(
                f"⚠ <b>{html.escape(text)}</b> is already {html.escape(names)}. "
                f"Give it to “{html.escape(mine)}” instead?")
            self.conflict.setVisible(True)
            self._pending = (action_id, text, others)
            self._check()
            return
        self.conflict.setVisible(False)
        self._pending = None
        self._commit(action_id, text)

    def reassign(self) -> None:
        """The key in question goes to the command it was pressed for; the
        others lose it."""
        if self._pending is None:
            return
        action_id, text, others = self._pending
        self._pending = None
        self.conflict.setVisible(False)
        for other in others:
            self.editors[other].setText("")
            self.manager.set_sequence(other, "")
        self._commit(action_id, text)

    def cancel_pending(self, revert: bool = True) -> None:
        """Leave the key where it was."""
        if self._pending is None:
            return
        action_id, _text, _others = self._pending
        self._pending = None
        self.conflict.setVisible(False)
        if revert:
            self.editors[action_id].setText(self.manager.sequence(action_id))
        self._check()

    def _commit(self, action_id: str, text: str) -> None:
        if self.manager.sequence(action_id) != text:
            self.manager.set_sequence(action_id, text)
        self._applied()

    def _commit_all(self) -> None:
        for action_id, text in self.assignments().items():
            if self.manager.sequence(action_id) != text:
                self.manager.set_sequence(action_id, text)
        self._applied()

    def _applied(self) -> None:
        """The window's keys follow at once."""
        apply = getattr(self.window_, "apply_shortcuts", None)
        if callable(apply):
            apply()
        self._check()
        if self.key_search.text():
            self._apply_filter()

    def _check(self) -> None:
        """Flag anything bound twice, on the rows themselves and in a line.

        Twice means where both could act: a key may be one thing in Calc mode
        and another in Markup mode, or one thing inside an equation and
        another outside it (shortcuts.scopes_overlap).
        """
        from .shortcuts import BY_ID, clashes_in
        found = clashes_in(self.assignments())
        clashing = {action_id for ids in found.values() for action_id in ids}
        clashes = []
        for text, ids in found.items():
            if self._pending is not None and self._pending[0] in ids:
                continue                   # the bar above is asking about it
            labels = [BY_ID[i].label if i in BY_ID else i for i in ids]
            shown = QKeySequence(text).toString(QKeySequence.NativeText) or text
            clashes.append(f"{labels[0]} and {', '.join(labels[1:])} are both on {shown}")
        for action_id, editor in self.editors.items():
            red = action_id in clashing and bool(editor.text().strip())
            style = "border: 1px solid #c0392b;" if red else ""
            if editor.styleSheet() != style:
                editor.setStyleSheet(style)
        self.warning.setText("⚠ " + "; ".join(clashes) if clashes else "")
        self.warning.setStyleSheet("color:#d9534f;" if clashes else "")

    def clashes(self) -> list[str]:
        """Keys bound to more than one thing that could both act."""
        from .shortcuts import clashes_in
        return list(clashes_in(self.assignments()))

    def accept(self) -> None:
        """Refuse to close on a key that would mean two different things."""
        self.cancel_pending()
        clashes = self.clashes()
        if clashes:
            QMessageBox.warning(
                self, "Keyboard Shortcuts",
                "These keys are each bound to more than one thing:\n\n  "
                + "\n  ".join(sorted(clashes))
                + "\n\nClear one of them, or give it a different key.")
            return
        super().accept()

    def apply(self) -> None:
        """Every box's key into the bindings (the boxes already apply as they
        change; this is for anything set on them directly)."""
        for action_id, text in self.assignments().items():
            if self.manager.sequence(action_id) != text:
                self.manager.set_sequence(action_id, text)


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About CalcForge")
        layout = QVBoxLayout(self)
        title = QLabel("CalcForge")
        font = QFont()
        font.setPointSize(20)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)
        # which CalcForge this is (F-36: About showed no version)
        from PySide6 import __version__ as pyside_version
        from .. import __version__
        version = QLabel(f"Version {__version__} · Qt {pyside_version}")
        version.setObjectName("aboutVersion")
        version.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(version)
        body = QLabel(
            "A PDF markup editor for drawings, with SMath's live "
            "calculations on the page.\n\n"
            "• A full markup tool set with scaled measurement and takeoff\n"
            "• Equations, plots and matrices that calculate as SMath does, "
            "across every page\n"
            "• Bluebeam tool sets import, and markups export as real PDF "
            "annotations other editors can move\n"
            "• Open a PDF, mark it up, save it back as a PDF")
        body.setWordWrap(True)
        layout.addWidget(body)
        box = QDialogButtonBox(QDialogButtonBox.Close)
        box.rejected.connect(self.reject)
        box.accepted.connect(self.accept)
        layout.addWidget(box)


class _GesturesSheet(QWidget):
    """The things the mouse and the canvas do, which are not rebindable.

    It lives inside the shortcut manager rather than in a dialog of its own:
    two menu entries both called "Keyboard Shortcuts" only ever made people
    open the wrong one.
    """

    ROWS = [
        ("Typing on the page", ""),
        ("\"", "Start a text markup where the cursor is"),
        ("|", "Start a note here"),
        ("@", "Start a callout here"),
        ("any other key", "Nothing, unless it is bound on the Shortcuts tab"),
        ("Canvas", ""),
        ("Ctrl + wheel", "Zoom"),
        ("Space + drag", "Pan"),
        ("Shift + drag", "Hold a line to 0°, 45° or 90°; square off a box"),
        ("Drag right / left", "Select what is wholly inside · what it crosses"),
        ("Click, click…", "Lasso a shape to select inside · Enter to close"),
        ("Double-click", "Edit the words · add a vertex to a polyline"),
        ("Delete", "Delete the selection"),
        ("1 … 9", "Pick up that tool from My Tools"),
        ("Ctrl+G / Ctrl+Shift+G", "Group · ungroup the selection"),
        ("Arrow keys", "Nudge the selection"),
        ("Esc", "Put the tool down and leave what is being typed"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        note = QLabel("What the mouse and the canvas do. These are not "
                      "rebindable; everything that is, is on the Shortcuts tab.")
        note.setWordWrap(True)
        layout.addWidget(note)
        table = QTableWidget(len(self.ROWS), 2)
        table.setHorizontalHeaderLabels(["Key", "Action"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for row, (key, action) in enumerate(self.ROWS):
            key_item = QTableWidgetItem(key)
            if not action:
                font = key_item.font()
                font.setBold(True)
                key_item.setFont(font)
            table.setItem(row, 0, key_item)
            table.setItem(row, 1, QTableWidgetItem(action))
        table.resizeColumnToContents(0)
        layout.addWidget(table)


class ToolbarDialog(QDialog):
    """Choose which markup tools appear on the toolbar."""

    def __init__(self, tools, chosen, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Customise Toolbars")
        self.resize(420, 560)
        layout = QVBoxLayout(self)
        note = QLabel("Tick the tools you want on the toolbar. Everything stays "
                      "available from the Tools menu and from its "
                      "keyboard shortcut either way.")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.boxes: dict[str, QCheckBox] = {}
        self.list = QTableWidget(0, 1)
        self.list.setHorizontalHeaderLabels(["Tool"])
        self.list.verticalHeader().setVisible(False)
        self.list.horizontalHeader().setStretchLastSection(True)
        self.list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.list, 1)

        category = None
        for tool in tools:
            if tool.category != category:
                category = tool.category
                row = self.list.rowCount()
                self.list.insertRow(row)
                heading = QTableWidgetItem(category.upper())
                heading.setFlags(Qt.ItemIsEnabled)
                font = heading.font()
                font.setBold(True)
                heading.setFont(font)
                self.list.setItem(row, 0, heading)
            row = self.list.rowCount()
            self.list.insertRow(row)
            box = QCheckBox(tool.label)
            box.setChecked(tool.key in chosen)
            self.boxes[tool.key] = box
            self.list.setCellWidget(row, 0, box)
        self.list.resizeRowsToContents()

        buttons = QHBoxLayout()
        every = QPushButton("Everything")
        every.clicked.connect(lambda: self._set_all(True))
        none = QPushButton("Nothing")
        none.clicked.connect(lambda: self._set_all(False))
        buttons.addWidget(every)
        buttons.addWidget(none)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        layout.addWidget(_buttons(self))

    def _set_all(self, on: bool) -> None:
        for box in self.boxes.values():
            box.setChecked(on)

    def chosen(self) -> set:
        return {key for key, box in self.boxes.items() if box.isChecked()}


class FlattenDialog(QDialog):
    """Revu's Flatten Markups (Document ▸ Flatten): the Type list, checked
    types flattened; Flatten: All Markups, Exclude Filtered Markups or
    Currently Selected Markups; Allow Markup Recovery (Unflatten), which
    belongs here and not in Preferences (the user, 2026-10-15: "flatten
    recovery is in settings not in flatten"); the Pages; Flatten and Cancel.

    Revu's Flatten to Layer and its Capture options are left out: layers
    were withdrawn, and nothing here records Capture media.
    """

    ALL_MARKUPS, EXCLUDE_FILTERED, SELECTED_MARKUPS = "all", "exclude_filtered", "selected"

    def __init__(self, types, parent=None, *, selected_markups: int = 0,
                 recoverable: bool = True, count: int = 1, current: int = 0,
                 selected_pages=None):
        super().__init__(parent)
        self.setWindowTitle("Flatten Markups")
        layout = QVBoxLayout(self)
        body = QHBoxLayout()
        body.setSpacing(12)
        layout.addLayout(body, 1)

        # the Type list: a tick per kind of markup in the document
        self.types = QTreeWidget()
        self.types.setObjectName("flattenTypes")
        self.types.setHeaderLabels(["Type"])
        self.types.setRootIsDecorated(False)
        self.types.setUniformRowHeights(True)
        self.types.setMinimumSize(200, 200)
        self.types.setToolTip("Checked types are flattened; unchecked ones are not")
        for name in types:
            entry = QTreeWidgetItem([name])
            entry.setFlags(entry.flags() | Qt.ItemIsUserCheckable)
            entry.setCheckState(0, Qt.Checked)
            self.types.addTopLevelItem(entry)
        body.addWidget(self.types, 1)

        options = QVBoxLayout()
        options.setSpacing(6)
        options.addWidget(QLabel("Flatten:"))
        self.scope_group = QButtonGroup(self)
        self.all_markups = QRadioButton("All Markups")
        self.all_markups.setToolTip("Every markup of the checked types, filtered or not")
        self.exclude_filtered = QRadioButton("Exclude Filtered Markups")
        self.exclude_filtered.setToolTip(
            "Leave alone the markups a filter in the Markups list is hiding")
        self.selected_markups = QRadioButton("Currently Selected Markups")
        self.selected_markups.setToolTip(
            "Only the markups that were selected before this was opened"
            if selected_markups else "Nothing was selected before this was opened")
        self.selected_markups.setEnabled(bool(selected_markups))
        choices = QVBoxLayout()
        choices.setContentsMargins(14, 0, 0, 0)
        choices.setSpacing(6)
        for button in (self.all_markups, self.exclude_filtered, self.selected_markups):
            self.scope_group.addButton(button)
            choices.addWidget(button)
        options.addLayout(choices)
        (self.selected_markups if selected_markups else self.all_markups).setChecked(True)
        options.addSpacing(8)
        self.allow_recovery = QCheckBox("Allow Markup Recovery (Unflatten)")
        self.allow_recovery.setObjectName("flattenAllowRecovery")
        self.allow_recovery.setToolTip(
            "Keep what is needed to unflatten them later (Document ▸ Unflatten).\n"
            "Without it, flattening cannot be undone once the file is saved.")
        self.allow_recovery.setChecked(bool(recoverable))
        options.addWidget(self.allow_recovery)
        options.addStretch(1)
        body.addLayout(options)

        pages = QHBoxLayout()
        pages.addWidget(QLabel("Pages:"))
        self.pages = PagesRange(count, current, selected_pages, default=PagesRange.ALL)
        pages.addWidget(self.pages, 1)
        layout.addLayout(pages)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.flatten_button = QPushButton("Flatten")
        self.flatten_button.setObjectName("flattenGo")
        self.flatten_button.setDefault(True)
        self.flatten_button.clicked.connect(self.flatten)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(self.flatten_button)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)

    def flatten(self) -> None:
        if not self.page_indexes():
            QMessageBox.warning(self, "Flatten Markups",
                                "Enter pages to flatten, such as 1-3, 5.")
            return
        self.accept()

    def set_type_checked(self, name: str, on: bool) -> None:
        for row in range(self.types.topLevelItemCount()):
            entry = self.types.topLevelItem(row)
            if entry.text(0) == name:
                entry.setCheckState(0, Qt.Checked if on else Qt.Unchecked)

    def chosen_types(self) -> set[str]:
        return {self.types.topLevelItem(row).text(0)
                for row in range(self.types.topLevelItemCount())
                if self.types.topLevelItem(row).checkState(0) == Qt.Checked}

    def scope(self) -> str:
        if self.selected_markups.isChecked():
            return self.SELECTED_MARKUPS
        if self.exclude_filtered.isChecked():
            return self.EXCLUDE_FILTERED
        return self.ALL_MARKUPS

    def recoverable(self) -> bool:
        return self.allow_recovery.isChecked()

    def page_indexes(self) -> Optional[list]:
        return self.pages.page_indexes()


class PreferencesDialog(QDialog):
    """The choices that belong to the person rather than to the document."""

    def __init__(self, prefs, parent=None):
        super().__init__(parent)
        from . import preferences as prefs_module

        self.setWindowTitle("Preferences")
        self.prefs = prefs
        layout = QVBoxLayout(self)

        canvas = QGroupBox("Canvas")
        form = QFormLayout(canvas)
        self.wheel = QComboBox()
        self.wheel.addItem("Zooms in and out", prefs_module.WHEEL_ZOOM)
        self.wheel.addItem("Scrolls up and down", prefs_module.WHEEL_SCROLL)
        self.wheel.setCurrentIndex(0 if prefs.wheel_zooms() else 1)
        self.wheel.setToolTip("Ctrl and the wheel always zoom, whichever this is;\n"
                              "a trackpad always scrolls")
        form.addRow("Mouse wheel", self.wheel)
        self.snapping = QCheckBox("Drawing snap")
        self.snapping.setToolTip("Catch on what is already drawn")
        self.snapping.setChecked(prefs.snap_while_drawing)
        self.snapping.setToolTip("Corners, midpoints and line ends pull the "
                                 "pointer to them while you draw")
        form.addRow("", self.snapping)
        self.insertion = QCheckBox("Insertion point")
        self.insertion.setChecked(prefs.insertion_point)
        self.insertion.setToolTip(
            "Click empty paper to leave a caret there; the arrow keys move it")
        form.addRow("", self.insertion)
        self.gpu_drawing = QCheckBox("Draw with the graphics card")
        self.gpu_drawing.setChecked(getattr(prefs, "gpu_drawing", True))
        self.gpu_drawing.setToolTip(
            "Smooth scrolling and panning on high-density (Retina, 4K) screens.\n"
            "Turn off if pages draw wrongly with your graphics driver.")
        form.addRow("", self.gpu_drawing)
        # Recoverable flattening is Flatten Markups' Allow Markup Recovery
        # now, as in Revu, and remembered from there (the user, 2026-10-15).
        layout.addWidget(canvas)

        markup = QGroupBox("Markup")
        form = QFormLayout(markup)
        self.style_keys = QCheckBox("Number keys pick markup styles")
        self.style_keys.setObjectName("markupStyleKeys")
        self.style_keys.setChecked(getattr(prefs, "markup_style_keys", True))
        self.style_keys.setToolTip(
            "With a markup tool in hand, 1 to 9 draw the next markup in that\n"
            "tool's style 1 to 9 from the Markup Styles toolbar; 0 is the default")
        form.addRow("", self.style_keys)
        layout.addWidget(markup)

        writing = QGroupBox("Writing")
        form = QFormLayout(writing)
        self.author = QLineEdit(getattr(prefs, "author", ""))
        self.author.setToolTip("The name new markups are signed with; saved PDFs carry it\n"
                               "as each markup's author")
        form.addRow("Author", self.author)
        self.autosize = QCheckBox("Autosize text")
        self.autosize.setToolTip("A text box grows to fit what is typed")
        self.autosize.setChecked(prefs.autosize_text)
        form.addRow("", self.autosize)
        self.spelling = QCheckBox("Check spelling")
        self.spelling.setToolTip("Check spelling as I type")
        self.spelling.setChecked(prefs.check_spelling)
        form.addRow("", self.spelling)
        self.dictionary = QComboBox()
        self.dictionary.addItem("New Zealand English", "en_NZ")
        self.dictionary.setCurrentIndex(0)
        self.dictionary.setToolTip("British spelling, with the words an engineer "
                                   "here writes")
        form.addRow("Dictionary", self.dictionary)
        layout.addWidget(writing)

        # SMath's Tools > Options: how results are shown unless an equation
        # says otherwise, and how a new equation is written.
        calcs = QGroupBox("Calculations")
        form = QFormLayout(calcs)
        self.result_decimals = QSpinBox()
        self.result_decimals.setObjectName("resultDecimals")
        self.result_decimals.setRange(0, 15)
        self.result_decimals.setValue(int(prefs.result_decimals))
        form.addRow("Decimals", self.result_decimals)
        self.result_threshold = QSpinBox()
        self.result_threshold.setRange(0, 15)
        self.result_threshold.setValue(int(prefs.result_threshold))
        self.result_threshold.setToolTip("Longer numbers are shown with a power of ten")
        form.addRow("Threshold", self.result_threshold)
        self.result_trailing = QCheckBox("Trailing zeros")
        self.result_trailing.setChecked(bool(prefs.result_trailing_zeros))
        form.addRow("", self.result_trailing)
        self.result_fractions = QComboBox()
        for key, title in (("decimal", "Decimal"), ("fraction", "Fraction"), ("auto", "Auto")):
            self.result_fractions.addItem(title, key)
        self.result_fractions.setCurrentIndex(
            max(self.result_fractions.findData(prefs.result_fractions), 0))
        form.addRow("Fractions", self.result_fractions)
        self.equation_size = QDoubleSpinBox()
        self.equation_size.setRange(4, 72)
        self.equation_size.setSuffix(" pt")
        self.equation_size.setValue(float(prefs.equation_font_size))
        form.addRow("Equation size", self.equation_size)
        from .widgets import ColorButton
        self.equation_colour = ColorButton(prefs.equation_colour, label="Equation colour")
        form.addRow("Equation colour", self.equation_colour)
        layout.addWidget(calcs)

        layout.addStretch(1)
        layout.addWidget(_buttons(self))

    def result_preferences(self):
        from . import preferences as prefs_module

        return prefs_module.Preferences(
            wheel=self.wheel.currentData(),
            author=self.author.text().strip(),
            check_spelling=self.spelling.isChecked(),
            dictionary=self.dictionary.currentData(),
            snap_while_drawing=self.snapping.isChecked(),
            autosize_text=self.autosize.isChecked(),
            insertion_point=self.insertion.isChecked(),
            gpu_drawing=self.gpu_drawing.isChecked(),
            recover_flattened=getattr(self.prefs, "recover_flattened", True),
            markup_style_keys=self.style_keys.isChecked(),
            page_thumbnails=getattr(self.prefs, "page_thumbnails", 1.0),
            result_decimals=self.result_decimals.value(),
            result_threshold=self.result_threshold.value(),
            result_trailing_zeros=self.result_trailing.isChecked(),
            result_fractions=self.result_fractions.currentData(),
            equation_font_size=self.equation_size.value(),
            equation_colour=self.equation_colour.color() or "#000000")


class SpellingDialog(QDialog):
    """Revu's Check Spelling, one misspelt word at a time: Ignore Once,
    Ignore All, Add to Dictionary, Change, Change All and Close.

    *choice* says which button closed it: ``ignore_once``, ``ignore_all``,
    ``add``, ``change``, ``change_all`` or ``stop`` (Close).
    """

    CHOICES = (("Ignore Once", "ignore_once"), ("Ignore All", "ignore_all"),
               ("Add to Dictionary", "add"), ("Change", "change"),
               ("Change All", "change_all"))

    def __init__(self, word: str, text: str, at: int, suggestions: list,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Check Spelling")
        self.setMinimumWidth(492)
        self.choice = "stop"
        layout = QVBoxLayout(self)
        before = text[max(at - 30, 0):at]
        after = text[at + len(word):at + len(word) + 30]
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)
        context = QLabel(f"…{html.escape(before)}<b style='color:#e03131'>"
                         f"{html.escape(word)}</b>{html.escape(after)}…")
        context.setTextFormat(Qt.RichText)
        context.setWordWrap(True)
        grid.addWidget(QLabel("Not in Dictionary:"), 0, 0, Qt.AlignTop)
        grid.addWidget(context, 0, 1)
        self.edit = QLineEdit(suggestions[0] if suggestions else word)
        grid.addWidget(QLabel("Change To:"), 1, 0)
        grid.addWidget(self.edit, 1, 1)
        self.options = QListWidget()
        self.options.addItems(suggestions)
        self.options.currentTextChanged.connect(self.edit.setText)
        self.options.itemDoubleClicked.connect(lambda _item: self._close("change"))
        grid.addWidget(QLabel("Suggestions:"), 2, 0, Qt.AlignTop)
        grid.addWidget(self.options, 2, 1)
        body = QHBoxLayout()
        body.setSpacing(12)
        body.addLayout(grid, 1)
        column = QVBoxLayout()
        column.setSpacing(6)
        self.buttons = {}
        for label, choice in self.CHOICES:
            button = QPushButton(label)
            button.setObjectName(f"spell_{choice}")
            button.clicked.connect(lambda _checked=False, c=choice: self._close(c))
            column.addWidget(button)
            self.buttons[choice] = button
            if choice == "change":
                button.setDefault(True)
        column.addStretch(1)
        close = QPushButton("Close")
        close.setObjectName("spell_close")
        close.clicked.connect(lambda: self._close("stop"))
        column.addWidget(close)
        self.buttons["stop"] = close
        body.addLayout(column)
        layout.addLayout(body)

    def _close(self, choice: str) -> None:
        self.choice = choice
        if choice == "stop":
            self.reject()
        else:
            self.accept()

    def replacement(self) -> str:
        return self.edit.text().strip()


class LinkDialog(QDialog):
    """Revu's Action dialog (the Hyperlink tool): Jump to Page, Snapshot View
    (the page and where the view is), Open File or Open URL."""

    def __init__(self, item, pages: int, current_view: tuple, parent=None):
        super().__init__(parent)
        from ..items.link import FILE, PAGE, VIEW, WEB
        self.setWindowTitle("Action")
        self.setMinimumWidth(492)
        self.item = item
        self._view = current_view
        layout = QVBoxLayout(self)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        self.kind = QComboBox()
        self.kind.setObjectName("actionKind")
        for key, label in ((PAGE, "Jump to Page"), (VIEW, "Snapshot View"),
                           (FILE, "Open File"), (WEB, "Open URL")):
            self.kind.addItem(label, key)
        self.kind.setCurrentIndex(max(self.kind.findData(item.kind), 0))
        grid.addWidget(QLabel("Action:"), 0, 0)
        grid.addWidget(self.kind, 0, 1)
        self.page = QSpinBox()
        self.page.setRange(1, max(pages, 1))
        self.page.setValue(item.target_page + 1)
        self.page.setSuffix(f" of {max(pages, 1)}")
        self.page.setMinimumWidth(90)
        self.here = QPushButton("Use Current View")
        self.here.setToolTip("The page and position the view is showing now")
        self.here.clicked.connect(self._use_view)
        self.page_label = QLabel("Page:")
        page_row = QHBoxLayout()
        page_row.setContentsMargins(0, 0, 0, 0)
        page_row.addWidget(self.page)
        page_row.addWidget(self.here)
        page_row.addStretch(1)
        self.page_holder = QWidget()
        self.page_holder.setLayout(page_row)
        grid.addWidget(self.page_label, 1, 0)
        grid.addWidget(self.page_holder, 1, 1)
        self.address = QLineEdit(item.address)
        self.address.setPlaceholderText("https://… or a file path")
        self.browse = QPushButton("Browse…")
        self.browse.clicked.connect(self._browse)
        self.address_label = QLabel("Address:")
        address_row = QHBoxLayout()
        address_row.setContentsMargins(0, 0, 0, 0)
        address_row.addWidget(self.address, 1)
        address_row.addWidget(self.browse)
        self.address_holder = QWidget()
        self.address_holder.setLayout(address_row)
        grid.addWidget(self.address_label, 2, 0)
        grid.addWidget(self.address_holder, 2, 1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        ok = QPushButton("OK")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        layout.addSpacing(4)
        layout.addLayout(buttons)
        self._y = item.target_y
        self.kind.currentIndexChanged.connect(self._show_fields)
        self._show_fields()

    def _show_fields(self, *_args) -> None:
        """Jump to Page and Snapshot View take a page; Open File and Open URL
        an address (Browse… only for a file)."""
        from ..items.link import FILE, PAGE, VIEW
        kind = self.kind.currentData()
        on_page = kind in (PAGE, VIEW)
        for widget in (self.page_label, self.page_holder):
            widget.setVisible(on_page)
        for widget in (self.address_label, self.address_holder):
            widget.setVisible(not on_page)
        self.here.setVisible(kind == VIEW)
        self.browse.setVisible(kind == FILE)
        self.address.setPlaceholderText("A file to open" if kind == FILE
                                        else "https://…")
        self.adjustSize()

    def _use_view(self) -> None:
        from ..items.link import VIEW
        page, y = self._view
        self.kind.setCurrentIndex(self.kind.findData(VIEW))
        self.page.setValue(page + 1)
        self._y = y

    def _browse(self) -> None:
        from ..items.link import FILE
        path, _ = QFileDialog.getOpenFileName(self, "Open File")
        if path:
            self.address.setText(path)
            self.kind.setCurrentIndex(self.kind.findData(FILE))

    def apply(self) -> None:
        self.item.kind = self.kind.currentData()
        self.item.target_page = self.page.value() - 1
        self.item.target_y = self._y
        self.item.address = self.address.text().strip()
        self.item.update()


class ViewportsDialog(QDialog):
    """The viewports on one page: each one's name and scale, to change or delete."""

    def __init__(self, window, page):
        super().__init__(window)
        self.setWindowTitle("Viewports")
        self.window_ = window
        self.page = page
        layout = QVBoxLayout(self)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _item: self.edit())
        layout.addWidget(self.list)
        row = QHBoxLayout()
        edit = QPushButton("Edit…")
        edit.setToolTip("Rename the viewport or change its scale")
        edit.clicked.connect(self.edit)
        delete = QPushButton("Delete")
        delete.clicked.connect(self.delete)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(edit)
        row.addWidget(delete)
        row.addStretch(1)
        row.addWidget(close)
        layout.addLayout(row)
        self.fill()

    def fill(self) -> None:
        row = max(self.list.currentRow(), 0)
        self.list.clear()
        for viewport in self.page.viewports:
            self.list.addItem(f"{viewport.name}  —  {viewport.scale.label}")
        if self.list.count():
            self.list.setCurrentRow(min(row, self.list.count() - 1))

    def _chosen(self):
        row = self.list.currentRow()
        if 0 <= row < len(self.page.viewports):
            return self.page.viewports[row]
        return None

    def edit(self) -> None:
        viewport = self._chosen()
        if viewport is not None and self.window_.edit_viewport(self.page, viewport):
            self.fill()

    def delete(self) -> None:
        viewport = self._chosen()
        if viewport is not None:
            self.window_.delete_viewport(self.page, viewport)
            self.fill()


# Revu's page dialogs live in pagedialogs.py; the old names stay for what
# used them ("Add pages" is Insert Blank Page, "Insert PDF pages" is Insert
# Pages).
from .pagedialogs import (ApplyToPagesDialog, CropPagesDialog,  # noqa: E402,F401
                          DeletePagesDialog, ExtractPagesDialog, InsertBlankPageDialog,
                          InsertPagesDialog, SplitDocumentDialog)

NewPagesDialog = InsertBlankPageDialog
PdfImportDialog = InsertPagesDialog
