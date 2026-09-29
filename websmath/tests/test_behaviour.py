"""Behaviour observed on SMath Cloud, replayed keystroke by keystroke.

Every expectation here was read back from smath.com (see
docs/SMATH_BEHAVIOUR.md); the tests type into the editor exactly as a user
would, so they cover the editor, the parser, the evaluator and formatting.
"""
from __future__ import annotations

import pytest

from websmath.engine.display import display_text
from websmath.engine.model import Frac
from websmath.worksheet import Worksheet


def sheet(*lines):
    """Type each line into its own region, top to bottom, and calculate.

    Items may be a string (typed) or a list of keys (named keys allowed)."""
    ws = Worksheet()
    regions = []
    for k, line in enumerate(lines):
        r = ws.add_region(18, 9 + 36 * k)
        keys = line if isinstance(line, list) else list(line)
        for key in keys:
            r.editor.key(key)
        regions.append(r)
    ws.calculate()
    return ws, regions


def result(r):
    return display_text(r.display) if r.display is not None else None


def error(r):
    return r.error.message if r.error else None


# -- "=" means define or evaluate ---------------------------------------------------

def test_equals_on_undefined_name_defines():
    ws, (r,) = sheet("x=")
    assert r.editor.root.text() == "x≔"
    assert not r.editor.evaluate


def test_equals_on_defined_name_evaluates():
    ws, (a, b) = sheet("x=5", "x=")
    assert a.editor.root.text() == "x≔5"
    assert b.editor.evaluate and result(b) == "5"


def test_cursor_stays_left_after_equals():
    # typing 7 after "x=" appends to x (observed "x7 - not defined.")
    ws, (a, b) = sheet("x=5", "x=7")
    assert b.editor.root.text() == "x7="
    assert error(b) == "x7 - not defined."


def test_symbolic_definition_is_allowed():
    ws, (a, b) = sheet("a=b", "a=")
    assert a.editor.root.text() == "a≔b" and error(a) is None
    assert error(b) == "b - not defined."


def test_use_above_definition_is_an_error():
    ws = Worksheet()
    d = ws.add_region(18, 45)
    d.editor.type("x:5")
    u = ws.add_region(18, 9)  # placed above the definition
    u.editor.type("y+1=")
    ws.calculate()
    assert error(u) == "y - not defined."
    # moving the definition above makes it work
    v = ws.add_region(18, 90)
    v.editor.type("x=")
    ws.calculate()
    assert result(v) == "5"


def test_moving_region_above_definition_breaks_it():
    ws, (a, b) = sheet("x:5", "x=")
    assert result(b) == "5"
    b.y = 0
    ws.calculate()
    assert error(b) == "x - not defined."


def test_redefinition_with_colon():
    ws, (a, b, c) = sheet("x:5", "x:9", "x=")
    assert result(c) == "9"


def test_empty_placeholder_error():
    ws, (r,) = sheet("abc=")
    assert r.editor.root.text() == "abc≔"
    assert error(r) == "Fill in all empty elements."


def test_function_call_equals_on_unknown_overload_defines():
    ws, (a, b) = sheet("log(100=", "max(1,5,3=")
    assert a.editor.root.text().endswith("≔")
    assert error(a) == "Syntax is incorrect."
    assert error(b) == "Syntax is incorrect."


def test_undefined_function_message():
    ws, (a, b) = sheet(["y", ":", "f", "(", "3"], "y=")
    assert error(b) == "f(#) - function is not defined."


# -- text regions ----------------------------------------------------------------------

def test_space_after_name_makes_text_region():
    ws, (r,) = sheet("abc def")
    assert r.kind == "text" and r.editor.text == "abc def"


def test_backspace_does_not_revert_text_but_undo_does():
    ws, (r,) = sheet("abc ")
    assert r.kind == "text"
    r.editor.key("BACK")
    assert r.kind == "text" and r.editor.text == "abc"
    r.editor.undo()  # undo the backspace
    r.editor.undo()  # undo the conversion
    assert r.kind == "math" and r.editor.root.text() == "abc"


def test_space_in_expression_does_not_make_text():
    ws, (r,) = sheet("1+2 ")
    assert r.kind == "math"


def test_quote_starts_text_region():
    ws, (r,) = sheet('"hello')
    assert r.kind == "text" and r.editor.text == "hello"


# -- structure of typed expressions -----------------------------------------------------

def test_slash_takes_operand_on_left_only():
    ws, (r,) = sheet("2*3/4=")
    assert result(r) == "1.5"
    items = r.editor.root.items
    assert items[:2] == ["2", "*"] and isinstance(items[2], Frac)


def test_denominator_keeps_typing():
    ws, (r,) = sheet("1/7*1000=")
    assert result(r) == "0.0001"
    assert r.editor.root.items[0].rows[1].text() == "7*1000"


def test_exponent_keeps_typing_until_right_arrow():
    ws, (a, b) = sheet(["a", ":", "2"], ["a", "^", "2", "+", "1", "="])
    assert result(b) == "8"  # a^(2+1)
    ws, (a, b) = sheet(["a", ":", "2"], ["a", "^", "2", "RIGHT", "+", "1", "="])
    assert result(b) == "5"


def test_close_bracket_is_ignored_right_arrow_leaves():
    ws, (a, b) = sheet("(1+2)*3=", ["(", "1", "+", "2", "RIGHT", "*", "3", "="])
    assert result(a) == "7"
    assert result(b) == "9"


def test_literal_subscript():
    ws, (a, b) = sheet("L.A:3", "L.A=")
    assert result(b) == "3"


def test_structures_from_words():
    ws, regions = sheet("sqrt(16=", list("nthroot(3,27="), "abs(-3=", "log(8,2=")
    assert [result(r) for r in regions] == ["4", "1.0415", "3", "3"]


# -- number formatting ---------------------------------------------------------------------

@pytest.mark.parametrize("typed,shown", [
    ("1/3=", "0.3333"), ("2/3=", "0.6667"), ("10/4=", "2.5"), ("123456=", "1.2346·10^5"),
    ("99999=", "99999"), ("1234567.8=", "1.2346·10^6"), ("0.001234=", "0.0012"),
    ("0.00001234=", "1.234·10^-5"), ("1.50=", "1.5"), ("10^5=", "1·10^5"), ("10^4=", "10000"),
    ("0.1+0.2=", "0.3"), ("100000.5=", "1·10^5"), ("12345.6789=", "12345.6789"),
    ("-2.25=", "-2.25"), ("22/7=", "3.1429"),
])
def test_number_formatting(typed, shown):
    ws, (r,) = sheet(typed)
    assert result(r) == shown


def test_decimal_places_and_significant_figures():
    ws, (r,) = sheet("1/3=")
    ws.format.decimals = 2
    ws.calculate()
    assert result(r) == "0.33"
    ws.format.significant = True
    ws.format.decimals = 3
    ws, (r2,) = sheet("200/3=")
    ws.format.significant, ws.format.decimals = True, 3
    ws.calculate()
    assert result(r2) == "66.7"


# -- units ------------------------------------------------------------------------------------

@pytest.mark.parametrize("typed,shown", [
    ("3'kN=", "3000 N"), ("2'kN*3'm=", "6000 J"), ("5'MPa=", "5·10^6 Pa"),
    ("9.81'kg*'m/'s^2=", "9.81 N"), ("60'deg=", "1.0472"), ("3/'s=", "3 Hz"),
    ("5'm/'s=", "5 m/s"), ("2'kg/'m=", "2 kg/m"), ("20'°C=", "293.15 K"), ("1'ft=", "0.3048 m"),
    ("1'in*1'in=", "0.0006 m^2"), ("2'kN/'m=", "2000 m Pa"), ("100'kPa*2'm^2=", "2·10^5 N"),
])
def test_unit_results(typed, shown):
    ws, (r,) = sheet(typed)
    assert result(r) == shown


def test_cubic_metres_stay_base_units():
    ws, (r,) = sheet(["2", "'", "m", "^", "3", "="])
    assert result(r) == "2 m^3"


def test_plain_m_is_a_variable_not_a_unit():
    ws, (a, b) = sheet("L:2*m", "L=")
    assert error(b) == "m - not defined."


def test_unit_mismatch():
    ws, (a, b) = sheet("L:2'm", "L+3's=")
    assert error(b) == "Units don't match."


def test_units_in_exponent():
    ws, (r,) = sheet("4'm^2/'s^2=")
    assert error(r) == "Operation cannot be performed with units."


def test_unit_placeholder_converts_result():
    ws, (a, b) = sheet("L:2'm", ["L", "=", "RIGHT", "'", "m", "m"])
    assert result(b) == "2000"
    ws, (a, b) = sheet("L:2'm", ["L", "=", "RIGHT", "c", "m"])
    assert error(b) == "cm - not defined."


# -- functions ---------------------------------------------------------------------------------

@pytest.mark.parametrize("typed,shown", [
    ("cos(π=", "-1"), ("asin(0.5=", "0.5236"), ("atan(1=", "0.7854"), ("ln(e=", "1"),
    ("exp(1=", "2.7183"), ("5!=", "120"), ("mod(7,3=", "1"), ("floor(2.7=", "2"),
    ("ceil(2.1=", "3"), ("round(2.567,2=", "2.57"), ("log10(1000=", "3"), ("π=", "3.1416"),
    ("e=", "2.7183"), ("sin(1=", "0.8415"),
])
def test_builtin_functions(typed, shown):
    ws, (r,) = sheet(typed)
    assert result(r) == shown


def test_trig_with_degrees():
    ws, (r,) = sheet(["s", "i", "n", "(", "3", "0", "'", "d", "e", "g", "="])
    assert result(r) == "0.5"


def test_custom_function():
    ws, regions = sheet(["f", "(", "t", "RIGHT", ":", "t", "^", "2", "RIGHT", "+", "1"], "f(3=",
                        ["g", "(", "a", ",", "b", "RIGHT", ":", "a", "*", "b"], "g(2,5=")
    assert result(regions[1]) == "10" and result(regions[3]) == "10"


def test_if_block():
    ws, (a, b) = sheet(["i", "f", "(", "1", ">", "0", ",", "2", "DOWN"], [])
    a.editor.set_cursor(a.editor.root, len(a.editor.root))
    prog = a.editor.root.items[0]
    assert prog.name == "if" and len(prog.rows) == 3
    prog.rows[2].append("3")
    a.editor.key("=")
    ws.calculate()
    assert result(a) == "2"


def test_matrix_and_determinant():
    keys = ["M", ":", "m", "a", "t", "(", "1", "RIGHT", "2", "RIGHT", "3", "RIGHT", "4"]
    ws, (a, b, c) = sheet(keys, "det(M=", "M=")
    assert result(b) == "-2"
    assert result(c) == "[1 2; 3 4]"


def test_for_and_while_loops():
    ws, regions = sheet(
        ["s", ":", "0"],
        ["f", "o", "r", "(", "i", ",", "r", "a", "n", "g", "e", "(", "1", ",", "4", "RIGHT", ",",
         "s", ":", "s", "+", "i"],
        "s=",
        ["n", ":", "1"],
        ["w", "h", "i", "l", "e", "(", "n", "<", "1", "0", "0", ",", "n", ":", "n", "*", "2"],
        "n=",
    )
    assert result(regions[2]) == "10"
    assert result(regions[5]) == "128"


def test_sum_and_max_min():
    ws, regions = sheet("v:mat(", ["s", "u", "m", "(", "i", "^", "2", "RIGHT", ",", "i", ",", "1", ",", "4", "="],
                        "max(v=")
    v = regions[0].editor.root.items[-1]
    for cell, val in zip(v.rows, "1423"):
        cell.append(val)
    ws.calculate()
    assert result(regions[1]) == "30"
    assert result(regions[2]) == "4"


# -- evaluation timing ------------------------------------------------------------------------

def test_only_edited_region_recalculates_until_left():
    ws, (a, b) = sheet("q:5", "q=")
    assert result(b) == "5"
    a.editor.set_cursor(a.editor.root, 1)
    a.editor.key("7")  # q7:=5 while still editing
    ws.calculate_region(a)
    assert result(b) == "5"  # unchanged until the region is left
    ws.calculate()
    assert error(b) == "q - not defined."
