"""Turn evaluated values into display structures (and plain text).

A result is shown as ``number unit``: the number formatted with the worksheet
settings (``1.2346·10^5``), the unit either the one the user typed into the
placeholder, SMath's derived unit for the dimension (N, J, Pa...), or base
units written as a fraction (``kg·m`` over ``s²``).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .numformat import FormattedNumber, NumberFormat, format_real
from .units import Quantity, base_unit_parts, derived_unit_for, derived_with_base
from .values import Matrix, String


@dataclass
class DNum:
    num: FormattedNumber


@dataclass
class DComplex:
    re: Optional[FormattedNumber]
    im: FormattedNumber  # coefficient of i (sign in .negative)


@dataclass
class DUnit:
    """Unit as numerator/denominator lists of (name, power)."""

    num: list
    den: list


@dataclass
class DQuantity:
    value: object  # DNum | DComplex
    unit: Optional[DUnit] = None


@dataclass
class DMatrix:
    nrows: int
    ncols: int
    cells: list


@dataclass
class DString:
    text: str


def _unit_for(dims: tuple) -> Optional[DUnit]:
    if all(d == 0 for d in dims):
        return None
    d = derived_unit_for(dims)
    if d:
        return DUnit([(d, 1)], [])
    # only when base units would need a squared (or worse) denominator:
    # kg/s² -> m Pa, but m/s, kg/m and m² stay in base units (observed)
    mixed = derived_with_base(dims) if any(d <= -2 for d in dims) else None
    if mixed:
        return DUnit([(mixed[0], 1), (mixed[1], 1)], [])
    num, den = base_unit_parts(dims)
    return DUnit(num, den)


def display_quantity(q: Quantity, fmt: NumberFormat, scale: float = 1.0,
                     show_unit: bool = True) -> DQuantity:
    v = q.value / scale if scale != 1.0 else q.value
    if isinstance(v, complex) and v.imag != 0:
        re = format_real(v.real, fmt) if _visible(v.real, fmt) else None
        im = format_real(v.imag, fmt)
        body = DComplex(re, im)
    else:
        body = DNum(format_real(v.real if isinstance(v, complex) else v, fmt))
    unit = _unit_for(q.dims) if show_unit else None
    return DQuantity(body, unit)


def _visible(x: float, fmt: NumberFormat) -> bool:
    f = format_real(x, fmt)
    return not (f.mantissa == "0" and f.exponent is None)


def display_value(v, fmt: NumberFormat, scale: float = 1.0, show_unit: bool = True):
    if isinstance(v, Quantity):
        return display_quantity(v, fmt, scale, show_unit)
    if isinstance(v, Matrix):
        return DMatrix(v.nrows, v.ncols, [display_value(x, fmt, scale, show_unit) for x in v.items])
    if isinstance(v, String):
        return DString(v.text)
    return DString(str(v))


def unit_text(u: Optional[DUnit]) -> str:
    if u is None:
        return ""

    def part(xs):
        return " ".join(n + (f"^{p:g}" if p != 1 else "") for n, p in xs)

    if u.den:
        return f"{part(u.num) or '1'}/{part(u.den)}"
    return part(u.num)


def display_text(d) -> str:
    if isinstance(d, DQuantity):
        if isinstance(d.value, DNum):
            s = d.value.num.plain()
        else:
            re = d.value.re.plain() if d.value.re else ""
            im = d.value.im
            coeff = im.mantissa + (f"·10^{im.exponent}" if im.exponent is not None else "")
            coeff = "" if coeff == "1" else coeff + "·"
            sign = "-" if im.negative else ("+" if re else "")
            s = f"{re}{sign}{coeff}i"
        u = unit_text(d.unit)
        return f"{s} {u}" if u else s
    if isinstance(d, DMatrix):
        rows = []
        for i in range(d.nrows):
            rows.append(" ".join(display_text(c) for c in d.cells[i * d.ncols:(i + 1) * d.ncols]))
        return "[" + "; ".join(rows) + "]"
    if isinstance(d, DString):
        return f'"{d.text}"'
    return str(d)


def value_to_text(v, fmt: Optional[NumberFormat] = None) -> str:
    return display_text(display_value(v, fmt or NumberFormat()))
