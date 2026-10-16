"""Panels dock on the left or the right, and nowhere else (the user,
2026-10-16).

A panel could be dragged into the middle and left lying over the canvas and
the other panels, or docked along the top. The Markups List keeps the bottom
(it is not a dock). A panel floated with its own float button stays a window
of its own; a drag that ends anywhere but on a side puts it back on its side.
Driven with real drags of the panels' title bars.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

SIDES = (Qt.LeftDockWidgetArea, Qt.RightDockWidgetArea)


def settle(ms: int = 150):
    timer = QTimer()
    timer.setSingleShot(True)
    timer.start(ms)
    while timer.isActive():
        QApplication.instance().processEvents()
    QApplication.instance().processEvents()


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    settle()
    return window


def drag_title(w, dock, target: QPoint):
    """Press on the panel's title, move it to *target* (window coordinates)
    in steps, and let go there."""
    bar = dock.titleBarWidget()
    grip = bar.rect().center() - QPoint(bar.width() // 4, 0)
    QTest.mousePress(bar, Qt.LeftButton, Qt.NoModifier, grip)
    start = bar.mapTo(w, grip)
    for step in (0.25, 0.5, 0.75, 1.0):
        here = start + (target - start) * step
        QTest.mouseMove(bar, bar.mapFromGlobal(w.mapToGlobal(here)))
        QApplication.instance().processEvents()
    QTest.mouseRelease(bar, Qt.LeftButton, Qt.NoModifier,
                       bar.mapFromGlobal(w.mapToGlobal(target)))
    settle()


def test_no_panel_may_dock_along_the_top_or_bottom(w):
    for dock in w.panels:
        assert not dock.isAreaAllowed(Qt.TopDockWidgetArea), dock.objectName()
        assert not dock.isAreaAllowed(Qt.BottomDockWidgetArea), dock.objectName()
        assert dock.isAreaAllowed(Qt.LeftDockWidgetArea)
        assert dock.isAreaAllowed(Qt.RightDockWidgetArea)
        assert w.dockWidgetArea(dock) in SIDES, dock.objectName()


@pytest.mark.parametrize("where", ["top", "middle", "over_thumbnails", "bottom"])
def test_a_dragged_panel_ends_on_a_side(w, where):
    dock = w.dock_properties
    centre = w.view.mapTo(w, w.view.rect().center())
    target = {
        "top": QPoint(centre.x(), 30),
        "middle": centre,
        "over_thumbnails": w.dock_pages.mapTo(w, w.dock_pages.rect().center()),
        "bottom": QPoint(centre.x(), w.height() - 20),
    }[where]
    drag_title(w, dock, target)
    assert not dock.isFloating()                 # not left lying over anything
    assert w.dockWidgetArea(dock) in SIDES
    assert dock.isVisible()
    for other in w.panels:                       # and nothing else moved off a side
        assert other.isFloating() or w.dockWidgetArea(other) in SIDES
    # the Markups List keeps the bottom
    assert w.bottom_split.widget(1) is w.markups_panel


def test_the_float_button_still_floats_a_panel(w):
    dock = w.dock_properties
    button = dock.titleBarWidget().float_button
    QTest.mouseClick(button, Qt.LeftButton)
    settle()
    assert dock.isFloating()                     # on purpose: stays a window
    QTest.mouseClick(button, Qt.LeftButton)      # and back
    settle()
    assert not dock.isFloating() and w.dockWidgetArea(dock) in SIDES


def test_a_saved_arrangement_with_a_panel_on_top_puts_it_on_its_side(w):
    dock = w.dock_search
    w.show_panel("dock_search", True)
    w.addDockWidget(Qt.TopDockWidgetArea, dock)  # as an older arrangement had it
    state = w.saveState()
    w.restoreState(state)
    settle()
    assert w.dockWidgetArea(dock) == Qt.LeftDockWidgetArea


def test_toolbars_keep_their_own_side_columns(w):
    """A toolbar may stand in a column of its own at the side; it never joins
    a panel's column, and moving it moves no panel."""
    bar = w.calculation_bar
    w.addToolBar(Qt.LeftToolBarArea, bar)
    settle()
    assert w.toolBarArea(bar) == Qt.LeftToolBarArea
    assert w.dockWidgetArea(w.dock_pages) == Qt.LeftDockWidgetArea
    # the toolbar's column sits outside the panels' column
    assert bar.geometry().right() <= w.dock_pages.geometry().left() + 1 \
        or not w.dock_pages.isVisible()
    assert not w.dock_pages.geometry().intersects(bar.geometry())
