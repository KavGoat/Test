"""What a typed entry becomes, as Excel reads it.

    5            -> 5                 (General)
    1,250.5      -> 1250.5            (#,##0.0? Excel keeps "#,##0.00")
    12%          -> 0.12              (0%)
    $1,200       -> 1200              ($#,##0)
    (40)         -> -40
    5 kN         -> 5 kN              (a quantity; CalcForge's units)
    2.5 kN/m^2   -> 2.5 kN/m^2
    TRUE         -> TRUE
    #N/A         -> the error #N/A
    2026-10-09   -> a date (its Excel serial number, shown as a date)
    9/10/2026    -> 9 October 2026 (day first; the workbook says which)
    14:30        -> a time
    'anything    -> the text "anything"
    =A1+1        -> a formula
"""
from __future__ import annotations

import datetime as _dt
import re
from typing import Optional

from .values import BLANK, ERRORS, UnitTextError, unit_parts, with_unit

_NUMBER = re.compile(r"""^\s*
    (?P<paren>\()?\s*
    (?P<sign>[+-])?\s*
    (?P<cur>[$€£¥])?\s*
    (?P<sign2>[+-])?
    (?P<int>[0-9]{1,3}(?:,[0-9]{3})+|[0-9]*)
    (?P<frac>\.[0-9]*)?
    (?:[eE](?P<exp>[+-]?[0-9]+))?
    \s*(?P<pct>%)?\s*
    (?P<paren2>\))?\s*$""", re.X)

_UNIT_AFTER = re.compile(r"^\s*([+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)\s*(\S.*?)\s*$")

_MONTHS = {m.lower(): i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_MONTH_NAMES = {_dt.date(2000, i, 1).strftime("%B").lower(): i for i in range(1, 13)}


def _plain_number(text: str):
    """(number, format or None) for plain, comma, currency and percent
    numbers; None if it isn't one."""
    m = _NUMBER.match(text)
    if not m:
        return None
    digits = m.group("int") or ""
    frac = m.group("frac") or ""
    if not digits and frac in ("", "."):
        return None
    if bool(m.group("paren")) != bool(m.group("paren2")):
        return None
    if m.group("sign") and m.group("sign2"):
        return None
    try:
        x = float(digits.replace(",", "") + frac + ("e" + m.group("exp") if m.group("exp") else ""))
    except ValueError:
        return None
    negative = (m.group("sign") or m.group("sign2")) == "-" or bool(m.group("paren"))
    if negative:
        x = -x
    places = len(frac) - 1 if frac else 0
    decimals = ("." + "0" * places) if places else ""
    fmt = None
    if m.group("pct"):
        x /= 100.0
        fmt = "0" + decimals + "%"
    elif m.group("cur"):
        fmt = m.group("cur") + "#,##0" + (".00" if places else "")
        if negative and m.group("paren"):
            fmt += ";(" + fmt + ")"
    elif "," in digits:
        fmt = "#,##0" + (".00" if places else "")
    elif m.group("exp"):
        fmt = "0.00E+00"
    return x, fmt


def _date_serial(d: _dt.date) -> float:
    from .dates import serial_from_date

    return serial_from_date(d)


def _year(y: int) -> int:
    if y < 100:                         # Excel: 00-29 -> 2000s, 30-99 -> 1900s
        return 2000 + y if y < 30 else 1900 + y
    return y


def _time_part(text: str) -> Optional[float]:
    m = re.fullmatch(r"\s*([0-9]{1,2}):([0-9]{2})(?::([0-9]{2}(?:\.[0-9]+)?))?\s*([AaPp][Mm])?\s*", text)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    s = float(m.group(3) or 0)
    if m.group(4):
        if not 1 <= h <= 12:
            return None
        h = h % 12 + (12 if m.group(4).lower() == "pm" else 0)
    if h > 23 or mi > 59 or s >= 60:
        return None
    return (h * 3600 + mi * 60 + s) / 86400.0


def _date(text: str, day_first: bool):
    """(serial, format) for a typed date, or None."""
    text = text.strip()
    today = _dt.date.today()
    tries = []
    m = re.fullmatch(r"([0-9]{4})-([0-9]{1,2})-([0-9]{1,2})", text)
    if m:
        tries.append((int(m.group(1)), int(m.group(2)), int(m.group(3)), "yyyy-mm-dd"))
    m = re.fullmatch(r"([0-9]{1,2})[/-]([0-9]{1,2})(?:[/-]([0-9]{2,4}))?", text)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        year = _year(int(m.group(3))) if m.group(3) else today.year
        day, month = (a, b) if day_first else (b, a)
        fmt = ("d/mm/yyyy" if day_first else "m/d/yyyy") if m.group(3) else ("d-mmm" if day_first else "mmm-d")
        tries.append((year, month, day, fmt))
    m = re.fullmatch(r"([0-9]{1,2})[ -]([A-Za-z]{3,9})\.?(?:[ -,]+([0-9]{2,4}))?", text)
    if m:
        name = m.group(2).lower()
        month = _MONTHS.get(name[:3]) if (name[:3] in _MONTHS and
                                           (len(name) == 3 or name in _MONTH_NAMES)) else None
        if month:
            year = _year(int(m.group(3))) if m.group(3) else today.year
            tries.append((year, month, int(m.group(1)), "d-mmm-yy" if m.group(3) else "d-mmm"))
    m = re.fullmatch(r"([A-Za-z]{3,9})\.? ([0-9]{1,2}),? ([0-9]{2,4})", text)
    if m:
        name = m.group(1).lower()
        month = _MONTHS.get(name[:3]) if (name[:3] in _MONTHS and
                                           (len(name) == 3 or name in _MONTH_NAMES)) else None
        if month:
            tries.append((_year(int(m.group(3))), month, int(m.group(2)), "d-mmm-yy"))
    for year, month, day, fmt in tries:
        try:
            return _date_serial(_dt.date(year, month, day)), fmt
        except ValueError:
            continue
    return None


def number_from_text(text: str, day_first: bool = True):
    """The number in a piece of text, as Excel finds it when text is used in
    arithmetic ("5" + 1 = 6); None when there isn't one."""
    got = read_value(text, day_first)
    value = got[0]
    from .values import Qty

    if isinstance(value, (float, Qty)) and not isinstance(value, bool):
        return value
    return None


def read_value(text: str, day_first: bool = True):
    """(value, number format or None) for something typed into a cell that
    isn't a formula."""
    if text == "":
        return BLANK, None
    if text.startswith("'"):
        return text[1:], None
    stripped = text.strip()
    upper = stripped.upper()
    if upper == "TRUE":
        return True, None
    if upper == "FALSE":
        return False, None
    if upper in ERRORS:
        return ERRORS[upper], None
    got = _plain_number(stripped)
    if got is not None:
        return got
    got = _date(stripped, day_first)
    if got is not None:
        return got
    t = _time_part(stripped)
    if t is not None:
        return t, ("h:mm:ss" if stripped.count(":") == 2 else "h:mm") + \
            (" AM/PM" if stripped[-2:].upper() in ("AM", "PM") else "")
    if " " in stripped:
        date_text, _, time_text = stripped.rpartition(" ")
        if ":" in time_text or time_text.upper() in ("AM", "PM"):
            if time_text.upper() in ("AM", "PM"):
                date_text, _, clock = date_text.rpartition(" ")
                time_text = clock + " " + time_text
            day = _date(date_text, day_first)
            clock = _time_part(time_text)
            if day is not None and clock is not None:
                return day[0] + clock, "d/mm/yyyy h:mm" if day_first else "m/d/yyyy h:mm"
    m = re.fullmatch(r"([+-]?[0-9]+) ([0-9]+)/([0-9]+)", stripped)
    if m and int(m.group(3)) != 0:
        whole, num, den = int(m.group(1)), int(m.group(2)), int(m.group(3))
        x = abs(whole) + num / den
        return (-x if stripped.startswith("-") else x), "# ?/?"
    m = _UNIT_AFTER.match(stripped)
    if m:
        try:
            unit_parts(m.group(2))
        except UnitTextError:
            return text, None
        return with_unit(float(m.group(1)), m.group(2)), None
    return text, None
