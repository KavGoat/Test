"""Cell addresses as Excel writes them: A1, $B$7, AA10, Sheet1!C3, 'My sheet'!A1:B4.

Rows and columns are counted from 0 inside the program; the letters and
numbers shown are Excel's (column 0 is "A", row 0 is "1").
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Optional

# Excel's own limits
MAX_ROWS = 1_048_576
MAX_COLS = 16_384

_COL_RE = re.compile(r"^[A-Za-z]{1,3}$")
_CELL_RE = re.compile(r"^(\$?)([A-Za-z]{1,3})(\$?)([0-9]{1,7})$")


def col_letters(col: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    out = ""
    col += 1
    while col:
        col, rem = divmod(col - 1, 26)
        out = chr(65 + rem) + out
    return out


def col_index(letters: str) -> int:
    """A -> 0, Z -> 25, AA -> 26."""
    n = 0
    for ch in letters.upper():
        n = n * 26 + (ord(ch) - 64)
    return n - 1


@dataclass(frozen=True)
class CellRef:
    """One cell, with Excel's $ marks kept so copying knows what moves."""

    row: int
    col: int
    row_abs: bool = False
    col_abs: bool = False
    sheet: Optional[str] = None        # as written; None means "this sheet"

    def a1(self, with_sheet: bool = True) -> str:
        text = ("$" if self.col_abs else "") + col_letters(self.col) + \
               ("$" if self.row_abs else "") + str(self.row + 1)
        if with_sheet and self.sheet is not None:
            return quote_sheet(self.sheet) + "!" + text
        return text

    def moved(self, drow: int, dcol: int) -> Optional["CellRef"]:
        """Where this reference points once its formula is copied by
        (drow, dcol): relative parts move, $ parts stay. None when it would
        fall off the sheet (Excel writes #REF!)."""
        row = self.row if self.row_abs else self.row + drow
        col = self.col if self.col_abs else self.col + dcol
        if not (0 <= row < MAX_ROWS and 0 <= col < MAX_COLS):
            return None
        return replace(self, row=row, col=col)

    def cycled(self) -> "CellRef":
        """F4: A1 -> $A$1 -> A$1 -> $A1 -> A1."""
        state = (self.col_abs, self.row_abs)
        order = [(False, False), (True, True), (False, True), (True, False)]
        col_abs, row_abs = order[(order.index(state) + 1) % 4]
        return replace(self, col_abs=col_abs, row_abs=row_abs)


@dataclass(frozen=True)
class RangeRef:
    """A block of cells. Whole columns (A:C) and whole rows (2:5) are
    ranges that run to the sheet's edge, flagged so they print as written."""

    first: CellRef
    last: CellRef
    whole: str = ""                     # "", "cols" or "rows"
    sheet: Optional[str] = None

    @property
    def top(self) -> int:
        return min(self.first.row, self.last.row)

    @property
    def bottom(self) -> int:
        return max(self.first.row, self.last.row)

    @property
    def left(self) -> int:
        return min(self.first.col, self.last.col)

    @property
    def right(self) -> int:
        return max(self.first.col, self.last.col)

    @property
    def rows(self) -> int:
        return self.bottom - self.top + 1

    @property
    def cols(self) -> int:
        return self.right - self.left + 1

    def contains(self, row: int, col: int) -> bool:
        return self.top <= row <= self.bottom and self.left <= col <= self.right

    def a1(self, with_sheet: bool = True) -> str:
        if self.whole == "cols":
            text = ("$" if self.first.col_abs else "") + col_letters(self.first.col) + ":" + \
                   ("$" if self.last.col_abs else "") + col_letters(self.last.col)
        elif self.whole == "rows":
            text = ("$" if self.first.row_abs else "") + str(self.first.row + 1) + ":" + \
                   ("$" if self.last.row_abs else "") + str(self.last.row + 1)
        else:
            text = self.first.a1(False) + ":" + self.last.a1(False)
        if with_sheet and self.sheet is not None:
            return quote_sheet(self.sheet) + "!" + text
        return text

    def moved(self, drow: int, dcol: int) -> Optional["RangeRef"]:
        if self.whole == "cols":
            drow = 0
        elif self.whole == "rows":
            dcol = 0
        first, last = self.first.moved(drow, dcol), self.last.moved(drow, dcol)
        if first is None or last is None:
            return None
        return replace(self, first=first, last=last)

    def cells(self):
        for row in range(self.top, self.bottom + 1):
            for col in range(self.left, self.right + 1):
                yield row, col


def parse_cell(text: str) -> Optional[CellRef]:
    """"$B$7" -> CellRef(6, 1, True, True); None when it is not a cell."""
    m = _CELL_RE.match(text)
    if not m:
        return None
    col = col_index(m.group(2))
    row = int(m.group(4)) - 1
    if not (0 <= row < MAX_ROWS and 0 <= col < MAX_COLS):
        return None
    return CellRef(row, col, row_abs=bool(m.group(3)), col_abs=bool(m.group(1)))


def is_cell_name(text: str) -> bool:
    """Would Excel read this as a cell address? (Such a name can't be a
    defined name; a document variable spelled like one is written var(M20).)"""
    return parse_cell(text) is not None


def parse_range(text: str) -> Optional[RangeRef | CellRef]:
    """A1, A1:B5, A:C, 3:7, with an optional Sheet! or 'Sheet name'! in front."""
    sheet = None
    if "!" in text:
        sheet_text, _, text = text.rpartition("!")
        sheet = unquote_sheet(sheet_text)
        if sheet is None:
            return None
    if ":" not in text:
        cell = parse_cell(text)
        return replace(cell, sheet=sheet) if cell else None
    a, _, b = text.partition(":")
    ca, cb = parse_cell(a), parse_cell(b)
    if ca and cb:
        return RangeRef(ca, cb, sheet=sheet)
    sa, sb = a.lstrip("$"), b.lstrip("$")
    if _COL_RE.match(sa) and _COL_RE.match(sb):
        c1, c2 = col_index(sa), col_index(sb)
        if c1 >= MAX_COLS or c2 >= MAX_COLS:
            return None
        return RangeRef(CellRef(0, c1, True, a.startswith("$")),
                        CellRef(MAX_ROWS - 1, c2, True, b.startswith("$")), "cols", sheet)
    if sa.isdigit() and sb.isdigit():
        r1, r2 = int(sa) - 1, int(sb) - 1
        if not (0 <= r1 < MAX_ROWS and 0 <= r2 < MAX_ROWS):
            return None
        return RangeRef(CellRef(r1, 0, a.startswith("$"), True),
                        CellRef(r2, MAX_COLS - 1, b.startswith("$"), True), "rows", sheet)
    return None


_PLAIN_SHEET = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


def quote_sheet(name: str) -> str:
    """Sheet1 stays as it is; 'Loads 2' and names that look like cells are quoted."""
    if _PLAIN_SHEET.match(name) and not is_cell_name(name) and name.upper() not in ("TRUE", "FALSE"):
        return name
    return "'" + name.replace("'", "''") + "'"


def unquote_sheet(text: str) -> Optional[str]:
    if text.startswith("'"):
        if len(text) < 2 or not text.endswith("'"):
            return None
        return text[1:-1].replace("''", "'")
    return text or None


def area_text(top: int, left: int, bottom: int, right: int) -> str:
    """A plain A1 or A1:C4 for a block (no $, no sheet)."""
    first = col_letters(left) + str(top + 1)
    if (top, left) == (bottom, right):
        return first
    return first + ":" + col_letters(right) + str(bottom + 1)
