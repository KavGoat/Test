"""Excel number formats: "0.00", "#,##0", "0%", "0.00E+00", "# ?/?",
"d/mm/yyyy", "h:mm AM/PM", "[Red]-0.0", "[>=1000]#,##0;0", "@"...

:func:`format_value` gives the text a cell shows and the colour the format
asks for. A quantity is shown as its number in its unit, formatted, then the
unit: "5.00 kN".
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from typing import Optional

from .dates import datetime_from_serial
from .values import BLANK, Array, ErrorValue, Qty, default_unit, general_number, unit_parts

COLORS = {"black": "#000000", "blue": "#0000FF", "cyan": "#00FFFF", "green": "#00FF00",
          "magenta": "#FF00FF", "red": "#FF0000", "white": "#FFFFFF", "yellow": "#FFFF00"}
# Excel's 56-colour palette, for [Color n]
_PALETTE = ["000000", "FFFFFF", "FF0000", "00FF00", "0000FF", "FFFF00", "FF00FF", "00FFFF",
            "800000", "008000", "000080", "808000", "800080", "008080", "C0C0C0", "808080",
            "9999FF", "993366", "FFFFCC", "CCFFFF", "660066", "FF8080", "0066CC", "CCCCFF",
            "000080", "FF00FF", "FFFF00", "00FFFF", "800080", "800000", "008080", "0000FF",
            "00CCFF", "CCFFFF", "CCFFCC", "FFFF99", "99CCFF", "FF99CC", "CC99FF", "FFCC99",
            "3366FF", "33CCCC", "99CC00", "FFCC00", "FF9900", "FF6600", "666699", "969696",
            "003366", "339966", "003300", "333300", "993300", "993366", "333399", "333333"]

_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"]
_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


@dataclass
class Shown:
    text: str
    color: Optional[str] = None
    number: bool = False            # right-aligned under General alignment


# -- splitting a format into sections and tokens -----------------------------------------------
def _sections(code: str) -> list[str]:
    out, cur, i = [], [], 0
    while i < len(code):
        ch = code[i]
        if ch == '"':
            j = code.find('"', i + 1)
            j = len(code) - 1 if j < 0 else j
            cur.append(code[i:j + 1])
            i = j + 1
            continue
        if ch == "\\" and i + 1 < len(code):
            cur.append(code[i:i + 2])
            i += 2
            continue
        if ch == ";":
            out.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(ch)
        i += 1
    out.append("".join(cur))
    return out


@dataclass
class _Section:
    tokens: list            # (kind, text)
    color: Optional[str]
    condition: Optional[tuple]
    kind: str               # "number", "date", "text", "general"
    percent: int
    scale: int              # trailing commas: divide by 1000 each
    elapsed: bool


_DATE_TOKEN = re.compile(r"(yyyy|yy|e|mmmmm|mmmm|mmm|mm|m|dddd|ddd|dd|d|hh|h|ss|s|AM/PM|am/pm|A/P|a/p|\[h+\]|\[m+\]|\[s+\])", re.I)


def _tokenize(text: str) -> list:
    tokens = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '"':
            j = text.find('"', i + 1)
            j = len(text) if j < 0 else j
            tokens.append(("lit", text[i + 1:j]))
            i = j + 1
            continue
        if ch == "\\":
            tokens.append(("lit", text[i + 1:i + 2]))
            i += 2
            continue
        if ch == "_":
            tokens.append(("lit", " "))
            i += 2
            continue
        if ch == "*":
            i += 2                       # fill: nothing in a fixed text
            continue
        if ch == "[":
            j = text.find("]", i)
            j = len(text) if j < 0 else j
            inner = text[i + 1:j]
            if re.fullmatch(r"h+|m+|s+", inner, re.I):
                tokens.append(("date", "[" + inner.lower() + "]"))
            elif inner.startswith("$"):
                sym = inner[1:].split("-")[0]
                tokens.append(("lit", sym))
            else:
                tokens.append(("bracket", inner))
            i = j + 1
            continue
        if ch in "Ee" and i + 1 < len(text) and text[i + 1] in "+-":
            tokens.append(("exp", text[i:i + 2]))
            i += 2
            continue
        m = _DATE_TOKEN.match(text, i)
        if m and ch.lower() in "ymdhsae":
            tokens.append(("date", m.group(0)))
            i = m.end()
            continue
        if ch in "0#?":
            tokens.append(("digit", ch))
            i += 1
            continue
        if ch == "." :
            tokens.append(("point", "."))
            i += 1
            continue
        if ch == ",":
            tokens.append(("comma", ","))
            i += 1
            continue
        if ch == "%":
            tokens.append(("percent", "%"))
            i += 1
            continue
        if ch in "Ee" and i + 1 < len(text) and text[i + 1] in "+-":
            tokens.append(("exp", text[i:i + 2]))
            i += 2
            continue
        if ch == "/":
            tokens.append(("slash", "/"))
            i += 1
            continue
        if ch == "@":
            tokens.append(("at", "@"))
            i += 1
            continue
        if ch.isdigit():
            tokens.append(("lit", ch))       # 1-9 in a fraction's denominator, else literal
            i += 1
            continue
        tokens.append(("lit", ch))
        i += 1
    return tokens


@lru_cache(maxsize=512)
def _parse(code: str) -> list:
    sections = []
    for raw in _sections(code):
        tokens = _tokenize(raw)
        color = None
        condition = None
        rest = []
        for kind, t in tokens:
            if kind == "bracket":
                low = t.lower()
                if low in COLORS:
                    color = COLORS[low]
                    continue
                m = re.fullmatch(r"color\s*([0-9]+)", low)
                if m:
                    n = int(m.group(1))
                    if 1 <= n <= 56:
                        color = "#" + _PALETTE[n - 1]
                    continue
                m = re.fullmatch(r"(<=|>=|<>|=|<|>)\s*(-?[0-9.]+)", t)
                if m:
                    condition = (m.group(1), float(m.group(2)))
                    continue
                continue                # locale codes and the like
            rest.append((kind, t))
        kinds = {k for k, _ in rest}
        if any(k == "date" for k in kinds):
            # m after h or before s is minutes
            fixed = []
            for idx, (k, t) in enumerate(rest):
                if k == "date" and t.lower() in ("m", "mm"):
                    prev = next((x for x in reversed(fixed) if x[0] == "date"), None)
                    nxt = next((x for x in rest[idx + 1:] if x[0] == "date"), None)
                    if (prev and prev[1].lower().startswith(("h", "[h"))) or \
                            (nxt and nxt[1].lower().startswith(("s", "[s"))):
                        t = "M" if t.lower() == "m" else "MM"     # minutes
                fixed.append((k, t))
            rest = fixed
            kind = "date"
        elif "at" in kinds and "digit" not in kinds:
            kind = "text"
        elif "digit" in kinds:
            kind = "number"
        elif raw.strip().lower() == "general" or raw == "":
            kind = "general"
        else:
            kind = "literal"
        if kind == "number" or kind == "literal":
            # General inside a section ("General;-General")
            pass
        if raw.lower().find("general") >= 0 and kind != "date":
            kind = "general"
        percent = sum(1 for k, _ in rest if k == "percent")
        # commas right after the last digit (before the point or the end) scale by 1000
        scale = 0
        last_digit = max((i for i, (k, _) in enumerate(rest) if k == "digit"), default=-1)
        j = last_digit + 1
        while j < len(rest) and rest[j][0] == "comma":
            scale += 1
            j += 1
        elapsed = any(k == "date" and t.startswith("[") for k, t in rest)
        sections.append(_Section(rest, color, condition, kind, percent, scale, elapsed))
    return sections


def _pick(sections: list, x: float):
    """The section for x, and whether the minus sign is the format's job."""
    conditional = [s for s in sections if s.condition]
    if conditional:
        for s in sections[:2]:
            if s.condition and _holds(s.condition, x):
                return s, False
        # the section after the conditions, for what they leave
        others = [s for s in sections if not s.condition and s.kind != "text"]
        if others:
            return others[0], True
        return sections[-1], True
    numeric = [s for s in sections if s.kind != "text"] or sections
    if len(numeric) == 1 or x > 0 or (x == 0 and len(numeric) < 3):
        return numeric[0], True
    if x < 0:
        return numeric[1], False
    return numeric[2], True


def _holds(cond, x) -> bool:
    op, v = cond
    return {"<": x < v, ">": x > v, "=": x == v, "<=": x <= v, ">=": x >= v, "<>": x != v}[op]


# -- numbers ---------------------------------------------------------------------------------
def _round_half_up(x: float, places: int) -> str:
    d = Decimal(repr(abs(x)))
    q = Decimal(1).scaleb(-places)
    return format(d.quantize(q, rounding=ROUND_HALF_UP), "f")


def _number(section: _Section, x: float, own_sign: bool) -> str:
    tokens = section.tokens
    x = x * (100 ** section.percent) / (1000 ** section.scale)
    if any(k == "slash" for k, _ in tokens):
        return _fraction(section, x, own_sign)
    exp_at = next((i for i, (k, _) in enumerate(tokens) if k == "exp"), None)
    mant_tokens = tokens if exp_at is None else tokens[:exp_at]
    point_at = next((i for i, (k, _) in enumerate(mant_tokens) if k == "point"), None)
    int_tokens = mant_tokens if point_at is None else mant_tokens[:point_at]
    frac_tokens = [] if point_at is None else mant_tokens[point_at + 1:]
    int_digits = [t for k, t in int_tokens if k == "digit"]
    frac_digits = [t for k, t in frac_tokens if k == "digit"]
    grouping = any(k == "comma" for k, _ in int_tokens[:max((i for i, (k, _) in enumerate(int_tokens)
                                                             if k == "digit"), default=-1)])
    negative = x < 0
    x = abs(x)
    exponent_text = ""
    if exp_at is not None:
        exp_tokens = tokens[exp_at + 1:]
        exp_digits = [t for k, t in exp_tokens if k == "digit"]
        sign_mode = tokens[exp_at][1][1]
        if x == 0:
            e = 0
        else:
            step = max(len(int_digits), 1) if len(int_digits) > 1 else 1
            e = math.floor(math.log10(x))
            if len(int_digits) > 1:
                e = (e // step) * step   # engineering: ##0.0E+0
            elif len(int_digits) == 1:
                e = e
        x = x / (10 ** e) if x else 0.0
        # rounding can make 9.99 into 10.0
        text = _round_half_up(x, len(frac_digits))
        if float(text) >= 10 ** max(len(int_digits), 1) and len(int_digits) <= 1:
            e += 1
            x /= 10
        es = str(abs(e)).rjust(max(len([d for d in exp_digits if d == "0"]), 1), "0")
        exponent_text = tokens[exp_at][1][0] + ("-" if e < 0 else ("+" if sign_mode == "+" else "")) + es
        trailing = "".join(t for k, t in exp_tokens if k == "lit")
        exponent_text += trailing
    places = len(frac_digits)
    text = _round_half_up(x, places)
    whole, _, frac = text.partition(".")
    if whole == "0" and all(d == "#" for d in int_digits) and int_digits:
        whole = ""
    if grouping and whole:
        whole = f"{int(whole):,}"
    min_int = sum(1 for d in int_digits if d == "0")
    if len(whole.replace(",", "")) < min_int:
        pad = min_int - len(whole.replace(",", ""))
        whole = "0" * pad + whole
        if grouping:
            whole = f"{int(whole):,}".rjust(len(whole), "0") if whole else whole
    q_int = sum(1 for d in int_digits if d == "?")
    if q_int and len(whole) < len(int_digits):
        whole = " " * (len(int_digits) - len(whole)) + whole
    # fraction digits: 0 keeps zeros, # drops trailing zeros, ? pads with spaces
    frac_chars = list(frac)
    for i in range(len(frac_digits) - 1, -1, -1):
        if frac_chars[i] == "0" and frac_digits[i] in "#?":
            frac_chars[i] = " " if frac_digits[i] == "?" else ""
        else:
            break
    frac = "".join(frac_chars)
    if negative and float(text or 0) == 0:
        negative = False
    # put the digits into the format's literals
    out = []
    int_placed = False
    for k, t in int_tokens:
        if k == "digit":
            if not int_placed:
                out.append(whole)
                int_placed = True
        elif k in ("lit",):
            out.append(t)
        elif k == "percent":
            out.append("%")
    if point_at is not None:
        out.append(".")
        frac_placed = False
        for k, t in frac_tokens:
            if k == "digit":
                if not frac_placed:
                    out.append(frac)
                    frac_placed = True
            elif k == "lit":
                out.append(t)
            elif k == "percent":
                out.append("%")
    out.append(exponent_text)
    body = "".join(out)
    if point_at is not None and body.endswith(".") and not frac_digits:
        pass
    if negative and own_sign:
        body = "-" + body
    return body


def _fraction(section: _Section, x: float, own_sign: bool) -> str:
    tokens = section.tokens
    slash = next(i for i, (k, _) in enumerate(tokens) if k == "slash")
    den_tokens = tokens[slash + 1:]
    den_text = "".join(t for k, t in den_tokens if k in ("digit", "lit") and (k == "digit" or t.isdigit()))
    before = tokens[:slash]
    # "# ?/?": a whole part, then the numerator's digits
    digit_runs = []
    run = []
    for k, t in before:
        if k == "digit":
            run.append(t)
        elif run:
            digit_runs.append(run)
            run = []
    if run:
        digit_runs.append(run)
    has_whole = len(digit_runs) >= 2
    negative = x < 0
    x = abs(x)
    from fractions import Fraction

    if den_text.isdigit():
        den = int(den_text)
        num = round(x * den)
        frac = Fraction(num, den) if False else None
        whole = int(num // den) if has_whole else 0
        n = num - whole * den if has_whole else num
        d = den
    else:
        limit = 10 ** len(den_text) - 1 if den_text else 9
        whole = int(x) if has_whole else 0
        f = Fraction(x - whole).limit_denominator(max(limit, 1))
        n, d = f.numerator, f.denominator
        if n == d:
            whole, n = whole + 1, 0
    sign = "-" if negative and own_sign and (whole or n) else ""
    if has_whole:
        if n == 0:
            return sign + str(whole) + " " * (len(den_text) * 2 + 2 if False else 0)
        return sign + (str(whole) + " " if whole else "") + f"{n}/{d}"
    if n == 0:
        return sign + "0"
    return sign + f"{n}/{d}"


# -- dates -------------------------------------------------------------------------------------
def _date(section: _Section, x: float) -> str:
    if x < 0 and not section.elapsed:
        return "#" * 8
    try:
        t = datetime_from_serial(x)
    except (ValueError, OverflowError):
        return "#" * 8
    leap_bug = int(x) == 60
    tokens = section.tokens
    has_ampm = any(k == "date" and t2.lower() in ("am/pm", "a/p") for k, t2 in tokens)
    fraction_places = 0
    # s.000: fractions of a second
    for i, (k, t2) in enumerate(tokens):
        if k == "date" and t2.lower() in ("s", "ss") and i + 1 < len(tokens) and tokens[i + 1][0] == "point":
            j = i + 2
            while j < len(tokens) and tokens[j] == ("digit", "0"):
                fraction_places += 1
                j += 1
    total_seconds = x * 86400
    if fraction_places == 0:
        rounded = round(total_seconds)
        t = datetime_from_serial(rounded / 86400) if abs(rounded - total_seconds) > 1e-9 else t
    out = []
    i = 0
    while i < len(tokens):
        k, tok = tokens[i]
        if k != "date":
            if k == "point" and fraction_places and i > 0:
                sec = total_seconds - math.floor(total_seconds)
                digits = _round_half_up(sec, fraction_places).partition(".")[2]
                out.append("." + digits)
                i += 1 + fraction_places
                continue
            out.append(tok if k != "digit" else tok)
            i += 1
            continue
        low = tok.lower()
        if tok in ("M", "MM"):
            out.append(f"{t.minute:02d}" if tok == "MM" else str(t.minute))
        elif low == "yyyy" or low == "e":
            out.append(str(t.year))
        elif low == "yy":
            out.append(f"{t.year % 100:02d}")
        elif low == "mmmmm":
            out.append(_MONTHS[t.month - 1][0])
        elif low == "mmmm":
            out.append(_MONTHS[t.month - 1] if not leap_bug else "February")
        elif low == "mmm":
            out.append(_MONTHS[t.month - 1][:3] if not leap_bug else "Feb")
        elif low == "mm":
            out.append(f"{t.month:02d}" if not leap_bug else "02")
        elif low == "m":
            out.append(str(t.month) if not leap_bug else "2")
        elif low == "dddd":
            out.append(_DAYS[t.weekday()])
        elif low == "ddd":
            out.append(_DAYS[t.weekday()][:3])
        elif low == "dd":
            out.append(f"{t.day:02d}" if not leap_bug else "29")
        elif low == "d":
            out.append(str(t.day) if not leap_bug else "29")
        elif low in ("hh", "h"):
            h = t.hour
            if has_ampm:
                h = h % 12 or 12
            out.append(f"{h:02d}" if low == "hh" else str(h))
        elif low in ("ss", "s"):
            out.append(f"{t.second:02d}" if low == "ss" else str(t.second))
        elif low == "am/pm":
            pm = t.hour >= 12
            out.append(("PM" if pm else "AM") if tok[0].isupper() else ("pm" if pm else "am"))
        elif low == "a/p":
            pm = t.hour >= 12
            out.append(("P" if pm else "A") if tok[0].isupper() else ("p" if pm else "a"))
        elif low.startswith("[h"):
            out.append(str(int(total_seconds // 3600)).rjust(len(low) - 2, "0"))
        elif low.startswith("[m"):
            out.append(str(int(total_seconds // 60)).rjust(len(low) - 2, "0"))
        elif low.startswith("[s"):
            out.append(str(int(round(total_seconds))).rjust(len(low) - 2, "0"))
        i += 1
    return "".join(out)


def _general(x: float, width: int = 11) -> str:
    """General: as many digits as fit in an ordinary column (11 characters)."""
    if x == 0:
        return "0"
    text = general_number(x)
    if len(text) <= width:
        return text
    ax = abs(x)
    if 1e-4 <= ax < 1e11:
        whole = len(str(int(ax)))
        places = max(width - whole - 1 - (1 if x < 0 else 0), 0)
        s = _round_half_up(ax, places)
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return ("-" if x < 0 else "") + s
    # scientific with as many digits as fit: 1.23457E+11
    mant_places = max(width - 6 - (1 if x < 0 else 0), 0)
    s = f"{x:.{mant_places}E}"
    mant, _, exp = s.partition("E")
    if "." in mant:
        mant = mant.rstrip("0").rstrip(".")
    sign = exp[0]
    return f"{mant}E{sign}{exp[1:].lstrip('0').rjust(2, '0')}"


def format_number(x: float, code: Optional[str]) -> Shown:
    if not code or code.lower() == "general":
        return Shown(_general(x), None, True)
    if not math.isfinite(x):
        return Shown("#NUM!", None, True)
    sections = _parse(code)
    section, own_sign = _pick(sections, x)
    if section.kind == "general":
        body = _general(abs(x) if not own_sign else x)
        prefix = "".join(t for k, t in section.tokens if k == "lit" and False)
        lits_before = []
        lits_after = []
        return Shown(body, section.color, True)
    if section.kind == "date":
        return Shown(_date(section, x), section.color, True)
    if section.kind == "text":
        return Shown(general_number(x), section.color, True)
    if section.kind == "literal":
        return Shown("".join(t for k, t in section.tokens if k == "lit"), section.color, True)
    return Shown(_number(section, x, own_sign), section.color, True)


def format_text(t: str, code: Optional[str]) -> Shown:
    if not code or code.lower() == "general":
        return Shown(t)
    sections = _parse(code)
    text_section = next((s for s in sections if s.kind == "text"), None)
    if text_section is None:
        if len(sections) >= 4:
            text_section = sections[3]
        else:
            return Shown(t)
    out = []
    for k, tok in text_section.tokens:
        out.append(t if k == "at" else tok if k == "lit" else "")
    return Shown("".join(out), text_section.color)


def format_value(value, code: Optional[str] = None, unit: Optional[str] = None) -> Shown:
    """How a cell shows its value with this number format (and unit)."""
    if value is BLANK:
        return Shown("")
    if isinstance(value, Array):
        value = value.get(0, 0) if value.height and value.width else BLANK
        return format_value(value, code, unit)
    if isinstance(value, bool):
        return Shown("TRUE" if value else "FALSE")
    if isinstance(value, ErrorValue):
        return Shown(value.code)
    if isinstance(value, str):
        return format_text(value, code)
    if isinstance(value, Qty):
        shown_unit = unit or value.unit or default_unit(value.dims)
        x = value.si
        if shown_unit:
            try:
                factor, dims, offset = unit_parts(shown_unit)
                if tuple(dims) != tuple(value.dims):
                    shown_unit = value.unit or default_unit(value.dims)
                    factor, dims, offset = unit_parts(shown_unit) if shown_unit else (1.0, None, 0.0)
                x = (value.si - offset) / factor
            except Exception:
                shown_unit = default_unit(value.dims)
                factor, _d, offset = unit_parts(shown_unit) if shown_unit else (1.0, None, 0.0)
                x = (value.si - offset) / factor
        got = format_number(x, code)
        if shown_unit:
            # kN*m is written kN·m, as CalcForge's equations write it
            got.text = f"{got.text} {shown_unit.replace('*', '·')}"
        return got
    if isinstance(value, (int, float)):
        if unit and code is None:
            pass
        return format_number(float(value), code)
    return Shown(str(value))


def is_date_format(code: Optional[str]) -> bool:
    if not code:
        return False
    return any(s.kind == "date" for s in _parse(code))
