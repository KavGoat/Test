"""Reading PDF objects out of bytes.

One function does the work — :func:`read` — and it is written the way PDF4QT's
parser is: a position in a buffer, one object read from it, and the position
after it handed back. Everything else in the engine is built on that, so there
is one place where the syntax of a PDF is understood and one place to fix when
something in the wild turns out to be written slightly differently.
"""
from __future__ import annotations

from typing import Optional

from .objects import Name, Object, Ref, Stream

WHITESPACE = b"\x00\t\n\x0c\r "
DELIMITERS = b"()<>[]{}/%"

_HEX = b"0123456789abcdefABCDEF"

# What a backslash means inside a string.
ESCAPES = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12,
           ord("("): 40, ord(")"): 41, ord("\\"): 92}


class Lexer:
    """A position in a PDF file, and the objects readable from it."""

    def __init__(self, data: bytes, at: int = 0):
        self.data = data
        self.at = at

    # -- the small things --------------------------------------------------
    def skip_space(self) -> None:
        """Past any whitespace and any comment, to the next real character."""
        data, size = self.data, len(self.data)
        while self.at < size:
            byte = data[self.at]
            if byte in WHITESPACE:
                self.at += 1
            elif byte == 0x25:                          # %, to end of line
                while self.at < size and data[self.at] not in b"\r\n":
                    self.at += 1
            else:
                return

    def at_keyword(self, word: bytes) -> bool:
        return self.data.startswith(word, self.at)

    def take_keyword(self, word: bytes) -> bool:
        if self.at_keyword(word):
            self.at += len(word)
            return True
        return False

    # -- one object --------------------------------------------------------
    def read(self, references: bool = True) -> Object:
        """The next object. ``None`` at the end, and for ``null``."""
        self.skip_space()
        if self.at >= len(self.data):
            return None
        byte = self.data[self.at]

        if byte == 0x2F:                                # /Name
            return self._name()
        if byte == 0x28:                                # (string)
            return self._string()
        if byte == 0x5B:                                # [array]
            return self._array(references)
        if byte == 0x3C:                                # <<dict>> or <hex>
            if self.data.startswith(b"<<", self.at):
                return self._dictionary(references)
            return self._hex_string()
        if byte == 0x5D or byte == 0x3E:                # a stray ] or >
            self.at += 1
            return None
        if self.take_keyword(b"true"):
            return True
        if self.take_keyword(b"false"):
            return False
        if self.take_keyword(b"null"):
            return None
        return self._number_or_reference(references)

    # -- each kind ---------------------------------------------------------
    def _name(self) -> Name:
        self.at += 1                                    # the slash
        out = bytearray()
        data, size = self.data, len(self.data)
        while self.at < size:
            byte = data[self.at]
            if byte in WHITESPACE or byte in DELIMITERS:
                break
            if byte == 0x23 and self.at + 2 < size \
                    and data[self.at + 1] in _HEX and data[self.at + 2] in _HEX:
                out.append(int(data[self.at + 1:self.at + 3], 16))
                self.at += 3
                continue
            out.append(byte)
            self.at += 1
        return Name(out.decode("latin-1"))

    def _string(self) -> bytes:
        self.at += 1                                    # the (
        out = bytearray()
        depth = 1
        data, size = self.data, len(self.data)
        while self.at < size:
            byte = data[self.at]
            self.at += 1
            if byte == 0x5C:                            # backslash
                if self.at >= size:
                    break
                following = data[self.at]
                self.at += 1
                if following in ESCAPES:
                    out.append(ESCAPES[following])
                elif 0x30 <= following <= 0x37:         # up to three octal
                    digits = chr(following)
                    while len(digits) < 3 and self.at < size \
                            and 0x30 <= data[self.at] <= 0x37:
                        digits += chr(data[self.at])
                        self.at += 1
                    out.append(int(digits, 8) & 0xFF)
                elif following in b"\r\n":
                    # A line continued: the break is not part of the string.
                    if following == 0x0D and self.at < size and data[self.at] == 0x0A:
                        self.at += 1
                else:
                    out.append(following)
                continue
            if byte == 0x28:
                depth += 1
            elif byte == 0x29:
                depth -= 1
                if depth == 0:
                    break
            out.append(byte)
        return bytes(out)

    def _hex_string(self) -> bytes:
        self.at += 1                                    # the <
        digits = bytearray()
        data, size = self.data, len(self.data)
        while self.at < size and data[self.at] != 0x3E:
            if data[self.at] in _HEX:
                digits.append(data[self.at])
            self.at += 1
        self.at += 1                                    # the >
        if len(digits) % 2:
            digits.append(ord("0"))                     # an odd tail reads as 0
        try:
            return bytes.fromhex(digits.decode("ascii"))
        except ValueError:
            return b""

    def _array(self, references: bool) -> list:
        self.at += 1                                    # the [
        out: list = []
        data, size = self.data, len(self.data)
        while True:
            self.skip_space()
            if self.at >= size:
                break
            if data[self.at] == 0x5D:
                self.at += 1
                break
            before = self.at
            out.append(self.read(references))
            if self.at == before:                       # nothing consumed
                self.at += 1
        return out

    def _dictionary(self, references: bool):
        self.at += 2                                    # the <<
        out: dict = {}
        data, size = self.data, len(self.data)
        while True:
            self.skip_space()
            if self.at >= size:
                break
            if data.startswith(b">>", self.at):
                self.at += 2
                break
            if data[self.at] != 0x2F:                   # not a key: give up
                before = self.at
                self.read(references)
                if self.at == before:
                    self.at += 1
                continue
            key = str(self._name())
            out[key] = self.read(references)
        return self._maybe_stream(out)

    def _maybe_stream(self, dictionary: dict):
        """A dictionary followed by ``stream`` is a stream."""
        mark = self.at
        self.skip_space()
        if not self.take_keyword(b"stream"):
            self.at = mark
            return dictionary
        # Exactly one CRLF or LF after the keyword, and nothing else.
        if self.data.startswith(b"\r\n", self.at):
            self.at += 2
        elif self.at < len(self.data) and self.data[self.at] in b"\n\r":
            self.at += 1
        start = self.at
        length = dictionary.get("Length")
        end = -1
        if isinstance(length, int) and length >= 0 and start + length <= len(self.data):
            end = start + length
            # Trust the length only if what follows really is the end of it.
            tail = self.data[end:end + 20]
            if b"endstream" not in tail:
                end = -1
        if end < 0:
            end = self.data.find(b"endstream", start)
            if end < 0:
                end = len(self.data)
            # The break before "endstream" belongs to the file, not the data.
            while end > start and self.data[end - 1] in b"\r\n":
                end -= 1
        raw = self.data[start:end]
        self.at = self.data.find(b"endstream", end)
        self.at = len(self.data) if self.at < 0 else self.at + len(b"endstream")
        return Stream(dictionary, raw)

    def _number_or_reference(self, references: bool):
        """A number, or ``12 0 R``, which starts out looking like one."""
        start = self.at
        data, size = self.data, len(self.data)
        while self.at < size and data[self.at] not in WHITESPACE \
                and data[self.at] not in DELIMITERS:
            self.at += 1
        word = data[start:self.at]
        if not word:
            self.at += 1
            return None
        number = _as_number(word)
        if number is None:
            # A bare keyword — an operator, or something malformed. Hand it
            # back as a name so a content stream reader can use it and an
            # object reader can ignore it.
            return Name(word.decode("latin-1", "replace"))
        if references and isinstance(number, int) and number >= 0:
            mark = self.at
            following = Lexer(data, self.at)
            following.skip_space()
            second = following.at
            while following.at < size and data[following.at] not in WHITESPACE \
                    and data[following.at] not in DELIMITERS:
                following.at += 1
            generation = _as_number(data[second:following.at])
            if isinstance(generation, int) and generation >= 0:
                following.skip_space()
                if following.take_keyword(b"R") and (
                        following.at >= size
                        or data[following.at] in WHITESPACE
                        or data[following.at] in DELIMITERS):
                    self.at = following.at
                    return Ref(number, generation)
            self.at = mark
        return number


def _as_number(word: bytes):
    """An integer or a real, or ``None`` when it is neither."""
    try:
        return int(word)
    except ValueError:
        pass
    try:
        # PDFs in the wild write ".5", "4.", "--3" and "6.-2"; float copes
        # with the first two and the rest are not worth a parser of their own.
        return float(word)
    except ValueError:
        return None


def read_object(data: bytes, at: int = 0, references: bool = True):
    """One object from *data*, and where reading stopped."""
    lexer = Lexer(data, at)
    value = lexer.read(references)
    return value, lexer.at
