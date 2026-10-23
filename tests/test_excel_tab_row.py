"""The workbook view's bottom row and zoom as Excel's (docs/qa/excel_audit.md,
A1-A5, C1-C5, H1, K1, F6, M1; the user, 2026-10-22: "the horizontal scroll
at the bottom is very small and not adjustable").

* The tabs take Excel's TabRatio of the row, 0.6 to start; the splitter at
  the scroll bar's left drags it (double-click puts it back), kept with the
  workbook, saved, and read from an Excel file.
* ◀ ▶ at the left scroll the tabs (Ctrl+click to the ends, right-click for
  every sheet), ⊕ after the tabs, the bare names, a name edited on its tab,
  Shift+F11 a sheet before the one shown.
* The thumb is the sheet's size again once scrolled back; the bars have
  arrows; dragging the thumb says the row at the top.
* 100 % is Excel's (a default column 64 px wide); Ctrl+wheel steps 15 %;
  a notch scrolls three rows; nothing between the tabs and the footer.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QMenu, QStyle, QStyleOptionSlider

openpyxl = pytest.importorskip("openpyxl")

from calcforge.items.sheetpage import SheetRunItem  # noqa: E402
from calcforge.ui import sheetpages  # noqa: E402
from calcforge.ui.sheettabs import TAB_RATIO  # noqa: E402
from calcforge.ui.sheetview import EXCEL_SCALE  # noqa: E402
from tests.test_workbook_sections import pump, w  # noqa: E402,F401

_ = w


def sheet_run(w, name=None) -> SheetRunItem:
    return next(i for i in w.view.scene().items() if isinstance(i, SheetRunItem)
                and i.sheet is not None and (name is None or i.sheet.name == name))


def shown_run(w) -> SheetRunItem:
    uid = w.scene.sheet_view
    return next(i for i in w.view.scene().items() if isinstance(i, SheetRunItem)
                and i.uid == uid)


@pytest.fixture
def book(w):
    """A page, then a workbook of three new sheets, shown in the workbook view."""
    sheetpages.insert_sheet_page(w, 0, new_sheet=True)
    pump()
    w.go_to_page(1)
    pump()
    for _ in range(2):
        w.sheet_tabs.new_sheet()
        pump()
    w.go_to_page(1)
    pump()
    assert w.scene.sheet_view is not None
    return w.sheet_tabs


def row_of(tabs):
    return tabs.parentWidget()


# -- A1, A2: the row shared, and its splitter --------------------------------------------------------
def test_the_tabs_take_six_tenths_of_the_row_the_scroll_bar_the_rest(w, book):
    tabs = book
    row = row_of(tabs)
    bar = w.view.horizontalScrollBar()
    assert tabs.width() == pytest.approx(row.width() * TAB_RATIO, abs=2)
    assert bar.width() >= row.width() * 0.35, "the scroll bar keeps its 40 %"
    # more sheets than fit: the tabs take what they need while the row has
    # room, the scroll bar keeping a good length (the user, 2026-10-22: "the
    # sheet tab chip at the bottom did not fully show all the sheets")
    from calcforge.ui.sheettabs import ROOMY_BAR
    for _ in range(6):
        tabs.new_sheet()
        pump()
    row = row_of(tabs)
    assert tabs.width() >= row.width() * TAB_RATIO - 2
    assert tabs.width() == min(max(int(round(row.width() * TAB_RATIO)), tabs.whole_width()),
                               row.width() - ROOMY_BAR) or \
        tabs.width() == pytest.approx(row.width() * TAB_RATIO, abs=2)
    assert w.view.horizontalScrollBar().width() >= ROOMY_BAR - 30


def test_a_tab_keeps_its_width_whichever_sheet_is_shown(w, book):
    """The user, 2026-10-24: "tabs for spreadsheet still buggy, theres so
    much space but it gets cut off". The current tab is drawn bold and grew,
    pushing the last tab out of sight; and the scroll bar kept 200 px."""
    tabs = book
    w.view.tables.rename_to(tabs._item(tabs.entries[1][0]), "Calculations and checks")
    tabs.entries = []
    tabs.refresh()
    pump()
    widths = []
    for k in range(tabs.bar.count()):
        tabs.go(k)
        pump()
        widths.append([tabs.bar.tabRect(i).width() for i in range(tabs.bar.count())])
        assert tabs.clip.width() >= tabs.bar.tabRect(tabs.bar.count() - 1).right(), \
            "every tab in sight, the row having room"
    assert all(row == widths[0] for row in widths), widths


def drag_splitter(w, tabs, dx, double=False):
    splitter = tabs.splitter
    at = splitter.rect().center()
    if double:
        QTest.mouseDClick(splitter, Qt.LeftButton, Qt.NoModifier, at)
        pump()
        return
    start = splitter.mapToGlobal(at)
    QTest.mousePress(splitter, Qt.LeftButton, Qt.NoModifier, at)
    # a hand on the mouse: the same place on the screen, wherever the
    # splitter has moved to under it
    for step in (0.3, 0.7, 1.0):
        QTest.mouseMove(splitter, splitter.mapFromGlobal(start + QPoint(int(dx * step), 0)))
        pump()
    QTest.mouseRelease(splitter, Qt.LeftButton, Qt.NoModifier,
                       splitter.mapFromGlobal(start + QPoint(dx, 0)))
    pump()


def test_the_splitter_drags_the_share_and_is_kept_with_the_workbook(w, book, tmp_path):
    tabs = book
    row = row_of(tabs)
    assert tabs.splitter.cursor().shape() == Qt.SplitHCursor, "Excel's double-headed arrow"
    before = tabs.width()
    drag_splitter(w, tabs, -150)
    assert tabs.width() == pytest.approx(before - 150, abs=3), "the scroll bar gets the room"
    ratio = sheet_run(w).sheet.page["tab_ratio"]
    assert ratio == pytest.approx((before - 150) / row.width(), abs=0.01)
    # every sheet of the workbook keeps it: another sheet shows the same split
    QTest.mouseClick(tabs.bar, Qt.LeftButton, Qt.NoModifier, tabs.bar.tabRect(1).center())
    pump()
    assert tabs.width() == pytest.approx(before - 150, abs=3)
    # saved and opened
    from tests.test_calc_saving import reopen, save_to
    saved = str(tmp_path / "split.pdf")
    save_to(w, saved)
    reopen(w, saved)
    pump()
    w.go_to_page(1)
    pump()
    assert w.sheet_tabs.width() == pytest.approx(row_of(w.sheet_tabs).width() * ratio, abs=3)
    # a double-click puts it back
    drag_splitter(w, w.sheet_tabs, 0, double=True)
    assert w.sheet_tabs.width() == pytest.approx(row_of(w.sheet_tabs).width() * TAB_RATIO,
                                                 abs=2)


def test_an_excel_files_tab_ratio_comes_in_with_it(w, tmp_path):
    path = tmp_path / "Narrow.xlsx"
    book = openpyxl.Workbook()
    book.active.title = "Data"
    book.active["A1"] = 1
    book.create_sheet("More")
    book.views[0].tabRatio = 300
    book.save(path)
    assert w.insert_workbook(str(path), 0)
    pump()
    w.go_to_page(1)
    pump()
    assert sheet_run(w, "Data").sheet.page["tab_ratio"] == pytest.approx(0.3)
    tabs = w.sheet_tabs
    assert tabs.width() == pytest.approx(row_of(tabs).width() * 0.3, abs=2)


# -- C1-C5: Excel's tab row ---------------------------------------------------------------------------
def test_the_arrows_come_first_then_the_tabs_then_new_sheet(w, book):
    tabs = book
    xs = [tabs.back.geometry().x(), tabs.forth.geometry().x(), tabs.clip.geometry().x(),
          tabs.add.geometry().x(), tabs.splitter.geometry().x()]
    assert xs == sorted(xs), "◀ ▶, the tabs, ⊕, … the splitter"
    assert tabs.add.text() == "⊕"
    assert [tabs.bar.tabText(i) for i in range(tabs.bar.count())] == [
        "Sheet1", "Sheet2", "Sheet3"], "the bare names (C4)"
    assert tabs.add.geometry().x() <= tabs.clip.geometry().right() + 6, "⊕ after the last tab"


def test_the_arrows_scroll_the_tabs_and_ctrl_click_goes_to_the_ends(w, book):
    tabs = book
    for _ in range(9):
        tabs.new_sheet()
        pump()
    w.go_to_page(1)
    pump()
    assert tabs.first_shown == 0
    assert tabs.bar.tabRect(tabs.bar.count() - 1).right() > tabs.clip.width(), "they overflow"
    QTest.mouseClick(tabs.forth, Qt.LeftButton)
    pump()
    assert tabs.first_shown == 1 and tabs.clip.offset == tabs.bar.tabRect(1).left()
    QTest.mouseClick(tabs.back, Qt.LeftButton)
    pump()
    assert tabs.first_shown == 0
    QTest.mouseClick(tabs.forth, Qt.LeftButton, Qt.ControlModifier)
    pump()
    last = tabs.bar.count() - 1
    assert tabs.bar.currentIndex() == last and shown_run(w).sheet.name == tabs.entries[last][1]
    rect = tabs.bar.tabRect(last)
    assert rect.right() - tabs.clip.offset <= tabs.clip.width(), "the sheet gone to: in sight"
    QTest.mouseClick(tabs.back, Qt.LeftButton, Qt.ControlModifier)
    pump()
    assert tabs.bar.currentIndex() == 0 and tabs.first_shown == 0


def test_a_right_click_on_the_arrows_lists_every_sheet(w, book):
    tabs = book
    from PySide6.QtCore import QTimer
    seen = {}

    def look():
        menu = QApplication.activePopupWidget()
        if isinstance(menu, QMenu):
            seen["names"] = [a.text() for a in menu.actions()]
            next(a for a in menu.actions() if a.text() == "Sheet3").trigger()
            menu.close()
        else:
            QTimer.singleShot(20, look)
    QTimer.singleShot(30, look)
    at = tabs.back.rect().center()
    from PySide6.QtGui import QContextMenuEvent
    QApplication.sendEvent(tabs.back, QContextMenuEvent(QContextMenuEvent.Mouse, at,
                                                        tabs.back.mapToGlobal(at)))
    QTest.qWait(150)
    pump()
    assert seen["names"] == ["Sheet1", "Sheet2", "Sheet3"]
    assert shown_run(w).sheet.name == "Sheet3"


def test_a_double_click_renames_the_sheet_on_its_tab(w, book):
    tabs = book
    bar = tabs.bar
    QTest.mouseDClick(bar, Qt.LeftButton, Qt.NoModifier, bar.tabRect(1).center())
    pump()
    editor = tabs.editor
    assert isinstance(editor, QLineEdit) and editor.isVisible()
    assert editor.geometry().intersects(bar.tabRect(1)), "on the tab itself"
    assert editor.text() == "Sheet2"
    QTest.keyClicks(editor, "Loads")
    QTest.keyClick(editor, Qt.Key_Return)
    pump()
    assert [n for _u, n in tabs.entries] == ["Sheet1", "Loads", "Sheet3"]
    # Esc leaves it as it was
    QTest.mouseDClick(bar, Qt.LeftButton, Qt.NoModifier, bar.tabRect(2).center())
    pump()
    QTest.keyClicks(tabs.editor, "Nope")
    QTest.keyClick(tabs.editor, Qt.Key_Escape)
    pump()
    assert [n for _u, n in tabs.entries][2] == "Sheet3" and tabs.editor is None


def test_a_name_already_taken_is_refused_with_a_warning(w, book, monkeypatch):
    """The user, 2026-10-22: "when trying to rename a sheet to something
    that's already named, show a warning saying no" (Excel: That name is
    already taken). The tab goes back to editing with the name typed."""
    from PySide6.QtWidgets import QMessageBox
    tabs = book
    bar = tabs.bar
    warned = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda parent, title, text, *a: warned.append(text)))
    w.interactive_prompts = True

    def rename(index, text):
        QTest.mouseDClick(bar, Qt.LeftButton, Qt.NoModifier, bar.tabRect(index).center())
        pump()
        QTest.keyClicks(tabs.editor, text)
        QTest.keyClick(tabs.editor, Qt.Key_Return)
        pump()

    rename(1, "sheet1")             # another's name, in any case
    assert len(warned) == 1 and "already taken" in warned[0] and "Sheet1" in warned[0]
    assert [n for _u, n in tabs.entries] == ["Sheet1", "Sheet2", "Sheet3"]
    editor = tabs.editor
    assert isinstance(editor, QLineEdit) and editor.isVisible(), "back to editing"
    assert editor.text() == "sheet1" and editor.selectedText() == "sheet1"
    assert editor.geometry().intersects(bar.tabRect(1))
    QTest.keyClicks(editor, "Loads (2)")     # typed over: a name of its own
    QTest.keyClick(editor, Qt.Key_Return)
    pump()
    assert [n for _u, n in tabs.entries] == ["Sheet1", "Loads (2)", "Sheet3"]
    assert tabs.editor is None and len(warned) == 1
    # equations write both Loads (2) and Loads_2 as Loads_2: refused too
    rename(2, "Loads_2")
    assert len(warned) == 2 and "Loads_2" in warned[1] and "Loads (2)" in warned[1]
    assert [n for _u, n in tabs.entries][2] == "Sheet3"
    QTest.keyClick(tabs.editor, Qt.Key_Escape)
    pump()
    assert tabs.editor is None and [n for _u, n in tabs.entries][2] == "Sheet3"
    # its own name in another case is no clash
    rename(2, "SHEET3")
    assert len(warned) == 2 and [n for _u, n in tabs.entries][2] == "SHEET3"


def test_shift_f11_inserts_a_sheet_before_the_one_shown(w, book):
    tabs = book
    QTest.mouseClick(tabs.bar, Qt.LeftButton, Qt.NoModifier, tabs.bar.tabRect(1).center())
    pump()
    w.view.setFocus()
    QTest.keyClick(w.view, Qt.Key_F11, Qt.ShiftModifier)
    pump()
    names = [n for _u, n in tabs.entries]
    assert len(names) == 4 and names[0] == "Sheet1" and names[2] == "Sheet2"
    assert shown_run(w).sheet.name == names[1], "the new sheet, shown"


# -- A3-A5: the scroll bars -----------------------------------------------------------------------
def test_the_thumb_grows_back_once_scrolled_back(w, book):
    bar = w.view.verticalScrollBar()
    small = bar.pageStep() / max(1, bar.maximum() - bar.minimum() + bar.pageStep())
    for _ in range(8):
        bar.setValue(bar.maximum())
        pump()
    far = bar.pageStep() / (bar.maximum() - bar.minimum() + bar.pageStep())
    assert far < small / 2, "scrolled far: more grid, a smaller thumb"
    grown = w.scene.sheet_extent[0]
    bar.setValue(bar.minimum())
    pump()
    assert w.scene.sheet_extent[0] < grown / 2, "back at A1: the grid shrinks again"
    back = bar.pageStep() / (bar.maximum() - bar.minimum() + bar.pageStep())
    assert back > far * 2


def test_the_bars_have_arrows_in_the_workbook_view(w, book):
    bar = w.view.verticalScrollBar()
    assert bar.property("sheetView") is True
    option = QStyleOptionSlider()
    bar.initStyleOption(option)
    down = bar.style().subControlRect(QStyle.CC_ScrollBar, option, QStyle.SC_ScrollBarAddLine, bar)
    assert down.height() >= 12, "an arrow button at the bottom"
    value = bar.value()
    QTest.mouseClick(bar, Qt.LeftButton, Qt.NoModifier, down.center())
    pump()
    assert bar.value() > value, "a click on it scrolls"
    w.sheet_tabs.close_sheet_view()
    pump()
    assert not w.view.verticalScrollBar().property("sheetView")


def test_dragging_the_thumb_says_the_row_at_the_top(w, book):
    bar = w.view.verticalScrollBar()
    bar.setValue(bar.maximum())
    pump()
    bar.setValue(bar.minimum())
    pump()
    option = QStyleOptionSlider()
    bar.initStyleOption(option)
    thumb = bar.style().subControlRect(QStyle.CC_ScrollBar, option, QStyle.SC_ScrollBarSlider, bar)
    QTest.mousePress(bar, Qt.LeftButton, Qt.NoModifier, thumb.center())
    QTest.mouseMove(bar, thumb.center() + QPoint(0, 60))
    pump()
    QTest.mouseRelease(bar, Qt.LeftButton, Qt.NoModifier, thumb.center() + QPoint(0, 60))
    pump()
    tip = w.view._sheet_view_watch.last_tip
    assert tip.startswith("Row: ") and int(tip.split()[1]) > 1


# -- H1, K1, F6: Excel's zoom and wheel -------------------------------------------------------------
def test_100_percent_is_the_pages_a_column_as_wide_as_on_its_page(w, book):
    # the user, 2026-10-23: the workbook view's zoom is the pages' (it was
    # Excel's, cells at 96 px an inch, and a sheet's page looked smaller)
    run = shown_run(w)
    w.zoom_combo.setCurrentText("100%")
    w._zoom_chosen(0)
    pump()
    assert w.zoom_combo.currentText() == "100%" and w.zoom_combo.isVisible()
    assert w.view.zoom() == pytest.approx(1.0)
    xs, _ys = run.edges()
    width = w.view.mapFromScene(run.mapToScene(QPointF(xs[1], 0))).x() - \
        w.view.mapFromScene(run.mapToScene(QPointF(xs[0], 0))).x()
    assert width == pytest.approx(48, abs=1), "a default column's 48 points, as on its page"
    # the zoom box's 50 % is the pages' 50 %
    w.zoom_combo.setCurrentText("50%")
    w._zoom_chosen(0)
    pump()
    assert w.view.zoom() == pytest.approx(0.5 * EXCEL_SCALE)
    assert w.zoom_combo.currentText() == "50%"
    # the pages keep their own 100 %
    w.sheet_tabs.close_sheet_view()
    pump()
    w.zoom_combo.setCurrentText("100%")
    w._zoom_chosen(0)
    assert w.view.zoom() == pytest.approx(1.0)


def wheel(w, notches, mods=Qt.NoModifier):
    view = w.view
    at = QPointF(view.viewport().rect().center())
    event = QWheelEvent(at, QPointF(view.viewport().mapToGlobal(at.toPoint())), QPoint(0, 0),
                        QPoint(0, 120 * notches), Qt.NoButton, mods, Qt.NoScrollPhase, False)
    QApplication.sendEvent(view.viewport(), event)
    view.finish_scrolling()
    pump()


def test_ctrl_wheel_steps_fifteen_percent(w, book):
    w.zoom_combo.setCurrentText("100%")
    w._zoom_chosen(0)
    pump()
    shown = []
    for _ in range(2):
        wheel(w, 1, Qt.ControlModifier)
        shown.append(w.zoom_combo.currentText())
    wheel(w, -1, Qt.ControlModifier)
    wheel(w, -1, Qt.ControlModifier)
    wheel(w, -1, Qt.ControlModifier)
    shown.append(w.zoom_combo.currentText())
    assert shown == ["115%", "130%", "85%"]


def test_a_notch_scrolls_three_rows(w, book):
    run = shown_run(w)
    bar = w.view.verticalScrollBar()
    before = bar.value()
    wheel(w, -1)
    rows = (bar.value() - before) / (run.sheet.default_height * w.view.zoom())
    assert rows == pytest.approx(3, abs=0.1)


def test_nothing_between_the_tabs_and_the_footer(w, book):
    split = w.bottom_split
    tabs_bottom = w.sheet_tabs.mapTo(w, w.sheet_tabs.rect().bottomLeft()).y()
    footer_top = w.statusBar().mapTo(w, w.statusBar().rect().topLeft()).y()
    assert split.handleWidth() == 0, "the closed Markups List's bar goes in the workbook view"
    assert footer_top - tabs_bottom <= 3
    w.sheet_tabs.close_sheet_view()
    pump()
    assert split.handleWidth() == 7

