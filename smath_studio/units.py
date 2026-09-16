"""Unit system for SMath Studio -- dimension analysis, unit conversion, Quantity arithmetic."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from xml.etree import ElementTree as ET


# ---------------------------------------------------------------------------
# Core data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Dimension:
    """A physical dimension represented as a tuple of exponents for the
    base units: (m, s, kg, K, A, cd, mol, bit, sr).
    A dimensionless quantity has all zeros.
    """
    m: float = 0
    s: float = 0
    kg: float = 0
    K: float = 0
    A: float = 0
    cd: float = 0
    mol: float = 0
    bit: float = 0
    sr: float = 0

    def __mul__(self, other: "Dimension") -> "Dimension":
        return Dimension(
            self.m + other.m, self.s + other.s, self.kg + other.kg,
            self.K + other.K, self.A + other.A, self.cd + other.cd,
            self.mol + other.mol, self.bit + other.bit, self.sr + other.sr,
        )

    def __truediv__(self, other: "Dimension") -> "Dimension":
        return Dimension(
            self.m - other.m, self.s - other.s, self.kg - other.kg,
            self.K - other.K, self.A - other.A, self.cd - other.cd,
            self.mol - other.mol, self.bit - other.bit, self.sr - other.sr,
        )

    def __pow__(self, exp: float) -> "Dimension":
        return Dimension(
            self.m * exp, self.s * exp, self.kg * exp,
            self.K * exp, self.A * exp, self.cd * exp,
            self.mol * exp, self.bit * exp, self.sr * exp,
        )

    @property
    def is_dimensionless(self) -> bool:
        return all(
            abs(v) < 1e-12
            for v in (self.m, self.s, self.kg, self.K, self.A,
                      self.cd, self.mol, self.bit, self.sr)
        )


DIMENSIONLESS = Dimension()


@dataclass
class Unit:
    """A named unit with a conversion factor to SI base."""
    name: str
    factor: float = 1.0       # multiply by this factor * 10^exp to get SI base
    exp: int = 0              # exponent for the factor
    dimension: Dimension = field(default_factory=lambda: DIMENSIONLESS)
    offset: float = 0.0       # additive offset (for non-linear units like degC)
    is_nonlinear: bool = False

    @property
    def si_factor(self) -> float:
        return self.factor * (10 ** self.exp)

    def reciprocal(self) -> "Unit":
        """Return the reciprocal unit (for division)."""
        return Unit(
            name=f"1/{self.name}",
            factor=1.0 / self.si_factor,
            dimension=self.dimension ** -1,
        )


@dataclass
class Prefix:
    """An SI prefix."""
    symbol: str
    full_name: str
    factor: float  # the multiplier (e.g. 1e3 for kilo)


# ---------------------------------------------------------------------------
# Quantity -- value with a unit
# ---------------------------------------------------------------------------

class Quantity:
    """A numeric value with an attached unit."""

    __slots__ = ("value", "unit")

    def __init__(self, value: float, unit: Optional[Unit] = None):
        self.value = value
        self.unit = unit or Unit("1")

    # -- arithmetic --

    def __add__(self, other):
        if isinstance(other, Quantity):
            if self.unit.dimension != other.unit.dimension:
                raise TypeError(
                    f"Cannot add '{self.unit.name}' and '{other.unit.name}': incompatible units"
                )
            converted = _convert_value(other.value, other.unit, self.unit)
            return Quantity(self.value + converted, self.unit)
        return Quantity(self.value + _num(other), self.unit)

    def __radd__(self, other):
        return self.__add__(other)

    def __sub__(self, other):
        if isinstance(other, Quantity):
            if self.unit.dimension != other.unit.dimension:
                raise TypeError(
                    f"Cannot subtract '{other.unit.name}' from '{self.unit.name}': incompatible units"
                )
            converted = _convert_value(other.value, other.unit, self.unit)
            return Quantity(self.value - converted, self.unit)
        return Quantity(self.value - _num(other), self.unit)

    def __rsub__(self, other):
        if isinstance(other, Quantity):
            if self.unit.dimension != other.unit.dimension:
                raise TypeError(
                    f"Cannot subtract '{self.unit.name}' from '{other.unit.name}': incompatible units"
                )
            converted = _convert_value(self.value, self.unit, other.unit)
            return Quantity(other.value - converted, other.unit)
        return Quantity(_num(other) - self.value, self.unit)

    def __mul__(self, other):
        if isinstance(other, Quantity):
            new_dim = self.unit.dimension * other.unit.dimension
            new_factor = self.unit.si_factor * other.unit.si_factor
            combined_name = f"{self.unit.name}*{other.unit.name}"
            new_unit = Unit(combined_name, factor=new_factor, dimension=new_dim)
            return Quantity(self.value * other.value, new_unit)
        return Quantity(self.value * _num(other), self.unit)

    def __rmul__(self, other):
        return self.__mul__(other)

    def __truediv__(self, other):
        if isinstance(other, Quantity):
            new_dim = self.unit.dimension / other.unit.dimension
            new_factor = self.unit.si_factor / other.unit.si_factor
            combined_name = f"{self.unit.name}/{other.unit.name}"
            new_unit = Unit(combined_name, factor=new_factor, dimension=new_dim)
            return Quantity(self.value / other.value, new_unit)
        return Quantity(self.value / _num(other), self.unit)

    def __rtruediv__(self, other):
        new_dim = self.unit.dimension ** -1
        new_factor = 1.0 / self.unit.si_factor
        new_unit = Unit(f"1/{self.unit.name}", factor=new_factor, dimension=new_dim)
        return Quantity(_num(other) / self.value, new_unit)

    def __pow__(self, exp):
        e = _num(exp)
        new_dim = self.unit.dimension ** e
        new_factor = self.unit.si_factor ** e
        new_name = f"{self.unit.name}^{e}"
        new_unit = Unit(new_name, factor=new_factor, dimension=new_dim)
        return Quantity(self.value ** e, new_unit)

    def __neg__(self):
        return Quantity(-self.value, self.unit)

    def __abs__(self):
        return Quantity(abs(self.value), self.unit)

    def __float__(self):
        return float(self.value * self.unit.si_factor)

    def __repr__(self):
        return f"Quantity({self.value}, {self.unit.name})"

    def __str__(self):
        return f"{self.value} {simplify_unit_name(self.unit.name)}"

    @property
    def display_unit(self) -> str:
        return simplify_unit_name(self.unit.name)

    def to_unit(self, target_unit: Unit) -> "Quantity":
        """Convert this quantity to a different unit of the same dimension."""
        si_val = self.value * self.unit.si_factor
        new_val = si_val / target_unit.si_factor
        return Quantity(new_val, target_unit)


def simplify_unit_name(name: str) -> str:
    """Simplify a compound unit name like 'm*m*m/kg*s*s' to 'm^3/(kg·s^2)'.

    Handles nested compound names produced by repeated arithmetic, e.g.
    'kg*m/s*s*kg/km^2*s^2' by flattening all tokens into a single
    numerator/denominator collection.
    """
    if not name or name == "1":
        return ""

    totals: dict[str, float] = {}

    def _parse_token(tok: str) -> tuple[str, float]:
        tok = tok.strip()
        if not tok:
            return ("", 1.0)
        if "^" in tok:
            base, exp_s = tok.rsplit("^", 1)
            try:
                return base.strip(), float(exp_s)
            except ValueError:
                return tok, 1.0
        return tok, 1.0

    def _collect(expr: str, sign: float):
        """Recursively flatten unit tokens from a compound expression."""
        expr = expr.strip().strip("()")
        if not expr or expr == "1":
            return

        # Split on the first '/' that isn't inside parentheses
        slash_pos = -1
        depth = 0
        for i, ch in enumerate(expr):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "/" and depth == 0 and i > 0:
                slash_pos = i
                break

        if slash_pos >= 0:
            num_part = expr[:slash_pos]
            den_part = expr[slash_pos + 1:]
            _collect(num_part, sign)
            _collect(den_part, -sign)
        else:
            # Split by * or · within this part
            for tok_str in re.split(r"[*·]", expr):
                tok_str = tok_str.strip()
                if not tok_str or tok_str == "1":
                    continue
                # If the token itself contains a slash, recurse
                if "/" in tok_str:
                    _collect(tok_str, sign)
                else:
                    base, exp = _parse_token(tok_str)
                    if base:
                        totals[base] = totals.get(base, 0) + exp * sign

    _collect(name, 1.0)

    # Split into numerator (positive exponents) and denominator (negative)
    def _fmt(base: str, exp: float) -> str:
        aexp = abs(exp)
        if abs(aexp - 1.0) < 1e-12:
            return base
        if aexp == int(aexp):
            return f"{base}^{int(aexp)}"
        return f"{base}^{aexp}"

    num_strs = [_fmt(b, e) for b, e in sorted(totals.items()) if e > 1e-12]
    den_strs = [_fmt(b, e) for b, e in sorted(totals.items()) if e < -1e-12]

    if not num_strs and not den_strs:
        return ""
    if not den_strs:
        return "·".join(num_strs)
    if not num_strs:
        num_strs = ["1"]

    num_text = "·".join(num_strs)
    den_text = "·".join(den_strs)
    if len(den_strs) > 1:
        return f"{num_text}/({den_text})"
    return f"{num_text}/{den_text}"


def _convert_value(value: float, from_unit: Unit, to_unit: Unit) -> float:
    """Convert a value from one unit to another."""
    si_val = value * from_unit.si_factor
    return si_val / to_unit.si_factor


def _num(val) -> float:
    if isinstance(val, (int, float)):
        return val
    if isinstance(val, Quantity):
        return val.value
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# Unit Registry -- parsed from Units.xml
# ---------------------------------------------------------------------------

# Map dimension base-unit names to Dimension fields
_BASE_UNIT_TO_DIM = {
    "m": "m", "s": "s", "kg": "kg", "K": "K", "A": "A",
    "cd": "cd", "mol": "mol", "bit": "bit", "sr": "sr",
}


def _parse_connection(conn: str) -> Dimension:
    """Parse a dimension connection string like '{kg*m^2}/{A*s^3}' into a Dimension."""
    if not conn:
        return DIMENSIONLESS

    dim = {k: 0.0 for k in _BASE_UNIT_TO_DIM.values()}

    def _process_part(part: str, sign: float):
        part = part.strip().strip("{}")
        # Split by *
        tokens = re.split(r"\*", part)
        for tok in tokens:
            tok = tok.strip()
            if not tok:
                continue
            # Check for exponent
            m = re.match(r"^([A-Za-z]+)\^(-?\d+\.?\d*)$", tok)
            if m:
                base = m.group(1)
                exp = float(m.group(2))
            else:
                base = tok
                exp = 1.0
            if base in _BASE_UNIT_TO_DIM:
                dim_key = _BASE_UNIT_TO_DIM[base]
                dim[dim_key] += sign * exp

    # Split numerator/denominator
    parts = conn.split("/")
    # Numerator
    _process_part(parts[0], 1.0)
    # Denominators
    for p in parts[1:]:
        _process_part(p, -1.0)

    return Dimension(**dim)


class UnitRegistry:
    """Registry of all known units, parsed from Units.xml."""

    def __init__(self):
        self._units: dict[str, Unit] = {}
        self._prefixes: list[Prefix] = []
        self._dimension_map: dict[str, Dimension] = {}  # dim_id -> Dimension

    def lookup(self, name: str) -> Optional[Unit]:
        """Look up a unit by symbol name. Tries exact match, then prefix expansion."""
        if name in self._units:
            return self._units[name]

        # Try prefix expansion
        for prefix in sorted(self._prefixes, key=lambda p: len(p.symbol), reverse=True):
            if name.startswith(prefix.symbol) and len(name) > len(prefix.symbol):
                base_name = name[len(prefix.symbol):]
                base_unit = self._units.get(base_name)
                if base_unit is not None:
                    combined = Unit(
                        name=name,
                        factor=base_unit.factor * prefix.factor,
                        exp=base_unit.exp,
                        dimension=base_unit.dimension,
                        offset=base_unit.offset,
                        is_nonlinear=base_unit.is_nonlinear,
                    )
                    self._units[name] = combined
                    return combined

        return None

    def register(self, unit: Unit):
        self._units[unit.name] = unit

    def all_units(self) -> dict[str, Unit]:
        return dict(self._units)

    @classmethod
    def from_xml(cls, path: str | Path) -> "UnitRegistry":
        """Parse a Units.xml file into a UnitRegistry."""
        registry = cls()
        tree = ET.parse(path)
        root = tree.getroot()

        ns = _detect_ns(root)

        # Parse prefixes
        for pfx_elem in root.iter(f"{ns}prefixes"):
            for add in pfx_elem.findall(f"{ns}add"):
                factor_str = add.get("factor", "1")
                exp_str = add.get("exp", "0")
                name_str = add.get("name", "")

                factor = _eval_factor(factor_str) * (10 ** int(exp_str)) if exp_str != "0" else _eval_factor(factor_str)

                symbols = name_str.split()
                for sym in symbols:
                    if sym:
                        registry._prefixes.append(Prefix(sym, sym, factor))

        # Parse dimensions -- build dimension_id -> Dimension map
        dim_map: dict[str, Dimension] = {}
        for dim_elem in root.iter(f"{ns}dimensions"):
            for add in dim_elem.findall(f"{ns}add"):
                dim_id = add.get("id", "")
                baseunit = add.get("baseunit", "")
                connection = add.get("connection", "")

                if baseunit and baseunit in _BASE_UNIT_TO_DIM:
                    # It IS a base unit
                    d = {k: 0.0 for k in _BASE_UNIT_TO_DIM.values()}
                    d[_BASE_UNIT_TO_DIM[baseunit]] = 1.0
                    dim_map[dim_id] = Dimension(**d)
                elif connection:
                    dim_map[dim_id] = _parse_connection(connection)
                elif baseunit:
                    # Derived base units like L, Hz, dB
                    if connection:
                        dim_map[dim_id] = _parse_connection(connection)
                    else:
                        dim_map[dim_id] = DIMENSIONLESS
                else:
                    dim_map[dim_id] = DIMENSIONLESS

        registry._dimension_map = dim_map

        # Parse units
        for units_elem in root.iter(f"{ns}units"):
            for prop in units_elem.findall(f"{ns}property"):
                dim_id = prop.get("dimension", "")
                dimension = dim_map.get(dim_id, DIMENSIONLESS)

                for add in prop.findall(f"{ns}add"):
                    factor = _eval_factor(add.get("factor", "1"))
                    exp = int(add.get("exp", "0"))
                    offset_str = add.get("offset", "")
                    offset = _eval_factor(offset_str) if offset_str else 0.0
                    is_nonlinear = offset != 0.0

                    # Get synonym names
                    names: list[str] = []
                    for syn in add.findall(f"{ns}synonym"):
                        name_str = syn.get("name", "")
                        for n in name_str.split():
                            n = n.strip()
                            if n:
                                names.append(n)

                    for uname in names:
                        unit = Unit(
                            name=uname,
                            factor=factor,
                            exp=exp,
                            dimension=dimension,
                            offset=offset,
                            is_nonlinear=is_nonlinear,
                        )
                        registry.register(unit)

                    # Handle extensions (prefixed units)
                    for ext in add.findall(f"{ns}extension"):
                        for pfx in ext.findall(f"{ns}prefix"):
                            pfx_name = pfx.get("name", "")
                            # Find the prefix factor
                            pfx_factor = 1.0
                            for p in registry._prefixes:
                                if p.symbol == pfx_name:
                                    pfx_factor = p.factor
                                    break

                            base_for = ext.get("for", "")
                            base_names = base_for.split()
                            for bn in base_names:
                                bn = bn.strip()
                                if bn:
                                    full_name = pfx_name + bn
                                    prefixed_unit = Unit(
                                        name=full_name,
                                        factor=factor * pfx_factor,
                                        exp=exp,
                                        dimension=dimension,
                                    )
                                    registry.register(prefixed_unit)

        return registry


def _detect_ns(root: ET.Element) -> str:
    """Detect XML namespace from root element tag."""
    m = re.match(r"\{(.+?)\}", root.tag)
    if m:
        return "{" + m.group(1) + "}"
    return ""


def _eval_factor(expr: str) -> float:
    """Safely evaluate a factor expression like '5/9', '2*pi', '365.2425*24*60*60'."""
    if not expr:
        return 1.0
    expr = expr.strip()
    # Replace pi/π with math.pi
    expr = expr.replace("π", str(math.pi))

    # Simple safe evaluation -- support +, -, *, /, ^, **
    try:
        # Only allow digits, operators, dots, parens, e/E, whitespace, braces
        clean = expr.replace("{", "(").replace("}", ")")
        clean = clean.replace("^", "**")
        return float(eval(clean, {"__builtins__": {}}, {"pi": math.pi}))
    except Exception:
        try:
            return float(expr)
        except ValueError:
            return 1.0


def get_default_registry() -> UnitRegistry:
    """Get a unit registry loaded from the bundled Units.xml."""
    units_xml = Path(__file__).parent.parent / "smath" / "SMath Studio" / "entries" / "Units.xml"
    if units_xml.exists():
        return UnitRegistry.from_xml(units_xml)
    return UnitRegistry()
