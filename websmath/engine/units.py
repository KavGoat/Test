"""Physical quantities: a number (real or complex) with a dimension vector.

SMath keeps every value in SI base units and only chooses a display unit when
a result is shown.  The display unit is the first *derived* unit (N, J, Pa...)
whose dimension matches exactly - taken from the same table SMath uses - and
otherwise a product of base units.
"""
from __future__ import annotations

import cmath
import math
from dataclasses import dataclass

from .unitdata import BASE, DERIVED, INFO, UNITS

NDIM = len(BASE)
NODIM: tuple = tuple([0] * NDIM)


def dims_add(a: tuple, b: tuple) -> tuple:
    return tuple(_clean(x + y) for x, y in zip(a, b))


def dims_sub(a: tuple, b: tuple) -> tuple:
    return tuple(_clean(x - y) for x, y in zip(a, b))


def dims_scale(a: tuple, p: float) -> tuple:
    return tuple(_clean(x * p) for x in a)


def _clean(x: float):
    r = round(x)
    return int(r) if abs(x - r) < 1e-9 else x


def is_unit(name: str) -> bool:
    return name in UNITS


def unit_names() -> list[str]:
    return sorted(UNITS)


def unit_info(name: str):
    return INFO.get(name)


@dataclass(frozen=True)
class Quantity:
    """A scalar value in SI base units."""

    value: complex | float
    dims: tuple = NODIM

    @property
    def dimensionless(self) -> bool:
        return all(d == 0 for d in self.dims)

    @property
    def real(self) -> float:
        v = self.value
        return v.real if isinstance(v, complex) else v

    def with_value(self, v) -> "Quantity":
        return Quantity(_tidy(v), self.dims)


def _tidy(v):
    if isinstance(v, complex):
        if v.imag == 0:
            return v.real
        return v
    return v


def unit_quantity(name: str) -> Quantity:
    factor, dims, _offset = UNITS[name]
    return Quantity(float(factor), tuple(dims))


def unit_offset(name: str) -> float:
    return UNITS[name][2]


# Derived units never chosen automatically for output (2 m³ stays m³).
_NOT_FOR_OUTPUT = {"L"}


def derived_unit_for(dims: tuple) -> str | None:
    """SMath's derived unit whose dimension matches exactly, or None."""
    for name, d in DERIVED:
        if name not in _NOT_FOR_OUTPUT and tuple(d) == tuple(dims):
            return name
    return None


def derived_with_base(dims: tuple):
    """(base unit, derived unit) when dims = base¹ · derived, else None.

    Observed: 2 kN/m (kg/s²) is shown as "2000 m Pa" rather than kg/s² or
    N/m - SMath combines a derived unit with one base unit to the first
    power.  When several fit, the later entry in the derived list wins
    (Pa over T for kg/s²).
    """
    found = None
    for name, d in DERIVED:
        if name in _NOT_FOR_OUTPUT:
            continue
        rest = [a - b for a, b in zip(dims, d)]
        nz = [(i, v) for i, v in enumerate(rest) if v != 0]
        if len(nz) == 1 and nz[0][1] == 1:
            found = (BASE[nz[0][0]], name)
    return found


def base_unit_parts(dims: tuple) -> tuple[list, list]:
    """Split a dimension into numerator/denominator base-unit factors.

    Returns ([(unit, power)...], [(unit, power)...]) with positive powers.
    SMath orders base units as they appear in BASE except that mass comes
    first (kg·m/s²).
    """
    order = ["kg", "m", "s", "A", "K", "mol", "cd", "bit", "sr", "dB", "¤"]
    num, den = [], []
    for u in order:
        p = dims[BASE.index(u)]
        if p > 0:
            num.append((u, p))
        elif p < 0:
            den.append((u, -p))
    return num, den


def sqrt_value(v):
    if isinstance(v, complex) or v < 0:
        return cmath.sqrt(v)
    return math.sqrt(v)
