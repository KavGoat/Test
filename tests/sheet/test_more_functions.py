"""The Excel functions added on 2026-10-10 (sheet/morefunctions.py), each
against Microsoft's documented examples: number bases and bits, roman
numerals, complex numbers, Bessel and error functions, the distributions
and tests, descriptive statistics, regression, money and depreciation,
text and information, and CONVERT in Excel's own unit codes."""
from __future__ import annotations

import pytest

from calcforge.sheet.values import Array, ErrorValue
from calcforge.sheet.workbook import Workbook


@pytest.fixture
def book():
    wb = Workbook()
    return wb, wb.add_sheet("S")


def calc(book, formula):
    wb, s = book
    wb.set_input(s, 0, 0, "=" + formula)
    if s.spills.get((0, 0)):
        return s.spill_values[(0, 0)]
    return s.cells[(0, 0)].value


# Microsoft shows some answers rounded (DDB's $1.32 is 1.3151); those are given in full here
CASES = [
 ("BASE(7,2)", "111"), ("BASE(100,16)", "64"), ("BASE(15,2,10)", "0000001111"),
 ("DECIMAL(\"FF\",16)", 255), ("DECIMAL(111,2)", 7), ("DECIMAL(\"zap\",36)", 45745),
 ("DEC2BIN(9,4)", "1001"), ("DEC2BIN(-100)", "1110011100"), ("DEC2HEX(100,4)", "0064"), ("DEC2HEX(-54)", "FFFFFFFFCA"),
 ("DEC2HEX(28)", "1C"), ("DEC2OCT(58,3)", "072"), ("DEC2OCT(-100)", "7777777634"),
 ("BIN2DEC(1100100)", 100), ("BIN2DEC(1111111111)", -1), ("BIN2HEX(11111011,4)", "00FB"), ("BIN2HEX(1110)", "E"),
 ("BIN2HEX(1111111111)", "FFFFFFFFFF"), ("BIN2OCT(1001,3)", "011"), ("BIN2OCT(1100100)", "144"), ("BIN2OCT(1111111111)", "7777777777"),
 ("HEX2BIN(\"F\",8)", "00001111"), ("HEX2BIN(\"B7\")", "10110111"), ("HEX2BIN(\"FFFFFFFFFF\")", "1111111111"),
 ("HEX2DEC(\"A5\")", 165), ("HEX2DEC(\"FFFFFFFF5B\")", -165), ("HEX2DEC(\"3DA408B9\")", 1034160313),
 ("HEX2OCT(\"F\",3)", "017"), ("HEX2OCT(\"3B4E\")", "35516"), ("HEX2OCT(\"FFFFFFFF00\")", "7777777400"),
 ("OCT2BIN(3,3)", "011"), ("OCT2BIN(7777777000)", "1000000000"), ("OCT2DEC(54)", 44), ("OCT2DEC(7777777533)", -165),
 ("OCT2HEX(100,4)", "0040"), ("OCT2HEX(7777777533)", "FFFFFFFF5B"),
 ("BITAND(1,5)", 1), ("BITAND(13,25)", 9), ("BITOR(23,10)", 31), ("BITXOR(5,3)", 6), ("BITLSHIFT(4,2)", 16), ("BITRSHIFT(13,2)", 3),
 ("DELTA(5,4)", 0), ("DELTA(5,5)", 1), ("DELTA(0.5,0)", 0), ("GESTEP(5,4)", 1), ("GESTEP(5,5)", 1), ("GESTEP(-4,-5)", 1), ("GESTEP(-1)", 0),
 ("ROMAN(499,0)", "CDXCIX"), ("ROMAN(499,1)", "LDVLIV"), ("ROMAN(499,2)", "XDIX"), ("ROMAN(499,3)", "VDIV"), ("ROMAN(499,4)", "ID"),
 ("ROMAN(2013,0)", "MMXIII"), ("ROMAN(1999)", "MCMXCIX"), ("ARABIC(\"LVII\")", 57), ("ARABIC(\"mcmxii\")", 1912), ("ARABIC(\"\")", 0), ("ARABIC(\"-MMXI\")", -2011),
 ("COMPLEX(3,4)", "3+4i"), ("COMPLEX(3,4,\"j\")", "3+4j"), ("COMPLEX(0,1)", "i"), ("COMPLEX(1,0)", "1"),
 ("IMABS(\"5+12i\")", 13), ("IMAGINARY(\"3+4i\")", 4), ("IMAGINARY(\"0-j\")", -1), ("IMAGINARY(4)", 0), ("IMREAL(\"6-9i\")", 6),
 ("IMARGUMENT(\"3+4i\")", 0.92729522), ("IMCONJUGATE(\"3+4i\")", "3-4i"), ("IMCOS(\"1+i\")", "0.833730025131149-0.988897705762865i"),
 ("IMDIV(\"-238+240i\",\"10+24i\")", "5+12i"), ("IMEXP(\"1+i\")", "1.46869393991589+2.28735528717884i"),
 ("IMLN(\"3+4i\")", "1.6094379124341+0.927295218001612i"), ("IMLOG10(\"3+4i\")", "0.698970004336019+0.402719196273373i"),
 ("IMLOG2(\"3+4i\")", "2.32192809488736+1.33780421245098i"), ("IMPOWER(\"2+3i\",3)", "-46+9.00000000000001i"),
 ("IMPRODUCT(\"3+4i\",\"5-3i\")", "27+11i"), ("IMPRODUCT(\"1+2i\",30)", "30+60i"), ("IMSIN(\"4+3i\")", "-7.61923172032141-6.548120040911i"),
 ("IMSQRT(\"1+i\")", "1.09868411346781+0.455089860562227i"), ("IMSUB(\"13+4i\",\"5+3i\")", "8+i"), ("IMSUM(\"3+4i\",\"5-3i\")", "8+i"),
 ("IMTAN(\"4+3i\")", "0.00490825806749606+1.00070953606723i"), ("IMSINH(\"4+3i\")", "-27.0168132580039+3.85373803791938i"),
 ("BESSELJ(1.9,2)", 0.329925829), ("BESSELY(2.5,1)", 0.145918138), ("BESSELI(1.5,1)", 0.981666428), ("BESSELK(1.5,1)", 0.277387804),
 ("ERF(0.745)", 0.70792892), ("ERF(1,2)", 0.15262), ("ERF.PRECISE(0.745)", 0.70792892), ("ERFC(1)", 0.15729921),
 ("GAMMA(2.5)", 1.329340388), ("GAMMA(0.5)", 1.772453851), ("GAMMALN(4)", 1.791759469),
 ("BETA.DIST(2,8,10,TRUE,1,3)", 0.6854706), ("BETA.DIST(2,8,10,FALSE,1,3)", 1.4837646), ("BETA.INV(0.685470581,8,10,1,3)", 2),
 ("BINOM.DIST(6,10,0.5,FALSE)", 0.2050781), ("BINOM.DIST.RANGE(60,0.75,48)", 0.083974967), ("BINOM.DIST.RANGE(60,0.75,45,50)", 0.523629793),
 ("BINOM.INV(6,0.5,0.75)", 4), ("CRITBINOM(6,0.5,0.75)", 4),
 ("CHISQ.DIST(0.5,1,TRUE)", 0.52049988), ("CHISQ.DIST(2,3,FALSE)", 0.20755375), ("CHISQ.DIST.RT(18.307,10)", 0.0500006),
 ("CHISQ.INV(0.93,1)", 3.28302029), ("CHISQ.INV(0.6,2)", 1.83258146), ("CHISQ.INV.RT(0.050001,10)", 18.306973),
 ("CHISQ.TEST({58,35;11,25;10,23},{45.35,47.65;17.56,18.44;16.09,16.91})", 0.0003082),
 ("CONFIDENCE.NORM(0.05,2.5,50)", 0.692952), ("CONFIDENCE.T(0.05,1,50)", 0.284196855),
 ("EXPON.DIST(0.2,10,TRUE)", 0.86466472), ("EXPON.DIST(0.2,10,FALSE)", 1.35335283),
 ("F.DIST(15.2069,6,4,TRUE)", 0.99), ("F.DIST(15.2069,6,4,FALSE)", 0.0012238), ("F.DIST.RT(15.2069,6,4)", 0.01),
 ("F.INV(0.01,6,4)", 0.10930991), ("F.INV.RT(0.01,6,4)", 15.20686), ("F.TEST({6,7,9,15,21},{20,28,31,38,40})", 0.64831785),
 ("FISHER(0.75)", 0.9729551), ("FISHERINV(0.972955)", 0.75), ("GAMMA.DIST(10.00001131,9,2,FALSE)", 0.032639),
 ("GAMMA.DIST(10.00001131,9,2,TRUE)", 0.068094), ("GAMMA.INV(0.068094,9,2)", 10.0000112), ("GAUSS(2)", 0.47724987),
 ("HYPGEOM.DIST(1,4,8,20,TRUE)", 0.465428277), ("HYPGEOM.DIST(1,4,8,20,FALSE)", 0.363261094),
 ("KURT(3,4,5,2,3,4,5,6,4,7)", -0.151799637), ("SKEW(3,4,5,2,3,4,5,6,4,7)", 0.359543), ("SKEW.P(3,4,5,2,3,4,5,6,4,7)", 0.303193),
 ("LOGNORM.DIST(4,3.5,1.2,TRUE)", 0.0390836), ("LOGNORM.DIST(4,3.5,1.2,FALSE)", 0.0176176), ("LOGNORM.INV(0.039084,3.5,1.2)", 4.0000252),
 ("NEGBINOM.DIST(10,5,0.25,TRUE)", 0.3135141), ("NEGBINOM.DIST(10,5,0.25,FALSE)", 0.0550487),
 ("PHI(0.75)", 0.3011374), ("POISSON.DIST(2,5,TRUE)", 0.124652), ("POISSON.DIST(2,5,FALSE)", 0.08422434),
 ("T.DIST(60,1,TRUE)", 0.99469533), ("T.DIST(8,3,FALSE)", 0.00073691), ("T.DIST.2T(1.959999998,60)", 0.054645),
 ("T.DIST.RT(1.959999998,60)", 0.027322), ("T.INV(0.75,2)", 0.8164966), ("T.INV.2T(0.546449,60)", 0.606533),
 ("TDIST(1.959999998,60,2)", 0.054645), ("TINV(0.546449,60)", 0.606533),
 ("T.TEST({3,4,5,8,9,1,2,4,5},{6,19,3,2,14,4,5,17,1},2,1)", 0.196016),
 ("WEIBULL.DIST(105,20,100,TRUE)", 0.929581), ("WEIBULL.DIST(105,20,100,FALSE)", 0.035589),
 ("Z.TEST({3,6,7,8,6,5,4,2,1,9},4)", 0.090574), ("Z.TEST({3,6,7,8,6,5,4,2,1,9},6)", 0.863043),
 ("PROB({0,1,2,3},{0.2,0.3,0.1,0.4},2)", 0.1), ("PROB({0,1,2,3},{0.2,0.3,0.1,0.4},1,3)", 0.8),
 ("VARA(1345,1301,1368,1322,1310,1370,1318,1350,1303,1299)", 754.2667), ("VARPA(1345,1301,1368,1322,1310,1370,1318,1350,1303,1299)", 678.84),
 ("STDEVPA(1345,1301,1368,1322,1310,1370,1318,1350,1303,1299)", 26.05456), ("TRIMMEAN({4,5,6,7,2,3,4,5,1,2,3},0.2)", 3.777778),
 ("PERCENTRANK.INC({13,12,11,8,4,3,2,1,1,1},2)", 0.333), ("PERCENTRANK.INC({13,12,11,8,4,3,2,1,1,1},4)", 0.555),
 ("PERCENTRANK.INC({13,12,11,8,4,3,2,1,1,1},8)", 0.666), ("PERCENTRANK.INC({13,12,11,8,4,3,2,1,1,1},5)", 0.583),
 ("PERCENTRANK.EXC({1,2,3,6,6,6,7,8,9},7)", 0.7), ("PERCENTRANK.EXC({1,2,3,6,6,6,7,8,9},5.43)", 0.381),
 ("PERCENTRANK.EXC({1,2,3,6,6,6,7,8,9},5.43,1)", 0.3), ("RANK.AVG(94,{89,88,92,101,94,97,95})", 4), ("RANK.AVG(3,{1,3,3,5})", 2.5),
 ("STEYX({2,3,9,1,8,7,5},{6,5,11,7,5,4,4})", 3.305719), ("COMBINA(4,3)", 20), ("COMBINA(10,3)", 220),
 ("PERMUTATIONA(3,2)", 9), ("PERMUTATIONA(2,2)", 4), ("MULTINOMIAL(2,3,4)", 1260),
 ("SERIESSUM(PI()/4,0,2,{1,-0.5,0.041666667,-0.001388889})", 0.707103), ("SUMX2MY2({2,3,9,1,8,7,5},{6,5,11,7,5,4,4})", -55),
 ("SUMX2PY2({2,3,9,1,8,7,5},{6,5,11,7,5,4,4})", 521), ("SUMXMY2({2,3,9,1,8,7,5},{6,5,11,7,5,4,4})", 79),
 ("IPMT(0.1/12,1,36,8000)", -66.66667), ("IPMT(0.1,3,3,8000)", -292.4471), ("PPMT(0.1/12,1,24,2000)", -75.623186),
 ("PPMT(0.08,10,10,200000)", -27598.05), ("CUMIPMT(0.09/12,30*12,125000,13,24,0)", -11135.23),
 ("CUMIPMT(0.09/12,30*12,125000,1,1,0)", -937.5), ("CUMPRINC(0.09/12,30*12,125000,13,24,0)", -934.1071234),
 ("CUMPRINC(0.09/12,30*12,125000,1,1,0)", -68.27827118), ("ISPMT(0.1/12,1,36,8000000)", -64814.8148),
 ("SLN(30000,7500,10)", 2250), ("SYD(30000,7500,10,1)", 4090.909091), ("SYD(30000,7500,10,10)", 409.0909091),
 ("DB(1000000,100000,6,1,7)", 186083.33), ("DB(1000000,100000,6,2,7)", 259639.42), ("DB(1000000,100000,6,7,7)", 15845.10),
 ("DDB(2400,300,10*365,1)", 1.315068493), ("DDB(2400,300,10*12,1,2)", 40), ("DDB(2400,300,10,1,2)", 480), ("DDB(2400,300,10,2,1.5)", 306), ("DDB(2400,300,10,10)", 22.1225472),
 ("VDB(2400,300,10*365,0,1)", 1.315068493), ("VDB(2400,300,10*12,0,1)", 40), ("VDB(2400,300,10,0,1)", 480), ("VDB(2400,300,10*12,6,18)", 396.31),
 ("VDB(2400,300,10*12,6,18,1.5)", 311.81), ("VDB(2400,300,10,0,0.875,1.5)", 315),
 ("EFFECT(0.0525,4)", 0.053542667), ("NOMINAL(0.053543,4)", 0.05250032), ("FVSCHEDULE(1,{0.09,0.11,0.1})", 1.33089),
 ("PDURATION(0.025,2000,2200)", 3.8598), ("PDURATION(0.025/12,1000,1200)", 87.6054764), ("RRI(96,10000,11000)", 0.0009933),
 ("MIRR({-120000,39000,30000,21000,37000,46000},0.1,0.12)", 0.126094), ("MIRR({-120000,39000,30000,21000},0.1,0.12)", -0.048044655),
 ("XNPV(0.09,{-10000,2750,4250,3250,2750},{39448,39508,39751,39859,39904})", 2086.6476),
 ("XIRR({-10000,2750,4250,3250,2750},{39448,39508,39751,39859,39904},0.1)", 0.373362535),
 ("ACCRINT(39508,39691,39569,0.1,1000,2,0)", 16.666667),
 ("ASC(\"ＥＸＣＥＬ\")", "EXCEL"), ("ENCODEURL(\"http://contoso.sharepoint.com/Finance/Profit and Loss Statement.xlsx\")",
   "http%3A%2F%2Fcontoso.sharepoint.com%2FFinance%2FProfit%20and%20Loss%20Statement.xlsx"),
 ("HYPERLINK(\"http://example.com\",\"Click\")", "Click"), ("VALUETOTEXT(\"Hello\",1)", "\"Hello\""), ("VALUETOTEXT(1234.01)", "1234.01"),
 ("ARRAYTOTEXT({\"a\",1;TRUE,2})", "a, 1, TRUE, 2"), ("ARRAYTOTEXT({\"a\",1;TRUE,2},1)", "{\"a\",1;TRUE,2}"),
 ("SHEETS()", 1), ("CONVERT(1,\"lbm\",\"kg\")", 0.4535924), ("CONVERT(68,\"F\",\"C\")", 20), ("CONVERT(2.5,\"ft\",\"sec\")", None),
 ("CONVERT(6,\"tsp\",\"tbs\")", 2), ("CONVERT(6,\"gal\",\"l\")", 22.71247), ("CONVERT(6,\"mi\",\"km\")", 9.656064),
 ("CONVERT(6,\"km\",\"mi\")", 3.728227), ("CONVERT(6,\"in\",\"ft\")", 0.5), ("CONVERT(6,\"cm\",\"in\")", 2.362205),
 ("CONVERT(1,\"byte\",\"kibyte\")", 1 / 1024), ("CONVERT(1024,\"byte\",\"kibyte\")", 1), ("CONVERT(1,\"m2\",\"ft2\")", 10.76391),
 ("CONVERT(100,\"ft2\",\"m2\")", 9.290304), ("CONVERT(1,\"m3\",\"ft3\")", 35.31467), ("CONVERT(1,\"yr\",\"day\")", 365.25),
 ("CONVERT(10,\"kN\",\"lbf\")", 2248.089), ("CONVERT(1,\"MPa\",\"psi\")", 145.0377), ("CONVERT(100,\"C\",\"K\")", 373.15),
 ("CONVERT(0,\"C\",\"Rank\")", 491.67), ("CONVERT(1,\"HP\",\"W\")", 745.6999), ("CONVERT(1,\"oz\",\"ml\")", 29.57353),
]


@pytest.mark.parametrize("formula, expected", CASES)
def test_as_microsoft_documents_it(book, formula, expected):
    got = calc(book, formula)
    if expected is None:
        assert isinstance(got, ErrorValue), f"{formula} should be an error, gave {got!r}"
    elif isinstance(expected, str):
        assert got == expected, formula
    else:
        assert not isinstance(got, ErrorValue), f"{formula} gave {got}"
        assert got == pytest.approx(expected, rel=2e-5, abs=1e-6), formula


def test_lambda_parameters_can_be_left_out(book):
    assert calc(book, "LAMBDA(a,b,IF(ISOMITTED(b),a,a+b))(1)") == 1
    assert calc(book, "LAMBDA(a,b,IF(ISOMITTED(b),a,a+b))(1,2)") == 3
    assert calc(book, "LAMBDA(a,b,IF(ISOMITTED(b),a,a+b))(1,)") == 1, "left empty counts as left out"
    assert calc(book, "LAMBDA(a,ISOMITTED(a))(5)") is False
    assert calc(book, "LAMBDA(a,a)(1,2)").code == "#VALUE!", "more than it takes"


def test_day_zero_and_the_leap_day_that_never_was(book):
    assert [calc(book, f"{f}(0)") for f in ("YEAR", "MONTH", "DAY")] == [1900, 1, 0]
    assert [calc(book, f"{f}(60)") for f in ("YEAR", "MONTH", "DAY")] == [1900, 2, 29]
    assert [calc(book, f"{f}(61)") for f in ("YEAR", "MONTH", "DAY")] == [1900, 3, 1]


def test_arrays_from_the_new_functions(book):
    assert [list(r) for r in calc(book, "FREQUENCY({79,85,78,85,50,81,95,88,97},{70,79,89})").rows] == \
        [[1], [2], [4], [2]]
    assert [list(r) for r in calc(book, "MODE.MULT({1,2,3,4,3,2,1,2,3})").rows] == [[2], [3]]
    assert [list(r) for r in calc(book, "WRAPROWS({1,2,3,4,5},2,0)").rows] == [[1, 2], [3, 4], [5, 0]]
    assert [list(r) for r in calc(book, "WRAPCOLS({1,2,3,4,5},2,0)").rows] == [[1, 3, 5], [2, 4, 0]]
    assert [list(r) for r in calc(book, "EXPAND({1,2},2,3,\"-\")").rows] == [[1, 2, "-"], ["-", "-", "-"]]
    m, b = calc(book, "LINEST({1,9,5,7},{0,4,2,3})").rows[0]
    assert (m, b) == (pytest.approx(2), pytest.approx(1))
    stats = calc(book, "LINEST({1,9,5,7},{0,4,2,3},TRUE,TRUE)")
    assert stats.height == 5 and stats.rows[2][0] == pytest.approx(1)      # a perfect fit: R² = 1
    two = calc(book, "LINEST({142000;144000;151000;150000;139000;169000;126000;142900;163000;169000;149000},"
                     "{2310,2,2,20;2333,2,2,12;2356,3,1.5,33;2379,3,2,43;2402,2,3,53;2425,4,2,23;"
                     "2448,2,1.5,99;2471,2,2,34;2494,3,3,23;2517,4,4,55;2540,2,3,22})")
    assert [round(v, 2) for v in two.rows[0]] == [-234.24, 2553.21, 12529.77, 27.64, 52317.83], \
        "Microsoft's office-building example"
    assert calc(book, "LOGEST({33100,47300,69000,102000,150000,220000},{11,12,13,14,15,16})").rows[0][0] == \
        pytest.approx(1.463275628)
    grown = calc(book, "GROWTH({33100;47300;69000;102000;150000;220000},{11;12;13;14;15;16},{17;18})")
    assert [round(r[0], 2) for r in grown.rows] == [320196.72, 468536.05]


def test_database_functions(book):
    wb, s = book
    rows = [("Tree", "Height", "Age", "Yield", "Profit"), ("Apple", 18, 20, 14, 105), ("Pear", 12, 12, 10, 96),
            ("Cherry", 13, 14, 9, 105), ("Apple", 14, 15, 10, 75), ("Pear", 9, 8, 8, 76.8),
            ("Apple", 8, 9, 6, 45)]
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            wb.set_input(s, 10 + r, c, str(v))
    crit = [("Tree", "Height", "Age", "Yield", "Profit", "Height"), ('="=Apple"', ">10", "", "", "", "<16"),
            ('="=Pear"', "", "", "", "", "")]
    for r, row in enumerate(crit):
        for c, v in enumerate(row):
            wb.set_input(s, 2 + r, c, v)
    db, cr = "A11:E17", "A3:F5"
    assert calc(book, f"DCOUNT({db},\"Age\",A3:F4)") == 1
    assert calc(book, f"DCOUNTA({db},\"Profit\",A3:F4)") == 1
    assert calc(book, f"DMAX({db},\"Profit\",{cr})") == 96
    assert calc(book, f"DMIN({db},\"Profit\",A3:B4)") == 75
    assert calc(book, f"DSUM({db},\"Profit\",A3:A4)") == 225
    assert calc(book, f"DSUM({db},\"Profit\",A3:F4)") == 75
    assert calc(book, f"DPRODUCT({db},\"Yield\",{cr})") == 800
    assert calc(book, f"DAVERAGE({db},\"Yield\",A3:B4)") == 12
    assert calc(book, f"DAVERAGE({db},3,{db})") == pytest.approx(13)
    assert calc(book, f"DSTDEV({db},\"Yield\",A3:A5)") == pytest.approx(2.966479)
    assert calc(book, f"DSTDEVP({db},\"Yield\",A3:A5)") == pytest.approx(2.6532998)
    assert calc(book, f"DVAR({db},\"Yield\",A3:A5)") == pytest.approx(8.8)
    assert calc(book, f"DVARP({db},\"Yield\",A3:A5)") == pytest.approx(7.04)
    assert calc(book, f"DGET({db},\"Yield\",{cr})").code == "#NUM!", "more than one record"


def test_regular_expressions_and_the_last_few(book):
    assert calc(book, 'REGEXTEST("BM-205","^[A-Z]{2}-\\d+$")') is True
    assert [r[0] for r in calc(book, 'REGEXEXTRACT("UB 406x178x60","\\d+",1)').rows] == ["406", "178", "60"]
    assert list(calc(book, 'REGEXEXTRACT("UB 406x178x60","(\\d+)x(\\d+)",2)').rows[0]) == ["406", "178"]
    assert calc(book, 'REGEXREPLACE("406x178","(\\d+)x(\\d+)","$2 by $1")') == "178 by 406"
    assert calc(book, 'REGEXREPLACE("a1b2c3","\\d","#",2)') == "a1b#c3", "only the second"
    assert calc(book, "ACOTH(6)") == pytest.approx(0.168236118)
    assert calc(book, "PERCENTOF({1,2},{1,2,3,4})") == pytest.approx(0.3)
    assert calc(book, "DOLLARDE(1.02,16)") == pytest.approx(1.125)
    assert calc(book, "DOLLARFR(1.125,16)") == pytest.approx(1.02)
    assert calc(book, 'JIS("AB 1")') == "ＡＢ　１" and calc(book, 'ASC(JIS("AB 1"))') == "AB 1"
    assert calc(book, 'LENB("abc")') == 3


def test_trimrange_drops_the_empty_edges(book):
    wb, s = book
    wb.set_input(s, 40, 2, "5")
    wb.set_input(s, 42, 3, "7")
    assert calc(book, "ROWS(TRIMRANGE(A38:H60))") == 3
    assert calc(book, "COLUMNS(TRIMRANGE(A38:H60))") == 2
    assert calc(book, "SUM(TRIMRANGE(A38:H60))") == 12
    assert calc(book, "ROWS(TRIMRANGE(A38:H60,2))") == 6, "trailing rows only"
