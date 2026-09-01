"""Modal dialogs: page setup, scale, PDF import, document properties and more."""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QGroupBox, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QMessageBox, QPushButton,
                               QRadioButton, QSpinBox, QTableWidget, QTableWidgetItem,
                               QTabWidget, QVBoxLayout, QWidget)

from ..core.document import (PAGE_SIZES, PageScale, PageSetup)
from ..core.units import parse_unit
from ..io import pdfio
from .widgets import UnitCombo


def _buttons(dialog: QDialog) -> QDialogButtonBox:
    box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)
    return box


class PageSetupDialog(QDialog):
    """Paper size, orientation and margins."""

    def __init__(self, setup: PageSetup, parent=None, multiple_pages: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Page setup")
        self.setup = PageSetup.from_dict(setup.to_dict())
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.size = QComboBox()
        self.size.addItems(list(PAGE_SIZES) + ["Custom"])
        self.size.setCurrentText(setup.size_name if setup.size_name in PAGE_SIZES else "Custom")
        self.size.currentTextChanged.connect(self._size_changed)
        form.addRow("Paper", self.size)

        sizes = QHBoxLayout()
        self.width = QDoubleSpinBox()
        self.width.setRange(20, 2000)
        self.width.setSuffix(" mm")
        self.width.setValue(setup.width_mm)
        self.height = QDoubleSpinBox()
        self.height.setRange(20, 2000)
        self.height.setSuffix(" mm")
        self.height.setValue(setup.height_mm)
        sizes.addWidget(self.width)
        sizes.addWidget(QLabel("×"))
        sizes.addWidget(self.height)
        holder = QWidget()
        holder.setLayout(sizes)
        form.addRow("Size", holder)

        self.orientation = QComboBox()
        self.orientation.addItems(["portrait", "landscape"])
        self.orientation.setCurrentText(setup.orientation)
        form.addRow("Orientation", self.orientation)
        layout.addLayout(form)

        margins = QGroupBox("Margins")
        margin_form = QFormLayout(margins)
        self.margins = {}
        for key, label, value in (("margin_left", "Left", setup.margin_left),
                                  ("margin_top", "Top", setup.margin_top),
                                  ("margin_right", "Right", setup.margin_right),
                                  ("margin_bottom", "Bottom", setup.margin_bottom)):
            spin = QDoubleSpinBox()
            spin.setRange(0, 100)
            spin.setSuffix(" mm")
            spin.setValue(value)
            margin_form.addRow(label, spin)
            self.margins[key] = spin
        layout.addWidget(margins)

        self.apply_all = QCheckBox("Apply to every page")
        self.apply_all.setEnabled(multiple_pages)
        layout.addWidget(self.apply_all)
        layout.addWidget(_buttons(self))

    def _size_changed(self, name: str) -> None:
        if name in PAGE_SIZES:
            width, height = PAGE_SIZES[name]
            self.width.setValue(width)
            self.height.setValue(height)

    def result_setup(self) -> PageSetup:
        setup = PageSetup(size_name=self.size.currentText(),
                          width_mm=self.width.value(),
                          height_mm=self.height.value(),
                          orientation=self.orientation.currentText())
        for key, spin in self.margins.items():
            setattr(setup, key, spin.value())
        return setup


class ScaleDialog(QDialog):
    """Set the drawing scale, either as a ratio or from a measured distance."""

    RATIOS = ["1:1", "1:5", "1:10", "1:20", "1:25", "1:50", "1:100", "1:200",
              "1:250", "1:500", "1:1000", "1:1250", "1:2500"]

    def __init__(self, scale: PageScale, measured_pt: Optional[float] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Page scale")
        self.measured_pt = measured_pt
        layout = QVBoxLayout(self)

        if measured_pt:
            note = QLabel(f"You drew a line {measured_pt:.1f} pt long on the page.\n"
                          "Type the real-world length it represents.")
            note.setWordWrap(True)
            layout.addWidget(note)

        self.by_measure = QRadioButton("From the distance I just drew")
        self.by_ratio = QRadioButton("From a standard ratio")
        self.by_measure.setChecked(bool(measured_pt))
        self.by_ratio.setChecked(not measured_pt)
        self.by_measure.setEnabled(bool(measured_pt))
        layout.addWidget(self.by_measure)

        form = QFormLayout()
        self.known = QLineEdit("5 m")
        self.known.setEnabled(bool(measured_pt))
        form.addRow("Represents", self.known)
        layout.addLayout(form)

        layout.addWidget(self.by_ratio)
        ratio_form = QFormLayout()
        self.ratio = QComboBox()
        self.ratio.setEditable(True)
        self.ratio.addItems(self.RATIOS)
        self.ratio.setCurrentText(scale.label if scale.label in self.RATIOS else "1:100")
        ratio_form.addRow("Ratio", self.ratio)
        layout.addLayout(ratio_form)

        units = QFormLayout()
        self.length_unit = UnitCombo(scale.display_unit)
        units.addRow("Show lengths in", self.length_unit)
        self.area_unit = UnitCombo(scale.area_unit)
        units.addRow("Show areas in", self.area_unit)
        self.precision = QSpinBox()
        self.precision.setRange(0, 6)
        self.precision.setValue(scale.precision)
        units.addRow("Decimal places", self.precision)
        layout.addLayout(units)
        layout.addWidget(_buttons(self))

        self.by_measure.toggled.connect(self.known.setEnabled)
        self.by_ratio.toggled.connect(self.ratio.setEnabled)

    def result_scale(self) -> Optional[PageScale]:
        if self.by_measure.isChecked() and self.measured_pt:
            if parse_unit(self.known.text()) is None:
                QMessageBox.warning(self, "Page scale",
                                    "That length could not be read. Try something like “5 m”.")
                return None
            scale = PageScale.from_calibration(self.measured_pt, self.known.text())
        else:
            text = self.ratio.currentText().strip()
            try:
                ratio = float(text.split(":")[-1])
            except ValueError:
                QMessageBox.warning(self, "Page scale", "Enter a ratio such as 1:100.")
                return None
            scale = PageScale.from_ratio(ratio)
        scale.display_unit = self.length_unit.currentText() or "m"
        scale.area_unit = self.area_unit.currentText() or "m^2"
        scale.precision = self.precision.value()
        return scale


class PdfImportDialog(QDialog):
    """Choose a PDF and which of its pages to bring in."""

    def __init__(self, parent=None, current_setup: Optional[PageSetup] = None):
        super().__init__(parent)
        self.setWindowTitle("Insert PDF pages")
        self.path = ""
        self._count = 0
        layout = QVBoxLayout(self)

        picker = QHBoxLayout()
        self.file = QLineEdit()
        self.file.setPlaceholderText("Choose a PDF file…")
        self.file.setReadOnly(True)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.browse)
        picker.addWidget(self.file, 1)
        picker.addWidget(browse)
        layout.addLayout(picker)

        form = QFormLayout()
        self.pages = QLineEdit("all")
        self.pages.setPlaceholderText("all, or 1-3,7")
        form.addRow("Pages", self.pages)

        self.fit = QComboBox()
        self.fit.addItem("Keep the PDF's own page size", pdfio.FIT_ORIGINAL)
        self.fit.addItem("Fit to A4", pdfio.FIT_A4)
        self.fit.addItem("Fit to this document's page size", pdfio.FIT_CURRENT)
        form.addRow("Page size", self.fit)

        self.dpi = QSpinBox()
        self.dpi.setRange(72, 600)
        self.dpi.setValue(150)
        self.dpi.setSuffix(" dpi")
        self.dpi.setToolTip("Higher values look sharper when zoomed in, "
                            "but make the file larger")
        form.addRow("Render at", self.dpi)
        layout.addLayout(form)

        self.info = QLabel("")
        self.info.setStyleSheet("color:#5a6270;")
        layout.addWidget(self.info)
        layout.addWidget(_buttons(self))

    def browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose a PDF", "",
                                              "PDF files (*.pdf);;All files (*)")
        if not path:
            return
        try:
            self._count = pdfio.page_count(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Insert PDF", str(exc))
            return
        self.path = path
        self.file.setText(path)
        self.info.setText(f"{os.path.basename(path)} — {self._count} page"
                          f"{'s' if self._count != 1 else ''}")

    def selection(self) -> tuple[str, list[int], str, int]:
        indices = pdfio.parse_page_range(self.pages.text(), self._count)
        return self.path, indices, self.fit.currentData(), self.dpi.value()


class DocumentPropertiesDialog(QDialog):
    """Title block information, running headers and calculation defaults."""

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Document properties")
        self.document = document
        self.resize(520, 460)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs, 1)

        info = QWidget()
        info_form = QFormLayout(info)
        self.title = QLineEdit(document.title)
        self.author = QLineEdit(document.author)
        self.subject = QLineEdit(document.subject)
        self.project = QLineEdit(document.project)
        info_form.addRow("Title", self.title)
        info_form.addRow("Project", self.project)
        info_form.addRow("Author", self.author)
        info_form.addRow("Subject", self.subject)
        tabs.addTab(info, "Information")

        running = QWidget()
        running_form = QFormLayout(running)
        settings = document.settings
        self.show_header = QCheckBox("Show a header on every page")
        self.show_header.setChecked(settings.show_header)
        self.show_footer = QCheckBox("Show a footer on every page")
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
        hint = QLabel("Fields: {title} {project} {author} {subject} {page} {pages} "
                      "{date} {time} {file}")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#5a6270;")
        running_form.addRow(hint)
        tabs.addTab(running, "Header && footer")

        calc = QWidget()
        calc_form = QFormLayout(calc)
        self.precision = QSpinBox()
        self.precision.setRange(1, 12)
        self.precision.setValue(settings.precision)
        calc_form.addRow("Default significant digits", self.precision)
        self.number_format = QComboBox()
        self.number_format.addItems(["auto", "fixed", "scientific", "engineering"])
        self.number_format.setCurrentText(settings.number_format)
        calc_form.addRow("Default number format", self.number_format)
        self.math_size = QDoubleSpinBox()
        self.math_size.setRange(4, 40)
        self.math_size.setValue(settings.math_size)
        self.math_size.setSuffix(" pt")
        calc_form.addRow("Calculation text size", self.math_size)
        self.default_author = QLineEdit(settings.default_author)
        self.default_author.setPlaceholderText("Stamped on new markups")
        calc_form.addRow("Markup author", self.default_author)
        tabs.addTab(calc, "Calculations")

        grid = QWidget()
        grid_form = QFormLayout(grid)
        self.show_grid = QCheckBox("Show grid")
        self.show_grid.setChecked(settings.show_grid)
        self.snap = QCheckBox("Snap to grid")
        self.snap.setChecked(settings.snap_to_grid)
        self.grid_mm = QDoubleSpinBox()
        self.grid_mm.setRange(0.5, 100)
        self.grid_mm.setValue(settings.grid_mm)
        self.grid_mm.setSuffix(" mm")
        self.show_margins = QCheckBox("Show margin guides")
        self.show_margins.setChecked(settings.show_margins)
        grid_form.addRow(self.show_grid)
        grid_form.addRow(self.snap)
        grid_form.addRow("Grid spacing", self.grid_mm)
        grid_form.addRow(self.show_margins)
        tabs.addTab(grid, "Grid")

        layout.addWidget(_buttons(self))

    def apply(self) -> None:
        document = self.document
        document.title = self.title.text()
        document.author = self.author.text()
        document.subject = self.subject.text()
        document.project = self.project.text()
        settings = document.settings
        settings.show_header = self.show_header.isChecked()
        settings.show_footer = self.show_footer.isChecked()
        settings.header_left, settings.header_center, settings.header_right = (
            field.text() for field in self.header_fields)
        settings.footer_left, settings.footer_center, settings.footer_right = (
            field.text() for field in self.footer_fields)
        settings.precision = self.precision.value()
        settings.number_format = self.number_format.currentText()
        settings.math_size = self.math_size.value()
        settings.default_author = self.default_author.text()
        settings.show_grid = self.show_grid.isChecked()
        settings.snap_to_grid = self.snap.isChecked()
        settings.grid_mm = self.grid_mm.value()
        settings.show_margins = self.show_margins.isChecked()
        document.modified = True


class NamedCellsDialog(QDialog):
    """Give cells or ranges a variable name so calculations can use them."""

    def __init__(self, table, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Named cells")
        self.table_item = table
        self.resize(420, 320)
        layout = QVBoxLayout(self)
        note = QLabel("Name a cell or range here and every calculation in the document "
                      "can use that name — for example <b>W_total</b> = <b>E7</b>.")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.grid = QTableWidget(0, 2)
        self.grid.setHorizontalHeaderLabels(["Variable name", "Cell or range"])
        self.grid.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.grid.verticalHeader().setVisible(False)
        layout.addWidget(self.grid, 1)
        for name, ref in table.named_cells.items():
            self._add_row(name, ref)
        self._add_row("", table.current_ref())

        buttons = QHBoxLayout()
        add = QPushButton("Add row")
        add.clicked.connect(lambda: self._add_row("", ""))
        remove = QPushButton("Remove row")
        remove.clicked.connect(self._remove_row)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        layout.addWidget(_buttons(self))

    def _add_row(self, name: str, ref: str) -> None:
        row = self.grid.rowCount()
        self.grid.insertRow(row)
        self.grid.setItem(row, 0, QTableWidgetItem(name))
        self.grid.setItem(row, 1, QTableWidgetItem(ref))

    def _remove_row(self) -> None:
        row = self.grid.currentRow()
        if row >= 0:
            self.grid.removeRow(row)

    def result_names(self) -> dict[str, str]:
        names: dict[str, str] = {}
        for row in range(self.grid.rowCount()):
            name_cell = self.grid.item(row, 0)
            ref_cell = self.grid.item(row, 1)
            name = name_cell.text().strip() if name_cell else ""
            ref = ref_cell.text().strip().upper() if ref_cell else ""
            if name and ref and name.isidentifier():
                names[name] = ref
        return names


class CountSubjectDialog(QDialog):
    """Pick what the count tool is counting."""

    def __init__(self, subject: str, symbol: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Count tool")
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


class ShortcutManagerDialog(QDialog):
    """Edit, check and reset the keyboard bindings."""

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Customise shortcuts")
        self.manager = manager
        self.resize(560, 560)
        layout = QVBoxLayout(self)

        note = QLabel(
            "Type the keys for each command. A single character — <b>\"</b> for text, "
            "<b>\\</b> for maths — acts when you type it straight onto the page with "
            "nothing selected. Anything longer, such as <b>Ctrl+0</b>, works everywhere. "
            "Leave a row empty to unbind it.")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Group", "Command", "Shortcut", "Default"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.table, 1)

        self.editors: dict[str, QLineEdit] = {}
        for binding in manager.bindings():
            row = self.table.rowCount()
            self.table.insertRow(row)
            group = QTableWidgetItem(binding.category)
            group.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 0, group)
            label = QTableWidgetItem(binding.label)
            label.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 1, label)
            editor = QLineEdit(manager.sequence(binding.action_id))
            editor.setPlaceholderText("unbound")
            editor.textChanged.connect(lambda _t: self._check())
            self.table.setCellWidget(row, 2, editor)
            self.editors[binding.action_id] = editor
            default = QTableWidgetItem(binding.default or "—")
            default.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 3, default)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        self.warning = QLabel("")
        self.warning.setStyleSheet("color:#b3261e;")
        self.warning.setWordWrap(True)
        layout.addWidget(self.warning)

        buttons = QHBoxLayout()
        reset_row = QPushButton("Reset this row")
        reset_row.clicked.connect(self._reset_row)
        reset_all = QPushButton("Reset all")
        reset_all.clicked.connect(self._reset_all)
        buttons.addWidget(reset_row)
        buttons.addWidget(reset_all)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        layout.addWidget(_buttons(self))
        self._check()

    def _reset_row(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        binding = self.manager.bindings()[row]
        self.editors[binding.action_id].setText(binding.default)

    def _reset_all(self) -> None:
        for binding in self.manager.bindings():
            self.editors[binding.action_id].setText(binding.default)

    def _check(self) -> None:
        seen: dict[str, list[str]] = {}
        for binding in self.manager.bindings():
            text = self.editors[binding.action_id].text().strip()
            if text:
                seen.setdefault(text.lower(), []).append(binding.label)
        clashes = [f"{key}: {', '.join(labels)}" for key, labels in seen.items()
                   if len(labels) > 1]
        self.warning.setText("Used more than once — " + "; ".join(clashes) if clashes else "")

    def apply(self) -> None:
        for binding in self.manager.bindings():
            self.manager.set_sequence(binding.action_id,
                                      self.editors[binding.action_id].text())


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
        body = QLabel(
            "Engineering calculations, drawing markup and spreadsheets in one "
            "page-by-page document.\n\n"
            "• Unit-aware maths with named variables and functions\n"
            "• A full markup tool set with scaled measurement and takeoff\n"
            "• Spreadsheets that read the same variables as your calculations\n"
            "• Import PDF pages, print or export to PDF — A4 by default")
        body.setWordWrap(True)
        layout.addWidget(body)
        box = QDialogButtonBox(QDialogButtonBox.Close)
        box.rejected.connect(self.reject)
        box.accepted.connect(self.accept)
        layout.addWidget(box)


class ShortcutsDialog(QDialog):
    ROWS = [
        ("Typing on the page", ""),
        ("\"", "Start a text region where the cursor is"),
        ("\\", "Start a calculation where the cursor is"),
        ("|", "Start a table here"),
        ("@", "Start a callout here"),
        ("any other key", "Nothing, unless you bind it (Help ▸ Customise shortcuts)"),
        ("Tools", ""),
        ("Esc", "Back to the select tool / finish what you are doing"),
        ("P / K", "Pen / highlighter"),
        ("L / A", "Line / arrow"),
        ("R / E / C", "Rectangle / ellipse / revision cloud"),
        ("T / N / S", "Text box / note / stamp"),
        ("M / B", "Calculation / table"),
        ("H", "Pan"),
        ("Canvas", ""),
        ("Ctrl + wheel", "Zoom"),
        ("Space + drag", "Pan"),
        ("Shift + drag", "Constrain to 15° or square"),
        ("Double-click", "Edit text, calculation or table · add a vertex to a polyline"),
        ("Delete", "Delete the selection"),
        ("Arrow keys", "Nudge the selection"),
        ("Enter", "In a one-line calculation: open the next line below"),
        ("Shift+Enter", "In a calculation: keep typing on a new line of the same region"),
        ("Spreadsheet", ""),
        ("Enter / F2", "Edit the current cell"),
        ("Tab / arrows", "Move between cells"),
        ("Ctrl+D / Ctrl+R", "Fill down / fill right"),
        ("Esc", "Leave the spreadsheet"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keyboard shortcuts")
        self.resize(460, 520)
        layout = QVBoxLayout(self)
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
        box = QDialogButtonBox(QDialogButtonBox.Close)
        box.rejected.connect(self.reject)
        layout.addWidget(box)
