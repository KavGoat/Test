"""Saving a marked-up drawing back onto the drawing itself.

The ordinary way to save a PDF is to read every object out of it and write
every object back. It works, and it quietly changes the file: streams are
re-compressed, dictionaries come out in another order, and a signature that
covered the old bytes no longer covers the new ones. For a program whose whole
job is adding to somebody else's drawing, that is the wrong shape of operation.

So when the document *is* one PDF plus what has been drawn on it — which is
what "open a drawing, mark it up, save" means — this writes an **incremental
update** instead. Every original byte stays where it was. Appended after them
are the markups as annotations, the pages that now point at them, and the
record of everything a PDF has no word for. Readers follow the new
cross-reference back through ``/Prev`` to the original, which is how a PDF has
always been added to.

MuPDF does the appending. It also decides when it cannot: a file it had to
repair on the way in has no original bytes left to leave alone, and then this
falls back to writing the file out whole — which is still the same document,
just not the same bytes.

Anything else — pages from several files, blank pages, pages fitted to
different paper or reordered — is not an update to one file, and
:mod:`markforge.io.pdfbase` assembles it as before.
"""
from __future__ import annotations

import os
from typing import Optional

from ..pdf import engine
from ..pdf.engine import PdfError


def source_bytes(document) -> Optional[bytes]:
    """The one PDF this document is, when it is one PDF and its markups.

    Every page has to have come from the same file, in its order, at its size
    and its full strength. A page moved, resized, turned or dimmed is a page
    this file no longer describes, and then the document has to be assembled
    rather than added to.
    """
    if not document.pages:
        return None
    key = document.pages[0].pdf_key
    if not key:
        return None
    data = document.asset(key)
    if not data:
        return None
    settings = document.settings
    for index, page in enumerate(document.pages):
        if page.pdf_key != key or page.pdf_page_index != index:
            return None
        if not page.printable or page.background_opacity != 1.0:
            return None
        # Anything painted onto the sheet — a grid, a running header, a markup
        # somebody flattened into the page — has to be painted, and painting
        # means writing the page again. Then this is not an update to a file;
        # it is a new file, and pdfbase assembles it.
        if page.shows_a_grid(settings) or page.shows_a_header(settings, index) \
                or page.shows_a_footer(settings, index):
            return None
        if page.frame is not None and any(item.flattened
                                          for item in page.frame.markups()):
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
    result. It has to be a file rather than the bytes in hand because an
    incremental update *is* an append: there has to be something on disk to
    append to, and its offsets have to be the ones the new cross-reference
    points back into.
    """
    from . import pdfbase

    temporary = path + ".tmp"
    written = 0
    # The scratch file the markups were drawn into. It cannot be deleted while
    # the document it was grafted into is open — MuPDF holds it, and Windows
    # will not delete a file anything holds — so it is kept until everything
    # is shut, which is after the file has been put in place. Deleting it too
    # early is what made every save fail on Windows with a message naming a
    # file in the temp folder.
    leftovers: list = []
    try:
        with open(temporary, "wb") as handle:
            handle.write(original)
        target = engine.open_path(temporary)
        try:
            if appearance:
                written = _add_the_markups(target, document, leftovers)
            engine.embed(target, pdfbase.RECORD_ENTRY,
                         pdfbase.record_bytes(document))
            if not engine.save_incremental(target, temporary):
                # A repaired file has no original bytes worth keeping — there
                # is nothing to append to that a reader would follow — so it
                # is written out whole instead. Still the same document. It
                # goes beside the file rather than over it: the document still
                # has that one open, and a file that is open is a file that
                # cannot be replaced.
                whole = temporary + ".whole"
                target.save(whole)
                engine.close(target)
                os.replace(whole, temporary)
        finally:
            engine.close(target)
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
