"""Symbolic differentiation (diff, Jacob, Calculation > Differentiate).

SMath differentiates symbolically: diff(x^3, x) shows 3·x² when x has no
value, and the number when x is defined.  The derivative is built on the
expression tree with the usual rules (sum, product, quotient, power and
chain rules, and the derivatives of the elementary functions), then tidied
by :func:`simplify` (constant folding, 0 and 1 rules, collecting numeric
factors).  User functions are expanded with their definitions first.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import ast as A


class NotSymbolic(Exception):
    """The expression contains something that cannot be differentiated."""


@dataclass
class Expr:
    """A symbolic result (a value that is an expression), e.g. diff(x^3,x)."""

    node: A.Node


# -- helpers ---------------------------------------------------------------------------

def num(v: float) -> A.Node:
    if v < 0:
        return A.Unary("-", num(-v))
    if float(v).is_integer():
        return A.Num(str(int(v)))
    return A.Num(repr(float(v)))


def _val(n: A.Node):
    """The number a node stands for, or None."""
    if isinstance(n, A.Num):
        try:
            return float(n.text)
        except ValueError:
            return None
    if isinstance(n, A.Unary) and n.op == "-":
        v = _val(n.arg)
        return -v if v is not None else None
    if isinstance(n, A.Group):
        return _val(n.inner)
    return None


def depends(n: A.Node, var: str) -> bool:
    return any(isinstance(m, A.Var) and m.name == var for m in A.walk(n))


def B(op, l, r):
    return A.BinOp(op, l, r)


def call(name, *args):
    return A.Call(name, list(args))


# -- expansion of user functions --------------------------------------------------------------

def expand(n: A.Node, ctx, depth: int = 0) -> A.Node:
    """Replace calls to user functions by their bodies (with the arguments
    substituted), so f(x):=x^2 can be differentiated as x^2."""
    if depth > 30:
        raise NotSymbolic("recursion")
    if isinstance(n, A.Call):
        args = [expand(a, ctx, depth) for a in n.args]
        f = ctx.function(n.name, len(args)) if ctx is not None else None
        if f is not None and getattr(f, "body", None) is not None:
            body = substitute(f.body, dict(zip(f.params, args)))
            return A.Group(expand(body, ctx, depth + 1))
        return A.Call(n.name, args)
    if isinstance(n, A.Var) and ctx is not None:
        # a definition kept symbolically (y:=x^2 with x undefined) is used as is
        from .evaluator import Lazy

        v = ctx.lookup(n.name)
        if isinstance(v, Lazy):
            return A.Group(expand(v.node, ctx, depth + 1))
        return n
    if isinstance(n, A.Group):
        return A.Group(expand(n.inner, ctx, depth))
    if isinstance(n, A.BinOp):
        return A.BinOp(n.op, expand(n.left, ctx, depth), expand(n.right, ctx, depth))
    if isinstance(n, A.Unary):
        return A.Unary(n.op, expand(n.arg, ctx, depth))
    if isinstance(n, A.MatrixLit):
        return A.MatrixLit(n.nrows, n.ncols, [expand(c, ctx, depth) for c in n.cells])
    return n


def substitute(n: A.Node, env: dict) -> A.Node:
    if isinstance(n, A.Var):
        return A.Group(env[n.name]) if n.name in env else n
    if isinstance(n, A.Call):
        return A.Call(n.name, [substitute(a, env) for a in n.args])
    if isinstance(n, A.Group):
        return A.Group(substitute(n.inner, env))
    if isinstance(n, A.BinOp):
        return A.BinOp(n.op, substitute(n.left, env), substitute(n.right, env))
    if isinstance(n, A.Unary):
        return A.Unary(n.op, substitute(n.arg, env))
    if isinstance(n, A.MatrixLit):
        return A.MatrixLit(n.nrows, n.ncols, [substitute(c, env) for c in n.cells])
    return n


# -- derivative ------------------------------------------------------------------------------

def derivative(n: A.Node, var: str, order: int = 1) -> A.Node:
    for _ in range(order):
        n = simplify(_d(n, var))
    return n


def _d(n: A.Node, x: str) -> A.Node:
    if not depends(n, x):
        return A.Num("0")
    if isinstance(n, A.Var):
        return A.Num("1")
    if isinstance(n, A.Group):
        return _d(n.inner, x)
    if isinstance(n, A.Unary):
        if n.op == "-":
            return A.Unary("-", _d(n.arg, x))
        if n.op == "+":
            return _d(n.arg, x)
        raise NotSymbolic(n.op)
    if isinstance(n, A.MatrixLit):
        return A.MatrixLit(n.nrows, n.ncols, [_d(c, x) for c in n.cells])
    if isinstance(n, A.BinOp):
        u, v = n.left, n.right
        if n.op in ("+", "-"):
            return B(n.op, _d(u, x), _d(v, x))
        if n.op == "*":
            if not depends(u, x):
                return B("*", u, _d(v, x))
            if not depends(v, x):
                return B("*", _d(u, x), v)
            return B("+", B("*", _d(u, x), v), B("*", u, _d(v, x)))
        if n.op == "/":
            if not depends(v, x):
                return B("/", _d(u, x), v)
            return B("/", B("-", B("*", _d(u, x), v), B("*", u, _d(v, x))), B("^", A.Group(v), A.Num("2")))
        if n.op == "^":
            if not depends(v, x):
                # n·u^(n-1)·u'
                return B("*", B("*", v, B("^", u, simplify(B("-", v, A.Num("1"))))), _d(u, x))
            if not depends(u, x):
                return B("*", B("*", n, call("ln", u)), _d(v, x))
            return B("*", n, B("+", B("*", _d(v, x), call("ln", u)), B("/", B("*", v, _d(u, x)), u)))
        raise NotSymbolic(n.op)
    if isinstance(n, A.Call):
        return _d_call(n, x)
    raise NotSymbolic(type(n).__name__)


def _d_call(n: A.Call, x: str) -> A.Node:
    name, args = n.name, n.args
    if name == "log" and len(args) == 2:
        u, b = args
        if depends(b, x):
            return _d(B("/", call("ln", u), call("ln", b)), x)
        return B("/", _d(u, x), B("*", u, call("ln", b)))
    if name == "nthroot" and len(args) == 2:
        u, k = args
        return _d(B("^", u, B("/", A.Num("1"), k)), x)
    if len(args) != 1:
        raise NotSymbolic(name)
    u = args[0]
    du = _d(u, x)
    one = A.Num("1")
    rules = {
        "sin": lambda: call("cos", u),
        "cos": lambda: A.Unary("-", call("sin", u)),
        "tan": lambda: B("/", one, B("^", call("cos", u), A.Num("2"))),
        "cot": lambda: A.Unary("-", B("/", one, B("^", call("sin", u), A.Num("2")))),
        "sec": lambda: B("*", call("sec", u), call("tan", u)),
        "csc": lambda: A.Unary("-", B("*", call("csc", u), call("cot", u))),
        "exp": lambda: call("exp", u),
        "ln": lambda: B("/", one, u),
        "log10": lambda: B("/", one, B("*", u, call("ln", A.Num("10")))),
        "sqrt": lambda: B("/", one, B("*", A.Num("2"), call("sqrt", u))),
        "sinh": lambda: call("cosh", u),
        "cosh": lambda: call("sinh", u),
        "tanh": lambda: B("/", one, B("^", call("cosh", u), A.Num("2"))),
        "coth": lambda: A.Unary("-", B("/", one, B("^", call("sinh", u), A.Num("2")))),
        "asin": lambda: B("/", one, call("sqrt", B("-", one, B("^", u, A.Num("2"))))),
        "acos": lambda: A.Unary("-", B("/", one, call("sqrt", B("-", one, B("^", u, A.Num("2")))))),
        "atan": lambda: B("/", one, B("+", one, B("^", u, A.Num("2")))),
        "acot": lambda: A.Unary("-", B("/", one, B("+", one, B("^", u, A.Num("2"))))),
        "asinh": lambda: B("/", one, call("sqrt", B("+", B("^", u, A.Num("2")), one))),
        "acosh": lambda: B("/", one, call("sqrt", B("-", B("^", u, A.Num("2")), one))),
        "atanh": lambda: B("/", one, B("-", one, B("^", u, A.Num("2")))),
        "abs": lambda: call("sign", u),
    }
    if name not in rules:
        raise NotSymbolic(name)
    return B("*", rules[name](), du)


# -- simplification -------------------------------------------------------------------------------

def simplify(n: A.Node) -> A.Node:
    for _ in range(12):
        m = _s(n)
        if _same(m, n):
            return m
        n = m
    return n


def _same(a, b) -> bool:
    from ..astitems import ast_to_items  # structural comparison via text

    try:
        from .model import Row

        return Row(ast_to_items(a)).text() == Row(ast_to_items(b)).text()
    except Exception:
        return a is b


def _s(n: A.Node) -> A.Node:
    if isinstance(n, A.Group):
        inner = _s(n.inner)
        if isinstance(inner, (A.Num, A.Var, A.Call, A.Group, A.UnitRef)):
            return inner
        return inner  # brackets are re-created where precedence needs them
    if isinstance(n, A.Unary):
        a = _s(n.arg)
        if n.op == "-":
            v = _val(a)
            if v is not None:
                return num(-v)
            if isinstance(a, A.Unary) and a.op == "-":
                return a.arg
        return A.Unary(n.op, a)
    if isinstance(n, A.Call):
        args = [_s(a) for a in n.args]
        if n.name == "ln" and len(args) == 1 and isinstance(args[0], A.Var) and args[0].name == "e":
            return A.Num("1")
        vals = [_val(a) for a in args]
        if n.name in _FOLD and all(v is not None for v in vals) and len(vals) == 1:
            try:
                r = _FOLD[n.name](vals[0])
                if float(r).is_integer():
                    return num(r)
            except (ValueError, OverflowError):
                pass
        return A.Call(n.name, args)
    if isinstance(n, A.MatrixLit):
        return A.MatrixLit(n.nrows, n.ncols, [_s(c) for c in n.cells])
    if not isinstance(n, A.BinOp):
        return n
    l, r = _s(n.left), _s(n.right)
    lv, rv = _val(l), _val(r)
    op = n.op
    if lv is not None and rv is not None and op in "+-*/^":
        try:
            v = {"+": lambda: lv + rv, "-": lambda: lv - rv, "*": lambda: lv * rv,
                 "/": lambda: lv / rv, "^": lambda: lv ** rv}[op]()
            if isinstance(v, float) and math.isfinite(v) and (float(v).is_integer() or op in "+-*"):
                return num(v)
        except (ZeroDivisionError, OverflowError, ValueError):
            pass
    if op == "+":
        if lv == 0:
            return r
        if rv == 0:
            return l
        if isinstance(r, A.Unary) and r.op == "-":
            return B("-", l, r.arg)
        if rv is not None and rv < 0:
            return B("-", l, num(-rv))
    if op == "-":
        if rv == 0:
            return l
        if lv == 0:
            return A.Unary("-", r)
        if isinstance(r, A.Unary) and r.op == "-":
            return B("+", l, r.arg)
        if _same(l, r):
            return A.Num("0")
    if op == "*":
        if lv == 0 or rv == 0:
            return A.Num("0")
        if lv == 1:
            return r
        if rv == 1:
            return l
        if lv == -1:
            return A.Unary("-", r)
        if rv == -1:
            return A.Unary("-", l)
        # numbers first: x·3 -> 3·x, 2·(3·x) -> 6·x
        if rv is not None and lv is None:
            return B("*", r, l)
        if lv is not None and isinstance(r, A.BinOp) and r.op == "*" and _val(r.left) is not None:
            return B("*", num(lv * _val(r.left)), r.right)
        if lv is None and isinstance(r, A.BinOp) and r.op == "*" and _val(r.left) is not None:
            return B("*", r.left, B("*", l, r.right))  # a·(2·x) -> 2·(a·x)
        if lv is None and isinstance(l, A.BinOp) and l.op == "*" and _val(l.right) is not None:
            return B("*", l.right, B("*", l.left, r))
        if isinstance(l, A.Unary) and l.op == "-":
            return A.Unary("-", B("*", l.arg, r))
        if isinstance(r, A.Unary) and r.op == "-":
            return A.Unary("-", B("*", l, r.arg))
        if isinstance(l, A.BinOp) and l.op == "/" and _val(l.left) == 1:
            return B("/", r, l.right)
        if isinstance(r, A.BinOp) and r.op == "/" and _val(r.left) == 1:
            return B("/", l, r.right)
    if op == "/":
        if lv == 0:
            return A.Num("0")
        if rv == 1:
            return l
        if isinstance(l, A.Unary) and l.op == "-":
            return A.Unary("-", B("/", l.arg, r))
    if op == "^":
        if rv == 0:
            return A.Num("1")
        if rv == 1:
            return l
        if lv == 1:
            return A.Num("1")
    return B(op, l, r)


_FOLD = {"sin": math.sin, "cos": math.cos, "exp": math.exp, "ln": math.log, "sqrt": math.sqrt,
         "sign": lambda v: (v > 0) - (v < 0)}


def to_row(n: A.Node):
    from ..astitems import ast_to_items
    from .model import Row

    return Row(ast_to_items(n))
