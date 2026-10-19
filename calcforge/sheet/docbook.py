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
* a table's names are defined where the table is: an equation reads the
  latest definition before it in reading order, an equation's or a
  table's (the user's report, 2026-10-17: test:=5 kN, then a sheet's cell
  named test, then test= gives the cell's 2). A name defined only below an
  equation is not defined there, as in SMath ("test - not defined."), even
  when a table further down has it (the user's answer, 2026-10-17);
* after every calculation the tables take up changed variables and the
  equations changed table values, until nothing changes (a true loop stops
  and is reported as circular).
"""
from __future__ import annotations

import math
import re
from typing import Callable, Optional

from .evaluate import RefValue, from_engine, result, to_engine
from .refs import parse_cell
from .values import Array, ErrorValue, Qty, SheetError, is_number
from .workbook import Sheet, Workbook

STRIDE = 1_000_000.0


class DocumentBook:
    """The document's workbook, kept in step with its equations."""

    def __init__(self, document):
        self.document = document
        self.workbook = Workbook()
        self.workbook.journal = False           # the window's undo stack records pages
        self.workbook.outside = self._outside
        self.workbook.reach = self._reach
        self.workbook.order_key = self._key
        # SMath's custom units: a quantity the equations define is a unit in the cells
        import weakref

        from . import values as _values
        method = weakref.WeakMethod(self._custom_unit)

        def custom(name, method=method):
            found = method()
            return found(name) if found is not None else None
        _values.CUSTOM_UNITS = custom
        # the reading key of the equation now asking for a table's values
        # (calc/worksheet.py sets it), for the calculation sections
        self.reading_at = None
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
        from .store import name_key, names_homed_on
        for name, _refers, local, _comment in names_homed_on(sheet):
            self.workbook.names.pop(name_key(sheet, name, local), None)
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
        sheet = self.by_uid.get(uid)
        was = self._key(sheet) if sheet is not None else None
        self._places[uid] = (page_uid, x_px, y_px)
        if sheet is not None:
            self.workbook.outside_changed({n for n in self.workbook.outside_names_read()})
            if self._passed_equations(was, self._key(sheet)):
                # its names now come before or after other definitions
                self._names_changed()

    def _passed_equations(self, was, now) -> bool:
        """Whether a table moving from reading key *was* to *now* passed an
        equation (or a calculation section's start) on the way."""
        if self._sheet is None or was == now:
            return False
        low, high = (was, now) if was < now else (now, was)
        calc = self._sheet
        if any(low < start <= high for start in calc.section_starts()):
            return True
        import bisect
        ws = calc.worksheet
        ws.ordered()
        keys = ws._order_keys
        i = bisect.bisect_right(keys, low)
        return i < len(keys) and keys[i] < high

    def _custom_unit(self, name: str):
        """(factor, dims) of a custom unit — a quantity with units the
        document's equations define (its last definition) — or None."""
        if self._sheet is None and self.document is None:
            return None
        lst = self._calc().worksheet.index.vars.get(name)
        if not lst:
            return None
        from calcforge.calc.engine.units import Quantity

        value = lst[-1][1]
        if not isinstance(value, Quantity):
            return None
        try:
            got = from_engine(value)
        except Exception:                              # noqa: BLE001
            return None
        if not isinstance(got, Qty) or not any(got.dims):
            return None
        return got.si, got.dims

    # -- calculation sections --------------------------------------------------------------
    def _section(self, key) -> int:
        return self._calc().section_of_key(key)

    @staticmethod
    def _within(area, ranges) -> bool:
        """Whether every cell of *area* is in one of *ranges* (or their union)."""
        t, l, b, r = area
        if not ranges:
            return False
        for row in range(t, b + 1):
            for col in range(l, r + 1):
                if not any(rt <= row <= rb and rl <= col <= rr for rt, rl, rb, rr in ranges):
                    return False
                if (b - t + 1) * (r - l + 1) > 20000:
                    break
        return True

    def readable(self, sheet: Sheet, area, at_key) -> bool:
        """Whether cells *area* of *sheet* are seen from reading key *at_key*:
        in its own section, or later ones where they were made global."""
        if at_key is None or not self._calc().section_starts():
            return True
        mine, theirs = self._section(at_key), self._section(self._key(sheet))
        if mine == theirs:
            return True
        if theirs > mine:
            return False
        return self._within(area, (sheet.page or {}).get("global_cells") or [])

    def _reach(self, reader: Sheet, sheet: Sheet, area) -> bool:
        wb = self.workbook
        if wb._in_pass:
            # while calculating, the sections and the sheets' places stand
            # still: worked out once a pass, not for every cell read from
            # another sheet (a page walk each: 5000 a pass, 2026-10-19)
            cache = wb._pass_cache
            starts = cache.get("starts")
            if starts is None:
                starts = cache["starts"] = tuple(self._calc().section_starts())
            if not starts:
                return True
            key = cache.get(("key", reader.id))
            if key is None:
                key = cache[("key", reader.id)] = self._key(reader)
            return self.readable(sheet, area, key)
        return self.readable(sheet, area, self._key(reader))

    def sections_changed(self) -> None:
        """Section breaks or global cells changed: every sheet calculates again."""
        self.workbook.recalculate(everything=True)

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
        # in the unit the equations show it in (35 kN·m, not 35000 J), with
        # this worksheet's engineering-units setting (the user, 2026-10-15)
        fmt = getattr(ws, "format", None)
        return from_engine(value, bool(getattr(fmt, "engineering", True)))

    # -- the equations reading tables --------------------------------------------------------------
    def _hook_equations(self) -> None:
        ws = self._calc().worksheet
        if ws.external is not self:
            ws.external = self
            calc = self._calc()
            if self._after_calculation not in calc.listeners:
                calc.listeners.append(self._after_calculation)

    def _named(self, name: str, at_key=None):
        """(sheet, RefValue or value) for a name the equations use, or None.

        A bare name is a document name, or a name of an imported workbook
        that isn't self-contained (the latest before *at_key* in reading
        order); a self-contained workbook's names are read only qualified:
        ``Sheet.Name`` (the name as that sheet's cells read it: the sheet's
        own, then its workbook's) or ``Book.Name`` (the workbook's). A
        sheet's cell is ``Sheet.H44``; a table's column ``Table.Heading``.
        Sheets are written as their names, or with each run of spaces and
        other characters an equation can't hold as one _ (Seismic Actions:
        Seismic_Actions)."""
        wb = self.workbook
        lower = name.lower()
        dn = wb.names.get((lower, None))
        other = wb.open_book_name(lower, None, at_key) if wb.books else None
        if other is not None and (dn is None or self._later(other, dn, at_key)):
            dn = other                   # (both: the latest before the equation)
        if dn is not None:
            return self._name_value(dn)
        if "." in name:
            table, _, rest = name.partition(".")
            sheet = sheet_named(wb, table)
            if sheet is not None:
                ref = parse_cell(rest)
                if ref is not None and not ref.row_abs and not ref.col_abs:
                    return sheet, RefValue(sheet, ref.row, ref.col, ref.row, ref.col)
                local = wb.names.get((rest.lower(), sheet.id))
                if local is None and sheet.book is not None:
                    local = wb.names.get((rest.lower(), sheet.book))
                if local is not None:
                    return self._name_value(local)
                column = self._column(sheet, rest)
                if column is not None:
                    return sheet, column
            book = book_named(wb, table)
            if book is not None:
                own = wb.names.get((rest.lower(), book.id))
                if own is not None:
                    return self._name_value(own)
        return None

    def _later(self, a, b, at_key) -> bool:
        """Whether defined name *a* is defined after *b* (where their sheets
        are) and still before *at_key*: the one an equation there reads."""
        wb = self.workbook

        def key(dn):
            home = wb.sheet_by_id(dn.home) if dn.home is not None else None
            return self._key(home) if home is not None else (float("inf"),)
        ka, kb = key(a), key(b)
        if at_key is not None and not kb < tuple(at_key):
            return True
        return kb < ka and (at_key is None or ka < tuple(at_key))

    def _name_value(self, dn):
        """(sheet, RefValue or value) of a defined name, as the equations read it."""
        from . import formula as F
        from .evaluate import Ctx, ev

        wb = self.workbook
        try:
            tree = F.parse(dn.refers_to).tree
        except F.FormulaError:
            return None
        home = wb.sheet_by_id(dn.sheet) if dn.sheet else \
            (wb.sheet_by_id(dn.home) if dn.home is not None else None) or \
            (wb.sheets[0] if wb.sheets else None)
        if home is None:
            return None
        got = ev(tree, Ctx(wb, home, 0, 0))
        sheet = got.sheet if isinstance(got, RefValue) else home
        return sheet, got

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

    def equation_names(self, at_key=None) -> dict:
        """The names the equations can read from the tables, for their
        autocomplete: defined names, and Table.Column for each heading —
        only those defined before *at_key* (an equation there), as SMath
        lists only the names defined above."""
        out = {}
        wb = self.workbook
        for (lower, scope), dn in wb.names.items():
            written = self.written_as(dn)
            if written and (at_key is None or self.defined_at(written, at_key) is not None):
                out[written] = f"named cells: ={dn.refers_to}"
        for sheet in self.workbook.sheets:
            if sheet.kind != "table":
                continue
            if at_key is not None and (self._before(sheet, at_key) is None or
                                       not self._lookup_readable(sheet, at_key)):
                continue
            for (row, col), cell in sheet.cells.items():
                if row == 0 and isinstance(cell.value, str) and _ident(cell.value):
                    out[f"{sheet.name}.{_ident(cell.value)}"] = f"column “{cell.value}” of {sheet.name}"
        return out

    def _seen(self, got, at_key=None):
        """The (sheet, value) an equation at *at_key* may read, or None."""
        if got is None:
            return None
        sheet, value = got
        if isinstance(value, RefValue):
            area = (value.top, value.left, value.bottom, value.right)
            ref_sheet = value.sheet
        else:
            used = sheet.used_area()
            area, ref_sheet = (used if used is not None else (0, 0, 0, 0)), sheet
        return got if self.readable(ref_sheet, area, at_key) else None

    # -- where the tables define a name: their place in reading order ------------------------
    # A table's or sheet's names (named cells, Table.D12, Table.Column, the
    # table as a lookup) are defined where it is in the document — its
    # top-left corner — and take their turn with the equations' definitions
    # there (calc/engine/evaluator.py IndexedContext.entry): an equation
    # reads the latest definition before it, whichever kind it is. A table
    # after it is not read at all: the name is not defined there yet, as
    # in SMath (the user's answer, 2026-10-17).
    def _before(self, sheet: Sheet, at_key) -> Optional[tuple]:
        """The sheet's reading key when it is before *at_key* (anywhere,
        when *at_key* is None: asked from nowhere in particular), else None."""
        key = self._key(sheet)
        return key if at_key is None or key < tuple(at_key) else None

    def defined_at(self, name: str, at_key) -> Optional[tuple]:
        """Where the tables define *name*, when that is before *at_key* and
        can be read there; else None."""
        got = self._named(name, at_key)
        if got is None:
            return None
        at = self._before(got[0], at_key)
        if at is None or self._seen(got, at_key) is None:
            return None
        return at

    def _lookup_sheet(self, name: str, nargs: int) -> Optional[Sheet]:
        if not 1 <= nargs <= 3 or not _ident_ok(name):
            return None
        return self.workbook.sheet(name)

    def _lookup_readable(self, sheet: Sheet, at_key) -> bool:
        used = sheet.used_area()
        return self.readable(sheet, used if used is not None else (0, 0, 0, 0), at_key)

    def function_at(self, name: str, nargs: int, at_key) -> Optional[tuple]:
        """Where the table that *name(…)* looks up is, when it is before
        *at_key* and can be read there; else None."""
        sheet = self._lookup_sheet(name, nargs)
        if sheet is None:
            return None
        at = self._before(sheet, at_key)
        return at if at is not None and self._lookup_readable(sheet, at_key) else None

    def has(self, name: str, at_key=None) -> bool:
        """Whether a table before *at_key* defines *name* — known from an
        earlier section too: its value then says why it can't be read."""
        at_key = self.reading_at if at_key is None else at_key
        got = self._named(name, at_key)
        return got is not None and self._before(got[0], at_key) is not None

    def value(self, name: str, at_key=None):
        """The value of a table's *name* for the equation at *at_key*: None
        when no table before it defines the name (it is "not defined" there)."""
        at_key = self.reading_at if at_key is None else at_key
        got = self._named(name, at_key)
        if got is None or self._before(got[0], at_key) is None:
            return None
        if self._seen(got, at_key) is None:
            from calcforge.calc.engine.errors import SMathError

            raise SMathError(f"{name} is in an earlier calculation section and not global.")
        sheet, value = got
        self._asked[name] = sheet.id
        if isinstance(value, RefValue):
            value = value.value_at(0, 0) if value.single else value.to_array()
        elif not isinstance(value, Array):
            value = result(value)              # a LAMBDA name: #CALC!
        if isinstance(value, ErrorValue):
            from calcforge.calc.engine.errors import SMathError

            raise SMathError(f"{name} is {value.code} in its table.")
        try:
            return to_engine(value)
        except SheetError as e:
            from calcforge.calc.engine.errors import SMathError

            raise SMathError(f"{name} is {e.error.code} in its table.")

    def function(self, name: str, nargs: int, at_key=None):
        """A table used as a lookup: name(x), name(x, "heading"), name(x, y)
        — by an equation after the table only."""
        at_key = self.reading_at if at_key is None else at_key
        sheet = self._lookup_sheet(name, nargs)
        if sheet is None or self._before(sheet, at_key) is None or \
                not self._lookup_readable(sheet, at_key):
            return None

        def look(args):
            self._asked[name] = sheet.id
            return lookup(sheet, args)
        return look

    def written_as(self, dn) -> str:
        """How an equation writes a defined name: bare (a document name, or
        a name of a workbook that isn't self-contained), Book.Name (a
        self-contained workbook's), Sheet.Name (a sheet's own); "" for a
        sheet's own name on a sheet or table made here (Excel's scope only)."""
        wb = self.workbook
        if dn.sheet is not None:
            home = wb.sheet_by_id(dn.sheet)
            return f"{sheet_ident(home.name)}.{dn.name}" if home is not None and home.book else ""
        book = wb.books.get(dn.book) if dn.book else None
        if book is not None and book.self_contained:
            return f"{book.name}.{dn.name}"
        return dn.name

    def names(self) -> set:
        out = {self.written_as(dn) for dn in self.workbook.names.values()} - {""}
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

    _starts_seen = None

    def _after_calculation(self) -> None:
        """The equations calculated: tables reading their variables follow."""
        starts = tuple(self._calc().section_starts())
        if self._starts_seen is not None and starts != self._starts_seen and not self._syncing:
            self._starts_seen = starts
            self._soon("sections", self.sections_changed)
        self._starts_seen = starts
        if self.workbook.unit_waiting and not self._syncing:
            self._soon("units", self.workbook.reread_units)
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


def sheet_ident(name: str) -> str:
    """How an equation writes a sheet's name: as it is when it can, else with
    each run of spaces and other characters an identifier can't hold as one
    _ (Seismic Actions: Seismic_Actions; Loads (2): Loads_2)."""
    text = re.sub(r"[^\w]+", "_", name.strip()).strip("_")
    if not text:
        return "Sheet"
    return "_" + text if text[0].isdigit() else text


def sheet_named(wb, written: str):
    """The sheet or table an equation names: by its name, else by
    sheet_ident (any case)."""
    sheet = wb.sheet(written)
    if sheet is not None:
        return sheet
    lower = written.lower()
    return next((s for s in wb.sheets if sheet_ident(s.name).lower() == lower), None)


def book_named(wb, written: str):
    """The imported workbook an equation names by Book.name (any case)."""
    lower = written.lower()
    return next((b for b in wb.books.values() if b.name.lower() == lower), None)


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
