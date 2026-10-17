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
STREAMS = ((BOTH, "Document & Markups"), (DOCUMENT, "Document Only"),
           (MARKUPS, "Markups Only"))

# Page Scaling, in Revu's order
NONE, FIT_PAPER, REDUCE_PAPER, CUSTOM, FIT_MARGINS, REDUCE_MARGINS = (
    "none", "fit_paper", "reduce_paper", "custom", "fit_margins", "reduce_margins")
SCALINGS = ((NONE, "None"), (FIT_PAPER, "Fit to Paper"), (REDUCE_PAPER, "Reduce to Paper"),
            (CUSTOM, "Custom Scale"), (FIT_MARGINS, "Fit to Margins"),
            (REDUCE_MARGINS, "Reduce to Margins"))

# Rotation: Auto turns the page to suit the paper
AUTO = "auto"
ROTATIONS = ((AUTO, "Auto"), ("0", "0°"), ("90", "90°"), ("180", "180°"), ("270", "270°"))

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
    auto_size: bool = True                # Auto: paper from each page's own size
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
        if made.rotation not in dict(ROTATIONS):
            made.rotation = AUTO
        made.copies = min(max(made.copies, 1), 999)
        made.custom_scale = min(max(made.custom_scale, 1.0), 1000.0)
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
    if options.rotation != AUTO:
        return int(options.rotation) % 360
    across, down = source.width(), source.height()
    if abs(across - down) < 0.5 or abs(paper.width() - paper.height()) < 0.5:
        return 0
    # Revu turns the page when it lies the other way to the paper
    return 90 if (across > down) != (paper.width() > paper.height()) else 0


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
              clip: Optional[QRectF] = None, draft: str = "") -> bool:
    """*page* drawn the way it prints, in page points on *painter* — the
    export's own drawing of it, in the stream asked for. With *dim*, the
    page content is washed out under the markups (Revu's Dim Page Content).
    *draft*: for the preview's small picture (render_page's *draft*);
    says whether the page drew everything (False while a "background"
    draft's picture of the PDF is still coming)."""
    frame = page.frame
    if frame is None:
        return True
    whole = QRectF(0, 0, float(page.width_pt), float(page.height_pt))
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    if not dim or stream == MARKUPS:
        frame.render_page(painter, whole, for_print=True,
                          stream="" if stream == BOTH else stream, draft=draft)
        return not frame.draft_waiting if draft else True
    frame.render_page(painter, whole, for_print=True, stream=DOCUMENT, draft=draft)
    complete = not frame.draft_waiting if draft else True
    painter.fillRect(clip if clip is not None else whole, dim_veil())
    if stream == BOTH:
        frame.render_page(painter, whole, for_print=True, stream=MARKUPS, draft=draft)
    return complete


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


def print_pages(printer, pages: list, options: PrintOptions,
                window: Optional[QRectF] = None,
                progress: Optional[Callable[[int, int], bool]] = None) -> int:
    """Print *pages* (already the printable ones, in range order) with
    *options* onto *printer*; how many sheets came out.

    Copies are made here, page by page, so Collate and Reverse come out the
    same on every printer and in a file. Under Auto each page gets its own
    paper where the printer can change paper during a job (a PDF file can);
    a printer that cannot keeps the first page's paper and the others are
    placed on it by Page Scaling.
    """
    sheets = sheet_order(pages, options)
    if not sheets:
        raise ValueError("No pages are included in print and export")
    try:
        printer.setCopyCount(1)
    except Exception:                                  # noqa: BLE001
        pass
    from PySide6.QtPrintSupport import QPrinter
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
            device = QTransform.fromScale(printer.resolution() / 72.0,
                                          printer.resolution() / 72.0)
            painter.save()
            painter.setTransform(placed.transform * device)
            painter.setClipRect(placed.clip)
            draw_page(painter, sheet, options.stream, options.dim, placed.clip)
            painter.restore()
            done += 1
            if progress is not None and not progress(done, len(sheets)):
                break
    finally:
        if started:
            painter.end()
    return done


__all__ = ["PrintOptions", "Placement", "place", "paper_for", "paper_points",
           "draw_page", "print_pages", "printable_pages", "sheet_order",
           "printer_margins", "STREAMS", "SCALINGS", "ROTATIONS", "PAPERS"]
