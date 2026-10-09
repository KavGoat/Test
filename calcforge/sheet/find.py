"""Find and Replace in a sheet's cells, as Excel's: in what was typed
(formulas) or in what is shown (values); match case; match the entire cell."""
from __future__ import annotations

import re

from .numfmt import format_value
from .values import BLANK


def _shown(sheet, cell) -> str:
    if cell.value is BLANK:
        return ""
    st = sheet.workbook.styles.get(cell.style)
    return format_value(cell.value, st.number_format, st.unit).text


def _pattern(what: str, case: bool, whole: bool):
    # Excel's wildcards: * any run, ? any one, ~ escapes them
    out = []
    i = 0
    while i < len(what):
        ch = what[i]
        if ch == "~" and i + 1 < len(what) and what[i + 1] in "*?~":
            out.append(re.escape(what[i + 1]))
            i += 2
            continue
        out.append(".*?" if ch == "*" else "." if ch == "?" else re.escape(ch))
        i += 1
    body = "".join(out)
    if whole:
        body = "^" + body + "$"
    return re.compile(body, 0 if case else re.I)


def find_all(sheet, what: str, look_in: str = "formulas", case: bool = False, whole: bool = False,
             block=None) -> list[tuple]:
    """(row, col) of every cell that matches, row by row."""
    if not what:
        return []
    pattern = _pattern(what, case, whole)
    out = []
    for (row, col), cell in sorted(sheet.cells.items()):
        if block is not None:
            t, l, b, r = block
            if not (t <= row <= b and l <= col <= r):
                continue
        text = cell.input if look_in == "formulas" else _shown(sheet, cell)
        if not text and cell.comment and look_in == "comments":
            text = cell.comment
        if look_in == "comments":
            text = cell.comment or ""
        if text and pattern.search(text):
            out.append((row, col))
    return out


def replace_in(sheet, row: int, col: int, what: str, replacement: str, case: bool = False,
               whole: bool = False) -> bool:
    """Replace in one cell's typed text (formulas too). True if it changed."""
    cell = sheet.cells.get((row, col))
    if cell is None or not cell.input:
        return False
    pattern = _pattern(what, case, whole)
    new = pattern.sub(lambda m: replacement, cell.input)
    if new == cell.input:
        return False
    sheet.workbook.set_input(sheet, row, col, new)
    return True


def replace_all(sheet, what: str, replacement: str, case: bool = False, whole: bool = False,
                block=None) -> int:
    wb = sheet.workbook
    n = 0
    with wb.transaction("Replace"):
        for row, col in find_all(sheet, what, "formulas", case, whole, block):
            n += replace_in(sheet, row, col, what, replacement, case, whole)
    return n
