"""Read a Bluebeam tool set — a ``.btx`` file — into MarkForge tools.

An engineer's tool chest is years of work. Section shapes, weld symbols,
review stamps, hatched concrete: nobody rebuilds that by hand, so a tool set
that cannot be brought across is a reason not to move. This brings them
across.

**What is in the file.** A ``.btx`` is XML. Each tool is a ``ToolChestItem``
whose ``Raw`` field is a zlib-compressed, hex-encoded PDF *annotation
dictionary* — exactly what Bluebeam would write onto a page. A tool made of
several markups carries the rest as ``Child`` elements, each with the offset
it sits at. The picture on a stamp is not in the annotation at all: the
annotation points at ``BBObjPtr_SOMETHING``, and the drawing lives in a
``Resources`` block further down the file, as a PDF form XObject with a
FlateDecoded content stream.

**What comes out.** Ordinary MarkForge markups. A ``Square`` is a rectangle,
a ``Polygon`` a polygon, a ``FreeText`` a text box or a call-out, an ``Ink`` a
pen stroke. A stamp's drawing is read out of its content stream and becomes a
:class:`~markforge.items.shapes.SketchItem`, so a steel section arrives as the
drawing it is and can still be scaled, coloured and printed as vectors.

Nothing here needs a PDF library: what is being read is a handful of loose
objects, and :mod:`markforge.io.pdfobj` reads those.
"""
from __future__ import annotations

import binascii
import math
import re
import zlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from .pdfobj import operations, parse_dict

# Importing the markups registers them, so a payload read out of a tool set
# can always be built into an item — whatever else the caller has imported.
from .. import items  # noqa: F401

# PDF works in points, and so does the page here, so nothing is converted.
POINTER = re.compile(r"BBObjPtr_(\w+)")


class BtxError(Exception):
    """The file is not a tool set, or is damaged past reading."""


# ---------------------------------------------------------------------------
# unpacking
# ---------------------------------------------------------------------------

def unpack(text: Optional[str]) -> bytes:
    """A zlib-compressed, hex-encoded field, as bytes. Empty if unreadable."""
    if not text:
        return b""
    try:
        return zlib.decompress(binascii.unhexlify(text.strip()))
    except (binascii.Error, zlib.error, ValueError):
        return b""


def _text(blob: bytes) -> str:
    return blob.decode("utf-8", "replace") if blob else ""


# ---------------------------------------------------------------------------
# colours and geometry
# ---------------------------------------------------------------------------

def colour(components) -> str:
    """A PDF colour array as ``#rrggbb``. Empty when there is no colour.

    PDF says what colour space by how many numbers there are: one is grey,
    three RGB, four CMYK. An empty array is "no colour at all", which is how a
    shape says it is not filled — not the same as being filled with white.
    """
    if not isinstance(components, (list, tuple)) or not components:
        return ""
    try:
        values = [max(0.0, min(float(v), 1.0)) for v in components]
    except (TypeError, ValueError):
        return ""
    if len(values) == 1:
        red = green = blue = values[0]
    elif len(values) >= 4:
        cyan, magenta, yellow, black = values[:4]
        red = (1 - cyan) * (1 - black)
        green = (1 - magenta) * (1 - black)
        blue = (1 - yellow) * (1 - black)
    else:
        red, green, blue = (values + [0.0, 0.0])[:3]
    return "#{:02x}{:02x}{:02x}".format(round(red * 255), round(green * 255),
                                        round(blue * 255))


def _rect(values) -> tuple[float, float, float, float]:
    """A PDF ``Rect`` as (x, y, width, height), with the corners sorted."""
    try:
        x0, y0, x1, y1 = [float(v) for v in values[:4]]
    except (TypeError, ValueError):
        return 0.0, 0.0, 1.0, 1.0
    return (min(x0, x1), min(y0, y1), abs(x1 - x0) or 1.0, abs(y1 - y0) or 1.0)


def _turn(annotation: dict, box: tuple):
    """How far Bluebeam has turned this markup, as a function, or None.

    A rotated markup keeps the points it was first drawn with and records the
    turn in ``/Rotation`` — degrees *clockwise*, which is the way somebody
    dragging a rotate handle counts them and the opposite way round from
    every angle PDF itself uses. ``Rect`` is the box the turned shape fills,
    so the turn happens about the middle of that box: put the points through
    this and they land where the markup actually looks. Without it a section
    mark's arrowhead sat beside its bubble instead of on top of it; with it
    the wrong way round, the arrowhead pointed into the bubble.
    """
    try:
        degrees = float(annotation.get("Rotation", 0) or 0) % 360.0
    except (TypeError, ValueError):
        return None
    if not degrees:
        return None
    x, y, width, height = box
    middle_x, middle_y = x + width / 2.0, y + height / 2.0
    cosine = math.cos(math.radians(-degrees))
    sine = math.sin(math.radians(-degrees))

    def turned(point):
        across = float(point[0]) - middle_x
        up = float(point[1]) - middle_y
        return [middle_x + across * cosine - up * sine,
                middle_y + across * sine + up * cosine]
    return turned


def drawn_box(box, inset, width: float) -> list[float]:
    """The rectangle a square or circle is actually drawn in.

    Not ``Rect``. A shape annotation sits inside ``Rect`` less its ``/RD``,
    and the border is then kept inside *that* rather than straddling it — so
    the path itself is in by another half a border width, and the outside of
    the ink lands exactly on ``Rect`` less ``/RD``.

    That last half-width is the whole of this. A section mark's arrowhead is
    built so that the two corners of its base sit exactly on its bubble;
    drawing the bubble in the whole of ``Rect`` makes it a border width wider
    than its own file draws it, and the arrowhead ends up a point inside the
    circle it is supposed to touch. On a forty-point bubble that is plain to
    see, and it is wrong on every square and every circle on the sheet.
    """
    try:
        x, y, wide, high = (float(v) for v in box[:4])
    except (TypeError, ValueError):
        return list(box)
    edges = [0.0, 0.0, 0.0, 0.0]
    if isinstance(inset, (list, tuple)) and len(inset) >= 4:
        try:
            edges = [float(v) for v in inset[:4]]
        except (TypeError, ValueError):
            edges = [0.0, 0.0, 0.0, 0.0]
    half = max(float(width or 0.0), 0.0) / 2.0
    left, top, right, bottom = (edge + half for edge in edges)
    return [x + left, y + top,
            max(wide - left - right, 0.5), max(high - top - bottom, 0.5)]


ARROWS = {
    "OpenArrow": "arrow", "ClosedArrow": "arrow", "ROpenArrow": "arrow",
    "RClosedArrow": "arrow", "Diamond": "diamond", "RDiamond": "diamond",
    "Circle": "circle", "Square": "square", "Butt": "none", "Slash": "none",
    "None": "none",
}


def _style(annotation: dict) -> dict:
    """The look of a markup, from the annotation's colour and border keys."""
    border = annotation.get("BS") if isinstance(annotation.get("BS"), dict) else {}
    dash = border.get("D") or annotation.get("D")
    style = {
        "stroke": colour(annotation.get("C")),
        "fill": colour(annotation.get("IC")),
        "width": float(border.get("W", 1.0) or 0.0),
        "opacity": float(annotation.get("CA", 1.0) or 1.0),
        "fill_opacity": float(annotation.get("FillOpacity",
                                             annotation.get("CA", 1.0)) or 1.0),
        # The line type. A dashed line used to come in solid, because what was
        # set here was a key no markup has: the field is line_style, and the
        # dashes themselves are worth keeping so the line looks the way it was
        # drawn rather than merely "dashed".
        "line_style": "dash" if (border.get("S") == "D" or dash) else "solid",
    }
    if isinstance(dash, list) and dash:
        steps = [float(step) for step in dash
                 if isinstance(step, (int, float)) and float(step) > 0]
        if steps:
            style["dash_array"] = tuple(steps)
    if annotation.get("BM") == "Multiply":
        style["blend"] = "multiply"
    ends = annotation.get("LE")
    if isinstance(ends, list) and len(ends) >= 2:
        style["arrow_start"] = ARROWS.get(str(ends[0]), "none")
        style["arrow_end"] = ARROWS.get(str(ends[1]), "none")
    elif isinstance(ends, str):
        style["arrow_end"] = ARROWS.get(ends, "none")
    size = _font_size(annotation)
    if size:
        style["font_size"] = size
    style.update(_text_look(annotation))
    return style


# How a FreeText lines its words up, and in what colour. Bluebeam writes it in
# two places: /Q, which PDF has always had, and the CSS-ish /DS string, which
# is where the vertical alignment and the colour actually live. Ignoring them
# is why a section mark's "S1" sat in the top-left corner of its own box
# instead of in the middle of the circle it belongs to.
_ALIGN = {0: "left", 1: "center", 2: "right"}


def _text_look(annotation: dict) -> dict:
    if str(annotation.get("Subtype", "")) != "FreeText":
        return {}
    look: dict = {}
    quadding = annotation.get("Q")
    if isinstance(quadding, (int, float)):
        look["align"] = _ALIGN.get(int(quadding), "left")
    settings = annotation.get("DS")
    if isinstance(settings, str):
        across = re.search(r"text-align\s*:\s*(left|center|centre|right)", settings)
        if across:
            found = across.group(1)
            look["align"] = "center" if found in ("center", "centre") else found
        down = re.search(r"text-valign\s*:\s*(top|middle|center|bottom)", settings)
        if down:
            found = down.group(1)
            look["valign"] = "middle" if found in ("middle", "center") else found
        colour_text = re.search(r"color\s*:\s*(#[0-9A-Fa-f]{6})", settings)
        if colour_text:
            look["text_color"] = colour_text.group(1).lower()
        # The typeface, and how close to the edge of its box the words sit.
        # Both are what decide whether a title fits on one line: set in the
        # wrong face, at four points of padding instead of one, "DESCRIPTION
        # OF DRAWING" broke in half across the middle of the sheet.
        family = re.search(r"font(?:-family)?\s*:\s*(?:bold\s+|italic\s+)*"
                           r"([A-Za-z][\w \-]*?)\s*(?:[\d.]+pt)?\s*(?:;|$)",
                           settings)
        if family and family.group(1).strip():
            look["font_family"] = family.group(1).strip()
        margin = re.search(r"(?<!-)margin\s*:\s*([\d.]+)pt", settings)
        if margin:
            try:
                look["padding"] = float(margin.group(1))
            except ValueError:
                pass
        if re.search(r"font\s*:\s*[^;]*\bbold\b", settings):
            look["bold"] = True
        if re.search(r"font\s*:\s*[^;]*\bitalic\b", settings):
            look["italic"] = True
        if re.search(r"text-decoration\s*:\s*underline", settings):
            look["underline"] = True
    # /DA sets the colour the words are painted in: "1 0 0 rg" is red.
    appearance = annotation.get("DA")
    if isinstance(appearance, str) and "text_color" not in look:
        painted = re.search(r"([\d.]+(?:\s+[\d.]+){0,3})\s+(?:rg|g|k)\b", appearance)
        if painted:
            found = colour([float(v) for v in painted.group(1).split()])
            if found:
                look["text_color"] = found
    return look


def _font_size(annotation: dict) -> float:
    """The point size out of ``/DA`` (``/Helv 12 Tf``) or ``/DS``."""
    appearance = annotation.get("DA")
    if isinstance(appearance, str):
        match = re.search(r"/\S+\s+([\d.]+)\s+Tf", appearance)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
    settings = annotation.get("DS")
    if isinstance(settings, str):
        match = re.search(r"font-size\s*:\s*([\d.]+)", settings) or \
            re.search(r"font:[^;]*?([\d.]+)pt", settings)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
    return 0.0


def _pairs(flat) -> list[list[float]]:
    """A flat ``[x, y, x, y, …]`` array as a list of points."""
    numbers = []
    for value in flat or ():
        try:
            numbers.append(float(value))
        except (TypeError, ValueError):
            return []
    return [[numbers[i], numbers[i + 1]] for i in range(0, len(numbers) - 1, 2)]


def _html_text(annotation: dict) -> str:
    """What a text markup says: its rich text if it has any, else Contents."""
    rich = annotation.get("RC")
    if isinstance(rich, str) and rich.strip():
        # The rich text is XHTML. Only the words are wanted here — how they
        # are set comes across separately, in _rich_text.
        text = re.sub(r"<br\s*/?>", "\n", rich)
        text = re.sub(r"<p\b[^>]*/>", "\n", text)     # a blank line is a line
        text = re.sub(r"</p\s*>", "\n", text)
        text = re.sub(r"<[^>]+>", "", text)
        text = (text.replace("&lt;", "<").replace("&gt;", ">")
                    .replace("&amp;", "&").replace("&#39;", "'")
                    .replace("&quot;", '"').replace("&nbsp;", " "))
        text = re.sub(r"\n{3,}", "\n\n", text).strip("\n")
        if text.strip():
            return text
    contents = annotation.get("Contents")
    return contents if isinstance(contents, str) else ""


# ---------------------------------------------------------------------------
# how a text markup is set
# ---------------------------------------------------------------------------

# A legend's heading is underlined, a drawing title is bold and sixteen point
# over a plain twelve, and the blank line between two legend entries is what
# holds them apart. All of that is in the annotation's rich text, and dropping
# it left the words in a heap in the corner of the box. These carry it across.
_XHTML = "{http://www.w3.org/1999/xhtml}"

# What a text box here can actually show. Anything else Bluebeam writes —
# line-height, the several kinds of margin — is left behind rather than
# passed on to be misread.
_SHOWABLE = ("font-family", "font-size", "font-weight", "font-style",
             "text-decoration", "color", "text-align")

# "font: bold Helvetica 16pt", which is shorthand for three of the above.
_SHORTHAND = re.compile(r"^\s*(?:(bold|normal)\s+)?(?:(italic|normal)\s+)?"
                        r"(.*?)\s*([\d.]+)pt\s*$")


def _showable(declarations: str) -> str:
    """The parts of a style Qt's rich text understands, as a style string."""
    parts = []
    for piece in (declarations or "").split(";"):
        name, colon, value = piece.partition(":")
        name, value = name.strip().lower(), value.strip()
        if not colon or not value:
            continue
        if name == "font-size":
            parts.append(f"font-size:{_points(value)}")
        elif name in _SHOWABLE:
            parts.append(f"{name}:{value}")
        elif name == "font":
            parts.extend(_shorthand(value))
    return ";".join(parts)


def _points(size: str) -> str:
    """A type size in the units the page is measured in.

    A scene unit here *is* a PDF point, but Qt's rich text reads ``pt``
    against the screen's resolution and makes it a third bigger again. Saying
    ``px`` instead is what keeps sixteen point sixteen points — and what
    keeps a drawing title on the one line it was set on.
    """
    match = re.match(r"^\s*([\d.]+)\s*(pt|px)?\s*$", size)
    return f"{match.group(1)}px" if match else size


def _shorthand(value: str) -> list[str]:
    match = _SHORTHAND.match(value)
    if not match:
        return []
    weight, slant, family, size = match.groups()
    parts = [f"font-size:{size}px"]
    if family:
        parts.append(f"font-family:{family}")
    if weight:
        parts.append(f"font-weight:{weight}")
    if slant:
        parts.append(f"font-style:{slant}")
    return parts


def _plain_tag(tag) -> str:
    return str(tag).replace(_XHTML, "").lower()


def _escaped(text) -> str:
    return (str(text or "").replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def _inline(node) -> str:
    """One element's words, with the runs inside it kept as they are set."""
    out = _escaped(node.text)
    for child in node:
        if _plain_tag(child.tag) == "br":
            out += "<br/>"
        else:
            inside = _inline(child)
            style = _showable(child.get("style", ""))
            out += f'<span style="{style}">{inside}</span>' if style else inside
        out += _escaped(child.tail)
    return out


def _rich_text(annotation: dict) -> str:
    """A text markup's rich text as HTML, or "" when it has none worth having.

    Bluebeam's paragraph margins are its own; they are dropped and replaced
    with none, because a text box here holds the spacing itself and adding
    both would open every line up twice over.
    """
    rich = annotation.get("RC")
    if not isinstance(rich, str) or "<" not in rich:
        return ""
    try:
        body = ET.fromstring(rich)
    except ET.ParseError:
        return ""
    paragraphs = []
    anything = False
    for node in body.iter():
        if _plain_tag(node.tag) != "p":
            continue
        words = _inline(node).strip()
        anything = anything or bool(words)
        style = _showable(node.get("style", ""))
        style = f"{style};margin:0px" if style else "margin:0px"
        # An empty paragraph is a blank line, and a blank line with nothing in
        # it is no line at all: the space is what keeps two legend entries
        # apart from each other.
        paragraphs.append(f'<p style="{style}">{words or "&nbsp;"}</p>')
    if not anything:
        return ""
    outer = _showable(body.get("style", ""))
    return (f'<body style="{outer}">' if outer else "<body>") + \
        "".join(paragraphs) + "</body>"


# ---------------------------------------------------------------------------
# one annotation -> one markup
# ---------------------------------------------------------------------------

def markup_from(annotation: dict, resources: dict, name: str = "") -> Optional[dict]:
    """One PDF annotation as a MarkForge markup payload, or None if unknown."""
    subtype = str(annotation.get("Subtype", ""))
    x, y, width, height = _rect(annotation.get("Rect", []))
    style = _style(annotation)
    label = name or (annotation.get("Subj") if isinstance(annotation.get("Subj"), str) else "")
    common = {"x": 0.0, "y": 0.0, "style": style, "label": label,
              "subject": label}

    # A markup that has been turned keeps the points it was drawn with and
    # says so in /Rotation, so the turn has to be put back before anything
    # else is read. Doing it here, inside flip, is what keeps every shape
    # below reading as though it had been drawn the way it now looks.
    turn = _turn(annotation, (x, y, width, height))

    # PDF measures up the page and this measures down it, so every y is
    # turned over inside the annotation's own box. Doing it here, once, is
    # what keeps every shape below reading as though it were drawn normally.
    def flip(point) -> list[float]:
        if turn is not None:
            point = turn(point)
        return [point[0] - x, (y + height) - point[1]]

    if subtype in ("Square", "Circle"):
        inside = drawn_box([0.0, 0.0, width, height], annotation.get("RD"),
                           style.get("width", 0.0))
        return dict(common, type="rect",
                    kind="ellipse" if subtype == "Circle" else "rect",
                    rect=inside)
    if subtype == "Line":
        points = _pairs(annotation.get("L"))
        if len(points) < 2:
            return None
        kind = "arrow" if style.get("arrow_end", "none") != "none" else "line"
        return dict(common, type="poly", kind=kind,
                    points=[flip(p) for p in points])
    if subtype in ("PolyLine", "Polygon"):
        points = _pairs(annotation.get("Vertices"))
        if len(points) < 2:
            return None
        kind = "polygon" if subtype == "Polygon" else "polyline"
        payload = dict(common, type="poly", kind=kind,
                       points=[flip(p) for p in points])
        pattern = annotation.get("PatternName")
        if isinstance(pattern, str) and pattern:
            # A hatched section: the pattern is part of the look, so it goes
            # on the style where it can be drawn, changed and kept.
            payload["style"] = dict(style, hatch=pattern,
                                    fill=colour(annotation.get("PatternColor"))
                                    or style.get("fill", ""))
        return payload
    if subtype == "Ink":
        strokes = annotation.get("InkList") or []
        points = []
        for stroke in strokes if isinstance(strokes, list) else []:
            points.extend(_pairs(stroke))
        if len(points) < 2:
            return None
        kind = "highlighter" if style.get("blend") == "multiply" else "ink"
        return dict(common, type="poly", kind=kind,
                    points=[flip(p) for p in points])
    if subtype == "FreeText":
        words = _html_text(annotation)
        leader = _pairs(annotation.get("CL"))
        inset = annotation.get("RD") if isinstance(annotation.get("RD"), list) else None
        box = [0.0, 0.0, width, height]
        if inset and len(inset) >= 4:
            try:
                left, top, right, bottom = [float(v) for v in inset[:4]]
                box = [left, top, max(width - left - right, 8.0),
                       max(height - top - bottom, 8.0)]
            except (TypeError, ValueError):
                pass
        set_out = _rich_text(annotation)
        made = dict(common, text=words, rect=box)
        if set_out:
            made["html"] = set_out
        if leader:
            return dict(made, type="callout", leader=[flip(leader[0])])
        return dict(made, type="text")
    if subtype == "Stamp":
        strokes = _stamp_strokes(annotation, resources)
        if strokes:
            return dict(common, type="sketch", strokes=strokes,
                        rect=[0, 0, width, height],
                        source_box=[0, 0, width, height])
        words = _html_text(annotation)
        if words:
            return dict(common, type="text", text=words,
                        rect=[0, 0, width, height])
    return None


# ---------------------------------------------------------------------------
# a stamp's drawing
# ---------------------------------------------------------------------------

def _stream_of(blob: bytes) -> bytes:
    """The content of a PDF stream object, decompressed if it needs to be."""
    start = blob.find(b"stream")
    if start < 0:
        return b""
    start += len(b"stream")
    if blob[start:start + 2] == b"\r\n":
        start += 2
    elif blob[start:start + 1] in (b"\n", b"\r"):
        start += 1
    end = blob.rfind(b"endstream")
    body = blob[start:end if end > start else len(blob)]
    header = parse_dict(blob[:blob.find(b"stream")])
    filters = header.get("Filter")
    filters = filters if isinstance(filters, list) else ([filters] if filters else [])
    for name in filters:
        if str(name) in ("FlateDecode", "Fl"):
            try:
                body = zlib.decompress(body)
            except zlib.error:
                try:                     # a stream with a stray trailing byte
                    body = zlib.decompressobj().decompress(body)
                except zlib.error:
                    return b""
    return body


def _stamp_strokes(annotation: dict, resources: dict) -> list[dict]:
    """The drawing on a stamp, as strokes, or an empty list if there is none."""
    appearance = annotation.get("AP")
    pointer = appearance.get("N") if isinstance(appearance, dict) else None
    match = POINTER.search(str(pointer or ""))
    blob = resources.get(match.group(1)) if match else None
    if not blob:
        return []
    header = parse_dict(blob[:blob.find(b"stream")] or blob)
    stream = _stream_of(blob)
    if not stream:
        return []
    x, y, width, height = _rect(annotation.get("Rect", []))
    strokes = read_content(stream, matrix=header.get("Matrix"),
                           box=header.get("BBox"))
    # Turn the drawing over, as with every other markup, and put it in the
    # annotation's own box rather than wherever on the page it was drawn.
    return _flip_strokes(strokes, height)


def _flip_strokes(strokes: list[dict], height: float) -> list[dict]:
    out = []
    for stroke in strokes:
        path = []
        for command in stroke["path"]:
            op = command[0]
            values = list(command[1:])
            for index in range(1, len(values), 2):
                values[index] = height - values[index]
            path.append([op] + values)
        out.append(dict(stroke, path=path))
    return out


# The path-drawing operators of a PDF content stream. Everything else — text,
# shading, images — is ignored: a section drawing is paths, and a partial
# drawing of the paths that are there beats no drawing at all.
def read_content(stream: bytes, matrix=None, box=None) -> list[dict]:
    """A PDF content stream as a list of strokes.

    Each stroke is ``{"path": [[op, …]], "stroke": "#rrggbb", "fill": …,
    "width": float}``, in the coordinates the stream draws in, after the form's
    own ``Matrix`` is applied.
    """
    state = _State()
    stack: list[_State] = []
    strokes: list[dict] = []
    path: list[list] = []
    start = [0.0, 0.0]
    here = [0.0, 0.0]
    pending_clip = False

    base = _matrix(matrix) if matrix else (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    state.ctm = base

    for operands, operator in operations(stream):
        numbers = [v for v in operands if isinstance(v, (int, float))]
        if operator == "q":
            stack.append(state.copy())
        elif operator == "Q":
            state = stack.pop() if stack else state
        elif operator == "cm" and len(numbers) >= 6:
            state.ctm = _multiply(tuple(float(v) for v in numbers[:6]), state.ctm)
        elif operator == "w" and numbers:
            state.width = float(numbers[0])
        elif operator in ("g", "rg", "k", "sc", "scn") and numbers:
            state.fill = colour(numbers)
        elif operator in ("G", "RG", "K", "SC", "SCN") and numbers:
            state.stroke = colour(numbers)
        elif operator == "gs":
            pass                          # graphics state: nothing here reads it
        elif operator == "m" and len(numbers) >= 2:
            here = start = _apply(state.ctm, numbers[0], numbers[1])
            path.append(["m"] + here)
        elif operator == "l" and len(numbers) >= 2:
            here = _apply(state.ctm, numbers[0], numbers[1])
            path.append(["l"] + here)
        elif operator == "c" and len(numbers) >= 6:
            one = _apply(state.ctm, numbers[0], numbers[1])
            two = _apply(state.ctm, numbers[2], numbers[3])
            here = _apply(state.ctm, numbers[4], numbers[5])
            path.append(["c"] + one + two + here)
        elif operator == "v" and len(numbers) >= 4:
            two = _apply(state.ctm, numbers[0], numbers[1])
            end = _apply(state.ctm, numbers[2], numbers[3])
            path.append(["c"] + here + two + end)
            here = end
        elif operator == "y" and len(numbers) >= 4:
            one = _apply(state.ctm, numbers[0], numbers[1])
            end = _apply(state.ctm, numbers[2], numbers[3])
            path.append(["c"] + one + end + end)
            here = end
        elif operator == "re" and len(numbers) >= 4:
            left, bottom, wide, high = [float(v) for v in numbers[:4]]
            corners = [(left, bottom), (left + wide, bottom),
                       (left + wide, bottom + high), (left, bottom + high)]
            path.append(["m"] + _apply(state.ctm, *corners[0]))
            for corner in corners[1:]:
                path.append(["l"] + _apply(state.ctm, *corner))
            path.append(["z"])
            here = start = _apply(state.ctm, *corners[0])
        elif operator == "h":
            path.append(["z"])
            here = list(start)
        elif operator in ("W", "W*"):
            pending_clip = True
        elif operator in ("S", "s", "f", "F", "f*", "B", "B*", "b", "b*", "n"):
            if operator in ("s", "b", "b*"):
                path.append(["z"])
            if path and not pending_clip:
                filled = operator[0] in ("f", "F", "B", "b")
                outlined = operator[0] in ("S", "s", "B", "b")
                if operator in ("f", "F", "f*", "B", "B*", "b", "b*"):
                    path = path + ([["z"]] if path[-1][0] != "z" else [])
                strokes.append({
                    "path": path,
                    "stroke": state.stroke if outlined else "",
                    "fill": state.fill if filled else "",
                    "width": max(state.width * _scale(state.ctm), 0.05),
                })
            path = []
            pending_clip = False
    return strokes


@dataclass
class _State:
    """The bit of PDF's graphics state a path needs: colours, width, matrix."""

    stroke: str = "#000000"
    fill: str = "#000000"
    width: float = 1.0
    ctm: tuple = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

    def copy(self) -> "_State":
        return _State(self.stroke, self.fill, self.width, self.ctm)


def _matrix(values) -> tuple:
    try:
        numbers = [float(v) for v in values[:6]]
    except (TypeError, ValueError, IndexError):
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    return tuple(numbers) if len(numbers) == 6 else (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _multiply(first: tuple, second: tuple) -> tuple:
    """*first* applied, then *second* — PDF's own order for ``cm``."""
    a, b, c, d, e, f = first
    A, B, C, D, E, F = second
    return (a * A + b * C, a * B + b * D,
            c * A + d * C, c * B + d * D,
            e * A + f * C + E, e * B + f * D + F)


def _apply(matrix: tuple, x, y) -> list[float]:
    a, b, c, d, e, f = matrix
    x, y = float(x), float(y)
    return [a * x + c * y + e, b * x + d * y + f]


def _scale(matrix: tuple) -> float:
    """How much the matrix magnifies, so a pen width comes out right."""
    a, b, c, d = matrix[:4]
    return math.sqrt(abs(a * d - b * c)) or 1.0


# ---------------------------------------------------------------------------
# the file
# ---------------------------------------------------------------------------

@dataclass
class Tool:
    """One entry in an imported tool chest."""

    name: str
    payloads: list[dict] = field(default_factory=list)

    @property
    def is_group(self) -> bool:
        return len(self.payloads) > 1


@dataclass
class ToolSet:
    name: str
    tools: list[Tool] = field(default_factory=list)
    skipped: int = 0                     # tools nothing here could represent


def read(path) -> ToolSet:
    """Read a ``.btx`` file into a tool set."""
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise BtxError(str(exc)) from exc
    return loads(raw, Path(path).stem)


def loads(raw: bytes, fallback: str = "Imported") -> ToolSet:
    """Read the bytes of a ``.btx`` file into a tool set."""
    text = raw.decode("utf-8-sig", "replace")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise BtxError(f"not a tool set file: {exc}") from exc
    if root.tag != "BluebeamRevuToolSet":
        raise BtxError("not a Bluebeam tool set")

    resources = {}
    for block in root.iter("Resources"):
        key = _text(unpack(block.findtext("ID")))
        data = unpack(block.findtext("Data"))
        if key and data:
            resources[key] = data

    name = _text(unpack(root.findtext("Title"))) or fallback
    tools: list[Tool] = []
    skipped = 0
    for element in root.findall("ToolChestItem"):
        tool = _tool_from(element, resources)
        if tool is None:
            skipped += 1
            continue
        tools.append(tool)
    return ToolSet(name=name, tools=tools, skipped=skipped)


def _tool_from(element, resources: dict) -> Optional[Tool]:
    """One ToolChestItem, with everything nested under it, as one tool."""
    payloads: list[dict] = []
    label = ""
    group_name = ""
    parts = list(_parts(element))
    nesting = group_paths([annotation for _x, _y, annotation in parts])
    for offset_x, offset_y, annotation in parts:
        payload = markup_from(annotation, resources)
        if payload is None:
            continue
        path = nesting.get(_own_name(annotation), ())
        if path:
            payload["group_path"] = list(path)
        # Where each part of a tool sits. X and Y say how far the tool's own
        # anchor is *from* this annotation's bottom-left corner, so they go on
        # the other way round: a part with X of -27 sits 27 points to the
        # right, not to the left. Reading the sign the other way put a section
        # mark's cut line ten points clear of the bubble it belongs to and
        # threw the arrowhead off the far side altogether.
        #
        # Y needs no such turn: it is negated once for being an offset from
        # the annotation, and again for PDF measuring up the page while this
        # measures down it. What is left is the top edge, a height above the
        # bottom-left corner PDF gave.
        _x, _y, _w, height = _rect(annotation.get("Rect", []))
        payload["x"] = float(payload.get("x", 0.0)) - offset_x
        payload["y"] = float(payload.get("y", 0.0)) + offset_y - height
        if not label:
            label = payload.get("label", "")
        group_name = group_name or _group_name(annotation)
        payloads.append(payload)
    # A grouped tool's own name is the one in GroupNesting: the parent markup
    # is only ever called "Rectangle" or "Line", while the group is called
    # "Timber Post 200x200", which is what somebody would go looking for.
    label = group_name or label
    if not payloads:
        return None
    if len(payloads) > 1:
        # Members of one tool travel together, the way a grouped markup does —
        # and in the arrangement of groups Bluebeam had them in, where it said
        # so. A part the file grouped with nothing still belongs to the tool,
        # so it goes in the tool's own outermost group with the rest.
        outermost = next((p["group_path"][0] for p in payloads
                          if p.get("group_path")), "btx")
        for payload in payloads:
            path = list(payload.get("group_path") or [])
            if not path or path[0] != outermost:
                path = [outermost] + [step for step in path if step != outermost]
            payload["group_path"] = path
            payload["group"] = path[0]
    return Tool(name=label or "Tool", payloads=payloads)


# ---------------------------------------------------------------------------
# groups, and groups inside groups
# ---------------------------------------------------------------------------
#
# Bluebeam keeps a group as one *leader* annotation carrying the names of its
# members, with every member pointing back at the leader through ``/IRT``. A
# group inside a group is the inner leader pointing at the outer one, so the
# whole tree is in those pointers — and a section mark whose bubble and label
# are a group of their own, inside the group that adds the cut line, only
# comes back as the one thing it is if the pointers are followed all the way
# up. Flattening them loses which parts belong together, so taking the mark
# apart takes the whole thing apart instead of the piece somebody meant.

def _own_name(annotation: dict) -> str:
    """What this annotation calls itself, if it says."""
    for key in ("NM", "TempNameID", "TempGroupNestingName"):
        found = annotation.get(key)
        if isinstance(found, str) and found.strip():
            return str(found)
    return ""


def _leads_a_group(annotation: dict) -> bool:
    for key in ("GroupNesting", "TempGroupNesting"):
        if isinstance(annotation.get(key), list):
            return True
    return False


def _its_leader(annotation: dict) -> str:
    """The group this annotation is in, by the name of the one that leads it."""
    for key in ("IRT", "TempIRT"):
        found = annotation.get(key)
        if isinstance(found, str) and found.strip():
            return str(found)
    return ""


def group_paths(annotations: list) -> dict[str, tuple]:
    """For each annotation, the groups it is inside — outermost first.

    Keyed by what each annotation calls itself. A leader is in its own group
    as well as leading it, so its path ends with its own name, which is what
    puts it in the same group as the members it leads.
    """
    leader_of = {}
    for annotation in annotations:
        name = _own_name(annotation)
        if name:
            leader_of[name] = _its_leader(annotation)
    paths: dict[str, tuple] = {}
    for annotation in annotations:
        name = _own_name(annotation)
        if not name:
            continue
        at = name if _leads_a_group(annotation) else _its_leader(annotation)
        chain: list[str] = []
        seen = set()
        while at and at not in seen:
            seen.add(at)
            chain.append(at)
            at = leader_of.get(at, "")
        paths[name] = tuple(reversed(chain))
    return paths


def _group_name(annotation: dict) -> str:
    """The name Bluebeam gives the group a markup belongs to, if it is in one."""
    for key in ("GroupNesting", "TempGroupNesting"):
        nesting = annotation.get(key)
        if isinstance(nesting, list) and nesting and isinstance(nesting[0], str):
            name = nesting[0].strip()
            # The names inside are opaque ids; only the first is a real name,
            # and only when it reads as one rather than as another id.
            if name and not (name.isupper() and name.isalpha() and len(name) > 12):
                return name
    return ""


def _parts(element) -> Iterable[tuple[float, float, dict]]:
    """Every annotation in a tool chest item, with where it sits."""
    for node in [element] + list(element.findall("Child")):
        annotation = parse_dict(unpack(node.findtext("Raw")))
        if not annotation:
            continue
        yield _number(node.findtext("X")), _number(node.findtext("Y")), annotation


def _number(text: Optional[str]) -> float:
    try:
        return float(text)
    except (TypeError, ValueError):
        return 0.0
