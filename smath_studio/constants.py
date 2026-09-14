"""Physical constants parsed from SMath Studio's Constants.xml."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

from .units import (
    Dimension,
    Quantity,
    Unit,
    UnitRegistry,
    _eval_factor,
    _parse_connection,
    _detect_ns,
    DIMENSIONLESS,
)


class ConstantsRegistry:
    """Registry of physical constants, each as a Quantity."""

    def __init__(self):
        self._constants: dict[str, Quantity] = {}

    def get(self, name: str) -> Optional[Quantity]:
        return self._constants.get(name)

    def all_constants(self) -> dict[str, Quantity]:
        return dict(self._constants)

    def register(self, name: str, quantity: Quantity):
        self._constants[name] = quantity

    @classmethod
    def from_xml(cls, path: str | Path, dim_map: Optional[dict[str, Dimension]] = None) -> "ConstantsRegistry":
        """Parse Constants.xml into a ConstantsRegistry."""
        registry = cls()
        tree = ET.parse(path)
        root = tree.getroot()
        ns = _detect_ns(root)

        if dim_map is None:
            dim_map = {}

        def _process_add(add_elem, dimension: Dimension):
            factor = _eval_factor(add_elem.get("factor", "1"))
            exp = int(add_elem.get("exp", "0"))
            connection = add_elem.get("connection", "")
            if connection:
                dimension = _parse_connection(connection)

            value = factor * (10 ** exp)

            # Create a unit representing the constant's dimension
            unit = Unit(name="SI", dimension=dimension)
            quantity = Quantity(value, unit)

            # Get synonym names
            for syn in add_elem.findall(f"{ns}synonym"):
                name_str = syn.get("name", "")
                for n in name_str.split():
                    n = n.strip()
                    if n:
                        registry.register(n, quantity)

        # Process constants inside <property> elements
        for constants_elem in root.iter(f"{ns}constants"):
            for prop in constants_elem.findall(f"{ns}property"):
                dim_id = prop.get("dimension", "")
                dimension = dim_map.get(dim_id, DIMENSIONLESS)

                for add in prop.findall(f"{ns}add"):
                    _process_add(add, dimension)

            # Process constants directly under <constants> (not in <property>)
            for add in constants_elem.findall(f"{ns}add"):
                _process_add(add, DIMENSIONLESS)

        return registry


def get_default_constants(unit_registry: Optional[UnitRegistry] = None) -> ConstantsRegistry:
    """Load constants from the bundled Constants.xml."""
    constants_xml = Path(__file__).parent.parent / "smath" / "SMath Studio" / "entries" / "Constants.xml"

    # Build dimension map from the unit registry
    dim_map = {}
    if unit_registry is not None:
        dim_map = unit_registry._dimension_map

    if constants_xml.exists():
        return ConstantsRegistry.from_xml(constants_xml, dim_map)
    return ConstantsRegistry()
