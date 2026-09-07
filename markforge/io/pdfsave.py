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

Anything else — pages from several files, blank pages, pages fitted to
different paper or reordered — is not an update to one file, and
:mod:`markforge.io.pdfbase` assembles it as before.
"""
from __future__ import annotations

import os
from typing import Optional

from ..pdf import reader, writer
from ..pdf.objects import Name, Ref, Stream, dictionary_of
from ..pdf.storage import ObjectStorage


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
        if page.shows_a_grid(settings) or page.shows_a_header(settings) \
                or page.shows_a_footer(settings):
            return None
        if page.frame is not None and any(item.flattened
                                          for item in page.frame.markups()):
            return None
    try:
        storage = reader.read(data)
    except Exception:                                  # noqa: BLE001
        return None
    if len(pages_of(storage)) != len(document.pages):
        return None
    if not _sizes_agree(storage, document):
        return None
    return data


def _sizes_agree(storage: ObjectStorage, document) -> bool:
    """Whether every page is still the size the source page was.

    A page fitted onto other paper is a different page: writing markups onto
    the source at their canvas positions would put them somewhere else.
    """
    for reference, page in zip(pages_of(storage), document.pages):
        box = media_box(storage, reference)
        if box is None:
            return False
        width, height = box[2] - box[0], box[3] - box[1]
        if abs(width - float(page.width_pt)) > 1.0:
            return False
        if abs(height - float(page.height_pt)) > 1.0:
            return False
    return True


def pages_of(storage: ObjectStorage) -> list[Ref]:
    """Every page of the file, in order, as references to its own objects.

    The page tree is a tree, and a reader has to walk it: a file of two hundred
    pages usually keeps them in balanced groups rather than one long list.
    """
    root = storage.resolve(storage.trailer.get("Root"))
    found: list[Ref] = []
    seen: set[int] = set()

    def walk(node) -> None:
        reference = node if isinstance(node, Ref) else None
        if reference is not None:
            if reference.number in seen:
                return                      # a tree that points back at itself
            seen.add(reference.number)
        holder = dictionary_of(storage.resolve(node))
        if not holder:
            return
        if storage.name(holder, "Type") == "Page":
            if reference is not None:
                found.append(reference)
            return
        for child in (storage.get(holder, "Kids") or []):
            walk(child)

    walk(dictionary_of(root).get("Pages"))
    return found


def media_box(storage: ObjectStorage, page) -> Optional[list[float]]:
    """A page's box, taken from the page or inherited from above it."""
    holder = dictionary_of(storage.resolve(page))
    for _ in range(storage.MOST_HOPS):
        if not holder:
            return None
        found = storage.numbers(holder, "MediaBox")
        if len(found) == 4:
            left, bottom = min(found[0], found[2]), min(found[1], found[3])
            right, top = max(found[0], found[2]), max(found[1], found[3])
            return [left, bottom, right, top]
        holder = dictionary_of(storage.get(holder, "Parent"))
    return None


# -- copying one file's objects into another -------------------------------
def copy_into(target: ObjectStorage, source: ObjectStorage, value,
              already: Optional[dict[int, Ref]] = None):
    """*value*, and everything it points at, moved into *target*.

    Object numbers belong to the file they are in, so a graph brought across
    from another file has to be renumbered as it comes. *already* remembers
    what has been brought, which both renumbers consistently and stops a
    dictionary that points back at itself from going round for ever.
    """
    already = {} if already is None else already
    if isinstance(value, Ref):
        if value.number in already:
            return already[value.number]
        reference = target.add(None)
        already[value.number] = reference
        target.put(reference, copy_into(target, source,
                                        source.resolve(value), already))
        return reference
    if isinstance(value, Stream):
        return Stream({key: copy_into(target, source, item, already)
                       for key, item in value.dictionary.items()}, value.raw)
    if isinstance(value, dict):
        return {key: copy_into(target, source, item, already)
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [copy_into(target, source, item, already) for item in value]
    return value


# -- the appearance of one markup ------------------------------------------
def form_for(target: ObjectStorage, drawn: ObjectStorage, page: Ref,
             width: float, height: float) -> Optional[Ref]:
    """One drawn markup, as the form XObject its annotation shows itself with.

    The markups are drawn to a scratch PDF with a page each; this lifts a page
    out of it — its content and the resources that content names — and puts it
    in the file being saved as a form.
    """
    holder = dictionary_of(drawn.resolve(page))
    if not holder:
        return None
    body = _content_of(drawn, holder)
    if not body:
        return None
    dictionary = {
        "Type": Name("XObject"),
        "Subtype": Name("Form"),
        "FormType": 1,
        "BBox": [0.0, 0.0, width, height],
    }
    resources = holder.get("Resources")
    if resources is not None:
        dictionary["Resources"] = copy_into(target, drawn, resources)
    return target.add(writer.compressed(body, dictionary))


def _content_of(storage: ObjectStorage, page: dict) -> bytes:
    """A page's content, however many streams it is written in."""
    found = storage.get(page, "Contents")
    if isinstance(found, list):
        return b"\n".join(storage.data_of(part) for part in found)
    return storage.data_of(page.get("Contents"))


# -- the record that rides along --------------------------------------------
def attach(target: ObjectStorage, name: str, data: bytes) -> None:
    """Put *data* into the file as an embedded file called *name*.

    Beside whatever is already attached, and replacing an earlier copy of the
    same name: saving twice must not leave two records, or reading it back
    would be a coin toss over which one is current.
    """
    stream = writer.compressed(data, {
        "Type": Name("EmbeddedFile"),
        "Subtype": Name("application#2Fzip"),
        "Params": {"Size": len(data)},
    })
    spec = target.add({
        "Type": Name("Filespec"),
        "F": name,
        "UF": name,
        "EF": {"F": target.add(stream)},
    })
    root_reference = target.trailer.get("Root")
    root = dictionary_of(target.resolve(root_reference))
    if not root:
        return
    names = dict(dictionary_of(target.get(root, "Names")) or {})
    files = dict(dictionary_of(target.get(names, "EmbeddedFiles")) or {})
    entries = list(target.get(files, "Names") or [])
    kept: list = []
    for index in range(0, len(entries) - 1, 2):
        if str(target.resolve(entries[index]) or "") != name:
            kept += [entries[index], entries[index + 1]]
    files["Names"] = kept + [name, spec]
    files.pop("Kids", None)
    names["EmbeddedFiles"] = files
    root = dict(root)
    root["Names"] = names
    if isinstance(root_reference, Ref):
        target.put(root_reference, root)
    else:
        target.trailer["Root"] = target.add(root)


# -- saving ------------------------------------------------------------------
def save(document, path: str, original: bytes, appearance: bool = True) -> None:
    """Write *document* to *path* as an update to *original*.

    Atomically, through a temporary beside it: a save interrupted half way
    through must leave the drawing that was there, not half of a new one.
    """
    from . import pdfbase

    storage = reader.read(original)
    before = set(storage.objects)
    references = pages_of(storage)

    written = 0
    if appearance:
        written = _add_the_markups(storage, document, references)
    attach(storage, pdfbase.RECORD_ENTRY, pdfbase.record_bytes(document))

    changed = {number: storage.objects[number] for number in storage.objects
               if number not in before or number in storage.rewritten}
    body = writer.incremental_update(original, changed)
    temporary = path + ".tmp"
    with open(temporary, "wb") as handle:
        handle.write(body)
    os.replace(temporary, path)
    return written


def _add_the_markups(storage: ObjectStorage, document, references) -> int:
    """Put every markup on the file's pages, as annotations.

    The page's annotation list is replaced rather than added to. What came in
    on the file was read as markups when it was opened, and those markups are
    what is being written back; appending them to the originals would leave
    every cloud in the document twice. The file's own furniture — its links
    and its form fields — is not markup and stays.
    """
    from . import annotate
    from ..pdf.annotations import NOT_MARKUP

    drawn, appearances = _drawings_of(document, references)
    if drawn is None:
        return 0
    placed: dict[int, list] = {}
    for (index, item, rect), page in zip(appearances.entries,
                                         pages_of(drawn)):
        height = float(document.pages[index].height_pt)
        form = form_for(storage, drawn, page, rect.width(), rect.height())
        if form is None:
            continue
        annotation = annotate.annotation_for(item, rect, height, form)
        placed.setdefault(index, []).append(storage.add(annotation))

    for index, reference in enumerate(references):
        page = dictionary_of(storage.resolve(reference))
        if not page:
            continue
        keep = [entry for entry in (storage.get(page, "Annots") or [])
                if storage.name(entry, "Subtype") in NOT_MARKUP]
        theirs = placed.get(index, [])
        if not keep and not theirs:
            if "Annots" not in page:
                continue
        page = dict(page)
        page["Annots"] = keep + theirs
        storage.put(reference, page)
        storage.rewritten.add(reference.number)
    return sum(len(entries) for entries in placed.values())


def _drawings_of(document, references):
    """Every markup drawn once, read back as objects to lift forms out of."""
    from . import annotate

    appearances = annotate.Appearances()
    for index, page in enumerate(document.pages):
        frame = page.frame
        if frame is None or index >= len(references):
            continue
        for item in annotate.exportable(frame, page, True):
            rect = item.mapRectToParent(item.boundingRect()).normalized()
            rect = rect.adjusted(-annotate.MARGIN, -annotate.MARGIN,
                                 annotate.MARGIN, annotate.MARGIN)
            if rect.width() <= 0 or rect.height() <= 0:
                continue
            appearances.add(index, item, rect)
    if not appearances.entries:
        appearances.discard()
        return None, appearances
    try:
        if appearances.draw() is None:
            return None, appearances
        with open(appearances.path, "rb") as handle:
            drawn = reader.read(handle.read())
    except Exception:                                  # noqa: BLE001
        return None, appearances
    finally:
        appearances.discard()
    if len(pages_of(drawn)) != len(appearances.entries):
        return None, appearances
    return drawn, appearances
