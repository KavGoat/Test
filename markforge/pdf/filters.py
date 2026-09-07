"""Getting the bytes out of a stream.

A stream says how it was encoded and this undoes it. Flate is nearly all of
what is met in practice; the rest are here because a file that uses one of them
is otherwise unreadable, and being unreadable is not something a drawing should
be for want of forty lines of run-length decoding.
"""
from __future__ import annotations

import zlib
from typing import Any

from .objects import Name, Stream, as_name, dictionary_of


def decode(stream: Stream, resolve=lambda value: value) -> bytes:
    """A stream's real bytes, every filter undone in the order it was applied.

    *resolve* follows indirect references, because a stream's own filter list
    may be one. A filter that is not understood stops the chain and what has
    been undone so far is handed back, which is more use than nothing.
    """
    data = stream.raw
    dictionary = dictionary_of(stream)
    filters = resolve(dictionary.get("Filter"))
    if filters is None:
        return data
    if not isinstance(filters, list):
        filters = [filters]
    settings = resolve(dictionary.get("DecodeParms"))
    if not isinstance(settings, list):
        settings = [settings] * len(filters)
    while len(settings) < len(filters):
        settings.append(None)

    for which, options in zip(filters, settings):
        name = as_name(resolve(which))
        parameters = dictionary_of(resolve(options))
        undo = _FILTERS.get(name)
        if undo is None:
            break
        try:
            data = undo(data, parameters, resolve)
        except Exception:                              # noqa: BLE001
            break
    return data


# -- the filters -----------------------------------------------------------
def _flate(data: bytes, parameters: dict, resolve) -> bytes:
    try:
        out = zlib.decompress(data)
    except zlib.error:
        # Truncated or with a broken tail: take what there is. A drawing that
        # is nearly all there beats an exception.
        machine = zlib.decompressobj()
        try:
            out = machine.decompress(data)
        except zlib.error:
            out = _flate_raw(data)
    return _unpredict(out, parameters, resolve)


def _flate_raw(data: bytes) -> bytes:
    """A stream whose zlib header is missing or wrong."""
    for skip in (0, 1, 2):
        try:
            return zlib.decompressobj(-15).decompress(data[skip:])
        except zlib.error:
            continue
    return b""


def _lzw(data: bytes, parameters: dict, resolve) -> bytes:
    early = int(_number(resolve(parameters.get("EarlyChange")), 1))
    out = bytearray()
    table = [bytes([i]) for i in range(256)] + [b"", b""]
    width = 9
    previous = None
    buffer = 0
    bits = 0
    for byte in data:
        buffer = (buffer << 8) | byte
        bits += 8
        while bits >= width:
            code = (buffer >> (bits - width)) & ((1 << width) - 1)
            bits -= width
            if code == 256:                             # start again
                table = [bytes([i]) for i in range(256)] + [b"", b""]
                width = 9
                previous = None
                continue
            if code == 257:                             # done
                return _unpredict(bytes(out), parameters, resolve)
            if previous is None:
                entry = table[code]
            elif code < len(table):
                entry = table[code]
                table.append(previous + entry[:1])
            else:
                entry = previous + previous[:1]
                table.append(entry)
            out += entry
            previous = entry
            if len(table) + early - 1 >= (1 << width) and width < 12:
                width += 1
    return _unpredict(bytes(out), parameters, resolve)


def _ascii_hex(data: bytes, parameters: dict, resolve) -> bytes:
    digits = bytearray()
    for byte in data:
        if byte == 0x3E:                                # >
            break
        if chr(byte) in "0123456789abcdefABCDEF":
            digits.append(byte)
    if len(digits) % 2:
        digits.append(ord("0"))
    return bytes.fromhex(digits.decode("ascii"))


def _ascii85(data: bytes, parameters: dict, resolve) -> bytes:
    import base64

    body = bytes(byte for byte in data if byte not in b" \t\r\n\x0c\x00")
    if body.startswith(b"<~"):
        body = body[2:]
    end = body.find(b"~>")
    if end >= 0:
        body = body[:end]
    return base64.a85decode(body)


def _run_length(data: bytes, parameters: dict, resolve) -> bytes:
    out = bytearray()
    at = 0
    while at < len(data):
        length = data[at]
        at += 1
        if length == 128:
            break
        if length < 128:
            out += data[at:at + length + 1]
            at += length + 1
        else:
            if at < len(data):
                out += bytes([data[at]]) * (257 - length)
                at += 1
    return bytes(out)


def _identity(data: bytes, parameters: dict, resolve) -> bytes:
    return data


_FILTERS = {
    "FlateDecode": _flate, "Fl": _flate,
    "LZWDecode": _lzw, "LZW": _lzw,
    "ASCIIHexDecode": _ascii_hex, "AHx": _ascii_hex,
    "ASCII85Decode": _ascii85, "A85": _ascii85,
    "RunLengthDecode": _run_length, "RL": _run_length,
    "Crypt": _identity,
}


# -- predictors ------------------------------------------------------------
def _number(value: Any, otherwise: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return otherwise
    return value


def _unpredict(data: bytes, parameters: dict, resolve) -> bytes:
    """Undo the row-by-row prediction a compressor may have applied.

    Cross-reference streams and most images in a modern PDF are written this
    way: each row is stored as its difference from the row above, because that
    compresses far better. Without undoing it the bytes are noise.
    """
    predictor = int(_number(resolve(parameters.get("Predictor")), 1))
    if predictor <= 1:
        return data
    colours = int(_number(resolve(parameters.get("Colors")), 1))
    depth = int(_number(resolve(parameters.get("BitsPerComponent")), 8))
    columns = int(_number(resolve(parameters.get("Columns")), 1))
    step = max(colours * depth // 8, 1)
    width = (columns * colours * depth + 7) // 8

    if predictor == 2:                                  # TIFF
        if depth != 8:
            return data
        out = bytearray(data)
        for row in range(0, len(out) - width + 1, width):
            for index in range(step, width):
                out[row + index] = (out[row + index] + out[row + index - step]) & 0xFF
        return bytes(out)

    # PNG predictors: one tag byte at the front of each row.
    out = bytearray()
    previous = bytearray(width)
    at = 0
    while at + 1 <= len(data) - 1:
        tag = data[at]
        at += 1
        row = bytearray(data[at:at + width])
        if len(row) < width:
            row += bytes(width - len(row))
        at += width
        if tag == 1:                                    # Sub
            for i in range(step, width):
                row[i] = (row[i] + row[i - step]) & 0xFF
        elif tag == 2:                                  # Up
            for i in range(width):
                row[i] = (row[i] + previous[i]) & 0xFF
        elif tag == 3:                                  # Average
            for i in range(width):
                left = row[i - step] if i >= step else 0
                row[i] = (row[i] + ((left + previous[i]) >> 1)) & 0xFF
        elif tag == 4:                                  # Paeth
            for i in range(width):
                left = row[i - step] if i >= step else 0
                up = previous[i]
                corner = previous[i - step] if i >= step else 0
                guess = left + up - corner
                by_left = abs(guess - left)
                by_up = abs(guess - up)
                by_corner = abs(guess - corner)
                if by_left <= by_up and by_left <= by_corner:
                    nearest = left
                elif by_up <= by_corner:
                    nearest = up
                else:
                    nearest = corner
                row[i] = (row[i] + nearest) & 0xFF
        out += row
        previous = row
    return bytes(out)
