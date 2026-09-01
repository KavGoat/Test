"""Dock panels: pages, markups list, variables, functions and properties."""
from __future__ import annotations

import csv

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox,
                               QFontComboBox, QFormLayout, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPlainTextEdit, QPushButton,
                               QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem,
                               QToolButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from ..core.units import format_quantity
from ..items.base import ARROW_HEADS, LINE_STYLES, MarkupItem
from ..items.mathitem import MathItem
from ..items.measure import CountItem, MeasureItem
from ..items.shapes import PolyItem, RectItem
from ..items.tableitem import TableItem
from ..items.text import STAMP_PRESETS, CalloutItem, NoteItem, StampItem, TextItem
from .icons import icon
from .widgets import ColorButton, LabeledSlider, UnitCombo


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

class PagesPanel(QWidget):
    """Thumbnail strip with reordering and page commands."""

    pageSelected = Signal(int)
    pagesReordered = Signal(int, int)

    def __init__(self, window):
        super().__init__()
        self.window = window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        buttons = QHBoxLayout()
        for label, tip, slot in (("+", "Add a page", self.window.add_page),
                                 ("⧉", "Duplicate this page", self.window.duplicate_page),
                                 ("−", "Delete this page", self.window.delete_page)):
            button = QToolButton()
            button.setText(label)
            button.setToolTip(tip)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.list = QListWidget()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setIconSize(QSize(96, 128))
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMovement(QListWidget.Static)
        self.list.setSpacing(6)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.currentRowChanged.connect(self._row_changed)
        self.list.model().rowsMoved.connect(self._rows_moved)
        layout.addWidget(self.list, 1)
        self._suppress = False

    def _row_changed(self, row: int) -> None:
        if not self._suppress and row >= 0:
            self.pageSelected.emit(row)

    def _rows_moved(self, _parent, start, _end, _dest, row) -> None:
        if self._suppress:
            return
        target = row - 1 if row > start else row
        self.pagesReordered.emit(start, target)

    def rebuild(self, document, current: int) -> None:
        self._suppress = True
        self.list.clear()
        for index, page in enumerate(document.pages):
            entry = QListWidgetItem(self._thumbnail(page), f"{index + 1}")
            entry.setTextAlignment(Qt.AlignHCenter)
            tip = page.label or page.source_note or f"Page {index + 1}"
            entry.setToolTip(f"{tip}\n{page.setup.size_name} {page.setup.orientation}")
            self.list.addItem(entry)
        self.list.setCurrentRow(current)
        self._suppress = False

    def refresh_current(self, document, current: int) -> None:
        entry = self.list.item(current)
        if entry is not None and 0 <= current < len(document.pages):
            entry.setIcon(self._thumbnail(document.pages[current]))

    @staticmethod
    def _thumbnail(page) -> QIcon:
        scene = page.scene
        if scene is None:
            pixmap = QPixmap(96, 128)
            pixmap.fill(Qt.white)
            return QIcon(pixmap)
        image = scene.render_image(dpi=18.0, for_print=False)
        return QIcon(QPixmap.fromImage(image))


# ---------------------------------------------------------------------------
# Markups list
# ---------------------------------------------------------------------------

class MarkupsPanel(QWidget):
    """Every markup in the document, filterable and exportable — like a takeoff list."""

    markupActivated = Signal(int, str)

    COLUMNS = ["Page", "Type", "Subject", "Value", "Author", "Date", "Comment"]

    def __init__(self, window):
        super().__init__()
        self.window = window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        top = QHBoxLayout()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter markups…")
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(lambda _: self.rebuild(self.window.document))
        top.addWidget(self.filter, 1)
        export = QToolButton()
        export.setText("CSV")
        export.setToolTip("Export the markups list to CSV")
        export.clicked.connect(self.export_csv)
        top.addWidget(export)
        layout.addLayout(top)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(len(self.COLUMNS))
        self.tree.setHeaderLabels(self.COLUMNS)
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.itemDoubleClicked.connect(self._activate)
        self.tree.header().setSectionResizeMode(QHeaderView.Interactive)
        layout.addWidget(self.tree, 1)

        self.totals = QLabel("")
        self.totals.setWordWrap(True)
        self.totals.setStyleSheet("color:#4a5261; padding:2px;")
        layout.addWidget(self.totals)

    def rebuild(self, document) -> None:
        needle = self.filter.text().strip().lower()
        self.tree.clear()
        rows = []
        for index, page in enumerate(document.pages):
            if page.scene is None:
                continue
            page_node = QTreeWidgetItem([f"Page {index + 1}", "", "", "", "", "", ""])
            font = page_node.font(0)
            font.setBold(True)
            page_node.setFont(0, font)
            added = False
            for item in page.scene.ordered_markups():
                row = [str(index + 1), item.display_name(), item.subject,
                       getattr(item, "value_text", ""), item.author,
                       item.modified[:10], item.summary()]
                if needle and not any(needle in str(cell).lower() for cell in row):
                    continue
                node = QTreeWidgetItem(row)
                node.setData(0, Qt.UserRole, (index, item.uid))
                node.setIcon(1, icon(_icon_for(item), 16))
                if item.locked:
                    node.setForeground(1, QColor("#8b93a1"))
                page_node.addChild(node)
                rows.append(row)
                added = True
            if added or not needle:
                self.tree.addTopLevelItem(page_node)
                page_node.setExpanded(True)
        for column in range(len(self.COLUMNS)):
            self.tree.resizeColumnToContents(column)
        self._rows = rows
        self.totals.setText(self._totals_text(document))

    @staticmethod
    def _totals_text(document) -> str:
        """Group measurement values and count markers, the way a takeoff does."""
        from collections import defaultdict
        lengths = defaultdict(list)
        counts = defaultdict(int)
        for page in document.pages:
            if page.scene is None:
                continue
            for item in page.scene.markups():
                if isinstance(item, CountItem):
                    counts[item.subject] += 1
                elif isinstance(item, MeasureItem) and item.value is not None:
                    lengths[item.subject].append(item.value)
        parts = []
        for subject, values in sorted(lengths.items()):
            try:
                total = values[0]
                for value in values[1:]:
                    total = total + value
                parts.append(f"{subject}: {format_quantity(total, 4)} ({len(values)})")
            except Exception:
                parts.append(f"{subject}: {len(values)} items")
        for subject, number in sorted(counts.items()):
            parts.append(f"{subject}: {number}")
        return "  •  ".join(parts) if parts else "No measurements yet."

    def _activate(self, node: QTreeWidgetItem, _column: int) -> None:
        data = node.data(0, Qt.UserRole)
        if data:
            self.markupActivated.emit(data[0], data[1])

    def export_csv(self) -> None:
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        path, _ = QFileDialog.getSaveFileName(self, "Export markups", "markups.csv",
                                              "CSV files (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(self.COLUMNS)
            writer.writerows(getattr(self, "_rows", []))
        QMessageBox.information(self, "Export markups", f"Saved {path}")


def _icon_for(item) -> str:
    if isinstance(item, MathItem):
        return "math"
    if isinstance(item, TableItem):
        return "table"
    if isinstance(item, MeasureItem):
        return "measure_length"
    if isinstance(item, CountItem):
        return "count"
    if isinstance(item, StampItem):
        return "stamp"
    if isinstance(item, NoteItem):
        return "note"
    if isinstance(item, CalloutItem):
        return "callout"
    if isinstance(item, TextItem):
        return "text"
    if isinstance(item, RectItem):
        return {"ellipse": "ellipse", "cloud": "cloud", "highlight": "highlight"}.get(
            item.kind, "rect")
    if isinstance(item, PolyItem):
        return {"ink": "pen", "highlighter": "highlighter", "arrow": "arrow",
                "polygon": "polygon", "cloud": "cloud"}.get(item.kind, "line")
    return "select"


# ---------------------------------------------------------------------------
# Variables
# ---------------------------------------------------------------------------

class VariablesPanel(QWidget):
    """Live view of every variable and function the document has defined."""

    insertRequested = Signal(str)

    def __init__(self, window):
        super().__init__()
        self.window = window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter variables…")
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(lambda _: self.rebuild(self.window.document.workspace))
        layout.addWidget(self.filter)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Name", "Value", "Defined in"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        self.table.setColumnWidth(0, 84)
        self.table.setColumnWidth(2, 92)
        self.table.setWordWrap(False)
        self.table.itemDoubleClicked.connect(
            lambda cell: self.insertRequested.emit(self.table.item(cell.row(), 0).text()))
        layout.addWidget(self.table, 1)

    def rebuild(self, workspace) -> None:
        needle = self.filter.text().strip().lower()
        entries = []
        for name, info in sorted(workspace.variables.items(), key=lambda kv: kv[1].order):
            entries.append((name, format_quantity(info.value, 6), info.source))
        for name, function in sorted(workspace.functions.items()):
            entries.append((function.signature(), function.source, ""))
        entries = [row for row in entries
                   if not needle or any(needle in str(cell).lower() for cell in row)]
        self.table.setRowCount(len(entries))
        mono = QFont("Cascadia Mono")
        mono.setFamilies(["Cascadia Mono", "Consolas", "DejaVu Sans Mono", "monospace"])
        for row, (name, value, source) in enumerate(entries):
            name_cell = QTableWidgetItem(name)
            name_cell.setFont(mono)
            self.table.setItem(row, 0, name_cell)
            self.table.setItem(row, 1, QTableWidgetItem(value))
            self.table.setItem(row, 2, QTableWidgetItem(source))


class FunctionsPanel(QWidget):
    """Searchable reference of the built-in function library."""

    insertRequested = Signal(str)

    def __init__(self):
        super().__init__()
        from ..core.functions import FUNCTION_HELP, FUNCTIONS
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Search functions…")
        self.filter.setClearButtonEnabled(True)
        layout.addWidget(self.filter)
        self.list = QListWidget()
        self.list.setAlternatingRowColors(True)
        layout.addWidget(self.list, 1)
        self.help = QLabel("Double-click a function to insert it.")
        self.help.setWordWrap(True)
        self.help.setStyleSheet("color:#4a5261; padding:3px;")
        layout.addWidget(self.help)

        self._entries = []
        for name in sorted(FUNCTIONS):
            self._entries.append((name, FUNCTION_HELP.get(name, f"{name}(…)")))
        self.filter.textChanged.connect(self._rebuild)
        self.list.currentRowChanged.connect(self._show_help)
        self.list.itemDoubleClicked.connect(
            lambda entry: self.insertRequested.emit(entry.text().split("(")[0] + "("))
        self._rebuild("")

    def _rebuild(self, needle: str) -> None:
        needle = needle.strip().lower()
        self.list.clear()
        self._visible = [(name, help_text) for name, help_text in self._entries
                         if not needle or needle in name.lower() or needle in help_text.lower()]
        for name, _help in self._visible:
            self.list.addItem(name)

    def _show_help(self, row: int) -> None:
        if 0 <= row < len(self._visible):
            self.help.setText(self._visible[row][1])


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

class PropertiesPanel(QScrollArea):
    """Context-sensitive editor for whatever is selected."""

    changed = Signal(str)

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self._items: list[MarkupItem] = []
        self._building = False
        self.body = QWidget()
        self.setWidget(self.body)
        self.layout = QVBoxLayout(self.body)
        self.layout.setContentsMargins(6, 6, 6, 6)
        self.layout.setSpacing(8)
        self.show_items([])

    # -- construction ------------------------------------------------------
    def show_items(self, items: list[MarkupItem]) -> None:
        self._items = [i for i in items if isinstance(i, MarkupItem)]
        self._building = True
        while self.layout.count():
            child = self.layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                # Hide before unparenting, then unparent before deleting:
                # deleteLater() only runs on the next trip through the event
                # loop, so until then an old child would keep painting over its
                # replacement — and a *visible* widget given no parent becomes a
                # floating top-level window.
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        if not self._items:
            hint = QLabel("Nothing selected.\n\nPick a markup on the page to edit its "
                          "appearance, or choose a tool to draw a new one.")
            hint.setWordWrap(True)
            hint.setStyleSheet("color:#6b7280;")
            self.layout.addWidget(hint)
            self.layout.addStretch(1)
            self._settle()
            self._building = False
            return

        first = self._items[0]
        heading = QLabel(first.display_name() if len(self._items) == 1
                         else f"{len(self._items)} markups selected")
        font = heading.font()
        font.setBold(True)
        heading.setFont(font)
        self.layout.addWidget(heading)

        self._add_appearance(first)
        if any(getattr(i, "HAS_TEXT", False) or isinstance(i, (StampItem, TableItem, MathItem))
               for i in self._items):
            self._add_text(first)
        if any(isinstance(i, (PolyItem, MeasureItem, CalloutItem)) for i in self._items):
            self._add_arrows(first)
        if len(self._items) == 1:
            if isinstance(first, MathItem):
                self._add_math(first)
            elif isinstance(first, TableItem):
                self._add_table(first)
            elif isinstance(first, MeasureItem):
                self._add_measure(first)
            elif isinstance(first, CountItem):
                self._add_count(first)
            elif isinstance(first, StampItem):
                self._add_stamp(first)
            elif isinstance(first, RectItem) and first.kind == "cloud":
                self._add_cloud(first)
            elif isinstance(first, PolyItem) and first.kind == "cloud":
                self._add_cloud(first)
        self._add_metadata(first)
        self.layout.addStretch(1)
        self._settle()
        self._building = False

    def _settle(self) -> None:
        """Re-lay-out the rebuilt form and scroll back to the top.

        Without this the scroll area keeps the geometry of the *previous*
        selection for one more event loop turn, which leaves the panel showing
        empty space below content that is no longer there.
        """
        self.layout.activate()
        self.body.adjustSize()
        self.verticalScrollBar().setValue(0)
        self.horizontalScrollBar().setValue(0)

    def _group(self, title: str) -> QFormLayout:
        box = QGroupBox(title)
        form = QFormLayout(box)
        form.setContentsMargins(8, 8, 8, 8)
        form.setSpacing(5)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.layout.addWidget(box)
        return form

    def _apply(self, setter, description: str) -> None:
        if self._building:
            return
        self.window.view.begin_snapshot()
        for item in self._items:
            setter(item)
            item.touch()
            item.prepareGeometryChange()
            if hasattr(item, "apply_style"):
                item.apply_style()
            item.update()
        self.window.view.commit_snapshot(description)
        self.changed.emit(description)

    # -- sections ----------------------------------------------------------
    def _add_appearance(self, first: MarkupItem) -> None:
        form = self._group("Appearance")

        stroke = ColorButton(first.style.stroke, allow_none=True, label="Line colour")
        stroke.colorChanged.connect(
            lambda colour: self._apply(lambda i: setattr(i.style, "stroke", colour), "Line colour"))
        form.addRow("Line", stroke)

        fill = ColorButton(first.style.fill, allow_none=True, label="Fill colour")
        fill.colorChanged.connect(
            lambda colour: self._apply(lambda i: setattr(i.style, "fill", colour), "Fill colour"))
        form.addRow("Fill", fill)

        width = QDoubleSpinBox()
        width.setRange(0.0, 40.0)
        width.setSingleStep(0.25)
        width.setDecimals(2)
        width.setValue(first.style.width)
        width.setSuffix(" pt")
        width.valueChanged.connect(
            lambda value: self._apply(lambda i: setattr(i.style, "width", value), "Line width"))
        form.addRow("Thickness", width)

        line_style = QComboBox()
        line_style.addItems(list(LINE_STYLES))
        line_style.setCurrentText(first.style.line_style)
        line_style.currentTextChanged.connect(
            lambda value: self._apply(lambda i: setattr(i.style, "line_style", value),
                                      "Line style"))
        form.addRow("Style", line_style)

        opacity = LabeledSlider(5, 100, int(first.style.opacity * 100))
        opacity.valueChanged.connect(
            lambda value: self._apply(lambda i: setattr(i.style, "opacity", value), "Opacity"))
        form.addRow("Opacity", opacity)

        fill_opacity = LabeledSlider(0, 100, int(first.style.fill_opacity * 100))
        fill_opacity.valueChanged.connect(
            lambda value: self._apply(lambda i: setattr(i.style, "fill_opacity", value),
                                      "Fill opacity"))
        form.addRow("Fill opacity", fill_opacity)

        blend = QCheckBox("Multiply (highlighter)")
        blend.setChecked(first.style.blend == "multiply")
        blend.toggled.connect(
            lambda on: self._apply(lambda i: setattr(i.style, "blend",
                                                     "multiply" if on else "normal"), "Blend"))
        form.addRow("", blend)

    def _add_text(self, first: MarkupItem) -> None:
        form = self._group("Text")
        family = QFontComboBox()
        family.setCurrentFont(QFont(first.style.font_family))
        family.currentFontChanged.connect(
            lambda font: self._apply(lambda i: setattr(i.style, "font_family", font.family()),
                                     "Font"))
        form.addRow("Font", family)

        size = QDoubleSpinBox()
        size.setRange(3.0, 96.0)
        size.setSingleStep(0.5)
        size.setValue(first.style.font_size)
        size.setSuffix(" pt")
        size.valueChanged.connect(
            lambda value: self._apply(lambda i: setattr(i.style, "font_size", value), "Font size"))
        form.addRow("Size", size)

        row = QHBoxLayout()
        for label, attribute in (("B", "bold"), ("I", "italic"), ("U", "underline")):
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.setChecked(getattr(first.style, attribute))
            button.toggled.connect(
                lambda on, a=attribute: self._apply(lambda i: setattr(i.style, a, on), "Font style"))
            row.addWidget(button)
        row.addStretch(1)
        holder = QWidget()
        holder.setLayout(row)
        form.addRow("Weight", holder)

        colour = ColorButton(first.style.text_color, label="Text colour")
        colour.colorChanged.connect(
            lambda value: self._apply(lambda i: setattr(i.style, "text_color", value),
                                      "Text colour"))
        form.addRow("Colour", colour)

        align = QComboBox()
        align.addItems(["left", "center", "right", "justify"])
        align.setCurrentText(first.style.align)
        align.currentTextChanged.connect(
            lambda value: self._apply(lambda i: setattr(i.style, "align", value), "Alignment"))
        form.addRow("Align", align)

        valign = QComboBox()
        valign.addItems(["top", "middle", "bottom"])
        valign.setCurrentText(first.style.valign)
        valign.currentTextChanged.connect(
            lambda value: self._apply(lambda i: setattr(i.style, "valign", value), "Alignment"))
        form.addRow("Vertical", valign)

    def _add_arrows(self, first: MarkupItem) -> None:
        form = self._group("Ends")
        start = QComboBox()
        start.addItems(ARROW_HEADS)
        start.setCurrentText(first.style.arrow_start)
        start.currentTextChanged.connect(
            lambda value: self._apply(lambda i: setattr(i.style, "arrow_start", value), "Arrow"))
        form.addRow("Start", start)
        end = QComboBox()
        end.addItems(ARROW_HEADS)
        end.setCurrentText(first.style.arrow_end)
        end.currentTextChanged.connect(
            lambda value: self._apply(lambda i: setattr(i.style, "arrow_end", value), "Arrow"))
        form.addRow("End", end)

    def _add_cloud(self, first) -> None:
        form = self._group("Cloud")
        radius = QDoubleSpinBox()
        radius.setRange(2.0, 60.0)
        radius.setValue(first.cloud_radius)
        radius.setSuffix(" pt")
        radius.valueChanged.connect(
            lambda value: self._apply(lambda i: setattr(i, "cloud_radius", value), "Cloud size"))
        form.addRow("Arc size", radius)

    def _add_math(self, item: MathItem) -> None:
        form = self._group("Calculation")
        digits = QSpinBox()
        digits.setRange(1, 12)
        digits.setValue(item.digits)
        digits.valueChanged.connect(
            lambda value: self._apply(lambda i: (setattr(i, "digits", value), i.relayout()),
                                      "Precision"))
        form.addRow("Significant digits", digits)

        number_format = QComboBox()
        number_format.addItems(["auto", "fixed", "scientific", "engineering"])
        number_format.setCurrentText(item.number_format)
        number_format.currentTextChanged.connect(
            lambda value: self._apply(lambda i: (setattr(i, "number_format", value), i.relayout()),
                                      "Number format"))
        form.addRow("Number format", number_format)

        for label, attribute in (("Show results of definitions", "show_definition_results"),
                                 ("Align results in a column", "align_results"),
                                 ("Show comments", "show_comments")):
            box = QCheckBox(label)
            box.setChecked(getattr(item, attribute))
            box.toggled.connect(
                lambda on, a=attribute: self._apply(
                    lambda i: (setattr(i, a, on), i.relayout()), "Calculation layout"))
            form.addRow("", box)

        edit = QPushButton("Edit calculation…")
        edit.clicked.connect(lambda: self.window.view.begin_item_edit(item))
        form.addRow("", edit)

    def _add_table(self, item: TableItem) -> None:
        form = self._group("Table")
        title = QLineEdit(item.title)
        title.textEdited.connect(
            lambda value: self._apply(lambda i: setattr(i, "title", value), "Table title"))
        form.addRow("Title", title)

        rows = QSpinBox()
        rows.setRange(1, 2000)
        rows.setValue(item.sheet.rows)
        rows.valueChanged.connect(
            lambda value: self._apply(
                lambda i: i.sheet.resize(value, i.sheet.cols), "Table size"))
        form.addRow("Rows", rows)

        cols = QSpinBox()
        cols.setRange(1, 200)
        cols.setValue(item.sheet.cols)
        cols.valueChanged.connect(
            lambda value: self._apply(
                lambda i: i.sheet.resize(i.sheet.rows, value), "Table size"))
        form.addRow("Columns", cols)

        digits = QSpinBox()
        digits.setRange(1, 12)
        digits.setValue(item.sheet.digits)
        digits.valueChanged.connect(
            lambda value: self._apply(lambda i: setattr(i.sheet, "digits", value), "Precision"))
        form.addRow("Digits", digits)

        for label, attribute in (("Header row", "header_row"), ("Banded rows", "banded"),
                                 ("Grid lines", "grid_lines")):
            box = QCheckBox(label)
            box.setChecked(getattr(item.sheet, attribute))
            box.toggled.connect(
                lambda on, a=attribute: self._apply(
                    lambda i: setattr(i.sheet, a, on), "Table style"))
            form.addRow("", box)

        publish = QCheckBox("Publish columns as variables")
        publish.setToolTip("Each column header becomes a variable holding that column's values")
        publish.setChecked(item.publish_headers)
        publish.toggled.connect(
            lambda on: self._apply(lambda i: setattr(i, "publish_headers", on), "Publish columns"))
        form.addRow("", publish)

        names = QPushButton("Named cells…")
        names.clicked.connect(lambda: self.window.edit_named_cells(item))
        form.addRow("", names)

    def _add_measure(self, item: MeasureItem) -> None:
        form = self._group("Measurement")
        value = QLabel(item.value_text or "—")
        font = value.font()
        font.setBold(True)
        value.setFont(font)
        form.addRow("Value", value)

        subject = QLineEdit(item.subject)
        subject.setToolTip("Measurements sharing a subject are totalled in the markups list")
        subject.textEdited.connect(
            lambda text: self._apply(lambda i: setattr(i, "subject", text), "Subject"))
        form.addRow("Subject", subject)

        if item.kind in ("area", "volume", "perimeter"):
            unit = UnitCombo(self.window.current_page().scale.area_unit)
            unit.currentTextChanged.connect(self.window.set_area_unit)
            form.addRow("Area unit", unit)
        if item.kind == "volume":
            depth = QLineEdit(item.depth_text)
            depth.setPlaceholderText("e.g. 150 mm")
            depth.textEdited.connect(
                lambda text: self._apply(
                    lambda i: (setattr(i, "depth_text", text),
                               i.refresh(page=self.window.current_page())), "Depth"))
            form.addRow("Depth", depth)

        label = QCheckBox("Show value label")
        label.setChecked(item.show_label)
        label.toggled.connect(
            lambda on: self._apply(lambda i: setattr(i, "show_label", on), "Label"))
        form.addRow("", label)

        calibrate = QPushButton("Calibrate page scale…")
        calibrate.clicked.connect(lambda: self.window.calibrate_dialog())
        form.addRow("", calibrate)

    def _add_count(self, item: CountItem) -> None:
        form = self._group("Count")
        subject = QLineEdit(item.subject)
        subject.textEdited.connect(
            lambda text: self._apply(lambda i: setattr(i, "subject", text), "Count subject"))
        form.addRow("Subject", subject)
        symbol = QComboBox()
        symbol.addItems(list(CountItem.SYMBOLS))
        symbol.setCurrentText(item.symbol)
        symbol.currentTextChanged.connect(
            lambda value: self._apply(lambda i: setattr(i, "symbol", value), "Count symbol"))
        form.addRow("Symbol", symbol)
        show = QCheckBox("Show number")
        show.setChecked(item.show_index)
        show.toggled.connect(
            lambda on: self._apply(lambda i: setattr(i, "show_index", on), "Count label"))
        form.addRow("", show)

    def _add_stamp(self, item: StampItem) -> None:
        form = self._group("Stamp")
        preset = QComboBox()
        preset.setEditable(True)
        preset.addItems(list(STAMP_PRESETS))
        preset.setCurrentText(item.text)
        preset.currentTextChanged.connect(self._set_stamp_text)
        form.addRow("Text", preset)
        subtext = QLineEdit(item.subtext)
        subtext.setPlaceholderText("Name, date, revision…")
        subtext.textEdited.connect(
            lambda text: self._apply(lambda i: setattr(i, "subtext", text), "Stamp"))
        form.addRow("Sub-text", subtext)

    def _set_stamp_text(self, text: str) -> None:
        colour = STAMP_PRESETS.get(text.upper())

        def setter(item):
            item.text = text
            if colour:
                item.style.stroke = colour
                item.style.fill = colour
                item.style.text_color = colour
        self._apply(setter, "Stamp text")

    def _add_metadata(self, first: MarkupItem) -> None:
        form = self._group("Details")
        label = QLineEdit(first.label)
        label.textEdited.connect(
            lambda text: self._apply(lambda i: setattr(i, "label", text), "Label"))
        form.addRow("Label", label)

        author = QLineEdit(first.author)
        author.textEdited.connect(
            lambda text: self._apply(lambda i: setattr(i, "author", text), "Author"))
        form.addRow("Author", author)

        comment = QPlainTextEdit(first.comment)
        comment.setFixedHeight(58)
        comment.textChanged.connect(
            lambda: self._apply(lambda i: setattr(i, "comment", comment.toPlainText()), "Comment"))
        form.addRow("Comment", comment)

        layer = QComboBox()
        layer.addItems([lyr.name for lyr in self.window.document.layers])
        layer.setCurrentText(first.layer)
        layer.currentTextChanged.connect(
            lambda text: self._apply(lambda i: setattr(i, "layer", text), "Layer"))
        form.addRow("Layer", layer)

        locked = QCheckBox("Locked")
        locked.setChecked(first.locked)
        locked.toggled.connect(
            lambda on: self._apply(lambda i: i.set_locked(on), "Lock"))
        form.addRow("", locked)

        printable = QCheckBox("Include when printing")
        printable.setChecked(first.printable)
        printable.toggled.connect(
            lambda on: self._apply(lambda i: setattr(i, "printable", on), "Print flag"))
        form.addRow("", printable)
