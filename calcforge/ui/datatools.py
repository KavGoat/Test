"""Excel's Home ▸ Conditional Formatting and Data tools for an open table:
the menus, and the dialogs behind them (sheet/condfmt.py, data.py,
validation.py, find.py). Every change is one undo step (TableEditing._change).

Dialogs are made by functions so tests (and windows with prompts turned off)
can fill them in and accept them without showing them.
"""
from __future__ import annotations

import copy

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMenu, QPlainTextEdit, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ..sheet import condfmt, data, find, validation
from ..sheet.refs import area_text, col_letters, parse_range

PRESET_LOOKS = [("Light red fill with dark red text", {"fill": "#ffc7ce", "color": "#9c0006"}),
                ("Yellow fill with dark yellow text", {"fill": "#ffeb9c", "color": "#9c5700"}),
                ("Green fill with dark green text", {"fill": "#c6efce", "color": "#006100"}),
                ("Light red fill", {"fill": "#ffc7ce"}), ("Red text", {"color": "#9c0006"}),
                ("Bold", {"bold": True})]

CELL_OPS = [("greater", "Greater Than"), ("less", "Less Than"), ("between", "Between"),
            ("equal", "Equal To"), ("notEqual", "Not Equal To"), ("greaterOrEqual", "Greater Or Equal"),
            ("lessOrEqual", "Less Or Equal"), ("notBetween", "Not Between")]


def _show(window, dialog) -> bool:
    if not getattr(window, "interactive_prompts", True):
        window._last_data_dialog = dialog
        return False
    return dialog.exec() == QDialog.Accepted


def _ranges(tables) -> list:
    t, l, b, r = tables.selection()
    return [[t, l, b, r]]


def add_rule(tables, rule: dict) -> None:
    """A new rule for the selected cells, at the top (highest priority)."""
    rule = dict(rule)
    rule.setdefault("ranges", _ranges(tables))
    sheet = tables.item.sheet
    rules = [rule] + copy.deepcopy(sheet.cond_rules)
    tables._change("Conditional formatting", lambda wb, s: wb.set_cond_rules(s, rules))


def clear_rules(tables, everywhere: bool) -> None:
    sheet = tables.item.sheet
    if everywhere:
        rules = []
    else:
        t, l, b, r = tables.selection()
        rules = []
        for rule in copy.deepcopy(sheet.cond_rules):
            kept = [rg for rg in rule["ranges"] if rg[2] < t or rg[0] > b or rg[3] < l or rg[1] > r]
            if kept:
                rule["ranges"] = kept
                rules.append(rule)
    tables._change("Clear rules", lambda wb, s: wb.set_cond_rules(s, rules))


# -- the menus -------------------------------------------------------------------------------
def fill_menu(menu: QMenu, tables) -> None:
    """Conditional formatting and the Data tools, for the table's right-click menu."""
    cf = menu.addMenu("Conditional Formatting")
    hi = cf.addMenu("Highlight Cells Rules")
    for op, label in CELL_OPS[:5]:
        hi.addAction(label + "…", lambda o=op: cell_rule_dialog(tables, o))
    hi.addAction("Text that Contains…", lambda: text_rule_dialog(tables))
    hi.addAction("A Date Occurring…", lambda: date_rule_dialog(tables))
    hi.addAction("Duplicate Values", lambda: add_rule(tables, {"type": "duplicate",
                                                               "format": PRESET_LOOKS[0][1]}))
    top = cf.addMenu("Top/Bottom Rules")
    top.addAction("Top 10 Items", lambda: add_rule(tables, {"type": "top", "n": 10, "format": PRESET_LOOKS[0][1]}))
    top.addAction("Top 10%", lambda: add_rule(tables, {"type": "top", "n": 10, "percent": True,
                                                       "format": PRESET_LOOKS[0][1]}))
    top.addAction("Bottom 10 Items", lambda: add_rule(tables, {"type": "bottom", "n": 10,
                                                               "format": PRESET_LOOKS[0][1]}))
    top.addAction("Above Average", lambda: add_rule(tables, {"type": "above", "format": PRESET_LOOKS[0][1]}))
    top.addAction("Below Average", lambda: add_rule(tables, {"type": "below", "format": PRESET_LOOKS[0][1]}))
    bars = cf.addMenu("Data Bars")
    for label, colour in (("Blue", "#638ec6"), ("Green", "#63c384"), ("Red", "#ff555a"),
                          ("Orange", "#ffb628"), ("Purple", "#d6007b")):
        bars.addAction(label, lambda c=colour: add_rule(tables, {"type": "databar", "color": c}))
    scales = cf.addMenu("Color Scales")
    for label, colours in (("Green - Yellow - Red", ["#63be7b", "#ffeb84", "#f8696b"]),
                           ("Red - Yellow - Green", ["#f8696b", "#ffeb84", "#63be7b"]),
                           ("White - Red", ["#ffffff", "#f8696b"]), ("White - Green", ["#ffffff", "#63be7b"]),
                           ("Blue - White - Red", ["#5a8ac6", "#ffffff", "#f8696b"])):
        scales.addAction(label, lambda c=colours: add_rule(tables, {"type": "scale", "colors": c}))
    icons = cf.addMenu("Icon Sets")
    for key, label in (("arrows", "3 Arrows"), ("traffic", "3 Traffic Lights"), ("flags", "3 Flags"),
                       ("symbols", "3 Symbols")):
        icons.addAction(label, lambda k=key: add_rule(tables, {"type": "icons", "set": k}))
    cf.addSeparator()
    cf.addAction("New Rule…", lambda: formula_rule_dialog(tables))
    clear = cf.addMenu("Clear Rules")
    clear.addAction("From Selected Cells", lambda: clear_rules(tables, False))
    clear.addAction("From Entire Table", lambda: clear_rules(tables, True))
    cf.addAction("Manage Rules…", lambda: manage_rules_dialog(tables))
    dm = menu.addMenu("Data")
    dm.addAction("Sort A to Z", lambda: quick_sort(tables, True))
    dm.addAction("Sort Z to A", lambda: quick_sort(tables, False))
    dm.addAction("Custom Sort…", lambda: sort_dialog(tables))
    sheet = tables.item.sheet
    flt = dm.addAction("Filter", lambda: toggle_filter(tables))
    flt.setCheckable(True)
    flt.setChecked(sheet.filter is not None)
    clr = dm.addAction("Clear Filter", lambda: clear_filter(tables))
    clr.setEnabled(bool(sheet.filter and sheet.filter.get("criteria")))
    dm.addSeparator()
    dm.addAction("Remove Duplicates…", lambda: duplicates_dialog(tables))
    dm.addAction("Text to Columns…", lambda: text_columns_dialog(tables))
    dm.addSeparator()
    dm.addAction("Data Validation…", lambda: validation_dialog(tables))
    dm.addAction("Circle Invalid Data", lambda: circle_invalid(tables))
    dm.addAction("Clear Validation Circles", lambda: clear_circles(tables))
    cm = menu.addMenu("Comment")
    cell = sheet.cells.get(tables.active)
    has = bool(cell and cell.comment)
    cm.addAction("Edit Comment…" if has else "New Comment…", lambda: comment_dialog(tables))
    rm = cm.addAction("Delete Comment", lambda: set_comment(tables, None))
    rm.setEnabled(has)
    menu.addAction("Find && Replace…", lambda: find_dialog(tables))


# -- conditional formatting dialogs ---------------------------------------------------------------
class _LookChoice(QComboBox):
    def __init__(self):
        super().__init__()
        for label, look in PRESET_LOOKS:
            self.addItem(label, look)

    def look(self) -> dict:
        return dict(self.currentData())


class CellRuleDialog(QDialog):
    def __init__(self, tables, op: str):
        super().__init__(tables.view)
        self.tables, self.op = tables, op
        self.setWindowTitle(dict(CELL_OPS)[op])
        layout = QFormLayout(self)
        self.a = QLineEdit()
        self.a.setPlaceholderText("a value (5, 200 kN), or =B1")
        layout.addRow("Format cells that are " + dict(CELL_OPS)[op].lower() + ":", self.a)
        self.b = QLineEdit()
        if op in ("between", "notBetween"):
            layout.addRow("and", self.b)
        self.look = _LookChoice()
        layout.addRow("with", self.look)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def accept(self) -> None:
        rule = {"type": "cell", "op": self.op, "a": self.a.text().strip(), "format": self.look.look()}
        if self.op in ("between", "notBetween"):
            rule["b"] = self.b.text().strip()
        add_rule(self.tables, rule)
        super().accept()


def cell_rule_dialog(tables, op: str):
    dialog = CellRuleDialog(tables, op)
    _show(tables.view.window, dialog)
    return dialog


class TextRuleDialog(QDialog):
    def __init__(self, tables):
        super().__init__(tables.view)
        self.tables = tables
        self.setWindowTitle("Text that Contains")
        layout = QFormLayout(self)
        self.how = QComboBox()
        for key, label in (("contains", "containing"), ("notContains", "not containing"),
                           ("begins", "beginning with"), ("ends", "ending with")):
            self.how.addItem(label, key)
        self.text = QLineEdit()
        self.look = _LookChoice()
        layout.addRow("Format cells", self.how)
        layout.addRow("the text", self.text)
        layout.addRow("with", self.look)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def accept(self) -> None:
        add_rule(self.tables, {"type": "text", "how": self.how.currentData(), "text": self.text.text(),
                               "format": self.look.look()})
        super().accept()


def text_rule_dialog(tables):
    dialog = TextRuleDialog(tables)
    _show(tables.view.window, dialog)
    return dialog


class DateRuleDialog(QDialog):
    def __init__(self, tables):
        super().__init__(tables.view)
        self.tables = tables
        self.setWindowTitle("A Date Occurring")
        layout = QFormLayout(self)
        self.when = QComboBox()
        for key, label in (("yesterday", "Yesterday"), ("today", "Today"), ("tomorrow", "Tomorrow"),
                           ("last7", "In the last 7 days"), ("lastMonth", "Last month"),
                           ("thisMonth", "This month"), ("nextMonth", "Next month")):
            self.when.addItem(label, key)
        self.look = _LookChoice()
        layout.addRow("Format cells that contain a date occurring", self.when)
        layout.addRow("with", self.look)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def accept(self) -> None:
        add_rule(self.tables, {"type": "date", "when": self.when.currentData(), "format": self.look.look()})
        super().accept()


def date_rule_dialog(tables):
    dialog = DateRuleDialog(tables)
    _show(tables.view.window, dialog)
    return dialog


class _FormatPicker(QWidget):
    """Fill, font colour, bold, italic, underline, strikethrough, number format."""

    def __init__(self, fmt: dict | None = None):
        super().__init__()
        fmt = fmt or {}
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.fill = fmt.get("fill")
        self.color = fmt.get("color")
        self.fill_button = QPushButton()
        self.fill_button.clicked.connect(lambda: self._pick("fill"))
        self.color_button = QPushButton()
        self.color_button.clicked.connect(lambda: self._pick("color"))
        self.bold = QCheckBox("Bold")
        self.bold.setChecked(bool(fmt.get("bold")))
        self.italic = QCheckBox("Italic")
        self.italic.setChecked(bool(fmt.get("italic")))
        self.underline = QCheckBox("Underline")
        self.underline.setChecked(bool(fmt.get("underline")))
        self.strike = QCheckBox("Strike")
        self.strike.setChecked(bool(fmt.get("strike")))
        self.number = QLineEdit(fmt.get("number_format") or "")
        self.number.setPlaceholderText("number format")
        self.number.setFixedWidth(90)
        for w in (self.fill_button, self.color_button, self.bold, self.italic, self.underline,
                  self.strike, self.number):
            layout.addWidget(w)
        self._labels()

    def _labels(self):
        self.fill_button.setText(f"Fill {self.fill or 'none'}")
        self.fill_button.setStyleSheet(f"background:{self.fill}" if self.fill else "")
        self.color_button.setText(f"Font {self.color or 'auto'}")
        self.color_button.setStyleSheet(f"color:{self.color}" if self.color else "")

    def _pick(self, which):
        got = QColorDialog.getColor(QColor(getattr(self, which) or "#ffc7ce"), self)
        if got.isValid():
            setattr(self, which, got.name())
            self._labels()

    def format(self) -> dict:
        out = {}
        if self.fill:
            out["fill"] = self.fill
        if self.color:
            out["color"] = self.color
        for key in ("bold", "italic", "underline", "strike"):
            if getattr(self, key).isChecked():
                out[key] = True
        if self.number.text().strip():
            out["number_format"] = self.number.text().strip()
        return out


class FormulaRuleDialog(QDialog):
    """New Formatting Rule: "Use a formula to determine which cells to format"."""

    def __init__(self, tables):
        super().__init__(tables.view)
        self.tables = tables
        self.setWindowTitle("New Formatting Rule")
        layout = QFormLayout(self)
        t, l, _b, _r = tables.selection()
        self.formula = QLineEdit("=")
        self.formula.setToolTip(f"Written for the top-left cell {col_letters(l)}{t + 1}; relative "
                                "references move across the range, as in Excel")
        layout.addRow("Format values where this formula is true:", self.formula)
        self.picker = _FormatPicker({"fill": "#ffc7ce"})
        layout.addRow("Format:", self.picker)
        self.stop = QCheckBox("Stop If True")
        layout.addRow("", self.stop)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def accept(self) -> None:
        text = self.formula.text().strip()
        if not text.startswith("="):
            text = "=" + text
        add_rule(self.tables, {"type": "formula", "formula": text, "format": self.picker.format(),
                               "stop": self.stop.isChecked()})
        super().accept()


def formula_rule_dialog(tables):
    dialog = FormulaRuleDialog(tables)
    _show(tables.view.window, dialog)
    return dialog


class ManageRulesDialog(QDialog):
    """Conditional Formatting Rules Manager: order, applies to, stop if true, delete."""

    def __init__(self, tables):
        super().__init__(tables.view)
        self.tables = tables
        self.setWindowTitle("Conditional Formatting Rules Manager")
        self.rules = copy.deepcopy(tables.item.sheet.cond_rules)
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Rule (in order applied)", "Applies to", "Stop If True"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)
        row = QHBoxLayout()
        for text, slot in (("Delete Rule", self.delete), ("Move Up", lambda: self.move(-1)),
                           ("Move Down", lambda: self.move(1))):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        layout.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._fill()
        self.resize(620, 360)

    def _fill(self):
        self.table.setRowCount(0)
        for rule in self.rules:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(condfmt.describe(rule)))
            edit = QLineEdit(",".join(area_text(*rg) for rg in rule["ranges"]))
            self.table.setCellWidget(r, 1, edit)
            stop = QCheckBox()
            stop.setChecked(bool(rule.get("stop")))
            self.table.setCellWidget(r, 2, stop)

    def _read(self):
        for r, rule in enumerate(self.rules):
            ranges = []
            for part in self.table.cellWidget(r, 1).text().split(","):
                ref = parse_range(part.strip().replace("$", ""))
                if ref is None:
                    continue
                if hasattr(ref, "top"):
                    ranges.append([ref.top, ref.left, ref.bottom, ref.right])
                else:
                    ranges.append([ref.row, ref.col, ref.row, ref.col])
            if ranges:
                rule["ranges"] = ranges
            rule["stop"] = self.table.cellWidget(r, 2).isChecked()

    def delete(self):
        r = self.table.currentRow()
        if 0 <= r < len(self.rules):
            self._read()
            del self.rules[r]
            self._fill()

    def move(self, step):
        r = self.table.currentRow()
        t = r + step
        if 0 <= r < len(self.rules) and 0 <= t < len(self.rules):
            self._read()
            self.rules[r], self.rules[t] = self.rules[t], self.rules[r]
            self._fill()
            self.table.setCurrentCell(t, 0)

    def accept(self) -> None:
        self._read()
        rules = self.rules
        self.tables._change("Conditional formatting", lambda wb, s: wb.set_cond_rules(s, rules))
        super().accept()


def manage_rules_dialog(tables):
    dialog = ManageRulesDialog(tables)
    _show(tables.view.window, dialog)
    return dialog


# -- sort and filter ------------------------------------------------------------------------------------
def _sort_block(tables):
    """What Sort sorts: the selection if it is more than one cell; else the
    whole table (or the filter's block), its first row taken as headings
    when it holds text over numbers."""
    item = tables.item
    sheet = item.sheet
    t, l, b, r = tables.selection()
    if (t, l) != (b, r):
        return (t, l, b, r), False
    if sheet.filter is not None:
        return tuple(sheet.filter["range"]), True
    used = sheet.data_area()
    if used is None:
        return None, False
    rows, cols = item.size
    block = (0, 0, min(used[2], rows - 1), min(used[3], cols - 1))
    first = [sheet.value(0, c) for c in range(block[1], block[3] + 1)]
    second = [sheet.value(1, c) for c in range(block[1], block[3] + 1)] if block[2] >= 1 else []
    header = any(isinstance(v, str) and v for v in first) and any(
        not isinstance(v, str) for v in second if v is not None)
    return block, header


def quick_sort(tables, ascending: bool, col: int | None = None) -> None:
    block, header = _sort_block(tables)
    if block is None:
        return
    key = tables.active[1] if col is None else col
    tables._change("Sort", lambda wb, s: data.sort_block(wb, s, *block, [(key, ascending)], header))


class SortDialog(QDialog):
    def __init__(self, tables):
        super().__init__(tables.view)
        self.tables = tables
        self.setWindowTitle("Sort")
        self.block, header = _sort_block(tables)
        layout = QVBoxLayout(self)
        self.header = QCheckBox("My data has headers")
        self.header.setChecked(header)
        layout.addWidget(self.header)
        self.levels = QVBoxLayout()
        layout.addLayout(self.levels)
        add = QPushButton("Add Level")
        add.clicked.connect(self.add_level)
        layout.addWidget(add, 0, Qt.AlignLeft)
        self.rows = []
        self.add_level()
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def add_level(self, col=None, ascending=True):
        if self.block is None:
            return
        t, l, b, r = self.block
        sheet = self.tables.item.sheet
        row = QHBoxLayout()
        column = QComboBox()
        for c in range(l, r + 1):
            head = data.shown(sheet, t, c) if self.header.isChecked() else ""
            column.addItem(head or f"Column {col_letters(c)}", c)
        if col is not None:
            column.setCurrentIndex(max(0, col - l))
        order = QComboBox()
        order.addItems(["A to Z (smallest first)", "Z to A (largest first)"])
        order.setCurrentIndex(0 if ascending else 1)
        row.addWidget(QLabel("Then by" if self.rows else "Sort by"))
        row.addWidget(column, 1)
        row.addWidget(order)
        self.levels.addLayout(row)
        self.rows.append((column, order))

    def keys(self) -> list:
        return [(column.currentData(), order.currentIndex() == 0) for column, order in self.rows]

    def accept(self) -> None:
        if self.block is not None:
            block, keys, header = self.block, self.keys(), self.header.isChecked()
            self.tables._change("Sort", lambda wb, s: data.sort_block(wb, s, *block, keys, header))
        super().accept()


def sort_dialog(tables):
    dialog = SortDialog(tables)
    _show(tables.view.window, dialog)
    return dialog


class DuplicatesDialog(QDialog):
    """Remove Duplicates: which columns make a row a repeat of another."""

    def __init__(self, tables):
        super().__init__(tables.view)
        self.tables = tables
        self.setWindowTitle("Remove Duplicates")
        self.block, header = _sort_block(tables)
        layout = QVBoxLayout(self)
        self.header = QCheckBox("My data has headers")
        self.header.setChecked(header)
        layout.addWidget(self.header)
        layout.addWidget(QLabel("Columns:"))
        self.columns = QListWidget()
        layout.addWidget(self.columns)
        self.header.toggled.connect(lambda _on: self._fill())
        self._fill()
        self.result_text = ""
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _fill(self):
        self.columns.clear()
        if self.block is None:
            return
        t, l, _b, r = self.block
        sheet = self.tables.item.sheet
        for c in range(l, r + 1):
            head = data.shown(sheet, t, c) if self.header.isChecked() else ""
            entry = QListWidgetItem(head or f"Column {col_letters(c)}")
            entry.setData(Qt.UserRole, c)
            entry.setFlags(entry.flags() | Qt.ItemIsUserCheckable)
            entry.setCheckState(Qt.Checked)
            self.columns.addItem(entry)

    def chosen(self) -> list:
        return [self.columns.item(i).data(Qt.UserRole) for i in range(self.columns.count())
                if self.columns.item(i).checkState() == Qt.Checked]

    def accept(self) -> None:
        cols = self.chosen()
        if self.block is not None and cols:
            block, header, got = self.block, self.header.isChecked(), []
            self.tables._change("Remove duplicates", lambda wb, s: got.append(
                data.remove_duplicates(wb, s, *block, cols, header)))
            removed, kept = got[0] if got else (0, 0)
            # Excel's own words
            self.result_text = (f"{removed} duplicate value{'s' if removed != 1 else ''} found and removed; "
                                f"{kept} unique value{'s' if kept != 1 else ''} remain."
                                if removed else "No duplicate values found.")
            self.tables.view.statusMessage.emit(self.result_text)
        super().accept()


def duplicates_dialog(tables):
    dialog = DuplicatesDialog(tables)
    _show(tables.view.window, dialog)
    return dialog


class TextColumnsDialog(QDialog):
    """Text to Columns: the selected column split at its delimiters."""

    def __init__(self, tables):
        super().__init__(tables.view)
        self.tables = tables
        self.setWindowTitle("Convert Text to Columns")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Split each cell of the selected column at:"))
        self.tab, self.semicolon, self.comma, self.space = (QCheckBox(t) for t in
                                                            ("Tab", "Semicolon", "Comma", "Space"))
        self.tab.setChecked(True)
        row = QHBoxLayout()
        for box in (self.tab, self.semicolon, self.comma, self.space):
            row.addWidget(box)
        self.other = QLineEdit()
        self.other.setMaxLength(1)
        self.other.setFixedWidth(28)
        row.addWidget(QLabel("Other:"))
        row.addWidget(self.other)
        row.addStretch(1)
        layout.addLayout(row)
        self.together = QCheckBox("Treat consecutive delimiters as one")
        layout.addWidget(self.together)
        self.qualifier = QComboBox()
        self.qualifier.addItem('"', '"')
        self.qualifier.addItem("'", "'")
        self.qualifier.addItem("{none}", "")
        form = QFormLayout()
        form.addRow("Text qualifier:", self.qualifier)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def delimiters(self) -> str:
        out = "".join(ch for box, ch in ((self.tab, "\t"), (self.semicolon, ";"), (self.comma, ","),
                                         (self.space, " ")) if box.isChecked())
        return out + self.other.text()

    def accept(self) -> None:
        t, l, b, r = self.tables.selection()
        if l != r:
            self.tables.view.statusMessage.emit("Text to Columns works on one column at a time")
            return
        delims, together, qual = self.delimiters(), self.together.isChecked(), self.qualifier.currentData()
        item = self.tables.item
        widest = max((len(data.split_text(item.sheet.input(row, l), delims, together, qual))
                      for row in range(t, b + 1)), default=1)

        def change(wb, sheet):
            if l + widest > item.size[1]:
                item.resize_table(item.size[0], l + widest)      # room for the pieces first
            data.text_to_columns(wb, sheet, t, l, b, delims, together, qual)
        self.tables._change("Text to columns", change)
        super().accept()


def text_columns_dialog(tables):
    dialog = TextColumnsDialog(tables)
    _show(tables.view.window, dialog)
    return dialog


def toggle_filter(tables) -> None:
    sheet = tables.item.sheet
    if sheet.filter is not None:
        tables._change("Filter", lambda wb, s: data.set_filter(wb, s, None))
        return
    t, l, b, r = tables.selection()
    if (t, l) == (b, r):
        used = sheet.data_area()
        rows, cols = tables.item.size
        bottom = max(1, min(used[2], rows - 1)) if used else rows - 1
        right = min(used[3], cols - 1) if used else cols - 1
        block = (0, 0, bottom, right)
    else:
        block = (t, l, b, r)
    tables._change("Filter", lambda wb, s: data.set_filter(wb, s, block))


def clear_filter(tables) -> None:
    sheet = tables.item.sheet

    def change(wb, s):
        for col in list(s.filter.get("criteria", {})):
            data.set_criteria(wb, s, col, None)
    if sheet.filter is not None:
        tables._change("Clear filter", change)


def filter_menu(tables, col: int, global_pos) -> QMenu:
    """The drop-down of a filtered column: sort, values to show, conditions."""
    menu = QMenu(tables.view)
    menu.addAction("Sort A to Z", lambda: _sort_filtered(tables, col, True))
    menu.addAction("Sort Z to A", lambda: _sort_filtered(tables, col, False))
    menu.addSeparator()
    clear = menu.addAction("Clear Filter From This Column",
                           lambda: tables._change("Filter", lambda wb, s: data.set_criteria(wb, s, col, None)))
    clear.setEnabled(col in tables.item.sheet.filter.get("criteria", {}))
    menu.addAction("Choose Values…", lambda: values_dialog(tables, col))
    menu.addAction("Number/Text Filter…", lambda: custom_filter_dialog(tables, col))
    menu.addAction("Top 10…", lambda: tables._change("Filter", lambda wb, s: data.set_criteria(
        wb, s, col, {"kind": "top", "n": 10})))
    if global_pos is not None and getattr(tables.view.window, "interactive_prompts", True):
        menu.exec(global_pos)
    return menu


def _sort_filtered(tables, col, ascending):
    block = tuple(tables.item.sheet.filter["range"])
    tables._change("Sort", lambda wb, s: data.sort_block(wb, s, *block, [(col, ascending)], True))


class ValuesDialog(QDialog):
    def __init__(self, tables, col: int):
        super().__init__(tables.view)
        self.tables, self.col = tables, col
        self.setWindowTitle("Filter")
        sheet = tables.item.sheet
        crit = sheet.filter.get("criteria", {}).get(col)
        chosen = set(crit["values"]) if crit and crit.get("kind") == "values" else None
        layout = QVBoxLayout(self)
        self.list = QListWidget()
        for text in data.column_values(sheet, col):
            entry = QListWidgetItem(text or "(Blanks)")
            entry.setData(Qt.UserRole, text)
            entry.setFlags(entry.flags() | Qt.ItemIsUserCheckable)
            entry.setCheckState(Qt.Checked if chosen is None or text in chosen else Qt.Unchecked)
            self.list.addItem(entry)
        layout.addWidget(self.list)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def set_checked(self, texts: list) -> None:
        for i in range(self.list.count()):
            entry = self.list.item(i)
            entry.setCheckState(Qt.Checked if entry.data(Qt.UserRole) in texts else Qt.Unchecked)

    def accept(self) -> None:
        values = [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())
                  if self.list.item(i).checkState() == Qt.Checked]
        crit = None if len(values) == self.list.count() else {"kind": "values", "values": values}
        col = self.col
        self.tables._change("Filter", lambda wb, s: data.set_criteria(wb, s, col, crit))
        super().accept()


def values_dialog(tables, col):
    dialog = ValuesDialog(tables, col)
    _show(tables.view.window, dialog)
    return dialog


class CustomFilterDialog(QDialog):
    def __init__(self, tables, col: int):
        super().__init__(tables.view)
        self.tables, self.col = tables, col
        self.setWindowTitle("Custom AutoFilter")
        layout = QFormLayout(self)
        ops = [("=", "equals"), ("<>", "does not equal"), (">", "is greater than"),
               (">=", "is greater than or equal to"), ("<", "is less than"),
               ("<=", "is less than or equal to"), ("=*", "contains"), ("<>*", "does not contain")]
        self.op1, self.op2 = QComboBox(), QComboBox()
        for box in (self.op1, self.op2):
            for key, label in ops:
                box.addItem(label, key)
        self.v1, self.v2 = QLineEdit(), QLineEdit()
        self.join = QComboBox()
        self.join.addItems(["And", "Or"])
        layout.addRow(self.op1, self.v1)
        layout.addRow("", self.join)
        layout.addRow(self.op2, self.v2)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    @staticmethod
    def _condition(op, text):
        if not text:
            return None
        if op == "=*":
            return f"*{text}*"
        if op == "<>*":
            return f"<>*{text}*"
        return op + text

    def accept(self) -> None:
        conditions = [c for c in (self._condition(self.op1.currentData(), self.v1.text().strip()),
                                  self._condition(self.op2.currentData(), self.v2.text().strip())) if c]
        crit = {"kind": "custom", "conditions": conditions, "join": self.join.currentText().lower()} \
            if conditions else None
        col = self.col
        self.tables._change("Filter", lambda wb, s: data.set_criteria(wb, s, col, crit))
        super().accept()


def custom_filter_dialog(tables, col):
    dialog = CustomFilterDialog(tables, col)
    _show(tables.view.window, dialog)
    return dialog


# -- data validation -------------------------------------------------------------------------------
class ValidationDialog(QDialog):
    def __init__(self, tables):
        super().__init__(tables.view)
        self.tables = tables
        self.setWindowTitle("Data Validation")
        sheet = tables.item.sheet
        now = validation.at(sheet, *tables.active) or {}
        layout = QFormLayout(self)
        self.kind = QComboBox()
        for key, label in (("any", "Any value"), ("whole", "Whole number"), ("decimal", "Decimal"),
                           ("list", "List"), ("date", "Date"), ("time", "Time"),
                           ("length", "Text length"), ("custom", "Custom")):
            self.kind.addItem(label, key)
        self.kind.setCurrentIndex(max(0, self.kind.findData(now.get("type", "any"))))
        self.op = QComboBox()
        for key, label in CELL_OPS:
            self.op.addItem(label.lower(), key)
        self.op.setCurrentIndex(max(0, self.op.findData(now.get("op", "between"))))
        self.a = QLineEdit(str(now.get("a", "") or ""))
        self.a.setPlaceholderText("0, 200 kN, =B1")
        self.b = QLineEdit(str(now.get("b", "") or ""))
        self.source = QLineEdit(str(now.get("source", "") or ""))
        self.source.setPlaceholderText("M16, M20, M24   or   =$D$1:$D$3")
        self.formula = QLineEdit(str(now.get("formula", "") or "="))
        self.blank = QCheckBox("Ignore blank")
        self.blank.setChecked(now.get("blank", True))
        self.dropdown = QCheckBox("In-cell dropdown")
        self.dropdown.setChecked(now.get("dropdown", True))
        self.input = QLineEdit(now.get("input", ""))
        self.input.setPlaceholderText("shown when the cell is selected")
        self.style = QComboBox()
        for key, label in (("stop", "Stop"), ("warning", "Warning"), ("information", "Information")):
            self.style.addItem(label, key)
        self.style.setCurrentIndex(max(0, self.style.findData(now.get("style", "stop"))))
        self.error = QLineEdit(now.get("error", ""))
        self.error.setPlaceholderText("shown when invalid data is entered")
        layout.addRow("Allow:", self.kind)
        layout.addRow("Data:", self.op)
        layout.addRow("Minimum / value:", self.a)
        layout.addRow("Maximum:", self.b)
        layout.addRow("Source:", self.source)
        layout.addRow("Formula:", self.formula)
        layout.addRow("", self.blank)
        layout.addRow("", self.dropdown)
        layout.addRow("Input message:", self.input)
        layout.addRow("Error style:", self.style)
        layout.addRow("Error message:", self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        clear = buttons.addButton("Clear All", QDialogButtonBox.ResetRole)
        clear.clicked.connect(self.clear_all)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def rule(self) -> dict:
        kind = self.kind.currentData()
        rule = {"type": kind, "blank": self.blank.isChecked(), "input": self.input.text(),
                "style": self.style.currentData(), "error": self.error.text()}
        if kind == "list":
            rule.update(source=self.source.text().strip(), dropdown=self.dropdown.isChecked())
        elif kind == "custom":
            rule["formula"] = self.formula.text().strip()
        elif kind != "any":
            rule.update(op=self.op.currentData(), a=self.a.text().strip(), b=self.b.text().strip())
        return rule

    def _apply(self, rule) -> None:
        tables = self.tables
        t, l, b, r = tables.selection()
        sheet = tables.item.sheet
        kept = []
        for v in copy.deepcopy(sheet.validations):
            v["ranges"] = [rg for rg in v["ranges"] if rg[2] < t or rg[0] > b or rg[3] < l or rg[1] > r]
            if v["ranges"]:
                kept.append(v)
        if rule is not None and rule["type"] != "any":
            rule["ranges"] = [[t, l, b, r]]
            kept.append(rule)
        tables._change("Data validation", lambda wb, s: wb.set_validations(s, kept))

    def clear_all(self) -> None:
        self._apply(None)
        self.reject()

    def accept(self) -> None:
        self._apply(self.rule())
        super().accept()


def validation_dialog(tables):
    dialog = ValidationDialog(tables)
    _show(tables.view.window, dialog)
    return dialog


def circle_invalid(tables) -> None:
    item = tables.item
    item.circles = validation.invalid_cells(item.sheet)
    item.update()
    n = len(item.circles)
    tables.view.statusMessage.emit(f"{n} cell{'s' if n != 1 else ''} with invalid data" if n
                                   else "No invalid data")


def clear_circles(tables) -> None:
    tables.item.circles = ()
    tables.item.update()


# -- comments ---------------------------------------------------------------------------------------
def set_comment(tables, text) -> None:
    row, col = tables.active
    tables._change("Comment", lambda wb, s: wb.set_comment(s, row, col, text or None))


class CommentDialog(QDialog):
    def __init__(self, tables):
        super().__init__(tables.view)
        self.tables = tables
        row, col = tables.active
        self.setWindowTitle(f"Comment on {col_letters(col)}{row + 1}")
        cell = tables.item.sheet.cells.get((row, col))
        layout = QVBoxLayout(self)
        self.text = QPlainTextEdit(cell.comment if cell and cell.comment else "")
        layout.addWidget(self.text)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self) -> None:
        set_comment(self.tables, self.text.toPlainText().strip())
        super().accept()


def comment_dialog(tables):
    dialog = CommentDialog(tables)
    _show(tables.view.window, dialog)
    return dialog


# -- find and replace -------------------------------------------------------------------------------
class FindDialog(QDialog):
    """Excel's Find and Replace, on the open table or on every table."""

    def __init__(self, tables, replace: bool = False):
        super().__init__(tables.view)
        self.tables = tables
        self.setWindowTitle("Find and Replace")
        self.setModal(False)
        layout = QFormLayout(self)
        self.what = QLineEdit()
        self.with_ = QLineEdit()
        layout.addRow("Find what:", self.what)
        layout.addRow("Replace with:", self.with_)
        self.within = QComboBox()
        self.within.addItems(["Table", "All tables"])
        self.look_in = QComboBox()
        self.look_in.addItem("Formulas", "formulas")
        self.look_in.addItem("Values", "values")
        self.look_in.addItem("Comments", "comments")
        self.case = QCheckBox("Match case")
        self.whole = QCheckBox("Match entire cell contents")
        layout.addRow("Within:", self.within)
        layout.addRow("Look in:", self.look_in)
        layout.addRow("", self.case)
        layout.addRow("", self.whole)
        row = QHBoxLayout()
        for text, slot in (("Replace All", self.replace_all), ("Replace", self.replace_one),
                           ("Find All", self.find_all), ("Find Next", self.find_next)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        layout.addRow(row)
        self.found = QListWidget()
        self.found.itemActivated.connect(self._go)
        self.found.itemClicked.connect(self._go)
        layout.addRow(self.found)
        self.result = QLabel("")
        layout.addRow(self.result)
        self._hits = []
        self._at = -1

    def _tables(self):
        if self.within.currentIndex() == 0 and self.tables.item is not None:
            return [self.tables.item]
        return self.tables._all_tables()

    def _search(self):
        hits = []
        for item in self._tables():
            for row, col in find.find_all(item.sheet, self.what.text(), self.look_in.currentData(),
                                          self.case.isChecked(), self.whole.isChecked()):
                hits.append((item, row, col))
        return hits

    def find_all(self):
        self._hits = self._search()
        self.found.clear()
        for item, row, col in self._hits:
            entry = QListWidgetItem(f"{item.name}  {col_letters(col)}{row + 1}   {item.sheet.input(row, col)}")
            entry.setData(Qt.UserRole, (item.uid, row, col))
            self.found.addItem(entry)
        self.result.setText(f"{len(self._hits)} cell(s) found")
        return self._hits

    def find_next(self):
        if not self._hits:
            self._hits = self._search()
            self._at = -1
        if not self._hits:
            self.result.setText("Nothing found")
            return None
        self._at = (self._at + 1) % len(self._hits)
        item, row, col = self._hits[self._at]
        self._select(item, row, col)
        return item, row, col

    def _select(self, item, row, col):
        tables = self.tables
        if tables.item is not item:
            tables.open(item, (row, col))
        tables.select((row, col))

    def _go(self, entry):
        uid, row, col = entry.data(Qt.UserRole)
        item = next((i for i in self.tables._all_tables() if i.uid == uid), None)
        if item is not None:
            self._select(item, row, col)

    def replace_one(self):
        tables = self.tables
        if tables.item is None:
            return
        row, col = tables.active
        what, rep = self.what.text(), self.with_.text()
        case, whole = self.case.isChecked(), self.whole.isChecked()
        tables._change("Replace", lambda wb, s: find.replace_in(s, row, col, what, rep, case, whole))
        self._hits = []
        self.find_next()

    def replace_all(self):
        what, rep = self.what.text(), self.with_.text()
        case, whole = self.case.isChecked(), self.whole.isChecked()
        total = 0
        view = self.tables.view
        frames = []
        for item in self._tables():
            if item.parentItem() not in frames:
                frames.append(item.parentItem())
        view.begin_snapshot(frames)
        for item in self._tables():
            total += find.replace_all(item.sheet, what, rep, case, whole)
            item.layout_changed()
        view.commit_snapshot("Replace all")
        self._hits = []
        self.result.setText(f"{total} replacement(s) made")
        return total


def find_dialog(tables, replace: bool = False):
    dialog = FindDialog(tables, replace)
    window = tables.view.window
    if not getattr(window, "interactive_prompts", True):
        window._last_data_dialog = dialog
    else:
        dialog.show()
    return dialog
