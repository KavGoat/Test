"""Excel's fill handle: dragging a selection's corner to fill more cells.

Each line along the drag (each column when dragging down, each row when
dragging across) is filled from what the selection holds in that line:

* one number is copied (Ctrl while dragging counts up by 1 instead);
* two or more numbers continue their straight line (1, 3 -> 5, 7, 9);
* a date counts on by a day; two dates continue by their step, in months
  or years when they are a whole number of months apart;
* text ending in a number counts on ("Item 1" -> "Item 2");
* day and month names continue (Mon, Tue...; January, February...);
* a quantity continues in its unit (100 mm, 200 mm -> 300 mm);
* formulas are copied with their relative references moved;
* anything else is repeated as a pattern.

Cell formats come along with the values, repeated as a pattern.
"""
from __future__ import annotations

import calendar
import re
from typing import Optional

from . import formula as F
from .dates import date_from_serial, serial_from_date
from .inputs import read_value
from .numfmt import is_date_format
from .values import BLANK, Qty, general_number

_LISTS = [
    ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
    ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    ["January", "February", "March", "April", "May", "June", "July", "August", "September",
     "October", "November", "December"],
]
_TRAILING = re.compile(r"^(.*?)(\d+)(\D*)$")


def _in_list(text: str):
    low = text.lower()
    for lst in _LISTS:
        for i, word in enumerate(lst):
            if word.lower() == low:
                return lst, i
    return None


def _cased(word: str, like: str) -> str:
    if like.isupper():
        return word.upper()
    if like.islower():
        return word.lower()
    return word


def _add_months(serial: float, months: int) -> float:
    d = date_from_serial(serial)
    total = d.year * 12 + d.month - 1 + months
    y, m = divmod(total, 12)
    day = min(d.day, calendar.monthrange(y, m + 1)[1])
    return serial_from_date(d.replace(year=y, month=m + 1, day=day)) + (serial - int(serial))


def _months_between(a: float, b: float) -> Optional[int]:
    da, db = date_from_serial(a), date_from_serial(b)
    if da.day != db.day:
        return None
    return (db.year - da.year) * 12 + db.month - da.month


def series(inputs: list[str], formats: list, count: int, step_one: bool = False,
           day_first: bool = True) -> list[str]:
    """What to type into the next ``count`` cells after ``inputs`` (one
    line of the selection, in fill order). Formulas are handled by the caller."""
    values = [read_value(t, day_first)[0] for t in inputs]
    n = len(inputs)
    if n == 0:
        return [""] * count
    nums = all(isinstance(v, float) and not isinstance(v, bool) for v in values)
    dated = nums and all(is_date_format(f) for f in formats)
    if dated:
        if n == 1:
            return [_date_text(values[0] + (i + 1), formats[0]) for i in range(count)]
        months = _months_between(values[0], values[1]) if n >= 2 else None
        if months and all(_months_between(values[i], values[i + 1]) == months for i in range(n - 1)):
            return [_date_text(_add_months(values[-1], months * (i + 1)), formats[-1]) for i in range(count)]
        step = values[1] - values[0]
        return [_date_text(values[-1] + step * (i + 1), formats[-1]) for i in range(count)]
    if nums:
        if n == 1:
            step = 1.0 if step_one else 0.0
            return [_number_text(values[0] + step * (i + 1), inputs[0]) for i in range(count)]
        slope, intercept = _line(values)
        return [_number_text(intercept + slope * (n + i), inputs[-1]) for i in range(count)]
    if all(isinstance(v, Qty) for v in values) and len({v.unit for v in values}) == 1 and values[0].unit:
        shown = [v.shown() for v in values]
        unit = values[0].unit
        if n == 1:
            step = 1.0 if step_one else 0.0
            return [f"{general_number(shown[0] + step * (i + 1))} {unit}" for i in range(count)]
        slope, intercept = _line(shown)
        return [f"{general_number(intercept + slope * (n + i))} {unit}" for i in range(count)]
    if all(isinstance(v, str) for v in values) and all(t for t in inputs):
        listed = [_in_list(t) for t in inputs]
        if all(listed) and len({id(lst) for lst, _ in listed}) == 1:
            lst = listed[0][0]
            step = (listed[1][1] - listed[0][1]) % len(lst) if n >= 2 else 1
            start = listed[-1][1]
            return [_cased(lst[(start + step * (i + 1)) % len(lst)], inputs[-1]) for i in range(count)]
        parts = [_TRAILING.match(t) for t in inputs]
        if all(parts) and len({(m.group(1), m.group(3)) for m in parts}) == 1:
            numbers = [int(m.group(2)) for m in parts]
            step = numbers[1] - numbers[0] if n >= 2 else 1
            width = len(parts[-1].group(2))
            prefix, suffix = parts[0].group(1), parts[0].group(3)
            out = []
            for i in range(count):
                k = numbers[-1] + step * (i + 1)
                digits = str(abs(k)).zfill(width) if parts[-1].group(2).startswith("0") else str(abs(k))
                out.append(f"{prefix}{'-' if k < 0 else ''}{digits}{suffix}")
            return out
    return [inputs[i % n] for i in range(count)]


def _line(ys: list[float]):
    """Least-squares straight line through (0, y0), (1, y1)... as Excel's
    fill does for a linear trend."""
    n = len(ys)
    mx = (n - 1) / 2
    my = sum(ys) / n
    sxx = sum((i - mx) ** 2 for i in range(n))
    slope = sum((i - mx) * (y - my) for i, y in enumerate(ys)) / sxx if sxx else 0.0
    return slope, my - slope * mx


def _number_text(x: float, like: str) -> str:
    x = round(x, 12)
    text = general_number(x)
    if like.strip().endswith("%"):
        return general_number(round(x * 100, 10)) + "%"
    return text


def _date_text(serial: float, fmt) -> str:
    d = date_from_serial(serial)
    return d.isoformat()


def fill(wb, sheet, src: tuple, dst: tuple, step_one: bool = False) -> None:
    """Fill dst (top, left, bottom, right), which extends src beyond one of
    its sides, from src. One undo step."""
    st, sl, sb, sr = src
    dt, dl, db, dr = dst
    if dt == st and db == sb:
        axis = "col"
        forward = dl > sr
    else:
        axis = "row"
        forward = dt > sb
    with wb.transaction("Fill"):
        if axis == "row":
            lines = range(sl, sr + 1)
            src_pos = list(range(st, sb + 1))
            targets = list(range(dt, db + 1)) if forward else list(range(db, dt - 1, -1))
        else:
            lines = range(st, sb + 1)
            src_pos = list(range(sl, sr + 1))
            targets = list(range(dl, dr + 1)) if forward else list(range(dr, dl - 1, -1))
        order = src_pos if forward else list(reversed(src_pos))
        for line in lines:
            def at(i):
                return (i, line) if axis == "row" else (line, i)
            cells = [sheet.cells.get(at(i)) for i in order]
            inputs = [c.input if c else "" for c in cells]
            styles = [c.style if c else 0 for c in cells]
            comments = [c.comment if c else None for c in cells]
            formats = [wb.styles.get(s).number_format for s in styles]
            has_formula = any(t.startswith("=") and len(t) > 1 for t in inputs)
            plain = not has_formula and all(inputs)
            if plain:
                fresh = series(inputs, formats, len(targets), step_one, wb.day_first)
            else:
                fresh = []
                for k, target in enumerate(targets):
                    j = k % len(order)
                    text = inputs[j]
                    if text.startswith("=") and len(text) > 1:
                        src_index = order[j]
                        d = target - src_index
                        drow, dcol = (d, 0) if axis == "row" else (0, d)
                        text = "=" + F.moved_formula(text[1:], drow, dcol)
                    fresh.append(text)
            for k, target in enumerate(targets):
                j = k % len(order)
                row, col = at(target)
                wb._set_state(sheet, row, col, (fresh[k], styles[j], None))
