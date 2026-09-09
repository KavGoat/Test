"""Exporting with the markups still markups.

An exported PDF that has had its markups painted into the page is a picture of
a marked-up drawing. What is wanted is the marked-up drawing: opened in
Bluebeam, every call-out, cloud and dimension is still an annotation — it can
be picked up, moved, given a different colour, replied to and listed in the
markups panel, exactly as it is here.

So the page is painted without them and each markup is written as a real PDF
annotation instead, carrying its own appearance so that it looks the same
wherever it is opened.
"""
from __future__ import annotations

import atexit
import os
import tempfile
from typing import Optional

from ..pdf import engine
from ..pdf.objects import Name, Ref

# What each kind of markup becomes. A shape that a PDF has a real annotation
# for gets that one, so a reader can edit it natively; everything else goes as
# a stamp, which every reader can select, move and delete.
#
# Everything here is built as the plain dictionaries and names of
# :mod:`markforge.pdf.objects`, and :func:`markforge.pdf.engine.serialize`
# writes them. One description of what a markup is, written once, whether the
# file is being added to in place or assembled from several sources.
STAMP = "Stamp"

# The appearance is drawn at this resolution and scaled back to points, which
# is only about how finely Qt rounds its coordinates.
APPEARANCE_DPI = 300.0

# A hair of room around each markup, so a stroke drawn on the very edge of a
# bounding box is not clipped out of its own appearance.
MARGIN = 1.0


# How a cloud's scallops are described: a border effect of style /C, and how
# pronounced it is. A PDF says a cloud this way rather than by drawing one, so
# a cloud written like this stays a cloud in the editor it is opened in.
CLOUD_INTENSITY = 2.0

# What each of our arrow heads is called in a PDF. Ten endings are defined and
# a markup that came in wearing one should go back out wearing the same one.
LINE_ENDINGS = {
    "none": "None",
    "arrow": "ClosedArrow",
    "open": "OpenArrow",
    "dot": "Circle",
    "square": "Square",
    "diamond": "Diamond",
    "slash": "Slash",
    "half": "OpenArrow",
}


def subtype_for(item) -> str:
    """The PDF annotation this markup is.

    A markup written as its own kind of annotation can be edited as that kind
    wherever it is opened; written as a stamp it can only be moved. So this
    reaches for the real thing wherever the specification has one — which,
    once the border effects and intents are used, is nearly everywhere.
    """
    kind = getattr(item, "kind", "")
    if item.TYPE == "rect":
        if kind == "ellipse":
            return "Circle"
        # A cloud is a square with a cloudy border, not a different shape.
        return "Square"
    if item.TYPE == "poly":
        if kind in ("ink", "highlighter"):
            return "Ink"
        if kind in ("polygon", "cloud"):
            return "Polygon"
        if kind in ("line", "arrow"):
            return "Line"
        if kind in ("polyline", "arc"):
            return "PolyLine"
        return STAMP
    if item.TYPE == "measure":
        from ..items import measure as measure_module

        if kind in (measure_module.AREA, measure_module.PERIMETER,
                    measure_module.VOLUME):
            return "Polygon"
        if kind in measure_module.DIMENSIONED:
            return "Line"
        if kind in (measure_module.POLYLENGTH, measure_module.ANGLE):
            return "PolyLine"
        return STAMP                       # radius and diameter draw a circle
    if item.TYPE == "note":
        return "Text"
    if item.TYPE in ("callout", "typewriter", "text"):
        return "FreeText"
    return STAMP


def exportable(frame, page, preserved: bool) -> list:
    """The markups on a page that should go out as annotations.

    The page's own line work is not markup: it is read out of the PDF the page
    came from so that things can snap to it. It belongs to the page and is
    written as part of it — as the original page where that has been kept, and
    painted into the sheet where it has not. Turning several thousand pieces of
    somebody else's drawing into several thousand annotations would be wrong as
    well as slow.

    Nor does anything flattened come out as a markup: flattening is the
    decision that it is part of the page now, and it is painted in.
    """
    items = []
    for item in frame.ordered_markups():
        if not item.printable:
            continue
        if item.flattened or item.from_drawing:
            continue
        items.append(item)
    return items


class Appearances:
    """Every markup drawn once, as one PDF with a page for each of them."""

    def __init__(self):
        self.path: Optional[str] = None
        self.entries: list = []            # (page index, item, rect on the page)
        # Per page, the annotations of the file being written that a markup is
        # still exactly — the ones to leave where they are rather than redraw.
        self.theirs: dict = {}

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
        writer.setCreator("MarkForge")
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
                # How many device units the writer gives to a point, asked of
                # the device rather than assumed from the resolution that was
                # requested: Qt does not always give back the resolution it was
                # asked for, and a markup drawn to the wrong scale lands in the
                # wrong place and the wrong size for everything that reads it.
                across = max(painter.device().width(), 1) / max(rect.width(), 1e-6)
                down = max(painter.device().height(), 1) / max(rect.height(), 1e-6)
                painter.scale(across, down)
                frame = item.parentItem()
                frame.paint_items(painter, [item], rect)
                painter.restore()
        finally:
            if started:
                painter.end()
        del writer
        self.path = path
        return path

    def discard(self) -> None:
        """Get rid of the scratch file — and never mind if it will not go.

        Windows will not delete a file anything still has open, and MuPDF
        holds a document open for as long as whatever it was grafted into is
        open. So the scratch file can outlive the moment somebody wants rid of
        it, and it must not be allowed to cost a save: a leftover file in the
        temp folder is a nuisance, a drawing that would not save is a day's
        work. Nothing here raises. What could not go now is tried again on the
        way out of the program.
        """
        path, self.path = self.path, None
        if not path:
            return
        try:
            os.remove(path)
        except OSError:
            _sweep_up_later(path)


_LEFTOVERS: list = []


def _sweep_up_later(path: str) -> None:
    """A scratch file that would not delete now, to try again on the way out."""
    if path in _LEFTOVERS:
        return
    if not _LEFTOVERS:
        atexit.register(_sweep_up)
    _LEFTOVERS.append(path)


def _sweep_up() -> None:
    while _LEFTOVERS:
        try:
            os.remove(_LEFTOVERS.pop())
        except OSError:
            pass


def markups_to_place(document, printed: list, carried=None) -> Appearances:
    """Every markup that should go out as an annotation, ready to be drawn.

    *carried* names the pages — by uid — whose own annotations are already in
    the file being written, because the page was kept rather than redrawn. On
    those, the markups nobody has changed are left out: the annotation that a
    markup still *is* is already there, exactly as its author wrote it, and
    putting a redrawing of it over the top is how a drawing that went round a
    loop stopped looking like itself. Which ones those are is in
    :attr:`Appearances.theirs`.
    """
    appearances = Appearances()
    kept = set() if carried is None else set(carried)
    for index, page in enumerate(printed):
        frame = page.frame
        if frame is None:
            continue
        preserved = bool(page.pdf_key and page.pdf_page_index is not None
                         and page.background_opacity == 1.0
                         and document.asset(page.pdf_key))
        for item in exportable(frame, page, preserved):
            if page.uid in kept and getattr(item, "still_theirs", False) \
                    and getattr(item, "from_annotation", 0):
                appearances.theirs.setdefault(index, []).append(
                    int(item.from_annotation))
                continue
            rect = item.mapRectToParent(item.boundingRect()).normalized()
            rect = rect.adjusted(-MARGIN, -MARGIN, MARGIN, MARGIN)
            if rect.width() <= 0 or rect.height() <= 0:
                continue
            appearances.add(index, item, rect)
    return appearances


def add_markups(path: str, document, printed: list, carried=None) -> bool:
    """Write every markup on *printed* into the PDF at *path* as an annotation.

    Says whether the file now holds what it should. The file is left exactly
    as it was if anything goes wrong, because an export that lost its markups
    would be worse than one whose markups are not yet live — and the caller
    falls back to painting them on. *carried* is as in
    :func:`markups_to_place`: the pages already carrying their own
    annotations, whose unchanged markups are already there and are not
    written again.

    Nothing to write is success, not failure. On a drawing opened and exported
    without a single markup being touched there is nothing to write — every
    one of them is still its own file's annotation and came across with the
    page — and reading that as a failure is what had the whole export painted
    again from the screen, losing those annotations altogether.
    """
    appearances = markups_to_place(document, printed, carried)
    if not appearances.entries:
        return True
    try:
        if appearances.draw() is None:
            return False
        return bool(_write_them(path, appearances))
    except Exception:                                  # noqa: BLE001
        return False
    finally:
        appearances.discard()


def _write_them(path: str, appearances: Appearances) -> int:
    """Put the drawn appearances into the file at *path* as annotations.

    The target is closed before the scratch file, and both before the caller
    gets rid of it: the target has been grafted from the scratch and holds it
    open until it is shut itself, and a file anything holds open is a file
    Windows will not delete.
    """
    target = scratch = None
    try:
        target = engine.open_path(path)
        scratch = engine.open_path(appearances.path)
        if scratch.page_count != len(appearances.entries):
            return 0
        written = place_markups(target, scratch, appearances,
                                keep_existing=True)
        if not written:
            return 0
        # Closes the target and the scratch: the target is open on the very
        # file being written, and the scratch is what it was grafted from.
        engine.save_as(target, path, also=(scratch,))
        target = scratch = None
        return written
    finally:
        engine.close(target)
        engine.close(scratch)


def place_markups(target, scratch, appearances: Appearances,
                  keep_existing: bool = False) -> int:
    """Put each drawn markup into *target* as an annotation with an appearance.

    *scratch* holds one page per markup — what Qt painted. Each becomes a form
    XObject in *target*, and each annotation points at its own.

    With *keep_existing* the page's annotations are added to, which is what an
    export wants: the page was painted without its markups and carries only
    its own links. Without it they are replaced, which is what saving over a
    drawing wants: what came in on the file was read as markups when it was
    opened, and those markups are what is being written back, so appending
    would leave every cloud in the document twice. Either way the file's own
    furniture — its links and its form fields — stays.
    """
    placed: dict[int, list[int]] = {}
    for order, (index, item, rect) in enumerate(appearances.entries):
        if not 0 <= index < target.page_count:
            continue
        form = engine.form_from_page(target, scratch, order,
                                     rect.width(), rect.height())
        if form is None:
            continue
        place = Placement.of_page(target[index])
        annotation = annotation_for(item, rect, place, Ref(form))
        placed.setdefault(index, []).append(
            engine.add_object(target, annotation))

    written = 0
    for index in range(target.page_count):
        ours = placed.get(index, [])
        already = engine.annotation_xrefs(target, index)
        kept = already if keep_existing else furniture(target, index)
        if not keep_existing:
            # The annotations a markup still *is*, kept exactly as their own
            # author wrote them, in the order the file had them. This is what
            # makes a drawing that has been opened and saved here identical to
            # the one that came in, wherever it is opened afterwards.
            untouched = set(appearances.theirs.get(index, ()))
            kept = kept + [number for number in already
                           if number in untouched and number not in kept]
        if kept + ours == already:
            continue                       # the page already says exactly this
        engine.set_page_annotations(target, index, kept + ours)
        written += len(ours)
    return written


def furniture(target, index: int) -> list[int]:
    """A page's own links and form fields — everything that is not markup."""
    from ..pdf.engine import NOT_MARKUP

    kept = []
    for number in engine.annotation_xrefs(target, index):
        holder = engine.object_at(target, number)
        if isinstance(holder, dict) and \
                str(holder.get("Subtype") or "") in NOT_MARKUP:
            kept.append(number)
    return kept


class Placement:
    """Where a markup's coordinates land in the file's own space.

    A markup is positioned in display points — down the page from its top-left
    corner, the way it is drawn. A PDF annotation is positioned in the file's
    own space, up the page from the bottom-left corner of the *unrotated*
    sheet. On a page that is not turned those differ by a flip, which is what
    this used to do everywhere and what everything still falls back to. On a
    page that says it is turned ninety degrees they differ by a rotation as
    well, and a markup written with only the flip lands on the wrong edge of
    the paper — which is precisely the sort of thing that only shows up on
    somebody else's drawing.
    """

    def __init__(self, matrix=None, page_height: float = 0.0):
        self._matrix = matrix
        self._height = float(page_height)

    @classmethod
    def upright(cls, page_height: float) -> "Placement":
        """A page with no rotation of its own: the flip, and nothing else."""
        return cls(None, page_height)

    @classmethod
    def of_page(cls, page) -> "Placement":
        """The real transform for a MuPDF page, rotation and all."""
        try:
            return cls(engine.to_pdf(page), float(page.rect.height))
        except Exception:                              # noqa: BLE001
            return cls(None, 0.0)

    def point(self, x: float, y: float) -> tuple[float, float]:
        if self._matrix is None:
            return float(x), self._height - float(y)
        return engine.pdf_point_with(self._matrix, x, y)

    def rect(self, rect) -> list[float]:
        """A QRectF in display points, as the annotation's own /Rect."""
        one = self.point(rect.left(), rect.top())
        two = self.point(rect.right(), rect.bottom())
        return [min(one[0], two[0]), min(one[1], two[1]),
                max(one[0], two[0]), max(one[1], two[1])]


def annotation_for(item, rect, place, appearance=None) -> dict:
    """The annotation dictionary for one markup.

    A plain dictionary of :mod:`markforge.pdf.objects` values. *place* says how
    display points become the file's own coordinates. *appearance* is the form
    the annotation shows itself with, and may be left out while the appearance
    is still being drawn.
    """
    if not isinstance(place, Placement):
        # A page height, which is what this took before there were pages that
        # could be turned. Still the right answer for a page that is not.
        place = Placement.upright(float(place))
    annotation: dict = {
        "Type": Name("Annot"),
        "Subtype": Name(subtype_for(item)),
        "Rect": place.rect(rect),
        "F": 4,                                         # printed, not hidden
        "NM": item.uid,
    }
    if item.author:
        annotation["T"] = item.author
    said = item.comment or item.summary()
    if said:
        annotation["Contents"] = said
    if item.subject:
        annotation["Subj"] = item.subject
    colour = _colour(getattr(item.style, "stroke", ""))
    if colour is not None:
        annotation["C"] = colour
    inside = _colour(getattr(item.style, "fill", ""))
    if inside is not None:
        annotation["IC"] = inside
    opacity = float(getattr(item.style, "opacity", 1.0) or 1.0)
    if opacity < 1.0:
        annotation["CA"] = opacity
    width = float(getattr(item.style, "width", 0.0) or 0.0)
    if width > 0:
        annotation["BS"] = {"W": width}
    _add_the_geometry(annotation, item, rect, place)
    if appearance is not None:
        annotation["AP"] = {"N": appearance}
    return annotation


def _add_the_geometry(annotation, item, rect, place: "Placement") -> None:
    """Say what the markup is, not only where its box is.

    An annotation's rectangle has to hold everything it draws, arrow heads and
    line thickness included, so it is bigger than the shape inside it. A reader
    that lets the shape be edited needs to know the difference, or the first
    drag of a handle moves an edge that was never there.

    Past that, this is where a markup says what kind of thing it is in the
    PDF's own words — a cloudy border rather than a drawn cloud, a callout
    line rather than a drawn leader, a dimension's leader lines rather than
    two drawn ticks. Written that way it stays that thing wherever it is
    opened, instead of arriving as a picture that happens to be movable.
    """
    subtype = str(annotation.get("Subtype"))
    kind = getattr(item, "kind", "")
    if subtype in ("Square", "Circle"):
        try:
            shape = item.mapRectToParent(item.local_rect()).normalized()
        except Exception:                              # noqa: BLE001
            return
        annotation["RD"] = [max(shape.left() - rect.left(), 0.0),
                            max(shape.top() - rect.top(), 0.0),
                            max(rect.right() - shape.right(), 0.0),
                            max(rect.bottom() - shape.bottom(), 0.0)]
        if kind == "cloud":
            _cloudy(annotation, item)
        return
    if subtype == "FreeText":
        _free_text(annotation, item, rect, place)
        return
    points = _points_on_the_page(item, place)
    if not points:
        return
    if subtype == "Line":
        annotation["L"] = [points[0][0], points[0][1],
                           points[-1][0], points[-1][1]]
        _line_endings(annotation, item)
        if item.TYPE == "measure":
            _dimension(annotation, item)
        return
    if subtype in ("Polygon", "PolyLine"):
        annotation["Vertices"] = [value for point in points for value in point]
        _line_endings(annotation, item)
        if kind == "cloud":
            _cloudy(annotation, item)
        elif item.TYPE == "measure":
            _measured(annotation, item, subtype)
        return
    if subtype == "Ink":
        annotation["InkList"] = [[value for point in points for value in point]]


def _cloudy(annotation, item) -> None:
    """A cloud is a border effect, not a shape drawn to look like one."""
    # How pronounced the scallops are. Ours are drawn to a radius; the PDF
    # says it in steps of one, and two is the middle setting every reader has.
    radius = float(getattr(item, "cloud_radius", 9.0) or 9.0)
    annotation["BE"] = {
        "S": Name("C"),
        "I": 1.0 if radius < 7.0 else (2.0 if radius < 14.0 else 3.0),
    }
    if str(annotation.get("Subtype")) == "Polygon":
        annotation["IT"] = Name("PolygonCloud")


def _line_endings(annotation, item) -> None:
    """What is drawn on each end of a line, in the PDF's ten names."""
    start = LINE_ENDINGS.get(getattr(item.style, "arrow_start", "none"), "None")
    end = LINE_ENDINGS.get(getattr(item.style, "arrow_end", "none"), "None")
    if start == "None" and end == "None":
        return
    annotation["LE"] = [Name(start), Name(end)]


def _dimension(annotation, item) -> None:
    """A dimension, said the way a PDF says one.

    Every part of it already had a name in the specification. The witness lines
    are a leader length with an extension past the line and an offset that
    keeps them clear of what they measure; the value written along the line is
    a rendered caption positioned inline; and the value dragged off onto a
    leader is that caption's offset.
    """
    from ..items import measure as measure_module

    if item.kind not in measure_module.DIMENSIONED:
        return
    annotation["IT"] = Name("LineDimension")
    reach = float(getattr(item, "witness_reach", 0.0) or 0.0)
    if reach:
        annotation["LL"] = -reach
        annotation["LLE"] = float(measure_module.WITNESS_OVERSHOOT)
        annotation["LLO"] = float(measure_module.WITNESS_GAP)
    if getattr(item, "show_label", False) and getattr(item, "value_text", ""):
        annotation["Cap"] = True
        annotation["CP"] = Name("Inline")
        offset = getattr(item, "label_offset", None)
        if offset is not None and (offset.x() or offset.y()):
            annotation["CO"] = [offset.x(), -offset.y()]
        annotation["Contents"] = item.value_text
    _measure_dictionary(annotation, item)


def _measured(annotation, item, subtype: str) -> None:
    """A take-off says it is one, and says what it was measured against."""
    from ..items import measure as measure_module

    if item.kind in (measure_module.AREA, measure_module.VOLUME,
                     measure_module.PERIMETER):
        annotation["IT"] = Name("PolygonDimension")
    elif item.kind == measure_module.POLYLENGTH:
        annotation["IT"] = Name("PolyLineDimension")
    _measure_dictionary(annotation, item)


def _measure_dictionary(annotation, item) -> None:
    """The page scale, as a PDF's own measurement dictionary.

    Without this a measurement is a line with a number written beside it, and
    the number means nothing to the reader it is opened in. With it, the scale
    travels: another editor can measure the same drawing and agree.
    """
    scale = getattr(item, "page_scale", None)
    scale = scale() if callable(scale) else None
    if scale is None:
        return
    calibrated = getattr(scale, "is_calibrated", False)
    if callable(calibrated):
        calibrated = calibrated()
    if not calibrated:
        return
    try:
        unit = str(scale.display_unit)
        per_point = float(scale.length(1.0).magnitude)
    except Exception:                                  # noqa: BLE001
        return
    if not per_point:
        return
    numbers = {
        "Type": Name("NumberFormat"),
        "U": unit,
        "C": per_point,
        "D": 100,
        "F": Name("D"),
        "RD": ".",
        "RT": ",",
    }
    annotation["Measure"] = {
        "Type": Name("Measure"),
        "Subtype": Name("RL"),
        "R": str(scale.label),
        "X": [numbers],
        "D": [dict(numbers)],
        "A": [dict(numbers)],
    }


def _free_text(annotation, item, rect, place: "Placement") -> None:
    """Words on the page, and the leader that points at what they are about."""
    if item.TYPE == "typewriter":
        annotation["IT"] = Name("FreeTextTypeWriter")
    written = ""
    try:
        written = item.text()
    except Exception:                                  # noqa: BLE001
        written = ""
    if written:
        annotation["Contents"] = written
    annotation["Q"] = _justification(item)
    colour = getattr(item.style, "text_color", "") or "#000000"
    numbers = _colour(colour)
    if numbers is not None:
        annotation["DA"] = (f"{numbers[0]} {numbers[1]} {numbers[2]} rg "
                            f"/Helv {float(item.style.font_size)} Tf")
    leader = _callout_line(item, place)
    if leader:
        annotation["IT"] = Name("FreeTextCallout")
        annotation["CL"] = [value for point in leader for value in point]
        annotation["LE"] = Name(
            LINE_ENDINGS.get(getattr(item.style, "arrow_end", "arrow"),
                             "ClosedArrow"))
    try:
        box = item.mapRectToParent(item.local_rect()).normalized()
    except Exception:                                  # noqa: BLE001
        return
    annotation["RD"] = [max(box.left() - rect.left(), 0.0),
                        max(box.top() - rect.top(), 0.0),
                        max(rect.right() - box.right(), 0.0),
                        max(rect.bottom() - box.bottom(), 0.0)]


def _justification(item) -> int:
    """Left, centred or right, as a PDF numbers them."""
    from PySide6.QtCore import Qt

    try:
        alignment = item.style.alignment()
    except Exception:                                  # noqa: BLE001
        return 0
    if alignment & Qt.AlignHCenter:
        return 1
    if alignment & Qt.AlignRight:
        return 2
    return 0


def _callout_line(item, place: "Placement") -> list:
    """A call-out's leader: where it points, its knee, and where the words are.

    Three points when the leader has a hinge, which is what a call-out's leader
    has; two when it runs straight. The PDF has both, in that order — the end
    that points at something comes first.
    """
    leaders = getattr(item, "leaders", None)
    if not leaders:
        return []
    leader = leaders[0]
    try:
        points = [item.mapToParent(item.tip_of(leader)),
                  item.mapToParent(item.elbow_of(leader)),
                  item.mapToParent(item.side_point_of(leader))]
    except Exception:                                  # noqa: BLE001
        return []
    return [place.point(point.x(), point.y()) for point in points]


def _points_on_the_page(item, place: "Placement") -> list:
    """A line's corners where the PDF keeps them: up from the bottom."""
    corners = getattr(item, "points", None)
    if not corners:
        return []
    placed = []
    for corner in corners:
        on_page = item.mapToParent(corner)
        placed.append(place.point(on_page.x(), on_page.y()))
    return placed


def _colour(value: str) -> Optional[list]:
    """A ``#rrggbb`` as the three numbers a PDF annotation wants."""
    text = (value or "").strip()
    if not text.startswith("#") or len(text) not in (7, 9):
        return None
    try:
        red = int(text[1:3], 16) / 255.0
        green = int(text[3:5], 16) / 255.0
        blue = int(text[5:7], 16) / 255.0
    except ValueError:
        return None
    return [red, green, blue]
