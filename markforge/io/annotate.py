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

from PySide6.QtCore import QPointF

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
    # Stacking order, bottom first, as a PDF paints its annotations: reading
    # order put a section mark's arrowhead over the white bubble meant to
    # cover its base, because the arrowhead's top was the higher on the page.
    stacked = sorted(enumerate(frame.markups()),
                     key=lambda pair: (pair[1].zValue(), pair[0]))
    for _order, item in stacked:
        if not item.printable:
            continue
        if item.flattened or item.from_drawing:
            continue
        if getattr(item, "TYPE", "") == "link":
            continue                   # written as a /Link annotation instead
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
            rect = _even_about_the_shape(item, rect)
            if rect.width() <= 0 or rect.height() <= 0:
                continue
            appearances.add(index, item, rect)
    return appearances


def _even_about_the_shape(item, rect):
    """A square or circle's Rect, the same distance out from it on each side.

    ``/RD`` says how far in from ``Rect`` the shape is, and readers do not
    agree which of its four numbers is the top and which the bottom: MuPDF and
    others take them in the file's own y-up order, the specification's words
    say top first. Room kept under a rectangle for its size label made the
    two differ by 26 pt, so an editor that read them the other way round put
    the drag box that far off the shape. Kept even, the order cannot matter —
    which is also how Bluebeam writes them.
    """
    if subtype_for(item) not in ("Square", "Circle"):
        return rect
    try:
        shape = item.mapRectToParent(item.local_rect()).normalized()
    except Exception:                                  # noqa: BLE001
        return rect
    # The narrowest side already holds the ink — border, scallops and margin;
    # the room above for the turning handle is screen furniture.
    across = max(min(shape.left() - rect.left(), rect.right() - shape.right()), 0.0)
    down = max(min(shape.top() - rect.top(), rect.bottom() - shape.bottom()), 0.0)
    if getattr(item, "show_size", False) and getattr(item, "size_text", ""):
        # The size written under it is printed, so the box keeps room for it
        # — on both sides, to stay even.
        down = max(shape.top() - rect.top(), rect.bottom() - shape.bottom(), 0.0)
    return shape.adjusted(-across, -down, across, down)


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
    groups = _groups_on_each_page(appearances.entries)
    leaders: dict = {}
    for order, (index, item, rect) in enumerate(appearances.entries):
        if not 0 <= index < target.page_count:
            continue
        form = engine.form_from_page(target, scratch, order,
                                     rect.width(), rect.height())
        if form is None:
            continue
        place = Placement.of_page(target[index])
        annotation = annotation_for(item, rect, place, Ref(form))
        members = groups.get((index, getattr(item, "group", "")))
        if members:
            leader = leaders.get((index, item.group))
            if leader is None:
                annotation["GroupNesting"] = _group_nesting(members)
            else:
                annotation["RT"] = Name("Group")
                annotation["IRT"] = Ref(leader)
        number = engine.add_object(target, annotation)
        if members and (index, item.group) not in leaders:
            leaders[(index, item.group)] = number
        placed.setdefault(index, []).append(number)

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


def _groups_on_each_page(entries) -> dict:
    """The grouped markups on each page, keyed by (page, outermost group)."""
    groups: dict = {}
    for index, item, _rect in entries:
        name = getattr(item, "group", "")
        if name:
            groups.setdefault((index, name), []).append(item)
    return {key: items for key, items in groups.items() if len(items) > 1}


def _group_nesting(members: list) -> list:
    """A group as Bluebeam writes it: its title, then its members by name.

    The first markup leads the group and carries this; every other one points
    at it with ``/IRT`` and says ``/RT /Group``. A group inside the group is a
    list of its own, headed "Group" — a section mark's bubble and its cut line
    are two, inside the one called "Section" — so the arrangement survives a
    trip through Bluebeam and back.
    """
    title = next((m.group_title for m in members if getattr(m, "group_title", "")),
                 "") or "Group"
    tree: dict = {"members": [], "groups": {}}
    for item in members:
        node = tree
        for step in tuple(getattr(item, "group_path", ()) or ())[1:]:
            node = node["groups"].setdefault(step, {"members": [], "groups": {}})
        node["members"].append(Name(item.uid))

    def listed(node, head) -> list:
        out = [head] + list(node["members"])
        out += [listed(inner, "Group") for inner in node["groups"].values()]
        return out
    return listed(tree, title)


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
        dashes = []
        try:
            dashes = [float(step) * width for step in item.style.dashes()]
        except Exception:                              # noqa: BLE001
            dashes = []
        if dashes:
            annotation["BS"] = {"W": width, "S": Name("D"), "D": dashes}
    _bluebeam_look(annotation, item)
    _add_the_geometry(annotation, item, rect, place)
    if appearance is not None:
        annotation["AP"] = {"N": appearance}
    return annotation


def _bluebeam_look(annotation, item) -> None:
    """The keys Bluebeam draws a markup from that PDF itself has no word for.

    Bluebeam keeps a fill's own transparency apart from the line's
    (/FillOpacity beside /CA), names its hatch and says how big it is drawn
    (/PatternName, /PatternColor, /PatternScale), and blends a highlighter
    with /BM. Other readers pass over them; Bluebeam draws with them, and
    without them a pale fill came back solid and a hatch came back as none.
    """
    style = item.style
    fill = _colour(getattr(style, "fill", ""))
    if fill is not None:
        try:
            annotation["FillOpacity"] = float(style.fill_opacity)
        except (TypeError, ValueError):
            pass
    if getattr(style, "hatched", lambda: False)():
        annotation["PatternName"] = str(style.hatch or "Hatch")
        ink = _colour(getattr(style, "hatch_color", "") or getattr(style, "stroke", ""))
        if ink is not None:
            annotation["PatternColor"] = ink
        annotation["PatternScale"] = float(style.hatch_scale or 1.0)
    if getattr(style, "blend", "") == "multiply":
        annotation["BM"] = Name("Multiply")


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
        # /RD is the gap between Rect and the *ink*, and the shape's own path
        # is inside that by half its border — a border is drawn on the line,
        # not beside it. Writing the gap to the path instead puts the shape
        # half a border width in wherever it is opened, and reads back that
        # much smaller here. See markforge.io.btx.drawn_box, which is the
        # same rule from the other side.
        border = max(float(getattr(item.style, "width", 0.0) or 0.0), 0.0) / 2.0
        # Left, bottom, right, top: the file's own y-up order, the one the
        # editors that redraw a markup from its dictionary go by.
        annotation["RD"] = [max(shape.left() - rect.left() - border, 0.0),
                            max(rect.bottom() - shape.bottom() - border, 0.0),
                            max(rect.right() - shape.right() - border, 0.0),
                            max(shape.top() - rect.top() - border, 0.0)]
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
    if subtype in ("Polygon", "PolyLine") and kind == "arc":
        # An arc is one curved side: its two ends, and the curve between them
        # in Bluebeam's own words, so an editor that redraws it bends it.
        ends, curves = _arc_on_the_page(item, place)
        if ends:
            annotation["Vertices"] = ends
            annotation["Curves"] = curves
            _line_endings(annotation, item)
            return
    if subtype in ("Polygon", "PolyLine"):
        annotation["Vertices"] = [value for point in points for value in point]
        curves = _curves_on_the_page(item, place)
        if curves:
            annotation["Curves"] = curves
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
    measure = {
        "Type": Name("Measure"),
        "Subtype": Name("RL"),
        "R": str(scale.label),
        "X": [numbers],
        "D": [dict(numbers)],
        "A": [dict(numbers)],
    }
    y_factor = float(getattr(scale, "y_factor", 1.0) or 1.0)
    if abs(y_factor - 1.0) > 1e-9:
        # A different scale down the page: the PDF's own Y number format,
        # given as a conversion from the X units.
        measure["Y"] = [dict(numbers, C=y_factor)]
    annotation["Measure"] = measure


def _free_text(annotation, item, rect, place: "Placement") -> None:
    """Words on the page, and the leader that points at what they are about."""
    if item.TYPE == "typewriter":
        annotation["IT"] = Name("FreeTextTypeWriter")
    # A box without a border says so, as Bluebeam writes one: no border
    # colour and a border width of nought. Left unsaid, an editor that
    # redraws the markup from its dictionary gives it the default one-point
    # frame it never had.
    # Colours the way Bluebeam writes words on the page: /C is the
    # background, the frame and leader take /DA's colour, the words /DS's,
    # and /LEIC fills the arrowhead. A box without a frame says so, with a
    # border of nought; left unsaid, an editor that redraws the markup gives
    # it the one-point frame it never had.
    width = float(getattr(item.style, "width", 0.0) or 0.0)
    background = _colour(getattr(item.style, "fill", ""))
    annotation["C"] = background if background is not None else []
    annotation.pop("IC", None)
    line = _colour(getattr(item.style, "stroke", ""))
    if line is not None:
        annotation["LEIC"] = line
    if line is None or width <= 0:
        annotation["BS"] = {"W": 0}
    if getattr(item.style, "text_shape", "") == "circle":
        annotation["Shape"] = Name("Circle")
    written = ""
    try:
        written = item.text()
    except Exception:                                  # noqa: BLE001
        written = ""
    if written:
        annotation["Contents"] = written
    annotation["Q"] = _justification(item)
    settings, rich = _rich_text_of(item)
    if settings:
        annotation["DS"] = settings
    if rich:
        annotation["RC"] = rich
    # /DA's colour is the frame's and the leader's, as Bluebeam has it; the
    # words' own colour is in /DS and /RC. Without a frame colour, the words'.
    colour = getattr(item.style, "stroke", "") or \
        getattr(item.style, "text_color", "") or "#000000"
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
    # Left, bottom, right, top, as for a square: see _add_the_geometry.
    annotation["RD"] = [max(box.left() - rect.left(), 0.0),
                        max(rect.bottom() - box.bottom(), 0.0),
                        max(rect.right() - box.right(), 0.0),
                        max(box.top() - rect.top(), 0.0)]


def _css_family(family: str) -> str:
    family = (family or "Helvetica").strip()
    return f"'{family}'" if " " in family else family


def _rich_text_of(item) -> tuple[str, str]:
    """The words' look as Bluebeam writes it: a default style and the runs.

    ``/DS`` is the box's own setting — face, size, alignment both ways, the
    margin and the colour; ``/RC`` is the words run by run, in the XHTML
    subset PDF defines. An editor that redraws a text box draws it from
    these, so without them every title came back as plain Helvetica at one
    size, left-aligned at the top of its box.
    """
    from html import escape
    from PySide6.QtGui import QTextFormat

    style = item.style
    size = float(getattr(style, "font_size", 10.0) or 10.0)
    colour = getattr(style, "text_color", "") or "#000000"
    align = {"center": "center", "right": "right"}.get(getattr(style, "align", ""), "left")
    valign = {"middle": "middle", "bottom": "bottom"}.get(getattr(style, "valign", ""), "top")
    # Bluebeam sets its words a point further in than the margin it states;
    # the importer adds that point back, so it is taken off here.
    margin = max(float(getattr(style, "padding", 4.0) or 0.0) - 1.0, 0.0)
    weight = " bold" if getattr(style, "bold", False) else ""
    slant = " italic" if getattr(style, "italic", False) else ""
    settings = (f"font:{slant}{weight} {_css_family(style.font_family)} {size:g}pt; "
                f"text-align:{align}; text-valign:{valign}; margin:{margin:g}pt; "
                f"line-height:{size * 1.15:.1f}pt; color:{colour}")
    if getattr(style, "underline", False):
        settings += "; text-decoration:underline"
    document = getattr(item, "doc", None)
    if document is None:
        return settings, ""
    paragraphs = []
    block = document.begin()
    while block.isValid():
        runs = []
        pieces = block.begin()
        while not pieces.atEnd():
            fragment = pieces.fragment()
            pieces += 1
            if not fragment.isValid() or not fragment.text():
                continue
            look = fragment.charFormat()
            said = []
            # fontFamilies() crashes PySide 6.11 when it holds nothing; the
            # font's own family is the same answer, safely.
            family = look.font().family() if look.hasProperty(QTextFormat.FontFamilies) else ""
            if family and family != style.font_family:
                said.append(f"font-family:{_css_family(family)}")
            point = look.fontPointSize()
            if point and abs(point - size) > 1e-3:
                said.append(f"font-size:{point:g}pt")
            if look.fontWeight() >= 600 and not getattr(style, "bold", False):
                said.append("font-weight:bold")
            if look.fontItalic() and not getattr(style, "italic", False):
                said.append("font-style:italic")
            if look.fontUnderline() and not getattr(style, "underline", False):
                said.append("text-decoration:underline")
            if look.hasProperty(QTextFormat.ForegroundBrush):
                shade = look.foreground().color().name()
                if shade.lower() != colour.lower():
                    said.append(f"color:{shade}")
            text = escape(fragment.text().replace("\u2028", "\n")).replace("\n", "<br/>")
            runs.append(f'<span style="{"; ".join(said)}">{text}</span>' if said else text)
        placed = block.blockFormat().alignment()
        from PySide6.QtCore import Qt
        own = ("center" if placed & Qt.AlignHCenter else
               "right" if placed & Qt.AlignRight else align)
        paragraphs.append(f'<p style="text-align:{own}">{"".join(runs)}</p>')
        block = block.next()
    rich = ('<?xml version="1.0"?><body xmlns="http://www.w3.org/1999/xhtml" '
            'xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" '
            'xfa:APIVersion="Acrobat:11.0.0" xfa:spec="2.0.2" '
            f'style="{escape(settings)}">{"".join(paragraphs)}</body>')
    return settings, rich


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


def _arc_on_the_page(item, place: "Placement"):
    """An arc's two ends and its one cubic curve, in the file's coordinates."""
    try:
        path = item.build_path()
    except Exception:                                  # noqa: BLE001
        return [], []
    if path.elementCount() < 4:
        return [], []

    def on_page(index):
        element = path.elementAt(index)
        where = item.mapToParent(QPointF(element.x, element.y))
        return place.point(where.x(), where.y())
    start, first, second, end = (on_page(i) for i in range(4))
    return [*start, *end], [0, *first, *second]


def _curves_on_the_page(item, place: "Placement") -> list:
    """Curved sides as Bluebeam writes them: side, then two control points."""
    out = []
    for side, (first, second) in sorted((getattr(item, "bezier", None) or {}).items()):
        out.append(int(side))
        for control in (first, second):
            on_page = item.mapToParent(control)
            out.extend(place.point(on_page.x(), on_page.y()))
    return out


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
