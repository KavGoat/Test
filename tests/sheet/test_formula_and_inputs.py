"""Reading formulas and typed entries; number formats."""
from __future__ import annotations

import pytest

from calcforge.sheet import formula as F
from calcforge.sheet.inputs import read_value
from calcforge.sheet.numfmt import format_value
from calcforge.sheet.refs import col_index, col_letters, parse_range, quote_sheet
from calcforge.sheet.values import ERRORS, Qty, simplified, with_unit


@pytest.mark.parametrize("n,letters", [(0, "A"), (25, "Z"), (26, "AA"), (701, "ZZ"), (702, "AAA"), (16383, "XFD")])
def test_column_letters(n, letters):
    assert col_letters(n) == letters and col_index(letters) == n


def test_ranges_as_excel_writes_them():
    assert parse_range("$B$7").a1() == "$B$7"
    assert parse_range("'Loads 2'!A1:B4").a1() == "'Loads 2'!A1:B4"
    assert parse_range("A:C").whole == "cols" and parse_range("3:5").whole == "rows"
    assert parse_range("XFE1") is None and parse_range("A0") is None
    assert quote_sheet("Sheet1") == "Sheet1" and quote_sheet("A1") == "'A1'" and quote_sheet("it's") == "'it''s'"


def test_copies_of_a_filled_formula_share_one_tree():
    assert F.parse("A1*2+$B$1", 0, 1) is F.parse("A2*2+$B$1", 1, 1)
    assert F.parse("A1*2", 0, 1) is not F.parse("A1*2", 1, 1)


def test_rewriting_keeps_what_was_typed():
    assert F.moved_formula("SUM( A1 : A3 ) * $B$1 + C$2", 2, 1) == "SUM( B3 : B5 ) * $B$1 + D$2"
    assert F.rename_sheet_in("Old!A1+'old'!B2+Other!C3+Old!Name", "OLD", "New sheet") == \
        "'New sheet'!A1+'New sheet'!B2+Other!C3+'New sheet'!Name"


def test_a_name_on_a_quoted_sheet_reads_as_excels():
    # 'Seismic Actions'!Z is a name of that sheet, as in Excel (it was read
    # as a unit and refused); 'Sheet'!A1 stays a reference, 5'kN a unit
    kinds = [(t.kind, t.text) for t in F.tokenize("'Seismic Actions'!Z*'It''s'!A1+5'kN")]
    assert kinds[:5] == [("name", "'Seismic Actions'!Z"), ("op", "*"), ("ref", "'It''s'!A1"),
                         ("op", "+"), ("num", "5")]
    assert F.rename_sheet_in("'Seismic Actions'!Z+1", "Seismic Actions", "Quake") == "Quake!Z+1"


def test_f4_cycles_the_reference_at_the_caret():
    text, caret = "A1+B2", 4
    seen = []
    for _ in range(4):
        text, caret = F.cycle_reference_at(text, caret)
        seen.append(text)
    assert seen == ["A1+$B$2", "A1+B$2", "A1+$B2", "A1+B2"]


def test_reference_spans_for_colouring():
    spans = F.reference_spans("A1+SUM(B2:C3)")
    assert [(a, b) for a, b, _ in spans] == [(0, 2), (7, 12)]


def test_units_after_numbers():
    tree = F.parse("10 kN/m*B2").tree
    assert isinstance(tree, F.Binary) and tree.left.right == F.Unit("kN/m")
    assert isinstance(F.parse("A1/'kN").tree.right, F.Unit)
    # after the apostrophe, a name may be a custom unit the equations define
    # (2026-10-11): it is read when calculated; what can't be a name is refused
    assert F.parse("A1/'kip_s").tree.right == F.Unit("kip_s")
    with pytest.raises(F.FormulaError):
        F.parse("A1/'1x")


def test_calc_reads_a_calcforge_variable_and_var_is_always_excels_variance():
    """The user, 2026-10-24: "maybe change from var to something excel does
    not have as a function, so there can never be a clash"."""
    assert F.parse("CALC(M20)").tree == F.DocVar("M20")
    assert F.parse("calc(L.beam)").tree == F.DocVar("L.beam")
    assert F.parse("CALC(PGA)").tree == F.DocVar("PGA")
    for excels in ("var(M20)", "VAR(L.beam)", "VAR(A1:A9)", "VAR(1,2,3)", "VAR($M$20)"):
        assert isinstance(F.parse(excels).tree, F.Call), excels
    # CF is CALC in two letters, and either takes an expression of the
    # equations' own, kept as typed (the user, 2026-10-29)
    assert F.parse("CF(M20)").tree == F.DocVar("M20", "CF")
    assert F.parse("cf(L.beam)").tree == F.DocVar("L.beam", "CF")
    assert F.parse("CALC(v1+v2)").tree == F.DocExpr("v1+v2")
    assert F.parse("CF( height * 2 )").tree == F.DocExpr("height * 2", "CF")
    assert F.parse("CALC(sin(x)+f(a,b))").tree == F.DocExpr("sin(x)+f(a,b)")
    assert F.parse("CF(x)+1").names >= {"x"}
    assert F.parse("CF(v1+v2)").names >= {"v1", "v2"}, "recalculated when either changes"
    for bad in ("CALC()", "CF()"):
        with pytest.raises(F.FormulaError, match="takes a CalcForge variable or expression"):
            F.parse(bad)
    with pytest.raises(F.FormulaError, match="missing its"):
        F.parse("CF(a+b")


def test_an_old_formula_is_written_with_calc_where_it_read_a_calcforge_variable():
    calc = {"x", "height", "M20", "L.beam", "pga"}.__contains__
    excel = {"height", "z"}.__contains__
    assert F.to_calc_names("x*2", excel, calc) == "CALC(x)*2"
    assert F.to_calc_names("var(height)+height", excel, calc) == "CALC(height)+height"
    assert F.to_calc_names("var(M20)+VAR(A1:A3)+var(nope)", excel, calc) == \
        "CALC(M20)+VAR(A1:A3)+var(nope)"
    assert F.to_calc_names("L.beam/2+z", excel, calc) == "CALC(L.beam)/2+z"
    assert F.to_calc_names("LET(x, 2, x*3)", excel, calc) == "LET(x, 2, x*3)", "LET's own x"
    assert F.to_calc_names("SUM(pga, Sheet1!pga)", excel, calc) == "SUM(CALC(pga), Sheet1!pga)"


def test_xlsx_function_prefixes_are_dropped():
    assert F.parse("_xlfn.XLOOKUP(1,A1:A2,B1:B2)").tree.name == "XLOOKUP"


@pytest.mark.parametrize("bad", ["", "1+", "SUM(1,", "(1", "{1,2;3}", "\"abc", "#BAD!"])
def test_formulas_that_cannot_be_read(bad):
    with pytest.raises(F.FormulaError):
        F.parse(bad)


@pytest.mark.parametrize("typed,value,fmt", [
    ("5", 5.0, None), ("-3.5", -3.5, None), ("1,250.50", 1250.5, "#,##0.00"), ("12%", 0.12, "0%"),
    ("$1,200", 1200.0, "$#,##0"), ("(40)", -40.0, None), ("TRUE", True, None), ("false", False, None),
    ("1e5", 100000.0, "0.00E+00"), ("2026-10-09", 46304.0, "yyyy-mm-dd"), ("9/10/2026", 46304.0, "d/mm/yyyy"),
    ("1 1/2", 1.5, "# ?/?"), ("'007", "007", None), ("3 apples", "3 apples", None), ("", None, None),
])
def test_typed_entries(typed, value, fmt):
    got, got_fmt = read_value(typed)
    if value is None:
        assert not got
    else:
        assert got == value and got_fmt == fmt


def test_typed_errors_and_quantities():
    assert read_value("#N/A")[0] is ERRORS["#N/A"]
    q = read_value("2.5 kN/m^2")[0]
    assert isinstance(q, Qty) and q.si == 2500.0 and q.unit == "kN/m^2"
    assert read_value("20 °C")[0].si == pytest.approx(293.15)
    assert read_value("9/10/2026", day_first=False)[0] == 46275.0   # 10 September


@pytest.mark.parametrize("value,code,shown", [
    (1234.5678, "0.00", "1234.57"), (1234.5678, "#,##0", "1,235"), (0.1234, "0.0%", "12.3%"),
    (0, '0;-0;"zero"', "zero"), (12345678, "0.00E+00", "1.23E+07"), (0.75, "?/?", "3/4"),
    (1.5, "# ?/?", "1 1/2"), (46304.6041666667, "d/mm/yyyy h:mm", "9/10/2026 14:30"),
    (0.6041666667, "h:mm AM/PM", "2:30 PM"), (1.5, "[h]:mm", "36:00"), (1234.5, "$#,##0.00", "$1,234.50"),
    (1 / 3, None, "0.333333333"), (123456789012, None, "1.23457E+11"), (1234567, '#,##0.0,,"M"', "1.2M"),
    (12, "000", "012"), (-0.0001, "0.00", "0.00"), (2.675, "0.00", "2.68"), (60, "d mmm yyyy", "29 Feb 1900"),
])
def test_number_formats(value, code, shown):
    assert format_value(value, code).text == shown


def test_format_colours_and_conditions():
    assert format_value(-5, "0.00;[Red](0.00)").color == "#FF0000"
    assert format_value(1500, '[>=1000]#,##0,"k";0').text == "2k"
    assert format_value(999, '[>=1000]#,##0,"k";0').text == "999"
    assert format_value("abc", '@" units"').text == "abc units"


def test_quantities_show_in_their_unit():
    q = with_unit(5.25, "kN")
    assert format_value(q, "0.00").text == "5.25 kN"
    assert format_value(q, "0.0", unit="N").text == "5250.0 N"
    # a unit of another kind: SMath's, the units still needed before it
    assert format_value(q, None, unit="m").text == "5.25 kN/m\u2009m"
    assert format_value(q, None, unit="frobs").text == "5.25 kN", "a name that is no unit is ignored"


def test_units_simplify():
    assert simplified("kN/m·m") == "kN" and simplified("kN·m/m^2") == "kN/m" and simplified("m·m") == "m^2"
