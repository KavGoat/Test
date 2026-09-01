"""Unit registry and quantity formatting for CalcForge.

Everything numeric that flows through the calculation engine is either a plain
``float``/``int``, a numpy array, or a :class:`pint.Quantity`.  This module owns
the single shared registry so that quantities created in a math region are
compatible with quantities created in a spreadsheet cell.
"""
from __future__ import annotations

import math
from typing import Any, Optional

import pint

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ureg = pint.UnitRegistry(autoconvert_offset_to_baseunit=False)
try:                                    # pint >= 0.24
    ureg.formatter.default_format = "~P"
except AttributeError:                  # pragma: no cover - older pint
    ureg.default_format = "~P"
Quantity = ureg.Quantity
Q_ = ureg.Quantity

# Extra engineering units that pint does not ship (or ships under a name that
# structural / civil engineers do not use).  Each line is applied defensively so
# that a future pint release adding one of them cannot break start-up.
_EXTRA_DEFINITIONS = [
    "kip = 1000 * force_pound = kips",
    "ksi = kip / inch ** 2",
    "psf = force_pound / foot ** 2",
    "pcf = force_pound / foot ** 3",
    "kcf = kip / foot ** 3",
    "klf = kip / foot",
    "plf = force_pound / foot",
    "tonf_metric = 1000 * kilogram_force = tonne_force",
    "MPa = 1e6 * pascal",
    "GPa = 1e9 * pascal",
    "kPa = 1000 * pascal",
    "kN = 1000 * newton",
    "MN = 1e6 * newton",
    "kNm = kilonewton * meter",
]

for _definition in _EXTRA_DEFINITIONS:
    try:
        ureg.define(_definition)
    except Exception:  # already defined, or shadows a prefix expansion
        pass


def dimensionless(value: Any) -> bool:
    """True when *value* carries no physical dimension."""
    if isinstance(value, Quantity):
        return value.dimensionless
    return True


def magnitude(value: Any) -> Any:
    """Strip units, converting to base units first when necessary."""
    if isinstance(value, Quantity):
        if value.dimensionless:
            return value.to_base_units().magnitude
        return value.magnitude
    return value


def as_float(value: Any) -> float:
    """Coerce *value* to a bare float, raising a friendly error if impossible."""
    if isinstance(value, Quantity):
        if not value.dimensionless:
            raise pint.DimensionalityError(value.units, ureg.dimensionless)
        value = value.to_base_units().magnitude
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    return float(value)


_UNIT_NAME_CACHE: dict[str, bool] = {}


def is_unit_name(name: str) -> bool:
    """True when *name* is a unit in the registry (cached; used for italics)."""
    known = _UNIT_NAME_CACHE.get(name)
    if known is None:
        try:
            ureg.Unit(name)
            known = True
        except Exception:
            known = False
        _UNIT_NAME_CACHE[name] = known
    return known


def parse_unit(text: str):
    """Parse a unit expression such as ``kN/m^2`` into a pint unit."""
    text = (text or "").strip()
    if not text:
        return None
    text = text.replace("^", "**").replace("·", "*").replace("×", "*")
    return ureg.parse_expression(text)


def convert(value: Any, unit_text: str):
    """Convert *value* to *unit_text*.  Accepts prefactors, e.g. ``1e3*mm``."""
    target = parse_unit(unit_text)
    if target is None:
        return value
    if not isinstance(value, Quantity):
        value = Q_(value, "dimensionless")
    if isinstance(target, Quantity):
        # e.g. "kN" parses to Quantity(1.0, kilonewton)
        return (value / target).to("dimensionless") * target
    return value.to(target)


# ---------------------------------------------------------------------------
# Number formatting
# ---------------------------------------------------------------------------

AUTO = "auto"
FIXED = "fixed"
SCIENTIFIC = "scientific"
ENGINEERING = "engineering"

_SUPERSCRIPT = str.maketrans("0123456789-+", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺")


def _strip_zeros(text: str) -> str:
    if "." in text and "e" not in text and "E" not in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def format_number(value: Any, digits: int = 4, mode: str = AUTO,
                  thousands: bool = False) -> str:
    """Format a scalar using engineering-friendly rules."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, complex):
        re_part = format_number(value.real, digits, mode)
        im_part = format_number(abs(value.imag), digits, mode)
        sign = "-" if value.imag < 0 else "+"
        return f"{re_part} {sign} {im_part}i"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return str(value)

    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "∞" if value > 0 else "-∞"
    if value == 0:
        return "0"

    if mode == FIXED:
        text = f"{value:,.{digits}f}" if thousands else f"{value:.{digits}f}"
        return text

    if mode == SCIENTIFIC:
        mant, exp = f"{value:.{digits}e}".split("e")
        return f"{_strip_zeros(mant)}·10{str(int(exp)).translate(_SUPERSCRIPT)}"

    if mode == ENGINEERING:
        exp = int(math.floor(math.log10(abs(value))))
        exp -= exp % 3
        mant = value / (10 ** exp)
        mant_digits = max(digits - 1 - int(math.floor(math.log10(abs(mant)))), 0)
        mant_text = _strip_zeros(f"{mant:.{mant_digits}f}")
        if exp == 0:
            return mant_text
        return f"{mant_text}·10{str(exp).translate(_SUPERSCRIPT)}"

    # AUTO: significant digits, falling back to scientific for extremes.
    exponent = math.floor(math.log10(abs(value)))
    if exponent < -5 or exponent >= digits + 6:
        return format_number(value, digits, SCIENTIFIC)
    decimals = max(digits - 1 - int(exponent), 0)
    text = f"{value:,.{decimals}f}" if thousands else f"{value:.{decimals}f}"
    return _strip_zeros(text)


def format_unit(unit) -> str:
    """Render a pint unit the way an engineer writes it."""
    if unit is None:
        return ""
    try:
        text = f"{unit:~P}"
    except Exception:
        text = str(unit)
    return text.replace(" ** ", "^").replace("**", "^").strip()


def format_quantity(value: Any, digits: int = 4, mode: str = AUTO,
                    unit: Optional[str] = None, thousands: bool = False) -> str:
    """Format anything the engine can produce into display text."""
    import numpy as np

    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, Quantity) and unit:
        try:
            value = convert(value, unit)
        except Exception:
            pass

    if isinstance(value, Quantity):
        mag = value.magnitude
        unit_text = format_unit(value.units)
        if isinstance(mag, np.ndarray):
            body = format_matrix(mag, digits, mode)
            return f"{body} {unit_text}".strip()
        body = format_number(mag, digits, mode, thousands)
        if not unit_text or unit_text == "dimensionless":
            return body
        return f"{body} {unit_text}"

    if isinstance(value, np.ndarray):
        return format_matrix(value, digits, mode)
    if isinstance(value, (list, tuple)):
        return "(" + ", ".join(format_quantity(v, digits, mode) for v in value) + ")"
    return format_number(value, digits, mode, thousands)


def format_matrix(array, digits: int = 4, mode: str = AUTO) -> str:
    """Bracketed row/column rendering for numpy arrays."""
    import numpy as np

    array = np.atleast_1d(array)
    if array.ndim == 1:
        cells = ", ".join(format_number(v, digits, mode) for v in array)
        return f"[{cells}]"
    rows = []
    for row in array:
        rows.append(", ".join(format_number(v, digits, mode) for v in row))
    return "[" + "; ".join(rows) + "]"


# Units offered in the UI drop-downs, grouped by quantity kind.
UNIT_MENU = {
    "Length": ["mm", "cm", "m", "km", "in", "ft", "yd", "mile"],
    "Area": ["mm^2", "cm^2", "m^2", "in^2", "ft^2", "ha", "acre"],
    "Volume": ["mm^3", "cm^3", "m^3", "L", "in^3", "ft^3", "gal"],
    "Mass": ["g", "kg", "tonne", "lb", "oz", "slug"],
    "Force": ["N", "kN", "MN", "kgf", "lbf", "kip"],
    "Moment": ["N*m", "kN*m", "lbf*ft", "kip*ft"],
    "Stress": ["Pa", "kPa", "MPa", "GPa", "psi", "ksi", "psf"],
    "Line load": ["N/m", "kN/m", "plf", "klf"],
    "Area load": ["Pa", "kPa", "psf", "kN/m^2"],
    "Density": ["kg/m^3", "kN/m^3", "pcf"],
    "Angle": ["deg", "rad", "grad"],
    "Time": ["s", "min", "hr", "day", "year"],
    "Temperature": ["degC", "degF", "kelvin"],
    "Energy": ["J", "kJ", "MJ", "kWh", "BTU"],
    "Power": ["W", "kW", "MW", "hp"],
    "Frequency": ["Hz", "kHz", "rpm"],
    "Velocity": ["m/s", "km/hr", "ft/s", "mph"],
}
