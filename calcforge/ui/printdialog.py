"""Revu's Print dialog, with the preview folded in (the user, Round 3: "Build
Revu's Print dialog, with the preview folded in. Print Pages… opens it with
Selected chosen. The per-page and per-markup print ticks stay").

Laid out as Revu 21's (menus__file__print.txt): the Preview, with its page
navigation under it; the Printer (Name, Properties, Status, To File); the
Page Range — the shared Pages control (widgets.PagesRange) and Get Window;
the Options — Size with Portrait/Landscape and Auto, Print (Document &
Markups, Document Only, Markups Only), Copies with Collate and Reverse,
Rotation, Page Scaling (None, Fit to Paper, Reduce to Paper, Custom Scale,
Fit to Margins, Reduce to Margins), Centre (or X and Y) and Dim Page
Content; Defaults at the bottom left, Print and Cancel at the bottom right.

The preview is the print's own drawing of each page (io/printing.draw_page)
at a low resolution, made when the event loop is idle — the page being
looked at first, then the ones either side — and kept, so changing the
scaling, rotation, paper or position only re-lays the picture already made
and is instant. Only a change of what prints (the stream, Dim) draws again.
The canvas's markups are QGraphicsItems and can only be painted on the
window's thread, which is why "in the background" means off the input path
rather than on another thread.
"""
from __future__ import annotations

import json
import os
import time
from typing import Optional

from PySide6.QtCore import QEvent, QObject, QPointF, QRect, QRectF, QSize, QSizeF, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QTransform
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog,
                               QDoubleSpinBox, QFileDialog, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QMessageBox, QPushButton, QRadioButton,
                               QRubberBand, QSizePolicy, QSpinBox, QToolButton, QVBoxLayout,
                               QWidget)

from ..core.document import MM_TO_PT, PAGE_SIZES
from ..io import printing
from ..io.printing import PrintOptions
from ..settings import app_settings
from .widgets import PagesRange

#: CalcForge's own printer: the print written to a PDF file. Always there,
#: so printing works on a machine with no printer installed.
PDF_PRINTER = "Print to PDF"
SETTINGS_KEY = "print/options"
PRINTER_KEY = "print/printer"
RANGE_KEY = "print/range"

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


def remembered_options() -> PrintOptions:
    """The options of the last print, or the defaults."""
    raw = app_settings().value(SETTINGS_KEY, "")
    try:
        data = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        data = {}
    return PrintOptions.from_dict(data if isinstance(data, dict) else {})


def remember_options(options: PrintOptions, printer: str, range_kind: str) -> None:
    settings = app_settings()
    settings.setValue(SETTINGS_KEY, json.dumps(options.to_dict()))
    settings.setValue(PRINTER_KEY, printer)
    if range_kind in (PagesRange.ALL, PagesRange.CURRENT):
        settings.setValue(RANGE_KEY, range_kind)
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
        self.setMinimumSize(300, 340)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setToolTip("How the page will appear on the printed paper; "
                        "red lines are the printer's margins")

    def paper_rect(self, paper: QSizeF) -> QRectF:
        """Where the paper is drawn in the widget."""
        room = QRectF(self.rect()).adjusted(14, 14, -14, -14)
        scale = min(room.width() / max(paper.width(), 1.0),
                    room.height() / max(paper.height(), 1.0))
        width, height = paper.width() * scale, paper.height() * scale
        return QRectF(room.center().x() - width / 2, room.center().y() - height / 2,
                      width, height)

    def paintEvent(self, _event) -> None:
        from ..app import current_theme
        from ..theme import CANVAS

        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(CANVAS.get(current_theme(), "#6e747d")))
        sheet = self.dialog.preview_sheet()
        if sheet is None:
            painter.setPen(QColor("#ffffff"))
            painter.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap,
                             self.dialog.preview_message())
            painter.end()
            return
        page, placed = sheet
        paper = self.paper_rect(placed.paper)
        scale = paper.width() / max(placed.paper.width(), 1.0)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.fillRect(paper.translated(3, 3), QColor(0, 0, 0, 70))      # its shadow
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
            painter.drawText(paper.adjusted(0, 0, 0, -8), Qt.AlignHCenter | Qt.AlignBottom,
                             "Drawing…")
        # the margins, in red, as Revu draws them
        margins = placed.margin_rect()
        pen = QPen(QColor("#e02020"))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(paper.left() + margins.left() * scale,
                                paper.top() + margins.top() * scale,
                                margins.width() * scale, margins.height() * scale))
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
# the dialog
# ---------------------------------------------------------------------------

def _spin(name: str, low: float, high: float, suffix: str = "", decimals: int = 1,
          tip: str = "") -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setObjectName(name)
    box.setRange(low, high)
    box.setDecimals(decimals)
    if suffix:
        box.setSuffix(suffix)
    if tip:
        box.setToolTip(tip)
    box.setKeyboardTracking(True)
    return box


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
        self.printed = 0                      # sheets the last Print sent

        count = len(self.document.pages)
        outer = QVBoxLayout(self)
        body = QHBoxLayout()
        body.setSpacing(10)
        outer.addLayout(body, 1)

        # -- Preview ------------------------------------------------------
        preview_box = QGroupBox("Preview")
        preview_column = QVBoxLayout(preview_box)
        self.preview = PrintPreview(self)
        preview_column.addWidget(self.preview, 1)
        nav = QHBoxLayout()
        nav.setSpacing(2)
        self.first_button = self._nav("printFirst", "⏮", "First page", self.first_page)
        self.prev_button = self._nav("printPrev", "◀", "Previous page", self.previous_page)
        self.page_of = QLabel()
        self.page_of.setObjectName("printPageOf")
        self.page_of.setAlignment(Qt.AlignCenter)
        self.page_of.setMinimumWidth(90)
        self.next_button = self._nav("printNext", "▶", "Next page", self.next_page)
        self.last_button = self._nav("printLast", "⏭", "Last page", self.last_page)
        nav.addStretch(1)
        for widget in (self.first_button, self.prev_button, self.page_of,
                       self.next_button, self.last_button):
            nav.addWidget(widget)
        nav.addStretch(1)
        preview_column.addLayout(nav)
        body.addWidget(preview_box, 1)

        right = QVBoxLayout()
        right.setSpacing(8)
        body.addLayout(right, 0)

        # -- Printer ------------------------------------------------------
        printer_box = QGroupBox("Printer")
        grid = QGridLayout(printer_box)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)
        self.printer = QComboBox()
        self.printer.setObjectName("printerName")
        self.printer.addItems(printer_names())
        self.printer.setToolTip("The printer to print on; Print to PDF writes a PDF file")
        self.properties = QPushButton("Properties")
        self.properties.setObjectName("printerProperties")
        self.properties.setToolTip("The printer's paper, orientation and margins")
        self.properties.clicked.connect(self.printer_properties)
        grid.addWidget(QLabel("Name:"), 0, 0)
        grid.addWidget(self.printer, 0, 1)
        grid.addWidget(self.properties, 0, 2)
        self.status = QLabel()
        self.status.setObjectName("printerStatus")
        self.to_file = QCheckBox("To File")
        self.to_file.setObjectName("printToFile")
        self.to_file.setToolTip("Save the print to a file instead of sending it to the printer")
        grid.addWidget(QLabel("Status:"), 1, 0)
        grid.addWidget(self.status, 1, 1)
        grid.addWidget(self.to_file, 1, 2)
        right.addWidget(printer_box)

        # -- Page Range ---------------------------------------------------
        range_box = QGroupBox("Page Range")
        column = QVBoxLayout(range_box)
        column.setSpacing(6)
        row = QHBoxLayout()
        self.pages = PagesRange(count, current, selected,
                                default=default_range or PagesRange.ALL)
        self.pages.combo.setObjectName("printPages")
        self.get_window_button = QPushButton("Get Window")
        self.get_window_button.setObjectName("printGetWindow")
        self.get_window_button.setToolTip("Go back to the document and drag a rectangle "
                                          "round the part of a page to print")
        self.get_window_button.clicked.connect(self.get_window)
        row.addWidget(self.pages, 1)
        row.addWidget(self.get_window_button)
        column.addLayout(row)
        self.window_note = QLabel()
        self.window_note.setObjectName("printWindowNote")
        self.window_note.setVisible(False)
        column.addWidget(self.window_note)
        right.addWidget(range_box)

        # -- Options ------------------------------------------------------
        options_box = QGroupBox("Options")
        grid = QGridLayout(options_box)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)
        r = 0
        self.size = QComboBox()
        self.size.setObjectName("printSize")
        self.size.setToolTip("The paper to print on")
        self.auto = QCheckBox("Auto")
        self.auto.setObjectName("printAuto")
        self.auto.setToolTip("Each page on paper of its own size")
        grid.addWidget(QLabel("Size:"), r, 0)
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
        turn.addSpacing(12)
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
        grid.addWidget(QLabel("Print:"), r, 0)
        grid.addWidget(self.stream, r, 1, 1, 2)
        r += 1
        copies_row = QHBoxLayout()
        self.copies = QSpinBox()
        self.copies.setObjectName("printCopies")
        self.copies.setRange(1, 999)
        self.copies.setKeyboardTracking(True)
        self.collate = QCheckBox("Collate")
        self.collate.setObjectName("printCollate")
        self.collate.setToolTip("Copies in page order: 1, 2, 3, 1, 2, 3")
        self.reverse = QCheckBox("Reverse")
        self.reverse.setObjectName("printReverse")
        self.reverse.setToolTip("Print the last page first")
        self.copies.setMinimumWidth(70)
        copies_row.addWidget(self.copies)
        copies_row.addSpacing(6)
        copies_row.addWidget(self.collate)
        copies_row.addSpacing(10)
        copies_row.addWidget(self.reverse)
        copies_row.addStretch(1)
        grid.addWidget(QLabel("Copies:"), r, 0)
        grid.addLayout(copies_row, r, 1, 1, 2)
        r += 1
        self.rotation = QComboBox()
        self.rotation.setObjectName("printRotation")
        for key, words in printing.ROTATIONS:
            self.rotation.addItem(words, key)
        self.rotation.setToolTip("Turn the page on the paper; Auto turns it to suit the paper")
        grid.addWidget(QLabel("Rotation:"), r, 0)
        grid.addWidget(self.rotation, r, 1, 1, 2)
        r += 1
        scaling_row = QHBoxLayout()
        self.scaling = QComboBox()
        self.scaling.setObjectName("printScaling")
        for key, words in printing.SCALINGS:
            self.scaling.addItem(words, key)
        self.custom_scale = _spin("printCustomScale", 1, 1000, " %", 0,
                                  "Custom Scale: the page at this percentage of its size")
        self.custom_scale.setFixedWidth(84)
        scaling_row.addWidget(self.scaling, 1)
        scaling_row.addWidget(self.custom_scale)
        grid.addWidget(QLabel("Page Scaling:"), r, 0)
        grid.addLayout(scaling_row, r, 1, 1, 2)
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
        centre_row.addSpacing(6)
        centre_row.addWidget(QLabel("X:"))
        centre_row.addWidget(self.x)
        centre_row.addSpacing(8)
        centre_row.addWidget(QLabel("Y:"))
        centre_row.addWidget(self.y)
        centre_row.addStretch(1)
        grid.addLayout(centre_row, r, 0, 1, 3)
        r += 1
        self.dim = QCheckBox("Dim Page Content")
        self.dim.setObjectName("printDim")
        self.dim.setToolTip("Tone the page down so the markups stand out on the print")
        grid.addWidget(self.dim, r, 0, 1, 3)
        right.addWidget(options_box)
        right.addStretch(1)

        # -- buttons ------------------------------------------------------
        buttons = QHBoxLayout()
        self.defaults = QPushButton("Defaults")
        self.defaults.setObjectName("printDefaults")
        self.defaults.setToolTip("Put the options back as they first were")
        self.defaults.setAutoDefault(False)
        self.defaults.clicked.connect(self.restore_defaults)
        self.go_button = QPushButton("Print")
        self.go_button.setObjectName("printGo")
        self.go_button.setDefault(True)
        self.go_button.clicked.connect(self.print_now)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("printCancel")
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(self.defaults)
        buttons.addStretch(1)
        buttons.addWidget(self.go_button)
        buttons.addWidget(cancel)
        outer.addLayout(buttons)

        # -- filled in, then listened to ----------------------------------
        remembered = app_settings().value(PRINTER_KEY, "")
        chosen = remembered if remembered in printer_names() else default_printer()
        self.printer.setCurrentText(chosen)
        self._fill_sizes()
        self.set_options(remembered_options())
        self._printer_changed()
        for signal in (self.size.currentIndexChanged, self.stream.currentIndexChanged,
                       self.rotation.currentIndexChanged, self.scaling.currentIndexChanged,
                       self.copies.valueChanged, self.custom_scale.valueChanged,
                       self.x.valueChanged, self.y.valueChanged,
                       self.auto.toggled, self.landscape.toggled, self.collate.toggled,
                       self.reverse.toggled, self.centre.toggled, self.dim.toggled):
            signal.connect(self._changed)
        self.printer.currentIndexChanged.connect(self._printer_changed)
        self.pages.combo.currentIndexChanged.connect(self._range_changed)
        self.pages.range.textChanged.connect(self._range_changed)
        self._building = False
        self.resize(780, 580)              # fits a window of 800 × 600
        self._changed()

    # -- small builders --------------------------------------------------
    def _nav(self, name: str, text: str, tip: str, slot) -> QToolButton:
        button = QToolButton()
        button.setObjectName(name)
        button.setText(text)
        button.setToolTip(tip)
        button.setAutoRaise(True)
        button.clicked.connect(slot)
        return button

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
        """The papers the printer offers (CalcForge's sizes for a PDF)."""
        wanted = self.size.currentText()
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
            self.size.addItem(name, (min(width, height), max(width, height)))
        found = self.size.findText(wanted) if wanted else -1
        if found < 0:
            found = max(self.size.findText("A4"), 0)
        self.size.setCurrentIndex(found)
        self.size.blockSignals(was)

    def _printer_changed(self, *_args) -> None:
        pdf = self.printer_name() == PDF_PRINTER
        info = self._printer_info()
        if pdf:
            self.status.setText("Ready: writes a PDF file")
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
            self.size.addItem(layout.pageSize().name() or "Custom", (short, long_))
            self.size.setCurrentIndex(self.size.count() - 1)
        self.landscape.setChecked(layout.orientation() == QPageLayout.Landscape)
        self.portrait.setChecked(layout.orientation() != QPageLayout.Landscape)
        self.auto.setChecked(False)

    # -- options ---------------------------------------------------------
    def options(self) -> PrintOptions:
        width, height = self.size.currentData() or (210 * MM_TO_PT, 297 * MM_TO_PT)
        return PrintOptions(
            stream=self.stream.currentData(), copies=self.copies.value(),
            collate=self.collate.isChecked(), reverse=self.reverse.isChecked(),
            rotation=self.rotation.currentData(), scaling=self.scaling.currentData(),
            custom_scale=self.custom_scale.value(), centre=self.centre.isChecked(),
            x_mm=self.x.value(), y_mm=self.y.value(), dim=self.dim.isChecked(),
            auto_size=self.auto.isChecked(), paper=self.size.currentText(),
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
            self.custom_scale.setValue(options.custom_scale)
            self.centre.setChecked(options.centre)
            self.x.setValue(options.x_mm)
            self.y.setValue(options.y_mm)
            self.dim.setChecked(options.dim)
            self.auto.setChecked(options.auto_size)
            found = self.size.findText(options.paper)
            self.size.setCurrentIndex(found if found >= 0 else max(self.size.findText("A4"), 0))
            self.landscape.setChecked(options.landscape)
            self.portrait.setChecked(not options.landscape)
        finally:
            self._building = building
        self._changed()

    def restore_defaults(self) -> None:
        """Defaults: the options as CalcForge ships them. The printer and
        the pages stay — they say what to print, not how."""
        self.set_options(PrintOptions())

    def _changed(self, *_args) -> None:
        if self._building:
            return
        self.collate.setEnabled(self.copies.value() > 1)
        self.custom_scale.setEnabled(self.scaling.currentData() == printing.CUSTOM)
        self.x.setEnabled(not self.centre.isChecked())
        self.y.setEnabled(not self.centre.isChecked())
        auto = self.auto.isChecked()
        self.size.setEnabled(not auto)
        self.portrait.setEnabled(not auto)
        self.landscape.setEnabled(not auto)
        self._show_sheet()

    # -- pages -----------------------------------------------------------
    def _range_changed(self, *_args) -> None:
        if self.window_region is not None and not self._building:
            self.clear_window()
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
        return (page.uid, self.stream.currentData(), self.dim.isChecked())

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
        try:
            complete = printing.draw_page(painter, page, self.stream.currentData(),
                                          self.dim.isChecked(), draft=draft)
        finally:
            painter.end()
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

    def _show_sheet(self) -> None:
        pages = self.printed_pages()
        total = len(pages)
        self.preview_index = min(max(self.preview_index, 0), max(total - 1, 0))
        self.page_of.setText(f"{self.preview_index + 1} of {total}" if total else "0 of 0")
        for button, enabled in ((self.first_button, self.preview_index > 0),
                                (self.prev_button, self.preview_index > 0),
                                (self.next_button, self.preview_index < total - 1),
                                (self.last_button, self.preview_index < total - 1)):
            button.setEnabled(enabled)
        self.go_button.setEnabled(total > 0)
        self.preview.update()
        if total:
            self._queue_timer.start(0)

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
            self.printed = printing.print_pages(printer, pages, options, region)
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
