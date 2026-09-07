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
    try:
        with open(path, "rb") as handle:
            return handle.read(5).startswith(b"%PDF")
    except OSError:
        return False


def record_in(path: str) -> Optional[bytes]:
    """The markup record inside the PDF at *path*, if it carries one."""
    if not is_pdf(path):
        return None
    from pypdf import PdfReader

    try:
        reader = PdfReader(path, strict=False)
        found = reader.attachments.get(RECORD_ENTRY)
    except Exception:                                  # noqa: BLE001
        return None
    if not found:
        return None
    # pypdf hands back every embedded file of that name; the last one written
    # is the current one, which is what an incrementally updated PDF means.
    return bytes(found[-1])


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
    from pypdf import PdfWriter

    output = PdfWriter()
    keep_alive: list = []                 # source readers, until the write
    for page in document.pages:
        output.add_page(_page_body(document, page, keep_alive))
    if appearance:
        _draw_the_sheets_onto(output, document)
    output.add_attachment(RECORD_ENTRY, record_bytes(document))
    output.add_metadata({"/Title": document.title or "", "/Creator": "MarkForge"})
    temporary = path + ".tmp"
    with open(temporary, "wb") as handle:
        output.write(handle)
    os.replace(temporary, path)
    if appearance:
        # The markups go in as real annotations, not as ink on the page. A
        # saved document is a PDF that anybody can open, and a markup that
        # cannot be picked up in the editor it is opened in is a picture of a
        # markup. The record is still what this application reads back.
        from . import annotate

        annotate.add_markups(path, document, _drawn_pages(document))


def _page_body(document, page, keep_alive: list):
    """One page of the file: the PDF it came from, or paper of the right size.

    A page imported from a PDF keeps that PDF's own page — its real line
    information, its text, its everything — rather than a picture of it. That
    is what makes an imported drawing still a drawing after a round trip.
    """
    from pypdf import PdfWriter

    source = _source_page(document, page, keep_alive)
    if source is not None:
        return source
    blank = PdfWriter()
    return blank.add_blank_page(float(page.width_pt), float(page.height_pt))


def _source_page(document, page, keep_alive: list):
    from pypdf import PdfReader

    data = document.asset(page.pdf_key) if page.pdf_key else None
    if not data or page.pdf_page_index is None:
        return None
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        keep_alive.append(reader)
        index = int(page.pdf_page_index)
        if not 0 <= index < len(reader.pages):
            return None
        source = reader.pages[index]
        if source.rotation:
            source.transfer_rotation_to_content()
        source.scale_to(float(page.width_pt), float(page.height_pt))
        return source
    except Exception:                                  # noqa: BLE001
        # A source that cannot be read is not worth losing the save over: the
        # page still comes out, the record still holds everything, and the
        # markups are still drawn onto it below.
        return None


def _drawn_pages(document) -> list:
    """The pages that can be drawn — the ones the UI has built a scene for."""
    return [page for page in document.pages if page.frame is not None]


def _draw_the_sheets_onto(output, document) -> None:
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
    try:
        overlay_path = _rendered_overlay(document, drawn)
        if overlay_path is None:
            return
        from pypdf import PdfReader

        with open(overlay_path, "rb") as handle:
            overlay = PdfReader(io.BytesIO(handle.read()), strict=False)
        if len(overlay.pages) != len(drawn):
            return
        where = {id(page): index for index, page in enumerate(document.pages)}
        for page, marks in zip(drawn, overlay.pages):
            index = where.get(id(page))
            if index is None:
                continue
            output.pages[index].merge_page(marks, over=True)
    except Exception:                                  # noqa: BLE001
        # Never lose a save over its appearance elsewhere.
        return
    finally:
        if overlay_path and os.path.exists(overlay_path):
            os.remove(overlay_path)


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
        os.remove(overlay_path)
        return None
    return overlay_path


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
