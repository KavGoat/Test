"""Split View inside one window, document tabs, and File ▸ Open in a tab.

The user, 2026-10-16: "if solo in one window then one; if split in two then
two; each window has one menu" — a split inside one window has one menu bar
and one set of toolbars and panels for both views, which act on the view last
clicked; each view has its own document tabs; Separate Views gives each window
its own menus. Driven with real mouse and key events.
"""
import time

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QMenuBar, QTabBar, QToolBar, QWidget

from calcforge.ui.mainwindow import MainWindow
from tests.test_canvas import wheel
from tests.test_usability import click, drag


def _settle(times=4):
    for _ in range(times):
        QApplication.processEvents()


def _names(window, pane):
    if pane is window._active_pane:
        return [window.document_tabs.tabText(i).rstrip(" •")
                for i in range(window.document_tabs.count())]
    return [pane.tabs.tabText(i).rstrip(" •") for i in range(pane.tabs.count())]


def _pdf(path, pages=1):
    import fitz
    doc = fitz.open()
    for number in range(pages):
        page = doc.new_page(width=420, height=297)
        page.insert_text((40, 60), f"{path.stem} page {number + 1}")
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture
def two_files(window, tmp_path):
    """The window with a.pdf and b.pdf open, each in its own tab (b showing)."""
    a, b = _pdf(tmp_path / "a.pdf"), _pdf(tmp_path / "b.pdf")
    window.show()
    window.activateWindow()
    QTest.qWaitForWindowActive(window)
    window.open_from_command_line(str(a))
    window.open_in_new_tab()
    window.open_from_command_line(str(b))
    _settle()
    return a, b


def _drag_tab(bar, index, target, at):
    """Press on a tab, move straight across to *at* in *target*, let go."""
    start = bar.tabRect(index).center()
    end = bar.mapFromGlobal(target.mapToGlobal(at))
    QTest.mousePress(bar, Qt.LeftButton, Qt.NoModifier, start)
    for share in (0.1, 0.3, 0.6, 1.0):
        QTest.mouseMove(bar, start + (end - start) * share)
        _settle(1)
    QTest.mouseRelease(bar, Qt.LeftButton, Qt.NoModifier, end)
    _settle()


def _zoom_in_by_wheel(view):
    """A notch of the wheel over the view: it zooms (no keys zoom by default,
    the user, 2026-10-18)."""
    wheel(view, 120)


def _split(window):
    window.act_split_view.trigger()
    _settle()
    assert window.is_split
    return window._panes


# -- one window, one set of controls ----------------------------------------

def test_split_view_is_one_window_with_one_menu_bar_and_opens_at_once(window, two_files):
    tops = [w for w in QApplication.topLevelWidgets() if w.isVisible()]
    bars = len(window.findChildren(QToolBar))
    started = time.perf_counter()
    window.act_split_view.trigger()
    QApplication.processEvents()
    took = time.perf_counter() - started
    _settle()
    assert window.is_split and window.act_split_view.isChecked()
    assert took < 0.5, f"Split View took {took:.2f} s"
    left, right = window._panes
    assert left.view.isVisible() and right.view.isVisible()
    assert QWidget.window(left.view) is window and QWidget.window(right.view) is window
    assert len(window.findChildren(QMenuBar)) == 1
    assert len(window.findChildren(QToolBar)) == bars
    assert [w for w in QApplication.topLevelWidgets() if w.isVisible()] == tops
    # each view has its own document tabs
    assert _names(window, left) == ["a.pdf", "b.pdf"]
    assert _names(window, right) == ["b.pdf"]
    window.resize(1400, 860)
    _settle()
    from pathlib import Path
    shots = Path(__file__).resolve().parent.parent / ".split-shots"
    if shots.is_dir():
        window.grab().save(str(shots / "split_view.png"))


def test_the_controls_act_on_the_view_last_clicked(window, two_files):
    left, right = _split(window)
    assert window.view is right.view                 # the new view is the one in hand
    click(left.view, 300, 300)
    assert window.view is left.view and window._active_pane is left
    assert window.document.path.endswith("b.pdf")
    QTest.keyClick(left.view.viewport(), Qt.Key_L)
    assert left.view.tool_key == "line" and right.view.tool_key == "select"
    QTest.keyClick(left.view.viewport(), Qt.Key_Escape)
    click(right.view, 300, 300)
    assert window.view is right.view
    QTest.keyClick(right.view.viewport(), Qt.Key_R)
    assert right.view.tool_key == "rect" and left.view.tool_key == "select"
    QTest.keyClick(right.view.viewport(), Qt.Key_Escape)
    before = left.view.zoom(), right.view.zoom()
    _zoom_in_by_wheel(right.view)
    _settle()
    assert right.view.zoom() > before[1] and left.view.zoom() == before[0]
    # a markup drawn in one view of the same document shows in the other
    window.select_tool("rect")
    drag(right.view, 120, 120, 240, 200)
    assert right.view.frame().markups()
    assert left.view.scene() is right.view.scene()
    # and the window's panels and title follow the view clicked
    click(left.view, 400, 400)
    assert window.windowTitle().startswith("b.pdf")
    QTest.mouseClick(left.tabs, Qt.LeftButton, Qt.NoModifier, left.tabs.tabRect(0).center())
    _settle()
    assert window.document.path.endswith("a.pdf")
    assert window.windowTitle().startswith("a.pdf")
    click(right.view, 300, 300)
    assert window.document.path.endswith("b.pdf")


def test_a_click_on_the_other_views_tab_bar_makes_it_the_one_in_hand(window, two_files):
    left, right = _split(window)
    click(left.view, 300, 300)
    QTest.mouseClick(right.tabs, Qt.LeftButton, Qt.NoModifier, right.tabs.tabRect(0).center())
    _settle()
    assert window._active_pane is right and window.view is right.view


# -- dragging tabs between the views ----------------------------------------

def test_dragging_a_tab_straight_across_moves_the_dragged_document(window, two_files):
    left, right = _split(window)
    click(left.view, 300, 300)                       # b.pdf is showing on the left
    assert window.document.path.endswith("b.pdf")
    # a.pdf's tab, dragged straight across onto the right-hand tab bar
    _drag_tab(left.tabs, 0, right.tabs, right.tabs.rect().center())
    assert _names(window, left) == ["b.pdf"]
    assert sorted(_names(window, right)) == ["a.pdf", "b.pdf"]
    assert window._active_pane is right and window.document.path.endswith("a.pdf")


def test_dragging_a_tab_onto_the_other_views_canvas_moves_it(window, two_files):
    left, right = _split(window)
    click(left.view, 300, 300)
    viewport = right.view.viewport()
    _drag_tab(left.tabs, 0, viewport, viewport.rect().center())
    assert _names(window, left) == ["b.pdf"]
    assert sorted(_names(window, right)) == ["a.pdf", "b.pdf"]
    assert window.document.path.endswith("a.pdf")


def test_dragging_a_views_last_tab_across_ends_the_split_without_copies(window, two_files):
    left, right = _split(window)
    # b.pdf is in both views: the right view's only tab, dragged onto the left
    assert window._active_pane is right
    _drag_tab(right.tabs, 0, left.tabs, left.tabs.rect().center())
    assert not window.is_split and not window.act_split_view.isChecked()
    assert _names(window, window._active_pane) == ["a.pdf", "b.pdf"]
    assert window.document.path.endswith("b.pdf")
    assert window.isWindow()


# -- turning the split off ---------------------------------------------------

def test_closing_a_views_last_tab_turns_the_split_off(window, two_files):
    left, right = _split(window)
    close = right.tabs.tabButton(0, QTabBar.RightSide) or right.tabs.tabButton(0, QTabBar.LeftSide)
    QTest.mouseClick(close, Qt.LeftButton)
    _settle()
    assert not window.is_split and not window.act_split_view.isChecked()
    assert _names(window, window._active_pane) == ["a.pdf", "b.pdf"]


def test_split_view_again_turns_it_off_and_keeps_every_document(window, two_files, tmp_path):
    left, right = _split(window)
    window.open_from_command_line(str(_pdf(tmp_path / "c.pdf")))   # into the right view
    window.open_in_new_tab()
    _settle()
    click(left.view, 300, 300)
    window.act_split_view.trigger()
    _settle()
    assert not window.is_split
    names = _names(window, window._active_pane)
    assert sorted(set(names)) == sorted(names)                    # nothing twice
    assert {"a.pdf", "b.pdf", "c.pdf"} <= set(names)
    assert window.document.path.endswith("b.pdf")                 # still in view


def test_separate_views_gives_each_window_its_own_menus(window, two_files):
    left, right = _split(window)
    click(left.view, 300, 300)
    window.act_separate_views.trigger()
    _settle()
    try:
        assert not window.is_split
        others = [w for w in MainWindow._windows if w is not window and w.isVisible()]
        assert len(others) == 1
        other = others[0]
        assert other.document.path.endswith("b.pdf")
        assert other.menuBar() is not window.menuBar()
        assert _names(window, window._active_pane) == ["a.pdf", "b.pdf"]
    finally:
        for other in [w for w in MainWindow._windows if w is not window]:
            other.confirm_discard = lambda: True
            other.close()
            other.deleteLater()
        _settle()


# -- File ▸ Open in a tab of its own -------------------------------------------

def test_file_open_opens_a_tab_and_reopening_goes_to_it(window, tmp_path, monkeypatch):
    a, b = _pdf(tmp_path / "a.pdf"), _pdf(tmp_path / "b.pdf")
    window.show()
    window.activateWindow()
    QTest.qWaitForWindowActive(window)
    chosen = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *args, **kw: (str(chosen[-1]), "")))
    # the blank Untitled nobody touched is replaced, not kept
    chosen.append(a)
    QTest.keyClick(window.view.viewport(), Qt.Key_O, Qt.ControlModifier)
    _settle()
    assert _names(window, window._active_pane) == ["a.pdf"]
    # a second file comes in beside it, in a tab of its own
    chosen.append(b)
    QTest.keyClick(window.view.viewport(), Qt.Key_O, Qt.ControlModifier)
    _settle()
    assert _names(window, window._active_pane) == ["a.pdf", "b.pdf"]
    assert window.document.path == str(b)
    # opening one already open brings its tab forward
    chosen.append(a)
    QTest.keyClick(window.view.viewport(), Qt.Key_O, Qt.ControlModifier)
    _settle()
    assert _names(window, window._active_pane) == ["a.pdf", "b.pdf"]
    assert window.document.path == str(a) and window._active_tab == 0


def test_file_open_keeps_worked_on_untitled(window, tmp_path, monkeypatch):
    a = _pdf(tmp_path / "a.pdf")
    window.show()
    window.select_tool("rect")
    drag(window.view, 120, 120, 240, 200)            # Untitled has work in it now
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *args, **kw: (str(a), "")))
    window.act_open.trigger()
    _settle()
    assert _names(window, window._active_pane) == ["Untitled", "a.pdf"]
    window.switch_to_document(0)
    assert window.view.frame().markups()


def test_window_sync_moves_the_other_view_of_the_same_document(window, two_files):
    """Document sync repeats a zoom in the other view (by the same factor);
    Page sync gives it the same zoom (and spot on its own page); Sync off
    leaves the zoom each view's own (tests/test_split_sync.py has the rest)."""
    left, right = _split(window)                     # b.pdf in both views
    window.window_sync.setCurrentIndex(2)            # Document sync
    ratio = left.view.zoom() / right.view.zoom()
    _zoom_in_by_wheel(right.view)
    _settle()
    assert left.view.zoom() == pytest.approx(right.view.zoom() * ratio)
    window.window_sync.setCurrentIndex(1)            # Page sync
    _zoom_in_by_wheel(right.view)
    _settle()
    assert left.view.zoom() == pytest.approx(right.view.zoom())
    window.window_sync.setCurrentIndex(0)            # Sync off
    was = left.view.zoom()
    _zoom_in_by_wheel(right.view)
    _settle()
    assert left.view.zoom() == was


def test_a_view_zoomed_while_not_in_hand_stays_as_it_was_left(window, two_files):
    left, right = _split(window)
    left.view.set_zoom(left.view.zoom() * 2)          # e.g. the wheel over it
    wanted = left.view.zoom()
    click(left.view, 300, 300)
    assert window.view is left.view and left.view.zoom() == pytest.approx(wanted)


def test_presentation_shows_only_the_view_in_hand(window, two_files):
    left, right = _split(window)
    window.set_presentation(True)
    _settle()
    try:
        assert right.view.isVisible() and not left.widget.isVisible()
    finally:
        window.set_presentation(False)
        _settle()
    assert left.widget.isVisible() and right.widget.isVisible() and window.is_split


def test_the_formula_bar_goes_with_the_view_in_hand(window, two_files):
    left, right = _split(window)
    bar = window.formula_bar
    assert right.widget.isAncestorOf(bar)
    assert right.layout.indexOf(bar) == right.layout.indexOf(right.tabs) + 1
    assert bar.tables is right.view.tables
    click(left.view, 300, 300)
    assert left.widget.isAncestorOf(bar) and bar.tables is left.view.tables
    assert left.layout.indexOf(bar) == left.layout.indexOf(left.tabs) + 1


def test_typing_in_the_formula_bar_fills_the_cell_of_the_view_in_hand(window, two_files):
    from tests.test_tables import fill_column, key, make_table, shown, typed
    left, right = _split(window)
    window.view.set_zoom(1.0)
    table = make_table(window)                       # in the right-hand view
    fill_column(window, table, ["5 kN", "200 N", "=A1+A2"])
    assert shown(table, "A3") == "5.2 kN"
    key(window, Qt.Key_Up)
    assert window.formula_bar.isVisible() and window.formula_bar.edit.text() == "=A1+A2"
    key(window, Qt.Key_Up)
    key(window, Qt.Key_Up)                            # A1
    edit = window.formula_bar.edit
    edit.setFocus()
    edit.selectAll()
    QTest.keyClicks(edit, "7 kN")
    QTest.keyClick(edit, Qt.Key_Return)
    _settle()
    assert typed(table, "A1") == "7 kN"
    assert shown(table, "A3") == "7.2 kN"
