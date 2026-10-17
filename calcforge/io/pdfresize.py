"""Revu's Page Setup, in the file: pages given new paper with their drawing
scaled, moved and turned onto it (Document ▸ Page Setup…).

The page's own content is not redrawn or resampled. It is wrapped, as it
stands, in one transform (``q a b c d e f cm … Q``), and the page's boxes
become the new paper, its /Rotate folded into the transform — so the saved
file opens in any reader showing the result, every line still a line. The
page's annotations are carried with it: their boxes, points and appearances
go through the same transform. Annotations that CalcForge has read out as
markups are taken off the page, because from here those markups are drawn and
written as CalcForge's own (they are moved with everything else).

No Qt here: this is the file side, called with plain numbers.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

import pymupdf

from ..pdf import engine

#: Keys holding an annotation's geometry as x, y pairs, in the file's space.
_POINT_ARRAYS = ("QuadPoints", "Vertices", "L", "CL")


class Job:
    """One source page to resize: its index, its new size in points, the
    transform from its old displayed page to the new one (display points, y
    down, as ``(a, b, c, d, e, f)`` mapping x, y to a·x + c·y + e,
    b·x + d·y + f), the annotations to take off it (by object number) and
    the part of the old page that showed (display points, x0 y0 x1 y1):
    what lay outside the old page stays out of sight on the new one."""

    __slots__ = ("index", "width", "height", "matrix", "drop", "clip")

    def __init__(self, index: int, width: float, height: float, matrix,
                 drop: Iterable[int] = (), clip: Optional[tuple] = None):
        self.index = int(index)
        self.width = float(width)
        self.height = float(height)
        self.matrix = tuple(float(v) for v in matrix)
        self.drop = set(int(v) for v in drop)
        self.clip = tuple(float(v) for v in clip) if clip else None


def resize(data: bytes, jobs: list) -> bytes:
    """A copy of the PDF *data* with each job's page resized; every other
    page and every object number left as it was."""
    document = engine.open_bytes(data)
    try:
        done_forms: set = set()
        for job in jobs:
            if not 0 <= job.index < document.page_count:
                continue
            _resize_page(document, job, done_forms)
        return document.tobytes(garbage=0, deflate=False)
    except Exception as exc:                           # noqa: BLE001
        engine.drain_messages()
        raise engine.PdfError(f"Could not resize the page: {exc}") from exc
    finally:
        engine.close(document)


def _resize_page(document, job: Job, done_forms: set) -> None:
    page = document[job.index]
    # the file's own space to where it lands on the new paper (its space too)
    shown = engine.to_display(page)
    a, b, c, d, e, f = job.matrix
    onto = pymupdf.Matrix(a, b, c, d, e, f)
    flip = pymupdf.Matrix(1, 0, 0, -1, 0, job.height)
    whole = shown * onto * flip

    _drop_annotations(document, page, job.drop)
    annotations = engine.annotation_xrefs(document, job.index)

    # the content, wrapped as it is in the one transform
    page.wrap_contents()
    contents = list(page.get_contents())
    prefix = "q %s cm\n" % _numbers(whole)
    if job.clip:
        back = ~shown
        corners = [pymupdf.Point(x, y) * back for x, y in
                   ((job.clip[0], job.clip[1]), (job.clip[2], job.clip[3]))]
        left, right = sorted((corners[0].x, corners[1].x))
        bottom, top = sorted((corners[0].y, corners[1].y))
        prefix += (f"{_number(left)} {_number(bottom)} {_number(right - left)} "
                   f"{_number(top - bottom)} re W n\n")
    before = _new_stream(document, prefix.encode("ascii"))
    after = _new_stream(document, b"\nQ\n")
    document.xref_set_key(page.xref, "Contents",
                          "[%s]" % " ".join(f"{x} 0 R" for x in [before] + contents + [after]))

    # the new paper, upright
    box = f"[0 0 {_number(job.width)} {_number(job.height)}]"
    document.xref_set_key(page.xref, "MediaBox", box)
    # the crop box is inherited from the page tree when a page has none, so
    # it is said outright; the others are the page's own
    document.xref_set_key(page.xref, "CropBox", box)
    for key in ("TrimBox", "BleedBox", "ArtBox"):
        document.xref_set_key(page.xref, key, "null")
    document.xref_set_key(page.xref, "Rotate", "0")

    for number in annotations:
        _move_annotation(document, number, whole, done_forms)


def _drop_annotations(document, page, numbers: set) -> None:
    """Take the annotations *numbers* — and their pop-ups — off the page."""
    if not numbers:
        return
    kept = []
    for number in engine.annotation_xrefs(document, page.number):
        if number in numbers:
            continue
        kind, parent = document.xref_get_key(number, "Parent")
        if kind == "xref" and _ref(parent) in numbers:
            continue                          # the pop-up of one taken off
        kept.append(number)
    document.xref_set_key(page.xref, "Annots",
                          "[%s]" % " ".join(f"{x} 0 R" for x in kept))


def _move_annotation(document, number: int, whole, done_forms: set) -> None:
    kind, value = document.xref_get_key(number, "Rect")
    rect = _array(value) if kind == "array" else None
    if rect and len(rect) >= 4:
        corners = [pymupdf.Point(x, y) * whole for x, y in
                   ((rect[0], rect[1]), (rect[2], rect[1]),
                    (rect[2], rect[3]), (rect[0], rect[3]))]
        xs, ys = [p.x for p in corners], [p.y for p in corners]
        document.xref_set_key(number, "Rect",
                              f"[{_number(min(xs))} {_number(min(ys))} "
                              f"{_number(max(xs))} {_number(max(ys))}]")
    for key in _POINT_ARRAYS:
        kind, value = document.xref_get_key(number, key)
        if kind == "array":
            document.xref_set_key(number, key, _moved_points(_array(value), whole))
    kind, value = document.xref_get_key(number, "InkList")
    if kind == "array":
        strokes = re.findall(r"\[([^\[\]]*)\]", value)
        document.xref_set_key(number, "InkList", "[%s]" % " ".join(
            _moved_points(_array(stroke), whole) for stroke in strokes))
    # the appearance: its own matrix turned and scaled the same way (the
    # reader then fits it to the new /Rect, which moves it)
    linear = pymupdf.Matrix(whole.a, whole.b, whole.c, whole.d, 0, 0)
    for state in ("N", "D", "R"):
        kind, value = document.xref_get_key(number, f"AP/{state}")
        forms = []
        if kind == "xref":
            forms = [_ref(value)]
        elif kind == "dict":
            forms = [int(n) for n in re.findall(r"(\d+)\s+0\s+R", value)]
        for form in forms:
            if form in done_forms:
                continue
            done_forms.add(form)
            kind, value = document.xref_get_key(form, "Matrix")
            old = _array(value) if kind == "array" else None
            matrix = pymupdf.Matrix(*old[:6]) if old and len(old) >= 6 else pymupdf.Matrix(1, 1)
            document.xref_set_key(form, "Matrix", "[%s]" % _numbers(matrix * linear))


def _moved_points(values: list, whole) -> str:
    moved = []
    for i in range(0, len(values) - 1, 2):
        point = pymupdf.Point(values[i], values[i + 1]) * whole
        moved += [point.x, point.y]
    return "[%s]" % " ".join(_number(v) for v in moved)


def _new_stream(document, data: bytes) -> int:
    number = document.get_new_xref()
    document.update_object(number, "<<>>")
    document.update_stream(number, data, compress=False)
    return number


def _array(text: str) -> list:
    try:
        return [float(v) for v in str(text).strip().strip("[]").split()]
    except ValueError:
        return []


def _ref(text: str) -> Optional[int]:
    try:
        return int(str(text).split()[0])
    except (ValueError, IndexError):
        return None


def _number(value: float) -> str:
    text = f"{float(value):.5f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


def _numbers(matrix) -> str:
    return " ".join(_number(v) for v in (matrix.a, matrix.b, matrix.c, matrix.d,
                                         matrix.e, matrix.f))
