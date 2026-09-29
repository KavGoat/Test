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
        ws.update_after_edit(r)  # the region is left, as a user moves on
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
    ("1'in*1'in=", "0.0006 m^2"), ("2'kN/'m=", "2000 N/m"), ("100'kPa*2'm^2=", "2·10^5 N"),
    ("25'kN/'m^3=", "25000 N/m^3"), ("100'W/'m^2=", "100 W/m^2"), ("3'J/'K=", "3 J/K"),
    ("9.81'm/'s^2=", "9.81 m/s^2"),
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


# -- typing over a selection (observed on SMath Cloud with "1+2*3") -------------------------

@pytest.mark.parametrize("spaces,op,expected", [
    (1, "(", "1+(2*3)"), (2, "(", "(1+2*3)"), (3, "(", "1+(2*3)"),
    (1, ")", "1+2*3"), (2, ")", "1+2*3"),
    (1, "/", "1+(2*3)/()"), (2, "/", "(1+2*3)/()"),
    (1, "^", "1+(2*3)^()"), (2, "^", "(1+2*3)^()"),
    (1, "\\", "1+√(2*3)"), (2, "\\", "√(1+2*3)"),
    (1, "-", "1+2*3-"), (2, "-", "1+2*3-"),
    (1, "*", "1+2*3*"), (2, "*", "(1+2*3)*"),
    (1, "+", "1+2*3+"), (2, "+", "1+2*3+"),
    (1, "s", "1+2*3"),
])
def test_typing_over_selection(spaces, op, expected):
    ws, (r,) = sheet(list("1+2*3") + [" "] * spaces + [op])
    assert r.editor.root.text() == expected


def test_bar_is_logical_or():
    ws, (r,) = sheet("1|0=")
    assert r.editor.root.text() == "1∨0=" and result(r) == "1"


# -- the cursor, as observed with the arrow keys on SMath Cloud -------------------------------

def _cursor(ed):
    """(pos, underline start, underline end, sub-expression state?) in the root row."""
    r, a, b = ed.underline()
    return ed.pos, a, b, ed.node is not None


def test_arrows_through_names_and_operators():
    # "ab+cd*ef": items a b + c d * e f  (positions 0..8)
    ws, (r,) = sheet("ab+cd*ef")
    ed = r.editor
    seen = [_cursor(ed)]
    for _ in range(9):
        ed.key("LEFT")
        seen.append(_cursor(ed))
    assert seen == [
        (8, 6, 8, False),  # end of ef, ef underlined
        (7, 6, 8, False),  # between e and f
        (6, 6, 8, False),  # start of ef
        (5, 3, 5, False),  # jumped over * to the end of cd
        (4, 3, 5, False),
        (3, 3, 5, False),  # start of cd
        (3, 3, 8, True),   # the whole cd·ef underlined
        (2, 0, 2, False),  # end of ab
        (1, 0, 2, False),
        (0, 0, 2, False),
    ]
    ed.key("LEFT")
    assert _cursor(ed) == (0, 0, 8, True)  # whole expression
    ed.key("LEFT")
    assert _cursor(ed) == (0, 0, 8, True)  # stays
    ws, (r,) = sheet("ab+cd*ef")
    ed = r.editor
    ed.set_cursor(ed.root, 2)
    ed.key("RIGHT")
    assert _cursor(ed) == (3, 3, 8, True)  # across + onto cd·ef as a whole
    ed.key("RIGHT")
    assert _cursor(ed) == (3, 3, 5, False)
    ed.key("RIGHT")
    assert _cursor(ed) == (4, 3, 5, False)


@pytest.mark.parametrize("key,expected", [
    ("/", "ab+()/(cd*ef)"),   # ■/(cd·ef), cursor in the numerator
    ("x", "ab+cd*ef"),        # ignored
    ("+", "ab++cd*ef"),
])
def test_typing_at_whole_subexpression(key, expected):
    ws, (r,) = sheet(list("ab+cd*ef") + ["LEFT"] * 6)
    assert r.editor.node is not None
    r.editor.key(key)
    assert r.editor.root.text() == expected


def test_power_and_function_navigation():
    ws, (r,) = sheet("a^23")
    ed = r.editor
    for _ in range(3):
        ed.key("LEFT")
    assert ed.row is ed.root and ed.pos == 1  # left from the exponent: end of the base
    ws, (r,) = sheet("sin(ab")
    ed = r.editor
    for _ in range(3):
        ed.key("LEFT")
    assert ed.row is ed.root and ed.pos == 3  # end of the function name


# -- calls that become structures once complete (as SMath draws them) -------------------------

def test_while_becomes_block_when_complete():
    ws, (a, b, c) = sheet("n:1", list("while(n<100,") + list("n:n*2"), "n=")
    prog = b.editor.root.items[0]
    assert prog.name == "while" and len(prog.rows) == 2
    assert result(c) == "128"


def test_sum_and_range_structures():
    ws, (a, b) = sheet(list("sum(i^2") + ["RIGHT"] + list(",i,1,4="), list("sum(range(1,4") + ["RIGHT", "RIGHT", "="])
    assert a.editor.root.items[0].name == "sum" and result(a) == "30"
    assert result(b) == "10"


@pytest.mark.parametrize("name,fill,shown", [
    ("sum", ["k", "k", "1", "10"], "55"),
    ("product", ["k", "k", "1", "5"], "120"),
    ("int", ["x", "x", "0", "2"], "2"),
    ("range", ["1", "3"], "[1; 2; 3]"),
    ("for", ["i", "range(1,3", "s:s+i"], None),
])
def test_toolbox_structures(name, fill, shown):
    ws = Worksheet()
    s0 = ws.add_region(18, 0)
    s0.editor.type("s:0")
    ws.update_after_edit(s0)
    r = ws.add_region(18, 40)
    r.editor.insert_structure(name)
    box = r.editor.root.items[0]
    for row, text in zip(box.rows, fill):
        r.editor.set_cursor(row, 0)
        r.editor.type(text)
    r.editor.set_cursor(r.editor.root, len(r.editor.root))
    if shown is not None:
        r.editor.key("=")
    ws.update_after_edit(r)
    if shown is not None:
        assert result(r) == shown
    else:
        t = ws.add_region(18, 80)
        t.editor.type("s=")
        ws.calculate()
        assert result(t) == "6"


def test_cross_product_and_approx():
    ws, (a, b, c) = sheet(["u", ":", "m", "a", "t", "(", "1", "RIGHT", "0", "RIGHT", "0", "RIGHT", "0"],
                          ["w", ":", "u"], "1≈1.00000000001=")
    assert result(c) == "1"


# -- subscripts, typed with "." (observed on SMath Cloud) -----------------------------

def _ed(keys):
    from websmath.editor import MathEditor

    e = MathEditor()
    for k in keys if isinstance(keys, list) else list(keys):
        e.key(k)
    return e


@pytest.mark.parametrize("typed,text", [
    ("x.1", "x.1"),          # x with subscript 1
    ("x.+1", "x+1"),         # an empty subscript is dropped by the operator
    ("2.5.3", "2.53"),       # a second decimal point is ignored
    ("x.1.2", "x.1.2"),      # inside a subscript a further dot is literal
    ("x.1^2", "x.1^(2)"),    # the power goes after the subscript
    ("f.a(x", "f.a(x)"),     # function names take subscripts too
])
def test_subscript_typing(typed, text):
    assert _ed(typed).root.text() == text


def test_subscript_backspace_and_underline():
    e = _ed("x.1")
    assert e.underline()[1:] == (2, 3) and e.in_subscript()  # only the subscript
    e.key("BACK")
    assert e.root.text() == "x." and e.underline()[1:] == (2, 2)  # empty subscript stays
    e.key("BACK")
    assert e.root.text() == "x" and e.underline()[1:] == (0, 1)


def test_subscript_left_walks_parts():
    # ab.cd: Left moves inside cd, to the start of the subscript, then to the
    # end of ab (underline switches from cd to ab), then inside ab
    e = _ed("ab.cd")
    seen = []
    for _ in range(4):
        e.key("LEFT")
        seen.append((e.pos, e.underline()[1:]))
    assert seen == [(4, (3, 5)), (3, (3, 5)), (2, (0, 2)), (1, (0, 2))]


@pytest.mark.parametrize("typed,kind", [
    ("q ", "text"), ("2 ", "text"), ("sin ", "text"), ("x.1 ", "text"), ("2.5 ", "text"),
    ("q+1 ", "math"), ("w: ", "math"), ("q=5 ", "math"),
])
def test_space_turns_lone_word_into_text(typed, kind):
    # only a lone name / number (before any operator or "=") becomes text;
    # elsewhere space never inserts a space, it widens the selection
    e = _ed(typed)
    assert e.kind == kind
    if kind == "math":
        assert " " not in e.root.text()


@pytest.mark.parametrize("typed,text", [
    ("2x", "2*x"), ("3.5a", "3.5*a"), ("2(", "2*()"), ("2e3", "2*e3"), ("x2", "x2"), ("2'm", "2'm"),
])
def test_number_then_letter_multiplies(typed, text):
    assert _ed(typed).root.text() == text


# -- functions: results and messages read off SMath Cloud ------------------------------

@pytest.mark.parametrize("expr,shown,message", [
    ("sqrt(-1)=", "i", None),
    ("ln(0)=", None, "Logarithm of zero is not defined."),
    ("1/0=", None, "Division by zero."),
    ("asin(2)=", "1.5708-1.317·i", None),
    ("acos(2)=", "1.317·i", None),
    ("mod(-7,3)=", "-1", None),
    ("mod(7,-3)=", "1", None),
    ("mod(5.5,2)=", "1.5", None),
    ("round(1.2345,2)=", "1.23", None),
    ("round(12345.6789,-2)=", None, "Coefficient of rounding should be in the range from 0 to 15 inclusive."),
    ("3.5!=", None, "Factorial is defined for real numbers and zero."),
    ("20!=", "2.4329·10^18", None),
    ("170!=", "7.2574·10^306", None),
    ("171!=", None, "Result is above max. allowed positive number."),
    ("sin(1'm)=", None, "Operation cannot be performed with units."),
    ("sin(30'deg)=", "0.5", None),
    ("cos(π/2)=", "0", None),
    ("sin(π)=", "0", None),
    ("tan(π/2)=", "1.6331·10^16", None),
    ("cot(0)=", None, "Result is above max. allowed positive number."),
    ("exp(1000)=", None, "Result is above max. allowed positive number."),
    ("10^400=", None, "Result is above max. allowed positive number."),
    ("0^0=", None, "Uncertainty."),
    ("ln(-1)=", "3.1416·i", None),
    ("floor(-2.5)=", "-3", None),
    ("ceil(-2.5)=", "-2", None),
    ("trunc(-2.5)=", "-2", None),
    ("sign(0)=", "0", None),
    ("nthroot(-8,3)=", "-2", None),
    ("sin(1+2i)=", "3.1658+1.9596·i", None),
    ("Re(3+4i)=", "3", None),
    ("perc(5,200)=", "10", None),
    ("log(8,2)=", "3", None),
])
def test_functions_match_smath(expr, shown, message):
    _, (r,) = sheet(expr)
    assert (result(r), error(r)) == (shown, message)


# -- constants: SMath's unit-library constants, shown as the site shows them ----------------

@pytest.mark.parametrize("expr,shown", [
    ("'g.e=", "9.8066 m/s^2"),
    ("'c=", "2.9979·10^8 m/s"),
    ("'h=", "6.6261·10^-34 s J"),
    ("'k=", "1.3807·10^-23 J/K"),
    ("'N.A=", "6.0221·10^23 1/mol"),
    ("'R.m=", "8.3145 J/K mol"),
    ("'ε.0=", "8.8542·10^-12 F/m"),
    ("'μ.0=", "1.2566·10^-6 m T/A"),
    ("'m.e=", "9.1094·10^-31 kg"),
    ("'m.p=", "1.6726·10^-27 kg"),
    ("'m.n=", "1.6749·10^-27 kg"),
    ("'u=", "1.6605·10^-27 kg"),
    ("'e=", "1.6022·10^-19 C"),
    ("'hildebrand=", "2045.48 kg^0.5/s m^0.5"),
    ("π=", "3.1416"), ("e=", "2.7183"), ("i=", "i"), ("∞=", "∞"),
])
def test_constants_match_smath(expr, shown):
    _, (r,) = sheet(expr)
    assert result(r) == shown


def test_constants_table_lists_every_constant():
    from websmath.engine.constants import constants

    typed = [c.typed for c in constants()]
    assert typed[:4] == ["π", "e", "i", "∞"]
    assert set(typed[4:]) == {"'c", "'e", "'g.e", "'G.N", "'h", "'hildebrand", "'k", "'m.e", "'m.n",
                              "'m.p", "'N.A", "'R.m", "'u", "'ε.0", "'μ.0"}


def test_variable_named_like_a_unit_wins():
    # observed: after m:10, m= shows 10 and 'm stays the metre
    _, (_, a, b) = sheet("m:10", "m=", "m*2'm=")
    assert (result(a), result(b)) == ("10", "20 m")


# -- symbolic differentiation and the functions completed from the catalogue --------------

def _ev(text, *defs):
    from websmath.engine.display import value_to_text
    from websmath.engine.evaluator import Context, Evaluator
    from websmath.engine.linear import parse_text
    from websmath.engine.parser import parse_row

    ev, ctx = Evaluator(), Context()
    for d in defs:
        ev.define(parse_row(parse_text(d)), ctx)
    ev.start_clock()
    return value_to_text(ev.eval(parse_row(parse_text(text)), ctx))


@pytest.mark.parametrize("expr,shown", [
    ("diff(x^3,x)", "3*x^(2)"),
    ("diff(x^3,x,2)", "6*x"),
    ("diff(a*x^2+b*x+c,x)", "2*a*x+b"),
    ("diff(sin(x),x)", "cos(x)"),
    ("diff(ln(x^2+1),x)", "2*(x)/(x^(2)+1)"),  # 2·x over x²+1
    ("diff(e^x,x)", "e^(x)"),
    ("diff(2^x,x)", "2^(x)*ln(2)"),
])
def test_diff_is_symbolic_when_variable_is_free(expr, shown):
    assert _ev(expr) == shown


def test_diff_evaluates_when_variable_has_value():
    assert _ev("diff(x^3,x)", "x:=2") == "12"
    assert _ev("diff(f(x),x)", "f(x):=x^2+3*x", "x:=1") == "5"


@pytest.mark.parametrize("expr,defs,shown", [
    ("Jacob(stack(x^2,x*y),stack(x,y))", ("x:=1", "y:=2"), "[2 0; 2 1]"),
    ("roots(x^2-4,x)", ("x:=1",), "2"),
    ("roots(stack(x+y-3,x-y-1),stack(x,y))", ("x:=0", "y:=0"), "[2; 1]"),
    ("numden(3/4)", (), "[3; 4]"),
    ("numden(0.75)", (), "[3; 4]"),
    ("mixed(2,1,4)", (), "2.25"),
    ("findrows(stack(augment(1,2),augment(3,4),augment(1,5)),1,1)", (), "[1 2; 1 5]"),
    ('trace("a={0}",5)', (), '"a=5"'),
    ('num2str(3.14159,"0.00")', (), '"3.14"'),
    ('num2str(1234.5,"F1")', (), '"1234.5"'),
    ("solve(x^2-4,x)", (), "[-2; 2]"),
])
def test_more_functions(expr, defs, shown):
    assert _ev(expr, *defs) == shown


def test_range_index_assigns_every_element():
    # SMath example GravitationAcceleration.sm: result[k,2]:=f(data[k,2]) with k a range
    assert _ev("v", "v:=stack(1,2,3)", "k:=range(1,3)", "w[k]:=v[k]^2", "v:=w") == "[1; 4; 9]"
    assert _ev("m[k]", "m:=stack(5,6,7)", "k:=range(2,3)") == "[6; 7]"
