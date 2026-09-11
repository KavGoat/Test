"""Modal dialogs: page setup, scale, PDF import, document properties and more."""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import QKeyCombination, Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox,
                               QDialog,
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

        self.apply_all = QCheckBox("All pages")
        self.apply_all.setToolTip("Apply to every page")
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
            self.known = QLineEdit()
            self.known.setPlaceholderText("5 m, 12 ft, 3600 mm…")
            form.addRow("It represents", self.known)
            layout.addWidget(box)
        else:
            self.known = QLineEdit()
            self.known.hide()
            pick = QPushButton("Calibrate…")
            pick.setToolTip("Pick two points on the drawing to calibrate its "
                            "scale: click one end of something you know the "
                            "length of, then the other, then type that length")
            pick.clicked.connect(lambda: self.done(self.PICK))
            layout.addWidget(pick)

        ratio_box = QGroupBox("Standard ratio")
        ratio_form = QFormLayout(ratio_box)
        self.ratio = QComboBox()
        self.ratio.setEditable(True)
        self.ratio.addItems(self.RATIOS)
        self.ratio.setCurrentText(scale.label if scale.label in self.RATIOS else "1:100")
        ratio_form.addRow("Ratio", self.ratio)
        layout.addWidget(ratio_box)

        units = QFormLayout()
        self.length_unit = UnitCombo(scale.display_unit)
        self.length_unit.setToolTip("Units used to display lengths")
        units.addRow("Length unit", self.length_unit)
        self.area_unit = UnitCombo(scale.area_unit)
        self.area_unit.setToolTip("Units used to display areas")
        units.addRow("Area unit", self.area_unit)
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


class CalibrationLengthDialog(QDialog):
    """Name the real length after two calibration points are picked."""

    def __init__(self, measured_pt: float, parent=None):
        super().__init__(parent)
        self.measured_pt = measured_pt
        self.setWindowTitle("Calibrate scale")
        layout = QVBoxLayout(self)
        note = QLabel(
            f"The picked line is {measured_pt:.1f} pt on the page. "
            "Enter the real length it represents.")
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.known = QLineEdit()
        self.known.setPlaceholderText("10 mm")
        form.addRow("Length", self.known)
        layout.addLayout(form)
        layout.addWidget(_buttons(self))

    def length_text(self) -> Optional[str]:
        text = self.known.text().strip()
        try:
            value = parse_unit(text)
            valid = value is not None and value.check("[length]")
        except Exception:  # noqa: BLE001 - invalid user-entered units
            valid = False
        if not valid:
            QMessageBox.warning(
                self, "Calibrate scale",
                "Enter a length with compatible units, such as 10 mm or 2 m.")
            return None
        return text


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

        # No resolution is asked about, because there is none to choose: an
        # inserted page is drawn from the file at whatever size it is being
        # looked at. The only question left is one about this document, which
        # is what size of page the imported ones should be.
        layout.addLayout(form)

        self.info = QLabel("")
        self.info.setStyleSheet("color:#5a6270;")
        layout.addWidget(self.info)

        # A look at what is actually coming in. A drawing that renders blank is
        # obvious here rather than after it has been inserted.
        self.preview = QLabel("Choose a PDF to see the first page it will bring in")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setWordWrap(True)
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

    def selection(self) -> tuple[str, list[int], str, float, bool]:
        indices = pdfio.parse_page_range(self.pages.text(), self._count)
        # The last of these says whether to make markups out of the page's own
        # line work. It is off: a page comes in as the page, and turning a
        # drawing into thousands of editable lines is a thing to ask for, not
        # a thing to have happen.
        return (self.path, indices, self.fit.currentData(), pdfio.BEST_DPI, False)


class RecolourDialog(QDialog):
    """Change the colours of a drawing that came in as a picture.

    Either one colour for another, or everything dark enough to be a line
    onto one colour — which is what turns a black sheet grey so markups can
    be read on top of it. The preview shows what will happen before it does.
    """

    def __init__(self, image, parent=None):
        super().__init__(parent)
        from ..io import recolour

        self.setWindowTitle("Change colours")
        self.image = image
        self.result_image = None
        self.resize(520, 520)
        layout = QVBoxLayout(self)

        self.lines_mode = QRadioButton("Line colour")
        self.lines_mode.setToolTip("Recolour the lines")
        self.lines_mode.setChecked(True)
        self.lines_mode.setToolTip(
            "Everything darker than the threshold takes the new colour, keeping "
            "how dark it was, so the drawing does not flatten out")
        layout.addWidget(self.lines_mode)

        lines = QFormLayout()
        self.line_colour = QPushButton("Choose…")
        self.line_target = QColor("#7a8290")
        self.line_colour.clicked.connect(lambda: self._pick("line_target",
                                                            self.line_colour))
        self._show_colour(self.line_colour, self.line_target)
        lines.addRow("New colour", self.line_colour)
        self.threshold = QSpinBox()
        self.threshold.setRange(16, 240)
        self.threshold.setValue(150)
        self.threshold.setToolTip("How dark a pixel has to be to count as a line")
        lines.addRow("Counts as a line below", self.threshold)
        layout.addLayout(lines)

        self.swap_mode = QRadioButton("Swap colour")
        self.swap_mode.setToolTip("Swap one colour for another")
        layout.addWidget(self.swap_mode)
        swap = QFormLayout()
        self.from_colour = QComboBox()
        for colour in recolour.common_colours(image):
            self.from_colour.addItem(_colour_chip(colour), colour.name(), colour)
        self.from_colour.setToolTip("The colours this sheet is mostly made of")
        swap.addRow("Change", self.from_colour)
        self.to_button = QPushButton("Choose…")
        self.to_target = QColor("#1971c2")
        self.to_button.clicked.connect(lambda: self._pick("to_target", self.to_button))
        self._show_colour(self.to_button, self.to_target)
        swap.addRow("To", self.to_button)
        self.tolerance = QSpinBox()
        self.tolerance.setRange(0, 200)
        self.tolerance.setValue(40)
        self.tolerance.setToolTip("How near a pixel has to be to count as that colour")
        swap.addRow("Tolerance", self.tolerance)
        layout.addLayout(swap)

        self.colourise_mode = QRadioButton("Colourise")
        self.colourise_mode.setToolTip(
            "Put the whole drawing onto the “To” colour, keeping its light "
            "and shade — Bluebeam's Colorize")
        layout.addWidget(self.colourise_mode)
        self.grey_mode = QRadioButton("Greyscale")
        self.grey_mode.setToolTip("Black and white")
        self.grey_mode.setToolTip("Convert the image to greyscale")
        layout.addWidget(self.grey_mode)
        self.transparent_mode = QRadioButton("Make transparent")
        self.transparent_mode.setToolTip(
            "Make the selected source colour transparent using the tolerance above")
        layout.addWidget(self.transparent_mode)

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(180)
        self.preview.setStyleSheet(
            "QLabel { border:1px solid palette(mid); background: palette(base); }")
        layout.addWidget(self.preview, 1)

        refresh = QPushButton("Preview")
        refresh.clicked.connect(self.refresh_preview)
        layout.addWidget(refresh)
        layout.addWidget(_buttons(self))
        self.refresh_preview()

    def _show_colour(self, button, colour: QColor) -> None:
        button.setIcon(_colour_chip(colour))
        button.setText(colour.name())

    def _pick(self, attribute: str, button) -> None:
        from PySide6.QtWidgets import QColorDialog
        chosen = QColorDialog.getColor(getattr(self, attribute), self, "Colour")
        if chosen.isValid():
            setattr(self, attribute, chosen)
            self._show_colour(button, chosen)
            self.refresh_preview()

    def apply_to_lines(self, items) -> int:
        """Do the same thing to real line work, so it does not fall behind.

        A page that came in from a PDF is a picture *and* the lines that drew
        it. Changing one and not the other leaves the lines their old colour
        on a recoloured sheet, which looks like the change half worked —
        because it did.
        """
        from ..io import recolour

        if self.grey_mode.isChecked():
            return recolour.colourise_lines(items, QColor("#666666"))
        if self.colourise_mode.isChecked():
            return recolour.colourise_lines(items, self.to_target)
        if self.lines_mode.isChecked():
            return recolour.colourise_lines(items, self.line_target)
        if self.transparent_mode.isChecked():
            return 0          # nothing to make transparent about a line
        source = self.from_colour.currentData() or QColor("#000000")
        return recolour.swap_line_colour(items, source, self.to_target,
                                         self.tolerance.value())

    def apply_to(self, image):
        """The recoloured version of *image*, however this dialog is set."""
        from ..io import recolour

        if self.lines_mode.isChecked():
            return recolour.recolour_lines(image, self.line_target,
                                           self.threshold.value())
        if self.colourise_mode.isChecked():
            return recolour.colourise(image, self.to_target)
        if self.grey_mode.isChecked():
            return recolour.to_greyscale(image)
        source = self.from_colour.currentData() or QColor("#000000")
        if self.transparent_mode.isChecked():
            return recolour.make_colour_transparent(
                image, source, self.tolerance.value())
        return recolour.swap_colour(image, source, self.to_target,
                                    self.tolerance.value())

    def refresh_preview(self) -> None:
        small = self.image.scaled(360, 360, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview.setPixmap(QPixmap.fromImage(self.apply_to(small)))


def _colour_chip(colour: QColor):
    """A small square of colour, for a button or a menu row."""
    pixmap = QPixmap(14, 14)
    pixmap.fill(colour)
    from PySide6.QtGui import QIcon
    return QIcon(pixmap)


class DocumentPropertiesDialog(QDialog):
    """Title block information, running headers and markup defaults."""

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Document properties")
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
        info_form.addRow("Title", self.title)
        info_form.addRow("Project", self.project)
        info_form.addRow("Author", self.author)
        info_form.addRow("Subject", self.subject)
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
        hint = QLabel("Fields: {title} {project} {author} {subject} {page} {pages} "
                      "{date} {time} {file}")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#5a6270;")
        running_form.addRow(hint)

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
        self.snap.setToolTip("Snap to grid")
        self.snap.setChecked(settings.snap_to_grid)
        self.grid_mm = QDoubleSpinBox()
        self.grid_mm.setRange(0.5, 100)
        self.grid_mm.setValue(settings.grid_mm)
        self.grid_mm.setSuffix(" mm")
        self.show_margins = QCheckBox("Margin guides")
        self.show_margins.setToolTip("Show margin guides")
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
    """Move or copy the selection at exact spacing, any number of times."""

    def __init__(self, unit: str, scaled: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Multiple")
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
            "markup. Symbols are the other way round: they type themselves in "
            "wherever the cursor is.")
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
        reset_row = QPushButton("Reset one")
        reset_row.setToolTip("Reset the selected shortcut")
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
        self.setWindowTitle("About MarkForge")
        layout = QVBoxLayout(self)
        title = QLabel("MarkForge")
        font = QFont()
        font.setPointSize(20)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)
        body = QLabel(
            "A PDF markup editor for drawings, page by page.\n\n"
            "• A full markup tool set with scaled measurement and takeoff\n"
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
    two menu entries both called "Keyboard shortcuts" only ever made people
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


class FlattenDialog(QDialog):
    """Choose the document content classes to make part of the page."""

    CLASSES = (("markups", "Markups"),
               ("text", "Text"),
               ("measurements", "Measurements"))

    def __init__(self, recoverable: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Flatten")
        layout = QVBoxLayout(self)
        note = QLabel(
            "Choose what to flatten on every page. Flatten Selection remains "
            "available for individual items.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.boxes = {}
        for key, label in self.CLASSES:
            box = QCheckBox(label)
            box.setChecked(key == "markups")
            self.boxes[key] = box
            layout.addWidget(box)
        recovery = QLabel(
            "Original item data will be retained and can be restored with Recover."
            if recoverable else
            "Recovery data is disabled in Preferences. This discards the chosen "
            "items' editable source when the file is saved.")
        recovery.setWordWrap(True)
        recovery.setStyleSheet("color:#6b7280;" if recoverable else "color:#b3261e;")
        layout.addWidget(recovery)
        layout.addWidget(_buttons(self))

    def chosen(self) -> set[str]:
        return {key for key, box in self.boxes.items() if box.isChecked()}


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
        self.recover_flattened = QCheckBox("Recoverable flattening")
        self.recover_flattened.setChecked(prefs.recover_flattened)
        self.recover_flattened.setToolTip(
            "Keep the original item data in the file so Markup > Recover can restore it.\n"
            "Turn this off only when deliberately producing an irreversible file.")
        form.addRow("", self.recover_flattened)
        layout.addWidget(canvas)

        writing = QGroupBox("Writing")
        form = QFormLayout(writing)
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

        layout.addStretch(1)
        layout.addWidget(_buttons(self))

    def result_preferences(self):
        from . import preferences as prefs_module

        return prefs_module.Preferences(
            wheel=self.wheel.currentData(),
            check_spelling=self.spelling.isChecked(),
            dictionary=self.dictionary.currentData(),
            snap_while_drawing=self.snapping.isChecked(),
            autosize_text=self.autosize.isChecked(),
            insertion_point=self.insertion.isChecked(),
            recover_flattened=self.recover_flattened.isChecked())
