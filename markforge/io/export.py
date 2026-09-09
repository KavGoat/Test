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
                               preserved: set[str]) -> set:
    """Replace overlay pages with their original PDF page plus that overlay.

    A page that came in from a PDF and has not been altered goes out as that
    PDF's own page — its real line work, its text, its everything — with what
    was painted here laid over the top. A page that is not preserved goes out
    as what was painted, which is all there is of it.

    Where the page is still the size it came in at, it is brought across whole
    rather than placed: the same objects, its own links, and its own
    annotations — which is what the markups nobody has changed still are. The
    ones somebody *has* changed are dropped from it, because this application
    draws those and puts them back as its own.
    """
    import pymupdf

    from ..pdf import engine

    rendered_pages = [page for page in pages if page.frame is not None]
    from_one = _one_source_in_order(document, rendered_pages, preserved)
    if from_one is not None:
        return _stamp_onto_the_source(document, path, rendered_pages, from_one)

    overlay = engine.open_path(path)
    output = pymupdf.open()
    sources: dict[str, object] = {}
    # Which exported sheet each source page became, so a link that pointed at
    # one still points at it.
    landed = {(page.pdf_key, int(page.pdf_page_index)): offset
              for offset, page in enumerate(rendered_pages)
              if page.uid in preserved and page.pdf_page_index is not None}
    carry_over: list = []                 # (sheet, source, index, key)
    carried: set = set()                  # pages that kept their annotations
    try:
        if overlay.page_count != len(rendered_pages):
            raise OSError("The PDF overlay page count did not match the document")
        for offset, page in enumerate(rendered_pages):
            width, height = float(page.width_pt), float(page.height_pt)
            sheet = None
            if page.uid in preserved:
                source = _opened(document, page, sources)
                index = int(page.pdf_page_index)
                if source is None or not 0 <= index < source.page_count:
                    raise OSError("An imported PDF page no longer exists "
                                  "in its source")
                across, down = engine.page_size(source, index)
                if abs(across - width) < 1.0 and abs(down - height) < 1.0:
                    # Grafted, not copied — and MuPDF's grafting quietly drops
                    # most annotations, so this page is *not* reported as
                    # carrying its own. The markups nobody has changed are
                    # redrawn onto it instead: not the author's own objects,
                    # but nothing missing. Only the one-source path above
                    # keeps them exactly.
                    output.insert_pdf(source, from_page=index, to_page=index,
                                      annots=True)
                    sheet = output[-1]
                    _clear_their_markups(sheet, page)
                else:
                    # Fitted onto other paper, so it has to be placed and
                    # scaled — and then its links and the markups nobody has
                    # changed have to be brought over by hand.
                    sheet = output.new_page(-1, width=width, height=height)
                    sheet.show_pdf_page(sheet.rect, source, index)
                    carry_over.append((offset, source, index, page.pdf_key))
            if sheet is None:
                sheet = output.new_page(-1, width=width, height=height)
            sheet.show_pdf_page(sheet.rect, overlay, offset, overlay=True)
        # The links go on once every sheet exists: one that points at a later
        # page cannot be written while that page is still to be made.
        for offset, source, index, key in carry_over:
            _carry_the_links(output[offset], source, index, key, landed)
        output.set_metadata({"title": document.title or "",
                             "creator": "MarkForge", "producer": "MarkForge"})
        # Closes both: the overlay is open on the file being replaced, and
        # Windows will not rename over a file anything still holds.
        engine.save_as(output, path, also=(overlay,))
        output = overlay = None
    finally:
        for source in sources.values():
            engine.close(source)
        engine.close(overlay)
        engine.close(output)
    return carried


def _one_source_in_order(document, rendered_pages: list, preserved: set):
    """The one PDF every page of this export is a kept page of, or None.

    Which is what "open a drawing and export it" is, and the only shape in
    which the source's own annotations can be kept exactly: the file is
    copied and stamped on rather than taken apart and rebuilt, because MuPDF's
    grafting drops most annotations on the way.
    """
    if not rendered_pages:
        return None
    key = rendered_pages[0].pdf_key
    if not key or not document.asset(key):
        return None
    wanted = []
    for page in rendered_pages:
        if page.uid not in preserved or page.pdf_key != key:
            return None
        if page.pdf_page_index is None:
            return None
        wanted.append(int(page.pdf_page_index))
    return key, wanted


def _stamp_onto_the_source(document, path: str, rendered_pages: list,
                           from_one) -> set:
    """The source PDF itself, with what was painted here laid over each page.

    Every annotation of the original survives, because the original is what is
    being written — its own objects, its authors, its dates, its replies and
    the appearances every other reader shows. Only the markups somebody has
    taken over are removed, and those go back on as this application's own.
    """
    from ..pdf import engine

    key, wanted = from_one
    overlay = engine.open_path(path)
    output = None
    try:
        output = engine.open_bytes(document.asset(key))
        if overlay.page_count != len(rendered_pages):
            raise OSError("The PDF overlay page count did not match the document")
        if max(wanted) >= output.page_count:
            raise OSError("An imported PDF page no longer exists in its source")
        output.select(wanted)
        for offset, page in enumerate(rendered_pages):
            sheet = output[offset]
            _clear_their_markups(sheet, page)
            sheet.show_pdf_page(sheet.rect, overlay, offset, overlay=True)
        output.set_metadata({"title": document.title or "",
                             "creator": "MarkForge", "producer": "MarkForge"})
        engine.save_as(output, path, also=(overlay,))
        output = overlay = None
    finally:
        engine.close(overlay)
        engine.close(output)
    return {page.uid for page in rendered_pages}


def _clear_their_markups(sheet, page) -> None:
    """Take off the page's own drawing of every markup somebody has changed.

    The rest stay exactly as their author wrote them — same author, same date,
    same replies, same appearance — which is the whole reason the page is
    kept rather than redrawn. The changed ones go back on afterwards as this
    application's own annotations, and leaving both would show each twice.
    """
    from ..pdf import engine

    frame = page.frame
    if frame is None:
        return
    ours = set(frame.left_to_us(for_print=True))
    if not ours:
        return
    try:
        for annotation in list(sheet.annots()):
            if annotation.xref in ours:
                sheet.delete_annot(annotation)
    except Exception:                                  # noqa: BLE001
        engine.drain_messages()


def _carry_the_links(sheet, source, index: int, key: str, landed: dict) -> None:
    """Bring a source page's links onto the sheet it was exported as.

    Placing a page draws it; it does not bring its links, and a drawing set's
    links are how one sheet points at another. A link to somewhere outside the
    document — a web address, a file — comes across as it is. One that points
    at another page of the same PDF only comes across if that page was exported
    too, remapped to wherever it landed: a link to a sheet that was not printed
    is worse than no link, because it goes somewhere and the somewhere is wrong.
    """
    import pymupdf

    from ..pdf import engine

    try:
        links = source[index].get_links()
    except Exception:                                  # noqa: BLE001
        engine.drain_messages()
        return
    for link in links:
        entry = dict(link)
        entry.pop("xref", None)
        entry.pop("id", None)
        if entry.get("kind") == pymupdf.LINK_GOTO:
            target = landed.get((key, int(entry.get("page", -1))))
            if target is None:
                continue
            entry["page"] = target
        elif entry.get("kind") not in (pymupdf.LINK_URI, pymupdf.LINK_LAUNCH):
            continue                       # a named or remote destination we
                                           # cannot honestly point anywhere
        try:
            sheet.insert_link(entry)
        except Exception:                              # noqa: BLE001
            engine.drain_messages()


def _opened(document: Document, page, sources: dict):
    """The PDF a page came from, opened once for the whole export."""
    from ..pdf import engine

    key = page.pdf_key
    if not key:
        return None
    if key in sources:
        return sources[key]
    data = document.asset(key)
    if not data:
        return None
    try:
        sources[key] = engine.open_bytes(data)
    except engine.PdfError:
        return None
    return sources[key]


def export_pdf(document: Document, path: str, pages: Optional[list] = None,
               resolution: int = 300, live_markups: bool = True) -> None:
    """Write the document out as a PDF.

    With *live_markups*, the page is written without its markups and each one
    goes into the file as a real PDF annotation instead, so that opening the
    export in Bluebeam gives back markups that can be picked up and moved
    rather than a picture of them.
    """
    from . import annotate

    printed = [page for page in (pages if pages is not None else document.pages)
               if page.printable]
    if not printed:
        raise ValueError("No pages are included in print and export")
    preserved = _preserved_pdf_pages(document, printed)
    # The pages that went out carrying their own annotations. On those, the
    # markups nobody has changed are already in the file, exactly as their
    # author wrote them, and must not be redrawn on top.
    carried: set = set()
    if preserved:
        try:
            _paint_pdf(document, path, printed, resolution, preserved,
                       without_markups=live_markups)
            carried = _merge_preserved_pdf_pages(document, path, printed,
                                                 preserved)
        except Exception:                              # noqa: BLE001
            # A malformed/encrypted source still exports honestly from the
            # screen raster rather than leaving a missing or corrupt page.
            carried = set()
            _paint_pdf(document, path, printed, resolution,
                       without_markups=live_markups)
    else:
        _paint_pdf(document, path, printed, resolution,
                   without_markups=live_markups)
    drawn = [page for page in printed if page.frame is not None]
    if live_markups and not annotate.add_markups(path, document, drawn,
                                                 carried):
        # Nothing could be written as an annotation — an appearance that would
        # not draw, or a file that could not be reopened. The markups are not
        # left out of the export over it: the sheet is painted again with
        # them on it.
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
                         item.created[:10], item.modified[:10],
                         item.summary()])
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Page", "Type", "Subject", "Value", "Author", "Created",
                         "Modified", "Comment"])
        writer.writerows(rows)
    return len(rows)

