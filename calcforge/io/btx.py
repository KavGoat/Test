"""Read a Bluebeam tool set — a ``.btx`` file — into CalcForge tools.

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

**What comes out.** Ordinary CalcForge markups. A ``Square`` is a rectangle,
a ``Polygon`` a polygon, a ``FreeText`` a text box or a call-out, an ``Ink`` a
pen stroke. A stamp's drawing is read out of its content stream and becomes a
:class:`~calcforge.items.shapes.SketchItem`, so a steel section arrives as the
drawing it is and can still be scaled, coloured and printed as vectors.

Nothing here needs a PDF library: what is being read is a handful of loose
objects, and :mod:`calcforge.io.pdfobj` reads those.
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
        "dash": "dash" if (border.get("S") == "D" or dash) else "solid",
    }
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
    return style


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
        # The rich text is XHTML. The words are what matter; a text box here
        # holds its own formatting, and carrying Bluebeam's markup across
        # would only bring its <span style=…> with it.
        text = re.sub(r"<br\s*/?>", "\n", rich)
        text = re.sub(r"</p\s*>", "\n", text)
        text = re.sub(r"<[^>]+>", "", text)
        text = (text.replace("&lt;", "<").replace("&gt;", ">")
                    .replace("&amp;", "&").replace("&#39;", "'")
                    .replace("&quot;", '"').replace("&nbsp;", " "))
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if text:
            return text
    contents = annotation.get("Contents")
    return contents if isinstance(contents, str) else ""


# ---------------------------------------------------------------------------
# one annotation -> one markup
# ---------------------------------------------------------------------------

def markup_from(annotation: dict, resources: dict, name: str = "") -> Optional[dict]:
    """One PDF annotation as a CalcForge markup payload, or None if unknown."""
    subtype = str(annotation.get("Subtype", ""))
    x, y, width, height = _rect(annotation.get("Rect", []))
    style = _style(annotation)
    label = name or (annotation.get("Subj") if isinstance(annotation.get("Subj"), str) else "")
    common = {"x": 0.0, "y": 0.0, "style": style, "label": label,
              "subject": label}

    # PDF measures up the page and this measures down it, so every y is
    # turned over inside the annotation's own box. Doing it here, once, is
    # what keeps every shape below reading as though it were drawn normally.
    def flip(point) -> list[float]:
        return [point[0] - x, (y + height) - point[1]]

    if subtype == "Square":
        return dict(common, type="rect", kind="rect",
                    rect=[0, 0, width, height])
    if subtype == "Circle":
        return dict(common, type="rect", kind="ellipse",
                    rect=[0, 0, width, height])
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
            payload["style"] = dict(style,
                                    fill=colour(annotation.get("PatternColor")))
            payload["hatch"] = pattern
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
        if leader:
            return dict(common, type="callout", text=words, rect=box,
                        leader=[flip(leader[0])])
        return dict(common, type="text", text=words, rect=box)
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
    for offset_x, offset_y, annotation in _parts(element):
        payload = markup_from(annotation, resources)
        if payload is None:
            continue
        payload["x"] = float(payload.get("x", 0.0)) + offset_x
        payload["y"] = float(payload.get("y", 0.0)) - offset_y
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
        # Members of one tool travel together, the way a grouped markup does.
        for payload in payloads:
            payload["group"] = "btx"
    return Tool(name=label or "Tool", payloads=payloads)


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
