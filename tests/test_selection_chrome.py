"""A selected markup paints its handles inside its own rectangle at any zoom.

The handles are a fixed number of pixels across, so zoomed out they cover
more of the page; outside the markup's rectangle Qt never repaints where
they were, and moving a markup left pieces of its selection box and its
rotation handle behind (the user, 2026-10-14)."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QPainter, QPicture, QTransform
from PySide6.QtWidgets import QStyleOptionGraphicsItem

from calcforge.ui.tools import TOOLS
from tests.probe_audit import make

KINDS = [t.key for t in TOOLS if t.factory is not None and t.mode != "none"
         and t.key not in ("image", "snapshot", "calibrate", "viewport", "eraser", "crop",
                           "cutout_polygon", "redact")]


def overhang(item, zoom: float) -> float:
    """How far past its own rectangle the markup paints, in pixels."""
    picture = QPicture()
    painter = QPainter(picture)
    painter.setTransform(QTransform.fromScale(zoom, zoom))
    item.paint(painter, QStyleOptionGraphicsItem(), None)
    painter.end()
    drawn = QRectF(picture.boundingRect())
    own = QTransform.fromScale(zoom, zoom).mapRect(item.boundingRect())
    return max(own.left() - drawn.left(), own.top() - drawn.top(),
               drawn.right() - own.right(), drawn.bottom() - own.bottom())


@pytest.mark.parametrize("kind", KINDS)
def test_a_selected_markup_paints_inside_itself_at_any_zoom(window, kind):
    window.show()
    item = make(window, kind)
    if item is None:
        pytest.skip(f"{kind} draws nothing here")
    window.select_tool("select")
    window.view.scene().clearSelection()
    item.setSelected(True)
    for zoom in (0.1, 0.25, 0.5, 1.0, 4.0):
        window.view._zoom = zoom
        window.view.apply_view_transform()
        assert overhang(item, zoom) <= 1.0, (kind, zoom)


def test_the_handles_room_does_not_count_as_what_a_markup_covers(window):
    """Align and redaction measure the markup, not its handles."""
    from PySide6.QtCore import QPointF
    from calcforge.items.shapes import RectItem
    frame = window.document.pages[0].frame
    box = RectItem("rect", QRectF(0, 0, 100, 50))
    frame.add_markup(box, QPointF(100, 100))
    alone = box.boundingRect()
    window.view._zoom = 0.2
    window.view.apply_view_transform()
    box.setSelected(True)
    assert box.boundingRect().width() > alone.width() + 50
    assert box.bounds_without_chrome() == alone
    box.setSelected(False)
    assert box.boundingRect() == alone
