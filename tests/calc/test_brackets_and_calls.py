""")" closes the bracket, and a call with numbers in it is evaluated.

The user, 2026-10-15: "Close the bracket" — SMath Cloud ignores ")", so
(1+2)*3= typed straight through was (1+2·3)=7, a silently wrong answer.  And
max(1,2)= turned into a definition with "Syntax is incorrect." because SMath
Cloud's catalogue knows max with one argument only.

The window tests type with real keys in Calc mode; the editor tests drive
the headless editor the same way, a key at a time.
"""
from __future__ import annotations

import pytest

from calcforge.calc.engine.display import display_text
from calcforge.calc.engine.model import Paren
from calcforge.calc.editor import MathEditor
from calcforge.calc.worksheet import Worksheet
from calcforge.ui import calcdialogs
from tests.test_calc_panels import an_equation


@pytest.fixture
def win(window):
    window.show()
    window.activateWindow()
    window.view.setFocus()
    yield window
    calcdialogs.ANSWERS.clear()


def shown(item):
    return display_text(item.region.display) if item.region.display is not None else None


def error(item):
    return item.region.error.message if item.region.error is not None else None


# -- with real keys in Calc mode ------------------------------------------------------

@pytest.mark.parametrize("typed, source, value", [
    ("(1+2)*3=", "(1+2)*3=", "9"),
    ("2*(3+4)-1=", "2*(3+4)-1=", "13"),
    ("sin(0)+1=", "sin(0)+1=", "1"),
    ("((1+2)*3)^2=", "((1+2)*3)^(2)=", "81"),
    ("max(1,2)=", "max(1,2)=", "2"),
    ("min(3,4)=", "min(3,4)=", "3"),
    ("max(1,2,3)=", "max(1,2,3)=", "3"),
    ("sum(1,2)=", "sum(1,2)=", "3"),
    ("atan2(1,1)=", "atan2(1,1)=", "0.7854"),
    ("lg(100)=", "lg(100)=", "2"),
    ("log(100;10)=", "log(100;10)=", "2"),
    ("log(100,10)=", "log(100,10)=", "2"),
    ("mod(7,3)=", "mod(7,3)=", "1"),
    ("max(3)=", "max(3)=", "3"),
    ("max(1,2)+1=", "max(1,2)+1=", "3"),
])
def test_typed_in_calc_mode(win, typed, source, value):
    item = an_equation(win, typed)
    assert item.region.editor.root.text() == source
    assert error(item) is None
    assert shown(item) == value


def test_a_user_function_is_defined_and_called(win):
    f = an_equation(win, "f(x):x+1", y=120)
    call = an_equation(win, "f(2)=", y=200)
    assert f.region.editor.root.text() == "f(x)≔x+1" and error(f) is None
    assert call.region.editor.root.text() == "f(2)=" and shown(call) == "3"


def test_a_user_function_squares(win):
    an_equation(win, "f(x):x^2", y=120)
    call = an_equation(win, "f(3)=", y=200)
    assert shown(call) == "9"


# -- the editor on its own --------------------------------------------------------------

def typed(text):
    ed = MathEditor()
    ed.type(text)
    return ed


def test_close_leaves_a_bracket_and_typing_carries_on_after_it():
    ed = typed("(1+2)")
    assert ed.row is ed.root and ed.pos == 1 and isinstance(ed.root.items[0], Paren)
    ed.type("*3")
    assert ed.root.text() == "(1+2)*3"


def test_close_leaves_a_calls_argument_list():
    ed = typed("sin(1)+1")
    assert ed.root.text() == "sin(1)+1" and ed.row is ed.root


def test_close_leaves_the_innermost_bracket_only():
    ed = typed("((1+2)")
    outer = ed.root.items[0]
    assert ed.row is outer.rows[0], "still inside the outer bracket"
    ed.type("*3)^2")
    assert ed.root.text() == "((1+2)*3)^(2)"


def test_close_leaves_an_exponent_inside_the_bracket_too():
    ed = typed("(2^3)+1")
    assert ed.root.text() == "(2^(3))+1"


def test_close_leaves_blocks_typed_as_calls():
    assert typed("sqrt(16)+1").root.text() == "√(16)+1"
    assert typed("if(1>0,1,2)+1").row.parent is None


def test_close_with_no_bracket_is_ignored():
    ed = typed("1)+2")
    assert ed.root.text() == "1+2"
    ed = typed("2^3)")
    assert ed.root.text() == "2^(3)" and ed.row is not ed.root, "an exponent is not a bracket"


def test_open_bracket_still_inserts_the_pair():
    ed = typed("(")
    assert isinstance(ed.root.items[0], Paren) and ed.row is ed.root.items[0].rows[0]


def test_close_bracket_is_undone_with_the_rest():
    ed = typed("(1)")
    ed.undo()
    assert ed.row is ed.root.items[0].rows[0], "back inside the bracket"


def sheet(*lines):
    ws = Worksheet()
    regions = []
    for k, line in enumerate(lines):
        r = ws.add_region(18, 9 + 36 * k)
        r.editor.type(line)
        ws.update_after_edit(r)
        regions.append(r)
    ws.calculate()
    return ws, regions


@pytest.mark.parametrize("text, value", [
    ("max(1,2)=", "2"), ("min(3,4)=", "3"), ("max(1,2,3)=", "3"), ("min(5;2;9)=", "2"),
    ("sum(1,2)=", "3"), ("sum(1,2,3)=", "6"), ("atan2(1,1)=", "0.7854"), ("lg(100)=", "2"),
    ("lg(1000)=", "3"), ("log(100;10)=", "2"), ("mod(7,3)=", "1"), ("round(2.567,2)=", "2.57"),
])
def test_built_ins_take_their_arities(text, value):
    ws, (r,) = sheet(text)
    assert r.editor.evaluate and r.error is None
    assert display_text(r.display) == value


def test_max_and_sum_with_a_variable_among_the_numbers():
    ws, (v, a, b) = sheet("v:2", "max(v,7,3)=", "sum(v,7,3)=")
    assert display_text(a.display) == "7" and display_text(b.display) == "12"


def test_sum_with_a_variable_still_iterates():
    ws, (r,) = sheet("sum(k,k,1,4=")
    assert display_text(r.display) == "10"


def test_a_call_with_numbers_is_never_a_definition():
    ws, (a, b) = sheet("foo(1,2)=", "round(2.5)=")
    assert a.editor.evaluate and a.error.message == "foo(#,#) - function is not defined."
    assert b.editor.evaluate and b.error.message == "Incorrect number of arguments."


def test_a_call_with_names_for_arguments_still_defines():
    ws, (a, b) = sheet("g(a,b)=", "h(x)=")
    assert a.editor.root.text() == "g(a,b)≔" and b.editor.root.text() == "h(x)≔"


def test_a_user_function_with_a_built_ins_name_wins():
    ws, (f, r) = sheet("max(a,b):a*b", "max(2,5)=")
    assert display_text(r.display) == "10"
