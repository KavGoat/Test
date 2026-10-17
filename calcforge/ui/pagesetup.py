"""Revu's Page Setup (Document ▸ Page Setup…): new paper for the pages, and
their content resized onto it (the user's decision, 2026-10-15: "Page Setup
follows Revu's layout and really resizes the content (Auto Scale, Scale,
Offset, Rotation, Center, Fit to Media), with a preview and a Pages range").

The dialog is laid out as Revu 21's Crop and Page Setup ▸ Page Setup tab:

- **Change Media Size (mm)**: Media Size (<Default Page Size> — each page
  keeps its own — the standard sizes, or Custom Page Size), Portrait or
  Landscape, Width and Height; Offset X and Y; Scale with Auto Scale;
  Rotation with Get Line; Clear, Centre and Fit to Media.
- **Pages**: Revu's shared range (widgets.PagesRange).
- **Margins (CalcForge)**: CalcForge's own calculation-layout margins, kept
  from the old dialog in a group of their own.
- **Preview**: the media, the page and the scale, the page drawn where it
  will land on the paper, and a page navigator.

What it does to a page (:func:`place`): the page's whole content — the PDF
drawing, its markups, equations, tables, pictures and viewports — is turned
by the Rotation, scaled by the Scale and put at the Offset on the new paper.
Offset X and Y are measured from the paper's top-left corner to the top-left
of the turned, scaled page. Rotation is in degrees anticlockwise. Auto Scale
(and Fit to Media) scale each page to fit its paper; Centre and Fit to Media
place it on its paper by the alignment chosen, page by page.

The file changes with it (io/pdfresize.py), so the saved PDF shows the
result in any reader; markups stay where they were on the drawing; a
measured length keeps its real value because the page's scale is adjusted
by the same factor; and the whole change is one undo step.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPalette, QPen, QTransform
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QDoubleSpinBox, QGridLayout,
                               QGroupBox, QHBoxLayout, QLabel, QMenu, QPushButton,
                               QRadioButton, QSizePolicy, QToolButton, QVBoxLayout,
                               QWidget)

from ..core.document import (LANDSCAPE, MM_TO_PT, PAGE_SIZES, PORTRAIT, PT_TO_MM,
                             PageScale, PageSetup)
from .widgets import PagesRange

DEFAULT_SIZE = "<Default Page Size>"
CUSTOM_SIZE = "Custom Page Size"

#: Fit to Media's alignments: where the page goes on its paper, as fractions
#: of the room left across and down.
ALIGNMENTS = (("top_left", "Top Left", (0.0, 0.0)),
              ("top_centre", "Top Centre", (0.5, 0.0)),
              ("top_right", "Top Right", (1.0, 0.0)),
              ("centre_left", "Centre Left", (0.0, 0.5)),
              ("centre", "Centre", (0.5, 0.5)),
              ("centre_right", "Centre Right", (1.0, 0.5)),
              ("bottom_left", "Bottom Left", (0.0, 1.0)),
              ("bottom_centre", "Bottom Centre", (0.5, 1.0)),
              ("bottom_right", "Bottom Right", (1.0, 1.0)))
_ALIGN = {key: where for key, _name, where in ALIGNMENTS}
MARGIN_KEYS = ("margin_left", "margin_top", "margin_right", "margin_bottom")


# ---------------------------------------------------------------------------
# what was chosen, and what it does to one page
# ---------------------------------------------------------------------------

@dataclass
class Plan:
    """Everything Page Setup was told.

    *media* is (size name, width mm, height mm, orientation) or None for
    each page's own size; *fit* scales each page to its paper (Auto Scale,
    Fit to Media), else *scale* (1.0 is 100 %); *align* places each page on
    its paper (Centre, Fit to Media), else *offset_mm* from the top-left;
    *rotation* is degrees anticlockwise; *margins* are CalcForge's
    calculation margins in mm, or None to leave each page's own.
    """

    media: Optional[tuple] = None
    fit: bool = False
    scale: float = 1.0
    offset_mm: tuple = (0.0, 0.0)
    align: Optional[str] = None
    rotation: float = 0.0
    margins: Optional[dict] = None
    #: True when the content is to stay where it is on the page whatever
    #: else changes (the Page panel's paper boxes; the Paper Size menu)
    keep_content: bool = False


def setup_for(page_setup: PageSetup, plan: Plan) -> PageSetup:
    """The paper a page gets: its own, or the media chosen; its margins, or
    the ones chosen."""
    setup = PageSetup.from_dict(page_setup.to_dict())
    if plan.media is not None:
        name, width, height, orientation = plan.media
        setup.size_name = name
        setup.width_mm = float(width)
        setup.height_mm = float(height)
        setup.orientation = orientation
    if plan.margins:
        for key in MARGIN_KEYS:
            if key in plan.margins:
                setattr(setup, key, float(plan.margins[key]))
    return setup


def _turned_box(width: float, height: float, degrees: float) -> tuple:
    """The page's box turned *degrees* anticlockwise, at scale 1: its width,
    height and the top-left of the turned corners."""
    angle = math.radians(degrees)
    cos, sin = math.cos(angle), math.sin(angle)
    if abs(cos) < 1e-12:
        cos = 0.0
    if abs(sin) < 1e-12:
        sin = 0.0
    xs = (0.0, width * cos, height * sin, width * cos + height * sin)
    ys = (0.0, -width * sin, height * cos, -width * sin + height * cos)
    return max(xs) - min(xs), max(ys) - min(ys), min(xs), min(ys), cos, sin


def place(old_w: float, old_h: float, new_w: float, new_h: float,
          plan: Plan) -> tuple:
    """Where a page *old_w* by *old_h* points lands on paper *new_w* by
    *new_h*: (scale, offset x pt, offset y pt, QTransform from the old page
    to the new, both in page points with y down)."""
    if plan.keep_content:
        return 1.0, 0.0, 0.0, QTransform()
    wide, high, left, top, cos, sin = _turned_box(old_w, old_h, plan.rotation)
    if plan.fit:
        scale = min(new_w / max(wide, 1e-6), new_h / max(high, 1e-6))
    else:
        scale = float(plan.scale)
    scale = max(scale, 1e-4)
    if plan.align in _ALIGN:
        across, down = _ALIGN[plan.align]
        x = (new_w - scale * wide) * across
        y = (new_h - scale * high) * down
    else:
        x, y = (float(v) * MM_TO_PT for v in plan.offset_mm)
    transform = QTransform(scale * cos, -scale * sin, scale * sin, scale * cos,
                           x - scale * left, y - scale * top)
    return scale, x, y, transform


def level_rotation(start: QPointF, end: QPointF) -> float:
    """Get Line: the Rotation (degrees anticlockwise) that makes the line
    from *start* to *end* — page points, y down — level; the smaller turn."""
    dx, dy = end.x() - start.x(), end.y() - start.y()
    if math.hypot(dx, dy) < 1e-6:
        return 0.0
    angle = math.degrees(math.atan2(dy, dx))        # clockwise on screen
    while angle > 90:
        angle -= 180
    while angle <= -90:
        angle += 180
    return round(angle, 2)


def is_identity(transform: QTransform) -> bool:
    return (abs(transform.m11() - 1) < 1e-9 and abs(transform.m22() - 1) < 1e-9
            and abs(transform.m12()) < 1e-9 and abs(transform.m21()) < 1e-9
            and abs(transform.dx()) < 1e-6 and abs(transform.dy()) < 1e-6)


def rescaled(scale: PageScale, factor: float, quarter_turned: bool) -> PageScale:
    """A page's (or viewport's) scale once its drawing is *factor* times the
    size on the paper — so a length measured on it reads what it did. A
    drawing turned a quarter turn swaps a Separate Y scale over."""
    new = PageScale.from_dict(scale.to_dict())
    if not scale.is_calibrated():
        return new                  # a paper length is a paper length
    per_point = scale.length_per_pt
    y_factor = scale.y_factor
    if quarter_turned and abs(y_factor - 1.0) > 1e-12:
        per_point = per_point * y_factor
        y_factor = 1.0 / y_factor
    new.length_per_pt = per_point / factor
    new.y_factor = y_factor
    new.label = _relabelled(scale, new, factor)
    return new


def _relabelled(old: PageScale, new: PageScale, factor: float) -> str:
    import re
    label = old.label or ""
    if re.fullmatch(r"1:[\d.eE+-]+", label) or re.fullmatch(r"X 1:.+, Y 1:.+", label):
        ratio, y_ratio = new.ratio(), new.y_ratio()
        if ratio:
            if new.separate_y() and y_ratio:
                return f"X 1:{ratio:.6g}, Y 1:{y_ratio:.6g}"
            return f"1:{ratio:.6g}"
    match = re.fullmatch(r"([\d.]+) (mm|cm|in|pt) = (.+)", label)
    if match:                                       # Set Scale's custom one
        return f"{float(match.group(1)) * factor:.6g} {match.group(2)} = {match.group(3)}"
    match = re.fullmatch(r"(.+) = ([\d.]+) pt", label)
    if match:                                       # a calibration
        return f"{match.group(1)} = {float(match.group(2)) * factor:.1f} pt"
    return label


# ---------------------------------------------------------------------------
# the dialog
# ---------------------------------------------------------------------------

def _spin(low: float, high: float, decimals: int, suffix: str, name: str,
          width: int = 84) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(low, high)
    spin.setDecimals(decimals)
    spin.setSuffix(suffix)
    spin.setObjectName(name)
    spin.setKeyboardTracking(False)
    spin.setMinimumWidth(width)
    spin.setAccelerated(True)
    return spin


class PageSetupDialog(QDialog):
    """Revu's Page Setup. Built, filled and read without being shown, so
    the window's command — and the tests — set its fields and accept it.

    Get Line closes it with PICK: the window hands over to a line drag on
    the drawing and opens it again as it was, with the Rotation that makes
    the dragged line level.
    """

    PICK = QDialog.Accepted + 10

    def __init__(self, setup: PageSetup, parent=None, multiple_pages: bool = False, *,
                 document=None, current: int = 0, selected=None,
                 state: Optional[dict] = None):
        super().__init__(parent)
        self.setWindowTitle("Page Setup")
        self.setObjectName("pageSetupDialog")
        self.document = document
        pages = list(document.pages) if document is not None else []
        self.count = max(len(pages), 2 if multiple_pages else 1)
        self.current = min(max(int(current), 0), self.count - 1)
        self.setup = PageSetup.from_dict(
            (pages[self.current].setup if pages else setup).to_dict())
        self._fit = False
        self._align: Optional[str] = None
        self._filling = True
        self._pictures: dict = {}
        self.preview_index = self.current
        self.picking = False

        outer = QVBoxLayout(self)
        body = QHBoxLayout()
        body.setSpacing(10)
        outer.addLayout(body)
        left = QVBoxLayout()
        left.setSpacing(8)
        body.addLayout(left, 0)

        # -- Change Media Size (mm) ------------------------------------------
        media = QGroupBox("Change Media Size (mm)")
        media.setObjectName("pageSetupMedia")
        grid = QGridLayout(media)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        row = 0
        self.media = QComboBox()
        self.media.setObjectName("pageSetupMediaSize")
        self.media.addItem(DEFAULT_SIZE, None)
        for name in PAGE_SIZES:
            self.media.addItem(name, name)
        self.media.addItem(CUSTOM_SIZE, "custom")
        self.media.setToolTip("The paper the pages are to be on; <Default Page Size> "
                              "keeps each page's own")
        label = QLabel("&Media Size:")
        label.setBuddy(self.media)
        grid.addWidget(label, row, 0)
        grid.addWidget(self.media, row, 1, 1, 3)
        row += 1
        self.portrait = QRadioButton("Portrait")
        self.portrait.setObjectName("pageSetupPortrait")
        self.landscape = QRadioButton("Landscape")
        self.landscape.setObjectName("pageSetupLandscape")
        turn = QButtonGroup(self)
        turn.addButton(self.portrait)
        turn.addButton(self.landscape)
        grid.addWidget(self.portrait, row, 1)
        grid.addWidget(self.landscape, row, 3)
        row += 1
        self.width_box = _spin(20, 5000, 1, " mm", "pageSetupWidth")
        self.height_box = _spin(20, 5000, 1, " mm", "pageSetupHeight")
        self._width_label = QLabel("Width:")
        self._height_label = QLabel("Height:")
        grid.addWidget(self._width_label, row, 0)
        grid.addWidget(self.width_box, row, 1)
        grid.addWidget(self._height_label, row, 2, Qt.AlignRight)
        grid.addWidget(self.height_box, row, 3)
        row += 1
        self.offset_x = _spin(-5000, 5000, 1, " mm", "pageSetupOffsetX")
        self.offset_y = _spin(-5000, 5000, 1, " mm", "pageSetupOffsetY")
        self.offset_x.setToolTip("How far the page sits in from the paper's left edge")
        self.offset_y.setToolTip("How far the page sits down from the paper's top edge")
        label = QLabel("&Offset:  X:")
        label.setBuddy(self.offset_x)
        grid.addWidget(label, row, 0)
        grid.addWidget(self.offset_x, row, 1)
        grid.addWidget(QLabel("Y:"), row, 2, Qt.AlignRight)
        grid.addWidget(self.offset_y, row, 3)
        row += 1
        self.scale_box = _spin(0.01, 10000, 2, "", "pageSetupScale")
        self.scale_box.setToolTip("The page's size on the paper, in per cent")
        self.auto_scale = QCheckBox("Auto Scale")
        self.auto_scale.setObjectName("pageSetupAutoScale")
        self.auto_scale.setToolTip("Scale each page up or down to fit its paper, "
                                   "in the middle of it")
        label = QLabel("&Scale (%):")
        label.setBuddy(self.scale_box)
        grid.addWidget(label, row, 0)
        grid.addWidget(self.scale_box, row, 1)
        grid.addWidget(self.auto_scale, row, 2, 1, 2)
        row += 1
        self.rotation = _spin(-360, 360, 2, "°", "pageSetupRotation")
        self.rotation.setToolTip("Turn the drawing on the paper, in degrees anticlockwise")
        self.get_line = QPushButton("Get Line")
        self.get_line.setObjectName("pageSetupGetLine")
        self.get_line.setToolTip("Drag along a line on the drawing: the Rotation "
                                 "becomes what makes that line level")
        self.get_line.setEnabled(document is not None)
        label = QLabel("&Rotation:")
        label.setBuddy(self.rotation)
        grid.addWidget(label, row, 0)
        grid.addWidget(self.rotation, row, 1)
        grid.addWidget(self.get_line, row, 2, 1, 2)
        row += 1
        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.clear_button = QPushButton("Clear")
        self.clear_button.setObjectName("pageSetupClear")
        self.clear_button.setToolTip("Reset the Offset, Scale and Rotation")
        self.centre_button = QPushButton("Centre")
        self.centre_button.setObjectName("pageSetupCentre")
        self.centre_button.setToolTip("Put each page in the middle of its paper")
        self.fit_button = QToolButton()
        self.fit_button.setObjectName("pageSetupFit")
        self.fit_button.setText("Fit to Media")
        self.fit_button.setToolTip("Scale each page to fit its paper; the arrow "
                                   "chooses where on the paper it goes")
        self.fit_button.setPopupMode(QToolButton.MenuButtonPopup)
        self.fit_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.fit_menu = QMenu(self.fit_button)
        self.fit_menu.setObjectName("pageSetupFitMenu")
        self.fit_actions = {}
        for key, name, _where in ALIGNMENTS:
            action = self.fit_menu.addAction(name)
            action.setData(key)
            action.triggered.connect(lambda _c=False, k=key: self.fit_to_media(k))
            self.fit_actions[key] = action
        self.fit_button.setMenu(self.fit_menu)
        self.fit_button.clicked.connect(lambda: self.fit_to_media("centre"))
        for button in (self.clear_button, self.centre_button):
            button.setAutoDefault(False)
        self.get_line.setAutoDefault(False)
        actions.addWidget(self.clear_button)
        actions.addWidget(self.centre_button)
        actions.addWidget(self.fit_button)
        grid.addLayout(actions, row, 0, 1, 4)
        left.addWidget(media)

        # -- Pages ----------------------------------------------------------
        selected = sorted(selected or [])
        self.pages = PagesRange(self.count, self.current, selected,
                                default=PagesRange.SELECTED if selected
                                else PagesRange.CURRENT)
        self.pages.setObjectName("pageSetupPages")
        pages_row = QHBoxLayout()
        label = QLabel("&Pages:")
        label.setBuddy(self.pages.combo)
        pages_row.addWidget(label)
        pages_row.addWidget(self.pages, 1)
        left.addLayout(pages_row)

        # -- Margins (CalcForge) -------------------------------------------------------------
        margins = QGroupBox("Margins (CalcForge)")
        margins.setObjectName("pageSetupMargins")
        margins.setToolTip("Where equations and tables are laid out on a page "
                           "written in CalcForge")
        margin_grid = QGridLayout(margins)
        margin_grid.setHorizontalSpacing(8)
        margin_grid.setVerticalSpacing(6)
        self.margins: dict = {}
        for index, (key, name) in enumerate((("margin_left", "Left:"),
                                             ("margin_top", "Top:"),
                                             ("margin_right", "Right:"),
                                             ("margin_bottom", "Bottom:"))):
            spin = _spin(0, 100, 1, " mm", f"pageSetup_{key}", width=76)
            spin.setValue(getattr(self.setup, key))
            r, c = divmod(index, 2)
            margin_grid.addWidget(QLabel(name), r, c * 2)
            margin_grid.addWidget(spin, r, c * 2 + 1)
            self.margins[key] = spin
        self._margins_were = {key: spin.value() for key, spin in self.margins.items()}
        left.addWidget(margins)
        left.addStretch(1)

        # -- Preview --------------------------------------------------------
        preview = QGroupBox("Preview")
        preview.setObjectName("pageSetupPreview")
        column = QVBoxLayout(preview)
        heads = QGridLayout()
        heads.setHorizontalSpacing(12)
        heads.setVerticalSpacing(0)
        self.media_value = QLabel()
        self.page_value = QLabel()
        self.scale_value = QLabel()
        for c, (title, value, align) in enumerate((("Media Size", self.media_value, Qt.AlignLeft),
                                                   ("Page Size", self.page_value, Qt.AlignHCenter),
                                                   ("Scale", self.scale_value, Qt.AlignRight))):
            heading = QLabel(title)
            heads.addWidget(heading, 0, c, align)
            heads.addWidget(value, 1, c, align)
        column.addLayout(heads)
        self.preview = _Preview(self)
        column.addWidget(self.preview, 1)
        navigate = QHBoxLayout()
        navigate.setSpacing(2)
        self.first_page = self._nav_button("⏮", "First page", lambda: self.show_page(0, step=0))
        self.previous_page = self._nav_button("◀", "Previous page",
                                              lambda: self.show_page(None, step=-1))
        self.page_label = QLabel()
        self.page_label.setObjectName("pageSetupPreviewPage")
        self.page_label.setAlignment(Qt.AlignCenter)
        self.page_label.setMinimumWidth(120)
        self.page_label.setFrameShape(QLabel.StyledPanel)
        self.next_page = self._nav_button("▶", "Next page", lambda: self.show_page(None, step=1))
        self.last_page = self._nav_button("⏭", "Last page", lambda: self.show_page(-1, step=0))
        navigate.addStretch(1)
        for widget in (self.first_page, self.previous_page, self.page_label,
                       self.next_page, self.last_page):
            navigate.addWidget(widget)
        navigate.addStretch(1)
        column.addLayout(navigate)
        body.addWidget(preview, 1)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)

        # -- as the page is now -----------------------------------------------------------
        self.scale_box.setValue(100.0)
        self.auto_scale.setChecked(True)               # Revu's: ticked
        self._fit, self._align = True, "centre"
        self._show_media()

        self.media.currentIndexChanged.connect(self._media_changed)
        self.portrait.toggled.connect(self._turned)
        self.width_box.valueChanged.connect(self._size_typed)
        self.height_box.valueChanged.connect(self._size_typed)
        self.offset_x.valueChanged.connect(self._offset_typed)
        self.offset_y.valueChanged.connect(self._offset_typed)
        self.scale_box.valueChanged.connect(self._scale_typed)
        self.auto_scale.toggled.connect(self._auto_toggled)
        self.rotation.valueChanged.connect(lambda _v: self._placed())
        self.get_line.clicked.connect(self.start_get_line)
        self.clear_button.clicked.connect(self.clear)
        self.centre_button.clicked.connect(self.centre)
        self.pages.combo.currentIndexChanged.connect(lambda _i: self._pages_changed())
        self.pages.range.textChanged.connect(lambda _t: self._pages_changed())
        self._filling = False
        if state:
            self.restore(state)
        self._placed()
        self.setMinimumWidth(720)

    def _nav_button(self, text: str, tip: str, slot) -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tip)
        button.setAutoRaise(True)
        button.clicked.connect(slot)
        return button

    # -- the pages ------------------------------------------------------------------------
    def page_indexes(self):
        return self.pages.page_indexes()

    def accept(self) -> None:
        """OK: only once the pages read, as Set Scale's Apply."""
        if self.document is not None and not self.page_indexes():
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Page Setup",
                                "Enter pages to set up, such as 1-3, 5.")
            return
        super().accept()

    def _page(self, index: Optional[int] = None):
        if self.document is None or not self.document.pages:
            return None
        index = self.preview_index if index is None else index
        return self.document.pages[min(max(index, 0), len(self.document.pages) - 1)]

    def _page_setup(self, index: Optional[int] = None) -> PageSetup:
        page = self._page(index)
        return page.setup if page is not None else self.setup

    def _pages_changed(self) -> None:
        chosen = self.pages.page_indexes() or []
        if chosen and self.preview_index not in chosen:
            self.preview_index = chosen[0]
        self._placed()

    def show_page(self, index: Optional[int], step: int = 0) -> None:
        """The preview's page navigator: the first, previous, next or last of
        the pages chosen."""
        chosen = self.pages.page_indexes() or [self.current]
        if index is not None:
            target = chosen[index] if -len(chosen) <= index < len(chosen) else chosen[0]
        else:
            here = chosen.index(self.preview_index) if self.preview_index in chosen else 0
            target = chosen[min(max(here + step, 0), len(chosen) - 1)]
        self.preview_index = target
        self._placed()

    # -- the media ------------------------------------------------------------------------
    def _show_media(self) -> None:
        """Width, Height and the orientation for what Media Size says."""
        was, self._filling = self._filling, True
        try:
            data = self.media.currentData()
            custom = data == "custom"
            own = data is None
            if own:
                setup = self._page_setup()
                width, height = setup.width_pt * PT_TO_MM, setup.height_pt * PT_TO_MM
            elif custom:
                width, height = self.width_box.value(), self.height_box.value()
            else:
                width, height = PAGE_SIZES[data]
                if self.landscape.isChecked():
                    width, height = height, width
            self.width_box.setValue(width)
            self.height_box.setValue(height)
            wide = width > height
            self.landscape.setChecked(wide)
            self.portrait.setChecked(not wide)
            for widget in (self.portrait, self.landscape):
                widget.setEnabled(not own)
            for widget in (self.width_box, self.height_box, self._width_label,
                           self._height_label):
                widget.setEnabled(custom)
        finally:
            self._filling = was

    def _media_changed(self, _index: int = 0) -> None:
        if self._filling:
            return
        data = self.media.currentData()
        if data not in (None, "custom"):
            # a standard size comes in the way the page in view is turned
            setup = self._page_setup()
            wide = setup.width_pt > setup.height_pt
            was, self._filling = self._filling, True
            self.landscape.setChecked(wide)
            self.portrait.setChecked(not wide)
            self._filling = was
        self._show_media()
        self._placed()

    def _turned(self, _on: bool) -> None:
        if self._filling:
            return
        width, height = self.width_box.value(), self.height_box.value()
        wide = self.landscape.isChecked()
        if (width > height) != wide:
            was, self._filling = self._filling, True
            self.width_box.setValue(height)
            self.height_box.setValue(width)
            self._filling = was
        self._placed()

    def _size_typed(self, _value: float) -> None:
        if self._filling:
            return
        was, self._filling = self._filling, True
        wide = self.width_box.value() > self.height_box.value()
        self.landscape.setChecked(wide)
        self.portrait.setChecked(not wide)
        self._filling = was
        self._placed()

    def media_size(self) -> Optional[tuple]:
        """(name, width mm, height mm, orientation) as a PageSetup keeps it,
        or None for each page's own."""
        data = self.media.currentData()
        if data is None:
            return None
        width, height = self.width_box.value(), self.height_box.value()
        orientation = LANDSCAPE if width > height else PORTRAIT
        if data == "custom":
            return ("Custom", min(width, height), max(width, height), orientation)
        portrait_w, portrait_h = PAGE_SIZES[data]
        return (data, portrait_w, portrait_h, orientation)

    def choose_media(self, name: str, landscape: Optional[bool] = None) -> None:
        """Pick a Media Size by what it says ("A3", "Custom Page Size",
        "<Default Page Size>"), and the orientation."""
        index = self.media.findText(name)
        if index >= 0:
            self.media.setCurrentIndex(index)
        if landscape is not None:
            (self.landscape if landscape else self.portrait).setChecked(True)

    # -- Offset, Scale, Rotation, Clear, Centre, Fit to Media ---------------------------------------
    def _offset_typed(self, _value: float) -> None:
        if self._filling:
            return
        self._align = None
        self._placed()

    def _scale_typed(self, _value: float) -> None:
        if self._filling:
            return
        self._fit = False
        was, self._filling = self._filling, True
        self.auto_scale.setChecked(False)
        self._filling = was
        self._placed()

    def _auto_toggled(self, on: bool) -> None:
        if self._filling:
            return
        self._fit = bool(on)
        if on:
            self._align = "centre"
        self._placed()

    def clear(self) -> None:
        """Revu's Clear: the Offset, Scale and Rotation back to none."""
        self._fit, self._align = False, None
        was, self._filling = self._filling, True
        self.auto_scale.setChecked(False)
        self.scale_box.setValue(100.0)
        self.offset_x.setValue(0.0)
        self.offset_y.setValue(0.0)
        self.rotation.setValue(0.0)
        self._filling = was
        self._placed()

    def centre(self) -> None:
        """Revu's Centre: each page in the middle of its paper, at its scale."""
        self._align = "centre"
        self._placed()

    def fit_to_media(self, align: str = "centre") -> None:
        """Revu's Fit to Media: each page scaled to fit its paper, put where
        *align* says (one of ALIGNMENTS)."""
        self._fit = True
        self._align = align if align in _ALIGN else "centre"
        was, self._filling = self._filling, True
        self.auto_scale.setChecked(True)
        self._filling = was
        self._placed()

    def start_get_line(self) -> None:
        """Get Line: drag along a line on the drawing, and come back."""
        self.picking = True
        self.done(self.PICK)

    def set_line(self, start: QPointF, end: QPointF) -> None:
        """The Rotation that makes the line from *start* to *end* (page
        points, y down) level."""
        if math.hypot(end.x() - start.x(), end.y() - start.y()) < 1e-6:
            return
        self.rotation.setValue(level_rotation(start, end))

    # -- what it comes to ------------------------------------------------------------------------
    def plan(self) -> Plan:
        margins = {key: spin.value() for key, spin in self.margins.items()}
        changed = any(abs(margins[key] - self._margins_were[key]) > 1e-9 for key in margins)
        return Plan(media=self.media_size(), fit=self._fit,
                    scale=self.scale_box.value() / 100.0,
                    offset_mm=(self.offset_x.value(), self.offset_y.value()),
                    align=self._align, rotation=self.rotation.value(),
                    margins=margins if changed else None)

    def result_setup(self) -> PageSetup:
        """The paper the page in view gets (what the old dialog gave)."""
        return setup_for(self._page_setup(self.current), self.plan())

    def placement(self, index: Optional[int] = None) -> tuple:
        """(scale, offset x pt, offset y pt, transform, new setup) for a page."""
        setup = self._page_setup(index)
        new = setup_for(setup, self.plan())
        return place(setup.width_pt, setup.height_pt, new.width_pt, new.height_pt,
                     self.plan()) + (new,)

    def _placed(self) -> None:
        """Bring the fields Auto Scale, Centre and Fit to Media work out, and
        the preview, up to date for the page in view."""
        if self._filling:
            return
        if self.media.currentData() is None:
            self._show_media()                 # the page in view's own paper
        scale, x, y, _transform, new = self.placement()
        was, self._filling = self._filling, True
        try:
            if self._fit:
                self.scale_box.setValue(scale * 100.0)
            if self._align is not None:
                self.offset_x.setValue(x * PT_TO_MM)
                self.offset_y.setValue(y * PT_TO_MM)
        finally:
            self._filling = was
        old = self._page_setup()
        self.media_value.setText(f"{new.width_pt * PT_TO_MM:.1f} × {new.height_pt * PT_TO_MM:.1f}")
        self.page_value.setText(f"{old.width_pt * PT_TO_MM:.1f} × {old.height_pt * PT_TO_MM:.1f}")
        self.scale_value.setText(f"{scale * 100.0:.2f}%")
        page = self._page()
        label = (page.label or "") if page is not None else ""
        number = self.preview_index + 1
        self.page_label.setText(f"{number} - {label}" if label else f"Page {number}")
        self.page_label.setToolTip(self.page_label.text())
        self.preview.update()

    # -- the preview's picture -------------------------------------------------
    def picture(self) -> Optional[QImage]:
        """The page in view, drawn small, once."""
        page = self._page()
        if page is None or page.frame is None:
            return None
        kept = self._pictures.get(self.preview_index)
        if kept is None:
            longest = max(page.width_pt, page.height_pt, 1.0)
            dpi = max(min(560.0 / (longest / 72.0), 96.0), 6.0)
            try:
                kept = page.frame.render_image(dpi=dpi, for_print=True)
            except Exception:                                  # noqa: BLE001
                kept = QImage()
            self._pictures[self.preview_index] = kept
        return kept if not kept.isNull() else None

    # -- Get Line's round trip ----------------------------------------------------------------
    def state(self) -> dict:
        return {"media": self.media.currentText(), "landscape": self.landscape.isChecked(),
                "width": self.width_box.value(), "height": self.height_box.value(),
                "offset": (self.offset_x.value(), self.offset_y.value()),
                "scale": self.scale_box.value(), "fit": self._fit, "align": self._align,
                "rotation": self.rotation.value(), "pages": self.pages.which(),
                "range": self.pages.range.text(), "preview": self.preview_index,
                "margins": {key: spin.value() for key, spin in self.margins.items()},
                "margins_were": dict(self._margins_were)}

    def restore(self, state: dict) -> None:
        self._filling = True
        try:
            index = self.media.findText(state.get("media", DEFAULT_SIZE))
            self.media.setCurrentIndex(max(index, 0))
            if self.media.currentData() == "custom":
                self.width_box.setValue(float(state.get("width", self.width_box.value())))
                self.height_box.setValue(float(state.get("height", self.height_box.value())))
            (self.landscape if state.get("landscape") else self.portrait).setChecked(True)
            self._show_media()
            self.scale_box.setValue(float(state.get("scale", 100.0)))
            x, y = state.get("offset", (0.0, 0.0))
            self.offset_x.setValue(float(x))
            self.offset_y.setValue(float(y))
            self._fit = bool(state.get("fit"))
            self._align = state.get("align")
            self.auto_scale.setChecked(self._fit)
            self.rotation.setValue(float(state.get("rotation", 0.0)))
            self.pages.choose(state.get("pages", PagesRange.CURRENT), state.get("range"))
            self.preview_index = int(state.get("preview", self.current))
            for key, value in (state.get("margins") or {}).items():
                if key in self.margins:
                    self.margins[key].setValue(float(value))
            self._margins_were.update(state.get("margins_were") or {})
        finally:
            self._filling = False
        self._placed()


class _Preview(QWidget):
    """Revu's Preview: the paper, dashed round, and the page drawn on it
    where it will land."""

    def __init__(self, dialog: PageSetupDialog):
        super().__init__(dialog)
        self.dialog = dialog
        self.setObjectName("pageSetupPreviewPicture")
        self.setMinimumSize(QSize(280, 280))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def sheet_rect(self) -> tuple:
        """(the paper's rectangle on the widget, points to pixels)."""
        _scale, _x, _y, _transform, new = self.dialog.placement()
        room = QRectF(self.rect()).adjusted(10, 10, -10, -10)
        width, height = new.width_pt, new.height_pt
        factor = min(room.width() / max(width, 1.0), room.height() / max(height, 1.0))
        sheet = QRectF(0, 0, width * factor, height * factor)
        sheet.moveCenter(room.center())
        return sheet, factor

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        palette = self.palette()
        painter.fillRect(self.rect(), palette.color(QPalette.Mid))
        sheet, factor = self.sheet_rect()
        painter.fillRect(sheet, QColor("#ffffff"))
        _scale, _x, _y, transform, _new = self.dialog.placement()
        setup = self.dialog._page_setup()
        painter.save()
        painter.setClipRect(sheet)
        painter.translate(sheet.topLeft())
        painter.scale(factor, factor)
        painter.setTransform(transform, True)
        page = QRectF(0, 0, setup.width_pt, setup.height_pt)
        picture = self.dialog.picture()
        if picture is not None:
            painter.drawImage(page, picture, QRectF(picture.rect()))
        else:
            painter.fillRect(page, QColor("#f4f4f4"))
        pen = QPen(QColor("#2f7fd0"))
        pen.setCosmetic(True)
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(page)
        painter.restore()
        pen = QPen(QColor("#202020"))
        pen.setStyle(Qt.DashLine)
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.drawRect(sheet.adjusted(-0.5, -0.5, 0.5, 0.5))
        painter.end()


# ---------------------------------------------------------------------------
# doing it
# ---------------------------------------------------------------------------

@dataclass
class Change:
    """One page's part in a Page Setup: its new paper, and the transform
    its content goes through (None: it stays where it is)."""

    page: object
    setup: PageSetup
    transform: Optional[QTransform]
    scale: float
    rotation: float
    resized: bool


def changes_for(document, plan: Plan, indexes) -> list:
    """What *plan* does to the pages *indexes* (a spreadsheet's pages go with
    their run, and keep their cells where they are); pages it leaves exactly
    as they are are left out."""
    from .sheetpages import with_runs
    pages = [document.pages[i] for i in sorted(set(indexes or ()))
             if 0 <= i < len(document.pages)]
    pages = with_runs(document, pages)
    changes = []
    for page in pages:
        new = setup_for(page.setup, plan)
        if page.sheet is not None:
            scale, transform = 1.0, QTransform()
        else:
            scale, _x, _y, transform = place(page.width_pt, page.height_pt,
                                             new.width_pt, new.height_pt, plan)
        moved = not is_identity(transform)
        resized = (abs(new.width_pt - page.width_pt) > 0.01
                   or abs(new.height_pt - page.height_pt) > 0.01)
        if not moved and new.to_dict() == page.setup.to_dict():
            continue
        changes.append(Change(page, new, transform if moved else None, scale,
                              plan.rotation if moved else 0.0, resized))
    return changes


def carry_out(window, changes: list) -> None:
    """Resize the pages: the files first (one copy of each source PDF for all
    its pages), then what is drawn on each page."""
    document = window.document
    _resize_the_files(document, changes)
    for change in changes:
        page = change.page
        if change.transform is not None:
            _move_the_content(window, page, change)
        if page.background_key and (change.transform is not None or change.resized):
            _redraw_the_picture(document, page, change)
        page.setup = PageSetup.from_dict(change.setup.to_dict())
        frame = page.frame
        if frame is not None:
            frame.prepareGeometryChange()
            frame._background = None
            frame.forget_sharp_background()
            frame.update()
    for change in changes:
        if change.transform is not None:
            window.refresh_page_measurements(change.page)


def _matrix(transform: Optional[QTransform]) -> tuple:
    if transform is None:
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    return (transform.m11(), transform.m12(), transform.m21(), transform.m22(),
            transform.dx(), transform.dy())


def _resize_the_files(document, changes: list) -> None:
    from ..io import pdfresize
    groups: dict = {}
    made: list = []
    for change in changes:
        page = change.page
        if page.pdf_key and page.pdf_page_index is not None \
                and (change.transform is not None or change.resized):
            groups.setdefault(page.pdf_key, []).append(change)
    for key, group in groups.items():
        data = document.asset(key)
        if not data:
            continue
        # one copy of the file holds each of its pages once; the same page
        # under two of the document's pages (a duplicate) goes in a second
        batches: list = []
        for change in group:
            index = int(change.page.pdf_page_index)
            for taken, members in batches:
                if index not in taken:
                    taken.add(index)
                    members.append(change)
                    break
            else:
                batches.append(({index}, [change]))
        for _taken, members in batches:
            jobs = []
            for change in members:
                page = change.page
                drop = list(page.markup_annotations) if change.transform is not None else []
                jobs.append(pdfresize.Job(int(page.pdf_page_index), change.setup.width_pt,
                                          change.setup.height_pt, _matrix(change.transform),
                                          drop=drop,
                                          clip=(0.0, 0.0, page.width_pt, page.height_pt)))
            made.append((members, pdfresize.resize(data, jobs)))
    # every file is written before any page is pointed at one: a file that
    # will not resize leaves the document exactly as it was
    for members, data in made:
        key = document.add_asset(data, "pdf")
        for change in members:
            change.page.pdf_key = key


def _redraw_the_picture(document, page, change: Change) -> None:
    """A page whose sheet is a picture: the picture drawn again onto the new
    paper, as dense as it was."""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    data = document.asset(page.background_key)
    if not data:
        return
    picture = QImage()
    if not picture.loadFromData(QByteArray(data)) or picture.isNull():
        return
    density = picture.width() / max(page.width_pt, 1.0)
    width = max(int(round(change.setup.width_pt * density)), 1)
    height = max(int(round(change.setup.height_pt * density)), 1)
    longest = max(width, height)
    if longest > 12000:
        shrink = 12000 / longest
        width, height, density = (max(int(width * shrink), 1), max(int(height * shrink), 1),
                                  density * shrink)
    made = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
    made.fill(Qt.transparent)
    painter = QPainter(made)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    painter.scale(density, density)
    if change.transform is not None:
        painter.setTransform(change.transform, True)
    painter.drawImage(QRectF(0, 0, page.width_pt, page.height_pt), picture,
                      QRectF(picture.rect()))
    painter.end()
    holder = QByteArray()
    buffer = QBuffer(holder)
    buffer.open(QIODevice.WriteOnly)
    made.save(buffer, "PNG")
    buffer.close()
    page.background_key = document.add_asset(bytes(holder), "png")


def _quarter(degrees: float) -> bool:
    turns = degrees / 90.0
    return abs(turns - round(turns)) < 1e-9


def _move_the_content(window, page, change: Change) -> None:
    transform, factor, turn = change.transform, change.scale, change.rotation
    frame = page.frame
    markups = frame.markups() if frame is not None else []
    if page.markup_annotations:
        # The markups read out of the file become ours: the file's own copies
        # of them are taken off the resized page (io/pdfresize.py), and these
        # are drawn — and saved — where the drawing now is.
        for item in markups:
            if item.from_annotation or item.split_from:
                item.make_it_ours()
                item.from_annotation = 0
                item.split_from = 0
                item.split_theirs = False
                item.their_box = ()
        page.markup_annotations = []
    for item in markups:
        move_item(item, transform, factor, turn)
    swapped = _quarter(turn) and int(round(turn / 90.0)) % 2 == 1
    for viewport in page.viewports:
        box = transform.mapRect(QRectF(viewport.x, viewport.y, viewport.width,
                                       viewport.height))
        viewport.x, viewport.y = box.x(), box.y()
        viewport.width, viewport.height = box.width(), box.height()
        viewport.scale = rescaled(viewport.scale, factor, swapped)
    page.scale = rescaled(page.scale, factor, swapped)
    if _quarter(turn) and abs(turn) > 1e-9:
        # equations on a page turned a quarter turn read the page's way
        page.turn = int(round(page.turn - turn)) % 360
    document = window.document
    for mark in document.bookmarks:
        if mark.page_uid == page.uid and not mark.markup:
            mark.y = max(transform.map(QPointF(0.0, mark.y)).y(), 0.0)
    index = document.index_of(page)
    from ..items.link import VIEW
    for other in document.pages:
        if other.frame is None:
            continue
        for item in other.frame.markups():
            if getattr(item, "TYPE", "") == "link" and getattr(item, "kind", None) == VIEW \
                    and item.target_page == index:
                item.target_y = max(transform.map(QPointF(0.0, item.target_y)).y(), 0.0)


def move_item(item, transform: QTransform, factor: float, turn: float) -> None:
    """Carry one markup with its page's content: turned *turn* degrees
    anticlockwise and *factor* times the size, landing where *transform*
    takes it. A measurement — and a shape sized to scale — changes by its
    own points, so what it measures stays what it is (the page's scale is
    changed by the same factor); everything else by its transform, as a
    group is resized."""
    from ..items.measure import MeasureItem
    from ..items.shapes import SIZED_KINDS, RectItem

    origin = QPointF(item.transformOriginPoint())
    landing = transform.map(item.mapToParent(origin))
    cos, sin = math.cos(math.radians(turn)), math.sin(math.radians(turn))
    item.prepareGeometryChange()
    plain = abs(item.rotation()) < 1e-9 and item.transform().isIdentity()
    if isinstance(item, MeasureItem):
        def mapped(point: QPointF, scale: float = factor) -> QPointF:
            if plain:            # turned by its points: it has no turn of its own
                return QPointF(scale * (point.x() * cos + point.y() * sin),
                               scale * (-point.x() * sin + point.y() * cos))
            return QPointF(point.x() * scale, point.y() * scale)
        item.points = [mapped(p) for p in item.points]
        item.cutouts = [[mapped(p) for p in hole] for hole in item.cutouts]
        item.witness_reach = item.witness_reach * factor
        if plain:
            item.label_offset = mapped(item.label_offset, 1.0)
            if item.label_angle is not None:
                item.label_angle = item.label_angle - turn
        new_origin = mapped(origin)
        if not plain and abs(turn) > 1e-9:
            item.setRotation(item.rotation() - turn)
        item.setTransformOriginPoint(new_origin)
    elif isinstance(item, RectItem) and item.kind in SIZED_KINDS:
        rect = item.local_rect()
        item.set_local_rect(QRectF(rect.x() * factor, rect.y() * factor,
                                   rect.width() * factor, rect.height() * factor))
        item.cutouts = [[QPointF(p.x() * factor, p.y() * factor) for p in hole]
                        for hole in item.cutouts]
        new_origin = QPointF(origin.x() * factor, origin.y() * factor)
        item.setTransformOriginPoint(new_origin)
        if abs(turn) > 1e-9:
            item.setRotation(item.rotation() - turn)
    else:
        new_origin = origin
        sized = getattr(item, "TYPE", "") != "note"      # a note is an icon
        scale = factor if sized else 1.0
        turns = abs(turn) > 1e-9 and (getattr(item, "ROTATABLE", True)
                                       or hasattr(item, "show_upright"))
        own = item.transform()
        similar = abs(own.m11() - own.m22()) < 1e-9 and abs(own.m12() + own.m21()) < 1e-9
        if turns and not similar:
            # its own transform is not a plain turn and scale (a flip, a
            # stretch): the turn goes on after it
            item.setTransform(own * QTransform().rotate(-turn).scale(scale, scale))
        else:
            if abs(scale - 1.0) > 1e-12:
                item.setTransform(own * QTransform.fromScale(scale, scale))
            if turns:
                item.setRotation(item.rotation() - turn)
    item.setPos(item.pos() + landing - item.mapToParent(new_origin))
    item.update()
