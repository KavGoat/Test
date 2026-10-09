"""How a spreadsheet section falls onto its pages (phase 4): the columns that
fit print and the rest is scratch, rows fill each page, manual breaks, Fit to
page width, Print Area, Print Titles, and page options moving with rows."""
from __future__ import annotations

from calcforge.core.document import LANDSCAPE, PageSetup
from calcforge.sheet.pagination import options, pages_needed, paginate, page_of_row
from calcforge.sheet.store import load_sheet, sheet_to_dict
from calcforge.sheet.workbook import Workbook


def a4(orientation=None):
    setup = PageSetup()
    if orientation:
        setup.orientation = orientation
    return setup


def fresh():
    wb = Workbook()
    return wb, wb.add_sheet("Sheet1", "sheet")


def test_columns_that_fit_print_the_rest_is_scratch():
    wb, sheet = fresh()
    paging = paginate(sheet, a4())
    left, top, width, height = paging.printable
    printed = sum(sheet.width(c) for c in range(paging.first_col, paging.last_col + 1))
    assert printed <= width + 0.01
    assert printed + sheet.width(paging.last_col + 1) > width
    assert (paging.first_col, paging.last_col) == (0, 10)          # A to K on A4 portrait
    # scratch to the right, at least a page wide
    scratch = sum(sheet.width(c) for c in range(paging.last_col + 1, paging.shown_cols))
    assert scratch >= paging.paper[0]
    assert paging.scale == 1.0


def test_landscape_prints_more_columns():
    wb, sheet = fresh()
    assert paginate(sheet, a4(LANDSCAPE)).last_col > paginate(sheet, a4()).last_col


def test_rows_fill_each_page_and_the_run_grows_with_its_data():
    wb, sheet = fresh()
    paging = paginate(sheet, a4())
    assert paging.pages == 1
    per_page = paging.slices[0][1] + 1
    assert per_page == 52
    wb.set_input(sheet, per_page + 3, 0, "x")
    paging = paginate(sheet, a4())
    assert paging.pages == 2
    assert paging.slices[1][0] == per_page
    assert page_of_row(paging, per_page + 3) == 1
    assert pages_needed(sheet, a4()) == 2
    # empty pages asked for are kept
    assert paginate(sheet, a4(), pages_wanted=4).pages == 4


def test_a_manual_break_starts_a_page():
    wb, sheet = fresh()
    wb.set_page_options(sheet, breaks=[10])
    paging = paginate(sheet, a4(), pages_wanted=2)
    assert paging.slices[0] == (0, 9)
    assert paging.slices[1][0] == 10
    assert 10 in paging.manual


def test_fit_to_width_scales_every_data_column_onto_the_page():
    wb, sheet = fresh()
    wb.set_input(sheet, 0, 20, "far")
    paging = paginate(sheet, a4())
    assert paging.last_col == 10                     # U is scratch without it
    wb.set_page_options(sheet, fit_width=True)
    paging = paginate(sheet, a4())
    assert paging.last_col == 20
    printed = sum(sheet.width(c) for c in range(21))
    assert abs(printed * paging.scale - paging.printable[2]) < 0.01
    # scaled down, a page holds more rows
    assert paging.slices[0][1] + 1 > 52


def test_print_area_and_titles():
    wb, sheet = fresh()
    wb.set_page_options(sheet, print_area=[2, 1, 80, 4], titles=[0, 1])
    paging = paginate(sheet, a4())
    assert (paging.first_col, paging.last_col) == (1, 4)
    assert paging.print_rows == (2, 80)
    assert paging.titles == (0, 1)
    # the pages after the first hold fewer rows: the titles repeat on them
    first = paging.slices[0][1] - paging.slices[0][0] + 1
    second = paging.slices[1][1] - paging.slices[1][0] + 1
    assert second == first - 2


def test_page_options_move_with_rows_and_are_saved():
    wb, sheet = fresh()
    wb.set_page_options(sheet, breaks=[10, 30], print_area=[5, 0, 40, 3], titles=[6, 7],
                        center_h=True)
    wb.insert_rows(sheet, 2, 3)
    opts = options(sheet)
    assert opts["breaks"] == [13, 33]
    assert opts["print_area"] == [8, 0, 43, 3]
    assert opts["titles"] == [9, 10]
    wb.delete_rows(sheet, 12, 2)                      # takes the break at 13 with it
    assert options(sheet)["breaks"] == [31]
    data = sheet_to_dict(sheet)
    wb2 = Workbook()
    other = wb2.add_sheet("S", "sheet")
    load_sheet(other, data)
    assert options(other)["breaks"] == [31]
    assert options(other)["center_h"] is True


def test_rows_going_in_tell_the_listeners_first():
    wb, sheet = fresh()
    heard = []
    sheet.on_shift.append(lambda axis, at, delta: heard.append((axis, at, delta)))
    wb.insert_rows(sheet, 4, 2)
    wb.delete_cols(sheet, 1)
    assert heard == [("row", 4, 2), ("col", 1, -1)]
