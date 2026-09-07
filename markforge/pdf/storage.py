"""Every object in a file, and how one object reaches another.

PDF4QT calls this the object storage, and the name is the idea: a file is a
numbered bag of objects, and everything else — a page, an annotation, a font —
is a dictionary in that bag pointing at others. One place resolves references,
so nothing above here has to remember that a value might be a reference to a
value that is itself a reference.
"""
from __future__ import annotations

from typing import Any, Iterator, Optional

from .objects import Object, Ref, Stream, dictionary_of


class ObjectStorage:
    """The objects of one file, by number."""

    #: How many references deep to follow before deciding it is a loop.
    MOST_HOPS = 32

    def __init__(self, objects: Optional[dict[int, Object]] = None,
                 trailer: Optional[dict] = None):
        self.objects: dict[int, Object] = dict(objects or {})
        self.trailer: dict = dict(trailer or {})
        #: Numbers whose object has been replaced since it was read. An
        #: incremental update appends only what changed, and an object that
        #: was rewritten in place looks exactly like one that was not unless
        #: somebody says so.
        self.rewritten: set[int] = set()

    # -- reaching things ---------------------------------------------------
    def resolve(self, value: Any) -> Any:
        """*value*, or what it points at. Never a reference."""
        seen = 0
        while isinstance(value, Ref):
            value = self.objects.get(value.number)
            seen += 1
            if seen > self.MOST_HOPS:
                return None
        return value

    def get(self, holder: Any, key: str, otherwise: Any = None) -> Any:
        """One entry of a dictionary or stream, resolved."""
        found = dictionary_of(self.resolve(holder)).get(key)
        return otherwise if found is None else self.resolve(found)

    def numbers(self, holder: Any, key: str) -> list[float]:
        from .objects import as_numbers

        return as_numbers([self.resolve(item)
                           for item in (self.get(holder, key) or [])])

    def name(self, holder: Any, key: str) -> str:
        from .objects import as_name

        return as_name(self.get(holder, key))

    def text(self, holder: Any, key: str) -> str:
        from .objects import as_text

        return as_text(self.get(holder, key))

    def number(self, holder: Any, key: str, otherwise: float = 0.0) -> float:
        from .objects import as_number

        return as_number(self.get(holder, key), otherwise)

    # -- the stream bytes --------------------------------------------------
    def data_of(self, value: Any) -> bytes:
        """A stream's decoded bytes, empty when it is not a stream."""
        from .filters import decode

        found = self.resolve(value)
        if not isinstance(found, Stream):
            return b""
        return decode(found, self.resolve)

    # -- adding to it ------------------------------------------------------
    def next_number(self) -> int:
        """A number nothing is using."""
        return max(self.objects, default=0) + 1

    def add(self, value: Object) -> Ref:
        number = self.next_number()
        self.objects[number] = value
        return Ref(number)

    def put(self, reference: Ref, value: Object) -> None:
        if reference.number in self.objects:
            self.rewritten.add(reference.number)
        self.objects[reference.number] = value

    def merge_into(self, reference: Ref, changes: dict) -> None:
        """Add *changes* to the dictionary *reference* points at."""
        if isinstance(reference, Ref):
            self.rewritten.add(reference.number)
        found = self.resolve(reference)
        if isinstance(found, Stream):
            found.dictionary.update(changes)
        elif isinstance(found, dict):
            found.update(changes)

    def __contains__(self, number: int) -> bool:
        return number in self.objects

    def __iter__(self) -> Iterator[int]:
        return iter(sorted(self.objects))

    def __len__(self) -> int:
        return len(self.objects)
