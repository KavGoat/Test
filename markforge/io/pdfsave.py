"""Saving a digitally signed PDF by appending to it.

Every save writes a fresh, compact file (decision 4) — except a signed one.
Rewriting a signed file re-compresses its streams and reorders its
dictionaries, and the signature, which covers the old bytes, no longer covers
the new ones. So a signed file gets an **incremental update** instead: every
original byte stays where it was, and appended after them are the markups as
annotations, CalcForge's layers (the old ones taken off the pages, the new
ones put on), the pages that now point at them, and the record. Readers
follow the new cross-reference back through ``/Prev`` to the original, which
is how a PDF has always been added to.

MuPDF does the appending. It also decides when it cannot: a file it had to
repair on the way in has no original bytes left to leave alone, and then this
falls back to writing the file out whole.

That only works while the document is still that file's pages, in its order,
at its sizes: anything else is not an update to that file, and
:mod:`markforge.io.pdfbase` writes it afresh (and says the signature no
longer applies).
"""
from __future__ import annotations

import os
from typing import Optional

from ..pdf import engine
from ..pdf.engine import PdfError


def source_bytes(document) -> Optional[bytes]:
    """The signed file this document is, when it is still that file.

    Every page has to be that file's page, in its order, at its size and its
    full strength. A page moved, resized or dimmed is a page the file no
    longer describes, and then the document is written afresh.
    """
    signed = getattr(document, "signed_source", None)
    if signed is None or not document.pages:
        return None
    key, data = signed
    for index, page in enumerate(document.pages):
        if page.pdf_key != key or page.pdf_page_index != index:
            return None
        if not page.printable or page.background_opacity != 1.0:
            return None
    try:
        source = engine.open_bytes(data)
    except PdfError:
        return None
    try:
        if source.page_count != len(document.pages):
            return None
        if not _sizes_agree(source, document):
            return None
    finally:
        engine.close(source)
    return data


def _sizes_agree(source, document) -> bool:
    """Whether every page is still the size the source page was.

    A page fitted onto other paper is a different page: writing markups onto
    the source at their canvas positions would put them somewhere else. The
    sizes compared are the ones as drawn, rotation included, because that is
    what a page in this document measures.
    """
    for index, page in enumerate(document.pages):
        width, height = engine.page_size(source, index)
        if abs(width - float(page.width_pt)) > 1.0:
            return False
        if abs(height - float(page.height_pt)) > 1.0:
            return False
    return True


# -- saving ------------------------------------------------------------------
def save(document, path: str, original: bytes, appearance: bool = True) -> int:
    """Write *document* to *path* as an update to *original*.

    Atomically, through a temporary beside it: a save interrupted half way
    through must leave the drawing that was there, not half of a new one.

    The original bytes go down first and the update is appended to them, so
    saving over the file it came from and saving somewhere else give the same
    result.
    """
    from . import calclayer, pdfbase

    temporary = path + ".tmp"
    written = 0
    # Scratch files the layers and markups were drawn into, and the files
    # opened on them. They cannot be deleted while the document they were
    # grafted into is open — MuPDF holds them, and Windows will not delete a
    # file anything holds — so they are kept until everything is shut.
    leftovers: list = []
    opened: list = []
    try:
        with open(temporary, "wb") as handle:
            handle.write(original)
        target = engine.open_path(temporary)
        try:
            # CalcForge's own layers from the last save come off; the page's
            # own content is not touched.
            for index in range(target.page_count):
                calclayer.strip(target, index)
                calclayer.mark_page(target, index, document.pages[index].uid)
            layers: dict = {}
            if appearance:
                pdfbase._draw_a_layer(target, document, leftovers, opened,
                                      calclayer.SHEET)
                layers = pdfbase._draw_a_layer(target, document, leftovers, opened,
                                               calclayer.CALC)
                written = _add_the_markups(target, document, leftovers)
                from .export import outline_and_links
                from . import pdflinks
                outline, links = outline_and_links(document, document.pages)
                pdflinks._set_outline(target, outline)
                pdflinks._add_links(target, links)
            key = document.pages[0].pdf_key
            facts = pdfbase._file_facts(document, {key: target},
                                        {page.uid for page in document.pages}, layers)
            engine.embed(target, pdfbase.RECORD_ENTRY,
                         pdfbase.record_bytes(document, facts))
            if not engine.save_incremental(target, temporary):
                # A repaired file has no original bytes worth keeping — there
                # is nothing to append to that a reader would follow — so it
                # is written out whole instead. It goes beside the file rather
                # than over it: the document still has that one open.
                whole = temporary + ".whole"
                target.save(whole)
                engine.close(target)
                os.replace(whole, temporary)
        finally:
            engine.close(target)
            for held in opened:
                engine.close(held)
        os.replace(temporary, path)
    except Exception as exc:                           # noqa: BLE001
        engine.drain_messages()
        _discard(temporary)
        _discard(temporary + ".whole")
        raise PdfError(f"Could not save {path}: {exc}") from exc
    finally:
        for scratch in leftovers:
            _discard(scratch)
    return written


def _discard(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _add_the_markups(target, document, leftovers: list) -> int:
    """Put every markup on the file's pages, as annotations.

    The page's annotation list is replaced rather than added to. What came in
    on the file was read as markups when it was opened, and those markups are
    what is being written back; appending them to the originals would leave
    every cloud in the document twice. The file's own furniture — its links
    and its form fields — is not markup and stays.

    The scratch file the markups were drawn into is handed to *leftovers*
    rather than deleted: *target* has been grafted from it and still holds it
    open, and it is the caller who knows when *target* is shut.
    """
    from . import annotate

    # The file being written is the file the markups came off, so every page
    # already carries its own annotations and the ones nobody has changed
    # stay exactly as they are.
    appearances = annotate.markups_to_place(
        document, document.pages, {page.uid for page in document.pages})
    if not appearances.entries:
        # Still worth saying so on the pages: a document whose last markup was
        # deleted has to lose it from the file too — and one where nothing has
        # been changed has to keep every annotation it came in with.
        return _clear_the_markups(target, document, appearances)
    scratch = None
    try:
        if appearances.draw() is None:
            return 0
        leftovers.append(appearances.path)
        scratch = engine.open_path(appearances.path)
        if scratch.page_count != len(appearances.entries):
            return 0
        return annotate.place_markups(target, scratch, appearances)
    except PdfError:
        return 0
    finally:
        engine.close(scratch)
        appearances.path = None


def _clear_the_markups(target, document, appearances) -> int:
    """Leave each page its own furniture, and the markups nobody has changed.

    Everything else goes: a markup deleted here has to be gone from the file
    too, and a markup taken over is about to be written back as one of ours.
    """
    from . import annotate

    for index in range(min(target.page_count, len(document.pages))):
        already = engine.annotation_xrefs(target, index)
        untouched = set(appearances.theirs.get(index, ()))
        kept = annotate.furniture(target, index)
        kept = kept + [number for number in already
                       if number in untouched and number not in kept]
        if kept != already:
            engine.set_page_annotations(target, index, kept)
    return 0
