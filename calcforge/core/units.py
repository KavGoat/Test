"""Unit-aware quantity system built on Pint.

Handles automatic display-unit selection (the 'ladder' logic):
- A length < 1 m shows in mm, >= 1 m shows in m
- A force < 1 kN shows in N, >= 1 kN shows in kN
- User-typed units are preserved as-is
- Imperial input stays imperial
- Angles from trig functions show in degrees
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pint

_ureg = pint.UnitRegistry()
_ureg.define("kip = 1000 * lbf")
_ureg.define("ksi = kip / inch**2")
_ureg.define("psf = lbf / foot**2")
_ureg.define("pcf = lbf / foot**3")
_ureg.define("klf = kip / foot")

Q_ = _ureg.Quantity
Unit = _ureg.Unit


_LADDERS: dict[str, list[tuple[str, float]]] = {
    "[length]": [("mm", 1e-3), ("m", 1.0), ("km", 1e3)],
    "[mass]": [("g", 1e-3), ("kg", 1.0), ("t", 1e3)],
    "[force]": [("N", 1.0), ("kN", 1e3), ("MN", 1e6)],
    "[pressure]": [("Pa", 1.0), ("kPa", 1e3), ("MPa", 1e6), ("GPa", 1e9)],
    "[energy]": [("J", 1.0), ("kJ", 1e3), ("MJ", 1e6)],
    "[power]": [("W", 1.0), ("kW", 1e3), ("MW", 1e6)],
}

_IMPERIAL_UNITS = frozenset([
    "inch", "foot", "yard", "mile", "lbf", "kip",
    "psi", "ksi", "psf", "pcf", "klf", "degF",
    "ft", "in", "lb", "lbm",
])


def _is_imperial(unit: pint.Unit) -> bool:
    return any(str(u) in _IMPERIAL_UNITS for u in unit._units)


@dataclass
class Quantity:
    """A value with optional unit and display preference."""
    value: float
    unit: Optional[pint.Unit] = None
    display_unit: Optional[pint.Unit] = None
    user_specified_unit: bool = False

    @property
    def pint_qty(self) -> pint.Quantity:
        if self.unit is None:
            return Q_(self.value, "dimensionless")
        return Q_(self.value, self.unit)

    @property
    def dimensionless(self) -> bool:
        return self.unit is None or self.pint_qty.dimensionless

    def to(self, target_unit: str | pint.Unit) -> "Quantity":
        if isinstance(target_unit, str):
            target_unit = Unit(target_unit)
        converted = self.pint_qty.to(target_unit)
        return Quantity(
            value=converted.magnitude,
            unit=target_unit,
            display_unit=target_unit,
            user_specified_unit=True,
        )

    def auto_display(self) -> "Quantity":
        if self.user_specified_unit or self.unit is None:
            return self
        dim = str(self.pint_qty.dimensionality)
        if _is_imperial(self.unit):
            return Quantity(self.value, self.unit, self.unit, True)
        if dim in _LADDERS:
            ladder = _LADDERS[dim]
            base_val = abs(self.pint_qty.to(Unit(ladder[0][0])).magnitude)
            chosen = ladder[0][0]
            for uname, threshold in ladder:
                if base_val >= threshold * 0.999:
                    chosen = uname
            converted = self.pint_qty.to(Unit(chosen))
            return Quantity(converted.magnitude, Unit(chosen), Unit(chosen), False)
        return self

    def __repr__(self) -> str:
        du = self.display_unit or self.unit
        if du is None:
            return f"{self.value:g}"
        displayed = self.pint_qty.to(du)
        return f"{displayed.magnitude:g} {du}"


def parse_unit(text: str) -> Optional[pint.Unit]:
    text = text.strip()
    if not text:
        return None
    try:
        return Unit(text)
    except pint.UndefinedUnitError:
        return None


def make_quantity(value: float, unit_str: str = "", display_unit_str: str = "") -> Quantity:
    unit = parse_unit(unit_str)
    display = parse_unit(display_unit_str) if display_unit_str else unit
    return Quantity(value, unit, display, user_specified_unit=bool(unit_str))


def add_quantities(a: Quantity, b: Quantity) -> Quantity:
    if a.dimensionless and b.dimensionless:
        return Quantity(a.value + b.value)
    result = a.pint_qty + b.pint_qty
    return Quantity(result.magnitude, result.units, a.display_unit or b.display_unit)


def subtract_quantities(a: Quantity, b: Quantity) -> Quantity:
    if a.dimensionless and b.dimensionless:
        return Quantity(a.value - b.value)
    result = a.pint_qty - b.pint_qty
    return Quantity(result.magnitude, result.units, a.display_unit or b.display_unit)


def multiply_quantities(a: Quantity, b: Quantity) -> Quantity:
    result = a.pint_qty * b.pint_qty
    if result.dimensionless:
        return Quantity(float(result.magnitude))
    return Quantity(result.magnitude, result.units)


def divide_quantities(a: Quantity, b: Quantity) -> Quantity:
    result = a.pint_qty / b.pint_qty
    if result.dimensionless:
        return Quantity(float(result.magnitude))
    return Quantity(result.magnitude, result.units)


def power_quantity(base: Quantity, exp: float) -> Quantity:
    result = base.pint_qty ** exp
    if result.dimensionless:
        return Quantity(float(result.magnitude))
    return Quantity(result.magnitude, result.units)


def quantities_compatible(a: Quantity, b: Quantity) -> bool:
    try:
        a.pint_qty + b.pint_qty
        return True
    except pint.DimensionalityError:
        return False
