"""A spreadsheet's rows and pages, as Excel has them (the user, 2026-10-17):

- a sheet has as many rows as it has: Insert Row adds one (the rows below
  move down), Delete Row takes one away, ↓ or Enter on the last row adds
  exactly one — never a page's worth;
- its pages follow its rows: a page comes when the rows run past the
  paper's printable height, and a page left with no rows goes;
- with a print area its pages are the print area's and no others — on the
  page, in Thumbnails and in Print — whatever the rows outside it hold.

Driven as a person drives them: the real right-click menus clicked
through, Excel's keys, the print area dragged by its edge; each checked
by the rows, the pages, the thumbnails and what Print would print.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest

from calcforge.items.table import ROWNUM_W
from calcforge.sheet.pagination import options
from tests.test_sheet_pages import open_at, put, runs, sheet_page, w  # noqa: F401
from tests.test_sheet_qa_round1 import right_click, right_click_cell, through_menu
from tests.test_tables import cell_scene, click, pump

CTRL, SHIFT = Qt.ControlModifier, Qt.ShiftModifier


def the_run(w):
    (run,) = runs(w)
    return run


def sheet_pages(w):
    return [p for p in w.document.pages if p.sheet is not None]


def thumbnails(w):
    return w.pages_panel.list.count()


def printed(w):
    """What Print would print of the sheet: for each of its pages in the
    Print dialog, the rows on the paper ([] for a page printing nothing)."""
    dialog = w.open_print_dialog()
    try:
        pages = dialog.printed_pages()
        assert dialog.preview_sheet() is not None, "the preview shows a page"
    finally:
        dialog.close()
    run = the_run(w)
    frames = run.run_frames()
    paging = run.paging
    out = []
    for page in pages:
        if page.sheet is None:
            continue
        k = frames.index(page.frame)
        i, _j = paging.page_of(k)
        a, b = paging.slices[i]
        if paging.print_rows:
            a, b = max(a, paging.print_rows[0]), min(b, paging.print_rows[1])
        out.append((a, b) if a <= b else ())
    return out


def right_click_row_heading(w, run, row):
    rect = run.cell_rect(row, 0)
    point = run.mapToScene(QPointF(rect.left() - ROWNUM_W / 2, rect.center().y()))
    return lambda: right_click(w.view, point.x(), point.y())


def fill(w, run, rows, col=0):
    """Numbers down a column (as a paste would), and the pages they need."""
    from calcforge.ui import sheetpages
    wb, sheet = run.sheet.workbook, run.sheet
    with wb.transaction("Fill"):
        for r in range(rows):
            wb.set_input(sheet, r, col, str(r + 1))
    short = sheetpages.short_runs(w)
    if short:
        sheetpages.add_run_pages(w, short)
    pump()
    w.undo_stack.clear()


# -- rows -------------------------------------------------------------------------------------------
def test_insert_and_delete_row_by_the_heading_menu_change_the_rows_and_pages(w):
    run = sheet_page(w)
    n = run.size[0]                                  # a fresh sheet: a page of rows
    assert len(sheet_pages(w)) == 1 and thumbnails(w) == 2
    open_at(w, run, "A1")
    put(w, run, 0, 1, "=A10")                        # reads a cell below the new row
    put(w, run, 9, 0, "7")
    found, enabled, got = through_menu(w, right_click_row_heading(w, the_run(w), 4),
                                       ["Insert Rows Above"])
    assert found and enabled and got["clicked"]
    run = the_run(w)
    assert run.size[0] == n + 1, "one row more (it stayed the same before)"
    assert run.sheet.input(0, 1) == "=A11" and run.sheet.input(10, 0) == "7"
    assert len(sheet_pages(w)) == 2 and thumbnails(w) == 3, "the row past the page: a page"
    assert run.paging.slices == [(0, n - 1), (n, n)]
    assert printed(w) == [(0, n - 1), (n, n)]
    found, enabled, got = through_menu(w, right_click_row_heading(w, run, 4), ["Delete Rows"])
    assert found and enabled and got["clicked"]
    run = the_run(w)
    assert run.size[0] == n and run.sheet.input(0, 1) == "=A10"
    assert len(sheet_pages(w)) == 1 and thumbnails(w) == 2, "the page left empty goes"
    assert printed(w) == [(0, n - 1)]
    w.undo_stack.undo()                              # one step: the row and its page back
    pump()
    assert the_run(w).size[0] == n + 1 and len(sheet_pages(w)) == 2
    w.undo_stack.undo()
    pump()
    assert the_run(w).size[0] == n and len(sheet_pages(w)) == 1
    assert the_run(w).sheet.input(0, 1) == "=A10"


def test_the_insert_and_delete_dialogs_take_whole_rows_too(w):
    run = sheet_page(w)
    n = run.size[0]
    open_at(w, run, "B3")
    w._last_data_dialog = None
    QTest.keyClick(w.view, Qt.Key_Plus, CTRL | SHIFT)       # Ctrl+Shift+=
    pump()
    dialog = w._last_data_dialog
    assert dialog is not None and dialog.windowTitle() == "Insert"
    dialog.choose("row")
    dialog.accept()
    assert the_run(w).size[0] == n + 1 and len(sheet_pages(w)) == 2
    click(w, cell_scene(the_run(w), "B3"))
    w._last_data_dialog = None
    QTest.keyClick(w.view, Qt.Key_Minus, CTRL)
    pump()
    dialog = w._last_data_dialog
    assert dialog is not None and dialog.windowTitle() == "Delete"
    dialog.choose("row")
    dialog.accept()
    assert the_run(w).size[0] == n and len(sheet_pages(w)) == 1
    # Insert Rows Below on the last row: the sheet's last row is one further
    click(w, cell_scene(the_run(w), f"A{n}"))
    found, enabled, got = through_menu(w, right_click_cell(w, the_run(w), f"A{n}"),
                                       ["Insert", "Insert Rows Below"])
    assert found and enabled and got["clicked"]
    assert the_run(w).size[0] == n + 1


def test_down_and_enter_on_the_last_row_add_one_row_each(w):
    run = sheet_page(w)
    n = run.size[0]
    open_at(w, run, "A1")
    w.view.tables.select((n - 1, 0))
    QTest.keyClick(w.view, Qt.Key_Down)
    pump()
    assert the_run(w).size[0] == n + 1 and w.view.tables.active == (n, 0)
    assert len(sheet_pages(w)) == 2
    QTest.keyClicks(w.view, "x")
    pump()
    QTest.keyClick(w.view.tables.editor, Qt.Key_Return)
    pump()
    assert the_run(w).size[0] == n + 2, "Enter on the last row: one more row, not a page"
    assert the_run(w).paging.slices[-1] == (n, n + 1) and len(sheet_pages(w)) == 2
    assert thumbnails(w) == 3 and printed(w) == [(0, n - 1), (n, n + 1)]
    w.undo_stack.undo()
    pump()
    assert the_run(w).size[0] == n + 1


# -- the print area ---------------------------------------------------------------------------------
def test_a_print_area_has_its_pages_and_no_others(w):
    """The user's bug: three pages of rows, a two-page print area, and three
    thumbnails. It happened whenever rows or cells ran past the print area
    (every page of rows stayed a page, the ones outside printing nothing)."""
    run = sheet_page(w)
    n = run.size[0]
    fill(w, run, 2 * n + 10)                      # three pages of rows
    run = the_run(w)
    assert len(sheet_pages(w)) == 3 and thumbnails(w) == 4
    # Set Print Area on A1:C(n+5), from the cells' right-click menu
    open_at(w, run, "A1")
    w.view.tables.select((0, 0), (n + 5, 2))
    found, enabled, got = through_menu(w, right_click_cell(w, the_run(w), "B2"),
                                       ["Page Layout", "Print Area", "Set Print Area"])
    assert found and enabled and got["clicked"]
    run = the_run(w)
    assert options(run.sheet)["print_area"] == [0, 0, n + 5, 2]
    assert len(sheet_pages(w)) == 2 and thumbnails(w) == 3, "the print area's two pages"
    assert printed(w) == [(0, n - 1), (n, n + 5)]
    assert run.size[0] == 2 * n + 10, "the rows below it are still there, outside the line"
    # its bottom edge dragged down past the next page break: three pages
    from tests.test_usability import drag
    xs, ys = run.edges()
    edge = run.mapToScene(QPointF(xs[1], ys[n + 6]))
    assert w.view.tables.hover_cursor(edge).shape() == Qt.SplitVCursor
    end = run.mapToScene(QPointF(xs[1], ys[2 * n + 3] + 1))
    drag(w.view, edge.x(), edge.y(), end.x(), end.y())
    pump()
    run = the_run(w)
    assert options(run.sheet)["print_area"][2] == 2 * n + 2
    assert len(sheet_pages(w)) == 3 and printed(w) == [(0, n - 1), (n, 2 * n - 1), (2 * n, 2 * n + 2)]
    # dragged back up into the first page: one page
    xs, ys = run.edges()
    edge = run.mapToScene(QPointF(xs[1], ys[2 * n + 3]))
    end = run.mapToScene(QPointF(xs[1], ys[10] + 1))
    drag(w.view, edge.x(), edge.y(), end.x(), end.y())
    pump()
    assert len(sheet_pages(w)) == 1 and thumbnails(w) == 2 and printed(w) == [(0, 9)]
    # rows added inside it, and a page break in it
    open_at(w, the_run(w), "A3")
    found, enabled, got = through_menu(w, right_click_row_heading(w, the_run(w), 2),
                                       ["Insert Rows Above"])
    assert got["clicked"] and options(the_run(w).sheet)["print_area"][2] == 10
    open_at(w, the_run(w), "A6")
    found, enabled, got = through_menu(w, right_click_cell(w, the_run(w), "A6"),
                                       ["Insert", "Insert Page Break"])
    assert got["clicked"]
    assert len(sheet_pages(w)) == 2 and printed(w) == [(0, 4), (5, 10)]
    # Clear Print Area: the pages follow the rows again
    found, enabled, got = through_menu(w, right_click_cell(w, the_run(w), "A2"),
                                       ["Page Layout", "Print Area", "Clear Print Area"])
    assert got["clicked"] and options(the_run(w).sheet)["print_area"] is None
    rows = the_run(w).size[0]
    assert rows == 2 * n + 11
    assert len(sheet_pages(w)) == len(the_run(w).paging.slices) == thumbnails(w) - 1
    assert printed(w)[-1][1] == rows - 1, "every row prints again"
    # each step was one undo
    for _ in range(5):
        w.undo_stack.undo()
        pump()
    run = the_run(w)
    assert options(run.sheet)["print_area"] == [0, 0, n + 5, 2] and len(sheet_pages(w)) == 2
