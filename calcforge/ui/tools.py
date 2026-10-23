"""Tool definitions: what each toolbar button creates and how it is drawn."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


from ..items import measure as measure_module
from ..items.contents import ContentsItem
from ..items.measure import CountItem, MeasureItem
from ..items.media import ImageItem
from ..items.shapes import PolyItem, RectItem
from ..items.text import CalloutItem, FlagItem, NoteItem, StampItem, TextItem

# How a tool gathers its geometry from the mouse.
DRAG = "drag"        # press, drag, release
CLICK = "click"      # single click places the item
POLY = "poly"        # click for each vertex, double-click / Enter to finish
FREE = "free"        # freehand: every mouse-move point is recorded
ANCHOR = "anchor"    # click what it points at, then click where the words go
CLOUD = "cloud"      # cloud it, then click where the words go
CLOUDY = "cloudy"    # drag for a rectangle, or click corner by corner
SNAPSHOT = "snapshot"  # drag a region and take a copy of what is in it
ERASE = "erase"      # rub out the ink it is dragged over
NONE = "none"        # navigation only

#: Revu's Sketch to Scale tools: on the Measure toolbar, in their own menu.
SKETCH = "Sketch to Scale"


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


def _rect(kind: str, to_scale: bool = False):
    return lambda: RectItem(kind, to_scale=to_scale)


def _poly(kind: str):
    return lambda: PolyItem(kind)


def _link():
    from ..items.link import LinkItem
    return LinkItem()


def _checkbox():
    from ..items.checkbox import CheckboxItem
    return CheckboxItem()


def _measure(kind: str):
    return lambda: MeasureItem(kind)


TOOLS: list[Tool] = [
    Tool("select", "Select", "select", NONE, "Navigate", "Esc",
         "Select, move and edit markups"),
    Tool("snapshot", "Snapshot", "snapshot", SNAPSHOT, "Navigate", "G",
         "Drag a region to copy everything in it — what comes back is the "
         "drawing itself, lines and all, so it stays sharp at any size",
         factory=_rect("marquee")),
    # H belongs to Highlight, as it does in Bluebeam. Panning is the space
    # bar, the middle button, this button, or Shift+V — Revu's key for Pan
    # (QA, 2026-10-15).
    Tool("pan", "Pan", "pan", NONE, "Navigate", "Shift+V", "Drag to move around the page"),

    Tool("pen", "Pen", "pen", FREE, "Draw", "Alt+P", "Freehand ink", factory=_poly("ink")),
    Tool("highlighter", "Highlight", "highlighter", FREE, "Draw", "H",
         "Translucent freehand highlight", factory=_poly("highlighter")),
    Tool("eraser", "Eraser", "eraser", ERASE, "Draw", "Shift+E",
         "Drag over freehand ink and highlighting to rub it out — it does not "
         "touch anything that was drawn as a shape"),
    Tool("line", "Line", "line", DRAG, "Draw", "L", "Straight line",
         max_points=2, factory=_poly("line")),
    Tool("arrow", "Arrow", "arrow", DRAG, "Draw", "A", "Arrow",
         max_points=2, factory=_poly("arrow")),
    Tool("arc", "Arc", "arc", DRAG, "Draw", "Shift+C",
         "A curve between two points — drag it, then move the middle handle to "
         "bend it where you want", max_points=2, factory=_poly("arc")),
    Tool("polyline", "Polyline", "polyline", POLY, "Draw", "N",
         "Click each vertex, double-click to finish", factory=_poly("polyline")),
    Tool("rect", "Rectangle", "rect", DRAG, "Draw", "R",
         "Rectangle — drag it or click twice; Shift squares it off. Its width "
         "and height are on the paper; right-click ▸ Exact Size… sets them",
         factory=_rect("rect")),
    Tool("ellipse", "Ellipse", "ellipse", DRAG, "Draw", "E",
         "Ellipse — hold Shift for a circle; its width and height are on the paper",
         factory=_rect("ellipse")),
    Tool("polygon", "Polygon", "polygon", POLY, "Draw", "P",
         "Click each vertex, double-click to close — not scaled",
         factory=_poly("polygon")),
    Tool("cloud", "Cloud", "cloud", CLOUDY, "Draw", "C",
         "Mark a revision: drag a rectangular Cloud, or click each corner for a "
         "custom Cloud+ — a double-click, the first corner again, Enter or a "
         "right-click closes it",
         factory=_rect("cloud")),
    Tool("highlight", "Highlight Area", "highlight", DRAG, "Draw", "J",
         "Drag over anything to highlight it — it darkens what is underneath "
         "rather than covering it", factory=_rect("highlight")),
    Tool("redact", "Mark for Redaction", "redact", DRAG, "Draw", "",
         "Opaque black-out box", factory=_rect("redact")),
    Tool("link", "Hyperlink", "link", DRAG, "Navigate", "",
         "Drag a region that goes to a page, a view, a file or a web address "
         "when clicked — a real link in the saved PDF",
         factory=lambda: _link()),
    Tool("crop", "Crop", "crop", SNAPSHOT, "Navigate", "",
         "Drag the part of the page to keep; the rest is cropped away, and "
         "Undo brings it back", factory=_rect("marquee")),
    Tool("whiteout", "Whiteout", "eraser", SNAPSHOT, "Draw", "",
         "Revu's Cut Content (Erase Content): drag a region to clear the "
         "flattened PDF artwork in it; Undo restores it",
         factory=_rect("marquee")),

    Tool("text", "Text Box", "text", DRAG, "Annotate", "T",
         "A box of words on the page — drag the box, then type in it",
         factory=lambda: TextItem("")),
    Tool("callout", "Callout", "callout", ANCHOR, "Annotate", "Q",
         "Click what it points at, then click where the words go",
         factory=lambda: CalloutItem("")),
    Tool("cloud_callout", "Cloud+", "cloud_callout", CLOUD, "Annotate", "Shift+Q",
         "Drag a rectangular Cloud or click the corners of a custom Cloud+ "
         "(a double-click or the first corner again closes it), then click "
         "where the words go — the cloud and note are one thing",
         factory=lambda: CalloutItem("")),
    Tool("checkbox", "Checkbox", "checkbox", DRAG, "Annotate", "",
         "Options with boxes to tick — click to place one; "
         "type one option a line, and click a box to tick it",
         factory=lambda: _checkbox()),
    Tool("note", "Note", "note", CLICK, "Annotate", "",
         "Sticky note with a comment", factory=lambda: NoteItem("")),
    Tool("stamp", "Stamp", "stamp", DRAG, "Annotate", "S",
         "Approval or status stamp", factory=lambda: StampItem("APPROVED")),
    Tool("flag", "Flag", "flag", CLICK, "Annotate", "Shift+F",
         "Pin a flag somewhere to come back to", factory=lambda: FlagItem()),
    Tool("image", "Image", "image", DRAG, "Annotate", "",
         "Place an image from disk", factory=lambda: ImageItem()),

    Tool("crop_image", "Crop Image", "crop", SNAPSHOT, "Annotate", "",
         "Select an image, then drag the part of it to keep",
         factory=_rect("marquee")),
    Tool("table", "Table", "table", "table", "Annotate", "",
         "Drag out a table: the rows and columns follow the size you drag — "
         "a spreadsheet on the page, with Excel's formulas, formats and units"),
    Tool("contents", "Contents", "contents", DRAG, "Annotate", "",
         "A table of contents built from the document's bookmarks — click a "
         "line to go there", factory=lambda: ContentsItem()),

    Tool("measure_length", "Length", "measure_length", DRAG, "Measure", "M",
         "Measure a distance to the page scale", max_points=2,
         factory=_measure(measure_module.LENGTH)),
    Tool("measure_dimension", "Dimension", "dimension", DRAG, "Measure", "Alt+M",
         "A dimension line carrying your own text instead of the measured value",
         max_points=2, factory=_measure(measure_module.DIMENSION)),
    Tool("measure_polylength", "Polylength", "measure_polylength", POLY, "Measure",
         "Shift+Alt+Q",
         "Measure along a path", factory=_measure(measure_module.POLYLENGTH)),
    Tool("measure_area", "Area", "measure_area", POLY, "Measure", "Shift+Alt+A",
         "Measure an enclosed area to the page scale", min_points=3,
         factory=_measure(measure_module.AREA)),
    Tool("measure_perimeter", "Perimeter", "measure_perimeter", POLY, "Measure",
         "Shift+Alt+P",
         "Measure around a shape", min_points=3, factory=_measure(measure_module.PERIMETER)),
    Tool("measure_volume", "Volume", "measure_volume", POLY, "Measure", "Shift+Alt+V",
         "Area × depth", min_points=3, factory=_measure(measure_module.VOLUME)),
    Tool("measure_angle", "Angle", "measure_angle", POLY, "Measure", "Shift+Alt+G",
         "Measure an angle from three points", min_points=3, max_points=3,
         factory=_measure(measure_module.ANGLE)),
    Tool("measure_radius", "Centre Radius", "measure_radius", DRAG, "Measure", "",
         "Measure a radius", max_points=2, factory=_measure(measure_module.RADIUS)),
    Tool("measure_diameter", "Diameter", "measure_diameter", DRAG, "Measure",
         "Shift+Alt+D",
         "Measure a diameter", max_points=2, factory=_measure(measure_module.DIAMETER)),
    Tool("cutout_polygon", "Polygon Cut-Out", "cutout_polygon", POLY, "Measure", "",
         "Draw a hole in the area measurement under it — the hole comes off "
         "the area", min_points=3, factory=_measure(measure_module.AREA)),
    Tool("cutout_ellipse", "Ellipse Cut-Out", "cutout_ellipse", DRAG, "Measure", "",
         "Drag a round hole in the area measurement under it",
         factory=_rect("ellipse")),
    Tool("count", "Count", "count", CLICK, "Measure", "Shift+Alt+C",
         "Click to drop numbered markers; they count as the subject on the "
         "Properties toolbar's Count subject… (Count to begin with)",
         factory=lambda: CountItem()),
    Tool("viewport", "Viewport", "viewport", SNAPSHOT, "Measure", "",
         "Drag a region of the sheet drawn at its own scale — a detail at "
         "1:20 beside a plan at 1:100; measurements inside use it",
         factory=_rect("marquee")),
    Tool("calibrate", "Calibrate", "calibrate", DRAG, "Measure", "",
         "Click each end of something you know the length of, then type that "
         "length — the page scale follows", max_points=2,
         factory=_measure(measure_module.CALIBRATE)),

    # Revu's Sketch to Scale tool set (Tools ▸ Sketch to Scale): shapes drawn
    # to a real size, which ask for the page scale as a measurement does.
    # The plain Rectangle and Ellipse never ask (the user, 2026-10-16).
    # Revu gives them no keys.
    Tool("sketch_rect", "Sketch to Scale Rectangle", "sketch_rect", DRAG,
         SKETCH, "",
         "A rectangle drawn to a real size: it uses the page scale, and its "
         "real width and height can be typed while drawing — 3 m × 1.5 m",
         factory=_rect("rect", to_scale=True)),
    Tool("sketch_ellipse", "Sketch to Scale Ellipse", "sketch_ellipse", DRAG,
         SKETCH, "",
         "An ellipse drawn to a real size: it uses the page scale, and its "
         "real diameters can be typed while drawing — Shift for a circle",
         factory=_rect("ellipse", to_scale=True)),
]

TOOL_MAP = {tool.key: tool for tool in TOOLS}


def _calc_block():
    from ..items.calc import CalcBlockItem
    block = CalcBlockItem()
    block.drafting = True          # the calculations hear of it once it is down
    return block


#: Calculation ▸ Calculation Block, drawn as a rectangle is (the user,
#: 2026-10-24: "like a rectangle or text block allowing me to place it
#: anywhere"). Its button is the Calculation bar's, so it is not in TOOLS:
#: not one of the Tools bar's markup tools, nor a second shortcut entry.
TOOL_MAP["calc_block"] = Tool(
    "calc_block", "Calculation Block", "calc_block", DRAG, "Calculation", "",
    "Drag out a calculation block anywhere, or click for one of the usual size: what "
    "you type in it is its own (Self-contained, on to start); equations it is drawn "
    "over stay out", factory=_calc_block)

CATEGORIES = ["Navigate", "Draw", "Annotate", "Measure", SKETCH]


def tools_in(category: str) -> list[Tool]:
    return [tool for tool in TOOLS if tool.category == category]
