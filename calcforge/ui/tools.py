"""Tool definitions: what each toolbar button creates and how it is drawn."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


from ..items import measure as measure_module
from ..items.contents import ContentsItem
from ..items.mathitem import MathItem
from ..items.measure import CountItem, MeasureItem
from ..items.media import ImageItem
from ..items.shapes import PolyItem, RectItem
from ..items.plotitem import PlotItem
from ..items.tableitem import TableItem
from ..items.text import CalloutItem, NoteItem, StampItem, TextItem

# How a tool gathers its geometry from the mouse.
DRAG = "drag"        # press, drag, release
CLICK = "click"      # single click places the item
POLY = "poly"        # click for each vertex, double-click / Enter to finish
FREE = "free"        # freehand: every mouse-move point is recorded
ANCHOR = "anchor"    # click what it points at, then drag out the box
SNAPSHOT = "snapshot"  # drag a region and take a copy of what is in it
NONE = "none"        # navigation only


@dataclass(frozen=True)
class Tool:
    key: str
    label: str
    icon: str
    mode: str
    category: str
    shortcut: str = ""
    hint: str = ""
    min_points: int = 2
    max_points: int = 0        # 0 = unlimited
    factory: Optional[Callable] = None


def _rect(kind: str):
    return lambda: RectItem(kind)


def _poly(kind: str):
    return lambda: PolyItem(kind)


def _measure(kind: str):
    return lambda: MeasureItem(kind)


TOOLS: list[Tool] = [
    Tool("select", "Select", "select", NONE, "Navigate", "Esc",
         "Select, move and edit markups"),
    Tool("snapshot", "Snapshot", "snapshot", SNAPSHOT, "Navigate", "G",
         "Drag a region to copy everything in it — paste it back and it is "
         "still the markups and the drawing, not a picture of them",
         factory=_rect("marquee")),
    Tool("pan", "Pan", "pan", NONE, "Navigate", "H", "Drag to move around the page"),

    Tool("pen", "Pen", "pen", FREE, "Draw", "Alt+P", "Freehand ink", factory=_poly("ink")),
    Tool("highlighter", "Highlighter", "highlighter", FREE, "Draw", "K",
         "Translucent freehand highlight", factory=_poly("highlighter")),
    Tool("line", "Line", "line", DRAG, "Draw", "L", "Straight line",
         max_points=2, factory=_poly("line")),
    Tool("arrow", "Arrow", "arrow", DRAG, "Draw", "A", "Arrow",
         max_points=2, factory=_poly("arrow")),
    Tool("polyline", "Polyline", "polyline", POLY, "Draw", "",
         "Click each vertex, double-click to finish", factory=_poly("polyline")),
    Tool("rect", "Rectangle", "rect", DRAG, "Draw", "R",
         "Rectangle — drag it or click twice; Shift squares it off, and an "
         "exact width and height can be typed when the page has a scale",
         factory=_rect("rect")),
    Tool("ellipse", "Ellipse", "ellipse", DRAG, "Draw", "E",
         "Ellipse — hold Shift for a circle; it carries its size like a rectangle",
         factory=_rect("ellipse")),
    Tool("polygon", "Polygon", "polygon", POLY, "Draw", "P",
         "Click each vertex, double-click to close — not scaled",
         factory=_poly("polygon")),
    Tool("cloud", "Revision cloud", "cloud", DRAG, "Draw", "C",
         "Revision cloud around an area", factory=_rect("cloud")),
    Tool("cloud_poly", "Cloud (polygon)", "cloud", POLY, "Draw", "",
         "Free-form revision cloud", factory=_poly("cloud")),
    Tool("highlight", "Highlight", "highlight", DRAG, "Draw", "J",
         "Drag over anything to highlight it — it darkens what is underneath "
         "rather than covering it", factory=_rect("highlight")),
    Tool("redact", "Redact", "highlight", DRAG, "Draw", "",
         "Opaque black-out box", factory=_rect("redact")),

    Tool("text", "Text box", "text", DRAG, "Annotate", "T", "Text box",
         factory=lambda: TextItem("")),
    Tool("callout", "Callout", "callout", ANCHOR, "Annotate", "Q",
         "Click what it points at, then drag out the box — or click two corners",
         factory=lambda: CalloutItem("")),
    Tool("cloud_callout", "Cloud callout", "cloud", ANCHOR, "Annotate", "Shift+Q",
         "A revision cloud with a leader: click what it points at, then draw "
         "the cloud", factory=lambda: CalloutItem("", shape="cloud")),
    Tool("note", "Note", "note", CLICK, "Annotate", "N",
         "Sticky note with a comment", factory=lambda: NoteItem("")),
    Tool("stamp", "Stamp", "stamp", DRAG, "Annotate", "S",
         "Approval or status stamp", factory=lambda: StampItem("APPROVED")),
    Tool("image", "Image", "image", DRAG, "Annotate", "",
         "Place an image from disk", factory=lambda: ImageItem()),

    Tool("math", "Calculation line", "math", DRAG, "Calculate", "",
         "One line of unit-aware maths, defining for the whole document — "
         "Enter opens the next line below it",
         factory=lambda: MathItem()),
    Tool("mathblock", "Calculation block", "math", DRAG, "Calculate", "",
         "A block of working kept to itself: as many lines as you like, and "
         "its own names stay inside it",
         factory=lambda: MathItem(block=True)),
    Tool("table", "Table", "table", DRAG, "Calculate", "B",
         "Spreadsheet that can use your variables", factory=lambda: TableItem()),
    Tool("plot", "Plot", "plot", DRAG, "Calculate", "Shift+G",
         "Plot a function or expression against a range", factory=lambda: PlotItem()),
    Tool("contents", "Contents", "page", DRAG, "Calculate", "",
         "A table of contents built from the document's bookmarks — click a "
         "line to go there", factory=lambda: ContentsItem()),

    Tool("measure_length", "Length", "measure_length", DRAG, "Measure", "M",
         "Measure a distance to the page scale", max_points=2,
         factory=_measure(measure_module.LENGTH)),
    Tool("measure_dimension", "Dimension", "measure_length", DRAG, "Measure", "Alt+M",
         "A dimension line carrying your own text instead of the measured value",
         max_points=2, factory=_measure(measure_module.DIMENSION)),
    Tool("measure_polylength", "Polyline length", "polyline", POLY, "Measure", "",
         "Measure along a path", factory=_measure(measure_module.POLYLENGTH)),
    Tool("measure_area", "Area", "measure_area", POLY, "Measure", "Shift+Alt+A",
         "Measure an enclosed area to the page scale", min_points=3,
         factory=_measure(measure_module.AREA)),
    Tool("measure_perimeter", "Perimeter", "polygon", POLY, "Measure", "",
         "Measure around a shape", min_points=3, factory=_measure(measure_module.PERIMETER)),
    Tool("measure_volume", "Volume", "measure_area", POLY, "Measure", "",
         "Area × depth", min_points=3, factory=_measure(measure_module.VOLUME)),
    Tool("measure_angle", "Angle", "measure_angle", POLY, "Measure", "",
         "Measure an angle from three points", min_points=3, max_points=3,
         factory=_measure(measure_module.ANGLE)),
    Tool("measure_radius", "Radius", "measure_radius", DRAG, "Measure", "",
         "Measure a radius", max_points=2, factory=_measure(measure_module.RADIUS)),
    Tool("measure_diameter", "Diameter", "measure_radius", DRAG, "Measure", "",
         "Measure a diameter", max_points=2, factory=_measure(measure_module.DIAMETER)),
    Tool("count", "Count", "count", CLICK, "Measure", "",
         "Drop counting markers", factory=lambda: CountItem()),
    Tool("calibrate", "Calibrate scale", "calibrate", DRAG, "Measure", "",
         "Click each end of something you know the length of, then type that "
         "length — the page scale follows", max_points=2,
         factory=_measure(measure_module.CALIBRATE)),
]

TOOL_MAP = {tool.key: tool for tool in TOOLS}

CATEGORIES = ["Navigate", "Draw", "Annotate", "Calculate", "Measure"]


def tools_in(category: str) -> list[Tool]:
    return [tool for tool in TOOLS if tool.category == category]
