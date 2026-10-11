"""Excel's Conditional Formatting Rules Manager and its New / Edit
Formatting Rule dialog, for an open table or spreadsheet page.

The manager lists the rules in the order they apply, each with a preview of
its look (the colours of its fill and text, its data bar, colour scale or
icons), the cells it applies to and Stop If True; rules can be shown for the
selected cells or the whole sheet, added, edited, duplicated, deleted and
moved up or down. The rule picked in the list has its cells outlined on the
sheet, and its Applies to can be chosen by dragging over the cells (the
button beside it), as in Excel. Nothing changes until OK or Apply, one undo
step each.
"""
from __future__ import annotations

import copy
from typing import Optional

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton,
                               QSpinBox, QStackedWidget, QStyledItemDelegate, QTableWidget,
                               QTableWidgetItem, QToolButton, QVBoxLayout, QWidget)

from ..sheet import condfmt
from ..sheet.refs import area_text, parse_range
from .datatools import CELL_OPS, _FormatPicker, _show

SAMPLE = "AaBbCcYyZz"


# -- what a rule looks like ------------------------------------------------------------------
def paint_preview(painter: QPainter, rect: QRectF, rule: dict) -> None:
    """A rule's look in a small box: Excel's Format column."""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    kind = rule.get("type")
    box = rect.adjusted(2, 3, -2, -3)
    painter.setPen(QPen(QColor("#a6a6a6"), 0))
    painter.setBrush(QColor("white"))
    painter.drawRect(box)
    if kind == "databar":
        colour = QColor(rule.get("color", "#638ec6"))
        bar = QRectF(box.left() + 1, box.top() + 2, box.width() * 0.7, box.height() - 4)
        grad = QLinearGradient(bar.topLeft(), bar.topRight())
        end = QColor(colour)
        end.setAlpha(60)
        grad.setColorAt(0, colour)
        grad.setColorAt(1, end)
        painter.fillRect(bar, grad)
    elif kind == "scale":
        colours = rule.get("colors") or ["#f8696b", "#ffeb84", "#63be7b"]
        grad = QLinearGradient(box.topLeft(), box.topRight())
        for i, c in enumerate(colours):
            grad.setColorAt(i / max(1, len(colours) - 1), QColor(c))
        painter.fillRect(box.adjusted(1, 1, 0, 0), grad)
    elif kind == "icons":
        icons = condfmt.ICON_SETS.get(rule.get("set", "arrows"), condfmt.ICON_SETS["arrows"])
        if rule.get("reverse"):
            icons = list(reversed(icons))
        step = box.width() / 3
        font = painter.font()
        font.setPixelSize(int(max(8, box.height() - 4)))
        painter.setFont(font)
        for i, (glyph, colour) in enumerate(reversed(icons)):
            painter.setPen(QColor(colour))
            painter.drawText(QRectF(box.left() + i * step, box.top(), step, box.height()),
                             Qt.AlignCenter, glyph)
    else:
        fmt = rule.get("format") or {}
        if fmt.get("fill"):
            painter.fillRect(box.adjusted(1, 1, 0, 0), QColor(fmt["fill"]))
        font = QFont(painter.font())
        font.setBold(bool(fmt.get("bold")))
        font.setItalic(bool(fmt.get("italic")))
        font.setUnderline(bool(fmt.get("underline")))
        font.setStrikeOut(bool(fmt.get("strike")))
        painter.setFont(font)
        painter.setPen(QColor(fmt.get("color") or "#000000"))
        painter.drawText(box, Qt.AlignCenter, SAMPLE if fmt else "No Format Set")
    painter.restore()


class _PreviewDelegate(QStyledItemDelegate):
    def __init__(self, rules_of):
        super().__init__()
        self.rules_of = rules_of

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        rules = self.rules_of()
        if 0 <= index.row() < len(rules):
            paint_preview(painter, QRectF(option.rect), rules[index.row()])

    def sizeHint(self, option, index):
        return QSize(130, 24)


class Preview(QWidget):
    """The preview in the rule dialog."""

    def __init__(self, rule_of):
        super().__init__()
        self.rule_of = rule_of
        self.setMinimumSize(160, 26)

    def paintEvent(self, _event):
        painter = QPainter(self)
        paint_preview(painter, QRectF(self.rect()), self.rule_of())
        painter.end()


# -- New / Edit Formatting Rule ----------------------------------------------------------------
TYPES = [
    ("values", "Format all cells based on their values"),
    ("contains", "Format only cells that contain"),
    ("rank", "Format only top or bottom ranked values"),
    ("average", "Format only values that are above or below average"),
    ("unique", "Format only unique or duplicate values"),
    ("formula", "Use a formula to determine which cells to format"),
]
CONTAINS = [("cell", "Cell Value"), ("text", "Specific Text"), ("date", "Dates Occurring"),
            ("blanks", "Blanks"), ("noBlanks", "No Blanks"), ("errors", "Errors"),
            ("noErrors", "No Errors")]
TEXT_HOW = [("contains", "containing"), ("notContains", "not containing"),
            ("begins", "beginning with"), ("ends", "ending with")]
DATES = [("yesterday", "Yesterday"), ("today", "Today"), ("tomorrow", "Tomorrow"),
         ("last7", "In the last 7 days"), ("lastMonth", "Last month"),
         ("thisMonth", "This month"), ("nextMonth", "Next month")]
STYLES = [("scale2", "2-Color Scale"), ("scale3", "3-Color Scale"), ("databar", "Data Bar"),
          ("icons", "Icon Sets")]
ICON_NAMES = [("arrows", "3 Arrows"), ("traffic", "3 Traffic Lights"), ("flags", "3 Flags"),
              ("symbols", "3 Symbols")]


def _type_of(rule: dict) -> str:
    kind = rule.get("type")
    if kind in ("databar", "scale", "icons"):
        return "values"
    if kind in ("top", "bottom"):
        return "rank"
    if kind in ("above", "below"):
        return "average"
    if kind in ("duplicate", "unique"):
        return "unique"
    if kind == "formula":
        return "formula"
    return "contains"


class _ColourButton(QPushButton):
    def __init__(self, colour: str, changed):
        super().__init__()
        self.colour = colour
        self.changed = changed
        self.setFixedWidth(70)
        self.clicked.connect(self._pick)
        self._show()

    def _show(self):
        self.setStyleSheet(f"background:{self.colour}; border:1px solid #888;")

    def _pick(self):
        from PySide6.QtWidgets import QColorDialog
        got = QColorDialog.getColor(QColor(self.colour), self)
        if got.isValid():
            self.colour = got.name()
            self._show()
            self.changed()


class RuleDialog(QDialog):
    """Excel's New Formatting Rule / Edit Formatting Rule."""

    def __init__(self, parent, rule: Optional[dict] = None):
        super().__init__(parent)
        self.original = copy.deepcopy(rule) if rule else None
        start = rule or {"type": "cell", "op": "greater", "a": "", "format": {"fill": "#ffc7ce",
                                                                             "color": "#9c0006"}}
        self.setWindowTitle("Edit Formatting Rule" if rule else "New Formatting Rule")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select a Rule Type:"))
        self.types = QListWidget()
        for _key, label in TYPES:
            self.types.addItem("► " + label)
        self.types.setFixedHeight(self.types.sizeHintForRow(0) * len(TYPES) + 6)
        layout.addWidget(self.types)
        layout.addWidget(QLabel("Edit the Rule Description:"))
        self.pages = QStackedWidget()
        layout.addWidget(self.pages)
        fmt = start.get("format") or {}
        self._build_values(start)
        self._build_contains(start)
        self._build_rank(start)
        self._build_average(start)
        self._build_unique(start)
        self._build_formula(start)
        # the look, for every type but "based on their values"
        self.look_row = QWidget()
        look = QHBoxLayout(self.look_row)
        look.setContentsMargins(0, 0, 0, 0)
        look.addWidget(QLabel("Preview:"))
        self.preview = Preview(self.rule)
        look.addWidget(self.preview, 1)
        self.picker = _FormatPicker(fmt)
        for box in (self.picker.bold, self.picker.italic, self.picker.underline, self.picker.strike):
            box.toggled.connect(self._changed)
        self.picker.number.textChanged.connect(self._changed)
        layout.addWidget(self.look_row)
        layout.addWidget(self.picker)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.types.currentRowChanged.connect(self._type_changed)
        keys = [k for k, _l in TYPES]
        self.types.setCurrentRow(keys.index(_type_of(start)))
        # _FormatPicker's colour buttons change their look only: redraw after them
        self.picker.fill_button.clicked.connect(self._changed)
        self.picker.color_button.clicked.connect(self._changed)

    # -- the pages ----------------------------------------------------------------------
    def _page(self) -> QFormLayout:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(4, 4, 4, 4)
        self.pages.addWidget(page)
        return form

    def _build_values(self, rule):
        form = self._page()
        self._values_form = form
        self.style = QComboBox()
        for key, label in STYLES:
            self.style.addItem(label, key)
        kind = rule.get("type")
        colours = list(rule.get("colors") or ["#f8696b", "#ffeb84", "#63be7b"])
        if kind == "scale":
            self.style.setCurrentIndex(0 if len(colours) == 2 else 1)
        elif kind == "databar":
            self.style.setCurrentIndex(2)
        elif kind == "icons":
            self.style.setCurrentIndex(3)
        else:
            self.style.setCurrentIndex(1)
        form.addRow("Format Style:", self.style)
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        if len(colours) == 2:
            colours = [colours[0], "#ffeb84", colours[1]]
        self.scale_min = _ColourButton(colours[0], self._changed)
        self.scale_mid = _ColourButton(colours[1], self._changed)
        self.scale_max = _ColourButton(colours[-1], self._changed)
        for label, button in (("Minimum", self.scale_min), ("Midpoint", self.scale_mid),
                              ("Maximum", self.scale_max)):
            h.addWidget(QLabel(label))
            h.addWidget(button)
        form.addRow("Colors:", row)
        self._scale_row = row
        self.bar_colour = _ColourButton(rule.get("color", "#638ec6"), self._changed)
        form.addRow("Bar Color:", self.bar_colour)
        self.icon_set = QComboBox()
        for key, label in ICON_NAMES:
            self.icon_set.addItem(label, key)
        self.icon_set.setCurrentIndex(max(0, [k for k, _l in ICON_NAMES].index(rule.get("set", "arrows"))
                                          if rule.get("set", "arrows") in dict(ICON_NAMES) else 0))
        self.icon_reverse = QCheckBox("Reverse Icon Order")
        self.icon_reverse.setChecked(bool(rule.get("reverse")))
        form.addRow("Icon Style:", self.icon_set)
        form.addRow("", self.icon_reverse)
        self.values_preview = Preview(self.rule)
        form.addRow("Preview:", self.values_preview)
        for w in (self.style, self.icon_set):
            w.currentIndexChanged.connect(self._changed)
        self.icon_reverse.toggled.connect(self._changed)

    def _build_contains(self, rule):
        form = self._page()
        self.what = QComboBox()
        for key, label in CONTAINS:
            self.what.addItem(label, key)
        kind = rule.get("type")
        keys = [k for k, _l in CONTAINS]
        self.what.setCurrentIndex(keys.index(kind) if kind in keys else 0)
        form.addRow("Format only cells with:", self.what)
        self.op = QComboBox()
        for key, label in CELL_OPS:
            self.op.addItem(label.lower(), key)
        ops = [k for k, _l in CELL_OPS]
        self.op.setCurrentIndex(ops.index(rule.get("op", "greater")) if rule.get("op") in ops else 0)
        self.a = QLineEdit(str(rule.get("a", "")) if kind == "cell" else "")
        self.a.setPlaceholderText("a value (5, 200 kN), or =B1")
        self.b = QLineEdit(str(rule.get("b", "")) if kind == "cell" else "")
        self.b.setPlaceholderText("and")
        form.addRow(self.op, self.a)
        form.addRow("and", self.b)
        self.how = QComboBox()
        for key, label in TEXT_HOW:
            self.how.addItem(label, key)
        hows = [k for k, _l in TEXT_HOW]
        self.how.setCurrentIndex(hows.index(rule.get("how", "contains")) if rule.get("how") in hows else 0)
        self.text = QLineEdit(str(rule.get("text", "")))
        form.addRow(self.how, self.text)
        self.when = QComboBox()
        for key, label in DATES:
            self.when.addItem(label, key)
        whens = [k for k, _l in DATES]
        self.when.setCurrentIndex(whens.index(rule.get("when", "today")) if rule.get("when") in whens else 1)
        form.addRow("Dates:", self.when)
        self.what.currentIndexChanged.connect(self._contains_fields)
        self.op.currentIndexChanged.connect(self._contains_fields)
        self._contains_form = form
        self._contains_fields()

    def _contains_fields(self, *_):
        what = self.what.currentData()
        form = self._contains_form
        between = self.op.currentData() in ("between", "notBetween")
        for widget, shown in ((self.op, what == "cell"), (self.a, what == "cell"),
                              (self.b, what == "cell" and between), (self.how, what == "text"),
                              (self.text, what == "text"), (self.when, what == "date")):
            widget.setVisible(shown)
            label = form.labelForField(widget)
            if label is not None:
                label.setVisible(shown)
        self._changed()

    def _build_rank(self, rule):
        form = self._page()
        self.rank = QComboBox()
        self.rank.addItem("Top", "top")
        self.rank.addItem("Bottom", "bottom")
        self.rank.setCurrentIndex(1 if rule.get("type") == "bottom" else 0)
        self.rank_n = QSpinBox()
        self.rank_n.setRange(1, 1000)
        self.rank_n.setValue(int(rule.get("n", 10)))
        self.rank_percent = QCheckBox("% of the selected range")
        self.rank_percent.setChecked(bool(rule.get("percent")))
        form.addRow("Format values that rank in the:", self.rank)
        form.addRow("", self.rank_n)
        form.addRow("", self.rank_percent)

    def _build_average(self, rule):
        form = self._page()
        self.average = QComboBox()
        self.average.addItem("above", "above")
        self.average.addItem("below", "below")
        self.average.setCurrentIndex(1 if rule.get("type") == "below" else 0)
        self.average_equal = QCheckBox("or equal to")
        self.average_equal.setChecked(bool(rule.get("equal")))
        form.addRow("Format values that are:", self.average)
        form.addRow("", self.average_equal)
        form.addRow("", QLabel("the average for the selected range"))

    def _build_unique(self, rule):
        form = self._page()
        self.unique = QComboBox()
        self.unique.addItem("duplicate", "duplicate")
        self.unique.addItem("unique", "unique")
        self.unique.setCurrentIndex(1 if rule.get("type") == "unique" else 0)
        form.addRow("Format all:", self.unique)
        form.addRow("", QLabel("values in the selected range"))

    def _build_formula(self, rule):
        form = self._page()
        self.formula = QLineEdit(str(rule.get("formula", "=")) if rule.get("type") == "formula" else "=")
        self.formula.setToolTip("Written for the range's top-left cell; relative references move "
                                "across the range, as in Excel")
        form.addRow("Format values where this formula is true:", self.formula)

    # -- reading it back -------------------------------------------------------------------
    def _type_changed(self, index):
        self.pages.setCurrentIndex(max(0, index))
        values = TYPES[max(0, index)][0] == "values"
        self.look_row.setVisible(not values)
        self.picker.setVisible(not values)
        self._changed()

    def _changed(self, *_):
        for preview in (getattr(self, "preview", None), getattr(self, "values_preview", None)):
            if preview is not None:
                preview.update()
        if hasattr(self, "style"):
            style = self.style.currentData()
            self.scale_mid.setVisible(style == "scale3")
            for w in (self.scale_min, self.scale_max):
                w.setVisible(style in ("scale2", "scale3"))
            form = self._values_form
            for widget, shown in ((self._scale_row, style in ("scale2", "scale3")),
                                  (self.bar_colour, style == "databar"),
                                  (self.icon_set, style == "icons"),
                                  (self.icon_reverse, style == "icons")):
                widget.setVisible(shown)
                label = form.labelForField(widget)
                if label is not None:
                    label.setVisible(shown)

    def rule(self) -> dict:
        """The rule as set: its kind and fields, keeping the ranges and Stop If
        True of the rule being edited."""
        kind = TYPES[max(0, self.types.currentRow())][0]
        out: dict = {}
        if kind == "values":
            style = self.style.currentData()
            if style == "scale2":
                out = {"type": "scale", "colors": [self.scale_min.colour, self.scale_max.colour]}
            elif style == "scale3":
                out = {"type": "scale", "colors": [self.scale_min.colour, self.scale_mid.colour,
                                                   self.scale_max.colour]}
            elif style == "databar":
                out = {"type": "databar", "color": self.bar_colour.colour}
            else:
                out = {"type": "icons", "set": self.icon_set.currentData()}
                if self.icon_reverse.isChecked():
                    out["reverse"] = True
        else:
            if kind == "contains":
                what = self.what.currentData()
                out = {"type": what}
                if what == "cell":
                    out.update(op=self.op.currentData(), a=self.a.text().strip())
                    if self.op.currentData() in ("between", "notBetween"):
                        out["b"] = self.b.text().strip()
                elif what == "text":
                    out.update(how=self.how.currentData(), text=self.text.text())
                elif what == "date":
                    out["when"] = self.when.currentData()
            elif kind == "rank":
                out = {"type": self.rank.currentData(), "n": self.rank_n.value()}
                if self.rank_percent.isChecked():
                    out["percent"] = True
            elif kind == "average":
                out = {"type": self.average.currentData()}
                if self.average_equal.isChecked():
                    out["equal"] = True
            elif kind == "unique":
                out = {"type": self.unique.currentData()}
            else:
                text = self.formula.text().strip()
                out = {"type": "formula", "formula": text if text.startswith("=") else "=" + text}
            out["format"] = self.picker.format() if hasattr(self, "picker") else {}
        if self.original is not None:
            for key in ("ranges", "stop"):
                if key in self.original:
                    out[key] = copy.deepcopy(self.original[key])
        return out


# -- the Rules Manager --------------------------------------------------------------------------
def _ranges_text(ranges) -> str:
    return "=" + ",".join(area_text(*rg) for rg in ranges)


def parse_ranges(text: str) -> list:
    out = []
    for part in text.lstrip("=").split(","):
        ref = parse_range(part.strip().replace("$", ""))
        if ref is None:
            continue
        if hasattr(ref, "first"):
            a, b = ref.first, ref.last
            out.append([min(a.row, b.row), min(a.col, b.col), max(a.row, b.row), max(a.col, b.col)])
        else:
            out.append([ref.row, ref.col, ref.row, ref.col])
    return out


def _overlaps(ranges, block) -> bool:
    t, l, b, r = block
    return any(not (rg[2] < t or rg[0] > b or rg[3] < l or rg[1] > r) for rg in ranges)


class RulesManager(QDialog):
    """Excel's Conditional Formatting Rules Manager."""

    COLUMNS = ["Rule (applied in order shown)", "Format", "Applies to", "Stop If True"]

    def __init__(self, tables):
        super().__init__(tables.view)
        self.tables = tables
        self.item = tables.item
        self.setWindowTitle("Conditional Formatting Rules Manager")
        self.rules = copy.deepcopy(self.item.sheet.cond_rules)
        self.picking: Optional[int] = None
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("Show formatting rules for:"))
        self.scope = QComboBox()
        self.scope.addItem("Current Selection", "selection")
        self.scope.addItem("This Sheet" if getattr(self.item, "SHEET_RUN", False) else "This Table",
                           "sheet")
        self.scope.setCurrentIndex(1)
        self.scope.currentIndexChanged.connect(lambda _i: self._fill())
        top.addWidget(self.scope)
        top.addStretch(1)
        layout.addLayout(top)
        bar = QHBoxLayout()
        self.buttons = {}
        for key, text in (("new", "New Rule…"), ("edit", "Edit Rule…"), ("delete", "Delete Rule"),
                          ("duplicate", "Duplicate Rule")):
            b = QPushButton(text)
            b.clicked.connect(getattr(self, key))
            bar.addWidget(b)
            self.buttons[key] = b
        for key, text, step in (("up", "▲", -1), ("down", "▼", 1)):
            b = QToolButton()
            b.setText(text)
            b.setToolTip("Move Up" if step < 0 else "Move Down")
            b.clicked.connect(lambda _=False, s=step: self.move(s))
            bar.addWidget(b)
            self.buttons[key] = b
        bar.addStretch(1)
        layout.addLayout(bar)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setItemDelegateForColumn(1, _PreviewDelegate(self._shown_rules))
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(0, 220)
        self.table.setColumnWidth(1, 140)
        self.table.setColumnWidth(2, 200)
        self.table.setColumnWidth(3, 90)
        self.table.itemSelectionChanged.connect(self._picked)
        self.table.cellDoubleClicked.connect(lambda _r, _c: self.edit())
        layout.addWidget(self.table)
        ok = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        ok.accepted.connect(self.accept)
        ok.rejected.connect(self.reject)
        ok.button(QDialogButtonBox.Apply).clicked.connect(self.apply)
        layout.addWidget(ok)
        self.resize(720, 380)
        self._fill()

    # -- the list ------------------------------------------------------------------------------
    def _shown(self) -> list:
        """Indexes into self.rules of the rules listed."""
        if self.scope.currentData() == "selection":
            block = self.tables.selection()
            return [i for i, rule in enumerate(self.rules) if _overlaps(rule.get("ranges", []), block)]
        return list(range(len(self.rules)))

    def _shown_rules(self) -> list:
        return [self.rules[i] for i in self._shown()]

    def _fill(self, keep: Optional[int] = None) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for row, index in enumerate(self._shown()):
            rule = self.rules[index]
            self.table.insertRow(row)
            name = QTableWidgetItem(condfmt.describe(rule))
            name.setData(Qt.UserRole, index)
            self.table.setItem(row, 0, name)
            self.table.setItem(row, 1, QTableWidgetItem(""))
            cell = QWidget()
            h = QHBoxLayout(cell)
            h.setContentsMargins(0, 0, 0, 0)
            edit = QLineEdit(_ranges_text(rule.get("ranges", [])))
            edit.editingFinished.connect(lambda e=edit, i=index: self._ranges_typed(i, e.text()))
            h.addWidget(edit, 1)
            pick = QToolButton()
            pick.setText("⬚")
            pick.setToolTip("Choose the cells on the sheet")
            pick.clicked.connect(lambda _=False, i=index: self.pick_cells(i))
            h.addWidget(pick)
            self.table.setCellWidget(row, 2, cell)
            stop = QCheckBox()
            stop.setChecked(bool(rule.get("stop")))
            stop.toggled.connect(lambda on, i=index: self.rules[i].__setitem__("stop", on))
            holder = QWidget()
            hh = QHBoxLayout(holder)
            hh.setContentsMargins(0, 0, 0, 0)
            hh.setAlignment(Qt.AlignCenter)
            hh.addWidget(stop)
            self.table.setCellWidget(row, 3, holder)
            self.table.setRowHeight(row, 26)
        self.table.blockSignals(False)
        rows = self._shown()
        if rows:
            row = rows.index(keep) if keep in rows else 0
            self.table.selectRow(row)
        self._picked()

    def ranges_edit(self, row: int) -> QLineEdit:
        return self.table.cellWidget(row, 2).findChild(QLineEdit)

    def stop_box(self, row: int) -> QCheckBox:
        return self.table.cellWidget(row, 3).findChild(QCheckBox)

    def current(self) -> Optional[int]:
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return item.data(Qt.UserRole) if item is not None else None

    def _picked(self) -> None:
        index = self.current()
        has = index is not None
        for key in ("edit", "delete", "duplicate", "up", "down"):
            self.buttons[key].setEnabled(has)
        # its cells outlined on the sheet
        self.tables.highlight_ranges = copy.deepcopy(self.rules[index]["ranges"]) if has else None
        if self.item is not None:
            self.item.update()

    def _ranges_typed(self, index: int, text: str) -> None:
        ranges = parse_ranges(text)
        if ranges:
            self.rules[index]["ranges"] = ranges
            self._picked()

    # -- the buttons -------------------------------------------------------------------------------
    def new(self) -> None:
        dialog = RuleDialog(self)
        if not self._ask(dialog):
            return
        rule = dialog.rule()
        rule["ranges"] = [list(self.tables.selection())]
        self.rules.insert(0, rule)
        self._fill(keep=0)

    def edit(self) -> None:
        index = self.current()
        if index is None:
            return
        dialog = RuleDialog(self, self.rules[index])
        if not self._ask(dialog):
            return
        self.rules[index] = dialog.rule()
        self._fill(keep=index)

    def delete(self) -> None:
        index = self.current()
        if index is not None:
            del self.rules[index]
            self._fill(keep=min(index, len(self.rules) - 1))

    def duplicate(self) -> None:
        index = self.current()
        if index is not None:
            self.rules.insert(index + 1, copy.deepcopy(self.rules[index]))
            self._fill(keep=index + 1)

    def move(self, step: int) -> None:
        index = self.current()
        if index is None:
            return
        target = index + step
        if 0 <= target < len(self.rules):
            self.rules[index], self.rules[target] = self.rules[target], self.rules[index]
            self._fill(keep=target)

    def _ask(self, dialog) -> bool:
        """A rule dialog: shown, or (prompts off, as in tests) left to be filled in."""
        window = self.tables.view.window
        if not getattr(window, "interactive_prompts", True):
            hook = getattr(window, "answer_rule_dialog", None)
            return bool(hook(dialog)) if hook is not None else False
        return dialog.exec() == QDialog.Accepted

    # -- Applies to, by dragging over the cells ---------------------------------------------------
    def pick_cells(self, index: int) -> None:
        """Excel's collapse button: the dialog steps aside, the cells are
        chosen on the sheet, and a small bar brings it back."""
        self.picking = index
        self.hide()
        self._bar = _PickBar(self)
        self._bar.show()

    def picked(self, ok: bool) -> None:
        index, self.picking = self.picking, None
        if ok and index is not None:
            self.rules[index]["ranges"] = [list(self.tables.selection())]
        self._bar = None
        self._fill(keep=index)
        self.show()

    # -- OK / Apply ------------------------------------------------------------------------------------
    def apply(self) -> None:
        rules = copy.deepcopy(self.rules)
        self.tables._change("Conditional formatting", lambda wb, s: wb.set_cond_rules(s, rules))

    def accept(self) -> None:
        self.apply()
        self._done()
        super().accept()

    def reject(self) -> None:
        self._done()
        super().reject()

    def _done(self) -> None:
        self.tables.highlight_ranges = None
        if self.item is not None:
            self.item.update()


class _PickBar(QWidget):
    """Applies to: the cells being chosen, and a button back to the manager."""

    def __init__(self, manager: RulesManager):
        super().__init__(manager.tables.view, Qt.Tool | Qt.WindowStaysOnTopHint)
        self.manager = manager
        self.setWindowTitle("Applies to")
        h = QHBoxLayout(self)
        self.text = QLabel("Select the cells, then press OK")
        h.addWidget(self.text, 1)
        ok = QPushButton("OK")
        ok.clicked.connect(lambda: self._close(True))
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(lambda: self._close(False))
        h.addWidget(ok)
        h.addWidget(cancel)
        from PySide6.QtCore import QTimer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._follow)
        self._timer.start(150)

    def _follow(self) -> None:
        tables = self.manager.tables
        if tables.item is not None:
            self.text.setText(_ranges_text([list(tables.selection())]))

    def _close(self, ok: bool) -> None:
        self._timer.stop()
        self.close()
        self.manager.picked(ok)


def rules_manager(tables):
    dialog = RulesManager(tables)
    _show(tables.view.window, dialog)
    return dialog


def new_rule(tables):
    """Conditional Formatting ▸ New Rule…: for the selected cells."""
    dialog = RuleDialog(tables.view)
    window = tables.view.window
    if not getattr(window, "interactive_prompts", True):
        window._last_data_dialog = dialog
        return dialog
    if dialog.exec() == QDialog.Accepted:
        from .datatools import add_rule
        add_rule(tables, dialog.rule())
    return dialog
