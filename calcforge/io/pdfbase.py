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
# What the calc layer is drawn at: the resolution SMath's layout measures its
# fonts at (see _rendered_overlay).
CALC_DPI = 96


# -- the record ------------------------------------------------------------
# What the record says about the file it is inside (io/calclayer.py): which
# assets the file's own pages stand in for, and a fingerprint of the calc
# layer written on each page.
FILE_FACTS = "calcforge_file"


def record_bytes(document, facts: Optional[dict] = None) -> bytes:
    """The markup record: the document's own account of itself, and its assets.

    With *facts* the record is going into a file whose pages are the pages'
    own sources: the PDFs they came from are not stored again (the file is
    them, once CalcForge's layers are taken off), and each markup that is
    still somebody else's annotation is named by what it is rather than by an
    object number, because the saved file numbers its objects afresh.
    """
    data = document.to_dict()
    assets = document.assets
    if facts is not None:
        data[FILE_FACTS] = {key: value for key, value in facts.items()
                            if not key.startswith("_")}
        itself = set(facts.get("itself", ()))
        assets = {key: value for key, value in assets.items() if key not in itself}
        held = set(facts.get("held_back", ()))
        for page in data.get("pages", []):
            if page.get("uid") in held and page.get("pdf_key") in itself:
                # a page held back stood on this file's page, which it no
                # longer has: it is CalcForge's own page again
                page["pdf_key"] = None
                page["pdf_page_index"] = None
        prints = facts.get("_prints", {})
        written = facts.get("_ours", {})
        for page in data.get("pages", []):
            for payload in _payloads(page.get("items", [])):
                made = written.get(payload.get("uid"))
                if made:
                    payload["written_print"] = made
            known = prints.get(page.get("uid"), {})
            page["markup_prints"] = [known[number] for number in
                                     page.get("markup_annotations", ()) if number in known]
            for payload in _payloads(page.get("items", [])):
                number = payload.get("from_annotation")
                if number and number in known:
                    payload["annotation_print"] = known[number]
    payload = json.dumps(data, indent=1, ensure_ascii=False)
    holder = io.BytesIO()
    with zipfile.ZipFile(holder, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(DOCUMENT_ENTRY, payload)
        for key, value in assets.items():
            archive.writestr(ASSET_PREFIX + key, value)
    return holder.getvalue()


def _payloads(items):
    """Every markup payload in a page's items, groups' members included."""
    for payload in items or ():
        if isinstance(payload, dict):
            yield payload
            for key in ("items", "children", "members"):
                if isinstance(payload.get(key), list):
                    yield from _payloads(payload[key])


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
def write(document, path: str, appearance: bool = True) -> str:
    """Write *document* to *path* as a PDF carrying its markup record.

    Every save writes a fresh, compact file (decision 4), so the file never
    grows however often it is saved. The one exception is a digitally signed
    PDF: rewriting it would break the signature, so it is appended to instead
    (:mod:`calcforge.io.pdfsave`), with CalcForge's layers swapped in the
    appended part. Says why when it did that, or why it could not.
    """
    from . import pdfsave

    note = ""
    signed = getattr(document, "signed_source", None)
    if signed is not None:
        original = pdfsave.source_bytes(document)
        if original is not None:
            try:
                pdfsave.save(document, path, original, appearance=appearance)
                return "Appended to the file, because it is digitally signed"
            except Exception:                          # noqa: BLE001
                # Never lose a save over the signature. The file is written
                # afresh, and says so.
                pass
        note = ("The file was digitally signed; its pages have changed, so it was "
                "saved afresh and the signature no longer applies")
    _assemble(document, path, appearance=appearance)
    if signed is not None:
        document.signed_source = None             # what was written is not signed
    return note


def held_back(document) -> list:
    """The pages not written as pages of the saved PDF: a spreadsheet's
    pages that don't print (the user, 2026-10-21: a sheet marked Don't
    Print). Other readers — Acrobat, Revu, a browser — then neither show nor
    print them, where an optional content group set not to print would still
    print each as a blank sheet; CalcForge's record keeps them whole, and
    they come back where they were when the file is opened here. Pages that
    came from somebody's PDF are always written (the file is their copy), and
    a file must have a page, so a document whose every page would be held
    back is written whole."""
    held = [page for page in document.pages
            if getattr(page, "sheet", None) is not None and not page.printable]
    return held if len(held) < len(document.pages) else []


def _assemble(document, path: str, appearance: bool = True) -> None:
    """Build the file page by page, from whatever each page came from, in
    memory, and write it once."""
    import pymupdf

    from . import calclayer

    held = held_back(document)
    if held:
        gone = {id(page) for page in held}
        written = [page for page in document.pages if id(page) not in gone]
    else:
        written = list(document.pages)

    output = pymupdf.open()
    sources: dict[str, object] = {}       # the PDFs pages are coming from
    # Scratch files the pages were drawn into, and the files opened on them.
    # They are kept until the file they were grafted into is shut, because
    # until then it holds them open — and a file anything holds open is a
    # file Windows will not delete.
    leftovers: list = []
    opened: list = []
    appearances = None
    carried: set = set()                  # pages that kept their annotations
    try:
        whole = _one_source_whole(document, written)
        if whole is not None:
            # Every page is a page of one PDF at its own size: that PDF is
            # copied and its pages picked out, rather than each page grafted
            # into a new file — grafting drops most annotations on the way,
            # and these are somebody's markups, to be kept exactly.
            key, wanted = whole
            engine.close(output)
            output = engine.open_bytes(document.asset(key))
            sources[key] = engine.open_bytes(document.asset(key))
            output.select(wanted)
            for index, page in enumerate(written):
                _drop_the_ones_taken_over(output[index], page)
                carried.add(page.uid)
        else:
            for page in written:
                if _add_page_body(output, document, page, sources):
                    carried.add(page.uid)
        for index, page in enumerate(written):
            calclayer.mark_page(output, index, page.uid)
        layers: dict = {}
        if appearance:
            _draw_a_layer(output, document, leftovers, opened, calclayer.SHEET, written)
            layers = _draw_a_layer(output, document, leftovers, opened, calclayer.CALC,
                                   written)
            # The markups go in as real annotations, not as ink on the page.
            # A saved document is a PDF that anybody can open, and a markup
            # that cannot be picked up in the editor it is opened in is a
            # picture of a markup. The record is still what this application
            # reads back.
            appearances = _place_the_markups(output, document, carried, opened, written)
            from .export import outline_and_links
            from . import pdflinks
            outline, links = outline_and_links(
                document, [page for page in written if page.frame is not None])
            pdflinks._set_outline(output, outline)
            pdflinks._add_links(output, links)
        facts = _file_facts(document, sources, carried, layers, output)
        if held:
            facts["held_back"] = [page.uid for page in held]
        engine.embed(output, RECORD_ENTRY, record_bytes(document, facts))
        output.set_metadata(pdf_properties(document))
        engine.save_as(output, path, also=tuple(opened))
        output = None
        opened = []
    finally:
        for source in sources.values():
            engine.close(source)
        engine.close(output)
        for held in opened:
            engine.close(held)
        if appearances is not None:
            appearances.discard()
        for scratch in leftovers:
            _throw_away(scratch)


def _one_source_whole(document, pages: Optional[list] = None):
    """(key, page numbers) when every page (of *pages*, the ones written) is
    a page of one PDF at its own size, else None."""
    pages = document.pages if pages is None else pages
    if not pages:
        return None
    key = pages[0].pdf_key
    data = document.asset(key)
    if not key or not data:
        return None
    wanted = []
    for page in pages:
        if page.pdf_key != key or page.pdf_page_index is None:
            return None
        wanted.append(int(page.pdf_page_index))
    try:
        source = engine.open_bytes(data)
    except PdfError:
        return None
    try:
        for page, index in zip(pages, wanted):
            if not 0 <= index < source.page_count:
                return None
            across, down = engine.page_size(source, index)
            if abs(across - page.width_pt) >= 1.0 or abs(down - page.height_pt) >= 1.0:
                return None
    finally:
        engine.close(source)
    return key, wanted


def pdf_properties(document) -> dict:
    """The PDF's standard properties (decision 28): title, author, subject and
    keywords, which any reader shows in its File > Properties. The rest of
    the document's properties stay in CalcForge's record."""
    return {"title": document.title or "", "author": document.author or "",
            "subject": document.subject or "", "keywords": document.keywords or "",
            "creator": "CalcForge", "producer": "CalcForge"}


def _file_facts(document, sources: dict, carried: set, layers: dict,
                output=None) -> dict:
    """What the record says about the file around it (see :func:`record_bytes`)."""
    from . import calclayer

    itself = sorted({page.pdf_key for page in document.pages if page.pdf_key})
    prints: dict = {}
    for page in document.pages:
        if page.uid not in carried or page.pdf_key not in sources:
            continue
        source = sources[page.pdf_key]
        known = {}
        wanted = set(page.markup_annotations)
        frame = page.frame
        if frame is not None:
            wanted |= frame.annotation_links()        # (nothing built for the asking)
        else:
            wanted |= {int(payload.get("from_annotation") or 0)
                       for payload in page._pending_items if isinstance(payload, dict)}
        for number in wanted:
            if number:
                known[number] = calclayer.annotation_print(source, number)
        prints[page.uid] = known
    return {"version": 1, "itself": itself, "calc_layers": layers, "_prints": prints,
            "_ours": {} if output is None else _ours_written(output)}


def _ours_written(output) -> dict:
    """Each annotation CalcForge wrote, by its markup's uid: its
    fingerprint, so an edit made to it in another program is noticed."""
    from . import calclayer

    found = {}
    for index in range(output.page_count):
        for number in engine.annotation_xrefs(output, index):
            if output.xref_get_key(number, calclayer.KEY)[0] != "name":
                continue
            kind, name = output.xref_get_key(number, "NM")
            if kind == "string" and name:
                found[name] = calclayer.annotation_print(output, number)
    return found


def _place_the_markups(output, document, carried: set, opened: list,
                       pages: Optional[list] = None):
    """Every markup that is not already its own annotation, as one of ours."""
    from . import annotate

    appearances = annotate.markups_to_place(
        document, document.pages if pages is None else pages, carried)
    if not appearances.entries:
        return appearances
    try:
        if appearances.draw() is None:
            return appearances
        scratch = engine.open_path(appearances.path)
        opened.append(scratch)
        if scratch.page_count == len(appearances.entries):
            annotate.place_markups(output, scratch, appearances, keep_existing=True)
    except Exception:                                  # noqa: BLE001
        # Never lose a save over its annotations: the record still holds
        # every markup, and they come back when the file is opened here.
        engine.drain_messages()
    return appearances


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


def _draw_a_layer(output, document, leftovers: list, opened: list,
                  kind: str, pages: Optional[list] = None) -> dict:
    """Paint one of CalcForge's layers onto the pages, tagged as such.

    The sheet (``SHEET``) is everything but the markups and the equations:
    the paper of a page written on here, the running header and footer, the
    page's own line work and anything flattened into it. The markups are not
    painted — they go in as annotations — and the equations have a layer of
    their own (``CALC``): vector drawing and real text, which other readers
    show and search but cannot move. Both are taken off again when the file
    is opened here (io/calclayer.py).

    This needs a scene to draw from; a document that has not been opened in a
    window has none, and then the file is still a correct PDF of the pages.
    Says, for each page given the calc layer, its fingerprint.
    """
    from . import calclayer

    written = document.pages if pages is None else pages
    # (a page whose markups are all still its file's, not even read yet, has
    # nothing of ours to draw, and is not built for a save)
    drawn = [page for page in written if page.frame is not None and not page.frame.file_only()]
    if kind == calclayer.CALC:
        drawn = [page for page in drawn
                 if getattr(page, "sheet", None) is not None
                 or any(getattr(item, "IS_CALC", False) and item.printable
                        for item in page.frame.markups())]
    if not drawn:
        return {}
    prints: dict = {}
    try:
        overlay_path = _rendered_overlay(document, drawn, kind)
        if overlay_path is None:
            return {}
        leftovers.append(overlay_path)
        overlay = engine.open_path(overlay_path)
        opened.append(overlay)
        if overlay.page_count != len(drawn):
            return {}
        where = {id(page): index for index, page in enumerate(written)}
        for offset, page in enumerate(drawn):
            index = where.get(id(page))
            if index is None or not 0 <= index < output.page_count:
                continue
            made = calclayer.place_layer(output, index, overlay, offset, kind)
            if made is not None:
                prints[page.uid] = made
        if kind == calclayer.SHEET:
            _multiply_what_multiplies(output, document, drawn, leftovers, opened, where)
    except Exception:                                  # noqa: BLE001
        # Never lose a save over its appearance elsewhere.
        engine.drain_messages()
    return prints


def _multiply_what_multiplies(output, document, drawn: list, leftovers: list, opened: list,
                              where: dict) -> None:
    """Flattened markups that multiply onto the page — a highlighted shape's
    inside, a highlighter's stroke — drawn on a sheet layer of their own
    whose form multiplies (ExtGState /BM /Multiply): a PDF writer cannot,
    and the sheet left that part out."""
    from . import calclayer
    wanted = [page for page in drawn
              if any(item.flattened and item.printable and item.isVisible()
                     and getattr(item, "multiplies", lambda: False)()
                     for item in page.frame.markups())]
    if not wanted:
        return
    overlay_path = _rendered_overlay(document, wanted, "sheet_multiply")
    if overlay_path is None:
        return
    leftovers.append(overlay_path)
    overlay = engine.open_path(overlay_path)
    opened.append(overlay)
    if overlay.page_count != len(wanted):
        return
    for offset, page in enumerate(wanted):
        index = where.get(id(page))
        if index is None or not 0 <= index < output.page_count:
            continue
        calclayer.place_multiplied(output, index, overlay, offset)
    # and a highlighted shape's border over its inside, as it is drawn
    bordered = [page for page in wanted
                if any(item.flattened and item.printable and item.isVisible()
                       and item.multiplies_inside_only() for item in page.frame.markups())]
    if not bordered:
        return
    over_path = _rendered_overlay(document, bordered, "sheet_over")
    if over_path is None:
        return
    leftovers.append(over_path)
    over = engine.open_path(over_path)
    opened.append(over)
    if over.page_count != len(bordered):
        return
    for offset, page in enumerate(bordered):
        index = where.get(id(page))
        if index is not None and 0 <= index < output.page_count:
            calclayer.place_layer(output, index, over, offset, calclayer.SHEET)


def _rendered_overlay(document, drawn: list, kind: str) -> Optional[str]:
    """One layer of the pages, on pages in a scratch file."""
    import tempfile

    from PySide6.QtGui import QPdfWriter

    from . import calclayer, export

    handle, overlay_path = tempfile.mkstemp(suffix=".pdf")
    os.close(handle)
    over_the_source = {page.uid for page in drawn
                       if page.pdf_key and page.pdf_page_index is not None
                       and page.background_opacity == 1.0
                       and document.asset(page.pdf_key)}
    # The equations' fonts are sized in points and Qt turns points into
    # pixels by the device's resolution: drawn at anything but the screen's
    # 96 dpi, the letters come out a different size from the layout they
    # were measured for, and run into each other.
    resolution = CALC_DPI if kind == calclayer.CALC else APPEARANCE_DPI
    writer = QPdfWriter(overlay_path)
    writer.setResolution(resolution)
    writer.setCreator("CalcForge")
    export.paint_pages(writer, document, drawn, resolution,
                       pdf_overlay_pages=over_the_source,
                       without_markups=True,
                       layer="calc" if kind == calclayer.CALC
                       else kind if kind in ("sheet_multiply", "sheet_over") else "sheet")
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
    """Load *path* into *document*. True when it carried a markup record.

    Anything worth telling the reader about how the file was found — the calc
    layer edited in another program, pages deleted elsewhere — is left in
    ``document.open_warnings``.
    """
    found = record_in(path)
    if found is None:
        return False
    record, assets = read_record(found)
    document.open_warnings = []
    document.deleted_elsewhere = []
    document.signed_source = None
    if isinstance(record.get(FILE_FACTS), dict):
        with open(path, "rb") as handle:
            data = handle.read()
        _take_the_file_back(document, data, record, assets)
    document.assets = assets
    document.load_dict(record)
    document.path = path
    document.modified = False
    return True


def _take_the_file_back(document, data: bytes, record: dict, assets: dict) -> None:
    """The file's own pages, with CalcForge's layers off, as their source.

    The pages are matched to the record by the uid each carries, so a reorder
    or a deletion done elsewhere is followed (decision 3): the record's pages
    are put in the file's order, a page the file no longer has goes, with its
    equations, and a page the record never had comes in as a plain page.
    """
    import uuid

    from . import calclayer

    facts = record[FILE_FACTS]
    written = facts.get("calc_layers") or {}
    itself = set(facts.get("itself") or ())
    source = engine.open_bytes(data)
    try:
        signed = calclayer.is_signed(source)
        record_pages = {page.get("uid"): page for page in record.get("pages", [])}
        record_order = [page.get("uid") for page in record.get("pages", [])]
        # a spreadsheet's pages that don't print were not written as pages
        # (held_back): they come back from the record, where they were
        kept_back = [record_pages.pop(uid) for uid in facts.get("held_back") or ()
                     if uid in record_pages]
        key = f"asset_{uuid.uuid4().hex[:12]}.pdf"
        pages: list = []
        changed: list = []
        foreign: dict = {}                       # file page index -> annotations to read
        for index in range(source.page_count):
            uid = calclayer.page_uid(source, index)
            page = record_pages.pop(uid, None) if uid else None
            there = calclayer.layer_print(source, index, calclayer.CALC)
            if page is not None and written.get(uid) != there and \
                    (uid in written or there is not None):
                changed.append(index + 1)
            calclayer.strip(source, index)
            if page is None:
                page = _plain_page(source, index)
                page["pdf_key"] = key
                page["written_here"] = False
            elif page.get("pdf_key") and (page["pdf_key"] in itself
                                          or page["pdf_key"] not in assets):
                page["pdf_key"] = key
                page["pdf_page_index"] = index
            elif not page.get("pdf_key") and not page.get("background_key"):
                # A page written here: the file's page is under it from now
                # on too, so whatever another program left on it — a markup
                # as they drew it, a stamp pressed into it — shows as it does
                # there. It is still a written page, with SMath's margins.
                page["pdf_key"] = key
                page["pdf_page_index"] = index
                if page.get("written_here") is None:
                    page["written_here"] = True
            if page.get("annotations_unread") is not None:
                # never read as markups: nothing of ours is on the page, and
                # they are read when it is looked at (Page.from_dict)
                pages.append(page)
                continue
            new, replaced = _sort_the_annotations(source, index, page)
            if new:
                foreign[index] = (new, replaced)
            pages.append(page)
        cleaned = source.tobytes(garbage=0)
    finally:
        engine.close(source)
    assets[key] = cleaned
    for index, (numbers, replaced) in foreign.items():
        _read_their_markups(document, cleaned, index, pages[index], numbers, assets,
                            replaced)
    for page in sorted(kept_back, key=lambda p: record_order.index(p.get("uid"))):
        at = record_order.index(page.get("uid"))
        placed = {other.get("uid"): k for k, other in enumerate(pages)}
        before = next((placed[uid] for uid in reversed(record_order[:at]) if uid in placed), -1)
        for payload in _payloads(page.get("items", [])):
            payload.pop("annotation_print", None)     # (only a written page's are read)
            payload.pop("written_print", None)
        page.pop("markup_prints", None)
        pages.insert(before + 1, page)
    gone = list(record_pages.values())
    # What was deleted, as it was saved here, for Restore — taken before a
    # spreadsheet's cells are moved off its deleted first page below
    import copy

    document.deleted_elsewhere = []
    for page in gone:
        at = record_order.index(page.get("uid"))
        # the page it came after as saved (restored together, a deleted
        # page before it is back by then)
        before = record_order[at - 1] if at > 0 else None
        drawing_lost = bool(page.get("pdf_key") and page["pdf_key"] in itself
                            and not page.get("written_here"))
        document.deleted_elsewhere.append({"number": at + 1, "after": before,
                                           "page": copy.deepcopy(page),
                                           "drawing_lost": drawing_lost})
    sheets_kept = _keep_the_sheets_of(gone, pages)
    record["pages"] = pages or record.get("pages", [])
    document.signed_source = (key, data) if signed else None
    warnings = []
    if changed:
        warnings.append(
            "The calculations on page " + ", ".join(str(n) for n in changed)
            + " were changed in another program. CalcForge has rebuilt them from "
            "its own record; the changes made elsewhere are not kept.")
    if gone:
        warnings.append(_what_went(document.deleted_elsewhere, pages, sheets_kept))
    document.open_warnings = warnings


#: What CalcForge itself puts on a page, which Restore Deleted Pages brings
#: back: the equations, calculation blocks and text, tables, spreadsheet
#: cells and charts — not markups, unless asked to (the user, 2026-10-19).
CALCFORGE_ITEMS = frozenset({"calc", "calc_block", "calc_text", "calc_drawing",
                             "table", "sheet_run", "chart"})


def calcforge_items(page: dict) -> list:
    return [p for p in page.get("items", []) if isinstance(p, dict)
            and p.get("type") in CALCFORGE_ITEMS]


def _keep_the_sheets_of(gone: list, pages: list) -> list:
    """A spreadsheet laid out over several pages keeps all its cells when
    some of its pages were deleted elsewhere (the user, 2026-10-19: "keep
    cells but warn"): its cells, kept with its first page, go to the first
    of its pages left. The names of the spreadsheets so kept."""
    kept = []
    for page in gone:
        run = page.get("sheet")
        if not run:
            continue
        left = [other for other in pages if other.get("sheet") == run]
        for payload in list(page.get("items", [])):
            if not (isinstance(payload, dict) and payload.get("type") == "sheet_run"):
                continue
            if left:
                page["items"].remove(payload)
                left[0].setdefault("items", []).insert(0, payload)
        if left:
            name = _sheet_name_of(run, pages, gone)
            if name not in kept:
                kept.append(name)
    return kept


def _sheet_name_of(run: str, *page_lists) -> str:
    for pages in page_lists:
        for page in pages:
            for payload in page.get("items", []):
                if isinstance(payload, dict) and payload.get("type") == "sheet_run" \
                        and payload.get("uid") == run:
                    return (payload.get("table") or {}).get("name") or "the spreadsheet"
    return "the spreadsheet"


def _what_went(deleted: list, pages: list, sheets_kept: list) -> str:
    """The warning for pages deleted elsewhere, page by page: which pages
    (their numbers as saved here, and labels), what was on each, what that
    leaves undefined, and that Restore can bring them back."""
    lines = [f"{len(deleted)} page{'s' if len(deleted) != 1 else ''} saved here "
             f"{'were' if len(deleted) != 1 else 'was'} deleted in another program:"]
    equations = []
    for entry in deleted:
        page = entry["page"]
        label = (page.get("label") or "").strip()
        what = []
        mine = [p for p in page.get("items", []) if isinstance(p, dict)]
        calc = [p for p in mine if p.get("type") == "calc"]
        equations.extend(calc)
        if calc:
            what.append(f"{len(calc)} equation{'s' if len(calc) != 1 else ''}")
        tables = [(p.get("table") or {}).get("name") or "a table"
                  for p in mine if p.get("type") == "table"]
        if tables:
            what.append(("the table " if len(tables) == 1 else "the tables ") + ", ".join(tables))
        if page.get("sheet"):
            what.append(f"a page of the spreadsheet {_sheet_name_of(page['sheet'], pages, [page])}")
        others = [p for p in mine if p.get("type") not in ("calc", "table", "sheet_run")]
        if others:
            what.append(f"{len(others)} markup{'s' if len(others) != 1 else ''}")
        text = f"• page {entry['number']}" + (f" “{label}”" if label else "")
        if what:
            text += " — " + "; ".join(what)
        lines.append(text)
    names = _names_lost(equations, pages)
    if names:
        lines.append(", ".join(names) + (" is" if len(names) == 1 else " are")
                     + " no longer defined.")
    for name in sheets_kept:
        lines.append(f"The spreadsheet {name} keeps all its cells; it is laid out again "
                     f"over its pages that are left.")
    lines.append("Document ▸ Restore Pages…, until the document is saved, "
                 "brings back their equations, tables, spreadsheets and charts on "
                 "pages where they were — not their markups or the page's drawing, "
                 "unless you tick those too (a drawing only where CalcForge still "
                 "holds it: one that was the file's own page went with it).")
    return "\n".join(lines)


def _plain_page(source, index: int) -> dict:
    """A page the record never had — added in another program."""
    from ..core.document import Page, PageSetup

    width, height = engine.page_size(source, index)
    setup = PageSetup.from_name("A4")
    setup.size_name = "Custom"
    setup.orientation = "portrait"
    setup.width_mm = width * 25.4 / 72.0
    setup.height_mm = height * 25.4 / 72.0
    setup.margin_left = setup.margin_top = setup.margin_right = setup.margin_bottom = 0.0
    page = Page(setup)
    page.pdf_page_index = index
    page.grid = False
    page.source_note = f"page {index + 1}, added in another program"
    page.label = page.source_note
    return page.to_dict()


def _sort_the_annotations(source, index: int, page: dict) -> tuple[list, dict]:
    """Leave on the page only its furniture and the annotations that are
    markups as the file now has them; say which are to be read in.

    For markups the file wins (2026-09-30): whatever another program wrote is
    what opens.

    - One of CalcForge's own, unchanged since it was saved: it comes off, and
      the record's markup — which knows more than a PDF can say — is used.
    - One of CalcForge's own, moved or edited elsewhere: it stays, and is
      read in as that program wrote it, keeping the record's identity.
    - One of CalcForge's own that is no longer there: deleted elsewhere, so
      its markup goes too.
    - Somebody else's that a markup still is, unchanged: found again by what
      it is, and the markup pointed at its number in this file.
    - Anything else was added or changed elsewhere, and is read in; a markup
      that was somebody else's annotation and no longer matches goes, because
      its new version is what is read in.

    Returns the annotations to read in, and for each one that replaces a
    markup of the record, that markup's payload.
    """
    from . import calclayer

    items = [payload for payload in page.get("items", []) if isinstance(payload, dict)]
    by_uid = {payload.get("uid"): payload for payload in items if payload.get("uid")}
    wanted: dict = {}
    for payload in items:
        made = payload.get("annotation_print")
        if made:
            wanted.setdefault(made, []).append(payload)
    kept_prints = set(page.get("markup_prints") or ())
    kept, found, new = [], {}, []
    replaced: dict = {}
    seen: set = set()
    for number in engine.annotation_xrefs(source, index):
        kind = source.xref_get_key(number, "Subtype")[1].lstrip("/")
        if kind in engine.NOT_MARKUP:
            kept.append(number)
            continue
        made = calclayer.annotation_print(source, number)
        name = source.xref_get_key(number, "NM")
        name = name[1] if name[0] == "string" else ""
        if made in wanted or made in kept_prints:
            found[made] = number
            kept.append(number)
            seen.add(name)
            continue
        old = by_uid.get(name)
        ours = source.xref_get_key(number, calclayer.KEY)[0] == "name" or \
            (old is not None and not old.get("still_theirs"))
        if ours:
            seen.add(name)
            if old is not None and old.get("written_print") and \
                    old["written_print"] != made:
                kept.append(number)                  # edited elsewhere: as written there
                new.append(number)
                replaced[number] = old
            continue                                 # unchanged: the record's markup
        kept.append(number)
        new.append(number)
    engine.set_page_annotations(source, index, kept)
    gone = {id(old) for old in replaced.values()}
    for payload in items:
        if payload.get("written_print") and payload.get("uid") not in seen:
            gone.add(id(payload))                     # deleted elsewhere
        made = payload.get("annotation_print")
        if made:
            if made in found:
                payload["from_annotation"] = found[made]
            else:
                gone.add(id(payload))                 # changed or deleted elsewhere
        elif payload.get("still_theirs") and payload.get("from_annotation"):
            gone.add(id(payload))                     # not found again at all
        payload.pop("annotation_print", None)
        payload.pop("written_print", None)
    page["items"] = [payload for payload in page.get("items", [])
                     if not isinstance(payload, dict) or id(payload) not in gone]
    page["markup_annotations"] = [found[made] for made in page.pop("markup_prints", [])
                                  if made in found]
    return new, replaced


# What a markup of the record keeps when another program has edited its
# annotation: who it is, and what a PDF has no word for.
_KEPT_THROUGH_AN_EDIT = ("uid", "locked", "group", "group_path", "group_title",
                         "created", "label")


def _read_their_markups(document, cleaned: bytes, index: int, page: dict,
                        numbers, assets: dict, replaced: Optional[dict] = None) -> None:
    """Annotations added or changed in another program, read in as markups
    that are still theirs: drawn by the file, exactly as that program wrote
    them, until changed here."""
    import tempfile

    from . import pdfmarkups, pdfvector

    handle, path = tempfile.mkstemp(suffix=".pdf")
    os.close(handle)
    try:
        with open(path, "wb") as out:
            out.write(cleaned)
        pdf = pdfvector.PdfFile.open(path)
        try:
            import uuid

            def picture_of(png: bytes) -> str:
                if not png:
                    return ""
                name = f"asset_{uuid.uuid4().hex[:12]}.png"
                assets[name] = png
                return name
            made = pdfmarkups.markups_of_page(pdf, index, keep_the_look=True,
                                              picture_of=picture_of)
        finally:
            pdf.close()
    except Exception:                                  # noqa: BLE001
        made = []
    finally:
        _throw_away(path)
    wanted = set(numbers)
    made = [payload for payload in made if payload.get("from_annotation") in wanted]
    if not made:
        return
    replaced = replaced or {}
    done: set = set()
    for payload in made:
        number = payload.get("from_annotation")
        old = replaced.get(number)
        if old is None or number in done:
            continue
        done.add(number)
        for key in _KEPT_THROUGH_AN_EDIT:
            if key in old:
                payload[key] = old[key]
    page["items"] = list(page.get("items", [])) + made
    page["markup_annotations"] = list(dict.fromkeys(list(page.get("markup_annotations", [])) + [
        int(payload.get("from_annotation") or payload.get("split_from_annotation"))
        for payload in made
        if payload.get("from_annotation") or payload.get("split_from_annotation")]))


def _names_lost(equations: list, pages: list) -> list:
    """The variables the *equations* defined that nothing left defines."""
    from ..calc.record import defined_names

    kept = [payload for page in pages for payload in page.get("items", [])
            if isinstance(payload, dict) and payload.get("type") == "calc"]
    return sorted(defined_names(equations) - defined_names(kept))
