"""Conditional formatting of cells, as Excel's.

A sheet keeps a list of rules, highest priority first. Each rule:

    {"type": ..., "ranges": [[top, left, bottom, right], ...], "stop": False,
     "format": {style fields: color, fill, bold, italic, underline, strike,
                number_format}, ...type's own settings}

Types (Excel's Highlight Cells, Top/Bottom, Data Bars, Colour Scales, Icon
Sets and "Use a formula"):

    cell      op (between notBetween equal notEqual greater less
              greaterOrEqual lessOrEqual), a, b — values or "=formulas";
              "200 kN" compares quantities, a plain number compares the
              number as shown; units that don't match never match
    text      how (contains notContains begins ends), text
    blanks / noBlanks / errors / noErrors
    duplicate / unique
    top / bottom   n, percent
    above / below  average (equal: also the average itself)
    date      when (today yesterday tomorrow last7 thisMonth lastMonth nextMonth)
    formula   formula (relative to the range's top-left cell)
    databar   color, min/max (auto)
    scale     colors [low, (mid,) high]
    icons     set (arrows traffic flags), reverse

Every rule that applies to a cell gives its format, the higher one winning
where two set the same thing; a rule with "stop" set ends the list for the
cells it applies to. Data bars, colour scales and icons are drawn together.
"""
from __future__ import annotations

import datetime as _dt
import math
from typing import Optional

from . import formula as F
from .values import BLANK, ErrorValue, Qty, SheetError, is_number

TYPES = ["cell", "text", "blanks", "noBlanks", "errors", "noErrors", "duplicate", "unique",
         "top", "bottom", "above", "below", "date", "formula", "databar", "scale", "icons"]

ICON_SETS = {
    "arrows": [("▼", "#c92a2a"), ("▶", "#e8a33a"), ("▲", "#2b8a3e")],
    "traffic": [("●", "#c92a2a"), ("●", "#f2c94c"), ("●", "#2b8a3e")],
    "flags": [("⚑", "#c92a2a"), ("⚑", "#f2c94c"), ("⚑", "#2b8a3e")],
    "symbols": [("✖", "#c92a2a"), ("!", "#e8a33a"), ("✔", "#2b8a3e")],
}


def in_rule(rule: dict, row: int, col: int) -> bool:
    return any(t <= row <= b and l <= col <= r for t, l, b, r in rule.get("ranges", []))


def _cells(sheet, rule):
    """(row, col, value) of the filled cells a rule covers."""
    seen = set()
    for t, l, b, r in rule.get("ranges", []):
        for row, col in sheet.positions_in(t, l, b, r):
            if (row, col) not in seen:
                seen.add((row, col))
                yield row, col, sheet.value(row, col)


def _numbers(sheet, rule) -> list:
    out = []
    for _r, _c, v in _cells(sheet, rule):
        if is_number(v):
            out.append(_magnitude(v))
    return out


def _magnitude(v) -> float:
    return v.si if isinstance(v, Qty) else float(v)


def _target(sheet, rule, text, row, col):
    """A rule's value: typed ("5", "200 kN", "abc") or a formula ("=$B$1")."""
    if text is None or text == "":
        return BLANK
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return float(text)
    text = str(text)
    if text.startswith("=") and len(text) > 1:
        t, l = rule["ranges"][0][0], rule["ranges"][0][1]
        try:
            tree = F.parse(text[1:], t, l).tree
        except F.FormulaError:
            return None
        from .evaluate import evaluate_cell
        value, _reads = evaluate_cell(sheet.workbook, sheet, row, col, tree)
        return value
    from .inputs import read_value
    value, _fmt = read_value(text, sheet.workbook.day_first)
    return value


def compare(value, target) -> Optional[int]:
    """-1, 0, 1, or None when they can't be compared (units that don't match)."""
    from .evaluate import compare_values
    if isinstance(value, ErrorValue) or isinstance(target, ErrorValue) or target is None:
        return None
    if isinstance(value, Qty) and isinstance(target, (float, int)) and not isinstance(target, bool):
        x, y = value.shown(), float(target)                # a plain number: as shown
        return (x > y) - (x < y)
    if isinstance(value, Qty) and isinstance(target, Qty) and tuple(value.dims) != tuple(target.dims):
        return None
    if isinstance(target, Qty) and not isinstance(value, Qty):
        return None
    try:
        return compare_values(value, target)
    except SheetError:
        return None


class Looks:
    """What the rules make of a sheet's cells, worked out once per change."""

    def __init__(self, sheet):
        self.sheet = sheet
        self.version = None
        self._stats: dict = {}

    def _fresh(self) -> None:
        version = (self.sheet.workbook.version, id(self.sheet.cond_rules), len(self.sheet.cond_rules))
        if version != self.version:
            self.version = version
            self._stats = {}

    def stats(self, index: int, rule: dict):
        got = self._stats.get(index)
        if got is not None:
            return got
        kind = rule["type"]
        sheet = self.sheet
        if kind in ("top", "bottom"):
            nums = sorted(_numbers(sheet, rule), reverse=(kind == "top"))
            n = int(rule.get("n", 10))
            if rule.get("percent"):
                n = max(1, int(len(nums) * n / 100))
            got = nums[n - 1] if 0 < n <= len(nums) else (nums[-1] if nums else None)
        elif kind in ("above", "below"):
            nums = _numbers(sheet, rule)
            got = sum(nums) / len(nums) if nums else None
        elif kind in ("duplicate", "unique"):
            counts: dict = {}
            for _r, _c, v in _cells(sheet, rule):
                if v is BLANK:
                    continue
                key = v.lower() if isinstance(v, str) else v
                counts[key] = counts.get(key, 0) + 1
            got = counts
        elif kind in ("databar", "scale", "icons"):
            nums = sorted(_numbers(sheet, rule))
            got = (nums[0], nums[-1], nums) if nums else None
        self._stats[index] = got
        return got

    def look(self, row: int, col: int) -> dict:
        """{"format": {style fields}, "bar": (fraction, colour), "scale": colour,
        "icon": (glyph, colour)} for one cell (only what applies)."""
        self._fresh()
        out: dict = {}
        fmt: dict = {}
        sheet = self.sheet
        value = sheet.value(row, col)
        for index, rule in enumerate(sheet.cond_rules):
            if not in_rule(rule, row, col):
                continue
            kind = rule.get("type")
            hit = False
            try:
                hit = self._test(index, rule, kind, value, row, col, out)
            except (SheetError, ValueError, TypeError, ZeroDivisionError):
                hit = False
            if hit:
                for k, v in (rule.get("format") or {}).items():
                    if v is not None and k not in fmt:
                        fmt[k] = v
                if rule.get("stop"):
                    break
        if fmt:
            out["format"] = fmt
        return out

    def _test(self, index, rule, kind, value, row, col, out) -> bool:
        sheet = self.sheet
        if kind == "cell":
            op = rule.get("op", "greater")
            a = _target(sheet, rule, rule.get("a"), row, col)
            if value is BLANK and op not in ("equal", "notEqual"):
                value = 0.0 if is_number(a) or isinstance(a, Qty) else ""
            ca = compare(value, a)
            if op in ("between", "notBetween"):
                b = _target(sheet, rule, rule.get("b"), row, col)
                cb = compare(value, b)
                if ca is None or cb is None:
                    return False
                lo_ok = ca >= 0 if compare(a, b) in (-1, 0, None) else ca <= 0
                hi_ok = cb <= 0 if compare(a, b) in (-1, 0, None) else cb >= 0
                inside = lo_ok and hi_ok
                return inside if op == "between" else not inside
            if ca is None:
                return op == "notEqual"
            return {"equal": ca == 0, "notEqual": ca != 0, "greater": ca > 0, "less": ca < 0,
                    "greaterOrEqual": ca >= 0, "lessOrEqual": ca <= 0}.get(op, False)
        if kind == "text":
            if isinstance(value, ErrorValue):
                return False
            from .values import to_text
            have = to_text(value).lower() if value is not BLANK else ""
            want = str(rule.get("text", "")).lower()
            how = rule.get("how", "contains")
            return {"contains": want in have, "notContains": want not in have,
                    "begins": have.startswith(want), "ends": have.endswith(want)}.get(how, False)
        if kind == "blanks":
            return value is BLANK or value == ""
        if kind == "noBlanks":
            return not (value is BLANK or value == "")
        if kind == "errors":
            return isinstance(value, ErrorValue)
        if kind == "noErrors":
            return not isinstance(value, ErrorValue)
        if kind in ("duplicate", "unique"):
            if value is BLANK:
                return False
            counts = self.stats(index, rule)
            key = value.lower() if isinstance(value, str) else value
            n = counts.get(key, 0)
            return n > 1 if kind == "duplicate" else n == 1
        if kind in ("top", "bottom"):
            cut = self.stats(index, rule)
            if cut is None or not is_number(value):
                return False
            x = _magnitude(value)
            return x >= cut if kind == "top" else x <= cut
        if kind in ("above", "below"):
            avg = self.stats(index, rule)
            if avg is None or not is_number(value):
                return False
            x = _magnitude(value)
            if rule.get("equal") and abs(x - avg) <= 1e-12 * max(1.0, abs(avg)):
                return True
            return x > avg if kind == "above" else x < avg
        if kind == "date":
            if not is_number(value) or isinstance(value, Qty):
                return False
            from .dates import date_from_serial
            try:
                d = date_from_serial(float(value))
            except ValueError:
                return False
            today = _dt.date.today()
            when = rule.get("when", "today")
            if when == "today":
                return d == today
            if when == "yesterday":
                return d == today - _dt.timedelta(days=1)
            if when == "tomorrow":
                return d == today + _dt.timedelta(days=1)
            if when == "last7":
                return today - _dt.timedelta(days=6) <= d <= today
            if when == "thisMonth":
                return (d.year, d.month) == (today.year, today.month)
            if when == "lastMonth":
                first = today.replace(day=1) - _dt.timedelta(days=1)
                return (d.year, d.month) == (first.year, first.month)
            if when == "nextMonth":
                nxt = (today.replace(day=28) + _dt.timedelta(days=4)).replace(day=1)
                return (d.year, d.month) == (nxt.year, nxt.month)
            return False
        if kind == "formula":
            got = _target(sheet, rule, rule.get("formula"), row, col)
            from .values import to_bool
            try:
                return got is not BLANK and not isinstance(got, ErrorValue) and to_bool(got)
            except SheetError:
                return False
        if kind in ("databar", "scale", "icons"):
            stats = self.stats(index, rule)
            if stats is None or not is_number(value):
                return False
            lo, hi, nums = stats
            x = _magnitude(value)
            t = 0.5 if hi == lo else (x - lo) / (hi - lo)
            if kind == "databar":
                out.setdefault("bar", (max(0.05, t), rule.get("color", "#638ec6")))
            elif kind == "scale":
                colours = rule.get("colors") or ["#f8696b", "#ffeb84", "#63be7b"]
                out.setdefault("scale", _blend(colours, t))
            else:
                icons = ICON_SETS.get(rule.get("set", "arrows"), ICON_SETS["arrows"])
                if rule.get("reverse"):
                    icons = list(reversed(icons))
                k = 0 if t < 1 / 3 else (1 if t < 2 / 3 else 2)
                out.setdefault("icon", icons[k])
            return False                   # drawn, not a format
        return False


def _blend(colours: list, t: float) -> str:
    from PySide6.QtGui import QColor  # (colour arithmetic only)

    t = max(0.0, min(1.0, t))
    if len(colours) == 3:
        if t <= 0.5:
            a, b, u = colours[0], colours[1], t * 2
        else:
            a, b, u = colours[1], colours[2], (t - 0.5) * 2
    else:
        a, b, u = colours[0], colours[-1], t
    ca, cb = QColor(a), QColor(b)
    return QColor(round(ca.red() + (cb.red() - ca.red()) * u), round(ca.green() + (cb.green() - ca.green()) * u),
                  round(ca.blue() + (cb.blue() - ca.blue()) * u)).name()


def looks_for(sheet) -> Looks:
    got = getattr(sheet, "_looks", None)
    if got is None:
        got = Looks(sheet)
        sheet._looks = got
    return got


def describe(rule: dict) -> str:
    kind = rule.get("type")
    names = {"greater": "greater than", "less": "less than", "between": "between",
             "notBetween": "not between", "equal": "equal to", "notEqual": "not equal to",
             "greaterOrEqual": "greater than or equal to", "lessOrEqual": "less than or equal to"}
    if kind == "cell":
        text = f"Cell value {names.get(rule.get('op'), rule.get('op'))} {rule.get('a')}"
        if rule.get("op") in ("between", "notBetween"):
            text += f" and {rule.get('b')}"
        return text
    if kind == "text":
        return f"Text {rule.get('how', 'contains')} “{rule.get('text', '')}”"
    if kind in ("top", "bottom"):
        return f"{kind.title()} {rule.get('n', 10)}{'%' if rule.get('percent') else ''}"
    if kind in ("above", "below"):
        return f"{kind.title()} average" + (" or equal" if rule.get("equal") else "")
    if kind == "formula":
        return f"Formula: {rule.get('formula')}"
    if kind == "date":
        return f"Date: {rule.get('when')}"
    return {"blanks": "Blanks", "noBlanks": "No blanks", "errors": "Errors", "noErrors": "No errors",
            "duplicate": "Duplicate values", "unique": "Unique values", "databar": "Data bar",
            "scale": "Colour scale", "icons": "Icon set"}.get(kind, kind)
