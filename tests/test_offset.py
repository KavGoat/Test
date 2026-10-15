"""Revu's Offset (Edit ▸ Offset, O; the user's choice, 2026-10-15)."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF

from calcforge.items.shapes import PolyItem, RectItem
from calcforge.ui import offset


def _square():
    return [QPointF(0, 0), QPointF(100, 0), QPointF(100, 100), QPointF(0, 100)]


def test_a_square_grows_and_shrinks_by_the_distance():
    item = PolyItem("polygon", _square())
    kind, out = offset.offset_geometry(item, 10, True)
    xs, ys = [p.x() for p in out], [p.y() for p in out]
    assert (min(xs), max(xs), min(ys), max(ys)) == (-10, 110, -10, 110)
    kind, inner = offset.offset_geometry(item, 10, False)
    xs = [p.x() for p in inner]
    assert (min(xs), max(xs)) == (10, 90)
    # the same whichever way round the square was drawn
    back = PolyItem("polygon", list(reversed(_square())))
    kind, out = offset.offset_geometry(back, 10, True)
    assert min(p.x() for p in out) == -10


def test_a_line_moves_to_the_side_the_pointer_is():
    line = PolyItem("polyline", [QPointF(0, 0), QPointF(100, 0)])
    assert offset.side_of(line, QPointF(50, 20)) != offset.side_of(line, QPointF(50, -20))
    below = offset.side_of(line, QPointF(50, 20))
    kind, moved = offset.offset_geometry(line, 15, below)
    assert all(abs(p.y() - 15) < 1e-9 for p in moved)


def test_a_sharp_corner_is_cut_off_past_the_miter_limit():
    spike = [QPointF(0, 0), QPointF(100, 5), QPointF(0, 10)]           # a very sharp turn
    sharp = offset.offset_points(spike, 5, False, miter_limit=100)
    cut = offset.offset_points(spike, 5, False, miter_limit=1)
    assert len(sharp) == 3 and len(cut) == 4


def test_a_rectangle_and_an_ellipse_offset_by_their_box():
    box = RectItem("ellipse", QRectF(0, 0, 80, 40))
    kind, rect = offset.offset_geometry(box, 5, True)
    assert kind == "rect" and rect == QRectF(-5, -5, 90, 50)
    assert offset.side_of(box, QPointF(40, 20)) is False          # inside
    assert offset.side_of(box, QPointF(1, 1)) is True             # outside the ellipse


def test_offset_on_the_page_is_one_undo_and_can_replace(window):
    frame = window.scene.frames[0]
    item = PolyItem("polygon", _square())
    item.setParentItem(frame)
    item.setPos(100, 100)
    window.scene.clearSelection()
    item.setSelected(True)
    window.show()
    window.act_offset.trigger()
    assert window._offset is not None and window.offset_toolbar().isVisible()
    window.offset_distance.setText("10 mm")
    d = 10 * 72 / 25.4
    before = len([m for m in frame.markups() if isinstance(m, PolyItem)])
    count = window.undo_stack.count()
    copy = window._offset.place(item.mapToScene(QPointF(150, 50)))      # outside, to the right
    polys = [m for m in frame.markups() if isinstance(m, PolyItem)]
    assert len(polys) == before + 1 and window.undo_stack.count() == count + 1
    xs = [p.x() for p in copy.points]
    assert math.isclose(min(xs), -d) and math.isclose(max(xs), 100 + d)
    assert window._offset is None and not window.offset_toolbar().isVisible()
    # Replace Markup: the original goes
    window.scene.clearSelection()
    copy.setSelected(True)
    window.act_offset.trigger()
    window.offset_replace.setChecked(True)
    window._offset.place(copy.mapToScene(QPointF(50, 50)))             # inside
    polys = [m for m in frame.markups() if isinstance(m, PolyItem)]
    assert len(polys) == before + 1
    window.offset_replace.setChecked(False)


def test_offset_asks_for_something_it_can_offset(window):
    window.scene.clearSelection()
    window.act_offset.trigger()
    assert getattr(window, "_offset", None) is None
    assert "Offset" in window.status_hint.text()
