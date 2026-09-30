"""SMath Studio's page dialogs: File > Page Setup, File > Properties,
Insert > Field and Insert > Background, laid out as the desktop's (checked
against screenshots of SMath Studio 0.99 and its English UI strings)."""
from __future__ import annotations

import datetime
import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QPlainTextEdit, QPushButton, QRadioButton, QTabWidget, QVBoxLayout, QWidget)

from markforge.calc.page import AVAILABLE_FIELDS, field_text, make_field

# (name, PaperKind id, width, height in hundredths of an inch) - System.Drawing's paper list
PAPERS = [
    ("A3", "8", 1169, 1654), ("A4", "9", 827, 1169), ("A5", "11", 583, 827), ("B5 (JIS)", "13", 717, 1012),
    ("Letter", "1", 850, 1100), ("Legal", "5", 850, 1400), ("Executive", "7", 725, 1050),
    ("Tabloid", "3", 1100, 1700),
]
MM_PER_PX = 25.4 / 96.0


def _mm(px: float) -> str:
    return f"{px * MM_PER_PX:.2f}".rstrip("0").rstrip(".").replace(".", ",") if px else "0"


def _px(text: str, default: float) -> float:
    try:
        return float(text.replace(",", ".")) / MM_PER_PX
    except ValueError:
        return default


def _buttons(dlg: QDialog, ok_text: str = "OK") -> QDialogButtonBox:
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    bb.button(QDialogButtonBox.Ok).setText(ok_text)
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    return bb


class PageSetupDialog(QDialog):
    """File > Page Setup: Paper options (Size, Orientation), Margins
    (millimeters), Header and Footer."""

    def __init__(self, page, parent=None):
        super().__init__(parent)
        self.page = page
        self.setWindowTitle("Page Setup")
        lay = QVBoxLayout(self)

        paper = QGroupBox("Paper options")
        g = QGridLayout(paper)
        self.size = QComboBox()
        for name, pid, w, h in PAPERS:
            self.size.addItem(name, pid)
        idx = self.size.findData(page.paper_id)
        self.size.setCurrentIndex(idx if idx >= 0 else 1)
        g.addWidget(QLabel("Size:"), 0, 0)
        g.addWidget(self.size, 0, 1)
        self.portrait = QRadioButton("Portrait")
        self.landscape = QRadioButton("Landscape")
        (self.landscape if page.orientation.lower() == "landscape" else self.portrait).setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.portrait)
        grp.addButton(self.landscape)
        g.addWidget(QLabel("Orientation:"), 1, 0)
        g.addWidget(self.portrait, 1, 1)
        g.addWidget(self.landscape, 2, 1)
        lay.addWidget(paper)

        margins = QGroupBox("Margins (millimeters)")
        m = QGridLayout(margins)
        self.left, self.right = QLineEdit(_mm(page.margin_l)), QLineEdit(_mm(page.margin_r))
        self.top, self.bottom = QLineEdit(_mm(page.margin_t)), QLineEdit(_mm(page.margin_b))
        for r, (a, wa, b, wb) in enumerate((("Left:", self.left, "Right:", self.right),
                                            ("Top:", self.top, "Bottom:", self.bottom))):
            m.addWidget(QLabel(a), r, 0)
            m.addWidget(wa, r, 1)
            m.addWidget(QLabel(b), r, 2)
            m.addWidget(wb, r, 3)
        lay.addWidget(margins)

        hf = QGroupBox("Header and Footer")
        f = QFormLayout(hf)
        self.header = QLineEdit(page.header_text)
        self.footer = QLineEdit(page.footer_text)
        f.addRow("Header:", self.header)
        f.addRow("Footer:", self.footer)
        lay.addWidget(hf)
        lay.addWidget(_buttons(self))

    def apply(self) -> None:
        p = self.page
        _name, pid, w, h = PAPERS[self.size.currentIndex()]
        p.paper_id = pid
        p.orientation = "Landscape" if self.landscape.isChecked() else "Portrait"
        w, h = w * 0.96, h * 0.96  # hundredths of an inch -> px
        p.paper_w, p.paper_h = (h, w) if p.orientation == "Landscape" else (w, h)
        p.margin_l = _px(self.left.text(), p.margin_l)
        p.margin_r = _px(self.right.text(), p.margin_r)
        p.margin_t = _px(self.top.text(), p.margin_t)
        p.margin_b = _px(self.bottom.text(), p.margin_b)
        p.header_text = self.header.text()
        p.footer_text = self.footer.text()


class FilePropertiesDialog(QDialog):
    """File > Properties: Summary (Title, Author, Company, Keywords,
    Description) and File info (Name, Type, Location, Size, Read-only).
    Title, Author, Company and Keywords are what the header fields show."""

    KEYS = (("title", "Title"), ("author", "Author"), ("company", "Company"), ("keywords", "Keywords"))

    def __init__(self, metadata: dict, path: Path | None = None, parent=None):
        super().__init__(parent)
        self.metadata = metadata
        self.setWindowTitle("File Properties")
        self.resize(420, 360)
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        summary = QWidget()
        f = QFormLayout(summary)
        self.fields = {}
        for key, label in self.KEYS:
            w = QLineEdit(metadata.get(key, ""))
            f.addRow(label + ":", w)
            self.fields[key] = w
        self.description = QPlainTextEdit(metadata.get("description", ""))
        f.addRow("Description:", self.description)
        tabs.addTab(summary, "Summary")
        info = QWidget()
        fi = QFormLayout(info)
        fi.addRow("Name:", QLabel(path.name if path else "(not saved)"))
        fi.addRow("Type:", QLabel("SMath Studio worksheet (*.sm)"))
        fi.addRow("Location:", QLabel(str(path.parent) if path else ""))
        size = ""
        if path and path.exists():
            size = f"{path.stat().st_size / 1024:.1f} KB ({path.stat().st_size} bytes)"
        fi.addRow("Size:", QLabel(size))
        fi.addRow("Worksheet Id:", QLabel(metadata.get("_id", "")))
        fi.addRow("Worksheet revision:", QLabel(metadata.get("_revision", "")))
        attrs = QGroupBox("File attributes")
        al = QHBoxLayout(attrs)
        self.read_only = QCheckBox("Read-only")
        self.read_only.setChecked(bool(path and path.exists() and not os.access(path, os.W_OK)))
        self.read_only.setEnabled(bool(path and path.exists()))
        al.addWidget(self.read_only)
        fi.addRow(attrs)
        self.path = path
        tabs.addTab(info, "File info")
        lay.addWidget(tabs)
        lay.addWidget(_buttons(self))

    def apply(self) -> None:
        for key, w in self.fields.items():
            self.metadata[key] = w.text()
        self.metadata["description"] = self.description.toPlainText()
        if self.path and self.path.exists() and self.read_only.isEnabled():
            mode = self.path.stat().st_mode
            os.chmod(self.path, (mode & ~0o222) if self.read_only.isChecked() else (mode | 0o200))


class InsertFieldDialog(QDialog):
    """Insert > Field: Available Fields; Options - Command, Format, Example;
    File Properties... link; Insert / Cancel."""

    def __init__(self, metadata: dict, count: int = 1, filename: str = "", on_properties=None, parent=None):
        super().__init__(parent)
        self.metadata, self.count, self.filename = metadata, count, filename
        self.setWindowTitle("Insert Field")
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(QLabel("Available Fields:"))
        self.list = QListWidget()
        for label, *_ in AVAILABLE_FIELDS:
            self.list.addItem(label)
        left.addWidget(self.list)
        top.addLayout(left)
        opts = QGroupBox("Options")
        o = QVBoxLayout(opts)
        o.addWidget(QLabel("Command:"))
        self.command = QLineEdit()
        self.command.setReadOnly(True)
        o.addWidget(self.command)
        o.addWidget(QLabel("Format:"))
        self.format = QComboBox()
        self.format.setEditable(True)
        o.addWidget(self.format)
        o.addWidget(QLabel("Example:"))
        self.example = QLineEdit()
        self.example.setReadOnly(True)
        o.addWidget(self.example)
        o.addStretch(1)
        top.addWidget(opts)
        lay.addLayout(top)
        bottom = QHBoxLayout()
        link = QLabel('<a href="#">File Properties...</a>')
        link.linkActivated.connect(lambda _=None: on_properties and on_properties())
        bottom.addWidget(link)
        bottom.addStretch(1)
        bb = _buttons(self, "Insert")
        bottom.addWidget(bb)
        lay.addLayout(bottom)
        self.list.currentRowChanged.connect(self._selected)
        self.format.currentTextChanged.connect(lambda _t: self._preview())
        self.list.setCurrentRow(0)

    def _selected(self, row: int) -> None:
        _label, cmd, default, choices = AVAILABLE_FIELDS[row]
        self.command.setText(cmd)
        self.format.blockSignals(True)
        self.format.clear()
        self.format.addItems(choices)
        self.format.setEnabled(bool(choices))
        self.format.setEditText(default)
        self.format.blockSignals(False)
        self._preview()

    def code(self) -> str:
        row = max(0, self.list.currentRow())
        _label, cmd, _default, choices = AVAILABLE_FIELDS[row]
        return make_field(cmd, self.format.currentText() if choices else "")

    def _preview(self) -> None:
        self.example.setText(field_text(self.code(), self.metadata, 1, self.count, self.filename,
                                        datetime.datetime.now()))


class BackgroundDialog(QDialog):
    """Insert > Background: No background / Background image, Browse,
    Image size (Fit, Stretch, Fill, Original), Full page, Preview."""

    SIZES = [("Fit", "fit"), ("Stretch", "stretch"), ("Fill", "fill"), ("Original", "original")]

    def __init__(self, page, parent=None):
        super().__init__(parent)
        self.page = page
        self.image = page.background
        self.setWindowTitle("Background")
        lay = QHBoxLayout(self)
        left = QVBoxLayout()
        self.none = QRadioButton("No background")
        self.has = QRadioButton("Background image")
        (self.has if page.background else self.none).setChecked(True)
        left.addWidget(self.none)
        left.addWidget(self.has)
        row = QHBoxLayout()
        self.path = QLineEdit("(embedded image)" if page.background else "")
        self.path.setReadOnly(True)
        browse = QPushButton("Browse")
        browse.clicked.connect(self._browse)
        row.addWidget(self.path)
        row.addWidget(browse)
        left.addLayout(row)
        form = QFormLayout()
        self.size = QComboBox()
        for label, key in self.SIZES:
            self.size.addItem(label, key)
        i = self.size.findData(page.background_size)
        self.size.setCurrentIndex(i if i >= 0 else 1)
        form.addRow("Image size:", self.size)
        left.addLayout(form)
        self.full = QCheckBox("Full page")
        self.full.setChecked(page.background_full_page)
        left.addWidget(self.full)
        self.print_bg = QCheckBox("Print background images")
        self.print_bg.setChecked(page.print_background)
        left.addWidget(self.print_bg)
        left.addStretch(1)
        left.addWidget(_buttons(self))
        lay.addLayout(left)
        prev = QGroupBox("Preview")
        pl = QVBoxLayout(prev)
        self.preview = QLabel()
        self.preview.setFixedSize(150, 212)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet("background:#ffffff;border:1px solid #808080;")
        pl.addWidget(self.preview)
        lay.addWidget(prev)
        for w in (self.none, self.has, self.full):
            w.toggled.connect(lambda _on: self._update_preview())
        self.size.currentIndexChanged.connect(lambda _i: self._update_preview())
        self._update_preview()

    def _browse(self) -> None:
        fn, _ = QFileDialog.getOpenFileName(self, "Select image", "", "Images (*.png *.jpg *.jpeg *.bmp *.gif)")
        if fn:
            self.image = Path(fn).read_bytes()
            self.path.setText(fn)
            self.has.setChecked(True)
            self._update_preview()

    def _update_preview(self) -> None:
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor, QPainter

        pm = QPixmap(150, 212)
        pm.fill(QColor("white"))
        if self.has.isChecked() and self.image:
            img = QImage()
            img.loadFromData(self.image)
            p = QPainter(pm)
            s = 150 / max(1.0, self.page.paper_w)
            area = QRectF(0, 0, 150, 212) if self.full.isChecked() else QRectF(
                self.page.margin_l * s, self.page.margin_t * s, 150 - (self.page.margin_l + self.page.margin_r) * s,
                212 - (self.page.margin_t + self.page.margin_b) * s)
            from tests.calc.legacy_ui.worksheet_view import background_rect

            p.drawImage(background_rect(area, img, self.size.currentData()), img)
            p.end()
        self.preview.setPixmap(pm)

    def apply(self) -> None:
        p = self.page
        p.background = self.image if self.has.isChecked() else b""
        p.background_size = self.size.currentData()
        p.background_full_page = self.full.isChecked()
        p.print_background = self.print_bg.isChecked()
