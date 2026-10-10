"""What a PDF is made of.

Eight kinds of object and nothing else: null, a boolean, a number, a string, a
name, an array, a dictionary and a stream. Everything in a PDF — a page, an
annotation, a font, the whole catalogue — is some arrangement of those, and a
reference is how one of them points at another.

Modelled on PDF4QT's object layer, where the same eight are one closed set with
a single way of asking what something is. The point of doing it that way is
that nothing downstream has to guess: a dictionary lookup either gives an
object of a known kind or gives null, and there is no third answer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator, Union


class Name(str):
    """A PDF name — ``/Type``, ``/Square``, ``/BE``.

    A subclass of :class:`str` so it compares and formats like the name it is,
    and a distinct type so writing one back out puts the slash on and quotes
    nothing. A string and a name are different things in a PDF and confusing
    them is how ``/Type`` ends up written as ``(Type)``.
    """

    __slots__ = ()

    def __repr__(self) -> str:                          # pragma: no cover
        return f"/{str(self)}"


@dataclass(frozen=True)
class Ref:
    """An indirect reference: object *number*, generation *generation*."""

    number: int
    generation: int = 0

    def __repr__(self) -> str:                          # pragma: no cover
        return f"{self.number} {self.generation} R"


@dataclass
class Stream:
    """A dictionary with bytes attached.

    The bytes as they are in the file, still encoded. Decoding needs the
    filters named in the dictionary and, for one of them, the document's own
    decryption, so it is asked for rather than done on the way in.
    """

    dictionary: dict = field(default_factory=dict)
    raw: bytes = b""

    def get(self, key: str, default=None):
        return self.dictionary.get(key, default)

    def __contains__(self, key: str) -> bool:
        return key in self.dictionary

    def __getitem__(self, key: str):
        return self.dictionary[key]


# What a parsed object can be. Null is Python's None, which is the same thing
# and saves everything downstream a second way of asking.
Object = Union[None, bool, int, float, str, Name, list, dict, Ref, Stream]


def as_text(value: Any) -> str:
    """A text string, decoded however the file wrote it.

    A PDF text string is UTF-16 when it starts with a byte-order mark and
    PDFDocEncoding otherwise, which for everything anybody actually types is
    Latin-1. Bytes that are neither are not worth losing a file over.
    """
    if isinstance(value, str) and not isinstance(value, Name):
        return value
    if isinstance(value, bytes):
        if value[:2] in (b"\xfe\xff", b"\xff\xfe"):
            try:
                return value.decode("utf-16")
            except UnicodeDecodeError:
                return ""
        try:
            return value.decode("latin-1")
        except UnicodeDecodeError:
            return ""
    return ""


def walk(value: Any) -> Iterator[Any]:
    """Every object inside *value*, itself included, depth first."""
    yield value
    if isinstance(value, Stream):
        yield from walk(value.dictionary)
    elif isinstance(value, dict):
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from walk(item)
