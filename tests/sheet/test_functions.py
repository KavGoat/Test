"""Formulas against the answers Excel gives (Excel 365, 1900 date system).

Each case: the formula typed into F1 of a sheet holding the data below, and
the text the cell shows with General format (or the value, for floats).
"""
from __future__ import annotations

import math

import pytest

from calcforge.sheet.numfmt import format_value
from calcforge.sheet.refs import parse_cell
from calcforge.sheet.workbook import Workbook

DATA = {
    "A1": "10", "A2": "20", "A3": "30", "A4": "40", "A5": "apple",
    "B1": "1", "B2": "2", "B3": "3", "B4": "4", "B5": "TRUE",
    "C1": "Bolt", "C2": "Nut", "C3": "Washer", "C4": "Bolt", "C5": "",
    "D1": "5 kN", "D2": "250 kN", "D3": "1.5 MN", "D4": "800 N",
    "E1": "2026-10-09", "E2": "2024-02-29", "E3": "14:30",
}


@pytest.fixture(scope="module")
def sheet():
    wb = Workbook()
    s = wb.add_sheet("Data")
    for a1, text in DATA.items():
        r = parse_cell(a1)
        wb.set_input(s, r.row, r.col, text)
    return s


def shown(sheet, formula):
    wb = sheet.workbook
    wb.set_input(sheet, 0, 5, formula)
    return sheet.value(0, 5), format_value(sheet.value(0, 5)).text


CASES = [
    # arithmetic and operators
    ("=1+2*3", "7"), ("=(1+2)*3", "9"), ("=-2^2", "4"), ("=2^3^2", "64"), ("=10/4", "2.5"),
    ("=5%", "0.05"), ("=50%*A1", "5"), ('="a"&"b"&1', "ab1"), ("=1/0", "#DIV/0!"),
    ("=A5+1", "#VALUE!"), ('="3"+4', "7"), ("=TRUE+1", "2"), ("=1=1", "TRUE"), ('="a"<"B"', "TRUE"),
    ('=1<"a"', "TRUE"), ("=FALSE<TRUE", "TRUE"), ("=Z99+1", "1"), ("=0.1+0.2=0.3", "TRUE"),
    ("=#N/A", "#N/A"), ("=SQRT(-1)", "#NUM!"),
    # sums and counts
    ("=SUM(A1:A5)", "100"), ("=SUM(A1:A4,5)", "105"), ("=SUM(B1:B5)", "10"), ("=SUM(B1:B4,TRUE)", "11"),
    ("=COUNT(A1:A5)", "4"), ("=COUNTA(A1:C5)", "14"), ("=COUNTBLANK(C1:C6)", "2"),
    ("=AVERAGE(A1:A5)", "25"), ("=MAX(A1:A5)", "40"), ("=MIN(A1:A4)", "10"),
    ("=PRODUCT(B1:B4)", "24"), ("=SUMPRODUCT(A1:A4,B1:B4)", "300"), ("=SUMSQ(B1:B4)", "30"),
    ('=COUNTIF(C1:C5,"Bolt")', "2"), ('=COUNTIF(A1:A5,">15")', "3"), ('=COUNTIF(C1:C5,"*sh*")', "1"),
    ('=COUNTIF(C1:C5,"")', "1"), ('=COUNTIF(C1:C5,"<>Bolt")', "3"),
    ('=SUMIF(C1:C4,"Bolt",A1:A4)', "50"), ('=SUMIFS(A1:A4,C1:C4,"Bolt",B1:B4,">1")', "40"),
    ('=COUNTIFS(C1:C4,"Bolt",A1:A4,"<20")', "1"), ('=AVERAGEIF(C1:C4,"Bolt",A1:A4)', "25"),
    ('=MAXIFS(A1:A4,C1:C4,"Bolt")', "40"), ('=MINIFS(A1:A4,C1:C4,"Bolt")', "10"),
    ("=MEDIAN(A1:A4)", "25"), ("=MODE(1,2,2,3)", "2"), ("=LARGE(A1:A4,2)", "30"), ("=SMALL(A1:A4,1)", "10"),
    ("=RANK(30,A1:A4)", "2"), ("=RANK(30,A1:A4,1)", "3"),
    ("=PERCENTILE(A1:A4,0.25)", "17.5"), ("=QUARTILE(A1:A4,3)", "32.5"),
    ("=STDEV(A1:A4)", "12.90994449"), ("=STDEVP(A1:A4)", "11.18033989"), ("=VAR(A1:A4)", "166.6666667"),
    # rounding
    ("=ROUND(2.675,2)", "2.68"), ("=ROUND(-2.5,0)", "-3"), ("=ROUND(1234.5,-2)", "1200"),
    ("=ROUNDUP(3.141,2)", "3.15"), ("=ROUNDDOWN(-3.149,2)", "-3.14"), ("=INT(-3.5)", "-4"),
    ("=TRUNC(-3.5)", "-3"), ("=MROUND(10,3)", "9"), ("=CEILING(4.3,0.5)", "4.5"), ("=FLOOR(4.7,0.5)", "4.5"),
    ("=MOD(-3,2)", "1"), ("=MOD(5,0)", "#DIV/0!"), ("=QUOTIENT(7,2)", "3"), ("=EVEN(3)", "4"), ("=ODD(4)", "5"),
    ("=ABS(-4)", "4"), ("=SIGN(-4)", "-1"), ("=FACT(5)", "120"), ("=COMBIN(5,2)", "10"), ("=GCD(12,18)", "6"),
    ("=LCM(4,6)", "12"), ("=POWER(2,10)", "1024"), ("=EXP(1)", "2.718281828"), ("=LN(EXP(2))", "2"),
    ("=LOG(100)", "2"), ("=LOG(8,2)", "3"), ("=PI()", "3.141592654"), ("=DEGREES(PI())", "180"),
    ("=SIN(PI()/2)", "1"), ("=ATAN2(1,1)", "0.785398163"), ("=SQRT(16)", "4"),
    # logic
    ('=IF(A1>5,"big","small")', "big"), ("=IF(FALSE,1)", "FALSE"), ('=IFS(A1>50,"a",A1>5,"b")', "b"),
    ("=IFERROR(1/0,99)", "99"), ("=IFNA(#N/A,1)", "1"), ("=AND(TRUE,1>0)", "TRUE"), ("=OR(FALSE,0)", "FALSE"),
    ("=XOR(TRUE,TRUE)", "FALSE"), ("=NOT(0)", "TRUE"), ('=SWITCH(2,1,"one",2,"two","other")', "two"),
    ('=CHOOSE(3,"a","b","c")', "c"), ("=LET(x,5,y,x*2,x+y)", "15"),
    # lookup
    ("=VLOOKUP(25,A1:B4,2)", "2"), ("=VLOOKUP(30,A1:B4,2,FALSE)", "3"), ("=VLOOKUP(35,A1:B4,2,FALSE)", "#N/A"),
    ("=VLOOKUP(5,A1:B4,2)", "#N/A"), ("=HLOOKUP(2,B1:B4,1)", "1"), ("=HLOOKUP(2,A1:B4,2,FALSE)", "#N/A"), ("=MATCH(30,A1:A4,0)", "3"),
    ("=MATCH(35,A1:A4)", "3"), ('=MATCH("w*",C1:C4,0)', "3"), ("=INDEX(A1:B4,2,2)", "2"),
    ("=INDEX(A1:A4,3)", "30"), ("=SUM(INDEX(A1:B4,0,2))", "10"), ('=XLOOKUP("Nut",C1:C4,A1:A4)', "20"),
    ('=XLOOKUP("x",C1:C4,A1:A4,"none")', "none"), ("=XLOOKUP(25,A1:A4,B1:B4,,-1)", "2"),
    ("=XMATCH(40,A1:A4)", "4"), ("=SUM(OFFSET(A1,1,0,2,1))", "50"), ('=INDIRECT("A"&2)', "20"),
    ('=SUM(INDIRECT("A1:A3"))', "60"), ("=ROW(A7)", "7"), ("=COLUMN(D1)", "4"), ("=ROWS(A1:B4)", "4"),
    ("=COLUMNS(A1:B4)", "2"), ('=ADDRESS(2,3)', "$C$2"), ('=ADDRESS(2,3,4)', "C2"),
    ("=LOOKUP(25,A1:A4,B1:B4)", "2"), ("=SUM(A1:INDEX(A1:A4,2))", "30"),
    # text
    ('=LEFT("Engineer",3)', "Eng"), ('=RIGHT("Engineer",2)', "er"), ('=MID("Engineer",3,4)', "gine"),
    ('=LEN("abc")', "3"), ('=UPPER("ab")', "AB"), ('=PROPER("hello world")', "Hello World"),
    ('=TRIM("  a   b  ")', "a b"), ('=SUBSTITUTE("a-b-c","-","+")', "a+b+c"),
    ('=SUBSTITUTE("a-b-c","-","+",2)', "a-b+c"), ('=REPLACE("abcdef",2,3,"X")', "aXef"),
    ('=FIND("b","abcb")', "2"), ('=FIND("B","abcb")', "#VALUE!"), ('=SEARCH("B","abcb")', "2"),
    ('=REPT("ab",3)', "ababab"), ('=EXACT("a","A")', "FALSE"), ('=CONCAT(C1:C2)', "BoltNut"),
    ('=TEXTJOIN(", ",TRUE,C1:C5)', "Bolt, Nut, Washer, Bolt"), ('=VALUE("12.5")', "12.5"),
    ('=TEXT(1234.567,"#,##0.00")', "1,234.57"), ('=TEXT(0.25,"0%")', "25%"), ('=CHAR(65)', "A"),
    ('=CODE("A")', "65"), ('=FIXED(1234.567,1)', "1,234.6"), ('=TEXTBEFORE("a-b-c","-")', "a"),
    ('=TEXTAFTER("a-b-c","-",2)', "c"), ('=T(A1)', ""), ('=N(TRUE)', "1"),
    # information
    ("=ISBLANK(Z1)", "TRUE"), ("=ISNUMBER(A1)", "TRUE"), ("=ISTEXT(A5)", "TRUE"), ("=ISERROR(1/0)", "TRUE"),
    ("=ISNA(#N/A)", "TRUE"), ("=ISERR(#N/A)", "FALSE"), ("=ISEVEN(4)", "TRUE"), ("=ISLOGICAL(B5)", "TRUE"),
    ("=ERROR.TYPE(1/0)", "2"), ("=TYPE(A5)", "2"), ("=ISFORMULA(A1)", "FALSE"),
    # dates
    ("=DATE(2026,10,9)", "46304"), ("=YEAR(E1)", "2026"), ("=MONTH(E1)", "10"), ("=DAY(E1)", "9"),
    ("=WEEKDAY(E1)", "6"), ("=WEEKDAY(E1,2)", "5"), ("=E1-E2", "953"), ("=EDATE(E2,12)", "45716"),
    ("=EOMONTH(E2,1)", "45382"), ("=DAYS(E1,E2)", "953"), ('=DATEDIF(E2,E1,"Y")', "2"),
    ('=DATEDIF(E2,E1,"M")', "31"), ("=HOUR(E3)", "14"), ("=MINUTE(E3)", "30"), ("=TIME(14,30,0)", "0.604166667"),
    ("=DATE(2026,13,1)", "46388"), ("=NETWORKDAYS(DATE(2026,10,5),DATE(2026,10,16))", "10"),
    ("=WORKDAY(DATE(2026,10,9),1)", "46307"), ("=DAY(60)", "29"), ("=DATE(1900,3,1)", "61"),
    ('=TEXT(E1,"dddd d mmm yyyy")', "Friday 9 Oct 2026"),
    # arrays
    ("=SUM(A1:A4*B1:B4)", "300"), ("=SUM({1,2;3,4})", "10"), ("=MMULT({1,2},{3;4})", "11"),
    ("=MDETERM({1,2;3,4})", "-2"), ("=INDEX(MINVERSE({2,0;0,4}),2,2)", "0.25"),
    ("=SUM(SEQUENCE(4))", "10"), ("=SUM(FILTER(A1:A4,A1:A4>15))", "90"), ("=ROWS(UNIQUE(C1:C4))", "3"),
    ("=INDEX(SORT(A1:A4,1,-1),1)", "40"), ("=SUM(TRANSPOSE(A1:A4))", "100"),
    ("=SUM(IF(A1:A4>15,1,0))", "3"),
    # money
    ("=PMT(0.05/12,360,200000)", "-1073.64325"), ("=FV(0.05,10,-100)", "1257.789254"),
    ("=NPV(0.1,100,100)", "173.553719"), ("=IRR({-100,60,60})", "0.130662386"),
    # units
    ("=D1+D4", "5.8 kN"), ("=SUM(D1:D4)", "1755.8 kN"), ("=D1*2", "10 kN"), ("=D1/2 m", "2.5 kN/m"),
    ("=D1/D4", "6.25"), ("=D1+1 m", "#UNITS!"), ("=AVERAGE(D1:D2)", "127.5 kN"), ("=MAX(D1:D4)", "1500 kN"),
    ("=ROUND(D1/3,2)", "1.67 kN"), ('=VALUEIN(D3,"kN")', "1500"), ('=CONVERT(D1,"N")', "5000 N"),
    ('=CONVERT(1,"in","mm")', "25.4"), ("=D1>D4", "TRUE"), ("=D1>0", "TRUE"), ("=SQRT(9 m^2)", "3 m"),
    ("=5 kN*2 m", "10 kN·m"), ("=10 kN/m*3 m", "30 kN"), ("=A1/'kN", "10 kN^-1"),
    ('=INTERP(25,A1:A4,B1:B4)', "2.5"), ('=UNITOF(D1)', "kN"), ("=D1/1 kN", "5"), ("=20 °C", "20 °C"),
    ("=STDEV(D1:D2)", "173.2411614 kN"),
]


@pytest.mark.parametrize("formula,expected", CASES, ids=[c[0] for c in CASES])
def test_excel_answers(sheet, formula, expected):
    value, text = shown(sheet, formula)
    assert text == expected, (formula, value)


def test_volatile_functions_recalculate(sheet):
    wb = sheet.workbook
    wb.set_input(sheet, 10, 5, "=RAND()")
    first = sheet.value(10, 5)
    assert 0 <= first < 1
    wb.set_input(sheet, 11, 5, "1")
    assert sheet.value(10, 5) != first, "RAND() is recalculated on every change, as in Excel"


def test_today(sheet):
    import datetime

    value, _ = shown(sheet, "=TODAY()")
    from calcforge.sheet.dates import date_from_serial

    assert date_from_serial(value) == datetime.date.today()


def test_unknown_function_is_name_error(sheet):
    assert shown(sheet, "=NOSUCHFUNCTION(1)")[1] == "#NAME?"


def test_unknown_name_is_name_error(sheet):
    assert shown(sheet, "=nosuchname+1")[1] == "#NAME?"
