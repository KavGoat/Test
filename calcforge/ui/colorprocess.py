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

import shiboken6
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QGridLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSlider,
                               QSpinBox, QStackedWidget, QToolButton, QVBoxLayout, QWidget)

from ..io import colorjobs, colorproc
from ..io.colorproc import (BLACK_WHITE, COLORIZE, GRAYSCALE, LSH, MASK, MODIFY, NAMES,
                            Process)

PAGES, SNAPSHOT, PHOTO = "pages", "snapshot", "photo"
NO_COLOR = "No Colour"


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


class _ColourButton(QToolButton):
    """Revu's colour swatch: a small square of the colour (No Color: white,
    a red slash); a click opens the picker (ui/colorpicker.py) — or, for a
    Source Color, the colours found in the drawing (*found*)."""

    def __init__(self, colour: Optional[str], changed, allow_none: bool = False,
                 found: Optional[list] = None, taken=None):
        super().__init__()
        self.taken = taken              # the Source Colors other rows have chosen
        self.colour = colour
        self.changed = changed
        self.allow_none = allow_none
        self.found = found
        self.setFixedSize(26, 24)
        self.setIconSize(QSize(18, 18))
        self.setToolTip("Click to choose the colour")
        self.clicked.connect(self._pick)
        self._show()

    def _show(self):
        from .colorpicker import swatch_icon
        if self.found is not None and not self.colour:
            # a Source Color not chosen yet: Revu's empty grey square
            self.setIcon(swatch_icon("#d4d4d4", 18))
            self.setToolTip("Source Colour: click for the colours in the drawing")
            return
        self.setIcon(swatch_icon(self.colour or "", 18))
        self.setToolTip((self.colour or NO_COLOR).upper() if self.colour else NO_COLOR)

    def _pick(self):
        from .colorpicker import choose, choose_found
        if self.found is not None:
            # a colour already a Source Color in another row is not offered again
            taken = set(self.taken()) if self.taken is not None else set()
            offered = [c for c in self.found if c.lower() not in taken]
            got = choose_found(self, offered, self.colour)
        else:
            got = choose(self, self.colour, self.allow_none)
        if got is None or not shiboken6.isValid(self):
            return
        self.set(got or None)

    def set(self, colour: Optional[str]):
        self.colour = colour
        self._show()
        self.changed()


# Bluebeam's Pages choices
ALL, CURRENT, SELECTED, CUSTOM = "all", "current", "selected", "custom"


class ColorProcessingDialog(QDialog):
    """Bluebeam Revu's Color Processing, laid out as its dialog is: Process
    Type; a Process group holding that type's settings with the Pages to do
    at its foot; Preview, Before and After; OK and Cancel."""

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
        self.setWindowTitle("Change Colours" if mode == SNAPSHOT else "Colour Processing")
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("Process Type:"))
        self.kind = QComboBox()
        kinds = [COLORIZE, MASK] if mode == PHOTO else \
            [MODIFY, COLORIZE, GRAYSCALE, BLACK_WHITE, LSH, MASK]
        for key in kinds:
            self.kind.addItem(NAMES[key], key)
        self.kind.setMinimumWidth(190)
        top.addWidget(self.kind)
        top.addStretch(1)
        layout.addLayout(top)
        # the Process group: the type's settings, then the pages
        self.process_box = QGroupBox("Process")
        process = QVBoxLayout(self.process_box)
        self.pages_stack = QStackedWidget()
        self.page_of = {}
        self.image_boxes: list = []                # each type's own Process Images
        for key in kinds:
            self.page_of[key] = self.pages_stack.addWidget(self._options(key))
        process.addWidget(self.pages_stack, 1)
        pages = QHBoxLayout()
        self.pages_label = QLabel("Pages")
        pages.addWidget(self.pages_label)
        self.pages = QComboBox()
        count = len(document.pages) if document is not None else 1
        self.page_count = count
        self.pages.addItem(f"All Pages (1 - {count})", ALL)
        self.pages.addItem(f"Current Page ({current + 1})", CURRENT)
        if self.selected:
            self.pages.addItem(f"Selected Pages ({len(self.selected)})", SELECTED)
        self.pages.addItem("Custom", CUSTOM)
        self.pages.setMinimumWidth(160)
        self.custom_text = QLineEdit()
        self.custom_text.setPlaceholderText("e.g. 1-3, 5, 9")
        self.custom_text.setFixedWidth(110)
        self.custom_text.setVisible(False)
        self.pages.currentIndexChanged.connect(
            lambda _i: self.custom_text.setVisible(self.pages.currentData() == CUSTOM))
        pages.addWidget(self.pages)
        pages.addWidget(self.custom_text)
        pages.addWidget(QLabel(f"of {count}"))
        pages.addStretch(1)
        self.pages_row = QWidget()
        self.pages_row.setLayout(pages)
        pages.setContentsMargins(0, 0, 0, 0)
        self.pages_row.setVisible(mode == PAGES)
        process.addWidget(self.pages_row)
        layout.addWidget(self.process_box)
        # the preview
        preview = QGroupBox("Preview")
        row = QHBoxLayout(preview)
        self.before = QLabel()
        self.after = QLabel()
        for label, caption in ((self.before, "Before:"), (self.after, "After:")):
            column = QVBoxLayout()
            column.setSpacing(2)
            column.addWidget(QLabel(caption))
            label.setFixedSize(QSize(220, 220))
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("background:#ffffff; border:1px solid #6b6f76;")
            column.addWidget(label)
            row.addLayout(column)
        layout.addWidget(preview)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.pages.setCurrentIndex(self.pages.findData(CURRENT))
        self._timer.timeout.connect(self._preview)
        self.kind.currentIndexChanged.connect(self._kind_changed)
        self.pages.currentIndexChanged.connect(self._changed)
        self._kind_changed()
        # The preview is there as the dialog opens, not a moment after it
        # (exercise round 1, F-27: Before and After were empty at first)
        self._timer.stop()
        self._preview()

    # -- each type's options ----------------------------------------------------------------
    def _side(self, *boxes) -> QVBoxLayout:
        column = QVBoxLayout()
        for box in boxes:
            column.addWidget(box)
        column.addStretch(1)
        return column

    def _process_images(self) -> QCheckBox:
        box = QCheckBox("Process Images")
        box.setToolTip("Change the colours of pictures on the page too")
        box.toggled.connect(self._changed)
        self.image_boxes.append(box)
        return box

    def _options(self, key: str) -> QWidget:
        page = QWidget()
        outer = QHBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        if key == MODIFY:
            # Revu: Source Color and To columns at the left, Add New and
            # Remove at the bottom right. No tolerance: a colour of the line
            # work is changed exactly, each one its own row (the user,
            # 2026-10-14); Mask Images has one, for a picture's near colours.
            left = QVBoxLayout()
            self.pairs_grid = QGridLayout()
            self.pairs_grid.setHorizontalSpacing(8)
            self.pairs_grid.setVerticalSpacing(8)
            self.pairs_grid.addWidget(QLabel("Source Colour:"), 0, 0, Qt.AlignRight)
            self.pairs_grid.addWidget(QLabel("To:"), 0, 2, Qt.AlignRight)
            self.pairs: list = []
            left.addLayout(self.pairs_grid)
            left.addStretch(1)
            outer.addLayout(left)
            outer.addStretch(1)
            right = QVBoxLayout()
            right.addStretch(1)
            buttons = QHBoxLayout()
            self.add_new = QPushButton("Add New")
            self.add_new.clicked.connect(lambda: self.add_pair())
            self.remove = QPushButton("Remove")
            self.remove.clicked.connect(self.remove_pair)
            buttons.addWidget(self.add_new)
            buttons.addWidget(self.remove)
            right.addLayout(buttons)
            outer.addLayout(right)
            self.add_pair(self.colours[0] if self.colours else None)
        elif key in (COLORIZE, GRAYSCALE, BLACK_WHITE):
            form = QGridLayout()
            select = _ColourButton("#000000", self._changed)
            to = _ColourButton("#ffffff", self._changed)
            scale = QCheckBox("Scale Colour")
            scale.setChecked(True)
            scale.setToolTip("Cleared: every colour becomes the Select Colour (white stays white)")
            scale.toggled.connect(self._changed)
            form.addWidget(QLabel("Select Colour:"), 0, 0, Qt.AlignRight)
            form.addWidget(select, 0, 1)
            form.addWidget(QLabel("To:"), 0, 2, Qt.AlignRight)
            form.addWidget(to, 0, 3)
            holder = QVBoxLayout()
            holder.addLayout(form)
            holder.addStretch(1)
            outer.addLayout(holder)
            outer.addStretch(1)
            outer.addLayout(self._side(scale, self._process_images()))
            if key == COLORIZE:
                self.select, self.to, self.scale = select, to, scale
            else:
                # as Revu shows them for these: there, greyed
                for widget in (select, to, scale, form.itemAtPosition(0, 0).widget(),
                               form.itemAtPosition(0, 2).widget()):
                    widget.setEnabled(False)
                if key == BLACK_WHITE:
                    select.colour, to.colour = "#000000", "#ffffff"
        elif key == LSH:
            grid = QGridLayout()
            self.sliders = {}
            for r, (name, low, high) in enumerate((("Luminosity", -100, 100),
                                                   ("Saturation", -100, 100),
                                                   ("Hue", -180, 180))):
                slider = QSlider(Qt.Horizontal)
                slider.setRange(low, high)
                slider.setMinimumWidth(150)
                value = QLabel("0")
                value.setFixedWidth(34)
                slider.valueChanged.connect(lambda v, lab=value: (lab.setText(str(v)),
                                                                   self._changed()))
                grid.addWidget(QLabel(f"{name}:"), r, 0)
                grid.addWidget(slider, r, 1)
                grid.addWidget(value, r, 2)
                self.sliders[name] = slider
            holder = QVBoxLayout()
            holder.addLayout(grid)
            holder.addStretch(1)
            outer.addLayout(holder)
            outer.addStretch(1)
            outer.addLayout(self._side(self._process_images()))
        elif key == MASK:
            row = QHBoxLayout()
            self.mask = _ColourButton("#ffffff", self._changed)
            self.mask_tolerance = QSpinBox()
            self.mask_tolerance.setRange(0, 100)
            self.mask_tolerance.setToolTip("How close a colour must be to the Mask Colour (%)")
            self.mask_tolerance.valueChanged.connect(self._changed)
            row.addWidget(QLabel("Mask Colour:"))
            row.addWidget(self.mask)
            row.addWidget(QLabel("±"))
            row.addWidget(self.mask_tolerance)
            row.addStretch(1)
            holder = QVBoxLayout()
            holder.addLayout(row)
            note = QLabel("Markups are not processed.")
            note.setEnabled(False)
            holder.addWidget(note)
            holder.addStretch(1)
            outer.addLayout(holder, 1)
        return page

    def add_pair(self, source: Optional[str] = None, target: Optional[str] = "#ff0000") -> None:
        r = len(self.pairs)
        src = _ColourButton(source, self._changed, found=list(self.colours))
        src.taken = lambda me=src: [s.colour.lower() for _h, s, _t in self.pairs
                                    if s is not me and s.colour]
        src.setToolTip("Source Colour: click for the colours in the drawing")
        to = _ColourButton(target, self._changed, allow_none=True)
        self.pairs_grid.addWidget(src, r, 1)
        self.pairs_grid.addWidget(to, r, 3)
        self.pairs.append((None, src, to))
        self.remove.setEnabled(len(self.pairs) > 1)
        self._changed()

    def remove_pair(self) -> None:
        if len(self.pairs) > 1:
            _h, src, to = self.pairs.pop()
            src.deleteLater()
            to.deleteLater()
            self.remove.setEnabled(len(self.pairs) > 1)
            self._changed()

    # -- reading it -----------------------------------------------------------------------------
    @property
    def images(self) -> QCheckBox:
        """The Process Images box of the type shown."""
        page = self.pages_stack.currentWidget()
        for box in self.image_boxes:
            if page is not None and page.isAncestorOf(box):
                return box
        return self.image_boxes[0] if self.image_boxes else QCheckBox()

    def process(self) -> Process:
        kind = self.kind.currentData()
        proc = Process(kind, images=self.images.isChecked())
        if kind == MODIFY:
            proc.pairs = [(src.colour, to.colour) for _h, src, to in self.pairs if src.colour]
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
        which = self.pages.currentData()
        if self.kind.currentData() == MODIFY or which == CURRENT:
            return [self.current]
        if which == ALL:
            return list(range(count))
        if which == SELECTED:
            return sorted(self.selected)
        return parse_pages(self.custom_text.text(), count)

    def _kind_changed(self, *_):
        kind = self.kind.currentData()
        self.pages_stack.setCurrentIndex(self.page_of[kind])
        self.process_box.setTitle("Mask Images" if kind == MASK else "Process")
        # Bluebeam: Modify Colors applies to the current page only
        self.pages_row.setVisible(self.mode == PAGES and kind != MODIFY)
        self._changed()

    def _changed(self, *_):
        self._timer.start(200)

    def _preview(self):
        proc = self.process()
        if hasattr(self.previewer, "submit"):
            # worked out by the helper; a later change overtakes it
            self._asked = getattr(self, "_asked", 0) + 1
            asked, future = self._asked, self.previewer.submit(proc)
            self._show(self.previewer.before, None)

            def look():
                if not shiboken6.isValid(self) or asked != self._asked:
                    return
                if not future.done():
                    QTimer.singleShot(40, look)
                    return
                self._show(*self.previewer.finish(future))
            look()
            return
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
        self._show(before, after)

    def _show(self, before, after):
        for label, image in ((self.before, before), (self.after, after)):
            if image is None or image.isNull():
                label.clear()
                if label is self.after and before is not None and not before.isNull():
                    label.setText("Working…")       # the helper is still at it
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


def _image(raw) -> QImage:
    width, height, stride, samples = raw
    return QImage(samples, width, height, stride, QImage.Format_RGB888).copy()


class _PagePreview:
    """Before and after of a PDF page, the after worked out by the helper
    process (io/colorjobs.py) so the dialog never stops answering."""

    def __init__(self, single: bytes):
        self.single = single
        self.before = _image(colorjobs.render(single, 0))

    def submit(self, proc):
        return colorjobs.submit(colorjobs.preview, self.single, proc)

    def finish(self, future):
        try:
            return self.before, _image(colorjobs.result(future, colorjobs.preview,
                                                        self.single))
        except Exception:  # noqa: BLE001
            return self.before, self.before


def page_previewer(window, page):
    """Before and after of a page, for the dialog's Preview."""
    document = window.document
    if page.pdf_key and page.pdf_page_index is not None:
        data = document.asset(page.pdf_key)
        if data:
            return _PagePreview(_one_page(data, int(page.pdf_page_index)))
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
        wanted = sorted({int(p.pdf_page_index) for p in pages})
        done = colorjobs.wait(colorjobs.submit(colorjobs.process, data, wanted, proc), window,
                              "Changing the colours…", colorjobs.process, data, wanted, proc)
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
    window._structural_change("Colour Processing", mutate, preserve_view=True)
    return len(changed)


#: The colours each page's drawing sets, kept: read once, the list opens at once.
_COLOURS: dict = {}


def page_colours(window, page) -> list:
    """The colours this page's own drawing sets (not another page's)."""
    key = (page.pdf_key, int(page.pdf_page_index))
    if key not in _COLOURS:
        data = window.document.asset(page.pdf_key)
        index = int(page.pdf_page_index)
        _COLOURS[key] = colorjobs.wait(colorjobs.submit(colorjobs.colours, data, index), window,
                                       "Reading the page's colours…", colorjobs.colours, data,
                                       index)
        if len(_COLOURS) > 64:
            _COLOURS.pop(next(iter(_COLOURS)))
    return list(_COLOURS[key])


def color_processing(window, index: Optional[int] = None) -> Optional[ColorProcessingDialog]:
    """Document ▸ Color Processing (Bluebeam's), from the page in view."""
    from .dialogs import QMessageBox
    which = window.page_index(index)
    page = window.document.pages[which]
    if not (page.pdf_key or page.background_key):
        QMessageBox.information(window, "Colour Processing",
                                "This page has no drawing of its own to process: it is a blank "
                                "sheet, and markups keep their own colours.")
        return None
    colours = ["#000000"]
    if page.pdf_key and page.pdf_page_index is not None:
        try:
            colours = page_colours(window, page) or colours
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
    from . import release
    release.done_with(dialog)          # answered: it and its document go
    return dialog


def finish_pages(window, dialog: ColorProcessingDialog) -> int:
    indexes = dialog.page_indexes(len(window.document.pages))
    if not indexes:
        return 0
    count = apply_to_pages(window, indexes, dialog.process())
    window.status_hint.setText(f"Colour Processing: {count} page{'s' * (count != 1)} processed"
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
            QMessageBox.information(window, "Change Colours",
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
        dialog._preview()                # the snapshot's own after, from the start
    elif isinstance(item, ImageItem):
        image = QImage()
        data = window.document.asset(item.asset_key)
        if not data or not image.loadFromData(data) or image.isNull():
            QMessageBox.information(window, "Colour Processing", "There is no picture in this one.")
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
    from . import release
    release.done_with(dialog)
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
        view.commit_snapshot("Change Colours")
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
        view.commit_snapshot("Colour Processing")
    else:
        return False
    window.refresh_selection()
    return True
