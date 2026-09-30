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
from .unitdata import UNITS
from .units import OBSERVED_UNITS, Quantity, base_unit_parts, derived_per_base, derived_unit_for
from .values import Matrix, String


@dataclass
class DNum:
    num: FormattedNumber


@dataclass
class DFrac:
    """A result shown as a fraction (right-click > Fractions > Fraction):
    1/(3+1/4) = 4/13; with mixed numbers 7/3 = 2 1/3."""

    negative: bool
    whole: Optional[int]
    num: int
    den: int


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
class DExpr:
    """Right-click > Optimization > None: the expression is shown as typed
    instead of its value (observed: 2+3 = 2+3)."""

    row: object  # model Row


@dataclass
class DString:
    text: str


def _unit_for(dims: tuple) -> Optional[DUnit]:
    if all(d == 0 for d in dims):
        return None
    d = derived_unit_for(dims)
    if d:
        return DUnit([(d, 1)], [])
    seen = OBSERVED_UNITS.get(tuple(dims))
    if seen:
        return DUnit(list(seen[0]), list(seen[1]))
    # only when base units would need a squared (or worse) denominator:
    # kg/s² -> N/m, but m/s, kg/m, m/s² and m² stay in base units
    per = derived_per_base(dims) if any(d <= -2 for d in dims) else None
    if per:
        return DUnit([(per[0], 1)], per[1])
    num, den = base_unit_parts(dims)
    return DUnit(num, den)


# Units that take an engineering prefix chosen by size (kN, MPa, kN/m...)
_ENG_PREFIX = {
    "N": [("", 1.0), ("k", 1e3), ("M", 1e6), ("G", 1e9)],
    "Pa": [("", 1.0), ("k", 1e3), ("M", 1e6), ("G", 1e9)],
    "J": [("", 1.0), ("k", 1e3), ("M", 1e6), ("G", 1e9)],
    "W": [("", 1.0), ("k", 1e3), ("M", 1e6), ("G", 1e9)],
}


def unit_factor(u: Optional[DUnit]) -> float:
    """Size of a displayed unit in SI base units."""
    if u is None:
        return 1.0
    f = 1.0
    for name, p in u.num:
        f *= UNITS[name][0] ** p
    for name, p in u.den:
        f /= UNITS[name][0] ** p
    return f


def engineering_unit(unit: Optional[DUnit], magnitude: float):
    """(unit, divisor) in the form engineers write: a prefix that keeps the
    number between 1 and 1000 for N, Pa, J, W (12.5 kN, 250 MPa, 5 kN/m,
    20 kPa) and mm², mm³, mm⁴ for small section properties."""
    if unit is None or magnitude == 0:
        return unit, 1.0
    num, den = unit.num, unit.den
    if num == [("J", 1)] and not den:
        # force x length: a moment, written kN·m (energy and moment share
        # the dimension; structural work needs the moment form)
        best = ("", 1.0)
        for pre, f in _ENG_PREFIX["N"]:
            if magnitude / f >= 1 - 1e-12:
                best = (pre, f)
        return DUnit([(best[0] + "N", 1), ("m", 1)], []), best[1]
    if len(num) == 1 and num[0][1] == 1 and num[0][0] in _ENG_PREFIX:
        name = num[0][0]
        best = ("", 1.0)
        for pre, f in _ENG_PREFIX[name]:
            if magnitude / f >= 1 - 1e-12:
                best = (pre, f)
        if best[0]:
            return DUnit([(best[0] + name, 1)], list(den)), best[1]
        return unit, 1.0
    if not den and len(num) == 1 and num[0][0] == "m" and num[0][1] in (2, 3, 4):
        n = num[0][1]
        limit = {2: 1e-2, 3: 1e-3, 4: 1.0}[n]
        if magnitude < limit:
            return DUnit([("mm", n)], []), 1e-3 ** n
    return unit, 1.0


def display_quantity(q: Quantity, fmt: NumberFormat, scale: float = 1.0,
                     show_unit: bool = True) -> DQuantity:
    unit = _unit_for(q.dims) if show_unit else None
    if show_unit and scale == 1.0:
        if getattr(fmt, "engineering", False):
            unit, _ = engineering_unit(unit, abs(q.value))
        # the number shown is always the value in exactly the unit shown:
        # divide by that unit's real factor (kN 1000, R 0.01, ...), never
        # assume a chosen unit is coherent
        scale = unit_factor(unit)
    v = q.value / scale if scale != 1.0 else q.value
    if isinstance(v, complex) and v.imag != 0:
        re = format_real(v.real, fmt) if _visible(v.real, fmt) else None
        im = format_real(v.imag, fmt)
        body = DComplex(re, im)
    else:
        x = v.real if isinstance(v, complex) else v
        body = _as_fraction(x, fmt) or DNum(format_real(x, fmt))
    return DQuantity(body, unit)


def _as_fraction(x: float, fmt: NumberFormat) -> Optional[DFrac]:
    """The fraction to show for x, or None to show it as a decimal.
    "Fraction" writes any value that is (very nearly) rational; "Auto" only
    simple ones (observed: 0.75 -> 3/4)."""
    import math
    from fractions import Fraction

    if fmt.fractions == "decimal" or not math.isfinite(x) or x == int(x):
        return None
    limit = 10 ** 6 if fmt.fractions == "fraction" else 1000
    fr = Fraction(x).limit_denominator(limit)
    if abs(float(fr) - x) > 1e-12 * max(1.0, abs(x)):
        return None
    n, d = abs(fr.numerator), fr.denominator
    whole = None
    if fmt.mixed and n > d:
        whole, n = divmod(n, d)
    return DFrac(fr < 0, whole, n, d)


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
    from .symbolic import Expr, to_row

    if isinstance(v, Expr):
        return DExpr(to_row(v.node))
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
        elif isinstance(d.value, DFrac):
            f = d.value
            s = ("-" if f.negative else "") + (f"{f.whole} " if f.whole else "") + f"{f.num}/{f.den}"
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
    if isinstance(d, DExpr):
        return d.row.text()
    return str(d)


def value_to_text(v, fmt: Optional[NumberFormat] = None) -> str:
    return display_text(display_value(v, fmt or NumberFormat()))
