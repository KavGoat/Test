"""The numbers a viewer redraws a markup from.

An annotation's ``/Rect`` says where it sits, but it is not what it is. A
cloud's shape is its ``/Vertices``, a line's is ``/L``, a highlight's is
``/QuadPoints``, a callout's leader is ``/CL``, a pen stroke's is ``/InkList``.

Move only the ``/Rect`` and this program's own drawing follows, because it
paints the appearance stream and that is mapped onto the ``/Rect`` — but
Bluebeam, Acrobat and anything else that redraws a markup from its geometry
puts it straight back where it was. So every edit here moves the geometry and
the rectangle together, and the file means the same thing everywhere.
"""
from __future__ import annotations

from typing import Optional

import pymupdf

#: Keys holding a flat run of x y pairs.
POINT_KEYS = ("Rect", "CL", "L", "QuadPoints", "Vertices")

#: Keys holding a list of such runs — one per stroke of a pen.
STROKE_KEYS = ("InkList",)

#: Keys holding distances rather than positions: they scale but do not move.
INSET_KEYS = ("RD",)

ALL_KEYS = POINT_KEYS + STROKE_KEYS + INSET_KEYS + ("AP", "IT", "Contents", "IRT", "RT")


def _numbers(raw: str) -> Optional[list[float]]:
    try:
        return [float(value) for value in raw.replace("[", " ").replace("]", " ").split()]
    except ValueError:
        return None                     # an indirect reference, or something odd


def _strokes(raw: str) -> Optional[list[list[float]]]:
    """``[[x y x y] [x y]]`` — one list per stroke."""
    strokes: list[list[float]] = []
    depth = 0
    current: list[str] = []
    for character in raw:
        if character == "[":
            depth += 1
            if depth == 2:
                current = []
            continue
        if character == "]":
            if depth == 2:
                numbers = _numbers("".join(current))
                if numbers is None:
                    return None
                strokes.append(numbers)
            depth -= 1
            continue
        if depth == 2:
            current.append(character)
    return strokes if strokes else None


def _format(numbers: list[float]) -> str:
    return "[%s]" % " ".join("%g" % value for value in numbers)


def _apply(matrix: "pymupdf.Matrix", numbers: list[float]) -> list[float]:
    moved: list[float] = []
    for index in range(0, len(numbers) - 1, 2):
        point = pymupdf.Point(numbers[index], numbers[index + 1]) * matrix
        moved.extend((point.x, point.y))
    return moved


def snapshot(doc: "pymupdf.Document", xref: int) -> dict[str, tuple[str, str]]:
    """Everything about a markup that an edit here can change."""
    kept: dict[str, tuple[str, str]] = {}
    for key in ALL_KEYS:
        try:
            kind, value = doc.xref_get_key(xref, key)
        except Exception:  # noqa: BLE001
            continue
        kept[key] = (kind, value)
    return kept


def restore(doc: "pymupdf.Document", xref: int,
            kept: dict[str, tuple[str, str]]) -> None:
    """Put a markup back exactly as it was."""
    for key, (kind, value) in kept.items():
        try:
            doc.xref_set_key(xref, key, "null" if kind == "null" else value)
        except Exception:  # noqa: BLE001 - a key this document will not take
            continue


def transform(doc: "pymupdf.Document", xref: int, matrix: "pymupdf.Matrix") -> bool:
    """Move a markup's whole geometry, not just the box round it.

    ``matrix`` is in PDF user space. Returns False only if nothing at all could
    be written, which would leave the markup where it was.
    """
    written = False
    for key in POINT_KEYS:
        try:
            kind, raw = doc.xref_get_key(xref, key)
        except Exception:  # noqa: BLE001
            continue
        if kind != "array":
            continue
        numbers = _numbers(raw)
        if numbers is None or len(numbers) < 2:
            continue
        moved = _apply(matrix, numbers)
        if key == "Rect":
            moved = list(pymupdf.Rect(*moved).normalize())
        try:
            doc.xref_set_key(xref, key, _format(moved))
            written = True
        except Exception:  # noqa: BLE001
            continue

    for key in STROKE_KEYS:
        try:
            kind, raw = doc.xref_get_key(xref, key)
        except Exception:  # noqa: BLE001
            continue
        if kind != "array":
            continue
        strokes = _strokes(raw)
        if strokes is None:
            continue
        try:
            doc.xref_set_key(xref, key, "[%s]" % " ".join(
                _format(_apply(matrix, stroke)) for stroke in strokes))
            written = True
        except Exception:  # noqa: BLE001
            continue

    scale_x, scale_y = abs(matrix.a), abs(matrix.d)
    if abs(scale_x - 1.0) > 1e-9 or abs(scale_y - 1.0) > 1e-9:
        for key in INSET_KEYS:
            try:
                kind, raw = doc.xref_get_key(xref, key)
            except Exception:  # noqa: BLE001
                continue
            if kind != "array":
                continue
            numbers = _numbers(raw)
            if numbers is None or len(numbers) != 4:
                continue
            # left, top, right, bottom — widths and heights, so each follows
            # the scale of its own axis.
            try:
                doc.xref_set_key(xref, key, _format(
                    [numbers[0] * scale_x, numbers[1] * scale_y,
                     numbers[2] * scale_x, numbers[3] * scale_y]))
                written = True
            except Exception:  # noqa: BLE001
                continue
    return written


def move_matrix(dx: float, dy: float) -> "pymupdf.Matrix":
    return pymupdf.Matrix(1, 0, 0, 1, dx, dy)


def resize_matrix(old: "pymupdf.Rect", new: "pymupdf.Rect") -> "pymupdf.Matrix":
    """The transform that takes one rectangle onto another."""
    scale_x = new.width / old.width if old.width else 1.0
    scale_y = new.height / old.height if old.height else 1.0
    return pymupdf.Matrix(scale_x, 0, 0, scale_y,
                          new.x0 - scale_x * old.x0, new.y0 - scale_y * old.y0)


def rect_of(doc: "pymupdf.Document", xref: int) -> Optional["pymupdf.Rect"]:
    try:
        kind, raw = doc.xref_get_key(xref, "Rect")
    except Exception:  # noqa: BLE001
        return None
    if kind != "array":
        return None
    numbers = _numbers(raw)
    if numbers is None or len(numbers) != 4:
        return None
    return pymupdf.Rect(*numbers).normalize()
