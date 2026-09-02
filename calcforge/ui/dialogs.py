"""Modal dialogs: page setup, scale, PDF import, document properties and more."""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import QKeyCombination, Qt, Signal
from PySide6.QtGui import QFont, QKeySequence, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox,
                               QCompleter, QDialog,
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
    """Set the drawing scale: from a standard ratio, or from a measured distance.

    Two ways in, and both have to be reachable from a standing start. Picking
    two points on the drawing is a button here rather than a radio that can
    only be chosen once a measurement already exists — which is what it was,
    and it read as broken.
    """

    RATIOS = ["1:1", "1:5", "1:10", "1:20", "1:25", "1:50", "1:100", "1:200",
              "1:250", "1:500", "1:1000", "1:1250", "1:2500"]

    PICK = QDialog.Accepted + 10        # "let me point at two things instead"

    def __init__(self, scale: PageScale, measured_pt: Optional[float] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Page scale")
        self.measured_pt = measured_pt
        layout = QVBoxLayout(self)

        if measured_pt:
            box = QGroupBox("From the distance you drew")
            box.setToolTip("Clear this box to use the ratio below instead")
            form = QFormLayout(box)
            note = QLabel(f"You drew a line {measured_pt:.1f} pt long on the page. "
                          "Type the real-world length it stands for.")
            note.setWordWrap(True)
            form.addRow(note)
            self.known = QLineEdit("5 m")
            self.known.setPlaceholderText("5 m, 12 ft, 3600 mm…")
            form.addRow("It represents", self.known)
            layout.addWidget(box)
        else:
            self.known = QLineEdit("5 m")
            self.known.hide()
            pick = QPushButton("Calibrate — pick two points on the drawing…")
            pick.setToolTip("Click one end of something you know the length of, "
                            "then the other, then type that length")
            pick.clicked.connect(lambda: self.done(self.PICK))
            layout.addWidget(pick)

        ratio_box = QGroupBox("…or from a standard ratio" if measured_pt
                              else "From a standard ratio")
        ratio_form = QFormLayout(ratio_box)
        self.ratio = QComboBox()
        self.ratio.setEditable(True)
        self.ratio.addItems(self.RATIOS)
        self.ratio.setCurrentText(scale.label if scale.label in self.RATIOS else "1:100")
        ratio_form.addRow("Ratio", self.ratio)
        layout.addWidget(ratio_box)

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

    def result_scale(self) -> Optional[PageScale]:
        # A measured distance wins when one was drawn and named; empty the box
        # and the ratio below is used instead.
        if self.measured_pt and self.known.text().strip():
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

        # A look at what is actually coming in. A drawing that renders blank is
        # obvious here rather than after it has been inserted.
        self.preview = QLabel("Choose a PDF to see the first page it will bring in")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(200)
        self.preview.setStyleSheet(
            "QLabel { border:1px solid palette(mid); background: palette(base); "
            "color:#5a6270; }")
        layout.addWidget(self.preview, 1)
        self.pages.textChanged.connect(lambda _: self.show_preview())

        layout.addWidget(_buttons(self))

    def _say_in_preview(self, message: str) -> None:
        """Words instead of a picture. Clearing the pixmap first, because
        setting a null one afterwards would wipe the words again."""
        self.preview.clear()
        self.preview.setText(message)

    def show_preview(self) -> None:
        """Draw the first page of the chosen range into the preview panel."""
        if not self.path or not self._count:
            return
        indices = pdfio.parse_page_range(self.pages.text(), self._count)
        if not indices:
            self._say_in_preview("No pages in that range")
            return
        try:
            image = pdfio.render_preview(self.path, indices[0], 560)
        except Exception as exc:  # noqa: BLE001
            self._say_in_preview(str(exc))
            return
        if image is None or image.isNull():
            self._say_in_preview(f"Page {indices[0] + 1} could not be drawn")
            return
        self.preview.setPixmap(QPixmap.fromImage(image).scaled(
            self.preview.width() - 8, self.preview.height() - 8,
            Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.preview.setText("")

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
        self.show_preview()

    def selection(self) -> tuple[str, list[int], str, int]:
        indices = pdfio.parse_page_range(self.pages.text(), self._count)
        return self.path, indices, self.fit.currentData(), self.dpi.value()


class TableSizeDialog(QDialog):
    """How many rows and columns a new table starts with."""

    def __init__(self, rows: int, cols: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New table")
        layout = QVBoxLayout(self)
        note = QLabel("How big is this table? Rows and columns can be added "
                      "or taken away later from its right-click menu.")
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.rows = QSpinBox()
        self.rows.setRange(1, 500)
        self.rows.setValue(rows)
        form.addRow("Rows", self.rows)
        self.cols = QSpinBox()
        self.cols.setRange(1, 100)
        self.cols.setValue(cols)
        form.addRow("Columns", self.cols)
        self.header = QCheckBox("First row is a header")
        form.addRow(self.header)
        layout.addLayout(form)
        layout.addWidget(_buttons(self))
        self.rows.setFocus()

    def values(self) -> tuple[int, int, bool]:
        return self.rows.value(), self.cols.value(), self.header.isChecked()


class PlotDialog(QDialog):
    """What a graph plots: its curves, the variable and the range.

    A plot with nothing in it is a blank box, and the way to fill it in used
    to be a text field in a panel that had to be found first. This asks
    outright, and offers the names the document already defines.
    """

    def __init__(self, item, names=(), parent=None):
        super().__init__(parent)
        self.setWindowTitle("Plot")
        self.item = item
        self.names = sorted(names)
        self.resize(520, 520)
        layout = QVBoxLayout(self)

        note = QLabel("One curve per row. Write an expression in the variable "
                      "below — <b>w*x*(L-x)/2</b> — or the name of a function "
                      "you have defined.")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.curves = QTableWidget(0, 2)
        self.curves.setHorizontalHeaderLabels(["Expression", "Legend label"])
        self.curves.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.curves.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.curves.verticalHeader().setVisible(False)
        layout.addWidget(self.curves, 1)
        for series in item.series:
            self._add_row(series.expression, series.label)
        if not item.series:
            self._add_row("", "")

        buttons = QHBoxLayout()
        add = QPushButton("Add curve")
        add.clicked.connect(lambda: self._add_row("", ""))
        remove = QPushButton("Remove curve")
        remove.clicked.connect(self._remove_row)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        form = QFormLayout()
        self.variable = QLineEdit(item.variable)
        self.variable.setPlaceholderText("x")
        form.addRow("Plot against", self.variable)
        self.x_from = QLineEdit(item.x_from)
        self.x_from.setPlaceholderText("0 m")
        form.addRow("From", self.x_from)
        self.x_to = QLineEdit(item.x_to)
        self.x_to.setPlaceholderText("L")
        form.addRow("To", self.x_to)
        for edit in (self.x_from, self.x_to):
            edit.setCompleter(self._completer(edit))
        self.title = QLineEdit(item.title)
        form.addRow("Title", self.title)
        self.x_label = QLineEdit(item.x_label)
        form.addRow("X label", self.x_label)
        self.y_label = QLineEdit(item.y_label)
        form.addRow("Y label", self.y_label)
        self.x_unit = UnitCombo(item.x_unit)
        form.addRow("X unit", self.x_unit)
        self.y_unit = UnitCombo(item.y_unit)
        form.addRow("Y unit", self.y_unit)
        layout.addLayout(form)

        toggles = QHBoxLayout()
        self.grid = QCheckBox("Grid")
        self.grid.setChecked(item.show_grid)
        self.legend = QCheckBox("Legend")
        self.legend.setChecked(item.show_legend)
        self.markers = QCheckBox("Markers")
        self.markers.setChecked(item.show_markers)
        for box in (self.grid, self.legend, self.markers):
            toggles.addWidget(box)
        toggles.addStretch(1)
        layout.addLayout(toggles)
        layout.addWidget(_buttons(self))

    def _completer(self, parent):
        completer = QCompleter(self.names, parent)
        completer.setCaseSensitivity(Qt.CaseSensitive)
        completer.setFilterMode(Qt.MatchContains)
        return completer

    def _add_row(self, expression: str, label: str) -> None:
        row = self.curves.rowCount()
        self.curves.insertRow(row)
        edit = QLineEdit(expression)
        edit.setPlaceholderText("w*x*(L-x)/2")
        edit.setCompleter(self._completer(edit))
        self.curves.setCellWidget(row, 0, edit)
        self.curves.setCellWidget(row, 1, QLineEdit(label))
        self.curves.setCurrentCell(row, 0)
        edit.setFocus()

    def _remove_row(self) -> None:
        row = self.curves.currentRow()
        if row >= 0 and self.curves.rowCount() > 1:
            self.curves.removeRow(row)

    def apply(self) -> None:
        from ..items.plotitem import Series

        series = []
        for row in range(self.curves.rowCount()):
            expression = self.curves.cellWidget(row, 0).text().strip()
            if not expression:
                continue
            series.append(Series(expression,
                                 self.curves.cellWidget(row, 1).text().strip()))
        item = self.item
        item.series = series or [Series()]
        item.variable = self.variable.text().strip() or "x"
        item.x_from = self.x_from.text().strip() or "0"
        item.x_to = self.x_to.text().strip() or "10"
        item.title = self.title.text()
        item.x_label = self.x_label.text()
        item.y_label = self.y_label.text()
        item.x_unit = self.x_unit.currentText().strip()
        item.y_unit = self.y_unit.currentText().strip()
        item.show_grid = self.grid.isChecked()
        item.show_legend = self.legend.isChecked()
        item.show_markers = self.markers.isChecked()


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
        self.tabs = tabs

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

    def show_tab(self, name: str) -> None:
        """Open on a named tab, so a menu entry can go straight to it."""
        for index in range(self.tabs.count()):
            if name.lower() in self.tabs.tabText(index).replace("&", "").lower():
                self.tabs.setCurrentIndex(index)
                return

    def _show_logo_name(self) -> None:
        self.logo_name.setText(os.path.basename(getattr(self, "_logo_path", ""))
                               or ("in the document" if self.logo_key else "none"))

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
        if self.logo_data is not None:
            suffix = os.path.splitext(getattr(self, "_logo_path", ""))[1].lstrip(".")
            settings.logo_key = document.add_asset(self.logo_data, suffix or "png")
        else:
            settings.logo_key = self.logo_key
        settings.logo_slot = self.logo_slot.currentData()
        settings.logo_height_mm = self.logo_height.value()
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


class RectangleSizeDialog(QDialog):
    """Type an exact real-world width and height for a box or an ellipse."""

    def __init__(self, width_text: str, height_text: str, unit: str, parent=None,
                 scaled: bool = True):
        super().__init__(parent)
        self.setWindowTitle("Rectangle size")
        layout = QVBoxLayout(self)
        if scaled:
            message = ("This page has a scale, so the rectangle can be set out at an "
                       "exact size. Leave these as they are to keep what you drew.")
        else:
            message = ("This page has no scale, so these are paper sizes. Give the "
                       "page a scale to set the rectangle out in real dimensions.")
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
    """Move or copy the selection by an exact offset, any number of times."""

    def __init__(self, unit: str, scaled: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Move or duplicate by an offset")
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
        self.dx = QLineEdit(f"1 {unit}")
        self.dy = QLineEdit("0")
        form.addRow("Across (x)", self.dx)
        form.addRow("Down (y)", self.dy)
        self.count = QSpinBox()
        self.count.setRange(1, 500)
        self.count.setValue(1)
        form.addRow("Times", self.count)
        layout.addLayout(form)

        self.duplicate = QRadioButton("Duplicate — leave the original in place")
        self.move = QRadioButton("Move — no copies")
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
    character with no Ctrl or Alt — ``m``, ``"`` — is stored as that character,
    because those act when they are typed straight onto the page. Anything with
    a modifier is stored as a key sequence, which works from the menu bar as
    well. Backspace clears the row; Escape puts back what was there.
    """

    changed = Signal()

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._original = text
        self.setReadOnly(True)             # every key is captured, not typed
        self.setPlaceholderText("press a key")
        self.setClearButtonEnabled(False)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta,
                   Qt.Key_AltGr, Qt.Key_unknown):
            return
        modifiers = event.modifiers()
        if key == Qt.Key_Escape and not modifiers:
            self.setText(self._original)
            self.changed.emit()
            return
        if key in (Qt.Key_Backspace, Qt.Key_Delete) and not modifiers:
            self.setText("")
            self.changed.emit()
            return
        if key == Qt.Key_Tab and not modifiers:
            super().keyPressEvent(event)   # let the focus move on
            return
        chord = modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)
        text = event.text()
        if text and text.isprintable() and not chord:
            self.setText(text)
        else:
            sequence = QKeySequence(QKeyCombination(modifiers, Qt.Key(key)))
            self.setText(sequence.toString(QKeySequence.PortableText))
        self.changed.emit()

    def focusInEvent(self, event) -> None:
        self._original = self.text()
        super().focusInEvent(event)


class ShortcutManagerDialog(QDialog):
    """Change any binding by pressing the keys for it."""

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keyboard shortcuts")
        self.manager = manager
        self.resize(620, 640)
        outer = QVBoxLayout(self)
        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)
        keys = QWidget()
        self.tabs.addTab(keys, "Shortcuts")
        self.tabs.addTab(_GesturesSheet(), "Mouse and canvas")
        layout = QVBoxLayout(keys)

        note = QLabel(
            "Click a shortcut and <b>press the keys you want</b>. "
            "A single character — <b>m</b>, <b>\"</b>, <b>\\</b> — acts when you type it "
            "straight onto the page; anything with Ctrl or Alt works from the menus too. "
            "Backspace clears one, Escape puts it back.<br>"
            "Tool keys are deliberately silent while you are typing into a "
            "calculation, a text box or a table. Maths symbols are the other way "
            "round: they type themselves in wherever the cursor is.")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter…")
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self._apply_filter)
        layout.addWidget(self.filter)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Group", "Command", "Shortcut", "Default"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table, 1)

        self.editors: dict[str, ShortcutEdit] = {}
        self.rows: dict[str, int] = {}
        for binding in manager.bindings():
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.rows[binding.action_id] = row
            group = QTableWidgetItem(binding.category)
            group.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 0, group)
            label = QTableWidgetItem(binding.label)
            label.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 1, label)
            editor = ShortcutEdit(manager.sequence(binding.action_id))
            editor.changed.connect(self._check)
            self.table.setCellWidget(row, 2, editor)
            self.editors[binding.action_id] = editor
            default = QTableWidgetItem(binding.default or "—")
            default.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 3, default)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        self.warning = QLabel("")
        self.warning.setWordWrap(True)
        layout.addWidget(self.warning)

        buttons = QHBoxLayout()
        clear_row = QPushButton("Clear")
        clear_row.clicked.connect(lambda: self._set_current(""))
        reset_row = QPushButton("Reset this one")
        reset_row.clicked.connect(self._reset_row)
        reset_all = QPushButton("Reset all")
        reset_all.clicked.connect(self._reset_all)
        for button in (clear_row, reset_row, reset_all):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        outer.addWidget(_buttons(self))
        self._check()

    # -- helpers -----------------------------------------------------------
    def _current_binding(self):
        row = self.table.currentRow()
        bindings = self.manager.bindings()
        return bindings[row] if 0 <= row < len(bindings) else None

    def _set_current(self, text: str) -> None:
        binding = self._current_binding()
        if binding is not None:
            self.editors[binding.action_id].setText(text)
            self._check()

    def _reset_row(self) -> None:
        binding = self._current_binding()
        if binding is not None:
            self._set_current(binding.default)

    def _reset_all(self) -> None:
        for binding in self.manager.bindings():
            self.editors[binding.action_id].setText(binding.default)
        self._check()

    def _apply_filter(self, needle: str) -> None:
        needle = needle.strip().lower()
        for binding in self.manager.bindings():
            row = self.rows[binding.action_id]
            haystack = f"{binding.category} {binding.label} " \
                       f"{self.editors[binding.action_id].text()}".lower()
            self.table.setRowHidden(row, bool(needle) and needle not in haystack)

    def assignments(self) -> dict[str, str]:
        return {binding.action_id: self.editors[binding.action_id].text().strip()
                for binding in self.manager.bindings()}

    def _check(self) -> None:
        """Flag anything bound twice, on the rows themselves and in a line."""
        seen: dict[str, list] = {}
        for binding in self.manager.bindings():
            text = self.editors[binding.action_id].text().strip()
            if text:
                seen.setdefault(text.lower(), []).append(binding)
        clashes = []
        for text, bindings in seen.items():
            clash = len(bindings) > 1
            if clash:
                clashes.append(f"{bindings[0].label} and "
                               f"{', '.join(b.label for b in bindings[1:])} "
                               f"are both on {text}")
            for binding in bindings:
                editor = self.editors[binding.action_id]
                editor.setStyleSheet("border: 1px solid #c0392b;" if clash else "")
        for binding in self.manager.bindings():
            if not self.editors[binding.action_id].text().strip():
                self.editors[binding.action_id].setStyleSheet("")
        self.warning.setText("⚠ " + "; ".join(clashes) if clashes else "")
        self.warning.setStyleSheet("color:#b3261e;" if clashes else "")

    def clashes(self) -> list[str]:
        """Keys bound to more than one thing."""
        seen: dict[str, list[str]] = {}
        for action_id, text in self.assignments().items():
            if text:
                seen.setdefault(text.lower(), []).append(action_id)
        return [key for key, ids in seen.items() if len(ids) > 1]

    def accept(self) -> None:
        """Refuse to save a key that would mean two different things."""
        clashes = self.clashes()
        if clashes:
            QMessageBox.warning(
                self, "Keyboard shortcuts",
                "These keys are each bound to more than one thing:\n\n  "
                + "\n  ".join(sorted(clashes))
                + "\n\nClear one of them, or give it a different key.")
            return
        super().accept()

    def apply(self) -> None:
        for action_id, text in self.assignments().items():
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


class _GesturesSheet(QWidget):
    """The things the mouse and the canvas do, which are not rebindable.

    It lives inside the shortcut manager rather than in a dialog of its own:
    two menu entries both called "Keyboard shortcuts" only ever made people
    open the wrong one.
    """

    ROWS = [
        ("Typing on the page", ""),
        ("\"", "Start a text region where the cursor is"),
        ("/", "Start a calculation where the cursor is"),
        ("|", "Start a table here"),
        ("@", "Start a callout here"),
        ("any other key", "Nothing, unless it is bound on the Shortcuts tab"),
        ("Canvas", ""),
        ("Ctrl + wheel", "Zoom"),
        ("Space + drag", "Pan"),
        ("Shift + drag", "Hold a line to 0°, 45° or 90°; square off a box"),
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
        self.setWindowTitle("Tools on the toolbar")
        self.resize(420, 560)
        layout = QVBoxLayout(self)
        note = QLabel("Tick the tools you want on the toolbar. Everything stays "
                      "available from the Insert and Markup menus and from its "
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
