"""A document's tables and sheet sections, and how they meet its equations.

Every table and sheet section of a document is a sheet of one
:class:`DocumentBook` workbook, so a formula can read any of them by name.

Between them and the equations (docs/SPREADSHEET_DESIGN.md):

* a table or sheet reads the document variables defined before it in
  reading order (its top-left corner is its place);
* the equations read a table's values four ways:
    - a named cell:            W_total            (Formulas ▸ Define Name)
    - a cell of a table:       Loads.D12
    - a column by its heading: Loads.Load         (the values under the heading, as a vector)
    - the table as a lookup:   bolts(d, "A")      (first column searched, interpolated)
* where the two disagree with reading order, dependencies win: after every
  calculation the tables take up changed variables and the equations
  changed table values, until nothing changes (a true loop stops and is
  reported as circular).
"""
from __future__ import annotations

import math
import re
from typing import Callable, Optional

from .evaluate import RefValue, from_engine, to_engine
from .refs import parse_cell
from .values import ErrorValue, Qty, SheetError, is_number
from .workbook import Sheet, Workbook

STRIDE = 1_000_000.0


class DocumentBook:
    """The document's workbook, kept in step with its equations."""

    def __init__(self, document):
        self.document = document
        self.workbook = Workbook()
        self.workbook.journal = False           # the window's undo stack records pages
        self.workbook.outside = self._outside
        self.by_uid: dict[str, Sheet] = {}
        self._parked: dict[str, Sheet] = {}
        self._places: dict[str, tuple] = {}     # uid -> (page uid, x px, y px)
        self._asked: dict[str, int] = {}        # name the equations asked for -> sheet id
        self._syncing = False
        self.circular = False
        # told the (sheet id, row, col) keys whose values changed (tables redraw)
        self.listeners: list[Callable[[set], None]] = []
        self.workbook.listeners.append(self._changed)
        self._sheet = None
        # How to run something just after the current work (the window sets
        # it to the event loop): tables and equations take up each other's
        # changes then, never from inside a calculation or while Qt is still
        # putting an item on its page. None runs it at once.
        self.later: Optional[Callable[[Callable[[], None]], None]] = None
        self._queued: set = set()
        self.workbook.on_names_changed = self._names_changed

    def _names_changed(self) -> None:
        """A table came, went or was renamed, or a name was defined: the
        equations that use names are calculated again (once, soon)."""
        if self._sheet is None or self._loading:
            return
        self._soon("names", lambda: self._calc().recalculate())

    _loading = False

    # -- sheets coming and going ------------------------------------------------------
    def attach(self, uid: str, name: Optional[str] = None, kind: str = "table") -> Sheet:
        """The sheet of a table or sheet section (made, or brought back)."""
        sheet = self.by_uid.get(uid)
        if sheet is not None:
            return sheet
        sheet = self._parked.pop(uid, None)
        wb = self.workbook
        if sheet is not None:
            if wb.sheet(sheet.name) is not None:
                sheet.name = wb.free_name("Table" if kind == "table" else "Sheet")
            wb.sheets.append(sheet)
            wb._names_changed()
        else:
            if name and wb.sheet(name) is not None:
                name = None
            sheet = wb.add_sheet(name, kind)
        self.by_uid[uid] = sheet
        self._hook_equations()
        return sheet

    def detach(self, uid: str) -> None:
        """A table left the document (deleted, or its page removed): what
        reads it shows #REF!, until it comes back (undo)."""
        sheet = self.by_uid.pop(uid, None)
        if sheet is None:
            return
        self._parked[uid] = sheet
        from .store import names_homed_on
        for name, _refers, local, _comment in names_homed_on(sheet):
            self.workbook.names.pop((name.lower(), sheet.id if local else None), None)
            self.workbook._name_dirty(name.lower())
        if sheet in self.workbook.sheets:
            self.workbook.sheets.remove(sheet)
            self.workbook._names_changed()
        self._places.pop(uid, None)
        self.equations_may_have_changed({sheet.id})

    def place(self, uid: str, page_uid: str, x_px: float, y_px: float) -> None:
        """Where a table sits (its top-left, in SMath pixels on its page as written)."""
        if self._places.get(uid) == (page_uid, x_px, y_px):
            return
        self._places[uid] = (page_uid, x_px, y_px)
        sheet = self.by_uid.get(uid)
        if sheet is not None:
            self.workbook.outside_changed({n for n in self.workbook.outside_names_read()})

    def _key(self, sheet: Sheet) -> tuple:
        uid = next((u for u, s in self.by_uid.items() if s is sheet), None)
        place = self._places.get(uid) if uid else None
        if place is None:
            return (float("inf"),)
        orders = {page.uid: i for i, page in enumerate(self.document.pages)}
        page_uid, x, y = place
        return (orders.get(page_uid, len(orders)) * STRIDE + y, x, -1)

    # -- tables reading the equations ---------------------------------------------------------
    def _calc(self):
        if self._sheet is None:
            from calcforge.calc.docsheet import sheet_for

            self._sheet = sheet_for(self.document)
        return self._sheet

    def _outside(self, sheet: Sheet, name: str):
        """A document variable as the table sees it: defined before it."""
        ws = self._calc().worksheet
        value = ws.index.var_before(name, self._key(sheet))
        if value is None:
            from calcforge.calc.engine.evaluator import BUILTIN_CONSTANTS

            value = BUILTIN_CONSTANTS.get(name)
        if value is None:
            raise KeyError(name)
        from calcforge.calc.engine.units import Quantity
        from calcforge.calc.engine.values import Matrix, String

        if not isinstance(value, (Quantity, Matrix, String)):
            raise KeyError(name)
        return value

    # -- the equations reading tables --------------------------------------------------------------
    def _hook_equations(self) -> None:
        ws = self._calc().worksheet
        if ws.external is not self:
            ws.external = self
            calc = self._calc()
            if self._after_calculation not in calc.listeners:
                calc.listeners.append(self._after_calculation)

    def _named(self, name: str):
        """(sheet, RefValue or value) for a name the equations use, or None."""
        wb = self.workbook
        dn = wb.find_name(name, None)
        if dn is not None:
            from . import formula as F
            from .evaluate import Ctx, ev

            try:
                tree = F.parse(dn.refers_to).tree
            except F.FormulaError:
                return None
            home = wb.sheet_by_id(dn.sheet) if dn.sheet else (wb.sheets[0] if wb.sheets else None)
            if home is None:
                return None
            got = ev(tree, Ctx(wb, home, 0, 0))
            sheet = got.sheet if isinstance(got, RefValue) else home
            return sheet, got
        if "." in name:
            table, _, rest = name.partition(".")
            sheet = wb.sheet(table)
            if sheet is None:
                return None
            ref = parse_cell(rest)
            if ref is not None and not ref.row_abs and not ref.col_abs:
                return sheet, RefValue(sheet, ref.row, ref.col, ref.row, ref.col)
            column = self._column(sheet, rest)
            if column is not None:
                return sheet, column
        return None

    @staticmethod
    def _column(sheet: Sheet, heading: str) -> Optional[RefValue]:
        """The values under a heading in a table's first row."""
        for (row, col), cell in sheet.cells.items():
            if row == 0 and isinstance(cell.value, str) and _ident(cell.value) == heading:
                bottom = max((r for r, c in sheet.cells if c == col), default=0)
                if bottom < 1:
                    return None
                return RefValue(sheet, 1, col, bottom, col)
        return None

    def equation_names(self) -> dict:
        """The names the equations can read from the tables, for their
        autocomplete: defined names, and Table.Column for each heading."""
        out = {}
        for (lower, scope), dn in self.workbook.names.items():
            if scope is None:
                out[dn.name] = f"named cells: ={dn.refers_to}"
        for sheet in self.workbook.sheets:
            if sheet.kind != "table":
                continue
            for (row, col), cell in sheet.cells.items():
                if row == 0 and isinstance(cell.value, str) and _ident(cell.value):
                    out[f"{sheet.name}.{_ident(cell.value)}"] = f"column “{cell.value}” of {sheet.name}"
        return out

    def has(self, name: str) -> bool:
        return self._named(name) is not None

    def value(self, name: str):
        got = self._named(name)
        if got is None:
            return None
        sheet, value = got
        self._asked[name] = sheet.id
        if isinstance(value, RefValue):
            value = value.value_at(0, 0) if value.single else value.to_array()
        if isinstance(value, ErrorValue):
            from calcforge.calc.engine.errors import SMathError

            raise SMathError(f"{name} is {value.code} in its table.")
        try:
            return to_engine(value)
        except SheetError as e:
            from calcforge.calc.engine.errors import SMathError

            raise SMathError(f"{name} is {e.error.code} in its table.")

    def function(self, name: str, nargs: int):
        """A table used as a lookup: name(x), name(x, "heading"), name(x, y)."""
        sheet = self.workbook.sheet(name)
        if sheet is None or not 1 <= nargs <= 3 or not _ident_ok(name):
            return None

        def look(args):
            self._asked[name] = sheet.id
            return lookup(sheet, args)
        return look

    def names(self) -> set:
        out = {dn.name for dn in self.workbook.names.values()}
        for sheet in self.workbook.sheets:
            for (row, col), cell in sheet.cells.items():
                if row == 0 and isinstance(cell.value, str) and _ident(cell.value):
                    out.add(f"{sheet.name}.{_ident(cell.value)}")
        return out

    # -- keeping both up to date ----------------------------------------------------------------------
    def _changed(self, keys: set) -> None:
        for listener in list(self.listeners):
            listener(keys)
        if not self._syncing:
            sheets = {k[0] for k in keys if isinstance(k[0], int)}
            if sheets:
                self._soon("tables", lambda: self.equations_may_have_changed(sheets), sheets)

    def _soon(self, what: str, run: Callable[[], None], sheets: Optional[set] = None) -> None:
        if self.later is None:
            run()
            return
        if what == "tables":
            pending = getattr(self, "_pending_sheets", set())
            pending |= sheets or set()
            self._pending_sheets = pending
            run = lambda: self.equations_may_have_changed(self.__dict__.pop("_pending_sheets", set()))
        if what in self._queued:
            return
        self._queued.add(what)

        def go():
            self._queued.discard(what)
            run()
        self.later(go)

    def equations_may_have_changed(self, sheets: set) -> None:
        """Table values changed: the equations that read them calculate again."""
        names = {n for n, sid in self._asked.items() if sid in sheets}
        if not names:
            return
        calc = self._calc()
        ws = calc.worksheet
        if not ws.auto_calculation or self._syncing:
            return
        self._syncing = True
        try:
            for _round in range(20):
                ws._propagate((-math.inf,), set(names))
                changed = self.workbook.outside_changed(None) if self.workbook.outside_names_read() else set()
                sheets = {k[0] for k in changed if isinstance(k[0], int)}
                names = {n for n, sid in self._asked.items() if sid in sheets}
                if not names:
                    self.circular = False
                    break
            else:
                self.circular = True
        finally:
            self._syncing = False
        calc._report()

    def _after_calculation(self) -> None:
        """The equations calculated: tables reading their variables follow."""
        if self._syncing or not self.workbook.outside_names_read():
            return
        self._soon("equations", self._take_up_equations)

    def _take_up_equations(self) -> None:
        if self._syncing or not self.workbook.outside_names_read():
            return
        self._syncing = True
        try:
            changed = self.workbook.outside_changed(None)
        finally:
            self._syncing = False
        sheets = {k[0] for k in changed if isinstance(k[0], int)}
        if sheets:
            self.equations_may_have_changed(sheets)


def _ident(text: str) -> str:
    """A heading as a name the equations can use: "Load (kN)" -> "Load"."""
    text = text.strip()
    m = re.match(r"[^\W\d][\w]*", text)
    return m.group(0) if m else ""


def _ident_ok(name: str) -> bool:
    return bool(re.fullmatch(r"[^\W\d][\w.]*", name))


def lookup(sheet: Sheet, args: list):
    """bolts(x): the row for x in the first column (interpolated between rows);
    bolts(x, "A"): its value under heading A (or column number);
    bolts(x, y): with numbers along the first row, interpolated both ways."""
    from calcforge.calc.engine.errors import SMathError
    from calcforge.calc.engine.values import Matrix, String

    used = sheet.used_area()
    if used is None:
        raise SMathError(f"{sheet.name} is empty.")
    _top, _left, bottom, right = used
    header = [sheet.value(0, c) for c in range(0, right + 1)]
    keys = [(r, sheet.value(r, 0)) for r in range(1, bottom + 1)]
    keys = [(r, k) for r, k in keys if is_number(k)]
    if not keys:
        raise SMathError(f"{sheet.name} has no numbers in its first column.")
    x = from_engine(args[0])
    if not is_number(x):
        raise SMathError("The value looked up must be a number.")

    def si(v):
        return v.si if isinstance(v, Qty) else float(v)

    def dims(v):
        return v.dims if isinstance(v, Qty) else None

    if any(dims(k) != dims(x) for _r, k in keys):
        from calcforge.calc.engine.errors import err
        raise err("units_mismatch")
    xs = si(x)
    keys.sort(key=lambda e: si(e[1]))
    lo = hi = None
    for (r0, k0), (r1, k1) in zip(keys, keys[1:]):
        if si(k0) <= xs <= si(k1):
            lo, hi = (r0, si(k0)), (r1, si(k1))
            break
    if lo is None:
        if len(keys) == 1 or si(keys[0][1]) == xs:
            lo = hi = (keys[0][0], si(keys[0][1]))
        elif si(keys[-1][1]) == xs:
            lo = hi = (keys[-1][0], si(keys[-1][1]))
        else:
            raise SMathError(f"{args and 'The value'} is outside the table {sheet.name}.")
    t = 0.0 if hi[1] == lo[1] else (xs - lo[1]) / (hi[1] - lo[1])

    def at_row(col):
        a, b = sheet.value(lo[0], col), sheet.value(hi[0], col)
        if not (is_number(a) and is_number(b)):
            return a if t < 0.5 else b
        from .values import add, mul, sub
        return add(a, mul(sub(b, a), t)) if t else a

    cols = list(range(1, right + 1))
    if len(args) == 1:
        values = [at_row(c) for c in cols]
        return to_engine(values[0]) if len(values) == 1 else Matrix(len(values), 1, [to_engine(v) for v in values])
    second = args[1]
    picks = []
    if isinstance(second, String):
        for name in args[1:]:
            if not isinstance(name, String):
                raise SMathError("Give the headings as text: bolts(d, \"A\", \"B\").")
            c = next((c for c in cols if isinstance(header[c], str) and
                      header[c].strip().lower() == name.text.strip().lower()), None)
            if c is None:
                raise SMathError(f"{sheet.name} has no heading {name.text}.")
            picks.append(c)
        values = [at_row(c) for c in picks]
        return to_engine(values[0]) if len(values) == 1 else Matrix(len(values), 1, [to_engine(v) for v in values])
    y = from_engine(second)
    if all(is_number(h) for h in header[1:]) and is_number(y) and len(args) == 2:
        heads = sorted(((c, si(header[c])) for c in cols), key=lambda e: e[1])
        ys = si(y)
        for (c0, h0), (c1, h1) in zip(heads, heads[1:]):
            if h0 <= ys <= h1:
                u = 0.0 if h1 == h0 else (ys - h0) / (h1 - h0)
                from .values import add, mul, sub
                a, b = at_row(c0), at_row(c1)
                return to_engine(add(a, mul(sub(b, a), u)) if u else a)
        if heads and heads[-1][1] == ys:
            return to_engine(at_row(heads[-1][0]))
        raise SMathError(f"The value is outside the table {sheet.name}.")
    # a column number
    k = int(round(si(y)))
    if not 1 <= k <= len(cols):
        raise SMathError(f"{sheet.name} has no column {k}.")
    return to_engine(at_row(cols[k - 1]))


def book_for(document) -> DocumentBook:
    book = getattr(document, "_sheet_book", None)
    if book is None:
        book = DocumentBook(document)
        document._sheet_book = book
    return book
