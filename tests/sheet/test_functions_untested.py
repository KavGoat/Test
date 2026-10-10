"""Every Excel function the rest of the suite never ran (coverage,
2026-10-10), against the answers Excel gives — mostly Microsoft's own
documented examples."""
from __future__ import annotations

import math

import pytest

from calcforge.sheet.refs import parse_cell
from calcforge.sheet.values import Array, ErrorValue
from calcforge.sheet.workbook import Workbook


@pytest.fixture
def book():
    wb = Workbook()
    s = wb.add_sheet("Data")
    # A: numbers, B: a mix, C: labels, D/E: x and y for the regressions
    cells = {
        "A1": "2", "A2": "4", "A3": "6", "A4": "8",
        "B1": "0.5", "B2": "TRUE", "B3": "text", "B4": "",
        "C1": "x", "C2": "y", "C3": "x", "C4": "x",
        "D1": "6", "D2": "5", "D3": "11", "D4": "7", "D5": "5", "D6": "4", "D7": "4",
        "E1": "2", "E2": "3", "E3": "9", "E4": "1", "E5": "8", "E6": "7", "E7": "5",
        "F1": "1", "F2": "=1/0", "F3": "3",
        "G1": "=1+2",
    }
    for a1, text in cells.items():
        r = parse_cell(a1)
        wb.set_input(s, r.row, r.col, text)
    return wb, s


def calc(book, formula):
    wb, s = book
    wb.set_input(s, 20, 20, "=" + formula)
    cell = s.cells[(20, 20)]
    if s.spills.get((20, 20)):
        return s.spill_values[(20, 20)]
    return cell.value


def grid(value):
    assert isinstance(value, Array), value
    return [list(row) for row in value.rows]


NUMBERS = [
    ("AVEDEV(2,4,6,8)", 2.0),
    ("AVERAGEA(B1:B3)", 0.5),                       # 0.5, TRUE=1, text=0
    ("AVERAGEIFS(A1:A4,A1:A4,\">2\",C1:C4,\"x\")", 7.0),
    ("CEILING.MATH(4.3)", 5.0), ("CEILING.MATH(-4.3)", -4.0), ("CEILING.MATH(-4.3,1,1)", -5.0),
    ("CEILING.MATH(24.3,5)", 25.0),
    ("FLOOR.MATH(4.7)", 4.0), ("FLOOR.MATH(-4.3)", -5.0), ("FLOOR.MATH(-4.3,1,1)", -4.0),
    ("DAYS360(DATE(2026,1,31),DATE(2026,3,31))", 60.0),
    ("DEVSQ(4,5,8,7,11,4,3)", 48.0),
    ("FORECAST(30,{6,7,9,15,21},{20,28,31,38,40})", 10.607253),
    ("FORECAST.LINEAR(30,{6,7,9,15,21},{20,28,31,38,40})", 10.607253),
    ("GEOMEAN(4,5,8,7,11,4,3)", 5.476987),
    ("HARMEAN(4,5,8,7,11,4,3)", 5.028376),
    ("INTERCEPT(E1:E5,D1:D5)", 0.0483871),
    ("SLOPE(E1:E7,D1:D7)", 0.305556),
    ("RSQ(E1:E7,D1:D7)", 0.05795),
    ("CORREL({3,2,4,5,6},{9,7,12,15,17})", 0.997054),
    ("PEARSON({9,7,5,3,1},{10,6,1,5,3})", 0.699379),
    ("COVAR({3,2,4,5,6},{9,7,12,15,17})", 5.2),
    ("COVARIANCE.P({3,2,4,5,6},{9,7,12,15,17})", 5.2),
    ("COVARIANCE.S({2,4,8},{5,11,12})", 9.666667),
    ("ISOWEEKNUM(DATE(2012,3,9))", 10.0),
    ("WEEKNUM(DATE(2012,3,9))", 10.0), ("WEEKNUM(DATE(2012,3,9),2)", 11.0),
    ("MAXA(B1:B3)", 1.0), ("MINA(B1:B3)", 0.0),
    ("NORM.DIST(42,40,1.5,TRUE)", 0.9087888), ("NORM.DIST(42,40,1.5,FALSE)", 0.10934),
    ("NORMDIST(42,40,1.5,TRUE)", 0.9087888),
    ("NORM.INV(0.908789,40,1.5)", 42.000002), ("NORMINV(0.908789,40,1.5)", 42.000002),
    ("NORM.S.DIST(1.333333,TRUE)", 0.908788726), ("NORM.S.INV(0.908789)", 1.3333347),
    ("NORMSINV(0.908789)", 1.3333347),
    ("NPER(0.12/12,-100,-1000,10000,1)", 59.6738657),
    ("NUMBERVALUE(\"2.500,27\",\",\",\".\")", 2500.27),
    ("PERCENTILE.EXC({1,2,3,6,6,6,7,8,9},0.25)", 2.5),
    ("QUARTILE.EXC({6,7,15,36,39,40,41,42,43,47,49},1)", 15.0),
    ("PERMUT(100,3)", 970200.0),
    ("PV(0.08/12,12*20,500,,0)", -59777.15),
    ("RATE(4*12,-200,8000)", 0.0077014),
    ("SECOND(TIME(1,2,33))", 33.0),
    ("SHEET()", 1.0),
    ("STANDARDIZE(42,40,1.5)", 1.333333),
    ("STDEVA(A1:A4)", 2.581989),
    ("TIMEVALUE(\"6:35 PM\")", 0.774306),
    ("TREND({1,2,3},{1,2,3},4)", 4.0),
    ("UNICODE(\"B\")", 66.0),
    ("VAR.P(1,2,3,4)", 1.25), ("VARP(1,2,3,4)", 1.25),
    ("YEARFRAC(DATE(2012,1,1),DATE(2012,7,30))", 0.58055556),
    ("YEARFRAC(DATE(2012,1,1),DATE(2012,7,30),1)", 0.57650273),
    ("YEARFRAC(DATE(2012,1,1),DATE(2012,7,30),3)", 0.57808219),
    ("AGGREGATE(9,6,F1:F3)", 4.0), ("AGGREGATE(4,6,F1:F3)", 3.0),
    ("DATEDIF(DATE(2001,1,1),DATE(2003,1,1),\"Y\")", 2.0),
    ("DATEDIF(DATE(2001,6,1),DATE(2002,8,15),\"D\")", 440.0),
    ("DATEDIF(DATE(2001,6,1),DATE(2002,8,15),\"YD\")", 75.0),
    ("DATEDIF(DATE(2001,6,1),DATE(2002,8,15),\"MD\")", 14.0),
    ("DATEDIF(DATE(2001,6,1),DATE(2002,8,15),\"YM\")", 2.0),
    ("DATEDIF(DATE(2001,6,1),DATE(2002,8,15),\"M\")", 14.0),
    ("LAMBDA(x,x*2)(3)", 6.0),
    ("DATEVALUE(\"2026-10-10\")", 46305.0),
    ("STRIPUNIT(5 kN)", 5.0),
]


@pytest.mark.parametrize("formula, expected", NUMBERS)
def test_numbers_match_excel(book, formula, expected):
    got = calc(book, formula)
    assert not isinstance(got, ErrorValue), f"{formula} gave {got}"
    assert float(got) == pytest.approx(expected, rel=1e-5, abs=1e-6), formula


TEXT_AND_LOGIC = [
    ("CLEAN(CHAR(7)&\"ab\")", "ab"),
    ("DOLLAR(1234.567,2)", "$1,234.57"),
    ("LOWER(\"ABC\")", "abc"),
    ("UNICHAR(66)", "B"),
    ("FORMULATEXT(G1)", "=1+2"),
    ("FALSE()", False), ("TRUE()", True),
    ("ISNONTEXT(1)", True), ("ISNONTEXT(\"a\")", False),
    ("ISODD(3)", True), ("ISODD(4)", False),
    ("ISREF(A1)", True), ("ISREF(1)", False),
]


@pytest.mark.parametrize("formula, expected", TEXT_AND_LOGIC)
def test_text_and_logic_match_excel(book, formula, expected):
    assert calc(book, formula) == expected


def test_na_is_the_na_error(book):
    got = calc(book, "NA()")
    assert isinstance(got, ErrorValue) and got.code == "#N/A"


ARRAYS = [
    ("CHOOSECOLS({1,2,3;4,5,6},3,1)", [[3, 1], [6, 4]]),
    ("CHOOSEROWS({1,2,3;4,5,6},2)", [[4, 5, 6]]),
    ("DROP({1,2;3,4;5,6},1)", [[3, 4], [5, 6]]),
    ("TAKE({1,2;3,4;5,6},2)", [[1, 2], [3, 4]]),
    ("TAKE({1,2;3,4;5,6},-1)", [[5, 6]]),
    ("HSTACK({1;2},{3;4})", [[1, 3], [2, 4]]),
    ("VSTACK({1,2},{3,4})", [[1, 2], [3, 4]]),
    ("TOCOL({1,2;3,4})", [[1], [2], [3], [4]]),
    ("TOROW({1,2;3,4})", [[1, 2, 3, 4]]),
    ("MUNIT(2)", [[1, 0], [0, 1]]),
    ("SORTBY({\"a\";\"b\";\"c\"},{3;1;2})", [["b"], ["c"], ["a"]]),
    ("TEXTSPLIT(\"a,b,c\",\",\")", [["a", "b", "c"]]),
]


@pytest.mark.parametrize("formula, expected", ARRAYS)
def test_array_functions_match_excel(book, formula, expected):
    assert grid(calc(book, formula)) == expected


def test_volatile_functions_give_sensible_values(book):
    assert calc(book, "NOW()") > 46000
    dice = calc(book, "RANDBETWEEN(1,6)")
    assert dice in (1, 2, 3, 4, 5, 6)
    block = grid(calc(book, "RANDARRAY(2,2)"))
    assert len(block) == 2 and all(0 <= v < 1 for row in block for v in row)
    assert not math.isnan(calc(book, "RAND()"))


LAMBDAS = [
    ("MAP({1,2,3},LAMBDA(v,v*10))", [[10, 20, 30]]),
    ("MAP({1,2},{10,20},LAMBDA(a,b,a+b))", [[11, 22]]),
    ("BYROW({1,2;3,4},LAMBDA(r,SUM(r)))", [[3], [7]]),
    ("BYCOL({1,2;3,4},LAMBDA(c,SUM(c)))", [[4, 6]]),
    ("SCAN(0,{1,2,3},LAMBDA(a,b,a+b))", [[1, 3, 6]]),
    ("MAKEARRAY(2,3,LAMBDA(r,c,r*c))", [[1, 2, 3], [2, 4, 6]]),
]


@pytest.mark.parametrize("formula, expected", LAMBDAS)
def test_lambda_helpers_match_excel(book, formula, expected):
    assert grid(calc(book, formula)) == expected


def test_lambda_called_at_once_by_let_and_by_name(book):
    wb, s = book
    assert calc(book, "REDUCE(0,{1,2,3},LAMBDA(a,b,a+b))") == 6
    assert calc(book, "LET(f,LAMBDA(x,x*2),f(3))") == 6
    assert calc(book, "LAMBDA(x,x*2)").code == "#CALC!", "left uncalled"
    wb.set_input(s, 30, 0, "=Dbl(4)")
    assert s.cells[(30, 0)].value.code == "#NAME?"
    wb.define_name("Dbl", "LAMBDA(x,x*2)")
    assert s.cells[(30, 0)].value == 8, "defining the name brings the formula to life"
    wb.define_name("Dbl", "LAMBDA(x,x*3)")
    assert s.cells[(30, 0)].value == 12
    wb.define_name("Fact", "LAMBDA(n,IF(n<=1,1,n*Fact(n-1)))")
    assert calc(book, "Fact(5)") == 120, "a named LAMBDA can call itself"
    wb.define_name("PlusA1", "LAMBDA(x,x+Data!$A$1)")
    wb.set_input(s, 31, 0, "=PlusA1(1)")
    assert s.cells[(31, 0)].value == 3
    wb.set_input(s, 0, 0, "10")
    assert s.cells[(31, 0)].value == 11, "a cell the LAMBDA reads recalculates it"
    assert calc(book, "BYROW({1,2;3,4},LAMBDA(r,r))").code == "#CALC!"
