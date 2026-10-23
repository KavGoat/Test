"""Toolbars dragged to the window's edges (the user, 2026-10-21: "Crashed
while I was trying to move the alignment toolbar to the right of the window.
Those toolbars (not panel bars) cannot be between the [panel] bar and the
sheet, they must be on the outer side of the window").

Each toolbar is dragged by its handle with the mouse to the right edge and
the left edge — the panels on that side open, and closed — and back to the
top. Dragging the Alignment toolbar to the right crashed: as it hovered over
the side, it stood on end, and the window rearranged its toolbars under it
while Qt's drag still held a pointer into the old arrangement. Now nothing is
rearranged until the toolbar is let go and has landed; then a toolbar on a
side edge has a column of its own between the window's edge and the panel
rail, never between the rail and the sheet. A saved arrangement and Reset
Layout keep to the same rule.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

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
    QTest.qWait(300)              # held there, as a hand pauses before letting go
    if before_letting_go is not None:
        before_letting_go()
    QTest.mouseRelease(bar, Qt.LeftButton, Qt.NoModifier, bar.mapFrom(w, to))
    QTest.qWait(700)
    pump()


def rails(w) -> dict:
    return {Qt.RightToolBarArea: w.right_rail_bar.geometry(),
            Qt.LeftToolBarArea: w.left_rail_bar.geometry()}


def preview_check(w, bar, area, side_capable: bool, out: dict):
    """What is shown while the toolbar is held at the edge: the panel rail
    moved in from the window's edge by the toolbar's width, as the rows along
    the top part for one (the user, 2026-10-22: "the preview wasn't showing
    the panel bar would move") — and no gap opened in the rail's own column
    (Qt's preview of joining it, under the rail)."""
    before = rails(w)

    def check():
        from PySide6.QtWidgets import QWidget
        QTest.qWait(250)                  # the rail glides in
        pump()
        assert w.toolBarArea(bar) != area or not bar.isFloating()
        column = w.findChild(QWidget, "toolbarDropColumn")
        other = Qt.LeftToolBarArea if area == Qt.RightToolBarArea else Qt.RightToolBarArea
        # (lifting a toolbar out of the top rows can take a row away, and
        # everything below moves up: only across must the other side stay)
        def across(box):
            return box.left(), box.right(), box.width()
        assert across(rails(w)[other]) == across(before[other]), "the other side stays put"
        if not side_capable:
            assert column is None or not column.isVisible(), "it only goes top or bottom"
            assert all(across(rails(w)[side]) == across(before[side]) for side in before)
            return
        assert column is not None and column.isVisible(), "the room it will land in is shown"
        shown = column.geometry()
        rail, now = before[area], rails(w)[area]
        edge = w.contentsRect()
        assert 20 <= shown.width() < 2 * rail.width(), "a toolbar's column, nothing wider"
        assert shown.top() == now.top() and shown.height() == now.height()
        assert now.width() == rail.width(), "the rail itself is as it was"
        # the rail has moved in by the room, which is at the window's edge
        if area == Qt.RightToolBarArea:
            assert shown.right() == edge.right() == rail.right()
            assert now.right() == shown.left() - 1
        else:
            assert shown.left() == edge.left() == rail.left()
            assert now.left() == shown.right() + 1
        # and the panels and the canvas with it
        central = w.centralWidget().geometry()
        if area == Qt.RightToolBarArea:
            assert central.right() < now.left()
        else:
            assert central.left() > now.right()
        # marked as the top rows mark the gap a toolbar held over them opens:
        # Qt's gap indicator, the toolbar itself under the pointer
        from PySide6.QtWidgets import QRubberBand
        assert isinstance(column, QRubberBand)
        assert bar.windowOpacity() == 1.0 and bar.isVisible(), "the toolbar held is seen"
        out["shown"] = shown
        out["picture"] = w.grab()
    return check


def outside_the_rail(w, bar, area) -> bool:
    w.layout().activate()
    rail = w.right_rail_bar if area == Qt.RightToolBarArea else w.left_rail_bar
    if area == Qt.RightToolBarArea:
        return bar.geometry().left() >= rail.geometry().right()
    return bar.geometry().right() <= rail.geometry().left()


@pytest.mark.parametrize("name", BARS)
@pytest.mark.parametrize("side", ["right", "left"])
def test_each_toolbar_dragged_to_a_side_lands_outside_the_panel_rail(w, name, side):
    w.show_panel("dock_properties", True)
    w.show_panel("dock_pages", True)
    pump()
    bar = bar_named(w, name)
    edge = QPoint(w.width() - 3, w.height() // 2) if side == "right" \
        else QPoint(3, w.height() // 2)
    area = Qt.RightToolBarArea if side == "right" else Qt.LeftToolBarArea
    seen = {}
    drag(w, bar, edge, preview_check(w, bar, area, name not in TOP_ONLY, seen))
    assert not bar.isFloating()
    if name not in TOP_ONLY:
        # it lands where it was shown it would
        w.layout().activate()
        landed = bar.geometry()
        assert abs(landed.left() - seen["shown"].left()) <= 3
        assert abs(landed.right() - seen["shown"].right()) <= 3
    if name in TOP_ONLY:
        assert w.toolBarArea(bar) == Qt.TopToolBarArea, "it only goes top or bottom"
    else:
        assert w.toolBarArea(bar) == area
        assert outside_the_rail(w, bar, area), "between the window's edge and the rail"
        panels = [dock for dock in w.panels if dock.isVisible() and not dock.isFloating()
                  and w.dockWidgetArea(dock) == (Qt.RightDockWidgetArea if side == "right"
                                                 else Qt.LeftDockWidgetArea)]
        assert panels, "a panel is open on that side"
        for dock in panels:
            if side == "right":
                assert dock.geometry().right() <= bar.geometry().left()
            else:
                assert dock.geometry().left() >= bar.geometry().right()
    drag(w, bar, QPoint(w.width() // 2, 60))
    assert w.toolBarArea(bar) == Qt.TopToolBarArea and not bar.isFloating()


@pytest.mark.parametrize("side", ["right", "left"])
def test_the_alignment_toolbar_goes_to_a_side_with_its_panels_closed(w, side):
    for dock in w.panels:
        dock.hide()
    pump()
    bar = w.alignment_bar
    edge = QPoint(w.width() - 3, w.height() // 2) if side == "right" \
        else QPoint(3, w.height() // 2)
    area = Qt.RightToolBarArea if side == "right" else Qt.LeftToolBarArea
    drag(w, bar, edge, preview_check(w, bar, area, True, {}))
    assert w.toolBarArea(bar) == area and outside_the_rail(w, bar, area)
    # a panel opened afterwards opens between the toolbar's column and the sheet
    w.show_panel("dock_properties" if side == "right" else "dock_pages", True)
    pump()
    dock = w.dock_properties if side == "right" else w.dock_pages
    assert outside_the_rail(w, bar, area)
    if side == "right":
        assert dock.geometry().right() <= bar.geometry().left()
    else:
        assert dock.geometry().left() >= bar.geometry().right()


def test_a_saved_layout_with_a_toolbar_inside_the_rail_is_put_outside(w):
    bar = w.alignment_bar
    # an arrangement from before, with the toolbar between the rail and the
    # sheet: restored, it goes outside the rail
    w.addToolBar(Qt.RightToolBarArea, bar)
    pump()
    state = w.saveState()
    w.restoreState(state)
    pump()
    assert w.toolBarArea(bar) == Qt.RightToolBarArea
    assert outside_the_rail(w, bar, Qt.RightToolBarArea)


def test_reset_layout_puts_every_toolbar_back_as_it_started(w):
    bar = w.alignment_bar
    drag(w, bar, QPoint(w.width() - 3, w.height() // 2))
    assert w.toolBarArea(bar) == Qt.RightToolBarArea
    w.reset_layout()
    pump()
    assert w.toolBarArea(bar) == Qt.TopToolBarArea
    assert bar.isHidden(), "the Alignment toolbar starts hidden, as Revu's"
    for other in w.toolbars:
        if other is not bar:
            assert w.toolBarArea(other) == Qt.TopToolBarArea and other.isVisible()


@pytest.mark.parametrize("side", ["right", "left"])
def test_let_go_at_a_side_it_is_never_seen_back_at_the_top(w, side):
    """The user, 2026-10-22: "the final placement is correct but the
    preview is still wrong, it gets pushed down etc. and then snaps to the
    correct position". Let go at a side edge, Qt puts the toolbar back where
    it came from before it is put in its column: the window is not drawn
    until it is there, and nothing glides."""
    from PySide6.QtCore import QTimer
    bar = bar_named(w, "toolbar_alignment")
    seen = []

    def look():
        if w.updatesEnabled() and not bar.isFloating():
            seen.append(w.toolBarArea(bar))
    timer = QTimer()
    timer.timeout.connect(look)
    timer.start(2)
    edge = QPoint(w.width() - 3, w.height() // 2) if side == "right" else QPoint(3, w.height() // 2)
    area = Qt.RightToolBarArea if side == "right" else Qt.LeftToolBarArea
    drag(w, bar, edge)
    timer.stop()
    assert w.toolBarArea(bar) == area and w.updatesEnabled() and w.isAnimated()
    assert seen and set(seen) == {area}, "drawn only in its column, never back at the top"
    drag(w, bar, QPoint(w.width() // 2, 60))
    assert w.toolBarArea(bar) == Qt.TopToolBarArea


@pytest.mark.parametrize("side", ["right", "left"])
def test_toolbars_share_a_column_on_a_side_as_they_share_a_row_along_the_top(w, side):
    """The user, 2026-10-24: "Doesn't allow me to stack toolbar on the sides,
    only one bar per column, let me join like the top." Dropped over a
    column of toolbars already on a side, a toolbar joins it, where the blue
    gap shows; dropped at the window's very edge it has a column of its own."""
    from PySide6.QtWidgets import QWidget
    area = Qt.RightToolBarArea if side == "right" else Qt.LeftToolBarArea
    edge = QPoint(w.width() - 3, w.height() // 2) if side == "right" else QPoint(3, w.height() // 2)
    first = w.alignment_bar
    drag(w, first, edge)
    assert w.toolBarArea(first) == area
    w.layout().activate()
    column = first.geometry()
    second = bar_named(w, "toolbar_measure")
    under = QPoint(column.center().x(), min(column.bottom() + 30, w.height() - 40))
    gaps = []

    def look():
        gap = getattr(w._toolbar_drags, "join_gap", None)
        gaps.append(gap is not None and gap.isVisible() and gap.geometry())
    drag(w, second, under, look)
    assert gaps and gaps[0], "the blue gap shows where it will go in the column"
    w.layout().activate()
    assert w.toolBarArea(second) == area
    assert second.geometry().x() == first.geometry().x(), "in the same column"
    assert second.geometry().top() > first.geometry().top(), "under the one it was dropped under"
    assert outside_the_rail(w, second, area)
    # the first is not pushed into a column of its own again
    w.arrange_side_toolbars()
    pump()
    w.layout().activate()
    assert second.geometry().x() == first.geometry().x()
    # at the very edge: a column of its own, outside theirs
    third = bar_named(w, "toolbar_tools")
    drag(w, third, edge)
    w.layout().activate()
    assert w.toolBarArea(third) == area
    assert third.geometry().x() != first.geometry().x()
    assert outside_the_rail(w, third, area)
    if side == "right":
        assert third.geometry().left() > first.geometry().right() - 2
    else:
        assert third.geometry().right() < first.geometry().left() + 2
    # kept as they are through a saved layout
    state = w.saveState()
    w.restoreState(state)
    pump()
    w.layout().activate()
    assert second.geometry().x() == first.geometry().x()
