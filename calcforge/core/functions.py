"""Function and constant library exposed to math regions and spreadsheet cells.

Every function here is unit-aware: it either propagates :class:`pint.Quantity`
values untouched, or strips/reapplies units where the mathematics demands a
dimensionless argument (trigonometry, logarithms, ...).
"""
from __future__ import annotations

import math
from typing import Any, Callable, Iterable

import numpy as np

from .units import Q_, Quantity, as_float, convert, format_unit, ureg


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _flatten(args: Iterable[Any]) -> list:
    out: list = []
    for a in args:
        if isinstance(a, Quantity) and isinstance(a.magnitude, np.ndarray):
            out.extend(Q_(v, a.units) for v in a.magnitude.ravel())
        elif isinstance(a, np.ndarray):
            out.extend(a.ravel().tolist())
        elif isinstance(a, (list, tuple, set)):
            out.extend(_flatten(a))
        elif a is None or a == "":
            continue
        else:
            out.append(a)
    return out


def _angle(value: Any) -> float:
    """Interpret *value* as an angle in radians (accepting degree quantities)."""
    if isinstance(value, Quantity):
        try:
            return float(value.to("radian").magnitude)
        except Exception:
            return as_float(value)
    return float(value)


def _wrap1(fn: Callable[[float], float]) -> Callable[[Any], Any]:
    def inner(x):
        if isinstance(x, (list, tuple, np.ndarray)):
            return np.array([inner(v) for v in np.asarray(x).ravel()]).reshape(
                np.asarray(x).shape)
        return fn(as_float(x))
    return inner


def _trig(fn: Callable[[float], float]) -> Callable[[Any], Any]:
    def inner(x):
        return fn(_angle(x))
    return inner


def _inverse_trig(fn: Callable[[float], float]) -> Callable[[Any], Any]:
    """Inverse trig returns a proper angle quantity so units keep flowing."""
    def inner(x):
        return Q_(fn(as_float(x)), "radian")
    return inner


# ---------------------------------------------------------------------------
# elementary maths
# ---------------------------------------------------------------------------

def sqrt(x):
    if isinstance(x, Quantity):
        return x ** 0.5
    if isinstance(x, (list, tuple, np.ndarray)):
        return np.sqrt(np.asarray(x, dtype=float))
    x = as_float(x)
    if x < 0:
        return complex(0, math.sqrt(-x))
    return math.sqrt(x)


def root(x, n=2):
    """n-th root, unit aware."""
    n = as_float(n)
    if isinstance(x, Quantity):
        return x ** (1.0 / n)
    return as_float(x) ** (1.0 / n)


def exp(x):
    return math.exp(as_float(x))


def ln(x):
    return math.log(as_float(x))


def log(x, base=10):
    return math.log(as_float(x), as_float(base))


def log2(x):
    return math.log2(as_float(x))


def abs_(x):
    if isinstance(x, Quantity):
        return Q_(abs(x.magnitude), x.units)
    if isinstance(x, np.ndarray):
        return np.abs(x)
    return abs(x)


def sign(x):
    v = x.magnitude if isinstance(x, Quantity) else x
    return 1 if v > 0 else (-1 if v < 0 else 0)


def _round_like(x, fn, digits=0):
    digits = int(as_float(digits))
    factor = 10 ** digits
    if isinstance(x, Quantity):
        return Q_(fn(x.magnitude * factor) / factor, x.units)
    return fn(as_float(x) * factor) / factor


def round_(x, digits=0):
    return _round_like(x, lambda v: math.floor(v + 0.5) if v >= 0 else math.ceil(v - 0.5), digits)


def floor(x, digits=0):
    return _round_like(x, math.floor, digits)


def ceil(x, digits=0):
    return _round_like(x, math.ceil, digits)


def trunc(x, digits=0):
    return _round_like(x, math.trunc, digits)


def roundto(x, step):
    """Round *x* to the nearest multiple of *step* (both may carry units)."""
    if isinstance(x, Quantity) or isinstance(step, Quantity):
        ratio = (x / step).to("dimensionless").magnitude
    else:
        ratio = as_float(x) / as_float(step)
    return step * math.floor(ratio + 0.5)


def ceilto(x, step):
    if isinstance(x, Quantity) or isinstance(step, Quantity):
        ratio = (x / step).to("dimensionless").magnitude
    else:
        ratio = as_float(x) / as_float(step)
    return step * math.ceil(ratio - 1e-12)


def floorto(x, step):
    if isinstance(x, Quantity) or isinstance(step, Quantity):
        ratio = (x / step).to("dimensionless").magnitude
    else:
        ratio = as_float(x) / as_float(step)
    return step * math.floor(ratio + 1e-12)


def mod(a, b):
    if isinstance(a, Quantity) or isinstance(b, Quantity):
        n = math.floor((a / b).to("dimensionless").magnitude)
        return a - n * b
    return as_float(a) % as_float(b)


def clamp(x, lo, hi):
    return min_(max_(x, lo), hi)


def factorial(n):
    return math.factorial(int(as_float(n)))


def gcd(a, b):
    return math.gcd(int(as_float(a)), int(as_float(b)))


def lcm(a, b):
    return math.lcm(int(as_float(a)), int(as_float(b)))


def hypot(*args):
    total = None
    for a in _flatten(args):
        term = a * a
        total = term if total is None else total + term
    return sqrt(total)


# ---------------------------------------------------------------------------
# aggregation / statistics
# ---------------------------------------------------------------------------

def sum_(*args):
    values = _flatten(args)
    if not values:
        return 0
    total = values[0]
    for v in values[1:]:
        total = total + v
    return total


def product(*args):
    values = _flatten(args)
    if not values:
        return 0
    total = values[0]
    for v in values[1:]:
        total = total * v
    return total


def mean(*args):
    values = _flatten(args)
    if not values:
        return 0
    return sum_(values) / len(values)


def median(*args):
    values = sorted(_flatten(args), key=lambda v: v.magnitude if isinstance(v, Quantity) else v)
    if not values:
        return 0
    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2


def stdev(*args):
    values = _flatten(args)
    if len(values) < 2:
        return 0
    m = mean(values)
    var = sum_([(v - m) ** 2 for v in values]) / (len(values) - 1)
    return sqrt(var)


def pstdev(*args):
    values = _flatten(args)
    if not values:
        return 0
    m = mean(values)
    var = sum_([(v - m) ** 2 for v in values]) / len(values)
    return sqrt(var)


def variance(*args):
    s = stdev(*args)
    return s * s


def count(*args):
    return len(_flatten(args))


def _cmp_key(v):
    return v.magnitude if isinstance(v, Quantity) else v


def max_(*args):
    values = _flatten(args)
    if not values:
        raise ValueError("max() needs at least one value")
    return max(values, key=_cmp_key)


def min_(*args):
    values = _flatten(args)
    if not values:
        raise ValueError("min() needs at least one value")
    return min(values, key=_cmp_key)


def sort_(*args, descending=False):
    return sorted(_flatten(args), key=_cmp_key, reverse=bool(descending))


# ---------------------------------------------------------------------------
# logic
# ---------------------------------------------------------------------------

def if_(condition, when_true, when_false=0):
    truth = condition
    if isinstance(truth, Quantity):
        truth = truth.magnitude
    return when_true if truth else when_false


def and_(*args):
    return all(bool(a) for a in _flatten(args))


def or_(*args):
    return any(bool(a) for a in _flatten(args))


def not_(a):
    return not bool(a)


def isdefined(x):
    return x is not None


# ---------------------------------------------------------------------------
# matrices / vectors
# ---------------------------------------------------------------------------

def _split_units(data):
    """Return (numpy array, unit) for possibly-quantity nested sequences."""
    flat = _flatten([data])
    unit = None
    for v in flat:
        if isinstance(v, Quantity):
            unit = v.units
            break

    def strip(node):
        if isinstance(node, (list, tuple)):
            return [strip(n) for n in node]
        if isinstance(node, Quantity):
            return float(node.to(unit).magnitude) if unit is not None else float(node.magnitude)
        return float(node)

    return np.array(strip(data), dtype=float), unit


def matrix(*rows):
    if len(rows) == 1 and isinstance(rows[0], (list, tuple, np.ndarray)):
        rows = rows[0]
    array, unit = _split_units(list(rows))
    return Q_(array, unit) if unit is not None else array


def vector(*values):
    if len(values) == 1 and isinstance(values[0], (list, tuple, np.ndarray)):
        values = values[0]
    array, unit = _split_units(list(values))
    return Q_(array, unit) if unit is not None else array


def _array_of(x):
    if isinstance(x, Quantity):
        return np.asarray(x.magnitude, dtype=float), x.units
    return np.asarray(x, dtype=float), None


def det(m):
    array, unit = _array_of(m)
    value = float(np.linalg.det(array))
    return Q_(value, unit ** array.shape[0]) if unit is not None else value


def inv(m):
    array, unit = _array_of(m)
    out = np.linalg.inv(array)
    return Q_(out, 1 / unit) if unit is not None else out


def transpose(m):
    array, unit = _array_of(m)
    return Q_(array.T, unit) if unit is not None else array.T


def identity(n):
    return np.eye(int(as_float(n)))


def zeros(rows, cols=None):
    rows = int(as_float(rows))
    return np.zeros((rows, int(as_float(cols)))) if cols else np.zeros(rows)


def ones(rows, cols=None):
    rows = int(as_float(rows))
    return np.ones((rows, int(as_float(cols)))) if cols else np.ones(rows)


def rows_(m):
    array, _ = _array_of(m)
    return int(np.atleast_2d(array).shape[0])


def cols_(m):
    array, _ = _array_of(m)
    return int(np.atleast_2d(array).shape[1])


def dot(a, b):
    aa, ua = _array_of(a)
    bb, ub = _array_of(b)
    out = aa.dot(bb)
    unit = None
    if ua is not None and ub is not None:
        unit = ua * ub
    elif ua is not None:
        unit = ua
    elif ub is not None:
        unit = ub
    return Q_(out, unit) if unit is not None else out


def cross(a, b):
    aa, ua = _array_of(a)
    bb, ub = _array_of(b)
    out = np.cross(aa, bb)
    if ua is not None and ub is not None:
        return Q_(out, ua * ub)
    return out


def norm(v):
    array, unit = _array_of(v)
    value = float(np.linalg.norm(array))
    return Q_(value, unit) if unit is not None else value


def lsolve(a, b):
    """Solve the linear system A·x = b."""
    aa, ua = _array_of(a)
    bb, ub = _array_of(b)
    out = np.linalg.solve(aa, bb)
    if ua is not None or ub is not None:
        unit = (ub if ub is not None else ureg.dimensionless) / (ua if ua is not None else ureg.dimensionless)
        return Q_(out, unit)
    return out


def el(m, i, j=None):
    """1-based element access, matching engineering notation."""
    array, unit = _array_of(m)
    i = int(as_float(i)) - 1
    value = array[i] if j is None else array[i][int(as_float(j)) - 1]
    return Q_(float(value), unit) if unit is not None else float(value)


# ---------------------------------------------------------------------------
# interpolation, calculus, root finding
# ---------------------------------------------------------------------------

def interp(x, xs, ys):
    """Piecewise linear interpolation with units on any of the three inputs."""
    xs_list = _flatten([xs])
    ys_list = _flatten([ys])
    if len(xs_list) != len(ys_list) or len(xs_list) < 2:
        raise ValueError("interp() needs two equal-length lists of 2+ points")
    pairs = sorted(zip(xs_list, ys_list), key=lambda p: _cmp_key(p[0]))
    if _cmp_key(x) <= _cmp_key(pairs[0][0]):
        return pairs[0][1]
    if _cmp_key(x) >= _cmp_key(pairs[-1][0]):
        return pairs[-1][1]
    for (x0, y0), (x1, y1) in zip(pairs, pairs[1:]):
        if _cmp_key(x0) <= _cmp_key(x) <= _cmp_key(x1):
            t = (x - x0) / (x1 - x0)
            if isinstance(t, Quantity):
                t = t.to("dimensionless").magnitude
            return y0 + (y1 - y0) * t
    return pairs[-1][1]


def lookup(x, xs, ys):
    """Step lookup: the y of the last x-breakpoint not greater than *x*."""
    pairs = sorted(zip(_flatten([xs]), _flatten([ys])), key=lambda p: _cmp_key(p[0]))
    result = pairs[0][1]
    for bx, by in pairs:
        if _cmp_key(x) >= _cmp_key(bx):
            result = by
    return result


def diff(f, x, h=None):
    """Central-difference derivative of callable *f* at *x*."""
    if h is None:
        h = x * 1e-6 if _cmp_key(x) else 1e-6
    return (f(x + h) - f(x - h)) / (2 * h)


def integral(f, a, b, n=200):
    """Composite Simpson integration of callable *f* from *a* to *b*."""
    n = int(as_float(n))
    if n % 2:
        n += 1
    h = (b - a) / n
    total = f(a) + f(b)
    for i in range(1, n):
        total = total + (4 if i % 2 else 2) * f(a + i * h)
    return total * h / 3


def solve_root(f, lo, hi, tol=1e-10, iterations=200):
    """Bisection root of callable *f* bracketed by *lo* and *hi*."""
    flo, fhi = f(lo), f(hi)
    if _cmp_key(flo) * _cmp_key(fhi) > 0:
        raise ValueError("root(): f(lo) and f(hi) must have opposite signs")
    for _ in range(int(iterations)):
        mid = (lo + hi) / 2
        fmid = f(mid)
        if abs(_cmp_key(fmid)) < tol:
            return mid
        if _cmp_key(flo) * _cmp_key(fmid) < 0:
            hi, fhi = mid, fmid
        else:
            lo, flo = mid, fmid
    return (lo + hi) / 2


def maximise(f, lo, hi, steps=400):
    """Golden-free coarse+refine search for the maximum of *f* on [lo, hi]."""
    best_x, best_y = lo, f(lo)
    for i in range(1, int(steps) + 1):
        x = lo + (hi - lo) * i / steps
        y = f(x)
        if _cmp_key(y) > _cmp_key(best_y):
            best_x, best_y = x, y
    return best_x


def minimise(f, lo, hi, steps=400):
    best_x, best_y = lo, f(lo)
    for i in range(1, int(steps) + 1):
        x = lo + (hi - lo) * i / steps
        y = f(x)
        if _cmp_key(y) < _cmp_key(best_y):
            best_x, best_y = x, y
    return best_x


# ---------------------------------------------------------------------------
# units
# ---------------------------------------------------------------------------

def to(value, unit_text):
    return convert(value, str(unit_text))


def unit_of(value):
    return format_unit(value.units) if isinstance(value, Quantity) else ""


def mag(value):
    return value.magnitude if isinstance(value, Quantity) else value


def strip_units(value):
    return as_float(value) if isinstance(value, Quantity) and value.dimensionless else mag(value)


# ---------------------------------------------------------------------------
# symbolic (sympy bridge)
# ---------------------------------------------------------------------------

def sym(name):
    import sympy
    return sympy.Symbol(str(name))


def simplify(expr):
    import sympy
    return sympy.simplify(expr)


def expand(expr):
    import sympy
    return sympy.expand(expr)


def factor(expr):
    import sympy
    return sympy.factor(expr)


def symsolve(expr, variable):
    import sympy
    return sympy.solve(expr, variable)


def symdiff(expr, variable, order=1):
    import sympy
    return sympy.diff(expr, variable, int(as_float(order)))


def symint(expr, variable, lo=None, hi=None):
    import sympy
    if lo is None:
        return sympy.integrate(expr, variable)
    return sympy.integrate(expr, (variable, lo, hi))


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------

FUNCTIONS: dict[str, Any] = {
    # elementary
    "sqrt": sqrt, "root": root, "exp": exp, "ln": ln, "log": log, "log10": lambda x: log(x, 10),
    "log2": log2, "abs": abs_, "sign": sign, "round": round_, "floor": floor,
    "ceil": ceil, "trunc": trunc, "roundto": roundto, "ceilto": ceilto,
    "floorto": floorto, "mod": mod, "clamp": clamp, "factorial": factorial,
    "gcd": gcd, "lcm": lcm, "hypot": hypot,
    # trigonometry
    "sin": _trig(math.sin), "cos": _trig(math.cos), "tan": _trig(math.tan),
    "asin": _inverse_trig(math.asin), "acos": _inverse_trig(math.acos),
    "atan": _inverse_trig(math.atan),
    "atan2": lambda y, x: Q_(math.atan2(_cmp_key(y), _cmp_key(x)), "radian"),
    "sinh": _wrap1(math.sinh), "cosh": _wrap1(math.cosh), "tanh": _wrap1(math.tanh),
    "asinh": _wrap1(math.asinh), "acosh": _wrap1(math.acosh), "atanh": _wrap1(math.atanh),
    "degrees": lambda x: math.degrees(_angle(x)), "radians": lambda x: Q_(math.radians(as_float(x)), "radian"),
    # aggregation
    "sum": sum_, "product": product, "mean": mean, "average": mean, "median": median,
    "stdev": stdev, "pstdev": pstdev, "variance": variance, "count": count,
    "max": max_, "min": min_, "sort": sort_,
    # logic
    "if": if_, "ifelse": if_, "and": and_, "or": or_, "not": not_,
    "isdefined": isdefined,
    # matrices
    "matrix": matrix, "vector": vector, "det": det, "inv": inv,
    "transpose": transpose, "identity": identity, "zeros": zeros, "ones": ones,
    "rows": rows_, "cols": cols_, "dot": dot, "cross": cross, "norm": norm,
    "lsolve": lsolve, "el": el,
    # numerical
    "interp": interp, "lookup": lookup, "diff": diff, "integral": integral,
    "root_of": solve_root, "maximise": maximise, "minimise": minimise,
    "maximize": maximise, "minimize": minimise,
    # units
    "to": to, "unit_of": unit_of, "mag": mag, "strip_units": strip_units,
    # symbolic
    "sym": sym, "simplify": simplify, "expand": expand, "factor": factor,
    "symsolve": symsolve, "symdiff": symdiff, "symint": symint,
}

CONSTANTS: dict[str, Any] = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
    "phi": (1 + math.sqrt(5)) / 2,
    "inf": math.inf,
    "true": True,
    "false": False,
    "g0": Q_(9.80665, "m/s**2"),
    "g_acc": Q_(9.80665, "m/s**2"),
}

# Short one-line help shown in the function browser panel.
FUNCTION_HELP: dict[str, str] = {
    "sqrt": "sqrt(x) — square root, unit aware",
    "root": "root(x, n) — n-th root",
    "log": "log(x, base=10) — logarithm",
    "ln": "ln(x) — natural logarithm",
    "round": "round(x, digits=0) — round to decimal places",
    "roundto": "roundto(x, step) — round to nearest multiple of step",
    "ceilto": "ceilto(x, step) — round up to a multiple of step",
    "mod": "mod(a, b) — remainder, unit aware",
    "clamp": "clamp(x, lo, hi) — constrain a value to a range",
    "hypot": "hypot(a, b, …) — root sum of squares",
    "sin": "sin(θ) — accepts deg or rad quantities",
    "atan2": "atan2(y, x) — angle of a vector, returns rad",
    "sum": "sum(a, b, …) — total of values or a range",
    "mean": "mean(…) — arithmetic average",
    "stdev": "stdev(…) — sample standard deviation",
    "max": "max(…) / min(…) — extreme value",
    "if": "if(condition, a, b) — conditional value",
    "matrix": "matrix([[1,2],[3,4]]) — build a matrix",
    "det": "det(M) — determinant",
    "inv": "inv(M) — matrix inverse",
    "lsolve": "lsolve(A, b) — solve A·x = b",
    "el": "el(M, i, j) — 1-based element access",
    "interp": "interp(x, xs, ys) — linear interpolation",
    "lookup": "lookup(x, xs, ys) — step table lookup",
    "diff": "diff(f, x) — numeric derivative of a defined function",
    "integral": "integral(f, a, b) — numeric integral (Simpson)",
    "root_of": "root_of(f, lo, hi) — bracketed root of f(x) = 0",
    "to": "to(x, \"mm\") — convert to a unit",
    "symsolve": "symsolve(expr, x) — symbolic solve via SymPy",
    "symdiff": "symdiff(expr, x) — symbolic derivative",
}
