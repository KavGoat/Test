"""Format Cells (Ctrl+1), as Excel's: Number, Alignment, Font, Border, Fill.

Every choice applies to the selected cells of the open table in one undo
step. The Number tab also takes a display unit: a quantity in the cell is
shown in it (5000 N shown as 5 kN), with the format's digits.
"""
from __future__ import annotations


from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFontComboBox, QFormLayout, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton,
                               QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from ..sheet.numfmt import format_value
from ..sheet.style import Border

CATEGORIES = ["General", "Number", "Currency", "Accounting", "Date", "Time", "Percentage",
              "Fraction", "Scientific", "Text", "Custom"]
DATES = ["d/mm/yyyy", "d-mmm-yy", "d mmmm yyyy", "dddd, d mmmm yyyy", "yyyy-mm-dd", "mmm-yy", "d/mm/yyyy h:mm"]
TIMES = ["h:mm", "h:mm:ss", "h:mm AM/PM", "[h]:mm", "mm:ss.0"]
def is_time_code(code: str) -> bool:
    """A date-kind format that shows only a time of day or a duration
    (h:mm, h:mm AM/PM, [h]:mm:ss, mm:ss.0): no day, month or year in it."""
    import re
    plain = re.sub(r'"[^"]*"|\\.', "", code or "")
    plain = re.sub(r"\[(?![hms]+\])[^\]]*\]", "", plain, flags=re.I).lower()
    plain = plain.replace("am/pm", "").replace("a/p", "")
    if "d" in plain or "y" in plain:
        return False
    return "h" in plain or "s" in plain


def category_of(code) -> str:
    """The Format Cells category a number format belongs to, as Excel names
    it (the table bar's format box shows the same, QA F-30)."""
    from ..sheet.numfmt import is_date_format

    code = code or "General"
    if code == "General":
        return "General"
    if "%" in code:
        return "Percentage"
    if "E+" in code.upper():
        return "Scientific"
    if "/" in code and "?" in code:
        return "Fraction"
    if is_date_format(code):
        return "Time" if code in TIMES or is_time_code(code) else "Date"
    if code == "@":
        return "Text"
    if any(sym in code for sym in "$€£¥"):
        return "Currency"
    plain = code.replace(",", "").replace("#", "").replace("0", "").replace(".", "")
    return "Number" if plain == "" else "Custom"


FRACTIONS = ["# ?/?", "# ??/??", "# ???/???", "# ?/2", "# ?/4", "# ?/8", "# ?/16", "# ?/10", "# ?/100"]
LINE_STYLES = ["thin", "medium", "thick", "dashed", "dotted", "double", "hair"]


class _Colour(QPushButton):
    def __init__(self, colour: str | None, none_text: str = "None"):
        super().__init__()
        self.none_text = none_text
        self.colour = colour
        self.clicked.connect(self._pick)
        self._show()

    def _show(self) -> None:
        if self.colour:
            self.setText(self.colour)
            self.setStyleSheet(f"background:{self.colour}; color:{'white' if QColor(self.colour).lightness() < 128 else 'black'}")
        else:
            self.setText(self.none_text)
            self.setStyleSheet("")

    def _pick(self) -> None:
        from .colorpicker import choose
        got = choose(self, self.colour, allow_none=True)
        if got is None:
            return
        self.colour = got or None
        self._show()


class FormatCellsDialog(QDialog):
    def __init__(self, tables, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Format Cells")
        self.tables = tables
        item = tables.item
        self.sheet = item.sheet
        self.wb = self.sheet.workbook
        self.cell = tables.active
        self.start = self.wb.style_of(self.sheet, *self.cell)
        self.value = self.sheet.value(*self.cell)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._number_tab(), "Number")
        tabs.addTab(self._alignment_tab(), "Alignment")
        tabs.addTab(self._font_tab(), "Font")
        tabs.addTab(self._border_tab(), "Border")
        tabs.addTab(self._fill_tab(), "Fill")
        layout.addWidget(tabs)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._update_sample()

    # -- Number ---------------------------------------------------------------------------
    def _number_tab(self) -> QWidget:
        w = QWidget()
        grid = QHBoxLayout(w)
        self.category = QListWidget()
        self.category.addItems(CATEGORIES)
        self.category.setFixedWidth(120)
        grid.addWidget(self.category)
        right = QVBoxLayout()
        self.sample = QLabel()
        self.sample.setFrameShape(QLabel.StyledPanel)
        right.addWidget(QLabel("Sample"))
        right.addWidget(self.sample)
        form = QFormLayout()
        self.decimals = QSpinBox()
        self.decimals.setRange(0, 30)
        self.decimals.setValue(2)
        # as the cells' right-click menu and an equation's (2026-10-19)
        self.significant = QCheckBox("Significant Figures")
        self.significant.setObjectName("formatCellsSignificant")
        self.significant.setToolTip("Decimal places counts significant figures, not places "
                                    "after the point (SMath's). An .xlsx keeps only the places")
        self.significant.setChecked(bool(self.start.significant))
        self.thousands = QCheckBox("Use 1000 separator (,)")
        self.negative = QComboBox()
        self.negative.addItems(["-1234.10", "[Red]1234.10", "(1234.10)", "[Red](1234.10)"])
        self.symbol = QComboBox()
        self.symbol.addItems(["$", "€", "£", "¥", "None"])
        self.types = QListWidget()
        self.custom = QLineEdit()
        # SMath's unit box: its black placeholder while empty or unfinished
        # (ui/unitbox.py); what it takes, in its tip
        from .unitbox import UnitField
        self.unit = UnitField(self.start.unit or "")
        self.unit.setToolTip("The unit quantities in the cell are shown in: e.g. kN, kN/m, "
                             "MPa, or a custom unit the equations define — blank: as typed")
        self.unit.setAccessibleName("Show quantities in")
        form.addRow("Decimal places:", self.decimals)
        form.addRow("", self.significant)
        form.addRow("", self.thousands)
        form.addRow("Symbol:", self.symbol)
        form.addRow("Negative numbers:", self.negative)
        form.addRow("Type:", self.types)
        form.addRow("Format code:", self.custom)
        form.addRow("Show quantities in:", self.unit)
        right.addLayout(form)
        grid.addLayout(right, 1)
        for widget in (self.decimals, self.thousands, self.negative, self.symbol):
            signal = getattr(widget, "valueChanged", None) or getattr(widget, "toggled", None) or \
                widget.currentIndexChanged
            signal.connect(self._rebuild_code)
        self.types.currentTextChanged.connect(self._type_chosen)
        self.custom.textEdited.connect(lambda _t: self._update_sample())
        self.significant.toggled.connect(lambda _on: self._update_sample())
        self.unit.textEdited.connect(lambda _t: self._update_sample())
        # flagged only once finished (Enter or leaving it), never while typed
        self.unit.editingFinished.connect(self._unit_finished)
        self.category.currentTextChanged.connect(self._category_chosen)
        code = self.start.number_format or "General"
        self.custom.setText(code)
        self.category.setCurrentRow(self._category_of(code))
        self.custom.setText(code)
        return w

    @staticmethod
    def _category_of(code: str) -> int:
        return CATEGORIES.index(category_of(code))

    def _category_chosen(self, name: str) -> None:
        self.types.blockSignals(True)
        self.types.clear()
        if name == "Date":
            self.types.addItems(DATES)
        elif name == "Time":
            self.types.addItems(TIMES)
        elif name == "Fraction":
            self.types.addItems(FRACTIONS)
        elif name == "Custom":
            self.types.addItems(["General", "0", "0.00", "#,##0", "#,##0.00", "0%", "0.00%", "0.00E+00",
                                 "# ?/?", "@", '0.0" mm"', "#,##0;[Red]-#,##0", "#,##0.00_);(#,##0.00)"])
        self.types.blockSignals(False)
        numeric = name in ("Number", "Currency", "Accounting", "Percentage", "Scientific")
        self.decimals.setEnabled(numeric)
        self.significant.setEnabled(numeric or name == "Custom")
        self.thousands.setEnabled(name == "Number")
        self.negative.setEnabled(name in ("Number", "Currency"))
        self.symbol.setEnabled(name in ("Currency", "Accounting"))
        self.types.setEnabled(name in ("Date", "Time", "Fraction", "Custom"))
        if name in ("Date", "Time", "Fraction") and self.types.count():
            self.types.setCurrentRow(0)
        self._rebuild_code()

    def _type_chosen(self, text: str) -> None:
        if text:
            self.custom.setText(text)
            self._update_sample()

    def _rebuild_code(self, *_):
        name = self.category.currentItem().text() if self.category.currentItem() else "General"
        d = self.decimals.value()
        dec = ("." + "0" * d) if d else ""
        code = self.custom.text()
        if name == "General":
            code = "General"
        elif name == "Number":
            body = ("#,##0" if self.thousands.isChecked() else "0") + dec
            neg = self.negative.currentIndex()
            code = [body, f"{body};[Red]{body}", f"{body}_);({body})", f"{body}_);[Red]({body})"][neg]
        elif name in ("Currency", "Accounting"):
            sym = self.symbol.currentText()
            sym = "" if sym == "None" else sym
            body = f"{sym}#,##0{dec}"
            neg = self.negative.currentIndex()
            code = [f"{body};-{body}", f"{body};[Red]{body}", f"{body}_);({body})",
                    f"{body}_);[Red]({body})"][neg]
            if name == "Accounting":
                code = f"_({sym}* #,##0{dec}_);_({sym}* ({body.replace(sym, '')});_({sym}* \"-\"??_);_(@_)"
        elif name == "Percentage":
            code = "0" + dec + "%"
        elif name == "Scientific":
            code = "0" + dec + "E+00"
        elif name == "Text":
            code = "@"
        elif name in ("Date", "Time", "Fraction", "Custom"):
            item = self.types.currentItem()
            if item is not None and name != "Custom":
                code = item.text()
        self.custom.setText(code)
        self._update_sample()

    def _unit_refusal(self):
        """Why the unit typed can't be the cell's, as SMath refuses it (a
        name that is no unit, °C on a force), or None."""
        unit = self.unit.unit_text()
        if not unit:
            return None
        from .cellunits import output_unit_refusal
        return output_unit_refusal(unit, self.value)

    def _unit_finished(self) -> None:
        """Red, with why, for a finished unit the cell can't take, as the
        unit boxes refuse them (the user, 2026-10-15) — only once it is
        finished, as SMath: nothing is said while it is typed (2026-10-19)."""
        why = self._unit_refusal()
        if why is not None:
            self.unit.flag(why)

    def _update_sample(self) -> None:
        unit = self.unit.unit_text() or None
        if unit and self._unit_refusal() is not None:
            unit = None                # not (yet) a unit: the sample as typed
        code = self.custom.text() or None
        try:
            shown = format_value(self.value, None if code == "General" else code, unit,
                                 significant=self._significant(code))
            self.sample.setText(shown.text or " ")
            self.sample.setStyleSheet(f"color:{shown.color}" if shown.color else "")
        except Exception:
            self.sample.setText("—")

    # -- Alignment --------------------------------------------------------------------------
    def _alignment_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        st = self.start
        self.h_align = QComboBox()
        self._h = ["general", "left", "center", "right", "fill", "justify", "centerAcross"]
        self.h_align.addItems(["General", "Left", "Centre", "Right", "Fill", "Justify", "Centre Across Selection"])
        self.h_align.setCurrentIndex(self._h.index(st.h_align) if st.h_align in self._h else 0)
        self.indent = QSpinBox()
        self.indent.setRange(0, 15)
        self.indent.setValue(st.indent)
        self.v_align = QComboBox()
        self._v = ["top", "center", "bottom"]
        self.v_align.addItems(["Top", "Centre", "Bottom"])
        self.v_align.setCurrentIndex(self._v.index(st.v_align) if st.v_align in self._v else 2)
        self.wrap = QCheckBox("Wrap text")
        self.wrap.setChecked(st.wrap)
        self.shrink = QCheckBox("Shrink to fit")
        self.shrink.setChecked(st.shrink)
        self.merge_box = QCheckBox("Merge cells")
        t, l, b, r = self.tables.selection()
        self.merge_box.setChecked(self.sheet.merge_at(t, l) == (t, l, b, r))
        self.rotation = QSpinBox()
        self.rotation.setRange(-90, 90)
        self.rotation.setSuffix("°")
        self.rotation.setValue(st.rotation if st.rotation != 255 else 90)
        form.addRow("Horizontal:", self.h_align)
        form.addRow("Indent:", self.indent)
        form.addRow("Vertical:", self.v_align)
        form.addRow("", self.wrap)
        form.addRow("", self.shrink)
        form.addRow("", self.merge_box)
        form.addRow("Orientation:", self.rotation)
        return w

    # -- Font --------------------------------------------------------------------------------
    def _font_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        st = self.start
        self.font_family = QFontComboBox()
        from PySide6.QtGui import QFont
        self.font_family.setCurrentFont(QFont(st.font or "Calibri"))
        self.font_size = QDoubleSpinBox()
        self.font_size.setRange(1, 409)
        self.font_size.setValue(st.size or 11.0)
        self.bold = QCheckBox("Bold")
        self.bold.setChecked(st.bold)
        self.italic = QCheckBox("Italic")
        self.italic.setChecked(st.italic)
        self.underline = QComboBox()
        self.underline.addItems(["None", "Single", "Double"])
        self.underline.setCurrentIndex({"": 0, "single": 1, "double": 2}.get(st.underline, 0))
        self.strike = QCheckBox("Strikethrough")
        self.strike.setChecked(st.strike)
        self.text_colour = _Colour(st.color, "Automatic")
        form.addRow("Font:", self.font_family)
        form.addRow("Size:", self.font_size)
        row = QHBoxLayout()
        row.addWidget(self.bold)
        row.addWidget(self.italic)
        form.addRow("Style:", row)
        form.addRow("Underline:", self.underline)
        form.addRow("", self.strike)
        form.addRow("Colour:", self.text_colour)
        return w

    # -- Border ------------------------------------------------------------------------------
    def _border_tab(self) -> QWidget:
        w = QWidget()
        layout = QGridLayout(w)
        self.line_style = QComboBox()
        self.line_style.addItems([s.capitalize() for s in LINE_STYLES])
        self.line_colour = _Colour("#000000", "Automatic")
        layout.addWidget(QLabel("Line style:"), 0, 0)
        layout.addWidget(self.line_style, 0, 1)
        layout.addWidget(QLabel("Colour:"), 1, 0)
        layout.addWidget(self.line_colour, 1, 1)
        self.border_choice = None
        presets = QHBoxLayout()
        for key, label in (("none", "None"), ("outside", "Outline"), ("inside", "Inside"), ("all", "All")):
            button = QPushButton(label)
            button.setCheckable(True)
            button.clicked.connect(lambda _c=False, k=key, b=button: self._choose_border(k, b))
            presets.addWidget(button)
        layout.addLayout(presets, 2, 0, 1, 2)
        sides = QHBoxLayout()
        for key, label in (("top", "Top"), ("bottom", "Bottom"), ("left", "Left"), ("right", "Right")):
            button = QPushButton(label)
            button.setCheckable(True)
            button.clicked.connect(lambda _c=False, k=key, b=button: self._choose_border(k, b))
            sides.addWidget(button)
        layout.addLayout(sides, 3, 0, 1, 2)
        self._border_buttons = [presets.itemAt(i).widget() for i in range(presets.count())] + \
            [sides.itemAt(i).widget() for i in range(sides.count())]
        self.border_choices: list = []
        return w

    def _choose_border(self, key: str, button) -> None:
        if key in ("none", "outside", "inside", "all"):
            for b in self._border_buttons:
                if b is not button:
                    b.setChecked(False)
            self.border_choices = [key] if button.isChecked() else []
        else:
            if button.isChecked():
                self.border_choices = [k for k in self.border_choices if k not in ("none", "all")] + [key]
            else:
                self.border_choices = [k for k in self.border_choices if k != key]

    # -- Fill ----------------------------------------------------------------------------------
    def _fill_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.fill = _Colour(self.start.fill, "No colour")
        clear = QPushButton("No colour")
        clear.clicked.connect(lambda: (setattr(self.fill, "colour", None), self.fill._show()))
        form.addRow("Background:", self.fill)
        form.addRow("", clear)
        return w

    # -- applying --------------------------------------------------------------------------------
    def _significant(self, code) -> bool:
        """Significant Figures, where the format has places to count."""
        from ..sheet.numfmt import places_of
        return (self.significant.isChecked() and self.significant.isEnabled()
                and places_of(None if code == "General" else code) is not None)

    def changes(self) -> dict:
        """The style fields that differ from what the active cell has."""
        st = self.start
        unit = self.unit.unit_text() or None
        if unit:
            from .cellunits import output_unit_refusal
            if output_unit_refusal(unit, self.value) is not None:
                unit = st.unit
        code = self.custom.text().strip() or "General"
        wanted = {
            "number_format": None if code == "General" else code,
            "significant": self._significant(code),
            "unit": unit,
            "h_align": self._h[self.h_align.currentIndex()],
            "indent": self.indent.value(),
            "v_align": self._v[self.v_align.currentIndex()],
            "wrap": self.wrap.isChecked(),
            "shrink": self.shrink.isChecked(),
            "rotation": self.rotation.value(),
            "font": None if self.font_family.currentFont().family() == "Calibri" and not st.font
            else self.font_family.currentFont().family(),
            "size": None if self.font_size.value() == 11.0 and not st.size else self.font_size.value(),
            "bold": self.bold.isChecked(),
            "italic": self.italic.isChecked(),
            "underline": ["", "single", "double"][self.underline.currentIndex()],
            "strike": self.strike.isChecked(),
            "color": self.text_colour.colour if self.text_colour.colour not in (None, "#000000") else
            (None if not st.color else self.text_colour.colour),
            "fill": self.fill.colour,
        }
        return {k: v for k, v in wanted.items() if getattr(st, k) != v}

    def accept(self) -> None:
        tables = self.tables
        changes = self.changes()
        t, l, b, r = tables.selection()
        merge_now = self.merge_box.isChecked()
        merged = self.sheet.merge_at(t, l) == (t, l, b, r)
        border = Border(LINE_STYLES[self.line_style.currentIndex()], self.line_colour.colour or "#000000")
        choices = list(self.border_choices)

        def change(wb, sheet):
            if changes:
                wb.format_block(sheet, t, l, b, r, **changes)
            for which in choices:
                wb.border_block(sheet, t, l, b, r, which, border)
            if merge_now and not merged and (t, l) != (b, r):
                wb.merge(sheet, t, l, b, r)
            elif not merge_now and merged:
                wb.unmerge(sheet, t, l, b, r)
        tables._change("Format Cells", change)
        super().accept()
