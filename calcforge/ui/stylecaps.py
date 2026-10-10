"""Selection-aware style capabilities shared by Properties and the toolbar."""
from __future__ import annotations

from ..items.contents import ContentsItem
from ..items.measure import CountItem, MeasureItem
from ..items.media import ImageItem
from ..items.shapes import PolyItem, RectItem, SketchItem
from ..items.snapshot import SnapshotItem
from ..items.text import CalloutItem, FlagItem, StampItem, _TextBase

STROKE = "stroke"
FILL = "fill"
WIDTH = "width"
DASH = "dash"
HATCH = "hatch"
OPACITY = "opacity"
FILL_OPACITY = "fill_opacity"
FONT = "font"
ARROW_SIZE = "arrow_size"
CLOUD = "cloud"            # a cloud's arc size
CORNER = "corner"          # a rectangle's corner radius
SYMBOL = "symbol"          # a count's symbol


def capabilities(item, for_default: bool = False) -> set[str]:
    """Return only controls whose values the item visibly uses.

    ``for_default`` asks what can be set for a newly created markup. Images
    expose their optional drawn border in both selected-item and default
    controls; their raster pixels are unaffected by its colour.
    """
    if getattr(item, "TYPE", "") == "link":
        return {STROKE}           # only the colour of its on-screen outline
    if getattr(item, "TYPE", "") in ("calc", "calc_drawing"):
        # an equation is drawn by SMath's typesetting: its font, colours and
        # result format are its own settings (Properties > Equation), not a
        # markup's pen and fill
        return set()
    if getattr(item, "TYPE", "") in ("table", "sheet_run", "chart"):
        return set()              # styled in their cells or their own dialog, not as markups
    if getattr(item, "TYPE", "") == "calc_block":
        return {STROKE, WIDTH, DASH}      # its frame
    if isinstance(item, SnapshotItem):
        # A snapshot is drawn linework, not a photo: it has an outline, that
        # outline defaults to none, and it is the user's to set — its colour,
        # its weight and what kind of line it is.
        return {OPACITY, STROKE, WIDTH, DASH}
    if isinstance(item, ImageItem):
        # The raster pixels are not recoloured by these fields, but its
        # optional drawn border uses all three in both style surfaces.
        return {OPACITY, STROKE, WIDTH, DASH}
    if isinstance(item, SketchItem):
        # Imported drawing strokes carry their own per-path colours and widths.
        return {OPACITY}
    if isinstance(item, CountItem):
        # a small symbol with its number: no dashes or hatching on a marker
        return {STROKE, FILL, WIDTH, OPACITY, FILL_OPACITY, FONT, SYMBOL}
    if isinstance(item, StampItem):
        return {STROKE, FILL, WIDTH, DASH, HATCH, OPACITY, FILL_OPACITY, FONT}
    if isinstance(item, FlagItem):
        return {STROKE, FILL, WIDTH, OPACITY, FILL_OPACITY}
    if isinstance(item, ContentsItem):
        return {STROKE, FILL, WIDTH, FONT, OPACITY, FILL_OPACITY}
    if isinstance(item, _TextBase):
        result = {STROKE, FILL, WIDTH, DASH, FONT, OPACITY, FILL_OPACITY}
        if isinstance(item, CalloutItem):
            result.add(ARROW_SIZE)
        return result
    if isinstance(item, MeasureItem):
        result = {STROKE, WIDTH, DASH, FONT, OPACITY}
        if getattr(item, "closed", False):
            result |= {FILL, FILL_OPACITY}       # an area has no arrowheads
        else:
            result |= {ARROW_SIZE}
        return result
    if isinstance(item, PolyItem) and item.kind == "highlighter":
        return {STROKE, WIDTH, OPACITY}       # a highlighter pen: colour, width, opacity
    if isinstance(item, PolyItem):
        result = {STROKE, WIDTH, DASH, OPACITY, ARROW_SIZE}
        if getattr(item, "closed", False) or item.kind in ("polygon", "cloud"):
            result |= {FILL, HATCH, FILL_OPACITY}
        if item.kind == "cloud":
            result |= {CLOUD}
        return result
    if isinstance(item, RectItem) and item.kind == "highlight":
        return {FILL, FILL_OPACITY, OPACITY}  # a highlight is a colour wash
    if isinstance(item, RectItem):
        result = {STROKE, FILL, WIDTH, DASH, HATCH, OPACITY, FILL_OPACITY}
        if item.kind == "cloud":
            result |= {CLOUD}
        elif item.kind == "rect":
            result |= {CORNER}
        return result
    return {STROKE, FILL, WIDTH, DASH, OPACITY, FILL_OPACITY}


def common_capabilities(items) -> set[str]:
    """Capabilities every item in a mixed selection has in common."""
    items = list(items)
    if not items:
        return set()
    common = capabilities(items[0])
    for item in items[1:]:
        common &= capabilities(item)
    return common
