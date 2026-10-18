"""A side panel column's edge, as Revu's (the user, 2026-10-17 and -18):
Revu's blue under the pointer, one click hides the column, one click on the
thin edge it leaves brings it back at its width, a drag sizes it, and a
double-click is two clicks. Real hovers, clicks and drags on the edges, in
the real window.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from calcforge.ui.docks import accent_colour

LEFT, RIGHT = "left", "right"


def settle(ms: int = 80):
    timer = QTimer()
    timer.setSingleShot(True)
    timer.start(ms)
    while timer.isActive():
        QApplication.instance().processEvents()


def wait_apart():
    """Long enough that the next click is a click of its own."""
    settle(QApplication.doubleClickInterval() + 60)


@pytest.fixture
def w(window):
    window.resize(1280, 860)
    window.show()
    window.activateWindow()
    settle()
    return window


def separator(w, side):
    edge = w.panel_separators[side]
    assert edge.isVisible(), f"no {side} column open"
    return edge


def click(widget):
    QTest.mouseClick(widget, Qt.LeftButton, Qt.NoModifier, widget.rect().center())
    settle(120)


def colour_at_middle(widget):
    image = widget.grab().toImage()
    return image.pixelColor(image.width() // 2, image.height() // 2).name()


@pytest.mark.parametrize("side", [LEFT, RIGHT])
def test_a_click_on_a_column_edge_hides_it_and_a_click_brings_it_back(w, side):
    dock = w.open_panel_on(side)
    name, width = dock.objectName(), dock.width()
    rail = w.left_rail if side == LEFT else w.right_rail
    edge = w.panel_edges[side]
    over = separator(w, side)
    # over QMainWindow's own separator, where the column meets the canvas
    zone = w.panel_column_edge(side)
    assert over.geometry().intersects(zone)
    assert not edge.isVisible()
    click(over)
    assert w.open_panel_on(side) is None and dock.isHidden()
    assert not rail.buttons[name].isChecked()            # the rail says so
    assert edge.isVisible() and edge.width() >= 4         # a thin edge stays
    assert not over.isVisible()
    assert w.open_panel_on(RIGHT if side == LEFT else LEFT) is not None   # the other side stays
    wait_apart()
    click(edge)                                           # back, at its width
    assert w.open_panel_on(side) is dock and rail.buttons[name].isChecked()
    assert abs(dock.width() - width) <= 4, (dock.width(), width)
    assert not edge.isVisible() and separator(w, side).isVisible()


@pytest.mark.parametrize("side", [LEFT, RIGHT])
def test_the_edge_is_blue_under_the_pointer(w, side):
    over = separator(w, side)
    QTest.mouseMove(w.view.viewport(), w.view.viewport().rect().center())
    settle()
    assert not over.hovered()
    resting = colour_at_middle(over)
    QTest.mouseMove(over, over.rect().center())                 # enters
    settle()
    assert over.hovered() and colour_at_middle(over) == accent_colour().name()
    assert over.cursor().shape() == Qt.SplitHCursor            # it still drags
    QTest.mouseMove(w.view.viewport(), w.view.viewport().rect().center())   # leaves
    settle()
    assert not over.hovered() and colour_at_middle(over) == resting
    # and the thin edge of a hidden column too
    click(over)
    edge = w.panel_edges[side]
    QTest.mouseMove(edge, edge.rect().center())
    settle()
    assert edge.hovered() and colour_at_middle(edge) == accent_colour().name()


@pytest.mark.parametrize("side", [LEFT, RIGHT])
def test_a_drag_on_the_edge_resizes_and_does_not_hide(w, side):
    dock = w.open_panel_on(side)
    before = dock.width()
    over = separator(w, side)
    at = over.rect().center()
    start = over.mapToGlobal(at)       # the hand moves on the screen; the edge follows it
    out = 60 if side == LEFT else -60
    QTest.mousePress(over, Qt.LeftButton, Qt.NoModifier, at)
    for step in range(1, 7):
        QTest.mouseMove(over, over.mapFromGlobal(start + QPoint(out * step // 6, 0)))
        settle(20)
    QTest.mouseRelease(over, Qt.LeftButton, Qt.NoModifier,
                       over.mapFromGlobal(start + QPoint(out, 0)))
    settle()
    assert not dock.isHidden()                       # a drag, not a click
    assert abs(dock.width() - (before + 60)) <= 6, (before, dock.width())
    assert separator(w, side).geometry().intersects(w.panel_column_edge(side))  # it followed


@pytest.mark.parametrize("side", [LEFT, RIGHT])
def test_dragging_out_from_the_thin_edge_brings_the_column_back(w, side):
    dock = w.open_panel_on(side)
    click(separator(w, side))
    edge = w.panel_edges[side]
    start = edge.rect().center()
    out = QPoint(240 if side == LEFT else -240, 0)
    QTest.mousePress(edge, Qt.LeftButton, Qt.NoModifier, start)
    QTest.mouseMove(edge, start + out / 2)
    QTest.mouseRelease(edge, Qt.LeftButton, Qt.NoModifier, start + out)
    settle(150)
    assert not dock.isHidden()
    assert dock.width() >= 200, dock.width()


@pytest.mark.parametrize("side", [LEFT, RIGHT])
def test_a_double_click_on_the_edge_ends_where_it_started(w, side):
    """The system's double-click: press, release, then the second press as a
    double-click to whatever is under that spot by then (the edge has moved)."""
    dock = w.open_panel_on(side)
    over = separator(w, side)
    at = over.rect().center()
    spot = over.mapToGlobal(at)
    QTest.mousePress(over, Qt.LeftButton, Qt.NoModifier, at)
    QTest.mouseRelease(over, Qt.LeftButton, Qt.NoModifier, at)
    settle(20)
    assert dock.isHidden()
    under = QApplication.widgetAt(spot) or w
    local = QPointF(under.mapFromGlobal(spot))
    for kind, buttons in ((QEvent.MouseButtonDblClick, Qt.LeftButton),
                          (QEvent.MouseButtonRelease, Qt.NoButton)):
        QApplication.sendEvent(under, QMouseEvent(kind, local, QPointF(spot), Qt.LeftButton,
                                                  buttons, Qt.NoModifier))
    settle(150)
    assert not dock.isHidden()                       # two clicks: as it was


def test_hide_panels_and_the_edges_stay_in_step(w):
    left, right = w.open_panel_on(LEFT), w.open_panel_on(RIGHT)
    click(separator(w, LEFT))                         # left gone by its edge
    assert left.isHidden() and not right.isHidden()
    QTest.keyClick(w, Qt.Key_F4, Qt.ShiftModifier)    # Hide Panels: the rest go
    settle()
    assert right.isHidden()
    assert w.panel_edges[LEFT].isVisible() and w.panel_edges[RIGHT].isVisible()
    assert not w.panel_separators[LEFT].isVisible() and not w.panel_separators[RIGHT].isVisible()
    QTest.keyClick(w, Qt.Key_F4, Qt.ShiftModifier)    # and everything comes back
    settle(150)
    assert not left.isHidden() and not right.isHidden()
    assert not w.panel_edges[LEFT].isVisible() and not w.panel_edges[RIGHT].isVisible()
    # a rail button brings a hidden column back too, and the edge goes
    wait_apart()
    click(separator(w, RIGHT))
    name = right.objectName()
    wait_apart()
    QTest.mouseClick(w.right_rail.buttons[name], Qt.LeftButton)
    settle(150)
    assert not right.isHidden() and not w.panel_edges[RIGHT].isVisible()
    assert separator(w, RIGHT).isVisible()


def test_side_toolbar_columns_are_left_alone(w):
    """A toolbar in a side column of its own keeps it while a panel column
    beside it is hidden and brought back."""
    bar = w.calculation_bar
    w.addToolBar(Qt.LeftToolBarArea, bar)
    settle()
    click(separator(w, LEFT))
    assert w.toolBarArea(bar) == Qt.LeftToolBarArea and bar.isVisible()
    wait_apart()
    click(w.panel_edges[LEFT])
    settle(150)
    assert w.toolBarArea(bar) == Qt.LeftToolBarArea
    assert w.dockWidgetArea(w.open_panel_on(LEFT)) == Qt.LeftDockWidgetArea
    assert separator(w, LEFT).geometry().intersects(w.panel_column_edge(LEFT))
