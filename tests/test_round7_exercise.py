"""Exercise round 1's findings in the markup area (docs/qa/exercise_round1.md:
F-05, F-10, F-11, F-12, F-19, F-32, F-33), driven by mouse and keyboard in
the real window: presses on the viewport where things are drawn, the
right-click menu that opens, dialogs read as they appear."""
from __future__ import annotations

import time

import pytest
from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from calcforge.items.measure import MeasureItem
from calcforge.items.shapes import PolyItem, RectItem
from calcforge.items.text import CalloutItem, TextItem
from tests.test_markup_interaction_round6 import (click, drag, key, markups, move, page,
                                                  pump, right_click_menu, scene_rect,
                                                  screen, vp)
from tests.test_round7_shapes import draw


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.view.set_zoom(1.0)
    pump()
    return window


def watch_dialog(handler, limit=4000):
    """Run *handler(dialog)* on the first modal dialog (not a menu) that opens."""
    seen = {"done": False}
    timer = QTimer()
    timer.setInterval(20)
    started = time.perf_counter()

    def look():
        if seen["done"] or (time.perf_counter() - started) * 1000 > limit:
            timer.stop()
            return
        dialog = QApplication.activeModalWidget()
        if isinstance(dialog, QDialog) and dialog.isVisible():
            seen["done"] = True
            timer.stop()
            handler(dialog)
    timer.timeout.connect(look)
    timer.start()
    return timer


def undo(w):
    """Ctrl+Z, once the window has the keyboard, and the step it undid."""
    from tests.test_markup_interaction_round6 import back_to_the_window
    assert back_to_the_window(w), "the window has the keyboard again"
    stack = w.undo_stack
    before = stack.index()
    key(w, Qt.Key_Z, Qt.ControlModifier)
    assert stack.index() == before - 1, "Ctrl+Z reached the undo stack"


# -- F-05: one placement, one undo ------------------------------------------------------

def test_a_text_box_and_its_words_are_one_undo_step(w):
    steps = w.undo_stack.count()
    key(w, Qt.Key_T)
    drag(w, page(w, 100, 300), page(w, 300, 350))
    QTest.keyClicks(vp(w), "Check this")
    key(w, Qt.Key_Escape)
    assert [m.text() for m in markups(w, TextItem)] == ["Check this"]
    assert w.undo_stack.count() == steps + 1
    undo(w)
    assert markups(w, TextItem) == []
    key(w, Qt.Key_Y, Qt.ControlModifier)               # Revu's redo
    assert [m.text() for m in markups(w, TextItem)] == ["Check this"]


def test_a_text_box_left_empty_leaves_no_step(w):
    steps = w.undo_stack.count()
    key(w, Qt.Key_T)
    drag(w, page(w, 100, 300), page(w, 300, 350))
    key(w, Qt.Key_Escape)
    assert markups(w, TextItem) == []
    assert w.undo_stack.count() == steps


def test_a_callout_and_its_words_are_one_undo_step(w):
    key(w, Qt.Key_Q)
    click(w, page(w, 100, 300))
    click(w, page(w, 220, 250))
    QTest.keyClicks(vp(w), "See detail")
    key(w, Qt.Key_Escape)
    (callout,) = markups(w, CalloutItem)
    assert callout.text() == "See detail"
    undo(w)
    assert markups(w, CalloutItem) == []


def test_a_cloud_plus_and_its_words_are_one_undo_step(w):
    key(w, Qt.Key_Q, Qt.ShiftModifier)
    drag(w, page(w, 300, 300), page(w, 380, 360))
    click(w, page(w, 460, 250))
    QTest.keyClicks(vp(w), "Revised")
    key(w, Qt.Key_Escape)
    (cloud,) = markups(w, CalloutItem)
    assert cloud.text() == "Revised" and cloud.cloud_leader() is not None
    undo(w)
    assert markups(w, CalloutItem) == []


# -- F-10: an ellipse converts to a polygon round its curve ------------------------------

def test_an_ellipse_converts_to_a_polygon_that_follows_it(w):
    oval = draw(w, "ellipse", 150, 250, 160, 100)
    centre = scene_rect(oval).center()
    rx, ry = scene_rect(oval).width() / 2, scene_rect(oval).height() / 2
    click(w, centre)
    labels = right_click_menu(w, centre, pick="Convert to Polygon")
    assert "Convert to Polygon" in labels
    pump()
    (shape,) = markups(w, PolyItem)
    assert shape.kind == "polygon" and len(shape.points) >= 24
    for point in shape.points:
        at = shape.mapToScene(point) - centre
        assert (at.x() / rx) ** 2 + (at.y() / ry) ** 2 == pytest.approx(1.0, abs=0.02)
    assert w.undo_stack.undoText() == "Turn into a polygon"     # the step is there
    undo(w)
    assert markups(w, PolyItem) == [] and len(markups(w, RectItem)) == 1


@pytest.mark.parametrize("tool, title", [("ellipse", "Ellipse Size"),
                                         ("rect", "Rectangle Size")])
def test_exact_size_is_named_for_the_shape(w, tool, title):
    shape = draw(w, tool, 150, 250, 160, 100)
    centre = scene_rect(shape).center()
    click(w, centre)
    seen = []
    keep = watch_dialog(lambda d: (seen.append(d.windowTitle()), d.reject()))
    right_click_menu(w, centre, pick="Exact Size…")
    pump(3)
    keep.stop()
    assert seen == [title]


# -- F-11: a group's menu is the group's ---------------------------------------------

MEMBER_EDITS = ("Round All Corners", "Convert to Polygon", "Exact Size…", "Show Size",
                "Control Point", "Arc Segment", "Set as Default", "Save as Markup Style")


def test_a_groups_right_click_menu_does_not_reach_inside_it(w):
    one = draw(w, "rect", 100, 200, 100, 60)
    draw(w, "rect", 300, 300, 100, 60)
    key(w, Qt.Key_A, Qt.ControlModifier)
    key(w, Qt.Key_G, Qt.ControlModifier)               # Group
    assert one.group
    centre = scene_rect(one).center()
    click(w, centre)
    labels = right_click_menu(w, centre)
    assert "Ungroup" in labels and "Copy" in labels and "Add to Tool Chest" in labels
    for entry in MEMBER_EDITS:
        assert entry not in labels, entry
    # a single rectangle still has them
    key(w, Qt.Key_G, Qt.ControlModifier | Qt.ShiftModifier)    # Ungroup
    click(w, page(w, 600, 600))
    click(w, centre)
    labels = right_click_menu(w, centre)
    assert "Convert to Polygon" in labels and "Exact Size…" in labels


def test_apply_to_pages_copies_the_whole_group(w):
    w.document.add_page()
    w.rebuild_scenes()
    pump()
    one = draw(w, "rect", 100, 200, 100, 60)
    draw(w, "ellipse", 300, 300, 100, 60)
    key(w, Qt.Key_A, Qt.ControlModifier)
    key(w, Qt.Key_G, Qt.ControlModifier)
    one = markups(w, RectItem)[0]
    w.apply_to_pages(one, pages=[1])
    other = w.document.pages[1].frame.markups()
    assert len(other) == 2
    assert other[0].group and other[0].group == other[1].group != one.group


# -- F-12: leaders point out of the box, and the Cloud+ keeps its cloud ------------------

def a_text_box(w):
    key(w, Qt.Key_T)
    drag(w, page(w, 200, 300), page(w, 360, 350))
    QTest.keyClicks(vp(w), "Words in the box")
    key(w, Qt.Key_Escape)
    (box,) = markups(w, TextItem)
    return box


def test_add_arrow_leader_never_points_into_its_own_box(w):
    box = a_text_box(w)
    centre = scene_rect(box).center()
    click(w, centre)
    labels = right_click_menu(w, centre, pick="Add Arrow Leader")
    assert "Add Arrow Leader" in labels
    pump()
    assert w.view._pending_arrow_leader is not None
    # the pointer is still on the words: nothing drawn through them
    move(w, centre)
    pump()
    before = vp(w).grab().toImage()
    move(w, centre + QPointF(5, 2))
    pump()
    assert vp(w).grab().toImage() == before
    click(w, centre)                                   # on its own box: not placed
    assert w.view._pending_arrow_leader is not None
    assert not any(getattr(m, "leaders", None) for m in markups(w))
    outside = page(w, 500, 450)
    move(w, outside)
    pump()
    assert vp(w).grab().toImage() != before, "the preview shows once outside"
    click(w, outside)
    (callout,) = markups(w, CalloutItem)
    assert len(callout.leaders) == 1
    tip = callout.mapToScene(callout.tip_of(callout.leaders[0]))
    assert (tip - outside).manhattanLength() < 3
    assert not scene_rect(callout).contains(tip)


def test_add_cloud_leader_is_drawn_by_hand(w):
    """The pointer is Cloud+'s, and the cloud is the one dragged — no cloud of
    a size of its own at the pointer first (the user, 2026-10-20: "still
    placed a pre-sized box instead of letting me size it by hand")."""
    box = a_text_box(w)
    centre = scene_rect(box).center()
    click(w, centre)
    right_click_menu(w, centre, pick="Add Cloud Leader")
    pump()
    assert w.view._pending_cloud_leader is not None
    move(w, page(w, 520, 470))
    pump()
    assert w.view._cloud_leader_preview() is None, "nothing pre-sized at the pointer"
    drag(w, page(w, 480, 440), page(w, 560, 500))
    (callout,) = markups(w, CalloutItem)
    leader = callout.cloud_leader()
    assert leader is not None
    drawn = callout.mapRectToParent(leader.cloud_box())
    assert (drawn.left(), drawn.top(), drawn.width(), drawn.height()) == \
        pytest.approx((480, 440, 80, 60), abs=1.5)


def test_remove_leader_keeps_the_cloud_plus_cloud(w):
    key(w, Qt.Key_Q, Qt.ShiftModifier)
    drag(w, page(w, 300, 300), page(w, 380, 360))
    click(w, page(w, 460, 250))
    QTest.keyClicks(vp(w), "Revised")
    key(w, Qt.Key_Escape)
    (cloud,) = markups(w, CalloutItem)
    words = scene_rect(cloud).center()
    click(w, words)
    labels = right_click_menu(w, words)
    assert "Remove Leader" not in labels, "its cloud is not a leader to take away"
    # an arrow added to it can be taken away, and the cloud stays
    right_click_menu(w, words, pick="Add Arrow Leader")
    click(w, page(w, 600, 150))
    (cloud,) = markups(w, CalloutItem)
    assert len(cloud.leaders) == 2
    words = scene_rect(cloud).center()
    click(w, words)
    labels = right_click_menu(w, words, pick="Remove Leader")
    assert "Remove Leader" in labels
    (cloud,) = markups(w, CalloutItem)
    assert len(cloud.leaders) == 1 and cloud.cloud_leader() is not None


# -- F-19: the Set Scale prompt, for every measuring tool and no plain shape ------------

@pytest.mark.parametrize("tool, asks", [("rect", False), ("ellipse", False),
                                        ("measure_dimension", True),
                                        ("measure_length", True),
                                        ("sketch_rect", True), ("sketch_ellipse", True)])
def test_the_set_scale_prompt_is_for_measuring(w, tool, asks):
    w.interactive_prompts = True
    seen = []
    keep = watch_dialog(lambda d: (seen.append(d.windowTitle()), d.reject()))
    w.select_tool(tool)
    drag(w, page(w, 150, 300), page(w, 300, 380))
    pump(3)
    keep.stop()
    assert bool(seen) == asks, seen
    assert len(markups(w)) == 1                       # drawn, scale or no scale


# -- F-32: a locked markup still shows that it is selected --------------------------------

def blue_near(w, item) -> int:
    from PySide6.QtCore import QRect
    image = vp(w).grab().toImage()
    box = item.mapRectToScene(item.local_rect().normalized())
    a, b = screen(w, box.topLeft()), screen(w, box.bottomRight())
    count = 0
    for x in range(a.x() - 16, b.x() + 17):
        for y in range(a.y() - 16, b.y() + 17):
            if not QRect(0, 0, image.width(), image.height()).contains(x, y):
                continue
            colour = image.pixelColor(x, y)
            if colour.blue() > 140 and colour.red() < 110 and colour.green() < 170:
                count += 1
    return count


@pytest.mark.parametrize("tool", ["rect", "polyline"])
def test_a_locked_markup_shows_it_is_selected(w, tool):
    if tool == "rect":
        item = draw(w, "rect", 150, 250, 120, 80)
    else:
        w.select_tool("polyline")
        for x, y in ((150, 250), (230, 320), (300, 250)):
            click(w, page(w, x, y))
        key(w, Qt.Key_Return)
        w.select_tool("select")
        (item,) = markups(w, PolyItem)
    at = item.mapToScene(item.local_rect().center()) if tool == "rect" else \
        item.mapToScene(item.points[1])
    click(w, at)
    assert item.isSelected()
    key(w, Qt.Key_L, Qt.ControlModifier)               # Lock
    assert item.locked and item.isSelected()
    pump(3)
    assert blue_near(w, item) > 20, "a dashed box and a padlock"
    click(w, page(w, 600, 650))
    pump(3)
    assert not item.isSelected() and blue_near(w, item) < 5


# -- F-33: Edit Text… on a measurement starts from what it says ---------------------------

def test_edit_text_on_a_length_starts_from_its_value(w):
    w.select_tool("measure_length")
    drag(w, page(w, 150, 300), page(w, 330, 300))
    w.select_tool("select")
    (length,) = markups(w, MeasureItem)
    shown = length.value_text
    assert shown
    on = length.mapToScene(length.points[0] + (length.points[-1] - length.points[0]) / 2)
    click(w, on)
    right_click_menu(w, on, pick="Edit Text…")
    pump()
    editor = w.view._label_editor
    assert editor is not None and editor.text() == shown
    assert editor.selectedText() == shown
    QTest.keyClicks(editor, "beam")
    QTest.keyClick(editor, Qt.Key_Return)
    pump()
    assert length.value_text == "beam"
    right_click_menu(w, on, pick="Edit Text…")
    pump()
    editor = w.view._label_editor
    assert editor.text() == "beam"
    editor.selectAll()
    QTest.keyClicks(editor, length.measured_text)
    QTest.keyClick(editor, Qt.Key_Return)
    pump()
    assert length.custom_label == "" and length.value_text == length.measured_text
