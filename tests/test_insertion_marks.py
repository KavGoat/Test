"""The red cross (Calc mode) and the insertion point (Markup mode) move or
go when something is put down elsewhere (the user, 2026-10-16: a click left
the red cross showing, and after a rectangle drawn somewhere else the first
point was still there). Real clicks, drags and tool keys.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from calcforge.items.shapes import RectItem
from calcforge.ui import preferences
from tests.test_usability import click, drag, on_page


def settle():
    for _ in range(4):
        QApplication.instance().processEvents()


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.view.set_zoom(1.0)
    settle()
    return window


@pytest.fixture
def blue_point():
    """Preferences ▸ the Markup-mode insertion point on."""
    prefs = preferences.current()
    was = prefs.insertion_point
    prefs.insertion_point = True
    preferences.apply(prefs)
    yield
    prefs.insertion_point = was
    preferences.apply(prefs)


def rects(w):
    return [i for i in w.view.scene().ordered_markups() if isinstance(i, RectItem)]


def draw_rect_with(w, pick_tool, x=300, y=400):
    pick_tool()
    a, b = on_page(w, 0, x, y), on_page(w, 0, x + 80, y + 50)
    drag(w.view, *a, *b)
    settle()


def cross_shown(w):
    calc = w.view.calc
    return calc.cross is not None and calc.calc_mode() and not calc.editing()


@pytest.mark.parametrize("stay_active", [False, True])
def test_calc_mode_cross_goes_when_a_rectangle_is_drawn_elsewhere(w, stay_active):
    if stay_active:
        # Reuse Markup Tools (Revu's Stay Active): the rectangle drawn is not
        # picked, so nothing else took the cross away
        w.act_sticky.setChecked(True)
    QTest.keyClick(w.view, Qt.Key_F12)                        # Calc mode
    click(w.view, *on_page(w, 0, 100, 120))                   # the red cross
    assert cross_shown(w)
    # the Rectangle tool from the toolbar (in Calc mode R is a letter)
    draw_rect_with(w, lambda: w.tool_actions["rect"].trigger())
    settle()
    assert len(rects(w)) == 1
    assert w.view.calc.cross is None                          # stayed before
    if stay_active:
        draw_rect_with(w, lambda: None, x=300, y=200)         # the tool still in hand
        assert len(rects(w)) == 2 and w.view.calc.cross is None
        w.act_sticky.setChecked(False)
    # a click on bare paper with Select puts it down again, where clicked
    w.select_tool("select")
    click(w.view, *on_page(w, 0, 100, 500))
    assert cross_shown(w)
    frame, point = w.view.calc.cross
    assert abs(point.y() - 500) < 12


@pytest.mark.parametrize("tool", ["count", "note", "stamp", "polyline", "crop"])
def test_calc_mode_cross_goes_when_any_tool_puts_something_down(w, tool):
    """The rectangle's siblings: put down by a click, or a click at a time."""
    QTest.keyClick(w.view, Qt.Key_F12)
    click(w.view, *on_page(w, 0, 100, 120))
    assert cross_shown(w)
    w.tool_actions[tool].trigger()
    settle()
    click(w.view, *on_page(w, 0, 320, 420))
    settle()
    assert w.view.calc.cross is None
    QTest.keyClick(w.view, Qt.Key_Escape)
    settle()
    assert w.view.calc.cross is None              # and Esc does not bring it back


def test_cross_from_calc_mode_does_not_come_back_after_markup_work(w):
    QTest.keyClick(w.view, Qt.Key_F12)
    click(w.view, *on_page(w, 0, 100, 120))
    assert cross_shown(w)
    QTest.keyClick(w.view, Qt.Key_F12)                        # Markup mode
    draw_rect_with(w, lambda: QTest.keyClick(w.view, Qt.Key_R))   # R picks Rectangle
    assert len(rects(w)) == 1
    QTest.keyClick(w.view, Qt.Key_Escape)
    QTest.keyClick(w.view, Qt.Key_F12)                        # back to Calc
    assert not cross_shown(w)


def test_a_markup_mode_click_clears_an_old_cross(w):
    QTest.keyClick(w.view, Qt.Key_F12)
    click(w.view, *on_page(w, 0, 100, 120))
    QTest.keyClick(w.view, Qt.Key_F12)                        # Markup mode
    click(w.view, *on_page(w, 0, 300, 300))                   # bare paper
    QTest.keyClick(w.view, Qt.Key_F12)
    assert not cross_shown(w)


def test_markup_insertion_point_goes_when_something_is_drawn(w, blue_point):
    click(w.view, *on_page(w, 0, 120, 140))
    assert w.view._insertion_point is not None
    draw_rect_with(w, lambda: QTest.keyClick(w.view, Qt.Key_R))
    assert len(rects(w)) == 1
    assert w.view._insertion_point is None
    # switching tools alone changes nothing: a fresh click sets it again
    QTest.keyClick(w.view, Qt.Key_V)                          # Select
    click(w.view, *on_page(w, 0, 120, 600))
    assert w.view._insertion_point is not None
    QTest.keyClick(w.view, Qt.Key_E)                          # Ellipse, then V
    QTest.keyClick(w.view, Qt.Key_V)
    assert w.view._insertion_point is not None


def test_panning_keeps_the_marks(w, blue_point):
    click(w.view, *on_page(w, 0, 120, 140))
    assert w.view._insertion_point is not None
    QTest.keyClick(w.view, Qt.Key_V, Qt.ShiftModifier)        # Pan
    drag(w.view, *on_page(w, 0, 300, 300), *on_page(w, 0, 320, 320))
    settle()
    assert w.view._insertion_point is not None
