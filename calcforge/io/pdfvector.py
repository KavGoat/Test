"""Reading a PDF's own line work, rather than a photograph of it.

A drawing that comes in as a picture is a drawing you cannot snap to, cannot
measure honestly and cannot zoom into. The lines are in the file — PDF draws
them with the same operators a Bluebeam stamp uses — so they can be read out
and put on the page as real geometry.

What is read here is the file's structure: its objects, its page tree and the
content stream of each page. Turning that stream into strokes is already done,
by :func:`calcforge.io.btx.read_content`.

Text is not read. Letters in a PDF are drawn from an embedded font, and
rendering those properly is a typesetting job of its own; the raster page is
kept underneath so the words still show, and the line work sits exactly over
it. That is the honest split, and it is the part an engineer needs to be able
to point at.
"""
from __future__ import annotations

import re
import zlib
from typing import Optional

from .pdfobj import Name, Ref, parse

# "12 0 obj" — every object in the file, wherever the cross-reference table
# says they are. Scanning for them directly reads a damaged file too, and
# saves implementing both the old table and the newer stream that replaced it.
_OBJECT = re.compile(rb"(\d+)\s+(\d+)\s+obj\b")


def inflate(data: bytes, entry: dict) -> bytes:
    """A stream's bytes, with the filters this reader knows about undone."""
    filters = entry.get("Filter")
    if isinstance(filters, (Name, str)):
        filters = [filters]
    for name in filters or []:
        if str(name) in ("FlateDecode", "Fl"):
            try:
                data = zlib.decompress(data)
            except zlib.error:
                try:
                    data = zlib.decompressobj().decompress(data)
                except zlib.error:
                    return b""
        else:
            return b""             # a filter this reader does not do
    predictor = (entry.get("DecodeParms") or {})
    if isinstance(predictor, list):
        predictor = predictor[0] if predictor else {}
    if isinstance(predictor, dict) and int(predictor.get("Predictor", 1) or 1) >= 10:
        data = _unpredict(data, predictor)
    return data


def _unpredict(data: bytes, parms: dict) -> bytes:
    """Undo a PNG predictor, which is how a cross-reference stream is packed."""
    columns = int(parms.get("Columns", 1) or 1)
    colours = int(parms.get("Colors", 1) or 1)
    bits = int(parms.get("BitsPerComponent", 8) or 8)
    step = max(colours * bits // 8, 1)
    row_length = columns * colours * bits // 8
    out = bytearray()
    previous = bytearray(row_length)
    at = 0
    while at + 1 + row_length <= len(data):
        tag = data[at]
        row = bytearray(data[at + 1:at + 1 + row_length])
        at += 1 + row_length
        for index in range(row_length):
            left = row[index - step] if index >= step else 0
            up = previous[index]
            upper_left = previous[index - step] if index >= step else 0
            if tag == 1:
                row[index] = (row[index] + left) & 0xFF
            elif tag == 2:
                row[index] = (row[index] + up) & 0xFF
            elif tag == 3:
                row[index] = (row[index] + (left + up) // 2) & 0xFF
            elif tag == 4:
                estimate = left + up - upper_left
                a, b, c = (abs(estimate - left), abs(estimate - up),
                           abs(estimate - upper_left))
                row[index] = (row[index] + (left if a <= b and a <= c
                                            else up if b <= c else upper_left)) & 0xFF
        out += row
        previous = row
    return bytes(out)


class PdfFile:
    """Every object in a PDF, and the pages made out of them."""

    def __init__(self, data: bytes):
        self.data = data
        self.objects: dict[int, object] = {}
        self.streams: dict[int, bytes] = {}
        self._read_objects()
        self._read_object_streams()

    @classmethod
    def open(cls, path: str) -> "PdfFile":
        with open(path, "rb") as handle:
            return cls(handle.read())

    # -- the objects -------------------------------------------------------
    def _read_objects(self) -> None:
        for match in _OBJECT.finditer(self.data):
            number = int(match.group(1))
            body, _end = self._object_at(match.end())
            if body is None:
                continue
            self.objects[number] = body

    def _object_at(self, start: int):
        """One object's value, and its stream if it has one."""
        try:
            value, at = parse(self.data, start, references=True)
        except Exception:                                  # noqa: BLE001
            return None, start
        tail = self.data[at:at + 20]
        if b"stream" in tail and isinstance(value, dict):
            begin = self.data.index(b"stream", at) + len(b"stream")
            if self.data[begin:begin + 2] == b"\r\n":
                begin += 2
            elif self.data[begin:begin + 1] in (b"\n", b"\r"):
                begin += 1
            length = self.resolve_later(value.get("Length"))
            if isinstance(length, (int, float)) and length > 0:
                raw = self.data[begin:begin + int(length)]
            else:
                end = self.data.find(b"endstream", begin)
                raw = self.data[begin:end if end > 0 else begin]
            value["__stream__"] = raw
        return value, at

    def _read_object_streams(self) -> None:
        """Objects packed inside another object, as a modern PDF stores them."""
        for entry in list(self.objects.values()):
            if not isinstance(entry, dict) or str(entry.get("Type")) != "ObjStm":
                continue
            body = inflate(entry.get("__stream__", b""), entry)
            if not body:
                continue
            count = int(entry.get("N", 0) or 0)
            first = int(entry.get("First", 0) or 0)
            heading = body[:first].split()
            for index in range(count):
                try:
                    number = int(heading[index * 2])
                    offset = int(heading[index * 2 + 1])
                except (IndexError, ValueError):
                    break
                try:
                    value, _at = parse(body, first + offset, references=True)
                except Exception:                          # noqa: BLE001
                    continue
                self.objects.setdefault(number, value)

    def resolve(self, value):
        """Follow an indirect reference, however many deep."""
        seen = 0
        while isinstance(value, Ref):
            value = self.objects.get(value.number)
            seen += 1
            if seen > 32:
                return None
        return value

    def resolve_later(self, value):
        """A length that is itself an object, read straight out of the file.

        The objects are not all read yet while the streams are being cut out
        of the file, so this looks the one number up on its own.
        """
        if not isinstance(value, Ref):
            return value
        found = re.search(rb"(?<![0-9])" + str(value.number).encode()
                          + rb"\s+\d+\s+obj\s*(\d+)", self.data)
        return int(found.group(1)) if found else None

    # -- the pages ---------------------------------------------------------
    def pages(self) -> list[dict]:
        """Every page, in the order they are read, with what they inherit."""
        found: list[dict] = []
        root = None
        for entry in self.objects.values():
            if isinstance(entry, dict) and str(entry.get("Type")) == "Pages" \
                    and "Parent" not in entry:
                root = entry
                break
        if root is not None:
            self._walk(root, {}, found, set())
        if not found:
            # No usable tree: take the page objects as they come, which is
            # what a file with a damaged catalogue leaves.
            for number, entry in sorted(self.objects.items()):
                if isinstance(entry, dict) and str(entry.get("Type")) == "Page":
                    found.append(self._inherited(entry, {}))
        return found

    _INHERITS = ("Resources", "MediaBox", "CropBox", "Rotate")

    def _inherited(self, page: dict, handed_down: dict) -> dict:
        merged = dict(page)
        for key in self._INHERITS:
            if key not in merged and key in handed_down:
                merged[key] = handed_down[key]
        return merged

    def _walk(self, node: dict, handed_down: dict, found: list, seen: set) -> None:
        marker = id(node)
        if marker in seen:
            return
        seen.add(marker)
        passed = dict(handed_down)
        for key in self._INHERITS:
            if key in node:
                passed[key] = node[key]
        for child in self.resolve(node.get("Kids")) or []:
            entry = self.resolve(child)
            if not isinstance(entry, dict):
                continue
            if str(entry.get("Type")) == "Pages":
                self._walk(entry, passed, found, seen)
            else:
                found.append(self._inherited(entry, passed))

    def content_of(self, page: dict) -> bytes:
        """One page's whole content stream, decompressed and joined."""
        contents = self.resolve(page.get("Contents"))
        parts = contents if isinstance(contents, list) else [page.get("Contents")]
        body = b""
        for part in parts:
            entry = self.resolve(part)
            if isinstance(entry, dict):
                body += inflate(entry.get("__stream__", b""), entry) + b"\n"
        return body

    def box_of(self, page: dict) -> list:
        """The page's size in points, as [left, bottom, right, top]."""
        box = self.resolve(page.get("CropBox")) or self.resolve(page.get("MediaBox"))
        numbers = [float(self.resolve(v) or 0) for v in box] if box else []
        if len(numbers) != 4:
            return [0.0, 0.0, 595.28, 841.89]              # A4, for want of better
        return numbers


def strokes_of_page(source: PdfFile, page: dict) -> list[dict]:
    """The line work on one page, in page coordinates with y down.

    PDF measures from the bottom-left corner upwards; a page here measures
    from the top-left downwards, so the whole thing is flipped once here
    rather than everywhere it is used.
    """
    from .btx import read_content

    box = source.box_of(page)
    left, bottom, right, top = box
    height = abs(top - bottom)
    # Move the origin to the box's corner, then flip.
    flip = (1.0, 0.0, 0.0, -1.0, -min(left, right), height + min(bottom, top))
    body = source.content_of(page)
    if not body:
        return []
    return read_content(body, matrix=flip)


def read(path: str, indices: Optional[list[int]] = None) -> list[list[dict]]:
    """The line work of each page asked for, in order."""
    source = PdfFile.open(path)
    pages = source.pages()
    wanted = range(len(pages)) if indices is None else indices
    return [strokes_of_page(source, pages[index])
            for index in wanted if 0 <= index < len(pages)]
