"""Excel's fill handle, case by case (sheet/fill.py): what dragging a
selection's corner types into the cells it reaches."""
from __future__ import annotations

import pytest

from calcforge.sheet.fill import fill
from calcforge.sheet.workbook import Workbook


def dragged(inputs, n, across=False, ctrl=False, back=False):
    """Type ``inputs`` in a line, drag on ``n`` cells (down, across, up or
    left) and read what the new cells hold, nearest the selection first."""
    wb = Workbook()
    s = wb.add_sheet("S")
    k = len(inputs)
    start = n if back else 0
    at = (lambda i: (0, i)) if across else (lambda i: (i, 0))
    for i, text in enumerate(inputs):
        wb.set_input(s, *at(start + i), text)
    src = (*at(start), *at(start + k - 1))
    new = list(range(start - 1, -1, -1)) if back else list(range(k, k + n))
    dst = (*at(min(new)), *at(max(new)))
    fill(wb, s, src, dst, ctrl)
    return [s.cells[at(i)].input if at(i) in s.cells else None for i in new]


CASES = [
    (["1"], 3, {}, ["1", "1", "1"]),
    (["1"], 3, {"ctrl": True}, ["2", "3", "4"]),
    (["1", "3"], 3, {}, ["5", "7", "9"]),
    (["0.1", "0.2"], 8, {}, ["0.3", "0.4", "0.5", "0.6", "0.7", "0.8", "0.9", "1"]),
    (["10%", "20%"], 2, {}, ["30%", "40%"]),
    (["2026-01-31"], 2, {}, ["2026-02-01", "2026-02-02"]),
    (["2026-01-15", "2026-02-15"], 2, {}, ["2026-03-15", "2026-04-15"]),
    (["2026-01-01", "2027-01-01"], 2, {}, ["2028-01-01", "2029-01-01"]),
    (["Item 1", "Item 3"], 2, {}, ["Item 5", "Item 7"]),
    (["P007"], 2, {}, ["P008", "P009"]),
    (["FRIDAY"], 3, {}, ["SATURDAY", "SUNDAY", "MONDAY"]),
    (["jan", "mar"], 2, {}, ["may", "jul"]),
    (["Dec"], 2, {"across": True}, ["Jan", "Feb"]),
    (["Q3"], 3, {}, ["Q4", "Q1", "Q2"]),
    (["Qtr 4"], 1, {}, ["Qtr 1"]),
    (["100 mm", "200 mm"], 2, {}, ["300 mm", "400 mm"]),
    (["5 kN"], 2, {"ctrl": True}, ["6 kN", "7 kN"]),
    (["a", "b"], 3, {}, ["a", "b", "a"]),
    (["=A1*2"], 2, {}, ["=A2*2", "=A3*2"]),
    # one cell dragged up or left counts down; two or more keep their step
    (["Item 5"], 3, {"back": True}, ["Item 4", "Item 3", "Item 2"]),
    (["Mon"], 2, {"back": True, "across": True}, ["Sun", "Sat"]),
    (["2026-03-01"], 1, {"back": True}, ["2026-02-28"]),
    (["10"], 2, {"back": True, "ctrl": True}, ["9", "8"]),
    (["3", "5"], 2, {"back": True}, ["1", "-1"]),
    (["=B5"], 1, {"back": True}, ["=B4"]),
]


@pytest.mark.parametrize("inputs, n, how, expected", CASES)
def test_fill_as_excel(inputs, n, how, expected):
    assert dragged(inputs, n, **how) == expected
