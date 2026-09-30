"""The bridge to SymPy behind symbolic(): the only place the worksheet
evaluates symbolically.  Inside symbolic(...), diff, int, sum, product,
solve and lim give formulas; everywhere else the worksheet is numeric.

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


class NoSolution(NotSymbolic):
    """solve found no solution."""

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
_WORKSHEET_FUNCS = {"sin", "cos", "tan", "cot", "sec", "csc", "asin", "acos", "atan", "acot", "sinh", "cosh",
                    "tanh", "coth", "asinh", "acosh", "atanh", "exp", "ln", "sqrt", "abs", "sign", "floor",
                    "ceil", "Gamma", "Re", "Im"}


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


def to_sympy(n: A.Node, ctx=None, ev=None):
    """A worksheet expression as a SymPy expression.  With an evaluator, a
    part SymPy cannot read (an index v[2], a programmed function...) is
    used by its numeric value when it holds no free letters."""
    from . import symbolic as S

    sp = sympy()
    if ctx is not None:
        n = S.expand(n, ctx)
    return _Tr(ctx, ev, sp).to(n)


def _free_names(n: A.Node, ctx, bound) -> set:
    from .evaluator import BUILTIN_CONSTANTS

    out = set()
    for m in A.walk(n):
        if isinstance(m, A.Var) and m.name not in BUILTIN_CONSTANTS:
            if m.name in bound or ctx is None or ctx.lookup(m.name) is None:
                out.add(m.name)
    return out


def _value(v, sp):
    """A computed worksheet value as SymPy."""
    from .units import Quantity
    from .values import Matrix

    if isinstance(v, Quantity):
        return _quantity(v)
    if isinstance(v, Matrix):
        return sp.Matrix(v.nrows, v.ncols, [_value(x, sp) for x in v.items])
    raise NotSymbolic(type(v).__name__)


class _Tr:
    """Translation to SymPy.  ``bound`` holds the variables of the diff,
    int, sum, product, lim and solve being translated: inside them the
    letter is free even when the worksheet gives it a value."""

    def __init__(self, ctx, ev, sp):
        self.ctx, self.ev, self.sp = ctx, ev, sp
        self.bound: set = set()

    def to(self, n):
        try:
            return _to(n, self.ctx, self.sp, self)
        except (NoLimit, NoSolution):
            raise
        except NotSymbolic:
            # a numeric part (v[2], a programmed function) with no free
            # letters: its value is exact enough to use
            if self.ev is None or isinstance(n, (A.Num, A.Var, A.UnitRef)) or _free_names(n, self.ctx, self.bound):
                raise
            from .errors import SMathError

            try:
                return _value(self.ev.eval(n, self.ctx), self.sp)
            except SMathError:
                raise NotSymbolic("cannot evaluate") from None

    def var(self, node) -> object:
        if not isinstance(node, A.Var):
            raise NotSymbolic("variable expected")
        return self.sp.Symbol(node.name)

    def with_bound(self, name, node):
        added = name not in self.bound
        self.bound.add(name)
        try:
            return self.to(node)
        finally:
            if added:
                self.bound.discard(name)

    def call(self, n: A.Call):
        """diff, int, sum, product, lim and solve, symbolically."""
        sp = self.sp
        name, args = n.name, n.args
        if name == "diff" and len(args) in (2, 3):
            x = self.var(args[1])
            order = int(self.to(args[2])) if len(args) == 3 else 1
            if order < 1:
                raise NotSymbolic("order")
            return sp.diff(self.with_bound(x.name, args[0]), x, order)
        if name == "int" and len(args) in (2, 4):
            x = self.var(args[1])
            f = self.with_bound(x.name, args[0])
            if len(args) == 2:
                r = sp.integrate(f, x)
            else:
                r = sp.integrate(f, (x, self.to(args[2]), self.to(args[3])))
            if r.has(sp.Integral):
                raise NotSymbolic("integral not found")
            return r
        if name in ("sum", "product") and len(args) == 4:
            i = self.var(args[1])
            f = self.with_bound(i.name, args[0])
            lims = (i, self.to(args[2]), self.to(args[3]))
            r = sp.summation(f, lims) if name == "sum" else sp.product(f, lims)
            if r.has(sp.Sum) or r.has(sp.Product):
                r = r.doit()
            if r.has(sp.Sum) or r.has(sp.Product):
                raise NotSymbolic("no closed form")
            return r
        if name == "lim" and len(args) == 3:
            x = self.var(args[1])
            return _limit(self.with_bound(x.name, args[0]), x, self.to(args[2]), sp)
        if name == "solve" and len(args) == 2:
            x = self.var(args[1])
            e = self.with_bound(x.name, args[0])
            if isinstance(e, sp.Equality):
                e = e.lhs - e.rhs
            try:
                sols = sp.solve(e, x)
            except (NotImplementedError, ValueError, TypeError) as ex:
                raise NotSymbolic(str(ex)) from None
            if not sols:
                raise NoSolution("no solution")
            return sols[0] if len(sols) == 1 else sp.Matrix(sols)
        return None


def _to(n, ctx, sp, tr=None):
    from .evaluator import BUILTIN_CONSTANTS, Lazy
    from .symbolic import Expr
    from .units import Quantity
    from .values import Matrix

    if tr is None:
        tr = _Tr(ctx, None, sp)
    if tr.bound and isinstance(n, A.Var) and n.name in tr.bound:
        return sp.Symbol(n.name)
    if isinstance(n, A.Num):
        return _num(n.text)
    if isinstance(n, A.Group):
        return tr.to(n.inner)
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
            return tr.to(v.node)
        if isinstance(v, Lazy):
            return tr.to(v.node)
        if isinstance(v, Matrix):
            return sp.Matrix(v.nrows, v.ncols, [_quantity(x) for x in v.items])
        if v is not None:
            raise NotSymbolic(n.name)
        if n.name in defined_above():
            raise NotSymbolic(f"{n.name} is defined above but has no value")
        return sp.Symbol(n.name)
    if isinstance(n, A.Unary):
        a = tr.to(n.arg)
        if n.op == "-":
            return -a
        if n.op == "+":
            return a
        if n.op == "!":
            return sp.factorial(a)
        raise NotSymbolic(n.op)
    if isinstance(n, A.BinOp):
        a, b = tr.to(n.left), tr.to(n.right)
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
        special = tr.call(n)
        if special is not None:
            return special
        args = [tr.to(x) for x in n.args]
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
        return sp.Matrix(n.nrows, n.ncols, [tr.to(c) for c in n.cells])
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


def _is_unit(f) -> bool:
    base = f.as_base_exp()[0]
    return bool(base.is_Symbol and base.name.startswith("'"))


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
        # units after the rest, as they are written: a·kN, not kN·a
        factors = sorted(e.as_ordered_factors(), key=lambda f: _is_unit(f))
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
    if isinstance(e, sp.exp):
        arg = e.args[0]
        return A.BinOp("^", A.Var("e"), _from(arg, sp))  # e^x, as SMath writes it
    if isinstance(e, sp.log) and len(e.args) == 1:
        return A.Call("ln", [_from(e.args[0], sp)])
    if isinstance(e, sp.factorial):
        arg = e.args[0]
        return A.Unary("!", _wrap(_from(arg, sp), not (arg.is_Symbol or (arg.is_Integer and arg >= 0))))
    if isinstance(e, (sp.Max, sp.Min)):
        return A.Call("max" if isinstance(e, sp.Max) else "min", [_from(a, sp) for a in e.args])
    if e.is_Function:
        # only functions the worksheet has: an answer in terms of anything
        # else (Piecewise, erf, LambertW...) is not shown
        name = type(e).__name__
        name = _BACK.get(name, name)
        if name not in _WORKSHEET_FUNCS:
            raise NotSymbolic(name)
        return A.Call(name, [_from(a, sp) for a in e.args])
    raise NotSymbolic(str(e))


# -- operations ------------------------------------------------------------------------------

MODES = ("simplify", "expand", "factor")


def _limit(e, x, a, sp):
    """The limit, exactly; NoLimit when it does not exist, NotSymbolic when
    SymPy cannot decide."""
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


def symbolic(n: A.Node, ctx, ev=None, mode: str = "simplify"):
    """symbolic(expr[, mode]): the expression worked out symbolically, as a
    SymPy expression (a Matrix for several solutions or a matrix)."""
    sp = sympy()
    if mode not in MODES:
        raise NotSymbolic("mode")
    e = to_sympy(n, ctx, ev)
    if ctx is not None:
        # the variable of a diff/int/solve left in the answer takes its
        # worksheet value when it has one (x:=2: diff(x^2,x) -> 4)
        tr = _Tr(ctx, ev, sp)
        subs = {}
        for s in e.free_symbols:
            if not s.name.startswith("'") and ctx.lookup(s.name) is not None:
                subs[s] = tr.to(A.Var(s.name))
        if subs:
            e = e.subs(subs)
    how = {"simplify": sp.simplify, "expand": sp.expand, "factor": sp.factor}[mode]
    e = e.applyfunc(how) if isinstance(e, sp.MatrixBase) else how(e)
    if e.has(sp.zoo) or e.has(sp.nan):
        raise NotSymbolic("undefined")
    return e


def is_formula(e) -> bool:
    """True when a symbolic result still holds letters (not only units)."""
    return any(not s.name.startswith("'") for s in e.free_symbols)
