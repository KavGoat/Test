"""Working out a formula's value, the way Excel does.

Values flow as plain Python values (see values.py); a reference stays a
:class:`RefValue` until something needs what is in it, so ROW(A5),
ISBLANK(B2), OFFSET(...) and SUM(A:A) see the reference itself and SUM can
walk only the cells that hold something.
"""
from __future__ import annotations

import bisect
import math
import re
from dataclasses import dataclass
from typing import Optional

from . import formula as F
from .refs import MAX_COLS, MAX_ROWS, col_letters, quote_sheet
from .values import (BLANK, CALC, DIV0, ERRORS, NA, NAME, NUM, REF, UNITS_ERR, VALUE, Array,
                     ErrorValue, Qty, SheetError, add, div, equation_unit, failed,
                     general_number, mul, neg, power, sub, units_clash, is_unit_text,
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

    def filled_values(self) -> list:
        """The values of filled(), in its order, as one list: what SUM and
        the like read, walked without a generator per cell (a column of
        running totals reads its column again for every row)."""
        sheet = self.sheet
        wb = sheet.workbook
        cells = sheet.cells
        pending = wb._dirty if wb._in_pass else None
        sid = sheet.id
        top, bottom = self.top, self.bottom
        by_col = sheet._rows_in_col
        left, right = self.left, self.right
        if right - left + 1 > len(by_col):
            wanted = sorted(c for c in by_col if left <= c <= right)
        else:
            wanted = [c for c in range(left, right + 1) if c in by_col]
        out = []
        for col in wanted:
            rows = by_col[col]
            i = bisect.bisect_left(rows, top)
            j = bisect.bisect_right(rows, bottom)
            if not pending:
                out.extend([cells[(row, col)].value for row in rows[i:j]])
                continue
            for row in rows[i:j]:
                if (sid, row, col) in pending:
                    out.append(wb.value(sheet, row, col))
                else:
                    out.append(cells[(row, col)].value)
        return out

    def float_values(self) -> Optional[list]:
        """The plain numbers in the block, as SUM reads them (text, TRUE,
        FALSE and blanks passed over), or None when something else is there
        (a quantity, an error, a cell not worked out yet) and the slow way
        must be taken. Only while calculating: each column's values are
        gathered once a pass, so a column of =SUM($D$2:D9) running totals
        slices one list instead of walking its block for every row
        (findings 5.2: 3000 of them took two seconds)."""
        sheet = self.sheet
        wb = sheet.workbook
        if not wb._in_pass or sheet.spills or sheet.wanted:
            return None
        by_col = sheet._rows_in_col
        left, right = self.left, self.right
        if right - left + 1 > len(by_col):
            wanted = sorted(c for c in by_col if left <= c <= right)
        else:
            wanted = [c for c in range(left, right + 1) if c in by_col]
        out = []
        for col in wanted:
            got = _column(wb, sheet, col)
            rows = got.rows
            i = bisect.bisect_left(rows, self.top)
            j = bisect.bisect_right(rows, self.bottom)
            if j > got.upto:
                got.extend(j)
                if j > got.upto:
                    return None            # a cell in it is still to be worked out
            if got.special[j] != got.special[i]:
                return None
            out.extend(got.floats[got.fpos[i]:got.fpos[j]])
        return out

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


class _Column:
    """One column's values during a pass, in row order, as far as they are
    final (worked out, or not formulas): the plain numbers among them, and
    running counts of numbers and of what SUM can't skip (quantities,
    errors), so any run of rows is two lookups and a slice."""

    __slots__ = ("sheet", "col", "rows", "serial", "upto", "floats", "fpos", "special")

    def __init__(self, sheet, col):
        self.sheet, self.col = sheet, col
        self.rows = sheet._rows_in_col.get(col, [])
        self.serial = sheet.cells_serial
        self.upto = 0
        self.floats: list = []
        self.fpos = [0]
        self.special = [0]

    def extend(self, to: int) -> None:
        sheet = self.sheet
        pending = sheet.workbook._dirty
        cells = sheet.cells
        sid, col, rows = sheet.id, self.col, self.rows
        floats, fpos, special = self.floats, self.fpos, self.special
        n_special = special[-1]
        k = self.upto
        while k < to:
            row = rows[k]
            if (sid, row, col) in pending:
                break
            v = cells[(row, col)].value
            t = type(v)
            if t is float:
                floats.append(v)
            elif t is not str and t is not bool and v is not BLANK:
                n_special += 1             # a quantity, an error, anything else
            fpos.append(len(floats))
            special.append(n_special)
            k += 1
        self.upto = k


def _column(wb, sheet, col) -> _Column:
    key = (sheet.id, col)
    got = wb._columns.get(key)
    if got is None or got.serial != sheet.cells_serial or \
            got.rows is not sheet._rows_in_col.get(col, got.rows):
        got = wb._columns[key] = _Column(sheet, col)
    return got


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


_compiled = None
_referred = None


def evaluate_cell(wb, sheet, row: int, col: int, tree, parsed=None):
    """(value, document variables read) of the formula in a cell; with its
    *parsed* form, through the closures compiled from it (compiled.py)."""
    ctx = Ctx(wb, sheet, row, col)
    try:
        if parsed is not None:
            global _compiled
            if _compiled is None:
                from .compiled import compiled as _compiled
            value = result(_compiled(parsed)(ctx))
        else:
            value = result(ev(tree, ctx))
    except SheetError as e:
        value = e.error
    except RecursionError:
        value = NUM.because("the formula goes round too many times (nested too deep)")
    except (OverflowError, ZeroDivisionError):
        value = NUM.because("a number got too big to work with")
    return value, ctx.reads


class Function:
    """A function made in a formula (LAMBDA): a value only to call."""


def result(v):
    """What a cell shows for a formula's result: a reference shows what is
    in it (an empty cell as 0), a 1×1 array its one value."""
    if type(v) is float and math.isfinite(v):
        return v                           # (most results: a plain number)
    if isinstance(v, Function):
        # =LAMBDA(x, x) left uncalled (Excel)
        return CALC.because("a LAMBDA is a function: call it with its values, LAMBDA(x, x*2)(3)")
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
        return NUM.because("the result is too big to be a number")
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


_call = None


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
        global _call
        if _call is None:                 # imported once (findings 5.5)
            from .functions import call as _call
        return _call(n, ctx)
    if t is F.Str:
        return n.value
    if t is F.Area:
        return _area(n, ctx)
    if t is F.Bool:
        return n.value
    if t is F.Err:
        return ERRORS.get(n.code, VALUE)
    if t is F.Unary:
        if n.op == "@":
            return _intersect(ev(n.arg, ctx), ctx)
        v = deref(ev(n.arg, ctx))
        if n.op == "+":
            return v
        return _lift1(v, lambda x: neg(to_number(x)))
    if t is F.Percent:
        v = deref(ev(n.arg, ctx))
        return _lift1(v, lambda x: div(to_number(x), 100.0))
    if t is F.Unit:
        _follow_custom(n.text, ctx)
        return _unit(n.text)
    if t is F.Name:
        return _name(n, ctx)
    if t is F.DocVar:
        return _calc_var(n, ctx)
    if t is F.Apply:
        from .functions import apply
        return apply(n, ctx)
    if t is F.SpillRef:
        return _spill_ref(n, ctx)
    if t is F.Structured:
        return structured(n, ctx)
    if t is F.BadRef:
        return REF.because("the formula reads cells that were deleted (#REF! is in the formula)")
    if t is F.ArrayLit:
        return Array(tuple(tuple(ev(x, ctx) for x in row) for row in n.rows))
    if t is F.Missing:
        return BLANK
    raise SheetError(VALUE)


def _intersect(v, ctx):
    """Excel's @: one value from a block — the cell in the formula's own row
    (a column) or column (a row), the first of an array."""
    if isinstance(v, RefValue):
        if v.single:
            return v.value_at(0, 0)
        if v.width == 1 and v.top <= ctx.row <= v.bottom:
            return v.value_at(ctx.row - v.top, 0)
        if v.height == 1 and v.left <= ctx.col <= v.right:
            return v.value_at(0, ctx.col - v.left)
        return VALUE.because("@ found no cell of the block in this formula's row or column")
    if isinstance(v, Array):
        return v.get(0, 0)
    return v


def _follow_custom(text: str, ctx: Ctx) -> None:
    """A custom unit ('kip_s): the cell follows the equation defining it, as
    it follows a document variable it reads."""
    if not is_unit_text(text):
        for name in re.findall(r"[^\W\d][\w]*", text):
            ctx.reads.add(name.lower())


def _unit(text: str, custom: bool = True):
    """1 of a unit; a custom unit (one the equations define) only when
    written SMath's way, 'kip_s — never a bare name."""
    try:
        factor, dims, _offset = unit_parts(text, custom=custom)
    except UnitTextError:
        raise failed(NAME, f"'{text}' isn't a unit")
    if not any(dims):
        return factor
    return Qty(factor, dims, text)


def _sheet_of(name: Optional[str], ctx: Ctx):
    if name is None:
        return ctx.sheet
    wb = ctx.wb
    if wb._in_pass:
        # sheets don't come, go or change their names while calculating:
        # each looked up once a pass (Tables!B2 in thousands of formulas)
        cache = wb._pass_cache
        sheet = cache.get(("sheet", name))
        if sheet is None:
            sheet = wb.sheet(name)
            if sheet is not None:
                cache[("sheet", name)] = sheet
    else:
        sheet = wb.sheet(name)
    if sheet is None:
        raise failed(REF, f"there's no sheet or table called '{name}'")
    return sheet


def reach(ctx: Ctx, ref: RefValue) -> RefValue:
    """Another sheet's cells, if this one may read them: one in an earlier
    calculation section only where they were made global (the document's
    workbook says, Workbook.reach)."""
    allowed = ctx.wb.reach
    if allowed is not None and ref.sheet is not ctx.sheet and \
            not allowed(ctx.sheet, ref.sheet, (ref.top, ref.left, ref.bottom, ref.right)):
        raise failed(REF, f"{ref.sheet.name} is in an earlier calc section: make its cells "
                          "global (right-click, Make Global) to read them here")
    return ref


def _ref(n: F.Ref, ctx: Ctx) -> RefValue:
    sheet = _sheet_of(n.sheet, ctx)
    row, col = n.at(ctx.row, ctx.col)
    if not (0 <= row < MAX_ROWS and 0 <= col < MAX_COLS):
        raise failed(REF, "the reference falls off the edge of the sheet")
    return reach(ctx, RefValue(sheet, row, col, row, col))


def _area(n: F.Area, ctx: Ctx) -> RefValue:
    sheet = _sheet_of(n.sheet, ctx)
    r1, c1 = n.first.at(ctx.row, ctx.col)
    r2, c2 = n.last.at(ctx.row, ctx.col)
    top, bottom = min(r1, r2), max(r1, r2)
    left, right = min(c1, c2), max(c1, c2)
    if top < 0 or left < 0 or bottom >= MAX_ROWS or right >= MAX_COLS:
        raise failed(REF, "the block falls off the edge of the sheet")
    return reach(ctx, RefValue(sheet, top, left, bottom, right))


def _spill_ref(n: F.SpillRef, ctx: Ctx) -> RefValue:
    """A1#: the block A1's formula spills (#REF! when it spills nothing)."""
    sheet = _sheet_of(n.ref.sheet, ctx)
    row, col = n.ref.at(ctx.row, ctx.col)
    ctx.wb.value(sheet, row, col)               # calculated first
    size = sheet.spills.get((row, col))
    if size is not None:
        return reach(ctx, RefValue(sheet, row, col, row + size[0] - 1, col + size[1] - 1))
    cell = sheet.cells.get((row, col))
    if cell is not None and cell.is_formula and (row, col) not in sheet.wanted:
        return RefValue(sheet, row, col, row, col)
    raise failed(REF, f"{col_letters(col)}{row + 1}# reads the block a formula there spills, "
                      "and none spills there")


def table_for(n: F.Structured, ctx: Ctx):
    sheet = ctx.sheet if n.table is None else ctx.wb.sheet(n.table)
    if sheet is None or sheet.kind != "table" or not sheet.size:
        raise failed(REF, f"there's no table called '{n.table}'" if n.table else
                     "a [column] reference without a table's name works only inside a table")
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
            missing = n.first if a is None else n.last
            raise failed(REF, f"{sheet.name} has no column headed '{missing}'")
        left, right = min(a, b), max(a, b)
    specials = set(n.specials) or {"#Data"}
    if "#Totals" in specials:
        raise failed(REF, f"{sheet.name} has no totals row")     # a table here has none
    if "@" in specials:
        if ctx.sheet is not sheet or not 1 <= ctx.row < rows:
            raise failed(VALUE, "[@...] means this row of the table, so it works only in the "
                                "table's own rows")
        top = bottom = ctx.row
    elif "#All" in specials or {"#Headers", "#Data"} <= specials:
        top, bottom = 0, rows - 1
    elif "#Headers" in specials:
        top = bottom = 0
    else:
        top, bottom = 1, rows - 1
        if bottom < top:
            raise failed(REF, f"{sheet.name} has only its heading row, no data")
    return reach(ctx, RefValue(sheet, top, left, bottom, right))


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
            raise failed(REF, f"there's no sheet or table called '{unquote_sheet(n.sheet)}'")
    # an Excel name only: a CalcForge variable is read as CALC(name)
    dn = ctx.wb.find_excel_name(n.name, sheet)
    if dn is not None and n.sheet is not None:
        closed = ctx.wb.closed_to(dn, ctx.sheet)
        if closed is not None:
            # dialled in from outside a self-contained workbook: its names
            # are its cells' only (the user, 2026-10-24)
            return NAME.because(f"{n.name} is a name of {closed.name}, which is self-contained: "
                                f"only its own cells read its names")
    if dn is not None:
        return _defined(n.name, dn, ctx)
    if n.sheet is None:
        try:
            return _unit(n.name, custom=False)
        except SheetError:
            pass
        ctx.reads.add(n.name.lower())   # its reason says CALC(x) once x is there
        return NAME.because(not_known(n.name, ctx))
    return NAME.because(f"'{n.name}' isn't a defined name on {n.sheet}")


def _defined(name: str, dn, ctx: Ctx):
    """What the defined name *dn* (read as *name*) refers to."""
    if ctx.depth > 40:
        raise failed(NUM, f"the name '{name}' refers to itself, round and round")
    # what it refers to, read once while it stays the same (parsing it
    # again for every formula that uses it was most of a name's cost)
    held = dn.__dict__.get("_parsed")
    if held is not None and held[0] == dn.refers_to:
        parsed = held[1]
    else:
        try:
            parsed = F.parse(dn.refers_to, 0, 0)
        except F.FormulaError:
            return NAME.because(f"the defined name '{name}' is a formula that can't be read")
        dn.__dict__["_parsed"] = (dn.refers_to, parsed)
    home = ctx.wb.sheet_by_id(dn.sheet) if dn.sheet else ctx.sheet
    inner = Ctx(ctx.wb, home, 0, 0)
    inner.reads = ctx.reads
    inner.depth = ctx.depth + 1
    global _referred
    if _referred is None:
        from .compiled import referred as _referred
    got = _referred(parsed)(inner)           # a name of one cell stays its reference
    if isinstance(got, ErrorValue) and got.code == REF.code:
        got = ErrorValue(got.code, _lost_name(name, dn, ctx))
    return got


def _lost_name(name: str, dn, ctx: Ctx) -> str:
    """Why a defined name gives #REF!: the cells it named were deleted (Excel
    keeps it so, Height = Calculations!#REF!) — and, when the equations have
    a variable of that name, how to read theirs instead: a workbook's own
    name comes first in its cells, as in Excel (the user, 2026-10-24: a
    variable height on a page, =height in a cell of the Seismic Parts
    workbook gave #REF!)."""
    why = f"the defined name '{dn.name}' refers to cells that were deleted ({dn.refers_to})"
    if _is_calc_variable(name, ctx):
        return why + f"; CALC({name}) reads the CalcForge variable {name}"
    return why


def _is_calc_variable(name: str, ctx: Optional["Ctx"]) -> bool:
    """Whether CALC(name) would read something where *ctx* is."""
    ask = (ctx.wb.calc_variable or ctx.wb.outside) if ctx is not None else None
    if ask is None:
        return False
    try:
        ask(ctx.sheet, name)
    except (KeyError, SheetError):
        return False
    return True


def not_known(name: str, ctx: Optional["Ctx"] = None) -> str:
    """Why a name gives #NAME? (QA, 2026-10-15: errors say what went wrong):
    and when it is a CalcForge variable, how a cell reads one."""
    if _is_calc_variable(name, ctx):
        return (f"'{name}' isn't an Excel name of this workbook or sheet; the CalcForge "
                f"variable {name} is read as CALC({name})")
    return f"'{name}' isn't a function or an Excel name of this workbook or sheet"


def _calc_var(n: F.DocVar, ctx: Ctx):
    """CALC(x): the CalcForge variable x — an equation's, or a cell named in
    its Variable box — in force where the sheet is (the user, 2026-10-24:
    "to use a calc forge variable, you always have to do var(variable),
    maybe change from var to something excel does not have as a function,
    so there can never be a clash"). Never an Excel name."""
    ctx.reads.add(n.name.lower())
    ask = ctx.wb.calc_variable
    if ask is None and ctx.wb.outside is not None:
        # a workbook of its own (no document): the equations' variables only
        def ask(sheet, name, outside=ctx.wb.outside):
            return from_engine(outside(sheet, name))
    if ask is None:
        return NAME.because(f"CALC({n.name}): there are no CalcForge variables here")
    try:
        got = ask(ctx.sheet, n.name)
    except KeyError as e:
        why = e.args[0] if e.args and isinstance(e.args[0], str) and " " in e.args[0] else \
            f"CALC({n.name}): there's no CalcForge variable {n.name} before this sheet"
        return NAME.because(why)
    except SheetError as e:
        return e.error
    from .workbook import DefinedName
    if isinstance(got, DefinedName):
        return _defined(n.name, got, ctx)
    return got                          # an equation's, as a cell's value


def from_engine(value, engineering: bool = True):
    """A value from the equations as a cell value.

    A quantity keeps the unit the equations show it in (35 kN·m, 5 kPa —
    what M= and s= show), not base SI units (35000 J, 5000 Pa): a cell
    reading =M shows what the equation shows, and =F*2 goes on in kN as a
    typed 10 kN*2 does (the user, 2026-10-15). *engineering* is the
    worksheet's engineering-units setting, which picks the prefix."""
    from calcforge.calc.engine.units import Quantity
    from calcforge.calc.engine.values import Matrix, String

    if isinstance(value, Quantity):
        v = value.value
        if isinstance(v, complex):
            if v.imag != 0:
                return NUM
            v = v.real
        if any(value.dims):
            v = float(v)
            if not math.isfinite(v):
                return Qty(v, tuple(value.dims), None)
            return Qty(v, tuple(value.dims),
                       equation_unit(tuple(value.dims), v, engineering) or None)
        return float(v)
    if isinstance(value, String):
        return value.text
    if isinstance(value, Matrix):
        rows = []
        for i in range(value.nrows):
            rows.append(tuple(from_engine(value.get(i, j), engineering) for j in range(value.ncols)))
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
            return VALUE.because("a : needs a cell on each side, on the same sheet") \
                if not isinstance(a, ErrorValue) else a
        return RefValue(a.sheet, min(a.top, b.top), min(a.left, b.left),
                        max(a.bottom, b.bottom), max(a.right, b.right))
    # 5 °C: a number written in a unit that has an offset
    if op == "*" and type(n.right) is F.Unit and type(n.left) is F.Num:
        _follow_custom(n.right.text, ctx)
        try:
            return with_unit(n.left.value, n.right.text)
        except UnitTextError:
            return NAME.because(f"'{n.right.text}' isn't a unit")
    a = deref(ev(n.left, ctx))
    b = deref(ev(n.right, ctx))
    if isinstance(a, Array) or isinstance(b, Array):
        return _broadcast(a, b, lambda x, y: _scalar_op(op, x, y))
    got = _scalar_op(op, a, b)
    if isinstance(got, ErrorValue) and got is not a and got is not b:
        return _located(got, n, b, ctx)
    return got


def _located(error: ErrorValue, n: F.Binary, b, ctx: Ctx) -> ErrorValue:
    """An error an operator made, saying where: "kN and m can't be added
    (A1 + A2)", "dividing by zero (B4 is 0)" (QA, 2026-10-15)."""
    left, right = operand_text(n.left, ctx), operand_text(n.right, ctx)
    if error.code == DIV0.code and n.op == "/" and type(n.right) is F.Ref:
        where = f"{right} is empty" if b is BLANK else f"{right} is 0"
    elif left is None and right is None:
        return error
    else:
        where = f"{left or '...'} {n.op} {right or '...'}"
    reason = error.reason or "this can't be worked out"
    return ErrorValue(error.code, f"{reason} ({where})")


def operand_text(node, ctx: Ctx) -> Optional[str]:
    """How a message names part of a formula: A1, Loads!B2, Span, 5 kN;
    None for anything longer."""
    t = type(node)
    if t is F.Ref:
        row, col = node.at(ctx.row, ctx.col)
        if not (0 <= row < MAX_ROWS and 0 <= col < MAX_COLS):
            return None
        return (quote_sheet(node.sheet) + "!" if node.sheet else "") + f"{col_letters(col)}{row + 1}"
    if t is F.Area:
        r1, c1 = node.first.at(ctx.row, ctx.col)
        r2, c2 = node.last.at(ctx.row, ctx.col)
        if min(r1, r2, c1, c2) < 0:
            return None
        return (quote_sheet(node.sheet) + "!" if node.sheet else "") + \
            f"{col_letters(c1)}{r1 + 1}:{col_letters(c2)}{r2 + 1}"
    if t is F.Name:
        return node.name if node.sheet is None else f"{node.sheet}!{node.name}"
    if t is F.DocVar:
        return f"{F.CALC}({node.name})"
    if t is F.Num:
        return general_number(node.value)
    if t is F.Unit:
        return "'" + node.text
    if t is F.Binary and node.op == "*" and type(node.left) is F.Num and type(node.right) is F.Unit:
        return f"{general_number(node.left.value)} {node.right.text}"
    if t is F.Str:
        return '"' + node.value + '"' if len(node.value) <= 20 else None
    if t is F.Call:
        return f"{node.name}(...)"
    return None


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
        return NUM.because("the result is too big")


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
                raise units_clash(x, y, "compared")
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
