"""Why a cell shows an error, in one line (Excel's error indicator and tip).

QA (2026-10-15): #UNITS!, #DIV/0!, #NAME?, #VALUE! and var() failures came
with no explanation. Errors now carry a reason from where they are made
(values.ErrorValue.reason), and :func:`why` says it for a cell, following
the error back to the cell it started in:

    #UNITS! — kN and m can't be added (A1 + A2)
    #DIV/0! — from B5: dividing by zero (B4 is 0)
    #NAME? — 'Spna' isn't a function, a defined name or a variable from the equations
"""
from __future__ import annotations

from typing import Optional

from . import formula as F
from .refs import col_letters, quote_sheet
from .values import ErrorValue

# what each error means, said when nothing more is known
MEANING = {
    "#DIV/0!": "dividing by zero (or nothing to average)",
    "#VALUE!": "a value of the wrong kind, such as text where a number is wanted",
    "#NAME?": "a name in the formula isn't known",
    "#REF!": "a reference to cells that aren't there",
    "#NUM!": "a number that can't be worked out: too big, or out of range",
    "#N/A": "no value is available: a lookup found nothing",
    "#NULL!": "the ranges don't meet",
    "#SPILL!": "the result can't spill: something is in the way of its block",
    "#CALC!": "the calculation gives nothing (an empty result)",
    "#UNITS!": "the units don't match",
}

_MOST_CELLS = 20000          # cells looked through in a block a formula reads


def _address(sheet, row: int, col: int, home) -> str:
    a1 = f"{col_letters(col)}{row + 1}"
    return a1 if sheet is home else f"{quote_sheet(sheet.name)}!{a1}"


def _source(sheet, row: int, col: int, error: ErrorValue, seen: set):
    """The cell this one's error came from — one the formula reads that
    holds the same error — or None when the error started here."""
    cell = sheet.cells.get((row, col))
    if cell is None:
        return None
    if cell.spill_from is not None and cell.spill_from != (row, col):
        return None
    if cell.parsed is None:
        return None
    wb = sheet.workbook
    looked = 0
    for name, top, left, bottom, right in F.references(cell.parsed.tree, row, col):
        target = sheet if name is None else wb.sheet(name)
        if target is None:
            continue
        for r, c in target.positions_in(top, left, bottom, right):
            looked += 1
            if looked > _MOST_CELLS:
                return None
            key = (target.id, r, c)
            if key in seen:
                continue
            v = target.cells[(r, c)].value
            if isinstance(v, ErrorValue) and v.code == error.code and \
                    (not error.reason or v.reason == error.reason):
                return target, r, c
    return None


def why(sheet, row: int, col: int) -> Optional[str]:
    """One line saying what went wrong in the cell and where, or None when
    it holds no error."""
    cell = sheet.cells.get((row, col))
    if cell is None or not isinstance(cell.value, ErrorValue):
        return None
    error = cell.value
    if cell.problem:
        return f"{error.code} — {cell.problem}"
    # follow the error back through the cells it was passed on from
    here, at = (sheet, row, col), error
    seen = {(sheet.id, row, col)}
    for _ in range(100):
        got = _source(*here, at, seen)
        if got is None:
            break
        here = got
        seen.add((got[0].id, got[1], got[2]))
        at = got[0].cells[(got[1], got[2])].value
    origin = here[0].cells.get(here[1:])
    reason = at.reason or error.reason
    if origin is not None and origin.problem:
        reason = origin.problem
    reason = reason or MEANING.get(error.code, "")
    if here == (sheet, row, col):
        return f"{error.code} — {reason}" if reason else error.code
    return f"{error.code} — from {_address(*here, sheet)}: {reason}"
