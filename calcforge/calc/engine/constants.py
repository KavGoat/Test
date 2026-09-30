"""The constants SMath defines, for the Insert > Constants table.

SMath has two kinds: the built-in operands (π, e, i, ∞ - typed without an
apostrophe) and the physical constants of its unit library (Constants.xml),
which are typed like units: 'g.e, 'c, 'h...  Values are those of the unit
library; the unit is shown as SMath Cloud shows the result of 'name=.
"""
from __future__ import annotations

from dataclasses import dataclass

from .catalog import UNIT_CATALOG
from .display import display_text, display_value, unit_text
from .numformat import NumberFormat
from .units import unit_quantity
from .unitdata import INFO

BUILTIN = [
    ("π", "π", "3.14159265358979", "", "Number 'Pi'"),
    ("e", "e", "2.71828182845905", "", "Number 'e'"),
    ("i", "i", "√-1", "", "Imaginary unit"),
    ("∞", "∞", "∞", "", "Positive infinity"),
]


@dataclass
class Constant:
    typed: str  # what to type: 'g.e
    symbol: str  # shown as: g with subscript e
    value: str
    unit: str
    description: str


def _symbol(name: str) -> str:
    base, dot, sub = name.partition(".")
    return base + ("_" + sub if dot else "")


def constants() -> list[Constant]:
    out = [Constant(t, s, v, u, d) for t, s, v, u, d in BUILTIN]
    names = [n for n, info in INFO.items() if info[0] == "constant"]
    names.sort(key=lambda n: (n.lower(), n))
    full = NumberFormat(decimals=12, threshold=5)
    for n in names:
        q = unit_quantity(n)
        d = display_value(q, full)
        value = display_value(q, full, show_unit=False)
        desc = UNIT_CATALOG.get(n, ("", n))[1]
        out.append(Constant("'" + n, _symbol(n), display_text(value), unit_text(d.unit), desc))
    return out
