"""Toolbars dragged to the window's edges.

The user, 2026-10-21: "Crashed while I was trying to move the alignment
toolbar to the right of the window. Those toolbars (not panel bars) cannot
be between the [panel] bar and the sheet, they must be on the outer side of
the window"; 2026-10-22: "Toolbar move to right or left should show a
preview and move other things out of the way, similar to how it deals with
it at the top."

The panel rails and the panels live in a main window of their own inside
the window (mainwindow._DockHost), so the window's left and right toolbar
areas are at its edges, outside the rails. Qt then previews a side drop as
it does a top one — the gap opening at the window's edge, the rail and the
panels sliding in to make room — and the toolbar lands there; nothing is
rearranged after it. Each toolbar is dragged by its handle with the mouse to
the right and left edges (the panels on that side open, and closed), looked
at while it is still held, let go, and dragged back to the top. Dragging the
Alignment toolbar to the right crashed once: nothing may rearrange the
toolbars while one is held, and nothing does.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QByteArray, QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDockWidget, QMainWindow, QToolBar, QWidget

BARS = ["toolbar_alignment", "toolbar_main", "toolbar_calculation", "toolbar_measure",
        "toolbar_tools", "toolbar_markup_styles", "toolbar_style"]
TOP_ONLY = ("toolbar_style", "toolbar_markup_styles")


def pump(times: int = 4) -> None:
    for _ in range(times):
        QApplication.processEvents()


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.alignment_bar.setVisible(True)
    pump()
    return window


def bar_named(w, name):
    return next(bar for bar in w.toolbars if bar.objectName() == name)


def in_window(w, widget) -> QRect:
    """*widget*'s place in the window's own coordinates."""
    return QRect(widget.mapTo(w, QPoint(0, 0)), widget.size())


def drag(w, bar, to: QPoint, before_letting_go=None) -> None:
    """Take hold of the toolbar's handle and drag it to *to* (window
    coordinates), a step at a time, the event loop running between steps as
    it does under a hand; *before_letting_go()* looks at the window while it
    is still held there; then let go and give it the moment it takes to
    glide into place."""
    handle = QPoint(4, bar.height() // 2) if bar.orientation() == Qt.Horizontal \
        else QPoint(bar.width() // 2, 4)
    QTest.mousePress(bar, Qt.LeftButton, Qt.NoModifier, handle)
    pump(1)
    start = bar.mapTo(w, handle)
    for step in range(1, 13):
        QTest.mouseMove(bar, bar.mapFrom(w, start + (to - start) * step / 12))
        pump(2)
    QTest.qWait(400)              # held there: the gap opens (the docks glide)
    if before_letting_go is not None:
        before_letting_go()
    QTest.mouseRelease(bar, Qt.LeftButton, Qt.NoModifier, bar.mapFrom(w, to))
    QTest.qWait(700)
    pump()


def edge(w, side) -> QPoint:
    return QPoint(w.width() - 3, w.height() // 2) if side == "right" \
        else QPoint(3, w.height() // 2)


def the_rail(w, side):
    return w.right_rail_bar if side == "right" else w.left_rail_bar


def preview_check(w, side, side_capable: bool, out: dict):
    """While the toolbar is held at the edge: Qt's own gap opens at the
    window's edge, and the rail and the panels move in for it — nothing is
    opened beside or under the rail (or, for a toolbar that only goes top or
    bottom, nothing moves at all)."""
    rail_before = in_window(w, the_rail(w, side))
    host_before = in_window(w, w.dock_host)

    def check():
        pump()
        rail_now = in_window(w, the_rail(w, side))
        host_now = in_window(w, w.dock_host)
        assert w.findChild(QWidget, "toolbarDropColumn") is None, "no outline: the room"
        if not side_capable:
            assert (host_now.left(), host_now.right()) == \
                (host_before.left(), host_before.right()), "it only goes top or bottom"
            return
        # the room opened between the window's edge and the rail
        if side == "right":
            gap = QRect(rail_now.right() + 1, rail_now.top(),
                        w.contentsRect().right() - rail_now.right(), rail_now.height())
            assert rail_now.right() < rail_before.right() - 15, "the rail moved in"
        else:
            gap = QRect(w.contentsRect().left(), rail_now.top(),
                        rail_now.left() - w.contentsRect().left(), rail_now.height())
            assert rail_now.left() > rail_before.left() + 15, "the rail moved in"
        assert gap.width() >= 20, "the gap is at the window's edge, outside the rail"
        out["gap"] = gap
        out["picture"] = w.grab()
    return check


def outside_the_rail(w, bar, side) -> bool:
    w.layout().activate()
    rail = in_window(w, the_rail(w, side))
    place = in_window(w, bar)
    if side == "right":
        return place.left() > rail.right()
    return place.right() < rail.left()


def panels_on(w, side) -> list:
    area = Qt.RightDockWidgetArea if side == "right" else Qt.LeftDockWidgetArea
    return [dock for dock in w.panels if dock.isVisible() and not dock.isFloating()
            and w.dockWidgetArea(dock) == area]


@pytest.mark.parametrize("name", BARS)
@pytest.mark.parametrize("side", ["right", "left"])
def test_each_toolbar_dragged_to_a_side_shows_its_gap_and_lands_outside_the_rail(
        w, name, side):
    w.show_panel("dock_properties", True)
    w.show_panel("dock_pages", True)
    pump()
    bar = bar_named(w, name)
    seen = {}
    drag(w, bar, edge(w, side), preview_check(w, side, name not in TOP_ONLY, seen))
    assert not bar.isFloating()
    if name in TOP_ONLY:
        assert w.toolBarArea(bar) == Qt.TopToolBarArea, "it only goes top or bottom"
    else:
        area = Qt.RightToolBarArea if side == "right" else Qt.LeftToolBarArea
        assert w.toolBarArea(bar) == area
        assert outside_the_rail(w, bar, side), "between the window's edge and the rail"
        place = in_window(w, bar)
        # it lands in the gap that was shown
        assert seen["gap"].left() - 3 <= place.left() and place.right() <= \
            seen["gap"].right() + 3
        panels = panels_on(w, side)
        assert panels, "a panel is open on that side"
        for dock in panels:
            where = in_window(w, dock)
            if side == "right":
                assert where.right() < in_window(w, the_rail(w, side)).left()
            else:
                assert where.left() > in_window(w, the_rail(w, side)).right()
    drag(w, bar, QPoint(w.width() // 2, 60))
    assert w.toolBarArea(bar) == Qt.TopToolBarArea and not bar.isFloating()


@pytest.mark.parametrize("side", ["right", "left"])
def test_the_alignment_toolbar_goes_to_a_side_with_its_panels_closed(w, side):
    for dock in w.panels:
        dock.hide()
    pump()
    bar = w.alignment_bar
    drag(w, bar, edge(w, side), preview_check(w, side, True, {}))
    area = Qt.RightToolBarArea if side == "right" else Qt.LeftToolBarArea
    assert w.toolBarArea(bar) == area and outside_the_rail(w, bar, side)
    # a panel opened afterwards opens between the rail and the sheet
    w.show_panel("dock_properties" if side == "right" else "dock_pages", True)
    pump()
    dock = w.dock_properties if side == "right" else w.dock_pages
    assert outside_the_rail(w, bar, side)
    where, rail = in_window(w, dock), in_window(w, the_rail(w, side))
    if side == "right":
        assert where.right() < rail.left()
    else:
        assert where.left() > rail.right()


def test_two_toolbars_on_one_side_both_stay_outside_the_rail(w):
    for name in ("toolbar_alignment", "toolbar_measure"):
        drag(w, bar_named(w, name), edge(w, "right"))
    for name in ("toolbar_alignment", "toolbar_measure"):
        bar = bar_named(w, name)
        assert w.toolBarArea(bar) == Qt.RightToolBarArea and outside_the_rail(w, bar, "right")


def test_an_arrangement_saved_before_the_panels_had_a_host_restores(w):
    """A layout saved by an older CalcForge, in one state holding the
    toolbars and the panels: the Alignment toolbar on the right, Properties
    on the left. It comes back so, the toolbar outside the rail."""
    old = QMainWindow()
    old.setCentralWidget(QWidget())
    for bar in w.toolbars:
        twin = QToolBar(bar.windowTitle())
        twin.setObjectName(bar.objectName())
        old.addToolBar(Qt.RightToolBarArea if bar is w.alignment_bar
                       else Qt.TopToolBarArea, twin)
    for dock in w.panels:
        twin = QDockWidget(dock.windowTitle())
        twin.setObjectName(dock.objectName())
        old.addDockWidget(Qt.LeftDockWidgetArea if dock is w.dock_properties
                          else Qt.RightDockWidgetArea, twin)
    state = old.saveState()
    assert not bytes(state).startswith(w.STATE_MAGIC)
    w.restoreState(state)
    pump()
    assert w.toolBarArea(w.alignment_bar) == Qt.RightToolBarArea
    assert outside_the_rail(w, w.alignment_bar, "right")
    assert w.dockWidgetArea(w.dock_properties) == Qt.LeftDockWidgetArea
    # and the arrangement as it is now saves and comes back the same
    again = w.saveState()
    assert bytes(again).startswith(w.STATE_MAGIC)
    w.reset_layout()
    pump()
    w.restoreState(QByteArray(again))
    pump()
    assert w.toolBarArea(w.alignment_bar) == Qt.RightToolBarArea
    assert w.dockWidgetArea(w.dock_properties) == Qt.LeftDockWidgetArea


def test_reset_layout_puts_every_toolbar_back_as_it_started(w):
    bar = w.alignment_bar
    drag(w, bar, edge(w, "right"))
    assert w.toolBarArea(bar) == Qt.RightToolBarArea
    w.reset_layout()
    pump()
    assert w.toolBarArea(bar) == Qt.TopToolBarArea
    assert bar.isHidden(), "the Alignment toolbar starts hidden, as Revu's"
    for other in w.toolbars:
        if other is not bar:
            assert w.toolBarArea(other) == Qt.TopToolBarArea and other.isVisible()
