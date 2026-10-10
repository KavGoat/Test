"""Working out a formula's value, the way Excel does.

Values flow as plain Python values (see values.py); a reference stays a
:class:`RefValue` until something needs what is in it, so ROW(A5),
ISBLANK(B2), OFFSET(...) and SUM(A:A) see the reference itself and SUM can
walk only the cells that hold something.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from . import formula as F
from .refs import MAX_COLS, MAX_ROWS, is_cell_name
from .values import (BLANK, CALC, DIV0, ERRORS, NA, NAME, NUM, REF, UNITS_ERR, VALUE, Array,
                     ErrorValue, Qty, SheetError, add, div, is_number, mul, neg, power, sub,
                     to_number, to_text, unit_parts, with_unit, UnitTextError)


@dataclass(frozen=True)
class RefValue:
    """A reference: a block of cells on a sheet."""

    sheet: object
    top: int
    left: int
    bottom: int
    right: int

    @property
    def height(self) -> int:
        return self.bottom - self.top + 1

    @property
    def width(self) -> int:
        return self.right - self.left + 1

    @property
    def single(self) -> bool:
        return self.top == self.bottom and self.left == self.right

    def value_at(self, i: int, j: int):
        return self.sheet.workbook.value(self.sheet, self.top + i, self.left + j)

    def filled(self):
        """(row, col, value) of each cell in the block that holds something."""
        sheet = self.sheet
        wb = sheet.workbook
        cells = sheet.cells
        pending = wb._dirty if wb._in_pass else None
        sid = sheet.id
        for row, col in sheet.positions_in(self.top, self.left, self.bottom, self.right):
            if pending and (sid, row, col) in pending:
                yield row, col, wb.value(sheet, row, col)
            else:
                yield row, col, cells[(row, col)].value

    def bounded(self) -> "RefValue":
        """Whole columns and rows cut down to what the sheet uses."""
        used = self.sheet.used_area()
        if used is None:
            return RefValue(self.sheet, self.top, self.left, self.top, self.left)
        bottom = min(self.bottom, max(used[2], self.top))
        right = min(self.right, max(used[3], self.left))
        return RefValue(self.sheet, self.top, self.left, bottom, right)

    def to_array(self) -> Array:
        ref = self.bounded() if (self.height * self.width > 100_000) else self
        wb = self.sheet.workbook
        rows = []
        for r in range(ref.top, ref.bottom + 1):
            rows.append(tuple(wb.value(self.sheet, r, c) for c in range(ref.left, ref.right + 1)))
        return Array(tuple(rows))


class Ctx:
    __slots__ = ("wb", "sheet", "row", "col", "reads", "depth", "lets")

    def __init__(self, wb, sheet, row, col):
        self.wb = wb
        self.sheet = sheet
        self.row = row
        self.col = col
        self.reads: set = set()
        self.depth = 0
        self.lets: Optional[dict] = None


MISSING = F.Missing()


def evaluate_cell(wb, sheet, row: int, col: int, tree):
    """(value, document variables read) of the formula in a cell."""
    ctx = Ctx(wb, sheet, row, col)
    try:
        value = result(ev(tree, ctx))
    except SheetError as e:
        value = e.error
    except RecursionError:
        value = NUM
    except (OverflowError, ZeroDivisionError):
        value = NUM
    return value, ctx.reads


def result(v):
    """What a cell shows for a formula's result: a reference shows what is
    in it (an empty cell as 0), a 1×1 array its one value."""
    if isinstance(v, RefValue):
        if v.single:
            v = v.value_at(0, 0)
        else:
            v = v.to_array()
    if isinstance(v, Array):
        if v.height == 1 and v.width == 1:
            v = v.get(0, 0)
        else:
            return Array(tuple(tuple(0.0 if x is BLANK else x for x in row) for row in v.rows))
    if v is BLANK:
        return 0.0
    if isinstance(v, int) and not isinstance(v, bool):
        return float(v)
    if isinstance(v, float) and not math.isfinite(v):
        return NUM
    return v


def deref(v):
    """A single value for a reference to one cell; a block becomes an array."""
    if isinstance(v, RefValue):
        if v.single:
            return v.value_at(0, 0)
        return v.to_array()
    return v


def scalar(v):
    """One value; a block gives its top-left (used where Excel needs one)."""
    v = deref(v)
    if isinstance(v, Array):
        return v.get(0, 0) if v.height and v.width else BLANK
    return v


# -- the tree ----------------------------------------------------------------------------
def ev(n, ctx: Ctx):
    t = type(n)
    if t is F.Num:
        return n.value
    if t is F.Ref:
        return _ref(n, ctx)
    if t is F.Binary:
        return _binary(n, ctx)
    if t is F.Call:
        from .functions import call

        return call(n, ctx)
    if t is F.Str:
        return n.value
    if t is F.Area:
        return _area(n, ctx)
    if t is F.Bool:
        return n.value
    if t is F.Err:
        return ERRORS.get(n.code, VALUE)
    if t is F.Unary:
        v = deref(ev(n.arg, ctx))
        if n.op == "+":
            return v
        return _lift1(v, lambda x: neg(to_number(x)))
    if t is F.Percent:
        v = deref(ev(n.arg, ctx))
        return _lift1(v, lambda x: div(to_number(x), 100.0))
    if t is F.Unit:
        return _unit(n.text)
    if t is F.Name:
        return _name(n, ctx)
    if t is F.DocVar:
        if not is_cell_name(n.name) and ctx.wb.find_name(n.name, ctx.sheet) is not None:
            from .functions import call

            return call(F.Call("VAR", (F.Name(n.name),)), ctx)   # VAR(named block)
        return _outside(n.name, ctx)
    if t is F.SpillRef:
        return _spill_ref(n, ctx)
    if t is F.Structured:
        return structured(n, ctx)
    if t is F.BadRef:
        return REF
    if t is F.ArrayLit:
        return Array(tuple(tuple(ev(x, ctx) for x in row) for row in n.rows))
    if t is F.Missing:
        return BLANK
    raise SheetError(VALUE)


def _unit(text: str):
    try:
        factor, dims, _offset = unit_parts(text)
    except UnitTextError:
        raise SheetError(NAME)
    if not any(dims):
        return factor
    return Qty(factor, dims, text)


def _sheet_of(name: Optional[str], ctx: Ctx):
    if name is None:
        return ctx.sheet
    sheet = ctx.wb.sheet(name)
    if sheet is None:
        raise SheetError(REF)
    return sheet


def _ref(n: F.Ref, ctx: Ctx) -> RefValue:
    sheet = _sheet_of(n.sheet, ctx)
    row, col = n.at(ctx.row, ctx.col)
    if not (0 <= row < MAX_ROWS and 0 <= col < MAX_COLS):
        raise SheetError(REF)
    return RefValue(sheet, row, col, row, col)


def _area(n: F.Area, ctx: Ctx) -> RefValue:
    sheet = _sheet_of(n.sheet, ctx)
    r1, c1 = n.first.at(ctx.row, ctx.col)
    r2, c2 = n.last.at(ctx.row, ctx.col)
    top, bottom = min(r1, r2), max(r1, r2)
    left, right = min(c1, c2), max(c1, c2)
    if top < 0 or left < 0 or bottom >= MAX_ROWS or right >= MAX_COLS:
        raise SheetError(REF)
    return RefValue(sheet, top, left, bottom, right)


def _spill_ref(n: F.SpillRef, ctx: Ctx) -> RefValue:
    """A1#: the block A1's formula spills (#REF! when it spills nothing)."""
    sheet = _sheet_of(n.ref.sheet, ctx)
    row, col = n.ref.at(ctx.row, ctx.col)
    ctx.wb.value(sheet, row, col)               # calculated first
    size = sheet.spills.get((row, col))
    if size is not None:
        return RefValue(sheet, row, col, row + size[0] - 1, col + size[1] - 1)
    cell = sheet.cells.get((row, col))
    if cell is not None and cell.is_formula and (row, col) not in sheet.wanted:
        return RefValue(sheet, row, col, row, col)
    raise SheetError(REF)


def table_for(n: F.Structured, ctx: Ctx):
    sheet = ctx.sheet if n.table is None else ctx.wb.sheet(n.table)
    if sheet is None or sheet.kind != "table" or not sheet.size:
        raise SheetError(REF)
    return sheet


def heading_col(sheet, heading: str) -> Optional[int]:
    """The column whose heading (first row) is *heading* (any case)."""
    from .numfmt import format_value

    wanted = heading.strip().lower()
    for c in range(sheet.size[1]):
        cell = sheet.cells.get((0, c))
        if cell is None:
            continue
        text = cell.value if isinstance(cell.value, str) else format_value(cell.value).text
        if str(text).strip().lower() == wanted:
            return c
    return None


def structured(n: F.Structured, ctx: Ctx) -> RefValue:
    """Loads[Load], Loads[@Load], Loads[[#Headers],[Load]]...: a block of
    the table, its first row being the headings (Excel's tables)."""
    sheet = table_for(n, ctx)
    rows, cols = sheet.size
    if n.first is None:
        left, right = 0, cols - 1
    else:
        a = heading_col(sheet, n.first)
        b = heading_col(sheet, n.last) if n.last is not None else a
        if a is None or b is None:
            raise SheetError(REF)
        left, right = min(a, b), max(a, b)
    specials = set(n.specials) or {"#Data"}
    if "#Totals" in specials:
        raise SheetError(REF)                    # a table here has no totals row
    if "@" in specials:
        if ctx.sheet is not sheet or not 1 <= ctx.row < rows:
            raise SheetError(VALUE)
        top = bottom = ctx.row
    elif "#All" in specials or {"#Headers", "#Data"} <= specials:
        top, bottom = 0, rows - 1
    elif "#Headers" in specials:
        top = bottom = 0
    else:
        top, bottom = 1, rows - 1
        if bottom < top:
            raise SheetError(REF)
    return RefValue(sheet, top, left, bottom, right)


def _name(n: F.Name, ctx: Ctx):
    if ctx.lets and n.sheet is None:
        got = ctx.lets.get(n.name.lower())
        if got is not None:
            return got
    sheet = ctx.sheet
    if n.sheet is not None:
        from .refs import unquote_sheet

        sheet = ctx.wb.sheet(unquote_sheet(n.sheet))
        if sheet is None:
            raise SheetError(REF)
    dn = ctx.wb.find_name(n.name, sheet)
    if dn is not None:
        if ctx.depth > 40:
            raise SheetError(NUM)
        try:
            parsed = F.parse(dn.refers_to, 0, 0)
        except F.FormulaError:
            return NAME
        home = ctx.wb.sheet_by_id(dn.sheet) if dn.sheet else ctx.sheet
        inner = Ctx(ctx.wb, home, 0, 0)
        inner.reads = ctx.reads
        inner.depth = ctx.depth + 1
        return ev(parsed.tree, inner)
    if n.sheet is None:
        try:
            return _outside(n.name, ctx)
        except SheetError as e:
            if e.error is not NAME:
                raise
        try:
            return _unit(n.name)
        except SheetError:
            pass
    return NAME


def _outside(name: str, ctx: Ctx):
    """A variable from the document's equations."""
    ctx.reads.add(name.lower())
    ask = ctx.wb.outside
    if ask is None:
        raise SheetError(NAME)
    try:
        value = ask(ctx.sheet, name)
    except KeyError:
        raise SheetError(NAME)
    return from_engine(value)


def from_engine(value):
    """A value from the equations as a cell value."""
    from calcforge.calc.engine.units import Quantity
    from calcforge.calc.engine.values import Matrix, String

    if isinstance(value, Quantity):
        v = value.value
        if isinstance(v, complex):
            if v.imag != 0:
                return NUM
            v = v.real
        if any(value.dims):
            return Qty(float(v), tuple(value.dims), None)
        return float(v)
    if isinstance(value, String):
        return value.text
    if isinstance(value, Matrix):
        rows = []
        for i in range(value.nrows):
            rows.append(tuple(from_engine(value.get(i, j)) for j in range(value.ncols)))
        return Array(tuple(rows))
    if isinstance(value, (float, int, str, bool, Qty, ErrorValue, Array)):
        return value
    return VALUE


def to_engine(value):
    """A cell value for the equations (a Quantity, a String or a Matrix)."""
    from calcforge.calc.engine.units import NODIM, Quantity
    from calcforge.calc.engine.values import Matrix, String

    if isinstance(value, bool):
        return Quantity(1.0 if value else 0.0, NODIM)
    if isinstance(value, (float, int)):
        return Quantity(float(value), NODIM)
    if isinstance(value, Qty):
        return Quantity(value.si, tuple(value.dims))
    if isinstance(value, str):
        return String(value)
    if value is BLANK:
        return Quantity(0.0, NODIM)
    if isinstance(value, Array):
        return Matrix(value.height, value.width, [to_engine(x) for x in value.values()])
    if isinstance(value, ErrorValue):
        raise SheetError(value)
    raise SheetError(VALUE)


# -- operators --------------------------------------------------------------------------
_ARITH = {"+": add, "-": sub, "*": mul, "/": div, "^": power}


def _binary(n: F.Binary, ctx: Ctx):
    op = n.op
    if op == ":":
        a, b = ev(n.left, ctx), ev(n.right, ctx)
        if not isinstance(a, RefValue) or not isinstance(b, RefValue) or a.sheet is not b.sheet:
            return VALUE if not isinstance(a, ErrorValue) else a
        return RefValue(a.sheet, min(a.top, b.top), min(a.left, b.left),
                        max(a.bottom, b.bottom), max(a.right, b.right))
    # 5 °C: a number written in a unit that has an offset
    if op == "*" and type(n.right) is F.Unit and type(n.left) is F.Num:
        try:
            return with_unit(n.left.value, n.right.text)
        except UnitTextError:
            return NAME
    a = deref(ev(n.left, ctx))
    b = deref(ev(n.right, ctx))
    if isinstance(a, Array) or isinstance(b, Array):
        return _broadcast(a, b, lambda x, y: _scalar_op(op, x, y))
    return _scalar_op(op, a, b)


def _scalar_op(op: str, a, b):
    if isinstance(a, ErrorValue):
        return a
    if isinstance(b, ErrorValue):
        return b
    try:
        f = _ARITH.get(op)
        if f is not None:
            if a is BLANK and isinstance(b, Qty) and op in "+-":
                return f(Qty(0.0, b.dims, b.unit), b)
            if b is BLANK and isinstance(a, Qty) and op in "+-":
                return a
            return f(to_number(a), to_number(b))
        if op == "&":
            return to_text(a) + to_text(b)
        return compare(op, a, b)
    except SheetError as e:
        return e.error
    except OverflowError:
        return NUM


def _rank(v) -> int:
    if isinstance(v, bool):
        return 2
    if isinstance(v, str):
        return 1
    return 0


def compare_values(a, b) -> int:
    """-1, 0 or 1 as Excel orders values: numbers < text < FALSE < TRUE;
    text without regard to case; an empty cell as 0 or "" to suit."""
    if a is BLANK:
        a = "" if isinstance(b, str) else (False if isinstance(b, bool) else 0.0)
    if b is BLANK:
        b = "" if isinstance(a, str) else (False if isinstance(a, bool) else 0.0)
    ra, rb = _rank(a), _rank(b)
    if ra != rb:
        return -1 if ra < rb else 1
    if ra == 1:
        x, y = a.lower(), b.lower()
    elif ra == 2:
        x, y = a, b
    else:
        x, y = a, b
        if isinstance(x, Qty) or isinstance(y, Qty):
            dx = x.dims if isinstance(x, Qty) else None
            dy = y.dims if isinstance(y, Qty) else None
            xs = x.si if isinstance(x, Qty) else float(x)
            ys = y.si if isinstance(y, Qty) else float(y)
            # a quantity compared with plain 0 is a test of its sign
            if dx != dy and not ((dx is None and xs == 0) or (dy is None and ys == 0)) \
                    and not (dx is not None and not any(dx) and dy is None) \
                    and not (dy is not None and not any(dy) and dx is None):
                raise SheetError(UNITS_ERR)
            x, y = xs, ys
        else:
            x, y = float(x), float(y)
            # Excel compares to 15 significant digits
            if x != y and abs(x - y) <= 1e-15 * max(abs(x), abs(y)):
                return 0
    return (x > y) - (x < y)


def compare(op: str, a, b) -> bool:
    c = compare_values(a, b)
    return {"=": c == 0, "<>": c != 0, "<": c < 0, ">": c > 0, "<=": c <= 0, ">=": c >= 0}[op]


def _as_array(v) -> Array:
    if isinstance(v, Array):
        return v
    return Array(((v,),))


def _broadcast(a, b, f) -> Array:
    """Element by element, as Excel does with arrays: a single row or
    column stretches across the other; past the end of the smaller is #N/A."""
    A, B = _as_array(a), _as_array(b)
    h = max(A.height, B.height)
    w = max(A.width, B.width)

    def pick(X, i, j):
        ii = 0 if X.height == 1 else i
        jj = 0 if X.width == 1 else j
        if ii >= X.height or jj >= X.width:
            return NA
        return X.get(ii, jj)

    rows = []
    for i in range(h):
        rows.append(tuple(f(pick(A, i, j), pick(B, i, j)) for j in range(w)))
    return Array(tuple(rows))


def _lift1(v, f):
    if isinstance(v, Array):
        return Array(tuple(tuple(_safe(f, x) for x in row) for row in v.rows))
    return _safe(f, v)


def _safe(f, x):
    if isinstance(x, ErrorValue):
        return x
    try:
        return f(x)
    except SheetError as e:
        return e.error
