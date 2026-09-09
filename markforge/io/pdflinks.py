"""Bookmarks and links for a finished PDF.

Qt writes the pages but has no way to say "this is the outline" or "this
rectangle is a link", so both are added afterwards. MuPDF has a proper name
for each — an outline is a table of contents, a link is a destination on a
page — and writes them itself, so what is left here is only the translation
from what an export knows to what MuPDF is asked for.

A failure costs the bookmarks, never the document: the file is written again
only if everything went in, and the caller carries on either way.
"""
from __future__ import annotations

from dataclasses import dataclass

import pymupdf

from ..pdf import engine
from ..pdf.engine import PdfError


@dataclass
class Destination:
    """Somewhere in the document: a page, and how far down it."""

    page: int
    y: float = 0.0


@dataclass
class Outline:
    """One line of the PDF's bookmark tree."""

    title: str
    where: Destination
    level: int = 0


@dataclass
class Link:
    """A rectangle on a page that goes somewhere when it is clicked.

    *rect* is in PDF user space: points, measured from the bottom-left of the
    page, which is the opposite way up from everything on the drawing side.
    """

    page: int
    rect: tuple[float, float, float, float]
    where: Destination


def add_outline_and_links(path: str, outline: list, links: list) -> bool:
    """Put the bookmarks and the links into the PDF at *path*.

    True when anything was written. The file is only rewritten if there was
    something to write, so an export with neither is left exactly as it was.
    """
    if not outline and not links:
        return False
    try:
        document = engine.open_path(path)
    except PdfError:
        return False
    try:
        wrote = _set_outline(document, outline)
        wrote = _add_links(document, links) or wrote
        if not wrote:
            return False
        engine.save_as(document, path)
    except Exception:                                  # noqa: BLE001
        engine.drain_messages()
        return False
    finally:
        engine.close(document)
    return True


def _set_outline(document, outline: list) -> bool:
    """The bookmark tree, as MuPDF's table of contents.

    A table of contents is a list of levels, and MuPDF insists a level only
    ever steps down by one — a heading three under a heading one is a file it
    refuses rather than repairs — so the levels are pulled back into line on
    the way in. The one that was written too deep still lands under the right
    parent; it simply stops claiming a generation that is not there.
    """
    if not outline:
        return False
    table = []
    previous = 0
    for entry in outline:
        page = max(0, min(int(entry.where.page), document.page_count - 1))
        level = max(1, min(int(entry.level) + 1, previous + 1))
        table.append([level, str(entry.title or ""), page + 1,
                      {"kind": pymupdf.LINK_GOTO,
                       "to": _landing(document, page, entry.where.y)}])
        previous = level
    try:
        document.set_toc(table)
    except Exception:                                  # noqa: BLE001
        engine.drain_messages()
        return False
    return True


def _add_links(document, links: list) -> bool:
    """Each clickable rectangle, on the page it is on.

    The rectangle arrives measured up from the bottom of the page, which is
    how a PDF says it and how the export works it out. MuPDF places a link in
    display points, so it is turned over here.
    """
    written = False
    for link in links:
        if not 0 <= link.page < document.page_count:
            continue
        try:
            page = document[link.page]
            height = page.rect.height
            left, bottom, right, top = link.rect
            box = pymupdf.Rect(left, height - top, right, height - bottom)
            page.insert_link({
                "kind": pymupdf.LINK_GOTO,
                "from": box.normalize(),
                "page": max(0, min(int(link.where.page),
                                   document.page_count - 1)),
                "to": _landing(document, link.where.page, link.where.y),
            })
            written = True
        except Exception:                              # noqa: BLE001
            engine.drain_messages()
            continue
    return written


def _landing(document, page: int, y: float) -> "pymupdf.Point":
    """Where a destination lands, in the space MuPDF is asked for it.

    A ``/XYZ`` destination is written in the file measuring up from the bottom
    of the page, and everything on the drawing side measures down from the top
    — but MuPDF does that turn itself, for both ``set_toc`` and
    ``insert_link``. So the display point goes in as it stands. Turning it over
    first put every bookmark and every link the same distance from the wrong
    end of the sheet, which on a title page is the difference between the top
    of the drawing and the bottom of it.

    Worth knowing that MuPDF is not consistent about this: a destination read
    back out of an outline is in display points, and one read back out of a
    *link* is in the file's own space. Reading is
    :func:`markforge.io.pdfio.outline` and :func:`_add_links` respectively; this
    is only about writing, where both take display points.
    """
    index = max(0, min(int(page), document.page_count - 1))
    height = engine.page_size(document, index)[1]
    return pymupdf.Point(0.0, max(min(float(y), height), 0.0))
