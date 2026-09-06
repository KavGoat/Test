"""Selection-aware style capabilities shared by Properties and the toolbar."""
from __future__ import annotations

from ..items.contents import ContentsItem
from ..items.mathitem import MathItem
from ..items.measure import MeasureItem
from ..items.media import ImageItem
from ..items.plotitem import PlotItem
from ..items.shapes import PolyItem, RectItem
from ..items.snapshot import SnapshotItem
from ..items.tableitem import TableItem
from ..items.text import _TextBase

STROKE = "stroke"
FILL = "fill"
WIDTH = "width"
DASH = "dash"
HATCH = "hatch"
OPACITY = "opacity"
FILL_OPACITY = "fill_opacity"
FONT = "font"


def capabilities(item) -> set[str]:
    """Return only controls whose values the item visibly uses."""
    if isinstance(item, (ImageItem, SnapshotItem)):
        return {OPACITY}
    if isinstance(item, MathItem):
        return {FONT}
    if isinstance(item, TableItem):
        return {FILL, STROKE, WIDTH, FONT}
    if isinstance(item, PlotItem):
        return {STROKE, WIDTH, FONT, OPACITY}
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

