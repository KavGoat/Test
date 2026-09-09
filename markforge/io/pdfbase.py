"""What a saved document actually is: a PDF.

There is one format and it is PDF. Every document saved here is a real PDF —
it opens in Bluebeam, in Acrobat, in a browser, in anything — and every markup
in it is a real PDF annotation, so it can be picked up and moved wherever it is
opened rather than being ink somebody else is stuck with.

A PDF annotation cannot hold quite everything: the hatch behind a markup, the
holes cut out of it, what it was measured against. Those ride along inside the
same file as an embedded record, so opening the file here again gives back exactly
what was saved, and opening it anywhere else gives back a perfectly ordinary
marked-up PDF. There is no second format and no other extension.
"""
from __future__ import annotations

import io
import json
import os
import zipfile
from typing import Optional

from ..pdf import engine
from ..pdf.engine import PdfError

# The embedded file the markup record travels in. A PDF reader that knows
# nothing about this application shows it as an attachment and is otherwise
# unbothered by it.
RECORD_ENTRY = "markups.json.zip"

DOCUMENT_ENTRY = "document.json"
ASSET_PREFIX = "assets/"

# What the markup appearance is drawn at when it has to be rasterised. The
# imported page's own content is carried through as itself and never resampled;
# this only governs what MarkForge draws on top.
APPEARANCE_DPI = 200


# -- the record ------------------------------------------------------------
def record_bytes(document) -> bytes:
    """The markup record: the document's own account of itself, and its assets."""
    payload = json.dumps(document.to_dict(), indent=1, ensure_ascii=False)
    holder = io.BytesIO()
    with zipfile.ZipFile(holder, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(DOCUMENT_ENTRY, payload)
        for key, data in document.assets.items():
            archive.writestr(ASSET_PREFIX + key, data)
    return holder.getvalue()


def read_record(data: bytes) -> tuple[dict, dict[str, bytes]]:
    """The document record and its assets, back out of the bytes."""
    with zipfile.ZipFile(io.BytesIO(data), "r") as archive:
        record = json.loads(archive.read(DOCUMENT_ENTRY).decode("utf-8"))
        assets = {entry[len(ASSET_PREFIX):]: archive.read(entry)
                  for entry in archive.namelist()
                  if entry.startswith(ASSET_PREFIX) and not entry.endswith("/")}
    return record, assets


def is_pdf(path: str) -> bool:
    return engine.is_pdf(path)


def record_in(path: str) -> Optional[bytes]:
    """The markup record inside the PDF at *path*, if it carries one.

    An incrementally updated PDF can carry the same attachment more than once,
    the later one overriding the earlier. MuPDF reads the file's current name
    tree, so what comes back is the one a reader would see — the current one.
    """
    if not is_pdf(path):
        return None
    try:
        document = engine.open_path(path)
    except PdfError:
        return None
    try:
        return engine.embedded(document, RECORD_ENTRY)
    finally:
        engine.close(document)


# -- writing ---------------------------------------------------------------
def write(document, path: str, appearance: bool = True) -> None:
    """Write *document* to *path* as a PDF carrying its markup record.

    Two ways, and which one is used depends on what the document is.

    A document that *is* one PDF with markups on it — a drawing opened, marked
    up and saved — is written as an incremental update to that PDF by
    :mod:`markforge.io.pdfsave`: the original bytes are kept exactly, and the
    markups are appended. Anything else is assembled page by page here.
    """
    from . import pdfsave

    original = pdfsave.source_bytes(document)
    if original is not None:
        try:
            pdfsave.save(document, path, original, appearance=appearance)
            return
        except Exception:                              # noqa: BLE001
            # Never lose a save over the clever path. The file is assembled
            # instead, which is what every earlier version did.
            pass
    _assemble(document, path, appearance=appearance)


def _assemble(document, path: str, appearance: bool = True) -> None:
    """Build the file page by page, from whatever each page came from."""
    import pymupdf

    output = pymupdf.open()
    sources: dict[str, object] = {}       # the PDFs pages are coming from
    # Scratch files the pages were drawn into. They are kept until the file
    # they were grafted into is shut, because until then it holds them open —
    # and a file anything holds open is a file Windows will not delete.
    leftovers: list = []
    carried: set = set()                  # pages that kept their annotations
    try:
        for page in document.pages:
            if _add_page_body(output, document, page, sources):
                carried.add(page.uid)
        if appearance:
            _draw_the_sheets_onto(output, document, leftovers)
        engine.embed(output, RECORD_ENTRY, record_bytes(document))
        output.set_metadata({"title": document.title or "",
                             "creator": "MarkForge",
                             "producer": "MarkForge"})
        engine.save_as(output, path)
    finally:
        for source in sources.values():
            engine.close(source)
        engine.close(output)
        for scratch in leftovers:
            _throw_away(scratch)
    if appearance:
        # The markups go in as real annotations, not as ink on the page. A
        # saved document is a PDF that anybody can open, and a markup that
        # cannot be picked up in the editor it is opened in is a picture of a
        # markup. The record is still what this application reads back.
        from . import annotate

        annotate.add_markups(path, document, _drawn_pages(document), carried)


def _add_page_body(output, document, page, sources: dict) -> bool:
    """One page of the file: the PDF it came from, or paper of the right size.

    A page imported from a PDF keeps that PDF's own page — its real line
    information, its text, its everything — rather than a picture of it. That
    is what makes an imported drawing still a drawing after a round trip.

    Where the page is still the size it came in at, the source page is brought
    across whole: the same objects, its own annotations, its links. Where it
    has been fitted onto other paper it is placed onto a sheet of the new size
    instead, which scales the drawing but cannot scale annotations with it —
    those are already markups here, and go back on as markups.

    Says whether the page kept its own annotations, because the markups
    nobody has changed *are* those annotations and must not be drawn again on
    top of them.
    """
    width, height = float(page.width_pt), float(page.height_pt)
    source = _source_for(document, page, sources)
    index = int(page.pdf_page_index) if page.pdf_page_index is not None else -1
    if source is None or not 0 <= index < source.page_count:
        output.new_page(-1, width=width, height=height)
        return False
    across, down = engine.page_size(source, index)
    wanted = output.page_count + 1
    try:
        if abs(across - width) < 1.0 and abs(down - height) < 1.0:
            output.insert_pdf(source, from_page=index, to_page=index,
                              annots=True)
            _drop_the_ones_taken_over(output[-1], page)
            return True
        sheet = output.new_page(-1, width=width, height=height)
        sheet.show_pdf_page(sheet.rect, source, index)
    except Exception:                                  # noqa: BLE001
        # A source that cannot be read is not worth losing the save over: the
        # page still comes out, the record still holds everything, and the
        # markups are still drawn onto it below.
        engine.drain_messages()
        if output.page_count < wanted:
            output.new_page(-1, width=width, height=height)
    return False


def _drop_the_ones_taken_over(sheet, page) -> None:
    """Take off the page's own drawing of every markup somebody has changed.

    The rest stay exactly as their author wrote them. The changed ones go back
    on afterwards as this application's own annotations, and leaving both
    would show each of them twice.
    """
    frame = getattr(page, "frame", None)
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


def _source_for(document, page, sources: dict):
    """The PDF a page came from, opened once and kept for the whole write."""
    key = page.pdf_key
    if not key or page.pdf_page_index is None:
        return None
    if key in sources:
        return sources[key]
    data = document.asset(key)
    if not data:
        return None
    try:
        source = engine.open_bytes(data)
    except PdfError:
        return None
    sources[key] = source
    return source


def _drawn_pages(document) -> list:
    """The pages that can be drawn — the ones the UI has built a scene for."""
    return [page for page in document.pages if page.frame is not None]


def _draw_the_sheets_onto(output, document, leftovers: list) -> None:
    """Paint the sheet itself onto the pages — everything but the markups.

    The paper, the grid, the running header and footer, the page's own line
    work and anything flattened into it. The markups are not painted: they go
    in afterwards as annotations, so they can still be moved wherever the file
    is opened. This needs a scene to draw from; a document that has not been
    opened in a window has none, and then the file is still a correct PDF of
    the pages themselves.
    """
    drawn = _drawn_pages(document)
    if not drawn:
        return
    overlay_path = None
    overlay = None
    try:
        overlay_path = _rendered_overlay(document, drawn)
        if overlay_path is None:
            return
        leftovers.append(overlay_path)
        overlay = engine.open_path(overlay_path)
        if overlay.page_count != len(drawn):
            return
        where = {id(page): index for index, page in enumerate(document.pages)}
        for offset, page in enumerate(drawn):
            index = where.get(id(page))
            if index is None or not 0 <= index < output.page_count:
                continue
            sheet = output[index]
            sheet.show_pdf_page(sheet.rect, overlay, offset, overlay=True)
    except Exception:                                  # noqa: BLE001
        # Never lose a save over its appearance elsewhere.
        engine.drain_messages()
        return
    finally:
        engine.close(overlay)


def _rendered_overlay(document, drawn: list) -> Optional[str]:
    """The sheet itself, without its markups, on pages in a scratch file."""
    import tempfile

    from PySide6.QtGui import QPdfWriter

    from . import export

    handle, overlay_path = tempfile.mkstemp(suffix=".pdf")
    os.close(handle)
    over_the_source = {page.uid for page in drawn
                       if page.pdf_key and page.pdf_page_index is not None
                       and page.background_opacity == 1.0
                       and document.asset(page.pdf_key)}
    writer = QPdfWriter(overlay_path)
    writer.setResolution(APPEARANCE_DPI)
    writer.setCreator("MarkForge")
    export.paint_pages(writer, document, drawn, APPEARANCE_DPI,
                       pdf_overlay_pages=over_the_source,
                       without_markups=True)
    del writer
    if os.path.getsize(overlay_path) < 1:
        _throw_away(overlay_path)
        return None
    return overlay_path


def _throw_away(path: str) -> None:
    """Get rid of a scratch file, and never mind if it will not go.

    A file left in the temp folder is a nuisance; a save that fails because of
    one is a lost drawing.
    """
    from .annotate import _sweep_up_later

    try:
        os.remove(path)
    except OSError:
        _sweep_up_later(path)


# -- reading ---------------------------------------------------------------
def read(document, path: str) -> bool:
    """Load *path* into *document*. True when it carried a markup record."""
    found = record_in(path)
    if found is None:
        return False
    record, assets = read_record(found)
    document.assets = assets
    document.load_dict(record)
    document.path = path
    document.modified = False
    return True
