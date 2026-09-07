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

import os
import tempfile
from typing import Optional

from ..pdf.objects import Name

# What each kind of markup becomes. A shape that a PDF has a real annotation
# for gets that one, so a reader can edit it natively; everything else goes as
# a stamp, which every reader can select, move and delete.
#
# Everything here is built as the plain dictionaries and names of
# :mod:`markforge.pdf`, not as any library's object types. That is what lets
# the same annotation be appended to a file MarkForge is updating in place and
# handed to pypdf when a document is being assembled from several sources —
# one description of what a markup is, written once.
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

    The Drawing layer is not markup: it is the page's own line work, read out
    of the PDF it came from so that things can snap to it. It belongs to the
    page and is written as part of it — as the original page where that has
    been kept, and painted into the sheet where it has not. Turning several
    thousand pieces of somebody else's drawing into several thousand
    annotations would be wrong as well as slow.

    Nor does anything flattened come out as a markup: flattening is the
    decision that it is part of the page now, and it is painted in.
    """
    items = []
    for item in frame.ordered_markups():
        if not item.printable or not frame.layer_prints(item):
            continue
        if item.flattened or item.layer == "Drawing":
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
        annotation = annotation_for(item, rect, height)
        holder = as_pypdf(annotation)
        _put_the_appearance_on(holder, reference)
        writer.add_annotation(index, holder)
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


def as_pypdf(value):
    """One of this module's values, as the object type pypdf writes.

    The description of a markup is written once, in the PDF's own vocabulary.
    This is the translation for the path that hands it to pypdf; the path that
    appends it to a file MarkForge is updating writes it as it stands.
    """
    from pypdf.generic import (ArrayObject, BooleanObject, DictionaryObject,
                               FloatObject, NameObject, NumberObject,
                               TextStringObject)

    if isinstance(value, Name):
        return NameObject("/" + str(value))
    if isinstance(value, bool):
        return BooleanObject(value)
    if isinstance(value, int):
        return NumberObject(value)
    if isinstance(value, float):
        return FloatObject(value)
    if isinstance(value, str):
        return TextStringObject(value)
    if isinstance(value, (list, tuple)):
        return ArrayObject([as_pypdf(item) for item in value])
    if isinstance(value, dict):
        holder = DictionaryObject()
        for key, item in value.items():
            holder[NameObject("/" + str(key))] = as_pypdf(item)
        return holder
    return value


def _put_the_appearance_on(holder, reference) -> None:
    """Point a pypdf annotation at the form it shows itself with."""
    from pypdf.generic import DictionaryObject, NameObject

    look = DictionaryObject()
    look[NameObject("/N")] = reference
    holder[NameObject("/AP")] = look


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


def annotation_for(item, rect, page_height: float, appearance=None) -> dict:
    """The annotation dictionary for one markup.

    A plain dictionary of :mod:`markforge.pdf` values. *appearance* is whatever
    stands for the form the annotation shows itself with — a reference in a
    file being updated, a cloned object in one being assembled — and may be
    left out while the appearance is still being drawn.
    """
    annotation: dict = {
        "Type": Name("Annot"),
        "Subtype": Name(subtype_for(item)),
        "Rect": [rect.left(), page_height - rect.bottom(),
                 rect.right(), page_height - rect.top()],
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
    _add_the_geometry(annotation, item, rect, page_height)
    if appearance is not None:
        annotation["AP"] = {"N": appearance}
    return annotation


def replies_to(item, target, rect, page_height: float) -> list[dict]:
    """The reply annotations that carry a markup's review, if it has one.

    A status and a conversation are not fields on an annotation: each is an
    annotation of its own pointing back at the markup through ``/IRT``. That
    is how Acrobat and Bluebeam both record a review, and writing it their way
    is the difference between a marked-up drawing somebody can answer and one
    they can only look at.

    *target* is whatever stands for the markup being answered — a reference in
    the file being written.
    """
    where = [rect.left(), page_height - rect.bottom(),
             rect.left() + 20.0, page_height - rect.bottom() + 20.0]
    out: list[dict] = []
    for reply in getattr(item, "replies", []) or []:
        entry = {
            "Type": Name("Annot"),
            "Subtype": Name("Text"),
            "Rect": list(where),
            "F": 2,                                    # hidden: it is the thread
            "IRT": target,
            "RT": Name("R"),
            "Contents": str(reply.get("text", "")),
        }
        if reply.get("author"):
            entry["T"] = str(reply["author"])
        stamp = _pdf_date(str(reply.get("at", "")))
        if stamp:
            entry["M"] = stamp
        out.append(entry)
    status = getattr(item, "status", "")
    if status or getattr(item, "status_by", ""):
        entry = {
            "Type": Name("Annot"),
            "Subtype": Name("Text"),
            "Rect": list(where),
            "F": 2,
            "IRT": target,
            "RT": Name("R"),
            "State": status or "None",
            "StateModel": "Review",
            "Contents": f"Set status to {status or 'None'}.",
        }
        if getattr(item, "status_by", ""):
            entry["T"] = item.status_by
        stamp = _pdf_date(getattr(item, "status_at", ""))
        if stamp:
            entry["M"] = stamp
        out.append(entry)
    return out


def _pdf_date(stamp: str) -> str:
    """An ISO time as a PDF one. Empty when there is nothing to say."""
    digits = "".join(character for character in stamp if character.isdigit())
    if len(digits) < 8:
        return ""
    return "D:" + digits[:14].ljust(14, "0")


def _add_the_geometry(annotation, item, rect, page_height: float) -> None:
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
        _free_text(annotation, item, rect, page_height)
        return
    points = _points_on_the_page(item, page_height)
    if not points:
        return
    if subtype == "Line":
        annotation["L"] = [points[0][0], points[0][1],
                           points[-1][0], points[-1][1]]
        _line_endings(annotation, item)
        if item.TYPE == "measure":
            _dimension(annotation, item, page_height)
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


def _dimension(annotation, item, page_height: float) -> None:
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


def _free_text(annotation, item, rect, page_height: float) -> None:
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
    leader = _callout_line(item, page_height)
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


def _callout_line(item, page_height: float) -> list:
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
    return [(point.x(), page_height - point.y()) for point in points]


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
