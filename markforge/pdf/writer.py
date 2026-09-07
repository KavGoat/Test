"""Writing objects back into a PDF.

Two ways, and the choice matters.

An **incremental update** leaves every original byte where it is and appends
the changed objects, a new cross-reference and a new trailer. That is what a
markup editor should do: the drawing that came in is still in the file, exactly
as its author wrote it, and what has been added is added. It is also the only
way to add to a signed document without breaking the signature.

A **full write** puts every object out afresh. Smaller, tidier, and the right
thing when building a document rather than adding to one.
"""
from __future__ import annotations

import re
import zlib
from typing import Iterable, Optional

from .objects import Name, Object, Ref, Stream, dictionary_of
from .storage import ObjectStorage


def serialize(value: Object) -> bytes:
    """One object, as a PDF writes it."""
    if value is None:
        return b"null"
    if value is True:
        return b"true"
    if value is False:
        return b"false"
    if isinstance(value, Ref):
        return f"{value.number} {value.generation} R".encode("ascii")
    if isinstance(value, Name):
        return b"/" + _escaped_name(str(value))
    if isinstance(value, int):
        return str(value).encode("ascii")
    if isinstance(value, float):
        return _real(value)
    if isinstance(value, bytes):
        return _string(value)
    if isinstance(value, str):
        return _string(_encoded_text(value))
    if isinstance(value, (list, tuple)):
        return b"[" + b" ".join(serialize(item) for item in value) + b"]"
    if isinstance(value, Stream):
        return _stream(value)
    if isinstance(value, dict):
        return _dictionary(value)
    return b"null"


def _real(value: float) -> bytes:
    """A number, without an exponent — a PDF has no way to read one."""
    if value != value or value in (float("inf"), float("-inf")):
        return b"0"
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return (text or "0").encode("ascii")


def _escaped_name(text: str) -> bytes:
    out = bytearray()
    for byte in text.encode("utf-8"):
        if byte < 0x21 or byte > 0x7E or bytes([byte]) in b"()<>[]{}/%#":
            out += b"#%02X" % byte
        else:
            out.append(byte)
    return bytes(out)


def _encoded_text(text: str) -> bytes:
    """A text string as a PDF holds one: Latin-1 when it can, UTF-16 when not."""
    try:
        return text.encode("latin-1")
    except UnicodeEncodeError:
        return b"\xfe\xff" + text.encode("utf-16-be")


def _string(raw: bytes) -> bytes:
    out = bytearray(b"(")
    for byte in raw:
        if byte in (0x28, 0x29, 0x5C):                  # ( ) \
            out += b"\\" + bytes([byte])
        elif byte in (0x0A, 0x0D):
            out += b"\\n" if byte == 0x0A else b"\\r"
        else:
            out.append(byte)
    out += b")"
    return bytes(out)


def _dictionary(value: dict) -> bytes:
    out = bytearray(b"<<")
    for key, item in value.items():
        out += b"\n/" + _escaped_name(str(key)) + b" " + serialize(item)
    out += b"\n>>"
    return bytes(out)


def _stream(value: Stream) -> bytes:
    body = value.raw
    dictionary = dict(value.dictionary)
    dictionary["Length"] = len(body)
    return _dictionary(dictionary) + b"\nstream\n" + body + b"\nendstream"


def compressed(data: bytes, extra: Optional[dict] = None) -> Stream:
    """*data* as a Flate stream, which is what everything should be written as."""
    dictionary = dict(extra or {})
    dictionary["Filter"] = Name("FlateDecode")
    return Stream(dictionary, zlib.compress(data, 9))


# -- adding to a file that already exists ----------------------------------
def incremental_update(original: bytes, changed: dict[int, Object],
                       trailer: Optional[dict] = None) -> bytes:
    """*original*, with *changed* appended as an update.

    Nothing already in the file is touched. Readers follow the new
    cross-reference to the new objects and back through ``/Prev`` to
    everything else, which is how a PDF has always been added to.
    """
    if not changed:
        return original

    body = bytearray(original)
    if body and not body.endswith(b"\n"):
        body += b"\n"

    offsets: dict[int, int] = {}
    for number in sorted(changed):
        offsets[number] = len(body)
        body += f"{number} 0 obj\n".encode("ascii")
        body += serialize(changed[number])
        body += b"\nendobj\n"

    start = len(body)
    body += _cross_reference(offsets)
    body += _trailer(original, changed, trailer)
    body += f"startxref\n{start}\n%%EOF\n".encode("ascii")
    return bytes(body)


def _cross_reference(offsets: dict[int, int]) -> bytes:
    """A classic table, in the runs of consecutive numbers it needs."""
    out = bytearray(b"xref\n")
    numbers = sorted(offsets)
    run: list[int] = []
    for number in numbers + [None]:
        if run and (number is None or number != run[-1] + 1):
            out += f"{run[0]} {len(run)}\n".encode("ascii")
            for member in run:
                out += b"%010d 00000 n \n" % offsets[member]
            run = []
        if number is not None:
            run.append(number)
    return bytes(out)


def _trailer(original: bytes, changed: dict, extra: Optional[dict]) -> bytes:
    """The new trailer, pointing back at whatever was there before."""
    previous = _last_startxref(original)
    old = _last_trailer(original)
    entries: dict = {}
    for key in ("Root", "Info", "ID", "Encrypt"):
        if key in old:
            entries[key] = old[key]
    entries.update(extra or {})
    size = max([_size_of(old)] + [number + 1 for number in changed])
    entries["Size"] = size
    if previous is not None:
        entries["Prev"] = previous
    return b"trailer\n" + _dictionary(entries) + b"\n"


def _last_startxref(data: bytes) -> Optional[int]:
    found = re.findall(rb"startxref\s+(\d+)", data)
    return int(found[-1]) if found else None


def _last_trailer(data: bytes) -> dict:
    """The trailer dictionary of the file as it stands, however it is stored."""
    from .lexer import Lexer

    for match in reversed(list(re.finditer(rb"trailer", data))):
        lexer = Lexer(data, match.end())
        found = dictionary_of(lexer.read())
        if found:
            return found
    # A file with only cross-reference streams has no `trailer` keyword; the
    # stream's own dictionary is the trailer.
    at = _last_startxref(data)
    if at is not None and 0 <= at < len(data):
        match = re.compile(rb"(\d+)\s+(\d+)\s+obj").match(data, at)
        if match:
            lexer = Lexer(data, match.end())
            return dictionary_of(lexer.read())
    return {}


def _size_of(trailer: dict) -> int:
    size = trailer.get("Size")
    return size if isinstance(size, int) else 0


# -- writing the whole thing out -------------------------------------------
def write(storage: ObjectStorage) -> bytes:
    """Every object in *storage*, as a complete file."""
    body = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets: dict[int, int] = {}
    for number in sorted(storage.objects):
        value = storage.objects[number]
        if value is None:
            continue
        offsets[number] = len(body)
        body += f"{number} 0 obj\n".encode("ascii")
        body += serialize(value)
        body += b"\nendobj\n"

    start = len(body)
    highest = max(offsets, default=0)
    out = bytearray(b"xref\n0 " + str(highest + 1).encode("ascii") + b"\n")
    out += b"0000000000 65535 f \n"
    for number in range(1, highest + 1):
        if number in offsets:
            out += b"%010d 00000 n \n" % offsets[number]
        else:
            out += b"0000000000 65535 f \n"
    body += out

    entries = {key: value for key, value in storage.trailer.items()
               if key in ("Root", "Info", "ID")}
    entries["Size"] = highest + 1
    body += b"trailer\n" + _dictionary(entries) + b"\n"
    body += f"startxref\n{start}\n%%EOF\n".encode("ascii")
    return bytes(body)
