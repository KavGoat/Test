"""Exporting with the markups still markups.

An exported PDF that has had its markups painted into the page is a picture of
a marked-up drawing. What is wanted is the marked-up drawing: opened in
Bluebeam, every call-out, cloud and dimension is still an annotation — it can
be picked up, moved, given a different colour, replied to and listed in the
markups panel, exactly as it is here.

So the page is painted without them and each markup is written as a real PDF
annotation instead, carrying its own appearance so that it looks the same
wherever it is opened. The one thing that cannot travel is the calculating:
a PDF has no idea what a variable is, so a calculation goes out as an ordinary
movable markup showing the value it held at the moment of export.
"""
from __future__ import annotations

import os
import tempfile
from typing import Optional

# What each kind of markup becomes. A shape that a PDF has a real annotation
# for gets that one, so a reader can edit it natively; everything else goes as
# a stamp, which every reader can select, move and delete.
STAMP = "/Stamp"

# The appearance is drawn at this resolution and scaled back to points, which
# is only about how finely Qt rounds its coordinates.
APPEARANCE_DPI = 300.0

# A hair of room around each markup, so a stroke drawn on the very edge of a
# bounding box is not clipped out of its own appearance.
MARGIN = 1.0


def subtype_for(item) -> str:
    """The PDF annotation this markup is."""
    kind = getattr(item, "kind", "")
    if item.TYPE == "rect":
        if kind == "ellipse":
            return "/Circle"
        if kind in ("rect", "highlight", "redact", "marquee"):
            return "/Square"
        return STAMP                       # a cloud is not a plain rectangle
    if item.TYPE == "poly":
        if kind in ("ink", "highlighter"):
            return "/Ink"
        if kind == "polygon":
            return "/Polygon"
        if kind in ("line", "arrow", "polyline"):
            return "/PolyLine"
        return STAMP                       # clouds and arcs are drawn, not listed
    if item.TYPE == "note":
        return "/Text"
    return STAMP


def exportable(frame, page, preserved: bool) -> list:
    """The markups on a page that should go out as annotations.

    A page kept as its own PDF already holds its line work; that layer came
    out of the file and belongs to it, so it is not written back over the top
    as several thousand annotations. Nor does anything flattened come out as a
    markup: flattening is the decision that it is part of the page now, and it
    is painted into the sheet instead.
    """
    items = []
    for item in frame.ordered_markups():
        if not item.printable or not frame.layer_prints(item):
            continue
        if item.flattened:
            continue
        if preserved and item.layer == "Drawing":
            continue
        items.append(item)
    return items


class Appearances:
    """Every markup drawn once, as one PDF with a page for each of them."""

    def __init__(self):
        self.path: Optional[str] = None
        self.entries: list = []            # (page index, item, rect on the page)

    def add(self, page_index: int, item, rect) -> None:
        self.entries.append((page_index, item, rect))

    def draw(self) -> Optional[str]:
        """Paint them all, into a scratch file, and say where it is."""
        if not self.entries:
            return None
        from PySide6.QtCore import QMarginsF, QRectF, QSizeF
        from PySide6.QtGui import (QPageLayout, QPageSize, QPainter, QPdfWriter)

        handle, path = tempfile.mkstemp(suffix=".pdf")
        os.close(handle)
        writer = QPdfWriter(path)
        writer.setResolution(int(APPEARANCE_DPI))
        writer.setCreator("CalcForge")
        painter = QPainter()
        started = False
        try:
            for _index, item, rect in self.entries:
                layout = QPageLayout()
                layout.setPageSize(QPageSize(QSizeF(rect.width(), rect.height()),
                                             QPageSize.Point, "markup",
                                             QPageSize.ExactMatch))
                layout.setOrientation(QPageLayout.Portrait)
                layout.setMode(QPageLayout.FullPageMode)
                layout.setMargins(QMarginsF(0, 0, 0, 0))
                writer.setPageLayout(layout)
                if not started:
                    if not painter.begin(writer):
                        raise OSError("Could not draw the markups")
                    started = True
                else:
                    writer.newPage()
                painter.setRenderHint(QPainter.Antialiasing, True)
                painter.setRenderHint(QPainter.TextAntialiasing, True)
                painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
                painter.save()
                painter.scale(APPEARANCE_DPI / 72.0, APPEARANCE_DPI / 72.0)
                frame = item.parentItem()
                picture = frame.render_items_picture([item], rect)
                painter.drawPicture(0, 0, picture)
                painter.restore()
        finally:
            if started:
                painter.end()
        del writer
        self.path = path
        return path

    def discard(self) -> None:
        if self.path and os.path.exists(self.path):
            os.remove(self.path)
        self.path = None


def add_markups(path: str, document, printed: list) -> int:
    """Write every markup on *printed* into the PDF at *path* as an annotation.

    Returns how many were written. The file is left exactly as it was if
    anything goes wrong, because an export that lost its markups would be
    worse than one whose markups are not yet live.
    """
    appearances = Appearances()
    for index, page in enumerate(printed):
        frame = page.frame
        if frame is None:
            continue
        preserved = bool(page.pdf_key and page.pdf_page_index is not None
                         and page.background_opacity == 1.0
                         and document.asset(page.pdf_key))
        for item in exportable(frame, page, preserved):
            rect = item.mapRectToParent(item.boundingRect()).normalized()
            rect = rect.adjusted(-MARGIN, -MARGIN, MARGIN, MARGIN)
            if rect.width() <= 0 or rect.height() <= 0:
                continue
            appearances.add(index, item, rect)
    if not appearances.entries:
        return 0
    try:
        drawn = appearances.draw()
        if drawn is None:
            return 0
        return _write_them(path, printed, appearances)
    except Exception:                                  # noqa: BLE001
        return 0
    finally:
        appearances.discard()


def _write_them(path: str, printed: list, appearances: Appearances) -> int:
    from pypdf import PdfReader, PdfWriter

    source = PdfReader(appearances.path, strict=False)
    if len(source.pages) != len(appearances.entries):
        return 0
    writer = PdfWriter(clone_from=path)
    if len(writer.pages) < len(printed):
        return 0
    written = 0
    for (index, item, rect), drawn in zip(appearances.entries, source.pages):
        form = _form_of(drawn, rect)
        if form is None:
            continue
        reference = writer._add_object(form.clone(writer))
        height = float(printed[index].height_pt)
        writer.add_annotation(index, _annotation(item, rect, height, reference))
        written += 1
    if not written:
        return 0
    temporary = path + ".markups.tmp"
    try:
        with open(temporary, "wb") as handle:
            writer.write(handle)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
    return written


def _form_of(drawn, rect):
    """One drawn markup, as the form a PDF annotation shows itself with."""
    from pypdf.generic import (ArrayObject, DecodedStreamObject, FloatObject,
                               NameObject, NumberObject)

    contents = drawn.get_contents()
    if contents is None:
        return None
    form = DecodedStreamObject()
    form.set_data(contents.get_data())
    form[NameObject("/Type")] = NameObject("/XObject")
    form[NameObject("/Subtype")] = NameObject("/Form")
    form[NameObject("/FormType")] = NumberObject(1)
    form[NameObject("/BBox")] = ArrayObject([
        FloatObject(0), FloatObject(0),
        FloatObject(rect.width()), FloatObject(rect.height())])
    if "/Resources" in drawn:
        form[NameObject("/Resources")] = drawn["/Resources"]
    return form


def _annotation(item, rect, page_height: float, appearance):
    """The annotation dictionary for one markup."""
    from pypdf.generic import (ArrayObject, DictionaryObject, FloatObject,
                               NameObject, NumberObject, TextStringObject)

    annotation = DictionaryObject()
    annotation[NameObject("/Type")] = NameObject("/Annot")
    annotation[NameObject("/Subtype")] = NameObject(subtype_for(item))
    annotation[NameObject("/Rect")] = ArrayObject([
        FloatObject(rect.left()), FloatObject(page_height - rect.bottom()),
        FloatObject(rect.right()), FloatObject(page_height - rect.top())])
    annotation[NameObject("/F")] = NumberObject(4)          # printed, not hidden
    annotation[NameObject("/NM")] = TextStringObject(item.uid)
    if item.author:
        annotation[NameObject("/T")] = TextStringObject(item.author)
    said = item.comment or item.summary()
    if said:
        annotation[NameObject("/Contents")] = TextStringObject(said)
    if item.subject:
        annotation[NameObject("/Subj")] = TextStringObject(item.subject)
    colour = _colour(getattr(item.style, "stroke", ""))
    if colour is not None:
        annotation[NameObject("/C")] = colour
    inside = _colour(getattr(item.style, "fill", ""))
    if inside is not None:
        annotation[NameObject("/IC")] = inside
    opacity = float(getattr(item.style, "opacity", 1.0) or 1.0)
    if opacity < 1.0:
        annotation[NameObject("/CA")] = FloatObject(opacity)
    width = float(getattr(item.style, "width", 0.0) or 0.0)
    if width > 0:
        border = DictionaryObject()
        border[NameObject("/W")] = FloatObject(width)
        annotation[NameObject("/BS")] = border
    _add_the_geometry(annotation, item, rect, page_height)
    look = DictionaryObject()
    look[NameObject("/N")] = appearance
    annotation[NameObject("/AP")] = look
    return annotation


def _add_the_geometry(annotation, item, rect, page_height: float) -> None:
    """Say where the shape itself is, not just the box it needs.

    An annotation's rectangle has to hold everything it draws, arrow heads and
    line thickness included, so it is bigger than the shape inside it. A reader
    that lets the shape be edited needs to know the difference, or the first
    drag of a handle moves an edge that was never there.
    """
    from pypdf.generic import ArrayObject, FloatObject, NameObject

    subtype = str(annotation.get("/Subtype"))
    if subtype in ("/Square", "/Circle"):
        try:
            shape = item.mapRectToParent(item.local_rect()).normalized()
        except Exception:                              # noqa: BLE001
            return
        annotation[NameObject("/RD")] = ArrayObject([
            FloatObject(max(shape.left() - rect.left(), 0.0)),
            FloatObject(max(shape.top() - rect.top(), 0.0)),
            FloatObject(max(rect.right() - shape.right(), 0.0)),
            FloatObject(max(rect.bottom() - shape.bottom(), 0.0))])
        return
    points = _points_on_the_page(item, page_height)
    if not points:
        return
    if subtype in ("/Polygon", "/PolyLine"):
        annotation[NameObject("/Vertices")] = ArrayObject(
            [FloatObject(value) for point in points for value in point])
    elif subtype == "/Ink":
        annotation[NameObject("/InkList")] = ArrayObject([ArrayObject(
            [FloatObject(value) for point in points for value in point])])


def _points_on_the_page(item, page_height: float) -> list:
    """A line's corners where the PDF keeps them: up from the bottom."""
    corners = getattr(item, "points", None)
    if not corners:
        return []
    placed = []
    for corner in corners:
        on_page = item.mapToParent(corner)
        placed.append((on_page.x(), page_height - on_page.y()))
    return placed


def _colour(value: str):
    """A ``#rrggbb`` as the three numbers a PDF annotation wants."""
    from pypdf.generic import ArrayObject, FloatObject

    text = (value or "").strip()
    if not text.startswith("#") or len(text) not in (7, 9):
        return None
    try:
        red = int(text[1:3], 16) / 255.0
        green = int(text[3:5], 16) / 255.0
        blue = int(text[5:7], 16) / 255.0
    except ValueError:
        return None
    return ArrayObject([FloatObject(red), FloatObject(green), FloatObject(blue)])
