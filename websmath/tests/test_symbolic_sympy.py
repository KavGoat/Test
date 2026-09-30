"""Symbolic algebra through SymPy: → (symbolic evaluation), expand, factor,
symbolic solve and lim.  Every symbolic answer is also checked numerically
at random points, so a wrong rewrite cannot pass."""
from __future__ import annotations

import random

import pytest

from websmath.engine import sym
from websmath.engine.display import display_text
from websmath.engine.evaluator import Context, Evaluator
from websmath.engine.linear import parse_text
from websmath.engine.parser import parse_row
from websmath.engine.symbolic import NotSymbolic, to_row
from websmath.io.smfile import dumps, loads
from websmath.worksheet import Worksheet


def P(t):
    return parse_row(parse_text(t))


def text(node):
    return to_row(node).text()


def _num(node, **env):
    ev = Evaluator()
    ev.start_clock()
    c = Context()
    for k, v in env.items():
        c.vars[k] = ev.eval(P(repr(v)), Context())
    return complex(ev.eval(node, c).value)


def same_function(a, b, names=("x", "y", "a", "b"), trials=12):
    rng = random.Random(1)
    for _ in range(trials):
        env = {n: round(rng.uniform(0.3, 3.0), 3) for n in names}
        try:
            va = _num(a, **env)
        except Exception:
            continue
        vb = _num(b, **env)
        assert abs(va - vb) <= 1e-9 * max(1, abs(va)), (text(a), text(b), env)


@pytest.mark.parametrize("src,want", [
    ("(x^2-1)/(x-1)", "x+1"), ("sin(x)^2+cos(x)^2", "1"), ("2*a+3*a", "5*a"), ("π/2+π/2", "π"),
    ("e^(ln(x))", "x"), ("5*'kg*2", "10'kg"),
])
def test_arrow_simplifies(src, want):
    got = sym.symbolic_value(P(src), Context())
    assert text(got) == want
    same_function(P(src), got)


def test_expand_factor_solve():
    c = Context()
    assert text(sym.expand_expr(P("(x+1)^3"), c)) == "x^(3)+3*x^(2)+3*x+1"
    assert text(sym.factor_expr(P("x^2-5*x+6"), c)) == "(x-3)*(x-2)"
    assert [text(n) for n in sym.solve_expr(P("x^2≡4"), "x", c)] == ["-2", "2"]
    (s,) = sym.solve_expr(P("a*x+b"), "x", c)
    same_function(s, P("-b/a"))


@pytest.mark.parametrize("f,var,a,want", [
    ("sin(x)/x", "x", "0", 1.0), ("(1-cos(x))/x^2", "x", "0", 0.5), ("(1+1/n)^n", "n", "∞", 2.718281828459045),
    ("x*sin(1/x)", "x", "0", 0.0), ("(x^2-4)/(x-2)", "x", "2", 4.0), ("1/x", "x", "∞", 0.0),
    ("sqrt(x)", "x", "0", 0.0), ("1/x^2", "x", "0", float("inf")), ("ln(x)", "x", "0", float("-inf")),
])
def test_limits(f, var, a, want):
    v = sym.limit_value(P(f), var, P(a), Context())
    assert float(v) == pytest.approx(want)


@pytest.mark.parametrize("f,var,a", [("sin(1/x)", "x", "0"), ("1/x", "x", "0"), ("floor(x)", "x", "1")])
def test_limits_that_do_not_exist(f, var, a):
    with pytest.raises(NotSymbolic):
        sym.limit_value(P(f), var, P(a), Context())


def _region(ws, x, y, keys, symbolic=False):
    r = ws.add_region(x, y)
    for k in keys:
        r.editor.key(k)
    if symbolic:
        assert r.editor.symbolic_equals()
        r.symbolic_eval = True
    ws.update_after_edit(r)
    return r


def test_arrow_in_a_worksheet_uses_definitions_and_saves():
    ws = Worksheet()
    _region(ws, 18, 9, list("k:3"))
    r = _region(ws, 18, 45, ["(", "x", "^", "2", "RIGHT", "-", "1", "RIGHT", "/", "x", "-", "1"], symbolic=True)
    s = _region(ws, 18, 90, list("k*y+k*y"), symbolic=True)
    ws.calculate()
    assert display_text(r.display) == "x+1"
    assert display_text(s.display) == "6*y"  # k is known: its value is used
    text_ = dumps(ws)
    assert text_.count('action="symbolic"') == 2
    again = loads(text_)
    shown = [display_text(x.display) for x in again.ordered() if x.symbolic_eval]
    assert shown == ["x+1", "6*y"]


def test_numeric_equals_is_unchanged():
    ws = Worksheet()
    r = _region(ws, 18, 9, list("2+3="))
    ws.calculate()
    assert display_text(r.display) == "5" and not r.symbolic_eval


def _show(keys):
    from websmath.tests.test_behaviour import sheet

    ws, rs = sheet(*keys)
    r = rs[-1]
    return display_text(r.display) if r.display is not None else r.error.message


def test_functions_in_a_worksheet():
    assert _show([list("expand((x+1)") + ["RIGHT", "^", "2", "RIGHT", "RIGHT", "="]]) == "x^(2)+2*x+1"
    assert _show([list("factor(x^2") + ["RIGHT"] + list("-1") + ["RIGHT", "="]]) == "(x-1)*(x+1)"
    assert _show([list("solve(a*x+b,x") + ["RIGHT", "="]]) == "(-b)/(a)"
    # numeric solve is unchanged: all values known
    assert _show([list("solve(x^2") + ["RIGHT"] + list("-4,x") + ["RIGHT", "="]]) == "[-2; 2]"
    assert _show([list("lim(sin(x") + ["RIGHT", "/", "x", "RIGHT"] + list(",x,0") + ["RIGHT", "="]]) == "1"
    assert _show([list("lim(1/x") + ["RIGHT"] + list(",x,0") + ["RIGHT", "="]]) == \
        "The limit does not exist or cannot be determined."
    # with a known value in it, the result is a number
    assert _show([list("k:2"), list("expand(k*(x+1") + ["RIGHT", "RIGHT", "="]]) == "2*x+2"


def test_lim_falls_back_to_the_strict_numeric_method():
    """A programmed function SymPy cannot read: the numeric limit, which
    only answers when both sides settle to the same value."""
    from websmath.engine.extra_functions import _lim
    from websmath.engine import ast as A

    ev = Evaluator()
    ev.start_clock()
    v = _lim(ev, A.Call("lim", [P("sin(x)/x"), A.Var("x"), P("0")]), Context())
    assert v.value == pytest.approx(1, abs=1e-9)
    from websmath.engine.errors import SMathError

    for bad in ("sin(1/x)", "1/x"):
        with pytest.raises(SMathError):
            _lim(ev, A.Call("lim", [P(bad), A.Var("x"), P("0")]), Context())


def test_symbolic_results_match_smath_or_are_errors():
    """SMath's example worksheets store SMath's own symbolic answers: ours
    must be the same or an error - never a different answer."""
    import glob
    import xml.etree.ElementTree as ET
    from pathlib import Path

    from websmath.io.smfile import NS, load_sm, rpn_to_ast

    folder = Path(__file__).resolve().parents[2] / "smath" / "SMath Studio" / "examples"
    if not folder.exists():
        pytest.skip("SMath examples not present")
    matched = 0
    for f in sorted(glob.glob(str(folder / "*.sm"))):
        root = ET.parse(f).getroot()
        stored = []
        for reg in root.iter(f"{{{NS}}}region"):
            m = reg.find(f"{{{NS}}}math")
            res = m.find(f"{{{NS}}}result") if m is not None else None
            if res is not None and res.get("action") == "symbolic":
                stored.append(to_row(rpn_to_ast(list(res))).text())
        if not stored:
            continue
        ws = load_sm(f)
        ours = [r for r in ws.ordered() if r.symbolic_eval]
        assert len(ours) == len(stored)
        for r, want in zip(ours, stored):
            if r.error is not None:
                continue
            assert to_row(r.value.node).text() == want, (f, r.editor.root.text())
            matched += 1
    assert matched >= 2
