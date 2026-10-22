"""Snap to Grid puts what is drawn, moved, resized and nudged on the page
grid — on a drawing too (the user, 2026-10-22: "Grid snap does not work").

What it was: the grid came last. A markup's corner or a line end within
reach, or a level or an upright lined up with, always won — and on a PDF
drawing there is something to catch within reach nearly everywhere, so the
grid never had a say; a point lined up one way was left wherever the pointer
was the other way. Now, with the grid snapped to, what is drawn is caught
only where it is nearer than the grid's nearest point, a line-up keeps the
grid the other way, and the marker shows the grid point. An arrow key takes
the selection to the grid's next line. A spreadsheet's page has no grid to
snap to, as in Excel.
"""
from __future__ import annotations

import os

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from calcforge.items.text import CalloutItem
from calcforge.ui.calcedit import GRID_PT
from tests.test_markup_interaction_round6 import (click, drag, key, move, page, pump,
                                                  screen, vp)


def _off(value: float) -> float:
    """How far *value* is from the nearest grid line, in points."""
    return abs(value / GRID_PT - round(value / GRID_PT)) * GRID_PT


def _on_grid(points) -> bool:
    return all(_off(p.x()) < 0.01 and _off(p.y()) < 0.01 for p in points)


@pytest.fixture
def w(window):
    window.interactive_prompts = False
    window.show()
    window.activateWindow()
    window.view.set_zoom(1.0)
    window.view.centerOn(page(window, 300, 300))
    pump()
    return window


def _grid(w, on: bool) -> None:
    if bool(w.document.settings.snap_to_grid) != on:
        w.act_snap.trigger()
        pump()
    assert w.document.settings.snap_to_grid == on


def _frame(w):
    return w.document.pages[0].frame


def _new(w, action) -> list:
    frame = _frame(w)
    before = {id(item) for item in frame.markups()}
    action()
    pump()
    return [item for item in frame.markups() if id(item) not in before]


def _points(w, item) -> list:
    """The points of *item* that the pointer put down, on its page."""
    from calcforge.items.checkbox import CheckboxItem
    from calcforge.items.measure import CountItem

    frame = _frame(w)
    if isinstance(item, CalloutItem):
        box = item.local_rect().normalized()
        words = frame.mapFromItem(item, QPointF(box.left(), box.center().y()))
        cloud = item.cloud_leader()
        if cloud is not None:                # a Cloud+: its cloud's corners
            return [words] + [frame.mapFromItem(item, point) for point in cloud.cloud]
        return [words, frame.mapFromItem(item, item.leaders[0].tip)]
    if isinstance(item, CheckboxItem):       # put down at its own size
        return [frame.mapFromItem(item, item.local_rect().normalized().topLeft())]
    if isinstance(item, CountItem):          # centred on the click
        return [frame.mapFromItem(item, item.local_rect().normalized().center())]
    vertices = getattr(item, "points", None)
    if vertices:
        return [frame.mapFromItem(item, point) for point in vertices]
    box = item.local_rect().normalized()
    return [frame.mapFromItem(item, box.topLeft()),
            frame.mapFromItem(item, box.bottomRight())]


#: points well off the grid (6.75 pt), so nothing lands on it by chance
A, B, C = (101.3, 102.9), (203.7, 151.1), (171.9, 233.3)


def _draw(w, tool: str) -> list:
    w.select_tool(tool)
    pump()
    a, b, c = (page(w, *A), page(w, *B), page(w, *C))
    if tool in ("polyline", "polygon", "measure_area"):
        def gesture():
            click(w, a)
            click(w, b)
            QTest.mouseDClick(vp(w), Qt.LeftButton, Qt.NoModifier, screen(w, c))
    elif tool == "callout":
        def gesture():
            click(w, a)
            move(w, b)
            click(w, b)
    elif tool == "cloud_callout":
        def gesture():
            drag(w, a, b)
            move(w, c)
            click(w, c)
    elif tool == "count":
        def gesture():
            click(w, a)
    else:
        def gesture():
            drag(w, a, b)
    made = _new(w, gesture)
    key(w, Qt.Key_Escape)
    key(w, Qt.Key_Escape)
    assert made, f"the {tool} was drawn"
    return made


TOOLS = ["rect", "ellipse", "line", "arrow", "polyline", "polygon", "cloud", "cloud_callout",
         "callout", "text", "checkbox", "measure_length", "measure_dimension", "measure_area",
         "count", "highlight"]


@pytest.mark.parametrize("tool", TOOLS)
def test_drawing_lands_on_the_grid(w, tool):
    _grid(w, True)
    for item in _draw(w, tool):
        points = _points(w, item)
        assert _on_grid(points), f"{tool}: {[(round(p.x(), 2), round(p.y(), 2)) for p in points]}"


@pytest.mark.parametrize("tool", ["rect", "polyline", "callout", "count"])
def test_drawing_is_left_alone_with_the_grid_off(w, tool):
    _grid(w, True)
    _grid(w, False)                          # (turned on and off again)
    for item in _draw(w, tool):
        assert not _on_grid(_points(w, item)), f"{tool} went on the grid with it off"


def _marked_up_drawing(w, tmp_path):
    from tests.test_big_pdf_smooth import _heavy_set
    w.open_from_command_line(_heavy_set(tmp_path / "set.pdf", pages=1))
    w.view.set_zoom(1.0)
    w.view.centerOn(page(w, 300, 300))
    pump()


@pytest.mark.parametrize("tool", ["rect", "polyline", "callout"])
def test_on_a_drawing_full_of_lines_too(w, tmp_path, tool):
    """Over a drawing's line work — something to catch nearly everywhere —
    what is drawn still goes on the grid."""
    _marked_up_drawing(w, tmp_path)
    _grid(w, True)
    for item in _draw(w, tool):
        points = _points(w, item)
        assert _on_grid(points), f"{tool}: {[(round(p.x(), 2), round(p.y(), 2)) for p in points]}"


def test_a_corner_pointed_at_exactly_is_still_caught(w):
    """Nearer than the grid's nearest point, a markup's corner wins."""
    _grid(w, False)
    (box,) = _draw(w, "rect")
    corner = box.mapToScene(box.local_rect().normalized().bottomRight())
    _grid(w, True)
    caught = w.view.snap_scene(corner + QPointF(0.3, 0.2))
    assert abs(caught.x() - corner.x()) < 0.01 and abs(caught.y() - corner.y()) < 0.01


def test_the_marker_shows_the_grid_point(w):
    _grid(w, True)
    w.select_tool("line")
    pump()
    move(w, page(w, *C))
    pump()
    marker = w.view._snap_marker
    assert marker is not None, "no marker while hovering with the grid on"
    assert _on_grid([_frame(w).mapFromScene(marker)])
    assert abs(marker.x() - page(w, *C).x()) <= GRID_PT and abs(marker.y() - page(w, *C).y()) <= GRID_PT


def _selected_rect(w):
    _grid(w, False)
    (box,) = _draw(w, "rect")
    _grid(w, True)
    w.select_tool("select")
    w.view.scene().clearSelection()
    box.setSelected(True)
    pump()
    return box


def test_moving_resizing_and_nudging_land_on_the_grid(w):
    box = _selected_rect(w)
    rect = box.local_rect().normalized()
    edge = box.mapToScene(QPointF(rect.left() + rect.width() * 0.3, rect.top()))
    drag(w, edge, edge + QPointF(37.3, 23.9))
    assert _on_grid(_points(w, box)[:1]), "moved: its corner is off the grid"
    box.setSelected(True)
    pump()
    corner = box.mapToScene(box.local_rect().normalized().bottomRight())
    drag(w, corner, corner + QPointF(31.7, 17.3))
    assert _on_grid(_points(w, box)), "resized: off the grid"
    # an arrow key: to the grid's next line that way, from wherever it is
    box.setPos(box.pos() + QPointF(1.3, 0.0))
    box.setSelected(True)
    before = _points(w, box)[0]
    QTest.keyClick(vp(w), Qt.Key_Right)
    pump()
    after = _points(w, box)[0]
    assert _on_grid([after]) and 0 < after.x() - before.x() <= GRID_PT + 0.01


def test_a_corner_dragged_and_a_hinge_dragged_land_on_the_grid(w):
    _grid(w, True)
    (line,) = _draw(w, "polyline")
    w.select_tool("select")
    w.view.scene().clearSelection()
    line.setSelected(True)
    pump()
    end = line.mapToScene(line.points[0])
    drag(w, end, end + QPointF(23.3, 19.1))
    assert _on_grid(_points(w, line)), "a corner dragged went off the grid"
    (callout,) = [item for item in _draw(w, "callout") if isinstance(item, CalloutItem)]
    w.view.scene().clearSelection()
    callout.setSelected(True)
    pump()
    tip = callout.mapToScene(callout.leaders[0].tip)
    drag(w, tip, tip + QPointF(-21.3, 17.7))
    assert _on_grid([_frame(w).mapFromItem(callout, callout.leaders[0].tip)]), \
        "the arrow head dragged went off the grid"


def test_on_a_turned_page(w):
    """The grid is the page's: on a page turned a quarter, along its sides."""
    frame = _frame(w)
    frame.setRotation(90)
    pump()
    _grid(w, True)
    for tool in ("rect", "polyline"):
        for item in _draw(w, tool):
            points = _points(w, item)
            assert _on_grid(points), \
                f"{tool} on a turned page: {[(round(p.x(), 2), round(p.y(), 2)) for p in points]}"


def test_with_frames_paced_as_on_windows(w):
    w.view.paces_its_frames = True
    _grid(w, True)
    for tool in ("rect", "callout"):
        for item in _draw(w, tool):
            assert _on_grid(_points(w, item)), tool


def test_after_zooming(w):
    w.view.set_zoom(2.5)
    w.view.centerOn(page(w, 150, 150))
    pump()
    _grid(w, True)
    for item in _draw(w, "rect"):
        assert _on_grid(_points(w, item))


def test_not_on_a_spreadsheets_page(w):
    """A spreadsheet's page has its cells for a grid and no page grid, and
    Excel has nothing to snap to: the page grid is not snapped to there."""
    _grid(w, True)

    class SheetPage:
        is_sheet = True
    raw = QPointF(101.3, 102.9)
    assert w.view.snap(raw, frame=SheetPage()) == raw
    assert w.view.grid_point(raw, SheetPage()) is None
    assert _on_grid([w.view.snap(raw, frame=_frame(w))]), "an ordinary page still snaps"
