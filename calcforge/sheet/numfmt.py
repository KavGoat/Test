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
from typing import Callable, Optional

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
    # the unit at the end of text ("kN·m" of "35 kN·m"), drawn as an
    # equation draws it (unit_runs); None when the value has no unit
    unit: Optional[str] = None


# -- a unit drawn as the equations draw it ------------------------------------------------
_RUN_TOKEN = re.compile(
    r"(\^\s*\(?\s*[-−]?\s*[0-9.]+\s*\)?|[⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+)"     # a power: ^2, ^-1, ^(-1), ²
    r"|([A-Za-zµμΩ°%'_](?:(?![⁰¹²³⁴⁵⁶⁷⁸⁹])[\wµμΩ°%'])*)"     # a unit's name
    r"|([*·⋅])|([/()])|(\s+)|(.)")
_FROM_SUPERSCRIPT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789−")


def unit_runs(unit: str) -> list:
    """A unit as the equations draw it: [(text, raised)], the powers raised
    and the products joined by a dot — "kN*m^2" is [("kN·m", False),
    ("2", True)], "m^-1" is [("m", False), ("−1", True)]. Display only:
    what is stored, copied and written to Excel stays as typed (the user,
    2026-10-15)."""
    if BOX_GAP in unit:
        # the units SMath fills in, a gap, then the unit typed in the box
        filled, _gap, typed = unit.partition(BOX_GAP)
        out = unit_runs(filled)
        for text, raised in [(" ", False)] + unit_runs(typed):
            if out and out[-1][1] == raised:
                out[-1] = (out[-1][0] + text, raised)
            else:
                out.append((text, raised))
        return out
    out: list = []

    def put(text, raised):
        if out and out[-1][1] == raised:
            out[-1] = (out[-1][0] + text, raised)
        else:
            out.append((text, raised))

    last = None                     # kind of the token before: "name", "power", ")"
    for m in _RUN_TOKEN.finditer(unit.strip()):
        power, name, times, other, space, rest = m.groups()
        if power is not None:
            p = power.translate(_FROM_SUPERSCRIPT).lstrip("^")
            p = re.sub(r"[\s()]", "", p).replace("-", "−")
            put(p, True)
            last = "power"
        elif name is not None:
            if last in ("name", "power", ")") and m.start() and unit.strip()[m.start() - 1].isspace():
                put("·", False)     # "kg m" is a product: kg·m
            put(name.replace("'", ""), False)
            last = "name"
        elif times is not None:
            put("·", False)
            last = None
        elif other is not None:
            put(other, False)
            last = ")" if other == ")" else None
        elif space is not None:
            continue
        else:
            put(rest, False)
            last = None
    return out


def unit_display(unit: str) -> str:
    """A unit as plain text the way it is drawn, with superscript digits
    (kN/m², m⁻¹): for messages that name a unit."""
    sup = str.maketrans("0123456789−-.", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁻·")
    return "".join(t.translate(sup) if raised else t for t, raised in unit_runs(unit))


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
        if text[i:i + 7].lower() == "general":
            tokens.append(("general", "General"))    # not G, e (a year), n, e, r, a, l
            i += 7
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
        if "general" in kinds:
            kind = "general"                 # General, with any text round it: General" kN"
        elif any(k == "date" for k in kinds):
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
    if whole == "0" and int_digits and all(d in "#?" for d in int_digits):
        whole = ""                      # no 0 placeholder: no zero ("??" pads it with spaces)
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
    # "?" pads: the numerator right-aligned, the denominator left-aligned, in
    # spaces to the width of their placeholders ("# ??/??" -> "2  1/3 ")
    num_width = len(digit_runs[-1]) if digit_runs and any(t == "?" for t in digit_runs[-1]) else 0
    den_width = len(den_text) if not den_text.isdigit() and "?" in "".join(
        t for k, t in den_tokens if k == "digit") else 0
    if has_whole:
        if n == 0:
            return sign + str(whole) + " " * (num_width + den_width + 1 + 1 if num_width else 0)
        return sign + (str(whole) + " " if whole else "") + f"{str(n).rjust(num_width)}/{str(d).ljust(den_width)}"
    if n == 0:
        return sign + "0"
    return sign + f"{str(n).rjust(num_width)}/{str(d).ljust(den_width)}"


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
    # elapsed time counts whole seconds too: 59.99996 s is [mm]:ss 01:00
    elapsed_seconds = total_seconds if fraction_places else round(total_seconds)
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
            out.append(str(int(elapsed_seconds // 3600)).rjust(len(low) - 2, "0"))
        elif low.startswith("[m"):
            out.append(str(int(elapsed_seconds // 60)).rjust(len(low) - 2, "0"))
        elif low.startswith("[s"):
            out.append(str(int(round(elapsed_seconds))).rjust(len(low) - 2, "0"))
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


def _significant(text: str) -> int:
    """How many significant digits a number's text shows."""
    mantissa = text.split("E")[0]
    digits = mantissa.replace("-", "").replace(".", "").lstrip("0")
    return len(digits)


def general_fit(x: float, fits: Callable[[str], bool]) -> str:
    """Excel's General format in a column of a given width (QA, 2026-10-15):
    the number as it is when it fits; else rounded to as many decimals as
    fit (0.333333, 666666.7); in scientific form when that keeps more
    digits or the whole part won't fit (5E+09, 1.23E-07). *fits(text)* says
    whether a text fits, measured with the cell's own font. When nothing
    fits the text returned doesn't fit either, and the cell shows ####."""
    full = _general(x)
    if fits(full) or x == 0 or not math.isfinite(x):
        return full
    sign = "-" if x < 0 else ""
    ax = abs(x)
    decimal = None
    if ax < 1e11:
        whole = sign + str(int(ax))
        if fits(whole) or fits(sign + _round_half_up(ax, 0)):
            for places in range(10, -1, -1):
                s = _round_half_up(ax, places)
                if "." in s:
                    s = s.rstrip("0").rstrip(".")
                if s.strip("0.") == "":
                    break                   # rounded away to nothing
                if fits(sign + s):
                    decimal = sign + s
                    break
    scientific = None
    for places in range(9, -1, -1):
        mantissa, _, exponent = f"{x:.{places}E}".partition("E")
        if "." in mantissa:
            mantissa = mantissa.rstrip("0").rstrip(".")
        text = f"{mantissa}E{exponent[0]}{exponent[1:].lstrip('0').rjust(2, '0')}"
        if fits(text):
            scientific = text
            break
    if decimal is not None and (scientific is None or
                                _significant(decimal) >= _significant(scientific)):
        return decimal
    return scientific if scientific is not None else full


def with_decimals(code: str, step: int):
    """The format with one decimal place more or fewer: 0.00 -> 0.000 / 0.0,
    #,##0 -> #,##0.0, 0.0% -> 0.00%, in every section."""
    out = []
    for sec in code.split(";"):
        out.append(section_decimals(sec, step))
    new = ";".join(out)
    return new if new != code else None


def section_decimals(sec: str, step: int) -> str:
    # where the number's digits are, outside quoted text and [colours]
    plain = []
    quoted = bracket = False
    for i, ch in enumerate(sec):
        if ch == '"':
            quoted = not quoted
        elif ch == "[" and not quoted:
            bracket = True
        elif ch == "]" and not quoted:
            bracket = False
        elif not quoted and not bracket:
            plain.append(i)
    digits = [i for i in plain if sec[i] in "0#?"]
    if not digits:
        return sec
    exp = next((i for i in plain if sec[i] in "Ee" and i + 1 < len(sec) and sec[i + 1] in "+-"), None)
    mantissa = [i for i in digits if exp is None or i < exp]
    point = next((i for i in plain if sec[i] == "." and (exp is None or i < exp)), None)
    if point is not None:
        after = [i for i in mantissa if i > point]
        places = len(after)
        if step > 0:
            insert_at = (after[-1] + 1) if after else point + 1
            return sec[:insert_at] + "0" + sec[insert_at:]
        if places == 0:
            return sec
        if places == 1:
            return sec[:point] + sec[after[-1] + 1:]
        return sec[:after[-1]] + sec[after[-1] + 1:]
    if step < 0:
        return sec
    last = mantissa[-1]
    return sec[:last + 1] + ".0" + sec[last + 1:]

# -- decimal places and significant figures (the Decimal Places entries) --------

def _fixed_section(section) -> bool:
    """A section of plain digits (0.00, #,##0.0, 0.0%, 0.00E+00), not a
    fraction, a date, text or General."""
    return section.kind == "number" and not any(k == "slash" for k, _t in section.tokens)


def _section_places(section) -> int:
    """How many digits a section shows after the point (before any E+00)."""
    count = seen_point = 0
    for kind, _t in section.tokens:
        if kind == "exp":
            break
        if kind == "point":
            seen_point = 1
        elif kind == "digit" and seen_point:
            count += 1
    return count


def places_of(code: Optional[str]) -> Optional[int]:
    """The decimal places a number format shows (its first section's), or
    None when it does not fix them (General, a date, a fraction, text)."""
    if not code or code.lower() == "general":
        return None
    sections = _parse(code)
    if not sections or not _fixed_section(sections[0]):
        return None
    return _section_places(sections[0])


def with_places(code: Optional[str], places: int) -> str:
    """*code* showing *places* decimal places, as Excel's Increase and
    Decrease Decimal would get it there, its kind kept (#,##0.00,
    0.0%, 0.00E+00, currency, colours); General, a date, a fraction or text
    becomes plain 0.00 (Excel's Number)."""
    places = max(0, min(int(places), 30))
    plain = "0" + ("." + "0" * places if places else "")
    if places_of(code) is None:
        return plain
    out = []
    for raw, section in zip(code.split(";"), _parse(code)):
        if _fixed_section(section):
            have = _section_places(section)
            while have != places:
                step = 1 if have < places else -1
                changed = section_decimals(raw, step)
                if changed == raw:
                    break
                raw, have = changed, have + step
        out.append(raw)
    return ";".join(out)


def _to_significant(x: float, code: str):
    """SMath's significant figures for a cell (the user, 2026-10-19): the
    format's decimal places count significant figures instead — 0.000 shows
    three, 12345 as 12300 and 0.0012345 as 0.00123 — the format's kind
    (thousands, percent, colours, text) kept. (value, code) to show."""
    sections = _parse(code)
    section, _own = _pick(sections, x)
    if not _fixed_section(section) or any(k == "exp" for k, _t in section.tokens) \
            or x == 0 or not math.isfinite(x):
        return x, code
    figures = max(_section_places(section), 1)
    factor = (100 ** section.percent) / (1000 ** section.scale)
    shown = Decimal(repr(abs(x * factor)))
    exponent = shown.adjusted()
    rounded = shown.quantize(Decimal(1).scaleb(exponent - figures + 1), rounding=ROUND_HALF_UP)
    if rounded.adjusted() != exponent:              # 9.99 -> 10.0: one decade up
        exponent = rounded.adjusted()
        rounded = shown.quantize(Decimal(1).scaleb(exponent - figures + 1),
                                 rounding=ROUND_HALF_UP)
    value = math.copysign(float(rounded) / factor, x)
    index = sections.index(section)
    raws = code.split(";")
    if index < len(raws):
        raws[index] = with_places(raws[index], max(figures - 1 - exponent, 0)) \
            if places_of(raws[index]) is not None else raws[index]
    return value, ";".join(raws)


def format_number(x: float, code: Optional[str],
                  fit: Optional[Callable[[str], bool]] = None,
                  significant: bool = False) -> Shown:
    if not code or code.lower() == "general":
        return Shown(general_fit(x, fit) if fit is not None else _general(x), None, True)
    if not math.isfinite(x):
        return Shown("#NUM!", None, True)
    if significant:
        x, code = _to_significant(x, code)
    sections = _parse(code)
    section, own_sign = _pick(sections, x)
    if section.kind == "general":
        body = _general(abs(x) if not own_sign else x)
        if not any(k == "general" for k, _t in section.tokens):
            return Shown(body, section.color, True)
        # text written round General: General" kN", "F = "General
        text = "".join(body if k == "general" else t for k, t in section.tokens
                       if k in ("general", "lit"))
        return Shown(text, section.color, True)
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


def format_value(value, code: Optional[str] = None, unit: Optional[str] = None,
                 fit: Optional[Callable[[str], bool]] = None,
                 significant: bool = False) -> Shown:
    """How a cell shows its value with this number format (and unit). With
    *fit* — whether a text fits the cell — a number in General is shortened
    to fit, as Excel does (see general_fit); its unit is kept whole. With
    *significant*, the format's decimal places count significant figures
    (SMath's, for a cell; Style.significant)."""
    if value is BLANK:
        return Shown("")
    if isinstance(value, Array):
        value = value.get(0, 0) if value.height and value.width else BLANK
        return format_value(value, code, unit, fit, significant)
    if isinstance(value, bool):
        return Shown("TRUE" if value else "FALSE")
    if isinstance(value, ErrorValue):
        return Shown(value.code)
    if isinstance(value, str):
        return format_text(value, code)
    if isinstance(value, Qty):
        filled = unit and in_unit_box(value, unit)
        if filled:
            x, shown_unit = filled
        else:
            shown_unit = unit or value.unit or default_unit(value.dims)
            x = value.si
        if shown_unit and not filled:
            try:
                factor, dims, offset = unit_parts(shown_unit)
                if tuple(dims) != tuple(value.dims):
                    shown_unit = value.unit or default_unit(value.dims)
                    factor, dims, offset = unit_parts(shown_unit) if shown_unit else (1.0, None, 0.0)
                x = (value.si - offset) / factor
            except Exception:
                # no unit (frobs): as typed, as when none is given
                shown_unit = default_unit(value.dims)
                if value.unit and value.unit != unit:
                    try:
                        unit_parts(value.unit)
                        shown_unit = value.unit
                    except Exception:
                        pass
                factor, _d, offset = unit_parts(shown_unit) if shown_unit else (1.0, None, 0.0)
                x = (value.si - offset) / factor
        # kN*m is written kN·m, as CalcForge's equations write it
        unit = shown_unit.replace('*', '·') if shown_unit else ""
        tail = f" {unit}" if unit else ""
        got = format_number(x, code, None if fit is None else (lambda t: fit(t + tail)),
                            significant)
        if unit:
            got.unit = unit
        got.text += tail
        return got
    if isinstance(value, (int, float)):
        return format_number(float(value), code, fit, significant)
    return Shown(str(value))


# Between the units SMath fills in and the unit typed in a cell's unit box
# (12500 s²/(kg·m) N²): a gap, as SMath draws the box's unit after the
# result's, where a space would be drawn as a product's dot (unit_runs).
BOX_GAP = "\u2009"


def in_unit_box(value: Qty, unit: str) -> Optional[tuple]:
    """A quantity shown in the unit typed in its cell's unit box when that
    unit is of another dimension: as SMath's unit placeholder (the equations'
    own code, calc/engine/display.in_unit_box), the typed unit stays at the
    end and the units still needed go before it, in the unit and prefix an
    equation shows them in, so the number times those units times the typed
    unit is the value — 12.5 kN with N^2 typed is 12500 s²/(kg·m) N².
    (number, unit as shown) or None: of the same dimension (converted as
    any unit), no unit at all, or a temperature with an offset (°C) of
    another dimension, which SMath refuses."""
    from calcforge.calc.engine.display import display_quantity, in_unit_box as box, unit_factor
    from calcforge.calc.engine.numformat import NumberFormat
    from calcforge.calc.engine.units import Quantity
    from .values import _written
    try:
        factor, dims, offset = unit_parts(unit)
    except Exception:
        return None
    if tuple(dims) == tuple(value.dims):
        return None
    shown = box(Quantity(value.si, tuple(value.dims)), factor, dims, offset)
    if shown is None:
        return None
    rest = display_quantity(shown, NumberFormat()).unit
    x = shown.value / unit_factor(rest)
    typed = unit.strip().replace("*", "·")
    return x, (_written(rest) + BOX_GAP + typed) if rest is not None else typed


def is_date_format(code: Optional[str]) -> bool:
    if not code:
        return False
    return any(s.kind == "date" for s in _parse(code))
