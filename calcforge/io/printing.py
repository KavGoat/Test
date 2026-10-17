"""Revu's Print: what prints, onto which paper, how big and where.

The Print dialog (ui/printdialog.py) fills a :class:`PrintOptions`; this
module turns it into sheets of paper. Each page is drawn by the page itself,
``PageFrame.render_page`` with ``for_print=True`` — the drawing the PDF
export and the image export make — so what prints looks exactly as written.
Only where it lands changes: Page Scaling, Rotation, Centre (or X and Y), and
Get Window's part of a page.

The streams (Revu: "Print: Document & Markups, Document Only, or Markups
Only"): CalcForge's equations, tables and spreadsheet grids are the page's
own content — a save writes them into the page as its calc and sheet layers,
not as annotations — so Document Only keeps them, and Markups Only is the
markups (annotations) alone on blank paper. A markup that has been flattened
is part of the page now, as in Revu.

The per-page "Include Page in Print & Export" and the per-markup Print tick
are honoured: a page left out does not print in any range, and a markup left
out does not print in any stream.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Callable, Optional

from PySide6.QtCore import QMarginsF, QRectF, QSizeF
from PySide6.QtGui import QColor, QPageLayout, QPageSize, QPainter, QTransform

from ..core.document import MM_TO_PT, PAGE_SIZES

# what prints (Revu's Print box)
BOTH, DOCUMENT, MARKUPS = "both", "document", "markups"
# Revu 21's own words (the user's photo of its Print dialog, 2026-10-17:
# "Document & Markup"; the manual says "Markups")
STREAMS = ((BOTH, "Document & Markup"), (DOCUMENT, "Document Only"),
           (MARKUPS, "Markup Only"))

# Page Scaling, in Revu's order
NONE, FIT_PAPER, REDUCE_PAPER, CUSTOM, FIT_MARGINS, REDUCE_MARGINS = (
    "none", "fit_paper", "reduce_paper", "custom", "fit_margins", "reduce_margins")
SCALINGS = ((NONE, "None"), (FIT_PAPER, "Fit to Paper"), (REDUCE_PAPER, "Reduce to Paper"),
            (CUSTOM, "Custom Scale"), (FIT_MARGINS, "Fit to Margins"),
            (REDUCE_MARGINS, "Reduce to Margins"))

# Rotation, in Revu's words: Auto-Rotate turns a page that lies the other
# way to the paper, a quarter clockwise (90) or anticlockwise (270)
AUTO, AUTO_270 = "auto90", "auto270"
ROTATIONS = ((AUTO, "Auto-Rotate 90"), (AUTO_270, "Auto-Rotate 270"), ("0", "No Rotation"),
             ("90", "Rotate 90"), ("180", "Rotate 180"), ("270", "Rotate 270"))

#: How far a markup the Markups List's filter leaves out is toned down when
#: Dim Filtered Markups is ticked: drawn at this opacity (Revu's Filtered
#: Annotation Dim, in its Markups List preferences).
FILTERED_OPACITY = 0.3

# Advanced: Revu's printing engines (menus__file__advanced-printing.txt)
ENGINE_MIXED, ENGINE_VECTOR, ENGINE_IMAGE, ENGINE_GRID = "mixed", "vector", "image", "grid"
ENGINES = ((ENGINE_MIXED, "Image/Vector/Grid"), (ENGINE_VECTOR, "Vector"),
           (ENGINE_IMAGE, "Image"), (ENGINE_GRID, "Grid"))

#: The margin a printer that reports none (a PDF file) is given, so Fit to
#: Margins and the preview's red margin lines still mean something: a
#: quarter of an inch, what office printers commonly cannot reach.
DEFAULT_MARGIN_PT = 18.0

#: The papers offered when the printer itself names none (a PDF file).
PAPERS = tuple(PAGE_SIZES)


@dataclass
class PrintOptions:
    """Everything in Print's Options box, as Defaults sets it."""

    stream: str = BOTH
    copies: int = 1
    collate: bool = True
    reverse: bool = False
    rotation: str = AUTO
    scaling: str = FIT_PAPER
    custom_scale: float = 100.0           # per cent, for Custom Scale
    centre: bool = True
    x_mm: float = 0.0                     # the content's top-left corner on the
    y_mm: float = 0.0                     # paper, when Centre is off
    dim: bool = False                     # Dim Page Content
    dim_filtered: bool = True             # Dim Filtered Markups
    links: bool = False                   # Print Visible Hyperlinks
    greyscale: bool = False               # Print in Greyscale
    auto_size: bool = False               # Auto: paper from each page's own size
    paper: str = "A4"                     # Size, by name...
    paper_w_pt: float = 210.0 * MM_TO_PT  # ...and by size, portrait, in points
    paper_h_pt: float = 297.0 * MM_TO_PT
    landscape: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PrintOptions":
        """Read back what was remembered; anything unreadable is the default."""
        made = cls()
        for field in fields(cls):
            if field.name not in data:
                continue
            value = data[field.name]
            default = getattr(made, field.name)
            try:
                if isinstance(default, bool):
                    value = value if isinstance(value, bool) else \
                        str(value).strip().lower() in ("1", "true", "yes")
                elif isinstance(default, int):
                    value = int(float(value))
                elif isinstance(default, float):
                    value = float(value)
                else:
                    value = str(value)
            except (TypeError, ValueError):
                continue
            setattr(made, field.name, value)
        if made.stream not in dict(STREAMS):
            made.stream = BOTH
        if made.scaling not in dict(SCALINGS):
            made.scaling = FIT_PAPER
        if made.rotation == "auto":            # remembered before Revu's words
            made.rotation = AUTO
        if made.rotation not in dict(ROTATIONS):
            made.rotation = AUTO
        made.copies = min(max(made.copies, 1), 999)
        made.custom_scale = min(max(made.custom_scale, 1.0), 1000.0)
        return made


@dataclass
class AdvancedOptions:
    """Revu's Advanced Printing, kept for each printer: the printing engine,
    its grid, and how an image goes to the printer."""

    engine: str = ENGINE_MIXED
    grid_in: float = 1.0                  # Grid Size, inches
    dpi: int = 300                        # resolution of what is sent as an image
    band_limit_mb: float = 12.0           # Image Band Limit
    band_size_mb: float = 4.0             # Image Band Size

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AdvancedOptions":
        made = cls()
        for field in fields(cls):
            if field.name in data:
                try:
                    setattr(made, field.name, type(getattr(made, field.name))(
                        float(data[field.name]) if field.name != "engine"
                        else str(data[field.name])))
                except (TypeError, ValueError):
                    pass
        if made.engine not in dict(ENGINES):
            made.engine = ENGINE_MIXED
        made.grid_in = min(max(made.grid_in, 0.1), 20.0)
        made.dpi = int(min(max(made.dpi, 72), 1200))
        made.band_limit_mb = min(max(made.band_limit_mb, 1.0), 1024.0)
        made.band_size_mb = min(max(made.band_size_mb, 0.5), made.band_limit_mb)
        return made


# ---------------------------------------------------------------------------
# paper and placing
# ---------------------------------------------------------------------------

def paper_points(name: str) -> QSizeF:
    """One of CalcForge's named papers, portrait, in points (A4 if unknown)."""
    width, height = (v * MM_TO_PT for v in PAGE_SIZES.get(name, PAGE_SIZES["A4"]))
    return QSizeF(min(width, height), max(width, height))


def paper_for(page, options: PrintOptions) -> QSizeF:
    """The paper *page* prints on: its own size under Auto, else the Size
    chosen, Portrait or Landscape."""
    if options.auto_size:
        return QSizeF(float(page.width_pt), float(page.height_pt))
    width = max(min(options.paper_w_pt, options.paper_h_pt), 1.0)
    height = max(max(options.paper_w_pt, options.paper_h_pt), 1.0)
    return QSizeF(height, width) if options.landscape else QSizeF(width, height)


@dataclass
class Placement:
    """Where a page lands on its paper."""

    paper: QSizeF                 # points
    margins: QMarginsF            # points
    transform: QTransform         # page points -> paper points
    clip: QRectF                  # the part of the page that prints (page points)
    scale: float
    rotation: int

    def content_rect(self) -> QRectF:
        """The printed part of the page, on the paper."""
        return self.transform.mapRect(self.clip)

    def margin_rect(self) -> QRectF:
        return QRectF(self.margins.left(), self.margins.top(),
                      self.paper.width() - self.margins.left() - self.margins.right(),
                      self.paper.height() - self.margins.top() - self.margins.bottom())


def _rotation(options: PrintOptions, source: QRectF, paper: QSizeF) -> int:
    if options.rotation not in (AUTO, AUTO_270):
        return int(options.rotation) % 360
    across, down = source.width(), source.height()
    if abs(across - down) < 0.5 or abs(paper.width() - paper.height()) < 0.5:
        return 0
    # Revu turns the page when it lies the other way to the paper
    if (across > down) == (paper.width() > paper.height()):
        return 0
    return 90 if options.rotation == AUTO else 270


def place(page_size: QSizeF, paper: QSizeF, options: PrintOptions,
          margins: Optional[QMarginsF] = None,
          window: Optional[QRectF] = None) -> Placement:
    """Page Scaling, Rotation and Centre (or X and Y) for one page.

    *window* is Get Window's part of the page, in page points: only that
    part prints, and it is what is scaled and placed.
    """
    margins = QMarginsF(margins) if margins is not None else QMarginsF(
        DEFAULT_MARGIN_PT, DEFAULT_MARGIN_PT, DEFAULT_MARGIN_PT, DEFAULT_MARGIN_PT)
    whole = QRectF(0, 0, page_size.width(), page_size.height())
    source = QRectF(window).normalized().intersected(whole) if window is not None else whole
    if source.isEmpty():
        source = whole
    rotation = _rotation(options, source, paper)
    turn = QTransform().rotate(rotation)
    turned = turn.mapRect(source)
    across, down = max(turned.width(), 1e-6), max(turned.height(), 1e-6)
    paper_area = QRectF(0, 0, paper.width(), paper.height())
    margin_area = QRectF(margins.left(), margins.top(),
                         max(paper.width() - margins.left() - margins.right(), 1.0),
                         max(paper.height() - margins.top() - margins.bottom(), 1.0))
    to_paper = min(paper_area.width() / across, paper_area.height() / down)
    to_margins = min(margin_area.width() / across, margin_area.height() / down)
    scaling = options.scaling
    if scaling == NONE:
        scale = 1.0
    elif scaling == CUSTOM:
        scale = max(float(options.custom_scale), 1.0) / 100.0
    elif scaling == REDUCE_PAPER:
        scale = min(1.0, to_paper)
    elif scaling == FIT_MARGINS:
        scale = to_margins
    elif scaling == REDUCE_MARGINS:
        scale = min(1.0, to_margins)
    else:
        scale = to_paper
    width, height = across * scale, down * scale
    area = margin_area if scaling in (FIT_MARGINS, REDUCE_MARGINS) else paper_area
    if options.centre:
        left = area.left() + (area.width() - width) / 2
        top = area.top() + (area.height() - height) / 2
    else:
        left, top = options.x_mm * MM_TO_PT, options.y_mm * MM_TO_PT
    transform = (turn * QTransform.fromTranslate(-turned.left(), -turned.top())
                 * QTransform.fromScale(scale, scale)
                 * QTransform.fromTranslate(left, top))
    return Placement(QSizeF(paper), margins, transform, source, scale, rotation)


# ---------------------------------------------------------------------------
# drawing a page
# ---------------------------------------------------------------------------

def dim_veil() -> QColor:
    """Dim Page Content's wash over the page: the View ▸ Dimmer level."""
    from ..ui.scene import DIMMER
    veil = QColor(255, 255, 255)
    veil.setAlphaF(max(0.0, min(1.0, 1.0 - float(DIMMER.get("level", 0.4)))))
    return veil


def draw_page(painter: QPainter, page, stream: str = BOTH, dim: bool = False,
              clip: Optional[QRectF] = None, draft: str = "", links: bool = False,
              dimmed=()) -> bool:
    """*page* drawn the way it prints, in page points on *painter* — the
    export's own drawing of it, in the stream asked for.

    *dim*: the page content washed out under the markups (Revu's Dim Page
    Content). *links*: the links' rectangles drawn as they show on screen
    (Print Visible Hyperlinks). *dimmed*: markups drawn toned down — those
    the Markups List's filter leaves out, under Dim Filtered Markups.
    *draft*: for the preview's small picture (render_page's *draft*).
    Says whether the page drew everything (False while a "background"
    draft's picture of the PDF is still coming)."""
    frame = page.frame
    if frame is None:
        return True
    whole = QRectF(0, 0, float(page.width_pt), float(page.height_pt))
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    toned = [item for item in frame.markups() if item in dimmed] if dimmed else []
    before = [item.opacity() for item in toned]
    for item in toned:
        item.setOpacity(item.opacity() * FILTERED_OPACITY)
    try:
        if not dim or stream == MARKUPS:
            frame.render_page(painter, whole, for_print=True,
                              stream="" if stream == BOTH else stream, draft=draft,
                              links=links)
            return not frame.draft_waiting if draft else True
        frame.render_page(painter, whole, for_print=True, stream=DOCUMENT, draft=draft,
                          links=links)
        complete = not frame.draft_waiting if draft else True
        painter.fillRect(clip if clip is not None else whole, dim_veil())
        if stream == BOTH:
            frame.render_page(painter, whole, for_print=True, stream=MARKUPS, draft=draft,
                              links=links)
        return complete
    finally:
        for item, opacity in zip(toned, before):
            item.setOpacity(opacity)


def see_through(page, dimmed=()) -> list:
    """The parts of *page* (page points) where something is drawn see-through
    — a markup with opacity, a filled one at its fill opacity, a highlighter,
    one toned down by Dim Filtered Markups: what Image/Vector/Grid sends to
    the printer as pictures."""
    frame = page.frame
    if frame is None:
        return []
    found = []
    for item in frame.markups():
        if not item.isVisible() or not item.printable:
            continue
        style = getattr(item, "style", None)
        clear = item in dimmed or item.opacity() < 0.999
        if style is not None:
            clear = clear or style.opacity < 0.999 or style.blend == "multiply" \
                or (bool(style.fill) and style.fill_opacity < 0.999)
        if clear:
            found.append(item.mapRectToParent(item.boundingRect()))
    return found


def sheet_order(pages: list, options: PrintOptions) -> list:
    """The pages in the order they come out: Reverse, then Copies (Collate:
    1,2,3,1,2,3; else 1,1,2,2,3,3)."""
    ordered = list(reversed(pages)) if options.reverse else list(pages)
    copies = max(int(options.copies), 1)
    if copies == 1:
        return ordered
    if options.collate:
        return ordered * copies
    return [page for page in ordered for _ in range(copies)]


def printer_margins(printer) -> QMarginsF:
    """What the printer cannot reach, in points; a quarter inch for one that
    says nothing (a file)."""
    try:
        reach = printer.pageLayout().minimumMargins()
        units = printer.pageLayout().units()
        to_points = {QPageLayout.Millimeter: MM_TO_PT, QPageLayout.Point: 1.0,
                     QPageLayout.Inch: 72.0}.get(units)
    except Exception:                                  # noqa: BLE001
        reach, to_points = None, None
    if reach is None or to_points is None or \
            max(reach.left(), reach.top(), reach.right(), reach.bottom()) <= 0:
        return QMarginsF(DEFAULT_MARGIN_PT, DEFAULT_MARGIN_PT,
                         DEFAULT_MARGIN_PT, DEFAULT_MARGIN_PT)
    return QMarginsF(reach.left() * to_points, reach.top() * to_points,
                     reach.right() * to_points, reach.bottom() * to_points)


def _layout(paper: QSizeF) -> QPageLayout:
    layout = QPageLayout()
    layout.setPageSize(QPageSize(paper, QPageSize.Point, "", QPageSize.ExactMatch))
    layout.setOrientation(QPageLayout.Portrait)       # the size carries the orientation
    layout.setMode(QPageLayout.FullPageMode)
    layout.setMargins(QMarginsF(0, 0, 0, 0))
    return layout


def printable_pages(document, indexes: list) -> list:
    """The pages of *indexes* that print: those not left out of print and
    export, and that have been built."""
    out = []
    for index in indexes:
        if 0 <= index < len(document.pages):
            page = document.pages[index]
            if page.printable and page.frame is not None:
                out.append(page)
    return out


def _cells(area: QRectF, step: float) -> list:
    """*area* cut into squares *step* points across, from its top left."""
    out = []
    step = max(step, 1.0)
    y = area.top()
    while y < area.bottom() - 1e-6:
        x = area.left()
        while x < area.right() - 1e-6:
            out.append(QRectF(x, y, min(step, area.right() - x), min(step, area.bottom() - y)))
            x += step
        y += step
    return out


def _bands(area: QRectF, dpi: float, advanced: "AdvancedOptions") -> list:
    """*area* as the image bands it goes to the printer in: all of it when
    it is within the Image Band Limit, else strips of the Image Band Size."""
    k = dpi / 72.0
    row_bytes = max(area.width() * k, 1.0) * 4
    total = row_bytes * max(area.height() * k, 1.0)
    if total <= advanced.band_limit_mb * 1024 * 1024:
        return [QRectF(area)]
    rows = max(int(advanced.band_size_mb * 1024 * 1024 / row_bytes), 1)
    step = rows / k
    out, y = [], area.top()
    while y < area.bottom() - 1e-6:
        out.append(QRectF(area.left(), y, area.width(), min(step, area.bottom() - y)))
        y += step
    return out


def _raster_cell(painter: QPainter, device: QTransform, sheet, placed: Placement,
                 options: PrintOptions, dpi: float, cell: QRectF, dimmed) -> None:
    """One part of the paper (*cell*, paper points) drawn as a picture at
    *dpi* — in grey for Print in Greyscale — and sent as that."""
    import math
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage
    k = dpi / 72.0
    across = max(int(math.ceil(cell.width() * k)), 1)
    down = max(int(math.ceil(cell.height() * k)), 1)
    image = QImage(across, down, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.white)
    drawing = QPainter(image)
    try:
        drawing.setTransform(placed.transform * QTransform.fromTranslate(-cell.left(), -cell.top())
                             * QTransform.fromScale(k, k))
        drawing.setClipRect(placed.clip)
        draw_page(drawing, sheet, options.stream, options.dim, placed.clip,
                  links=options.links, dimmed=dimmed)
    finally:
        drawing.end()
    if options.greyscale:
        image = image.convertToFormat(QImage.Format_Grayscale8)
    painter.save()
    painter.setTransform(device)
    painter.setClipping(False)
    painter.drawImage(QRectF(cell.left(), cell.top(), across / k, down / k), image)
    painter.restore()


def paint_sheet(painter: QPainter, resolution: float, sheet, placed: Placement,
                options: PrintOptions, advanced: Optional["AdvancedOptions"] = None,
                dimmed=()) -> None:
    """One sheet of paper, by the printing engine chosen (Advanced):
    Vector draws everything as it is drawn; Image sends the sheet as a
    picture, in bands; Grid as pictures a Grid Size square; Image/Vector/Grid
    draws as Vector and sends the squares where something is see-through as
    pictures. Print in Greyscale sends the whole sheet as a grey picture —
    there is no other way to turn a drawing's colours grey."""
    advanced = advanced or AdvancedOptions()
    device = QTransform.fromScale(resolution / 72.0, resolution / 72.0)
    paper = QRectF(0, 0, placed.paper.width(), placed.paper.height())
    content = placed.content_rect().intersected(paper)
    if content.isEmpty():
        return
    dpi = float(min(advanced.dpi, resolution))
    engine = advanced.engine
    if options.greyscale or engine in (ENGINE_IMAGE, ENGINE_GRID):
        cells = _cells(content, advanced.grid_in * 72.0) if engine == ENGINE_GRID \
            else _bands(content, dpi, advanced)
        for cell in cells:
            _raster_cell(painter, device, sheet, placed, options, dpi, cell, dimmed)
        return
    painter.save()
    painter.setTransform(placed.transform * device)
    painter.setClipRect(placed.clip)
    draw_page(painter, sheet, options.stream, options.dim, placed.clip,
              links=options.links, dimmed=dimmed)
    painter.restore()
    if engine != ENGINE_MIXED or options.stream == DOCUMENT:
        return
    regions = [placed.transform.mapRect(box.intersected(placed.clip))
               for box in see_through(sheet, dimmed)]
    regions = [box for box in regions if not box.isEmpty()]
    if not regions:
        return
    for cell in _cells(QRectF(content), advanced.grid_in * 72.0):
        if any(cell.intersects(box) for box in regions):
            _raster_cell(painter, device, sheet, placed, options, dpi, cell, dimmed)


def print_pages(printer, pages: list, options: PrintOptions,
                window: Optional[QRectF] = None,
                progress: Optional[Callable[[int, int], bool]] = None,
                advanced: Optional["AdvancedOptions"] = None, filtered=()) -> int:
    """Print *pages* (already the printable ones, in range order) with
    *options* onto *printer*; how many sheets came out.

    Copies are made here, page by page, so Collate and Reverse come out the
    same on every printer and in a file. Under Auto each page gets its own
    paper where the printer can change paper during a job (a PDF file can);
    a printer that cannot keeps the first page's paper and the others are
    placed on it by Page Scaling. *filtered*: the markups the Markups List's
    filter leaves out, toned down under Dim Filtered Markups.
    """
    sheets = sheet_order(pages, options)
    if not sheets:
        raise ValueError("No pages are included in print and export")
    try:
        printer.setCopyCount(1)
    except Exception:                                  # noqa: BLE001
        pass
    from PySide6.QtPrintSupport import QPrinter
    if options.greyscale:
        try:
            printer.setColorMode(QPrinter.GrayScale)
        except Exception:                              # noqa: BLE001
            pass
    dimmed = frozenset(filtered) if options.dim_filtered else frozenset()
    can_change = getattr(printer, "outputFormat", lambda: None)() == QPrinter.PdfFormat
    margins = printer_margins(printer)
    painter = QPainter()
    started = False
    current_paper: Optional[QSizeF] = None
    done = 0
    try:
        for sheet in sheets:
            paper = paper_for(sheet, options)
            if not started:
                printer.setPageLayout(_layout(paper))
                if not painter.begin(printer):
                    raise OSError("Could not start the print job")
                started = True
                current_paper = paper
            else:
                if can_change and paper != current_paper:
                    printer.setPageLayout(_layout(paper))
                    current_paper = paper
                printer.newPage()
            paper = current_paper
            placed = place(QSizeF(float(sheet.width_pt), float(sheet.height_pt)),
                           paper, options, margins, window)
            paint_sheet(painter, printer.resolution(), sheet, placed, options,
                        advanced, dimmed)
            done += 1
            if progress is not None and not progress(done, len(sheets)):
                break
    finally:
        if started:
            painter.end()
    return done


__all__ = ["PrintOptions", "AdvancedOptions", "Placement", "paint_sheet", "see_through", "place", "paper_for", "paper_points",
           "draw_page", "print_pages", "printable_pages", "sheet_order",
           "printer_margins", "STREAMS", "SCALINGS", "ROTATIONS", "PAPERS"]
