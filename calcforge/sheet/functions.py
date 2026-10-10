"""Excel's worksheet functions, written from Excel's documented behaviour.

Every function that does arithmetic keeps units: SUM of kN is kN, AVERAGE
of mm is mm, VAR of kN is kN², and mixing units that don't match is
#UNITS!. A few are CalcForge's own, for engineering work:

    VALUEIN(x, "kN")     x as a plain number in kN (5000 N -> 5)
    CONVERT(x, "kN")     x shown in kN (CONVERT(x, from, to) is Excel's)
    INTERP(x, xs, ys)    straight-line interpolation in a table
    UNITOF(x)            the unit x is shown in, as text
"""
from __future__ import annotations

import datetime as _dt
import math
import random
import re
import statistics
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_UP, ROUND_UP, Decimal
from typing import Callable, Optional

from calcforge.calc.engine.units import NODIM, dims_scale

from . import formula as F
from .dates import date_from_serial, serial_from_date, serial_from_datetime
from .evaluate import (MISSING, Ctx, Function, RefValue, _broadcast, compare_values, deref, ev, scalar)
from .refs import MAX_COLS, MAX_ROWS, CellRef, parse_range, quote_sheet
from .values import (BLANK, CALC, DIV0, ERROR_NUMBERS, NA, NAME, NUM, REF, UNITS_ERR, VALUE, Array,
                     ErrorValue, Qty, SheetError, add, default_unit, div, general_number, is_number,
                     magnitude, map_shown, mul, power, quantity, scaled, to_bool, to_float, to_int,
                     to_number, to_text, unit_parts, UnitTextError)


@dataclass
class Spec:
    fn: Callable
    least: int
    most: Optional[int]
    lazy: bool
    lift: tuple            # which arguments map element by element over arrays


FUNCTIONS: dict[str, Spec] = {}


def fn(*names, least=0, most=None, lazy=False, lift=()):
    def deco(f):
        for name in names:
            FUNCTIONS[name] = Spec(f, least, most, lazy, tuple(lift))
        return f
    return deco


def _many(n):
    return n if n is not None else 255


def call(n: F.Call, ctx: Ctx):
    spec = FUNCTIONS.get(n.name)
    if spec is None:
        fun = _lambda_named(n.name, ctx)
        if fun is not None:
            return fun.call([ev(a, ctx) for a in n.args], ctx)
        return NAME
    count = len(n.args)
    if count < spec.least or count > _many(spec.most):
        return VALUE
    if spec.lazy:
        try:
            return spec.fn(ctx, n.args)
        except SheetError as e:
            return e.error
    args = [MISSING if type(a) is F.Missing else ev(a, ctx) for a in n.args]
    if spec.lift:
        lifted = [i for i in spec.lift if i < len(args) and _is_block(args[i])]
        if lifted:
            return _lifted(spec, args, lifted, ctx)
    try:
        return spec.fn(*args)
    except SheetError as e:
        return e.error
    except (OverflowError, ValueError, ZeroDivisionError):
        return NUM


def _is_block(v) -> bool:
    return isinstance(v, Array) and (v.height > 1 or v.width > 1) or \
        isinstance(v, RefValue) and not v.single


def _lifted(spec: Spec, args, lifted, ctx):
    grids = {i: grid(args[i]) for i in lifted}
    h = max(g.height for g in grids.values())
    w = max(g.width for g in grids.values())
    rows = []
    for r in range(h):
        row = []
        for c in range(w):
            call_args = list(args)
            for i, g in grids.items():
                rr = 0 if g.height == 1 else r
                cc = 0 if g.width == 1 else c
                call_args[i] = g.get(rr, cc) if rr < g.height and cc < g.width else NA
            try:
                row.append(spec.fn(*call_args))
            except SheetError as e:
                row.append(e.error)
            except (OverflowError, ValueError, ZeroDivisionError):
                row.append(NUM)
        rows.append(tuple(row))
    return Array(tuple(rows))


# -- reading arguments --------------------------------------------------------------------
def grid(v) -> Array:
    v = deref(v)
    if isinstance(v, Array):
        return v
    return Array(((v,),))


def one(v):
    """One value; an error stops the function with that error."""
    v = scalar(v)
    if isinstance(v, ErrorValue):
        raise SheetError(v)
    return v


def num(v):
    return to_number(one(v))


def real(v) -> float:
    return to_float(one(v))


def integer(v) -> int:
    return to_int(one(v))


def text(v) -> str:
    return to_text(one(v))


def flag(v, default: bool = False) -> bool:
    if v is MISSING:
        return default
    v = one(v)
    if v is BLANK:
        return False
    return to_bool(v)


def opt(v, default):
    return default if v is MISSING or (scalar(v) is BLANK and not isinstance(v, RefValue)) else v


def numbers(args, text_counts=False, logical_counts=False):
    """The numbers in the arguments, as SUM and AVERAGE take them: in a
    reference or array only numbers count (text, TRUE/FALSE and blanks are
    passed over); typed straight in, TRUE is 1 and "5" is 5."""
    out = []
    for a in args:
        if a is MISSING:
            continue
        if isinstance(a, RefValue):
            for _r, _c, v in a.filled():
                t = type(v)
                if t is float or t is Qty:
                    out.append(v)
                elif t is ErrorValue:
                    raise SheetError(v)
                elif text_counts and isinstance(v, str):
                    out.append(0.0)
                elif logical_counts and isinstance(v, bool):
                    out.append(1.0 if v else 0.0)
        elif isinstance(a, Array):
            for v in a.values():
                if isinstance(v, ErrorValue):
                    raise SheetError(v)
                if is_number(v):
                    out.append(v)
                elif text_counts and isinstance(v, str):
                    out.append(0.0)
                elif logical_counts and isinstance(v, bool):
                    out.append(1.0 if v else 0.0)
        else:
            if isinstance(a, ErrorValue):
                raise SheetError(a)
            if a is BLANK:
                continue
            out.append(to_number(a))
    return out


def every_value(args):
    """Every value, blanks included, for COUNTA and the like."""
    for a in args:
        if a is MISSING:
            continue
        if isinstance(a, RefValue):
            for _r, _c, v in a.filled():
                yield v
        elif isinstance(a, Array):
            yield from a.values()
        else:
            yield a


def unify(nums):
    """(SI floats, dims, unit) of numbers that must share a unit."""
    dims = None
    unit = None
    out = []
    for n in nums:
        d = n.dims if isinstance(n, Qty) else NODIM
        if dims is None:
            dims = d
        elif d != dims:
            raise SheetError(UNITS_ERR)
        if unit is None and isinstance(n, Qty):
            unit = n.unit
        out.append(n.si if isinstance(n, Qty) else float(n))
    return out, (dims or NODIM), unit


def rebuild(si: float, dims, unit, p: float = 1.0):
    """A result in the inputs' unit (raised to p for VAR and SUMSQ)."""
    if p != 1.0:
        dims = dims_scale(dims, p)
        unit = f"{unit}^{general_number(p)}" if unit and re.fullmatch(r"[A-Za-zµμΩ]+", unit) else None
    return quantity(si, dims, unit if any(dims) else None)


# -- maths ----------------------------------------------------------------------------------
@fn("SUM", least=1)
def SUM(*args):
    nums = numbers(args)
    if all(type(n) is float for n in nums):
        return math.fsum(nums)
    total = None
    for n in nums:
        total = n if total is None else add(total, n)
    return 0.0 if total is None else total


@fn("PRODUCT", least=1)
def PRODUCT(*args):
    total = 1.0
    for n in numbers(args):
        total = mul(total, n)
    return total


@fn("SUMSQ", least=1)
def SUMSQ(*args):
    si, dims, unit = unify(numbers(args))
    return rebuild(sum(x * x for x in si), dims, unit, 2.0)


@fn("SUMPRODUCT", least=1)
def SUMPRODUCT(*args):
    grids = [grid(a) for a in args]
    h, w = grids[0].height, grids[0].width
    if any(g.height != h or g.width != w for g in grids):
        return VALUE
    total = None
    for i in range(h):
        for j in range(w):
            p = None
            for g in grids:
                v = g.get(i, j)
                if isinstance(v, ErrorValue):
                    return v
                x = v if is_number(v) else 0.0
                p = x if p is None else mul(p, x)
            total = p if total is None else add(total, p)
    return 0.0 if total is None else total


@fn("AVERAGE", least=1)
def AVERAGE(*args):
    si, dims, unit = unify(numbers(args))
    if not si:
        return DIV0
    return rebuild(math.fsum(si) / len(si), dims, unit)


@fn("AVERAGEA", least=1)
def AVERAGEA(*args):
    si, dims, unit = unify(numbers(args, text_counts=True, logical_counts=True))
    if not si:
        return DIV0
    return rebuild(math.fsum(si) / len(si), dims, unit)


@fn("COUNT", least=1)
def COUNT(*args):
    n = 0
    for a in args:
        if isinstance(a, (RefValue, Array)):
            n += sum(1 for v in every_value([a]) if is_number(v))
        elif a is not MISSING and not isinstance(a, ErrorValue):
            try:
                to_number(a)
                n += 1
            except SheetError:
                pass
    return float(n)


@fn("COUNTA", least=1)
def COUNTA(*args):
    return float(sum(1 for v in every_value(args) if v is not BLANK))


@fn("COUNTBLANK", least=1, most=1)
def COUNTBLANK(ref):
    if not isinstance(ref, RefValue):
        return VALUE
    filled = sum(1 for _r, _c, v in ref.filled() if not (v is BLANK or v == ""))
    return float(ref.height * ref.width - filled)


@fn("MAX", least=1)
def MAX(*args):
    nums = numbers(args)
    if not nums:
        return 0.0
    si, dims, unit = unify(nums)
    return rebuild(max(si), dims, unit)


@fn("MIN", least=1)
def MIN(*args):
    nums = numbers(args)
    if not nums:
        return 0.0
    si, dims, unit = unify(nums)
    return rebuild(min(si), dims, unit)


@fn("MAXA", least=1)
def MAXA(*args):
    nums = numbers(args, text_counts=True, logical_counts=True)
    return MAX(*[Array(((n,),)) for n in nums]) if nums else 0.0


@fn("MINA", least=1)
def MINA(*args):
    nums = numbers(args, text_counts=True, logical_counts=True)
    return MIN(*[Array(((n,),)) for n in nums]) if nums else 0.0


@fn("MEDIAN", least=1)
def MEDIAN(*args):
    si, dims, unit = unify(numbers(args))
    if not si:
        return NUM
    return rebuild(statistics.median(si), dims, unit)


@fn("MODE", "MODE.SNGL", least=1)
def MODE(*args):
    si, dims, unit = unify(numbers(args))
    counts = {}
    for x in si:
        counts[x] = counts.get(x, 0) + 1
    best = max(counts.values(), default=0)
    if best < 2:
        return NA
    for x in si:
        if counts[x] == best:
            return rebuild(x, dims, unit)


def _variance(args, sample: bool, a_variant=False):
    si, dims, unit = unify(numbers(args, text_counts=a_variant, logical_counts=a_variant))
    n = len(si)
    if n < (2 if sample else 1):
        return None, dims, unit
    mean = math.fsum(si) / n
    ss = math.fsum((x - mean) ** 2 for x in si)
    return ss / (n - 1 if sample else n), dims, unit


@fn("VAR", "VAR.S", least=1)
def VAR(*args):
    v, dims, unit = _variance(args, True)
    return DIV0 if v is None else rebuild(v, dims, unit, 2.0)


@fn("VARP", "VAR.P", least=1)
def VARP(*args):
    v, dims, unit = _variance(args, False)
    return DIV0 if v is None else rebuild(v, dims, unit, 2.0)


@fn("STDEV", "STDEV.S", least=1)
def STDEV(*args):
    v, dims, unit = _variance(args, True)
    return DIV0 if v is None else rebuild(math.sqrt(v), dims, unit)


@fn("STDEVP", "STDEV.P", least=1)
def STDEVP(*args):
    v, dims, unit = _variance(args, False)
    return DIV0 if v is None else rebuild(math.sqrt(v), dims, unit)


@fn("STDEVA", least=1)
def STDEVA(*args):
    v, dims, unit = _variance(args, True, True)
    return DIV0 if v is None else rebuild(math.sqrt(v), dims, unit)


@fn("LARGE", least=2, most=2)
def LARGE(values, k):
    si, dims, unit = unify(numbers([values]))
    k = integer(k)
    if k < 1 or k > len(si):
        return NUM
    return rebuild(sorted(si, reverse=True)[k - 1], dims, unit)


@fn("SMALL", least=2, most=2)
def SMALL(values, k):
    si, dims, unit = unify(numbers([values]))
    k = integer(k)
    if k < 1 or k > len(si):
        return NUM
    return rebuild(sorted(si)[k - 1], dims, unit)


@fn("RANK", "RANK.EQ", "RANK.AVG", least=2, most=3)
def RANK(x, ref, order=MISSING):
    value = magnitude(num(x))
    si, _dims, _unit = unify(numbers([ref]))
    if value not in si:
        return NA
    ascending = flag(order)
    ordered = sorted(si, reverse=not ascending)
    return float(ordered.index(value) + 1)


def _percentile(si, p, exclusive=False):
    si = sorted(si)
    n = len(si)
    if not n:
        raise SheetError(NUM)
    if exclusive:
        pos = p * (n + 1) - 1
        if pos < 0 or pos > n - 1:
            raise SheetError(NUM)
    else:
        if not 0 <= p <= 1:
            raise SheetError(NUM)
        pos = p * (n - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    return si[lo] + (si[hi] - si[lo]) * (pos - lo)


@fn("PERCENTILE", "PERCENTILE.INC", least=2, most=2)
def PERCENTILE(values, p):
    si, dims, unit = unify(numbers([values]))
    return rebuild(_percentile(si, real(p)), dims, unit)


@fn("PERCENTILE.EXC", least=2, most=2)
def PERCENTILE_EXC(values, p):
    si, dims, unit = unify(numbers([values]))
    return rebuild(_percentile(si, real(p), True), dims, unit)


@fn("QUARTILE", "QUARTILE.INC", least=2, most=2)
def QUARTILE(values, q):
    q = integer(q)
    if not 0 <= q <= 4:
        return NUM
    return PERCENTILE(values, q / 4)


@fn("QUARTILE.EXC", least=2, most=2)
def QUARTILE_EXC(values, q):
    q = integer(q)
    if not 1 <= q <= 3:
        return NUM
    return PERCENTILE_EXC(values, q / 4)


def _plain(f):
    """A function of a plain number (units not allowed, except when they cancel)."""
    def g(x):
        return float(f(real(x)))
    return g


def _angle(f):
    """Sine and the like: an angle in degrees ("30 deg") is taken as such."""
    def g(x):
        v = num(x)
        if isinstance(v, Qty):
            if any(v.dims):
                raise SheetError(UNITS_ERR)
            v = v.si
        return float(f(v))
    return g


for _name, _f in {"SIN": math.sin, "COS": math.cos, "TAN": math.tan, "SINH": math.sinh,
                  "COSH": math.cosh, "TANH": math.tanh, "ASINH": math.asinh,
                  "COT": lambda x: 1 / math.tan(x), "SEC": lambda x: 1 / math.cos(x),
                  "CSC": lambda x: 1 / math.sin(x), "COTH": lambda x: 1 / math.tanh(x),
                  "SECH": lambda x: 1 / math.cosh(x), "CSCH": lambda x: 1 / math.sinh(x)}.items():
    fn(_name, least=1, most=1, lift=(0,))(_angle(_f))


def _domain(f, ok):
    def g(x):
        v = real(x)
        if not ok(v):
            raise SheetError(NUM)
        return float(f(v))
    return g


fn("ASIN", least=1, most=1, lift=(0,))(_domain(math.asin, lambda x: -1 <= x <= 1))
fn("ACOS", least=1, most=1, lift=(0,))(_domain(math.acos, lambda x: -1 <= x <= 1))
fn("ATAN", least=1, most=1, lift=(0,))(_plain(math.atan))
fn("ACOSH", least=1, most=1, lift=(0,))(_domain(math.acosh, lambda x: x >= 1))
fn("ATANH", least=1, most=1, lift=(0,))(_domain(math.atanh, lambda x: -1 < x < 1))
fn("ACOT", least=1, most=1, lift=(0,))(_plain(lambda x: math.pi / 2 - math.atan(x)))
fn("EXP", least=1, most=1, lift=(0,))(_plain(math.exp))
fn("LN", least=1, most=1, lift=(0,))(_domain(math.log, lambda x: x > 0))
fn("LOG10", least=1, most=1, lift=(0,))(_domain(math.log10, lambda x: x > 0))
fn("DEGREES", least=1, most=1, lift=(0,))(_angle(math.degrees))
fn("RADIANS", least=1, most=1, lift=(0,))(_plain(math.radians))
fn("SQRTPI", least=1, most=1, lift=(0,))(_domain(lambda x: math.sqrt(x * math.pi), lambda x: x >= 0))
fn("FACTDOUBLE", least=1, most=1, lift=(0,))(_domain(
    lambda x: math.prod(range(int(x), 0, -2)) if int(x) > 0 else 1, lambda x: x >= -1))


@fn("ATAN2", least=2, most=2, lift=(0, 1))
def ATAN2(x, y):
    a, b = num(x), num(y)
    if isinstance(a, Qty) or isinstance(b, Qty):
        si, _dims, _unit = unify([a, b])
        a, b = si
    if a == 0 and b == 0:
        return DIV0
    return math.atan2(b, a)


@fn("LOG", least=1, most=2, lift=(0, 1))
def LOG(x, base=MISSING):
    v = real(x)
    b = 10.0 if base is MISSING else real(base)
    if v <= 0 or b <= 0:
        return NUM
    if b == 1:
        return DIV0
    return math.log(v) / math.log(b)


@fn("PI", most=0)
def PI():
    return math.pi


@fn("ABS", least=1, most=1, lift=(0,))
def ABS(x):
    v = num(x)
    return scaled(v, -1.0) if magnitude(v) < 0 else v


@fn("SIGN", least=1, most=1, lift=(0,))
def SIGN(x):
    v = magnitude(num(x))
    return float((v > 0) - (v < 0))


@fn("SQRT", least=1, most=1, lift=(0,))
def SQRT(x):
    v = num(x)
    if magnitude(v) < 0:
        return NUM
    return power(v, 0.5)


@fn("POWER", least=2, most=2, lift=(0, 1))
def POWER(x, y):
    return power(num(x), num(y))


def _dec(x: float) -> Decimal:
    return Decimal(repr(x))


def _round_to(x: float, digits: int, mode) -> float:
    if not math.isfinite(x):
        raise SheetError(NUM)
    q = Decimal(1).scaleb(-digits)
    d = _dec(x)
    # Excel rounds the 15-significant-digit value, so 2.675 rounds to 2.68
    d = Decimal(f"{float(d):.15g}")
    return float(d.quantize(q, rounding=mode)) if digits >= 0 else \
        float((d / Decimal(10) ** (-digits)).quantize(Decimal(1), rounding=mode) * Decimal(10) ** (-digits))


@fn("ROUND", least=2, most=2, lift=(0, 1))
def ROUND(x, digits):
    d = integer(digits)
    return map_shown(num(x), lambda v: _round_to(v, d, ROUND_HALF_UP))


@fn("ROUNDUP", least=2, most=2, lift=(0, 1))
def ROUNDUP(x, digits):
    d = integer(digits)
    return map_shown(num(x), lambda v: _round_to(v, d, ROUND_UP))


@fn("ROUNDDOWN", least=2, most=2, lift=(0, 1))
def ROUNDDOWN(x, digits):
    d = integer(digits)
    return map_shown(num(x), lambda v: _round_to(v, d, ROUND_DOWN))


@fn("TRUNC", least=1, most=2, lift=(0, 1))
def TRUNC(x, digits=MISSING):
    d = 0 if digits is MISSING else integer(digits)
    return map_shown(num(x), lambda v: _round_to(v, d, ROUND_DOWN))


@fn("INT", least=1, most=1, lift=(0,))
def INT(x):
    return map_shown(num(x), lambda v: float(math.floor(v)))


def _same_shown(a, b):
    """b's number in a's unit, for MROUND/CEILING/FLOOR(5.3 kN, 0.5 kN)."""
    if isinstance(a, Qty) or isinstance(b, Qty):
        si, dims, unit = unify([a, b])
        if isinstance(a, Qty):
            unit = a.unit or default_unit(a.dims)
            factor, _d, _o = unit_parts(unit) if unit else (1.0, None, 0)
            return a, si[1] / factor
        return a, si[1]
    return a, float(b)


@fn("MROUND", least=2, most=2, lift=(0, 1))
def MROUND(x, multiple):
    a, m = _same_shown(num(x), num(multiple))
    if m == 0:
        return 0.0
    if magnitude(a) * m < 0:
        return NUM
    return map_shown(a, lambda v: float(_dec(m) * (_dec(v) / _dec(m)).quantize(Decimal(1), ROUND_HALF_UP)))


@fn("CEILING", "CEILING.PRECISE", "ISO.CEILING", least=1, most=2, lift=(0, 1))
def CEILING(x, significance=MISSING):
    a = num(x)
    a, s = _same_shown(a, num(significance) if significance is not MISSING else 1.0)
    if s == 0:
        return 0.0
    s = abs(s)
    return map_shown(a, lambda v: float(math.ceil(round(v / s, 12)) * s))


@fn("CEILING.MATH", least=1, most=3, lift=(0, 1, 2))
def CEILING_MATH(x, significance=MISSING, mode=MISSING):
    a = num(x)
    a, s = _same_shown(a, num(significance) if significance is not MISSING else 1.0)
    if s == 0:
        return 0.0
    s = abs(s)
    away = flag(mode)
    def f(v):
        if v < 0 and away:
            return float(math.floor(round(v / s, 12)) * s)
        return float(math.ceil(round(v / s, 12)) * s)
    return map_shown(a, f)


@fn("FLOOR", "FLOOR.PRECISE", least=1, most=2, lift=(0, 1))
def FLOOR(x, significance=MISSING):
    a = num(x)
    a, s = _same_shown(a, num(significance) if significance is not MISSING else 1.0)
    if s == 0:
        return DIV0
    s = abs(s)
    return map_shown(a, lambda v: float(math.floor(round(v / s, 12)) * s))


@fn("FLOOR.MATH", least=1, most=3, lift=(0, 1, 2))
def FLOOR_MATH(x, significance=MISSING, mode=MISSING):
    a = num(x)
    a, s = _same_shown(a, num(significance) if significance is not MISSING else 1.0)
    if s == 0:
        return 0.0
    s = abs(s)
    toward = flag(mode)
    def f(v):
        if v < 0 and toward:
            return float(math.ceil(round(v / s, 12)) * s)
        return float(math.floor(round(v / s, 12)) * s)
    return map_shown(a, f)


@fn("MOD", least=2, most=2, lift=(0, 1))
def MOD(x, y):
    a, b = num(x), num(y)
    if isinstance(a, Qty) or isinstance(b, Qty):
        si, dims, unit = unify([a, b])
        if si[1] == 0:
            return DIV0
        return rebuild(si[0] - si[1] * math.floor(si[0] / si[1]), dims, unit)
    if b == 0:
        return DIV0
    return a - b * math.floor(a / b)


@fn("QUOTIENT", least=2, most=2, lift=(0, 1))
def QUOTIENT(x, y):
    q = div(num(x), num(y))
    if isinstance(q, Qty):
        return q
    return float(math.trunc(q))


@fn("EVEN", least=1, most=1, lift=(0,))
def EVEN(x):
    v = real(x)
    n = math.ceil(abs(v))
    n += n % 2
    return float(n if v >= 0 else -n)


@fn("ODD", least=1, most=1, lift=(0,))
def ODD(x):
    v = real(x)
    n = math.ceil(abs(v))
    if n % 2 == 0:
        n += 1
    return float(n if v >= 0 else -n)


@fn("FACT", least=1, most=1, lift=(0,))
def FACT(x):
    v = real(x)
    if v < 0:
        return NUM
    return float(math.factorial(int(v)))


@fn("COMBIN", least=2, most=2, lift=(0, 1))
def COMBIN(n, k):
    a, b = integer(n), integer(k)
    if a < 0 or b < 0 or b > a:
        return NUM
    return float(math.comb(a, b))


@fn("PERMUT", least=2, most=2, lift=(0, 1))
def PERMUT(n, k):
    a, b = integer(n), integer(k)
    if a < 0 or b < 0 or b > a:
        return NUM
    return float(math.perm(a, b))


@fn("GCD", least=1)
def GCD(*args):
    out = 0
    for n in numbers(args):
        v = to_float(n)
        if v < 0:
            raise SheetError(NUM)
        out = math.gcd(out, int(v))
    return float(out)


@fn("LCM", least=1)
def LCM(*args):
    out = 1
    for n in numbers(args):
        v = to_float(n)
        if v < 0:
            raise SheetError(NUM)
        v = int(v)
        if v == 0:
            return 0.0
        out = out * v // math.gcd(out, v)
    return float(out)


@fn("RAND", most=0)
def RAND():
    return random.random()


@fn("RANDBETWEEN", least=2, most=2)
def RANDBETWEEN(a, b):
    lo, hi = math.ceil(real(a)), math.floor(real(b))
    if lo > hi:
        return NUM
    return float(random.randint(lo, hi))


@fn("RANDARRAY", most=5)
def RANDARRAY(rows=MISSING, cols=MISSING, lo=MISSING, hi=MISSING, whole=MISSING):
    r = 1 if rows is MISSING else integer(rows)
    c = 1 if cols is MISSING else integer(cols)
    a = 0.0 if lo is MISSING else real(lo)
    b = 1.0 if hi is MISSING else real(hi)
    w = flag(whole)
    if r < 1 or c < 1 or a > b:
        return VALUE
    make = (lambda: float(random.randint(math.ceil(a), math.floor(b)))) if w else \
        (lambda: a + (b - a) * random.random())
    return Array(tuple(tuple(make() for _ in range(c)) for _ in range(r)))


@fn("SUBTOTAL", least=2)
def SUBTOTAL(code, *refs):
    """Leaves out rows a filter hides (101-111: rows hidden by hand too), as Excel."""
    n = integer(code)
    which = n % 100
    kept = []
    for ref in refs:
        if isinstance(ref, RefValue):
            sheet = ref.sheet
            skip = set(sheet.filtered_rows) | (set(sheet.hidden_rows) if n > 100 else set())
            if skip:
                rows = [tuple(sheet.workbook.value(sheet, r, c) for c in range(ref.left, ref.right + 1))
                        for r in range(ref.top, ref.bottom + 1) if r not in skip]
                kept.append(Array(tuple(rows)) if rows else Array(((BLANK,),)))
                continue
        kept.append(ref)
    refs = kept
    table = {1: AVERAGE, 2: COUNT, 3: COUNTA, 4: MAX, 5: MIN, 6: PRODUCT, 7: STDEV, 8: STDEVP,
             9: SUM, 10: VAR, 11: VARP}
    f = table.get(which)
    if f is None:
        return VALUE
    return f(*refs)


@fn("AGGREGATE", least=3)
def AGGREGATE(code, options, *refs):
    which = integer(code)
    table = {1: AVERAGE, 2: COUNT, 3: COUNTA, 4: MAX, 5: MIN, 6: PRODUCT, 7: STDEV, 8: STDEVP,
             9: SUM, 10: VAR, 11: VARP, 12: MEDIAN, 13: MODE}
    if which in table:
        clean = []
        for r in refs:
            g = grid(r)
            clean.append(Array(tuple(tuple(BLANK if isinstance(v, ErrorValue) else v for v in row)
                                     for row in g.rows)))
        return table[which](*clean)
    if which in (14, 15, 16, 17, 18, 19) and len(refs) == 2:
        g = grid(refs[0])
        clean = Array(tuple(tuple(BLANK if isinstance(v, ErrorValue) else v for v in row) for row in g.rows))
        f = {14: LARGE, 15: SMALL, 16: PERCENTILE, 17: QUARTILE, 18: PERCENTILE_EXC, 19: QUARTILE_EXC}[which]
        return f(clean, refs[1])
    return VALUE


# -- matrices ------------------------------------------------------------------------------
def _matrix(v):
    g = grid(v)
    out = []
    for row in g.rows:
        line = []
        for x in row:
            if isinstance(x, ErrorValue):
                raise SheetError(x)
            if not is_number(x):
                raise SheetError(VALUE)
            line.append(to_float(x))
        out.append(line)
    return out


@fn("MMULT", least=2, most=2)
def MMULT(a, b):
    A, B = _matrix(a), _matrix(b)
    if len(A[0]) != len(B):
        return VALUE
    return Array(tuple(tuple(math.fsum(A[i][k] * B[k][j] for k in range(len(B)))
                             for j in range(len(B[0]))) for i in range(len(A))))


def _det(M):
    n = len(M)
    M = [row[:] for row in M]
    det = 1.0
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(M[r][i]))
        if abs(M[p][i]) < 1e-300:
            return 0.0
        if p != i:
            M[i], M[p] = M[p], M[i]
            det = -det
        det *= M[i][i]
        for r in range(i + 1, n):
            f = M[r][i] / M[i][i]
            for c in range(i, n):
                M[r][c] -= f * M[i][c]
    return det


@fn("MDETERM", least=1, most=1)
def MDETERM(a):
    M = _matrix(a)
    if len(M) != len(M[0]):
        return VALUE
    return _det(M)


@fn("MINVERSE", least=1, most=1)
def MINVERSE(a):
    M = _matrix(a)
    n = len(M)
    if n != len(M[0]):
        return VALUE
    A = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(M)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(A[r][i]))
        if abs(A[p][i]) < 1e-300:
            return NUM
        A[i], A[p] = A[p], A[i]
        piv = A[i][i]
        A[i] = [x / piv for x in A[i]]
        for r in range(n):
            if r != i:
                f = A[r][i]
                A[r] = [x - f * y for x, y in zip(A[r], A[i])]
    return Array(tuple(tuple(row[n:]) for row in A))


@fn("MUNIT", least=1, most=1)
def MUNIT(n):
    k = integer(n)
    if k < 1:
        return VALUE
    return Array(tuple(tuple(1.0 if i == j else 0.0 for j in range(k)) for i in range(k)))


@fn("TRANSPOSE", least=1, most=1)
def TRANSPOSE(a):
    g = grid(a)
    return Array(tuple(tuple(g.get(i, j) for i in range(g.height)) for j in range(g.width)))


# -- logic --------------------------------------------------------------------------------
@fn("IF", least=1, most=3, lazy=True)
def IF(ctx, args):
    test = deref(ev(args[0], ctx))
    if isinstance(test, Array):
        yes = deref(ev(args[1], ctx)) if len(args) > 1 else True
        no = deref(ev(args[2], ctx)) if len(args) > 2 else False
        def pick(t, a, b):
            if isinstance(t, ErrorValue):
                return t
            try:
                return a if to_bool(t) else b
            except SheetError as e:
                return e.error
        g = _broadcast(test, yes, lambda t, a: (t, a))
        out = []
        nog = grid(no)
        for i, row in enumerate(g.rows):
            line = []
            for j, (t, a) in enumerate(row):
                b = nog.get(0 if nog.height == 1 else i, 0 if nog.width == 1 else j) \
                    if (nog.height == 1 or i < nog.height) and (nog.width == 1 or j < nog.width) else NA
                line.append(pick(t, a, b))
            out.append(tuple(line))
        return Array(tuple(out))
    if isinstance(test, ErrorValue):
        return test
    if to_bool(test):
        if len(args) < 2:
            return True
        return BLANK_TO_ZERO(ev(args[1], ctx), args[1])
    if len(args) < 3:
        return False
    return BLANK_TO_ZERO(ev(args[2], ctx), args[2])


def BLANK_TO_ZERO(v, node):
    if type(node) is F.Missing:
        return 0.0
    return v


@fn("IFS", least=2, lazy=True)
def IFS(ctx, args):
    if len(args) % 2:
        return VALUE
    for i in range(0, len(args), 2):
        test = one(ev(args[i], ctx))
        if to_bool(test):
            return ev(args[i + 1], ctx)
    return NA


@fn("IFERROR", least=2, most=2, lazy=True)
def IFERROR(ctx, args):
    v = deref(ev(args[0], ctx))
    if isinstance(v, Array):
        fallback = deref(ev(args[1], ctx))
        return Array(tuple(tuple(fallback if isinstance(x, ErrorValue) else x for x in row) for row in v.rows))
    if isinstance(v, ErrorValue):
        return ev(args[1], ctx)
    return v


@fn("IFNA", least=2, most=2, lazy=True)
def IFNA(ctx, args):
    v = deref(ev(args[0], ctx))
    if v == NA:
        return ev(args[1], ctx)
    return v


def _truths(args):
    out = []
    for a in args:
        if isinstance(a, (RefValue, Array)):
            for v in every_value([a]):
                if isinstance(v, ErrorValue):
                    raise SheetError(v)
                if isinstance(v, bool) or is_number(v):
                    out.append(to_bool(v))
        elif a is not MISSING:
            out.append(to_bool(one(a)))
    if not out:
        raise SheetError(VALUE)
    return out


@fn("AND", least=1)
def AND(*args):
    return all(_truths(args))


@fn("OR", least=1)
def OR(*args):
    return any(_truths(args))


@fn("XOR", least=1)
def XOR(*args):
    return sum(_truths(args)) % 2 == 1


@fn("NOT", least=1, most=1, lift=(0,))
def NOT(x):
    return not to_bool(one(x))


@fn("TRUE", most=0)
def TRUE():
    return True


@fn("FALSE", most=0)
def FALSE():
    return False


@fn("SWITCH", least=3, lazy=True)
def SWITCH(ctx, args):
    value = one(ev(args[0], ctx))
    rest = args[1:]
    for i in range(0, len(rest) - 1, 2):
        if compare_values(value, one(ev(rest[i], ctx))) == 0:
            return ev(rest[i + 1], ctx)
    if len(rest) % 2:
        return ev(rest[-1], ctx)
    return NA


@fn("CHOOSE", least=2, lazy=True)
def CHOOSE(ctx, args):
    i = integer(ev(args[0], ctx))
    if not 1 <= i < len(args):
        return VALUE
    return ev(args[i], ctx)


@fn("LET", least=3, lazy=True)
def LET(ctx, args):
    if len(args) % 2 == 0:
        return VALUE
    saved = ctx.lets
    ctx.lets = dict(saved or {})
    try:
        for i in range(0, len(args) - 1, 2):
            name = args[i]
            if not isinstance(name, F.Name):
                return VALUE
            ctx.lets[name.name.lower()] = ev(args[i + 1], ctx)
        return ev(args[-1], ctx)
    finally:
        ctx.lets = saved


class _Lambda(Function):
    def __init__(self, params, body, ctx):
        self.params = params
        self.body = body
        self.lets = dict(ctx.lets or {})

    def call(self, values, ctx):
        if len(values) != len(self.params):
            return VALUE
        saved = ctx.lets
        ctx.lets = dict(self.lets)
        ctx.lets.update({p: v for p, v in zip(self.params, values)})
        try:
            return ev(self.body, ctx)
        finally:
            ctx.lets = saved


def _lambda_named(name: str, ctx):
    """A function the formula didn't get from Excel: a LET name holding a
    LAMBDA, or a defined name (Name Manager) that is one."""
    lower = name.lower()
    if ctx.lets and lower in ctx.lets and isinstance(ctx.lets[lower], _Lambda):
        return ctx.lets[lower]
    dn = ctx.wb.find_name(name, ctx.sheet)
    if dn is None or ctx.depth > 40:
        return None
    try:
        parsed = F.parse(dn.refers_to, 0, 0)
    except F.FormulaError:
        return None
    from .evaluate import Ctx
    home = ctx.wb.sheet_by_id(dn.sheet) if dn.sheet else ctx.sheet
    inner = Ctx(ctx.wb, home, ctx.row, ctx.col)
    inner.reads = ctx.reads
    inner.depth = ctx.depth + 1
    got = ev(parsed.tree, inner)
    return got if isinstance(got, _Lambda) else None


def apply(n, ctx):
    """LAMBDA(x, x*2)(3)."""
    fun = ev(n.fn, ctx)
    if not isinstance(fun, _Lambda):
        return VALUE
    return fun.call([ev(a, ctx) for a in n.args], ctx)


def _lambda_arg(node, ctx):
    fun = ev(node, ctx)
    if not isinstance(fun, _Lambda):
        raise SheetError(VALUE)
    return fun


def _scalar_result(v):
    from .evaluate import result
    v = result(v)
    if isinstance(v, Array):
        raise SheetError(CALC)                 # one value per cell (Excel's #CALC!)
    return v


@fn("MAP", least=2, lazy=True)
def MAP(ctx, args):
    """MAP(array1, [array2…], LAMBDA): each element through the function."""
    fun = _lambda_arg(args[-1], ctx)
    grids = [grid(ev(a, ctx)) for a in args[:-1]]
    h = max(g.height for g in grids)
    w = max(g.width for g in grids)
    rows = []
    for r in range(h):
        rows.append(tuple(_scalar_result(fun.call(
            [g.get(r if g.height > 1 else 0, c if g.width > 1 else 0) for g in grids], ctx))
            for c in range(w)))
    return Array(tuple(rows))


@fn("BYROW", least=2, most=2, lazy=True)
def BYROW(ctx, args):
    g = grid(ev(args[0], ctx))
    fun = _lambda_arg(args[1], ctx)
    return Array(tuple((_scalar_result(fun.call([Array((g.rows[r],))], ctx)),)
                       for r in range(g.height)))


@fn("BYCOL", least=2, most=2, lazy=True)
def BYCOL(ctx, args):
    g = grid(ev(args[0], ctx))
    fun = _lambda_arg(args[1], ctx)
    cols = [Array(tuple((g.rows[r][c],) for r in range(g.height))) for c in range(g.width)]
    return Array((tuple(_scalar_result(fun.call([col], ctx)) for col in cols),))


@fn("REDUCE", least=3, most=3, lazy=True)
def REDUCE(ctx, args):
    acc = ev(args[0], ctx)
    g = grid(ev(args[1], ctx))
    fun = _lambda_arg(args[2], ctx)
    for v in g.values():
        acc = fun.call([acc, v], ctx)
    return acc


@fn("SCAN", least=3, most=3, lazy=True)
def SCAN(ctx, args):
    acc = ev(args[0], ctx)
    g = grid(ev(args[1], ctx))
    fun = _lambda_arg(args[2], ctx)
    rows = []
    for r in range(g.height):
        row = []
        for c in range(g.width):
            acc = _scalar_result(fun.call([acc, g.get(r, c)], ctx))
            row.append(acc)
        rows.append(tuple(row))
    return Array(tuple(rows))


@fn("MAKEARRAY", least=3, most=3, lazy=True)
def MAKEARRAY(ctx, args):
    rows = int(to_number(scalar(ev(args[0], ctx))))
    cols = int(to_number(scalar(ev(args[1], ctx))))
    if rows < 1 or cols < 1:
        return VALUE
    fun = _lambda_arg(args[2], ctx)
    return Array(tuple(tuple(_scalar_result(fun.call([float(r + 1), float(c + 1)], ctx))
                             for c in range(cols)) for r in range(rows)))


@fn("LAMBDA", least=1, lazy=True)
def LAMBDA(ctx, args):
    params = []
    for a in args[:-1]:
        if not isinstance(a, F.Name):
            return VALUE
        params.append(a.name.lower())
    return _Lambda(params, args[-1], ctx)


# -- information -------------------------------------------------------------------------
@fn("ISBLANK", least=1, most=1)
def ISBLANK(x):
    return deref(x) is BLANK if not isinstance(x, Array) else False


@fn("ISNUMBER", least=1, most=1, lift=(0,))
def ISNUMBER(x):
    return is_number(scalar(x))


@fn("ISTEXT", least=1, most=1, lift=(0,))
def ISTEXT(x):
    return isinstance(scalar(x), str)


@fn("ISNONTEXT", least=1, most=1, lift=(0,))
def ISNONTEXT(x):
    return not isinstance(scalar(x), str)


@fn("ISLOGICAL", least=1, most=1, lift=(0,))
def ISLOGICAL(x):
    return isinstance(scalar(x), bool)


@fn("ISERROR", least=1, most=1, lift=(0,))
def ISERROR(x):
    return isinstance(scalar(x), ErrorValue)


@fn("ISERR", least=1, most=1, lift=(0,))
def ISERR(x):
    v = scalar(x)
    return isinstance(v, ErrorValue) and v != NA


@fn("ISNA", least=1, most=1, lift=(0,))
def ISNA(x):
    return scalar(x) == NA


@fn("ISREF", least=1, most=1)
def ISREF(x):
    return isinstance(x, RefValue)


@fn("ISEVEN", least=1, most=1, lift=(0,))
def ISEVEN(x):
    return int(real(x)) % 2 == 0


@fn("ISODD", least=1, most=1, lift=(0,))
def ISODD(x):
    return int(real(x)) % 2 == 1


@fn("ISFORMULA", least=1, most=1)
def ISFORMULA(x):
    if not isinstance(x, RefValue):
        return VALUE
    cell = x.sheet.cell(x.top, x.left)
    return bool(cell and cell.is_formula)


@fn("FORMULATEXT", least=1, most=1)
def FORMULATEXT(x):
    if not isinstance(x, RefValue):
        return VALUE
    cell = x.sheet.cell(x.top, x.left)
    if not cell or not cell.is_formula:
        return NA
    return cell.input


@fn("NA", most=0)
def NA_():
    return NA


@fn("ERROR.TYPE", least=1, most=1)
def ERROR_TYPE(x):
    v = scalar(x)
    if isinstance(v, ErrorValue):
        return float(ERROR_NUMBERS.get(v.code, 3))
    return NA


@fn("TYPE", least=1, most=1)
def TYPE(x):
    v = deref(x)
    if isinstance(v, Array):
        return 64.0
    if isinstance(v, bool):
        return 4.0
    if is_number(v) or v is BLANK:
        return 1.0
    if isinstance(v, str):
        return 2.0
    if isinstance(v, ErrorValue):
        return 16.0
    return 1.0


@fn("N", least=1, most=1)
def N(x):
    v = scalar(x)
    if isinstance(v, ErrorValue):
        return v
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if is_number(v):
        return v
    return 0.0


@fn("T", least=1, most=1)
def T(x):
    v = scalar(x)
    if isinstance(v, ErrorValue):
        return v
    return v if isinstance(v, str) else ""


@fn("SHEET", most=1)
def SHEET(x=MISSING):
    return 1.0


# -- text ----------------------------------------------------------------------------------
@fn("CONCAT", "CONCATENATE", least=1)
def CONCAT(*args):
    out = []
    for v in every_value(args):
        if isinstance(v, ErrorValue):
            return v
        out.append(to_text(v))
    return "".join(out)


@fn("TEXTJOIN", least=3)
def TEXTJOIN(delim, skip_empty, *args):
    d = text(delim)
    skip = flag(skip_empty)
    parts = []
    for v in every_value(args):
        if isinstance(v, ErrorValue):
            return v
        t = to_text(v)
        if skip and t == "":
            continue
        parts.append(t)
    return d.join(parts)


@fn("LEFT", least=1, most=2, lift=(0, 1))
def LEFT(x, n=MISSING):
    k = 1 if n is MISSING else integer(n)
    if k < 0:
        return VALUE
    return text(x)[:k]


@fn("RIGHT", least=1, most=2, lift=(0, 1))
def RIGHT(x, n=MISSING):
    k = 1 if n is MISSING else integer(n)
    if k < 0:
        return VALUE
    t = text(x)
    return t[len(t) - k:] if k else ""


@fn("MID", least=3, most=3, lift=(0, 1, 2))
def MID(x, start, n):
    s, k = integer(start), integer(n)
    if s < 1 or k < 0:
        return VALUE
    return text(x)[s - 1:s - 1 + k]


@fn("LEN", least=1, most=1, lift=(0,))
def LEN(x):
    return float(len(text(x)))


@fn("UPPER", least=1, most=1, lift=(0,))
def UPPER(x):
    return text(x).upper()


@fn("LOWER", least=1, most=1, lift=(0,))
def LOWER(x):
    return text(x).lower()


@fn("PROPER", least=1, most=1, lift=(0,))
def PROPER(x):
    return re.sub(r"[A-Za-z]+", lambda m: m.group(0)[0].upper() + m.group(0)[1:].lower(), text(x))


@fn("TRIM", least=1, most=1, lift=(0,))
def TRIM(x):
    return " ".join(text(x).split(" ")).strip() if False else re.sub(" +", " ", text(x)).strip(" ")


@fn("CLEAN", least=1, most=1, lift=(0,))
def CLEAN(x):
    return "".join(ch for ch in text(x) if ord(ch) >= 32)


@fn("SUBSTITUTE", least=3, most=4, lift=(0, 1, 2, 3))
def SUBSTITUTE(x, old, new, which=MISSING):
    t, o, n = text(x), text(old), text(new)
    if not o:
        return t
    if which is MISSING:
        return t.replace(o, n)
    k = integer(which)
    if k < 1:
        return VALUE
    at = -1
    for _ in range(k):
        at = t.find(o, at + 1)
        if at < 0:
            return t
    return t[:at] + n + t[at + len(o):]


@fn("REPLACE", least=4, most=4, lift=(0, 1, 2, 3))
def REPLACE(x, start, count, new):
    t = text(x)
    s, k = integer(start), integer(count)
    if s < 1 or k < 0:
        return VALUE
    return t[:s - 1] + text(new) + t[s - 1 + k:]


@fn("FIND", least=2, most=3, lift=(0, 1, 2))
def FIND(what, within, start=MISSING):
    s = 1 if start is MISSING else integer(start)
    t = text(within)
    if s < 1 or s > len(t) + 1:
        return VALUE
    at = t.find(text(what), s - 1)
    return VALUE if at < 0 else float(at + 1)


def _wild(pattern: str) -> re.Pattern:
    out = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "~" and i + 1 < len(pattern) and pattern[i + 1] in "*?~":
            out.append(re.escape(pattern[i + 1]))
            i += 2
            continue
        out.append(".*" if ch == "*" else "." if ch == "?" else re.escape(ch))
        i += 1
    return re.compile("".join(out), re.I | re.S)


@fn("SEARCH", least=2, most=3, lift=(0, 1, 2))
def SEARCH(what, within, start=MISSING):
    s = 1 if start is MISSING else integer(start)
    t = text(within)
    if s < 1 or s > len(t) + 1:
        return VALUE
    m = _wild(text(what)).search(t, s - 1)
    return VALUE if m is None else float(m.start() + 1)


@fn("REPT", least=2, most=2, lift=(0, 1))
def REPT(x, n):
    k = integer(n)
    if k < 0:
        return VALUE
    return text(x) * k


@fn("EXACT", least=2, most=2, lift=(0, 1))
def EXACT(a, b):
    return text(a) == text(b)


@fn("CHAR", least=1, most=1, lift=(0,))
def CHAR(x):
    k = integer(x)
    if not 1 <= k <= 255:
        return VALUE
    return bytes([k]).decode("cp1252", errors="replace")


@fn("UNICHAR", least=1, most=1, lift=(0,))
def UNICHAR(x):
    k = integer(x)
    if k < 1:
        return VALUE
    return chr(k)


@fn("CODE", least=1, most=1, lift=(0,))
def CODE(x):
    t = text(x)
    if not t:
        return VALUE
    try:
        return float(t[0].encode("cp1252")[0])
    except UnicodeEncodeError:
        return 63.0


@fn("UNICODE", least=1, most=1, lift=(0,))
def UNICODE(x):
    t = text(x)
    if not t:
        return VALUE
    return float(ord(t[0]))


@fn("VALUE", least=1, most=1, lift=(0,))
def VALUE_(x):
    v = one(x)
    if is_number(v):
        return v
    if isinstance(v, str):
        from .inputs import number_from_text

        got = number_from_text(v.strip())
        return VALUE if got is None else got
    if v is BLANK:
        return 0.0
    return VALUE


@fn("NUMBERVALUE", least=1, most=3)
def NUMBERVALUE(x, decimal=MISSING, group=MISSING):
    t = text(x).replace(" ", "")
    d = "." if decimal is MISSING else text(decimal)[:1]
    g = "," if group is MISSING else text(group)[:1]
    t = t.replace(g, "").replace(d, ".")
    pct = 0
    while t.endswith("%"):
        pct += 1
        t = t[:-1]
    try:
        return float(t or 0) / (100 ** pct)
    except ValueError:
        return VALUE


@fn("TEXT", least=2, most=2, lift=(0, 1))
def TEXT(x, fmt):
    from .numfmt import format_value

    return format_value(one(x), text(fmt)).text


@fn("FIXED", least=1, most=3)
def FIXED(x, digits=MISSING, no_commas=MISSING):
    d = 2 if digits is MISSING else integer(digits)
    v = _round_to(real(x), d, ROUND_HALF_UP)
    s = f"{abs(v):,.{max(d, 0)}f}" if not flag(no_commas) else f"{abs(v):.{max(d, 0)}f}"
    return ("-" if v < 0 else "") + s


@fn("DOLLAR", least=1, most=2)
def DOLLAR(x, digits=MISSING):
    d = 2 if digits is MISSING else integer(digits)
    v = _round_to(real(x), d, ROUND_HALF_UP)
    s = f"${abs(v):,.{max(d, 0)}f}"
    return f"({s})" if v < 0 else s


@fn("TEXTBEFORE", least=2, most=6)
def TEXTBEFORE(x, delim, instance=MISSING, match_mode=MISSING, match_end=MISSING, if_not_found=MISSING):
    t, d = text(x), text(delim)
    k = 1 if instance is MISSING else integer(instance)
    hay = t.lower() if (match_mode is not MISSING and integer(match_mode) == 1) else t
    nd = d.lower() if hay is not t else d
    parts = hay.split(nd)
    if k == 0 or abs(k) >= len(parts) + (0 if k > 0 else 0):
        return NA if if_not_found is MISSING else one(if_not_found)
    if k > 0:
        end = len(nd.join(parts[:k]))
    else:
        end = len(nd.join(parts[:len(parts) + k]))
    return t[:end]


@fn("TEXTAFTER", least=2, most=6)
def TEXTAFTER(x, delim, instance=MISSING, match_mode=MISSING, match_end=MISSING, if_not_found=MISSING):
    t, d = text(x), text(delim)
    k = 1 if instance is MISSING else integer(instance)
    hay = t.lower() if (match_mode is not MISSING and integer(match_mode) == 1) else t
    nd = d.lower() if hay is not t else d
    parts = hay.split(nd)
    if k == 0 or abs(k) >= len(parts):
        return NA if if_not_found is MISSING else one(if_not_found)
    if k > 0:
        start = len(nd.join(parts[:k])) + len(nd)
    else:
        start = len(nd.join(parts[:len(parts) + k])) + len(nd)
    return t[start:]


@fn("TEXTSPLIT", least=2, most=6)
def TEXTSPLIT(x, col_delim, row_delim=MISSING, ignore_empty=MISSING, match_mode=MISSING, pad=MISSING):
    t = text(x)
    cd = text(col_delim)
    rows = t.split(text(row_delim)) if row_delim is not MISSING and text(row_delim) else [t]
    skip = flag(ignore_empty)
    grid_rows = []
    for r in rows:
        cells = r.split(cd) if cd else [r]
        if skip:
            cells = [c for c in cells if c]
        grid_rows.append(cells)
    w = max(len(r) for r in grid_rows) if grid_rows else 0
    filler = NA if pad is MISSING else one(pad)
    return Array(tuple(tuple(r + [filler] * (w - len(r))) for r in grid_rows))


# -- dates and times ----------------------------------------------------------------------
def _date(v) -> _dt.date:
    x = real(v)
    try:
        return date_from_serial(x)
    except (ValueError, OverflowError):
        raise SheetError(NUM)


@fn("DATE", least=3, most=3, lift=(0, 1, 2))
def DATE(y, m, d):
    year, month, day = integer(y), integer(m), integer(d)
    if 0 <= year < 1900:
        year += 1900
    year += (month - 1) // 12
    month = (month - 1) % 12 + 1
    try:
        base = serial_from_date(_dt.date(year, month, 1))
    except ValueError:
        return NUM
    serial = base + day - 1
    if serial < 0:
        return NUM
    return serial


@fn("TIME", least=3, most=3, lift=(0, 1, 2))
def TIME(h, m, s):
    total = integer(h) * 3600 + integer(m) * 60 + integer(s)
    if total < 0:
        return NUM
    return (total % 86400) / 86400.0


@fn("DATEVALUE", least=1, most=1, lift=(0,))
def DATEVALUE(x):
    from .inputs import read_value

    v, fmt = read_value(text(x))
    if isinstance(v, float) and fmt and any(c in fmt for c in "dmy"):
        return float(int(v))
    return VALUE


@fn("TIMEVALUE", least=1, most=1, lift=(0,))
def TIMEVALUE(x):
    from .inputs import read_value

    v, fmt = read_value(text(x))
    if isinstance(v, float) and fmt and "h" in fmt:
        return v - int(v)
    return VALUE


@fn("TODAY", most=0)
def TODAY():
    return serial_from_date(_dt.date.today())


@fn("NOW", most=0)
def NOW():
    return serial_from_datetime(_dt.datetime.now())


@fn("YEAR", least=1, most=1, lift=(0,))
def YEAR(x):
    return float(_date(x).year) if not _leap(x) else 1900.0


@fn("MONTH", least=1, most=1, lift=(0,))
def MONTH(x):
    return float(_date(x).month) if not _leap(x) else 2.0


@fn("DAY", least=1, most=1, lift=(0,))
def DAY(x):
    return float(_date(x).day) if not _leap(x) else 29.0


def _leap(x) -> bool:
    return int(real(x)) == 60


def _secs(x) -> int:
    v = real(x)
    if v < 0:
        raise SheetError(NUM)
    return int(round((v - math.floor(v)) * 86400)) % 86400


@fn("HOUR", least=1, most=1, lift=(0,))
def HOUR(x):
    return float(_secs(x) // 3600)


@fn("MINUTE", least=1, most=1, lift=(0,))
def MINUTE(x):
    return float(_secs(x) // 60 % 60)


@fn("SECOND", least=1, most=1, lift=(0,))
def SECOND(x):
    return float(_secs(x) % 60)


@fn("WEEKDAY", least=1, most=2, lift=(0, 1))
def WEEKDAY(x, kind=MISSING):
    k = 1 if kind is MISSING else integer(kind)
    serial = int(real(x))
    sunday0 = (serial - 1) % 7          # serial 1 (1 Jan 1900) was a Sunday in Excel's count
    if k == 1:
        return float(sunday0 + 1)
    if k in (2, 11):
        return float((sunday0 - 1) % 7 + 1)
    if k == 3:
        return float((sunday0 - 1) % 7)
    if 12 <= k <= 17:
        start = k - 10                  # 12: Tuesday ... 17: Sunday
        return float((sunday0 - start % 7) % 7 + 1)
    return NUM


@fn("WEEKNUM", least=1, most=2)
def WEEKNUM(x, kind=MISSING):
    k = 1 if kind is MISSING else integer(kind)
    d = _date(x)
    if k == 21:
        return float(d.isocalendar()[1])
    start = 6 if k in (1, 17) else 0     # Sunday or Monday
    jan1 = _dt.date(d.year, 1, 1)
    offset = (jan1.weekday() - start) % 7
    return float((d - jan1).days + offset) // 7 + 1


@fn("ISOWEEKNUM", least=1, most=1)
def ISOWEEKNUM(x):
    return float(_date(x).isocalendar()[1])


def _add_months(d: _dt.date, months: int) -> _dt.date:
    total = d.year * 12 + d.month - 1 + months
    y, m = divmod(total, 12)
    import calendar

    last = calendar.monthrange(y, m + 1)[1]
    return _dt.date(y, m + 1, min(d.day, last))


@fn("EDATE", least=2, most=2, lift=(0, 1))
def EDATE(x, months):
    try:
        return serial_from_date(_add_months(_date(x), integer(months)))
    except ValueError:
        return NUM


@fn("EOMONTH", least=2, most=2, lift=(0, 1))
def EOMONTH(x, months):
    import calendar

    try:
        d = _add_months(_date(x).replace(day=1), integer(months))
    except ValueError:
        return NUM
    return serial_from_date(d.replace(day=calendar.monthrange(d.year, d.month)[1]))


@fn("DAYS", least=2, most=2, lift=(0, 1))
def DAYS(end, start):
    return float(int(real(end)) - int(real(start)))


@fn("DAYS360", least=2, most=3)
def DAYS360(start, end, european=MISSING):
    a, b = _date(start), _date(end)
    d1, d2 = a.day, b.day
    if flag(european):
        d1, d2 = min(d1, 30), min(d2, 30)
    else:
        if d1 == 31:
            d1 = 30
        if d2 == 31 and d1 >= 30:
            d2 = 30
    return float((b.year - a.year) * 360 + (b.month - a.month) * 30 + d2 - d1)


@fn("DATEDIF", least=3, most=3)
def DATEDIF(start, end, unit):
    a, b = _date(start), _date(end)
    if a > b:
        return NUM
    u = text(unit).upper()
    if u == "D":
        return float((b - a).days)
    months = (b.year - a.year) * 12 + b.month - a.month - (b.day < a.day)
    if u == "M":
        return float(months)
    if u == "Y":
        return float(months // 12)
    if u == "YM":
        return float(months % 12)
    if u == "MD":
        prev = _add_months(b.replace(day=1), -1 if b.day < a.day else 0)
        import calendar

        anchor = prev.replace(day=min(a.day, calendar.monthrange(prev.year, prev.month)[1]))
        return float((b - anchor).days)
    if u == "YD":
        anchor = a.replace(year=b.year) if (a.month, a.day) <= (b.month, b.day) else a.replace(year=b.year - 1)
        return float((b - anchor).days)
    return NUM


def _holidays(h):
    out = set()
    if h is MISSING:
        return out
    for v in every_value([h]):
        if is_number(v):
            out.add(int(to_float(v)))
    return out


@fn("NETWORKDAYS", "NETWORKDAYS.INTL", least=2, most=4)
def NETWORKDAYS(start, end, *rest):
    a, b = int(real(start)), int(real(end))
    holidays = _holidays(rest[-1]) if rest else set()
    step = 1 if b >= a else -1
    n = 0
    for s in range(a, b + step, step):
        if (s - 1) % 7 not in (0, 6) and s not in holidays:   # not Sunday, not Saturday
            n += 1
    return float(n * step)


@fn("WORKDAY", "WORKDAY.INTL", least=2, most=4)
def WORKDAY(start, days, *rest):
    s, k = int(real(start)), integer(days)
    holidays = _holidays(rest[-1]) if rest else set()
    step = 1 if k >= 0 else -1
    while k:
        s += step
        if (s - 1) % 7 not in (0, 6) and s not in holidays:
            k -= step
    return float(s)


@fn("YEARFRAC", least=2, most=3)
def YEARFRAC(start, end, basis=MISSING):
    a, b = sorted([_date(start), _date(end)])
    k = 0 if basis is MISSING else integer(basis)
    if k == 0:
        return DAYS360(serial_from_date(a), serial_from_date(b)) / 360.0
    days = (b - a).days
    if k == 1:
        years = range(a.year, b.year + 1)
        avg = sum(366 if (y % 4 == 0 and (y % 100 or y % 400 == 0)) else 365 for y in years) / len(years)
        return days / avg
    if k == 2:
        return days / 360.0
    if k == 3:
        return days / 365.0
    if k == 4:
        return DAYS360(serial_from_date(a), serial_from_date(b), True) / 360.0
    return NUM


# -- lookups ----------------------------------------------------------------------------------
def _match_exact(target, values, wildcard=True):
    if isinstance(target, str) and wildcard and any(c in target for c in "*?~"):
        pattern = _wild(target)
        for i, v in enumerate(values):
            if isinstance(v, str) and pattern.fullmatch(v):
                return i
        return None
    for i, v in enumerate(values):
        if v is BLANK:
            continue
        try:
            if _rank_same(target, v) and compare_values(target, v) == 0:
                return i
        except SheetError:
            continue
    return None


def _rank_same(a, b) -> bool:
    def r(x):
        return 2 if isinstance(x, bool) else 1 if isinstance(x, str) else 0
    return r(a) == r(b)


def _match_sorted(target, values, descending=False):
    """Excel's approximate match: the last value not past the target, in a
    list sorted ascending (binary search, as Excel does)."""
    lo, hi = 0, len(values) - 1
    found = None
    while lo <= hi:
        mid = (lo + hi) // 2
        v = values[mid]
        if v is BLANK or not _rank_same(target, v):
            # step past values of another type, as Excel's search does
            j = mid - 1
            while j >= lo and (values[j] is BLANK or not _rank_same(target, values[j])):
                j -= 1
            if j < lo:
                lo = mid + 1
                continue
            mid, v = j, values[j]
        try:
            c = compare_values(v, target)
        except SheetError:
            c = 1
        if descending:
            c = -c
        if c <= 0:
            found = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return found


def _column(v, index: int, vertical=True):
    g = grid(v)
    if vertical:
        return [g.get(i, index) for i in range(g.height)]
    return [g.get(index, j) for j in range(g.width)]


@fn("VLOOKUP", least=3, most=4)
def VLOOKUP(target, table, col, approx=MISSING):
    t = one(target)
    c = integer(col)
    g = grid(table)
    if c < 1:
        return VALUE
    if c > g.width:
        return REF
    keys = [g.get(i, 0) for i in range(g.height)]
    fuzzy = True if approx is MISSING else flag(approx)
    i = _match_sorted(t, keys) if fuzzy else _match_exact(t, keys)
    if i is None:
        return NA
    return g.get(i, c - 1)


@fn("HLOOKUP", least=3, most=4)
def HLOOKUP(target, table, row, approx=MISSING):
    t = one(target)
    r = integer(row)
    g = grid(table)
    if r < 1:
        return VALUE
    if r > g.height:
        return REF
    keys = list(g.rows[0])
    fuzzy = True if approx is MISSING else flag(approx)
    i = _match_sorted(t, keys) if fuzzy else _match_exact(t, keys)
    if i is None:
        return NA
    return g.get(r - 1, i)


@fn("LOOKUP", least=2, most=3)
def LOOKUP(target, look, result=MISSING):
    t = one(target)
    g = grid(look)
    vertical = g.height >= g.width
    keys = _column(g, 0, True) if vertical else _column(g, 0, False)
    i = _match_sorted(t, keys)
    if i is None:
        return NA
    if result is MISSING:
        return g.get(i, g.width - 1) if vertical else g.get(g.height - 1, i)
    r = grid(result)
    vals = list(r.values())
    return vals[i] if i < len(vals) else NA


@fn("MATCH", least=2, most=3)
def MATCH(target, look, kind=MISSING):
    t = one(target)
    g = grid(look)
    if g.height != 1 and g.width != 1:
        return NA
    values = list(g.values())
    k = 1 if kind is MISSING else integer(kind)
    if k == 0:
        i = _match_exact(t, values)
    elif k > 0:
        i = _match_sorted(t, values)
    else:
        i = _match_sorted(t, values, descending=True)
    return NA if i is None else float(i + 1)


@fn("XMATCH", least=2, most=4)
def XMATCH(target, look, mode=MISSING, search=MISSING):
    g = grid(look)
    values = list(g.values())
    i = _xfind(one(target), values, 0 if mode is MISSING else integer(mode),
               1 if search is MISSING else integer(search))
    return NA if i is None else float(i + 1)


def _xfind(t, values, mode, search):
    order = range(len(values)) if search in (1, 2) else range(len(values) - 1, -1, -1)
    if search in (2, -2):
        if mode == 0 or mode == 2:
            return _match_exact(t, values, wildcard=(mode == 2))
        i = _match_sorted(t, values, descending=(search == -2))
        if mode == -1:
            return i
        if i is not None and compare_values(values[i], t) == 0:
            return i
        j = (i + 1) if i is not None else 0
        return j if j < len(values) else None
    if mode in (0, 2):
        pattern = _wild(t) if mode == 2 and isinstance(t, str) else None
        for i in order:
            v = values[i]
            if pattern is not None:
                if isinstance(v, str) and pattern.fullmatch(v):
                    return i
            elif v is not BLANK and _rank_same(t, v) and compare_values(t, v) == 0:
                return i
        return None
    best = None
    for i in order:
        v = values[i]
        if v is BLANK or not _rank_same(t, v):
            continue
        c = compare_values(v, t)
        if c == 0:
            return i
        if mode == -1 and c < 0 and (best is None or compare_values(v, values[best]) > 0):
            best = i
        if mode == 1 and c > 0 and (best is None or compare_values(v, values[best]) < 0):
            best = i
    return best


@fn("XLOOKUP", least=3, most=6)
def XLOOKUP(target, look, ret, missing=MISSING, mode=MISSING, search=MISSING):
    g = grid(look)
    r = grid(ret)
    vertical = g.width == 1
    values = list(g.values())
    i = _xfind(one(target), values, 0 if mode is MISSING else integer(mode),
               1 if search is MISSING else integer(search))
    if i is None:
        return NA if missing is MISSING else deref(missing)
    if vertical:
        if r.height != g.height:
            return VALUE
        row = r.rows[i]
        return row[0] if len(row) == 1 else Array((row,))
    if r.width != g.width:
        return VALUE
    col = tuple((r.get(k, i),) for k in range(r.height))
    return col[0][0] if len(col) == 1 else Array(col)


@fn("INDEX", least=2, most=4)
def INDEX(ref, row, col=MISSING, area=MISSING):
    r = integer(row) if scalar(row) is not BLANK else 0
    c = 1 if col is MISSING else (integer(col) if scalar(col) is not BLANK else 0)
    if isinstance(ref, RefValue):
        h, w = ref.height, ref.width
        if col is MISSING and h == 1 and w > 1:
            r, c = 1, r
        if r < 0 or c < 0 or r > h or c > w:
            return REF
        top = ref.top + r - 1 if r else ref.top
        bottom = top if r else ref.bottom
        left = ref.left + c - 1 if c else ref.left
        right = left if c else ref.right
        return RefValue(ref.sheet, top, left, bottom, right)
    g = grid(ref)
    if col is MISSING and g.height == 1:
        r, c = 1, r
    if r < 0 or c < 0 or r > g.height or c > g.width:
        return REF
    if r and c:
        return g.get(r - 1, c - 1)
    if r:
        return Array((g.rows[r - 1],))
    return Array(tuple((g.get(i, c - 1),) for i in range(g.height)))


@fn("OFFSET", least=3, most=5)
def OFFSET(ref, rows, cols, height=MISSING, width=MISSING):
    if not isinstance(ref, RefValue):
        return VALUE
    top = ref.top + integer(rows)
    left = ref.left + integer(cols)
    h = ref.height if height is MISSING else integer(height)
    w = ref.width if width is MISSING else integer(width)
    if h < 1 or w < 1:
        return REF
    if top < 0 or left < 0 or top + h > MAX_ROWS or left + w > MAX_COLS:
        return REF
    return RefValue(ref.sheet, top, left, top + h - 1, left + w - 1)


@fn("INDIRECT", least=1, most=2, lazy=True)
def INDIRECT(ctx, args):
    t = text(ev(args[0], ctx)).strip()
    got = parse_range(t)
    if got is None:
        dn = ctx.wb.find_name(t, ctx.sheet)
        if dn is not None:
            return ev(F.Name(t), ctx)
        return REF
    sheet = ctx.sheet if got.sheet is None else ctx.wb.sheet(got.sheet)
    if sheet is None:
        return REF
    if isinstance(got, CellRef):
        return RefValue(sheet, got.row, got.col, got.row, got.col)
    return RefValue(sheet, got.top, got.left, got.bottom, got.right)


@fn("ROW", most=1, lazy=True)
def ROW(ctx, args):
    if not args or type(args[0]) is F.Missing:
        return float(ctx.row + 1)
    v = ev(args[0], ctx)
    if not isinstance(v, RefValue):
        return VALUE
    if v.height == 1:
        return float(v.top + 1)
    return Array(tuple((float(r + 1),) for r in range(v.top, v.bottom + 1)))


@fn("COLUMN", most=1, lazy=True)
def COLUMN(ctx, args):
    if not args or type(args[0]) is F.Missing:
        return float(ctx.col + 1)
    v = ev(args[0], ctx)
    if not isinstance(v, RefValue):
        return VALUE
    if v.width == 1:
        return float(v.left + 1)
    return Array((tuple(float(c + 1) for c in range(v.left, v.right + 1)),))


@fn("ROWS", least=1, most=1)
def ROWS(v):
    if isinstance(v, RefValue):
        return float(v.height)
    return float(grid(v).height)


@fn("COLUMNS", least=1, most=1)
def COLUMNS(v):
    if isinstance(v, RefValue):
        return float(v.width)
    return float(grid(v).width)


@fn("ADDRESS", least=2, most=5)
def ADDRESS(row, col, kind=MISSING, a1=MISSING, sheet=MISSING):
    r, c = integer(row), integer(col)
    k = 1 if kind is MISSING else integer(kind)
    if r < 1 or c < 1 or k not in (1, 2, 3, 4):
        return VALUE
    ref = CellRef(r - 1, c - 1, row_abs=k in (1, 2), col_abs=k in (1, 3))
    if a1 is not MISSING and not flag(a1, True):
        rr = f"R{r}" if k in (1, 2) else f"R[{r}]"
        cc = f"C{c}" if k in (1, 3) else f"C[{c}]"
        out = rr + cc
    else:
        out = ref.a1(False)
    if sheet is not MISSING:
        out = quote_sheet(text(sheet)) + "!" + out
    return out


@fn("CHOOSECOLS", least=2)
def CHOOSECOLS(a, *cols):
    g = grid(a)
    picks = []
    for c in cols:
        k = integer(c)
        k = k if k > 0 else g.width + k + 1
        if not 1 <= k <= g.width:
            return VALUE
        picks.append(k - 1)
    return Array(tuple(tuple(row[k] for k in picks) for row in g.rows))


@fn("CHOOSEROWS", least=2)
def CHOOSEROWS(a, *rows):
    g = grid(a)
    picks = []
    for r in rows:
        k = integer(r)
        k = k if k > 0 else g.height + k + 1
        if not 1 <= k <= g.height:
            return VALUE
        picks.append(g.rows[k - 1])
    return Array(tuple(picks))


# -- dynamic arrays ---------------------------------------------------------------------------
@fn("SEQUENCE", least=1, most=4)
def SEQUENCE(rows, cols=MISSING, start=MISSING, step=MISSING):
    r = integer(rows)
    c = 1 if cols is MISSING else integer(cols)
    s = 1.0 if start is MISSING else num(start)
    d = 1.0 if step is MISSING else num(step)
    if r < 1 or c < 1:
        return CALC
    out = []
    for i in range(r):
        out.append(tuple(add(s, mul(d, float(i * c + j))) for j in range(c)))
    return Array(tuple(out))


@fn("FILTER", least=2, most=3)
def FILTER(a, include, empty=MISSING):
    g = grid(a)
    keep = grid(include)
    if keep.width == 1 and keep.height == g.height:
        rows = [g.rows[i] for i in range(g.height) if _keep(keep.get(i, 0))]
        if not rows:
            return CALC if empty is MISSING else deref(empty)
        return Array(tuple(rows))
    if keep.height == 1 and keep.width == g.width:
        cols = [j for j in range(g.width) if _keep(keep.get(0, j))]
        if not cols:
            return CALC if empty is MISSING else deref(empty)
        return Array(tuple(tuple(row[j] for j in cols) for row in g.rows))
    return VALUE


def _keep(v) -> bool:
    if isinstance(v, ErrorValue):
        raise SheetError(v)
    return to_bool(v) if v is not BLANK else False


def _sort_key(v):
    from functools import cmp_to_key

    return cmp_to_key(compare_values)(v)


@fn("SORT", least=1, most=4)
def SORT(a, index=MISSING, order=MISSING, by_col=MISSING):
    g = grid(a)
    k = 1 if index is MISSING else integer(index)
    descending = (1 if order is MISSING else integer(order)) == -1
    if flag(by_col):
        cols = list(zip(*g.rows))
        cols.sort(key=lambda col: _sort_key(col[k - 1]), reverse=descending)
        return Array(tuple(zip(*cols)))
    if k < 1 or k > g.width:
        return VALUE
    rows = sorted(g.rows, key=lambda row: _sort_key(row[k - 1]), reverse=descending)
    return Array(tuple(rows))


@fn("SORTBY", least=2)
def SORTBY(a, *pairs):
    g = grid(a)
    keys = []
    for i in range(0, len(pairs), 2):
        by = list(grid(pairs[i]).values())
        desc = len(pairs) > i + 1 and integer(pairs[i + 1]) == -1
        if len(by) != g.height:
            return VALUE
        keys.append((by, desc))
    order = list(range(g.height))
    for by, desc in reversed(keys):
        order.sort(key=lambda i: _sort_key(by[i]), reverse=desc)
    return Array(tuple(g.rows[i] for i in order))


@fn("UNIQUE", least=1, most=3)
def UNIQUE(a, by_col=MISSING, exactly_once=MISSING):
    g = grid(a)
    rows = list(zip(*g.rows)) if flag(by_col) else list(g.rows)
    def key(row):
        return tuple((x.lower() if isinstance(x, str) else x) for x in row)
    counts = {}
    for row in rows:
        counts[key(row)] = counts.get(key(row), 0) + 1
    seen = set()
    out = []
    for row in rows:
        k = key(row)
        if k in seen:
            continue
        if flag(exactly_once) and counts[k] != 1:
            continue
        seen.add(k)
        out.append(row)
    if not out:
        return CALC
    if flag(by_col):
        return Array(tuple(zip(*out)))
    return Array(tuple(out))


@fn("TAKE", least=2, most=3)
def TAKE(a, rows, cols=MISSING):
    g = grid(a)
    r = integer(rows) if scalar(rows) is not BLANK else g.height
    c = g.width if cols is MISSING else integer(cols)
    rs = g.rows[:r] if r >= 0 else g.rows[r:]
    out = tuple(row[:c] if c >= 0 else row[c:] for row in rs)
    return Array(out) if out and out[0] else CALC


@fn("DROP", least=2, most=3)
def DROP(a, rows, cols=MISSING):
    g = grid(a)
    r = integer(rows) if scalar(rows) is not BLANK else 0
    c = 0 if cols is MISSING else integer(cols)
    rs = g.rows[r:] if r >= 0 else g.rows[:r]
    out = tuple(row[c:] if c >= 0 else row[:c] for row in rs)
    return Array(out) if out and out[0] else CALC


@fn("VSTACK", least=1)
def VSTACK(*arrays):
    gs = [grid(a) for a in arrays]
    w = max(g.width for g in gs)
    rows = []
    for g in gs:
        for row in g.rows:
            rows.append(tuple(row) + (NA,) * (w - len(row)))
    return Array(tuple(rows))


@fn("HSTACK", least=1)
def HSTACK(*arrays):
    gs = [grid(a) for a in arrays]
    h = max(g.height for g in gs)
    rows = []
    for i in range(h):
        row = []
        for g in gs:
            row.extend(g.rows[i] if i < g.height else (NA,) * g.width)
        rows.append(tuple(row))
    return Array(tuple(rows))


@fn("TOCOL", least=1, most=3)
def TOCOL(a, ignore=MISSING, by_col=MISSING):
    g = grid(a)
    vals = [x for col in zip(*g.rows) for x in col] if flag(by_col) else list(g.values())
    k = 0 if ignore is MISSING else integer(ignore)
    if k in (1, 3):
        vals = [v for v in vals if v is not BLANK]
    if k in (2, 3):
        vals = [v for v in vals if not isinstance(v, ErrorValue)]
    return Array(tuple((v,) for v in vals))


@fn("TOROW", least=1, most=3)
def TOROW(a, ignore=MISSING, by_col=MISSING):
    col = TOCOL(a, ignore, by_col)
    return Array((tuple(r[0] for r in col.rows),))


# -- counting and summing by criteria -----------------------------------------------------------
def criterion(c) -> Callable:
    """A COUNTIF criterion as a test: 5, ">5", "<>x", "a*", ">=2 kN", ""."""
    c = scalar(c)
    if isinstance(c, ErrorValue):
        return lambda v: v == c
    if not isinstance(c, str):
        if c is BLANK:
            c = 0.0
        return lambda v, c=c: v is not BLANK and _rank_same(c, v) and compare_values(v, c) == 0
    m = re.match(r"^(<=|>=|<>|=|<|>)?(.*)$", c, re.S)
    op, rest = m.group(1) or "", m.group(2)
    from .inputs import number_from_text

    target = number_from_text(rest) if rest.strip() else None
    if target is None and rest.upper() in ("TRUE", "FALSE"):
        target = rest.upper() == "TRUE"
    if target is not None:
        def test(v, op=op or "=", target=target):
            if v is BLANK or not _rank_same(target, v):
                if isinstance(v, str) and op in ("=", "<>") and not isinstance(target, bool):
                    got = number_from_text(v)
                    if got is not None:
                        v = got
                    else:
                        return op == "<>"
                else:
                    return op == "<>"
            try:
                cmp = compare_values(v, target)
            except SheetError:
                return False
            return {"=": cmp == 0, "<>": cmp != 0, "<": cmp < 0, ">": cmp > 0,
                    "<=": cmp <= 0, ">=": cmp >= 0}[op]
        return test
    if op in ("", "="):
        if rest == "":
            return (lambda v: v is BLANK or v == "") if op == "" else (lambda v: v is BLANK)
        pattern = _wild(rest)
        return lambda v: isinstance(v, str) and pattern.fullmatch(v) is not None
    if op == "<>":
        if rest == "":
            return lambda v: v is not BLANK and v != ""
        pattern = _wild(rest)
        return lambda v: not (isinstance(v, str) and pattern.fullmatch(v) is not None)
    def text_test(v, op=op, rest=rest):
        if not isinstance(v, str):
            return False
        cmp = compare_values(v, rest)
        return {"<": cmp < 0, ">": cmp > 0, "<=": cmp <= 0, ">=": cmp >= 0}[op]
    return text_test


def _positions(ref, test, also_blank: bool):
    """Offsets (i, j) in ref whose value passes the test."""
    if isinstance(ref, RefValue):
        if also_blank:
            b = ref.bounded() if ref.height * ref.width > 200_000 else ref
            for i in range(b.height):
                for j in range(b.width):
                    if test(b.value_at(i, j)):
                        yield i, j
            if (b.height, b.width) != (ref.height, ref.width) and test(BLANK):
                # the rest of a whole column is blank: Excel counts it too
                yield from ()
        else:
            for row, col, v in ref.filled():
                if test(v):
                    yield row - ref.top, col - ref.left
        return
    g = grid(ref)
    for i in range(g.height):
        for j in range(g.width):
            if test(g.get(i, j)):
                yield i, j


def _ifs(pairs):
    """Offsets where every (range, criterion) pair matches."""
    tests = [(r, criterion(c)) for r, c in pairs]
    first, test = tests[0]
    blank = test(BLANK)
    shape = (first.height, first.width) if isinstance(first, RefValue) else (grid(first).height, grid(first).width)
    for r, _t in tests[1:]:
        s = (r.height, r.width) if isinstance(r, RefValue) else (grid(r).height, grid(r).width)
        if s != shape:
            raise SheetError(VALUE)
    for i, j in _positions(first, test, blank):
        ok = True
        for r, t in tests[1:]:
            v = r.value_at(i, j) if isinstance(r, RefValue) else grid(r).get(i, j)
            if not t(v):
                ok = False
                break
        if ok:
            yield i, j


def _at(ref, i, j):
    if isinstance(ref, RefValue):
        if i >= MAX_ROWS - ref.top or j >= MAX_COLS - ref.left:
            return BLANK
        return ref.sheet.workbook.value(ref.sheet, ref.top + i, ref.left + j)
    g = grid(ref)
    return g.get(i, j) if i < g.height and j < g.width else BLANK


@fn("COUNTIF", least=2, most=2)
def COUNTIF(ref, crit):
    test = criterion(crit)
    if test(BLANK) and isinstance(ref, RefValue):
        filled = sum(1 for _r, _c, v in ref.filled() if not test(v))
        return float(ref.height * ref.width - filled)
    return float(sum(1 for _ in _positions(ref, test, False)))


@fn("COUNTIFS", least=2)
def COUNTIFS(*args):
    if len(args) % 2:
        return VALUE
    pairs = [(args[i], args[i + 1]) for i in range(0, len(args), 2)]
    return float(sum(1 for _ in _ifs(pairs)))


def _summed(ref, offsets):
    total = None
    for i, j in offsets:
        v = _at(ref, i, j)
        if isinstance(v, ErrorValue):
            raise SheetError(v)
        if is_number(v):
            total = v if total is None else add(total, v)
    return 0.0 if total is None else total


@fn("SUMIF", least=2, most=3)
def SUMIF(ref, crit, sum_range=MISSING):
    target = ref if sum_range is MISSING else sum_range
    return _summed(target, _positions(ref, criterion(crit), criterion(crit)(BLANK)))


@fn("SUMIFS", least=3)
def SUMIFS(sum_range, *args):
    if len(args) % 2:
        return VALUE
    pairs = [(args[i], args[i + 1]) for i in range(0, len(args), 2)]
    return _summed(sum_range, _ifs(pairs))


def _averaged(ref, offsets):
    vals = []
    for i, j in offsets:
        v = _at(ref, i, j)
        if isinstance(v, ErrorValue):
            raise SheetError(v)
        if is_number(v):
            vals.append(v)
    if not vals:
        return DIV0
    si, dims, unit = unify(vals)
    return rebuild(math.fsum(si) / len(si), dims, unit)


@fn("AVERAGEIF", least=2, most=3)
def AVERAGEIF(ref, crit, avg_range=MISSING):
    target = ref if avg_range is MISSING else avg_range
    return _averaged(target, _positions(ref, criterion(crit), False))


@fn("AVERAGEIFS", least=3)
def AVERAGEIFS(avg_range, *args):
    pairs = [(args[i], args[i + 1]) for i in range(0, len(args), 2)]
    return _averaged(avg_range, _ifs(pairs))


def _extreme(target, offsets, pick):
    vals = []
    for i, j in offsets:
        v = _at(target, i, j)
        if isinstance(v, ErrorValue):
            raise SheetError(v)
        if is_number(v):
            vals.append(v)
    if not vals:
        return 0.0
    si, dims, unit = unify(vals)
    return rebuild(pick(si), dims, unit)


@fn("MAXIFS", least=3)
def MAXIFS(target, *args):
    pairs = [(args[i], args[i + 1]) for i in range(0, len(args), 2)]
    return _extreme(target, _ifs(pairs), max)


@fn("MINIFS", least=3)
def MINIFS(target, *args):
    pairs = [(args[i], args[i + 1]) for i in range(0, len(args), 2)]
    return _extreme(target, _ifs(pairs), min)


# -- statistics with two series ---------------------------------------------------------------------
def _pairs(ys, xs):
    Y, X = list(grid(ys).values()), list(grid(xs).values())
    if len(X) != len(Y):
        raise SheetError(NA)
    px, py = [], []
    for x, y in zip(X, Y):
        if is_number(x) and is_number(y):
            px.append(x)
            py.append(y)
    sx, dx, ux = unify(px) if px else ([], NODIM, None)
    sy, dy, uy = unify(py) if py else ([], NODIM, None)
    return sx, sy, (dx, ux), (dy, uy)


def _fit(ys, xs):
    sx, sy, xu, yu = _pairs(ys, xs)
    n = len(sx)
    if n < 2:
        raise SheetError(DIV0)
    mx, my = math.fsum(sx) / n, math.fsum(sy) / n
    sxx = math.fsum((x - mx) ** 2 for x in sx)
    if sxx == 0:
        raise SheetError(DIV0)
    sxy = math.fsum((x - mx) * (y - my) for x, y in zip(sx, sy))
    slope = sxy / sxx
    return slope, my - slope * mx, sx, sy, xu, yu


@fn("SLOPE", least=2, most=2)
def SLOPE(ys, xs):
    slope, _b, _sx, _sy, (dx, _ux), (dy, _uy) = _fit(ys, xs)
    from calcforge.calc.engine.units import dims_sub

    return quantity(slope, dims_sub(dy, dx))


@fn("INTERCEPT", least=2, most=2)
def INTERCEPT(ys, xs):
    _slope, b, _sx, _sy, _xu, (dy, uy) = _fit(ys, xs)
    return rebuild(b, dy, uy)


@fn("FORECAST", "FORECAST.LINEAR", least=3, most=3)
def FORECAST(x, ys, xs):
    slope, b, _sx, _sy, (dx, _ux), (dy, uy) = _fit(ys, xs)
    v = num(x)
    vd = v.dims if isinstance(v, Qty) else NODIM
    if vd != dx:
        return UNITS_ERR
    return rebuild(b + slope * magnitude(v), dy, uy)


@fn("TREND", least=1, most=3)
def TREND(ys, xs=MISSING, new_xs=MISSING):
    if xs is MISSING:
        xs = Array(tuple((float(i + 1),) for i in range(grid(ys).height)))
    slope, b, _sx, _sy, _xu, (dy, uy) = _fit(ys, xs)
    targets = grid(xs if new_xs is MISSING else new_xs)
    return Array(tuple(tuple(rebuild(b + slope * magnitude(to_number(v)), dy, uy) for v in row)
                       for row in targets.rows))


@fn("CORREL", "PEARSON", least=2, most=2)
def CORREL(a, b):
    sx, sy, _xu, _yu = _pairs(a, b)
    n = len(sx)
    if n < 2:
        return DIV0
    mx, my = math.fsum(sx) / n, math.fsum(sy) / n
    sxx = math.fsum((x - mx) ** 2 for x in sx)
    syy = math.fsum((y - my) ** 2 for y in sy)
    if sxx == 0 or syy == 0:
        return DIV0
    return math.fsum((x - mx) * (y - my) for x, y in zip(sx, sy)) / math.sqrt(sxx * syy)


@fn("RSQ", least=2, most=2)
def RSQ(ys, xs):
    r = CORREL(ys, xs)
    return r if isinstance(r, ErrorValue) else r * r


@fn("COVARIANCE.P", "COVAR", least=2, most=2)
def COVAR(a, b):
    sx, sy, _xu, _yu = _pairs(a, b)
    n = len(sx)
    if not n:
        return DIV0
    mx, my = math.fsum(sx) / n, math.fsum(sy) / n
    return math.fsum((x - mx) * (y - my) for x, y in zip(sx, sy)) / n


@fn("COVARIANCE.S", least=2, most=2)
def COVARIANCE_S(a, b):
    sx, sy, _xu, _yu = _pairs(a, b)
    n = len(sx)
    if n < 2:
        return DIV0
    mx, my = math.fsum(sx) / n, math.fsum(sy) / n
    return math.fsum((x - mx) * (y - my) for x, y in zip(sx, sy)) / (n - 1)


@fn("GEOMEAN", least=1)
def GEOMEAN(*args):
    si = [to_float(n) for n in numbers(args)]
    if not si or any(x <= 0 for x in si):
        return NUM
    return math.exp(math.fsum(math.log(x) for x in si) / len(si))


@fn("HARMEAN", least=1)
def HARMEAN(*args):
    si = [to_float(n) for n in numbers(args)]
    if not si or any(x <= 0 for x in si):
        return NUM
    return len(si) / math.fsum(1 / x for x in si)


@fn("AVEDEV", least=1)
def AVEDEV(*args):
    si, dims, unit = unify(numbers(args))
    if not si:
        return NUM
    m = math.fsum(si) / len(si)
    return rebuild(math.fsum(abs(x - m) for x in si) / len(si), dims, unit)


@fn("DEVSQ", least=1)
def DEVSQ(*args):
    si, dims, unit = unify(numbers(args))
    if not si:
        return NUM
    m = math.fsum(si) / len(si)
    return rebuild(math.fsum((x - m) ** 2 for x in si), dims, unit, 2.0)


@fn("NORM.DIST", "NORMDIST", least=4, most=4)
def NORM_DIST(x, mean, sd, cumulative):
    v, m, s = real(x), real(mean), real(sd)
    if s <= 0:
        return NUM
    z = (v - m) / s
    if flag(cumulative):
        return 0.5 * math.erfc(-z / math.sqrt(2))
    return math.exp(-z * z / 2) / (s * math.sqrt(2 * math.pi))


@fn("NORM.S.DIST", least=2, most=2)
def NORM_S_DIST(z, cumulative):
    return NORM_DIST(z, 0.0, 1.0, cumulative)


@fn("NORM.INV", "NORMINV", least=3, most=3)
def NORM_INV(p, mean, sd):
    q, m, s = real(p), real(mean), real(sd)
    if not 0 < q < 1 or s <= 0:
        return NUM
    return m + s * statistics.NormalDist().inv_cdf(q)


@fn("NORM.S.INV", "NORMSINV", least=1, most=1)
def NORM_S_INV(p):
    return NORM_INV(p, 0.0, 1.0)


@fn("STANDARDIZE", least=3, most=3)
def STANDARDIZE(x, mean, sd):
    s = real(sd)
    if s <= 0:
        return NUM
    return (real(x) - real(mean)) / s


# -- money ------------------------------------------------------------------------------------
@fn("PMT", least=3, most=5)
def PMT(rate, nper, pv, fv=MISSING, kind=MISSING):
    r, n, p = real(rate), real(nper), real(pv)
    f = 0.0 if fv is MISSING else real(fv)
    t = 0 if kind is MISSING else integer(kind)
    if n == 0:
        return NUM
    if r == 0:
        return -(p + f) / n
    g = (1 + r) ** n
    return -(r * (p * g + f)) / ((1 + r * t) * (g - 1))


@fn("FV", least=3, most=5)
def FV(rate, nper, pmt, pv=MISSING, kind=MISSING):
    r, n, m = real(rate), real(nper), real(pmt)
    p = 0.0 if pv is MISSING else real(pv)
    t = 0 if kind is MISSING else integer(kind)
    if r == 0:
        return -(p + m * n)
    g = (1 + r) ** n
    return -(p * g + m * (1 + r * t) * (g - 1) / r)


@fn("PV", least=3, most=5)
def PV(rate, nper, pmt, fv=MISSING, kind=MISSING):
    r, n, m = real(rate), real(nper), real(pmt)
    f = 0.0 if fv is MISSING else real(fv)
    t = 0 if kind is MISSING else integer(kind)
    if r == 0:
        return -(f + m * n)
    g = (1 + r) ** n
    return -(f + m * (1 + r * t) * (g - 1) / r) / g


@fn("NPER", least=3, most=5)
def NPER(rate, pmt, pv, fv=MISSING, kind=MISSING):
    r, m, p = real(rate), real(pmt), real(pv)
    f = 0.0 if fv is MISSING else real(fv)
    t = 0 if kind is MISSING else integer(kind)
    if r == 0:
        return -(p + f) / m if m else NUM
    a = m * (1 + r * t) / r
    try:
        return math.log((a - f) / (a + p)) / math.log(1 + r)
    except (ValueError, ZeroDivisionError):
        return NUM


@fn("NPV", least=2)
def NPV(rate, *values):
    r = real(rate)
    total = 0.0
    for i, v in enumerate(numbers(values)):
        total += to_float(v) / (1 + r) ** (i + 1)
    return total


@fn("IRR", least=1, most=2)
def IRR(values, guess=MISSING):
    flows = [to_float(v) for v in numbers([values])]
    r = 0.1 if guess is MISSING else real(guess)
    for _ in range(100):
        f = sum(c / (1 + r) ** i for i, c in enumerate(flows))
        d = sum(-i * c / (1 + r) ** (i + 1) for i, c in enumerate(flows))
        if d == 0:
            return NUM
        step = f / d
        r -= step
        if abs(step) < 1e-12:
            return r
    return NUM


@fn("RATE", least=3, most=6)
def RATE(nper, pmt, pv, fv=MISSING, kind=MISSING, guess=MISSING):
    n, m, p = real(nper), real(pmt), real(pv)
    f = 0.0 if fv is MISSING else real(fv)
    t = 0 if kind is MISSING else integer(kind)
    r = 0.1 if guess is MISSING else real(guess)

    def g(rate):
        if abs(rate) < 1e-12:
            return p + m * n + f
        q = (1 + rate) ** n
        return p * q + m * (1 + rate * t) * (q - 1) / rate + f

    for _ in range(100):
        h = 1e-7
        d = (g(r + h) - g(r - h)) / (2 * h)
        if d == 0:
            return NUM
        step = g(r) / d
        r -= step
        if abs(step) < 1e-12:
            return r
    return NUM


# -- units (CalcForge's own) ----------------------------------------------------------------------
def _unit_text(v) -> str:
    t = text(v).strip()
    if t.startswith("'"):
        t = t[1:]
    try:
        unit_parts(t)
    except UnitTextError:
        raise SheetError(NAME)
    return t


@fn("VALUEIN", least=2, most=2, lift=(0,))
def VALUEIN(x, unit):
    """x as a plain number in a unit: VALUEIN(5000 N, "kN") = 5."""
    v = num(x)
    u = _unit_text(unit)
    factor, dims, offset = unit_parts(u)
    vd = v.dims if isinstance(v, Qty) else NODIM
    if tuple(vd) != tuple(dims):
        return UNITS_ERR
    return (magnitude(v) - offset) / factor


@fn("CONVERT", least=2, most=3, lift=(0,))
def CONVERT(x, a, b=MISSING):
    """CONVERT(x, "kN") shows x in kN; CONVERT(5, "kN", "lbf") is Excel's
    form: a plain number from one unit to another."""
    if b is MISSING:
        v = num(x)
        u = _unit_text(a)
        factor, dims, _offset = unit_parts(u)
        vd = v.dims if isinstance(v, Qty) else NODIM
        if tuple(vd) != tuple(dims):
            return UNITS_ERR
        return Qty(magnitude(v), tuple(dims), u)
    v = real(x)
    ua, ub = _unit_text(a), _unit_text(b)
    fa, da, oa = unit_parts(ua)
    fb, db, ob = unit_parts(ub)
    if tuple(da) != tuple(db):
        return NA
    return (v * fa + oa - ob) / fb


@fn("UNITOF", least=1, most=1, lift=(0,))
def UNITOF(x):
    v = num(x)
    if isinstance(v, Qty):
        return v.unit or default_unit(v.dims)
    return ""


@fn("STRIPUNIT", least=1, most=1, lift=(0,))
def STRIPUNIT(x):
    v = num(x)
    return v.shown() if isinstance(v, Qty) else v


@fn("INTERP", least=3, most=3)
def INTERP(x, xs, ys):
    """Straight-line interpolation: INTERP(x, A2:A10, B2:B10), the table
    sorted by its first column; outside the table is #N/A."""
    v = num(x)
    X = [to_number(a) for a in grid(xs).values() if is_number(a)]
    Y = [to_number(b) for b in grid(ys).values() if is_number(b)]
    if len(X) != len(Y) or len(X) < 1:
        return NA
    sx, dx, _ux = unify(X)
    sy, dy, uy = unify(Y)
    vd = v.dims if isinstance(v, Qty) else NODIM
    if tuple(vd) != tuple(dx):
        return UNITS_ERR
    t = magnitude(v)
    pairs = sorted(zip(sx, sy))
    for (x0, y0), (x1, y1) in zip(pairs, pairs[1:]):
        if x0 <= t <= x1:
            if x1 == x0:
                return rebuild(y0, dy, uy)
            return rebuild(y0 + (y1 - y0) * (t - x0) / (x1 - x0), dy, uy)
    if len(pairs) == 1 and pairs[0][0] == t:
        return rebuild(pairs[0][1], dy, uy)
    return NA


def names() -> list[str]:
    """Every function's name, for autocomplete."""
    return sorted(FUNCTIONS)
