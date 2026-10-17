"""Double-clicking a panel column's edge hides the column, and double-clicking
again brings it back (the user, 2026-10-17), as the Markups List's bar does
(test_markups_list_handle.py). Real double-clicks and drags on QMainWindow's
own separator between the panels and the canvas, and on the thin edge a
hidden column leaves.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

LEFT, RIGHT = "left", "right"


def settle(ms: int = 80):
    timer = QTimer()
    timer.setSingleShot(True)
    timer.start(ms)
    while timer.isActive():
        QApplication.instance().processEvents()


@pytest.fixture
def w(window):
    window.resize(1280, 860)
    window.show()
    window.activateWindow()
    settle()
    return window


def separator(w, side) -> QPoint:
    zone = w.panel_column_edge(side)
    assert zone is not None, f"no {side} column open"
    return zone.center()


def double_click_separator(w, side):
    QTest.mouseDClick(w, Qt.LeftButton, Qt.NoModifier, separator(w, side))
    settle()


@pytest.mark.parametrize("side", [LEFT, RIGHT])
def test_double_clicking_a_column_edge_hides_it_and_its_edge_brings_it_back(w, side):
    dock = w.open_panel_on(side)
    name, width = dock.objectName(), dock.width()
    rail = w.left_rail if side == LEFT else w.right_rail
    edge = w.panel_edges[side]
    assert not edge.isVisible()
    double_click_separator(w, side)
    assert w.open_panel_on(side) is None and dock.isHidden()
    assert not rail.buttons[name].isChecked()            # the rail says so
    assert edge.isVisible() and edge.width() >= 4         # a thin edge stays
    other = w.open_panel_on(RIGHT if side == LEFT else LEFT)
    assert other is not None                              # the other side is left alone
    # double-click the thin edge: back, at its width
    QTest.mouseDClick(edge, Qt.LeftButton, Qt.NoModifier, edge.rect().center())
    settle(150)
    assert w.open_panel_on(side) is dock and rail.buttons[name].isChecked()
    assert abs(dock.width() - width) <= 4, (dock.width(), width)
    assert not edge.isVisible()
    # and once more by its separator
    double_click_separator(w, side)
    assert dock.isHidden()


@pytest.mark.parametrize("side", [LEFT, RIGHT])
def test_dragging_out_from_the_edge_brings_the_column_back(w, side):
    dock = w.open_panel_on(side)
    double_click_separator(w, side)
    edge = w.panel_edges[side]
    start = edge.rect().center()
    out = QPoint(240 if side == LEFT else -240, 0)
    QTest.mousePress(edge, Qt.LeftButton, Qt.NoModifier, start)
    QTest.mouseMove(edge, start + out / 2)
    QTest.mouseRelease(edge, Qt.LeftButton, Qt.NoModifier, start + out)
    settle(150)
    assert not dock.isHidden()
    assert dock.width() >= 200, dock.width()


def drag_separator(w, side, dx):
    at = separator(w, side)
    QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, at)
    for step in range(1, 7):
        QTest.mouseMove(w, at + QPoint(dx * step // 6, 0))
        settle(30)                 # Qt moves the separator on a timer, as a hand does
    QTest.mouseRelease(w, Qt.LeftButton, Qt.NoModifier, at + QPoint(dx, 0))
    settle()


@pytest.mark.parametrize("side", [LEFT, RIGHT])
def test_a_single_drag_on_the_separator_still_resizes(w, side):
    dock = w.open_panel_on(side)
    before = dock.width()
    drag_separator(w, side, 60 if side == LEFT else -60)
    assert not dock.isHidden()
    assert dock.width() >= before + 40, (before, dock.width())
    # and after it has been hidden and brought back by its edge, too
    double_click_separator(w, side)
    QTest.mouseDClick(w.panel_edges[side], Qt.LeftButton, Qt.NoModifier,
                      w.panel_edges[side].rect().center())
    settle(150)
    wide = dock.width()
    assert abs(wide - (before + 60)) <= 8, (wide, before)   # back at the width it was left
    drag_separator(w, side, -40 if side == LEFT else 40)
    assert dock.width() <= wide - 25, (wide, dock.width())


def test_hide_panels_and_the_edges_stay_in_step(w):
    left, right = w.open_panel_on(LEFT), w.open_panel_on(RIGHT)
    double_click_separator(w, LEFT)                       # left gone by its edge
    assert left.isHidden() and not right.isHidden()
    QTest.keyClick(w, Qt.Key_F4, Qt.ShiftModifier)        # Hide Panels: the rest go
    settle()
    assert right.isHidden()
    assert w.panel_edges[LEFT].isVisible() and w.panel_edges[RIGHT].isVisible()
    QTest.keyClick(w, Qt.Key_F4, Qt.ShiftModifier)        # and everything comes back
    settle(150)
    assert not left.isHidden() and not right.isHidden()
    assert not w.panel_edges[LEFT].isVisible() and not w.panel_edges[RIGHT].isVisible()
    # a rail button brings a hidden column back too, and the edge goes
    double_click_separator(w, RIGHT)
    name = right.objectName()
    QTest.mouseClick(w.right_rail.buttons[name], Qt.LeftButton)
    settle()
    assert not right.isHidden() and not w.panel_edges[RIGHT].isVisible()


def test_side_toolbar_columns_are_left_alone(w):
    """A toolbar in a side column of its own keeps it while a panel column
    beside it is hidden and brought back."""
    bar = w.calculation_bar
    w.addToolBar(Qt.LeftToolBarArea, bar)
    settle()
    double_click_separator(w, LEFT)
    assert w.toolBarArea(bar) == Qt.LeftToolBarArea and bar.isVisible()
    QTest.mouseDClick(w.panel_edges[LEFT], Qt.LeftButton, Qt.NoModifier,
                      w.panel_edges[LEFT].rect().center())
    settle(150)
    assert w.toolBarArea(bar) == Qt.LeftToolBarArea
    assert w.dockWidgetArea(w.open_panel_on(LEFT)) == Qt.LeftDockWidgetArea
