"""The arithmetic of charts (phase 5): series read from cells with their
units, Excel's axis scaling, trendlines and error bars."""
from __future__ import annotations

import math

import numpy as np
import pytest

from calcforge.sheet import chartdata as CD
from calcforge.sheet.workbook import Workbook


def book():
    wb = Workbook()
    s = wb.add_sheet("Loads", "table")
    s.size = (6, 3)
    rows = [("Span", "Load", "Name"), ("2 m", "10 kN", "a"), ("3 m", "12 kN", "b"),
            ("4 m", "15 kN", "c"), ("5 m", "", "d"), ("6 m", "21 kN", "e")]
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            wb.set_input(s, r, c, text)
    return wb, s


def test_a_series_reads_its_cells_in_their_units():
    wb, s = book()
    got = CD.read_series(wb, {"name": "=Loads!$B$1", "x": "Loads!$A$2:$A$6",
                              "y": "Loads!$B$2:$B$6"}, numeric_x=True)
    assert got.name == "Load"
    assert got.xs == [2, 3, 4, 5, 6]
    assert got.ys == [10, 12, 15, None, 21]          # an empty cell is a gap
    assert (got.x_unit, got.y_unit) == ("m", "kN")
    cats = CD.read_series(wb, {"x": "Loads!$C$2:$C$6", "y": "Loads!$B$2:$B$6"}, numeric_x=False)
    assert cats.categories == ["a", "b", "c", "d", "e"]
    alone = CD.read_series(wb, {"y": "Loads!$B$2:$B$4"}, numeric_x=True)
    assert alone.xs == [1, 2, 3]
    by_heading = CD.read_series(wb, {"y": "Loads[Load]"}, numeric_x=True)
    assert by_heading.ys == [10, 12, 15, None, 21]
    assert CD.sheets_read({"series": [{"x": "Loads!$A$2:$A$6", "y": "Other[Load]"}]}) == \
        {"loads", "other"}


@pytest.mark.parametrize("lo, hi, expect", [
    (1.2, 48, (0, 60, 10)),          # zero kept, room above the top value
    (0, 100, (0, 120, 20)),
    (95, 105, (94, 106, 2)),          # far from zero: zero not forced in
    (-12, 30, (-20, 40, 10)),
    (0.012, 0.048, (0, 0.06, 0.01)),
])
def test_axes_are_scaled_as_excel_scales_them(lo, hi, expect):
    a, b, step = CD.nice_scale(lo, hi, ticks=6)
    assert (round(a, 9), round(b, 9), round(step, 9)) == pytest.approx(expect)
    assert CD.nice_scale(1, 9, 6, fixed_min=2, fixed_max=8)[:2] == (2, 8)


def test_log_axes_run_whole_decades():
    assert CD.log_scale(1.2, 48) == (1, 100)
    assert CD.log_scale(0.05, 3000) == (0.01, 10000)
    assert CD.log_ticks(1, 1000) == [1, 10, 100, 1000]
    assert CD.tick_label(0.25, 0.05) == "0.25"
    assert CD.tick_label(40.0, 10) == "40"


def test_trendlines_match_least_squares():
    x = [1, 2, 3, 4, 5, 6]
    y = [2.1, 3.9, 6.2, 8.1, 9.8, 12.2]
    lin = CD.fit_trend(x, y, "linear")
    m, b = np.polyfit(x, y, 1)
    assert lin.f(10) == pytest.approx(m * 10 + b)
    assert lin.label == "y = 2.0029x + 0.04"
    assert 0.99 < lin.r2 < 1
    fixed = CD.fit_trend(x, y, "linear", intercept=0)
    assert fixed.f(0) == 0
    poly = CD.fit_trend([2, 3, 4, 5, 6, 7], [1.2, 3.9, 9.1, 17.8, 30.5, 48], "poly", order=2)
    assert poly.label == "y = 1.8571x² - 7.5x + 9.1429"
    assert poly.r2 == pytest.approx(0.9994, abs=1e-4)
    ex = CD.fit_trend(x, [2 * math.exp(0.5 * t) for t in x], "exp")
    assert ex.f(3) == pytest.approx(2 * math.exp(1.5))
    assert ex.r2 == pytest.approx(1.0)
    pw = CD.fit_trend(x, [3 * t ** 1.5 for t in x], "power")
    assert pw.f(4) == pytest.approx(24)
    lg = CD.fit_trend(x, [2 * math.log(t) + 1 for t in x], "log")
    assert lg.f(math.e) == pytest.approx(3)
    ma = CD.fit_trend(x, y, "moving", period=3)
    assert ma.points[0] == (3, pytest.approx((2.1 + 3.9 + 6.2) / 3))
    assert len(ma.points) == 4
    # gaps left out; impossible fits give none
    assert CD.fit_trend([1, 2, None], [1, None, 3], "linear") is None
    assert CD.fit_trend(x, [-1, 2, 3, 4, 5, 6], "exp") is None


def test_error_bars_as_excel_draws_them():
    wb, s = book()
    ys = [10.0, 20.0, None, 40.0]
    assert CD.error_amounts(wb, ys, {"type": "fixed", "value": 2}) == [(2, 2), (2, 2), None, (2, 2)]
    assert CD.error_amounts(wb, ys, {"type": "percent", "value": 10})[3] == (4.0, 4.0)
    sd = np.std([10, 20, 40], ddof=1)
    got = CD.error_amounts(wb, ys, {"type": "stddev", "value": 1})
    assert got[0] == ("mean", pytest.approx(70 / 3), pytest.approx(sd))
    se = CD.error_amounts(wb, ys, {"type": "stderr"})[1]
    assert se[0] == pytest.approx(sd / math.sqrt(3))
    custom = CD.error_amounts(wb, [1.0, 2.0, 3.0], {"type": "custom", "plus": "Loads!$B$2:$B$4",
                                                     "minus": "Loads!$B$2"})
    assert custom == [(10, 10), (10, 12), (10, 15)]
    assert CD.error_amounts(wb, ys, None) == [None] * 4
