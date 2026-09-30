"""The bridge to SymPy for symbolic results: → (symbolic evaluation),
expand(), factor(), symbolic solve() and lim().

Worksheet expressions are translated to SymPy and back.  Numbers are taken
exactly (1.35 is 27/20), user functions and symbolic definitions are
expanded first, defined variables use their values, undefined names stay
symbols, and units are symbols (so 5·kg stays 5·kg).  Anything SymPy
cannot represent raises NotSymbolic, and the caller falls back or reports
it - a symbolic result is never guessed.
"""
from __future__ import annotations

from fractions import Fraction

from . import ast as A
from .symbolic import NotSymbolic


class NoLimit(NotSymbolic):
    """The limit does not exist (one-sided limits differ, oscillation)."""

_sp = None

# names the worksheet defines above the region being calculated (set by the
# worksheet): such a name without a value here is a failed or partial
# definition, and taking it as a free symbol would give a wrong answer
defined_above = lambda: set()  # noqa: E731


def sympy():
    global _sp
    if _sp is None:
        try:
            import sympy as sp
        except ImportError as e:  # pragma: no cover - sympy is a requirement
            raise NotSymbolic("sympy is not installed") from e
        _sp = sp
    return _sp


# worksheet name -> sympy function
def _funcs():
    sp = sympy()
    return {
        "sin": sp.sin, "cos": sp.cos, "tan": sp.tan, "cot": sp.cot, "sec": sp.sec, "csc": sp.csc,
        "asin": sp.asin, "acos": sp.acos, "atan": sp.atan, "acot": sp.acot,
        "sinh": sp.sinh, "cosh": sp.cosh, "tanh": sp.tanh, "coth": sp.coth,
        "asinh": sp.asinh, "acosh": sp.acosh, "atanh": sp.atanh,
        "exp": sp.exp, "ln": sp.log, "log10": lambda x: sp.log(x, 10), "sqrt": sp.sqrt,
        "abs": sp.Abs, "sign": sp.sign, "floor": sp.floor, "ceil": sp.ceiling, "Gamma": sp.gamma,
        "Re": sp.re, "Im": sp.im,
    }


_BACK = {"log": "ln", "Abs": "abs", "ceiling": "ceil", "gamma": "Gamma", "re": "Re", "im": "Im"}


def _num(text: str):
    sp = sympy()
    try:
        return sp.Rational(Fraction(text))  # exact: 1.35 -> 27/20
    except (ValueError, ZeroDivisionError):
        raise NotSymbolic(text) from None


def _quantity(q):
    """A worksheet value as SymPy: the number (exact when it is a short
    decimal) times its SI base units as symbols."""
    sp = sympy()
    from .units import BASE

    v = q.value
    if isinstance(v, complex):
        x = _real_number(v.real, sp) + sp.I * _real_number(v.imag, sp)
    else:
        x = _real_number(float(v), sp)
    for base, e in zip(BASE, q.dims):
        if e:
            x = x * sp.Symbol("'" + base, positive=True) ** sp.nsimplify(e)
    return x


def _real_number(v: float, sp):
    """A computed number as SymPy: the simple fraction it is within 1e-12 of
    (0.7999999999999999 -> 4/5, the result of 4/5 in floating point),
    otherwise its decimal value."""
    import math

    if not math.isfinite(v):
        return sp.oo if v > 0 else (-sp.oo if v < 0 else sp.nan)
    fr = Fraction(v).limit_denominator(10 ** 6)
    if abs(float(fr) - v) <= 1e-12 * max(1.0, abs(v)):
        return sp.Rational(fr.numerator, fr.denominator)
    return sp.Float(repr(v), 17)


def to_sympy(n: A.Node, ctx=None):
    """A worksheet expression as a SymPy expression."""
    from . import symbolic as S

    sp = sympy()
    if ctx is not None:
        n = S.expand(n, ctx)
    return _to(n, ctx, sp)


def _to(n, ctx, sp):
    from .evaluator import BUILTIN_CONSTANTS, Lazy
    from .symbolic import Expr
    from .units import Quantity
    from .values import Matrix

    if isinstance(n, A.Num):
        return _num(n.text)
    if isinstance(n, A.Group):
        return _to(n.inner, ctx, sp)
    if isinstance(n, A.UnitRef):
        return sp.Symbol("'" + n.name, positive=True)
    if isinstance(n, A.Var):
        v = ctx.lookup(n.name) if ctx is not None else None
        if v is None and n.name in BUILTIN_CONSTANTS:
            # π, e, i, ∞ exactly (unless the worksheet redefined them)
            return {"π": sp.pi, "e": sp.E, "i": sp.I, "∞": sp.oo}[n.name]
        if isinstance(v, Quantity):
            return _quantity(v)
        if isinstance(v, Expr):
            return _to(v.node, ctx, sp)
        if isinstance(v, Lazy):
            return _to(v.node, ctx, sp)
        if isinstance(v, Matrix):
            return sp.Matrix(v.nrows, v.ncols, [_quantity(x) for x in v.items])
        if v is not None:
            raise NotSymbolic(n.name)
        if n.name in defined_above():
            raise NotSymbolic(f"{n.name} is defined above but has no value")
        return sp.Symbol(n.name)
    if isinstance(n, A.Unary):
        a = _to(n.arg, ctx, sp)
        if n.op == "-":
            return -a
        if n.op == "+":
            return a
        if n.op == "!":
            return sp.factorial(a)
        raise NotSymbolic(n.op)
    if isinstance(n, A.BinOp):
        a, b = _to(n.left, ctx, sp), _to(n.right, ctx, sp)
        op = n.op
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            return a / b
        if op == "^":
            return a ** b
        if op == "≡":
            return sp.Eq(a, b)
        rel = {"<": sp.Lt, ">": sp.Gt, "≤": sp.Le, "≥": sp.Ge, "≠": sp.Ne}.get(op)
        if rel:
            return rel(a, b)
        raise NotSymbolic(op)
    if isinstance(n, A.Call):
        args = [_to(x, ctx, sp) for x in n.args]
        f = _funcs().get(n.name)
        if f is not None and len(args) == 1:
            return f(args[0])
        if n.name == "log" and len(args) == 2:
            return sp.log(args[0], args[1])
        if n.name == "nthroot" and len(args) == 2:
            return sp.root(args[0], args[1])
        if n.name in ("max", "min") and args:
            return (sp.Max if n.name == "max" else sp.Min)(*args)
        raise NotSymbolic(n.name)
    if isinstance(n, A.MatrixLit):
        return sp.Matrix(n.nrows, n.ncols, [_to(c, ctx, sp) for c in n.cells])
    raise NotSymbolic(type(n).__name__)


# -- back to a worksheet expression ------------------------------------------------------------

def from_sympy(e) -> A.Node:
    sp = sympy()
    if isinstance(e, sp.MatrixBase):
        return A.MatrixLit(e.rows, e.cols, [from_sympy(x) for x in e])
    if isinstance(e, sp.Equality):
        return A.BinOp("≡", from_sympy(e.lhs), from_sympy(e.rhs))
    return _from(e, sp)


def _number(e, sp) -> A.Node:
    if e.is_Integer:
        v = int(e)
        return A.Unary("-", A.Num(str(-v))) if v < 0 else A.Num(str(v))
    if e.is_Rational:
        p, q = int(e.p), int(e.q)
        frac = A.BinOp("/", A.Num(str(abs(p))), A.Num(str(q)))
        return A.Unary("-", frac) if p < 0 else frac
    f = float(e)
    text = f"{abs(f):.15g}"
    return A.Unary("-", A.Num(text)) if f < 0 else A.Num(text)


def _wrap(n: A.Node, need: bool) -> A.Node:
    return A.Group(n) if need else n


def _from(e, sp) -> A.Node:
    if e is sp.pi:
        return A.Var("π")
    if e is sp.E:
        return A.Var("e")
    if e is sp.I:
        return A.Var("i")
    if e is sp.oo:
        return A.Var("∞")
    if e is sp.zoo or e is sp.nan:
        raise NotSymbolic("undefined")
    if e == -sp.oo:
        return A.Unary("-", A.Var("∞"))
    if e.is_Number:
        return _number(e, sp)
    if e.is_Symbol:
        name = e.name
        return A.UnitRef(name[1:]) if name.startswith("'") else A.Var(name)
    if e.is_Add:
        terms = e.as_ordered_terms()
        out = _from(terms[0], sp)
        for t in terms[1:]:
            c, rest = t.as_coeff_Mul()
            if c.is_Number and c < 0:
                out = A.BinOp("-", out, _wrap(_from(-t, sp), (-t).is_Add))
            else:
                out = A.BinOp("+", out, _wrap(_from(t, sp), False))
        return out
    if e.is_Mul:
        num, den = e.as_numer_denom()
        if den != 1:
            top = _from(num, sp)
            return A.BinOp("/", top, _from(den, sp))
        c, rest = e.as_coeff_Mul()
        if c.is_Number and c < 0:
            return A.Unary("-", _wrap(_from(-e, sp), (-e).is_Add))
        factors = e.as_ordered_factors()
        out = None
        for f in factors:
            node = _wrap(_from(f, sp), f.is_Add)
            out = node if out is None else A.BinOp("*", out, node)
        return out
    if e.is_Pow:
        base, ex = e.as_base_exp()
        if ex == sp.Rational(1, 2):
            return A.Call("sqrt", [_from(base, sp)])
        if ex.is_Number and ex < 0:
            return A.BinOp("/", A.Num("1"), _from(base ** -ex, sp))
        b = _wrap(_from(base, sp), not (base.is_Symbol or (base.is_Integer and base > 0) or base.is_Function))
        return A.BinOp("^", b, _from(ex, sp))
    if isinstance(e, sp.log) and len(e.args) == 1:
        return A.Call("ln", [_from(e.args[0], sp)])
    if e.is_Function:
        name = type(e).__name__
        return A.Call(_BACK.get(name, name), [_from(a, sp) for a in e.args])
    if isinstance(e, sp.factorial):
        return A.Unary("!", _wrap(_from(e.args[0], sp), True))
    raise NotSymbolic(str(e))


# -- operations ------------------------------------------------------------------------------

def symbolic_value(n: A.Node, ctx):
    """→: the expression simplified symbolically (numbers when everything is
    known).  Returns a worksheet expression node."""
    sp = sympy()
    e = to_sympy(n, ctx)
    e = sp.simplify(e) if not isinstance(e, sp.MatrixBase) else e.applyfunc(sp.simplify)
    return from_sympy(e)


def expand_expr(n: A.Node, ctx) -> A.Node:
    sp = sympy()
    return from_sympy(sp.expand(to_sympy(n, ctx)))


def factor_expr(n: A.Node, ctx) -> A.Node:
    sp = sympy()
    return from_sympy(sp.factor(to_sympy(n, ctx)))


def solve_expr(eq: A.Node, var: str, ctx) -> list:
    """Exact solutions of eq (an equation a≡b, or an expression = 0) for var."""
    sp = sympy()
    e = to_sympy(eq, ctx)
    x = sp.Symbol(var)
    if isinstance(e, sp.Equality):
        e = e.lhs - e.rhs
    sols = sp.solve(e, x)
    return [from_sympy(s) for s in sols]


def limit_value(n: A.Node, var: str, point: A.Node, ctx):
    """The limit, exactly: a SymPy number/expression, or NotSymbolic when it
    does not exist or SymPy cannot decide."""
    sp = sympy()
    e = to_sympy(n, ctx)
    x = sp.Symbol(var)
    a = to_sympy(point, ctx)
    try:
        if a in (sp.oo, -sp.oo):
            v = sp.limit(e, x, a)
        else:
            left, right = sp.limit(e, x, a, dir="-"), sp.limit(e, x, a, dir="+")
            if left == right:
                v = left
            elif not left.is_real and right.is_real:
                v = right  # defined on one side only: sqrt(x) at 0
            elif not right.is_real and left.is_real:
                v = left
            else:
                raise NoLimit("one-sided limits differ")
    except (NotImplementedError, ValueError, TypeError) as ex:
        raise NotSymbolic(str(ex)) from None
    if v.has(sp.AccumBounds) or v.has(sp.zoo) or v.has(sp.nan):
        raise NoLimit("no limit")
    if v.has(sp.Limit):
        raise NotSymbolic("undecided")
    return v
