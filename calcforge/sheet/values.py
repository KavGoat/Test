"""What a cell can hold: numbers (with or without a unit), text, TRUE/FALSE,
Excel's errors, nothing at all, and arrays.

A number without a unit is a plain float, as in Excel. A number with a unit
is a :class:`Qty`, kept in SI base units like every CalcForge quantity, with
the unit it was written in remembered so it is shown that way again
(``5 kN`` stays ``5 kN``, not ``5000 N``). Adding or comparing quantities
whose units don't match is the error ``#UNITS!``.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from calcforge.calc.engine.units import NODIM, UNITS, dims_add, dims_scale, dims_sub


# -- errors --------------------------------------------------------------------
@dataclass(frozen=True)
class ErrorValue:
    code: str

    def __str__(self) -> str:
        return self.code


NULL = ErrorValue("#NULL!")
DIV0 = ErrorValue("#DIV/0!")
VALUE = ErrorValue("#VALUE!")
REF = ErrorValue("#REF!")
NAME = ErrorValue("#NAME?")
NUM = ErrorValue("#NUM!")
NA = ErrorValue("#N/A")
SPILL = ErrorValue("#SPILL!")
CALC = ErrorValue("#CALC!")
UNITS_ERR = ErrorValue("#UNITS!")          # CalcForge's own: units that don't match

ERRORS = {e.code: e for e in (NULL, DIV0, VALUE, REF, NAME, NUM, NA, SPILL, CALC, UNITS_ERR)}
# Excel's ERROR.TYPE numbers
ERROR_NUMBERS = {"#NULL!": 1, "#DIV/0!": 2, "#VALUE!": 3, "#REF!": 4, "#NAME?": 5,
                 "#NUM!": 6, "#N/A": 7, "#SPILL!": 9, "#CALC!": 14, "#UNITS!": 20}


class SheetError(Exception):
    """Raised inside a calculation; the cell then holds ``error``."""

    def __init__(self, error: ErrorValue):
        super().__init__(error.code)
        self.error = error


class _Blank:
    """An empty cell. 0 in sums, "" in text."""

    _one = None

    def __new__(cls):
        if cls._one is None:
            cls._one = super().__new__(cls)
        return cls._one

    def __repr__(self) -> str:
        return "BLANK"

    def __bool__(self) -> bool:
        return False


BLANK = _Blank()


# -- quantities ----------------------------------------------------------------
@dataclass(frozen=True)
class Qty:
    """A number with a unit: ``si`` in SI base units, ``dims`` the
    dimension, ``unit`` how it was written (None: choose one to show)."""

    si: float
    dims: tuple
    unit: Optional[str] = None

    @property
    def dimensionless(self) -> bool:
        return not any(self.dims)

    def shown(self) -> float:
        """The number in the unit it is shown in."""
        unit = self.unit or default_unit(self.dims)
        if not unit:
            return self.si
        factor, _dims, offset = unit_parts(unit)
        return (self.si - offset) / factor


def quantity(si: float, dims: tuple, unit: Optional[str] = None):
    """A float when there is no unit to keep, else a Qty."""
    if not any(dims) and unit is None:
        return float(si)
    return Qty(float(si), tuple(dims), unit)


Number = (float, int, Qty)


@dataclass(frozen=True)
class Array:
    """A block of values (a range read as a whole, or {1,2;3,4})."""

    rows: tuple                         # tuple of tuples

    @property
    def height(self) -> int:
        return len(self.rows)

    @property
    def width(self) -> int:
        return len(self.rows[0]) if self.rows else 0

    def get(self, row: int, col: int):
        return self.rows[row][col]

    def values(self):
        for row in self.rows:
            yield from row

    @staticmethod
    def of(rows) -> "Array":
        return Array(tuple(tuple(r) for r in rows))


# -- units written as text -------------------------------------------------------
_SUPERSCRIPT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")
_UNIT_TOKEN = re.compile(r"\s*(?:(\()|(\))|([*·⋅/])|(\^\s*-?\s*[0-9.]+|[⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+)|([A-Za-zµμΩ°%'][A-Za-z0-9_µμΩ°%']*))")


class UnitTextError(ValueError):
    pass


@lru_cache(maxsize=2048)
def unit_parts(text: str):
    """(factor, dims, offset) of a unit written like "kN", "kN/m^2", "kN·m",
    "kg m/s²", "N/(m s)". Raises UnitTextError if it isn't one."""
    tokens = []
    pos, text = 0, text.strip()
    while pos < len(text):
        m = _UNIT_TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise UnitTextError(text)
        pos = m.end()
        if m.group(1):
            tokens.append(("(", None))
        elif m.group(2):
            tokens.append((")", None))
        elif m.group(3):
            tokens.append(("/" if m.group(3) == "/" else "*", None))
        elif m.group(4):
            power = m.group(4).translate(_SUPERSCRIPT).lstrip("^").replace(" ", "")
            tokens.append(("^", float(power)))
        else:
            name = m.group(5).lstrip("'")
            if name not in UNITS:
                raise UnitTextError(name)
            tokens.append(("u", name))
        if pos < len(text) and text[pos] == " " and tokens[-1][0] in ("u", ")", "^"):
            # a space between two units multiplies them: "kg m"
            rest = text[pos:].lstrip()
            if rest and rest[0] not in "*·⋅/^)⁰¹²³⁴⁵⁶⁷⁸⁹⁻":
                tokens.append(("*", None))
    if not tokens:
        raise UnitTextError(text)
    at = [0]

    def peek():
        return tokens[at[0]][0] if at[0] < len(tokens) else None

    def factor():
        kind, value = tokens[at[0]] if at[0] < len(tokens) else (None, None)
        if kind == "(":
            at[0] += 1
            f, d = product()
            if peek() != ")":
                raise UnitTextError(text)
            at[0] += 1
        elif kind == "u":
            at[0] += 1
            f, d = float(UNITS[value][0]), tuple(UNITS[value][1])
        elif kind is None and False:
            raise UnitTextError(text)
        else:
            raise UnitTextError(text)
        if peek() == "^":
            p = tokens[at[0]][1]
            at[0] += 1
            f, d = f ** p, dims_scale(d, p)
        return f, d

    def product():
        f, d = factor()
        while peek() in ("*", "/"):
            op = tokens[at[0]][0]
            at[0] += 1
            g, e = factor()
            if op == "*":
                f, d = f * g, dims_add(d, e)
            else:
                f, d = f / g, dims_sub(d, e)
        return f, d

    f, d = product()
    if at[0] != len(tokens):
        raise UnitTextError(text)
    offset = 0.0
    if len(tokens) == 1:
        offset = float(UNITS[tokens[0][1]][2])
    return f, tuple(d), offset


def is_unit_text(text: str) -> bool:
    try:
        unit_parts(text)
        return True
    except UnitTextError:
        return False


@lru_cache(maxsize=1024)
def default_unit(dims: tuple) -> str:
    """The unit CalcForge's equations would show for this dimension (N, Pa,
    kg/m...), as text; "" when there is none."""
    if not any(dims):
        return ""
    from calcforge.calc.engine.display import _unit_for, unit_text

    return unit_text(_unit_for(tuple(dims))).replace(" ", "·")


def with_unit(x: float, unit: str):
    """x written in unit: 5, "kN" -> Qty(5000, force, "kN")."""
    factor, dims, offset = unit_parts(unit)
    return Qty(x * factor + offset, dims, unit)


# -- what Excel does with each kind of value ---------------------------------------
def is_number(v) -> bool:
    return isinstance(v, (float, int, Qty)) and not isinstance(v, bool)


def to_number(v):
    """A value in arithmetic: blanks are 0, TRUE is 1, text that reads as a
    number is that number, other text is #VALUE!."""
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (float, Qty)):
        return v
    if isinstance(v, int):
        return float(v)
    if v is BLANK:
        return 0.0
    if isinstance(v, ErrorValue):
        raise SheetError(v)
    if isinstance(v, str):
        from .inputs import number_from_text

        got = number_from_text(v)
        if got is None:
            raise SheetError(VALUE)
        return got
    if isinstance(v, Array):
        return to_number(v.get(0, 0))
    raise SheetError(VALUE)


def to_float(v) -> float:
    """A plain number; a unit is only allowed if it cancels out."""
    n = to_number(v)
    if isinstance(n, Qty):
        if any(n.dims):
            raise SheetError(UNITS_ERR)
        return n.si
    return n


def to_int(v) -> int:
    """Excel truncates toward zero where a whole number is wanted."""
    x = to_float(v)
    if not math.isfinite(x):
        raise SheetError(NUM)
    return int(x)


def to_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (float, int)):
        return v != 0
    if isinstance(v, Qty):
        return v.si != 0
    if v is BLANK:
        return False
    if isinstance(v, ErrorValue):
        raise SheetError(v)
    if isinstance(v, str):
        if v.upper() == "TRUE":
            return True
        if v.upper() == "FALSE":
            return False
        raise SheetError(VALUE)
    if isinstance(v, Array):
        return to_bool(v.get(0, 0))
    raise SheetError(VALUE)


def general_number(x: float) -> str:
    """A number as Excel's General format writes it when it has no room
    limit: up to 15 significant digits, no trailing zeros."""
    if x == 0:
        return "0"
    if not math.isfinite(x):
        return "#NUM!"
    text = f"{x:.15g}"
    if "e" in text:
        mantissa, _, exp = text.partition("e")
        if "." in mantissa:
            mantissa = mantissa.rstrip("0").rstrip(".")
        sign = "-" if exp.startswith("-") else "+"
        text = f"{mantissa}E{sign}{exp.lstrip('+-').zfill(2)}"
    return text


def quantity_text(q: Qty) -> str:
    unit = q.unit or default_unit(q.dims)
    number = general_number(q.shown())
    return f"{number} {unit}" if unit else number


def to_text(v) -> str:
    """A value where text is wanted (& and the text functions)."""
    if isinstance(v, str):
        return v
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (float, int)):
        return general_number(float(v))
    if isinstance(v, Qty):
        return quantity_text(v)
    if v is BLANK:
        return ""
    if isinstance(v, ErrorValue):
        raise SheetError(v)
    if isinstance(v, Array):
        return to_text(v.get(0, 0))
    raise SheetError(VALUE)


# -- arithmetic with units -----------------------------------------------------------
def _dims(n) -> tuple:
    return n.dims if isinstance(n, Qty) else NODIM


def _si(n) -> float:
    return n.si if isinstance(n, Qty) else float(n)


def _keep_unit(a, b, si, dims):
    """The result of + or -: shown in the first operand's unit (5 kN + 200 N
    = 5.2 kN)."""
    unit = a.unit if isinstance(a, Qty) and a.unit else (b.unit if isinstance(b, Qty) else None)
    if unit and unit_parts(unit)[2]:
        unit = None                     # 20 °C + 5 °C is no longer in °C
    return quantity(si, dims, unit if any(dims) or unit in ("%", "deg", "°") else None)


def add(a, b):
    if type(a) is float and type(b) is float:
        return a + b
    if _dims(a) != _dims(b):
        raise SheetError(UNITS_ERR)
    return _keep_unit(a, b, _si(a) + _si(b), _dims(a))


def sub(a, b):
    if type(a) is float and type(b) is float:
        return a - b
    if _dims(a) != _dims(b):
        raise SheetError(UNITS_ERR)
    return _keep_unit(a, b, _si(a) - _si(b), _dims(a))


def _joined(a, b, op: str) -> Optional[str]:
    ua = a.unit if isinstance(a, Qty) else None
    ub = b.unit if isinstance(b, Qty) else None
    if isinstance(a, Qty) and ua is None and any(a.dims):
        return None
    if isinstance(b, Qty) and ub is None and any(b.dims):
        return None
    if ua in ("%",):
        ua = None
    if ub in ("%",):
        ub = None
    if not ua and not ub:
        return None
    if not ub:
        return ua if op == "*" else ua
    if not ua:
        return ub if op == "*" else f"1/{_wrapped(ub)}"
    if ua == ub and op == "*":
        return f"{ua}^2" if re.fullmatch(r"[A-Za-zµμΩ]+", ua) else None
    if ua == ub and op == "/":
        return None
    return f"{ua}·{_wrapped(ub)}" if op == "*" else f"{ua}/{_wrapped(ub)}"


_SIMPLE_PART = re.compile(r"([A-Za-zµμΩ°]+)(?:\^(-?[0-9.]+))?$")


def simplified(unit: str) -> Optional[str]:
    """A unit written as a product of simple units with like ones
    cancelled: "kN/m·m" -> "kN", "kN·m/m^2" -> "kN/m". None when it isn't
    such a product."""
    powers: dict = {}
    order: list = []
    sign = 1
    depth_sign = [1]
    for token in re.findall(r"\(|\)|/|[*·⋅]|[^()/*·⋅\s]+", unit):
        if token == "(":
            depth_sign.append(depth_sign[-1] * sign)
            sign = 1
            continue
        if token == ")":
            if len(depth_sign) == 1:
                return None
            depth_sign.pop()
            sign = 1
            continue
        if token == "/":
            sign = -1
            continue
        if token in "*·⋅":
            sign = 1
            continue
        m = _SIMPLE_PART.match(token)
        if not m or m.group(1) not in UNITS:
            return None
        p = float(m.group(2)) if m.group(2) else 1.0
        name = m.group(1)
        if name not in powers:
            order.append(name)
        powers[name] = powers.get(name, 0.0) + p * sign * depth_sign[-1]
        if token and len(depth_sign) == 1:
            sign = sign if False else sign
    def part(name, p):
        p = abs(p)
        return name if p == 1 else f"{name}^{general_number(p)}"
    num = [part(n, powers[n]) for n in order if powers[n] > 1e-12]
    den = [part(n, powers[n]) for n in order if powers[n] < -1e-12]
    if not num and not den:
        return ""
    if not num:
        return "·".join(f"{n}^{general_number(powers[n])}" for n in order if powers[n] < -1e-12)
    text = "·".join(num)
    if den:
        text += "/" + (den[0] if len(den) == 1 else "(" + "·".join(den) + ")")
    return text


def _wrapped(unit: str) -> str:
    return unit if re.fullmatch(r"[A-Za-zµμΩ°]+(\^-?[0-9.]+)?", unit) else f"({unit})"


def _product(si, dims, unit):
    if unit is not None:
        if unit.startswith("1/"):
            unit = simplified("x/" + unit[2:]) if False else simplified(unit[2:])
            unit = None if unit is None else (unit if not unit else _inverse(unit))
        else:
            simple = simplified(unit)
            if simple is not None:
                unit = simple or None
    if unit is not None:
        try:
            factor, udims, offset = unit_parts(unit)
            if tuple(udims) != tuple(dims) or offset:
                unit = None
        except UnitTextError:
            unit = None
    if not any(dims):
        return float(si)
    return Qty(si, dims, unit)


def _inverse(unit: str) -> Optional[str]:
    """1/unit written with negative powers: kN -> kN^-1, kN/m -> m/kN."""
    if "/" in unit:
        top, _, bottom = unit.partition("/")
        bottom = bottom.strip("()")
        return simplified(f"{bottom}/{top}")
    parts = unit.split("·")
    out = []
    for p in parts:
        m = _SIMPLE_PART.match(p)
        if not m:
            return None
        power = -(float(m.group(2)) if m.group(2) else 1.0)
        out.append(f"{m.group(1)}^{general_number(power)}")
    return "·".join(out)


def mul(a, b):
    if type(a) is float and type(b) is float:
        return a * b
    return _product(_si(a) * _si(b), dims_add(_dims(a), _dims(b)), _joined(a, b, "*"))


def div(a, b):
    if type(a) is float and type(b) is float:
        if b == 0:
            raise SheetError(DIV0)
        return a / b
    if _si(b) == 0:
        raise SheetError(DIV0)
    return _product(_si(a) / _si(b), dims_sub(_dims(a), _dims(b)), _joined(a, b, "/"))


def power(a, b):
    if isinstance(b, Qty) and any(b.dims):
        raise SheetError(UNITS_ERR)
    p = _si(b)
    x = _si(a)
    if x == 0 and p < 0:
        raise SheetError(DIV0)
    if x == 0 and p == 0:
        raise SheetError(NUM)
    try:
        if x < 0 and p != int(p):
            raise SheetError(NUM)
        r = x ** p
    except OverflowError:
        raise SheetError(NUM)
    if isinstance(r, complex) or not math.isfinite(r):
        raise SheetError(NUM)
    if isinstance(a, Qty) and any(a.dims):
        unit = None
        if a.unit and re.fullmatch(r"[A-Za-zµμΩ]+", a.unit):
            unit = f"{a.unit}^{general_number(p)}"
        return _product(r, dims_scale(a.dims, p), unit)
    return float(r)


def neg(a):
    if type(a) is float:
        return -a
    return Qty(-a.si, a.dims, a.unit) if isinstance(a, Qty) else -float(a)


def magnitude(n) -> float:
    """SI value of a number (for comparing and sorting)."""
    return _si(n)


def scaled(n, f: float):
    """n times a plain factor, keeping its unit (ROUND, ABS, AVERAGE...)."""
    if isinstance(n, Qty):
        return Qty(n.si * f, n.dims, n.unit)
    return float(n) * f


def map_shown(n, f):
    """Apply f to the number as it is shown in its unit (ROUND(5.237 kN, 1)
    rounds the kN, not the newtons), keeping the unit."""
    if isinstance(n, Qty):
        unit = n.unit or default_unit(n.dims)
        if not unit:
            return Qty(f(n.si), n.dims, n.unit)
        factor, _dims, offset = unit_parts(unit)
        return Qty(f((n.si - offset) / factor) * factor + offset, n.dims, n.unit)
    return float(f(float(n)))
