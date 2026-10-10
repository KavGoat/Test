"""The cells of every sheet and table in a document, and keeping them calculated.

One :class:`Workbook` holds all of a document's spreadsheet sections and
tables (each a :class:`Sheet`), so a formula can read any of them by name
('Sheet 2'!B4). Within the workbook cells are calculated in the order they
depend on each other, as Excel does; a loop is a circular reference: its
cells show 0 and :attr:`Workbook.circular` lists them, as Excel's status bar
does.

Names that are neither cells nor defined names are variables from the
document's equations; :attr:`Workbook.outside` is asked for them (the
document answers with the value defined before the sheet in reading order).

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
from .style import Border, Style, StyleTable
from .values import BLANK, NAME, REF, SPILL, Array, ErrorValue, SheetError


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


class Sheet:
    """One spreadsheet section or table."""

    def __init__(self, workbook: "Workbook", sheet_id: int, name: str, kind: str = "sheet"):
        self.workbook = workbook
        self.id = sheet_id
        self.name = name
        self.kind = kind                 # "sheet" (pages of grid) or "table" (on a page)
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

    def _put(self, row: int, col: int, cell: Cell) -> None:
        if (row, col) not in self.cells:
            rows = self._rows_in_col.setdefault(col, [])
            bisect.insort(rows, row)
        self.cells[(row, col)] = cell

    def _drop(self, row: int, col: int) -> None:
        if self.cells.pop((row, col), None) is not None:
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

    def col_x(self, col: int) -> float:
        """Left edge of a column, from the sheet's left edge."""
        x = col * self.default_width
        for c, w in self.widths.items():
            if c < col:
                x += w - self.default_width
        for c in self.hidden_cols:
            if c < col:
                x -= self.widths.get(c, self.default_width)
        return x

    def row_y(self, row: int) -> float:
        y = row * self.default_height
        for r, h in self.heights.items():
            if r < row:
                y += h - self.default_height
        for r in self.hidden_rows | self.filtered_rows:
            if r < row:
                y -= self.heights.get(r, self.default_height)
        return y

    def col_at(self, x: float) -> int:
        """The column under x (the last one when x is past the right edge of a table)."""
        return _index_at(x, self.width, self.size[1] if self.size else None)

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


class Workbook:
    def __init__(self):
        self.sheets: list[Sheet] = []
        self._next_id = 1
        self.styles = StyleTable()
        self.names: dict[tuple, DefinedName] = {}    # (lower name, sheet id or None)
        self.day_first = True
        # asked for a document variable: outside(sheet, name) -> value; raises KeyError
        self.outside: Optional[Callable] = None
        self.circular: list[tuple] = []              # (sheet, row, col) in a loop
        self.listeners: list[Callable[[set], None]] = []   # told the keys whose values changed
        self._deps = _Dependents()
        self._dirty: set = set()
        self._touched: list = []                     # cells changed since the last calculation
        self._volatile: set = set()
        self._precedents: dict[tuple, tuple] = {}    # key -> (cells, blocks) as read statically
        self._evaluating: set = set()
        self._done: set = set()
        self._in_pass = False
        self._changed: set = set()
        self._outside_reads: dict[tuple, set] = {}
        self._spill_moved: list = []                 # spilled values that changed this pass
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
        for s in self.sheets:
            if s.name.lower() == lower:
                return s
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
                        text = F.rename_sheet_in(cell.input[1:], old, new)
                        if "=" + text != cell.input:
                            self._set_state(other, row, col, ("=" + text, cell.style, cell.comment))
            for key, dn in list(self.names.items()):
                text = F.rename_sheet_in(dn.refers_to, old, new)
                if text != dn.refers_to:
                    self._set_name(key, replace(dn, refers_to=text))

            def apply(name, s=sheet):
                s.name = name
                self._names_changed()

            apply(new)
            self._record(lambda: apply(old), lambda: apply(new))

    #: told when sheets or defined names come, go or are renamed (the
    #: document's equations read them by name)
    on_names_changed: Optional[Callable[[], None]] = None

    def _names_changed(self) -> None:
        """Sheets or names came or went: anything reading them by name is
        looked at again."""
        if self.on_names_changed is not None:
            self.on_names_changed()
        for sheet in self.sheets:
            for (row, col), cell in sheet.cells.items():
                if cell.is_formula:
                    self._dirty.add((sheet.id, row, col))
        self._recalc_if_auto()

    # -- defined names ----------------------------------------------------------------
    def define_name(self, name: str, refers_to: str, sheet: Optional[Sheet] = None,
                    comment: str = "", home: Optional[Sheet] = None) -> None:
        """Name a cell, block or constant: define_name("W_total", "Loads!$D$12").
        *sheet* makes it local to that sheet; *home* is the sheet it is saved
        with when it names no cells (g = 9.81)."""
        problem = defined_name_problem(name)
        if problem:
            raise ValueError(problem)
        if refers_to.startswith("="):
            refers_to = refers_to[1:]
        F.parse(refers_to)              # raises FormulaError if it can't be read
        key = (name.lower(), sheet.id if sheet else None)
        with self.transaction("Define name"):
            self._set_name(key, DefinedName(name, refers_to, sheet.id if sheet else None, comment,
                                            (home or sheet).id if (home or sheet) else None))

    def remove_name(self, name: str, sheet: Optional[Sheet] = None) -> None:
        key = (name.lower(), sheet.id if sheet else None)
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
        self._dirty_many(list(self._deps.names.get(lower, ())), include_self=True)
        self._recalc_if_auto()

    def find_name(self, name: str, sheet: Optional[Sheet]) -> Optional[DefinedName]:
        lower = name.lower()
        if sheet is not None:
            local = self.names.get((lower, sheet.id))
            if local is not None:
                return local
        return self.names.get((lower, None))

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

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo_label(self) -> str:
        return self._undo[-1].label if self._undo else ""

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
        with self.transaction("Typing"):
            self._set_state(sheet, row, col, (text, style, comment))

    def set_inputs(self, sheet: Sheet, row: int, col: int, rows: list[list[str]], label="Paste") -> None:
        with self.transaction(label):
            for i, line in enumerate(rows):
                for j, text in enumerate(line):
                    self.set_input(sheet, row + i, col + j, text)

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
            self._dirty.add(key)
        elif cell is not None:
            value, _fmt = read_value(text, self.day_first)
            if cell.value != value or type(cell.value) is not type(value):
                cell.value = value
            cell.parsed = None
            cell.problem = None
            self._changed.add(key)
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
            self._dirty.add((sheet.id,) + anchor)
        for anchor, (rows, cols) in list(sheet.wanted.items()):
            if anchor != (row, col) and anchor[0] <= row < anchor[0] + rows \
                    and anchor[1] <= col < anchor[1] + cols:
                self._dirty.add((sheet.id,) + anchor)

    def _recalc_if_auto(self) -> None:
        if self.auto and self._open is None and not self._replaying and not self._in_pass:
            self.recalculate()

    # -- what each formula reads ------------------------------------------------------------
    def _forget(self, key) -> None:
        self._deps.remove(key)
        self._precedents.pop(key, None)
        self._volatile.discard(key)
        self._outside_reads.pop(key, None)

    def _learn(self, sheet: Sheet, row: int, col: int, cell: Cell) -> None:
        key = (sheet.id, row, col)
        try:
            cell.parsed = F.parse(cell.input[1:], row, col)
            cell.problem = None
        except F.FormulaError as e:
            cell.parsed = None
            cell.problem = str(e)
            return
        cells, blocks = [], []
        for sheet_name, top, left, bottom, right in F.references(cell.parsed.tree, row, col):
            target = sheet if sheet_name is None else self.sheet(sheet_name)
            if target is None:
                continue
            if top == bottom and left == right:
                cells.append((target.id, top, left))
            else:
                blocks.append((target.id, top, left, bottom, right))
        names = [n.lower() for n in cell.parsed.names]
        for n in cell.parsed.names:
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

    def _dirty_from(self, key, include_self: bool) -> None:
        """Mark everything that reads key (directly or not) for recalculation."""
        self._dirty_many([key], include_self)

    def _dirty_many(self, keys, include_self: bool) -> None:
        seen = set(keys)
        if include_self:
            self._dirty.update(keys)
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
        if self._touched:
            touched, self._touched = self._touched, []
            self._dirty_many(touched, include_self=False)
        if everything:
            for sheet in self.sheets:
                for (row, col), cell in sheet.cells.items():
                    if cell.is_formula:
                        self._dirty.add((sheet.id, row, col))
        if edited and self._volatile:
            self._dirty_many(list(self._volatile), include_self=True)
        if not self._dirty:
            changed, self._changed = self._changed, set()
            if changed:
                self._tell(changed)
            return changed
        self._in_pass = True
        try:
            order, loops = self._order()
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
            for key in order:
                if key not in self._done:
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
                order, loops = self._order()
                for key in order:
                    if key not in self._done:
                        self._compute(key)
                        self._dirty.discard(key)
        finally:
            self._spill_moved = []
            self._dirty.clear()
            self._done.clear()
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
        """The dirty formulas, each after those it reads; and the ones in loops."""
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

        def precedents(key):
            cells, blocks = self._precedents.get(key, ((), ()))
            for k in cells:
                if k in dirty:
                    yield k
                else:
                    a = anchor_of(k)
                    if a is not None:
                        yield a
            for sid, top, left, bottom, right in blocks:
                sheet = sheets.get(sid)
                if sheet is None:
                    continue
                for row, col in sheet.positions_in(top, left, bottom, right):
                    k = (sid, row, col)
                    if k in dirty:
                        yield k
                    else:
                        a = anchor_of(k)
                        if a is not None:
                            yield a

        for start in list(dirty):
            if start in state:
                continue
            sheet = sheets.get(start[0])
            if sheet is None or (start[1], start[2]) not in sheet.cells:
                state[start] = 2
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
                    state[key] = 2
                    order.append(key)
        return order, loops

    def _compute(self, key) -> None:
        from .evaluate import evaluate_cell

        sheet = self.sheet_by_id(key[0])
        cell = sheet.cells.get(key[1:]) if sheet else None
        if cell is None:
            self._done.add(key)
            return
        if not cell.is_formula:
            self._done.add(key)
            return
        self._evaluating.add(key)
        try:
            if cell.parsed is None and cell.problem is None:
                self._learn(sheet, key[1], key[2], cell)
            if cell.parsed is None:
                value = NAME if cell.problem else BLANK
                reads = set()
            else:
                value, reads = evaluate_cell(self, sheet, key[1], key[2], cell.parsed.tree)
        finally:
            self._evaluating.discard(key)
        self._done.add(key)
        self._dirty.discard(key)
        if reads:
            self._outside_reads[key] = reads
        else:
            self._outside_reads.pop(key, None)
        value = self._spill(sheet, key, value)
        if not _same(cell.value, value):
            cell.value = value
            self._changed.add(key)

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
    def _rewrite_all(self, change, label_sheet: Sheet) -> None:
        """Pass every reference in every formula and name through change(ref,
        effective sheet)."""
        for other in self.sheets:
            for (row, col), cell in list(other.cells.items()):
                if not cell.is_formula:
                    continue
                text = F.rewrite(cell.input[1:], lambda ref, s, o=other: change(ref, self.sheet(s) if s else o))
                if "=" + text != cell.input:
                    self._set_state(other, row, col, ("=" + text, cell.style, cell.comment))
        for key, dn in list(self.names.items()):
            home = self.sheet_by_id(dn.sheet) if dn.sheet else None
            text = F.rewrite(dn.refers_to, lambda ref, s, h=home: change(ref, self.sheet(s) if s else h))
            if text != dn.refers_to:
                self._set_name(key, replace(dn, refers_to=text))

    def _clear_spills(self, sheet: Sheet) -> None:
        """Before cells move about: every spill on the sheet is taken back and
        its formula calculated again where it lands."""
        for anchor in list(sheet.spills):
            self._unspill(sheet, anchor)
        for anchor in list(sheet.wanted):
            sheet.wanted.pop(anchor, None)
            self._dirty.add((sheet.id,) + anchor)

    def _move_cells(self, sheet: Sheet, mapping: Callable[[int, int], Optional[tuple]]) -> None:
        """Move every cell of the sheet to mapping(row, col) (None: deleted)."""
        self._clear_spills(sheet)
        moves = []
        for (row, col), cell in list(sheet.cells.items()):
            to = mapping(row, col)
            if to != (row, col):
                moves.append(((row, col), to, cell.state()))
        for (row, col), _to, _state in moves:
            self._set_state(sheet, row, col, ("", 0, None))
        for _frm, to, state in moves:
            if to is not None:
                self._set_state(sheet, to[0], to[1], state)

    def insert_rows(self, sheet: Sheet, at: int, count: int = 1) -> None:
        with self.transaction("Insert rows"):
            self._move_cells(sheet, lambda r, c: (r + count, c) if r >= at else (r, c))
            self._rewrite_all(lambda ref, s: _shift_ref(ref, s is sheet, "row", at, count, 0), sheet)
            self._shift_extras(sheet, "row", at, count)

    def delete_rows(self, sheet: Sheet, at: int, count: int = 1) -> None:
        with self.transaction("Delete rows"):
            last = at + count - 1
            self._move_cells(sheet, lambda r, c: None if at <= r <= last else
                             ((r - count, c) if r > last else (r, c)))
            self._rewrite_all(lambda ref, s: _shift_ref(ref, s is sheet, "row", at, 0, count), sheet)
            self._shift_extras(sheet, "row", at, -count)

    def insert_cols(self, sheet: Sheet, at: int, count: int = 1) -> None:
        with self.transaction("Insert columns"):
            self._move_cells(sheet, lambda r, c: (r, c + count) if c >= at else (r, c))
            self._rewrite_all(lambda ref, s: _shift_ref(ref, s is sheet, "col", at, count, 0), sheet)
            self._shift_extras(sheet, "col", at, count)

    def delete_cols(self, sheet: Sheet, at: int, count: int = 1) -> None:
        with self.transaction("Delete columns"):
            last = at + count - 1
            self._move_cells(sheet, lambda r, c: None if at <= c <= last else
                             ((r, c - count) if c > last else (r, c)))
            self._rewrite_all(lambda ref, s: _shift_ref(ref, s is sheet, "col", at, 0, count), sheet)
            self._shift_extras(sheet, "col", at, -count)

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
            if axis == "row" and page.get("breaks"):
                page["breaks"] = sorted({m for m in (mv(b) for b in page["breaks"]) if m})
            for key in ("print_area",):
                if page.get(key):
                    moved = _shift_ranges({"ranges": [page[key]]}, axis, at, delta)
                    page[key] = moved["ranges"][0] if moved else None
            if axis == "row" and page.get("titles"):
                moved = _shift_ranges({"ranges": [[page["titles"][0], 0, page["titles"][1], 0]]},
                                      axis, at, delta)
                page["titles"] = [moved["ranges"][0][0], moved["ranges"][0][2]] if moved else None
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
        moved formulas themselves are unchanged."""
        drow, dcol = row - top, col - left
        if dst is sheet and drow == 0 and dcol == 0:
            return
        block = {}
        for r, c in list(sheet.positions_in(top, left, bottom, right)):
            block[(r, c)] = sheet.cells[(r, c)].state()
        with self.transaction("Move"):
            def change(ref, s):
                if s is not sheet:
                    return ref
                if isinstance(ref, CellRef):
                    if top <= ref.row <= bottom and left <= ref.col <= right:
                        moved = replace(ref, row=ref.row + drow, col=ref.col + dcol)
                        return replace(moved, sheet=dst.name) if dst is not sheet else moved
                    return ref
                if ref.whole:
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
    return a == b


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
    if is_cell_name(name) or name.upper() in ("R", "C", "TRUE", "FALSE"):
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
