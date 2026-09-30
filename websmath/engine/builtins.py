"""Built-in functions (the SMath Cloud catalogue) and programming constructs."""
from __future__ import annotations

import cmath
import re
import math
import random as _random
import time as _time

from . import ast as A
from .catalog import FUNCTIONS
from .errors import SMathError, err
from .units import NODIM, Quantity, dims_scale, sqrt_value
from .values import (Matrix, Q, String, add, determinant, div, identity, inverse, mul,
                     need_dimless, need_int, need_real, need_scalar, neg, transpose, truth)

_TABLE: dict = {}  # (name, nargs) -> callable ; nargs -1 = variadic


def fn(name: str, nargs: int = 1):
    def deco(f):
        _TABLE[(name, nargs)] = f
        return f

    return deco


def lookup(name: str, nargs: int):
    return _TABLE.get((name, nargs)) or _TABLE.get((name, -1))


def has_overload(name: str, nargs: int) -> bool:
    """Whether SMath lists name with this argument count (catalogue arities).

    Decides whether "=" after name(args) evaluates or defines: SMath knows
    max/min with one (matrix) argument only, so max(1,5,3)= becomes a
    definition (observed).
    """
    arities = {k for n, k, _, _ in FUNCTIONS if n == name}
    if arities:
        return nargs in arities or -1 in arities
    return lookup(name, nargs) is not None or name in SPECIAL


def known(name: str) -> bool:
    return any(n == name for n, _ in _TABLE) or name in SPECIAL


def catalogue_names() -> list:
    return sorted({f[0] for f in FUNCTIONS} | {n for n, _ in _TABLE} | set(SPECIAL))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _num(v):
    q = need_scalar(v)
    if not q.dimensionless:
        raise err("function_units")  # observed: sin(1'm)
    return q.value


def _out(v, dims=NODIM):
    if isinstance(v, complex):
        if abs(v.imag) < 1e-15 * max(1.0, abs(v.real)):
            v = v.real
    return Q(v, dims)


def _cfun(f_real, f_complex, domain=None):
    def run(v):
        if isinstance(v, Matrix):
            return Matrix(v.nrows, v.ncols, [run(x) for x in v.items])
        x = _num(v)
        try:
            if isinstance(x, complex) or (domain is not None and not domain(x)):
                r = f_complex(complex(x))
            else:
                try:
                    r = f_real(x)
                except ValueError:
                    r = f_complex(complex(x))
        except (OverflowError, ZeroDivisionError):
            raise err("overflow")  # observed: exp(1000), cot(0)
        if isinstance(r, complex) and (math.isinf(r.real) or math.isinf(r.imag)) or \
                (not isinstance(r, complex) and math.isinf(r)):
            raise err("overflow")
        return _out(r)

    return run


def _snap_zero(y: float) -> float:
    """sin(π) and cos(π/2) show 0 on SMath Cloud, not 1.2246·10^-16."""
    return 0.0 if abs(y) < 1e-15 else y


def _no_log_zero(f):
    def run(v):
        if isinstance(v, Quantity) and v.value == 0:
            raise err("log_zero")  # observed: ln(0)
        return f(v)

    return run


# .NET's complex inverse sine/cosine (SMath: asin(2) = 1.5708-1.317i,
# acos(2) = 1.317i; Python's cmath picks the other branch on the cut)
def _net_asin(z: complex) -> complex:
    return -1j * cmath.log(1j * z + cmath.sqrt(1 - z * z))


def _net_acos(z: complex) -> complex:
    return -1j * cmath.log(z + 1j * cmath.sqrt(1 - z * z))


def _mat(v) -> Matrix:
    if isinstance(v, Matrix):
        return v
    if isinstance(v, Quantity):
        return Matrix(1, 1, [v])
    raise err("must_be_matrix")


def _real(v) -> float:
    return need_real(v)


# ---------------------------------------------------------------------------
# elementary
# ---------------------------------------------------------------------------

for _n, _r, _c, _dom in [
    ("sin", math.sin, cmath.sin, None), ("cos", math.cos, cmath.cos, None),
    ("tan", math.tan, cmath.tan, None),
    ("asin", math.asin, _net_asin, lambda x: -1 <= x <= 1),
    ("acos", math.acos, _net_acos, lambda x: -1 <= x <= 1),
    ("sinh", math.sinh, cmath.sinh, None), ("cosh", math.cosh, cmath.cosh, None),
    ("tanh", math.tanh, cmath.tanh, None), ("asinh", math.asinh, cmath.asinh, None),
    ("acosh", math.acosh, cmath.acosh, lambda x: x >= 1),
    ("atanh", math.atanh, cmath.atanh, lambda x: -1 < x < 1),
    ("exp", math.exp, cmath.exp, None),
    ("ln", math.log, cmath.log, lambda x: x > 0),
    ("log10", math.log10, cmath.log10, lambda x: x > 0),
]:
    if _n in ("sin", "cos"):
        _r = (lambda f: lambda x: _snap_zero(f(x)))(_r)
    fn(_n)(_no_log_zero(_cfun(_r, _c, _dom)) if _n in ("ln", "log10") else _cfun(_r, _c, _dom))


fn("cot")(_cfun(lambda x: 1 / math.tan(x), lambda z: 1 / cmath.tan(z)))
fn("sec")(_cfun(lambda x: 1 / math.cos(x), lambda z: 1 / cmath.cos(z)))
fn("csc")(_cfun(lambda x: 1 / math.sin(x), lambda z: 1 / cmath.sin(z)))
fn("coth")(_cfun(lambda x: 1 / math.tanh(x), lambda z: 1 / cmath.tanh(z)))
fn("sech")(_cfun(lambda x: 1 / math.cosh(x), lambda z: 1 / cmath.cosh(z)))
fn("csch")(_cfun(lambda x: 1 / math.sinh(x), lambda z: 1 / cmath.sinh(z)))
fn("atan")(_cfun(math.atan, cmath.atan))
fn("acot")(_cfun(lambda x: math.pi / 2 - math.atan(x), lambda z: cmath.pi / 2 - cmath.atan(z)))
fn("asec")(_cfun(lambda x: math.acos(1 / x), lambda z: cmath.acos(1 / z), lambda x: abs(x) >= 1))
fn("acsc")(_cfun(lambda x: math.asin(1 / x), lambda z: cmath.asin(1 / z), lambda x: abs(x) >= 1))
fn("acoth")(_cfun(lambda x: math.atanh(1 / x), lambda z: cmath.atanh(1 / z), lambda x: abs(x) > 1))


@fn("atan", 2)
def _atan2(x, y):
    a, b = need_scalar(x), need_scalar(y)
    if a.dims != b.dims:
        raise err("units_mismatch")
    return Q(math.atan2(b.real, a.real))


@fn("sqrt")
def _sqrt(v):
    if isinstance(v, Matrix):
        return Matrix(v.nrows, v.ncols, [_sqrt(x) for x in v.items])
    q = need_scalar(v)
    return _out(sqrt_value(q.value), dims_scale(q.dims, 0.5))


@fn("nthroot", 2)
def _nthroot(x, n):
    k = _real(need_dimless(n))
    q = need_scalar(x)
    v = q.value
    if not isinstance(v, complex) and v < 0 and float(k).is_integer() and int(k) % 2 == 1:
        r = -((-v) ** (1 / k))
    else:
        r = complex(v) ** (1 / k) if (isinstance(v, complex) or v < 0) else v ** (1 / k)
    return _out(r, dims_scale(q.dims, 1 / k))


@fn("log", 2)
def _log(x, b):
    if _num(x) == 0:
        raise err("log_zero")
    return _out(cmath.log(_num(x)) / cmath.log(_num(b))) if _num(x) <= 0 or _num(b) <= 0 else Q(math.log(_num(x), _num(b)))


@fn("abs")
def _abs(v):
    if isinstance(v, Matrix):
        if v.nrows == v.ncols:
            return determinant(v)
        return Matrix(v.nrows, v.ncols, [_abs(x) for x in v.items])
    if isinstance(v, String):
        return Q(len(v.text))
    q = need_scalar(v)
    return Q(abs(q.value), q.dims)


def _unit_preserving(f):
    def run(v):
        if isinstance(v, Matrix):
            return Matrix(v.nrows, v.ncols, [run(x) for x in v.items])
        q = need_scalar(v)
        if isinstance(q.value, complex):
            return Q(complex(f(q.value.real), f(q.value.imag)), q.dims)
        return Q(float(f(q.value)), q.dims)

    return run


fn("floor")(_unit_preserving(math.floor))
fn("ceil")(_unit_preserving(math.ceil))
fn("trunc")(_unit_preserving(math.trunc))


def _round_half_away(x: float, n: int) -> float:
    m = 10 ** n
    return math.floor(abs(x) * m + 0.5) / m * (1 if x >= 0 else -1)


@fn("round", 2)
def _round2(v, n):
    k = need_int(n)
    if not 0 <= k <= 15:
        raise err("round_range")  # observed: round(12345.6789, -2)
    q = need_scalar(v)
    return Q(_round_half_away(q.real, k), q.dims)


@fn("round", 3)
def _round3(v, n, mode):
    return _round2(v, n)


@fn("sign")
def _sign(v):
    x = _real(v)
    return Q(0.0 if x == 0 else (1.0 if x > 0 else -1.0))


@fn("mod", 2)
def _mod(a, b):
    x, y = need_scalar(a), need_scalar(b)
    if x.dims != y.dims:
        raise err("units_mismatch")
    if y.value == 0:
        raise err("div_zero")
    # the remainder takes the sign of the dividend (observed: mod(-7,3) = -1,
    # mod(7,-3) = 1, mod(5.5,2) = 1.5)
    return Q(math.fmod(x.real, y.real), x.dims)


@fn("Gamma")
def _gamma(v):
    return Q(math.gamma(_real(need_dimless(v))))


@fn("perc", 2)
def _perc(a, p):
    return mul(a, div(p, Q(100.0)))


@fn("random")
def _random_fn(v):
    q = need_scalar(v)
    return Q(_random.random() * q.real, q.dims)


@fn("Re")
def _re(v):
    q = need_scalar(v)
    return Q(q.value.real if isinstance(q.value, complex) else q.value, q.dims)


@fn("Im")
def _im(v):
    q = need_scalar(v)
    return Q(q.value.imag if isinstance(q.value, complex) else 0.0, q.dims)


@fn("arg")
def _arg(v):
    return Q(cmath.phase(complex(need_scalar(v).value)))


@fn("UnitsOf")
def _unitsof(v):
    q = need_scalar(v)
    return Q(1.0, q.dims)


@fn("time")
def _time_fn(v):
    return Q(float((_time.time() + 11644473600) * 1000))


@fn("pol2xy", 2)
def _pol2xy(r, phi):
    rr, p = need_scalar(r), _real(need_dimless(phi))
    return Matrix(2, 1, [Q(rr.real * math.cos(p), rr.dims), Q(rr.real * math.sin(p), rr.dims)])


@fn("xy2pol", 2)
def _xy2pol(x, y):
    a, b = need_scalar(x), need_scalar(y)
    return Matrix(2, 1, [Q(math.hypot(a.real, b.real), a.dims), Q(math.atan2(b.real, a.real))])


# ---------------------------------------------------------------------------
# matrices
# ---------------------------------------------------------------------------

@fn("mat", -1)
def _matf(*args):
    if len(args) < 3:
        raise err("args_count")
    r, c = need_int(args[-2]), need_int(args[-1])
    items = list(args[:-2])
    if len(items) != r * c:
        raise err("args_count")
    return Matrix(r, c, items)


@fn("matrix", 2)
def _matrix(r, c):
    return Matrix(need_int(r), need_int(c), [Q(0.0)] * (need_int(r) * need_int(c)))


@fn("identity")
def _identity(n):
    return identity(need_int(n))


@fn("det")
def _det(m):
    return determinant(_mat(m))


@fn("invert")
def _invert(m):
    return inverse(_mat(m))


@fn("transpose")
def _transpose(m):
    return transpose(_mat(m))


@fn("rows")
def _rows(m):
    return Q(float(_mat(m).nrows))


@fn("cols")
def _cols(m):
    return Q(float(_mat(m).ncols))


@fn("length")
def _length(m):
    return Q(float(len(_mat(m).items)))


@fn("el", 2)
def _el2(m, i):
    mm = _mat(m)
    k = need_int(i) - 1
    if not 0 <= k < len(mm.items):
        raise err("index_range")
    return mm.items[k]


@fn("el", 3)
def _el3(m, i, j):
    mm = _mat(m)
    a, b = need_int(i) - 1, need_int(j) - 1
    if not (0 <= a < mm.nrows and 0 <= b < mm.ncols):
        raise err("index_range")
    return mm.get(a, b)


@fn("row", 2)
def _row(m, i):
    mm = _mat(m)
    k = need_int(i) - 1
    return Matrix(1, mm.ncols, [mm.get(k, j) for j in range(mm.ncols)])


@fn("col", 2)
def _col(m, j):
    mm = _mat(m)
    k = need_int(j) - 1
    return Matrix(mm.nrows, 1, [mm.get(i, k) for i in range(mm.nrows)])


@fn("tr")
def _tr(m):
    mm = _mat(m)
    acc = mm.get(0, 0)
    for i in range(1, min(mm.nrows, mm.ncols)):
        acc = add(acc, mm.get(i, i))
    return acc


@fn("diag")
def _diag(v):
    mm = _mat(v)
    n = len(mm.items)
    zero = Q(0.0, mm.items[0].dims) if n else Q(0.0)
    return Matrix(n, n, [mm.items[i] if i == j else zero for i in range(n) for j in range(n)])


def _flat(args):
    out = []
    for a in args:
        if isinstance(a, Matrix):
            out.extend(a.items)
        else:
            out.append(need_scalar(a))
    return out


@fn("max", -1)
def _max(*args):
    vals = _flat(args)
    if not vals:
        raise err("args_count")
    d = vals[0].dims
    if any(v.dims != d for v in vals):
        raise err("units_mismatch")
    if any(isinstance(v.value, complex) for v in vals):
        return Q(complex(max(complex(v.value).real for v in vals), max(complex(v.value).imag for v in vals)), d)
    return max(vals, key=lambda v: v.value)


@fn("min", -1)
def _min(*args):
    vals = _flat(args)
    if not vals:
        raise err("args_count")
    d = vals[0].dims
    if any(v.dims != d for v in vals):
        raise err("units_mismatch")
    if any(isinstance(v.value, complex) for v in vals):
        return Q(complex(min(complex(v.value).real for v in vals), min(complex(v.value).imag for v in vals)), d)
    return min(vals, key=lambda v: v.value)


@fn("sum", 1)
def _sum1(m):
    vals = _flat([m])
    acc = vals[0]
    for v in vals[1:]:
        acc = add(acc, v)
    return acc


@fn("sort")
def _sort(m):
    vals = _flat([m])
    return Matrix.column(sorted(vals, key=lambda v: v.real))


@fn("reverse")
def _reverse(m):
    mm = _mat(m)
    rows = [mm.items[i * mm.ncols:(i + 1) * mm.ncols] for i in range(mm.nrows)]
    return Matrix(mm.nrows, mm.ncols, [x for r in reversed(rows) for x in r])


@fn("csort", 2)
def _csort(m, j):
    mm = _mat(m)
    k = need_int(j) - 1
    if not 0 <= k < mm.ncols:
        raise err("index_range")
    rows = [mm.items[i * mm.ncols:(i + 1) * mm.ncols] for i in range(mm.nrows)]
    rows.sort(key=lambda r: r[k].real)
    return Matrix(mm.nrows, mm.ncols, [x for r in rows for x in r])


@fn("rsort", 2)
def _rsort(m, i):
    return transpose(_csort(transpose(_mat(m)), i))


@fn("augment", -1)
def _augment(*args):
    ms = [_mat(a) for a in args]
    n = ms[0].nrows
    if any(m.nrows != n for m in ms):
        raise err("matrix_size")
    items = []
    for i in range(n):
        for m in ms:
            items.extend(m.get(i, j) for j in range(m.ncols))
    return Matrix(n, sum(m.ncols for m in ms), items)


@fn("stack", -1)
def _stack(*args):
    ms = [_mat(a) for a in args]
    c = ms[0].ncols
    if any(m.ncols != c for m in ms):
        raise err("matrix_size")
    return Matrix(sum(m.nrows for m in ms), c, [x for m in ms for x in m.items])


@fn("submatrix", 5)
def _submatrix(m, r1, r2, c1, c2):
    mm = _mat(m)
    a, b, c, d = (need_int(x) - 1 for x in (r1, r2, c1, c2))
    return Matrix(b - a + 1, d - c + 1, [mm.get(i, j) for i in range(a, b + 1) for j in range(c, d + 1)])


@fn("vminor", 3)
def _vminor(m, i, j):
    mm = _mat(m)
    a, b = need_int(i) - 1, need_int(j) - 1
    return Matrix(mm.nrows - 1, mm.ncols - 1,
                  [mm.get(r, c) for r in range(mm.nrows) if r != a for c in range(mm.ncols) if c != b])


@fn("minor", 3)
def _minor(m, i, j):
    return determinant(_vminor(m, i, j))


@fn("alg", 3)
def _alg(m, i, j):
    s = (-1) ** (need_int(i) + need_int(j))
    d = _minor(m, i, j)
    return d if s > 0 else neg(d)


@fn("rank")
def _rank(m):
    mm = _mat(m)
    a = [[mm.get(i, j).real for j in range(mm.ncols)] for i in range(mm.nrows)]
    rank, rows, cols = 0, mm.nrows, mm.ncols
    for c in range(cols):
        piv = None
        for r in range(rank, rows):
            if abs(a[r][c]) > 1e-12:
                piv = r
                break
        if piv is None:
            continue
        a[rank], a[piv] = a[piv], a[rank]
        for r in range(rows):
            if r != rank and abs(a[r][c]) > 0:
                f = a[r][c] / a[rank][c]
                a[r] = [x - f * y for x, y in zip(a[r], a[rank])]
        rank += 1
    return Q(float(rank))


@fn("norme")
def _norme(m):
    vals = _flat([m])
    return Q(math.sqrt(sum(abs(v.value) ** 2 for v in vals)), vals[0].dims)


@fn("norm1")
def _norm1(m):
    mm = _mat(m)
    return Q(max(sum(abs(mm.get(i, j).value) for i in range(mm.nrows)) for j in range(mm.ncols)), mm.items[0].dims)


@fn("normi")
def _normi(m):
    mm = _mat(m)
    return Q(max(sum(abs(mm.get(i, j).value) for j in range(mm.ncols)) for i in range(mm.nrows)), mm.items[0].dims)


@fn("range", 2)
def _range2(a, b):
    return _range3(a, b, add(a, Q(1.0, need_scalar(a).dims)))


@fn("range", 3)
def _range3(a, b, second):
    x, y, s = need_scalar(a), need_scalar(b), need_scalar(second)
    step = s.real - x.real
    if step == 0:
        raise err("cannot_evaluate")
    out, v, k = [], x.real, 0
    if (y.real - x.real) * step < 0:
        step = -step
    while (step > 0 and v <= y.real + 1e-12) or (step < 0 and v >= y.real - 1e-12):
        out.append(Q(v, x.dims))
        k += 1
        v = x.real + k * step
    return Matrix.column(out)


def _interp(kind):
    def run(xv, yv, x):
        xs = [v.real for v in _flat([xv])]
        ys = _flat([yv])
        t = need_scalar(x).real
        if len(xs) != len(ys) or len(xs) < 2:
            raise err("matrix_size")
        pts = sorted(zip(xs, ys), key=lambda p: p[0])
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        k = 0
        while k < len(xs) - 2 and t > xs[k + 1]:
            k += 1
        x0, x1 = xs[k], xs[k + 1]
        f = (t - x0) / (x1 - x0)
        return Q(ys[k].real + f * (ys[k + 1].real - ys[k].real), ys[k].dims)

    return run


fn("linterp", 3)(_interp("linear"))
fn("cinterp", 3)(_interp("cubic"))
fn("ainterp", 3)(_interp("akima"))


@fn("polyroots")
def _polyroots(v):
    coeffs = [complex(x.value) for x in _flat([v])]
    # coefficients in ascending powers (SMath convention)
    while coeffs and coeffs[-1] == 0:
        coeffs.pop()
    n = len(coeffs) - 1
    if n < 1:
        raise err("cannot_evaluate")
    a = [c / coeffs[-1] for c in coeffs]
    roots = [complex(0.4, 0.9) ** k for k in range(n)]
    for _ in range(500):
        new = []
        for i, r in enumerate(roots):
            num = sum(a[k] * r ** k for k in range(n + 1))
            den = 1
            for j, s in enumerate(roots):
                if j != i:
                    den *= r - s
            new.append(r - num / den)
        roots = new
    roots.sort(key=lambda z: (round(z.real, 9), z.imag))
    return Matrix.column([_out(complex(round(z.real, 12), round(z.imag, 12))) for z in roots])


# ---------------------------------------------------------------------------
# strings
# ---------------------------------------------------------------------------

def _s(v) -> str:
    if isinstance(v, String):
        return v.text
    raise err("must_be_string")


@fn("concat", -1)
def _concat(*a):
    return String("".join(_s(x) for x in a))


@fn("strlen")
def _strlen(a):
    return Q(float(len(_s(a))))


@fn("substr", 2)
def _substr2(a, i):
    return String(_s(a)[need_int(i):])


@fn("substr", 3)
def _substr3(a, i, n):
    k = need_int(i)
    return String(_s(a)[k:k + need_int(n)])


@fn("strrep", 3)
def _strrep(a, b, c):
    return String(_s(a).replace(_s(b), _s(c)))


@fn("findstr", 2)
def _findstr(a, b):
    s, t = _s(a), _s(b)
    pos = [i for i in range(len(s)) if s.startswith(t, i)]
    return Matrix.column([Q(float(p)) for p in pos]) if pos else Q(-1.0)


@fn("IsString")
def _isstring(a):
    return Q(1.0 if isinstance(a, String) else 0.0)


@fn("num2str", 1)
def _num2str(a):
    from .display import value_to_text

    return String(value_to_text(a))


@fn("num2str", 2)
def _num2str_fmt(a, f):
    """num2str(x, "0.00"): .NET-style number formats - 0.00, #.##, F2, E3,
    N2, P1 and 0.0E+00."""
    fmt = f.text if isinstance(f, String) else ""
    x = need_real(a)
    m = re.fullmatch(r"([FfEeNnPp])(\d*)", fmt)
    if m:
        k = int(m.group(2) or 2)
        c = m.group(1).upper()
        if c == "F":
            return String(f"{x:.{k}f}")
        if c == "N":
            return String(f"{x:,.{k}f}")
        if c == "P":
            return String(f"{x * 100:.{k}f} %")
        s = f"{x:.{k}E}"
        mant, e = s.split("E")
        return String(f"{mant}E{int(e):+04d}")
    if "E" in fmt.upper():
        mant, _, ex = fmt.upper().partition("E")
        k = len(mant.split(".")[1]) if "." in mant else 0
        e = math.floor(math.log10(abs(x))) if x else 0
        return String(f"{x / 10 ** e:.{k}f}E{e:+0{len(ex.lstrip('+-')) + 1}d}")
    if "." in fmt:
        whole, dec = fmt.split(".", 1)
        req, opt = dec.count("0"), dec.count("#")
        s = f"{x:.{req + opt}f}"
        if opt:
            head, tail = s.split(".")
            tail = tail[:req] + tail[req:].rstrip("0")
            s = head + ("." + tail if tail else "")
        return String(s)
    if fmt:
        return String(f"{x:.0f}")
    from .display import value_to_text

    return String(value_to_text(a))


@fn("mixed", 3)
def _mixed(w, a, b):
    """mixed(2, 1, 3) is the mixed number 2 1/3 = 7/3."""
    x, y, z = need_scalar(w), need_scalar(a), need_scalar(b)
    if z.value == 0:
        raise err("div_zero")
    frac = y.value / z.value
    return Q(x.value - frac if x.real < 0 else x.value + frac)


@fn("findrows", 3)
def _findrows(m, value, col):
    """The rows of m whose column col holds value (0 when there are none)."""
    mat = _mat(m)
    c = need_int(col) - 1
    if not 0 <= c < mat.ncols:
        raise err("index_range")
    rows = [i for i in range(mat.nrows) if _equal(mat.get(i, c), value)]
    if not rows:
        return Q(0.0)
    return Matrix(len(rows), mat.ncols, [mat.get(i, j) for i in rows for j in range(mat.ncols)])


def _equal(a, b) -> bool:
    if isinstance(a, String) or isinstance(b, String):
        return isinstance(a, String) and isinstance(b, String) and a.text == b.text
    return isinstance(a, Quantity) and isinstance(b, Quantity) and a.dims == b.dims and a.value == b.value


@fn("Sleep")
def _sleep(ms):
    """Waits the given milliseconds (at most 10 s, the evaluation limit)."""
    t = max(0.0, min(need_real(ms), 10000.0))
    _time.sleep(t / 1000)
    return Q(t)


@fn("appVersion")
def _app_version(v):
    """The SMath Studio version this replica follows (the bundled desktop
    SMath Studio is 1.3; SMath Cloud reports the same)."""
    need_int(v)
    return String("1.3.0.9126")


@fn("description")
def _description(v):
    return String("")  # regions have no description text in the replica


@fn("str2num")
def _str2num(a):
    from .linear import parse_linear
    from .parser import parse_row
    from .evaluator import Context, Evaluator

    return Evaluator().eval(parse_row(parse_linear(_s(a))), Context())


@fn("error")
def _error(a):
    raise SMathError(_s(a))


# ---------------------------------------------------------------------------
# constructs that need unevaluated arguments
# ---------------------------------------------------------------------------

def _if(ev, n: A.Call, ctx):
    args = n.args
    if len(args) < 2:
        raise err("args_count", node=n)
    # if(c1, v1, c2, v2, ..., else)
    i = 0
    while i + 1 < len(args):
        if truth(ev.eval(args[i], ctx)):
            return ev.eval(args[i + 1], ctx)
        i += 2
    if i < len(args):
        return ev.eval(args[i], ctx)
    return Q(0.0)


def _line(ev, n: A.Call, ctx):
    result = Q(0.0)
    for a in n.args:
        result = ev.eval(a, ctx)
    return result


def _while(ev, n: A.Call, ctx):
    from .evaluator import BreakLoop, ContinueLoop

    if len(n.args) != 2:
        raise err("args_count", node=n)
    cond, body = n.args
    result = Q(0.0)
    guard = 0
    while truth(ev.eval(cond, ctx)):
        try:
            result = ev.eval(body, ctx)
        except BreakLoop:
            break
        except ContinueLoop:
            pass
        guard += 1
        if guard % 1000 == 0:
            ev.check_time(n)
    return result


def _for(ev, n: A.Call, ctx):
    from .evaluator import BreakLoop, ContinueLoop

    args = n.args
    result = Q(0.0)
    if len(args) == 3:
        var, rng, body = args
        if not isinstance(var, A.Var):
            raise err("syntax", node=var)
        values = ev.eval(rng, ctx)
        seq = values.items if isinstance(values, Matrix) else [values]
        for k, v in enumerate(seq):
            if k % 1000 == 999:
                ev.check_time(n)
            ctx.assign(var.name, v)
            try:
                result = ev.eval(body, ctx)
            except BreakLoop:
                break
            except ContinueLoop:
                continue
        return result
    if len(args) == 4:
        init, cond, step, body = args
        ev.eval(init, ctx)
        guard = 0
        while truth(ev.eval(cond, ctx)):
            try:
                result = ev.eval(body, ctx)
            except BreakLoop:
                break
            except ContinueLoop:
                pass
            ev.eval(step, ctx)
            guard += 1
            if guard % 1000 == 0:
                ev.check_time(n)
        return result
    raise err("args_count", node=n)


def _break(ev, n, ctx):
    from .evaluator import BreakLoop

    raise BreakLoop()


def _continue(ev, n, ctx):
    from .evaluator import ContinueLoop

    raise ContinueLoop()


def _try(ev, n: A.Call, ctx):
    if len(n.args) != 2:
        raise err("args_count", node=n)
    try:
        return ev.eval(n.args[0], ctx)
    except SMathError:
        return ev.eval(n.args[1], ctx)


def _iterate(ev, n: A.Call, ctx, combine, start):
    if len(n.args) != 4:
        raise err("args_count", node=n)
    expr, var, lo, hi = n.args
    if not isinstance(var, A.Var):
        raise err("syntax", node=var)
    a, b = need_int(ev.eval(lo, ctx)), need_int(ev.eval(hi, ctx))
    from .evaluator import Context

    local = Context(ctx)
    acc = None
    for k in range(a, b + 1):
        local.vars[var.name] = Q(float(k))
        v = ev.eval(expr, local)
        acc = v if acc is None else combine(acc, v)
    return acc if acc is not None else start


def _sum(ev, n, ctx):
    if len(n.args) == 1:
        return _sum1(ev.eval(n.args[0], ctx))
    return _iterate(ev, n, ctx, add, Q(0.0))


def _product(ev, n, ctx):
    return _iterate(ev, n, ctx, mul, Q(1.0))


def _with_var(ev, ctx, expr, var, x):
    from .evaluator import Context

    local = Context(ctx)
    local.vars[var.name] = x
    return need_scalar(ev.eval(expr, local))


def _names(node) -> set:
    out = set()
    for m in A.walk(node):
        if isinstance(m, A.Var):
            out.add(m.name)
        elif isinstance(m, A.IndexOp) and isinstance(m.base, A.Var):
            out.add(m.base.name)
    return out


def _undefined_names(node, ctx, var: str) -> set:
    from .evaluator import BUILTIN_CONSTANTS

    return {name for name in _names(node) if name != var and name not in BUILTIN_CONSTANTS
            and ctx.lookup(name) is None}


def _diff(ev, n: A.Call, ctx):
    """diff(f, x[, n]): symbolic when x has no value (diff(x^3,x) = 3·x²),
    the derivative's value at x when it has one."""
    from . import symbolic as S

    if len(n.args) not in (2, 3):
        raise err("args_count", node=n)
    expr, var = n.args[0], n.args[1]
    if not isinstance(var, A.Var):
        raise err("syntax", node=var)
    order = need_int(ev.eval(n.args[2], ctx)) if len(n.args) == 3 else 1
    try:
        expanded = S.expand(expr, ctx)
        d = S.derivative(expanded, var.name, order)
    except S.NotSymbolic:
        d = None
    if d is not None:
        # an unknown name that vanished from the derivative (diff(T[k], z)
        # with T undefined gave 0) is reported, never silently taken as a
        # constant: that turned a failed definition into zeros
        from . import sym

        # (only names the worksheet defines above: a free constant such as c
        # in diff(a·x²+b·x+c, x) rightly drops out)
        lost = (_undefined_names(expanded, ctx, var.name) - _names(d)) & sym.defined_above()
        if lost:
            raise err("not_defined", sorted(lost)[0], node=n)
    if ctx.lookup(var.name) is None or _is_lazy(ctx.lookup(var.name)):
        if d is None:
            raise err("cannot_evaluate", node=n)
        try:
            # everything else may be known: then the result is a number
            return ev.eval(d, ctx)
        except SMathError:
            return S.Expr(d)
    if d is not None:
        return ev.eval(d, ctx)
    x0 = need_scalar(ev.eval(var, ctx))
    h = 1e-3 * max(1.0, abs(x0.real))

    def d(k, x):
        if k == 0:
            return _with_var(ev, ctx, expr, var, Q(x, x0.dims)).value
        return (d(k - 1, x + h) - d(k - 1, x - h)) / (2 * h)

    val = d(order, x0.real)
    f0 = _with_var(ev, ctx, expr, var, x0)
    return _out(val, tuple(a - order * b for a, b in zip(f0.dims, x0.dims)))


def _is_lazy(v) -> bool:
    from .evaluator import Lazy

    return isinstance(v, Lazy)


def _jacob(ev, n: A.Call, ctx):
    """Jacob(F, X): the matrix of dF_i/dX_j (symbolic where X has no value)."""
    from . import symbolic as S

    if len(n.args) != 2:
        raise err("args_count", node=n)
    fs, xs = _vector_nodes(n.args[0], ctx), _vector_nodes(n.args[1], ctx)
    if not all(isinstance(x, A.Var) for x in xs):
        raise err("syntax", node=n.args[1])
    cells, symbolic = [], False
    for f in fs:
        fe = S.expand(f, ctx)
        for x in xs:
            try:
                d = S.derivative(fe, x.name)
            except S.NotSymbolic:
                raise err("cannot_evaluate", node=n)
            try:
                cells.append(ev.eval(d, ctx))
            except SMathError:
                cells.append(d)
                symbolic = True
    if symbolic:
        nodes = [c if isinstance(c, A.Node) else S.num(need_real(c)) for c in cells]
        return S.Expr(A.MatrixLit(len(fs), len(xs), nodes))
    return Matrix(len(fs), len(xs), cells)


def _vector_nodes(node, ctx) -> list:
    """The element expressions of a vector argument: a matrix literal,
    stack(...), a plain list of one, or a variable holding a vector."""
    if isinstance(node, A.Group):
        return _vector_nodes(node.inner, ctx)
    if isinstance(node, A.MatrixLit):
        return list(node.cells)
    if isinstance(node, A.Call) and node.name in ("stack", "sys"):
        return list(node.args)
    if isinstance(node, A.Var):
        v = ctx.lookup(node.name)
        if _is_lazy(v):
            return _vector_nodes(v.node, ctx)
    return [node]


def _roots(ev, n: A.Call, ctx):
    """roots(F, X[, X0]): Newton's method on the system F(X) = 0, starting
    from the values X has (or X0)."""
    from .evaluator import Context

    if len(n.args) not in (2, 3):
        raise err("args_count", node=n)
    fs, xs = _vector_nodes(n.args[0], ctx), _vector_nodes(n.args[1], ctx)
    if not all(isinstance(x, A.Var) for x in xs) or len(fs) != len(xs):
        raise err("args_count", node=n)
    if len(n.args) == 3:
        g = ev.eval(n.args[2], ctx)
        guess = [need_scalar(v) for v in (g.items if isinstance(g, Matrix) else [g])]
    else:
        guess = []
        for x in xs:
            v = ctx.lookup(x.name)
            guess.append(need_scalar(ev.eval(x, ctx)) if v is not None and not _is_lazy(v) else Q(1.0))
    dims = [q.dims for q in guess]
    xv = [complex(q.value) if isinstance(q.value, complex) else float(q.value) for q in guess]

    def F(vals):
        local = Context(ctx)
        for x, v, d in zip(xs, vals, dims):
            local.vars[x.name] = Q(v, d)
        return [need_scalar(ev.eval(f, local)).value for f in fs]

    for _ in range(100):
        ev.check_time(n)
        f0 = F(xv)
        if max(abs(v) for v in f0) < 1e-12:
            break
        k = len(xv)
        J = []
        for j in range(k):
            h = 1e-7 * max(1.0, abs(xv[j]))
            xp = list(xv)
            xp[j] += h
            fp = F(xp)
            J.append([(fp[i] - f0[i]) / h for i in range(k)])
        J = [[J[j][i] for j in range(k)] for i in range(k)]  # rows: equations
        step = _linsolve(J, [-v for v in f0])
        if step is None:
            raise err("no_solution", node=n)
        xv = [a + b for a, b in zip(xv, step)]
    else:
        raise err("no_solution", node=n)
    if max(abs(v) for v in F(xv)) > 1e-6:
        raise err("no_solution", node=n)
    vals = [_out(v, d) for v, d in zip(xv, dims)]
    return vals[0] if len(vals) == 1 else Matrix.column(vals)


def _linsolve(a, b):
    k = len(b)
    m = [list(r) + [v] for r, v in zip(a, b)]
    for c in range(k):
        piv = max(range(c, k), key=lambda r: abs(m[r][c]))
        if abs(m[piv][c]) < 1e-300:
            return None
        m[c], m[piv] = m[piv], m[c]
        for r in range(k):
            if r != c:
                f = m[r][c] / m[c][c]
                m[r] = [x - f * y for x, y in zip(m[r], m[c])]
    return [m[i][k] / m[i][i] for i in range(k)]


def _numden(ev, n: A.Call, ctx):
    """numden(a/b) = [a; b]; a plain number is written as a fraction."""
    from fractions import Fraction

    if len(n.args) != 1:
        raise err("args_count", node=n)
    e = n.args[0]
    while isinstance(e, A.Group):
        e = e.inner
    if isinstance(e, A.BinOp) and e.op == "/":
        return Matrix.column([ev.eval(e.left, ctx), ev.eval(e.right, ctx)])
    q = need_scalar(ev.eval(e, ctx))
    fr = Fraction(q.real).limit_denominator(10 ** 9)
    return Matrix.column([Q(float(fr.numerator), q.dims), Q(float(fr.denominator))])


def _trace(ev, n: A.Call, ctx):
    """trace(["text {0} {1}",] a, b...): the values as a string (SMath also
    writes it to its output window)."""
    from .display import value_to_text

    vals = [ev.eval(a, ctx) for a in n.args]
    if vals and isinstance(vals[0], String):
        text = vals[0].text
        for k, v in enumerate(vals[1:]):
            text = text.replace("{%d}" % k, v.text if isinstance(v, String) else value_to_text(v))
        return String(text)
    return String(" ".join(v.text if isinstance(v, String) else value_to_text(v) for v in vals))


def _int(ev, n: A.Call, ctx):
    if len(n.args) != 4:
        raise err("args_count", node=n)
    expr, var, lo, hi = n.args
    a, b = need_scalar(ev.eval(lo, ctx)), need_scalar(ev.eval(hi, ctx))
    if a.dims != b.dims:
        raise err("units_mismatch", node=n)
    N = 2000
    h = (b.real - a.real) / N
    total = 0.0
    dims = None
    for k in range(N + 1):
        x = a.real + k * h
        f = _with_var(ev, ctx, expr, var, Q(x, a.dims))
        dims = f.dims
        w = 1 if k in (0, N) else (4 if k % 2 else 2)
        total += w * f.value
    return _out(total * h / 3, tuple(p + q for p, q in zip(dims, a.dims)))


def _solve(ev, n: A.Call, ctx):
    if len(n.args) not in (2, 4):
        raise err("args_count", node=n)
    expr, var = n.args[0], n.args[1]
    if isinstance(expr, A.BinOp) and expr.op == "≡":
        expr = A.BinOp("-", expr.left, expr.right)
    if len(n.args) == 4:
        lo, hi = need_real(ev.eval(n.args[2], ctx)), need_real(ev.eval(n.args[3], ctx))
    else:
        lo, hi = -1e3, 1e3
    samples = 4000
    roots = []
    f = lambda x: _with_var(ev, ctx, expr, var, Q(x)).real
    prev_x, prev = lo, f(lo)
    for k in range(1, samples + 1):
        x = lo + (hi - lo) * k / samples
        y = f(x)
        if prev == 0:
            roots.append(prev_x)
        elif prev * y < 0:
            a, b, fa = prev_x, x, prev
            for _ in range(200):
                m = (a + b) / 2
                fm = f(m)
                if fa * fm <= 0:
                    b = m
                else:
                    a, fa = m, fm
            roots.append((a + b) / 2)
        prev_x, prev = x, y
    if not roots:
        raise err("no_solution", node=n)
    if len(roots) == 1:
        return Q(roots[0])
    return Matrix.column([Q(r) for r in roots])


def _isdefined(ev, n: A.Call, ctx):
    try:
        ev.eval(n.args[0], ctx)
        return Q(1.0)
    except SMathError:
        return Q(0.0)


def _eval_fn(ev, n: A.Call, ctx):
    return ev.eval(n.args[0], ctx)


def _vectorize(ev, n: A.Call, ctx):
    return ev.eval(n.args[0], ctx)


def _clear(ev, n: A.Call, ctx):
    for a in n.args:
        if isinstance(a, A.Var):
            ctx.vars.pop(a.name, None)
    return Q(1.0)


def _sys(ev, n: A.Call, ctx):
    return Matrix.column([ev.eval(a, ctx) for a in n.args[:-2]] if len(n.args) > 2 else [ev.eval(a, ctx) for a in n.args])


SPECIAL = {
    "if": _if,
    "line": _line,
    "while": _while,
    "for": _for,
    "break": _break,
    "continue": _continue,
    "try": _try,
    "sum": _sum,
    "product": _product,
    "diff": _diff,
    "Jacob": _jacob,
    "roots": _roots,
    "numden": _numden,
    "trace": _trace,
    "int": _int,
    "solve": _solve,
    "IsDefined": _isdefined,
    "eval": _eval_fn,
    "vectorize": _vectorize,
    "Clear": _clear,
    "sys": _sys,
}


from . import extra_functions  # noqa: E402,F401  (plugin functions: eigenvals, fft, delta...)
from . import files  # noqa: E402,F401  (importData, exportData.CSV)
