"""Numbers and units: random expressions calculated by the engine and by
the independent double-check must agree (value and unit); random numbers
must be displayed exactly as SMath's rules say (decimal places, exponential
threshold, half-to-even rounding of the binary value), checked against an
exact decimal reference."""
from __future__ import annotations

import math
import random
from decimal import ROUND_HALF_EVEN, Decimal

import pytest

from markforge.calc.engine import ast as A
from markforge.calc.engine.evaluator import Context, Evaluator
from markforge.calc.engine.numformat import NumberFormat, format_real
from markforge.calc.engine.units import Quantity
from markforge.calc.engine.verify import Checker, Fail, Unchecked, _dims_of

UNITS = ["m", "mm", "kN", "N", "kPa", "MPa", "s", "kg", "kN", "GPa", "cm", "t"]


def _rand_expr(rng, depth=0):
    if depth > 3 or rng.random() < 0.3:
        v = A.Num(str(rng.choice([rng.randint(1, 999), round(rng.uniform(0.001, 1000), rng.randint(0, 5))])))
        if rng.random() < 0.4:
            return A.BinOp("*", v, A.UnitRef(rng.choice(UNITS)))
        return v
    op = rng.choice(["+", "-", "*", "/", "*", "/", "^", "sqrt", "neg"])
    if op == "sqrt":
        return A.Call("sqrt", [_rand_expr(rng, depth + 1)])
    if op == "neg":
        return A.Unary("-", _rand_expr(rng, depth + 1))
    if op == "^":
        return A.BinOp("^", A.Group(_rand_expr(rng, depth + 1)), A.Num(str(rng.choice([2, 3, -1, 0.5]))))
    left = _rand_expr(rng, depth + 1)
    right = left if op in "+-" and rng.random() < 0.5 else _rand_expr(rng, depth + 1)
    return A.BinOp(op, A.Group(left), A.Group(right))


@pytest.mark.parametrize("block", range(10))
def test_engine_and_double_check_agree(block):
    agree = 0
    for seed in range(block * 300, block * 300 + 300):
        rng = random.Random(seed)
        node = _rand_expr(rng)
        try:
            mine = Checker().ev(node)
            ok_mine = True
        except (Fail, ZeroDivisionError):
            ok_mine = False
        except (Unchecked, OverflowError, ValueError):
            continue
        ev = Evaluator()
        ev.start_clock()
        try:
            got = ev.eval(node, Context())
            ok_got = isinstance(got, Quantity)
        except Exception as e:  # noqa: BLE001 - an SMathError is an error, anything else a bug
            from markforge.calc.engine.errors import SMathError

            assert isinstance(e, SMathError), (seed, repr(e))
            ok_got = False
        if not ok_mine or not ok_got:
            assert ok_mine == ok_got or not ok_mine, (seed, "engine errored but the check did not")
            continue
        if isinstance(got.value, complex) or isinstance(mine.x, complex):
            continue
        x = float(mine.x)
        if not math.isfinite(x) or not math.isfinite(got.value):
            continue
        assert math.isclose(x, got.value, rel_tol=1e-9, abs_tol=1e-300), (seed, x, got.value)
        assert mine.d == _dims_of(tuple(got.dims)), (seed, mine.d, got.dims)
        agree += 1
    assert agree > 150


def _reference(x: float, fmt: NumberFormat) -> str:
    """SMath's display rule, written independently with exact decimals."""
    if x == 0:
        return "0"
    d = Decimal(x)  # the exact binary value
    neg = d < 0
    d = abs(d)
    fixed = d.quantize(Decimal(1).scaleb(-fmt.decimals), rounding=ROUND_HALF_EVEN)
    exp = fixed.adjusted() if fixed else d.adjusted()
    if fixed == 0:
        exp = d.adjusted()
    if exp >= fmt.threshold or exp <= -fmt.threshold:
        m = (d.scaleb(-exp)).quantize(Decimal(1).scaleb(-fmt.decimals), rounding=ROUND_HALF_EVEN)
        if m >= 10:
            exp += 1
            m = (d.scaleb(-exp)).quantize(Decimal(1).scaleb(-fmt.decimals), rounding=ROUND_HALF_EVEN)
        s = format(m, "f").rstrip("0").rstrip(".")
        return ("-" if neg else "") + s + f"·10^{exp}"
    if fixed == 0:
        return "0"
    s = format(fixed, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return ("-" if neg else "") + s


@pytest.mark.parametrize("decimals,threshold", [(4, 5), (2, 5), (0, 5), (6, 8), (3, 3)])
def test_number_display_matches_reference(decimals, threshold):
    fmt = NumberFormat(decimals=decimals, threshold=threshold, engineering=False)
    rng = random.Random(decimals * 100 + threshold)
    for _ in range(3000):
        x = rng.choice([rng.uniform(-1e3, 1e3), 10 ** rng.uniform(-12, 12) * rng.choice([1, -1]),
                        rng.randint(-99999, 99999) / 8, round(rng.uniform(0, 10), 5)])
        assert format_real(x, fmt).plain() == _reference(x, fmt), x


def _reference_sig(x: float, n: int, thr: int) -> str:
    """Significant-figures mode: n significant digits (also left of the
    point), exponential form outside the threshold; exact decimals."""
    d = Decimal(x)
    neg = d < 0
    d = abs(d)
    if d == 0:
        return "0"
    exp = d.adjusted()
    q = d.quantize(Decimal(1).scaleb(exp - n + 1), rounding=ROUND_HALF_EVEN)
    if q.adjusted() != exp:
        exp = q.adjusted()
        q = d.quantize(Decimal(1).scaleb(exp - n + 1), rounding=ROUND_HALF_EVEN)
    if exp >= thr or exp <= -thr:
        m = q.scaleb(-exp)
        s = format(m.quantize(Decimal(1).scaleb(-(n - 1))), "f").rstrip("0").rstrip(".")
        return ("-" if neg else "") + s + f"·10^{exp}"
    s = format(q, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return ("-" if neg else "") + s


@pytest.mark.parametrize("n,thr", [(4, 5), (3, 5), (6, 8), (2, 3)])
def test_significant_figures_match_reference(n, thr):
    fmt = NumberFormat(decimals=n, threshold=thr, significant=True, engineering=False)
    rng = random.Random(n * 10 + thr)
    for _ in range(3000):
        x = rng.choice([rng.uniform(-1e4, 1e4), 10 ** rng.uniform(-9, 9), rng.randint(1, 99999) / 8])
        assert format_real(x, fmt).plain() == _reference_sig(x, n, thr), x
