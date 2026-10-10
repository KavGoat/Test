"""Excel's Data tools on a sheet: Sort, AutoFilter, Remove Duplicates and
Text to Columns.

Sort: rows of a block reordered by one or more columns, each A→Z or Z→A, as
Excel orders values (numbers, text without regard to case, FALSE, TRUE,
errors; blanks always last). A formula moving with its row reads the same
row as before, as Excel's sort leaves it.

AutoFilter: drop-downs on a block's first row; each column may keep only
some values, or those passing one or two conditions, or its top/bottom n;
rows that don't pass are hidden (and not printed), and SUBTOTAL leaves them
out.

Remove Duplicates: rows whose chosen columns repeat an earlier row's (text
compared without regard to case, as Excel does) go; the rest close up.

Text to Columns: each cell of one column split at its delimiters into it
and the cells to its right, typed in as if entered there.
"""
from __future__ import annotations

from functools import cmp_to_key
from typing import Optional

from . import formula as F
from .inputs import read_value
from .numfmt import format_value
from .values import BLANK, ErrorValue, Qty, is_number


def _key(value):
    """Excel's sort order."""
    if value is BLANK or value == "":
        return (5, 0)
    if isinstance(value, ErrorValue):
        return (4, value.code)
    if isinstance(value, bool):
        return (3, int(value))
    if isinstance(value, str):
        return (2, value.lower())
    if isinstance(value, Qty):
        return (1, value.si)
    return (1, float(value))


def sort_block(wb, sheet, top: int, left: int, bottom: int, right: int,
               keys: list, header: bool = False) -> None:
    """keys: [(column, ascending), ...] in order of importance."""
    first = top + 1 if header else top
    if first > bottom:
        return
    rows = list(range(first, bottom + 1))

    def cmp(a, b):
        for col, ascending in keys:
            ka, kb = _key(sheet.value(a, col)), _key(sheet.value(b, col))
            if ka == kb:
                continue
            # blanks stay last whichever way
            if ka[0] == 5 or kb[0] == 5:
                return 1 if ka[0] == 5 else -1
            less = ka < kb
            return (-1 if less else 1) * (1 if ascending else -1)
        return 0

    order = sorted(rows, key=cmp_to_key(cmp))
    if order == rows:
        return
    states = {}
    for r in rows:
        for c in range(left, right + 1):
            cell = sheet.cells.get((r, c))
            states[(r, c)] = cell.state() if cell else ("", 0, None)
    with wb.transaction("Sort"):
        for target, source in zip(rows, order):
            for c in range(left, right + 1):
                text, style, comment = states[(source, c)]
                if text.startswith("=") and len(text) > 1 and target != source:
                    text = "=" + F.moved_formula(text[1:], target - source, 0)
                wb._set_state(sheet, target, c, (text, style, comment))


# -- AutoFilter ---------------------------------------------------------------------------
def shown(sheet, row: int, col: int) -> str:
    cell = sheet.cells.get((row, col))
    if cell is None or cell.value is BLANK:
        return ""
    st = sheet.workbook.styles.get(cell.style)
    return format_value(cell.value, st.number_format, st.unit).text


def column_values(sheet, col: int) -> list:
    """The distinct values shown in a filtered column (for the check list),
    of every row of the filter, hidden or not; "" stands for blanks."""
    t, l, b, r = sheet.filter["range"]
    seen = []
    for row in range(t + 1, b + 1):
        text = shown(sheet, row, col)
        if text not in seen:
            seen.append(text)
    return sorted(seen, key=lambda s: (s == "", _key(_value_of(sheet, s))))


def _value_of(sheet, text):
    from .inputs import read_value
    return read_value(text, sheet.workbook.day_first)[0]


def _passes(sheet, row: int, col: int, crit: dict, stats) -> bool:
    kind = crit.get("kind")
    if kind == "values":
        return shown(sheet, row, col) in set(crit.get("values", []))
    value = sheet.value(row, col)
    if kind == "top":
        return stats is not None and is_number(value) and (
            (value.si if isinstance(value, Qty) else float(value)) >= stats if not crit.get("bottom")
            else (value.si if isinstance(value, Qty) else float(value)) <= stats)
    if kind == "custom":
        from .functions import criterion
        tests = [criterion(c) for c in crit.get("conditions", []) if c]
        if not tests:
            return True
        results = [t(value) for t in tests]
        return all(results) if crit.get("join", "and") == "and" else any(results)
    return True


def apply_filter(wb, sheet) -> None:
    """Hide the rows of the filter's block that don't pass every column's
    criteria (one undo step with whatever set them)."""
    flt = sheet.filter
    before = set(sheet.filtered_rows)
    hidden = set()
    if flt is not None:
        t, l, b, r = flt["range"]
        stats = {}
        for col, crit in flt.get("criteria", {}).items():
            if crit.get("kind") == "top":
                nums = []
                for row in range(t + 1, b + 1):
                    v = sheet.value(row, int(col))
                    if is_number(v):
                        nums.append(v.si if isinstance(v, Qty) else float(v))
                nums.sort(reverse=not crit.get("bottom"))
                n = int(crit.get("n", 10))
                if crit.get("percent"):
                    n = max(1, len(nums) * n // 100)
                stats[col] = nums[min(n, len(nums)) - 1] if nums else None
        for row in range(t + 1, b + 1):
            for col, crit in flt.get("criteria", {}).items():
                if not _passes(sheet, row, int(col), crit, stats.get(col)):
                    hidden.add(row)
                    break
    if hidden != before:
        wb._layout_change(sheet, lambda: setattr(sheet, "filtered_rows", hidden))
        # SUBTOTAL and AGGREGATE leave filtered rows out: they count again
        for other in wb.sheets:
            for (r, c), cell in other.cells.items():
                if cell.parsed is not None and cell.parsed.functions & {"SUBTOTAL", "AGGREGATE"}:
                    wb._dirty.add((other.id, r, c))
                    wb._touched.append((other.id, r, c))
        wb._recalc_if_auto()


def set_filter(wb, sheet, block: Optional[tuple]) -> None:
    """Turn AutoFilter on for a block (its first row the headings), or off."""
    with wb.transaction("Filter"):
        if block is None:
            wb._layout_change(sheet, lambda: (setattr(sheet, "filter", None),
                                              setattr(sheet, "filtered_rows", set())))
        else:
            wb._layout_change(sheet, lambda: setattr(sheet, "filter",
                                                     {"range": list(block), "criteria": {}}))


def set_criteria(wb, sheet, col: int, crit: Optional[dict]) -> None:
    with wb.transaction("Filter"):
        def change():
            criteria = dict(sheet.filter.get("criteria", {}))
            if crit is None:
                criteria.pop(col, None)
            else:
                criteria[col] = crit
            sheet.filter = dict(sheet.filter, criteria=criteria)
        wb._layout_change(sheet, change)
        apply_filter(wb, sheet)


# -- Remove Duplicates and Text to Columns -------------------------------------------------------------
def remove_duplicates(wb, sheet, top: int, left: int, bottom: int, right: int,
                      columns: list, header: bool = False) -> tuple:
    """(removed, kept): rows of the block whose ``columns`` repeat an earlier
    row's are taken out and the rest move up, formulas moving with them."""
    first = top + 1 if header else top
    seen, keep = set(), []
    for r in range(first, bottom + 1):
        key = tuple(_key(sheet.value(r, c)) for c in columns)
        if key in seen:
            continue
        seen.add(key)
        keep.append(r)
    removed = bottom - first + 1 - len(keep)
    if not removed:
        return 0, len(keep)
    states = {(r, c): (sheet.cells[(r, c)].state() if (r, c) in sheet.cells else ("", 0, None))
              for r in range(first, bottom + 1) for c in range(left, right + 1)}
    with wb.transaction("Remove duplicates"):
        for target in range(first, bottom + 1):
            k = target - first
            for c in range(left, right + 1):
                if k < len(keep):
                    source = keep[k]
                    text, style, comment = states[(source, c)]
                    if text.startswith("=") and len(text) > 1 and target != source:
                        text = "=" + F.moved_formula(text[1:], target - source, 0)
                    wb._set_state(sheet, target, c, (text, style, comment))
                else:
                    wb._set_state(sheet, target, c, ("", states[(target, c)][1], None))
    return removed, len(keep)


def split_text(text: str, delimiters: str, together: bool = False, qualifier: str = '"') -> list:
    """One cell's text in pieces, as Text to Columns cuts it: at any of the
    delimiters, not inside the qualifier's quotes; several delimiters in a
    row as one when ``together``."""
    if not delimiters:
        return [text]
    out, piece, quoted, i = [], "", False, 0
    while i < len(text):
        ch = text[i]
        if qualifier and ch == qualifier:
            if quoted and text[i + 1:i + 2] == qualifier:
                piece += ch
                i += 2
                continue
            quoted = not quoted
        elif ch in delimiters and not quoted:
            out.append(piece)
            piece = ""
            if together:
                while i + 1 < len(text) and text[i + 1] in delimiters:
                    i += 1
        else:
            piece += ch
        i += 1
    out.append(piece)
    return out


def text_to_columns(wb, sheet, top: int, col: int, bottom: int, delimiters: str,
                    together: bool = False, qualifier: str = '"') -> int:
    """Split column ``col`` from ``top`` to ``bottom``; the widest row's
    number of pieces."""
    widest = 0
    with wb.transaction("Text to columns"):
        for r in range(top, bottom + 1):
            cell = sheet.cells.get((r, col))
            if cell is None or not cell.input or cell.input.startswith("="):
                continue
            pieces = split_text(cell.input, delimiters, together, qualifier)
            widest = max(widest, len(pieces))
            for k, piece in enumerate(pieces):
                target = sheet.cells.get((r, col + k))
                style = target.style if target else 0
                if piece.strip() and is_number(read_value(piece.strip(), wb.day_first)[0]):
                    piece = piece.strip()          # " 2" comes in as the number 2, as in Excel
                wb._set_state(sheet, r, col + k, (piece, style, target.comment if target else None))
    return widest
