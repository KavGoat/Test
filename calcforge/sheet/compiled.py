"""A formula's tree turned once into Python closures, for working it out
again and again (the user, 2026-10-19: an input of the seismic workbook,
read by 4000 formulas, must feel instant).

evaluate.ev walks the tree every time it works a formula out, dispatching on
each node's type and wrapping every cell it reads in a RefValue. Here each
node becomes a closure that does just its own work: a cell read for its
value is fetched straight from the workbook, + - * / and the comparisons of
two plain numbers are done on the spot, and IF and IFERROR choose their
branch without the generic call. Everything else goes back to evaluate.ev
(and functions.call) for that node, so the answers are evaluate's own:
every short cut ends in the same code, or in Python's float arithmetic
exactly as values.add/sub/mul/div do it.

The closures are kept on the formula's shared tree (formula.Parsed), so a
column of filled formulas compiles once.
"""
from __future__ import annotations

from . import formula as F
from .evaluate import (MISSING, RefValue, _binary, _broadcast, _intersect, _lift1, _located,
                       _name, _ref, _scalar_op, _sheet_of, deref, ev, reach)
from .refs import MAX_COLS, MAX_ROWS
from .values import BLANK, REF, Array, ErrorValue, SheetError, div, failed, neg, to_bool, to_number

_COMPARE = ("=", "<>", "<", ">", "<=", ">=")
_ARITH = ("+", "-", "*", "/", "^", "&") + _COMPARE


def compiled(parsed):
    """The closure working out *parsed*'s formula: fn(ctx) -> what ev gives."""
    got = getattr(parsed, "fast", None)
    if got is None:
        got = parsed.fast = _c(parsed.tree)
    return got


# -- a node as what ev gives (a reference stays a RefValue) ---------------------------------
def _c(n):
    t = type(n)
    if t is F.Num or t is F.Str or t is F.Bool:
        value = n.value
        return lambda ctx: value
    if t is F.Ref:
        return lambda ctx: _ref(n, ctx)
    if t is F.Binary:
        return _binary_fn(n)
    if t is F.Unary:
        return _unary_fn(n)
    if t is F.Percent:
        arg = _v(n.arg)

        def percent(ctx):
            v = arg(ctx)
            if type(v) is float:
                return v / 100.0
            return _lift1(v, lambda x: div(to_number(x), 100.0))
        return percent
    if t is F.Call:
        return _call_fn(n)
    if t is F.Name:
        return lambda ctx: _name(n, ctx)
    return lambda ctx: ev(n, ctx)


# -- a node as a value (deref(ev(node))): a cell's value read straight away -------------------
def _v(n):
    if type(n) is F.Ref:
        sheet_name = n.sheet
        r, c, rabs, cabs = n.row, n.col, n.row_abs, n.col_abs

        def cell_value(ctx):
            sheet = ctx.sheet if sheet_name is None else _sheet_of(sheet_name, ctx)
            row = r if rabs else ctx.row + r
            col = c if cabs else ctx.col + c
            if not (0 <= row < MAX_ROWS and 0 <= col < MAX_COLS):
                raise failed(REF, "the reference falls off the edge of the sheet")
            wb = ctx.wb
            if wb.reach is not None and sheet is not ctx.sheet:
                reach(ctx, RefValue(sheet, row, col, row, col))
            cell = sheet.cells.get((row, col))
            if cell is None:
                return BLANK
            if (sheet.id, row, col) in wb._dirty:
                return wb.value(sheet, row, col)     # to work out first (Workbook.value)
            return cell.value
        return cell_value
    t = type(n)
    if t in (F.Num, F.Str, F.Bool):
        value = n.value
        return lambda ctx: value
    if (t is F.Binary and n.op in _ARITH) or t is F.Unary or t is F.Percent:
        return _c(n)                     # never a reference: nothing to look into
    inner = _c(n)
    return lambda ctx: deref(inner(ctx))


def _binary_fn(n):
    op = n.op
    if op not in _ARITH or (op == "*" and type(n.right) is F.Unit and type(n.left) is F.Num):
        return lambda ctx: _binary(n, ctx)          # A1:B2, 5 °C
    left, right = _v(n.left), _v(n.right)

    def slow(ctx, a, b):
        if isinstance(a, Array) or isinstance(b, Array):
            return _broadcast(a, b, lambda x, y: _scalar_op(op, x, y))
        got = _scalar_op(op, a, b)
        if isinstance(got, ErrorValue) and got is not a and got is not b:
            return _located(got, n, b, ctx)
        return got

    if op == "+":
        def f(ctx):
            a, b = left(ctx), right(ctx)
            if type(a) is float and type(b) is float:
                return a + b
            return slow(ctx, a, b)
    elif op == "-":
        def f(ctx):
            a, b = left(ctx), right(ctx)
            if type(a) is float and type(b) is float:
                return a - b
            return slow(ctx, a, b)
    elif op == "*":
        def f(ctx):
            a, b = left(ctx), right(ctx)
            if type(a) is float and type(b) is float:
                return a * b
            return slow(ctx, a, b)
    elif op == "/":
        def f(ctx):
            a, b = left(ctx), right(ctx)
            if type(a) is float and type(b) is float and b != 0:
                return a / b
            return slow(ctx, a, b)
    elif op in _COMPARE:
        test = {"=": lambda d: d == 0, "<>": lambda d: d != 0, "<": lambda d: d < 0,
                ">": lambda d: d > 0, "<=": lambda d: d <= 0, ">=": lambda d: d >= 0}[op]

        def f(ctx):
            a, b = left(ctx), right(ctx)
            if type(a) is float and type(b) is float:
                # evaluate.compare_values: Excel compares to 15 significant digits
                if a != b and abs(a - b) <= 1e-15 * max(abs(a), abs(b)):
                    return test(0)
                return test((a > b) - (a < b))
            return slow(ctx, a, b)
    else:
        def f(ctx):
            return slow(ctx, left(ctx), right(ctx))
    return f


def _unary_fn(n):
    if n.op == "@":
        arg = _c(n.arg)
        return lambda ctx: _intersect(arg(ctx), ctx)
    arg = _v(n.arg)
    if n.op == "+":
        return arg
    if n.op != "-":
        return lambda ctx: ev(n, ctx)

    def minus(ctx):
        v = arg(ctx)
        if type(v) is float:
            return -v
        return _lift1(v, lambda x: neg(to_number(x)))
    return minus


# -- calls --------------------------------------------------------------------------------
def _call_fn(n):
    from .functions import FUNCTIONS, _many, call, run, MEANING

    spec = FUNCTIONS.get(n.name)
    count = len(n.args)
    if spec is None or count < spec.least or count > _many(spec.most):
        return lambda ctx: call(n, ctx)           # a LAMBDA's name, a wrong count: as before

    def reasoned(got):
        if isinstance(got, ErrorValue) and not got.reason:
            return ErrorValue(got.code, f"{n.name}: {MEANING.get(got.code, 'it gives ' + got.code)}")
        return got

    if spec.lazy:
        if n.name == "IF":
            return _if_fn(n, reasoned, call)
        if n.name == "IFERROR":
            return _iferror_fn(n, reasoned, call)
        return lambda ctx: call(n, ctx)
    args = [None if type(a) is F.Missing else _c(a) for a in n.args]

    def f(ctx):
        return reasoned(run(spec, [MISSING if g is None else g(ctx) for g in args], ctx))
    return f


def _if_fn(n, reasoned, call):
    """functions.IF, with its branches compiled."""
    args = n.args
    test = _c(args[0])
    yes = _c(args[1]) if len(args) > 1 else None
    no = _c(args[2]) if len(args) > 2 else None
    yes_missing = len(args) > 1 and type(args[1]) is F.Missing
    no_missing = len(args) > 2 and type(args[2]) is F.Missing

    def f(ctx):
        try:
            t = deref(test(ctx))
            if isinstance(t, Array):
                return call(n, ctx)                # a test over an array: IF's own way
            if isinstance(t, ErrorValue):
                got = t
            elif to_bool(t):
                got = True if yes is None else (0.0 if yes_missing else yes(ctx))
            else:
                got = False if no is None else (0.0 if no_missing else no(ctx))
        except SheetError as e:
            got = e.error
        return reasoned(got)
    return f


def _iferror_fn(n, reasoned, call):
    """functions.IFERROR, with both parts compiled."""
    first, fallback = _c(n.args[0]), _c(n.args[1])

    def f(ctx):
        try:
            v = deref(first(ctx))
            if isinstance(v, Array):
                return call(n, ctx)
            got = fallback(ctx) if isinstance(v, ErrorValue) else v
        except SheetError as e:
            got = e.error
        return reasoned(got)
    return f
