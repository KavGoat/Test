"""Double-check: an independent second calculation of every result.

The worksheet's engine is fast and incremental.  This module recalculates
the page from scratch with a separate, deliberately simple implementation:

* exact rational arithmetic (fractions.Fraction) wherever the maths allows
  it, floating point only for functions such as sin or sqrt;
* its own unit bookkeeping: a dictionary of SI base-unit exponents, built
  from the unit table, never the engine's dimension tuples or code paths;
* definitions and redefinitions taken strictly in reading order.

For every evaluation (x=) and definition it compares the engine's value and
unit with its own, and it reads the shown result back (number, power of ten,
unit, or a unit typed in the result's box) to check the display too.  What
it does not understand (programs, matrices, strings, solve...) is counted as
"not checked" rather than guessed, and so is everything that depends on it.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from fractions import Fraction

from . import ast as A
from .unitdata import BASE, UNITS


class Unchecked(Exception):
    """Something the double-check does not handle."""


class Fail(Exception):
    """The expression is an error in the double-check too."""


Dims = dict  # base unit -> Fraction exponent (only non-zero entries)


def _dims_of(t: tuple) -> Dims:
    return {b: Fraction(e).limit_denominator(64) for b, e in zip(BASE, t) if e}


def _dmul(a: Dims, b: Dims, k=1) -> Dims:
    out = dict(a)
    for u, e in b.items():
        v = out.get(u, 0) + k * e
        if v:
            out[u] = v
        else:
            out.pop(u, None)
    return out


def _dpow(a: Dims, p) -> Dims:
    return {u: e * p for u, e in a.items() if e * p}


@dataclass
class V:
    x: object  # Fraction, float or complex
    d: Dims = field(default_factory=dict)


def _num(text: str):
    try:
        return Fraction(text)
    except (ValueError, ZeroDivisionError):
        return float(text)


def _f(v) -> float:
    return float(v) if not isinstance(v, complex) else v


_FUNCS = {"sin": math.sin, "cos": math.cos, "tan": math.tan, "exp": math.exp, "ln": math.log,
          "log10": math.log10, "sinh": math.sinh, "cosh": math.cosh, "tanh": math.tanh,
          "asin": math.asin, "acos": math.acos, "atan": math.atan}


class Checker:
    def __init__(self):
        self.vars: dict = {}
        self.funcs: dict = {}  # (name, nargs) -> (params, body)

    # -- evaluation -------------------------------------------------------------------------
    def ev(self, n: A.Node, env=None) -> V:
        env = env or {}
        if isinstance(n, A.Num):
            return V(_num(n.text))
        if isinstance(n, A.Group):
            return self.ev(n.inner, env)
        if isinstance(n, A.Var):
            if n.name in env:
                return env[n.name]
            if n.name in self.vars:
                v = self.vars[n.name]
                if v is None:
                    raise Unchecked(n.name)
                return v
            if n.name == "π":
                return V(math.pi)
            if n.name == "e":
                return V(math.e)
            if n.name in UNITS:  # a unit typed without its apostrophe
                return self._unit(n.name)
            raise Fail(n.name)
        if isinstance(n, A.UnitRef):
            if n.name not in UNITS:
                raise Fail(n.name)
            return self._unit(n.name)
        if isinstance(n, A.Unary) and n.op in "-+":
            v = self.ev(n.arg, env)
            return V(-v.x if n.op == "-" else v.x, v.d)
        if isinstance(n, A.BinOp):
            return self._bin(n, env)
        if isinstance(n, A.Call):
            return self._call(n, env)
        raise Unchecked(type(n).__name__)

    def _unit(self, name: str) -> V:
        factor, dims, offset = UNITS[name]
        if offset:
            raise Unchecked("temperature offset")
        return V(Fraction(factor).limit_denominator(10 ** 15) if float(factor).is_integer() else float(factor),
                 _dims_of(tuple(dims)))

    def _bin(self, n: A.BinOp, env) -> V:
        a, b = self.ev(n.left, env), self.ev(n.right, env)
        op = n.op
        if op in "+-":
            if a.d != b.d:
                raise Fail("units")
            return V(a.x + b.x if op == "+" else a.x - b.x, a.d)
        if op == "*":
            return V(a.x * b.x, _dmul(a.d, b.d))
        if op == "/":
            if b.x == 0:
                raise Fail("division by zero")
            return V(a.x / b.x, _dmul(a.d, b.d, -1))
        if op == "^":
            if b.d:
                raise Fail("units in exponent")
            p = b.x
            if isinstance(p, Fraction) and p.denominator == 1 and isinstance(a.x, Fraction):
                if a.x == 0 and p <= 0:
                    raise Fail("0^0")
                return V(a.x ** int(p), _dpow(a.d, p))
            if isinstance(p, complex) or (a.x < 0 and not float(p).is_integer()):
                raise Unchecked("complex power")
            return V(float(a.x) ** float(p), _dpow(a.d, Fraction(p).limit_denominator(64)))
        raise Unchecked(op)

    def _call(self, n: A.Call, env) -> V:
        key = (n.name, len(n.args))
        if key in self.funcs:
            if self.funcs[key] is None:
                raise Unchecked(n.name)
            params, body = self.funcs[key]
            local = dict(env)
            for p, a in zip(params, n.args):
                local[p] = self.ev(a, env)
            return self.ev(body, local)
        if not (n.name in _FUNCS or n.name in ("sqrt", "abs", "floor", "ceil", "round")):
            # int, sum, solve, for, if...: variables inside may be bound by
            # the construct itself, so nothing is evaluated
            raise Unchecked(n.name)
        args = [self.ev(a, env) for a in n.args]
        if n.name == "sqrt" and len(args) == 1:
            a = args[0]
            if a.x < 0:
                raise Unchecked("complex")
            r = math.sqrt(float(a.x))
            return V(Fraction(r).limit_denominator(10 ** 9) if abs(round(r) ** 2 - float(a.x)) == 0 else r,
                     _dpow(a.d, Fraction(1, 2)))
        if n.name == "abs" and len(args) == 1:
            return V(abs(args[0].x), args[0].d)
        if n.name in _FUNCS and len(args) == 1:
            if args[0].d:
                raise Fail("units in function")
            try:
                return V(_FUNCS[n.name](float(args[0].x)))
            except (ValueError, OverflowError):
                raise Unchecked(n.name)
        if n.name in ("floor", "ceil") and len(args) == 1:
            f = math.floor if n.name == "floor" else math.ceil
            return V(Fraction(f(args[0].x)), args[0].d)
        if n.name == "round" and len(args) == 2:
            x, k = args[0].x, int(args[1].x)
            q = Fraction(10) ** k
            y = Fraction(x) * q
            r = math.floor(abs(y) + Fraction(1, 2)) * (1 if y >= 0 else -1)  # half away from zero
            return V(Fraction(r) / q, args[0].d)
        raise Unchecked(n.name)

    # -- statements --------------------------------------------------------------------------
    def define(self, node: A.Define) -> None:
        t = node.target
        if isinstance(t, A.Var):
            try:
                self.vars[t.name] = self.ev(node.value)
            except (Unchecked, Fail):
                self.vars[t.name] = None  # unknown from here on
                raise
        elif isinstance(t, A.Call) and all(isinstance(a, A.Var) for a in t.args):
            self.funcs[(t.name, len(t.args))] = ([a.name for a in t.args], node.value)
        else:
            raise Unchecked("indexed definition")


# -- comparing with the engine -----------------------------------------------------------------

def _close(a, b, rel=1e-9) -> bool:
    a, b = complex(a), complex(b)
    return abs(a - b) <= rel * max(abs(a), abs(b), 1e-300)


def _engine_dims(q) -> Dims:
    return _dims_of(tuple(q.dims))


_SUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")


def parse_unit_text(text: str):
    """(factor, dims) of a unit as displayed: "kN/m", "kg m^2/s^2", "m/s^2 kg"."""
    text = text.strip()
    if not text:
        return Fraction(1), {}
    num, _, den = text.partition("/")
    factor, dims = 1.0, {}
    for part, sign in ((num, 1), (den, -1)):
        for tok in part.split():
            name, _, p = tok.partition("^")
            if name == "1":
                continue
            if name not in UNITS:
                raise Unchecked("unit " + name)
            p = Fraction(p) if p else Fraction(1)
            f, d, _o = UNITS[name]
            factor *= float(f) ** (float(p) * sign)
            dims = _dmul(dims, _dpow(_dims_of(tuple(d)), p), sign)
    return factor, dims


def parse_shown(text: str):
    """(number, unit text) of a shown scalar result: "1.2346·10^5 kN/m"."""
    m = re.fullmatch(r"\s*(-?[0-9.]+)(?:·10\^(-?\d+))?\s*(.*)", text)
    if not m:
        raise Unchecked("shown " + text)
    x = float(m.group(1)) * (10 ** int(m.group(2)) if m.group(2) else 1)
    return x, m.group(3)


@dataclass
class Report:
    checked: int = 0
    unchecked: int = 0
    mismatches: list = field(default_factory=list)  # (region, what, expected, got)

    @property
    def ok(self) -> bool:
        return not self.mismatches

    def summary(self) -> str:
        if self.mismatches:
            return f"Double-check: {len(self.mismatches)} result(s) differ!"
        extra = f", {self.unchecked} not checkable" if self.unchecked else ""
        return f"Double-check: {self.checked} result(s) agree{extra}"


def double_check(ws) -> Report:
    """Recalculate every region independently and compare (see module doc)."""
    from ..engine.display import display_text
    from ..engine.parser import ParseError, parse_row
    from .units import Quantity

    rep = Report()
    chk = Checker()
    for r in ws.ordered():
        if r.kind != "math" or not r.enabled or r.plot is not None:
            continue
        if getattr(r, "symbolic_eval", False):
            rep.unchecked += 1  # → shows an expression: nothing numeric to compare
            continue
        try:
            node = parse_row(r.expression_row())
        except ParseError:
            _forget(chk, r)
            continue
        # names this region defines in ways the double-check cannot follow
        # (programs, element assignment...) become unknown from here on
        simple = isinstance(node, A.Define) and (
            isinstance(node.target, A.Var) or
            (isinstance(node.target, A.Call) and all(isinstance(a, A.Var) for a in node.target.args)))
        if not simple:
            _forget(chk, r)
        try:
            if isinstance(node, A.Define):
                try:
                    chk.define(node)
                except Fail:
                    continue
                if isinstance(node.target, A.Var):
                    mine = chk.vars.get(node.target.name)
                    got = r.defined_vars.get(node.target.name)
                    if isinstance(got, Quantity) and mine is not None:
                        rep.checked += 1
                        if not (_close(mine.x if not isinstance(mine.x, Fraction) else float(mine.x), got.value)
                                and mine.d == _engine_dims(got)):
                            rep.mismatches.append((r, "value", mine, got))
                continue
            if not r.editor.evaluate or r.optimization == "none" or r.ignore_units:
                continue
            try:
                mine = chk.ev(node)
            except Fail:
                if r.error is None:
                    rep.checked += 1
                    rep.mismatches.append((r, "error expected", "an error", display_text(r.display)
                                           if r.display is not None else None))
                continue
            got = r.value
            if not isinstance(got, Quantity) or r.error is not None:
                rep.checked += 1
                rep.mismatches.append((r, "value", mine, got if r.error is None else r.error.message))
                continue
            rep.checked += 1
            if not (_close(float(mine.x) if isinstance(mine.x, Fraction) else mine.x, got.value)
                    and mine.d == _engine_dims(got)):
                rep.mismatches.append((r, "value", mine, got))
                continue
            _check_display(r, mine, rep, ws)
        except Unchecked:
            rep.unchecked += 1
    return rep


def _forget(chk: Checker, r) -> None:
    for n in r.defined_vars:
        chk.vars[n] = None
    for key in r.defined_funcs:
        chk.funcs[key] = None


def _check_display(r, mine: V, rep: Report, ws) -> None:
    """Read the shown number and unit(s) back and compare with the value."""
    from ..engine.display import DNum, DQuantity, display_text
    from ..engine.parser import parse_row

    d = r.display
    if not isinstance(d, DQuantity) or not isinstance(d.value, DNum) or isinstance(mine.x, complex):
        return
    x, unit = parse_shown(display_text(d))
    factor, dims = parse_unit_text(unit)
    if not r.editor.unit.is_empty():
        # the unit typed in the result's box follows the shown units
        chk = Checker()
        typed = chk.ev(parse_row(r.editor.unit))
        factor *= float(typed.x)
        dims = _dmul(dims, typed.d)
    shown_si = x * factor
    fmt = r.fmt or ws.format
    # the shown number is rounded: allow half a unit in its last shown digit
    m = re.search(r"·10\^(-?\d+)", display_text(d))
    power = int(m.group(1)) if m else 0
    if fmt.significant:
        lead = math.floor(math.log10(abs(x))) if x else 0
        step = 10.0 ** (lead - fmt.decimals + 1)
    else:
        step = 10.0 ** (power - fmt.decimals)
    tol = 0.5 * step * abs(factor) * 1.0001
    true = float(mine.x)
    if dims != mine.d or abs(shown_si - true) > tol + abs(true) * 1e-9:
        rep.mismatches.append((r, "display", true, display_text(d) + (" " + r.editor.unit.text() if not r.editor.unit.is_empty() else "")))
