"""Bookmarks and links for a finished PDF.

Qt writes the pages but has no way to say "this is the outline" or "this
rectangle is a link", so the two are added afterwards as a PDF incremental
update: the original bytes are left exactly as they were and the new objects,
a new cross-reference section and a new trailer are appended to the end. Every
reader understands that; it is how a PDF is annotated without rewriting it.

Only what Qt actually produces has to be understood here — a PDF 1.4 file with
plain uncompressed objects and a classic cross-reference table — so this is a
small, deliberate reader rather than a general one. Anything it does not
recognise is left alone: the document still opens, without an outline.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

_OBJECT = re.compile(rb"(?:^|[\s>])(\d+)\s+0\s+obj\b")
_STARTXREF = re.compile(rb"startxref\s+(\d+)\s*%%EOF\s*$", re.S)


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


def _escape(text: str) -> bytes:
    """A PDF text string, in UTF-16 so anything can be written in it."""
    body = text.encode("utf-16-be")
    out = bytearray(b"\xfe\xff")
    for byte in body:
        if byte in (0x28, 0x29, 0x5C):        # ( ) \
            out += b"\\"
        out.append(byte)
    return b"(" + bytes(out) + b")"


class _Pdf:
    """Just enough of a PDF to find its pages and add to it."""

    def __init__(self, data: bytes):
        self.data = data
        self.objects: dict[int, tuple[int, bytes]] = {}
        for match in _OBJECT.finditer(data):
            number = int(match.group(1))
            start = match.end()
            end = data.find(b"endobj", start)
            if end < 0:
                continue
            self.objects[number] = (match.start(1), data[start:end])

    def body(self, number: int) -> bytes:
        return self.objects.get(number, (0, b""))[1]

    def trailer(self) -> bytes:
        index = self.data.rfind(b"trailer")
        return self.data[index:] if index >= 0 else b""

    def startxref(self) -> Optional[int]:
        match = _STARTXREF.search(self.data)
        return int(match.group(1)) if match else None

    def size(self) -> int:
        match = re.search(rb"/Size\s+(\d+)", self.trailer())
        return int(match.group(1)) if match else max(self.objects, default=0) + 1

    def root(self) -> Optional[int]:
        match = re.search(rb"/Root\s+(\d+)\s+0\s+R", self.trailer())
        return int(match.group(1)) if match else None

    def page_numbers(self) -> list[int]:
        """The page objects, in the order the document puts them in."""
        root = self.root()
        if root is None:
            return []
        pages = re.search(rb"/Pages\s+(\d+)\s+0\s+R", self.body(root))
        if not pages:
            return []
        kids = re.search(rb"/Kids\s*\[(.*?)\]", self.body(int(pages.group(1))), re.S)
        if not kids:
            return []
        return [int(number) for number in re.findall(rb"(\d+)\s+0\s+R", kids.group(1))]

    def page_height(self, number: int) -> float:
        box = re.search(rb"/MediaBox\s*\[\s*([\d.\-]+)\s+([\d.\-]+)\s+"
                        rb"([\d.\-]+)\s+([\d.\-]+)", self.body(number))
        return float(box.group(4)) - float(box.group(2)) if box else 842.0

    def annots_object(self, number: int) -> Optional[int]:
        """The array object a page keeps its annotations in, if it has one."""
        match = re.search(rb"/Annots\s+(\d+)\s+0\s+R", self.body(number))
        return int(match.group(1)) if match else None


def add_outline_and_links(path: str, outline: list, links: list) -> bool:
    """Append an outline and link annotations to the PDF at *path*.

    Returns False, having changed nothing, when the file is not the shape this
    understands — a document without bookmarks is better than a broken one.
    """
    if not outline and not links:
        return False
    with open(path, "rb") as handle:
        data = handle.read()
    pdf = _Pdf(data)
    pages = pdf.page_numbers()
    root = pdf.root()
    start = pdf.startxref()
    if not pages or root is None or start is None:
        return False

    next_number = max(pdf.size(), max(pdf.objects, default=0) + 1)
    new: dict[int, bytes] = {}          # object number -> body

    def claim() -> int:
        nonlocal next_number
        next_number += 1
        return next_number - 1

    def destination(where) -> bytes:
        index = max(0, min(where.page, len(pages) - 1))
        page_number = pages[index]
        top = pdf.page_height(page_number) - max(where.y, 0.0)
        return b"[ %d 0 R /XYZ null %.2f null ]" % (page_number, top)

    # -- the links, page by page -------------------------------------------
    per_page: dict[int, list[int]] = {}
    for link in links:
        if not (0 <= link.page < len(pages)):
            continue
        number = claim()
        left, bottom, right, top = link.rect
        new[number] = (b"<<\n/Type /Annot\n/Subtype /Link\n"
                       b"/Rect [ %.2f %.2f %.2f %.2f ]\n"
                       b"/Border [ 0 0 0 ]\n/F 4\n/Dest %s\n>>"
                       % (left, bottom, right, top, destination(link.where)))
        per_page.setdefault(link.page, []).append(number)

    for index, numbers in per_page.items():
        page_number = pages[index]
        array = pdf.annots_object(page_number)
        references = b" ".join(b"%d 0 R" % number for number in numbers)
        if array is not None:
            existing = pdf.body(array).strip()
            inner = existing[1:-1] if existing.startswith(b"[") else b""
            new[array] = b"[ " + inner.strip() + b" " + references + b" ]"
        else:
            body = pdf.body(page_number).strip()
            if not body.endswith(b">>"):
                continue
            new[page_number] = (body[:-2] + b"\n/Annots [ " + references + b" ]\n>>")

    # -- the outline -------------------------------------------------------
    if outline:
        outlines_number = claim()
        numbers = [claim() for _ in outline]
        # A flat tree, indented by level: readers show the indentation and
        # nothing depends on the nesting being real.
        for position, (entry, number) in enumerate(zip(outline, numbers)):
            parts = [b"<<", b"/Title " + _escape(entry.title),
                     b"/Parent %d 0 R" % outlines_number,
                     b"/Dest " + destination(entry.where)]
            if position:
                parts.append(b"/Prev %d 0 R" % numbers[position - 1])
            if position + 1 < len(numbers):
                parts.append(b"/Next %d 0 R" % numbers[position + 1])
            parts.append(b">>")
            new[number] = b"\n".join(parts)
        new[outlines_number] = (b"<<\n/Type /Outlines\n/First %d 0 R\n"
                                b"/Last %d 0 R\n/Count %d\n>>"
                                % (numbers[0], numbers[-1], len(numbers)))
        catalog = pdf.body(root).strip()
        if catalog.endswith(b">>"):
            new[root] = (catalog[:-2] + b"\n/Outlines %d 0 R\n/PageMode /UseOutlines\n>>"
                         % outlines_number)

    if not new:
        return False

    # -- append it ---------------------------------------------------------
    out = bytearray(data)
    if not out.endswith(b"\n"):
        out += b"\n"
    offsets: dict[int, int] = {}
    for number in sorted(new):
        offsets[number] = len(out)
        out += b"%d 0 obj\n" % number + new[number] + b"\nendobj\n"

    xref_at = len(out)
    out += b"xref\n"
    for number in sorted(offsets):                # one section per object,
        out += b"%d 1\n" % number                 # since they are not contiguous
        out += b"%010d 00000 n \n" % offsets[number]
    out += (b"trailer\n<<\n/Size %d\n/Root %d 0 R\n/Prev %d\n>>\n"
            b"startxref\n%d\n%%%%EOF\n"
            % (next_number, root, start, xref_at))

    with open(path, "wb") as handle:
        handle.write(bytes(out))
    return True
