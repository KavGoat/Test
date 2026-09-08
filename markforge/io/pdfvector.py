"""Reading a PDF's own line work, rather than a photograph of it.

A drawing that comes in as a picture is a drawing you cannot snap to, cannot
measure honestly and cannot zoom into. The lines are in the file, so they can
be read out and put on the page as real geometry.

MuPDF is what reads them. It runs the page the way a renderer does — every
content stream, every form XObject the page draws, the graphics state stack,
the clipping, the transformations — and hands back the paths that came out of
it with the colour and width each was actually stroked at. That is the whole
point of doing it this way rather than interpreting the content stream here: a
drawing is not a flat list of ``m``/``l``/``c`` operators, it is those
operators run through nested transformations, and a reader that skips the
running gets the lines in the wrong places.

Coordinates come back in **display points** — origin at the top-left corner, y
down, and the page's own ``/Rotate`` applied — which is what the rest of
MarkForge means by a page coordinate. A page that says it is turned ninety
degrees has its line work turned with it, rather than arriving in the shape the
file happens to store it in.

Text is not read. Letters are drawn from an embedded font, and turning those
into geometry is a typesetting job of its own; the page itself is drawn
underneath so the words still show, and the line work sits exactly over it.
"""
from __future__ import annotations

from typing import Any, Optional

import pymupdf

from ..pdf import engine
from ..pdf.engine import PdfError
from ..pdf.objects import Ref

#: Paths with more points than this are a hatch, a shading or a scanned trace
#: rather than something anybody wants to snap to.
MOST_POINTS_IN_A_PATH = 4000


class PdfFile:
    """One PDF, open for its geometry and its annotations.

    A thin thing over a MuPDF document. It exists so the readers above it can
    ask for a page's line work, an annotation's dictionary or an appearance's
    strokes without any of them holding a MuPDF handle or knowing which matrix
    turns what into what.
    """

    def __init__(self, document: "pymupdf.Document", data: bytes = b""):
        self.doc = document
        self._data = data
        self._bare: "Optional[pymupdf.Document]" = None
        self._stripped: set[int] = set()

    @classmethod
    def open(cls, path: str) -> "PdfFile":
        with open(path, "rb") as handle:
            data = handle.read()
        return cls(engine.open_bytes(data), data)

    @classmethod
    def from_bytes(cls, data: bytes) -> "PdfFile":
        return cls(engine.open_bytes(data), data)

    @property
    def page_count(self) -> int:
        return self.doc.page_count

    def page(self, index: int) -> "pymupdf.Page":
        return self.doc[index]

    def page_size(self, index: int) -> tuple[float, float]:
        return engine.page_size(self.doc, index)

    def bare_page(self, index: int) -> "Optional[pymupdf.Page]":
        """The page with nobody's markups on it, for reading its own lines.

        MuPDF runs a page the way a renderer does, and a renderer draws the
        annotations too — so asking a marked-up drawing for its geometry hands
        back somebody's clouds along with the building. They are markups and
        they come across as markups; here they are in the way.

        So the line work is read off a second copy of the file with the
        annotations taken off the page. A copy, rather than the document in
        hand, because that one is still being asked for those same annotations.
        """
        if self._bare is None:
            if not self._data:
                return None
            try:
                self._bare = engine.open_bytes(self._data)
            except PdfError:
                return None
        if not 0 <= index < self._bare.page_count:
            return None
        page = self._bare[index]
        if index not in self._stripped:
            try:
                for annot in list(page.annots()):
                    page.delete_annot(annot)
            except Exception:                          # noqa: BLE001
                engine.drain_messages()
            self._stripped.add(index)
        return page

    def close(self) -> None:
        engine.close(self.doc)
        engine.close(self._bare)
        self.doc = None
        self._bare = None

    def __enter__(self) -> "PdfFile":
        return self

    def __exit__(self, *_unused) -> None:
        self.close()

    # -- objects -----------------------------------------------------------
    def resolve(self, value: Any) -> Any:
        """Follow an indirect reference, however many deep.

        The readers above work in the plain dictionaries a PDF is written in,
        where a value may be the thing or a reference to it. One place follows
        those, so nothing else has to remember to.
        """
        seen = 0
        while isinstance(value, Ref):
            value = engine.object_at(self.doc, value.number)
            seen += 1
            if seen > 32:                              # a file pointing at itself
                return None
        return value

    def object_at(self, number: int) -> Any:
        return engine.object_at(self.doc, number)

    def annotations_of(self, index: int) -> list[dict]:
        """Every annotation on a page, as the dictionary the file holds.

        In the page's own order, which is the order they are drawn in, so a
        markup that was on top comes back on top.
        """
        found: list[dict] = []
        for number in engine.annotation_xrefs(self.doc, index):
            holder = engine.object_at(self.doc, number)
            if isinstance(holder, dict):
                holder = dict(holder)
                holder["__xref__"] = number
                found.append(holder)
        return found


# ---------------------------------------------------------------------------
# line work
# ---------------------------------------------------------------------------

def strokes_of_page(source: PdfFile, index: int) -> list[dict]:
    """The line work on one page, in display points.

    The page's own drawing only. What is in the annotations is somebody's
    markup, and it comes across as markup rather than as line work — a cloud
    read as sixty loose segments is not a cloud.
    """
    page = source.bare_page(index)
    if page is None:
        return []
    try:
        drawings = page.get_drawings()
        rotation = page.rotation_matrix
    except Exception:                                  # noqa: BLE001
        engine.drain_messages()
        return []
    return _strokes_from(drawings, rotation)


def strokes_of_annotation(source: PdfFile, annotation: dict) -> list[dict]:
    """What one annotation draws, where it draws it.

    For the annotations a PDF has no proper shape for — somebody's stamp, a
    tool from a set nobody else has — where the appearance *is* the markup.

    An appearance is a form XObject: a content stream and a box, drawn at
    whatever the annotation's rectangle maps that box onto. MuPDF gets the
    stream out of the file — filters, object streams, encryption and all —
    and :func:`markforge.io.btx.read_content` reads the handful of path
    operators in it, which is the same reader a Bluebeam stamp goes through.
    """
    from .btx import read_content

    form = _appearance_of(source, annotation)
    if form is None:
        return []
    body = engine.stream_of(source.doc, form["__xref__"])
    if not body:
        return []
    placed = _appearance_matrix(source, annotation, form)
    if placed is None:
        return []
    index = _page_index_of(source, annotation)
    if index is None:
        return []
    try:
        page = source.page(index)
        flip = _compose(placed, _flip_of(page))
        return read_content(body, matrix=flip)
    except Exception:                                  # noqa: BLE001
        engine.drain_messages()
        return []


def _flip_of(page: "pymupdf.Page") -> tuple:
    """The file's own space to display points, as a plain PDF matrix.

    The same transform :func:`markforge.pdf.engine.to_display` gives, in the
    six numbers the content reader takes rather than as a MuPDF matrix.
    """
    matrix = engine.to_display(page)
    return (matrix.a, matrix.b, matrix.c, matrix.d, matrix.e, matrix.f)


def _page_index_of(source: PdfFile, annotation: dict) -> Optional[int]:
    """Which page an annotation is on, by the ``/P`` it carries or by looking."""
    parent = annotation.get("P")
    if isinstance(parent, Ref):
        for index in range(source.page_count):
            try:
                if source.doc.page_xref(index) == parent.number:
                    return index
            except Exception:                          # noqa: BLE001
                break
    number = annotation.get("__xref__")
    for index in range(source.page_count):
        if number in engine.annotation_xrefs(source.doc, index):
            return index
    return None


def _appearance_of(source: PdfFile, annotation: dict) -> Optional[dict]:
    """An annotation's normal appearance, whichever state it is kept under."""
    look = source.resolve(annotation.get("AP"))
    if not isinstance(look, dict):
        return None
    found = _stream_dictionary(source, look.get("N"))
    if found is not None:
        return found
    # A form for each state — a tick box, say. The first is as good a guess
    # as any, and better than reading nothing.
    states = source.resolve(look.get("N"))
    if not isinstance(states, dict):
        return None
    for value in states.values():
        found = _stream_dictionary(source, value)
        if found is not None:
            return found
    return None


def _stream_dictionary(source: PdfFile, value) -> Optional[dict]:
    """A referenced object that really is a stream, with its number kept."""
    if not isinstance(value, Ref):
        return None
    holder = source.object_at(value.number)
    if not isinstance(holder, dict) or "Length" not in holder:
        return None
    holder = dict(holder)
    holder["__xref__"] = value.number
    return holder


def _compose(first: tuple, second: tuple) -> tuple:
    """One transform and then the other, as a PDF matrix."""
    a1, b1, c1, d1, e1, f1 = first
    a2, b2, c2, d2, e2, f2 = second
    return (a1 * a2 + b1 * c2, a1 * b2 + b1 * d2,
            c1 * a2 + d1 * c2, c1 * b2 + d1 * d2,
            e1 * a2 + f1 * c2 + e2, e1 * b2 + f1 * d2 + f2)


def _appearance_matrix(source: PdfFile, annotation: dict,
                       form: dict) -> Optional[tuple]:
    """Where the appearance lands: its own box, fitted into the annotation's.

    That is what a PDF reader does with an appearance — transform it by its
    matrix, then map the box that comes out onto the rectangle the annotation
    occupies — and it is why a markup drawn at its own origin ends up in the
    right place on the page.
    """
    rect = _numbers(source, annotation.get("Rect"))
    if len(rect) != 4:
        return None
    left, bottom = min(rect[0], rect[2]), min(rect[1], rect[3])
    across, up = abs(rect[2] - rect[0]), abs(rect[3] - rect[1])
    box = _numbers(source, form.get("BBox"))
    if len(box) != 4:
        return (1.0, 0.0, 0.0, 1.0, left, bottom)
    matrix = _numbers(source, form.get("Matrix"))
    own = tuple(matrix) if len(matrix) == 6 else (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    corners = _transformed_box(box, own)
    wide = max(corners[2] - corners[0], 1e-9)
    high = max(corners[3] - corners[1], 1e-9)
    scale_x = across / wide if across > 0 else 1.0
    scale_y = up / high if up > 0 else 1.0
    fit = (scale_x, 0.0, 0.0, scale_y,
           left - corners[0] * scale_x, bottom - corners[1] * scale_y)
    return _compose(own, fit)


def _transformed_box(box: list, matrix: tuple) -> tuple:
    """The bounding box of a box once the matrix has been applied to it."""
    a, b, c, d, e, f = matrix
    xs, ys = [], []
    for x, y in ((box[0], box[1]), (box[2], box[1]),
                 (box[2], box[3]), (box[0], box[3])):
        xs.append(a * x + c * y + e)
        ys.append(b * x + d * y + f)
    return min(xs), min(ys), max(xs), max(ys)


def _numbers(source: PdfFile, value: Any) -> list[float]:
    values = source.resolve(value)
    if not isinstance(values, (list, tuple)):
        return []
    out = []
    for item in values:
        found = source.resolve(item)
        if isinstance(found, (int, float)) and not isinstance(found, bool):
            out.append(float(found))
    return out


def _strokes_from(drawings: list, rotation: "pymupdf.Matrix") -> list[dict]:
    """MuPDF's paths as MarkForge's strokes, turned into display points.

    MuPDF gives a path already run and already the right way up, but not
    rotated: a page that says it is turned still hands its geometry back in the
    shape the file stores it in. The rotation is applied here, once, so
    everything downstream is in the coordinates that are actually on screen.
    """
    strokes: list[dict] = []
    for entry in drawings:
        path = _path_of(entry, rotation)
        if not path:
            continue
        stroke = _colour_of(entry.get("color"))
        fill = _colour_of(entry.get("fill"))
        if entry.get("type") == "f" and not stroke:
            # A filled shape with no outline: its own edge is what is visible,
            # so that is what the geometry should follow.
            stroke = fill
        strokes.append({
            "path": path,
            "stroke": stroke or "#3d4350",
            "fill": fill if entry.get("type") in ("f", "fs") else "",
            "width": max(float(entry.get("width") or 0.0) or 0.6, 0.1),
        })
    return strokes


def _path_of(entry: dict, rotation: "pymupdf.Matrix") -> list:
    """One MuPDF path as the ``m``/``l``/``c``/``z`` steps everything reads."""
    path: list = []
    points = 0
    for item in entry.get("items") or []:
        kind = item[0]
        if kind == "l":
            path.append(["m", *_at(item[1], rotation)])
            path.append(["l", *_at(item[2], rotation)])
            points += 2
        elif kind == "c":
            path.append(["m", *_at(item[1], rotation)])
            path.append(["c", *_at(item[2], rotation), *_at(item[3], rotation),
                         *_at(item[4], rotation)])
            points += 4
        elif kind == "re":
            box = pymupdf.Rect(item[1]).normalize()
            corners = [(box.x0, box.y0), (box.x1, box.y0),
                       (box.x1, box.y1), (box.x0, box.y1)]
            placed = [_at(pymupdf.Point(*corner), rotation) for corner in corners]
            path.append(["m", *placed[0]])
            path.extend(["l", *corner] for corner in placed[1:])
            path.append(["z"])
            points += 5
        elif kind == "qu":
            quad = item[1]
            placed = [_at(point, rotation) for point in
                      (quad.ul, quad.ur, quad.lr, quad.ll)]
            path.append(["m", *placed[0]])
            path.extend(["l", *corner] for corner in placed[1:])
            path.append(["z"])
            points += 5
        if points > MOST_POINTS_IN_A_PATH:
            break
    if path and entry.get("closePath"):
        path.append(["z"])
    return path


def _at(point, rotation: "pymupdf.Matrix") -> tuple[float, float]:
    placed = pymupdf.Point(point) * rotation
    return float(placed.x), float(placed.y)


def _colour_of(value) -> str:
    """A MuPDF colour as ``#rrggbb``, or empty when there is none."""
    if not value:
        return ""
    try:
        parts = [max(0.0, min(1.0, float(component))) for component in value]
    except (TypeError, ValueError):
        return ""
    if len(parts) == 1:
        parts = parts * 3
    elif len(parts) == 4:
        cyan, magenta, yellow, black = parts
        parts = [(1.0 - cyan) * (1.0 - black), (1.0 - magenta) * (1.0 - black),
                 (1.0 - yellow) * (1.0 - black)]
    if len(parts) != 3:
        return ""
    return "#%02x%02x%02x" % tuple(int(round(part * 255)) for part in parts)


def read(path: str, indices: Optional[list[int]] = None) -> list[list[dict]]:
    """The line work of each page asked for, in order."""
    with PdfFile.open(path) as source:
        wanted = range(source.page_count) if indices is None else indices
        return [strokes_of_page(source, index) for index in wanted
                if 0 <= index < source.page_count]
