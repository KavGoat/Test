"""Every function against Excel's rules, on the awkward arguments (the
user, 2026-10-26: "make sure that the min error does not occur for any
other excel function. Compare all excel functions we have and check for
any other inconsistencies too").

All 472 functions were given their arguments as cells and as names of
those cells, and worked out through the compiled closures and the plain
tree walk — the same answer every way (the MIN(ae_3, ae_4) class of bug).
Then every function was given text, blanks, TRUE, numeric text, #N/A, a
date, in cells and typed in, and compared with LibreOffice; each
difference was judged against Excel's documented behaviour. What was
wrong is pinned here.
"""
from __future__ import annotations

import pytest

from calcforge.sheet import formula as F
from calcforge.sheet.evaluate import evaluate_cell
from calcforge.sheet.functions import FUNCTIONS
from calcforge.sheet.values import Array, ErrorValue
from calcforge.sheet.workbook import Workbook


@pytest.fixture
def wb():
    book = Workbook()
    data = book.add_sheet("Data")
    # A1..A8: number, text, number, blank, TRUE, numeric text, #N/A, fraction
    for i, text in enumerate(["49", "N/A", "50", "", "TRUE", "'5", "=NA()", "0.5"]):
        if text:
            book.set_input(data, i, 0, text)
        book.set_input(data, i, 1, str(i + 1))
    book.add_sheet("Test")
    return book


def value(wb, text):
    test = wb.sheet("Test")
    wb.set_input(test, 0, 0, text)
    return test.cells[(0, 0)].value


def code(v):
    return v.code if isinstance(v, ErrorValue) else v


# -- no function takes the calculation down ------------------------------------------------------
def test_a_function_short_of_an_argument_errs_in_its_cell_only(wb):
    """MINIFS without its criterion raised an IndexError that stopped every
    sheet calculating; a fault inside any function is its cell's #VALUE!."""
    for text in ("=MINIFS(Data!A1:A8,Data!A1:A8)", "=MAXIFS(Data!A1:A8,Data!A1:A8)",
                 "=AVERAGEIFS(Data!A1:A8,Data!A1:A8)", "=SUMIFS(Data!A1:A8,Data!A1:A8)"):
        assert code(value(wb, text)) == "#VALUE!", text
    assert value(wb, "=Data!A1+1") == 50.0, "the sheet goes on calculating"


def test_an_impossibly_big_array_is_num_not_all_the_memory(wb):
    """MUNIT(45366) — a date given as the size — took all the memory there
    was; it is #NUM!, as Excel's arrays past the sheet are."""
    for text in ("=MUNIT(45366)", "=SEQUENCE(45366,45366)", "=RANDARRAY(45366,45366)",
                 "=EXPAND(Data!A1:B2,45366,45366)", "=MAKEARRAY(45366,45366,LAMBDA(r,c,r))"):
        assert code(value(wb, text)) == "#NUM!", text
    assert code(value(wb, '=REPT("abc",20000)')) == "#VALUE!", "longer than a cell holds"
    assert code(value(wb, "=FACT(171)")) == "#NUM!" and value(wb, "=FACT(170)") > 7e306
    assert code(value(wb, "=FACTDOUBLE(301)")) == "#NUM!"


# -- the arguments every function is given ------------------------------------------------------
def test_a_criterion_passes_over_an_error_in_the_range(wb):
    """COUNTIF over a range holding #N/A crashed (a TypeError on the error
    value); the error simply doesn't match, as in Excel."""
    assert value(wb, "=COUNTIF(Data!A1:A8,49)") == 1.0
    assert value(wb, "=COUNTIF(Data!A1:A8,Data!A1)") == 1.0
    assert value(wb, '=COUNTIF(Data!A1:A8,">1")') == 2.0
    assert value(wb, "=SUMIF(Data!A1:A8,Data!A1)") == 49.0
    assert value(wb, "=SUMIF(Data!A1:A8,49,Data!A1:A8)") == 49.0
    assert value(wb, "=AVERAGEIF(Data!A1:A8,50)") == 50.0
    assert value(wb, "=COUNTIFS(Data!A1:A8,49,Data!B1:B8,1)") == 1.0
    assert code(value(wb, "=COUNTIF(Data!A1:A8,NA())")) == 1.0 or \
        value(wb, "=COUNTIF(Data!A1:A8,NA())") == 1.0, "an error criterion matches an equal error"


def test_sumifs_wants_the_summed_range_the_size_of_the_criteria(wb):
    assert code(value(wb, "=SUMIFS(Data!A1:A8,Data!A1,49)")) == "#VALUE!"
    assert code(value(wb, "=AVERAGEIFS(Data!B1:B8,Data!A1:A4,49)")) == "#VALUE!"
    assert value(wb, "=SUMIFS(Data!B1:B8,Data!A1:A8,49)") == 1.0


@pytest.mark.parametrize("text, wanted", [
    ("=ROUND(49,50)", 49.0), ("=ROUNDUP(2.5,100)", 2.5), ("=ROUNDDOWN(2.5,40)", 2.5),
    ("=TRUNC(2.5,30)", 2.5), ("=ROUND(49,-50)", 0.0), ("=ROUND(2.675,2)", 2.68),
    ("=ROUND(1234.5,-2)", 1200.0),
])
def test_round_with_more_digits_than_a_number_has(wb, text, wanted):
    """ROUND(49, 50) ran out of decimal precision and gave an error; Excel
    gives the number as it is."""
    assert value(wb, text) == pytest.approx(wanted)


def test_concatenate_joins_one_value_an_argument_and_concat_whole_ranges(wb):
    """Excel's CONCATENATE(A1:A3) is the cells one by one (spilling in Excel
    365); CONCAT(A1:A3) joins them all. CalcForge joined for both."""
    test = wb.sheet("Test")
    assert value(wb, "=CONCATENATE(Data!A1:A3)") == "49"
    assert [test.cells[(r, 0)].value for r in range(3)] == ["49", "N/A", "50"], "spilt"
    assert value(wb, "=CONCAT(Data!A1:A3)") == "49N/A50"
    assert value(wb, '=CONCATENATE(Data!A1,"-",Data!A3)') == "49-50"
    assert value(wb, "=CONCATENATE(TRUE)") == "TRUE"


@pytest.mark.parametrize("text, wanted", [
    ("=PRODUCT(Data!A2)", 0.0),               # only text: nothing to multiply
    ("=PRODUCT(Data!A4)", 0.0),
    ("=PRODUCT(Data!A1,Data!A3)", 2450.0),
    ('=PRODUCT("5",2)', 10.0),                # text typed in counts, as in Excel
    ("=LCM(Data!A4)", 0.0),                   # an empty cell is 0, and LCM(…, 0) is 0
    ("=LCM(49,Data!A4)", 0.0),
    ("=LCM(4,6)", 12.0),
    ("=GCD(49,Data!A4)", 49.0),
    ('=TEXT(49,"")', ""),                     # an empty format gives ""
    ('=TEXT(49,"0.0")', "49.0"),
    ("=BETA.INV(1,2,3)", 1.0),                # probability 1 is the upper bound
    ("=BETA.INV(1,2,3,10,20)", 20.0),
])
def test_products_lcm_text_and_beta_inv_as_excel(wb, text, wanted):
    assert value(wb, text) == wanted


def test_beta_inv_refuses_what_excel_refuses(wb):
    assert code(value(wb, "=BETA.INV(0,2,3)")) == "#NUM!"
    assert code(value(wb, "=BETA.INV(1.5,2,3)")) == "#NUM!"


def test_workday_intl_and_networkdays_intl_honour_their_weekend(wb):
    """Friday 15 March 2024 is 45366. The weekend argument was taken for
    the holidays, so every weekend was Saturday and Sunday."""
    friday = 45366
    assert value(wb, f"=WORKDAY.INTL({friday},2)") == friday + 4          # Tue
    assert value(wb, f"=WORKDAY.INTL({friday},2,1)") == friday + 4
    assert value(wb, f"=WORKDAY.INTL({friday},2,3)") == friday + 2        # Mon/Tue off: Sun
    assert value(wb, f"=WORKDAY.INTL({friday},2,7)") == friday + 3        # Fri/Sat off: Mon
    assert value(wb, f"=WORKDAY.INTL({friday},2,11)") == friday + 3       # Sunday only: Mon
    assert value(wb, f"=WORKDAY.INTL({friday},2,17)") == friday + 3       # Saturday only: Mon
    assert value(wb, f'=WORKDAY.INTL({friday},2,"1100000")') == friday + 2
    assert value(wb, f'=WORKDAY.INTL({friday},2,"0000011")') == friday + 4
    assert value(wb, f"=WORKDAY.INTL({friday},2,1,{friday + 4})") == friday + 5, "a holiday"
    assert value(wb, f"=WORKDAY({friday},2,{friday + 4})") == friday + 5
    assert value(wb, f"=NETWORKDAYS.INTL({friday},{friday + 7})") == 6.0
    assert value(wb, f"=NETWORKDAYS.INTL({friday},{friday + 7},3)") == 6.0
    assert value(wb, f"=NETWORKDAYS.INTL({friday},{friday + 7},11)") == 7.0
    assert value(wb, f'=NETWORKDAYS.INTL({friday},{friday + 7},"0000001")') == 7.0
    assert value(wb, f"=NETWORKDAYS({friday},{friday + 7},{friday + 3})") == 5.0
    for bad in (f"=WORKDAY.INTL({friday},2,8)", f"=NETWORKDAYS.INTL({friday},{friday + 7},18)"):
        assert code(value(wb, bad)) == "#NUM!", bad
    assert code(value(wb, f'=WORKDAY.INTL({friday},2,"1111111")')) == "#VALUE!"
    for negative in ("=WORKDAY(-3,2)", "=NETWORKDAYS(-3,2)", "=WORKDAY.INTL(-3,2)"):
        assert code(value(wb, negative)) == "#NUM!", negative


@pytest.mark.parametrize("text, wanted", [
    ("=WEEKNUM(45366)", 11.0), ("=WEEKNUM(45366,2)", 11.0), ("=WEEKNUM(45366,11)", 11.0),
    ("=WEEKNUM(45366,21)", 11.0), ("=WEEKNUM(45368,1)", 12.0),     # Sunday 17 March: a new week
    ("=WEEKNUM(45368,2)", 11.0),                                    # weeks from Monday
    ("=WEEKNUM(45368,12)", 12.0), ("=WEEKNUM(45369,12)", 12.0),    # weeks from Tuesday (12 March)
    ("=WEEKNUM(45370,12)", 13.0),                                   # Tuesday 19 March
])
def test_weeknum_return_types(wb, text, wanted):
    assert value(wb, text) == wanted


def test_weeknum_refuses_an_unknown_return_type(wb):
    assert code(value(wb, "=WEEKNUM(45366,50)")) == "#NUM!"


def test_sumx_functions_pass_an_error_on_and_want_pairs(wb):
    assert code(value(wb, "=SUMX2MY2(Data!A1:A8,Data!B1:B8)")) == "#N/A"
    assert code(value(wb, "=SUMXMY2(Data!A1,Data!A2)")) == "#N/A", "no numeric pairs"
    assert value(wb, "=SUMXMY2(Data!A1,Data!A3)") == 1.0


def test_base_conversions_as_excel(wb):
    assert code(value(wb, "=DEC2BIN(49,50)")) == "#NUM!", "1 to 10 places"
    assert code(value(wb, "=BIN2HEX(1,11)")) == "#NUM!"
    assert value(wb, "=DEC2BIN(49,8)") == "00110001"
    assert code(value(wb, "=HEX2DEC(-3)")) == "#NUM!", "a negative number isn't a numeral"
    assert value(wb, "=HEX2DEC(Data!A4)") == 0.0, "an empty cell is 0"
    assert value(wb, '=BIN2DEC("")') == 0.0


def test_convert_of_a_unit_excel_hasnt_is_na(wb):
    assert code(value(wb, '=CONVERT(1,"m","furlongs")')) == "#N/A"
    assert code(value(wb, '=CONVERT(1,"m","kg")')) == "#N/A"
    assert value(wb, '=CONVERT(1,"m","cm")') == pytest.approx(100.0)


# -- the whole battery still agrees name for cell -----------------------------------------------
def test_every_function_reads_a_name_as_the_cells_it_names(wb):
    """f(A1, A2) and f(name of A1, name of A2) agree for every function
    (CALC, LET and LAMBDA take names as syntax, not cells)."""
    for name, ref in (("nm_1", "$A$1"), ("nm_2", "$A$2"), ("nm_r", "$A$1:$A$4")):
        wb.define_name(name, "Data!" + ref)
    test = wb.sheet("Test")
    disagree = []
    for fn, spec in sorted(FUNCTIONS.items()):
        if fn in {"RAND", "RANDBETWEEN", "RANDARRAY", "NOW", "TODAY", "CALC", "LET", "LAMBDA",
                  "INFO", "CELL"}:
            continue
        for refs, names in ((["Data!A1"], ["nm_1"]), (["Data!A1:A4"], ["nm_r"]),
                            (["Data!A1", "Data!A2"], ["nm_1", "nm_2"]),
                            (["Data!A1:A4", "Data!A2"], ["nm_r", "nm_2"])):
            count = len(refs)
            if count < spec.least or (spec.most is not None and count > spec.most):
                continue
            got = []
            for args in (refs, names):
                parsed = F.parse(f"{fn}(" + ",".join(args) + ")", 0, 0)
                v, _reads = evaluate_cell(wb, test, 0, 0, parsed.tree, parsed)
                got.append(_plain(v))
            if got[0] != got[1]:
                disagree.append((fn, refs, got))
    assert not disagree, disagree


def _plain(v):
    if isinstance(v, ErrorValue):
        return ("err", v.code)
    if isinstance(v, Array):
        return tuple(tuple(_plain(x) for x in row) for row in v.rows)
    if isinstance(v, float):
        return round(v, 9)
    return v
