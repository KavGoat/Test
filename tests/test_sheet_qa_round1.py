"""QA exercise round 1, the sheet and table findings (docs/qa/exercise_round1.md),
driven as a person drives them: clicks on the cells and headings, the real
right-click menus opened and clicked through, Excel's keys pressed.

- F-03 Paste with nothing on the clipboard: greyed in the menus, a word in
  the status bar for the keys, and never an exception;
- F-13 Ctrl+- and Ctrl++ ask, as Excel does, unless whole rows or columns
  are selected; the cells beside the selection shift;
- F-16 Sort and Remove Duplicates guess the header row as Excel does;
- F-17 Insert Page Break at B2 makes Excel's four pages;
- F-25 the Markups List's Comment column (and its filter) are comments;
- F-26 thumbnails catch up with Undo and with a table at once, and the slot
  line of a paste goes with its undo;
- F-30 the table bar's format box names General and Time.
"""
from __future__ import annotations

import sys
import time

import pytest
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu, QPushButton

from calcforge.items.table import ROWNUM_W
from calcforge.sheet.values import ErrorValue
from tests.test_tables import (cell_scene, click, enter, make_table, pump, tables, type_text,
                               typed, w)  # noqa: F401
from PySide6.QtGui import QContextMenuEvent

CTRL, SHIFT = Qt.ControlModifier, Qt.ShiftModifier


@pytest.fixture
def said(w):
    """What the window said in its status bar, every message in turn."""
    heard = []
    w.view.statusMessage.connect(heard.append)
    return heard


@pytest.fixture
def errors(monkeypatch):
    """Exceptions raised inside Qt's event handlers (they are only printed)."""
    caught = []
    monkeypatch.setattr(sys, "excepthook", lambda kind, value, tb: caught.append(value))
    return caught


def settle(ms=60):
    end = time.perf_counter() + ms / 1000
    while time.perf_counter() < end:
        QApplication.processEvents()
    pump()


def loads(w):
    """A table of Beam 3 / Joist 5 / Post 4 down columns A and B, typed in."""
    table = make_table(w, width=48 * 4, height=15 * 6)
    w.view.tables.select((0, 0))
    for name, number in (("3", "Beam"), ("5", "Joist"), ("4", "Post")):
        type_text(w, name)
        QTest.keyClick(w.view.tables.editor, Qt.Key_Tab)
        pump()
        type_text(w, number)
        enter(w)
        w.view.tables.select((w.view.tables.active[0], 0))
    return table


def _wait_for(condition, limit=2.0):
    """Process events until *condition()* holds (True) or *limit* seconds pass."""
    deadline = time.perf_counter() + limit
    while not condition():
        if time.perf_counter() > deadline:
            return False
        QApplication.processEvents()
        time.sleep(0.005)
    return True


def _menus_showing():
    return [m for m in QApplication.topLevelWidgets() if isinstance(m, QMenu) and m.isVisible()]


def _point_at(menu, action) -> bool:
    """Move the pointer onto *action* the way a hand does, in several small
    steps, and wait until the menu has it under the pointer. QMenu takes a
    click only once the pointer has moved since the menu opened (six moves,
    or more than the drag distance from where the pointer was): one jump
    could land within that distance of where an earlier test left the
    pointer, and the click was ignored (gate af22d2b)."""
    rect = menu.actionGeometry(action)
    centre = rect.center()
    for k in range(8, -1, -1):
        QTest.mouseMove(menu, QPoint(centre.x() - k * max(1, rect.width() // 20), centre.y()))
    return _wait_for(lambda: menu.activeAction() is action, 1.0)


def through_menu(w, open_it, path):
    """Open a real (modal) menu with *open_it* and click through *path* with
    the mouse. Returns (found, enabled, details) of the last entry; a greyed
    one is not clicked and the menu is closed, as a person would.

    The menu driven is the one *open_it* opened (not any popup a test before
    left showing), each submenu is the one its entry opens, and each step
    waits for the menu to be in the state a person would see before the
    next: the entry under the pointer, the submenu shown, the menu closed
    after the click."""
    from tests.test_markup_interaction_round6 import back_to_the_window
    for stale in _menus_showing():
        stale.close()
    back_to_the_window(w)
    before = {id(m) for m in _menus_showing()}
    got = {"found": False, "enabled": None, "clicked": False}

    def close_all():
        for menu in reversed(_menus_showing()):
            menu.close()

    def drive():
        def opened():
            return [m for m in _menus_showing() if id(m) not in before]
        if not _wait_for(lambda: bool(opened())):
            got["error"] = "no menu opened"
            return close_all()
        menu = opened()[0]
        for depth, label in enumerate(path):
            action = next((a for a in menu.actions()
                           if a.text().replace("&", "") == label and a.isVisible()), None)
            if action is None:
                got["found"] = False
                got["entries"] = [a.text() for a in menu.actions()]
                return close_all()
            got["found"], got["enabled"] = True, action.isEnabled()
            if not action.isEnabled():
                return close_all()         # greyed (a greyed submenu greys what is in it)
            if not _point_at(menu, action):
                got["error"] = f"the pointer never rested on {label}"
                return close_all()
            centre = menu.actionGeometry(action).center()
            if depth < len(path) - 1:
                sub = action.menu()
                if not sub.isVisible():
                    QTest.mouseClick(menu, Qt.LeftButton, Qt.NoModifier, centre)
                if not _wait_for(sub.isVisible):
                    got["error"] = f"{label} ▸ did not open"
                    return close_all()
                menu = sub
                continue
            QTest.mouseClick(menu, Qt.LeftButton, Qt.NoModifier, centre)
            got["clicked"] = _wait_for(lambda: not menu.isVisible(), 1.0)
            return close_all()

    QTimer.singleShot(0, drive)
    open_it()
    pump()
    back_to_the_window(w)
    return got["found"], got["enabled"], got


def right_click(view, x, y):
    """A right-click where it is drawn: the viewport gets the context menu event."""
    local = view.mapFromScene(QPointF(x, y))
    QApplication.sendEvent(view.viewport(), QContextMenuEvent(
        QContextMenuEvent.Mouse, local, view.viewport().mapToGlobal(local)))


def right_click_cell(w, table, a1):
    point = cell_scene(table, a1)
    return lambda: right_click(w.view, point.x(), point.y())


def right_click_row_heading(w, table, row):
    rect = table.cell_rect(row, 0)
    point = table.mapToScene(QPointF(rect.left() - ROWNUM_W / 2, rect.center().y()))
    return lambda: right_click(w.view, point.x(), point.y())


# -- F-03 ------------------------------------------------------------------------------------------
def test_paste_with_nothing_on_the_clipboard_is_greyed_and_never_raises(w, errors, said):
    table = loads(w)
    click(w, cell_scene(table, "B2"))
    QApplication.clipboard().clear()
    before = [typed(table, a) for a in ("A1", "B1", "A2", "B2")]
    for path in (["Paste"], ["Paste Special", "Values"], ["Paste Special", "Transpose"]):
        found, enabled, _ = through_menu(w, right_click_row_heading(w, table, 1), path)
        assert found and enabled is False, f"{path} greyed on the row heading"
        found, enabled, _ = through_menu(w, right_click_cell(w, table, "B2"), path)
        assert found and enabled is False, f"{path} greyed on the cell"
    # the keys: nothing happens, and the status bar says why
    QTest.keyClick(w.view, Qt.Key_V, CTRL)
    pump()
    QTest.keyClick(w.view, Qt.Key_V, CTRL | SHIFT)
    pump()
    assert not errors, errors
    assert [typed(tables(w)[0], a) for a in ("A1", "B1", "A2", "B2")] == before
    assert any("Nothing to paste" in m for m in said), said
    # with cells copied the same entries are live and paste
    click(w, cell_scene(table, "A1"))
    QTest.keyClick(w.view, Qt.Key_C, CTRL)
    pump()
    found, enabled, _ = through_menu(w, right_click_cell(w, table, "D1"), ["Paste"])
    assert found and enabled
    assert typed(tables(w)[0], "D1") == "3"
    found, enabled, _ = through_menu(w, right_click_row_heading(w, table, 2),
                                     ["Paste Special", "Values"])
    assert found and enabled and not errors


def test_every_clipboard_reader_copes_with_an_empty_clipboard(w, errors, monkeypatch):
    """QClipboard.mimeData() is None on some platforms when nothing is on it."""
    from PySide6.QtGui import QClipboard
    from calcforge.ui import mainwindow, tableedit
    monkeypatch.setattr(QClipboard, "mimeData", lambda self, mode=None: None)
    assert tableedit.clipboard_formats() == {} and not tableedit.clipboard_has_something()
    assert mainwindow._our_clipboard() is None
    assert w.clipboard_has_image() is False and w._image_from_clipboard() is None
    assert w._clipboard_is_a_foreign_picture() is False
    table = loads(w)
    click(w, cell_scene(table, "B2"))
    assert w.view.tables.paste() is False
    w.paste_items()
    assert not errors


# -- F-13 ------------------------------------------------------------------------------------------
def test_ctrl_minus_on_cells_asks_and_shifts_them_up_as_excel(w):
    table = loads(w)
    wb, s = table.sheet.workbook, table.sheet
    wb.set_input(s, 0, 3, "=B3")          # reads Post, which moves up
    wb.set_input(s, 1, 3, "=B2")          # reads Joist, which goes
    click(w, cell_scene(table, "B2"))
    w._last_data_dialog = None
    QTest.keyClick(w.view, Qt.Key_Minus, CTRL)
    pump()
    dialog = w._last_data_dialog
    assert type(dialog).__name__ == "CellsDialog" and dialog.windowTitle() == "Delete"
    assert [r.text().replace("&", "") for r in dialog.radios.values()] == [
        "Shift cells left", "Shift cells up", "Entire row", "Entire column"]
    assert dialog.choice() == "up", "Excel's guess for one cell"
    assert typed(tables(w)[0], "B2") == "Joist", "nothing is deleted before OK"
    dialog.show()
    pump()
    QTest.mouseClick(dialog.radios["up"], Qt.LeftButton)
    ok = next(b for b in dialog.findChildren(QPushButton) if b.text().replace("&", "") == "OK")
    QTest.mouseClick(ok, Qt.LeftButton)
    pump()
    t = tables(w)[0]
    assert [typed(t, a) for a in ("A1", "A2", "A3", "B1", "B2", "B3")] == [
        "3", "5", "4", "Beam", "Post", ""], "only column B moved up"
    assert typed(t, "D1") == "=B2", "the formula follows Post"
    assert isinstance(t.sheet.value(1, 3), ErrorValue), "the deleted cell: #REF!"
    w.undo_stack.undo()
    t = tables(w)[0]
    assert [typed(t, a) for a in ("B2", "B3", "D1", "D2")] == ["Joist", "Post", "=B3", "=B2"]


def test_ctrl_plus_on_cells_asks_and_shifts_them_right_or_down(w):
    table = loads(w)
    click(w, cell_scene(table, "A2"))
    w._last_data_dialog = None
    QTest.keyClick(w.view, Qt.Key_Plus, CTRL | SHIFT)
    pump()
    dialog = w._last_data_dialog
    assert dialog.windowTitle() == "Insert" and dialog.choice() == "down"
    assert [r.text().replace("&", "") for r in dialog.radios.values()] == [
        "Shift cells right", "Shift cells down", "Entire row", "Entire column"]
    dialog.choose("right")
    dialog.accept()
    t = tables(w)[0]
    assert [typed(t, a) for a in ("A2", "B2", "C2", "A3", "B3")] == ["", "5", "Joist", "4", "Post"]
    # down, from the dialog the cell menu's Insert ▸ Insert Cells… opens
    click(w, cell_scene(t, "B1"))
    w._last_data_dialog = None
    found, enabled, _ = through_menu(w, right_click_cell(w, t, "B1"), ["Insert", "Insert Cells…"])
    assert found and enabled
    dialog = w._last_data_dialog
    assert dialog is not None and dialog.choice() == "down"
    dialog.accept()
    t = tables(w)[0]
    assert [typed(t, a) for a in ("B1", "B2", "B3", "A1")] == ["", "Beam", "5", "3"]
    # a table grows rather than lose cells pushed past its end
    rows = t.size[0]
    t.sheet.workbook.set_input(t.sheet, rows - 1, 1, "last")
    click(w, cell_scene(t, "B1"))
    w.view.tables.insert_or_delete("down", True)
    t = tables(w)[0]
    assert t.size[0] == rows + 1 and t.sheet.input(rows, 1) == "last"


def test_whole_rows_and_columns_go_at_once_and_the_dialog_takes_them_too(w):
    table = loads(w)
    click(w, cell_scene(table, "B1"))
    QTest.keyClick(w.view, Qt.Key_Space, CTRL)       # the whole column
    pump()
    w._last_data_dialog = None
    QTest.keyClick(w.view, Qt.Key_Minus, CTRL)
    pump()
    assert w._last_data_dialog is None, "a whole column is deleted without asking"
    t = tables(w)[0]
    assert [typed(t, a) for a in ("A1", "B1")] == ["3", ""]
    w.undo_stack.undo()
    t = tables(w)[0]
    click(w, cell_scene(t, "A2"))
    QTest.keyClick(w.view, Qt.Key_Space, SHIFT)      # the whole row
    pump()
    QTest.keyClick(w.view, Qt.Key_Plus, CTRL | SHIFT)
    pump()
    assert w._last_data_dialog is None
    t = tables(w)[0]
    assert [typed(t, a) for a in ("A2", "A3")] == ["", "5"]
    # Entire row / Entire column chosen in the dialog
    click(w, cell_scene(t, "A3"))
    w.view.tables.delete_cells().choose("row")
    w._last_data_dialog.accept()
    t = tables(w)[0]
    assert [typed(t, a) for a in ("A2", "A3")] == ["", "4"]
    click(w, cell_scene(t, "A3"))
    w.view.tables.delete_cells().choose("col")
    w._last_data_dialog.accept()
    assert typed(tables(w)[0], "A1") == "Beam"


def test_shifting_through_merged_cells_is_refused(w, said):
    table = loads(w)
    tabs = w.view.tables
    tabs.select((3, 1), (3, 2))           # B4:C4 merged, under B2
    tabs.merge("cells")
    click(w, cell_scene(tables(w)[0], "B2"))
    tabs.insert_or_delete("up", False)    # B4 would move up and C4 not: refused
    assert any("merged" in m for m in said), said
    assert typed(tables(w)[0], "B2") == "Joist"
    said.clear()
    tabs.select((3, 1), (3, 2))
    tabs.merge("unmerge")
    tabs.select((0, 1), (0, 2))           # B1:C1, above: not in the way
    tabs.merge("cells")
    click(w, cell_scene(tables(w)[0], "C2"))
    tabs.insert_or_delete("up", False)
    assert not any("merged" in m for m in said)
    assert tables(w)[0].sheet.merges and (0, 1, 0, 2) in tables(w)[0].sheet.merges


def test_insert_and_delete_cells_are_offered_beside_rows_and_columns(w):
    table = loads(w)
    click(w, cell_scene(table, "B2"))
    menu = w.view.tables.cell_menu()
    sub = {a.text(): a.menu() for a in menu.actions() if a.menu() is not None}
    assert "Insert Cells…" in [a.text() for a in sub["Insert"].actions()]
    assert "Delete Cells…" in [a.text() for a in sub["Delete"].actions()]
    bar_menus = [b.menu() for b in w.findChildren(QPushButton.__mro__[1])
                 if getattr(b, "menu", None) and b.menu() is not None
                 and b.text().replace("&&", "&") == "Rows & Columns"]
    assert bar_menus, "the table bar's Rows & Columns button"
    texts = [a.text() for a in bar_menus[0].actions()]
    assert "Insert Cells…" in texts and "Delete Cells…" in texts
    for action in bar_menus[0].actions():
        if action.text() == "Delete Cells…":
            w._last_data_dialog = None
            action.trigger()
    assert w._last_data_dialog.windowTitle() == "Delete"


# -- F-16 ------------------------------------------------------------------------------------------
def test_sort_z_to_a_sorts_every_row_of_headerless_data(w):
    table = loads(w)
    click(w, cell_scene(table, "B2"))
    found, enabled, _ = through_menu(w, right_click_cell(w, table, "B2"), ["Data", "Sort Z to A"])
    assert found and enabled
    t = tables(w)[0]
    assert [typed(t, f"B{r}") for r in (1, 2, 3)] == ["Post", "Joist", "Beam"]
    assert [typed(t, f"A{r}") for r in (1, 2, 3)] == ["4", "5", "3"]


def test_sort_and_remove_duplicates_dialogs_guess_no_header_and_follow_the_box(w):
    from calcforge.ui import datatools
    table = loads(w)
    click(w, cell_scene(table, "A1"))
    tabs = w.view.tables
    d = datatools.sort_dialog(tabs)
    assert not d.header.isChecked(), "a number in the first row: data, not a heading"
    column = d.rows[0][0]
    assert [column.itemText(i) for i in range(column.count())] == ["Column A", "Column B"]
    d.show()
    pump()
    from PySide6.QtCore import QPoint
    QTest.mouseClick(d.header, Qt.LeftButton, Qt.NoModifier, QPoint(8, d.header.height() // 2))
    assert d.header.isChecked()
    assert [column.itemText(i) for i in range(column.count())] == ["3", "Beam"]
    d.reject()
    r = datatools.duplicates_dialog(tabs)
    assert not r.header.isChecked()
    assert [r.columns.item(i).text() for i in range(r.columns.count())] == ["Column A", "Column B"]
    r.reject()


def test_a_bold_or_text_over_numbers_first_row_is_a_header(w):
    from calcforge.ui import datatools
    table = make_table(w, width=48 * 3, height=15 * 4)
    wb, s = table.sheet.workbook, table.sheet
    for r, (a, b) in enumerate([("Member", "Grade"), ("B1", "S275"), ("B2", "S355")]):
        wb.set_input(s, r, 0, a)
        wb.set_input(s, r, 1, b)
    tabs = w.view.tables
    tabs.open(table, (0, 0))
    assert not datatools._sort_block(tabs)[1], "plain text over plain text: Excel can't tell"
    tabs.select((0, 0), (0, 1))
    QTest.keyClick(w.view, Qt.Key_B, CTRL)            # bold headings
    pump()
    tabs.select((0, 0))
    assert datatools._sort_block(tabs)[1]
    wb.set_input(s, 1, 1, "275")
    tabs.select((0, 0), (0, 1))
    QTest.keyClick(w.view, Qt.Key_B, CTRL)            # plain again; text over a number
    tabs.select((0, 0))
    assert datatools._sort_block(tabs)[1]


# -- F-17 ------------------------------------------------------------------------------------------
def test_insert_page_break_at_b2_makes_excels_four_pages(w):
    from calcforge.items.sheetpage import SheetRunItem
    from calcforge.sheet.pagination import options
    from tests.test_sheet_pages import open_at, sheet_page
    run = sheet_page(w)
    open_at(w, run, "B2")
    pages = len(w.document.pages)
    found, enabled, _ = through_menu(w, right_click_cell(w, run, "B2"),
                                     ["Insert", "Insert Page Break"])
    assert found and enabled
    (run,) = [i for i in w.view.scene().items() if isinstance(i, SheetRunItem)]
    # Excel: above row 2 and left of column B, so A1, B1, A2: and B2: are
    # four pages where there was one
    assert options(run.sheet)["breaks"] == [1] and options(run.sheet)["col_breaks"] == [1]
    assert len(w.document.pages) == pages + 3
    w.undo_stack.undo()
    pump()
    assert len(w.document.pages) == pages
    # a cell in row 1 breaks only to its left: one page more
    (run,) = [i for i in w.view.scene().items() if isinstance(i, SheetRunItem)]
    open_at(w, run, "C1")
    through_menu(w, right_click_cell(w, run, "C1"), ["Insert", "Insert Page Break"])
    assert len(w.document.pages) == pages + 1


# -- F-25 ------------------------------------------------------------------------------------------
def test_the_markups_list_comment_column_holds_comments(w):
    from calcforge.items.shapes import RectItem
    from calcforge.ui.panels import MarkupsPanel
    frame = w.document.pages[0].frame
    plain = RectItem("rect", QRectF(50, 50, 100, 80))
    noted = RectItem("rect", QRectF(200, 50, 100, 80))
    noted.comment = "check bearing"
    frame.add_markup(plain)
    frame.add_markup(noted)
    w.refresh_lists()
    pump()
    panel = w.markups_panel
    comment = MarkupsPanel.COLUMNS.index("Comment")
    value = MarkupsPanel.COLUMNS.index("Value")
    rows = {item.uid: row for _i, item, row in panel.all_rows(w.document)}
    assert rows[plain.uid][comment] == "" and rows[noted.uid][comment] == "check bearing"
    menu = panel.filter_menu(comment)
    entries = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert entries == ["(All)", "(blank)", "check bearing"], entries
    assert all("mm" not in e for e in entries), "no sizes: those are the Value column's"
    assert rows[plain.uid][value] == plain.value_text


# -- F-26 ------------------------------------------------------------------------------------------
def ink(w, row=0):
    image = w.pages_panel.list.item(row).icon().pixmap(96, 128).toImage()
    return sum(1 for y in range(image.height()) for x in range(image.width())
               if image.pixelColor(x, y).green() < 235)


def ink_becomes(w, wanted, limit=1.5):
    """Whether the first thumbnail's ink comes to satisfy *wanted* within
    *limit* seconds (the refresh waits up to 400 ms after an edit)."""
    deadline = time.perf_counter() + limit
    while time.perf_counter() < deadline:
        settle(40)
        if wanted(ink(w)):
            return True
    return wanted(ink(w))


def test_thumbnails_catch_up_with_undo_and_a_table_at_once(w):
    from tests.test_usability import drag
    settle(500)
    blank = ink(w)
    QTest.keyClick(w.view, Qt.Key_R)
    a = w.document.pages[0].frame.mapToScene(QPointF(100, 100))
    b = w.document.pages[0].frame.mapToScene(QPointF(300, 260))
    w.view.centerOn(a)
    drag(w.view, a.x(), a.y(), b.x(), b.y())
    assert ink_becomes(w, lambda n: n > blank)
    drawn = ink(w)
    assert drawn > blank, "the new rectangle shows on its thumbnail"
    QTest.keyClick(w.view, Qt.Key_Z, CTRL)
    # within the longest wait (400 ms; was always 400 ms, and the harness
    # caught it stale), however loaded the machine is
    assert ink_becomes(w, lambda n: n == blank)
    QTest.keyClick(w.view, Qt.Key_Y, CTRL)
    assert ink_becomes(w, lambda n: n == drawn)
    table = make_table(w, x=100, y=400)
    settle(600)                       # the new table drawn in, whatever the wait
    with_table = ink(w)
    click(w, cell_scene(table, "A1"))
    type_text(w, "8888888")
    enter(w)
    assert ink_becomes(w, lambda n: n != with_table), \
        "a value typed in an open table shows (it stayed blank while a table was open)"


def test_the_slot_line_of_pasted_pages_goes_with_their_undo(w):
    w.add_page()
    pump()
    panel = w.pages_panel
    menu = w.page_menu(0)
    copy = next(a for a in menu.actions() if a.text().replace("&", "") == "Copy Pages")
    copy.trigger()
    pump()
    w.paste_page(0)
    pump()
    assert panel.list.external_drop_row == 1, "where the page went, shown"
    QTest.keyClick(w.view, Qt.Key_Z, CTRL)
    pump()
    assert len(w.document.pages) == 2
    assert panel.list.external_drop_row is None, "no line left at the old place"


# -- F-30 ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("keys, shown", [
    ((Qt.Key_AsciiTilde, CTRL | SHIFT), "General"),
    ((Qt.Key_At, CTRL | SHIFT), "Time"),
    ((Qt.Key_NumberSign, CTRL | SHIFT), "Date"),
    ((Qt.Key_Exclam, CTRL | SHIFT), "Number"),
    ((Qt.Key_Dollar, CTRL | SHIFT), "Currency"),
    ((Qt.Key_Percent, CTRL | SHIFT), "Percent"),
    ((Qt.Key_AsciiCircum, CTRL | SHIFT), "Scientific"),
])
def test_the_format_box_names_the_format_the_keys_give(w, keys, shown):
    table = loads(w)
    click(w, cell_scene(table, "A1"))
    QTest.keyClick(w.view, Qt.Key_Percent, CTRL | SHIFT)   # something else first
    pump()
    QTest.keyClick(w.view, *keys)
    pump()
    click(w, cell_scene(tables(w)[0], "A1"))
    assert w.table_controls.number.currentText() == shown


# -- the user, 2026-10-16: "=" and a black unit box stuck on a cell ---------------------------------
def a_sheet(w):
    from tests.test_sheet_pages import open_at, sheet_page
    run = sheet_page(w)
    w.view.set_zoom(1.5)
    open_at(w, run, "A1")
    type_text(w, "7")
    enter(w)
    open_at(w, run, "B2")
    type_text(w, "5 kN")
    enter(w)
    return the_run(w)


def the_run(w):
    from calcforge.items.sheetpage import SheetRunItem
    (run,) = [i for i in w.view.scene().items() if isinstance(i, SheetRunItem)]
    return run


def left_over(w):
    """Editing boxes still showing over the canvas."""
    from calcforge.ui.cellunits import ResultUnit
    from calcforge.ui.tableedit import CellEditor
    return [box for kind in (ResultUnit, CellEditor)
            for box in w.view.viewport().findChildren(kind) if box.isVisible()]


def ink_in(w, run, a1):
    """Dark pixels drawn inside a cell, as the screen shows it."""
    from calcforge.sheet.refs import parse_cell
    settle(80)
    ref = parse_cell(a1)
    rect = run.cell_rect(ref.row, ref.col).adjusted(3, 3, -3, -3)
    box = w.view.mapFromScene(run.mapToScene(rect)).boundingRect()
    image = w.view.viewport().grab(box).toImage()
    return sum(1 for y in range(image.height()) for x in range(image.width())
               if image.pixelColor(x, y).lightness() < 120)


def equals_in_the_unit_box(w, run):
    """Click B2's black unit box (SMath's), type = in it."""
    click(w, cell_scene(run, "B2"))
    kind, rect = run.unit_box_rect(1, 1)
    assert kind == "box"
    click(w, run.mapToScene(rect.center()))
    box = w.view.tables._result_unit
    assert box is not None and box.isVisible()
    QTest.keyClick(box, Qt.Key_Equal, Qt.NoModifier)
    pump()
    assert box.text() == "="


def test_the_unit_box_goes_when_another_cell_or_the_page_is_clicked(w, said):
    run = a_sheet(w)
    equals_in_the_unit_box(w, run)
    click(w, cell_scene(run, "D6"))
    assert not left_over(w), "the box with = in it was left over the cells"
    assert run.sheet.workbook.style_of(run.sheet, 1, 1).unit is None, "= is not a unit"
    assert any("unit" in m.lower() for m in said), said
    equals_in_the_unit_box(w, run)
    click(w, w.document.pages[0].frame.mapToScene(QPointF(300, 300)))
    assert not left_over(w)


def test_delete_clears_a_cell_left_with_equals(w):
    run = a_sheet(w)
    equals_in_the_unit_box(w, run)
    click(w, cell_scene(run, "B2"))
    QTest.keyClick(w.view, Qt.Key_Delete)
    pump()
    assert not left_over(w) and the_run(w).sheet.input(1, 1) == ""
    assert ink_in(w, the_run(w), "B2") == 0
    # "=" typed in the cell itself, Enter, then Delete
    click(w, cell_scene(run, "C3"))
    type_text(w, "=")
    enter(w)
    assert the_run(w).sheet.input(2, 2) == "=" and ink_in(w, the_run(w), "C3") > 0
    click(w, cell_scene(run, "C3"))
    QTest.keyClick(w.view, Qt.Key_Delete)
    pump()
    assert the_run(w).sheet.input(2, 2) == "" and ink_in(w, the_run(w), "C3") == 0


def test_pasting_over_a_cell_left_with_equals_replaces_it(w):
    run = a_sheet(w)
    click(w, cell_scene(run, "A1"))
    QTest.keyClick(w.view, Qt.Key_C, CTRL)
    pump()
    equals_in_the_unit_box(w, run)
    click(w, cell_scene(run, "B2"))
    QTest.keyClick(w.view, Qt.Key_V, CTRL)
    pump()
    assert not left_over(w) and the_run(w).sheet.input(1, 1) == "7"
    click(w, cell_scene(run, "C3"))
    type_text(w, "=")
    QTest.keyClick(w.view.tables.editor, Qt.Key_Tab)
    pump()
    click(w, cell_scene(run, "C3"))
    QTest.keyClick(w.view, Qt.Key_V, CTRL)
    pump()
    assert the_run(w).sheet.input(2, 2) == "7"


def test_deleting_the_row_takes_a_cell_left_with_equals(w):
    run = a_sheet(w)
    equals_in_the_unit_box(w, run)
    click(w, cell_scene(run, "B2"))
    QTest.keyClick(w.view, Qt.Key_Space, SHIFT)
    QTest.keyClick(w.view, Qt.Key_Minus, CTRL)
    pump()
    assert not left_over(w)
    assert the_run(w).sheet.input(1, 1) == "" and ink_in(w, the_run(w), "B2") == 0
    click(w, cell_scene(the_run(w), "C2"))
    type_text(w, "=")
    QTest.keyClick(w.view.tables.editor, Qt.Key_Escape)
    pump()
    assert the_run(w).sheet.input(1, 2) == "", "Esc throws the = away"
    type_text(w, "=")
    enter(w)
    click(w, cell_scene(the_run(w), "C2"))
    QTest.keyClick(w.view, Qt.Key_Space, SHIFT)
    QTest.keyClick(w.view, Qt.Key_Minus, CTRL)
    pump()
    assert the_run(w).sheet.input(1, 2) == "" and not left_over(w)
    assert ink_in(w, the_run(w), "C2") == 0


# -- the user, 2026-10-16: a cell's Variable name and Global at the top of its menu ------------------
def test_a_cells_menu_starts_with_its_variable_name_and_global(w):
    from calcforge.ui import calcsections
    table = loads(w)
    click(w, cell_scene(table, "B2"))
    menu = w.view.tables.cell_menu()
    actions = [a for a in menu.actions() if a.isVisible()]
    holder = actions[0].defaultWidget()
    assert holder.objectName() == "cellVariableRow"
    assert actions[1].text() == "Global (Read by Later Calc Sections)" and actions[1].isCheckable()
    assert actions[2].isSeparator() and actions[3].text() == "Cut", "then Excel's menu, as before"
    labels = [a.text() for a in menu.actions()]
    assert "Make Global" not in labels and "Make Local" not in labels, "Global once, at the top"
    # typed into the box in the real menu, Enter names the cell
    from PySide6.QtWidgets import QLineEdit
    from tests.test_markup_interaction_round6 import back_to_the_window
    for stale in _menus_showing():
        stale.close()
    back_to_the_window(w)
    typed_in = []

    def name_it():
        # the menu this right-click opened: the one holding the Variable box
        def field():
            return next((m.findChild(QLineEdit, "cellVariable") for m in _menus_showing()
                         if m.findChild(QLineEdit, "cellVariable") is not None), None)
        if not _wait_for(lambda: field() is not None and field().hasFocus()):
            typed_in.append("no Variable box with the keys")
            for m in _menus_showing():
                m.close()
            return
        QTest.keyClicks(field(), "P_joist")
        QTest.keyClick(field(), Qt.Key_Return)
        typed_in.append("ok")
    QTimer.singleShot(0, name_it)
    right_click_cell(w, table, "B2")()
    pump()
    back_to_the_window(w)
    assert typed_in == ["ok"], typed_in
    t = tables(w)[0]
    dn = t.sheet.workbook.find_name("P_joist", None)
    assert dn is not None and dn.refers_to.replace("$", "").endswith("!B2")
    # the box shows the name next time; the Name Manager lists it
    click(w, cell_scene(t, "B2"))
    assert w.view.tables.selection_name().name == "P_joist"
    w.view.tables.cell_menu()
    assert w.view.tables.name_field.text() == "P_joist"
    # renamed, then taken away, each one undo step
    assert w.view.tables.name_selection("P_post")
    wb = tables(w)[0].sheet.workbook
    assert wb.find_name("P_post", None) and wb.find_name("P_joist", None) is None
    w.undo_stack.undo()
    wb = tables(w)[0].sheet.workbook
    assert wb.find_name("P_joist", None) and wb.find_name("P_post", None) is None
    click(w, cell_scene(tables(w)[0], "B2"))
    assert w.view.tables.name_selection("")
    assert tables(w)[0].sheet.workbook.find_name("P_joist", None) is None
    # Global, clicked in the real menu
    click(w, cell_scene(tables(w)[0], "B2"))
    found, enabled, _ = through_menu(w, right_click_cell(w, tables(w)[0], "B2"),
                                     ["Global (Read by Later Calc Sections)"])
    assert found and enabled
    t = tables(w)[0]
    assert calcsections.cells_global(t.sheet, [1, 1, 1, 1])
    click(w, cell_scene(t, "B2"))
    menu = w.view.tables.cell_menu()
    assert [a for a in menu.actions() if a.isVisible()][1].isChecked()


# -- findings 5.3: a heading's edge, dragged as in Excel -------------------------------------------
def press_move(w, start, moves):
    """Press at *start* (scene), move through *moves*, not let go yet."""
    from PySide6.QtCore import QEvent
    from tests.test_usability import _mouse
    vp = w.view.viewport()
    QApplication.sendEvent(vp, _mouse(w.view, QEvent.MouseButtonPress, start.x(), start.y()))
    for p in moves:
        QApplication.sendEvent(vp, _mouse(w.view, QEvent.MouseMove, p.x(), p.y(),
                                          Qt.NoButton, Qt.LeftButton))
        pump()


def let_go(w, at):
    from PySide6.QtCore import QEvent
    from tests.test_usability import _mouse
    QApplication.sendEvent(w.view.viewport(),
                           _mouse(w.view, QEvent.MouseButtonRelease, at.x(), at.y()))
    pump()


def test_a_column_edge_drag_shows_a_guide_and_sizes_on_release(w):
    from PySide6.QtWidgets import QToolTip
    run = a_sheet(w)
    sheet = the_run(w).sheet
    xs, ys = run.edges()
    width = sheet.width(1)
    edge = run.mapToScene(QPointF(xs[2], ys[0] - 6))       # B's right edge, in its heading
    end = QPointF(edge.x() + 30, edge.y())
    press_move(w, edge, [QPointF(edge.x() + 10, edge.y()), end])
    te = w.view.tables
    moved = run.mapFromScene(end).x() - run.mapFromScene(edge).x()     # in the sheet's points
    assert sheet.width(1) == width, "Excel: nothing moves until the edge is let go"
    axis, at = te.size_guide
    # (to a screen pixel: the pointer's place is a whole pixel)
    assert axis == "col" and at == pytest.approx(xs[1] + width + moved, abs=1.0), \
        "the dashed line, under the pointer"
    wanted = at - xs[1]
    assert QToolTip.text() == f"Width: {wanted:.2f} pt ({round(wanted * 96 / 72)} pixels)"
    let_go(w, end)
    assert the_run(w).sheet.width(1) == pytest.approx(wanted) and te.size_guide is None
    w.undo_stack.undo()
    assert the_run(w).sheet.width(1) == pytest.approx(width), "one undo step"
    # Esc while dragging leaves it as it was
    run = the_run(w)
    xs, ys = run.edges()
    edge = run.mapToScene(QPointF(xs[2], ys[0] - 6))
    press_move(w, edge, [QPointF(edge.x() + 25, edge.y())])
    QTest.keyClick(w.view, Qt.Key_Escape)
    pump()
    let_go(w, QPointF(edge.x() + 25, edge.y()))
    assert the_run(w).sheet.width(1) == pytest.approx(width) and te.size_guide is None
    # dragged to nothing: hidden, as before
    run = the_run(w)
    xs, ys = run.edges()
    edge = run.mapToScene(QPointF(xs[2], ys[0] - 6))
    press_move(w, edge, [QPointF(edge.x() - width - 10, edge.y())])
    assert QToolTip.text() == "Width: 0 (hidden)"
    let_go(w, QPointF(edge.x() - width - 10, edge.y()))
    assert 1 in the_run(w).sheet.hidden_cols


def test_a_row_edge_drag_in_a_table_shows_a_guide_and_sizes_on_release(w):
    table = loads(w)
    click(w, cell_scene(table, "A1"))
    xs, ys = table.edges()
    height = table.sheet.height(1)
    edge = table.mapToScene(QPointF(-ROWNUM_W / 2, ys[2]))  # row 2's lower edge
    end = QPointF(edge.x(), edge.y() + 12)
    moved = table.mapFromScene(end).y() - table.mapFromScene(edge).y()
    press_move(w, edge, [end])
    te = w.view.tables
    assert table.sheet.height(1) == height
    axis, at = te.size_guide
    # (to a screen pixel: the pointer's place is a whole pixel)
    assert axis == "row" and at == pytest.approx(ys[1] + height + moved, abs=1.0)
    let_go(w, end)
    assert tables(w)[0].sheet.height(1) == pytest.approx(height + moved, abs=1.0)
