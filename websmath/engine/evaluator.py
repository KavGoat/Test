"""Evaluate ASTs against a worksheet context, the way SMath does.

The worksheet is evaluated top-to-bottom, left-to-right; each region sees
only what was defined before it.  A definition whose right-hand side refers
to something not yet defined is kept symbolically (``a:=b`` is legal) and
only fails when a value is actually required.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from . import ast as A
from .errors import SMathError, err
from .units import is_unit, unit_offset, unit_quantity


def unit_offset_of(name: str) -> float:
    return unit_offset(name) if is_unit(name) else 0.0
from .values import (Matrix, Q, String, add, compare, div, mul, need_int, need_real, neg,
                     power, sub, truth)


@dataclass
class UserFunction:
    name: str
    params: list  # parameter names
    body: A.Node


@dataclass
class Lazy:
    """A definition kept symbolically because it could not be evaluated yet."""

    node: A.Node


class BreakLoop(Exception):
    pass


class ContinueLoop(Exception):
    pass


BUILTIN_CONSTANTS = {
    "π": Q(math.pi),
    "e": Q(math.e),
    "i": Q(1j),
    "∞": Q(math.inf),
}


class Context:
    def __init__(self, parent: Optional["Context"] = None):
        self.parent = parent
        self.vars: dict = {}
        self.funcs: dict = {}  # (name, nargs) -> UserFunction

    def lookup(self, name: str):
        c = self
        while c is not None:
            if name in c.vars:
                return c.vars[name]
            c = c.parent
        return None

    def has(self, name: str) -> bool:
        c = self
        while c is not None:
            if name in c.vars:
                return True
            c = c.parent
        return False

    def assign(self, name: str, value) -> None:
        """Assign in the scope that already owns the name, else locally."""
        c = self
        while c is not None:
            if name in c.vars:
                c.vars[name] = value
                return
            c = c.parent
        self.vars[name] = value

    def function(self, name: str, nargs: int):
        c = self
        while c is not None:
            f = c.funcs.get((name, nargs))
            if f is not None:
                return f
            c = c.parent
        return None

    def any_function(self, name: str):
        c = self
        while c is not None:
            for (n, k), f in c.funcs.items():
                if n == name:
                    return f
            c = c.parent
        return None

    def names(self) -> set:
        out = set()
        c = self
        while c is not None:
            out |= set(c.vars)
            out |= {n for n, _ in c.funcs}
            c = c.parent
        return out


class Evaluator:
    def __init__(self):
        from . import builtins  # local import: builtins needs Evaluator types

        self.builtins = builtins

    # -- entry points ---------------------------------------------------------
    def define(self, node: A.Define, ctx: Context) -> None:
        target = node.target
        if isinstance(target, A.Var):
            if _has_placeholder(node.value):
                raise err("missing_operand", node=node.value)
            try:
                value = self.eval(node.value, ctx)
            except SMathError as e:
                if _is_not_defined(e):
                    ctx.vars[target.name] = Lazy(node.value)
                    return
                raise
            ctx.vars[target.name] = value
        elif isinstance(target, A.Call):
            params = []
            for a in target.args:
                if not isinstance(a, A.Var):
                    raise err("syntax", node=a)
                params.append(a.name)
            ctx.funcs[(target.name, len(params))] = UserFunction(target.name, params, node.value)
        elif isinstance(target, A.IndexOp) and isinstance(target.base, A.Var):
            self._assign_element(target, self.eval(node.value, ctx), ctx)
        else:
            raise err("syntax", node=target)

    def _assign_element(self, target: A.IndexOp, value, ctx: Context) -> None:
        name = target.base.name
        idx = [need_int(self.eval(i, ctx), i) for i in target.indices]
        cur = ctx.lookup(name)
        if isinstance(cur, Lazy):
            cur = self.eval(cur.node, ctx)
        if not isinstance(cur, Matrix):
            cur = Matrix(0, 1 if len(idx) == 1 else 0, [])
        m = cur.copy()
        r = idx[0]
        c = idx[1] if len(idx) > 1 else 1
        nr, nc = max(m.nrows, r), max(m.ncols, c, 1)
        if (nr, nc) != (m.nrows, m.ncols):
            grown = Matrix(nr, nc, [Q(0.0)] * (nr * nc))
            for i in range(m.nrows):
                for j in range(m.ncols):
                    grown.items[i * nc + j] = m.get(i, j)
            m = grown
        if r < 1 or c < 1:
            raise err("index_range", node=target)
        m.items[(r - 1) * m.ncols + (c - 1)] = value
        ctx.assign(name, m)

    # -- evaluation -----------------------------------------------------------
    def eval(self, n: A.Node, ctx: Context):
        m = getattr(self, "_" + type(n).__name__)
        return m(n, ctx)

    def _Num(self, n: A.Num, ctx):
        return Q(float(n.text))

    def _Str(self, n: A.Str, ctx):
        return String(n.text)

    def _Placeholder(self, n, ctx):
        raise err("missing_operand", node=n)

    def _UnitRef(self, n: A.UnitRef, ctx):
        if not is_unit(n.name):
            raise err("not_defined", "'" + n.name, node=n)
        q = unit_quantity(n.name)
        return q

    def _Var(self, n: A.Var, ctx):
        v = ctx.lookup(n.name)
        if v is None:
            if n.name in BUILTIN_CONSTANTS:
                return BUILTIN_CONSTANTS[n.name]
            raise err("not_defined", n.name, node=n)
        if isinstance(v, Lazy):
            try:
                return self.eval(v.node, ctx)
            except SMathError as e:
                if e.node is not None and not _inside(e.node, n):
                    raise SMathError(e.message, n)
                raise
        return v

    def _Group(self, n: A.Group, ctx):
        return self.eval(n.inner, ctx)

    def _Unary(self, n: A.Unary, ctx):
        v = self.eval(n.arg, ctx)
        try:
            if n.op == "-":
                return neg(v)
            if n.op == "+":
                return v
            if n.op == "!":
                x = need_real(v, n)
                if x < 0 or x != int(x):
                    return Q(math.gamma(x + 1))
                return Q(float(math.factorial(int(x))))
            if n.op == "¬":
                return Q(0.0 if truth(v) else 1.0)
            if n.op == "±":
                return Matrix.column([v, neg(v)])
        except SMathError as e:
            raise _at(e, n)
        raise err("syntax", node=n)

    def _BinOp(self, n: A.BinOp, ctx):
        op = n.op
        if op in ("∧", "∨", "⊕"):
            a = truth(self.eval(n.left, ctx))
            b = truth(self.eval(n.right, ctx))
            r = {"∧": a and b, "∨": a or b, "⊕": a != b}[op]
            return Q(1.0 if r else 0.0)
        a = self.eval(n.left, ctx)
        b = self.eval(n.right, ctx)
        try:
            if op == "+":
                return add(a, b)
            if op == "-":
                return sub(a, b)
            if op == "*":
                # 20'°C is an absolute temperature: factor and offset apply
                if isinstance(n.right, A.UnitRef) and unit_offset_of(n.right.name):
                    return add(mul(a, b), Q(unit_offset_of(n.right.name), b.dims))
                return mul(a, b)
            if op == "/":
                return div(a, b)
            if op == "^":
                return power(a, b)
            if op in ("<", ">", "≤", "≥", "≠", "≡"):
                return compare(op, a, b)
            if op == "±":
                return Matrix.column([add(a, b), sub(a, b)])
        except SMathError as e:
            raise _at(e, n)
        raise err("syntax", node=n)

    def _IndexOp(self, n: A.IndexOp, ctx):
        base = self.eval(n.base, ctx)
        idx = [need_int(self.eval(i, ctx), i) for i in n.indices]
        if isinstance(base, Matrix):
            try:
                if len(idx) == 1:
                    k = idx[0] - 1
                    if base.ncols == 1 or base.nrows == 1:
                        if not 0 <= k < len(base.items):
                            raise IndexError
                        return base.items[k]
                    raise err("args_count", node=n)
                i, j = idx[0] - 1, idx[1] - 1
                if not (0 <= i < base.nrows and 0 <= j < base.ncols):
                    raise IndexError
                return base.get(i, j)
            except IndexError:
                raise err("index_range", node=n)
        raise err("must_be_matrix", node=n)

    def _MatrixLit(self, n: A.MatrixLit, ctx):
        return Matrix(n.nrows, n.ncols, [self.eval(c, ctx) for c in n.cells])

    def _Define(self, n: A.Define, ctx):
        # definitions inside programs (line(...), for bodies...)
        self.define(n, ctx)
        if isinstance(n.target, A.Var):
            return self._Var(n.target, ctx)
        return Q(0.0)

    def _Evaluate(self, n: A.Evaluate, ctx):
        return self.eval(n.expr, ctx)

    def _Call(self, n: A.Call, ctx):
        name = n.name
        # user-defined functions win over built-ins with the same arity
        f = ctx.function(name, len(n.args))
        if f is not None:
            return self.call_user(f, n, ctx)
        special = self.builtins.SPECIAL.get(name)
        if special is not None:
            return special(self, n, ctx)
        fn = self.builtins.lookup(name, len(n.args))
        if fn is not None:
            args = [self.eval(a, ctx) for a in n.args]
            try:
                return fn(*args)
            except SMathError as e:
                raise _at(e, n)
            except (ValueError, OverflowError, ZeroDivisionError):
                raise err("cannot_evaluate", node=n)
        if name == "":
            raise err("syntax", node=n)
        # a variable holding a matrix called like v(2)? SMath reports undefined.
        if self.builtins.known(name) or ctx.any_function(name):
            raise err("args_count", node=n)
        raise err("function_not_defined", f"{name}({','.join('#' for _ in n.args)})", node=n)

    def call_user(self, f: UserFunction, n: A.Call, ctx: Context):
        local = Context(ctx)
        for p, a in zip(f.params, n.args):
            local.vars[p] = self.eval(a, ctx)
        return self.eval(f.body, local)


def _has_placeholder(n: A.Node) -> bool:
    return any(isinstance(x, A.Placeholder) for x in A.walk(n))


def _is_not_defined(e: SMathError) -> bool:
    return e.message.endswith("not defined.")


def _inside(inner, outer) -> bool:
    return any(x is inner for x in A.walk(outer))


def _at(e: SMathError, n: A.Node) -> SMathError:
    if e.node is None:
        e.node = n
    return e
