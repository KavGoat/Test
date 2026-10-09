"""Spreadsheet pages (spreadsheet phase 4), through the real window.

A run of consecutive spreadsheet pages is one sheet that grows a page when
typed past its end; the columns that fit inside the margins print and the
rest is scratch; markups on it move with their cells; pages move, turn and
delete as a run; it prints slice by slice inside the margins and survives a
save and reopen; equations and tables stay off it.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QImage, QPainter

from calcforge.core.document import LANDSCAPE, PORTRAIT
from calcforge.items.sheetpage import SheetRunItem
from calcforge.items.shapes import RectItem
from calcforge.sheet.pagination import options
from calcforge.ui import sheetlayout
from tests.test_tables import cell_scene, click, enter, key, pump, type_text


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.view.set_zoom(1.0)
    return window


def runs(w):
    return [i for i in w.view.scene().items() if isinstance(i, SheetRunItem)]


def sheet_page(w, after=0):
    w.insert_sheet_page(after)
    pump()
    pump()
    (run,) = runs(w)
    return run


def open_at(w, run, a1):
    pos = cell_scene(run, a1)
    w.view.centerOn(pos)
    pump()
    click(w, pos)
    assert w.view.tables.item is run


def put(w, run, row, col, text):
    w.view.tables.select((row, col))
    type_text(w, text)
    enter(w)


def value(run, row, col):
    cell = run.sheet.cells.get((row, col))
    return None if cell is None else cell.value


def box_on(frame, x, y):
    box = RectItem()
    box.set_local_rect(QRectF(0, 0, 30, 12))
    frame.add_markup(box, QPointF(x, y))
    return box


def paper(frame, scale=1.0):
    size = (int(frame.page.width_pt * scale), int(frame.page.height_pt * scale))
    image = QImage(size[0], size[1], QImage.Format_RGB32)
    image.fill(0xFFFFFFFF)
    painter = QPainter(image)
    frame.render_page(painter, QRectF(0, 0, size[0], size[1]), for_print=True)
    painter.end()
    return image


def ink_box(image):
    import numpy as np
    a = np.frombuffer(image.constBits(), np.uint8).reshape(
        image.height(), image.bytesPerLine() // 4, 4)[:, :image.width(), :3].mean(axis=2)
    ys, xs = np.nonzero(a < 200)
    if len(xs) == 0:
        return None
    return xs.min(), ys.min(), xs.max(), ys.max()


# -- making one -----------------------------------------------------------------------------------
def test_a_sheet_page_is_a_page_of_cells_with_scratch_to_its_right(w):
    run = sheet_page(w)
    page = w.document.pages[1]
    assert page.sheet == run.uid
    assert run.parentItem() is page.frame
    paging = run.paging
    assert (paging.first_col, paging.last_col) == (0, 10)       # A to K print on A4
    rect = page.frame.page_rect()
    xs, ys = run.edges()
    assert rect.width() == pytest.approx(xs[paging.shown_cols])  # printed + scratch
    assert rect.width() > page.setup.width_pt
    assert rect.height() == pytest.approx(ys[52])                # 52 rows on the page
    # the ordinary page before it is still paper
    assert w.document.pages[0].frame.page_rect().width() == pytest.approx(
        w.document.pages[0].setup.width_pt)
    # one undo step takes it away again
    w.undo_stack.undo()
    pump()
    assert len(w.document.pages) == 1 and not runs(w)


def test_clicks_go_to_the_cells_in_markup_mode_and_markups_win(w):
    run = sheet_page(w)
    assert not w.view.calc.calc_mode()
    open_at(w, run, "B2")
    assert w.view.tables.active == (1, 1)
    type_text(w, "12.5")
    enter(w)
    assert value(run, 1, 1) == 12.5
    w.view.tables.close()
    # a markup over the cells is picked, not the cell under it
    frame = w.document.pages[1].frame
    box = box_on(frame, *(run.cell_rect(5, 2).topLeft() + QPointF(2, 2)).toTuple())
    pos = box.mapToScene(box.local_rect().center())
    click(w, pos)
    assert w.view.tables.item is None
    assert box.isSelected()


def test_typing_past_the_last_page_adds_one_in_the_same_undo_step(w):
    run = sheet_page(w)
    open_at(w, run, "A1")
    w.view.tables.select((51, 0))
    key(w, Qt.Key_Down)
    assert w.view.tables.active == (52, 0), "one row past the last page can be typed in"
    type_text(w, "next")
    enter(w)
    assert len(w.document.pages) == 3
    assert [p.sheet for p in w.document.pages[1:]] == [run.uid, run.uid]
    (run,) = runs(w)
    assert value(run, 52, 0) == "next"
    assert run.paging.slices[1][0] == 52
    # page 2 sits right under page 1: one continuous grid
    f1, f2 = (w.document.pages[i].frame for i in (1, 2))
    assert f2.scenePos().y() == pytest.approx(f1.scenePos().y() + f1.page_rect().height())
    w.undo_stack.undo()
    pump()
    assert len(w.document.pages) == 2
    (run,) = runs(w)
    assert value(run, 52, 0) is None
    w.undo_stack.redo()
    pump()
    assert len(w.document.pages) == 3


def test_empty_pages_at_the_end_are_kept(w):
    run = sheet_page(w)
    w.insert_sheet_page(1)              # one more page of the same sheet
    pump()
    assert [p.sheet for p in w.document.pages] == [None, run.uid, run.uid]
    (run,) = runs(w)
    assert run.paging.pages == 2
    w.rebuild_scenes()
    assert len(w.document.pages) == 3


# -- markups move with their cells ------------------------------------------------------------------
def test_markups_move_with_inserted_rows_even_onto_the_next_page(w):
    run = sheet_page(w)
    w.insert_sheet_page(1)
    pump()
    (run,) = runs(w)
    f1 = w.document.pages[1].frame
    near_end = run.cell_rect(50, 3).topLeft() + QPointF(4, 3)
    box = box_on(f1, near_end.x(), near_end.y())
    open_at(w, run, "A10")
    w.view.tables.select((9, 0), (13, 0))      # five rows above the markup
    w.view.tables.insert_rows()
    pump()
    f2 = w.document.pages[2].frame
    assert box.parentItem() is f2, "row 51 moved to row 56: the second page"
    where = run.mapFromScene(box.scenePos())
    target = run.cell_rect(55, 3).topLeft() + QPointF(4, 3)
    assert where.x() == pytest.approx(target.x(), abs=0.01)
    assert where.y() == pytest.approx(target.y(), abs=0.01)
    w.undo_stack.undo()
    pump()
    (box2,) = [m for m in w.document.pages[1].frame.markups() if isinstance(m, RectItem)]
    assert box2.pos().y() == pytest.approx(near_end.y())


def test_a_taller_row_pushes_the_markups_below_it_down(w):
    run = sheet_page(w)
    frame = w.document.pages[1].frame
    start = run.cell_rect(20, 1).topLeft()
    box = box_on(frame, start.x(), start.y())
    open_at(w, run, "A5")
    w.view.tables.set_size("row", 40.0)
    pump()
    (run,) = runs(w)
    assert run.mapFromScene(box.scenePos()).y() == pytest.approx(run.cell_rect(20, 1).top())
    assert run.cell_rect(20, 1).top() > start.y()


# -- pages of a run ---------------------------------------------------------------------------------
def test_nothing_goes_between_the_pages_of_a_run(w):
    run = sheet_page(w)
    w.insert_sheet_page(1)
    pump()
    w.add_page(1)                        # "after page 2", the run's first page
    pump()
    assert [p.sheet is not None for p in w.document.pages] == [False, True, True, False]
    # a reorder that would split it is refused; the whole run can move
    w.move_page(2, 0)
    assert [p.sheet is not None for p in w.document.pages] == [False, True, True, False]
    w.move_page(1, 0, 2)
    assert [p.sheet is not None for p in w.document.pages] == [True, True, False, False]
    (run,) = runs(w)
    assert run.parentItem() is w.document.pages[0].frame


def test_deleting_a_page_of_a_run_takes_its_rows(w, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    run = sheet_page(w)
    w.insert_sheet_page(1)
    w.insert_sheet_page(1)
    pump()
    (run,) = runs(w)
    wb = run.sheet.workbook
    wb.set_input(run.sheet, 0, 0, "first")
    wb.set_input(run.sheet, 60, 0, "second")
    wb.set_input(run.sheet, 110, 0, "third")
    f3 = w.document.pages[3].frame
    box = box_on(f3, *(run.cell_rect(110, 2).topLeft() - QPointF(0, run._tops[2])).toTuple())
    w.delete_page(1)                     # the run's first page: rows 1–52 go
    pump()
    (run,) = runs(w)
    assert len(w.document.pages) == 3
    assert run.parentItem() is w.document.pages[1].frame
    assert value(run, 0, 0) is None
    assert value(run, 8, 0) == "second"
    assert value(run, 58, 0) == "third"
    # the markup kept to its cell, now on the run's second page
    assert box.parentItem() is w.document.pages[2].frame
    assert run.mapFromScene(box.scenePos()).y() == pytest.approx(run.cell_rect(58, 2).top())
    w.undo_stack.undo()
    pump()
    (run,) = runs(w)
    assert value(run, 0, 0) == "first" and len(w.document.pages) == 4


def test_turning_a_page_turns_the_whole_run_and_reflows_the_breaks(w):
    run = sheet_page(w)
    w.insert_sheet_page(1)
    pump()
    w.rotate_page(1)
    pump()
    assert [p.setup.orientation for p in w.document.pages[1:]] == [LANDSCAPE, LANDSCAPE]
    assert w.document.pages[0].setup.orientation == PORTRAIT
    (run,) = runs(w)
    assert run.paging.last_col > 10                 # more columns across
    assert run.paging.slices[0][1] + 1 < 52         # fewer rows down


def test_a_copied_sheet_page_is_an_ordinary_page(w):
    run = sheet_page(w)
    w.duplicate_page(1)
    pump()
    assert [p.sheet for p in w.document.pages] == [None, run.uid, None]
    assert len(runs(w)) == 1


# -- what does not go on it -------------------------------------------------------------------------
def test_no_equations_or_tables_on_a_sheet_page(w):
    run = sheet_page(w)
    frame = w.document.pages[1].frame
    w.view.calc.place_cross(frame, QPointF(100, 100))
    assert w.view.calc.cross is None
    w.toggle_calc_mode(True)
    # in Calc mode a click is a cell, never the red cross
    pos = cell_scene(run, "C3")
    w.view.centerOn(pos)
    click(w, pos)
    assert w.view.tables.item is run and w.view.calc.cross is None
    w.view.tables.close()
    w.toggle_calc_mode(False)
    # a table dragged out on it is refused
    w.insert_table()
    from tests.test_usability import drag
    a, b = cell_scene(run, "B5"), cell_scene(run, "D9")
    drag(w.view, a.x(), a.y(), b.x(), b.y())
    pump()
    assert [i for i in frame.markups() if type(i).__name__ == "TableItem"] == []


# -- page breaks and layout ------------------------------------------------------------------------
def test_manual_breaks_and_a_dragged_automatic_break(w):
    run = sheet_page(w)
    w.insert_sheet_page(1)
    pump()
    (run,) = runs(w)
    sheetlayout.insert_break(w, run, 20)
    (run,) = runs(w)
    assert run.paging.slices[0] == (0, 19) and 20 in run.paging.manual
    sheetlayout.reset_breaks(w, run)
    (run,) = runs(w)
    assert run.paging.slices[0] == (0, 51)
    # drag the automatic break at row 53 up to row 41: a manual break there
    open_at(w, run, "A1")
    xs, ys = run.edges()
    start = run.mapToScene(QPointF(xs[2], ys[52]))
    end = run.mapToScene(QPointF(xs[2], ys[40] + 2))
    from tests.test_usability import drag
    drag(w.view, start.x(), start.y(), end.x(), end.y())
    pump()
    (run,) = runs(w)
    assert options(run.sheet)["breaks"] == [40]
    assert run.paging.slices[0] == (0, 39)
    w.undo_stack.undo()
    pump()
    (run,) = runs(w)
    assert options(run.sheet)["breaks"] == []


def test_page_layout_dialog_sets_the_options(w):
    run = sheet_page(w)
    w.interactive_prompts = False
    w.sheet_page_setup(1)
    dialog = w._last_data_dialog
    dialog.area.setText("A1:F30")
    dialog.titles.setText("1:2")
    dialog.center_h.setChecked(True)
    dialog.gridlines.setChecked(True)
    sheetlayout.apply_dialog(w, run, dialog)
    (run,) = runs(w)
    opts = options(run.sheet)
    assert opts["print_area"] == [0, 0, 29, 5]
    assert opts["titles"] == [0, 1]
    assert opts["center_h"] and opts["print_gridlines"]
    assert (run.paging.first_col, run.paging.last_col) == (0, 5)
    dialog.area.setText("nonsense")
    assert dialog.changes() is None


# -- on paper ------------------------------------------------------------------------------------------
def test_each_page_prints_its_slice_inside_the_margins(w):
    run = sheet_page(w)
    w.insert_sheet_page(1)
    pump()
    (run,) = runs(w)
    wb = run.sheet.workbook
    wb.set_input(run.sheet, 0, 0, "TOP")
    wb.set_input(run.sheet, 52, 0, "SECOND")
    wb.set_input(run.sheet, 0, 15, "SCRATCH")       # column P: never printed
    f1, f2 = (w.document.pages[i].frame for i in (1, 2))
    one, two = paper(f1, 2), paper(f2, 2)
    left, top, width, height = run.paging.printable
    for image in (one, two):
        box = ink_box(image)
        assert box is not None
        assert box[0] >= left * 2 - 2 and box[1] >= top * 2 - 2
        assert box[2] <= (left + width) * 2 + 2
    # the page shape on paper is the paper, not the grid's slice
    assert one.width() == int(f1.page.width_pt * 2)
    # no gridlines on paper by default: an empty page prints nothing
    w.insert_sheet_page(1)
    pump()
    blank = paper(w.document.pages[3].frame, 2)
    assert ink_box(blank) is None


def test_titles_repeat_and_markups_print_over_their_cells(w):
    run = sheet_page(w)
    w.insert_sheet_page(1)
    pump()
    (run,) = runs(w)
    wb = run.sheet.workbook
    wb.set_input(run.sheet, 0, 0, "HEAD")
    wb.set_page_options(run.sheet, titles=[0, 0])
    run.relayout()
    f2 = w.document.pages[2].frame
    plain = ink_box(paper(f2, 2))
    assert plain is not None, "the title row prints at the top of page 2"
    left, top, _w, _h = run.paging.printable
    assert plain[1] < (top + run.sheet.height(0)) * 2 + 2
    # a markup on the second page prints where its cell went
    k = 1
    a = run.paging.slices[k][0]
    spot = run.cell_rect(a + 5, 4).topLeft() - QPointF(0, run._tops[k])
    box_on(f2, spot.x(), spot.y())
    image = paper(f2, 2)
    import numpy as np
    arr = np.frombuffer(image.constBits(), np.uint8).reshape(
        image.height(), image.bytesPerLine() // 4, 4)[:, :image.width(), :3]
    ink = np.nonzero(arr.mean(axis=2) < 200)
    xs, ys = run.edges()
    expect_x = (left + xs[4]) * 2
    expect_y = (top + run.sheet.height(0) + (ys[a + 5] - ys[a])) * 2
    near = [(x, y) for y, x in zip(*ink) if abs(x - expect_x) < 6 and abs(y - expect_y) < 6]
    assert near, "the markup's corner prints at its cell"


def test_save_and_reopen_keep_the_run_its_cells_and_its_markups(w, tmp_path):
    import pymupdf
    from tests.test_calc_saving import reopen, save_to
    run = sheet_page(w)
    w.insert_sheet_page(1)
    pump()
    (run,) = runs(w)
    wb = run.sheet.workbook
    wb.set_input(run.sheet, 2, 1, "7.5")
    wb.set_input(run.sheet, 3, 1, "=B3*2")
    wb.set_page_options(run.sheet, breaks=[30], center_h=True)
    run.relayout()
    box = box_on(w.document.pages[2].frame, 40, 30)
    path = str(tmp_path / "sheet.pdf")
    save_to(w, path)
    with pymupdf.open(path) as doc:
        assert len(doc) == 3
        assert list(doc[2].annots()) == [], "a sheet page's markups are not annotations"
        assert "15" in doc[1].get_text(), "the cells are drawn into the page"
    reopen(w, path)
    pump()
    pump()
    assert [p.sheet is not None for p in w.document.pages] == [False, True, True]
    (run,) = runs(w)
    assert value(run, 3, 1) == 15.0
    assert options(run.sheet)["breaks"] == [30]
    assert run.paging.slices[0] == (0, 29)
    (box2,) = [m for m in w.document.pages[2].frame.markups() if isinstance(m, RectItem)]
    assert box2.pos() == box.pos()
    with pymupdf.open(path) as doc:
        assert "15" in doc[1].get_text()
