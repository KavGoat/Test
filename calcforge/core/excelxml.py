"""Reading Excel's own clipboard format, so formulas come across.

Excel puts several things on the clipboard at once. The plain text everybody
reads is what the cells *looked* like — the numbers, already worked out. The
formulas are only in one of the other flavours: "XML Spreadsheet 2003", where
each cell carries its formula in R1C1 notation.

So a paste that wants the formulas has to read that. What comes back is an
ordinary grid of strings — a formula as ``=B2*C2``, anything else as it was
typed — which is exactly what a paste of plain text produces, only better.
"""
from __future__ import annotations

import re
from xml.etree import ElementTree

# The namespace every one of these documents uses.
NS = "urn:schemas-microsoft-com:office:spreadsheet"
_SS = f"{{{NS}}}"

# R1C1 pieces: a letter, then either [offset] or a plain number, or neither.
_PART = re.compile(r"(?P<axis>[RC])(?:\[(?P<offset>-?\d+)\]|(?P<absolute>\d+))?")
# Where a reference can appear: not inside a name like "CURRENT" or "ROUND".
_REFERENCE = re.compile(r"(?<![A-Za-z0-9_$])"
                        r"(R(?:\[-?\d+\]|\d+)?C(?:\[-?\d+\]|\d+)?)"
                        r"(?![A-Za-z0-9_(])")


def looks_like_excel_xml(text: str) -> bool:
    """Whether this is the flavour that carries formulas."""
    head = (text or "")[:600]
    return "urn:schemas-microsoft-com:office:spreadsheet" in head


def column_name(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    name = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(ord("A") + remainder) + name
    return name


def r1c1_to_a1(reference: str, row: int, col: int) -> str:
    """One R1C1 reference, as it reads from the cell at *row*, *col*.

    Rows and columns are 0-based here, as they are everywhere else in the
    sheet. An absolute part comes back with its dollar sign, because that is
    what it means and what the fill handle will then respect.
    """
    parts = {match.group("axis"): match for match in _PART.finditer(reference)}
    pieces = {}
    for axis, here in (("R", row), ("C", col)):
        match = parts.get(axis)
        if match is None:
            pieces[axis] = (here, False)
            continue
        if match.group("absolute") is not None:
            pieces[axis] = (int(match.group("absolute")) - 1, True)
        else:
            pieces[axis] = (here + int(match.group("offset") or 0), False)
    target_row, row_fixed = pieces["R"]
    target_col, col_fixed = pieces["C"]
    if target_row < 0 or target_col < 0:
        return "#REF!"
    return (("$" if col_fixed else "") + column_name(target_col)
            + ("$" if row_fixed else "") + str(target_row + 1))


def formula_to_a1(formula: str, row: int, col: int) -> str:
    """A whole R1C1 formula, rewritten as it reads from that cell."""
    body = formula[1:] if formula.startswith("=") else formula
    rewritten = _REFERENCE.sub(
        lambda match: r1c1_to_a1(match.group(1), row, col), body)
    return "=" + rewritten


def parse(text: str, row: int = 0, col: int = 0) -> list[list[str]]:
    """The clipboard as a grid of what to type into each cell.

    *row* and *col* are where the top-left of the paste is going, because a
    relative formula means something different depending on where it lands.
    """
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError:
        return []
    grid: list[list[str]] = []
    for table in root.iter(f"{_SS}Table"):
        line_number = 0
        for line in table.findall(f"{_SS}Row"):
            said = line.get(f"{_SS}Index")
            if said:
                # Blank rows between the ones with something in them.
                while line_number < int(said) - 1:
                    grid.append([])
                    line_number += 1
            cells: list[str] = []
            for cell in line.findall(f"{_SS}Cell"):
                where = cell.get(f"{_SS}Index")
                if where:
                    while len(cells) < int(where) - 1:
                        cells.append("")
                formula = cell.get(f"{_SS}Formula")
                if formula:
                    cells.append(formula_to_a1(formula, row + line_number,
                                               col + len(cells)))
                else:
                    data = cell.find(f"{_SS}Data")
                    cells.append("" if data is None or data.text is None
                                 else data.text)
            grid.append(cells)
            line_number += 1
        if grid:
            break            # one table is what a copy from Excel gives
    return grid
