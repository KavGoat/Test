"""What a saved document actually is: a PDF, with the calculation layer in it.

This is a PDF editor that can also do calculations, and the file format follows
from that. Every document saved by CalcForge is a real PDF — it opens in
Bluebeam, in a browser, in anything — and the parts a PDF has no way to hold,
the calculations and everything else CalcForge knows about a markup, ride
along inside it as an embedded file.

So there is only one file. A drawing set that has been marked up and never
calculated on is a PDF and is named one. Put a calculation on it and the same
bytes are named ``.cfx``: the calculation layer is an addition to the PDF, not
a replacement for it, and renaming a ``.cfx`` to ``.pdf`` loses nothing but the
calculations' ability to be edited again.
"""
from __future__ import annotations

import io
import json
import os
import zipfile
from typing import Optional

# The embedded file the calculation layer travels in. A PDF reader that knows
# nothing about CalcForge shows it as an attachment and is otherwise unbothered.
LAYER_ENTRY = "calcforge.cfx"

DOCUMENT_ENTRY = "document.json"
ASSET_PREFIX = "assets/"

# Item types that are calculations rather than markups. What decides whether a
# document is a PDF or a PDF with a calculation layer.
CALCULATION_TYPES = {"math", "table", "plot"}

# What the markup appearance is drawn at when it has to be rasterised. The
# imported page's own content is carried through as itself and never resampled;
# this only governs what CalcForge draws on top.
APPEARANCE_DPI = 200


# -- what is in the document ----------------------------------------------
def has_calculations(document) -> bool:
    """Whether this document is a PDF with a calculation layer, or just a PDF."""
    for page in document.pages:
        for item in page.to_dict().get("items", []):
            if item.get("type") in CALCULATION_TYPES:
                return True
    return False


# -- the layer -------------------------------------------------------------
def layer_bytes(document) -> bytes:
    """The calculation layer: the document's own record, and its assets."""
    payload = json.dumps(document.to_dict(), indent=1, ensure_ascii=False)
    holder = io.BytesIO()
    with zipfile.ZipFile(holder, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(DOCUMENT_ENTRY, payload)
        for key, data in document.assets.items():
            archive.writestr(ASSET_PREFIX + key, data)
    return holder.getvalue()


def read_layer(data: bytes) -> tuple[dict, dict[str, bytes]]:
    """A layer's document record and assets, back out of the bytes."""
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


def layer_in(path: str) -> Optional[bytes]:
    """The calculation layer inside the PDF at *path*, if it carries one."""
    if not is_pdf(path):
        return None
    from pypdf import PdfReader

    try:
        reader = PdfReader(path, strict=False)
        found = reader.attachments.get(LAYER_ENTRY)
    except Exception:                                  # noqa: BLE001
        return None
    if not found:
        return None
    # pypdf hands back every embedded file of that name; the last one written
    # is the current one, which is what an incrementally updated PDF means.
    return bytes(found[-1])


# -- writing ---------------------------------------------------------------
def write(document, path: str, appearance: bool = True) -> None:
    """Write *document* to *path* as a PDF carrying its calculation layer."""
    from pypdf import PdfWriter

    output = PdfWriter()
    keep_alive: list = []                 # source readers, until the write
    for page in document.pages:
        output.add_page(_page_body(document, page, keep_alive))
    if appearance:
        _draw_the_sheets_onto(output, document)
    output.add_attachment(LAYER_ENTRY, layer_bytes(document))
    output.add_metadata({"/Title": document.title or "", "/Creator": "CalcForge"})
    temporary = path + ".tmp"
    with open(temporary, "wb") as handle:
        output.write(handle)
    os.replace(temporary, path)
    if appearance:
        # The markups go in as real annotations, not as ink on the page. A
        # saved document is a PDF that anybody can open, and a markup that
        # cannot be picked up in the editor it is opened in is a picture of a
        # markup. The layer is still what CalcForge reads back.
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
        # page still comes out, the layer still holds everything, and the
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
    writer.setCreator("CalcForge")
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
    """Load *path* into *document*. True when it carried a calculation layer."""
    found = layer_in(path)
    if found is None:
        return False
    record, assets = read_layer(found)
    document.assets = assets
    document.load_dict(record)
    document.path = path
    document.modified = False
    return True
