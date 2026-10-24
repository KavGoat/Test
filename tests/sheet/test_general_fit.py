"""QA round 2 (2026-10-15), the engine's side: Excel's General format fitting
a column; errors carrying a reason that doesn't change how they compare;
why a cell shows an error; var(X) when X is no equation variable; a column
dragged to nothing being hidden; date formulas implying a date format."""
from __future__ import annotations

import math

import pytest

from calcforge.sheet.explain import why
from calcforge.sheet.numfmt import format_value, general_fit
from calcforge.sheet.refs import parse_cell
from calcforge.sheet.values import DIV0, NAME, UNITS_ERR, ErrorValue, with_unit
from calcforge.sheet.workbook import Workbook, formula_format


def chars(n):
    """fits() for a column n characters wide (each character a digit's width)."""
    return lambda text: len(text) <= n


# -- General fits its column ---------------------------------------------------------------
@pytest.mark.parametrize("x, shown", [
    (1 / 3, "0.333333"), (math.pi, "3.141593"), (2 / 3 * 1e6, "666666.7"),
    (1.2909944487358056, "1.290994"), (123.456789, "123.4568"), (5e9, "5E+09"),
    (-1 / 3, "-0.33333"), (123456789, "1.23E+08"), (12345678.9, "12345679"),
    (0.000123456, "0.000123"), (1.23e-7, "1.23E-07"), (0.5, "0.5"), (42, "42"),
])
def test_general_rounds_to_fit_or_goes_scientific(x, shown):
    assert general_fit(x, chars(8)) == shown


def test_general_gives_up_only_when_nothing_fits():
    assert general_fit(5e9, chars(4)) == "5000000000", "too wide: the cell shows ####"
    assert general_fit(1 / 3, chars(2)) == general_fit(1 / 3, chars(0)), "0.3 rounds to nothing"
    assert general_fit(1 / 3, chars(3)) == "0.3"
    assert general_fit(7.0, chars(1)) == "7"


def test_a_quantity_keeps_its_unit_whole():
    q = with_unit(1 / 3, "kN")
    assert format_value(q).text == "0.333333333 kN"
    assert format_value(q, fit=chars(9)).text == "0.3333 kN"
    assert format_value(1 / 3, "0.00", fit=chars(3)).text == "0.33", "a set format is kept"


def test_without_fit_nothing_changes():
    assert format_value(1 / 3).text == "0.333333333"
    assert format_value(5e9).text == "5000000000"


# -- errors carry reasons ----------------------------------------------------------------------
def test_a_reason_takes_no_part_in_comparing():
    told = DIV0.because("dividing by zero (B4 is 0)")
    assert told == DIV0 and hash(told) == hash(DIV0) and str(told) == "#DIV/0!"
    assert told.reason and not DIV0.reason
    assert told.because("another") is told, "the first reason stays"
    assert format_value(told).text == "#DIV/0!"
    assert {told: 1}[DIV0] == 1


def put(wb, s, **cells):
    with wb.transaction():
        for a1, text in cells.items():
            r = parse_cell(a1)
            wb.set_input(s, r.row, r.col, text)


def get(s, a1):
    r = parse_cell(a1)
    return s.value(r.row, r.col)


def said(s, a1):
    r = parse_cell(a1)
    return why(s, r.row, r.col)


@pytest.fixture
def book():
    wb = Workbook()
    return wb, wb.add_sheet()


def test_why_a_cell_shows_its_error(book):
    wb, s = book
    put(wb, s, A1="5 kN", A2="2 m", A3="=A1+A2", A4="=A3*2", B4="0", B5="=10/B4",
        B6="=10/B9", C1="=Spna", C2="=1+", C3='="abc"*2', C4="=A1>A2", C5="=SUM(B5,1)",
        C6="=SQRT(-1)", C7="=SIN(A1)", C8="=SUM(1,2,", D1="7")
    assert said(s, "A3") == "#UNITS! — kN and m can't be added (A1 + A2)"
    assert said(s, "A4") == "#UNITS! — from A3: kN and m can't be added (A1 + A2)"
    assert said(s, "B5") == "#DIV/0! — dividing by zero (B4 is 0)"
    assert said(s, "B6") == "#DIV/0! — dividing by zero (B9 is empty)"
    assert said(s, "C1") == ("#NAME? — 'Spna' isn't a function or an Excel name of this "
                             "workbook or sheet")
    assert said(s, "C2") == "#NAME? — There's a problem with this formula."
    assert said(s, "C3").startswith("#VALUE! — “abc” is text, not a number")
    assert said(s, "C4") == "#UNITS! — kN and m can't be compared (A1 > A2)"
    assert said(s, "C5") == "#DIV/0! — from B5: dividing by zero (B4 is 0)"
    assert said(s, "C6").startswith("#NUM! — SQRT:")
    assert "angle" in said(s, "C7") and "kN" in said(s, "C7")
    assert said(s, "D1") is None and said(s, "Z9") is None
    assert get(s, "A3") == UNITS_ERR and get(s, "C1") == NAME
    # the reason follows a change: B4 no longer 0, then 0 again elsewhere
    put(wb, s, B4="", B5="=10/B4")
    assert said(s, "B5") == "#DIV/0! — dividing by zero (B4 is empty)"


# -- CALC() ---------------------------------------------------------------------------------------
def test_calc_reads_the_variable_and_var_is_always_excels(book):
    """The user, 2026-10-24: a bare name in a cell is only ever an Excel
    name; CALC(x) reads the CalcForge variable x; VAR is Excel's variance."""
    wb, s = book
    variables = {"F": 10.0}

    def outside(_sheet, name):
        from calcforge.calc.engine.units import NODIM, Quantity
        if name not in variables:
            raise KeyError(name)
        return Quantity(variables[name], NODIM)

    wb.outside = outside
    put(wb, s, A1="4", B1="1", B2="2", B3="3")
    wb.define_name("F", "Sheet1!$A$1")
    assert wb.find_name("F", s) is not None
    put(wb, s, C1="=CALC(F)", C2="=CALC(Span)", C3="=VAR(B1:B3)", C4="=CALC(M20)", C5="=F",
        C6="=Span", C7="=var(B1:B3)")
    assert get(s, "C1") == 10.0, "the equations' F, though a cell is named F"
    assert get(s, "C5") == 4.0, "bare: the Excel name F"
    assert get(s, "C2") == NAME and "CALC(Span)" in said(s, "C2")
    assert get(s, "C3") == 1.0 and get(s, "C7") == 1.0
    assert get(s, "C4") == NAME
    assert said(s, "C6") == "#NAME? — 'Span' isn't a function or an Excel name of this workbook or sheet"
    variables["M20"] = 3.0
    variables["Span"] = 2.0
    wb.outside_changed({"m20", "span"})
    assert get(s, "C4") == 3.0 and get(s, "C2") == 2.0
    assert "read as CALC(Span)" in said(s, "C6"), "bare, it says how a cell reads the variable"


# -- hiding by dragging ----------------------------------------------------------------------
def test_a_column_sized_to_nothing_is_hidden_with_its_width_kept(book):
    wb, s = book
    wb.set_widths(s, [1], 70.0)
    wb.drag_size(s, "col", [1], 0.0, {1: 70.0})
    assert 1 in s.hidden_cols and s.width(1) == 0 and s.widths[1] == 70.0
    wb.set_hidden(s, "col", [1], False)
    assert s.width(1) == 70.0
    wb.drag_size(s, "col", [1], 0.0, {1: None})
    assert 1 in s.hidden_cols and 1 not in s.widths, "a default width stays the default"
    wb.drag_size(s, "col", [1], 25.0, {1: None})
    assert 1 not in s.hidden_cols and s.width(1) == 25.0
    wb.drag_size(s, "row", [3], 0.0, {3: None})
    assert 3 in s.hidden_rows and s.height(3) == 0
    wb.undo()
    assert 3 not in s.hidden_rows


# -- dates -----------------------------------------------------------------------------------------
def test_date_formulas_imply_a_date_format(book):
    wb, s = book
    assert formula_format("DATE(2026,10,15)") == "d/mm/yyyy"
    assert formula_format("TODAY()+7") == "d/mm/yyyy"
    assert formula_format("7+TODAY()") == "d/mm/yyyy"
    assert formula_format("NOW()") == "d/mm/yyyy h:mm"
    assert formula_format("TIME(14,30,0)") == "h:mm AM/PM"
    assert formula_format("TODAY()-DATE(2026,1,1)") is None, "days between: a number"
    assert formula_format("1/3") is None and formula_format("1+") is None
    assert formula_format("DATE(2026,10,15)", day_first=False) == "m/d/yyyy"
    put(wb, s, A1="=DATE(2026,10,15)", A2="=TODAY()", A3="=A1+1")
    fmt = lambda a1: wb.style_of(s, parse_cell(a1).row, parse_cell(a1).col).number_format
    assert format_value(get(s, "A1"), fmt("A1")).text == "15/10/2026"
    assert fmt("A2") == "d/mm/yyyy" and fmt("A3") in (None, "General")
    # a cell with a format of its own keeps it
    from dataclasses import replace
    style = wb.styles.add(replace(wb.style_of(s, 4, 0), number_format="0.00"))
    wb.set_style(s, 4, 0, style)
    put(wb, s, A5="=DATE(2026,10,15)")
    assert fmt("A5") == "0.00"
