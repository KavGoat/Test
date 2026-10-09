"""How a cell looks: number format, unit, font, fill, borders, alignment.

Styles are shared: each distinct look is stored once in the workbook's
:class:`StyleTable` and cells hold its index (0 is the plain default), so a
sheet of thousands of alike cells keeps one copy.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import Optional


@dataclass(frozen=True)
class Border:
    style: str = "thin"          # thin medium thick dashed dotted double hair
    color: str = "#000000"


@dataclass(frozen=True)
class Style:
    number_format: Optional[str] = None      # Excel format code; None is General
    unit: Optional[str] = None               # show quantities in this unit ("kN")
    font: Optional[str] = None               # family; None is the sheet's
    size: Optional[float] = None             # points
    bold: bool = False
    italic: bool = False
    underline: str = ""                      # "", "single", "double"
    strike: bool = False
    color: Optional[str] = None              # text colour
    fill: Optional[str] = None               # background colour
    h_align: str = "general"                 # general left center right fill justify centerAcross
    v_align: str = "bottom"                  # top center bottom
    wrap: bool = False
    shrink: bool = False
    indent: int = 0
    rotation: int = 0                        # degrees, -90..90, or 255 for stacked
    left: Optional[Border] = None
    right: Optional[Border] = None
    top: Optional[Border] = None
    bottom: Optional[Border] = None
    diagonal_up: Optional[Border] = None
    diagonal_down: Optional[Border] = None
    locked: bool = True
    hidden: bool = False

    def changed(self, **kw) -> "Style":
        return replace(self, **kw)


DEFAULT = Style()
FIELDS = [f.name for f in fields(Style)]


class StyleTable:
    def __init__(self):
        self._styles: list[Style] = [DEFAULT]
        self._index: dict[Style, int] = {DEFAULT: 0}

    def add(self, style: Style) -> int:
        """The index of this look, stored once."""
        got = self._index.get(style)
        if got is None:
            got = len(self._styles)
            self._styles.append(style)
            self._index[style] = got
        return got

    def get(self, index: int) -> Style:
        try:
            return self._styles[index]
        except IndexError:
            return DEFAULT

    def __len__(self) -> int:
        return len(self._styles)

    def all(self) -> list[Style]:
        return list(self._styles)
