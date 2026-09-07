"""The annotations a PDF can hold, read and written as what they are.

Modelled on PDF4QT's annotation model, which is written straight from the
specification. The point of having it is fidelity in both directions: a cloud
read out of somebody's drawing comes back a cloud, and a cloud written into one
goes in as a square with a cloudy border rather than as a picture of a cloud
that happens to be movable.

Everything here is data. Drawing is the application's business and appearance
streams are written beside these, not instead of them — a reader that
understands the annotation gets to edit it, and one that does not still sees
what it looks like.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .objects import Name, Ref, as_name, as_numbers, as_text

# The annotations that are somebody's markup, as against the file's own
# furniture. A link is not a markup and neither is a form field.
NOT_MARKUP = {"Link", "Popup", "Widget", "FileAttachment", "Movie", "Screen",
              "PrinterMark", "TrapNet", "Watermark", "3D", "Projection"}

#: How the ten line endings are named, and what each is drawn as here.
LINE_ENDINGS = {
    "None": "none", "Square": "square", "Circle": "dot", "Diamond": "diamond",
    "OpenArrow": "open", "ClosedArrow": "arrow", "Butt": "none",
    "ROpenArrow": "open", "RClosedArrow": "arrow", "Slash": "slash",
}
ENDING_NAMES = {"none": "None", "arrow": "ClosedArrow", "open": "OpenArrow",
                "dot": "Circle", "square": "Square", "diamond": "Diamond",
                "slash": "Slash", "half": "OpenArrow"}


@dataclass
class BorderEffect:
    """``/BE`` — the only two there are: nothing, or a cloud.

    A revision cloud in a PDF is not a shape drawn as scallops. It is a square
    or a polygon that says its border is cloudy and how pronounced to make it,
    and the reader draws the scallops. Written that way it stays adjustable.
    """

    cloudy: bool = False
    intensity: float = 0.0

    @classmethod
    def read(cls, storage, value: Any) -> "BorderEffect":
        found = storage.resolve(value)
        if not isinstance(found, dict):
            return cls()
        if as_name(storage.resolve(found.get("S"))) != "C":
            return cls()
        return cls(True, storage.number(found, "I", 1.0))

    def write(self) -> Optional[dict]:
        if not self.cloudy:
            return None
        return {"S": Name("C"), "I": int(max(1.0, min(self.intensity or 2.0, 2.0)))}


@dataclass
class CalloutLine:
    """``/CL`` — where a call-out points, its knee, and where the words are.

    Two points when the leader runs straight, three when it has a hinge, and
    the end that points at something comes first. The three-point form is
    exactly the leader a call-out is drawn with.
    """

    points: list[tuple[float, float]] = field(default_factory=list)

    @property
    def hinged(self) -> bool:
        return len(self.points) >= 3

    @classmethod
    def read(cls, storage, value: Any) -> "CalloutLine":
        numbers = as_numbers([storage.resolve(item)
                              for item in (storage.resolve(value) or [])])
        return cls([(numbers[i], numbers[i + 1])
                    for i in range(0, len(numbers) - 1, 2)])

    def write(self) -> Optional[list]:
        if len(self.points) < 2:
            return None
        return [value for point in self.points for value in point]


@dataclass
class Measure:
    """``/Measure`` — what the page is a drawing of.

    Without one, a measurement is a line with a number written next to it and
    the number means nothing to anybody else's reader. With one, the scale
    travels: another editor measures the same drawing and agrees.
    """

    ratio: str = ""
    unit: str = "mm"
    per_point: float = 1.0

    @classmethod
    def read(cls, storage, value: Any) -> Optional["Measure"]:
        found = storage.resolve(value)
        if not isinstance(found, dict):
            return None
        numbers = storage.resolve(found.get("X")) or storage.resolve(found.get("D"))
        first = storage.resolve(numbers[0]) if isinstance(numbers, list) and numbers else None
        if not isinstance(first, dict):
            return None
        return cls(ratio=as_text(storage.resolve(found.get("R"))),
                   unit=as_text(storage.resolve(first.get("U"))) or "mm",
                   per_point=storage.number(first, "C", 1.0))

    def write(self) -> dict:
        numbers = {
            "Type": Name("NumberFormat"),
            "U": self.unit,
            "C": float(self.per_point),
            "D": 100,
            "F": Name("D"),
            "RD": ".",
            "RT": ",",
        }
        return {
            "Type": Name("Measure"),
            "Subtype": Name("RL"),
            "R": self.ratio or "1:1",
            "X": [numbers],
            "D": [numbers],
            "A": [numbers],
        }


@dataclass
class Annotation:
    """One annotation, in the terms the PDF keeps it in.

    Every field a markups list wants to show is here — who made it, what they
    said, what they called it — because a list that has to ask each kind of
    markup a different question is a list with holes in it.
    """

    subtype: str = "Square"
    rect: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    intent: str = ""
    author: str = ""
    contents: str = ""
    subject: str = ""
    stroke: tuple[float, float, float] = (0.0, 0.0, 0.0)
    interior: Optional[tuple[float, float, float]] = None
    width: float = 1.0
    opacity: float = 1.0
    border_effect: BorderEffect = field(default_factory=BorderEffect)
    callout: Optional[CalloutLine] = None
    measure: Optional[Measure] = None
    vertices: list[tuple[float, float]] = field(default_factory=list)
    ink: list[list[tuple[float, float]]] = field(default_factory=list)
    line: Optional[tuple[float, float, float, float]] = None
    endings: tuple[str, str] = ("none", "none")
    # A dimension's own dimensions, so to speak.
    leader_length: float = 0.0
    leader_extension: float = 0.0
    leader_offset: float = 0.0
    caption: bool = False
    caption_inline: bool = True
    caption_offset: tuple[float, float] = (0.0, 0.0)
    difference: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    #: Everything else, kept so a round trip does not quietly drop it.
    rest: dict = field(default_factory=dict)

    @property
    def is_markup(self) -> bool:
        return self.subtype not in NOT_MARKUP

    @property
    def is_cloud(self) -> bool:
        return self.border_effect.cloudy or self.intent == "PolygonCloud"

    @property
    def is_dimension(self) -> bool:
        return self.intent in ("LineDimension", "PolyLineDimension",
                               "PolygonDimension")


def read(storage, reference: Any) -> Optional[Annotation]:
    """One annotation out of the file, or nothing when it is not one."""
    found = storage.resolve(reference)
    if not isinstance(found, dict):
        return None
    subtype = storage.name(reference, "Subtype")
    if not subtype:
        return None

    rect = as_numbers([storage.resolve(item)
                       for item in (storage.get(reference, "Rect") or [])])
    annotation = Annotation(
        subtype=subtype,
        rect=tuple(rect[:4]) if len(rect) >= 4 else (0.0, 0.0, 1.0, 1.0),
        intent=storage.name(reference, "IT"),
        author=storage.text(reference, "T"),
        contents=storage.text(reference, "Contents"),
        subject=storage.text(reference, "Subj"),
        opacity=storage.number(reference, "CA", 1.0),
        border_effect=BorderEffect.read(storage, found.get("BE")),
        measure=Measure.read(storage, found.get("Measure")),
    )

    colour = storage.numbers(reference, "C")
    if colour:
        annotation.stroke = _rgb(colour)
    inside = storage.numbers(reference, "IC")
    if inside:
        annotation.interior = _rgb(inside)

    border = storage.get(reference, "BS")
    if isinstance(border, dict):
        annotation.width = storage.number(border, "W", 1.0)
    else:
        widths = storage.numbers(reference, "Border")
        if len(widths) >= 3:
            annotation.width = widths[2]

    annotation.vertices = _pairs(storage.numbers(reference, "Vertices"))
    for run in (storage.get(reference, "InkList") or []):
        points = _pairs(as_numbers([storage.resolve(v)
                                    for v in (storage.resolve(run) or [])]))
        if len(points) >= 2:
            annotation.ink.append(points)

    ends = storage.numbers(reference, "L")
    if len(ends) >= 4:
        annotation.line = tuple(ends[:4])

    endings = storage.get(reference, "LE")
    if isinstance(endings, (list, tuple)):
        names = [as_name(storage.resolve(item)) for item in endings]
        annotation.endings = (LINE_ENDINGS.get(names[0] if names else "", "none"),
                              LINE_ENDINGS.get(names[1] if len(names) > 1 else "", "none"))
    elif isinstance(endings, Name):
        annotation.endings = ("none", LINE_ENDINGS.get(str(endings), "none"))

    annotation.leader_length = storage.number(reference, "LL", 0.0)
    annotation.leader_extension = storage.number(reference, "LLE", 0.0)
    annotation.leader_offset = storage.number(reference, "LLO", 0.0)
    annotation.caption = bool(storage.get(reference, "Cap"))
    annotation.caption_inline = storage.name(reference, "CP") != "Top"
    offset = storage.numbers(reference, "CO")
    if len(offset) >= 2:
        annotation.caption_offset = (offset[0], offset[1])
    difference = storage.numbers(reference, "RD")
    if len(difference) >= 4:
        annotation.difference = tuple(difference[:4])

    if "CL" in found:
        annotation.callout = CalloutLine.read(storage, found.get("CL"))
    return annotation


def write(annotation: Annotation, page: Ref,
          appearance: Optional[Ref] = None) -> dict:
    """*annotation* as the dictionary a PDF holds it in."""
    out: dict = {
        "Type": Name("Annot"),
        "Subtype": Name(annotation.subtype),
        "Rect": [float(value) for value in annotation.rect],
        "F": 4,                                     # printed, never hidden
        "P": page,
    }
    if annotation.author:
        out["T"] = annotation.author
    if annotation.contents:
        out["Contents"] = annotation.contents
    if annotation.subject:
        out["Subj"] = annotation.subject
    if annotation.intent:
        out["IT"] = Name(annotation.intent)
    out["C"] = [float(value) for value in annotation.stroke]
    if annotation.interior is not None:
        out["IC"] = [float(value) for value in annotation.interior]
    if annotation.opacity < 1.0:
        out["CA"] = float(annotation.opacity)
    if annotation.width > 0:
        out["BS"] = {"Type": Name("Border"), "W": float(annotation.width),
                     "S": Name("S")}

    effect = annotation.border_effect.write()
    if effect:
        out["BE"] = effect
    if annotation.vertices:
        out["Vertices"] = [value for point in annotation.vertices for value in point]
    if annotation.ink:
        out["InkList"] = [[value for point in run for value in point]
                          for run in annotation.ink]
    if annotation.line:
        out["L"] = [float(value) for value in annotation.line]
    if annotation.endings != ("none", "none"):
        out["LE"] = [Name(ENDING_NAMES.get(annotation.endings[0], "None")),
                     Name(ENDING_NAMES.get(annotation.endings[1], "None"))]
    if annotation.leader_length:
        out["LL"] = float(annotation.leader_length)
        out["LLE"] = float(annotation.leader_extension)
        out["LLO"] = float(annotation.leader_offset)
    if annotation.caption:
        out["Cap"] = True
        out["CP"] = Name("Inline" if annotation.caption_inline else "Top")
        if any(annotation.caption_offset):
            out["CO"] = [float(value) for value in annotation.caption_offset]
    if annotation.callout is not None:
        written = annotation.callout.write()
        if written:
            out["CL"] = written
    if annotation.measure is not None:
        out["Measure"] = annotation.measure.write()
    if any(annotation.difference):
        out["RD"] = [float(value) for value in annotation.difference]
    if appearance is not None:
        out["AP"] = {"N": appearance}
    out.update(annotation.rest)
    return out


def on_page(storage, page: Any) -> list[Annotation]:
    """Every markup annotation on one page, in the order the file lists them."""
    found = []
    for entry in (storage.get(page, "Annots") or []):
        annotation = read(storage, entry)
        if annotation is not None and annotation.is_markup:
            found.append(annotation)
    return found


def _rgb(values: list[float]) -> tuple[float, float, float]:
    """A PDF colour array, whichever space it is in, as red, green and blue."""
    if len(values) >= 4:                                # CMYK
        cyan, magenta, yellow, black = values[:4]
        return (max(0.0, 1.0 - min(cyan + black, 1.0)),
                max(0.0, 1.0 - min(magenta + black, 1.0)),
                max(0.0, 1.0 - min(yellow + black, 1.0)))
    if len(values) >= 3:
        return (values[0], values[1], values[2])
    if values:
        return (values[0], values[0], values[0])        # grey
    return (0.0, 0.0, 0.0)


def _pairs(values: list[float]) -> list[tuple[float, float]]:
    return [(values[i], values[i + 1]) for i in range(0, len(values) - 1, 2)]
