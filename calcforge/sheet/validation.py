"""Data validation, as Excel's: what a cell may hold.

    {"ranges": [[t, l, b, r]], "type": "any|whole|decimal|list|date|time|length|custom",
     "op": "between|notBetween|equal|notEqual|greater|less|greaterOrEqual|lessOrEqual",
     "a": ..., "b": ..., "source": "a,b,c" or "=$A$1:$A$5", "formula": "=...",
     "blank": True, "dropdown": True,
     "input_title": "", "input": "", "style": "stop|warning|information",
     "error_title": "", "error": ""}

Quantities are allowed in the limits ("between 0 kN and 500 kN").
"""
from __future__ import annotations

from typing import Optional

from . import formula as F
from .inputs import read_value
from .values import BLANK, ErrorValue, Qty, is_number


def at(sheet, row: int, col: int) -> Optional[dict]:
    for v in reversed(sheet.validations):
        if any(t <= row <= b and l <= col <= r for t, l, b, r in v.get("ranges", [])):
            return v
    return None


def _limit(sheet, rule, text, row, col):
    from .condfmt import _target
    return _target(sheet, rule, text, row, col)


def list_items(sheet, rule: dict, row: int = 0, col: int = 0) -> list[str]:
    """The choices of a List validation, as text."""
    source = str(rule.get("source", "")).strip()
    if source.startswith("="):
        try:
            tree = F.parse(source[1:], rule["ranges"][0][0], rule["ranges"][0][1]).tree
        except F.FormulaError:
            return []
        from .evaluate import Ctx, RefValue, ev
        try:
            got = ev(tree, Ctx(sheet.workbook, sheet, row, col))
        except Exception:
            return []
        from .numfmt import format_value
        if isinstance(got, RefValue):
            out = []
            for r in range(got.top, got.bottom + 1):
                for c in range(got.left, got.right + 1):
                    v = got.sheet.value(r, c)
                    if v is not BLANK:
                        st = got.sheet.workbook.style_of(got.sheet, r, c)
                        out.append(format_value(v, st.number_format, st.unit).text)
            return out
        return []
    sep = ";" if ";" in source and "," not in source else ","
    return [s.strip() for s in source.split(sep) if s.strip()]


def check(sheet, row: int, col: int, text: str) -> Optional[str]:
    """None when what was typed is allowed in the cell; else the message to show."""
    rule = at(sheet, row, col)
    if rule is None or rule.get("type", "any") == "any":
        return None
    message = rule.get("error") or "This value doesn't match the data validation restrictions defined for this cell."
    if text == "":
        return None if rule.get("blank", True) else message
    kind = rule["type"]
    if kind == "list":
        items = list_items(sheet, rule, row, col)
        return None if text.strip().lower() in [i.lower() for i in items] else message
    if kind == "custom":
        from .condfmt import _target
        from .values import to_bool
        wb = sheet.workbook
        # the formula sees the new value: try it in, then put the old one back
        cell = sheet.cells.get((row, col))
        old = cell.state() if cell else ("", 0, None)
        journal, wb.journal = wb.journal, False
        try:
            wb._set_state(sheet, row, col, (text, old[1], old[2]))
            wb.recalculate()
            got = _target(sheet, rule, rule.get("formula"), row, col)
        finally:
            wb._set_state(sheet, row, col, old)
            wb.recalculate()
            wb.journal = journal
        try:
            return None if got is not BLANK and not isinstance(got, ErrorValue) and to_bool(got) else message
        except Exception:
            return message
    value = read_value(text, sheet.workbook.day_first)[0]
    if kind == "length":
        value = float(len(text))
    elif kind in ("whole", "decimal", "date", "time"):
        if not is_number(value):
            return message
        if kind == "whole":
            x = value.shown() if isinstance(value, Qty) else float(value)
            if abs(x - round(x)) > 1e-9:
                return message
        if kind == "time" and not isinstance(value, Qty):
            value = float(value) - int(float(value))
    from .condfmt import compare
    op = rule.get("op", "between")
    a = _limit(sheet, rule, rule.get("a"), row, col)
    ca = compare(value, a)
    if op in ("between", "notBetween"):
        b = _limit(sheet, rule, rule.get("b"), row, col)
        cb = compare(value, b)
        if ca is None or cb is None:
            return message
        inside = ca >= 0 and cb <= 0
        ok = inside if op == "between" else not inside
    else:
        if ca is None:
            return message
        ok = {"equal": ca == 0, "notEqual": ca != 0, "greater": ca > 0, "less": ca < 0,
              "greaterOrEqual": ca >= 0, "lessOrEqual": ca <= 0}.get(op, True)
    return None if ok else message


def invalid_cells(sheet) -> list[tuple]:
    """Cells that hold something their validation doesn't allow (Circle Invalid Data)."""
    from .numfmt import format_value
    out = []
    for rule in sheet.validations:
        for t, l, b, r in rule.get("ranges", []):
            for row, col in list(sheet.positions_in(t, l, b, r)):
                cell = sheet.cells.get((row, col))
                text = cell.input if cell else ""
                if text.startswith("="):
                    st = sheet.workbook.styles.get(cell.style)
                    text = format_value(cell.value, st.number_format, st.unit).text
                if check(sheet, row, col, text) is not None:
                    out.append((row, col))
    return out
