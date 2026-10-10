"""Bugs the code review found (2026-10-10): General with text written round
it, and the fill handle taking cells' notes along (Excel)."""
from __future__ import annotations

import pytest

from calcforge.sheet.fill import fill
from calcforge.sheet.numfmt import format_value
from calcforge.sheet.workbook import Workbook


@pytest.mark.parametrize("code, value, shown", [
    ('General" kN"', 5.25, "5.25 kN"),
    ('"F = "General', 5.25, "F = 5.25"),
    ('General" kN";-General" kN"', -2.5, "-2.5 kN"),
    ("General", 1234.5, "1234.5"),
    ("General;-General", -3.0, "-3"),
])
def test_general_keeps_the_text_written_round_it(code, value, shown):
    assert format_value(value, code).text == shown
    assert "1900" not in format_value(value, code).text, "the e of General is not a year"


def test_the_fill_handle_takes_the_notes_along():
    wb = Workbook()
    s = wb.add_sheet("S")
    wb.set_input(s, 0, 0, "1")
    wb.set_comment(s, 0, 0, "checked")
    wb.set_input(s, 3, 0, "x")
    wb.set_comment(s, 3, 0, "old note")
    fill(wb, s, (0, 0, 0, 0), (1, 0, 3, 0))
    assert [s.cells[(r, 0)].comment for r in range(4)] == ["checked"] * 4
