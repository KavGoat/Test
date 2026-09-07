"""Just enough of PDF's object syntax to read an annotation out of a file.

A Bluebeam tool set stores each tool as the PDF annotation dictionary it would
write onto a page, and the artwork of a stamp as a PDF form XObject. Both are
written in PDF's own object syntax:

    <</Subtype/Square/Rect[0 0 57 57]/C[1 0 0]/BS<</W 0.5/S/S>>>>

which is a handful of shapes — dictionaries, arrays, names, strings, numbers
and booleans — and nothing else. There is no need for a PDF library to read
that, and a PDF library would be the wrong shape for it anyway: what is being
read is one loose object, not a document with a cross-reference table.

Content streams — the ``m``/``l``/``c``/``re`` path operators that draw a
stamp — are read here too, as a flat list of (operands, operator).
"""
from __future__ import annotations

import re

WHITESPACE = b"\x00\t\n\x0c\r "
DELIMITERS = b"()<>[]{}/%"
NUMBER = re.compile(rb"[+-]?(?:\d+\.?\d*|\.\d+)")


class Ref:
    """An indirect reference: "12 0 R", one object pointing at another.

    An annotation dictionary rarely uses them, so the reader that was written
    for tool sets read the two numbers and the R as three separate tokens and
    nothing minded. Reading a whole PDF does mind: the page's contents, its
    resources and even the length of its own stream are all written this way.
    """

    __slots__ = ("number", "generation")

    def __init__(self, number: int, generation: int = 0):
        self.number = int(number)
        self.generation = int(generation)

    def __repr__(self) -> str:
        return f"{self.number} {self.generation} R"

    def __eq__(self, other) -> bool:
        return (isinstance(other, Ref) and other.number == self.number
                and other.generation == self.generation)

    def __hash__(self) -> int:
        return hash((self.number, self.generation))


# "12 0 R", when what follows a pair of integers is the letter R.
REFERENCE = re.compile(rb"(\d+)\s+(\d+)\s+R(?![A-Za-z0-9])")


class Name(str):
    """A PDF name, ``/Square``. A string that remembers it was a name.

    It matters when a value can be either: ``/S/S`` is the name "S", while
    ``(S)`` would be the text "S", and a border style of one is not the other.
    """

    __slots__ = ()


def _skip(data: bytes, i: int) -> int:
    """Past whitespace and comments, to the next real character."""
    while i < len(data):
        byte = data[i]
        if byte in WHITESPACE:
            i += 1
        elif byte == 0x25:                  # "%", a comment to end of line
            while i < len(data) and data[i] not in (10, 13):
                i += 1
        else:
            return i
    return i


def _read_name(data: bytes, i: int) -> tuple[Name, int]:
    i += 1                                  # the "/"
    start = i
    while i < len(data) and data[i] not in WHITESPACE and data[i] not in DELIMITERS:
        i += 1
    raw = data[start:i].decode("latin-1")
    # #41 is how a "(" gets into a name; rare, but free to support.
    if "#" in raw:
        raw = re.sub(r"#([0-9A-Fa-f]{2})", lambda m: chr(int(m.group(1), 16)), raw)
    return Name(raw), i


def _read_string(data: bytes, i: int) -> tuple[str, int]:
    """A literal string, ``(like this)``, with nesting and escapes."""
    i += 1
    depth = 1
    out = bytearray()
    while i < len(data):
        ch = data[i]
        if ch == 0x5C:                      # backslash
            i += 1
            if i >= len(data):
                break
            nxt = data[i]
            simple = {0x6E: 10, 0x72: 13, 0x74: 9, 0x62: 8, 0x66: 12}
            if nxt in simple:
                out.append(simple[nxt])
            elif 0x30 <= nxt <= 0x37:       # octal, up to three digits
                digits = chr(nxt)
                while len(digits) < 3 and i + 1 < len(data) \
                        and 0x30 <= data[i + 1] <= 0x37:
                    i += 1
                    digits += chr(data[i])
                out.append(int(digits, 8) & 0xFF)
            elif nxt in (10, 13):           # a line continuation
                if nxt == 13 and i + 1 < len(data) and data[i + 1] == 10:
                    i += 1
            else:
                out.append(nxt)
            i += 1
            continue
        if ch == 0x28:
            depth += 1
        elif ch == 0x29:
            depth -= 1
            if depth == 0:
                return out.decode("latin-1"), i + 1
        out.append(ch)
        i += 1
    return out.decode("latin-1"), i


def _read_hex_string(data: bytes, i: int) -> tuple[str, int]:
    end = data.find(b">", i)
    if end < 0:
        return "", len(data)
    digits = re.sub(rb"[^0-9A-Fa-f]", b"", data[i + 1:end]).decode("ascii")
    if len(digits) % 2:
        digits += "0"
    return bytes.fromhex(digits).decode("latin-1"), end + 1


def parse(data: bytes, i: int = 0, references: bool = False):
    """One PDF object out of *data*, starting at *i*. Returns (value, index).

    *references* makes "12 0 R" come back as a :class:`Ref` rather than as
    the number 12 and two loose tokens. Off by default, because a tool set's
    annotations do not use them and reading a bare number is what everything
    already written expects.
    """
    i = _skip(data, i)
    if i >= len(data):
        return None, i
    ch = data[i:i + 1]

    if ch == b"<" and data[i + 1:i + 2] == b"<":
        i += 2
        found: dict = {}
        while True:
            i = _skip(data, i)
            if i >= len(data):
                break
            if data[i:i + 2] == b">>":
                i += 2
                break
            if data[i:i + 1] != b"/":
                # Something that is not a key: step over it rather than spin.
                value, i = parse(data, i, references)
                if value is None and i < len(data):
                    i += 1
                continue
            key, i = _read_name(data, i)
            value, i = parse(data, i, references)
            found[str(key)] = value
        return found, i

    if ch == b"<":
        return _read_hex_string(data, i)

    if ch == b"[":
        i += 1
        items: list = []
        while True:
            i = _skip(data, i)
            if i >= len(data) or data[i:i + 1] == b"]":
                i = min(i + 1, len(data))
                break
            value, after = parse(data, i, references)
            if after == i:                  # no progress; do not spin
                i += 1
                continue
            items.append(value)
            i = after
        return items, i

    if ch == b"/":
        return _read_name(data, i)

    if ch == b"(":
        return _read_string(data, i)

    if data[i:i + 4] == b"true":
        return True, i + 4
    if data[i:i + 5] == b"false":
        return False, i + 5
    if data[i:i + 4] == b"null":
        return None, i + 4

    if references:
        reference = REFERENCE.match(data, i)
        if reference:
            return (Ref(int(reference.group(1)), int(reference.group(2))),
                    reference.end())

    match = NUMBER.match(data, i)
    if match:
        text = match.group(0).decode("ascii")
        value = float(text) if ("." in text) else int(text)
        return value, match.end()

    return None, i


def parse_dict(data: bytes, references: bool = False) -> dict:
    """The first dictionary in *data*, or an empty one."""
    start = data.find(b"<<")
    if start < 0:
        return {}
    value, _ = parse(data, start, references)
    return value if isinstance(value, dict) else {}


# ---------------------------------------------------------------------------
# content streams
# ---------------------------------------------------------------------------

OPERATOR = re.compile(rb"[A-Za-z'\"][A-Za-z0-9*'\"]*")


def operations(stream: bytes) -> list[tuple[list, str]]:
    """A content stream as a list of (operands, operator).

    Inline images (``BI … ID … EI``) are skipped whole: their data is raw
    bytes that would otherwise be read as operators.
    """
    out: list[tuple[list, str]] = []
    operands: list = []
    i = 0
    while i < len(stream):
        i = _skip(stream, i)
        if i >= len(stream):
            break
        ch = stream[i:i + 1]
        if ch in (b"/", b"(", b"[", b"<") or NUMBER.match(stream, i):
            value, after = parse(stream, i)
            if after == i:
                i += 1
                continue
            operands.append(value)
            i = after
            continue
        match = OPERATOR.match(stream, i)
        if not match:
            i += 1
            continue
        word = match.group(0).decode("latin-1")
        i = match.end()
        if word == "BI":
            end = stream.find(b"EI", i)
            i = len(stream) if end < 0 else end + 2
            operands = []
            continue
        if word in ("true", "false", "null"):
            operands.append(word == "true")
            continue
        out.append((operands, word))
        operands = []
    return out
