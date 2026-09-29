"""Evaluate ASTs against a worksheet context, the way SMath does.

The worksheet is evaluated top-to-bottom, left-to-right; each region sees
only what was defined before it.  A definition whose right-hand side refers
to something not yet defined is kept symbolically (``a:=b`` is legal) and
only fails when a value is actually required.
"""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from typing import Optional

from . import ast as A
from .errors import SMathError, err
from .units import is_unit, unit_offset, unit_quantity
from .values import (Matrix, Q, String, add, compare, cross, div, mul, need_int, need_real, neg,
                     power, sub, truth)


def unit_offset_of(name: str) -> float:
    return unit_offset(name) if is_unit(name) else 0.0


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

    # Each level asks its parent through these methods, so a parent that is
    # an IndexedContext answers from the worksheet's definition index.
    def lookup(self, name: str):
        if name in self.vars:
            return self.vars[name]
        return self.parent.lookup(name) if self.parent is not None else None

    def has(self, name: str) -> bool:
        if name in self.vars:
            return True
        return self.parent.has(name) if self.parent is not None else False

    def assign(self, name: str, value) -> None:
        """Assign in the scope that already owns the name, else locally."""
        if name in self.vars or self.parent is None or not self.parent.has(name):
            self.vars[name] = value
        else:
            self.parent.assign(name, value)

    def function(self, name: str, nargs: int):
        f = self.funcs.get((name, nargs))
        if f is not None:
            return f
        return self.parent.function(name, nargs) if self.parent is not None else None

    def any_function(self, name: str):
        for (n, k), f in self.funcs.items():
            if n == name:
                return f
        return self.parent.any_function(name) if self.parent is not None else None

    def names(self) -> set:
        out = set(self.vars) | {n for n, _ in self.funcs}
        if self.parent is not None:
            out |= self.parent.names()
        return out

    def function_arities(self) -> dict:
        """name -> argument count of the user functions visible here."""
        out = self.parent.function_arities() if self.parent is not None else {}
        out.update({n: k for n, k in self.funcs})
        return out


class DefinitionIndex:
    """Every definition in the worksheet, by name, in reading order.

    Looking up "the value of x as seen at this point of the page" is a
    binary search instead of re-running everything above, which keeps
    typing and autocomplete instant on worksheets with thousands of regions.
    Keys are the regions' reading-order keys (y, x, id).
    """

    def __init__(self):
        self.vars: dict = {}  # name -> [(key, value)] sorted by key
        self.funcs: dict = {}  # (name, nargs) -> [(key, UserFunction)]

    def clear(self) -> None:
        self.vars.clear()
        self.funcs.clear()

    @staticmethod
    def _put(table: dict, name, key, value) -> None:
        lst = table.setdefault(name, [])
        i = bisect.bisect_left(lst, key, key=lambda e: e[0])
        if i < len(lst) and lst[i][0] == key:
            lst[i] = (key, value)
        else:
            lst.insert(i, (key, value))

    @staticmethod
    def _drop(table: dict, name, key) -> None:
        lst = table.get(name)
        if not lst:
            return
        i = bisect.bisect_left(lst, key, key=lambda e: e[0])
        if i < len(lst) and lst[i][0] == key:
            del lst[i]
            if not lst:
                del table[name]

    @staticmethod
    def _before(table: dict, name, key):
        lst = table.get(name)
        if not lst:
            return None
        i = bisect.bisect_left(lst, key, key=lambda e: e[0])
        return lst[i - 1][1] if i else None

    def add(self, key, variables: dict, functions: dict) -> None:
        for n, v in variables.items():
            self._put(self.vars, n, key, v)
        for n, f in functions.items():
            self._put(self.funcs, n, key, f)

    def remove(self, key, variables, functions) -> None:
        for n in variables:
            self._drop(self.vars, n, key)
        for n in functions:
            self._drop(self.funcs, n, key)

    def var_before(self, name: str, key):
        return self._before(self.vars, name, key)

    def func_before(self, name: str, nargs: int, key):
        return self._before(self.funcs, (name, nargs), key)

    def names_before(self, key) -> set:
        out = {n for n, lst in self.vars.items() if lst[0][0] < key}
        out |= {n for (n, _), lst in self.funcs.items() if lst[0][0] < key}
        return out


class IndexedContext(Context):
    """What one region sees: its own definitions over the index at its key."""

    def __init__(self, index: DefinitionIndex, key):
        super().__init__(None)
        self.index = index
        self.key = key

    def lookup(self, name: str):
        if name in self.vars:
            return self.vars[name]
        return self.index.var_before(name, self.key)

    def has(self, name: str) -> bool:
        return name in self.vars or self.index.var_before(name, self.key) is not None

    def function(self, name: str, nargs: int):
        f = self.funcs.get((name, nargs))
        return f if f is not None else self.index.func_before(name, nargs, self.key)

    def any_function(self, name: str):
        for (n, k), f in self.funcs.items():
            if n == name:
                return f
        for (n, k), lst in self.index.funcs.items():
            if n == name and lst[0][0] < self.key:
                return lst[0][1]
        return None

    def names(self) -> set:
        return set(self.vars) | {n for n, _ in self.funcs} | self.index.names_before(self.key)

    def function_arities(self) -> dict:
        out = {n: k for (n, k), lst in self.index.funcs.items() if lst[0][0] < self.key}
        out.update({n: k for n, k in self.funcs})
        return out

    def assign(self, name: str, value) -> None:
        # a program assigning a worksheet variable redefines it here
        self.vars[name] = value


class Evaluator:
    # A region that runs longer than this is interrupted (a runaway while
    # loop must not freeze the worksheet), like SMath's Interrupt processing.
    TIME_LIMIT = 10.0
    # right-click > Ignore units on the region being evaluated
    ignore_units = False

    def __init__(self):
        from . import builtins  # local import: builtins needs Evaluator types

        self.builtins = builtins
        self.deadline = None

    def start_clock(self) -> None:
        import time

        self.deadline = time.monotonic() + self.TIME_LIMIT

    def check_time(self, node=None) -> None:
        import time

        if self.deadline is not None and time.monotonic() > self.deadline:
            raise err("interrupted", node=node)

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
        if self.ignore_units:
            # right-click > Ignore units (observed: 5'm+2 = 7, 5'm*2'kg = 10)
            return Q(q.value)
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
                    raise err("factorial", node=n)  # observed: 3.5!
                if x > 170:
                    raise err("overflow", node=n)  # observed: 171!
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
            if op in ("<", ">", "≤", "≥", "≠", "≡", "≈", "≉"):
                return compare(op, a, b)
            if op == "†":
                return cross(a, b)
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
