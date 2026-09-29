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


# Derived units used to build "unit per length" style results, in order of
# preference, and the divisors allowed with them.
_READABLE = ["N", "J", "W", "Pa", "V", "C"]


def derived_per_base(dims: tuple):
    """(derived, [(base, power)]) for results that read naturally as a derived
    unit over a base unit: N/m (force per length), N/m³ (unit weight),
    W/m² (heat flux), J/K, W/m...  None when nothing reads well.

    SMath itself shows kg/s² as "m Pa"; that is correct but nobody writes a
    line load that way, so the replica prefers the engineering form.
    Lengths are tried as divisors first (N/m before N/s).
    """
    m, s, K = BASE.index("m"), BASE.index("s"), BASE.index("K")
    passes = [[(m, -1), (m, -2), (m, -3)], [(s, -1), (K, -1)]]
    lookup = dict(DERIVED)
    for divisors in passes:
        for name in _READABLE:
            d = lookup[name]
            rest = [a - b for a, b in zip(dims, d)]
            for idx, p in divisors:
                want = [0] * len(BASE)
                want[idx] = p
                if rest == want:
                    return name, [(BASE[idx], -p)]
    return None


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
