"""Adding a cloud leader to a call-out never moves the leaders it already
has (the user, 2026-10-22, on Windows: "Had a weird bug with adding a cloud
leader to an existing callout which moved the old arrow leader position,
which should never happen.").

What moved it: adding a cloud leader released the side of every leader on
the call-out, as moving the box does, so an arrow leader that kept a side of
its own — one its hinge was dragged to, or the one it held while the
call-out was placed (f85be82) — went over to the side facing its head, its
hinge jumping across the box. Now a new leader, or one leader's head moved,
leaves the others as they were; only moving the box works them all out
again.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtTest import QTest

from calcforge.items.text import CalloutItem
from tests.test_markup_interaction_round6 import (click, drag, key, markups, move,
                                                  page, pump, screen, vp)
from tests.test_usability import double_click


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.view.set_zoom(1.0)
    pump()
    return window


def _the_callout(w) -> CalloutItem:
    (callout,) = markups(w, CalloutItem)
    return callout


def _place_callout(w) -> CalloutItem:
    w.select_tool("callout")
    move(w, page(w, 120, 140))
    click(w, page(w, 120, 140))
    move(w, page(w, 260, 90))
    click(w, page(w, 260, 90))
    key(w, Qt.Key_Escape)
    return _the_callout(w)


def _select(w, callout):
    click(w, callout.mapToScene(callout.local_rect().center()))
    assert callout.isSelected()


def _drag_handle(w, callout, name, to_scene: QPointF):
    _select(w, callout)
    at = callout.mapToScene(callout.handle_points()[name])
    move(w, at)
    drag(w, at, to_scene)


def _arrangements():
    return ["arrow", "hinge set by hand", "two leaders", "box moved", "box resized",
            "turned page"]


def _set_up(w, how: str) -> CalloutItem:
    if how == "turned page":
        w.rotate_page(0, clockwise=True)
        pump()
    callout = _place_callout(w)
    if how == "hinge set by hand":
        # under the box rather than the side facing its head
        box = callout.mapRectToScene(callout.local_rect())
        _drag_handle(w, callout, "e0", QPointF(box.center().x(), box.bottom() + 30))
        callout = _the_callout(w)
        assert callout.side_of(callout.leaders[0]) == "bottom"
        assert callout.leaders[0].side == "bottom", "a side of its own"
    elif how == "two leaders":
        at = callout.mapToScene(callout.local_rect().center())
        menu = w.build_context_menu(callout, at)
        (arrow,) = [a for a in menu.actions() if a.text() == "Add Arrow Leader"]
        arrow.trigger()
        pump()
        move(w, page(w, 200, 230))
        click(w, page(w, 200, 230))
        callout = _the_callout(w)
        assert len(callout.leaders) == 2
    elif how == "box moved":
        _select(w, callout)
        middle = callout.mapToScene(callout.local_rect().center())
        drag(w, middle, middle + QPointF(30, 45))
        callout = _the_callout(w)
    elif how == "box resized":
        _drag_handle(w, callout, "se",
                     callout.mapToScene(callout.local_rect().bottomRight()) + QPointF(40, 30))
        callout = _the_callout(w)
    w.view.scene().clearSelection()
    pump()
    return callout


def _geometry(callout, count) -> list:
    """Each of the first *count* leaders: its tip, hinge, the middle of the
    side it leaves by, and that side — on the page, so a rebuilt item is
    compared where it is drawn."""
    out = []
    for leader in callout.leaders[:count]:
        points = [callout.tip_of(leader), callout.elbow_of(leader),
                  callout.side_point_of(leader)]
        out.append(([(round(p.x(), 6), round(p.y(), 6))
                     for p in (callout.mapToScene(q) for q in points)],
                    callout.side_of(leader)))
    return out


def _local(callout, count) -> list:
    return [([(round(p.x(), 6), round(p.y(), 6)) for p in
              (callout.tip_of(l), callout.elbow_of(l), callout.side_point_of(l))],
             callout.side_of(l)) for l in callout.leaders[:count]]


def _picture(callout, count) -> QImage:
    """The first *count* leaders as drawn, in the call-out's own place."""
    copy = CalloutItem()
    copy.deserialize(callout.serialize())
    copy.leaders = copy.leaders[:count]
    image = QImage(900, 700, QImage.Format_ARGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.translate(450, 350)
    painter.scale(2, 2)
    painter.setTransform(callout.sceneTransform(), True)
    painter.translate(-callout.mapToScene(callout.local_rect().center()))
    copy.paint_leader(painter)
    painter.end()
    return image


@pytest.mark.parametrize("drawn", ["dragged", "corners"])
@pytest.mark.parametrize("how", _arrangements())
def test_adding_a_cloud_leader_leaves_the_others_where_they_were(w, tmp_path, how, drawn):
    from tests.test_propbar_gaps import save_and_reopen

    callout = _set_up(w, how)
    count = len(callout.leaders)
    before, local, picture = _geometry(callout, count), _local(callout, count), \
        _picture(callout, count)
    steps = w.undo_stack.count()

    at = callout.mapToScene(callout.local_rect().center())
    menu = w.build_context_menu(callout, at)
    (cloud,) = [a for a in menu.actions() if a.text() == "Add Cloud Leader"]
    cloud.trigger()
    pump()
    corners = [page(w, x, y) for x, y in ((330, 230), (470, 240), (455, 330), (375, 315))]
    if drawn == "dragged":
        QTest.mousePress(vp(w), Qt.LeftButton, Qt.NoModifier, screen(w, corners[0]))
        for t in (0.3, 0.6, 0.9):
            move(w, corners[0] + (corners[2] - corners[0]) * t)
    else:
        for corner in corners[:3]:
            move(w, corner)
            click(w, corner)
        move(w, corners[3])
    pump()
    found = w.view._cloud_leader_preview()
    assert found is not None, "the new leader is shown while its cloud is drawn"
    preview, _origin = found
    assert len(preview.leaders) == count + 1
    assert _local(preview, count) == local, "the preview moves no other leader"
    if drawn == "dragged":
        QTest.mouseRelease(vp(w), Qt.LeftButton, Qt.NoModifier, screen(w, corners[2]))
        pump()
    else:
        double_click(w.view, corners[3].x(), corners[3].y())
        pump()

    callout = _the_callout(w)
    assert len(callout.leaders) == count + 1 and callout.leaders[-1].clouds()
    assert _geometry(callout, count) == before, "no other leader moved"
    assert _picture(callout, count) == picture, "nor is drawn any differently"
    assert w.undo_stack.count() == steps + 1

    w.undo_stack.undo()
    pump()
    callout = _the_callout(w)
    assert len(callout.leaders) == count
    assert _geometry(callout, count) == before, "undo puts back exactly what was there"
    w.undo_stack.redo()
    pump()
    callout = _the_callout(w)
    assert _geometry(callout, count) == before

    save_and_reopen(w, tmp_path)
    callout = _the_callout(w)
    assert len(callout.leaders) == count + 1 and callout.leaders[-1].clouds()
    assert _geometry(callout, count) == before, "and it is saved so"


def test_moving_one_leaders_head_leaves_the_others_alone(w):
    """Moving one leader's head works out its own hinge, nobody else's."""
    callout = _set_up(w, "hinge set by hand")
    at = callout.mapToScene(callout.local_rect().center())
    menu = w.build_context_menu(callout, at)
    (arrow,) = [a for a in menu.actions() if a.text() == "Add Arrow Leader"]
    arrow.trigger()
    pump()
    move(w, page(w, 520, 60))
    click(w, page(w, 520, 60))
    callout = _the_callout(w)
    first = _geometry(callout, 1)
    _drag_handle(w, callout, "l1", page(w, 540, 200))
    callout = _the_callout(w)
    assert _geometry(callout, 1) == first


def test_moving_the_box_still_works_every_hinge_out():
    """The box moved: a side chosen by hand may now be the wrong one, so the
    hinges are worked out again — that much is as it was."""
    callout = CalloutItem("Note", QRectF(0, 0, 100, 40))
    callout.leaders = []
    leader = callout.add_leader(QPointF(-80, 60))
    leader.side = "bottom"
    callout.move_keeping_leader(QPointF(10, 0))
    assert leader.side == ""
