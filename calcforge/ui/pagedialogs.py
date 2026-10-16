"""Revu's page dialogs (Document menu and the Thumbnails menu): Insert Blank
Page, Insert Pages, Extract Pages, Split Document, Delete Pages, Crop Pages
and Apply to Pages (the user, 2026-10-16: "Page scale pop up, insert page pop
up, all popups should look nice and follow the same Bluebeam style and
wording").

They are laid out as Set Scale and Flatten Markups are: a grid of
"Label:" rows, the shared Pages control (widgets.PagesRange) where Revu has
one, and the verb (or OK) with Cancel at the bottom right. Each is built,
filled and read without being shown, so the window's commands — and the
tests — set its fields and call the accept path directly.
"""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog,
                               QDoubleSpinBox, QFileDialog, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QRadioButton, QSpinBox, QVBoxLayout, QWidget)

from ..core.document import LANDSCAPE, PAGE_SIZES, PORTRAIT, PageSetup
from ..io import pdfio
from .widgets import PagesRange, page_ranges

#: As wide as Set Scale, so the page dialogs read as one family.
DIALOG_WIDTH = 492
SAME_AS_CURRENT = "Same as Current"
CUSTOM = "Custom"


def form_grid(layout: QVBoxLayout) -> QGridLayout:
    """Set Scale's grid: labels on the left with a colon, fields stretched."""
    grid = QGridLayout()
    grid.setHorizontalSpacing(10)
    grid.setVerticalSpacing(8)
    grid.setColumnStretch(1, 1)
    layout.addLayout(grid)
    return grid


def button_row(dialog: QDialog, layout: QVBoxLayout, verb: str = "OK",
               slot=None, name: str = "") -> QPushButton:
    """The verb (default) and Cancel, at the bottom right, as Set Scale has."""
    buttons = QHBoxLayout()
    buttons.addStretch(1)
    go = QPushButton(verb)
    go.setObjectName(name or "dialogGo")
    go.setDefault(True)
    go.clicked.connect(slot or dialog.accept)
    cancel = QPushButton("Cancel")
    cancel.clicked.connect(dialog.reject)
    buttons.addWidget(go)
    buttons.addWidget(cancel)
    layout.addSpacing(4)
    layout.addLayout(buttons)
    dialog.go_button = go
    return go


def _row(*widgets, stretch_last: bool = False) -> QWidget:
    holder = QWidget()
    row = QHBoxLayout(holder)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(8)
    for widget in widgets:
        if isinstance(widget, str):
            row.addWidget(QLabel(widget))
        else:
            row.addWidget(widget)
    if not stretch_last:
        row.addStretch(1)
    return holder


def quiet(label: QLabel) -> QLabel:
    """A note in the theme's faint text colour (its placeholder colour), so it
    reads in light and dark alike."""
    from PySide6.QtGui import QPalette
    palette = label.palette()
    palette.setColor(QPalette.WindowText, palette.color(QPalette.PlaceholderText))
    label.setPalette(palette)
    return label


def _mm_spin(value: float, low: float = 20.0, high: float = 5000.0) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(low, high)
    spin.setDecimals(1)
    spin.setSuffix(" mm")
    spin.setValue(value)
    spin.setMinimumWidth(96)
    return spin


class Placement(QWidget):
    """Revu's placement: Before or After, then First Page, Last Page or
    Page [n]."""

    BEFORE, AFTER = "before", "after"
    FIRST, LAST, PAGE = "first", "last", "page"

    def __init__(self, count: int, page: int = 0, after: bool = True,
                 where: str = PAGE, parent=None):
        super().__init__(parent)
        self.total = max(int(count), 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.side = QComboBox()
        self.side.setObjectName("placementSide")
        self.side.addItem("Before", self.BEFORE)
        self.side.addItem("After", self.AFTER)
        self.side.setCurrentIndex(1 if after else 0)
        self.side.setMinimumContentsLength(7)
        self.first = QRadioButton("First Page")
        self.last = QRadioButton("Last Page")
        self.page = QRadioButton("Page:")
        self.number = QSpinBox()
        self.number.setObjectName("placementPage")
        self.number.setRange(1, self.total)
        self.number.setValue(min(max(int(page), 0), self.total - 1) + 1)
        self.number.setSuffix(f" of {self.total}")
        self.number.setMinimumWidth(80)
        self.group = QButtonGroup(self)
        for button in (self.first, self.last, self.page):
            self.group.addButton(button)
        layout.addWidget(_row(self.side))
        layout.addWidget(_row(self.first, self.last, self.page, self.number))
        self.number.valueChanged.connect(lambda _v: self.page.setChecked(True))
        self.choose(where)

    def choose(self, where: str, side: Optional[str] = None, page: Optional[int] = None):
        {self.FIRST: self.first, self.LAST: self.last}.get(where, self.page).setChecked(True)
        if side is not None:
            self.side.setCurrentIndex(self.side.findData(side))
        if page is not None:
            was = self.number.blockSignals(True)
            self.number.setValue(page + 1)
            self.number.blockSignals(was)

    def where(self) -> str:
        if self.first.isChecked():
            return self.FIRST
        if self.last.isChecked():
            return self.LAST
        return self.PAGE

    def target(self) -> int:
        """Where the new pages go, as the index the first of them takes."""
        anchor = {self.FIRST: 0, self.LAST: self.total - 1}.get(
            self.where(), self.number.value() - 1)
        return anchor + (1 if self.side.currentData() == self.AFTER else 0)


def _add_placement(grid: QGridLayout, row: int, placement: Placement) -> int:
    label = QLabel("Placement:")
    grid.addWidget(label, row, 0, Qt.AlignTop | Qt.AlignLeft)
    label.setContentsMargins(0, 4, 0, 0)
    grid.addWidget(placement, row, 1)
    return row + 1


def _add_pages(grid: QGridLayout, row: int, pages: PagesRange) -> int:
    grid.addWidget(QLabel("Pages:"), row, 0)
    grid.addWidget(pages, row, 1)
    return row + 1


class InsertBlankPageDialog(QDialog):
    """Revu's Insert Blank Page: Size (Same as Current, the paper sizes or
    Custom), Width and Height, Portrait or Landscape, Page Count, and the
    placement — Before or After the First Page, the Last Page or Page [n].
    The pages go in in one undo step."""

    def __init__(self, setup: PageSetup, parent=None, *, count: int = 1, page: int = 0,
                 after: bool = True):
        super().__init__(parent)
        self.setWindowTitle("Insert Blank Page")
        self.setMinimumWidth(DIALOG_WIDTH)
        self.current = PageSetup.from_dict(setup.to_dict())
        layout = QVBoxLayout(self)
        grid = form_grid(layout)
        row = 0
        self.paper = QComboBox()
        self.paper.setObjectName("blankSize")
        self.paper.addItems([SAME_AS_CURRENT] + list(PAGE_SIZES) + [CUSTOM])
        grid.addWidget(QLabel("Size:"), row, 0)
        grid.addWidget(self.paper, row, 1)
        row += 1
        self.width_box = _mm_spin(setup.width_mm)
        self.height_box = _mm_spin(setup.height_mm)
        grid.addWidget(QLabel("Width:"), row, 0)
        grid.addWidget(_row(self.width_box, "Height:", self.height_box), row, 1)
        row += 1
        self.portrait = QRadioButton("Portrait")
        self.landscape = QRadioButton("Landscape")
        self.orientation_group = QButtonGroup(self)
        self.orientation_group.addButton(self.portrait)
        self.orientation_group.addButton(self.landscape)
        (self.landscape if setup.orientation == LANDSCAPE else self.portrait).setChecked(True)
        grid.addWidget(QLabel("Orientation:"), row, 0)
        grid.addWidget(_row(self.portrait, self.landscape), row, 1)
        row += 1
        self.page_count = QSpinBox()
        self.page_count.setObjectName("blankCount")
        self.page_count.setRange(1, 500)
        self.page_count.setValue(1)
        self.page_count.setMinimumWidth(80)
        grid.addWidget(QLabel("Page Count:"), row, 0)
        grid.addWidget(self.page_count, row, 1, Qt.AlignLeft)
        row += 1
        self.placement = Placement(count, page, after)
        _add_placement(grid, row, self.placement)
        self.paper.currentTextChanged.connect(self._size_changed)
        self.width_box.valueChanged.connect(self._typed)
        self.height_box.valueChanged.connect(self._typed)
        self._filling = False
        self._size_changed(self.paper.currentText())
        button_row(self, layout, "OK", name="blankGo")

    def _size_changed(self, name: str) -> None:
        self._filling = True
        if name == SAME_AS_CURRENT:
            width, height = self.current.width_mm, self.current.height_mm
        else:
            width, height = PAGE_SIZES.get(name, (self.width_box.value(), self.height_box.value()))
        self.width_box.setValue(width)
        self.height_box.setValue(height)
        self._filling = False

    def _typed(self, _value: float) -> None:
        """A width or height typed in is a Custom size."""
        if self._filling or self.paper.currentText() == CUSTOM:
            return
        was = self.paper.blockSignals(True)
        self.paper.setCurrentText(CUSTOM)
        self.paper.blockSignals(was)

    def orientation(self) -> str:
        return LANDSCAPE if self.landscape.isChecked() else PORTRAIT

    def chosen_setup(self, current: Optional[PageSetup] = None) -> PageSetup:
        setup = PageSetup.from_dict((current or self.current).to_dict())
        name = self.paper.currentText()
        if name != SAME_AS_CURRENT:
            setup.size_name = name
            setup.width_mm, setup.height_mm = self.width_box.value(), self.height_box.value()
        setup.orientation = self.orientation()
        return setup

    def target(self) -> int:
        return self.placement.target()


class InsertPagesDialog(QDialog):
    """Revu's Insert Pages, for one file: the file and Browse…, which of its
    Pages ("All" or "1-3, 5"), CalcForge's Page Size, and the placement —
    Before or After the First Page, the Last Page or Page [n] — with a look
    at the first page coming in."""

    def __init__(self, parent=None, current_setup: Optional[PageSetup] = None, *,
                 count: int = 1, page: int = 0, after: bool = True):
        super().__init__(parent)
        self.setWindowTitle("Insert Pages")
        self.setMinimumWidth(DIALOG_WIDTH)
        self.path = ""
        self._count = 0
        layout = QVBoxLayout(self)
        grid = form_grid(layout)
        row = 0
        self.file = QLineEdit()
        self.file.setObjectName("insertFile")
        self.file.setPlaceholderText("Choose a PDF file…")
        self.file.setReadOnly(True)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.browse)
        grid.addWidget(QLabel("File:"), row, 0)
        grid.addWidget(_row(self.file, browse, stretch_last=True), row, 1)
        row += 1
        self.pages = QLineEdit("All")
        self.pages.setObjectName("insertPages")
        self.pages.setPlaceholderText("All, or 1-3, 5")
        self.pages.setToolTip("The file's pages to insert: All, or pages and ranges "
                              "such as 1-3, 5")
        grid.addWidget(QLabel("Pages:"), row, 0)
        grid.addWidget(self.pages, row, 1)
        row += 1
        # No resolution is asked about, because there is none to choose: an
        # inserted page is drawn from the file at whatever size it is being
        # looked at. The only question left is one about this document, which
        # is what size of page the imported ones should be.
        self.fit = QComboBox()
        self.fit.setObjectName("insertPageSize")
        self.fit.addItem("Keep the PDF's Own Page Size", pdfio.FIT_ORIGINAL)
        self.fit.addItem("Fit to A4", pdfio.FIT_A4)
        self.fit.addItem("Fit to This Document's Page Size", pdfio.FIT_CURRENT)
        grid.addWidget(QLabel("Page Size:"), row, 0)
        grid.addWidget(self.fit, row, 1)
        row += 1
        self.placement = Placement(count, page, after)
        _add_placement(grid, row, self.placement)

        self.info = QLabel("")
        quiet(self.info)
        self.info.hide()                      # until a file is chosen
        layout.addWidget(self.info)
        # A look at what is actually coming in. A drawing that renders blank is
        # obvious here rather than after it has been inserted.
        self.preview = QLabel("Choose a PDF to see the first page it will bring in")
        self.preview.setObjectName("insertPreview")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setWordWrap(True)
        self.preview.setMinimumHeight(200)
        self.preview.setStyleSheet(
            "QLabel#insertPreview { border:1px solid palette(mid); background: palette(base); }")
        layout.addWidget(self.preview, 1)
        self.pages.textChanged.connect(lambda _: self.show_preview())
        button_row(self, layout, "OK", self.insert, name="insertGo")

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
        path, _ = QFileDialog.getOpenFileName(self, "Insert Pages", "",
                                              "PDF files (*.pdf);;All files (*)")
        if path:
            self.set_path(path)

    def set_path(self, path: str) -> bool:
        try:
            self._count = pdfio.page_count(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Insert Pages", str(exc))
            return False
        self.path = path
        self.file.setText(path)
        self.info.setText(f"{os.path.basename(path)} — {self._count} page"
                          f"{'s' if self._count != 1 else ''}")
        self.info.show()
        self.show_preview()
        return True

    def insert(self) -> None:
        if not self.path:
            QMessageBox.warning(self, "Insert Pages", "Choose a PDF file to insert.")
            return
        if not pdfio.parse_page_range(self.pages.text(), self._count):
            QMessageBox.warning(self, "Insert Pages",
                                f"Enter pages to insert, such as 1-3, 5 (the file has "
                                f"{self._count}).")
            return
        self.accept()

    def selection(self) -> tuple[str, list[int], str, float, bool]:
        indices = pdfio.parse_page_range(self.pages.text(), self._count)
        # The last of these says whether to make markups out of the page's own
        # line work. It is off: a page comes in as the page, and turning a
        # drawing into thousands of editable lines is a thing to ask for, not
        # a thing to have happen.
        return (self.path, indices, self.fit.currentData(), pdfio.BEST_DPI, False)

    def target(self) -> int:
        return self.placement.target()


class ExtractPagesDialog(QDialog):
    """Revu's Extract Pages: the Pages, then Options — Delete Pages After
    Extracting, Extract Pages as Separate Files (with Use Page Label to Name
    Files) and Open Files After Extraction. The save dialog follows."""

    def __init__(self, count: int, current: int = 0, selected=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Extract Pages")
        self.setMinimumWidth(DIALOG_WIDTH)
        self.total = max(int(count), 1)
        layout = QVBoxLayout(self)
        grid = form_grid(layout)
        self.pages = PagesRange(count, current, selected,
                                default=PagesRange.SELECTED if selected else PagesRange.CURRENT)
        _add_pages(grid, 0, self.pages)
        options = QGroupBox("Options")
        column = QVBoxLayout(options)
        column.setSpacing(6)
        self.delete_after = QCheckBox("Delete Pages After Extracting")
        self.delete_after.setObjectName("extractDelete")
        self.delete_after.setToolTip("Take the extracted pages out of this document "
                                     "(one undo step)")
        self.separate = QCheckBox("Extract Pages as Separate Files")
        self.separate.setObjectName("extractSeparate")
        self.separate.setToolTip("One PDF for each page, numbered after the name you give")
        self.use_labels = QCheckBox("Use Page Label to Name Files")
        self.use_labels.setObjectName("extractLabels")
        self.use_labels.setToolTip("Name each file after its page's label instead of "
                                   "its number")
        self.use_labels.setEnabled(False)
        self.separate.toggled.connect(self.use_labels.setEnabled)
        self.open_after = QCheckBox("Open Files After Extraction")
        self.open_after.setObjectName("extractOpen")
        self.open_after.setToolTip("Open what was extracted, each in a tab of its own")
        labelled = QHBoxLayout()
        labelled.setContentsMargins(20, 0, 0, 0)
        labelled.addWidget(self.use_labels)
        for box in (self.delete_after, self.separate):
            column.addWidget(box)
        column.addLayout(labelled)
        column.addWidget(self.open_after)
        layout.addWidget(options)
        button_row(self, layout, "OK", self.extract, name="extractGo")

    def extract(self) -> None:
        if not self.page_indexes():
            QMessageBox.warning(self, "Extract Pages",
                                "Enter pages to extract, such as 1-3, 5.")
            return
        self.accept()

    def page_indexes(self) -> Optional[list]:
        return self.pages.page_indexes()


class SplitDocumentDialog(QDialog):
    """Revu's Split Document, by Page Count: so many pages to a file, into a
    Folder, each named after the document with a File Name Suffix and its
    number ("plan part 1.pdf")."""

    def __init__(self, count: int, folder: str = "", stem: str = "document", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Split Document")
        self.setMinimumWidth(DIALOG_WIDTH)
        self.total = max(int(count), 1)
        self.stem = stem
        layout = QVBoxLayout(self)
        grid = form_grid(layout)
        row = 0
        self.page_count = QSpinBox()
        self.page_count.setObjectName("splitCount")
        self.page_count.setRange(1, self.total)
        self.page_count.setValue(1)
        self.page_count.setMinimumWidth(80)
        self.by_count = QRadioButton("Page Count:")
        self.by_count.setChecked(True)
        self.by_count.setToolTip("Each file holds this many pages; the last holds "
                                 "what is left")
        grid.addWidget(QLabel("Split By:"), row, 0)
        grid.addWidget(_row(self.by_count, self.page_count), row, 1)
        row += 1
        self.folder = QLineEdit(folder)
        self.folder.setObjectName("splitFolder")
        self.folder.setPlaceholderText("The folder the files go in")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.browse)
        grid.addWidget(QLabel("Folder:"), row, 0)
        grid.addWidget(_row(self.folder, browse, stretch_last=True), row, 1)
        row += 1
        self.suffix = QLineEdit("part")
        self.suffix.setObjectName("splitSuffix")
        self.suffix.setToolTip("Added after the document's name, before each file's number")
        grid.addWidget(QLabel("File Name Suffix:"), row, 0)
        grid.addWidget(self.suffix, row, 1)
        row += 1
        self.example = QLabel("")
        self.example.setObjectName("splitExample")
        quiet(self.example)
        grid.addWidget(self.example, row, 1)
        self.page_count.valueChanged.connect(self._say)
        self.suffix.textChanged.connect(self._say)
        self._say()
        button_row(self, layout, "OK", self.split, name="splitGo")

    def file_name(self, number: int) -> str:
        suffix = self.suffix.text().strip()
        return f"{self.stem} {suffix} {number}.pdf" if suffix else f"{self.stem} {number}.pdf"

    def files(self) -> int:
        every = self.page_count.value()
        return (self.total + every - 1) // every

    def _say(self, *_args) -> None:
        many = self.files()
        names = self.file_name(1) + (f" … {self.file_name(many)}" if many > 1 else "")
        self.example.setText(f"{many} file{'s' if many != 1 else ''}: {names}")

    def browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Split Document", self.folder.text())
        if folder:
            self.folder.setText(folder)

    def split(self) -> None:
        folder = self.folder.text().strip()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, "Split Document", "Choose a folder for the files.")
            return
        self.accept()


class DeletePagesDialog(QDialog):
    """Revu's Delete Pages: the Pages to take out. Every page cannot go — a
    document keeps at least one."""

    def __init__(self, count: int, current: int = 0, selected=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Delete Pages")
        self.setMinimumWidth(DIALOG_WIDTH)
        self.total = max(int(count), 1)
        layout = QVBoxLayout(self)
        grid = form_grid(layout)
        self.pages = PagesRange(count, current, selected,
                                default=PagesRange.SELECTED if selected else PagesRange.CURRENT)
        _add_pages(grid, 0, self.pages)
        self.note = QLabel("")
        self.note.setObjectName("deleteNote")
        quiet(self.note)
        grid.addWidget(self.note, 1, 1)
        self.pages.combo.currentIndexChanged.connect(self._say)
        self.pages.range.textChanged.connect(self._say)
        self._say()
        button_row(self, layout, "OK", self.delete, name="deleteGo")

    def _say(self, *_args) -> None:
        chosen = self.page_indexes() or []
        if not chosen:
            self.note.setText("")
        elif len(chosen) >= self.total:
            self.note.setText("A document needs at least one page")
        else:
            self.note.setText(f"{len(chosen)} of {self.total} page"
                              f"{'s' if self.total != 1 else ''} will be deleted")

    def problem(self) -> str:
        """Why these pages cannot be deleted, or "" when they can."""
        chosen = self.page_indexes()
        if not chosen:
            return "Enter pages to delete, such as 1-3, 5."
        if len(chosen) >= self.total:
            return ("A document needs at least one page, so every page cannot be "
                    "deleted. Choose fewer pages.")
        return ""

    def delete(self) -> None:
        problem = self.problem()
        if problem:
            QMessageBox.warning(self, "Delete Pages", problem)
            return
        self.accept()

    def page_indexes(self) -> Optional[list]:
        return self.pages.page_indexes()


class CropPagesDialog(QDialog):
    """Revu's Crop Pages: Top, Bottom, Left and Right margins cut off each
    page; Set Proportional keeps all four equal; Get Window drags the part of
    the page to keep (the Crop tool) and comes back here with its margins; the
    Pages they apply to."""

    PICK = QDialog.Accepted + 11        # Get Window: "let me drag it instead"
    SIDES = (("top", "Top:"), ("bottom", "Bottom:"), ("left", "Left:"), ("right", "Right:"))

    def __init__(self, count: int, current: int = 0, selected=None, parent=None,
                 state: Optional[dict] = None):
        super().__init__(parent)
        self.setWindowTitle("Crop Pages")
        self.setMinimumWidth(DIALOG_WIDTH)
        layout = QVBoxLayout(self)
        margins = QGroupBox("Margins")
        boxes = QGridLayout(margins)
        boxes.setHorizontalSpacing(10)
        boxes.setVerticalSpacing(8)
        self.margins = {}
        for place, (side, label) in enumerate(self.SIDES):
            spin = _mm_spin(0.0, 0.0, 5000.0)
            spin.setObjectName(f"crop_{side}")
            spin.valueChanged.connect(lambda value, s=side: self._changed(s, value))
            boxes.addWidget(QLabel(label), place // 2, (place % 2) * 2)
            boxes.addWidget(spin, place // 2, (place % 2) * 2 + 1)
            self.margins[side] = spin
        boxes.setColumnStretch(1, 1)
        boxes.setColumnStretch(3, 1)
        self.proportional = QCheckBox("Set Proportional")
        self.proportional.setObjectName("cropProportional")
        self.proportional.setToolTip("The same margin on all four sides")
        self.get_window = QPushButton("Get Window")
        self.get_window.setObjectName("cropGetWindow")
        self.get_window.setToolTip("Drag the part of the page to keep; its margins "
                                   "come back here")
        self.get_window.clicked.connect(lambda: self.done(self.PICK))
        boxes.addWidget(self.proportional, 2, 0, 1, 2)
        boxes.addWidget(self.get_window, 2, 2, 1, 2, Qt.AlignRight)
        layout.addWidget(margins)
        grid = form_grid(layout)
        self.pages = PagesRange(count, current, selected,
                                default=PagesRange.SELECTED if selected else PagesRange.CURRENT)
        _add_pages(grid, 0, self.pages)
        self._following = False
        if state:
            self.restore(state)
        button_row(self, layout, "OK", self.crop, name="cropGo")

    def _changed(self, side: str, value: float) -> None:
        if self._following or not self.proportional.isChecked():
            return
        self._following = True
        for other, spin in self.margins.items():
            if other != side:
                spin.setValue(value)
        self._following = False

    def set_margins_mm(self, top: float, bottom: float, left: float, right: float) -> None:
        self._following = True
        for side, value in (("top", top), ("bottom", bottom), ("left", left),
                            ("right", right)):
            self.margins[side].setValue(max(value, 0.0))
        self._following = False

    def margins_mm(self) -> dict:
        return {side: spin.value() for side, spin in self.margins.items()}

    def state(self) -> dict:
        return {"margins": self.margins_mm(), "proportional": self.proportional.isChecked(),
                "pages": self.pages.which(), "range": self.pages.range.text()}

    def restore(self, state: dict) -> None:
        self.proportional.setChecked(False)
        margins = state.get("margins", {})
        self.set_margins_mm(margins.get("top", 0.0), margins.get("bottom", 0.0),
                            margins.get("left", 0.0), margins.get("right", 0.0))
        self.proportional.setChecked(bool(state.get("proportional")))
        self.pages.choose(state.get("pages", PagesRange.CURRENT), state.get("range"))

    def crop(self) -> None:
        if not self.page_indexes():
            QMessageBox.warning(self, "Crop Pages", "Enter pages to crop, such as 1-3, 5.")
            return
        if not any(value > 0 for value in self.margins_mm().values()):
            QMessageBox.warning(self, "Crop Pages",
                                "Enter the margins to crop, or use Get Window to drag "
                                "the part of the page to keep.")
            return
        self.accept()

    def page_indexes(self) -> Optional[list]:
        return self.pages.page_indexes()


class ApplyToPagesDialog(QDialog):
    """Revu's Apply to Pages: a copy of the markup on All Pages, a Custom
    Range (filled from the pages picked in Thumbnails), the Even or Odd
    Pages, or the Landscape or Portrait ones. The page it is on already has
    it, so that one is left out."""

    ALL, CUSTOM, EVEN, ODD, LANDSCAPE, PORTRAIT = (
        "all", "custom", "even", "odd", "landscape", "portrait")

    def __init__(self, orientations, current: int = 0, selected=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Apply to Pages")
        self.setMinimumWidth(DIALOG_WIDTH)
        self.landscapes = [bool(on) for on in orientations]
        self.total = max(len(self.landscapes), 1)
        self.current = current
        layout = QVBoxLayout(self)
        grid = form_grid(layout)
        self.group = QButtonGroup(self)
        self.buttons = {}
        self.range = QLineEdit()
        self.range.setObjectName("applyRange")
        self.range.setPlaceholderText("1-3, 5")
        self.range.setToolTip("Pages and ranges, e.g. 1-3, 5, 9")
        self.range.textEdited.connect(lambda _t: self.choose(self.CUSTOM))
        rows = ((self.ALL, "All Pages"), (self.CUSTOM, "Custom Range:"),
                (self.EVEN, "Even Pages"), (self.ODD, "Odd Pages"),
                (self.LANDSCAPE, "Landscape Pages"), (self.PORTRAIT, "Portrait Pages"))
        grid.addWidget(QLabel("Pages:"), 0, 0, Qt.AlignTop)
        for row, (key, text) in enumerate(rows):
            button = QRadioButton(text)
            button.setObjectName(f"apply_{key}")
            self.group.addButton(button)
            self.buttons[key] = button
            if key == self.CUSTOM:
                grid.addWidget(_row(button, self.range, stretch_last=True), row, 1)
            else:
                grid.addWidget(button, row, 1)
        if selected:
            self.choose(self.CUSTOM, page_ranges(selected))
        else:
            self.choose(self.ALL)
        button_row(self, layout, "OK", self.apply, name="applyGo")

    def choose(self, which: str, text: Optional[str] = None) -> None:
        self.buttons[which].setChecked(True)
        if text is not None:
            self.range.setText(text)

    def which(self) -> str:
        return next((key for key, button in self.buttons.items() if button.isChecked()),
                    self.ALL)

    def page_indexes(self) -> Optional[list]:
        """The pages to copy it onto, from 0, without the one it is on; None
        when the Custom Range will not read."""
        which = self.which()
        every = range(self.total)
        if which == self.CUSTOM:
            from .colorprocess import parse_pages
            chosen = parse_pages(self.range.text(), self.total)
            if chosen is None:
                return None
        elif which == self.EVEN:
            chosen = [i for i in every if (i + 1) % 2 == 0]
        elif which == self.ODD:
            chosen = [i for i in every if (i + 1) % 2 == 1]
        elif which == self.LANDSCAPE:
            chosen = [i for i in every if self.landscapes[i]]
        elif which == self.PORTRAIT:
            chosen = [i for i in every if not self.landscapes[i]]
        else:
            chosen = list(every)
        return [i for i in chosen if i != self.current]

    def apply(self) -> None:
        chosen = self.page_indexes()
        if chosen is None:
            QMessageBox.warning(self, "Apply to Pages",
                                "Enter pages to apply it to, such as 1-3, 5.")
            return
        if not chosen:
            QMessageBox.warning(self, "Apply to Pages",
                                "None of those pages is another page to put it on.")
            return
        self.accept()
