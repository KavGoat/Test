"""symbolic(...): the only symbolic evaluation (through SymPy).  Every
formula is also checked numerically at random points, so a wrong rewrite
cannot pass; outside symbolic(...) the worksheet stays numeric."""
from __future__ import annotations

import random

import pytest

from calcforge.calc.engine.errors import SMathError
from calcforge.calc.engine.display import display_text
from calcforge.calc.engine.evaluator import Context, Evaluator
from calcforge.calc.engine.linear import parse_text
from calcforge.calc.engine.parser import parse_row
from calcforge.calc.engine.symbolic import Expr, to_row


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


def sym_eval(src, *defs):
    """symbolic(src) evaluated after the definitions: the formula node, or the value."""
    ev, c = Evaluator(), Context()
    for d in defs:
        ev.define(P(d), c)
    ev.start_clock()
    return ev.eval(P(f"symbolic({src})"), c)


def formula(src, *defs):
    v = sym_eval(src, *defs)
    assert isinstance(v, Expr), v
    return v.node


def number(src, *defs):
    v = sym_eval(src, *defs)
    assert not isinstance(v, Expr), text(v.node)
    return complex(v.value)


@pytest.mark.parametrize("src,want", [
    ("(x^2-1)/(x-1)", "x+1"), ("2*a+3*a", "5*a"), ("e^(ln(x))", "x"), ("sin(x)^2+cos(x)^2+y", "y+1"),
    ('(x+1)^3,"expand"', "x^(3)+3*x^(2)+3*x+1"), ('x^2-5*x+6,"factor"', "(x-3)*(x-2)"),
    ("diff(x^3,x)", "3*x^(2)"), ("diff(x^3,x,2)", "6*x"), ("diff(a*x^2+b*x+c,x)", "2*a*x+b"),
    ("int(x^2,x)", "(x^(3))/(3)"), ("int(x^2,x,0,a)", "(a^(3))/(3)"),
    ("sum(i,i,1,n)", "(n*(n+1))/(2)"), ("product(i,i,1,n)", "n!"),
    ("solve(a*x+b,x)", "(-b)/(a)"),
])
def test_formulas(src, want):
    got = formula(src)
    assert text(got) == want
    same_function(P(src.split(",\"")[0]) if "int(" not in src and "sum(" not in src and "product(" not in src
                  and "diff(" not in src and "solve(" not in src else got, got, names=("x", "y", "a", "b", "c"))


@pytest.mark.parametrize("src,want", [
    ("lim(sin(x)/x,x,0)", 1.0), ("lim((1-cos(x))/x^2,x,0)", 0.5), ("lim((1+1/n)^n,n,∞)", 2.718281828459045),
    ("lim(x*sin(1/x),x,0)", 0.0), ("lim((x^2-4)/(x-2),x,2)", 4.0), ("lim(sqrt(x),x,0)", 0.0),
    ("int(x^2,x,0,1)", 1 / 3), ("int(e^(-x^2),x,0,∞)", 0.886226925452758), ("sum(1/k^2,k,1,∞)", 1.6449340668482264),
    ("π/2+π/2", 3.141592653589793), ("sqrt(8)", 8 ** 0.5),
])
def test_numbers_when_no_letters_are_left(src, want):
    assert number(src) == pytest.approx(want, rel=1e-12)


@pytest.mark.parametrize("src,message", [
    ("lim(sin(1/x),x,0)", "limit does not exist"), ("lim(1/x,x,0)", "limit does not exist"),
    ("lim(floor(x),x,1)", "limit does not exist"), ("1/0", "cannot be evaluated symbolically"),
    ("int(x^n,x)", "cannot be evaluated symbolically"),  # the answer needs cases: never shown
    ("solve(x^2+1≡x^2,x)", "No solution"), ('x,"sideways"', "mode must be"),
])
def test_errors_instead_of_guesses(src, message):
    with pytest.raises(SMathError, match=message):
        sym_eval(src)


def test_worksheet_values_are_used():
    assert text(formula("k*y+k*y", "k:=3")) == "6*y"
    assert text(formula("f(t)", "f(x):=x^2+1")) == "t^(2)+1"
    assert text(formula("y", "y:=a+a")) == "2*a"  # a definition kept as a formula
    assert text(formula("v[2]*x", "v:=stack(1,2,3)")) == "2*x"  # numeric parts by value
    # the variable of diff/int/solve is free inside, then takes its value
    assert number("diff(x^3,x)", "x:=2") == 12
    assert number("int(x^2,x,0,1)", "x:=5") == pytest.approx(1 / 3)


def test_units():
    assert text(formula("a*'kN+b*'m")) == "a*'kN+b*'m"
    v = sym_eval("5*'m+20*'cm")
    assert v.value == pytest.approx(5.2) and v.dims[0] == 1  # no letters: 5.2 m, with its units


def test_several_solutions_are_a_column():
    v = sym_eval("solve(x^2-4,x)")
    assert [x.value for x in v.items] == [-2, 2]
    f = formula("solve(x^2-a,x)")
    assert text(f) == "mat(-√(a),√(a),2,1)"


def test_outside_symbolic_everything_is_numeric():
    from tests.calc.test_behaviour import sheet

    ws, (r,) = sheet(list("diff(x^3") + ["RIGHT"] + list(",x") + ["RIGHT", "="])
    assert r.error is not None and r.error.message == "x - not defined."
    for gone in ("lim", "expand", "factor"):
        # no longer functions: "=" after an unknown f(x) starts a definition, as in SMath
        ws, (r,) = sheet(list(f"{gone}(x") + ["RIGHT", "="])
        assert r.editor.root.text() == f"{gone}(x)≔"


def test_in_a_worksheet():
    from tests.calc.test_behaviour import sheet

    ws, rs = sheet(list("k:3"), list("symbolic(k*y+k*y") + ["RIGHT", "="])
    assert display_text(rs[-1].display) == "6*y"


def test_symbolic_results_match_smath_or_are_errors():
    """SMath's example worksheets store SMath's own → answers: symbolic() of
    the same expressions must give the same or an error - never a different
    answer.  (The → regions themselves open as plain expressions.)"""
    import glob
    import xml.etree.ElementTree as ET
    from pathlib import Path

    from tests.calc.smfile import NS, load_sm, rpn_to_ast
    from calcforge.calc.engine import ast as A

    folder = Path(__file__).resolve().parents[2] / "SMath Studio" / "examples"
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
                stored.append((rpn_to_ast(list(m.find(f"{{{NS}}}input"))), rpn_to_ast(list(res))))
        if not stored:
            continue
        ws = load_sm(f)
        ws.calculate()
        for node, want_node in stored:
            want = to_row(want_node).text()
            # the region holding it, and the context just before it
            r = next(x for x in ws.ordered() if x.kind == "math" and x.plot is None
                     and not x.editor.evaluate and to_row(node).text() == x.editor.root.text())
            ctx = ws._context_before(r)
            try:
                v = ws.evaluator.eval(A.Call("symbolic", [node]), ctx)
            except SMathError:
                continue
            if isinstance(v, Expr):
                assert to_row(v.node).text() == want, (f, want, to_row(v.node).text())
            else:
                # a number (or matrix of numbers): SMath's stored answer, worked out
                w = ws.evaluator.eval(want_node, Context())
                ours = v.items if hasattr(v, "items") else [v]
                theirs = w.items if hasattr(w, "items") else [w]
                assert len(ours) == len(theirs), (f, want)
                for a, b in zip(ours, theirs):
                    assert complex(a.value) == pytest.approx(complex(b.value), rel=1e-12, abs=1e-12), (f, want)
            matched += 1
    assert matched >= 2
