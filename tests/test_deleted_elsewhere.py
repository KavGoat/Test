"""Pages deleted in another program (the user, 2026-10-19: "What happens if a
page containing a calculation or spreadsheet or table is deleted in another
editor"; answers by pop-up: offer to restore, being very clear which pages
were deleted and which are being restored; a spreadsheet that lost some of
its pages keeps all its cells, with a warning).

Found before: the first page of a spreadsheet deleted elsewhere took every
cell of the sheet with it, the pages left came back as plain pages, and the
warning named neither the sheet nor the tables that went."""
from __future__ import annotations

import os

import pymupdf
from PySide6.QtCore import QPointF

from calcforge.calc.docsheet import sheet_for
from calcforge.items.sheetpage import run_item_for
from calcforge.items.table import TableItem
from calcforge.ui import sheetpages
from tests.test_calc_saving import equations, reopen, save_to, src, win, write_lines  # noqa: F401


def delete_pages_elsewhere(path, *numbers):
    """Another program deletes pages (0-based) and saves the file."""
    with pymupdf.open(path) as document:
        for number in sorted(numbers, reverse=True):
            document.delete_page(number)
        document.save(path + ".x")
    os.replace(path + ".x", path)


def tables(win):
    return [i for p in win.document.pages for i in p.frame.markups() if isinstance(i, TableItem)]


def a_table_then_an_equation(win):
    win.document.add_page()
    win.rebuild_scenes()
    table = TableItem(1, 1)
    frame = win.document.pages[0].frame
    win.view.begin_snapshot([frame])
    frame.add_markup(table, QPointF(72, 72))
    table.sheet.workbook.set_input(table.sheet, 0, 0, "5")
    table.sheet.workbook.rename_sheet(table.sheet, "Loads")
    win.view.commit_snapshot("table")
    write_lines(win, ["a:Loads.A1", "a="], page=1)


def a_spreadsheet_of_three_pages(win):
    sheetpages.insert_sheet_page(win, 0)
    win.rebuild_scenes()
    first = next(i for i, p in enumerate(win.document.pages) if p.sheet)
    item = run_item_for(win.document.pages[first].frame)
    for row in range(120):
        item.sheet.workbook.set_input(item.sheet, row, 0, str(row + 1))
    for _ in range(2):
        sheetpages.insert_sheet_page(win, first)
        win.rebuild_scenes()
    return [i for i, p in enumerate(win.document.pages) if p.sheet]


def the_sheet(win):
    return next((run_item_for(p.frame) for p in win.document.pages if p.sheet), None)


def test_a_deleted_page_with_a_table_is_named_and_can_be_restored(win, tmp_path):
    a_table_then_an_equation(win)
    path = str(tmp_path / "t.pdf")
    save_to(win, path)
    delete_pages_elsewhere(path, 0)
    reopen(win, path)
    assert tables(win) == []
    (said,) = [w for w in win.document.open_warnings if "deleted in another program" in w]
    assert "page 1" in said and "the table Loads" in said, said
    assert "Restore Pages" in said and "not their markups" in said
    assert win.restore_deleted_pages(ask=False)
    assert [t.sheet.name for t in tables(win)] == ["Loads"]
    assert len(win.document.pages) == 2
    sheet_for(win.document).recalculate()
    (got,) = [i for i in equations(win) if src(i) == "a="]
    assert got.region.error is None
    win.undo_stack.undo()
    assert tables(win) == [] and len(win.document.pages) == 1
    assert win.restore_deleted_pages(ask=False), "undone, it can be restored again"


def test_a_spreadsheets_first_page_deleted_elsewhere_keeps_every_cell(win, tmp_path):
    pages = a_spreadsheet_of_three_pages(win)
    path = str(tmp_path / "s.pdf")
    save_to(win, path)
    delete_pages_elsewhere(path, pages[0])
    reopen(win, path)
    item = the_sheet(win)
    assert item is not None and item.sheet is not None, "the sheet is still a sheet"
    assert len(item.sheet.cells) == 120
    (said,) = [w for w in win.document.open_warnings if "deleted in another program" in w]
    assert f"page {pages[0] + 1}" in said and "keeps all its cells" in said, said
    assert win.restore_deleted_pages(ask=False)
    runs = [run_item_for(p.frame) for p in win.document.pages if p.sheet]
    assert len({id(r) for r in runs if r is not None}) == 1, "one sheet, on its first page"
    assert len(the_sheet(win).sheet.cells) == 120
    assert [i for i, p in enumerate(win.document.pages) if p.sheet][0] == pages[0]


def test_a_spreadsheets_middle_page_deleted_elsewhere_keeps_every_cell_and_says_so(win, tmp_path):
    pages = a_spreadsheet_of_three_pages(win)
    path = str(tmp_path / "m.pdf")
    save_to(win, path)
    delete_pages_elsewhere(path, pages[1])
    reopen(win, path)
    assert len(the_sheet(win).sheet.cells) == 120
    (said,) = [w for w in win.document.open_warnings if "deleted in another program" in w]
    assert "a page of the spreadsheet" in said and "keeps all its cells" in said, said


def a_page_of_equations_and_a_cloud(win):
    from calcforge.items.shapes import RectItem

    win.document.add_page()
    win.rebuild_scenes()
    write_lines(win, ["b:2", "b="], page=0)
    frame = win.document.pages[0].frame
    win.view.begin_snapshot([frame])
    frame.add_markup(RectItem(), QPointF(300, 300))
    win.view.commit_snapshot("rect")


def kinds(win, page):
    return sorted(i.TYPE for i in win.document.pages[page].frame.markups())


def test_restore_brings_back_calcforges_own_not_the_markups(win, tmp_path):
    a_page_of_equations_and_a_cloud(win)
    assert "rect" in kinds(win, 0)
    path = str(tmp_path / "e.pdf")
    save_to(win, path)
    delete_pages_elsewhere(path, 0)
    reopen(win, path)
    assert win.restore_deleted_pages(ask=False)
    assert kinds(win, 0) == ["calc", "calc"], "the equations, not the rectangle"
    assert win.document.pages[0].pdf_key is None, "paper, never the page's drawing"
    win.undo_stack.undo()
    assert win.restore_deleted_pages(ask=False, markups=True)
    assert kinds(win, 0) == ["calc", "calc", "rect"], "ticked: the markups too"


def test_a_page_with_only_markups_is_restored_only_when_asked(win, tmp_path):
    from calcforge.items.shapes import RectItem

    win.document.add_page()
    win.rebuild_scenes()
    frame = win.document.pages[0].frame
    win.view.begin_snapshot([frame])
    frame.add_markup(RectItem(), QPointF(300, 300))
    win.view.commit_snapshot("rect")
    path = str(tmp_path / "r.pdf")
    save_to(win, path)
    delete_pages_elsewhere(path, 0)
    reopen(win, path)
    assert not win.restore_deleted_pages(ask=False)
    assert len(win.document.pages) == 1
    assert win.restore_deleted_pages(ask=False, markups=True)
    assert len(win.document.pages) == 2 and kinds(win, 0) == ["rect"]


def test_a_drawing_calcforge_holds_comes_back_only_when_ticked(win, tmp_path):
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QColor, QImage

    image = QImage(200, 100, QImage.Format_RGB32)
    image.fill(QColor("#3366cc"))
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    win.document.add_page()
    page = win.document.pages[0]
    page.background_key = win.document.put_asset("picture-test", bytes(data))
    win.rebuild_scenes()
    write_lines(win, ["c:3", "c="], page=0)
    path = str(tmp_path / "d.pdf")
    save_to(win, path)
    delete_pages_elsewhere(path, 0)
    reopen(win, path)
    assert win.restore_deleted_pages(ask=False)
    assert win.document.pages[0].background_key is None, "not ticked: paper"
    win.undo_stack.undo()
    assert win.restore_deleted_pages(ask=False, drawing=True)
    assert win.document.pages[0].background_key == "picture-test", "ticked: the picture"
    assert kinds(win, 0) == ["calc", "calc"]


def test_after_saving_there_is_nothing_left_to_restore(win, tmp_path):
    a_table_then_an_equation(win)
    path = str(tmp_path / "t.pdf")
    save_to(win, path)
    delete_pages_elsewhere(path, 0)
    reopen(win, path)
    assert win.document.deleted_elsewhere
    save_to(win, path)
    assert not win.restore_deleted_pages(ask=False)
