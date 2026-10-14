"""Bluebeam's Color Processing dialog (Document ▸ Color Processing), for the
document's pages, for a snapshot (its Change Colors) and for a photo
(Colorize and Mask only, as in Bluebeam). The work is io/colorproc.py's.

Process Type chooses what is done; each has Bluebeam's options; Process
Images takes the pictures along; Pages is All Pages, Current, Selected (when
pages are picked in the Pages panel) or Custom ("1-3, 5, 9"); Modify Colors
applies to the current page only and lists only the colours on it, as in
Bluebeam. The Preview shows the page (or picture) before and after.
"""
from __future__ import annotations

import re
from typing import Optional

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDialog,
                               QDialogButtonBox, QFormLayout, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton,
                               QSlider, QSpinBox, QStackedWidget, QVBoxLayout, QWidget)

from ..io import colorproc
from ..io.colorproc import (BLACK_WHITE, COLORIZE, GRAYSCALE, LSH, MASK, MODIFY, NAMES,
                            Process)

PAGES, SNAPSHOT, PHOTO = "pages", "snapshot", "photo"
NO_COLOR = "No Color"


def parse_pages(text: str, count: int) -> Optional[list]:
    """Bluebeam's Custom pages: "1-3, 5, 9" → [0, 1, 2, 4, 8]; None if not."""
    out: list = []
    for part in [p.strip() for p in (text or "").split(",") if p.strip()]:
        m = re.fullmatch(r"(\d+)\s*(?:-\s*(\d+))?", part)
        if not m:
            return None
        a = int(m.group(1))
        b = int(m.group(2) or a)
        if a < 1 or b < a or b > count:
            return None
        out.extend(range(a - 1, b))
    return sorted(set(out)) or None


def _swatch(colour: str) -> QIcon:
    pix = QPixmap(14, 14)
    pix.fill(QColor(colour))
    return QIcon(pix)


class _ColourButton(QPushButton):
    """A colour, chosen with the colour picker; optionally "No Color"."""

    def __init__(self, colour: Optional[str], changed, allow_none: bool = False):
        super().__init__()
        self.colour = colour
        self.changed = changed
        self.allow_none = allow_none
        self.setFixedWidth(90)
        self.clicked.connect(self._pick)
        self._show()

    def _show(self):
        if self.colour is None:
            self.setText(NO_COLOR)
            self.setStyleSheet("")
        else:
            self.setText("")
            self.setStyleSheet(f"background:{self.colour}; border:1px solid #888;")

    def _pick(self):
        from PySide6.QtWidgets import QMenu
        if self.allow_none:
            menu = QMenu(self)
            menu.addAction(NO_COLOR, lambda: self.set(None))
            menu.addAction("Choose a colour…", self._choose)
            menu.exec(self.mapToGlobal(self.rect().bottomLeft()))
        else:
            self._choose()

    def _choose(self):
        got = QColorDialog.getColor(QColor(self.colour or "#000000"), self)
        if got.isValid():
            self.set(got.name())

    def set(self, colour: Optional[str]):
        self.colour = colour
        self._show()
        self.changed()


class ColorProcessingDialog(QDialog):
    def __init__(self, parent, mode: str = PAGES, *, document=None, current: int = 0,
                 selected: Optional[list] = None, colours: Optional[list] = None,
                 picture: Optional[QImage] = None, preview=None):
        """*colours*: the colours on the current page (Modify Colors' list);
        *picture*: a snapshot's or photo's look, for its preview; *preview*:
        callable(Process) → (before QImage, after QImage), for pages."""
        super().__init__(parent)
        self._timer = QTimer(self)               # the preview, a moment after a change
        self._timer.setSingleShot(True)
        self.mode = mode
        self.document = document
        self.current = current
        self.selected = selected or []
        self.colours = colours or ["#000000"]
        self.picture = picture
        self.previewer = preview
        self.setWindowTitle("Change Colors" if mode == SNAPSHOT else "Color Processing")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.kind = QComboBox()
        kinds = [COLORIZE, MASK] if mode == PHOTO else \
            [MODIFY, COLORIZE, GRAYSCALE, BLACK_WHITE, LSH, MASK]
        for key in kinds:
            self.kind.addItem(NAMES[key], key)
        form.addRow("Process Type:", self.kind)
        layout.addLayout(form)
        self.pages_stack = QStackedWidget()
        self.page_of = {}
        for key in kinds:
            self.page_of[key] = self.pages_stack.addWidget(self._options(key))
        layout.addWidget(self.pages_stack)
        self.images = QCheckBox("Process Images")
        self.images.setToolTip("Change the colours of pictures on the page too")
        self.images.toggled.connect(self._changed)
        layout.addWidget(self.images)
        # the pages
        self.pages_box = QGroupBox("Pages")
        grid = QGridLayout(self.pages_box)
        self.all_pages = QRadioButton("All Pages")
        self.current_page = QRadioButton(f"Current ({current + 1})")
        self.selected_pages = QRadioButton("Selected")
        self.custom_pages = QRadioButton("Custom")
        self.custom_text = QLineEdit()
        self.custom_text.setPlaceholderText("e.g. 1-3, 5, 9")
        group = QButtonGroup(self)
        for i, button in enumerate((self.all_pages, self.current_page, self.selected_pages,
                                    self.custom_pages)):
            group.addButton(button)
            grid.addWidget(button, i, 0)
        grid.addWidget(self.custom_text, 3, 1)
        self.current_page.setChecked(True)
        self.selected_pages.setVisible(bool(self.selected))
        self.pages_box.setVisible(mode == PAGES)
        layout.addWidget(self.pages_box)
        # the preview
        preview = QGroupBox("Preview")
        row = QHBoxLayout(preview)
        self.before = QLabel()
        self.after = QLabel()
        for label, caption in ((self.before, "Before"), (self.after, "After")):
            column = QVBoxLayout()
            label.setFixedSize(QSize(200, 200))
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("background:#ffffff; border:1px solid #888;")
            column.addWidget(label)
            column.addWidget(QLabel(caption), 0, Qt.AlignHCenter)
            row.addLayout(column)
        layout.addWidget(preview)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._timer.timeout.connect(self._preview)
        self.kind.currentIndexChanged.connect(self._kind_changed)
        self._kind_changed()

    # -- each type's options ----------------------------------------------------------------
    def _options(self, key: str) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        if key == MODIFY:
            self.pairs_box = QVBoxLayout()
            self.pairs: list = []
            holder = QWidget()
            holder.setLayout(self.pairs_box)
            form.addRow(holder)
            buttons = QHBoxLayout()
            add = QPushButton("Add New")
            add.clicked.connect(lambda: self.add_pair())
            remove = QPushButton("Remove")
            remove.clicked.connect(self.remove_pair)
            buttons.addWidget(add)
            buttons.addWidget(remove)
            buttons.addStretch(1)
            form.addRow(buttons)
            self.tolerance = QSpinBox()
            self.tolerance.setRange(0, 100)
            self.tolerance.setSuffix(" %")
            self.tolerance.valueChanged.connect(self._changed)
            form.addRow("Tolerance:", self.tolerance)
            self.add_pair()
        elif key == COLORIZE:
            self.select = _ColourButton("#000000", self._changed)
            self.to = _ColourButton("#ffffff", self._changed)
            self.scale = QCheckBox("Scale Color")
            self.scale.setChecked(True)
            self.scale.setToolTip("Cleared: every colour becomes the Select Color (white stays white)")
            self.scale.toggled.connect(self._changed)
            form.addRow("Select Color:", self.select)
            form.addRow("To:", self.to)
            form.addRow("", self.scale)
        elif key == LSH:
            self.sliders = {}
            for name, low, high in (("Luminosity", -100, 100), ("Saturation", -100, 100),
                                    ("Hue", -180, 180)):
                slider = QSlider(Qt.Horizontal)
                slider.setRange(low, high)
                value = QLabel("0")
                value.setFixedWidth(34)
                slider.valueChanged.connect(lambda v, lab=value: (lab.setText(str(v)),
                                                                   self._changed()))
                row = QHBoxLayout()
                row.addWidget(slider, 1)
                row.addWidget(value)
                form.addRow(f"{name}:", row)
                self.sliders[name] = slider
        elif key == MASK:
            self.mask = _ColourButton("#ffffff", self._changed)
            self.mask_tolerance = QSpinBox()
            self.mask_tolerance.setRange(0, 100)
            self.mask_tolerance.setSuffix(" %")
            self.mask_tolerance.valueChanged.connect(self._changed)
            form.addRow("Mask Color:", self.mask)
            form.addRow("Tolerance:", self.mask_tolerance)
            form.addRow("", QLabel("Markups are not processed."))
        else:
            form.addRow(QLabel({GRAYSCALE: "Converts colours to shades of grey.",
                                BLACK_WHITE: "Converts colours to black; the paper's white stays."}
                               [key]))
        return page

    def add_pair(self, source: Optional[str] = None, target: Optional[str] = "#ff0000") -> None:
        row = QHBoxLayout()
        combo = QComboBox()
        for colour in self.colours:
            combo.addItem(_swatch(colour), colour, colour)
        if source and source not in self.colours:
            combo.addItem(_swatch(source), source, source)
        if source:
            combo.setCurrentIndex(combo.findData(source))
        combo.currentIndexChanged.connect(self._changed)
        to = _ColourButton(target, self._changed, allow_none=True)
        row.addWidget(QLabel("Source Color:"))
        row.addWidget(combo, 1)
        row.addWidget(QLabel("To:"))
        row.addWidget(to)
        holder = QWidget()
        holder.setLayout(row)
        self.pairs_box.addWidget(holder)
        self.pairs.append((holder, combo, to))
        self._changed()

    def remove_pair(self) -> None:
        if len(self.pairs) > 1:
            holder, _c, _t = self.pairs.pop()
            holder.deleteLater()
            self._changed()

    # -- reading it -----------------------------------------------------------------------------
    def process(self) -> Process:
        kind = self.kind.currentData()
        proc = Process(kind, images=self.images.isChecked())
        if kind == MODIFY:
            proc.pairs = [(combo.currentData(), to.colour) for _h, combo, to in self.pairs]
            proc.tolerance = self.tolerance.value()
        elif kind == COLORIZE:
            proc.select, proc.to, proc.scale = self.select.colour, self.to.colour, self.scale.isChecked()
        elif kind == LSH:
            proc.luminosity = self.sliders["Luminosity"].value()
            proc.saturation = self.sliders["Saturation"].value()
            proc.hue = self.sliders["Hue"].value()
        elif kind == MASK:
            proc.mask, proc.tolerance = self.mask.colour, self.mask_tolerance.value()
        if self.mode == PHOTO:
            proc.images = True                 # a photo is a picture
        return proc

    def page_indexes(self, count: int) -> Optional[list]:
        if self.kind.currentData() == MODIFY or self.current_page.isChecked():
            return [self.current]
        if self.all_pages.isChecked():
            return list(range(count))
        if self.selected_pages.isChecked():
            return sorted(self.selected)
        return parse_pages(self.custom_text.text(), count)

    def _kind_changed(self, *_):
        kind = self.kind.currentData()
        self.pages_stack.setCurrentIndex(self.page_of[kind])
        self.images.setVisible(self.mode != PHOTO and kind in (COLORIZE, GRAYSCALE, BLACK_WHITE, LSH))
        # Bluebeam: Modify Colors applies to the current page only
        for button in (self.all_pages, self.selected_pages, self.custom_pages, self.custom_text):
            button.setEnabled(kind != MODIFY)
        if kind == MODIFY:
            self.current_page.setChecked(True)
        self._changed()

    def _changed(self, *_):
        self._timer.start(200)

    def _preview(self):
        proc = self.process()
        if self.previewer is not None:
            got = self.previewer(proc)
            if got is None:
                return
            before, after = got
        elif self.picture is not None:
            before = self.picture
            after = self.on_snapshot_preview(proc) if self.on_snapshot_preview is not None \
                else colorproc.process_qimage(self.picture, proc)
        else:
            return
        for label, image in ((self.before, before), (self.after, after)):
            if image is None or image.isNull():
                label.clear()
                continue
            label.setPixmap(QPixmap.fromImage(image).scaled(
                label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    on_snapshot_preview = None         # callable(Process) → QImage, set for a snapshot

    def accept(self) -> None:
        if self.mode == PAGES and self.document is not None:
            if self.page_indexes(len(self.document.pages)) is None:
                self.custom_text.setStyleSheet("border:1px solid #c92a2a")
                return
        super().accept()


# -- doing it ------------------------------------------------------------------------------------
def _render(data: bytes, index: int, size: int = 200) -> QImage:
    import pymupdf
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        page = doc[index]
        zoom = size / max(page.rect.width, page.rect.height, 1.0)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        return QImage(pix.samples, pix.width, pix.height, pix.stride,
                      QImage.Format_RGB888).copy()
    finally:
        doc.close()


def _one_page(data: bytes, index: int) -> bytes:
    import pymupdf
    source = pymupdf.open(stream=data, filetype="pdf")
    out = pymupdf.open()
    try:
        out.insert_pdf(source, from_page=index, to_page=index)
        return out.tobytes()
    finally:
        out.close()
        source.close()


def page_previewer(window, page):
    """Before and after of a page, for the dialog's Preview."""
    document = window.document
    if page.pdf_key and page.pdf_page_index is not None:
        data = document.asset(page.pdf_key)
        if data:
            single = _one_page(data, int(page.pdf_page_index))
            before = _render(single, 0)

            def preview(proc):
                try:
                    return before, _render(colorproc.process_pdf(single, [0], proc), 0)
                except Exception:  # noqa: BLE001
                    return before, before
            return preview
    image = window._background_image(page)
    if image is None:
        return None
    small = image.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return lambda proc: (small, colorproc.process_qimage(small, proc) if proc.acts_on_images()
                         else small)


def apply_to_pages(window, indexes: list, proc: Process) -> int:
    """The process on these pages, one undo step; how many pages changed."""
    from PySide6.QtCore import QBuffer, QIODevice
    document = window.document
    by_key: dict = {}
    rasters = []
    for index in indexes:
        page = document.pages[index]
        if page.pdf_key and page.pdf_page_index is not None:
            by_key.setdefault(page.pdf_key, []).append(page)
        elif page.background_key and proc.acts_on_images():
            rasters.append(page)
    new_keys: dict = {}
    for key, pages in by_key.items():
        data = document.asset(key)
        if not data:
            continue
        done = colorproc.process_pdf(data, sorted({int(p.pdf_page_index) for p in pages}), proc)
        new_keys[key] = document.add_asset(done, "pdf")
    new_backgrounds = {}
    for page in rasters:
        image = window._background_image(page)
        if image is None:
            continue
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        colorproc.process_qimage(image, proc).save(buffer, "PNG")
        new_backgrounds[id(page)] = document.add_asset(bytes(buffer.data()), "png")
    lines = []
    if proc.acts_on_vectors():
        for index in indexes:
            frame = document.pages[index].frame
            if frame is not None:
                lines.extend(i for i in frame.markups() if getattr(i, "from_drawing", False))
    changed = [p for pages in by_key.values() for p in pages] + rasters
    if not changed and not lines:
        return 0

    def mutate():
        for key, pages in by_key.items():
            if key in new_keys:
                for page in pages:
                    page.pdf_key = new_keys[key]
                    if page.frame is not None:
                        page.frame._background = None
        for page in rasters:
            if id(page) in new_backgrounds:
                page.background_key = new_backgrounds[id(page)]
                if page.frame is not None:
                    page.frame._background = None
        colorproc.process_items(lines, proc)
    window._structural_change("Color Processing", mutate, preserve_view=True)
    return len(changed)


def color_processing(window, index: Optional[int] = None) -> Optional[ColorProcessingDialog]:
    """Document ▸ Color Processing (Bluebeam's), from the page in view."""
    from .dialogs import QMessageBox
    which = window.page_index(index)
    page = window.document.pages[which]
    if not (page.pdf_key or page.background_key):
        QMessageBox.information(window, "Color Processing",
                                "This page has no drawing of its own to process: it is a blank "
                                "sheet, and markups keep their own colours.")
        return None
    colours = ["#000000"]
    if page.pdf_key and page.pdf_page_index is not None:
        data = window.document.asset(page.pdf_key)
        try:
            colours = colorproc.colours_in_pdf(data, int(page.pdf_page_index)) or colours
        except Exception:  # noqa: BLE001
            pass
    listed = window.pages_panel.list
    selected = sorted(listed.row(entry) for entry in listed.selectedItems())
    dialog = ColorProcessingDialog(window, PAGES, document=window.document, current=which,
                                   selected=selected if len(selected) > 1 else [],
                                   colours=colours, preview=page_previewer(window, page))
    if not getattr(window, "interactive_prompts", True):
        window._last_color_dialog = dialog
        return dialog
    if dialog.exec() == QDialog.Accepted:
        finish_pages(window, dialog)
    return dialog


def finish_pages(window, dialog: ColorProcessingDialog) -> int:
    indexes = dialog.page_indexes(len(window.document.pages))
    if not indexes:
        return 0
    count = apply_to_pages(window, indexes, dialog.process())
    window.status_hint.setText(f"Color Processing: {count} page{'s' * (count != 1)} processed"
                               if count else "Nothing on those pages to process")
    return count


def change_colors(window, item) -> Optional[ColorProcessingDialog]:
    """A snapshot's Change Colors, or a photo's Color Processing (Colorize and
    Mask only, as in Bluebeam)."""
    from ..items.media import ImageItem
    from ..items.snapshot import SnapshotItem
    from .dialogs import QMessageBox
    if isinstance(item, SnapshotItem):
        source = item.source_markups(window.document)
        if not source:
            QMessageBox.information(window, "Change Colors",
                                    "This snapshot was taken before CalcForge kept what a snapshot "
                                    "was made of, so its colours can't be changed. Take it again.")
            return None
        picture = window._snapshot_preview(item)
        dialog = ColorProcessingDialog(window, SNAPSHOT, picture=picture,
                                       colours=_item_colours(source))

        def preview(proc):
            copies = item.source_markups(window.document)
            colorproc.process_items(copies, proc)
            from ..items.snapshot import picture_of
            from PySide6.QtCore import QRectF
            from PySide6.QtGui import QPainter
            taken = item.natural_size()
            pic = picture_of(copies, QRectF(0, 0, taken.width(), taken.height()))
            image = QImage(max(1, int(taken.width())), max(1, int(taken.height())),
                           QImage.Format_ARGB32)
            image.fill(0xFFFFFFFF)
            painter = QPainter(image)
            painter.drawPicture(0, 0, pic)
            painter.end()
            return image
        dialog.on_snapshot_preview = preview
    elif isinstance(item, ImageItem):
        image = QImage()
        data = window.document.asset(item.asset_key)
        if not data or not image.loadFromData(data) or image.isNull():
            QMessageBox.information(window, "Color Processing", "There is no picture in this one.")
            return None
        dialog = ColorProcessingDialog(window, PHOTO, picture=image)
    else:
        return None
    if not getattr(window, "interactive_prompts", True):
        window._last_color_dialog = dialog
        dialog._item = item
        return dialog
    if dialog.exec() == QDialog.Accepted:
        finish_item(window, item, dialog.process())
    return dialog


def _item_colours(items) -> list:
    """The colours what a snapshot was taken of shows: its drawing's own (a
    PDF's line work), else each markup's line, fill and text colour."""
    found = []
    for item in items:
        drawn = getattr(item, "drawing_colours", None)
        if drawn is not None:
            for colour in drawn():
                if colour not in found:
                    found.append(colour)
            continue
        style = getattr(item, "style", None)
        for name in ("stroke", "fill", "text_color"):
            colour = getattr(style, name, "") if style is not None else ""
            if colour and colour.startswith("#") and colour[:7] not in found:
                found.append(colour[:7])
    return found or ["#000000"]


def finish_item(window, item, proc: Process) -> bool:
    from PySide6.QtCore import QBuffer, QIODevice
    from ..items.media import ImageItem
    from ..items.snapshot import SnapshotItem
    document = window.document
    view = window.view
    if isinstance(item, SnapshotItem):
        source = item.source_markups(document)
        if not colorproc.process_items(source, proc):
            window.status_hint.setText("Nothing in that snapshot has those colours")
            return False
        view.begin_snapshot(view.involved_frames(item))
        picture = item.redraw_from(source)
        # a new recording: the undo step and other copies keep the old one
        item.asset_key = document.add_asset(bytes(picture.data()), "qpic")
        view.commit_snapshot("Change Colors")
        item.update()
    elif isinstance(item, ImageItem):
        image = QImage()
        image.loadFromData(document.asset(item.asset_key))
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        colorproc.process_qimage(image, proc).save(buffer, "PNG")
        view.begin_snapshot(view.involved_frames(item))
        item.asset_key = document.add_asset(bytes(buffer.data()), "png")
        item.load_from_document(document)
        view.commit_snapshot("Color Processing")
    else:
        return False
    window.refresh_selection()
    return True
