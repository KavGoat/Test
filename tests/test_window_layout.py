"""The window in less room than a full screen, its toolbars' rows, and a
cloud's outline where it closes (QA, 2026-10-15).

The status bar's fixed controls asked for 1174 px, so the window could not be
made narrower than about 1180 — no half-screen snapping on a 1920 px monitor.
At 1280 px the Calculation bar showed one button of twelve and the markup
tools hid fifteen. A dragged cloud had a hook at its south-east corner.
"""
import math
import sys

import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainterPath, QPolygonF
from PySide6.QtWidgets import QToolBar

from calcforge.items.base import cloud_path


def _settle(qapp, times=6):
    for _ in range(times):
        qapp.processEvents()


def _in_overflow(bar: QToolBar) -> list:
    """The actions a toolbar has put behind its » for want of room."""
    hidden = []
    for action in bar.actions():
        if action.isSeparator() or not action.isVisible():
            continue
        widget = bar.widgetForAction(action)
        if widget is None or not widget.isVisible():
            hidden.append(action)
    return hidden


def _bars(window):
    return {bar.objectName(): bar for bar in window.toolbars}


# ---------------------------------------------------------------------------
# narrow windows
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("size", [(800, 600), (640, 480)])
def test_the_window_can_be_made_half_a_screen_wide(window, qapp, size):
    window.show()
    _settle(qapp)
    window.resize(*size)
    _settle(qapp)
    assert window.width() == size[0]
    assert window.minimumSizeHint().width() <= 640
    assert window.minimumSizeHint().height() <= 600
    if size == (800, 600):
        assert window.height() == 600


def test_a_sheet_page_does_not_hold_the_window_wide(window, qapp):
    window.show()
    window.insert_sheet_page()
    _settle(qapp)
    window.resize(800, 600)
    _settle(qapp)
    assert window.size().toTuple() == (800, 600)


def test_the_status_bar_keeps_page_navigation_and_zoom_at_800(window, qapp):
    window.show()
    _settle(qapp)
    window.resize(800, 600)
    _settle(qapp)
    status = window.statusBar()
    for widget in (window.page_navigation, window.page_spin, window.page_back,
                   window.page_forward, window.zoom_combo):
        assert widget.isVisible(), widget
        assert widget.width() >= min(widget.sizeHint().width(), widget.minimumSizeHint().width())
    # the page navigation is laid out whole, not under its neighbours
    navigation = window.page_navigation.geometry()
    assert navigation.width() >= window.page_navigation.minimumSizeHint().width()
    assert not navigation.intersects(window.zoom_combo.geometry())
    # the coordinates go first; what went is on the » menu
    assert not window.status_position.isVisible()
    assert window.status_position in status.dropped()
    assert window.status_more.isVisible()
    for shown in (w for w in status.children()
                  if getattr(w, "isVisible", None) and w.isVisible()
                  and w.isWidgetType() and not w.isWindow()):
        assert shown.geometry().right() <= status.width() + 1, shown


def test_dropped_status_controls_come_back_with_room(window, qapp):
    window.show()
    _settle(qapp)
    window.resize(700, 600)
    _settle(qapp)
    dropped = window.statusBar().dropped()
    assert window.status_size in dropped and window.window_sync in dropped
    window.status_more.menu().aboutToShow.emit()
    texts = [a.text() for a in window.status_more.menu().actions()]
    assert any(text.startswith("Page Setup") for text in texts)
    assert "Window Sync" in texts
    window.resize(1280, 860)
    _settle(qapp)
    assert window.statusBar().dropped() == []
    for widget in (window.status_position, window.status_size, window.window_sync,
                   window.status_snap, window.status_scroll):
        assert widget.isVisible()
    assert not window.status_more.isVisible()


@pytest.mark.skipif(sys.platform != "win32",
                    reason="the menus are in the system's title bar on Windows only")
def test_the_caption_buttons_room_stays_on_the_menu_row(window, qapp):
    """The menus are drawn in Windows' own title bar: the row keeps room at
    its right for Windows' minimise, maximise and close."""
    if window._native_frame is None:
        pytest.skip("not on Windows' own window system (an offscreen run)")
    window.show()
    _settle(qapp)
    window.resize(640, 480)
    _settle(qapp)
    bar = window.menuBar()
    frame = window._native_frame
    gap = frame.gap
    assert gap.width() > 0
    right = gap.mapTo(bar, gap.rect().topRight()).x()
    assert right <= bar.width()
    # nothing that takes a click sits under the caption buttons
    caption = frame.caption_rect()
    assert not any(rect.intersects(caption) for rect in frame.widget_rects())
    # the search field gave way first, and the menus went behind the » that
    # can be seen
    assert window.search_field.width() < 260
    corner = bar.cornerWidget(Qt.TopRightCorner).geometry()
    assert corner.left() >= bar.cornerWidget(Qt.TopLeftCorner).geometry().right()


def test_the_side_panels_give_up_room_and_get_it_back(window, qapp):
    window.show()
    _settle(qapp)
    wide = {dock: dock.width() for dock in (window.dock_pages, window.dock_properties)}
    window.resize(800, 600)
    _settle(qapp)
    assert window.centralWidget().width() >= 0.38 * window.width()
    window.resize(1280, 860)
    _settle(qapp)
    for dock, width in wide.items():
        assert abs(dock.width() - width) <= 2, dock.objectName()


# ---------------------------------------------------------------------------
# toolbar rows
# ---------------------------------------------------------------------------

def test_the_calculation_bar_shows_every_action_at_1280(window, qapp):
    window.show()
    _settle(qapp)
    assert window.width() == 1280
    bars = _bars(window)
    calculation = bars["toolbar_calculation"]
    assert calculation.isVisible()
    assert _in_overflow(calculation) == []
    for name in ("toolbar_main", "toolbar_tools", "toolbar_measure", "toolbar_style"):
        assert _in_overflow(bars[name]) == [], name
    window.toggle_calc_mode(True)
    _settle(qapp)
    assert _in_overflow(calculation) == []


def test_every_tool_is_still_on_a_toolbar(window):
    on_bars = {action for bar in window.toolbars for action in bar.actions()}
    for key, action in window.tool_actions.items():
        assert action in on_bars, key
    measure = _bars(window)["toolbar_measure"]
    assert window.tool_actions["measure_length"] in measure.actions()
    assert window.act_sticky in _bars(window)["toolbar_tools"].actions()


def test_a_narrow_window_wraps_toolbar_rows_and_unwraps_them(window, qapp):
    window.show()
    _settle(qapp)
    bars = _bars(window)
    main, measure = bars["toolbar_main"], bars["toolbar_measure"]
    assert measure.y() == main.y(), "Main, Calculation and Measure share a row"
    window.resize(800, 600)
    _settle(qapp)
    assert measure.y() > main.y(), "the bar with no room went down a row"
    assert _in_overflow(bars["toolbar_calculation"]) == []
    # the wrapping is not saved as the user's arrangement
    window.restoreState(window.saveState())
    _settle(qapp)
    window.resize(1280, 860)
    _settle(qapp)
    assert measure.y() == main.y()


def test_wrapping_keeps_locking_and_remembered_rows(window, qapp):
    window.show()
    window.lock_toolbars(True)
    _settle(qapp)
    window.resize(800, 600)
    _settle(qapp)
    assert not any(bar.isMovable() for bar in window.toolbars)
    window.lock_toolbars(False)
    assert all(bar.isMovable() for bar in window.toolbars)


def test_an_old_saved_layout_gets_the_new_rows(window, qapp):
    """A layout saved before the Measure bar existed had the Calculation bar
    squeezed beside the markup tools: it is put in the new rows once."""
    from calcforge.settings import app_settings
    bars = _bars(window)
    window.addToolBarBreak()
    window.addToolBar(Qt.TopToolBarArea, bars["toolbar_tools"])
    window.addToolBar(Qt.TopToolBarArea, bars["toolbar_calculation"])
    settings = app_settings()
    settings.setValue("window/state", window.saveState())
    settings.remove("toolbars/rows")
    window.restore_layout()
    window.show()
    _settle(qapp)
    assert bars["toolbar_calculation"].y() == bars["toolbar_main"].y()
    assert _in_overflow(bars["toolbar_calculation"]) == []


# ---------------------------------------------------------------------------
# the cloud
# ---------------------------------------------------------------------------

def _points(path: QPainterPath) -> list:
    return [QPointF(path.elementAt(i).x, path.elementAt(i).y)
            for i in range(path.elementCount())]


def _no_doubling_back(path: QPainterPath) -> None:
    """Where one piece of the outline meets the next, the line may turn
    sharply (a cusp) but never back on itself: a curl drawn backwards — the
    hook — turns it right round."""
    pieces = []          # (start tangent, end tangent) of each piece
    for i in range(path.elementCount()):
        element = path.elementAt(i)
        if element.type == QPainterPath.ElementType.CurveToElement:
            p0 = path.elementAt(i - 1)
            c2, p3 = path.elementAt(i + 1), path.elementAt(i + 2)
            start = (element.x - p0.x, element.y - p0.y)
            end = (p3.x - c2.x, p3.y - c2.y)
            pieces.append((start, end))
        elif element.type == QPainterPath.ElementType.LineToElement:
            p0 = path.elementAt(i - 1)
            if math.hypot(element.x - p0.x, element.y - p0.y) > 1e-6:
                step = (element.x - p0.x, element.y - p0.y)
                pieces.append((step, step))
    assert len(pieces) > 8
    for (_s, came), (went, _e) in zip(pieces, pieces[1:] + pieces[:1]):
        dot = came[0] * went[0] + came[1] * went[1]
        size = math.hypot(*came) * math.hypot(*went)
        assert size > 0
        turn = math.degrees(math.acos(max(-1.0, min(1.0, dot / size))))
        assert turn < 150, f"the outline turns back on itself ({turn:.0f}°)"


@pytest.mark.parametrize("rect", [QRectF(0, 0, 160, 100), QRectF(0, 0, 97, 61),
                                  QRectF(0, 0, 300, 40)])
def test_a_cloud_closes_without_a_hook(rect):
    polygon = QPolygonF([rect.topLeft(), rect.topRight(), rect.bottomRight(),
                         rect.bottomLeft()])
    path = cloud_path(polygon, 10.25)
    points = _points(path)
    assert (points[0] - points[-1]).manhattanLength() < 1e-6
    _no_doubling_back(path)


def test_a_dragged_cloud_closes_without_a_hook(window):
    from tests.test_usability import drag, markups
    from calcforge.items.shapes import RectItem

    window.select_tool("cloud")
    drag(window.view, 100, 100, 260, 200)
    (cloud,) = [item for item in markups(window)
                if isinstance(item, RectItem) and item.kind == "cloud"]
    rect = cloud._rect.normalized()
    path = cloud.hatch_region()
    points = _points(path)
    assert (points[0] - points[-1]).manhattanLength() < 1e-6
    _no_doubling_back(path)


def test_a_clouds_scallops_are_evenly_spaced():
    rect = QRectF(0, 0, 160, 100)
    path = cloud_path(QPolygonF([rect.topLeft(), rect.topRight(), rect.bottomRight(),
                                 rect.bottomLeft()]), 10.25)
    # the cusps along the top: every scallop the same width
    top = sorted(p.x() for p in _points(path)
                 if p.y() < 0 and abs(p.y() + 10.25 * math.sin(math.radians(34))) < 0.6)
    gaps = [b - a for a, b in zip(top, top[1:]) if b - a > 1]
    assert gaps and max(gaps) - min(gaps) < 0.5
