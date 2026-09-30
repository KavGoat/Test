"""Quantities for scales, sizes and measurements, in SMath's unit system.

There is one unit system in CalcForge and it is SMath's (decision 1): the unit
table the calculation engine uses (``calc/engine/unitdata.py``, generated from
SMath Studio's own Units.xml) and the engine's number formatter. A scale set at
1:100, a line measured in metres and a variable in an equation all meet in the
same table, so a measurement that feeds a calculation cannot be converted one
way here and another way there.

This module keeps the small interface the markup code has always used —
``Q_``, ``parse_unit``, ``convert``, ``format_quantity`` — and builds it on the
engine. A :class:`Quantity` is a value in SI base units with a dimension
vector, exactly as the engine holds it, plus the unit it is being shown in.

Units are written the way SMath writes them: ``mm``, ``kN``, ``°C``, ``hr``
(``h`` is Planck's constant in SMath's table). As plain text they read with a
middle dot and superscripts — ``kN·m``, ``m²`` — which is how an equation
draws them.
"""
from __future__ import annotations

import math
import re
from typing import Any, Optional

# Importing the engine's units module installs the prefixed units SMath's own
# library lacks (hPa, daN, kWh…), so the table below is the engine's table.
from ..calc.engine import units as _engine_units
from ..calc.engine.numformat import NumberFormat, format_real
from ..calc.engine.unitdata import BASE, UNITS

NDIM = len(BASE)
NODIM = tuple([0] * NDIM)
_LENGTH = tuple(1 if name == "m" else 0 for name in BASE)

# Documents saved by MarkForge wrote scales with Pint's unit names. They still
# open: each old name reads as the SMath unit it always meant.
_OLD_NAMES = {
    "millimeter": "mm", "centimeter": "cm", "meter": "m", "kilometer": "km",
    "inch": "in", "foot": "ft", "yard": "yd", "mile": "mi",
    "micrometer": "μm", "nanometer": "nm",
    "degree": "deg", "radian": "rad", "gradian": "grad",
    "hour": "hr", "minute": "min", "second": "s", "day": "day", "year": "yr",
    "degC": "°C", "degF": "°F", "kelvin": "K", "degree_Celsius": "°C",
    "degree_Fahrenheit": "°F",
    "liter": "L", "litre": "L", "gallon": "gal",
    "gram": "g", "kilogram": "kg", "tonne": "tonne", "pound": "lb",
    "newton": "N", "kilonewton": "kN", "pascal": "Pa",
    "hectare": "ha", "dimensionless": "",
}


class DimensionalityError(ValueError):
    """Two quantities that cannot be converted into each other."""


def _dims_mul(a: tuple, b: tuple, k: float = 1) -> tuple:
    return tuple(_clean(x + k * y) for x, y in zip(a, b))


def _clean(x: float):
    r = round(x)
    return int(r) if abs(x - r) < 1e-9 else x


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------

class Unit:
    """A unit expression: named units with powers, e.g. kN·m or kN/m².

    ``parts`` keeps the names in the order they were written, which is the
    order they are shown in: the force before the lever arm, as an engineer
    writes a moment.
    """

    __slots__ = ("parts",)

    def __init__(self, parts=()):
        merged: list = []
        for name, power in parts:
            for i, (have, p) in enumerate(merged):
                if have == name:
                    merged[i] = (have, _clean(p + power))
                    break
            else:
                merged.append((name, _clean(power)))
        self.parts = tuple((n, p) for n, p in merged if p != 0)

    # -- what the unit is
    @property
    def factor(self) -> float:
        f = 1.0
        for name, power in self.parts:
            f *= float(UNITS[name][0]) ** power
        return f

    @property
    def dims(self) -> tuple:
        d = NODIM
        for name, power in self.parts:
            d = _dims_mul(d, tuple(UNITS[name][1]), power)
        return d

    @property
    def offset(self) -> float:
        """°C and °F are a shift as well as a size — but only on their own."""
        if len(self.parts) == 1 and self.parts[0][1] == 1:
            return float(UNITS[self.parts[0][0]][2])
        return 0.0

    def __mul__(self, other: "Unit") -> "Unit":
        return Unit(self.parts + other.parts)

    def __truediv__(self, other: "Unit") -> "Unit":
        return Unit(self.parts + tuple((n, -p) for n, p in other.parts))

    def __pow__(self, power) -> "Unit":
        return Unit(tuple((n, p * power) for n, p in self.parts))

    def __eq__(self, other) -> bool:
        return isinstance(other, Unit) and self.parts == other.parts

    def __hash__(self) -> int:
        return hash(self.parts)

    def __str__(self) -> str:
        """The unit as it is stored: ``kN*m``, ``m^2``, ``kN/m^2``."""
        return unit_text(self, plain=False)

    def __repr__(self) -> str:
        return f"Unit({str(self)!r})"


_SUPERSCRIPT = str.maketrans("0123456789-.", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻·")


def _power_text(power, plain: bool) -> str:
    if power == 1:
        return ""
    text = f"{power:g}"
    if plain:
        return text.translate(_SUPERSCRIPT)
    return "^" + text


def unit_text(unit: Optional[Unit], plain: bool = True) -> str:
    """``kN·m``, ``kN/m²`` (plain) or ``kN*m``, ``kN/m^2`` (stored)."""
    if unit is None or not unit.parts:
        return ""
    join = "·" if plain else "*"
    num = [n + _power_text(p, plain) for n, p in unit.parts if p > 0]
    den = [n + _power_text(-p, plain) for n, p in unit.parts if p < 0]
    text = join.join(num) or "1"
    if den:
        text += "/" + (den[0] if len(den) == 1 else "(" + join.join(den) + ")")
    return text


def format_unit(unit) -> str:
    """A unit as it is written on a drawing: ``kN·m``, ``m²``."""
    if isinstance(unit, Unit):
        return unit_text(unit)
    parsed = _parse_unit_expression(str(unit or ""))
    return unit_text(parsed) if parsed is not None else str(unit or "")


# -- reading unit text -------------------------------------------------------

_TOKEN = re.compile(r"\s*(?:(?P<num>\d+(?:\.\d*)?(?:[eE][-+]?\d+)?|\.\d+(?:[eE][-+]?\d+)?)"
                    r"|(?P<pow>\*\*|\^)|(?P<sup>[⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+)"
                    r"|(?P<op>[*/·×()])|(?P<minus>-)"
                    r"|(?P<name>[^\s\d*/·×()^\-⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+))")
_FROM_SUPERSCRIPT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")


def _unit_named(name: str) -> Optional[Unit]:
    if name in UNITS:
        return Unit(((name, 1),))
    old = _OLD_NAMES.get(name)
    if old is not None:
        return Unit(((old, 1),)) if old else Unit()
    # Pint wrote products such as "millimeter ** 2"; plural and spelled-out
    # forms of the old names are read the same way.
    if name.endswith("s") and _OLD_NAMES.get(name[:-1]):
        return Unit(((_OLD_NAMES[name[:-1]], 1),))
    return None


class _Reader:
    """A tiny recursive-descent reader for ``5 kN/m^2``, ``m²``, ``kN*m``."""

    def __init__(self, text: str):
        self.tokens = []
        pos = 0
        text = text.strip()
        while pos < len(text):
            m = _TOKEN.match(text, pos)
            if not m or m.end() == pos:
                raise ValueError(text)
            kind = m.lastgroup
            self.tokens.append((kind, m.group(kind)))
            pos = m.end()
        self.i = 0

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else (None, None)

    def take(self):
        token = self.peek()
        self.i += 1
        return token

    def done(self) -> bool:
        return self.i >= len(self.tokens)

    # number? unit-product
    def quantity(self):
        value = 1.0
        kind, text = self.peek()
        negative = False
        if kind == "minus":
            self.take()
            negative = True
            kind, text = self.peek()
        if kind == "num":
            self.take()
            value = float(text)
        elif negative:
            raise ValueError("minus without a number")
        if negative:
            value = -value
        unit = Unit()
        if not self.done():
            unit = self.product()
        if not self.done():
            raise ValueError("trailing text")
        return value, unit

    def product(self) -> Unit:
        unit = self.power()
        while not self.done():
            kind, text = self.peek()
            if kind == "op" and text in "*·×":
                self.take()
                unit = unit * self.power()
            elif kind == "op" and text == "/":
                self.take()
                unit = unit / self.power()
            elif kind in ("name",) or (kind == "op" and text == "("):
                unit = unit * self.power()       # "kN m" is kN·m
            else:
                break
        return unit

    def power(self) -> Unit:
        unit = self.atom()
        kind, text = self.peek()
        if kind == "pow":
            self.take()
            sign = 1
            if self.peek()[0] == "minus":
                self.take()
                sign = -1
            kind, text = self.take()
            if kind != "num":
                raise ValueError("power without a number")
            unit = unit ** (sign * float(text))
        elif kind == "sup":
            self.take()
            unit = unit ** float(text.translate(_FROM_SUPERSCRIPT))
        return unit

    def atom(self) -> Unit:
        kind, text = self.take()
        if kind == "op" and text == "(":
            unit = self.product()
            if self.take() != ("op", ")"):
                raise ValueError("unclosed bracket")
            return unit
        if kind == "num" and text == "1":
            return Unit()                          # "1/s"
        if kind != "name":
            raise ValueError("expected a unit")
        unit = _unit_named(text)
        if unit is None:
            raise ValueError(f"unknown unit {text}")
        return unit


def _parse_unit_expression(text: str) -> Optional[Unit]:
    try:
        reader = _Reader(text)
        if reader.done():
            return Unit()
        value, unit = reader.quantity()
    except (ValueError, IndexError, TypeError):
        return None
    return unit if value == 1.0 else None


# ---------------------------------------------------------------------------
# Quantities
# ---------------------------------------------------------------------------

class Quantity:
    """A magnitude in a unit, held as the engine holds it: SI value + dims.

    ``magnitude`` is the number in ``units``; ``si`` is the same amount in SI
    base units, which is what every conversion goes through.
    """

    __slots__ = ("magnitude", "units")

    def __init__(self, magnitude, units=None):
        if isinstance(units, str):
            parsed = _parse_unit_expression(units)
            if parsed is None:
                raise DimensionalityError(f"unknown unit {units!r}")
            units = parsed
        self.magnitude = magnitude
        self.units = units if isinstance(units, Unit) else Unit()

    # -- what it is
    @property
    def si(self) -> float:
        return self.magnitude * self.units.factor + self.units.offset

    @property
    def dims(self) -> tuple:
        return self.units.dims

    @property
    def dimensionless(self) -> bool:
        return all(d == 0 for d in self.dims)

    def check(self, dimension: str) -> bool:
        """``check("[length]")``, as the size and calibration boxes ask it."""
        wanted = {"[length]": _LENGTH, "[area]": tuple(2 * x for x in _LENGTH),
                  "[volume]": tuple(3 * x for x in _LENGTH)}.get(dimension)
        return wanted is not None and self.dims == wanted

    def engine_quantity(self):
        """The same amount as the calculation engine's own value."""
        return _engine_units.Quantity(self.si, self.dims)

    # -- conversion
    def to(self, target) -> "Quantity":
        if isinstance(target, str):
            unit = _parse_unit_expression(target)
            if unit is None:
                raise DimensionalityError(f"unknown unit {target!r}")
        else:
            unit = target
        if unit.dims != self.dims:
            raise DimensionalityError(
                f"cannot convert {unit_text(self.units)} to {unit_text(unit)}")
        return Quantity((self.si - unit.offset) / unit.factor, unit)

    def to_reduced_units(self) -> "Quantity":
        """One unit per dimension: m²·mm reads as m³, the first unit written."""
        kept: list = []
        for name, power in self.units.parts:
            dims = tuple(UNITS[name][1])
            for i, (other, other_power) in enumerate(kept):
                if tuple(UNITS[other][1]) == dims:
                    kept[i] = (other, other_power + power)
                    break
            else:
                kept.append((name, power))
        return self.to(Unit(tuple(kept)))

    # -- arithmetic
    def _other(self, other) -> "Quantity":
        return other if isinstance(other, Quantity) else Quantity(other)

    def __mul__(self, other):
        if isinstance(other, Quantity):
            return Quantity(self.magnitude * other.magnitude, self.units * other.units)
        return Quantity(self.magnitude * other, self.units)

    __rmul__ = __mul__

    def __truediv__(self, other):
        if isinstance(other, Quantity):
            return Quantity(self.magnitude / other.magnitude, self.units / other.units)
        return Quantity(self.magnitude / other, self.units)

    def __rtruediv__(self, other):
        return Quantity(other / self.magnitude, Unit() / self.units)

    def __pow__(self, power):
        return Quantity(self.magnitude ** power, self.units ** power)

    def __add__(self, other):
        other = self._other(other).to(self.units)
        return Quantity(self.magnitude + other.magnitude, self.units)

    __radd__ = __add__

    def __sub__(self, other):
        other = self._other(other).to(self.units)
        return Quantity(self.magnitude - other.magnitude, self.units)

    def __neg__(self):
        return Quantity(-self.magnitude, self.units)

    def __abs__(self):
        return Quantity(abs(self.magnitude), self.units)

    def __float__(self) -> float:
        if not self.dimensionless:
            raise DimensionalityError(f"{self} has units")
        return float(self.si)

    def _compare(self, other) -> float:
        other = self._other(other)
        if other.dims != self.dims:
            raise DimensionalityError("cannot compare")
        return self.si - other.si

    def __lt__(self, other):
        return self._compare(other) < 0

    def __le__(self, other):
        return self._compare(other) <= 0

    def __gt__(self, other):
        return self._compare(other) > 0

    def __ge__(self, other):
        return self._compare(other) >= 0

    def __eq__(self, other):
        try:
            return self._compare(other) == 0
        except (DimensionalityError, TypeError, ValueError):
            return False

    __hash__ = None

    def __str__(self) -> str:
        return format_quantity(self)

    def __repr__(self) -> str:
        return f"Quantity({self.magnitude!r}, {str(self.units)!r})"


Q_ = Quantity


def parse_unit(text: str) -> Optional[Quantity]:
    """``5 m``, ``kN/m^2``, ``1.5m`` — or None when it is not one.

    None is what every caller reads as "that is not a length": an empty box,
    and a box holding something the unit table has never heard of. It must
    never raise: an exception raised inside a Qt slot is not an error message,
    it is a crash a few events later.
    """
    text = (text or "").strip()
    if not text:
        return None
    try:
        reader = _Reader(text)
        value, unit = reader.quantity()
    except (ValueError, IndexError, TypeError):
        return None
    return Quantity(value, unit)


def convert(value: Any, unit_text_: str):
    """*value* in the unit *unit_text_*; a prefactor such as ``1e3*mm`` works."""
    target = parse_unit(unit_text_)
    if target is None:
        return value
    if not isinstance(value, Quantity):
        value = Quantity(value)
    converted = value.to(target.units)
    if target.magnitude != 1.0:
        converted = Quantity(converted.magnitude / target.magnitude, target.units)
    return converted


# ---------------------------------------------------------------------------
# Number formatting — the engine's formatter, so a label and an equation
# round exactly alike.
# ---------------------------------------------------------------------------

AUTO = "auto"
FIXED = "fixed"

# A measurement label is written with the page's decimal places and never
# switches to powers of ten for an ordinary drawing dimension.
_LABEL_THRESHOLD = 15


def _number_format(digits: int, mode: str) -> NumberFormat:
    if mode == FIXED:
        return NumberFormat(decimals=max(int(digits), 0), threshold=_LABEL_THRESHOLD,
                            trailing_zeros=True)
    return NumberFormat(decimals=max(int(digits), 0))


def format_number(value: Any, digits: int = 4, mode: str = AUTO) -> str:
    """A number as SMath writes it (``·10⁵`` for a large one)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    try:
        x = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(x):
        return "NaN"
    if math.isinf(x):
        return "∞" if x > 0 else "-∞"
    shown = format_real(x, _number_format(digits, mode))
    text = ("-" if shown.negative else "") + shown.mantissa
    if shown.exponent is not None:
        text += "·10" + str(shown.exponent).translate(_SUPERSCRIPT)
    return text


def format_quantity(value: Any, digits: int = 4, mode: str = AUTO,
                    unit: Optional[str] = None) -> str:
    """A value as it is written on a drawing: ``2.40 m``, ``12.5 m²``."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, Quantity):
        if unit:
            try:
                value = convert(value, unit)
            except DimensionalityError:
                pass
        body = format_number(value.magnitude, digits, mode)
        text = unit_text(value.units)
        return f"{body} {text}" if text else body
    return format_number(value, digits, mode)


# Units offered in the drop-downs, grouped by kind, in SMath's names. Pint's
# pcf, klf and plf are not in SMath's table; they are the same units written
# out (lbf/ft³, kip/ft, lbf/ft).
UNIT_MENU = {
    "Length": ["mm", "cm", "m", "km", "in", "ft", "yd", "mi"],
    "Area": ["mm^2", "cm^2", "m^2", "in^2", "ft^2", "ha", "acre"],
    "Volume": ["mm^3", "cm^3", "m^3", "L", "in^3", "ft^3", "gal"],
    "Mass": ["g", "kg", "tonne", "lb", "oz", "slug"],
    "Force": ["N", "kN", "MN", "kgf", "lbf", "kip"],
    "Moment": ["N*m", "kN*m", "lbf*ft", "kip*ft"],
    "Stress": ["Pa", "kPa", "MPa", "GPa", "psi", "ksi", "psf"],
    "Line load": ["N/m", "kN/m", "lbf/ft", "kip/ft"],
    "Area load": ["Pa", "kPa", "psf", "kN/m^2"],
    "Density": ["kg/m^3", "kN/m^3", "lbf/ft^3"],
    "Angle": ["deg", "rad", "grad"],
    "Time": ["s", "min", "hr", "day", "yr"],
    "Temperature": ["°C", "°F", "K"],
    "Energy": ["J", "kJ", "MJ", "kWh", "BTU"],
    "Power": ["W", "kW", "MW", "hp"],
    "Frequency": ["Hz", "kHz", "rpm"],
    "Velocity": ["m/s", "km/hr", "ft/s", "mph"],
}
