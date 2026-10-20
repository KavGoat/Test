"""Shift, Ctrl and Alt over a selected outline, as Revu.

The user, 2026-10-20: "I run into issues when I'm trying to move a markup or
copy a markup by holding Ctrl or Shift but instead it adds a control point or
deletes or curves things or rounds things… Bluebeam doesn't, so it must be
possible." And then, with photos of Revu 21's pointers: "Shift then click is
add/subtract point unless I start dragging, and Ctrl click/drag is copy, and
Alt click is curve things."

- Shift: a click on a selected outline puts a point into a side or takes a
  point out; pressed and dragged past the system's drag distance it is a move,
  kept straight. Elsewhere Shift-click picks out and Shift on bare paper lassos.
- Ctrl: a drag copies, a click adds to the selection. Nothing is reshaped.
- Alt: a click rounds a corner off or bends a side into an arc; a drag is
  just a move.

Nothing is drawn on the outline: the pointer says what a click does — Revu's
arrow with a "+", a "−", an arc, a copy sign or a move sign at its foot.

Every gesture here is real QTest input to the canvas's viewport.
"""
from __future__ import annotations


import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from calcforge.items.shapes import PolyItem, RectItem
from calcforge.ui.cursors import ADD, COPY, CURVE, MOVE, REMOVE, is_revu_cursor
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
    for key in (Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt):
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


def test_alt_click_rounds_a_corner_and_bends_a_side(w):
    shape = polygon(w)
    hold(w, Qt.Key_Alt)
    click(w, scene_of(shape, shape.points[1]), Qt.AltModifier)
    assert shape.is_rounded(1)
    click(w, side_middle(shape, 3), Qt.AltModifier)
    assert shape.is_curved(3)
    let_go(w, Qt.Key_Alt)
    assert len(polys(w)) == 1 and len(shape.points) == 4, "a click copies nothing"
    w.undo_stack.undo()
    shape = polys(w)[0]
    assert shape.is_rounded(1) and not shape.is_curved(3), "each its own undo step"


@pytest.mark.parametrize("where", ["side", "corner"])
def test_alt_dragging_the_outline_only_moves_it(w, where):
    shape = polygon(w)
    points = [QPointF(p) for p in shape.points]
    origin = QPointF(shape.pos())
    start = side_middle(shape) if where == "side" else scene_of(shape, shape.points[1])
    hold(w, Qt.Key_Alt)
    gesture(w, start, QPointF(start.x() + 70, start.y() + 40), Qt.AltModifier)
    let_go(w, Qt.Key_Alt)
    assert polys(w) == [shape]
    assert same_points(shape.points, points)
    assert not shape.rounded and not shape.curved, "nothing rounded or bent"
    moved = shape.pos() - origin
    assert moved.x() == pytest.approx(70, abs=1.5) and moved.y() == pytest.approx(40, abs=1.5)


@pytest.mark.parametrize("where", ["side", "corner"])
def test_ctrl_click_reshapes_nothing_and_keeps_the_selection(w, where):
    shape = polygon(w)
    points = [QPointF(p) for p in shape.points]
    here = side_middle(shape) if where == "side" else scene_of(shape, shape.points[1])
    hold(w, Qt.Key_Control)
    click(w, here, Qt.ControlModifier)
    let_go(w, Qt.Key_Control)
    assert polys(w) == [shape] and shape.isSelected()
    assert same_points(shape.points, points)
    assert not shape.rounded and not shape.curved, "Ctrl no longer rounds or bends"


def test_ctrl_click_adds_another_markup_to_the_selection(w):
    shape = polygon(w)
    w.select_tool("rect")
    gesture(w, page(w, 400, 140), page(w, 480, 200), Qt.NoModifier)
    w.select_tool("select")
    box = [i for i in markups(w) if isinstance(i, RectItem)][-1]
    w.view.scene().clearSelection()
    shape.setSelected(True)
    hold(w, Qt.Key_Control)
    click(w, box.mapToScene(box.local_rect().center()), Qt.ControlModifier)
    let_go(w, Qt.Key_Control)
    assert shape.isSelected() and box.isSelected()


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


# -- the pointer says what a click does --------------------------------------------------

@pytest.mark.parametrize("key, modifier, where, badge", [
    (None, Qt.NoModifier, "inside", MOVE),
    (None, Qt.NoModifier, "body", MOVE),
    (Qt.Key_Shift, Qt.ShiftModifier, "side", ADD),
    (Qt.Key_Shift, Qt.ShiftModifier, "corner", REMOVE),
    (Qt.Key_Alt, Qt.AltModifier, "side", CURVE),
    (Qt.Key_Alt, Qt.AltModifier, "corner", CURVE),
    (Qt.Key_Control, Qt.ControlModifier, "side", COPY),
    (Qt.Key_Control, Qt.ControlModifier, "corner", COPY),
])
def test_the_pointer_shows_revus_sign_for_what_a_click_does(w, key, modifier, where, badge):
    """And nothing is drawn on the canvas for it: the pointer alone says."""
    shape = polygon(w)
    if where == "inside":          # a filled box's body, away from its outline
        w.select_tool("rect")
        gesture(w, page(w, 400, 300), page(w, 520, 380), Qt.NoModifier)
        w.select_tool("select")
        shape = [i for i in markups(w) if isinstance(i, RectItem)][-1]
        w.view.scene().clearSelection()
        shape.setSelected(True)
        here = shape.mapToScene(shape.local_rect().center())
    elif where == "corner":
        here = scene_of(shape, shape.corner_points()[1])
    else:
        here = side_middle(shape)
        here = QPointF(here.x() - 20, here.y())   # along the side, off its handles
    move(w, QPointF(here.x() + 1, here.y()))
    move(w, here)
    if key is not None:
        hold(w, key)
        move(w, QPointF(here.x() + 0.5, here.y()))
        move(w, here)
    painted_before = vp(w).grab().toImage()
    cursor = vp(w).cursor()
    assert is_revu_cursor(cursor, badge), (where, badge, cursor.shape())
    if key is not None:
        let_go(w, key)
        move(w, QPointF(here.x() + 0.5, here.y()))
        assert not is_revu_cursor(vp(w).cursor(), badge) or badge == MOVE
        assert vp(w).grab().toImage() == painted_before, "nothing was drawn for it"


def test_shift_over_a_box_corner_says_take_it_out(w):
    w.select_tool("rect")
    gesture(w, page(w, 140, 140), page(w, 340, 240), Qt.NoModifier)
    w.select_tool("select")
    box = [i for i in markups(w) if isinstance(i, RectItem)][-1]
    box.setSelected(True)
    corner = box.mapToScene(box.local_rect().normalized().topLeft())
    move(w, corner)
    assert vp(w).cursor().shape() == Qt.SizeFDiagCursor, "a resize handle, plainly"
    hold(w, Qt.Key_Shift)
    move(w, QPointF(corner.x() + 0.5, corner.y()))
    assert is_revu_cursor(vp(w).cursor(), REMOVE)
    let_go(w, Qt.Key_Shift)


# -- Alt-click does not leave the menus picked out --------------------------------------

def test_alt_after_an_alt_click_does_not_take_the_keyboard_to_the_menus(w):
    bar = w.menuBar()
    shape = polygon(w)
    corner = scene_of(shape, shape.points[1])
    # what a lone Alt does: the menu bar takes the keyboard (Qt's and Revu's)
    QTest.keyClick(vp(w), Qt.Key_Alt)
    pump()
    lone = bar.activeAction() is not None or bar.hasFocus()
    assert lone, "a lone Alt does reach the menus here, so the check below means something"
    QTest.keyClick(bar, Qt.Key_Escape)
    pump()
    w.view.setFocus()
    shape.setSelected(True)
    pump()
    # Alt held for a click on the canvas, then let go
    QTest.keyPress(vp(w), Qt.Key_Alt)
    pump()
    click(w, corner, Qt.AltModifier)
    QTest.keyRelease(vp(w), Qt.Key_Alt)
    pump()
    assert shape.is_rounded(1)
    assert bar.activeAction() is None, "no menu picked out after the Alt-click"
    assert not bar.hasFocus() and QApplication.focusWidget() is not bar
    # and a lone Alt afterwards still reaches the menus as it did
    QTest.keyClick(vp(w), Qt.Key_Alt)
    pump()
    assert bar.activeAction() is not None or bar.hasFocus()
    QTest.keyClick(bar, Qt.Key_Escape)
