"""Selection-aware style capabilities shared by Properties and the toolbar."""
from __future__ import annotations

from ..items.contents import ContentsItem
from ..items.measure import MeasureItem
from ..items.media import ImageItem
from ..items.shapes import PolyItem, RectItem
from ..items.snapshot import SnapshotItem
from ..items.text import _TextBase

STROKE = "stroke"
FILL = "fill"
WIDTH = "width"
DASH = "dash"
HATCH = "hatch"
OPACITY = "opacity"
FILL_OPACITY = "fill_opacity"
FONT = "font"


def capabilities(item, for_default: bool = False) -> set[str]:
    """Return only controls whose values the item visibly uses.

    ``for_default`` asks the other question: not "what can be changed about
    this markup" but "what can be set as the default for making one". They
    differ for a photo. Its own border means nothing — a stroke colour on a
    raster image has nowhere to go — but the frame a placed image is given is
    a real setting, and with no way to reach it the only frame available was
    whatever the code happened to start with.
    """
    if isinstance(item, SnapshotItem):
        # A snapshot is drawn linework, not a photo: it has an outline, that
        # outline defaults to none, and it is the user's to set — its colour,
        # its weight and what kind of line it is.
        return {OPACITY, STROKE, WIDTH, DASH}
    if isinstance(item, ImageItem):
        # A photo's own border means nothing, but the frame a placed one is
        # given is a real setting, and a frame has a line type like any other.
        return {OPACITY, STROKE, WIDTH, DASH} if for_default else {OPACITY}
    if isinstance(item, ContentsItem):
        return {STROKE, FILL, WIDTH, FONT, OPACITY, FILL_OPACITY}
    if isinstance(item, _TextBase):
        return {STROKE, FILL, WIDTH, DASH, FONT, OPACITY, FILL_OPACITY}
    if isinstance(item, MeasureItem):
        result = {STROKE, WIDTH, DASH, FONT, OPACITY}
        if getattr(item, "closed", False):
            result |= {FILL, FILL_OPACITY}
        return result
    if isinstance(item, PolyItem):
        result = {STROKE, WIDTH, DASH, OPACITY}
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

