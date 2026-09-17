"""Selection-aware style capabilities shared by Properties and the toolbar."""
from __future__ import annotations

from ..items.contents import ContentsItem
from ..items.measure import MeasureItem
from ..items.media import ImageItem
from ..items.shapes import PolyItem, RectItem
from ..items.snapshot import SnapshotItem
from ..items.text import CalloutItem, _TextBase

STROKE = "stroke"
FILL = "fill"
WIDTH = "width"
DASH = "dash"
HATCH = "hatch"
OPACITY = "opacity"
FILL_OPACITY = "fill_opacity"
FONT = "font"
ARROW_SIZE = "arrow_size"


def capabilities(item, for_default: bool = False) -> set[str]:
    """Return only controls whose values the item visibly uses.

    ``for_default`` asks what can be set for a newly created markup. Images
    expose their optional drawn border in both selected-item and default
    controls; their raster pixels are unaffected by its colour.
    """
    if isinstance(item, SnapshotItem):
        # A snapshot is drawn linework, not a photo: it has an outline, that
        # outline defaults to none, and it is the user's to set — its colour,
        # its weight and what kind of line it is.
        return {OPACITY, STROKE, WIDTH, DASH}
    if isinstance(item, ImageItem):
        # The raster pixels are not recoloured by these fields, but its
        # optional drawn border uses all three in both style surfaces.
        return {OPACITY, STROKE, WIDTH, DASH}
    if isinstance(item, ContentsItem):
        return {STROKE, FILL, WIDTH, FONT, OPACITY, FILL_OPACITY}
    if isinstance(item, _TextBase):
        result = {STROKE, FILL, WIDTH, DASH, FONT, OPACITY, FILL_OPACITY}
        if isinstance(item, CalloutItem):
            result.add(ARROW_SIZE)
        return result
    if isinstance(item, MeasureItem):
        result = {STROKE, WIDTH, DASH, FONT, OPACITY, ARROW_SIZE}
        if getattr(item, "closed", False):
            result |= {FILL, FILL_OPACITY}
        return result
    if isinstance(item, PolyItem):
        result = {STROKE, WIDTH, DASH, OPACITY, ARROW_SIZE}
        if getattr(item, "closed", False) or item.kind in ("polygon", "cloud"):
            result |= {FILL, HATCH, FILL_OPACITY}
        return result
    if isinstance(item, RectItem):
        return {STROKE, FILL, WIDTH, DASH, HATCH, OPACITY, FILL_OPACITY}
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
