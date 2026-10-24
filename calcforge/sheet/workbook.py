"""The cells of every sheet and table in a document, and keeping them calculated.

One :class:`Workbook` holds all of a document's spreadsheet sections and
tables (each a :class:`Sheet`), so a formula can read any of them by name
('Sheet 2'!B4). Within the workbook cells are calculated in the order they
depend on each other, as Excel does; a loop is a circular reference: its
cells show 0 and :attr:`Workbook.circular` lists them, as Excel's status bar
does.

A bare name in a formula is only ever an Excel name (find_excel_name): the
sheet's own, its workbook's, a spreadsheet's own. A CalcForge variable — an
equation's, or a cell named in its Variable box — is read as CALC(name)
(the user, 2026-10-24: "there should now never be a clash"):
:attr:`Workbook.calc_variable` is asked for it (the document answers with
the one in force where the sheet is, in reading order).

Every change goes through a transaction, so it can be undone as one step.
"""
from __future__ import annotations

import bisect
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from typing import Callable, Iterable, Optional

from . import formula as F
from .inputs import read_value
from .refs import MAX_COLS, MAX_ROWS, CellRef, RangeRef, is_cell_name, parse_range
from .style import Style, StyleTable
from .values import BLANK, NAME, SPILL, Array, ErrorValue


# -- cells ---------------------------------------------------------------------------
class Cell:
    """What is in one cell: what was typed, its style, and its value."""

    __slots__ = ("input", "style", "value", "parsed", "problem", "comment", "spill_from")

    def __init__(self, input: str = "", style: int = 0):
        self.input = input              # exactly what was typed ("=A1*2", "5 kN", "")
        self.style = style              # index into the workbook's style table
        self.value = BLANK
        self.parsed: Optional[F.Parsed] = None
        self.problem: Optional[str] = None   # why a formula can't be read
        self.comment: Optional[str] = None
        self.spill_from = None

    @property
    def is_formula(self) -> bool:
        return self.input.startswith("=") and len(self.input) > 1

    @property
    def formula(self) -> Optional[str]:
        return self.input[1:] if self.is_formula else None

    def state(self) -> tuple:
        return (self.input, self.style, self.comment)

    def empty(self) -> bool:
        return not self.input and not self.style and not self.comment


@dataclass
class DefinedName:
    """A name for a cell, a block or a constant: W_total = Loads!$D$12."""

    name: str
    refers_to: str                       # formula text without "=", absolute refs
    sheet: Optional[int] = None          # sheet id when the name is local to one sheet
    comment: str = ""
    home: Optional[int] = None           # the sheet it is saved with, when it names no cells
    book: Optional[str] = None           # the imported workbook it belongs to (Book.id)
    # A CalcForge variable (named with the cell's Variable box): the
    # equations read it bare, and its cells carry a name tag. Any other name
    # is the spreadsheet's own (Define Name, the Name Box, the Name Manager,
    # Create from Selection, an Excel file's): the equations and other
    # sheets read it only as Sheet.Name (the user, 2026-10-21).
    variable: bool = False

    @property
    def key(self) -> tuple:
        """Its key in Workbook.names: (lower name, scope) — the sheet id of a
        sheet-local name, the Book.id of an imported workbook's name, None for
        a document name."""
        return (self.name.lower(), self.sheet if self.sheet is not None else self.book)


@dataclass
class Book:
    """An imported Excel workbook: its sheets share its names (Excel's
    workbook scope), and they are its own: its cells read them bare, and
    nothing outside does (the user, 2026-10-24: "un self contained workbook
    variable names (like spreadsheet names) should not be accessible from
    outside unless I dial in like sheet1.variable ... selfcontained shows
    nothing and cant dial in"). Not self-contained, outside reads them only
    by dialling in: an equation as ``Sheet.Name`` or ``Book.Name``, a cell
    as ``=Sheet!Name``. Self-contained (the default), not even that."""

    id: str
    name: str                            # how equations qualify its names (an identifier)
    file: str = ""                       # the file it came from, as a reminder
    self_contained: bool = True
    #: its sheets renamed coming in, as Excel named them -> as named here
    #: ("Loads" -> "Loads (2)"): text its formulas build still means them
    renamed: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        out = {"id": self.id, "name": self.name, "file": self.file,
               "self_contained": self.self_contained}
        if self.renamed:
            out["renamed"] = dict(self.renamed)
        return out


class Sheet:
    """One spreadsheet section or table."""

    def __init__(self, workbook: "Workbook", sheet_id: int, name: str, kind: str = "sheet"):
        self.workbook = workbook
        self.id = sheet_id
        self.name = name
        self.kind = kind                 # "sheet" (pages of grid) or "table" (on a page)
        self.book: Optional[str] = None  # the imported workbook it is part of (Book.id)
        self.cells: dict[tuple, Cell] = {}
        self._rows_in_col: dict[int, list] = {}
        # where it sits in the document's reading order (set by the document)
        self.position: tuple = ()
        # how it is laid out, in points (Excel's 64 x 20 px at 96 px to the inch)
        self.default_width = DEFAULT_WIDTH
        self.default_height = DEFAULT_HEIGHT
        self.widths: dict[int, float] = {}
        self.heights: dict[int, float] = {}
        self.hidden_rows: set = set()
        self.hidden_cols: set = set()
        self.merges: list[tuple] = []        # (top, left, bottom, right)
        # a table's extent (rows, columns); a sheet section grows without one
        self.size: Optional[tuple] = None
        self.show_gridlines = True
        self.show_headings = False           # print row and column headings
        self.cond_rules: list = []           # conditional formatting (condfmt.py)
        self.validations: list = []          # data validation (validation.py)
        self.filter: Optional[dict] = None   # AutoFilter: {"range": [t,l,b,r], "criteria": {col: {...}}}
        self.filtered_rows: set = set()      # rows the filter hides
        self.page: dict = {}                 # a sheet section's page options (pagination.py)
        # dynamic arrays: a formula whose result is a block spills it into the
        # cells below and to the right (Excel 365)
        self.spills: dict = {}               # anchor (row, col) -> (rows, cols) spilled
        self.spill_values: dict = {}         # anchor -> the whole Array
        self.wanted: dict = {}               # anchor -> (rows, cols) it would spill, spilled or not
        self.on_shift: list = []             # told (axis, at, delta) when rows/columns go in or out

    def __repr__(self) -> str:
        return f"Sheet({self.name!r})"

    # -- sparse storage --
    def cell(self, row: int, col: int) -> Optional[Cell]:
        return self.cells.get((row, col))

    #: bumped whenever a cell is added or taken away (evaluate.py's column
    #: summaries are only good for the cells there when they were made)
    cells_serial = 0

    def _put(self, row: int, col: int, cell: Cell) -> None:
        if (row, col) not in self.cells:
            rows = self._rows_in_col.setdefault(col, [])
            bisect.insort(rows, row)
            self.cells_serial += 1
        self.cells[(row, col)] = cell

    def _drop(self, row: int, col: int) -> None:
        if self.cells.pop((row, col), None) is not None:
            self.cells_serial += 1
            rows = self._rows_in_col.get(col)
            if rows:
                i = bisect.bisect_left(rows, row)
                if i < len(rows) and rows[i] == row:
                    rows.pop(i)
                if not rows:
                    del self._rows_in_col[col]

    def positions_in(self, top: int, left: int, bottom: int, right: int):
        """(row, col) of every cell that holds something in the block, row
        by row within each column (cheap for whole columns and rows)."""
        cols = self._rows_in_col
        if right - left + 1 > len(cols):
            wanted = sorted(c for c in cols if left <= c <= right)
        else:
            wanted = [c for c in range(left, right + 1) if c in cols]
        for col in wanted:
            rows = cols[col]
            i = bisect.bisect_left(rows, top)
            j = bisect.bisect_right(rows, bottom)
            for row in rows[i:j]:
                yield row, col

    def data_area(self) -> Optional[tuple]:
        """(top, left, bottom, right) of the cells that hold something typed
        (not those that only have a look, like a table's empty bordered
        cells); None when there are none."""
        keys = [k for k, c in self.cells.items() if c.input]
        if not keys:
            return None
        rows = [r for r, _ in keys]
        cols = [c for _, c in keys]
        return min(rows), min(cols), max(rows), max(cols)

    def used_area(self) -> Optional[tuple]:
        """(top, left, bottom, right) of everything in the sheet, or None."""
        if not self.cells:
            return None
        rows = [r for r, _ in self.cells]
        cols = [c for _, c in self.cells]
        return min(rows), min(cols), max(rows), max(cols)

    # -- reading --
    def value(self, row: int, col: int):
        return self.workbook.value(self, row, col)

    def input(self, row: int, col: int) -> str:
        cell = self.cells.get((row, col))
        return cell.input if cell else ""

    # -- layout --
    def height(self, row: int) -> float:
        if row in self.hidden_rows or row in self.filtered_rows:
            return 0.0
        return self.heights.get(row, self.default_height)

    def width(self, col: int) -> float:
        if col in self.hidden_cols:
            return 0.0
        return self.widths.get(col, self.default_width)

    def row_at(self, y: float) -> int:
        return _index_at(y, self.height, self.size[0] if self.size else None)

    def merge_at(self, row: int, col: int) -> Optional[tuple]:
        for m in self.merges:
            if m[0] <= row <= m[2] and m[1] <= col <= m[3]:
                return m
        return None

    def __getitem__(self, a1: str):
        ref = parse_range(a1)
        if isinstance(ref, CellRef):
            return self.value(ref.row, ref.col)
        raise KeyError(a1)


DEFAULT_WIDTH = 48.0      # points: 64 px
DEFAULT_HEIGHT = 15.0     # points: 20 px


def _index_at(pos: float, size, count: Optional[int]) -> int:
    i, edge = 0, 0.0
    limit = count if count is not None else MAX_ROWS
    while i < limit - 1:
        edge += size(i)
        if pos < edge:
            return i
        i += 1
    return i


# -- dependency bookkeeping --------------------------------------------------------------
_BUCKET = 32  # columns per bucket of block references


class _Dependents:
    """Who reads what: for a changed cell, the formulas to recalculate."""

    def __init__(self):
        self.cell: dict[tuple, set] = {}         # (sheet, row, col) -> {reader key}
        self.blocks: dict[tuple, list] = {}      # (sheet, bucket) -> [(top, left, bottom, right, reader)]
        self.names: dict[str, set] = {}          # lower name -> {reader key}
        self.read: dict[tuple, tuple] = {}       # reader key -> (cells, blocks, names) it registered

    def add(self, reader, cells, blocks, names) -> None:
        self.remove(reader)
        for key in cells:
            self.cell.setdefault(key, set()).add(reader)
        for sheet, top, left, bottom, right in blocks:
            for b in range(left // _BUCKET, right // _BUCKET + 1):
                self.blocks.setdefault((sheet, b), []).append((top, left, bottom, right, reader))
        for name in names:
            self.names.setdefault(name, set()).add(reader)
        self.read[reader] = (tuple(cells), tuple(blocks), tuple(names))

    def remove(self, reader) -> None:
        old = self.read.pop(reader, None)
        if old is None:
            return
        cells, blocks, names = old
        for key in cells:
            s = self.cell.get(key)
            if s:
                s.discard(reader)
                if not s:
                    del self.cell[key]
        for sheet, top, left, bottom, right in blocks:
            for b in range(left // _BUCKET, right // _BUCKET + 1):
                lst = self.blocks.get((sheet, b))
                if lst:
                    try:
                        lst.remove((top, left, bottom, right, reader))
                    except ValueError:
                        pass
                    if not lst:
                        del self.blocks[(sheet, b)]
        for name in names:
            s = self.names.get(name)
            if s:
                s.discard(reader)
                if not s:
                    del self.names[name]

    def hit(self, reached, skip: set) -> list:
        """Readers (not in skip) of blocks that hold any of the reached
        cells; each block is looked at once, however many cells changed."""
        by_bucket: dict = {}
        for sheet, row, col in reached:
            by_bucket.setdefault((sheet, col // _BUCKET), {}).setdefault(col, []).append(row)
        out = []
        for (sheet, b), cols in by_bucket.items():
            entries = self.blocks.get((sheet, b))
            if not entries:
                continue
            for rows in cols.values():
                rows.sort()
            for top, left, bottom, right, reader in entries:
                if reader in skip:
                    continue
                for col, rows in cols.items():
                    if left <= col <= right:
                        i = bisect.bisect_left(rows, top)
                        if i < len(rows) and rows[i] <= bottom:
                            skip.add(reader)
                            out.append(reader)
                            break
        return out

    def of(self, sheet: int, row: int, col: int):
        out = set(self.cell.get((sheet, row, col), ()))
        for top, left, bottom, right, reader in self.blocks.get((sheet, col // _BUCKET), ()):
            if top <= row <= bottom and left <= col <= right:
                out.add(reader)
        return out


# -- the workbook ------------------------------------------------------------------------
class _Transaction:
    def __init__(self, label: str):
        self.label = label
        self.steps: list = []            # (undo, redo) callables



def _kept(rewrite, text: str, *args) -> str:
    """*text* passed through one of formula.py's rewrites, or left as it is
    when it can't be read: one formula Excel wrote that CalcForge can't parse
    must never stop a move, an insert or a rename of every other (the user,
    2026-10-24: moving cells crashed on a workbook's "Tables!#REF!" names)."""
    try:
        return rewrite(text, *args)
    except F.FormulaError:
        return text

class Workbook:
    def __init__(self):
        self.sheets: list[Sheet] = []
        self._next_id = 1
        self.styles = StyleTable()
        self.names: dict[tuple, DefinedName] = {}    # DefinedName.key -> the name
        self.books: dict[str, Book] = {}              # imported workbooks by Book.id
        self.day_first = True
        # asked for a document variable: outside(sheet, name) -> value; raises KeyError
        self.outside: Optional[Callable] = None
        # CALC(name) in a cell: (sheet, name) -> a DefinedName (a cell named
        # in its Variable box) or a value (an equation's); KeyError(why)
        self.calc_variable: Optional[Callable] = None
        # whether one sheet may read cells of another (from, to, (t, l, b, r)):
        # the document's calculation sections (sheet/docbook.py); None: always
        self.reach: Optional[Callable] = None
        # cells typed with a custom unit not (yet) defined: (sheet id, row, col)
        self.unit_waiting: set = set()
        self.circular: list[tuple] = []              # (sheet, row, col) in a loop
        self.listeners: list[Callable[[set], None]] = []   # told the keys whose values changed
        self._deps = _Dependents()
        self._dirty: set = set()
        # of the dirty formulas, those worked out whatever their inputs did
        # (typed, volatile, a name or a document variable changed...); the
        # others only once something they read changed value (_needed)
        self._roots: set = set()
        self._needed: Optional[set] = None
        self._pass_changed: set = set()
        self._pass_cache: dict = {}
        self._reach_memo = None             # (cells typed, kept order, dirty, roots, order)
        self._held_order = None
        self._changed_rows: dict = {}       # (sheet id, col) -> sorted rows changed this pass
        self._changed_cols: dict = {}       # sheet id -> sorted columns changed this pass
        self._touched: list = []                     # cells changed since the last calculation
        self._volatile: set = set()
        self._precedents: dict[tuple, tuple] = {}    # key -> (cells, blocks) as read statically
        # every formula's place in an order where each comes after what it
        # reads, kept until a formula, sheet or name changes (None: to make):
        # an edit then sorts its dirty formulas by it instead of walking them
        self._rank: Optional[dict] = None
        self._rank_loops: set = set()
        self._evaluating: set = set()
        self._done: set = set()
        self._in_pass = False
        # during a pass: each column's values already worked out, kept so a
        # column of running totals reads its column once rather than once a
        # row (findings 5.2; evaluate.RefValue.float_values)
        self._columns: dict = {}
        self._changed: set = set()
        self._outside_reads: dict[tuple, set] = {}
        self._spill_moved: list = []                 # spilled values that changed this pass
        # ranges kept outside the cells (a chart's series): they follow renames
        # and moved rows and columns like formulas (formula_texts / set_formula_texts)
        self.outside_formulas: list = []
        # told how references change with what is done to the cells, so that
        # what reads them from outside the cells — the document's equations
        # (sheet/docbook.py) — follows as the formulas here do, Excel's way:
        #   ("sheet", sheet, old name, new name)        a sheet or table renamed
        #   ("cells", change)                           cells moved, inserted or
        #       deleted: change(CellRef, sheet) is the cell's new reference,
        #       the same one when it stays, None when it was deleted (#REF!)
        #   ("name", old DefinedName, new DefinedName)  a defined name renamed
        #   ("heading", sheet, old text, new text)      a column's heading retyped
        self.on_references: Optional[Callable[[tuple], None]] = None
        # document names loaded from a record made before names had two
        # kinds (store.load_sheet): keys, until DocumentBook settles them
        self.unsettled_names: set = set()
        # sheets loaded from a record of before CALC(name) (store.CALC_NAMES)
        self.unmigrated_formulas: set = set()
        # formulas naming a sheet or table that isn't there (yet): learnt again
        # when one comes, so they follow it from then on
        self._unresolved: set = set()
        self.version = 0                             # bumped whenever a value changes
        self._undo: list[_Transaction] = []
        self._redo: list[_Transaction] = []
        self._open: Optional[_Transaction] = None
        self._depth = 0
        self.auto = True

    # -- sheets --------------------------------------------------------------------
    def add_sheet(self, name: Optional[str] = None, kind: str = "sheet") -> Sheet:
        name = name or self.free_name("Table" if kind == "table" else "Sheet")
        if self.sheet(name) is not None:
            raise ValueError(f"A sheet or table is already called {name}.")
        problem = name_problem(name)
        if problem:
            raise ValueError(problem)
        sheet = Sheet(self, self._next_id, name, kind)
        self._next_id += 1
        self.sheets.append(sheet)

        def undo(s=sheet):
            self.sheets.remove(s)
            self._names_changed()

        def redo(s=sheet):
            self.sheets.append(s)
            self._names_changed()

        self._record(undo, redo)
        self._names_changed()
        return sheet

    def free_name(self, stem: str) -> str:
        taken = {s.name.lower() for s in self.sheets}
        n = 1
        while f"{stem}{n}".lower() in taken:
            n += 1
        return f"{stem}{n}"

    def sheet(self, name: Optional[str]) -> Optional[Sheet]:
        if name is None:
            return None
        lower = name.lower()
        # the last found by this name, while it is still here and so called
        # (formulas name other sheets thousands of times a calculation)
        cache = self.__dict__.setdefault("_sheet_found", {})
        s = cache.get(lower)
        if s is not None and s.name.lower() == lower and any(x is s for x in self.sheets):
            return s
        for s in self.sheets:
            if s.name.lower() == lower:
                cache[lower] = s
                return s
        cache.pop(lower, None)
        return None

    def sheet_by_id(self, sheet_id: int) -> Optional[Sheet]:
        for s in self.sheets:
            if s.id == sheet_id:
                return s
        return None

    def remove_sheet(self, sheet: Sheet) -> None:
        """Formulas that read it show #REF!, as in Excel."""
        index = self.sheets.index(sheet)
        saved = {pos: c.state() for pos, c in sheet.cells.items()}
        with self.transaction("Delete sheet"):
            for (row, col) in list(sheet.cells):
                self._set_state(sheet, row, col, ("", 0, None))
            self.sheets.remove(sheet)

            def undo(s=sheet, i=index):
                self.sheets.insert(i, s)
                self._names_changed()

            def redo(s=sheet):
                self.sheets.remove(s)
                self._names_changed()

            self._record(undo, redo)
            self._names_changed()
        del saved

    def rename_sheet(self, sheet: Sheet, new: str) -> None:
        """Every formula and name that reads the sheet follows the new name."""
        new = new.strip()
        if new.lower() != sheet.name.lower() and self.sheet(new) is not None:
            raise ValueError(f"A sheet or table is already called {new}.")
        problem = name_problem(new)
        if problem:
            raise ValueError(problem)
        old = sheet.name
        if old == new:
            return
        with self.transaction("Rename sheet"):
            for other in self.sheets:
                for (row, col), cell in list(other.cells.items()):
                    if cell.is_formula and old.lower() in cell.input.lower():
                        text = _kept(F.rename_sheet_in, cell.input[1:], old, new)
                        if "=" + text != cell.input:
                            self._set_state(other, row, col, ("=" + text, cell.style, cell.comment))
            for key, dn in list(self.names.items()):
                text = _kept(F.rename_sheet_in, dn.refers_to, old, new)
                if text != dn.refers_to:
                    self._set_name(key, replace(dn, refers_to=text))
            for holder in list(self.outside_formulas):
                texts = holder.formula_texts()
                moved = [_kept(F.rename_sheet_in, t, old, new) if t else t for t in texts]
                if moved != texts:
                    holder.set_formula_texts(moved)

            def apply(name, s=sheet):
                s.name = name
                # a sheet renamed coming in, renamed again: still the one
                # its workbook's text means by the name Excel knew it by
                book = self.books.get(s.book) if s.book else None
                for excel, now in list((book.renamed if book is not None else {}).items()):
                    if now.lower() in (old.lower(), new.lower()):
                        book.renamed[excel] = name
                self._names_changed()

            apply(new)
            self._record(lambda: apply(old), lambda: apply(new))
            self._tell_references(("sheet", sheet, old, new))

    def _tell_references(self, event: tuple) -> None:
        if self.on_references is not None:
            self.on_references(event)

    def rename_name(self, dn: "DefinedName", new: str) -> None:
        """A defined name called something else: every formula that uses it
        uses the new name, as Excel's Name Manager does (and the equations,
        on_references). *dn* keeps its scope, what it refers to and its
        comment; use define_name afterwards to change those."""
        new = new.strip()
        if new == dn.name:
            return
        problem = defined_name_problem(new)
        if problem:
            raise ValueError(problem)
        clash = self.names.get((new.lower(), dn.key[1]))
        if clash is not None and clash is not dn:
            raise ValueError(f"There is already a name {new} with that scope.")
        home = self.sheet_by_id(dn.sheet) if dn.sheet else None
        fresh = replace(dn, name=new)

        def uses(reader: Optional["Sheet"], written_sheet: Optional[str]) -> bool:
            """Whether a name written in a formula on *reader* (Sheet!Name:
            *written_sheet*) is *dn*."""
            if written_sheet is not None:
                from .refs import unquote_sheet

                there = self.sheet(unquote_sheet(written_sheet))
                return there is not None and self.find_name(dn.name, there) is dn
            return self.find_name(dn.name, reader) is dn

        with self.transaction("Rename name"):
            for other in self.sheets:
                for (row, col), cell in list(other.cells.items()):
                    if cell.is_formula and dn.name.lower() in cell.input.lower():
                        text = _kept(F.rename_name_in, cell.input[1:], dn.name, new,
                                                lambda written, o=other: uses(o, written))
                        if "=" + text != cell.input:
                            self._set_state(other, row, col, ("=" + text, cell.style, cell.comment))
            for key, other_dn in list(self.names.items()):
                if other_dn is dn or dn.name.lower() not in other_dn.refers_to.lower():
                    continue
                reader = self.sheet_by_id(other_dn.sheet) if other_dn.sheet else \
                    (self.sheet_by_id(other_dn.home) if other_dn.home is not None else home)
                text = _kept(F.rename_name_in, other_dn.refers_to, dn.name, new,
                                        lambda written, r=reader: uses(r, written))
                if text != other_dn.refers_to:
                    self._set_name(key, replace(other_dn, refers_to=text))
            self._set_name(dn.key, None)
            self._set_name(fresh.key, fresh)
            self._tell_references(("name", dn, fresh))

    #: told when sheets or defined names come, go or are renamed (the
    #: document's equations read them by name)
    on_names_changed: Optional[Callable[[], None]] = None

    def _names_changed(self) -> None:
        """Sheets or names came or went: anything reading them by name is
        looked at again."""
        self._rank = None                  # a sheet came, went or was renamed
        if self.on_names_changed is not None:
            self.on_names_changed()
        waiting, self._unresolved = self._unresolved, set()
        for key in waiting:
            sheet = self.sheet_by_id(key[0])
            cell = sheet.cells.get(key[1:]) if sheet is not None else None
            if cell is not None and cell.is_formula:
                self._learn(sheet, key[1], key[2], cell)
        for sheet in self.sheets:
            for (row, col), cell in sheet.cells.items():
                if cell.is_formula:
                    self._mark((sheet.id, row, col))
        self._recalc_if_auto()

    # -- defined names ----------------------------------------------------------------
    def define_name(self, name: str, refers_to: str, sheet: Optional[Sheet] = None,
                    comment: str = "", home: Optional[Sheet] = None,
                    variable: bool = False) -> None:
        """Name a cell, block or constant: define_name("W_total", "Loads!$D$12").
        *sheet* makes it local to that sheet; *home* is the sheet it is saved
        with when it names no cells (g = 9.81); *variable* makes it a
        CalcForge variable (DefinedName.variable)."""
        problem = defined_name_problem(name)
        if problem:
            raise ValueError(problem)
        if refers_to.startswith("="):
            refers_to = refers_to[1:]
        F.parse(refers_to)              # raises FormulaError if it can't be read
        where = home or sheet or self._first_sheet_read(refers_to)
        # a name made on an imported workbook's sheet is that workbook's (as
        # a new name in Excel is the workbook's); a CalcForge variable is the
        # document's, read bare by the equations whatever its cells are part
        # of (PGA named on a self-contained workbook was read by nothing)
        book = None if variable or sheet is not None or where is None else where.book
        dn = DefinedName(name, refers_to, sheet.id if sheet else None, comment,
                         where.id if where else None, book, variable)
        with self.transaction("Define name"):
            self._set_name(dn.key, dn)

    def _first_sheet_read(self, refers_to: str) -> Optional[Sheet]:
        try:
            tokens = F.tokenize(refers_to)
        except F.FormulaError:
            return None
        first = next((t for t in tokens if t.kind == "ref" and t.ref.sheet), None)
        return self.sheet(first.ref.sheet) if first is not None else None

    def remove_name(self, name: str, sheet: Optional[Sheet] = None,
                    book: Optional[str] = None) -> None:
        key = (name.lower(), sheet.id if sheet else book)
        if key in self.names:
            with self.transaction("Delete name"):
                self._set_name(key, None)

    def _set_name(self, key, dn: Optional[DefinedName]) -> None:
        old = self.names.get(key)
        if dn is None:
            self.names.pop(key, None)
        else:
            self.names[key] = dn
        self._record(lambda: self._put_name(key, old), lambda: self._put_name(key, dn))
        self._name_dirty(key[0])

    def _put_name(self, key, dn) -> None:
        if dn is None:
            self.names.pop(key, None)
        else:
            self.names[key] = dn
        self._name_dirty(key[0])

    def _name_dirty(self, lower: str) -> None:
        if self.on_names_changed is not None:
            self.on_names_changed()
        readers = list(self._deps.names.get(lower, ()))
        self._relearn(readers)
        self._dirty_many(readers, include_self=True)
        self._recalc_if_auto()

    def _relearn(self, keys) -> None:
        """What these formulas read, found again: a name they use came, went
        or now means other cells (a sheet that names them was put in after
        them, a workbook's names became its own)."""
        for key in keys:
            sheet = self.sheet_by_id(key[0])
            cell = sheet.cells.get(key[1:]) if sheet is not None else None
            if cell is not None and cell.is_formula:
                self._learn(sheet, key[1], key[2], cell)

    def find_name(self, name: str, sheet: Optional[Sheet]) -> Optional[DefinedName]:
        """The defined name a formula on *sheet* means by *name*, Excel's way:
        the sheet's own (local) name, then its workbook's, then a document
        name. Another workbook's names are its own (Book): a formula
        elsewhere reaches one only as ``Sheet!Name``, *sheet* being that
        workbook's sheet (``closed_to`` says when even that is refused)."""
        lower = name.lower()
        names = self.names
        if sheet is not None:
            local = names.get((lower, sheet.id))
            if local is not None:
                return local
            if sheet.book is not None:
                mine = names.get((lower, sheet.book))
                if mine is not None:
                    return mine
        return names.get((lower, None))

    def sheet_as_written(self, name: str, reader: Optional[Sheet]) -> Optional[Sheet]:
        """The sheet *name* means in text a formula on *reader* builds
        (INDIRECT("Loads!A1")): its own workbook's sheet by the name Excel
        knew it by, when bringing it in renamed it ("Loads" is "Loads (2)"
        here, another workbook having a Loads), else the sheet so named."""
        book = self.books.get(reader.book) if reader is not None and reader.book else None
        if book is not None and book.renamed:
            now = next((v for k, v in book.renamed.items() if k.lower() == name.lower()), None)
            found = self.sheet(now) if now else None
            if found is not None:
                return found
        return self.sheet(name)

    def find_excel_name(self, name: str, sheet: Optional[Sheet]) -> Optional[DefinedName]:
        """The Excel name a formula on *sheet* means by *name*: the sheet's
        own, then its workbook's, then (on a sheet of no imported workbook)
        a spreadsheet's own name kept with the document. Never a CalcForge
        variable: a cell reads one as CALC(name), so the two can't clash."""
        lower = name.lower()
        names = self.names
        if sheet is not None:
            local = names.get((lower, sheet.id))
            if local is not None:
                return local
            if sheet.book is not None:
                return names.get((lower, sheet.book))
        dn = names.get((lower, None))
        return dn if dn is not None and not dn.variable else None

    def closed_to(self, dn: DefinedName, reader: Optional[Sheet]) -> Optional[Book]:
        """The self-contained workbook *dn* is the own name of, when *reader*
        (a sheet outside it, or none) dials in to it: refused, as from an
        equation (the user, 2026-10-24: "selfcontained ... cant dial in").
        None when *reader* may read it."""
        if dn.book is not None:
            book_id = dn.book
        elif dn.sheet is not None:
            home = self.sheet_by_id(dn.sheet)
            book_id = home.book if home is not None else None
        else:
            return None
        book = self.books.get(book_id) if book_id else None
        if book is None or not book.self_contained:
            return None
        if reader is not None and reader.book == book_id:
            return None
        return book

    def book_names(self, book_id: str) -> list:
        """The names of an imported workbook (its own scope, not sheet-local)."""
        return [dn for (lower, scope), dn in self.names.items() if scope == book_id]

    def set_self_contained(self, book_id: str, on: bool) -> None:
        """Whether a workbook is closed even to dialling in (one undo step);
        every formula that reads a name is worked out again."""
        book = self.books.get(book_id)
        if book is None or book.self_contained == bool(on):
            return
        with self.transaction("Self-contained"):
            was = book.self_contained
            self.book_state(book_id, bool(on))
            self._record(lambda: self.book_state(book_id, was),
                         lambda: self.book_state(book_id, bool(on)))

    def book_state(self, book_id: str, self_contained: bool) -> None:
        """Puts a workbook's setting in place (no undo step of its own) and
        works out again every formula reading a name."""
        book = self.books.get(book_id)
        if book is None or book.self_contained == self_contained:
            return
        book.self_contained = self_contained
        self._names_changed()
        readers = set()
        for lower in {k[0] for k in self.names}:
            readers |= self._deps.names.get(lower, set())
        self._relearn(list(readers))
        self._dirty_many(list(readers), include_self=True)
        self._recalc_if_auto()

    # -- transactions and undo -------------------------------------------------------------
    @contextmanager
    def transaction(self, label: str = "Edit"):
        """Changes made inside are one undo step, calculated once at the end."""
        outer = self._open is None
        if outer:
            self._open = _Transaction(label)
        self._depth += 1
        try:
            yield self._open
        finally:
            self._depth -= 1
            if outer:
                t, self._open = self._open, None
                if t.steps and self.journal:
                    self._undo.append(t)
                    self._redo.clear()
                self.recalculate()

    #: Whether the workbook keeps its own undo steps. The app turns it off:
    #: its undo stack records whole pages, tables and all.
    journal = True

    def _record(self, undo: Callable, redo: Callable) -> None:
        if not self.journal:
            return
        if self._open is not None:
            self._open.steps.append((undo, redo))
        elif not self._replaying:
            t = _Transaction("Edit")
            t.steps.append((undo, redo))
            self._undo.append(t)
            self._redo.clear()

    _replaying = False

    def undo(self) -> None:
        if not self._undo:
            return
        t = self._undo.pop()
        self._replaying = True
        try:
            for undo, _redo in reversed(t.steps):
                undo()
        finally:
            self._replaying = False
        self._redo.append(t)
        self.recalculate()

    def redo(self) -> None:
        if not self._redo:
            return
        t = self._redo.pop()
        self._replaying = True
        try:
            for _undo, redo in t.steps:
                redo()
        finally:
            self._replaying = False
        self._undo.append(t)
        self.recalculate()

    # -- changing cells ------------------------------------------------------------------
    def set_input(self, sheet: Sheet, row: int, col: int, text: str) -> None:
        """Type into a cell, as Excel takes what is typed (a number, a date,
        5 kN, a formula...). A number format it implies (12% -> 0%) is set
        unless the cell already has one."""
        cell = sheet.cells.get((row, col))
        style = cell.style if cell else 0
        comment = cell.comment if cell else None
        if text and not text.startswith("=") and not text.startswith("'"):
            _value, fmt = read_value(text, self.day_first)
            if fmt and self.styles.get(style).number_format in (None, "General"):
                style = self.styles.add(replace(self.styles.get(style), number_format=fmt))
        if text.startswith("=") and len(text) > 1:
            text = "=" + _tidy_formula(text[1:])
            # Excel: a formula whose result is a date (=DATE(2026,10,15),
            # =TODAY()+7) gives a General cell a date format, as a typed
            # date does (QA, 2026-10-15)
            if self.styles.get(style).number_format in (None, "General"):
                fmt = formula_format(text[1:], row, col, self.day_first)
                if fmt:
                    style = self.styles.add(replace(self.styles.get(style), number_format=fmt))
        with self.transaction("Typing"):
            before = self._heading_text(sheet, row, col)
            self._set_state(sheet, row, col, (text, style, comment))
            if before:
                self._heading_retyped(sheet, col, before, self._heading_text(sheet, row, col))

    # -- a column's heading retyped: what reads the column by it follows ----------------
    def _heading_text(self, sheet: Sheet, row: int, col: int) -> str:
        """The heading of a column as structured references and the
        equations match it: the first row's text ("" for anything else)."""
        if row != 0:
            return ""
        cell = sheet.cells.get((0, col))
        text = cell.input if cell is not None else ""
        if not text or text.startswith("="):
            return ""
        if text.startswith("'"):
            return text[1:].strip()
        value, _fmt = read_value(text, self.day_first)
        return text.strip() if isinstance(value, str) else ""

    def _heading_retyped(self, sheet: Sheet, col: int, old: str, new: str) -> None:
        """Excel's table: Loads[Load] becomes Loads[Load_kN] when the heading
        is retyped — and an equation's Loads.Load, Loads.Load_kN. Not when
        the old heading heads another column too (which one was meant?), nor
        when the heading is cleared (that is a missing column, as in Excel
        a deleted one)."""
        if not new or new == old:
            return
        lower = old.lower()
        if any(c != col and self._heading_text(sheet, 0, c).lower() == lower
               for _r, c in sheet.positions_in(0, 0, 0, MAX_COLS - 1)):
            return
        for other in self.sheets:
            for (row, c), cell in list(other.cells.items()):
                if cell.is_formula and "[" in cell.input and lower in cell.input.lower():
                    text = _kept(F.rename_column_in, cell.input[1:], sheet.name, other is sheet, old, new)
                    if "=" + text != cell.input:
                        self._set_state(other, row, c, ("=" + text, cell.style, cell.comment))
        for key, dn in list(self.names.items()):
            if "[" in dn.refers_to and lower in dn.refers_to.lower():
                text = _kept(F.rename_column_in, dn.refers_to, sheet.name, False, old, new)
                if text != dn.refers_to:
                    self._set_name(key, replace(dn, refers_to=text))
        self._tell_references(("heading", sheet, old, new))

    def reread_units(self) -> None:
        """Cells typed with a custom unit read again (its equation calculated)."""
        changed = False
        for key in list(self.unit_waiting):
            sheet = self.sheet_by_id(key[0])
            cell = sheet.cells.get(key[1:]) if sheet is not None else None
            if cell is None or cell.is_formula:
                self.unit_waiting.discard(key)
                continue
            value, _fmt = read_value(cell.input, self.day_first)
            if not isinstance(value, str):
                self.unit_waiting.discard(key)
                cell.value = value
                self._changed.add(key)
                self._touched.append(key)
                changed = True
        if changed:
            self._recalc_if_auto()

    def set_style(self, sheet: Sheet, row: int, col: int, style: int) -> None:
        cell = sheet.cells.get((row, col))
        state = (cell.input, style, cell.comment) if cell else ("", style, None)
        with self.transaction("Format"):
            self._set_state(sheet, row, col, state)

    def set_comment(self, sheet: Sheet, row: int, col: int, comment: Optional[str]) -> None:
        cell = sheet.cells.get((row, col))
        state = (cell.input, cell.style, comment) if cell else ("", 0, comment)
        with self.transaction("Comment"):
            self._set_state(sheet, row, col, state)

    def clear(self, sheet: Sheet, top: int, left: int, bottom: int, right: int,
              what: str = "contents") -> None:
        """Delete key ("contents"), Clear Formats ("formats"), Clear All ("all")."""
        with self.transaction("Clear"):
            for row, col in list(sheet.positions_in(top, left, bottom, right)):
                cell = sheet.cells[(row, col)]
                if what == "contents":
                    state = ("", cell.style, cell.comment)
                elif what == "formats":
                    state = (cell.input, 0, cell.comment)
                elif what == "comments":
                    state = (cell.input, cell.style, None)
                else:
                    state = ("", 0, None)
                self._set_state(sheet, row, col, state)

    def _set_state(self, sheet: Sheet, row: int, col: int, state: tuple) -> None:
        cell = sheet.cells.get((row, col))
        old = cell.state() if cell else ("", 0, None)
        if old == state:
            return
        self._apply_state(sheet, row, col, state)
        self._record(lambda: self._apply_state(sheet, row, col, old),
                     lambda: self._apply_state(sheet, row, col, state))

    def _apply_state(self, sheet: Sheet, row: int, col: int, state: tuple) -> None:
        text, style, comment = state
        key = (sheet.id, row, col)
        cell = sheet.cells.get((row, col))
        same_input = cell is not None and cell.input == text
        if not same_input:
            self._spill_area_changed(sheet, row, col, cell, text)
        if not text and not style and not comment:
            sheet._drop(row, col)
            cell = None
        else:
            if cell is None:
                cell = Cell()
                sheet._put(row, col, cell)
            cell.input, cell.style, cell.comment = text, style, comment
        if same_input:
            return
        self._forget(key)
        if cell is not None and cell.is_formula:
            self._learn(sheet, row, col, cell)
            self._mark(key)
        elif cell is not None:
            value, _fmt = read_value(text, self.day_first)
            if cell.value != value or type(cell.value) is not type(value):
                cell.value = value
            cell.parsed = None
            cell.problem = None
            self._changed.add(key)
            # 5'kip_s: a custom unit not defined (yet) — read again once it is
            if isinstance(value, str) and "'" in text and not text.startswith("'"):
                self.unit_waiting.add(key)
            else:
                self.unit_waiting.discard(key)
        else:
            self._changed.add(key)
        self._touched.append(key)
        if key in self.circular:
            self.circular.remove(key)
        self._recalc_if_auto()

    def _spill_area_changed(self, sheet: Sheet, row: int, col: int, cell, text: str) -> None:
        """Typing into (or clearing) a cell a formula spills, or would spill,
        over: that formula is calculated again (it spills, or shows #SPILL!)."""
        if (row, col) in sheet.wanted and not text.startswith("="):
            self._unspill(sheet, (row, col))           # the spilling formula itself went
        if cell is not None and cell.spill_from is not None:
            anchor = cell.spill_from
            cell.spill_from = None                     # typed over: its own cell now
            cell.value = BLANK
            self._mark((sheet.id,) + anchor)
        for anchor, (rows, cols) in list(sheet.wanted.items()):
            if anchor != (row, col) and anchor[0] <= row < anchor[0] + rows \
                    and anchor[1] <= col < anchor[1] + cols:
                self._mark((sheet.id,) + anchor)

    def _recalc_if_auto(self) -> None:
        if self.auto and self._open is None and not self._replaying and not self._in_pass:
            self.recalculate()

    # -- what each formula reads ------------------------------------------------------------
    def _forget(self, key) -> None:
        if self._rank is not None and key in self._rank:
            self._rank = None              # a formula went: the kept order with it
        self._unresolved.discard(key)
        self._deps.remove(key)
        self._precedents.pop(key, None)
        self._volatile.discard(key)
        self._outside_reads.pop(key, None)

    def _learn(self, sheet: Sheet, row: int, col: int, cell: Cell) -> None:
        key = (sheet.id, row, col)
        self._rank = None
        try:
            cell.parsed = F.parse(cell.input[1:], row, col)
            cell.problem = None
        except F.FormulaError as e:
            cell.parsed = None
            cell.problem = str(e)
            return
        cells, blocks = [], []
        self._unresolved.discard(key)
        for sheet_name, top, left, bottom, right in F.references(cell.parsed.tree, row, col):
            target = sheet if sheet_name is None else self.sheet(sheet_name)
            if target is None:
                self._unresolved.add(key)
                continue
            if top == bottom and left == right:
                cells.append((target.id, top, left))
            else:
                blocks.append((target.id, top, left, bottom, right))
        FUNCTIONS = _functions()
        # a call to no Excel function may be a defined name holding a LAMBDA
        called = [f for f in cell.parsed.functions if f not in FUNCTIONS]
        names = [n.lower() for n in cell.parsed.names] + [f.lower() for f in called]
        for n in (*cell.parsed.names, *called):
            dn = self.find_name(n, sheet)
            if dn is not None:
                try:
                    p = F.parse(dn.refers_to)
                except F.FormulaError:
                    continue
                for sheet_name, top, left, bottom, right in F.references(p.tree, 0, 0):
                    target = self.sheet_by_id(dn.sheet) if sheet_name is None and dn.sheet else \
                        self.sheet(sheet_name) if sheet_name else sheet
                    if target is None:
                        continue
                    if top == bottom and left == right:
                        cells.append((target.id, top, left))
                    else:
                        blocks.append((target.id, top, left, bottom, right))
        # structured references: the table's headings, and the columns (and
        # rows) they name, as far down as the table may grow
        for node in _structured_nodes(cell.parsed.tree):
            target = sheet if node.table is None else self.sheet(node.table)
            names.append((node.table or sheet.name).lower())
            if target is None:
                self._unresolved.add(key)
            if target is None or target.size is None:
                continue
            width = target.size[1]
            blocks.append((target.id, 0, 0, 0, width + 31))
            left, right = 0, width + 31
            if node.first is not None:
                from .evaluate import heading_col
                a = heading_col(target, node.first)
                b = heading_col(target, node.last) if node.last is not None else a
                if a is not None and b is not None:
                    left, right = min(a, b), max(a, b)
            if "@" in node.specials:
                blocks.append((target.id, row, left, row, right))
            elif set(node.specials) <= {"#Headers"} and node.specials:
                pass
            else:
                blocks.append((target.id, 1, left, MAX_ROWS - 1, right))
        # sheets named in formulas: registered by name so a new or renamed
        # sheet brings them back
        self._deps.add(key, cells, blocks, names)
        self._precedents[key] = (tuple(cells), tuple(blocks))
        if cell.parsed.volatile:
            self._volatile.add(key)

    def _mark(self, key) -> None:
        """A formula to work out on the next pass, whatever its inputs did."""
        self._dirty.add(key)
        self._roots.add(key)

    def _note_changed(self, key) -> None:
        """A cell's value changed in this pass (or it was typed): what reads
        it is worked out when its turn comes (_inputs_changed)."""
        if key in self._pass_changed:
            return
        self._pass_changed.add(key)
        sid, row, col = key
        rows = self._changed_rows.get((sid, col))
        if rows is None:
            rows = self._changed_rows[(sid, col)] = []
            bisect.insort(self._changed_cols.setdefault(sid, []), col)
        bisect.insort(rows, row)

    def _inputs_changed(self, key) -> bool:
        """Whether anything a formula reads (cells, blocks, the cells of the
        names it uses) changed value in this pass."""
        cells, blocks = self._precedents.get(key, ((), ()))
        changed = self._pass_changed
        for k in cells:
            if k in changed:
                return True
        if blocks:
            by_col, cols_of = self._changed_rows, self._changed_cols
            for sid, top, left, bottom, right in blocks:
                cols = cols_of.get(sid)
                if not cols:
                    continue
                i = bisect.bisect_left(cols, left)
                j = bisect.bisect_right(cols, right)
                for col in cols[i:j]:
                    rows = by_col[(sid, col)]
                    a = bisect.bisect_left(rows, top)
                    if a < len(rows) and rows[a] <= bottom:
                        return True
        return False

    def _dirty_many(self, keys, include_self: bool) -> None:
        seen = set(keys)
        if include_self:
            self._dirty.update(keys)
            self._roots.update(keys)
        frontier = list(keys)
        cell_readers = self._deps.cell
        while frontier:
            reached = list(frontier)
            stack = list(frontier)
            while stack:
                k = stack.pop()
                for reader in cell_readers.get(k, ()):
                    if reader not in seen:
                        seen.add(reader)
                        self._dirty.add(reader)
                        stack.append(reader)
                        reached.append(reader)
            frontier = self._deps.hit(reached, seen)
            self._dirty.update(frontier)

    # -- outside names (the document's equations) ------------------------------------------------
    def outside_changed(self, names: Optional[Iterable[str]] = None) -> set:
        """Document variables changed: recalculate the cells that read them
        (all that read any, when names is None). Returns the keys that changed."""
        lowered = None if names is None else {n.lower() for n in names}
        hit = [key for key, read in self._outside_reads.items() if lowered is None or read & lowered]
        self._dirty_many(hit, include_self=True)
        if self._open is not None:
            return set()            # a transaction is open: calculated once, at its end
        return self.recalculate()

    def outside_names_read(self) -> set:
        out = set()
        for read in self._outside_reads.values():
            out |= read
        return out

    # -- calculating ---------------------------------------------------------------------
    def recalculate(self, everything: bool = False) -> set:
        """Bring every value up to date. Returns the keys whose value changed."""
        if self._in_pass:
            return set()
        edited = bool(self._touched) or bool(self._dirty)
        touched = ()
        memo = None
        if self._touched:
            touched, self._touched = self._touched, []
            # the same cells typed into again (one input, value after
            # value): what they reach, and its order, are as last time while
            # no formula has changed (the kept order still stands)
            if not self._dirty and not everything and self._rank is not None and \
                    not any(x.spills or x.wanted for x in self.sheets):
                memo = (frozenset(touched), self._rank)
                held = self._reach_memo
                if held is not None and held[0] == memo[0] and held[1] is memo[1]:
                    self._dirty.update(held[2])
                    self._roots.update(held[3])
                    self._held_order = held[4]
                    edited = False                     # (its volatile ones are in it)
                    touched_known = True
                else:
                    touched_known = False
            else:
                touched_known = False
            if not touched_known:
                self._dirty_many(touched, include_self=False)
        if everything:
            for sheet in self.sheets:
                for (row, col), cell in sheet.cells.items():
                    if cell.is_formula:
                        self._mark((sheet.id, row, col))
        if edited and self._volatile:
            self._dirty_many(list(self._volatile), include_self=True)
        if not self._dirty:
            self._roots.clear()
            changed, self._changed = self._changed, set()
            if changed:
                self._tell(changed)
            return changed
        self._in_pass = True
        self._columns = {}
        self._pass_cache = {}              # what stands still during a pass (DocumentBook._reach)
        # Only what can have changed is worked out: the roots, and a formula
        # once something it reads changed value — a dependent whose inputs
        # came out the same is left as it is (the user's seismic workbook:
        # its INDIRECTs, volatile, recalculated 4000 formulas for any edit)
        self._needed = None if everything else (self._roots & self._dirty)
        self._roots = set()
        self._pass_changed, self._changed_rows, self._changed_cols = set(), {}, {}
        for key in touched:
            self._note_changed(key)
        try:
            held_order, self._held_order = self._held_order, None
            if held_order is not None:
                order, loops = held_order, set()
            else:
                order, loops = self._order()
                if memo is not None and not loops and self._rank is memo[1]:
                    self._reach_memo = (memo[0], memo[1], frozenset(self._dirty),
                                        frozenset(self._needed or ()), order)
            kept = {k for k in self.circular if k not in self._dirty}
            self.circular = sorted(kept | loops)
            for key in loops:
                sheet = self.sheet_by_id(key[0])
                cell = sheet.cells.get(key[1:]) if sheet else None
                if cell is not None and cell.value != 0.0:
                    cell.value = 0.0
                    self._changed.add(key)
                self._done.add(key)
                self._dirty.discard(key)
            needed = self._needed
            for key in order:
                if key not in self._done:
                    if needed is not None and key not in needed and \
                            not self._inputs_changed(key):
                        self._done.add(key)        # nothing it reads changed
                    else:
                        self._compute(key)
                    self._dirty.discard(key)
            # spilled blocks that changed: what reads them, again (a few
            # rounds at most: a spill that feeds itself settles or stops)
            rounds = 0
            while self._spill_moved and rounds < 20:
                rounds += 1
                moved, self._spill_moved = self._spill_moved, []
                self._dirty.clear()
                self._dirty_many(moved, include_self=False)
                self._done -= self._dirty
                self._columns = {}         # values seen final may change again
                self._needed = None
                order, loops = self._order()
                for key in order:
                    if key not in self._done:
                        self._compute(key)
                        self._dirty.discard(key)
        finally:
            self._spill_moved = []
            self._dirty.clear()
            self._done.clear()
            self._columns = {}
            self._needed = None
            self._in_pass = False
        changed, self._changed = self._changed, set()
        if changed:
            self._tell(changed)
        return changed

    def _tell(self, changed: set) -> None:
        self.version += 1
        for listener in list(self.listeners):
            listener(changed)

    def _order(self):
        """The dirty formulas, each after those it reads; and the ones in loops.

        Sorted by the kept order of every formula (_rank) when it can be:
        the formulas haven't changed since it was made, none of the dirty
        ones is in a loop, and nothing spills (a spill moves what reads
        what as it is worked out). Otherwise worked out afresh (_walk_order)."""
        if any(s.spills or s.wanted for s in self.sheets):
            return self._walk_order()
        rank = self._rank
        dirty = self._dirty
        if rank is None:
            # made when a pass is most of the formulas anyway (costing about
            # what walking them does), not for small ones: loading sheet
            # after sheet would make it again and again
            if len(dirty) * 2 < len(self._precedents):
                return self._walk_order()
            rank = self._make_rank()
        if self._rank_loops and not self._rank_loops.isdisjoint(dirty):
            return self._walk_order()
        order = []
        for key in dirty:
            if key in rank:
                order.append(key)
                continue
            sheet = self.sheet_by_id(key[0])
            cell = sheet.cells.get(key[1:]) if sheet is not None else None
            if cell is not None and cell.is_formula:
                return self._walk_order()      # (not in the kept order: never)
        order.sort(key=rank.__getitem__)
        return order, set()

    def _make_rank(self) -> dict:
        everything = {(sheet.id, row, col) for sheet in self.sheets
                      for (row, col), cell in sheet.cells.items() if cell.is_formula}
        dirty, self._dirty = self._dirty, everything
        try:
            order, loops = self._walk_order()
        finally:
            self._dirty = dirty
        self._rank = {key: i for i, key in enumerate(order)}
        self._rank_loops = set(loops)
        return self._rank

    def _walk_order(self):
        """_order, worked out by walking the dirty formulas."""
        dirty = self._dirty
        state: dict = {}
        order: list = []
        loops: set = set()
        sheets = {s.id: s for s in self.sheets}

        def anchor_of(k):
            """A spilled cell is calculated by the formula it spilled from."""
            sheet = sheets.get(k[0])
            ghost = sheet.cells.get(k[1:]) if sheet is not None else None
            if ghost is not None and ghost.spill_from is not None:
                a = (k[0],) + ghost.spill_from
                if a in dirty:
                    return a
            return None

        # The dirty cells by sheet and column, rows in order, and the dirty
        # formulas that spill: a block read is looked up in these rather than
        # walked cell by cell. Walking them made a column of running totals
        # (=SUM($D$1:D2), =SUM($D$1:D3), ...) square in its length to order
        # -- seconds for one value typed above 3000 of them (2026-10-16).
        dirty_rows: dict = {}             # (sheet id, col) -> sorted rows
        dirty_cols: dict = {}             # sheet id -> sorted columns with dirty rows
        for sid, row, col in dirty:
            sheet = sheets.get(sid)
            if sheet is not None and (row, col) in sheet.cells:
                dirty_rows.setdefault((sid, col), []).append(row)
        for (sid, col), rows in dirty_rows.items():
            rows.sort()
            dirty_cols.setdefault(sid, []).append(col)
        for cols in dirty_cols.values():
            cols.sort()
        # A block read gives only its dirty cells not yet ordered: each
        # column's rows skip past the finished ones (a "next unfinished"
        # pointer per row, halved as it is followed). A column of running
        # totals otherwise offered every cell above each total again: 4.5
        # million steps to order 3000 of them (findings 5.1 and 5.5).
        ahead: dict = {k: list(range(len(rows) + 1)) for k, rows in dirty_rows.items()}
        place: dict = {(k[0], row, k[1]): i for k, rows in dirty_rows.items()
                       for i, row in enumerate(rows)}

        def unfinished(nxt, i):
            while nxt[i] != i:
                nxt[i] = nxt[nxt[i]]
                i = nxt[i]
            return i

        def finished(key):
            state[key] = 2
            i = place.get(key)
            if i is not None:
                ahead[(key[0], key[2])][i] = i + 1
        spilling: dict = {}               # sheet id -> [(anchor key, its spilled block)]
        for sid, sheet in sheets.items():
            for (row, col), (h, w) in sheet.spills.items():
                if (sid, row, col) in dirty:
                    spilling.setdefault(sid, []).append(
                        ((sid, row, col), (row, col, row + h - 1, col + w - 1)))

        def in_block(sid, top, left, bottom, right):
            cols = dirty_cols.get(sid)
            if cols:
                i = bisect.bisect_left(cols, left)
                j = bisect.bisect_right(cols, right)
                for col in cols[i:j]:
                    rows = dirty_rows[(sid, col)]
                    nxt = ahead[(sid, col)]
                    a = bisect.bisect_left(rows, top)
                    b = bisect.bisect_right(rows, bottom)
                    a = unfinished(nxt, a)
                    while a < b:
                        yield (sid, rows[a], col)
                        a = unfinished(nxt, a + 1)
            # a spilled cell in the block is calculated by the formula it
            # spilled from
            for anchor, (t, l, b, r) in spilling.get(sid, ()):
                if t <= bottom and b >= top and l <= right and r >= left and \
                        not (top <= t <= bottom and left <= l <= right):
                    sheet = sheets[sid]
                    if any(sheet.cells.get(p) is not None and sheet.cells[p].spill_from == anchor[1:]
                           for p in sheet.positions_in(max(t, top), max(l, left),
                                                       min(b, bottom), min(r, right))):
                        yield anchor

        any_spills = any(s.spills for s in sheets.values())

        def precedents(key):
            cells, blocks = self._precedents.get(key, ((), ()))
            for k in cells:
                if k in dirty:
                    yield k
                elif any_spills:
                    a = anchor_of(k)
                    if a is not None:
                        yield a
            for sid, top, left, bottom, right in blocks:
                if sid in sheets:
                    yield from in_block(sid, top, left, bottom, right)

        for start in list(dirty):
            if start in state:
                continue
            sheet = sheets.get(start[0])
            if sheet is None or (start[1], start[2]) not in sheet.cells:
                finished(start)
                continue
            state[start] = 1
            stack = [(start, precedents(start))]
            while stack:
                key, it = stack[-1]
                for p in it:
                    s = state.get(p)
                    if s is None:
                        state[p] = 1
                        stack.append((p, precedents(p)))
                        break
                    if s == 1:
                        # a loop: everything on the stack from p up to here
                        at = len(stack) - 1
                        while at >= 0 and stack[at][0] != p:
                            loops.add(stack[at][0])
                            at -= 1
                        loops.add(p)
                else:
                    stack.pop()
                    finished(key)
                    order.append(key)
        return order, loops

    def _compute(self, key) -> None:
        sheet = self.sheet_by_id(key[0])
        cell = sheet.cells.get((key[1], key[2])) if sheet else None
        done = self._done
        if cell is None or not cell.input.startswith("=") or len(cell.input) < 2:
            done.add(key)
            return
        evaluating = self._evaluating
        evaluating.add(key)
        try:
            parsed = cell.parsed
            if parsed is None and cell.problem is None:
                self._learn(sheet, key[1], key[2], cell)
                parsed = cell.parsed
            if parsed is None:
                value = NAME.because(cell.problem) if cell.problem else BLANK
                reads = None
            else:
                value, reads = _evaluate_cell()(self, sheet, key[1], key[2], parsed.tree, parsed)
        finally:
            evaluating.discard(key)
        done.add(key)
        self._dirty.discard(key)
        if reads:
            self._outside_reads[key] = reads
        elif key in self._outside_reads:
            del self._outside_reads[key]
        value = self._spill(sheet, key, value)
        old = cell.value
        if type(old) is float and type(value) is float:
            if old == value or (old != old and value != value):
                return
        elif _same(old, value):
            return
        cell.value = value
        self._changed.add(key)
        if self._needed is not None:
            self._note_changed(key)

    # -- dynamic arrays ---------------------------------------------------------------------------
    def _spill_blocked(self, sheet: Sheet, anchor: tuple, rows: int, cols: int) -> bool:
        """Excel's #SPILL!: something is in the way (a value, another spill,
        a merged cell), or the block runs off the sheet or out of its table."""
        r, c = anchor
        if r + rows > MAX_ROWS or c + cols > MAX_COLS:
            return True
        if sheet.size is not None and (r + rows > sheet.size[0] or c + cols > sheet.size[1]):
            return True
        for row, col in sheet.positions_in(r, c, r + rows - 1, c + cols - 1):
            if (row, col) == anchor:
                continue
            other = sheet.cells[(row, col)]
            if other.input or (other.spill_from is not None and other.spill_from != anchor):
                return True
        for m in sheet.merges:
            if m[0] <= r + rows - 1 and m[2] >= r and m[1] <= c + cols - 1 and m[3] >= c:
                return True
        return False

    def _spill(self, sheet: Sheet, key: tuple, value):
        """Put a block result into the cells it spills over; what the formula's
        own cell shows (its top-left value, or #SPILL!)."""
        anchor = (key[1], key[2])
        if type(value) is not Array and anchor not in sheet.spills and \
                anchor not in sheet.wanted and anchor not in sheet.spill_values:
            return value                   # (the usual: one value, nothing spilled before)
        old = sheet.spills.pop(anchor, None)
        old_values = sheet.spill_values.pop(anchor, None)
        new = None
        shown = value
        if isinstance(value, Array) and value.height * value.width > 1:
            size = (value.height, value.width)
            sheet.wanted[anchor] = size
            if self._spill_blocked(sheet, anchor, *size):
                shown = SPILL
            else:
                new = size
                shown = value.get(0, 0)
                sheet.spills[anchor] = new
                sheet.spill_values[anchor] = value
        else:
            sheet.wanted.pop(anchor, None)
        if old is None and new is None:
            return shown
        r, c = anchor
        moved = []
        old_cells = set(_block(anchor, old)) if old else set()
        new_cells = set(_block(anchor, new)) if new else set()
        sid = sheet.id
        for p in old_cells - new_cells:
            ghost = sheet.cells.get(p)
            if ghost is None or ghost.spill_from != anchor:
                continue
            ghost.spill_from = None
            if ghost.value is not BLANK:
                ghost.value = BLANK
                moved.append((sid,) + p)
            if ghost.empty():
                sheet._drop(*p)
        for p in new_cells:
            v = value.get(p[0] - r, p[1] - c)
            ghost = sheet.cells.get(p)
            if ghost is None:
                ghost = Cell()
                sheet._put(p[0], p[1], ghost)
            ghost.spill_from = anchor
            if not _same(ghost.value, v):
                ghost.value = v
                moved.append((sid,) + p)
        for k in moved:
            self._changed.add(k)
        if moved or old_values != sheet.spill_values.get(anchor) or old != new:
            # whatever reads the spilled cells, or the block as A1#, again
            self._spill_moved.extend(moved + [key])
        return shown

    def _unspill(self, sheet: Sheet, anchor: tuple) -> None:
        """A formula that spilled is gone or changed: its spilled cells empty."""
        if anchor in sheet.spills:
            self._spill(sheet, (sheet.id,) + anchor, BLANK)
        sheet.wanted.pop(anchor, None)

    def spill_block(self, sheet: Sheet, row: int, col: int) -> Optional[tuple]:
        """(top, left, bottom, right) of the spill a cell is part of, if any."""
        cell = sheet.cells.get((row, col))
        anchor = cell.spill_from if cell is not None and cell.spill_from else (row, col)
        size = sheet.spills.get(anchor)
        if size is None:
            return None
        return anchor[0], anchor[1], anchor[0] + size[0] - 1, anchor[1] + size[1] - 1

    def value(self, sheet: Sheet, row: int, col: int):
        """A cell's value, calculating it first if it is out of date (a
        reference found while calculating, e.g. through INDIRECT)."""
        cell = sheet.cells.get((row, col))
        if cell is None:
            return BLANK
        key = (sheet.id, row, col)
        if self._in_pass and key in self._dirty:
            if key in self._evaluating:
                if key not in self.circular:
                    self.circular.append(key)
                    self.circular.sort()
                return 0.0
            self._compute(key)
        return cell.value

    # -- moving things about -------------------------------------------------------------------
    def _rewrite_all(self, change, label_sheet: Sheet, done: frozenset = frozenset()) -> None:
        """Pass every reference in every formula and name through change(ref,
        effective sheet); *done*: cells (sheet id, row, col) already passed
        through it as they moved."""
        for other in self.sheets:
            for (row, col), cell in list(other.cells.items()):
                if not cell.is_formula or (other.id, row, col) in done:
                    continue
                text = _kept(F.rewrite, cell.input[1:], lambda ref, s, o=other: change(ref, self.sheet(s) if s else o))
                if "=" + text != cell.input:
                    self._set_state(other, row, col, ("=" + text, cell.style, cell.comment))
        for key, dn in list(self.names.items()):
            home = self.sheet_by_id(dn.sheet) if dn.sheet else None
            text = _kept(F.rewrite, dn.refers_to, lambda ref, s, h=home: change(ref, self.sheet(s) if s else h))
            if text != dn.refers_to:
                self._set_name(key, replace(dn, refers_to=text))
        for holder in list(self.outside_formulas):
            texts = holder.formula_texts()
            moved = []
            for t in texts:
                try:
                    moved.append(F.rewrite(t, lambda ref, s: change(ref, self.sheet(s) if s else None))
                                 if t else t)
                except F.FormulaError:
                    moved.append(t)
            if moved != texts:
                holder.set_formula_texts(moved)
        self._tell_references(("cells", change))

    def _clear_spills(self, sheet: Sheet) -> None:
        """Before cells move about: every spill on the sheet is taken back and
        its formula calculated again where it lands."""
        for anchor in list(sheet.spills):
            self._unspill(sheet, anchor)
        for anchor in list(sheet.wanted):
            sheet.wanted.pop(anchor, None)
            self._mark((sheet.id,) + anchor)

    def _move_cells(self, sheet: Sheet, mapping: Callable[[int, int], Optional[tuple]],
                    change=None) -> frozenset:
        """Move every cell of the sheet to mapping(row, col) (None: deleted).
        With *change* (the references' rewrite that goes with the move), a
        moved formula takes its rewritten text as it lands, so it is read
        once rather than once moved and again rewritten (findings 5.1).
        Returns the cells so rewritten, for _rewrite_all to pass over."""
        self._clear_spills(sheet)
        moves = []
        done = set()
        for (row, col), cell in list(sheet.cells.items()):
            to = mapping(row, col)
            if to != (row, col):
                state = cell.state()
                if change is not None and to is not None and cell.is_formula:
                    text = _kept(F.rewrite, state[0][1:], lambda ref, s: change(
                        ref, self.sheet(s) if s else sheet))
                    state = ("=" + text, state[1], state[2])
                    done.add((sheet.id,) + to)
                moves.append(((row, col), to, state))
        for (row, col), _to, _state in moves:
            self._set_state(sheet, row, col, ("", 0, None))
        for _frm, to, state in moves:
            if to is not None:
                self._set_state(sheet, to[0], to[1], state)
        return frozenset(done)

    def insert_rows(self, sheet: Sheet, at: int, count: int = 1) -> None:
        with self.transaction("Insert rows"):
            change = lambda ref, s: _shift_ref(ref, s is sheet, "row", at, count, 0)
            done = self._move_cells(sheet, lambda r, c: (r + count, c) if r >= at else (r, c), change)
            self._rewrite_all(change, sheet, done)
            self._shift_extras(sheet, "row", at, count)

    def delete_rows(self, sheet: Sheet, at: int, count: int = 1) -> None:
        with self.transaction("Delete rows"):
            last = at + count - 1
            change = lambda ref, s: _shift_ref(ref, s is sheet, "row", at, 0, count)
            done = self._move_cells(sheet, lambda r, c: None if at <= r <= last else
                                    ((r - count, c) if r > last else (r, c)), change)
            self._rewrite_all(change, sheet, done)
            self._shift_extras(sheet, "row", at, -count)

    def insert_cols(self, sheet: Sheet, at: int, count: int = 1) -> None:
        with self.transaction("Insert columns"):
            change = lambda ref, s: _shift_ref(ref, s is sheet, "col", at, count, 0)
            done = self._move_cells(sheet, lambda r, c: (r, c + count) if c >= at else (r, c), change)
            self._rewrite_all(change, sheet, done)
            self._shift_extras(sheet, "col", at, count)

    def delete_cols(self, sheet: Sheet, at: int, count: int = 1) -> None:
        with self.transaction("Delete columns"):
            last = at + count - 1
            change = lambda ref, s: _shift_ref(ref, s is sheet, "col", at, 0, count)
            done = self._move_cells(sheet, lambda r, c: None if at <= c <= last else
                                    ((r, c - count) if c > last else (r, c)), change)
            self._rewrite_all(change, sheet, done)
            self._shift_extras(sheet, "col", at, -count)

    # -- Excel's Insert / Delete cells, shifting the cells beside them --------------------
    def merges_in_the_way(self, sheet: Sheet, top: int, left: int, bottom: int, right: int,
                          axis: str) -> bool:
        """Whether shifting the cells of the block along *axis* ("row": up
        or down, "col": left or right) would cut a merged block, which Excel
        refuses ("We can't do that to a merged cell")."""
        lo, hi = (left, right) if axis == "row" else (top, bottom)
        start = top if axis == "row" else left
        for m in sheet.merges:
            m_lo, m_hi = (m[1], m[3]) if axis == "row" else (m[0], m[2])
            m_start, m_end = (m[0], m[2]) if axis == "row" else (m[1], m[3])
            if m_end < start or m_hi < lo or m_lo > hi:
                continue                   # wholly before the block or beside the band
            if m_lo < lo or m_hi > hi:
                return True                # straddles the band's side
            if m_start < start <= m_end:
                return True                # straddles the block's leading edge
        return False

    def shift_cells(self, sheet: Sheet, top: int, left: int, bottom: int, right: int,
                    axis: str, insert: bool) -> None:
        """Excel's Insert ▸ Shift cells down / right (*insert*) and Delete ▸
        Shift cells up / left, for the block (top, left)-(bottom, right).
        *axis* "row" moves the cells of the block's columns up or down; "col"
        moves those of its rows left or right. Formulas that read the moved
        cells follow them; one that read a deleted cell gives #REF!, as in
        Excel. A table grows rather than lose cells pushed past its end."""
        on_row = axis == "row"
        lo, hi = (left, right) if on_row else (top, bottom)
        at = top if on_row else left
        n = (bottom - top + 1) if on_row else (right - left + 1)
        last = at + n - 1

        def in_band(r, c):
            k = c if on_row else r
            return lo <= k <= hi

        def along(r, c):
            return r if on_row else c

        def put(r, c, k):
            return (k, c) if on_row else (r, k)

        def mapping(r, c):
            if not in_band(r, c):
                return (r, c)
            k = along(r, c)
            if insert:
                return put(r, c, k + n) if k >= at else (r, c)
            if at <= k <= last:
                return None
            return put(r, c, k - n) if k > last else (r, c)

        def change(ref, s):
            if s is not sheet:
                return ref
            if isinstance(ref, CellRef):
                if not in_band(ref.row, ref.col):
                    return ref
                return _shift_ref(ref, True, axis, at, n if insert else 0, 0 if insert else n)
            if ref.whole:
                return ref                 # whole rows and columns are not cut
            r_lo, r_hi = (ref.left, ref.right) if on_row else (ref.top, ref.bottom)
            if r_lo < lo or r_hi > hi:
                return ref                 # reaches beside the band: left as it is
            return _shift_ref(ref, True, axis, at, n if insert else 0, 0 if insert else n)

        label = ("Insert cells" if insert else "Delete cells")
        with self.transaction(label):
            before = _layout_state(sheet)
            if insert and sheet.size is not None:
                rows, cols = sheet.size
                reach = max((along(r, c) for (r, c) in sheet.cells
                             if in_band(r, c) and along(r, c) >= at and
                             not sheet.cells[(r, c)].empty()), default=-1)
                end = (rows if on_row else cols)
                if reach + n >= end:       # the table grows to keep them
                    grown = reach + n + 1
                    sheet.size = (grown, cols) if on_row else (rows, grown)
            done = self._move_cells(sheet, mapping, change)
            self._rewrite_all(change, sheet, done)
            merges = []
            for m in sheet.merges:
                if not in_band(m[0], m[1]) or not in_band(m[2], m[3]):
                    merges.append(m)
                    continue
                a, b = mapping(m[0], m[1]), mapping(m[2], m[3])
                if a is not None and b is not None:
                    merges.append((a[0], a[1], b[0], b[1]))
            sheet.merges = merges
            after = _layout_state(sheet)
            if after != before:
                self._record(lambda: _set_layout(sheet, before), lambda: _set_layout(sheet, after))
                self._tell({("layout", sheet.id)})

    def _shift_extras(self, sheet, axis, at, delta) -> None:
        """Sizes, hidden rows/columns, merges and a table's extent move with
        inserted and deleted rows and columns."""
        for listener in list(sheet.on_shift):
            listener(axis, at, delta)
        before = _layout_state(sheet)

        def moved(i):
            if delta > 0:
                return i + delta if i >= at else i
            gone = -delta
            if at <= i < at + gone:
                return None
            return i - gone if i >= at + gone else i

        sizes = sheet.heights if axis == "row" else sheet.widths
        hidden = sheet.hidden_rows if axis == "row" else sheet.hidden_cols
        new_sizes = {moved(i): v for i, v in sizes.items() if moved(i) is not None}
        new_hidden = {moved(i) for i in hidden if moved(i) is not None}
        sizes.clear()
        sizes.update(new_sizes)
        hidden.clear()
        hidden.update(new_hidden)
        merges = []
        for top, left, bottom, right in sheet.merges:
            lo, hi = (top, bottom) if axis == "row" else (left, right)
            if delta > 0:
                lo2 = lo + delta if lo >= at else lo
                hi2 = hi + delta if hi >= at else hi
            else:
                gone = -delta
                last = at + gone - 1
                if lo >= at and hi <= last:
                    continue
                lo2 = lo if lo < at else (at if lo <= last else lo - gone)
                hi2 = hi if hi < at else (at - 1 if hi <= last else hi - gone)
            m = (lo2, left, hi2, right) if axis == "row" else (top, lo2, bottom, hi2)
            if m[0] != m[2] or m[1] != m[3]:
                merges.append(m)
        sheet.merges = merges
        sheet.cond_rules = [r for r in (_shift_ranges(rule, axis, at, delta) for rule in sheet.cond_rules) if r]
        sheet.validations = [r for r in (_shift_ranges(v, axis, at, delta) for v in sheet.validations) if r]
        if sheet.filter is not None:
            moved = _shift_ranges({"ranges": [sheet.filter["range"]]}, axis, at, delta)
            if moved is None:
                sheet.filter, sheet.filtered_rows = None, set()
            else:
                sheet.filter["range"] = moved["ranges"][0]
                if axis == "col":
                    crit = {}
                    for c, v in sheet.filter.get("criteria", {}).items():
                        c = int(c)
                        nc = c + delta if (delta > 0 and c >= at) else (
                            None if delta < 0 and at <= c < at - delta else (c + delta if delta < 0 and c >= at - delta else c))
                        if nc is not None:
                            crit[nc] = v
                    sheet.filter["criteria"] = crit
            sheet.filtered_rows = {moved_r for moved_r in (
                (r + delta if r >= at else r) if delta > 0 else
                (None if at <= r < at - delta else (r + delta if r >= at - delta else r))
                for r in sheet.filtered_rows) if moved_r is not None} if axis == "row" else sheet.filtered_rows
        if sheet.page:
            page = dict(sheet.page)
            def mv(i):
                if delta > 0:
                    return i + delta if i >= at else i
                return None if at <= i < at - delta else (i + delta if i >= at - delta else i)
            if axis == "row" and page.get("rows") is not None:
                # a sheet has as many rows as it has: an inserted row is one
                # more, a deleted one fewer (the user, 2026-10-17)
                rows = int(page["rows"])
                if delta > 0:
                    rows = rows + delta if at < rows else max(rows, at + delta)
                else:
                    rows = max(1, rows - max(0, min(rows, at - delta) - at))
                used = sheet.data_area()          # (the cells have moved already)
                page["rows"] = max(rows, used[2] + 1) if used is not None else rows
            if axis == "row" and page.get("breaks"):
                page["breaks"] = sorted({m for m in (mv(b) for b in page["breaks"]) if m})
            if axis == "col" and page.get("col_breaks"):
                page["col_breaks"] = sorted({m for m in (mv(b) for b in page["col_breaks"]) if m})
            for key in ("print_area",):
                if page.get(key):
                    moved = _shift_ranges({"ranges": [page[key]]}, axis, at, delta)
                    page[key] = moved["ranges"][0] if moved else None
            if page.get("global_cells"):
                moved = _shift_ranges({"ranges": page["global_cells"]}, axis, at, delta)
                page["global_cells"] = moved["ranges"] if moved else []
            if axis == "row" and page.get("titles"):
                moved = _shift_ranges({"ranges": [[page["titles"][0], 0, page["titles"][1], 0]]},
                                      axis, at, delta)
                page["titles"] = [moved["ranges"][0][0], moved["ranges"][0][2]] if moved else None
            if axis == "col" and page.get("title_cols"):
                moved = _shift_ranges({"ranges": [[0, page["title_cols"][0], 0, page["title_cols"][1]]]},
                                      axis, at, delta)
                page["title_cols"] = [moved["ranges"][0][1], moved["ranges"][0][3]] if moved else None
            sheet.page = page
        if sheet.size is not None:
            rows, cols = sheet.size
            if axis == "row":
                rows = max(1, rows + delta) if delta > 0 or at < rows else rows
            else:
                cols = max(1, cols + delta) if delta > 0 or at < cols else cols
            sheet.size = (rows, cols)
        after = _layout_state(sheet)
        self._record(lambda: _set_layout(sheet, before), lambda: _set_layout(sheet, after))

    # -- layout ---------------------------------------------------------------------
    def _layout_change(self, sheet: Sheet, change: Callable[[], None]) -> None:
        before = _layout_state(sheet)
        change()
        after = _layout_state(sheet)
        if after != before:
            self._record(lambda: _set_layout(sheet, before), lambda: _set_layout(sheet, after))
            self._tell({("layout", sheet.id)})

    def set_widths(self, sheet: Sheet, cols, width: Optional[float]) -> None:
        """Column widths in points (None: back to the default)."""
        def change():
            for c in cols:
                if width is None:
                    sheet.widths.pop(c, None)
                else:
                    sheet.widths[c] = max(0.0, float(width))
        self._layout_change(sheet, change)

    def set_heights(self, sheet: Sheet, rows, height: Optional[float]) -> None:
        def change():
            for r in rows:
                if height is None:
                    sheet.heights.pop(r, None)
                else:
                    sheet.heights[r] = max(0.0, float(height))
        self._layout_change(sheet, change)

    def distribute(self, sheet: Sheet, axis: str, first: int, last: int) -> None:
        """Make the rows (or columns) first..last share their total evenly."""
        size = sheet.height if axis == "row" else sheet.width
        total = sum(size(i) for i in range(first, last + 1))
        each = total / (last - first + 1)
        if axis == "row":
            self.set_heights(sheet, range(first, last + 1), each)
        else:
            self.set_widths(sheet, range(first, last + 1), each)

    def set_hidden(self, sheet: Sheet, axis: str, indexes, hidden: bool) -> None:
        def change():
            target = sheet.hidden_rows if axis == "row" else sheet.hidden_cols
            for i in indexes:
                (target.add if hidden else target.discard)(i)
        self._layout_change(sheet, change)

    def drag_size(self, sheet: Sheet, axis: str, indexes, size: float, before: dict) -> None:
        """A column (row) heading's edge dragged to *size*, as Excel does it:
        dragged to nothing the column is hidden, keeping the width it had
        before the drag (*before*: index -> its own width or None) for
        Unhide; dragged open again it shows at the new width. Before, a
        column dragged to 0 was a 0-wide ghost that Unhide didn't know
        (QA, 2026-10-15)."""
        sizes = sheet.heights if axis == "row" else sheet.widths
        hidden = sheet.hidden_rows if axis == "row" else sheet.hidden_cols

        def change():
            for i in indexes:
                if size <= 0:
                    hidden.add(i)
                    old = before.get(i)
                    if old is None or old <= 0:
                        sizes.pop(i, None)
                    else:
                        sizes[i] = old
                else:
                    hidden.discard(i)
                    sizes[i] = float(size)
        self._layout_change(sheet, change)

    def merge(self, sheet: Sheet, top: int, left: int, bottom: int, right: int,
              across: bool = False) -> None:
        """Merge cells (Excel keeps only the top-left value); across=True
        merges each row on its own (Merge Across)."""
        with self.transaction("Merge"):
            blocks = [(r, left, r, right) for r in range(top, bottom + 1)] if across \
                else [(top, left, bottom, right)]
            for t, l, b, r in blocks:
                for row, col in list(sheet.positions_in(t, l, b, r)):
                    if (row, col) != (t, l):
                        cell = sheet.cells[(row, col)]
                        self._set_state(sheet, row, col, ("", cell.style, cell.comment))

            def change():
                for t, l, b, r in blocks:
                    sheet.merges = [m for m in sheet.merges
                                    if m[2] < t or m[0] > b or m[3] < l or m[1] > r]
                    if (t, l) != (b, r):
                        sheet.merges.append((t, l, b, r))
            self._layout_change(sheet, change)

    def unmerge(self, sheet: Sheet, top: int, left: int, bottom: int, right: int) -> None:
        def change():
            sheet.merges = [m for m in sheet.merges
                            if m[2] < top or m[0] > bottom or m[3] < left or m[1] > right]
        with self.transaction("Unmerge"):
            self._layout_change(sheet, change)

    def set_size(self, sheet: Sheet, rows: int, cols: int) -> None:
        """A table's extent; cells outside it are cleared."""
        rows, cols = max(1, int(rows)), max(1, int(cols))
        with self.transaction("Resize table"):
            for (r, c) in list(sheet.cells):
                if r >= rows or c >= cols:
                    self._set_state(sheet, r, c, ("", 0, None))

            def change():
                sheet.size = (rows, cols)
                sheet.merges = [m for m in sheet.merges if m[2] < rows and m[3] < cols]
            self._layout_change(sheet, change)

    # -- conditional formats, validation, filter ------------------------------------------
    def set_cond_rules(self, sheet: Sheet, rules: list) -> None:
        import copy
        with self.transaction("Conditional formatting"):
            self._layout_change(sheet, lambda: setattr(sheet, "cond_rules", copy.deepcopy(rules)))
        self._tell({("layout", sheet.id)})

    def set_page_options(self, sheet: Sheet, **changes) -> None:
        """Print area, titles, breaks, fit to width, centring... (one step)."""
        with self.transaction("Page setup"):
            self._layout_change(sheet, lambda: setattr(sheet, "page", {**sheet.page, **changes}))

    def set_validations(self, sheet: Sheet, validations: list) -> None:
        import copy
        with self.transaction("Data validation"):
            self._layout_change(sheet, lambda: setattr(sheet, "validations", copy.deepcopy(validations)))

    # -- styles ------------------------------------------------------------------------
    def style_of(self, sheet: Sheet, row: int, col: int) -> Style:
        cell = sheet.cells.get((row, col))
        return self.styles.get(cell.style if cell else 0)

    def restyle(self, sheet: Sheet, top: int, left: int, bottom: int, right: int,
                change: Callable[[Style, int, int], Style], label: str = "Format") -> None:
        """Give every cell in the block change(style, row, col)."""
        with self.transaction(label):
            for row in range(top, bottom + 1):
                for col in range(left, right + 1):
                    cell = sheet.cells.get((row, col))
                    old = self.styles.get(cell.style if cell else 0)
                    new = change(old, row, col)
                    if new != old:
                        index = self.styles.add(new)
                        state = (cell.input, index, cell.comment) if cell else ("", index, None)
                        self._set_state(sheet, row, col, state)

    def format_block(self, sheet: Sheet, top: int, left: int, bottom: int, right: int,
                     **fields) -> None:
        """Set style fields on every cell of a block: bold=True, fill="#ffff00"..."""
        self.restyle(sheet, top, left, bottom, right, lambda st, r, c: replace(st, **fields))

    def border_block(self, sheet: Sheet, top: int, left: int, bottom: int, right: int,
                     which: str, border) -> None:
        """Excel's border buttons: which is "all", "outside", "inside",
        "left", "right", "top", "bottom", "thick_box", or "none"."""
        def change(st: Style, r: int, c: int) -> Style:
            edges = {}
            if which == "none":
                return replace(st, left=None, right=None, top=None, bottom=None)
            if which in ("all", "inside"):
                if which == "all" or c > left:
                    edges["left"] = border
                if which == "all" or c < right:
                    edges["right"] = border
                if which == "all" or r > top:
                    edges["top"] = border
                if which == "all" or r < bottom:
                    edges["bottom"] = border
            if which in ("outside", "thick_box"):
                b = border if which == "outside" else replace(border, style="thick")
                if c == left:
                    edges["left"] = b
                if c == right:
                    edges["right"] = b
                if r == top:
                    edges["top"] = b
                if r == bottom:
                    edges["bottom"] = b
            if which == "left" and c == left:
                edges["left"] = border
            if which == "right" and c == right:
                edges["right"] = border
            if which == "top" and r == top:
                edges["top"] = border
            if which == "bottom" and r == bottom:
                edges["bottom"] = border
            return replace(st, **edges) if edges else st
        self.restyle(sheet, top, left, bottom, right, change, "Borders")

    def copy_block(self, src: Sheet, top: int, left: int, bottom: int, right: int,
                   dst: Sheet, row: int, col: int, what: str = "all") -> None:
        """Copy and paste: formulas follow by their relative references;
        what is "all", "values", "formulas" or "formats" (Paste Special)."""
        drow, dcol = row - top, col - left
        block = {}
        for r, c in list(src.positions_in(top, left, bottom, right)):
            cell = src.cells[(r, c)]
            block[(r - top, c - left)] = (cell.input, cell.style, cell.comment, cell.value)
        with self.transaction("Paste"):
            for i in range(bottom - top + 1):
                for j in range(right - left + 1):
                    got = block.get((i, j))
                    target = dst.cells.get((row + i, col + j))
                    old_style = target.style if target else 0
                    old_comment = target.comment if target else None
                    old_input = target.input if target else ""
                    if got is None:
                        if what in ("all", "formulas", "values"):
                            state = ("", old_style if what != "all" else 0, old_comment if what != "all" else None)
                        else:
                            state = (old_input, 0, old_comment)
                        self._set_state(dst, row + i, col + j, state)
                        continue
                    text, style, comment, value = got
                    if text.startswith("=") and len(text) > 1:
                        text = "=" + F.moved_formula(text[1:], drow, dcol)
                    if what == "values":
                        text = value_as_input(value)
                        state = (text, old_style, old_comment)
                    elif what == "formulas":
                        state = (text, old_style, old_comment)
                    elif what == "formats":
                        state = (old_input, style, old_comment)
                    else:
                        state = (text, style, comment)
                    self._set_state(dst, row + i, col + j, state)

    def move_block(self, sheet: Sheet, top: int, left: int, bottom: int, right: int,
                   dst: Sheet, row: int, col: int) -> None:
        """Cut and paste, or drag the selection's border: the cells move and
        every formula that read them reads them where they are now; the
        moved formulas themselves are unchanged. A formula that read a cell
        the block lands on gives #REF!, as in Excel: that cell was replaced."""
        drow, dcol = row - top, col - left
        if dst is sheet and drow == 0 and dcol == 0:
            return
        block = {}
        for r, c in list(sheet.positions_in(top, left, bottom, right)):
            block[(r, c)] = sheet.cells[(r, c)].state()
        d_top, d_left = row, col
        d_bottom, d_right = row + bottom - top, col + right - left

        def in_source(r, c):
            return top <= r <= bottom and left <= c <= right

        def landed_on(r, c):
            return d_top <= r <= d_bottom and d_left <= c <= d_right

        with self.transaction("Move"):
            def change(ref, s):
                if s is not sheet and s is not dst:
                    return ref
                if isinstance(ref, CellRef):
                    if s is sheet and in_source(ref.row, ref.col):
                        moved = replace(ref, row=ref.row + drow, col=ref.col + dcol)
                        return replace(moved, sheet=dst.name) if dst is not sheet else moved
                    if s is dst and landed_on(ref.row, ref.col):
                        return None
                    return ref
                if ref.whole:
                    return ref
                if s is dst and not (s is sheet and in_source(ref.top, ref.left)
                                     and in_source(ref.bottom, ref.right)) \
                        and landed_on(ref.top, ref.left) and landed_on(ref.bottom, ref.right):
                    return None
                if s is not sheet:
                    return ref
                if top <= ref.top and ref.bottom <= bottom and left <= ref.left and ref.right <= right:
                    moved = RangeRef(replace(ref.first, row=ref.first.row + drow, col=ref.first.col + dcol),
                                     replace(ref.last, row=ref.last.row + drow, col=ref.last.col + dcol),
                                     sheet=ref.sheet)
                    return replace(moved, sheet=dst.name) if dst is not sheet else moved
                return ref

            self._rewrite_all(change, sheet)
            fresh = {}
            for (r, c) in block:
                cell = sheet.cells.get((r, c))
                fresh[(r, c)] = cell.state() if cell else block[(r, c)]
                self._set_state(sheet, r, c, ("", 0, None))
            for i in range(bottom - top + 1):
                for j in range(right - left + 1):
                    state = fresh.get((top + i, left + j), ("", 0, None))
                    if dst is not sheet and state[0].startswith("="):
                        state = ("=" + _qualify_for(state[0][1:], sheet, dst), state[1], state[2])
                    self._set_state(dst, row + i, col + j, state)


# imported once, not on every cell read or worked out (an import inside a
# function costs a few microseconds each time under PySide6's import hook:
# 30 000 of them opening a 3000-row workbook, findings 5.5)
_LATE: dict = {}


def _functions():
    got = _LATE.get("functions")
    if got is None:
        from .functions import FUNCTIONS as got
        _LATE["functions"] = got
    return got


def _evaluate_cell():
    got = _LATE.get("evaluate_cell")
    if got is None:
        from .evaluate import evaluate_cell as got
        _LATE["evaluate_cell"] = got
    return got


def _shift_ranges(rule: dict, axis: str, at: int, delta: int):
    """A rule's (or validation's) ranges after rows/columns were inserted
    (delta > 0) or deleted; None when nothing of it is left."""
    out = []
    for t, l, b, r in rule.get("ranges", []):
        lo, hi = (t, b) if axis == "row" else (l, r)
        if delta > 0:
            lo2 = lo + delta if lo >= at else lo
            hi2 = hi + delta if hi >= at else hi
        else:
            gone = -delta
            last = at + gone - 1
            if lo >= at and hi <= last:
                continue
            lo2 = lo if lo < at else (at if lo <= last else lo - gone)
            hi2 = hi if hi < at else (at - 1 if hi <= last else hi - gone)
        out.append([lo2, l, hi2, r] if axis == "row" else [t, lo2, b, hi2])
    if not out:
        return None
    new = dict(rule)
    new["ranges"] = out
    return new


def _layout_state(sheet: Sheet) -> tuple:
    import copy
    return (dict(sheet.widths), dict(sheet.heights), frozenset(sheet.hidden_rows),
            frozenset(sheet.hidden_cols), tuple(sheet.merges), sheet.size,
            copy.deepcopy(sheet.cond_rules), copy.deepcopy(sheet.validations),
            copy.deepcopy(sheet.filter), frozenset(sheet.filtered_rows), copy.deepcopy(sheet.page))


def _set_layout(sheet: Sheet, state: tuple) -> None:
    import copy
    widths, heights, hrows, hcols, merges, size, rules, valids, filt, frows, page = state
    sheet.page = copy.deepcopy(page)
    sheet.widths, sheet.heights = dict(widths), dict(heights)
    sheet.hidden_rows, sheet.hidden_cols = set(hrows), set(hcols)
    sheet.merges, sheet.size = list(merges), size
    sheet.cond_rules, sheet.validations = copy.deepcopy(rules), copy.deepcopy(valids)
    sheet.filter, sheet.filtered_rows = copy.deepcopy(filt), set(frows)


def _qualify_for(text: str, src: Sheet, dst: Sheet) -> str:
    """A formula moved to another sheet keeps reading its old sheet."""
    def change(ref, s):
        if ref.sheet is None:
            return replace(ref, sheet=src.name)
        return ref

    return F.rewrite(text, change)


def _shift_ref(ref, on_sheet: bool, axis: str, at: int, inserted: int, deleted: int):
    """A reference after rows/columns were inserted or deleted (Excel's rules)."""
    if not on_sheet:
        return ref
    if isinstance(ref, CellRef):
        pos = ref.row if axis == "row" else ref.col
        if inserted:
            if pos >= at:
                pos += inserted
            else:
                return ref
        else:
            last = at + deleted - 1
            if at <= pos <= last:
                return None
            if pos > last:
                pos -= deleted
            else:
                return ref
        return replace(ref, row=pos) if axis == "row" else replace(ref, col=pos)
    if (axis == "row" and ref.whole == "cols") or (axis == "col" and ref.whole == "rows"):
        return ref
    lo = ref.top if axis == "row" else ref.left
    hi = ref.bottom if axis == "row" else ref.right
    limit = (MAX_ROWS if axis == "row" else MAX_COLS) - 1
    if inserted:
        new_lo = lo + inserted if lo >= at else lo
        new_hi = min(hi + inserted, limit) if hi >= at else hi
    else:
        last = at + deleted - 1
        if lo >= at and hi <= last:
            return None
        new_lo = lo if lo < at else (at if lo <= last else lo - deleted)
        new_hi = hi if hi < at else (at - 1 if hi <= last else hi - deleted)
    if (new_lo, new_hi) == (lo, hi):
        return ref
    first, last_ref = ref.first, ref.last
    # keep first as the top-left corner, as written
    if axis == "row":
        a, b = (first, last_ref) if first.row <= last_ref.row else (last_ref, first)
        a, b = replace(a, row=new_lo), replace(b, row=new_hi)
    else:
        a, b = (first, last_ref) if first.col <= last_ref.col else (last_ref, first)
        a, b = replace(a, col=new_lo), replace(b, col=new_hi)
    if first.row <= last_ref.row and first.col <= last_ref.col:
        return replace(ref, first=a, last=b)
    return replace(ref, first=a, last=b)


def _same(a, b) -> bool:
    if type(a) is not type(b):
        return False
    if isinstance(a, float):
        return a == b or (a != a and b != b)
    if isinstance(a, ErrorValue):
        return a == b and a.reason == b.reason      # a new reason is told too
    return a == b


# functions whose result is a date or a time, and the format they give a
# General cell (Excel's; the date as a typed one is shown)
_DATE_RESULT = {"DATE", "DATEVALUE", "TODAY", "EDATE", "EOMONTH", "WORKDAY", "WORKDAY.INTL"}
_TIME_RESULT = {"TIME", "TIMEVALUE"}


def formula_format(text: str, row: int = 0, col: int = 0, day_first: bool = True) -> Optional[str]:
    """The number format a formula's result implies, as Excel gives one to a
    General cell: a date for =DATE(...), =TODAY(), =TODAY()+7; a date and
    time for =NOW(); a time for =TIME(...). None otherwise (and for a date
    minus a date, a number of days)."""
    try:
        tree = F.parse(text, row, col).tree
    except F.FormulaError:
        return None
    date = "d/mm/yyyy" if day_first else "m/d/yyyy"

    def kind(n) -> Optional[str]:
        if type(n) is F.Call:
            if n.name in _DATE_RESULT:
                return date
            if n.name == "NOW":
                return date + " h:mm"
            if n.name in _TIME_RESULT:
                return "h:mm AM/PM"
            return None
        if type(n) is F.Binary and n.op in "+-":
            a, b = kind(n.left), kind(n.right)
            if a and b:
                return None if n.op == "-" else a
            return a or (b if n.op == "+" else None)
        return None

    return kind(tree)


def _tidy_formula(text: str) -> str:
    """What Excel does to a formula as it is entered: missing closing
    brackets are added."""
    depth = 0
    in_str = False
    for ch in text:
        if ch == '"':
            in_str = not in_str
        elif not in_str:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
    if depth > 0 and not in_str:
        text += ")" * depth
    return text


def _structured_nodes(tree) -> list:
    """The structured references in a formula's tree."""
    out = []

    def walk(n):
        if isinstance(n, F.Structured):
            out.append(n)
            return
        for child in getattr(n, "args", ()) or ():
            walk(child)
        for attr in ("left", "right", "arg"):
            child = getattr(n, attr, None)
            if child is not None:
                walk(child)

    walk(tree)
    return out


def _block(anchor: tuple, size: tuple):
    for i in range(size[0]):
        for j in range(size[1]):
            yield anchor[0] + i, anchor[1] + j


def value_as_input(value) -> str:
    """What to type to get this value back (Paste Values)."""
    from .values import Qty, general_number

    if value is BLANK:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        return general_number(value)
    if isinstance(value, Qty):
        unit = value.unit
        if not unit:
            from .values import default_unit
            unit = default_unit(value.dims)
        return f"{general_number(value.shown())} {unit}".strip()
    if isinstance(value, ErrorValue):
        return value.code
    if isinstance(value, str):
        from .inputs import read_value as rv

        got, _ = rv(value)
        return value if isinstance(got, str) and got == value else "'" + value
    if isinstance(value, Array):
        return value_as_input(value.get(0, 0))
    return str(value)


def defined_name_problem(name: str) -> Optional[str]:
    """Why a name can't be a defined name (Excel's rules); None when it can."""
    import re as _re
    if not name:
        return "A name can't be empty."
    if not _re.match(r"^[A-Za-z_\\\u00c0-\uffff][\w.\u00c0-\uffff]*$", name):
        return "A name starts with a letter or _ and has no spaces or symbols."
    if is_cell_name(name) or name.upper() in ("TRUE", "FALSE") or \
            _re.match(r"^(?:R\d*C\d*|R\d*|C\d*)$", name, _re.I):
        # R1C1, RC, R2C, C3 … are cells in Excel's other way of writing them
        return f"{name} looks like a cell; choose another name."
    return None


def name_problem(name: str) -> Optional[str]:
    """Why a name can't be used for a sheet, a table or a defined name; None
    when it can."""
    if not name or not name.strip():
        return "A name can't be empty."
    if len(name) > 31 and False:
        return "A name can be at most 31 characters."
    if any(ch in name for ch in "[]:*?/\\!"):
        return "A name can't contain [ ] : * ? / \\ or !"
    if name.startswith("'") or name.endswith("'"):
        return "A name can't start or end with an apostrophe."
    return None
