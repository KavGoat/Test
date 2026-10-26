"""A defined name of one cell is that cell, not only its value, as in Excel
(the user, 2026-10-26: 200PFC_WP30NC.xlsx's G115, =MIN(ae_3,ae_4,ae_5),
gave #VALUE! where Excel shows 49 "even though there were two N/A values").

MIN, MAX, SUM and the like pass over the text in the cells they are given;
a name that gave its cell's value instead handed them "N/A" as typed text.
ROW, COLUMN and OFFSET of a one-cell name need the cell too.
"""
from __future__ import annotations

import pytest

from calcforge.sheet.workbook import Workbook


@pytest.fixture
def calc():
    wb = Workbook()
    sheet = wb.add_sheet("Calc")
    wb.set_input(sheet, 0, 0, "49")
    wb.set_input(sheet, 1, 0, '=IF(TRUE,"N/A",3)')
    wb.set_input(sheet, 2, 0, "50")
    wb.define_name("ae_3", "Calc!$A$1")
    wb.define_name("ae_4", "Calc!$A$2")
    wb.define_name("ae_6", "Calc!$A$3")
    return wb, sheet


def value(wb, sheet, text):
    wb.set_input(sheet, 9, 0, text)
    return sheet.cells[(9, 0)].value


@pytest.mark.parametrize("text, wanted", [
    ("=MIN(ae_3,ae_4)", 49.0),
    ("=MIN(ae_3,ae_4,ae_6)", 49.0),
    ("=MAX(ae_3,ae_4,ae_6)", 50.0),
    ("=SUM(ae_3,ae_4,ae_6)", 99.0),
    ("=AVERAGE(ae_3,ae_4,ae_6)", 49.5),
    ("=COUNT(ae_3,ae_4,ae_6)", 2.0),
    ("=ae_3*2", 98.0),
    ("=ROW(ae_4)", 2.0),
    ("=COLUMN(ae_6)", 1.0),
    ("=OFFSET(ae_3,2,0)", 50.0),
])
def test_a_name_of_one_cell_is_read_as_its_cell(calc, text, wanted):
    wb, sheet = calc
    assert value(wb, sheet, text) == pytest.approx(wanted)


def test_text_typed_straight_in_is_still_refused(calc):
    wb, sheet = calc
    assert value(wb, sheet, '=MIN(ae_3,"x")').code == "#VALUE!"
    assert value(wb, sheet, "=ae_4") == "N/A"
