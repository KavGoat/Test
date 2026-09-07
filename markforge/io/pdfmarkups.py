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
"""
from __future__ import annotations

import os
from typing import Optional

# Annotations that are not somebody's markup and should not become one.
NOT_MARKUP = {"Link", "Popup", "Widget", "FileAttachment", "Movie", "Screen",
              "PrinterMark", "TrapNet", "Watermark", "3D", "Projection"}

# How many annotations are worth bringing across from one page. A page with
# more than this on it is not a marked-up drawing, it is a data dump.
MOST_MARKUPS = 3000


def markups_of_page(source, page: dict, flip: tuple,
                    scale: float = 1.0) -> list[dict]:
    """Every annotation on one page, as markup payloads in page coordinates."""
    from .btx import colour

    found: list[dict] = []
    for entry in source.resolve(page.get("Annots")) or []:
        annotation = source.resolve(entry)
        if not isinstance(annotation, dict):
            continue
        kind = str(annotation.get("Subtype") or "")
        if kind in NOT_MARKUP:
            continue
        try:
            made = _one(source, annotation, kind, flip, scale, colour)
        except Exception:                              # noqa: BLE001
            made = None
        if made:
            found.extend(made)
        if len(found) >= MOST_MARKUPS:
            break
    return found


def _one(source, annotation: dict, kind: str, flip: tuple, scale: float,
         colour) -> list[dict]:
    """One annotation, as the markup it is."""
    box = _box(source, annotation, flip, scale)
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
        return [_free_text(source, annotation, box, style, common, flip,
                           scale, intent)]
    if kind == "Line":
        ends = _numbers(source, annotation.get("L"))
        if len(ends) >= 4:
            points = [_at(flip, ends[0], ends[1], scale),
                      _at(flip, ends[2], ends[3], scale)]
            _line_endings(source, annotation, style)
            if intent == "LineDimension":
                return [_dimension(source, annotation, points, style, common,
                                   scale)]
            style.setdefault("arrow_end", "arrow")
            return [_line("line", points, style, common)]
    if kind in ("PolyLine", "Polygon"):
        corners = _numbers(source, annotation.get("Vertices"))
        points = [_at(flip, corners[i], corners[i + 1], scale)
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
        return _ink(source, annotation, flip, scale, style, common)
    if kind in ("Highlight", "StrikeOut", "Underline", "Squiggly"):
        style = dict(style)
        style["fill"] = style.get("stroke") or "#ffe066"
        style["stroke"] = ""
        style["fill_opacity"] = 0.5
        return [_shape("rect", "highlight", box, style, common)]
    if kind == "FreeText":
        return [_text("text", box, style, common)]
    if kind == "Text":
        return [_text("note", box, style, common)]
    drawn = _appearance(source, annotation, flip, scale)
    if drawn:
        return drawn
    return []


# -- the pieces ------------------------------------------------------------
def _at(flip: tuple, x, y, scale: float) -> list[float]:
    a, b, c, d, e, f = flip
    x, y = float(x), float(y)
    return [(a * x + c * y + e) * scale, (b * x + d * y + f) * scale]


def _numbers(source, value) -> list[float]:
    values = source.resolve(value)
    if not isinstance(values, (list, tuple)):
        return []
    out = []
    for item in values:
        found = source.resolve(item)
        if isinstance(found, (int, float)):
            out.append(float(found))
    return out


def _box(source, annotation: dict, flip: tuple, scale: float) -> list[float]:
    """The annotation's rectangle, in page coordinates: [x, y, w, h]."""
    rect = _numbers(source, annotation.get("Rect"))
    if len(rect) != 4:
        return [0.0, 0.0, 1.0, 1.0]
    one = _at(flip, rect[0], rect[1], scale)
    two = _at(flip, rect[2], rect[3], scale)
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


def _common(source, annotation: dict) -> dict:
    """What the annotation says about itself, whoever it came from."""
    out = {"layer": "Markups"}
    for key, field in (("T", "author"), ("Contents", "comment"),
                       ("Subj", "subject")):
        said = source.resolve(annotation.get(key))
        if isinstance(said, bytes):
            said = _readable(said)
        if isinstance(said, str) and said.strip():
            out[field] = said.strip()
    return out


def _readable(raw: bytes) -> str:
    """A PDF text string, which may be UTF-16 with a mark on the front."""
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
    return isinstance(effect, dict) and str(effect.get("S") or "") == "C"


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
               flip: tuple, scale: float, intent: str) -> dict:
    """Words on the page — plain, typed straight on, or on a call-out."""
    corners = _numbers(source, annotation.get("CL"))
    leader = [_at(flip, corners[i], corners[i + 1], scale)
              for i in range(0, len(corners) - 1, 2)]
    kind = "text"
    if intent == "FreeTextTypeWriter":
        kind = "typewriter"
    elif intent == "FreeTextCallout" or len(leader) >= 2:
        kind = "callout"
    payload = _text(kind, box, style, common)
    if kind == "callout" and leader:
        # The leader's own end is where it points; the rest is worked out from
        # the box, the way every call-out here works out its hinge.
        tip = leader[0]
        payload["leaders"] = [{"tip": [tip[0] - box[0], tip[1] - box[1]]}]
    return payload


def _ink(source, annotation: dict, flip: tuple, scale: float,
         style: dict, common: dict) -> list[dict]:
    lists = source.resolve(annotation.get("InkList"))
    if not isinstance(lists, (list, tuple)):
        return []
    made = []
    for run in lists:
        numbers = _numbers(source, run)
        points = [_at(flip, numbers[i], numbers[i + 1], scale)
                  for i in range(0, len(numbers) - 1, 2)]
        if len(points) >= 2:
            made.append(_line("ink", points, dict(style), dict(common)))
    return made


def _appearance(source, annotation: dict, flip: tuple, scale: float) -> list[dict]:
    """Whatever it draws, as one drawing that can be picked up and moved."""
    from . import pdfvector

    strokes = pdfvector.strokes_of_annotation(source, annotation, flip)
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
