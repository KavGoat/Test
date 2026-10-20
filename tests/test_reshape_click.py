"""Shift and Ctrl over a selected outline: a drag moves, a click reshapes.

The user, 2026-10-20: "I run into issues when I'm trying to move a markup or
copy a markup by holding Ctrl or Shift but instead it adds a control point or
deletes or curves things or rounds things… Bluebeam doesn't, so it must be
possible." Asked how, they chose "drag moves and click adds, the cursors for
curves and control points are confusing since it's not clear where the point
is added or removed, confusing with the + or −".

So, over a selected outline with Shift or Ctrl held, a press does nothing yet.
Past the system's drag distance it is a move — Ctrl copies, Shift keeps it
straight — and the outline is left as it was. Let go without moving and the
click reshapes it as before: Shift puts a point into a side or takes a point
out, Ctrl rounds a corner off or bends a side into an arc, one undo step each.
Instead of a plus or a minus on the pointer, the outline shows what the click
would do: a hollow point where the new one goes, the point that goes ringed
in red with the outline dashed without it, the rounded corner or the arc
dashed. The pointer keeps saying move — or copy, with Ctrl.

Every gesture here is real QTest input to the canvas's viewport.
"""
from __future__ import annotations


import pytest
from PySide6.QtCore import QEvent, QObject, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QRegion
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from calcforge.items.shapes import PolyItem, RectItem
from tests.test_markup_interaction_round6 import markups, page, pump, screen, vp


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.view.set_zoom(1.0)
    settings = window.document.settings
    settings.snap_to_grid = settings.snap_to_items = False
    settings.snap_to_content = settings.snap_to_alignment = False
    pump()
    yield window
    for key in (Qt.Key_Shift, Qt.Key_Control):
        QTest.keyRelease(window.view, key)


def hold(w, key):
    QTest.keyPress(w.view, key)
    pump()


def let_go(w, key):
    QTest.keyRelease(w.view, key)
    pump()


def move(w, point):
    QTest.mouseMove(vp(w), screen(w, point))
    pump(1)


def gesture(w, a, b, modifiers):
    """Press at *a* with *modifiers*, go to *b* in steps, let go there."""
    QTest.mousePress(vp(w), Qt.LeftButton, modifiers, screen(w, a))
    for t in (0.1, 0.25, 0.5, 0.75, 1.0):
        move(w, QPointF(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t))
    QTest.mouseRelease(vp(w), Qt.LeftButton, modifiers, screen(w, b))
    pump()


def click(w, point, modifiers):
    move(w, point)
    QTest.mouseClick(vp(w), Qt.LeftButton, modifiers, screen(w, point))
    pump()


def polygon(w):
    """A selected four-cornered polygon, clicked out corner by corner."""
    w.select_tool("polygon")
    for x, y in ((120, 120), (300, 120), (300, 260), (120, 260)):
        click(w, page(w, x, y), Qt.NoModifier)
    QTest.keyClick(vp(w), Qt.Key_Return)
    pump()
    w.select_tool("select")
    shape = [i for i in markups(w) if isinstance(i, PolyItem)][-1]
    w.view.scene().clearSelection()
    shape.setSelected(True)
    pump()
    return shape


def scene_of(shape, local):
    return shape.mapToScene(QPointF(local))


def side_middle(shape, index=0):
    start, end = shape.segment_ends(index)
    return scene_of(shape, (start + end) / 2)


def same_points(a, b) -> bool:
    """The same outline, to the thousandth of a point a file keeps."""
    return len(a) == len(b) and all(
        abs(p.x() - q.x()) < 1e-3 and abs(p.y() - q.y()) < 1e-3 for p, q in zip(a, b))


def polys(w):
    return [i for i in markups(w) if isinstance(i, PolyItem)]


# -- a drag moves -------------------------------------------------------------------

@pytest.mark.parametrize("where", ["side", "corner"])
def test_ctrl_dragging_the_outline_copies_it_and_adds_no_point(w, where):
    shape = polygon(w)
    points = [QPointF(p) for p in shape.points]
    start = side_middle(shape) if where == "side" else scene_of(shape, shape.points[1])
    hold(w, Qt.Key_Control)
    gesture(w, start, QPointF(start.x() + 90, start.y() + 70), Qt.ControlModifier)
    let_go(w, Qt.Key_Control)

    found = polys(w)
    assert len(found) == 2, "Ctrl-drag left a copy behind"
    for each in found:
        assert len(each.points) == 4, "no point was added or taken out"
        assert not each.rounded and not each.curved, "nothing was rounded or bent"
        assert same_points(each.points, points), "the outline kept its shape"
    assert w.undo_stack.undoText() == "Copy markup"


@pytest.mark.parametrize("where", ["side", "corner"])
def test_shift_dragging_the_outline_moves_it_straight_and_adds_no_point(w, where):
    shape = polygon(w)
    points = [QPointF(p) for p in shape.points]
    origin = QPointF(shape.pos())
    start = side_middle(shape) if where == "side" else scene_of(shape, shape.points[1])
    hold(w, Qt.Key_Shift)
    gesture(w, start, QPointF(start.x() + 80, start.y() + 9), Qt.ShiftModifier)
    let_go(w, Qt.Key_Shift)

    assert polys(w) == [shape], "moved, not copied"
    assert len(shape.points) == 4 and same_points(shape.points, points)
    moved = shape.pos() - origin
    assert moved.x() == pytest.approx(80, abs=1.5)
    assert moved.y() == pytest.approx(0, abs=0.01), "Shift kept the move level"
    assert w.undo_stack.undoText() == "Move markup"


def test_a_drag_that_comes_back_is_still_a_drag(w):
    """Out past the drag distance and back to where it was pressed: a move
    that ended where it began, never the click's reshaping."""
    shape = polygon(w)
    start = side_middle(shape)
    hold(w, Qt.Key_Shift)
    QTest.mousePress(vp(w), Qt.LeftButton, Qt.ShiftModifier, screen(w, start))
    move(w, QPointF(start.x() + 40, start.y()))
    move(w, start)
    QTest.mouseRelease(vp(w), Qt.LeftButton, Qt.ShiftModifier, screen(w, start))
    pump()
    let_go(w, Qt.Key_Shift)
    assert len(shape.points) == 4


def test_a_tremble_within_the_drag_distance_is_still_a_click(w):
    shape = polygon(w)
    start = side_middle(shape)
    near = QApplication.startDragDistance() - 2
    hold(w, Qt.Key_Shift)
    QTest.mousePress(vp(w), Qt.LeftButton, Qt.ShiftModifier, screen(w, start))
    move(w, QPointF(start.x() + max(near, 1) * 0.5, start.y()))
    QTest.mouseRelease(vp(w), Qt.LeftButton, Qt.ShiftModifier, screen(w, start))
    pump()
    let_go(w, Qt.Key_Shift)
    assert len(shape.points) == 5, "a click that trembled still put a point in"


# -- a click reshapes -----------------------------------------------------------------

def test_shift_click_on_a_side_puts_one_point_where_it_was_clicked(w):
    shape = polygon(w)
    start, end = (scene_of(shape, p) for p in shape.segment_ends(0))
    # a third of the way along the top, a pixel or two off the line
    here = QPointF(start.x() + (end.x() - start.x()) / 3, start.y() + 2)
    hold(w, Qt.Key_Shift)
    click(w, here, Qt.ShiftModifier)
    let_go(w, Qt.Key_Shift)

    assert len(shape.points) == 5
    added = shape.mapToScene(shape.points[1])
    assert added.x() == pytest.approx(here.x(), abs=1.0), "where it was clicked"
    assert added.y() == pytest.approx(start.y(), abs=0.01), "on the side itself"
    assert shape.isSelected()
    w.undo_stack.undo()
    assert len(polys(w)[0].points) == 4, "one undo step"


def test_shift_click_on_a_point_takes_it_out(w):
    shape = polygon(w)
    gone = QPointF(shape.points[2])
    hold(w, Qt.Key_Shift)
    click(w, scene_of(shape, gone), Qt.ShiftModifier)
    let_go(w, Qt.Key_Shift)
    assert len(shape.points) == 3 and gone not in shape.points
    assert shape.isSelected(), "a Shift-click on its point does not drop it"
    w.undo_stack.undo()
    assert len(polys(w)[0].points) == 4


def test_ctrl_click_rounds_a_corner_and_bends_a_side(w):
    shape = polygon(w)
    hold(w, Qt.Key_Control)
    click(w, scene_of(shape, shape.points[1]), Qt.ControlModifier)
    assert shape.is_rounded(1)
    click(w, side_middle(shape, 3), Qt.ControlModifier)
    assert shape.is_curved(3)
    let_go(w, Qt.Key_Control)
    assert len(polys(w)) == 1 and len(shape.points) == 4, "a click copies nothing"
    w.undo_stack.undo()
    shape = polys(w)[0]
    assert shape.is_rounded(1) and not shape.is_curved(3), "each its own undo step"


def test_a_rectangle_reshaped_by_a_click_but_resized_in_proportion_by_a_shift_drag(w):
    """A box's corner is a corner of its outline and its resize handle: a
    Shift-click takes the corner out, a Shift-drag keeps the proportions."""
    w.select_tool("rect")
    a, b = page(w, 140, 140), page(w, 340, 240)
    gesture(w, a, b, Qt.NoModifier)
    w.select_tool("select")
    box = [i for i in markups(w) if isinstance(i, RectItem)][-1]
    box.setSelected(True)
    corner = box.mapToScene(box.local_rect().normalized().bottomRight())
    hold(w, Qt.Key_Shift)
    gesture(w, corner, QPointF(corner.x() + 100, corner.y() + 10), Qt.ShiftModifier)
    rect = box.local_rect().normalized()
    assert rect.width() / rect.height() == pytest.approx(2.0, rel=0.02)
    corner = box.mapToScene(rect.bottomRight())
    click(w, corner, Qt.ShiftModifier)
    let_go(w, Qt.Key_Shift)
    shape = polys(w)[-1]
    assert len(shape.points) == 3, "the click took the corner out"


def test_shift_click_elsewhere_still_picks_out_and_lassos(w):
    shape = polygon(w)
    w.select_tool("rect")
    gesture(w, page(w, 400, 140), page(w, 480, 200), Qt.NoModifier)
    w.select_tool("select")
    box = [i for i in markups(w) if isinstance(i, RectItem)][-1]
    w.view.scene().clearSelection()
    shape.setSelected(True)
    hold(w, Qt.Key_Shift)
    click(w, box.mapToScene(box.local_rect().center()), Qt.ShiftModifier)
    assert shape.isSelected() and box.isSelected(), "Shift-click adds"
    click(w, box.mapToScene(box.local_rect().center()), Qt.ShiftModifier)
    assert shape.isSelected() and not box.isSelected(), "and takes away"
    click(w, page(w, 600, 600), Qt.ShiftModifier)
    assert w.view._mode == "lasso", "Shift on bare paper starts a lasso"
    QTest.keyClick(vp(w), Qt.Key_Escape)
    let_go(w, Qt.Key_Shift)
    assert len(shape.points) == 4


# -- what the click would do, shown on the outline -------------------------------------

class _Painted(QObject):
    """Every region of the viewport repainted."""

    def __init__(self, viewport):
        super().__init__()
        self.viewport = viewport
        self.region = QRegion()
        viewport.installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched is self.viewport and event.type() == QEvent.Paint:
            self.region += event.region()
        return False

    def stop(self):
        self.viewport.removeEventFilter(self)


def _pixel_at(w, scene_point, up_px=0) -> QColor:
    image = vp(w).grab().toImage()
    at = screen(w, scene_point)
    return QColor(image.pixel(at.x(), at.y() - up_px))


def _covers(region: QRegion, rect: QRect) -> bool:
    return QRegion(rect).subtracted(region).isEmpty()


@pytest.mark.parametrize("modifier, where, what", [
    (Qt.Key_Shift, "side", "add"), (Qt.Key_Shift, "corner", "delete"),
    (Qt.Key_Control, "corner", "round"), (Qt.Key_Control, "side", "curve")])
def test_the_preview_shows_what_the_click_would_do_and_leaves_nothing(
        w, modifier, where, what):
    shape = polygon(w)
    preview = w.view.reshape_preview
    start, end = (scene_of(shape, p) for p in shape.segment_ends(0))
    here = (QPointF(start.x() + (end.x() - start.x()) * 0.3, start.y() + 2)
            if where == "side" else scene_of(shape, shape.points[1]))
    move(w, here)
    assert not preview.showing(), "nothing shown without a key held"
    hold(w, modifier)
    move(w, QPointF(here.x() + 0.5, here.y()))
    move(w, here)
    assert preview.showing() and preview.what == what

    if what == "add":
        # the hollow point, on the side, nearest the pointer
        assert preview.point.y() == pytest.approx(start.y(), abs=0.01)
        pointer = w.view.mapToScene(screen(w, here))
        assert preview.point.x() == pytest.approx(pointer.x(), abs=0.01)
    elif what == "delete":
        assert preview.point == scene_of(shape, shape.points[1])
        # the outline without it: a triangle's three sides
        assert preview.path is not None
        assert not preview.path.boundingRect().isEmpty()
    else:
        assert preview.path is not None
    if what in ("round", "curve"):
        # the dashed outline differs from the outline as it is
        now = shape.sceneTransform().map(shape.build_path())
        assert preview.path.boundingRect() != now.boundingRect() or \
            preview.path.length() != pytest.approx(now.length())

    # the pointer still says move (copy with Ctrl), never a plus or a minus
    from calcforge.ui.view import copy_cursor
    cursor = w.view.cursor()
    if modifier == Qt.Key_Control:
        assert cursor.shape() == Qt.BitmapCursor
        assert cursor.pixmap().cacheKey() == copy_cursor().pixmap().cacheKey()
    else:
        assert cursor.shape() == Qt.SizeAllCursor
    # it is drawn: the theme's colour is on the canvas where the point is
    drawn = preview.pixel_rect()
    assert not drawn.isEmpty()
    assert vp(w).rect().contains(drawn)

    # let go of the key: the preview goes, and its pixels are repainted
    painted = _Painted(vp(w))
    let_go(w, modifier)
    pump(3)
    painted.stop()
    assert not preview.showing()
    assert _covers(painted.region, drawn.adjusted(1, 1, -1, -1)), \
        "the pixels the preview covered were repainted when it went"
    shown = vp(w).grab().toImage()
    vp(w).repaint()
    assert shown == vp(w).grab().toImage(), "a piece of the preview was left behind"

    # back on, then the pointer leaves the outline: gone again, and cleared
    hold(w, modifier)
    move(w, QPointF(here.x() + 0.5, here.y()))
    move(w, here)
    assert preview.showing()
    drawn = preview.pixel_rect()
    painted = _Painted(vp(w))
    move(w, page(w, 600, 600))
    pump(3)
    painted.stop()
    assert not preview.showing()
    assert _covers(painted.region, drawn.adjusted(1, 1, -1, -1))
    let_go(w, modifier)


def test_the_preview_follows_the_pointer_along_a_side_repainting_only_its_own_pixels(w):
    shape = polygon(w)
    start, end = (scene_of(shape, p) for p in shape.segment_ends(0))
    hold(w, Qt.Key_Shift)
    move(w, QPointF(start.x() + 30, start.y()))
    painted = _Painted(vp(w))
    for step in range(1, 8):
        move(w, QPointF(start.x() + 30 + 12 * step, start.y() + 1))
        pump(1)
        pointer = w.view.mapToScene(screen(w, QPointF(start.x() + 30 + 12 * step, 0)))
        assert w.view.reshape_preview.point.x() == pytest.approx(pointer.x(), abs=0.01)
    painted.stop()
    let_go(w, Qt.Key_Shift)
    whole = vp(w).width() * vp(w).height()
    covered = sum(r.width() * r.height() for r in painted.region)
    assert covered < whole * 0.25, "the hollow point repaints its own few pixels"


def test_the_preview_is_drawn_in_the_themes_colours(w, qapp):
    from calcforge.app import apply_theme, current_theme
    from calcforge.theme import DARK, LIGHT, tokens

    before = current_theme()
    shape = polygon(w)
    preview = w.view.reshape_preview
    try:
        for theme in (LIGHT, DARK):
            apply_theme(qapp, theme)
            pump()
            accent, danger, _halo = preview.colours()
            assert accent == QColor(tokens(theme)["accent"])
            assert danger == QColor(tokens(theme)["danger"])
            hold(w, Qt.Key_Shift)
            corner = scene_of(shape, shape.points[1])
            move(w, QPointF(corner.x() + 0.5, corner.y()))
            move(w, corner)
            assert preview.what == "delete"
            # the red ring is on the canvas, a ring's radius from the point
            got = _pixel_at(w, corner, up_px=5)
            assert got.red() > got.blue() and got.red() > 120, (theme, got.name())
            let_go(w, Qt.Key_Shift)
    finally:
        apply_theme(qapp, before)
