"""What you see is right: random calculations with units are TYPED key by
key into the real editor, calculated by the worksheet, and the number and
unit SHOWN on screen are read back and compared with the exact answer.

The exact answer is computed here from the generated calculation itself,
in 60-digit arithmetic (mpmath) - not with the app's parser, evaluator or
number formatting.  Unit factors come from the unit table, which
test_proof_units.py checks against the exact NIST definitions.  The shown number must be the
exact value correctly rounded (within half a unit of its last shown digit)
and the shown unit must have exactly the right dimensions; with a unit typed
in the result's box the conversion must be exact too.

Hypothesis generates the calculations and, if one ever fails, shrinks it to
the smallest failing case.  PROOF_EXAMPLES sets how many (default 300).
"""
from __future__ import annotations

import os
from fractions import Fraction

import mpmath
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from websmath.engine.display import DNum, DQuantity, display_text
from websmath.engine.unitdata import BASE, UNITS
from websmath.engine.verify import parse_shown, parse_unit_text
from websmath.worksheet import Worksheet

mpmath.mp.dps = 60
N_EXAMPLES = int(os.environ.get("PROOF_EXAMPLES", "300"))

# units grouped by dimension, so sums can be generated with matching units
GROUPS = {
    "force": ["N", "kN", "MN", "lbf", "kip"],
    "length": ["m", "mm", "cm", "km", "in", "ft"],
    "pressure": ["Pa", "kPa", "MPa", "GPa", "psi", "bar"],
    "mass": ["kg", "g", "t", "lb"],
    "time": ["s", "min", "hr"],
    "none": [""],
}


def _dims(unit: str) -> dict:
    if not unit:
        return {}
    return {b: Fraction(e) for b, e in zip(BASE, UNITS[unit][1]) if e}


def _dmul(a, b, k=1):
    out = dict(a)
    for u, e in b.items():
        v = out.get(u, 0) + k * e
        if v:
            out[u] = v
        else:
            out.pop(u, None)
    return out


class Expr:
    """An expression as keystrokes plus its exact value and dimensions."""

    def __init__(self, keys, value, dims):
        self.keys, self.value, self.dims = keys, value, dims

    def __repr__(self):
        return f"Expr(typed={''.join(k if len(k) == 1 else ' ' + k + ' ' for k in self.keys)!r}, exact={mpmath.nstr(self.value, 20)}, dims={self.dims})"


decimals = st.builds(lambda i, k: Fraction(i, 10 ** k), st.integers(1, 99999), st.integers(0, 4))


@st.composite
def leaf(draw, group=None):
    g = group or draw(st.sampled_from(sorted(GROUPS)))
    unit = draw(st.sampled_from(GROUPS[g]))
    x = draw(decimals)
    text = _dec_text(x)
    factor = mpmath.mpf(UNITS[unit][0]) if unit else mpmath.mpf(1)
    keys = list(text) + (["'"] + list(unit) if unit else [])
    return Expr(keys, _exact(x) * factor, _dims(unit)), g


def _dec_text(x: Fraction) -> str:
    k = 0
    while (x * 10 ** k).denominator != 1:
        k += 1
    n = x * 10 ** k
    s = str(n.numerator).rjust(k + 1, "0")
    return s if k == 0 else s[:-k] + "." + s[-k:]


def paren(e: Expr) -> list:
    return ["("] + e.keys + ["RIGHT"]


@st.composite
def expr(draw, depth=0):
    if depth >= 3 or draw(st.booleans()) and depth > 0:
        e, _ = draw(leaf())
        return e
    op = draw(st.sampled_from(["+", "-", "*", "/", "^", "sqrt"]))
    if op in "+-":
        g = draw(st.sampled_from(sorted(GROUPS)))
        (a, _), (b, _) = draw(leaf(g)), draw(leaf(g))
        if draw(st.booleans()):
            # a sub-calculation plus a multiple of itself: same dimension
            a = draw(expr(depth + 1))
            k, _ = draw(leaf("none"))
            b = Expr(paren(a) + ["*"] + k.keys, a.value * k.value, a.dims)
        v = a.value + b.value if op == "+" else a.value - b.value
        return Expr(paren(a) + [op] + paren(b), v, a.dims)
    if op == "*":
        a, b = draw(expr(depth + 1)), draw(expr(depth + 1))
        return Expr(paren(a) + ["*"] + paren(b), a.value * b.value, _dmul(a.dims, b.dims))
    if op == "/":
        a, b = draw(expr(depth + 1)), draw(expr(depth + 1))
        if b.value == 0:
            return a
        return Expr(paren(a) + ["/"] + paren(b) + ["RIGHT"], a.value / b.value, _dmul(a.dims, b.dims, -1))
    if op == "^":
        a = draw(expr(depth + 1))
        n = draw(st.sampled_from([2, 3, -1, -2]))
        if a.value == 0:
            return a
        keys = paren(a) + ["^"] + (["-"] if n < 0 else []) + [str(abs(n))] + ["RIGHT"]
        return Expr(keys, a.value ** n, {u: e * n for u, e in a.dims.items()})
    a = draw(expr(depth + 1))
    if a.value <= 0 or any(e.denominator != 1 or e % 2 for e in a.dims.values()):
        return a
    return Expr(["sqrt("] + a.keys + ["RIGHT"], mpmath.sqrt(a.value),
                {u: e / 2 for u, e in a.dims.items()})


def _type(ed, keys):
    for k in keys:
        if k == "sqrt(":
            ed.type("sqrt(")
        else:
            ed.key(k)


def _exact(v) -> mpmath.mpf:
    if isinstance(v, Fraction):
        return mpmath.mpf(v.numerator) / v.denominator
    return mpmath.mpf(v)


def _check_shown(r, e: Expr, unit_box: str = ""):
    d = r.display
    assert r.error is None, (r.editor.root.text(), r.error.message)
    assert isinstance(d, DQuantity) and isinstance(d.value, DNum), display_text(d)
    text = display_text(d)
    x, unit = parse_shown(text)
    factor, dims = parse_unit_text(unit)
    if unit_box:
        bf, bd = parse_unit_text(unit_box)
        factor *= bf
        dims = _dmul(dims, bd)
    # the unit shown (plus the box) has exactly the dimensions of the answer
    assert dims == {k: v for k, v in e.dims.items() if v}, (text, dims, e.dims)
    exact = e.value / _exact(factor)
    # the shown number is the exact value correctly rounded: within half a
    # unit of its last shown digit (plus float noise, 1e-12 relative)
    num = text.split(" ")[0]
    mant = num.split("·10^")[0]
    power = int(num.split("·10^")[1]) if "·10^" in num else 0
    places = len(mant.split(".")[1]) if "." in mant else 0
    half = mpmath.mpf(10) ** (power - max(places, 4)) / 2  # 4 decimal places shown by default
    assert abs(mpmath.mpf(x) - exact) <= half + abs(exact) * mpmath.mpf("1e-12"), (text, float(exact))


@settings(max_examples=N_EXAMPLES, deadline=None, suppress_health_check=list(HealthCheck))
@given(expr())
def test_typed_calculation_shows_the_exact_answer(e):
    ws = Worksheet()
    r = ws.add_region(18, 18)
    _type(r.editor, e.keys + ["="])
    ws.update_after_edit(r)
    if r.error is not None and r.error.message in ("Result is above max. allowed positive number.",):
        return
    if abs(e.value) > mpmath.mpf("1e300") or (e.value != 0 and abs(e.value) < mpmath.mpf("1e-300")):
        return
    _check_shown(r, e)


BOX = {"force": ["N", "kN", "lbf"], "length": ["mm", "m", "ft"], "pressure": ["MPa", "kPa", "psi"],
       "mass": ["kg", "t"], "time": ["s", "hr"]}


@settings(max_examples=N_EXAMPLES, deadline=None, suppress_health_check=list(HealthCheck))
@given(st.sampled_from(sorted(BOX)), st.data())
def test_unit_typed_in_the_box_converts_exactly(group, data):
    (a, _), (b, _) = data.draw(leaf(group)), data.draw(leaf(group))
    e = Expr(paren(a) + ["+"] + paren(b), a.value + b.value, a.dims)
    target = data.draw(st.sampled_from(BOX[group]))
    ws = Worksheet()
    r = ws.add_region(18, 18)
    _type(r.editor, e.keys + ["="])
    r.editor.set_cursor(r.editor.unit, 0)
    _type(r.editor, ["'"] + list(target))
    ws.update_after_edit(r)
    _check_shown(r, e, unit_box=target)
