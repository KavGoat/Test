"""Symbolic functions through SymPy: lim, expand, factor, and solve giving
formulas when an equation holds letters without a value.  (They are not in
SMath Cloud's autocomplete list; EXTRA_FUNCTIONS names them.)"""
from __future__ import annotations

from .builtins import fn  # noqa: F401  (the function table)
from .catalog import FUNCTIONS
from .errors import err
from .units import NODIM
from .values import Matrix, Q

EXTRA_FUNCTIONS: set = set()


# ---------------------------------------------------------------------------
# lim(f, x, a): a limit, numerically - and never a silently wrong one
# ---------------------------------------------------------------------------
import math as _math  # noqa: E402

from . import ast as A  # noqa: E402
from .builtins import SPECIAL, _with_var  # noqa: E402
from .errors import SMathError  # noqa: E402

FUNCTIONS.append(("lim", 3, "Unknown",
                  'lim("1:expression", "2:variable", "3:number") — The limit of "1:expression" as "2:variable" '
                  'approaches "3:number" (which may be ∞ or -∞). An error is shown when the limit does not exist '
                  "or cannot be determined reliably."))
EXTRA_FUNCTIONS.add("lim")

NO_LIMIT = "The limit does not exist or cannot be determined."


def _richardson(values: list) -> list:
    """Two rounds of Richardson extrapolation for samples at steps halving
    each time (errors ~ c1·h + c2·h²)."""
    e1 = [2 * values[j + 1] - values[j] for j in range(len(values) - 1)]
    return [(4 * e1[j + 1] - e1[j]) / 3 for j in range(len(e1) - 1)]


def _settled(values: list):
    """The limit a run of samples converges to, or None.  Accepted only when
    three successive extrapolated estimates agree to about 9 digits."""
    ok = [v for v in values if v is not None and _math.isfinite(v)]
    if len(ok) < 8 or len(ok) != len(values):
        return None
    est = _richardson(ok)
    best = None
    for j in range(len(est) - 2):
        a, b, c = est[j], est[j + 1], est[j + 2]
        scale = max(1.0, abs(b))
        if abs(a - b) <= 1e-9 * scale and abs(b - c) <= 1e-9 * scale:
            best = b
            break
    if best is None:
        return None
    # the raw samples must be heading there too (guards against oscillation)
    tail = ok[-6:]
    if max(abs(v - best) for v in tail) > 1e-4 * max(1.0, abs(best)):
        return None
    return 0.0 if abs(best) < 1e-12 else best


def _blows_up(values: list):
    """+1 or -1 when the samples grow without bound with one sign, else None."""
    ok = [v for v in values if v is not None]
    if len(ok) < 10:
        return None
    tail = ok[-10:]
    if any(not _math.isfinite(v) for v in tail[:-1]):
        return None
    sign = 1 if tail[-1] > 0 else -1
    grows = all(abs(tail[k + 1]) > 1.3 * abs(tail[k]) and tail[k] * sign > 0 for k in range(len(tail) - 1))
    return sign if grows and abs(tail[-1]) > 1e6 else None


def _lim(ev, n: A.Call, ctx):
    from .builtins import need_scalar

    if len(n.args) != 3:
        raise err("args_count", node=n)
    expr, var, point = n.args
    if not isinstance(var, A.Var):
        raise err("syntax", node=var)
    a = need_scalar(ev.eval(point, ctx))
    dims = a.dims
    av = a.real

    def f(x):
        try:
            v = _with_var(ev, ctx, expr, var, Q(x, dims))
        except SMathError:
            return None, None
        if isinstance(v.value, complex) and abs(v.value.imag) > 1e-12 * max(1.0, abs(v.value.real)):
            raise SMathError(NO_LIMIT, n)
        return v.real, v.dims

    out_dims = None
    sides = []
    if _math.isinf(av):
        # x -> ±∞: samples at x = ±2^j, a function of u = 1/x -> 0
        pts = [av / abs(av) * 2.0 ** j for j in range(4, 44)]
        runs = [pts]
    else:
        s = max(1.0, abs(av))
        runs = [[av + sg * s * 2.0 ** -j for j in range(4, 44)] for sg in (-1, 1)]
    for xs in runs:
        vals = []
        for x in xs:
            v, d = f(x)
            vals.append(v)
            if d is not None:
                out_dims = d
        sides.append(vals)
    results = []
    for vals in sides:
        v = _settled(vals)
        if v is None:
            up = _blows_up(vals)
            if up is None:
                raise SMathError(NO_LIMIT, n)
            v = up * _math.inf
        results.append(v)
    if len(results) == 2:
        l, r = results
        if _math.isinf(l) or _math.isinf(r):
            if l != r:
                raise SMathError(NO_LIMIT, n)  # 1/x at 0: -∞ from the left, +∞ from the right
        elif abs(l - r) > 1e-7 * max(1.0, abs(l), abs(r)):
            raise SMathError(NO_LIMIT, n)  # a jump
    v = results[-1] if len(results) == 1 else (results[0] + results[1]) / 2 if not _math.isinf(results[0]) else results[0]
    return Q(v, out_dims or NODIM)


def _as_value(ev, node, ctx):
    """A symbolic answer as a value: a number when nothing in it is unknown,
    otherwise the expression itself."""
    from .symbolic import Expr

    try:
        return ev.eval(node, ctx)
    except SMathError:
        return Expr(node)


def _lim_any(ev, n: A.Call, ctx):
    """lim: exact with SymPy; the strict numeric method only when SymPy
    cannot take the expression (e.g. a programmed function)."""
    from . import sym
    from .symbolic import Expr, NotSymbolic

    if len(n.args) != 3 or not isinstance(n.args[1], A.Var):
        raise err("args_count", node=n)
    expr, var, point = n.args
    try:
        v = sym.limit_value(expr, var.name, point, ctx)
    except sym.NoLimit:
        raise SMathError(NO_LIMIT, n) from None
    except NotSymbolic:
        return _lim(ev, n, ctx)
    sp = sym.sympy()
    if v.free_symbols:
        return Expr(sym.from_sympy(v))
    if v in (sp.oo, -sp.oo):
        return Q(_math.inf if v == sp.oo else -_math.inf)
    return _as_value(ev, sym.from_sympy(v), ctx)


def _sym_fn(kind):
    def run(ev, n: A.Call, ctx):
        from . import sym
        from .symbolic import NotSymbolic

        if len(n.args) not in (1, 2):
            raise err("args_count", node=n)
        try:
            node = (sym.expand_expr if kind == "expand" else sym.factor_expr)(n.args[0], ctx)
        except NotSymbolic:
            raise SMathError("This expression cannot be evaluated symbolically.", n) from None
        return _as_value(ev, node, ctx)

    return run


_numeric_solve = SPECIAL["solve"]


def _solve_any(ev, n: A.Call, ctx):
    """solve: numerically as before; symbolically (exact formulas) when the
    equation holds other letters that have no value, e.g. solve(a·x+b, x)."""
    from . import sym
    from .evaluator import _is_not_defined
    from .symbolic import NotSymbolic

    try:
        return _numeric_solve(ev, n, ctx)
    except SMathError as e:
        if not _is_not_defined(e) or len(n.args) != 2 or not isinstance(n.args[1], A.Var):
            raise
        try:
            sols = sym.solve_expr(n.args[0], n.args[1].name, ctx)
        except NotSymbolic:
            raise e from None
        if not sols:
            raise err("no_solution", node=n) from None
        vals = [_as_value(ev, s, ctx) for s in sols]
        return vals[0] if len(vals) == 1 else Matrix.column(vals)


FUNCTIONS.extend([
    ("expand", 1, "Unknown", 'expand("expression") — Multiplies out products and powers of sums (symbolic).'),
    ("factor", 1, "Unknown", 'factor("expression") — Writes a polynomial as a product of factors (symbolic).'),
])
EXTRA_FUNCTIONS.update({"expand", "factor"})
SPECIAL["lim"] = _lim_any
SPECIAL["expand"] = _sym_fn("expand")
SPECIAL["factor"] = _sym_fn("factor")
SPECIAL["solve"] = _solve_any
