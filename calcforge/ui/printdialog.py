"""Revu's Print dialog, with the preview folded in (the user, Round 3: "Build
Revu's Print dialog, with the preview folded in. Print Pages… opens it with
Selected chosen. The per-page and per-markup print ticks stay").

Laid out as the user's own Revu 21 shows it (docs/qa/revu_shots/
print_dialog.jpg, 2026-10-17), in its words:

* on the left, a group named after the document, the page's size in
  centimetres under its title, the page as it will print, and
  |◀ ◀ "1 (1 of 1)" ▶ ▶| under it;
* Printer — Name ▾ and Properties, Status, To File;
* Pages (n) — Page Range ▾ ("All Pages (1 - n)", Current, Selected, Custom,
  whose range box shows only for Custom) and Get Window;
* Options — Size ▾ and Auto; Portrait, Landscape; Print ("Document &
  Markup"); Copies, Collate, Reverse; Rotation ("Auto-Rotate 90"); Page
  Scaling; Scale; Centre with X and Y; Dim Page Content, Dim Filtered
  Markups, Print Spaces, Print Visible Hyperlinks, Print in Greyscale;
* Defaults ▾, Advanced and Add Files ▾ at the bottom left, Print and
  Cancel at the bottom right.

Print Spaces and Add Files are there, greyed, because Spaces and batch
printing were declined (docs/qa/revu_audit.md); their tooltips say so.

The preview is the print's own drawing of each page (io/printing.draw_page)
at a low resolution. The PDF part comes from the render processes' small
picture of the page (pdftiles), so only the markups are painted on the
window's thread; pictures are kept, so changing the scaling, rotation, paper
or position only re-lays the picture already made.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Optional

from PySide6.QtCore import QEvent, QObject, QPointF, QRect, QRectF, QSize, QSizeF, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QImage, QPainter, QPen, QTransform
from PySide6.QtWidgets import (QAbstractButton, QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog,
                               QDoubleSpinBox, QFileDialog, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton,
                               QRadioButton, QRubberBand, QSizePolicy, QSpinBox, QToolButton,
                               QVBoxLayout, QWidget)

from ..core.document import MM_TO_PT, PAGE_SIZES
from ..io import printing
from ..io.printing import AdvancedOptions, PrintOptions
from ..settings import app_settings
from .widgets import PagesRange

#: CalcForge's own printer: the print written to a PDF file. Always there,
#: so printing works on a machine with no printer installed.
PDF_PRINTER = "Print to PDF"
SETTINGS_KEY = "print/options"
DEFAULTS_KEY = "print/defaults"
PRINTER_KEY = "print/printer"
RANGE_KEY = "print/range"
ADVANCED_KEY = "print/advanced/"

#: How sharp the preview is drawn: about this many pixels down the longer
#: side of the page, whatever its size — enough for a crisp preview, little
#: enough to draw in a moment.
PREVIEW_PIXELS = 720
#: How long the dialog waits, idle, before drawing the pages either side of
#: the one shown, so a page about to be stepped to is ready but typing into
#: a field is never held up by a page nobody is looking at.
NEIGHBOUR_DELAY_MS = 150
#: How long a preview page waits for the render processes' picture of its
#: PDF before drawing it here instead.
BACKGROUND_PATIENCE_S = 1.5

DECLINED_SPACES = ("Print Spaces needs Revu's Spaces, which CalcForge does not have "
                   "(declined: see the Revu audit)")
DECLINED_BATCH = ("Add Files is Revu's batch printing, which CalcForge does not have "
                  "(declined: see the Revu audit)")
NO_DATA_TYPE = ("Print Data Type is a Windows print-spooler setting: CalcForge prints "
                "through Qt, which chooses the data type itself")

#: Every command id the dialog offers (bindable_list.COMMANDS has them all),
#: by the object name of its button
BUTTON_IDS = {
    "printerProperties": "print.properties",
    "printGetWindow": "print.get_window",
    "printAdvanced": "print.advanced",
    "printGo": "print.print",
    "printCancel": "print.cancel",
    "printFirst": "print.first_page",
    "printPrev": "print.previous_page",
    "printNext": "print.next_page",
    "printLast": "print.last_page",
}
MENU_IDS = ("print.restore_defaults", "print.save_as_default", "print.factory_defaults")


def _load(key: str) -> dict:
    raw = app_settings().value(key, "")
    try:
        data = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        data = {}
    return data if isinstance(data, dict) else {}


def remembered_options() -> PrintOptions:
    """The options of the last print, or the defaults."""
    data = _load(SETTINGS_KEY)
    return PrintOptions.from_dict(data) if data else saved_defaults()


def saved_defaults() -> PrintOptions:
    """Defaults ▾ Save as Default's options, or CalcForge's own."""
    return PrintOptions.from_dict(_load(DEFAULTS_KEY))


def remember_options(options: PrintOptions, printer: str, range_kind: str) -> None:
    settings = app_settings()
    settings.setValue(SETTINGS_KEY, json.dumps(options.to_dict()))
    settings.setValue(PRINTER_KEY, printer)
    if range_kind in (PagesRange.ALL, PagesRange.CURRENT):
        settings.setValue(RANGE_KEY, range_kind)
    settings.sync()


def advanced_for(printer: str) -> AdvancedOptions:
    """Revu keeps the Advanced settings "separately for each printer"."""
    return AdvancedOptions.from_dict(_load(ADVANCED_KEY + printer))


def remember_advanced(printer: str, advanced: AdvancedOptions) -> None:
    settings = app_settings()
    settings.setValue(ADVANCED_KEY + printer, json.dumps(advanced.to_dict()))
    settings.sync()


def printer_names() -> list[str]:
    """The printers on this machine, then CalcForge's PDF printer."""
    try:
        from PySide6.QtPrintSupport import QPrinterInfo
        names = list(QPrinterInfo.availablePrinterNames())
    except Exception:                                  # noqa: BLE001
        names = []
    return names + [PDF_PRINTER]


def default_printer() -> str:
    try:
        from PySide6.QtPrintSupport import QPrinterInfo
        name = QPrinterInfo.defaultPrinterName()
    except Exception:                                  # noqa: BLE001
        name = ""
    return name or PDF_PRINTER


def paper_words(name: str, width_pt: float, height_pt: float) -> str:
    """A paper as Revu's Size list names it: "A4 (210 x 297 mm)"."""
    short, long_ = sorted((width_pt / MM_TO_PT, height_pt / MM_TO_PT))
    return f"{name} ({short:.0f} x {long_:.0f} mm)"


def _right(text: str) -> QLabel:
    """A form label, right-aligned against its field, as Revu's are."""
    label = QLabel(text)
    label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return label


# ---------------------------------------------------------------------------
# the preview
# ---------------------------------------------------------------------------

class PrintPreview(QWidget):
    """The paper, the page on it as it will print, and the margins in red
    (Revu: "Red borders indicate the margins defined for the page")."""

    def __init__(self, dialog: "PrintDialog"):
        super().__init__(dialog)
        self.dialog = dialog
        self.setObjectName("printPreview")
        self.setMinimumSize(250, 300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setToolTip("How the page will appear on the printed paper; "
                        "the red border is the printer's margins")

    def paper_rect(self, paper: QSizeF) -> QRectF:
        """Where the paper is drawn in the widget."""
        room = QRectF(self.rect()).adjusted(8, 8, -8, -8)
        scale = min(room.width() / max(paper.width(), 1.0),
                    room.height() / max(paper.height(), 1.0))
        width, height = paper.width() * scale, paper.height() * scale
        return QRectF(room.center().x() - width / 2, room.center().y() - height / 2,
                      width, height)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        sheet = self.dialog.preview_sheet()
        if sheet is None:
            painter.setPen(self.palette().windowText().color())
            painter.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap,
                             self.dialog.preview_message())
            painter.end()
            return
        page, placed = sheet
        paper = self.paper_rect(placed.paper)
        scale = paper.width() / max(placed.paper.width(), 1.0)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.fillRect(paper, QColor("#ffffff"))
        image = self.dialog.preview_image(page)
        painter.save()
        painter.setClipRect(paper)
        to_widget = QTransform.fromScale(scale, scale) * \
            QTransform.fromTranslate(paper.left(), paper.top())
        painter.setTransform(placed.transform * to_widget)
        painter.setClipRect(placed.clip, Qt.IntersectClip)
        if image is not None:
            painter.drawImage(QRectF(0, 0, float(page.width_pt), float(page.height_pt)),
                              image, QRectF(image.rect()))
        else:
            painter.fillRect(placed.clip, QColor(235, 235, 235))
        painter.restore()
        if image is None or self.dialog._image_key(page) in self.dialog._waiting:
            # still coming: say so, rather than show a page that looks empty
            painter.setPen(QColor("#666666"))
            painter.drawText(paper.adjusted(0, 0, 0, -14), Qt.AlignHCenter | Qt.AlignBottom,
                             "Drawing…")
        # the margins, as Revu draws them: the paper outside them washed red
        margins = placed.margin_rect()
        inner = QRectF(paper.left() + margins.left() * scale,
                       paper.top() + margins.top() * scale,
                       margins.width() * scale, margins.height() * scale)
        band = QColor(232, 96, 96, 110)
        for part in (QRectF(paper.left(), paper.top(), paper.width(), inner.top() - paper.top()),
                     QRectF(paper.left(), inner.bottom(), paper.width(),
                            paper.bottom() - inner.bottom()),
                     QRectF(paper.left(), inner.top(), inner.left() - paper.left(),
                            inner.height()),
                     QRectF(inner.right(), inner.top(), paper.right() - inner.right(),
                            inner.height())):
            if part.width() > 0 and part.height() > 0:
                painter.fillRect(part, band)
        pen = QPen(QColor("#e05050"))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(inner)
        painter.setPen(QColor(0, 0, 0, 90))
        painter.drawRect(paper)
        painter.end()


class WindowPicker(QObject):
    """Get Window: a rectangle dragged on the canvas, the dialog out of the
    way meanwhile (Revu: "Temporarily returns to the document to define a
    rectangular region to set the print area"). Esc gives up."""

    def __init__(self, view, done):
        super().__init__(view)
        self.view = view
        self.done = done
        self.start: Optional[QPointF] = None
        self.band = QRubberBand(QRubberBand.Rectangle, view.viewport())
        view.viewport().installEventFilter(self)
        view.installEventFilter(self)
        QApplication.instance().installEventFilter(self)
        self.view.viewport().setCursor(Qt.CrossCursor)

    def finish(self, result) -> None:
        QApplication.instance().removeEventFilter(self)
        self.view.viewport().removeEventFilter(self)
        self.view.removeEventFilter(self)
        self.view.viewport().unsetCursor()
        self.band.hide()
        self.band.deleteLater()
        done, self.done = self.done, None
        self.deleteLater()
        if done is not None:
            done(result)

    def eventFilter(self, watched, event) -> bool:
        kind = event.type()
        if kind == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            self.finish(None)
            return True
        if watched is not self.view.viewport():
            return False
        if kind == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            self.start = event.position()
            self.band.setGeometry(QRect(self.start.toPoint(), QSize()))
            self.band.show()
            return True
        if kind == QEvent.MouseMove and self.start is not None:
            self.band.setGeometry(QRect(self.start.toPoint(),
                                        event.position().toPoint()).normalized())
            return True
        if kind == QEvent.MouseButtonRelease and self.start is not None \
                and event.button() == Qt.LeftButton:
            first = self.view.mapToScene(self.start.toPoint())
            last = self.view.mapToScene(event.position().toPoint())
            self.start = None
            frame = self.view.frame_at(first) or self.view.frame_at(last)
            if frame is None:
                self.finish(None)
                return True
            region = QRectF(frame.mapFromScene(first), frame.mapFromScene(last)).normalized()
            region = region.intersected(QRectF(0, 0, frame.page.width_pt, frame.page.height_pt))
            self.finish((frame.page, region) if region.width() > 2 and region.height() > 2
                        else None)
            return True
        if kind in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick,
                    QEvent.MouseButtonRelease):
            return True                       # nothing else happens meanwhile
        return False



# ---------------------------------------------------------------------------
# Advanced
# ---------------------------------------------------------------------------

def _spin(name: str, low: float, high: float, suffix: str = "", decimals: int = 1,
          tip: str = "") -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setObjectName(name)
    box.setRange(low, high)
    box.setDecimals(decimals)
    box.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    if suffix:
        box.setSuffix(suffix)
    if tip:
        box.setToolTip(tip)
    box.setKeyboardTracking(True)
    return box


class AdvancedPrintDialog(QDialog):
    """Revu's Advanced Printing (menus__file__advanced-printing.txt): the
    printer it is for at the top, the Printing Engine — Image/Vector/Grid,
    Vector, Image, Grid — with its Grid Size, the resolution an image is sent
    at, Print Data Type, Image Band Limit and Image Band Size; Defaults. Kept
    for each printer, as Revu keeps them."""

    def __init__(self, printer: str, advanced: AdvancedOptions, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Advanced Printing")
        self.setObjectName("printAdvancedDialog")
        self.printer = printer
        layout = QVBoxLayout(self)
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        r = 0
        grid.addWidget(_right("Printer:"), r, 0)
        name = QLabel(printer)
        name.setObjectName("advancedPrinter")
        grid.addWidget(name, r, 1)
        r += 1
        self.engine = QComboBox()
        self.engine.setObjectName("advancedEngine")
        for key, words in printing.ENGINES:
            self.engine.addItem(words, key)
        self.engine.setItemData(0, "Vector, with the squares where something is see-through "
                                   "sent as pictures", Qt.ToolTipRole)
        self.engine.setItemData(1, "Everything as vector, as drawn", Qt.ToolTipRole)
        self.engine.setItemData(2, "The whole page as a picture, in bands", Qt.ToolTipRole)
        self.engine.setItemData(3, "The whole page as pictures a Grid Size square",
                                Qt.ToolTipRole)
        self.engine.setToolTip("How the page is sent to the printer")
        grid.addWidget(_right("Printing Engine:"), r, 0)
        grid.addWidget(self.engine, r, 1)
        r += 1
        self.grid_size = _spin("advancedGrid", 0.1, 20, " in", 2,
                               "Grid Size: the squares sent as pictures")
        grid.addWidget(_right("Grid Size:"), r, 0)
        grid.addWidget(self.grid_size, r, 1)
        r += 1
        self.dpi = QSpinBox()
        self.dpi.setObjectName("advancedDpi")
        self.dpi.setRange(72, 1200)
        self.dpi.setSuffix(" dpi")
        self.dpi.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.dpi.setToolTip("How sharp a page sent as a picture is (Revu: Maximum Print DPI); "
                            "never more than the printer's own")
        grid.addWidget(_right("Resolution:"), r, 0)
        grid.addWidget(self.dpi, r, 1)
        r += 1
        self.data_type = QComboBox()
        self.data_type.setObjectName("advancedDataType")
        self.data_type.addItems(["Printer Default", "RAW", "EMF"])
        self.data_type.setEnabled(False)
        self.data_type.setToolTip(NO_DATA_TYPE)
        grid.addWidget(_right("Print Data Type:"), r, 0)
        grid.addWidget(self.data_type, r, 1)
        r += 1
        self.band_limit = _spin("advancedBandLimit", 1, 1024, " MB", 0,
                                "Image Band Limit: a picture bigger than this is sent "
                                "in bands")
        grid.addWidget(_right("Image Band Limit:"), r, 0)
        grid.addWidget(self.band_limit, r, 1)
        r += 1
        self.band_size = _spin("advancedBandSize", 0.5, 1024, " MB", 1,
                               "Image Band Size: how big each band is")
        grid.addWidget(_right("Image Band Size:"), r, 0)
        grid.addWidget(self.band_size, r, 1)
        buttons = QHBoxLayout()
        self.defaults = QPushButton("Defaults")
        self.defaults.setObjectName("advancedDefaults")
        self.defaults.setAutoDefault(False)
        self.defaults.setToolTip("Put the Advanced settings back as they first were")
        self.defaults.clicked.connect(lambda: self.set_options(AdvancedOptions()))
        ok = QPushButton("OK")
        ok.setObjectName("advancedOk")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("advancedCancel")
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(self.defaults)
        buttons.addStretch(1)
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        layout.addSpacing(4)
        layout.addLayout(buttons)
        self.engine.currentIndexChanged.connect(self._follow)
        self.band_limit.valueChanged.connect(self._follow)
        self.set_options(advanced)
        self.setMinimumWidth(380)

    def set_options(self, advanced: AdvancedOptions) -> None:
        self.engine.setCurrentIndex(max(self.engine.findData(advanced.engine), 0))
        self.grid_size.setValue(advanced.grid_in)
        self.dpi.setValue(advanced.dpi)
        self.band_limit.setValue(advanced.band_limit_mb)
        self.band_size.setValue(advanced.band_size_mb)
        self._follow()

    def _follow(self, *_args) -> None:
        engine = self.engine.currentData()
        self.grid_size.setEnabled(engine in (printing.ENGINE_MIXED, printing.ENGINE_GRID))
        self.band_size.setMaximum(self.band_limit.value())

    def options(self) -> AdvancedOptions:
        return AdvancedOptions.from_dict({
            "engine": self.engine.currentData(), "grid_in": self.grid_size.value(),
            "dpi": self.dpi.value(), "band_limit_mb": self.band_limit.value(),
            "band_size_mb": self.band_size.value()})


# ---------------------------------------------------------------------------
# the dialog
# ---------------------------------------------------------------------------

class PrintDialog(QDialog):
    """File ▸ Print… (Ctrl+P), File ▸ Print Preview… and a thumbnail's
    Print Pages…. Shown, not run: the window stays drawn under it and the
    preview fills itself in while the event loop runs."""

    def __init__(self, window, current: int = 0, selected=None,
                 default_range: Optional[str] = None):
        super().__init__(window)
        self.window = window
        self.document = window.document
        self.setWindowTitle("Print")
        self.setObjectName("printDialog")
        self.setWindowModality(Qt.ApplicationModal)
        self.file_path = ""                   # To File / Print to PDF: where (asked if empty)
        self.window_region: Optional[tuple] = None    # Get Window: (page, rect)
        self.preview_index = 0
        self._images: dict = {}
        self._queue_timer = QTimer(self)
        self._queue_timer.setSingleShot(True)
        self._queue_timer.setInterval(0)
        self._queue_timer.timeout.connect(self._draw_next)
        self._waiting: dict = {}              # preview pages whose PDF picture is coming
        self._patience = QTimer(self)
        self._patience.setSingleShot(True)
        self._patience.setInterval(int(BACKGROUND_PATIENCE_S * 1000) + 50)
        self._patience.timeout.connect(self._draw_next)
        from ..io import pdftiles
        pdftiles.TILES.sheetReady.connect(self._sheet_arrived)
        self._listening = True
        self._building = True
        self._custom_scale = 100.0            # Scale's own value, for Custom Scale
        self.printed = 0                      # sheets the last Print sent
        self.advanced = AdvancedOptions()
        self._filtered: frozenset = frozenset()   # what the Markups List filters out

        count = len(self.document.pages)
        outer = QVBoxLayout(self)
        outer.setSpacing(8)
        body = QHBoxLayout()
        body.setSpacing(10)
        outer.addLayout(body, 1)

        # -- the document: its name, its size, the page, the navigation ----
        name = os.path.basename(self.document.path or "") or self.document.title \
            or "Untitled"
        preview_box = QGroupBox(name)
        preview_box.setObjectName("printDocument")
        preview_column = QVBoxLayout(preview_box)
        preview_column.setSpacing(4)
        self.page_size = QLabel()
        self.page_size.setObjectName("printPageSize")
        preview_column.addWidget(self.page_size)
        self.preview = PrintPreview(self)
        preview_column.addWidget(self.preview, 1)
        nav = QHBoxLayout()
        nav.setSpacing(2)
        self.first_button = self._nav("printFirst", "|◀", "First page", self.first_page)
        self.prev_button = self._nav("printPrev", "◀", "Previous page", self.previous_page)
        self.page_of = QLineEdit()
        self.page_of.setObjectName("printPageOf")
        self.page_of.setAlignment(Qt.AlignCenter)
        self.page_of.setFixedWidth(120)
        self.page_of.setToolTip("The page shown: type a page number to go to it")
        self.page_of.editingFinished.connect(self._typed_page)
        self.page_of.installEventFilter(self)    # Enter there goes to the page, not Print
        self.next_button = self._nav("printNext", "▶", "Next page", self.next_page)
        self.last_button = self._nav("printLast", "▶|", "Last page", self.last_page)
        nav.addStretch(1)
        for widget in (self.first_button, self.prev_button, self.page_of,
                       self.next_button, self.last_button):
            nav.addWidget(widget)
            nav.addSpacing(6)
        nav.addStretch(1)
        preview_column.addLayout(nav)
        body.addWidget(preview_box, 4)

        # the settings keep one width, so the range box appearing for Custom
        # does not push the preview about
        column = QWidget()
        column.setObjectName("printSettings")
        column.setFixedWidth(430)
        right = QVBoxLayout(column)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(6)
        body.addWidget(column, 0)

        # -- Printer ------------------------------------------------------
        printer_box = QGroupBox("Printer")
        grid = self._form(printer_box)
        self.printer = QComboBox()
        self.printer.setObjectName("printerName")
        self.printer.addItems(printer_names())
        self.printer.setToolTip("The printer to print on; Print to PDF writes a PDF file")
        self.printer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.printer.setMinimumContentsLength(14)
        self.properties = QPushButton("Properties")
        self.properties.setObjectName("printerProperties")
        self.properties.setAutoDefault(False)
        self.properties.setToolTip("The printer's paper, orientation and margins")
        self.properties.clicked.connect(self.printer_properties)
        grid.addWidget(_right("Name:"), 0, 0)
        grid.addWidget(self.printer, 0, 1)
        grid.addWidget(self.properties, 0, 2)
        self.status = QLabel()
        self.status.setObjectName("printerStatus")
        self.to_file = QCheckBox("To File")
        self.to_file.setObjectName("printToFile")
        self.to_file.setToolTip("Save the print to a file instead of sending it to the printer")
        grid.addWidget(_right("Status:"), 1, 0)
        grid.addWidget(self.status, 1, 1)
        grid.addWidget(self.to_file, 1, 2)
        right.addWidget(printer_box)

        # -- Pages (n) ----------------------------------------------------
        self.range_box = QGroupBox("Pages")
        self.range_box.setObjectName("printPagesBox")
        grid = self._form(self.range_box)
        self.pages = PagesRange(count, current, selected,
                                default=default_range or PagesRange.ALL)
        self.pages.combo.setObjectName("printPages")
        self.pages.layout().setSpacing(4)
        # Revu's words: "All Pages (1 - 6)"
        self.pages.combo.setItemText(self.pages.combo.findData(PagesRange.ALL),
                                     f"All Pages (1 - {count})")
        self.pages.combo.setToolTip("Which pages print; Custom takes pages and ranges, "
                                    "such as 1-3, 5, 9")
        self.pages.range.setFixedWidth(96)
        self.get_window_button = QPushButton("Get Window")
        self.get_window_button.setObjectName("printGetWindow")
        self.get_window_button.setAutoDefault(False)
        self.get_window_button.setToolTip("Go back to the document and drag a rectangle "
                                          "round the part of a page to print")
        self.get_window_button.clicked.connect(self.get_window)
        grid.addWidget(_right("Page Range:"), 0, 0)
        grid.addWidget(self.pages, 0, 1)
        grid.addWidget(self.get_window_button, 0, 2)
        self.window_note = QLabel()
        self.window_note.setObjectName("printWindowNote")
        self.window_note.setVisible(False)
        grid.addWidget(self.window_note, 1, 1, 1, 2)
        right.addWidget(self.range_box)

        # -- Options ------------------------------------------------------
        options_box = QGroupBox("Options")
        grid = self._form(options_box)
        grid.setVerticalSpacing(5)
        r = 0
        self.size = QComboBox()
        self.size.setObjectName("printSize")
        self.size.setToolTip("The paper to print on")
        self.auto = QCheckBox("Auto")
        self.auto.setObjectName("printAuto")
        self.auto.setToolTip("Each page on paper of its own size")
        grid.addWidget(_right("Size:"), r, 0)
        grid.addWidget(self.size, r, 1)
        grid.addWidget(self.auto, r, 2)
        r += 1
        turn = QHBoxLayout()
        self.portrait = QRadioButton("Portrait")
        self.portrait.setObjectName("printPortrait")
        self.landscape = QRadioButton("Landscape")
        self.landscape.setObjectName("printLandscape")
        self.orientation = QButtonGroup(self)
        self.orientation.addButton(self.portrait)
        self.orientation.addButton(self.landscape)
        turn.addWidget(self.portrait)
        turn.addSpacing(16)
        turn.addWidget(self.landscape)
        turn.addStretch(1)
        grid.addLayout(turn, r, 1, 1, 2)
        r += 1
        self.stream = QComboBox()
        self.stream.setObjectName("printStream")
        for key, words in printing.STREAMS:
            self.stream.addItem(words, key)
        self.stream.setToolTip("What prints: the page and its markups, the page alone, "
                               "or the markups alone on blank paper")
        grid.addWidget(_right("Print:"), r, 0)
        grid.addWidget(self.stream, r, 1)
        r += 1
        copies_row = QHBoxLayout()
        self.copies = QSpinBox()
        self.copies.setObjectName("printCopies")
        self.copies.setRange(1, 999)
        self.copies.setKeyboardTracking(True)
        self.copies.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.copies.setFixedWidth(110)
        self.collate = QCheckBox("Collate")
        self.collate.setObjectName("printCollate")
        self.collate.setToolTip("Copies in page order: 1, 2, 3, 1, 2, 3")
        self.reverse = QCheckBox("Reverse")
        self.reverse.setObjectName("printReverse")
        self.reverse.setToolTip("Print the last page first")
        copies_row.addWidget(self.copies)
        copies_row.addSpacing(10)
        copies_row.addWidget(self.collate)
        copies_row.addSpacing(14)
        copies_row.addWidget(self.reverse)
        copies_row.addStretch(1)
        grid.addWidget(_right("Copies:"), r, 0)
        grid.addLayout(copies_row, r, 1, 1, 2)
        r += 1
        self.rotation = QComboBox()
        self.rotation.setObjectName("printRotation")
        for key, words in printing.ROTATIONS:
            self.rotation.addItem(words, key)
        self.rotation.setToolTip("Turn the page on the paper; Auto-Rotate turns a page that "
                                 "lies the other way to the paper")
        grid.addWidget(_right("Rotation:"), r, 0)
        grid.addWidget(self.rotation, r, 1)
        r += 1
        self.scaling = QComboBox()
        self.scaling.setObjectName("printScaling")
        for key, words in printing.SCALINGS:
            self.scaling.addItem(words, key)
        grid.addWidget(_right("Page Scaling:"), r, 0)
        grid.addWidget(self.scaling, r, 1)
        r += 1
        self.custom_scale = _spin("printCustomScale", 1, 1000, " %", 0,
                                  "Scale: the page at this percentage of its size "
                                  "(Custom Scale); otherwise the scale Page Scaling gives")
        self.custom_scale.setFixedWidth(110)
        scale_row = QHBoxLayout()
        scale_row.addWidget(self.custom_scale)
        scale_row.addStretch(1)
        grid.addWidget(_right("Scale:"), r, 0)
        grid.addLayout(scale_row, r, 1, 1, 2)
        r += 1
        centre_row = QHBoxLayout()
        self.centre = QCheckBox("Centre")
        self.centre.setObjectName("printCentre")
        self.centre.setToolTip("Centre the page on the paper; untick to place its top-left "
                               "corner at X and Y")
        self.x = _spin("printX", -2000, 2000, " mm", 1, "X: from the paper's left edge")
        self.y = _spin("printY", -2000, 2000, " mm", 1, "Y: from the paper's top edge")
        self.x.setFixedWidth(96)
        self.y.setFixedWidth(96)
        centre_row.addWidget(self.centre)
        centre_row.addSpacing(12)
        centre_row.addWidget(QLabel("X:"))
        centre_row.addWidget(self.x)
        centre_row.addSpacing(12)
        centre_row.addWidget(QLabel("Y:"))
        centre_row.addWidget(self.y)
        centre_row.addStretch(1)
        grid.addLayout(centre_row, r, 1, 1, 2)
        r += 1
        self.dim = self._tick("printDim", "Dim Page Content",
                              "Tone the page down so the markups stand out on the print")
        self.dim_filtered = self._tick(
            "printDimFiltered", "Dim Filtered Markups",
            "Markups the Markups List's filter leaves out print toned down; "
            "untick to print them as they are")
        self.spaces = self._tick("printSpaces", "Print Spaces", DECLINED_SPACES)
        self.spaces.setEnabled(False)
        self.links = self._tick("printLinks", "Print Visible Hyperlinks",
                                "Print the links' rectangles as they show on screen")
        self.greyscale = self._tick("printGreyscale", "Print in Greyscale",
                                    "Print in shades of grey (sent as a picture at the "
                                    "Advanced resolution)")
        for tick in (self.dim, self.dim_filtered, self.spaces, self.links, self.greyscale):
            grid.addWidget(tick, r, 1, 1, 2)
            r += 1
        right.addWidget(options_box)
        right.addStretch(1)

        # -- buttons ------------------------------------------------------
        buttons = QHBoxLayout()
        from . import bindable
        # Defaults ▾ and Add Files ▾ only open their menus: the entries are
        # the commands (bindable.DATA keeps the faces out of the list)
        self.defaults = QPushButton("Defaults")
        self.defaults.setObjectName("printDefaults")
        self.defaults.setAutoDefault(False)
        self.defaults.setProperty(bindable.DATA, True)
        self.defaults.setToolTip("Put the options back to your defaults, or save these as them")
        self.defaults_menu = self.build_defaults_menu()
        self.defaults.setMenu(self.defaults_menu)
        self.advanced_button = QPushButton("Advanced")
        self.advanced_button.setObjectName("printAdvanced")
        self.advanced_button.setAutoDefault(False)
        self.advanced_button.setToolTip("How the page is sent to the printer: vector, "
                                        "image or grid, and at what resolution")
        self.advanced_button.clicked.connect(self.open_advanced)
        self.add_files = QPushButton("Add Files")
        self.add_files.setObjectName("printAddFiles")
        self.add_files.setAutoDefault(False)
        self.add_files.setProperty(bindable.DATA, True)
        added = QMenu(self.add_files)
        added.addAction("Add Files…").setEnabled(False)
        added.addAction("Add Folder…").setEnabled(False)
        self.add_files.setMenu(added)
        self.add_files.setEnabled(False)
        self.add_files.setToolTip(DECLINED_BATCH)
        self.go_button = QPushButton("Print")
        self.go_button.setObjectName("printGo")
        self.go_button.setDefault(True)
        self.go_button.setProperty("accent", True)
        self.go_button.clicked.connect(self.print_now)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("printCancel")
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)
        for button in (self.defaults, self.advanced_button, self.add_files):
            buttons.addWidget(button)
            buttons.addSpacing(4)
        buttons.addStretch(1)
        buttons.addWidget(self.go_button)
        buttons.addWidget(cancel)
        outer.addLayout(buttons)

        # -- filled in, then listened to ----------------------------------
        remembered = app_settings().value(PRINTER_KEY, "")
        chosen = remembered if remembered in printer_names() else default_printer()
        self.printer.setCurrentText(chosen)
        self.advanced = advanced_for(self.printer_name())
        self._fill_sizes()
        self.set_options(remembered_options())
        self._printer_changed()
        for signal in (self.size.currentIndexChanged, self.stream.currentIndexChanged,
                       self.rotation.currentIndexChanged, self.scaling.currentIndexChanged,
                       self.copies.valueChanged, self.custom_scale.valueChanged,
                       self.x.valueChanged, self.y.valueChanged,
                       self.auto.toggled, self.landscape.toggled, self.collate.toggled,
                       self.reverse.toggled, self.centre.toggled, self.dim.toggled,
                       self.dim_filtered.toggled, self.links.toggled, self.greyscale.toggled):
            signal.connect(self._changed)
        self.printer.currentIndexChanged.connect(self._printer_changed)
        self.pages.combo.currentIndexChanged.connect(self._range_changed)
        self.pages.range.textChanged.connect(self._range_changed)
        self._bind_commands()
        self._building = False
        self._filtered = frozenset(self._filtered_markups())
        self.pages.range.setVisible(self.pages.which() == PagesRange.CUSTOM)
        self.go_button.setFocus()
        self.resize(800, 600)
        self._changed()

    # -- small builders --------------------------------------------------
    @staticmethod
    def _form(box: QGroupBox) -> QGridLayout:
        grid = QGridLayout(box)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)
        return grid

    @staticmethod
    def _tick(name: str, text: str, tip: str) -> QCheckBox:
        box = QCheckBox(text)
        box.setObjectName(name)
        box.setToolTip(tip)
        return box

    def _nav(self, name: str, text: str, tip: str, slot) -> QToolButton:
        button = QToolButton()
        button.setObjectName(name)
        button.setText(text)
        button.setToolTip(tip)
        button.setAutoRaise(True)
        button.clicked.connect(slot)
        return button

    def build_defaults_menu(self) -> QMenu:
        """Defaults ▾: Restore Defaults (the ones saved, else CalcForge's),
        Save as Default, and Factory Defaults."""
        from . import bindable
        menu = QMenu(self)
        bindable.set_context(menu, "print")
        restore = menu.addAction("Restore Defaults", self.restore_defaults)
        restore.setToolTip("The options saved with Save as Default (CalcForge's own if none "
                           "were)")
        menu.addAction("Save as Default", self.save_as_default).setToolTip(
            "Keep these options as the ones Restore Defaults brings back")
        menu.addSeparator()
        menu.addAction("Factory Defaults", self.factory_defaults).setToolTip(
            "The options as CalcForge ships them")
        menu.setToolTipsVisible(True)
        return menu

    def _bind_commands(self) -> None:
        """Every button and Defaults entry is a command a key can be given to
        (Keyboard Shortcuts, under File); the keys work while the dialog is
        up, which the window's own cannot."""
        router = getattr(self.window, "commands", None)
        if router is None:
            return
        for name, command_id in BUTTON_IDS.items():
            button = self.findChild(QAbstractButton, name)
            if button is not None:
                router.bind_button(button, command_id)
        self._key_actions = []
        for command_id in list(BUTTON_IDS.values()) + list(MENU_IDS):
            keys = router.keys_of(command_id)
            if not keys:
                continue
            action = QAction(self)
            action.setShortcuts(keys)
            action.setShortcutContext(Qt.WindowShortcut)
            action.triggered.connect(lambda _c=False, c=command_id: router.run(c))
            self.addAction(action)
            self._key_actions.append(action)

    # -- the printer -----------------------------------------------------
    def printer_name(self) -> str:
        return self.printer.currentText()

    def _printer_info(self):
        from PySide6.QtPrintSupport import QPrinterInfo
        name = self.printer_name()
        if name == PDF_PRINTER:
            return None
        info = QPrinterInfo.printerInfo(name)
        return None if info.isNull() else info

    def _fill_sizes(self) -> None:
        """The papers the printer offers (CalcForge's sizes for a PDF), each
        as Revu names it: "A4 (210 x 297 mm)"."""
        wanted = self.size.currentData(Qt.UserRole + 1)
        was = self.size.blockSignals(True)
        self.size.clear()
        info = self._printer_info()
        sizes = []
        if info is not None:
            for size in info.supportedPageSizes():
                points = size.sizePoints()
                sizes.append((size.name(), float(points.width()), float(points.height())))
        if not sizes:
            sizes = [(name, w * MM_TO_PT, h * MM_TO_PT) for name, (w, h) in PAGE_SIZES.items()]
        for name, width, height in sizes:
            self.size.addItem(paper_words(name, width, height),
                              (min(width, height), max(width, height)))
            self.size.setItemData(self.size.count() - 1, name, Qt.UserRole + 1)
        found = self._size_index(wanted) if wanted else -1
        self.size.setCurrentIndex(found if found >= 0 else max(self._size_index("A4"), 0))
        self.size.blockSignals(was)

    def _size_index(self, name: str) -> int:
        for index in range(self.size.count()):
            if self.size.itemData(index, Qt.UserRole + 1) == name:
                return index
        return -1

    def _printer_changed(self, *_args) -> None:
        pdf = self.printer_name() == PDF_PRINTER
        info = self._printer_info()
        if pdf:
            self.status.setText("Ready")
            self.status.setToolTip("Print to PDF writes a PDF file")
        elif info is None:
            self.status.setText("Not available")
        else:
            from PySide6.QtPrintSupport import QPrinter
            state = info.state()
            self.status.setText({QPrinter.Idle: "Ready", QPrinter.Active: "Printing",
                                 QPrinter.Aborted: "Aborted",
                                 QPrinter.Error: "Error"}.get(state, "Ready"))
        was = self.to_file.blockSignals(True)
        if pdf:
            self.to_file.setChecked(True)
        self.to_file.setEnabled(not pdf)
        self.to_file.blockSignals(was)
        if not self._building:
            self.advanced = advanced_for(self.printer_name())
            self._fill_sizes()
            self._changed()

    def make_printer(self):
        """A QPrinter for the printer chosen, or None if no file was given."""
        from PySide6.QtPrintSupport import QPrinter
        info = self._printer_info()
        printer = QPrinter(info, QPrinter.HighResolution) if info is not None \
            else QPrinter(QPrinter.HighResolution)
        printer.setDocName(self.document.title or "CalcForge document")
        if info is None or self.to_file.isChecked():
            path = self.file_path
            pdf = info is None
            if not path:
                from .mainwindow import in_start_folder
                stem = os.path.splitext(os.path.basename(self.document.path or "document"))[0]
                path, _ = QFileDialog.getSaveFileName(
                    self, "Print to File",
                    in_start_folder(stem + (".pdf" if pdf else ".prn"), self.document),
                    "PDF files (*.pdf)" if pdf else "Print files (*.prn)")
                if not path:
                    return None
            if pdf:
                printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(path)
        return printer

    def printer_properties(self) -> None:
        """Properties: the printer's own page set-up; its paper and
        orientation come back into Size."""
        from PySide6.QtPrintSupport import QPageSetupDialog, QPrinter
        info = self._printer_info()
        printer = QPrinter(info, QPrinter.HighResolution) if info is not None \
            else QPrinter(QPrinter.HighResolution)
        options = self.options()
        printer.setPageSize(printing.QPageSize(QSizeF(options.paper_w_pt, options.paper_h_pt),
                                               printing.QPageSize.Point, options.paper))
        dialog = QPageSetupDialog(printer, self)
        if dialog.exec() != QDialog.Accepted:
            return
        self.take_paper(printer.pageLayout())

    def take_paper(self, layout) -> None:
        """A page layout's paper and orientation into Size, Auto off."""
        from PySide6.QtGui import QPageLayout
        points = layout.pageSize().sizePoints()
        across, down = float(points.width()), float(points.height())
        short, long_ = min(across, down), max(across, down)
        best, gap = -1, None
        for index in range(self.size.count()):
            width, height = self.size.itemData(index)
            miss = abs(width - short) + abs(height - long_)
            if gap is None or miss < gap:
                best, gap = index, miss
        if best >= 0 and gap is not None and gap < 3.0:
            self.size.setCurrentIndex(best)
        else:
            name = layout.pageSize().name() or "Custom"
            self.size.addItem(paper_words(name, short, long_), (short, long_))
            self.size.setItemData(self.size.count() - 1, name, Qt.UserRole + 1)
            self.size.setCurrentIndex(self.size.count() - 1)
        self.landscape.setChecked(layout.orientation() == QPageLayout.Landscape)
        self.portrait.setChecked(layout.orientation() != QPageLayout.Landscape)
        self.auto.setChecked(False)

    def open_advanced(self) -> Optional[AdvancedPrintDialog]:
        """Advanced: Revu's Advanced Printing, for the printer chosen. Shown
        over the Print dialog; OK keeps its settings for that printer."""
        dialog = AdvancedPrintDialog(self.printer_name(), self.advanced, self)
        dialog.setWindowModality(Qt.ApplicationModal)
        router = getattr(self.window, "commands", None)
        if router is not None:
            for name, command_id in (("advancedDefaults", "print.advanced_defaults"),
                                     ("advancedOk", "print.advanced_ok"),
                                     ("advancedCancel", "print.advanced_cancel")):
                router.bind_button(dialog.findChild(QPushButton, name), command_id)
        dialog.accepted.connect(lambda: self._take_advanced(dialog))
        self.advanced_dialog = dialog
        dialog.show()
        return dialog

    def _take_advanced(self, dialog: AdvancedPrintDialog) -> None:
        self.advanced = dialog.options()
        remember_advanced(self.printer_name(), self.advanced)

    # -- options ---------------------------------------------------------
    def options(self) -> PrintOptions:
        width, height = self.size.currentData() or (210 * MM_TO_PT, 297 * MM_TO_PT)
        return PrintOptions(
            stream=self.stream.currentData(), copies=self.copies.value(),
            collate=self.collate.isChecked(), reverse=self.reverse.isChecked(),
            rotation=self.rotation.currentData(), scaling=self.scaling.currentData(),
            custom_scale=self._custom_scale, centre=self.centre.isChecked(),
            x_mm=self.x.value(), y_mm=self.y.value(), dim=self.dim.isChecked(),
            dim_filtered=self.dim_filtered.isChecked(), links=self.links.isChecked(),
            greyscale=self.greyscale.isChecked(),
            auto_size=self.auto.isChecked(),
            paper=self.size.currentData(Qt.UserRole + 1) or "A4",
            paper_w_pt=float(width), paper_h_pt=float(height),
            landscape=self.landscape.isChecked())

    def set_options(self, options: PrintOptions) -> None:
        building, self._building = self._building, True
        try:
            self.stream.setCurrentIndex(max(self.stream.findData(options.stream), 0))
            self.copies.setValue(options.copies)
            self.collate.setChecked(options.collate)
            self.reverse.setChecked(options.reverse)
            self.rotation.setCurrentIndex(max(self.rotation.findData(options.rotation), 0))
            self.scaling.setCurrentIndex(max(self.scaling.findData(options.scaling), 0))
            self._custom_scale = float(options.custom_scale)
            self.custom_scale.setValue(options.custom_scale)
            self.centre.setChecked(options.centre)
            self.x.setValue(options.x_mm)
            self.y.setValue(options.y_mm)
            self.dim.setChecked(options.dim)
            self.dim_filtered.setChecked(options.dim_filtered)
            self.links.setChecked(options.links)
            self.greyscale.setChecked(options.greyscale)
            self.auto.setChecked(options.auto_size)
            found = self._size_index(options.paper)
            self.size.setCurrentIndex(found if found >= 0 else max(self._size_index("A4"), 0))
            self.landscape.setChecked(options.landscape)
            self.portrait.setChecked(not options.landscape)
        finally:
            self._building = building
        self._changed()

    def restore_defaults(self) -> None:
        """Defaults ▾ Restore Defaults: the options saved as default (or
        CalcForge's own). The printer and the pages stay — they say what to
        print, not how."""
        self.set_options(saved_defaults())

    def save_as_default(self) -> None:
        """Defaults ▾ Save as Default: these options, for Restore Defaults
        (and for the first print after)."""
        settings = app_settings()
        settings.setValue(DEFAULTS_KEY, json.dumps(self.options().to_dict()))
        settings.sync()
        self.window.status_hint.setText("Print options saved as the default")

    def factory_defaults(self) -> None:
        """Defaults ▾ Factory Defaults: the options as CalcForge ships them."""
        self.set_options(PrintOptions())

    def _changed(self, *_args) -> None:
        if self._building:
            return
        custom = self.scaling.currentData() == printing.CUSTOM
        if self.sender() is self.custom_scale and custom:
            self._custom_scale = self.custom_scale.value()
        self.collate.setEnabled(self.copies.value() > 1)
        self.custom_scale.setEnabled(custom)
        self.x.setEnabled(not self.centre.isChecked())
        self.y.setEnabled(not self.centre.isChecked())
        auto = self.auto.isChecked()
        self.size.setEnabled(not auto)
        self.portrait.setEnabled(not auto)
        self.landscape.setEnabled(not auto)
        self._show_sheet()

    def _show_scale(self) -> None:
        """Scale: Custom Scale's own value, or what Page Scaling makes of the
        page shown (greyed)."""
        if self.scaling.currentData() == printing.CUSTOM:
            value = self._custom_scale
        else:
            sheet = self.preview_sheet()
            value = sheet[1].scale * 100.0 if sheet is not None else 100.0
        if abs(self.custom_scale.value() - value) > 1e-6:
            was = self.custom_scale.blockSignals(True)
            self.custom_scale.setValue(value)
            self.custom_scale.blockSignals(was)

    # -- pages -----------------------------------------------------------
    def _range_changed(self, *_args) -> None:
        if self.window_region is not None and not self._building:
            self.clear_window()
        # the range box only for Custom, as Revu's single Page Range box
        self.pages.range.setVisible(self.pages.which() == PagesRange.CUSTOM)
        if self.sender() is self.pages.combo and self.pages.which() == PagesRange.CUSTOM:
            self.pages.range.setFocus()
            self.pages.range.selectAll()
        self.preview_index = 0
        self._show_sheet()

    def page_indexes(self) -> Optional[list]:
        """The pages asked for, from 0; None when the range will not read."""
        if self.window_region is not None:
            page = self.window_region[0]
            return [self.document.pages.index(page)] if page in self.document.pages else []
        return self.pages.page_indexes()

    def printed_pages(self) -> list:
        """The pages that print, in the order they come out (Reverse), each
        once — what the preview steps through."""
        pages = printing.printable_pages(self.document, self.page_indexes() or [])
        return list(reversed(pages)) if self.reverse.isChecked() else pages

    def _filtered_markups(self) -> list:
        panel = getattr(self.window, "markups_panel", None)
        if panel is None or not hasattr(panel, "filtered_out"):
            return []
        return panel.filtered_out(self.document)

    def get_window(self) -> None:
        """Get Window: the dialog steps aside while a rectangle is dragged
        on the page."""
        self.hide()
        self.window.status_hint.setText(
            "Get Window: drag a rectangle round what to print (Esc to go back)")
        self._picker = WindowPicker(self.window.view, self._window_got)

    def _window_got(self, result) -> None:
        self._picker = None
        if result is not None:
            page, region = result
            self.window_region = (page, QRectF(region))
            number = self.document.pages.index(page) + 1
            self.window_note.setText(
                f"Window on page {number}: {region.width() / MM_TO_PT:.0f} × "
                f"{region.height() / MM_TO_PT:.0f} mm")
            self.window_note.setVisible(True)
            self.preview_index = 0
        self.window.status_hint.setText("Ready")
        self.show()
        self.raise_()
        self.activateWindow()
        self._show_sheet()

    def clear_window(self) -> None:
        self.window_region = None
        self.window_note.setVisible(False)
        self._show_sheet()

    # -- the preview -----------------------------------------------------
    def preview_message(self) -> str:
        if self.page_indexes() is None:
            return "Enter pages to print, such as 1-3, 5, 9."
        return "No pages are included in print and export."

    def preview_sheet(self):
        """(page, placement) of the sheet the preview shows, or None."""
        pages = self.printed_pages()
        if not pages:
            return None
        self.preview_index = min(max(self.preview_index, 0), len(pages) - 1)
        page = pages[self.preview_index]
        options = self.options()
        region = self.window_region[1] if self.window_region is not None else None
        placed = printing.place(QSizeF(float(page.width_pt), float(page.height_pt)),
                                printing.paper_for(page, options), options,
                                printing.printer_margins(self._preview_printer()), region)
        return page, placed

    def _preview_printer(self):
        held = getattr(self, "_held_printer", None)
        if held is None or held[0] != self.printer_name():
            from PySide6.QtPrintSupport import QPrinter
            info = self._printer_info()
            printer = QPrinter(info, QPrinter.ScreenResolution) if info is not None \
                else QPrinter(QPrinter.ScreenResolution)
            self._held_printer = held = (self.printer_name(), printer)
        return held[1]

    def _image_key(self, page) -> tuple:
        return (page.uid, self.stream.currentData(), self.dim.isChecked(),
                self.dim_filtered.isChecked(), self.links.isChecked(),
                self.greyscale.isChecked())

    def preview_image(self, page) -> Optional[QImage]:
        """The page as it prints, small, if it has been drawn; asks for it
        if it has not."""
        image = self._images.get(self._image_key(page))
        if image is None:
            self._queue_timer.start(0)
        return image

    def draw_preview_image(self, page, draft: str = "background") -> tuple:
        """*page* in the stream chosen, drawn by the print's own code, and
        whether it is all there (the PDF's own picture may still be coming
        from the render processes)."""
        longest = max(float(page.width_pt), float(page.height_pt), 1.0)
        scale = PREVIEW_PIXELS / longest
        image = QImage(max(int(page.width_pt * scale), 1), max(int(page.height_pt * scale), 1),
                       QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.white)
        painter = QPainter(image)
        painter.scale(scale, scale)
        dimmed = self._filtered if self.dim_filtered.isChecked() else ()
        try:
            complete = printing.draw_page(painter, page, self.stream.currentData(),
                                          self.dim.isChecked(), draft=draft,
                                          links=self.links.isChecked(), dimmed=dimmed)
        finally:
            painter.end()
        if self.greyscale.isChecked():
            image = image.convertToFormat(QImage.Format_Grayscale8)
        return image, complete

    def _sheet_arrived(self, *_args) -> None:
        """A picture came from the render processes: the preview pages that
        were waiting for one are drawn again."""
        if self._waiting:
            self._queue_timer.start(0)

    def _draw_next(self) -> None:
        """Draw one missing preview page — the one shown at once, then its
        neighbours while nothing else is happening — and come back for the
        next while any is missing."""
        pages = self.printed_pages()
        if not pages:
            return
        at = min(max(self.preview_index, 0), len(pages) - 1)
        order = [at] + [i for d in (1, -1, 2, -2) for i in (at + d,) if 0 <= i < len(pages)]
        now = time.monotonic()
        for index in order:
            page = pages[index]
            key = self._image_key(page)
            asked = self._waiting.get(key)
            if page.frame is None or (key in self._images and asked is None):
                continue
            # drawn from the render processes' picture of the page; drawn
            # here, small, if that has not come in a second and a half
            late = asked is not None and now - asked > BACKGROUND_PATIENCE_S
            image, complete = self.draw_preview_image(page, "now" if late else "background")
            if image is not None and (complete or key not in self._images or late):
                self._images[key] = image
            if complete or late:
                self._waiting.pop(key, None)
            elif asked is None:
                self._waiting[key] = now
            if index == at:
                self.preview.update()
            if not complete and not late and key in self._waiting:
                # waiting for its picture: the others meanwhile, and this one
                # again when a picture arrives (or patience runs out)
                self._patience.start()
                continue
            # the next one only once the person has stopped for a moment
            self._queue_timer.start(NEIGHBOUR_DELAY_MS)
            return

    def preview_ready(self) -> bool:
        """Whether the page shown is drawn, all of it."""
        sheet = self.preview_sheet()
        if sheet is None:
            return True
        key = self._image_key(sheet[0])
        return key in self._images and key not in self._waiting

    def page_of_text(self) -> str:
        """Revu's "1 (1 of 1)": the page's own number, then where it is in
        what prints."""
        pages = self.printed_pages()
        if not pages:
            return "0 (0 of 0)"
        page = pages[self.preview_index]
        number = self.document.pages.index(page) + 1
        return f"{number} ({self.preview_index + 1} of {len(pages)})"

    def _show_sheet(self) -> None:
        pages = self.printed_pages()
        total = len(pages)
        self.preview_index = min(max(self.preview_index, 0), max(total - 1, 0))
        self.page_of.setText(self.page_of_text())
        self.range_box.setTitle(f"Pages ({total})")
        for button, enabled in ((self.first_button, self.preview_index > 0),
                                (self.prev_button, self.preview_index > 0),
                                (self.next_button, self.preview_index < total - 1),
                                (self.last_button, self.preview_index < total - 1)):
            button.setEnabled(enabled)
        self.go_button.setEnabled(total > 0)
        if total:
            page = pages[self.preview_index]
            self.page_size.setText(f"{page.width_pt / MM_TO_PT / 10:.2f} x "
                                   f"{page.height_pt / MM_TO_PT / 10:.2f} Centimetres")
        else:
            self.page_size.setText("")
        self._show_scale()
        self.preview.update()
        if total:
            self._queue_timer.start(0)

    def _typed_page(self) -> None:
        """A page number typed into "1 (1 of 1)": that page, if it prints."""
        found = re.match(r"\s*(\d+)", self.page_of.text())
        pages = self.printed_pages()
        if found:
            wanted = int(found.group(1)) - 1
            for index, page in enumerate(pages):
                if self.document.pages.index(page) == wanted:
                    self.preview_index = index
                    break
        self._show_sheet()

    def first_page(self) -> None:
        self.preview_index = 0
        self._show_sheet()

    def previous_page(self) -> None:
        self.preview_index -= 1
        self._show_sheet()

    def next_page(self) -> None:
        self.preview_index += 1
        self._show_sheet()

    def last_page(self) -> None:
        self.preview_index = len(self.printed_pages()) - 1
        self._show_sheet()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.page_of and event.type() == QEvent.KeyPress \
                and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._typed_page()
            return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event) -> None:
        """Page Up and Page Down step the preview, as in Revu's."""
        if event.key() == Qt.Key_PageDown:
            self.next_page() if self.next_button.isEnabled() else None
            return
        if event.key() == Qt.Key_PageUp:
            self.previous_page() if self.prev_button.isEnabled() else None
            return
        super().keyPressEvent(event)

    # -- printing --------------------------------------------------------
    def print_now(self) -> int:
        """Print: the job, then the options remembered for next time."""
        indexes = self.page_indexes()
        if indexes is None:
            QMessageBox.warning(self, "Print", "Enter pages to print, such as 1-3, 5, 9.")
            return 0
        pages = printing.printable_pages(self.document, indexes)
        if not pages:
            QMessageBox.warning(self, "Print", "No pages are included in print and export.")
            return 0
        printer = self.make_printer()
        if printer is None:
            return 0
        options = self.options()
        region = self.window_region[1] if self.window_region is not None else None
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.printed = printing.print_pages(printer, pages, options, region,
                                                advanced=self.advanced,
                                                filtered=self._filtered)
        except Exception as exc:  # noqa: BLE001
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Print", str(exc))
            return 0
        QApplication.restoreOverrideCursor()
        remember_options(options, self.printer_name(), self.pages.which())
        self.window.status_hint.setText(
            f"Printed {self.printed} sheet{'s' if self.printed != 1 else ''}")
        self.accept()
        return self.printed

    def done(self, result) -> None:
        self._queue_timer.stop()
        self._patience.stop()
        if self._listening:
            from ..io import pdftiles
            self._listening = False
            try:
                pdftiles.TILES.sheetReady.disconnect(self._sheet_arrived)
            except (RuntimeError, TypeError):
                pass
        super().done(result)

