"""Property panel for the selected markup's colour, border, opacity."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QDoubleSpinBox, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QPushButton,
                               QSlider, QVBoxLayout, QWidget)

from ..document import Markup


def _colour_button(colour: QColor) -> QPushButton:
    btn = QPushButton()
    btn.setFixedSize(28, 22)
    btn.setStyleSheet(
        f"background: {colour.name()}; border: 1px solid #888; border-radius: 3px;")
    return btn


def _rgb_to_qcolor(rgb: tuple[float, ...]) -> QColor:
    if not rgb:
        return QColor(Qt.transparent)
    return QColor.fromRgbF(min(rgb[0], 1.0), min(rgb[1], 1.0),
                           min(rgb[2], 1.0) if len(rgb) > 2 else 0.0)


def _qcolor_to_rgb(colour: QColor) -> tuple[float, float, float]:
    return (colour.redF(), colour.greenF(), colour.blueF())


class PropertyPanel(QWidget):
    """Shows and edits the properties of the currently selected markup."""

    colour_changed = Signal(tuple)
    fill_changed = Signal(tuple)
    border_width_changed = Signal(float)
    opacity_changed = Signal(float)
    hidden_changed = Signal(bool)
    locked_changed = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._markup: Optional[Markup] = None
        self._updating = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        self._info_label = QLabel("No markup selected")
        self._info_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(self._info_label)

        self._props_box = QGroupBox("Properties")
        form = QFormLayout(self._props_box)
        form.setContentsMargins(6, 10, 6, 6)

        # Stroke colour
        stroke_row = QHBoxLayout()
        self._stroke_btn = _colour_button(QColor("#d92828"))
        self._stroke_btn.clicked.connect(self._pick_stroke)
        self._stroke_label = QLabel("—")
        stroke_row.addWidget(self._stroke_btn)
        stroke_row.addWidget(self._stroke_label)
        stroke_row.addStretch()
        form.addRow("Stroke:", stroke_row)

        # Fill colour
        fill_row = QHBoxLayout()
        self._fill_btn = _colour_button(QColor(Qt.transparent))
        self._fill_btn.clicked.connect(self._pick_fill)
        self._fill_label = QLabel("none")
        fill_row.addWidget(self._fill_btn)
        fill_row.addWidget(self._fill_label)
        fill_row.addStretch()
        form.addRow("Fill:", fill_row)

        # Border width
        self._width_spin = QDoubleSpinBox()
        self._width_spin.setRange(0.1, 20.0)
        self._width_spin.setSingleStep(0.5)
        self._width_spin.setDecimals(1)
        self._width_spin.setSuffix(" pt")
        self._width_spin.valueChanged.connect(self._on_width)
        form.addRow("Border:", self._width_spin)

        # Opacity
        opacity_row = QHBoxLayout()
        self._opacity_slider = QSlider(Qt.Horizontal)
        self._opacity_slider.setRange(0, 100)
        self._opacity_slider.setValue(100)
        self._opacity_slider.valueChanged.connect(self._on_opacity)
        self._opacity_label = QLabel("100%")
        self._opacity_label.setFixedWidth(36)
        opacity_row.addWidget(self._opacity_slider)
        opacity_row.addWidget(self._opacity_label)
        form.addRow("Opacity:", opacity_row)

        # Hidden / Locked
        flags_row = QHBoxLayout()
        self._hidden_cb = QCheckBox("Hidden")
        self._hidden_cb.stateChanged.connect(self._on_hidden)
        self._locked_cb = QCheckBox("Locked")
        self._locked_cb.stateChanged.connect(self._on_locked)
        flags_row.addWidget(self._hidden_cb)
        flags_row.addWidget(self._locked_cb)
        flags_row.addStretch()
        form.addRow("Flags:", flags_row)

        # Info
        self._type_label = QLabel("")
        form.addRow("Type:", self._type_label)
        self._author_label = QLabel("")
        form.addRow("Author:", self._author_label)

        layout.addWidget(self._props_box)
        layout.addStretch()
        self._props_box.setVisible(False)

    def set_markup(self, markup: Optional[Markup]) -> None:
        self._markup = markup
        self._updating = True
        try:
            if markup is None:
                self._info_label.setVisible(True)
                self._props_box.setVisible(False)
                return
            self._info_label.setVisible(False)
            self._props_box.setVisible(True)

            stroke_colour = _rgb_to_qcolor(markup.colour)
            self._stroke_btn.setStyleSheet(
                f"background: {stroke_colour.name()}; border: 1px solid #888; "
                f"border-radius: 3px;")
            self._stroke_label.setText(stroke_colour.name() if markup.colour else "none")

            fill_colour = _rgb_to_qcolor(markup.fill_colour)
            self._fill_btn.setStyleSheet(
                f"background: {fill_colour.name() if markup.fill_colour else '#f0f0f0'}; "
                f"border: 1px solid #888; border-radius: 3px;")
            self._fill_label.setText(fill_colour.name() if markup.fill_colour else "none")

            self._width_spin.setValue(markup.border_width)
            self._opacity_slider.setValue(int(markup.opacity * 100))
            self._opacity_label.setText(f"{int(markup.opacity * 100)}%")
            self._hidden_cb.setChecked(markup.hidden)
            self._locked_cb.setChecked(markup.locked)
            self._type_label.setText(markup.subtype)
            self._author_label.setText(markup.author or "—")
        finally:
            self._updating = False

    def _pick_stroke(self) -> None:
        if self._markup is None:
            return
        current = _rgb_to_qcolor(self._markup.colour)
        colour = QColorDialog.getColor(current, self, "Stroke Colour")
        if colour.isValid():
            self.colour_changed.emit(_qcolor_to_rgb(colour))

    def _pick_fill(self) -> None:
        if self._markup is None:
            return
        current = _rgb_to_qcolor(self._markup.fill_colour)
        colour = QColorDialog.getColor(current, self, "Fill Colour")
        if colour.isValid():
            self.fill_changed.emit(_qcolor_to_rgb(colour))

    def _on_width(self, value: float) -> None:
        if not self._updating:
            self.border_width_changed.emit(value)

    def _on_opacity(self, value: int) -> None:
        self._opacity_label.setText(f"{value}%")
        if not self._updating:
            self.opacity_changed.emit(value / 100.0)

    def _on_hidden(self, state: int) -> None:
        if not self._updating:
            self.hidden_changed.emit(state == Qt.Checked.value)

    def _on_locked(self, state: int) -> None:
        if not self._updating:
            self.locked_changed.emit(state == Qt.Checked.value)
