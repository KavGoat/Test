"""Printing and export: PDF, images and the markups list."""
from __future__ import annotations

import csv
import io
import os
from typing import Iterable, Optional

from PySide6.QtCore import QMarginsF, QRectF, QSizeF
from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QPdfWriter
from PySide6.QtPrintSupport import QPrinter

from ..core.document import Document


def page_size_for(page) -> QPageSize:
    """Qt page size matching a document page, in points."""
    setup = page.setup
    return QPageSize(QSizeF(setup.width_pt, setup.height_pt), QPageSize.Point,
                     setup.size_name or "Custom", QPageSize.ExactMatch)


def _apply_layout(device, page) -> None:
    layout = QPageLayout()
    layout.setPageSize(page_size_for(page))
    layout.setOrientation(QPageLayout.Portrait)     # size already carries orientation
    layout.setMode(QPageLayout.FullPageMode)
    layout.setMargins(QMarginsF(0, 0, 0, 0))
    device.setPageLayout(layout)


def paint_pages(device, document: Document, pages: Iterable, resolution: float,
                per_page_layout: bool = True,
                pdf_overlay_pages: Optional[set[str]] = None,
                without_markups: bool = False) -> None:
    """Render *pages* onto a paged paint device.

    ``QPdfWriter`` accepts a new page size for every page, so an export can mix
    A4 and A3 sheets faithfully.  ``QPrinter`` refuses to change its layout once
    printing has started, so for a real printer the layout is fixed by the first
    page and every other page is scaled to fit it — pass ``per_page_layout=False``
    for that.  The painter is always ended, even if a page fails to draw, because
    leaving it open crashes the print-preview dialog on its next repaint.
    """
    painter = QPainter()
    started = False
    try:
        for page in pages:
            if page.frame is None:
                continue
            if not started:
                _apply_layout(device, page)
                if not painter.begin(device):
                    raise OSError("Could not start the print job")
                started = True
            else:
                if per_page_layout:
                    _apply_layout(device, page)
                device.newPage()
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            page.frame.render_page(
                painter, _target_rect(painter, page, resolution, per_page_layout),
                for_print=True,
                pdf_overlay=bool(pdf_overlay_pages and page.uid in pdf_overlay_pages),
                without_markups=without_markups)
    finally:
        if started:
            painter.end()


def _target_rect(painter: QPainter, page, resolution: float,
                 per_page_layout: bool) -> QRectF:
    """Where this page lands on the device, in device pixels."""
    if per_page_layout:
        scale = resolution / 72.0
        return QRectF(0, 0, page.width_pt * scale, page.height_pt * scale)
    device = painter.device()
    available = QRectF(0, 0, device.width(), device.height())
    scale = min(available.width() / max(page.width_pt, 1.0),
                available.height() / max(page.height_pt, 1.0))
    width = page.width_pt * scale
    height = page.height_pt * scale
    return QRectF((available.width() - width) / 2, (available.height() - height) / 2,
                  width, height)


def outline_and_links(document: Document, printed: list) -> tuple[list, list]:
    """The bookmarks and contents links that belong in the exported PDF.

    Everything is worked out against the pages actually printed, so exporting
    a range does not leave links pointing at pages that are not there.
    """
    from . import pdflinks

    where = {page.uid: index for index, page in enumerate(printed)}
    outline = []
    for mark, _index in document.contents_entries():
        index = where.get(mark.page_uid)
        if index is not None:
            outline.append(pdflinks.Outline(
                mark.title, pdflinks.Destination(index, mark.y), mark.level))

    links = []
    for index, page in enumerate(printed):
        if page.frame is None:
            continue
        height = page.height_pt
        for item in page.frame.markups():
            rows = getattr(item, "rows", None)
            if not rows or not hasattr(item, "row_at"):
                continue
            for rect, target, y in rows:
                on_page = item.mapToParent(rect.topLeft()), item.mapToParent(rect.bottomRight())
                target_index = where.get(document.pages[target].uid) \
                    if 0 <= target < len(document.pages) else None
                if target_index is None:
                    continue
                links.append(pdflinks.Link(
                    index,
                    (on_page[0].x(), height - on_page[1].y(),
                     on_page[1].x(), height - on_page[0].y()),
                    pdflinks.Destination(target_index, y)))
    return outline, links


def _preserved_pdf_pages(document: Document, pages: list) -> set[str]:
    """Imported pages whose untouched source is available for vector export."""
    return {page.uid for page in pages
            if page.frame is not None and page.pdf_key
            and page.pdf_page_index is not None
            and page.background_opacity == 1.0
            and document.asset(page.pdf_key)}


def _paint_pdf(document: Document, path: str, pages: list, resolution: int,
               overlays: Optional[set[str]] = None,
               without_markups: bool = False) -> None:
    writer = QPdfWriter(path)
    writer.setResolution(resolution)
    writer.setTitle(document.title)
    writer.setCreator("MarkForge")
    paint_pages(writer, document, pages, resolution, pdf_overlay_pages=overlays,
                without_markups=without_markups)


def _merge_preserved_pdf_pages(document: Document, path: str, pages: list,
                               preserved: set[str]) -> None:
    """Replace overlay pages with their original PDF page plus that overlay."""
    from pypdf import PdfReader, PdfWriter

    rendered_pages = [page for page in pages if page.frame is not None]
    overlay = PdfReader(path)
    if len(overlay.pages) != len(rendered_pages):
        raise OSError("The PDF overlay page count did not match the document")
    output = PdfWriter()
    readers = []                 # keep source streams alive until writer.write
    for page, overlay_page in zip(rendered_pages, overlay.pages):
        if page.uid not in preserved:
            output.add_page(overlay_page)
            continue
        reader = PdfReader(io.BytesIO(document.asset(page.pdf_key)), strict=False)
        readers.append(reader)
        index = int(page.pdf_page_index)
        if not 0 <= index < len(reader.pages):
            raise OSError("An imported PDF page no longer exists in its source")
        source = reader.pages[index]
        if source.rotation:
            source.transfer_rotation_to_content()
        source.scale_to(float(page.width_pt), float(page.height_pt))
        source.merge_page(overlay_page, over=True)
        output.add_page(source)
    output.add_metadata({"/Title": document.title or "", "/Creator": "MarkForge"})
    temporary = path + ".vector.tmp"
    try:
        with open(temporary, "wb") as handle:
            output.write(handle)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def export_pdf(document: Document, path: str, pages: Optional[list] = None,
               resolution: int = 300, live_markups: bool = True) -> None:
    """Write the document out as a PDF.

    With *live_markups*, the sheet is written without its markups and each one
    goes into the file as a real PDF annotation instead, so that opening the
    export in Bluebeam gives back markups that can be picked up and moved
    rather than a picture of them. Calculations cannot travel as calculations —
    a PDF has no notion of a variable — so each goes out as an ordinary movable
    markup showing the value it held when the export was made.
    """
    from . import annotate

    printed = [page for page in (pages if pages is not None else document.pages)
               if page.printable]
    if not printed:
        raise ValueError("No pages are included in print and export")
    preserved = _preserved_pdf_pages(document, printed)
    if preserved:
        try:
            _paint_pdf(document, path, printed, resolution, preserved,
                       without_markups=live_markups)
            _merge_preserved_pdf_pages(document, path, printed, preserved)
        except Exception:                              # noqa: BLE001
            # A malformed/encrypted source still exports honestly from the
            # screen raster rather than leaving a missing or corrupt page.
            _paint_pdf(document, path, printed, resolution,
                       without_markups=live_markups)
    else:
        _paint_pdf(document, path, printed, resolution,
                   without_markups=live_markups)
    drawn = [page for page in printed if page.frame is not None]
    if live_markups and not annotate.add_markups(path, document, drawn):
        # Nothing could be written as an annotation — an appearance that would
        # not draw, a file pypdf will not reopen. The markups are not left out
        # of the export over it: the sheet is painted again with them on it.
        _paint_the_markups_after_all(document, path, printed, resolution, preserved)
    # Qt has no way to write an outline or a link, so both are appended to the
    # finished file. A failure there costs the bookmarks, never the document.
    from . import pdflinks
    outline, links = outline_and_links(document, drawn)
    try:
        pdflinks.add_outline_and_links(path, outline, links)
    except Exception:                              # noqa: BLE001
        pass


def _paint_the_markups_after_all(document: Document, path: str, printed: list,
                                 resolution: int, preserved: set[str]) -> None:
    """The old way out: everything painted into the sheet."""
    if preserved:
        try:
            _paint_pdf(document, path, printed, resolution, preserved)
            _merge_preserved_pdf_pages(document, path, printed, preserved)
            return
        except Exception:                              # noqa: BLE001
            pass
    _paint_pdf(document, path, printed, resolution)


def pages_for_printer(document: Document, printer: QPrinter) -> list:
    """The pages the print dialog actually asked for."""
    try:
        selection = printer.printRange()
    except Exception:
        return [page for page in document.pages if page.printable]
    if selection == QPrinter.PageRange:
        first = max(printer.fromPage(), 1)
        last = printer.toPage() or len(document.pages)
        return [page for page in document.pages[first - 1:last] if page.printable]
    if selection == QPrinter.CurrentPage:
        return [page for page in document.pages if page.printable]
    return [page for page in document.pages if page.printable]


def print_document(document: Document, printer: QPrinter,
                   pages: Optional[list] = None) -> None:
    chosen = [page for page in (pages if pages is not None
                                else pages_for_printer(document, printer))
              if page.printable]
    if not chosen:
        raise ValueError("No pages are included in print and export")
    paint_pages(printer, document, chosen, printer.resolution(), per_page_layout=False)


def export_images(document: Document, folder: str, dpi: float = 200.0,
                  prefix: str = "page") -> list[str]:
    written = []
    for index, page in enumerate(document.pages):
        if page.frame is None or not page.printable:
            continue
        image = page.frame.render_image(dpi=dpi, for_print=True)
        path = f"{folder}/{prefix}_{index + 1:02d}.png"
        image.save(path, "PNG")
        written.append(path)
    return written


def export_markups_csv(document: Document, path: str) -> int:
    rows = []
    for index, page in enumerate(document.pages):
        if page.frame is None:
            continue
        for item in page.frame.ordered_markups():
            rows.append([index + 1, item.display_name(), item.subject,
                         getattr(item, "value_text", ""), item.author,
                         item.created[:10], item.modified[:10], item.layer,
                         item.summary()])
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Page", "Type", "Subject", "Value", "Author", "Created",
                         "Modified", "Layer", "Comment"])
        writer.writerows(rows)
    return len(rows)

