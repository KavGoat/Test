"""Inserting and editing charts (items/chart.py).

Insert ▸ Chart (or a table's right-click ▸ Insert Chart) charts the cells
picked out in the open table: the first column as x (scatter) or the
categories (line, column) when there is more than one, each other column a
series, the headings in the first row as the series' names. Double-click a
chart, or right-click ▸ Edit Chart…, for its type, titles, axes (bounds,
log scale, gridlines), legend, and each series' cells, error bars and
trendline.
"""
from __future__ import annotations

import copy
from typing import Optional

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QGroupBox, QHBoxLayout, QLineEdit, QListWidget, QPushButton,
                               QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from ..items.chart import ChartItem, new_series, new_spec
from ..sheet.refs import col_letters, quote_sheet
from ..sheet.values import Qty

TYPES = (("XY scatter", "scatter", False, True), ("Scatter with lines", "scatter", True, True),
         ("Scatter with lines only", "scatter", True, False), ("Line", "line", True, False),
         ("Line with markers", "line", True, True), ("Column", "column", False, False))
ERRORS = (("None", None), ("Fixed value", "fixed"), ("Percentage", "percent"),
          ("Standard deviation", "stddev"), ("Standard error", "stderr"), ("Custom", "custom"))
TRENDS = (("None", None), ("Linear", "linear"), ("Polynomial", "poly"), ("Exponential", "exp"),
          ("Logarithmic", "log"), ("Power", "power"), ("Moving average", "moving"))


# -- from the cells picked out -------------------------------------------------------------------
def _ref(sheet_name: str, top: int, left: int, bottom: int, right: int) -> str:
    text = f"{quote_sheet(sheet_name)}!${col_letters(left)}${top + 1}"
    if (top, left) != (bottom, right):
        text += f":${col_letters(right)}${bottom + 1}"
    return text


def spec_from_selection(sheet, block: tuple, kind: str, lines: bool = False,
                        markers: bool = True) -> dict:
    """A chart of a block of cells, read as Excel reads it."""
    t, l, b, r = block

    def value(row, col):
        cell = sheet.cells.get((row, col))
        return None if cell is None else cell.value

    def numeric(v):
        return isinstance(v, (int, float, Qty)) and not isinstance(v, bool)

    headed = b > t and any(isinstance(value(t, c), str) for c in range(l, r + 1)) and \
        any(numeric(value(t + 1, c)) for c in range(l, r + 1))
    first = t + 1 if headed else t
    spec = new_spec(kind)
    spec["lines"], spec["markers"] = lines, markers
    columns = list(range(l, r + 1))
    x_col = None
    if len(columns) > 1:
        if kind == "scatter" or not numeric(value(first, l)):
            x_col = l
            columns = columns[1:]
    if x_col is not None and headed:
        spec["x_heading"] = str(value(t, x_col) or "")
    for c in columns:
        s = new_series(_ref(sheet.name, first, x_col, b, x_col) if x_col is not None else "",
                       _ref(sheet.name, first, c, b, c),
                       ("=" + _ref(sheet.name, t, c, t, c)) if headed else "")
        spec["series"].append(s)
    return spec


def insert_chart(tables, kind: str = "scatter", lines: bool = False, markers: bool = True):
    """Chart the selection of the open table; the chart goes beside it."""
    item = tables.item
    view = tables.view
    if item is None or item.sheet is None:
        view.statusMessage.emit("Pick out cells in a table first, then Insert ▸ Chart")
        return None
    block = tables.selection()
    if block[0] == block[2] and block[1] == block[3]:
        used = item.sheet.data_area() if hasattr(item.sheet, "data_area") else None
        if used is not None:
            block = used
    spec = spec_from_selection(item.sheet, block, kind, lines, markers)
    chart = ChartItem(spec)
    window = view.window
    chart.author = window.document.settings.default_author or window.document.author
    frame, where = _place_for(item, block, chart)
    tables.close()
    view.begin_snapshot([frame])
    frame.add_markup(chart, where)
    view.commit_snapshot("Insert chart")
    view.scene().clearSelection()
    chart.setSelected(True)
    return chart


def _place_for(item, block, chart):
    """Beside the cells: on a sheet page to the right of the block, over the
    cells; on a page, right of the table if it fits, else below it."""
    t, l, b, r = block
    if getattr(item, "SHEET_RUN", False):
        frames = item.run_frames()
        k = min(item.page_index_of_row(t), len(frames) - 1)
        frame = frames[k]
        point = item.cell_rect(t, r).topRight() + QPointF(12, 0)
        return frame, frame.mapFromItem(item, point)
    frame = item.parentItem()
    box = item.mapRectToParent(item.local_rect())
    width = frame.page.width_pt
    if box.right() + 12 + chart.rect.width() <= width - 18:
        return frame, QPointF(box.right() + 12, box.top())
    return frame, QPointF(box.left(), box.bottom() + 12)


# -- the dialog ----------------------------------------------------------------------------------
def _number(text: str) -> Optional[float]:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


class ChartDialog(QDialog):
    def __init__(self, spec: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Chart")
        self.spec = copy.deepcopy(spec)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)
        tabs.addTab(self._chart_tab(), "Chart")
        tabs.addTab(self._axes_tab(), "Axes")
        tabs.addTab(self._series_tab(), "Series")
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._show_series(0)

    # chart tab
    def _chart_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.type = QComboBox()
        for label, *_rest in TYPES:
            self.type.addItem(label)
        spec = self.spec
        wanted = (spec["kind"], bool(spec.get("lines")), bool(spec.get("markers")))
        index = next((i for i, t in enumerate(TYPES) if t[1:] == wanted),
                     next(i for i, t in enumerate(TYPES) if t[1] == spec["kind"]))
        self.type.setCurrentIndex(index)
        form.addRow("Type:", self.type)
        self.title, self.show_title = self._title_row(form, "Chart title:", spec.get("title", "auto"))
        self.x_title, self.show_x_title = self._title_row(form, "Horizontal axis title:",
                                                          spec.get("x_title", "auto"))
        self.y_title, self.show_y_title = self._title_row(form, "Vertical axis title:",
                                                          spec.get("y_title", "auto"))
        self.legend = QComboBox()
        for label in ("Bottom", "Right", "Top", "None"):
            self.legend.addItem(label, label.lower())
        self.legend.setCurrentIndex(max(0, self.legend.findData(spec.get("legend", "bottom"))))
        form.addRow("Legend:", self.legend)
        return page

    @staticmethod
    def _title_row(form, label, value):
        row = QHBoxLayout()
        show = QCheckBox("Show")
        show.setChecked(value != "")
        edit = QLineEdit("" if value in ("auto", "") else value)
        edit.setPlaceholderText("automatic")
        row.addWidget(show)
        row.addWidget(edit, 1)
        form.addRow(label, row)
        return edit, show

    # axes tab
    def _axes_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.axes = {}
        for which, label in (("x_axis", "Horizontal (x) axis"), ("y_axis", "Vertical (y) axis")):
            box = QGroupBox(label)
            form = QFormLayout(box)
            axis = self.spec.get(which, {})
            fields = {}
            for key, name in (("min", "Minimum:"), ("max", "Maximum:"), ("major", "Major unit:")):
                edit = QLineEdit("" if axis.get(key) is None else f"{axis[key]:g}")
                edit.setPlaceholderText("automatic")
                form.addRow(name, edit)
                fields[key] = edit
            fields["log"] = QCheckBox("Logarithmic scale (base 10)")
            fields["log"].setChecked(bool(axis.get("log")))
            form.addRow(fields["log"])
            fields["gridlines"] = QCheckBox("Major gridlines")
            fields["gridlines"].setChecked(bool(axis.get("gridlines")))
            form.addRow(fields["gridlines"])
            self.axes[which] = fields
            layout.addWidget(box)
        return page

    # series tab
    def _series_tab(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        left = QVBoxLayout()
        self.series_list = QListWidget()
        for i, s in enumerate(self.spec["series"]):
            self.series_list.addItem(self._series_label(s, i))
        left.addWidget(self.series_list, 1)
        buttons = QHBoxLayout()
        add = QPushButton("Add")
        remove = QPushButton("Remove")
        buttons.addWidget(add)
        buttons.addWidget(remove)
        left.addLayout(buttons)
        layout.addLayout(left, 1)
        right = QVBoxLayout()
        form = QFormLayout()
        self.s_name = QLineEdit()
        self.s_x = QLineEdit()
        self.s_y = QLineEdit()
        self.s_name.setPlaceholderText("text, or =Sheet!$B$1")
        self.s_x.setPlaceholderText("e.g. Loads!$A$2:$A$9")
        self.s_y.setPlaceholderText("e.g. Loads!$B$2:$B$9")
        form.addRow("Name:", self.s_name)
        form.addRow("X values:", self.s_x)
        form.addRow("Y values:", self.s_y)
        right.addLayout(form)
        err = QGroupBox("Error bars (y)")
        ef = QFormLayout(err)
        self.e_type = QComboBox()
        for label, _key in ERRORS:
            self.e_type.addItem(label)
        self.e_value = QLineEdit()
        self.e_plus = QLineEdit()
        self.e_minus = QLineEdit()
        self.e_dir = QComboBox()
        for label in ("Both", "Plus", "Minus"):
            self.e_dir.addItem(label, label.lower())
        ef.addRow("Type:", self.e_type)
        ef.addRow("Amount:", self.e_value)
        ef.addRow("Plus (custom):", self.e_plus)
        ef.addRow("Minus (custom):", self.e_minus)
        ef.addRow("Direction:", self.e_dir)
        right.addWidget(err)
        xerr = QGroupBox("Error bars (x, scatter)")
        xf = QFormLayout(xerr)
        self.x_type = QComboBox()
        for label, _key in ERRORS[:3]:
            self.x_type.addItem(label)
        self.x_value = QLineEdit()
        xf.addRow("Type:", self.x_type)
        xf.addRow("Amount:", self.x_value)
        right.addWidget(xerr)
        trend = QGroupBox("Trendline")
        tf = QFormLayout(trend)
        self.t_type = QComboBox()
        for label, _key in TRENDS:
            self.t_type.addItem(label)
        self.t_order = QSpinBox()
        self.t_order.setRange(2, 6)
        self.t_period = QSpinBox()
        self.t_period.setRange(2, 255)
        self.t_intercept = QLineEdit()
        self.t_intercept.setPlaceholderText("free")
        self.t_eq = QCheckBox("Display equation on chart")
        self.t_r2 = QCheckBox("Display R-squared value on chart")
        tf.addRow("Type:", self.t_type)
        tf.addRow("Order (polynomial):", self.t_order)
        tf.addRow("Period (moving average):", self.t_period)
        tf.addRow("Set intercept (linear):", self.t_intercept)
        tf.addRow(self.t_eq)
        tf.addRow(self.t_r2)
        right.addWidget(trend)
        right.addStretch(1)
        layout.addLayout(right, 2)
        self._current = None
        self.series_list.currentRowChanged.connect(self._show_series)
        add.clicked.connect(self.add_series)
        remove.clicked.connect(self.remove_series)
        return page

    @staticmethod
    def _series_label(s, i) -> str:
        name = s.get("name") or f"Series{i + 1}"
        return name.lstrip("=")

    def _show_series(self, row: int) -> None:
        self._keep_series()
        series = self.spec["series"]
        if not 0 <= row < len(series):
            self._current = None
            return
        if self.series_list.currentRow() != row:
            self.series_list.blockSignals(True)
            self.series_list.setCurrentRow(row)
            self.series_list.blockSignals(False)
        self._current = row
        s = series[row]
        self.s_name.setText(s.get("name") or "")
        self.s_x.setText(s.get("x") or "")
        self.s_y.setText(s.get("y") or "")
        e = s.get("error") or {}
        self.e_type.setCurrentIndex([k for _l, k in ERRORS].index(e.get("type")))
        self.e_value.setText("" if e.get("value") is None else f"{e['value']:g}")
        self.e_plus.setText(e.get("plus") or "")
        self.e_minus.setText(e.get("minus") or "")
        self.e_dir.setCurrentIndex(max(0, self.e_dir.findData(e.get("direction", "both"))))
        xe = s.get("x_error") or {}
        self.x_type.setCurrentIndex([k for _l, k in ERRORS[:3]].index(xe.get("type")))
        self.x_value.setText("" if xe.get("value") is None else f"{xe['value']:g}")
        t = s.get("trend") or {}
        self.t_type.setCurrentIndex([k for _l, k in TRENDS].index(t.get("type")))
        self.t_order.setValue(int(t.get("order", 2)))
        self.t_period.setValue(int(t.get("period", 2)))
        self.t_intercept.setText("" if t.get("intercept") is None else f"{t['intercept']:g}")
        self.t_eq.setChecked(bool(t.get("equation")))
        self.t_r2.setChecked(bool(t.get("r2")))

    def _keep_series(self) -> None:
        row = self._current
        series = self.spec["series"]
        if row is None or not 0 <= row < len(series):
            return
        s = series[row]
        s["name"] = self.s_name.text().strip()
        s["x"] = self.s_x.text().strip().lstrip("=")
        s["y"] = self.s_y.text().strip().lstrip("=")
        kind = ERRORS[self.e_type.currentIndex()][1]
        s["error"] = None if kind is None else {
            "type": kind, "value": _number(self.e_value.text()) or (1.0 if kind == "stddev" else
                                                                      5.0 if kind == "percent" else 0.0),
            "plus": self.e_plus.text().strip().lstrip("="), "minus": self.e_minus.text().strip().lstrip("="),
            "direction": self.e_dir.currentData()}
        xkind = ERRORS[self.x_type.currentIndex()][1]
        s["x_error"] = None if xkind is None else {"type": xkind, "value": _number(self.x_value.text()) or 0.0,
                                                   "direction": "both"}
        tkind = TRENDS[self.t_type.currentIndex()][1]
        s["trend"] = None if tkind is None else {
            "type": tkind, "order": self.t_order.value(), "period": self.t_period.value(),
            "intercept": _number(self.t_intercept.text()), "equation": self.t_eq.isChecked(),
            "r2": self.t_r2.isChecked()}
        item = self.series_list.item(row)
        if item is not None:
            item.setText(self._series_label(s, row))

    def add_series(self) -> None:
        self._keep_series()
        self.spec["series"].append(new_series())
        self.series_list.addItem(f"Series{len(self.spec['series'])}")
        self._current = None
        self._show_series(len(self.spec["series"]) - 1)

    def remove_series(self) -> None:
        row = self.series_list.currentRow()
        if not 0 <= row < len(self.spec["series"]):
            return
        self._current = None
        del self.spec["series"][row]
        self.series_list.takeItem(row)
        self._show_series(min(row, len(self.spec["series"]) - 1))

    def result(self) -> dict:
        """The chart as the dialog now says."""
        self._keep_series()
        spec = self.spec
        _label, kind, lines, markers = TYPES[self.type.currentIndex()]
        spec["kind"], spec["lines"], spec["markers"] = kind, lines, markers
        for key, edit, show in (("title", self.title, self.show_title),
                                ("x_title", self.x_title, self.show_x_title),
                                ("y_title", self.y_title, self.show_y_title)):
            spec[key] = "" if not show.isChecked() else (edit.text().strip() or "auto")
        spec["legend"] = self.legend.currentData()
        for which, fields in self.axes.items():
            axis = spec.setdefault(which, {})
            for key in ("min", "max", "major"):
                axis[key] = _number(fields[key].text())
            axis["log"] = fields["log"].isChecked()
            axis["gridlines"] = fields["gridlines"].isChecked()
        return copy.deepcopy(spec)


def edit_chart(window, chart: ChartItem) -> None:
    dialog = ChartDialog(chart.spec, window)
    if not getattr(window, "interactive_prompts", True):
        window._last_chart_dialog = dialog
        return
    if dialog.exec() == QDialog.Accepted:
        apply_dialog(window, chart, dialog)


def apply_dialog(window, chart: ChartItem, dialog: ChartDialog) -> None:
    view = window.view
    frame = chart.parentItem()
    view.begin_snapshot([frame])
    chart.set_spec(dialog.result())
    view.commit_snapshot("Edit chart")
