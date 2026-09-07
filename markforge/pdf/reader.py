"""Reading a PDF file into objects.

A PDF is read from the back: the last line says where the cross-reference is,
the cross-reference says where every object is, and the trailer says which
object is the catalogue. Two kinds of cross-reference exist — the old table and
the newer stream — and a file may chain both, so both are understood here.

And when none of that can be believed, every ``N 0 obj`` in the file is found
by scanning it. A damaged drawing that opens is worth more than a correct
refusal, and this is the one place that decides how hard to try.
"""
from __future__ import annotations

import re
from typing import Optional

from .lexer import Lexer
from .objects import Name, Object, Ref, Stream, dictionary_of
from .storage import ObjectStorage

_START_XREF = re.compile(rb"startxref\s+(\d+)", re.S)
_OBJECT = re.compile(rb"(?:^|[\s>])(\d+)\s+(\d+)\s+obj\b")


class ReadError(Exception):
    """The file is not a PDF, or not one this can make anything of."""


def read(data: bytes) -> ObjectStorage:
    """Every object in *data*, however the file has to be taken apart."""
    if not data.lstrip()[:5].startswith(b"%PDF"):
        # Some files carry junk in front of the header; the specification
        # allows it and readers are expected to look past it.
        if b"%PDF" not in data[:1024]:
            raise ReadError("that file does not begin like a PDF")

    storage = ObjectStorage()
    found = _by_cross_reference(data, storage)
    if not found or not storage.trailer.get("Root"):
        # Either there was no usable cross-reference or it did not lead to a
        # catalogue. Scanning finds what is really there.
        _by_scanning(data, storage)
    if not storage.trailer.get("Root"):
        _find_the_catalogue(storage)
    _read_object_streams(storage)
    if not storage.objects:
        raise ReadError("no objects could be read from that file")
    return storage


# -- the tidy way ----------------------------------------------------------
def _by_cross_reference(data: bytes, storage: ObjectStorage) -> bool:
    starts = _START_XREF.findall(data)
    if not starts:
        return False
    seen: set[int] = set()
    at: Optional[int] = int(starts[-1])
    read_any = False
    while at is not None and 0 <= at < len(data) and at not in seen:
        seen.add(at)
        section = _one_section(data, at, storage)
        if section is None:
            return read_any
        read_any = True
        for key, value in section.items():
            storage.trailer.setdefault(key, value)
        following = section.get("Prev")
        # A hybrid file points at a stream holding the rest of the entries.
        extra = section.get("XRefStm")
        if isinstance(extra, int) and extra not in seen:
            _one_section(data, extra, storage)
            seen.add(extra)
        at = int(following) if isinstance(following, int) else None
    return read_any


def _one_section(data: bytes, at: int, storage: ObjectStorage) -> Optional[dict]:
    """One cross-reference and its trailer, whichever kind it is."""
    lexer = Lexer(data, at)
    lexer.skip_space()
    if lexer.take_keyword(b"xref"):
        return _classic_table(data, lexer, storage)
    return _cross_reference_stream(data, at, storage)


def _classic_table(data: bytes, lexer: Lexer, storage: ObjectStorage) -> Optional[dict]:
    """``xref`` … subsections of ``offset generation n`` … ``trailer``."""
    while True:
        lexer.skip_space()
        if lexer.at_keyword(b"trailer"):
            lexer.take_keyword(b"trailer")
            trailer = lexer.read()
            return dictionary_of(trailer)
        first = lexer.read(references=False)
        count = lexer.read(references=False)
        if not isinstance(first, int) or not isinstance(count, int):
            return {}
        for index in range(count):
            lexer.skip_space()
            entry = data[lexer.at:lexer.at + 20]
            match = re.match(rb"(\d{1,10})\s+(\d{1,5})\s+([nf])", entry)
            if not match:
                return {}
            lexer.at += match.end()
            if match.group(3) == b"n":
                number = first + index
                if number not in storage.objects:
                    value = _object_at(data, int(match.group(1)), number)
                    if value is not _MISSING:
                        storage.objects[number] = value


def _cross_reference_stream(data: bytes, at: int, storage: ObjectStorage) -> Optional[dict]:
    """The newer form: the cross-reference is itself a compressed stream."""
    value, _end = _read_indirect(data, at)
    if not isinstance(value, Stream):
        return None
    dictionary = value.dictionary
    if dictionary.get("Type") not in (Name("XRef"), None):
        return None
    from .filters import decode

    body = decode(value, lambda item: item)
    widths = [int(w) for w in (dictionary.get("W") or []) if isinstance(w, int)]
    if len(widths) < 3:
        return None
    size = dictionary.get("Size")
    index = dictionary.get("Index") or [0, size if isinstance(size, int) else 0]
    row = sum(widths)
    if row <= 0:
        return None

    place = 0
    for pair in range(0, len(index) - 1, 2):
        first, count = index[pair], index[pair + 1]
        if not isinstance(first, int) or not isinstance(count, int):
            continue
        for offset in range(count):
            if place + row > len(body):
                break
            fields = []
            for width in widths:
                fields.append(int.from_bytes(body[place:place + width], "big")
                              if width else None)
                place += width
            kind = 1 if fields[0] is None else fields[0]
            number = first + offset
            if kind == 1 and number not in storage.objects:
                found = _object_at(data, fields[1] or 0, number)
                if found is not _MISSING:
                    storage.objects[number] = found
            elif kind == 2 and number not in storage.objects:
                # In an object stream; picked up once those are read.
                storage.objects.setdefault(number, _INSIDE_STREAM)
    return dictionary


_MISSING = object()
#: Marks an object that lives inside an object stream, until it is read out.
_INSIDE_STREAM = object()


def _object_at(data: bytes, offset: int, expected: int):
    """The object at *offset*, if the header there is the one expected."""
    if not 0 <= offset < len(data):
        return _MISSING
    match = re.compile(rb"(\d+)\s+(\d+)\s+obj").match(data, offset)
    if not match:
        # Offsets are often out by a little in files that have been edited.
        window = data[max(offset - 40, 0):offset + 200]
        near = _OBJECT.search(window)
        if not near or int(near.group(1)) != expected:
            return _MISSING
        offset = max(offset - 40, 0) + near.end()
    else:
        if int(match.group(1)) != expected:
            return _MISSING
        offset = match.end()
    lexer = Lexer(data, offset)
    return lexer.read()


def _read_indirect(data: bytes, offset: int):
    """The object whose ``N G obj`` header is at *offset*."""
    match = re.compile(rb"(\d+)\s+(\d+)\s+obj").match(data, offset)
    if not match:
        return None, offset
    lexer = Lexer(data, match.end())
    return lexer.read(), lexer.at


# -- the untidy way --------------------------------------------------------
def _by_scanning(data: bytes, storage: ObjectStorage) -> None:
    """Every ``N G obj`` in the file, later ones winning.

    Which is what a repair does, and it is right: a file that has been edited
    has the same object written more than once, and the last is the live one.
    """
    for match in _OBJECT.finditer(data):
        number = int(match.group(1))
        lexer = Lexer(data, match.end())
        try:
            storage.objects[number] = lexer.read()
        except Exception:                              # noqa: BLE001
            continue
    for at in (m.start() for m in re.finditer(rb"trailer", data)):
        lexer = Lexer(data, at + len(b"trailer"))
        trailer = dictionary_of(lexer.read())
        for key, value in trailer.items():
            storage.trailer.setdefault(key, value)


def _find_the_catalogue(storage: ObjectStorage) -> None:
    """No usable trailer: the catalogue is the object that says it is one."""
    for number in sorted(storage.objects):
        found = storage.objects[number]
        if isinstance(found, dict) and found.get("Type") == Name("Catalog"):
            storage.trailer["Root"] = Ref(number)
            return
    # Still nothing: a file with a page tree and no catalogue is worth opening.
    for number in sorted(storage.objects):
        found = storage.objects[number]
        if isinstance(found, dict) and found.get("Type") == Name("Pages") \
                and "Parent" not in found:
            storage.trailer["Root"] = Ref(storage.add({
                "Type": Name("Catalog"), "Pages": Ref(number)}).number)
            return


def _read_object_streams(storage: ObjectStorage) -> None:
    """Objects packed inside another object, as a modern PDF stores them."""
    from .filters import decode

    for number in list(storage.objects):
        holder = storage.objects.get(number)
        if not isinstance(holder, Stream):
            continue
        if holder.dictionary.get("Type") != Name("ObjStm"):
            continue
        body = decode(holder, storage.resolve)
        if not body:
            continue
        count = int(storage.number(holder, "N", 0))
        first = int(storage.number(holder, "First", 0))
        heading = body[:first].split()
        for index in range(count):
            try:
                inner = int(heading[index * 2])
                offset = int(heading[index * 2 + 1])
            except (IndexError, ValueError):
                break
            existing = storage.objects.get(inner)
            if existing is not None and existing is not _INSIDE_STREAM:
                continue
            lexer = Lexer(body, first + offset)
            try:
                storage.objects[inner] = lexer.read()
            except Exception:                          # noqa: BLE001
                continue
    for number, value in list(storage.objects.items()):
        if value is _INSIDE_STREAM:
            del storage.objects[number]


def read_file(path: str) -> ObjectStorage:
    with open(path, "rb") as handle:
        return read(handle.read())
