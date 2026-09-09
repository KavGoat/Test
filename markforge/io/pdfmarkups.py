"""A PDF's annotations, read back as markups.

A drawing that has been through Bluebeam keeps its clouds, dimensions,
call-outs and comments as PDF annotations. Opening one and getting a picture of
somebody's redlines — or worse, several thousand loose line segments where a
cloud used to be — is not opening their markup. So each annotation comes back
as the markup it is: one thing to click on, in its own colour, carrying whoever
wrote it and whatever they said.

What a PDF has no annotation for, or what this does not recognise, still comes
across as one markup rather than as debris: its appearance is a drawing, and a
drawing is what a sketch markup holds.

Everything an annotation says about where it is — its rectangle, a line's two
ends, a polygon's corners, a call-out's leader — is written in the file's own
space, measured up from the bottom-left corner of the unrotated page. Every one
of them is put through the same transform on the way in, so a markup read off a
page that says it is turned ninety degrees lands where it is actually drawn.
"""
from __future__ import annotations

import os
import re

import pymupdf

from ..pdf import engine

# Annotations that are not somebody's markup and should not become one.
NOT_MARKUP = set(engine.NOT_MARKUP)

# How many annotations are worth bringing across from one page. A page with
# more than this on it is not a marked-up drawing, it is a data dump.
MOST_MARKUPS = 3000


#: How finely an annotation's own appearance is kept. Three times life size
#: stays crisp at the zoom somebody reads a detail at, and a markup is a small
#: part of a sheet, so the pictures are small.
LOOK_SCALE = 3.0


def markups_of_page(source, index: int, scale: float = 1.0,
                    keep_the_look=None) -> list[dict]:
    """Every annotation on one page, as markup payloads in display points.

    With *keep_the_look* — anything that takes PNG bytes and gives back
    somewhere to find them again — each markup also carries a picture of how
    the file it came from drew it. That is what it shows until it is edited,
    and it is the difference between somebody's drawing looking like their
    drawing and looking like this application's best guess at it.
    """
    from .btx import colour

    page = source.page(index)
    place = engine.to_display(page)
    found: list[dict] = []
    for annotation in source.annotations_of(index):
        kind = str(source.resolve(annotation.get("Subtype")) or "")
        if kind in NOT_MARKUP:
            continue
        try:
            made = _one(source, annotation, kind, place, scale, colour)
        except Exception:                              # noqa: BLE001
            made = None
        if made:
            if keep_the_look is not None:
                _keep_the_look(source, index, annotation, made,
                               keep_the_look, place, scale)
            found.extend(made)
        if len(found) >= MOST_MARKUPS:
            break
    return found


def _keep_the_look(source, index: int, annotation: dict, made: list,
                   keep_the_look, place, scale: float) -> None:
    """Hang a picture of the annotation's own appearance on what it became.

    With the rectangle it belongs in, which is the annotation's own and not
    the markup's. A text box sizes itself to whatever it is holding; the
    picture has to go where the file put it, or it is stretched to fit a box
    the file never had and comes out big and soft.

    Only where one markup came of one annotation. An ink annotation is several
    strokes and there is no honest way to cut its picture between them, so
    those draw themselves.
    """
    number = annotation.get("__xref__")
    if len(made) != 1 or not isinstance(number, int):
        return
    raster = engine.annotation_raster(source.doc, index, number, LOOK_SCALE)
    if raster is None or raster.is_empty:
        return
    kept = keep_the_look(_as_png(raster))
    if not kept:
        return
    payload = made[0]
    box = _box(source, annotation, place, scale)
    payload["as_it_came_asset"] = kept
    # Where the picture goes, relative to the markup's own origin.
    payload["as_it_came_rect"] = [box[0] - float(payload.get("x", 0.0)),
                                  box[1] - float(payload.get("y", 0.0)),
                                  box[2], box[3]]


def _as_png(raster) -> bytes:
    """A rendered appearance as PNG bytes."""
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QImage

    # Premultiplied: that is how MuPDF hands back a pixmap with alpha, and
    # reading it as straight alpha puts a grey wash over the whole picture.
    shape = (QImage.Format_RGBA8888_Premultiplied if raster.alpha
             else QImage.Format_RGB888)
    image = QImage(raster.samples, raster.width, raster.height,
                   raster.stride, shape).copy()
    holder = QBuffer()
    holder.open(QIODevice.WriteOnly)
    if not image.save(holder, "PNG"):
        return b""
    return bytes(holder.data())


def _one(source, annotation: dict, kind: str, place, scale: float,
         colour) -> list[dict]:
    """One annotation, as the markup it is."""
    box = _box(source, annotation, place, scale)
    style = _style(source, annotation, colour, scale)
    common = _common(source, annotation)

    intent = str(source.resolve(annotation.get("IT")) or "")
    if kind in ("Square", "Circle"):
        inside = _inset(source, annotation, box, scale)
        shape = "ellipse" if kind == "Circle" else "rect"
        if _is_cloudy(source, annotation):
            shape = "cloud"
        return [_shape("rect", shape, inside, style, common)]
    if kind == "FreeText":
        return [_free_text(source, annotation, box, style, common, place,
                           scale, intent)]
    if kind == "Line":
        ends = _numbers(source, annotation.get("L"))
        if len(ends) >= 4:
            points = [_at(place, ends[0], ends[1], scale),
                      _at(place, ends[2], ends[3], scale)]
            _line_endings(source, annotation, style)
            if intent == "LineDimension":
                return [_dimension(source, annotation, points, style, common,
                                   scale)]
            # No head unless the annotation asked for one. Defaulting to an
            # arrow put a head on every plain line on the sheet — section cut
            # lines, legend rules, leader tails — none of which had one.
            style.setdefault("arrow_end", "none")
            return [_line("line", points, style, common)]
    if kind in ("PolyLine", "Polygon"):
        corners = _numbers(source, annotation.get("Vertices"))
        points = [_at(place, corners[i], corners[i + 1], scale)
                  for i in range(0, len(corners) - 1, 2)]
        if len(points) >= 2:
            _line_endings(source, annotation, style)
            if _is_cloudy(source, annotation) or intent == "PolygonCloud":
                return [_line("cloud", points, style, common)]
            if intent in ("PolygonDimension", "PolyLineDimension"):
                return [_take_off(points, style, common, intent)]
            return [_line("polyline" if kind == "PolyLine" else "polygon",
                          points, style, common)]
    if kind == "Ink":
        return _ink(source, annotation, place, scale, style, common)
    if kind in ("Highlight", "StrikeOut", "Underline", "Squiggly"):
        style = dict(style)
        style["fill"] = style.get("stroke") or "#ffe066"
        style["stroke"] = ""
        style["fill_opacity"] = 0.5
        return [_shape("rect", "highlight", box, style, common)]
    if kind == "Text":
        return [_text("note", box, style, common)]
    drawn = _appearance(source, annotation, scale)
    if drawn:
        return drawn
    # A stamp, or anything else this does not have a shape for. It still has
    # an appearance — that is what the file draws for it, and for a title block
    # or a company stamp it is the whole of the markup — so it comes across as
    # a plain box carrying that picture, which can be picked up and moved like
    # anything else. Leaving it out because there is no shape to give it is how
    # a title block goes missing from a drawing.
    return [_shape("rect", "rect", box,
                   dict(style, stroke="", fill="", width=0.0), common)]


# -- the pieces ------------------------------------------------------------
def _at(place, x, y, scale: float) -> list[float]:
    """One point of the file's own space, as a display point."""
    point = pymupdf.Point(float(x), float(y)) * place
    return [point.x * scale, point.y * scale]


def _numbers(source, value) -> list[float]:
    values = source.resolve(value)
    if not isinstance(values, (list, tuple)):
        return []
    out = []
    for item in values:
        found = source.resolve(item)
        if isinstance(found, (int, float)) and not isinstance(found, bool):
            out.append(float(found))
    return out


def _box(source, annotation: dict, place, scale: float) -> list[float]:
    """The annotation's rectangle, in display points: [x, y, w, h]."""
    rect = _numbers(source, annotation.get("Rect"))
    if len(rect) != 4:
        return [0.0, 0.0, 1.0, 1.0]
    one = _at(place, rect[0], rect[1], scale)
    two = _at(place, rect[2], rect[3], scale)
    left, right = min(one[0], two[0]), max(one[0], two[0])
    top, bottom = min(one[1], two[1]), max(one[1], two[1])
    return [left, top, max(right - left, 0.5), max(bottom - top, 0.5)]


def _inset(source, annotation: dict, box: list, scale: float) -> list[float]:
    """A square or circle sits inside its rectangle by its own difference."""
    inset = _numbers(source, annotation.get("RD"))
    if len(inset) != 4:
        return box
    left, top, right, bottom = (value * scale for value in inset)
    return [box[0] + left, box[1] + top,
            max(box[2] - left - right, 0.5), max(box[3] - top - bottom, 0.5)]


def _style(source, annotation: dict, colour, scale: float) -> dict:
    line = colour(_numbers(source, annotation.get("C")))
    fill = colour(_numbers(source, annotation.get("IC")))
    width = 1.0
    border = source.resolve(annotation.get("BS"))
    if isinstance(border, dict):
        found = source.resolve(border.get("W"))
        if isinstance(found, (int, float)):
            width = float(found)
    opacity = source.resolve(annotation.get("CA"))
    style = {"stroke": line or "#e03131", "fill": fill,
             "width": max(width * scale, 0.1)}
    if isinstance(opacity, (int, float)) and 0 < float(opacity) < 1:
        style["opacity"] = float(opacity)
    return style


#: ``/DA`` is a scrap of a content stream: the colour to set and the font to
#: pick, in the operators a page would use. Two of them matter here — the size
#: the words are set at, and what colour they are set in — and without them
#: every text box on a sheet comes back at whatever size this application
#: happens to default to, which on a title block is the difference between a
#: label and a word running off the end of its box.
_FONT = re.compile(r"/([^\s/]+)\s+([0-9.]+)\s+Tf")
_GREY = re.compile(r"([0-9.]+)\s+g(?![A-Za-z])")
_RGB = re.compile(r"([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s+rg(?![A-Za-z])")
_CMYK = re.compile(r"([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s+k(?![A-Za-z])")


def _how_the_words_are_set(source, annotation: dict, scale: float) -> dict:
    """The size and colour a free text annotation sets its words in."""
    said = source.resolve(annotation.get("DA"))
    out: dict = {}
    if not isinstance(said, str) or not said:
        return out
    found = _FONT.search(said)
    if found:
        try:
            size = float(found.group(2))
        except ValueError:
            size = 0.0
        # A size of zero means "fit the box", which a PDF reader works out for
        # itself. Nothing here can, so it keeps its own default rather than
        # setting the words at nothing.
        if size > 0:
            out["font_size"] = max(size * scale, 1.0)
    found = _RGB.search(said)
    if found:
        out["text_color"] = _hex(*(float(v) for v in found.groups()))
    elif _CMYK.search(said):
        cyan, magenta, yellow, black = (float(v) for v in
                                        _CMYK.search(said).groups())
        out["text_color"] = _hex((1 - cyan) * (1 - black),
                                 (1 - magenta) * (1 - black),
                                 (1 - yellow) * (1 - black))
    elif _GREY.search(said):
        grey = float(_GREY.search(said).group(1))
        out["text_color"] = _hex(grey, grey, grey)
    return out


def _hex(red: float, green: float, blue: float) -> str:
    return "#%02x%02x%02x" % tuple(
        int(round(max(0.0, min(1.0, part)) * 255)) for part in (red, green, blue))


def _common(source, annotation: dict) -> dict:
    """What the annotation says about itself, whoever it came from."""
    out: dict = {}
    for key, field in (("T", "author"), ("Contents", "comment"),
                       ("Subj", "subject")):
        said = _readable(source.resolve(annotation.get(key)))
        if said.strip():
            out[field] = said.strip()
    return out


def _readable(raw) -> str:
    """A PDF text string as words.

    PDF writes text either in its own single-byte encoding or in UTF-16 with a
    byte-order mark on the front, and Bluebeam writes UTF-16. The catch is
    that a reader may hand this back as a ``str`` it has already decoded one
    byte at a time — so the mark arrives as the two characters ``þÿ`` and the
    words come with a null between every letter. Left alone that is what puts
    ``þÿN␀O␀T␀E␀S`` on the page where NOTES belongs, so a string that arrives
    looking like that is put back to bytes and decoded properly.
    """
    if isinstance(raw, str):
        if not raw.startswith(("\xfe\xff", "\xff\xfe")):
            return raw
        try:
            raw = raw.encode("latin-1")
        except UnicodeEncodeError:
            return raw
    if not isinstance(raw, bytes):
        return ""
    if raw[:2] in (b"\xfe\xff", b"\xff\xfe"):
        try:
            return raw.decode("utf-16")
        except UnicodeDecodeError:
            return ""
    try:
        return raw.decode("latin-1")
    except UnicodeDecodeError:
        return ""


def _payload(kind: str, style: dict, common: dict) -> dict:
    payload = {"type": kind, "style": style, "uid": os.urandom(8).hex()}
    payload.update(common)
    return payload


def _shape(kind: str, shape: str, box: list, style: dict, common: dict) -> dict:
    payload = _payload(kind, style, common)
    payload.update({"kind": shape, "x": box[0], "y": box[1],
                    "rect": [0, 0, box[2], box[3]]})
    return payload


def _line(shape: str, points: list, style: dict, common: dict) -> dict:
    left = min(point[0] for point in points)
    top = min(point[1] for point in points)
    payload = _payload("poly", style, common)
    payload.update({"kind": shape, "x": left, "y": top,
                    "points": [[x - left, y - top] for x, y in points]})
    return payload


def _text(kind: str, box: list, style: dict, common: dict) -> dict:
    payload = _payload(kind, style, common)
    payload.update({"x": box[0], "y": box[1], "rect": [0, 0, box[2], box[3]],
                    "text": common.get("comment", "")})
    return payload


def _is_cloudy(source, annotation: dict) -> bool:
    """A cloudy border effect: what a PDF calls a revision cloud."""
    effect = source.resolve(annotation.get("BE"))
    return isinstance(effect, dict) and \
        str(source.resolve(effect.get("S")) or "") == "C"


# The PDF's ten line endings, and the arrow head each is drawn with here.
INCOMING_ENDINGS = {
    "None": "none", "ClosedArrow": "arrow", "OpenArrow": "open",
    "Circle": "dot", "Square": "square", "Diamond": "diamond",
    "Slash": "slash", "Butt": "none", "RClosedArrow": "arrow",
    "ROpenArrow": "open",
}


def _line_endings(source, annotation: dict, style: dict) -> None:
    """What was drawn on each end of the line it came from."""
    endings = source.resolve(annotation.get("LE"))
    if isinstance(endings, str):
        endings = [endings]
    if not isinstance(endings, (list, tuple)) or not endings:
        return
    names = [str(source.resolve(entry) or "") for entry in endings]
    if names:
        style["arrow_start"] = INCOMING_ENDINGS.get(names[0], "none")
    if len(names) > 1:
        style["arrow_end"] = INCOMING_ENDINGS.get(names[1], "none")


def _dimension(source, annotation: dict, points: list, style: dict,
               common: dict, scale: float) -> dict:
    """A line annotation that says it is a dimension comes back as one.

    Its leader length is the reach the dimension line stands off what it
    measures, and its caption offset is where the value was dragged to. Both
    had a name in the specification long before this application had one.
    """
    payload = _payload("measure", style, common)
    left = min(point[0] for point in points)
    top = min(point[1] for point in points)
    reach = source.resolve(annotation.get("LL"))
    offset = _numbers(source, annotation.get("CO"))
    payload.update({
        "kind": "dimension",
        "x": left, "y": top,
        "points": [[x - left, y - top] for x, y in points],
        "witness_reach": -float(reach) * scale
        if isinstance(reach, (int, float)) else 0.0,
        "custom_label": common.get("comment", ""),
    })
    if len(offset) >= 2:
        payload["label_offset"] = [offset[0] * scale, -offset[1] * scale]
    return payload


def _take_off(points: list, style: dict, common: dict, intent: str) -> dict:
    """A polygon or polyline that says it is a measurement."""
    payload = _payload("measure", style, common)
    left = min(point[0] for point in points)
    top = min(point[1] for point in points)
    payload.update({
        "kind": "area" if intent == "PolygonDimension" else "polylength",
        "x": left, "y": top,
        "points": [[x - left, y - top] for x, y in points],
    })
    return payload


def _free_text(source, annotation: dict, box: list, style: dict, common: dict,
               place, scale: float, intent: str) -> dict:
    """Words on the page — plain, typed straight on, or on a call-out.

    What makes it a call-out is the annotation saying so. A leader line on its
    own does not: ``/CL`` means nothing without ``/IT /FreeTextCallout`` to
    give it meaning, and writers leave one behind on plain text boxes — which
    is how every text box on a sheet arrives wearing a leader pointing at a
    corner of the page.
    """
    corners = _numbers(source, annotation.get("CL"))
    leader = [_at(place, corners[i], corners[i + 1], scale)
              for i in range(0, len(corners) - 1, 2)]
    kind = "text"
    if intent == "FreeTextTypeWriter":
        kind = "typewriter"
    elif intent == "FreeTextCallout":
        kind = "callout"
    payload = _text(kind, box, style, common)
    # Set the way the annotation says to set it, not the way this application
    # would have set it.
    payload["style"] = dict(payload.get("style") or {},
                            **_how_the_words_are_set(source, annotation, scale))
    if kind == "callout" and leader:
        # The leader's own end is where it points; the rest is worked out from
        # the box, the way every call-out here works out its hinge.
        tip = leader[0]
        payload["leaders"] = [{"tip": [tip[0] - box[0], tip[1] - box[1]]}]
    return payload


def _ink(source, annotation: dict, place, scale: float,
         style: dict, common: dict) -> list[dict]:
    lists = source.resolve(annotation.get("InkList"))
    if not isinstance(lists, (list, tuple)):
        return []
    made = []
    for run in lists:
        numbers = _numbers(source, run)
        points = [_at(place, numbers[i], numbers[i + 1], scale)
                  for i in range(0, len(numbers) - 1, 2)]
        if len(points) >= 2:
            made.append(_line("ink", points, dict(style), dict(common)))
    return made


def _appearance(source, annotation: dict, scale: float) -> list[dict]:
    """Whatever it draws, as one drawing that can be picked up and moved."""
    from . import pdfvector

    strokes = pdfvector.strokes_of_annotation(source, annotation)
    if not strokes:
        return []
    if scale != 1.0:
        strokes = _scaled(strokes, scale)
    payload = _payload("sketch", {"stroke": "", "fill": "", "width": 0.0},
                       _common(source, annotation))
    payload["strokes"] = strokes
    payload["x"] = 0.0
    payload["y"] = 0.0
    return [payload]


def _scaled(strokes: list, scale: float) -> list:
    out = []
    for stroke in strokes:
        moved = dict(stroke)
        moved["path"] = [[step[0]] + [value * scale for value in step[1:]]
                         for step in stroke.get("path") or []]
        moved["width"] = float(stroke.get("width", 0.6)) * scale
        out.append(moved)
    return out
