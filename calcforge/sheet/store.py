"""A sheet as data, for the document's record and the clipboard.

    {"name": ..., "kind": ..., "size": [rows, cols],
     "cells": [[row, col, input, style index, comment], ...],
     "styles": [style as dict, ...],          # this sheet's own list
     "widths": {col: pt}, "heights": {row: pt},
     "hidden_rows": [...], "hidden_cols": [...], "merges": [[t, l, b, r], ...],
     "default_width": pt, "default_height": pt, "gridlines": bool, "headings": bool}
"""
from __future__ import annotations

from dataclasses import fields

from .style import Border, Style


def style_to_dict(style: Style) -> dict:
    out = {}
    for f in fields(Style):
        value = getattr(style, f.name)
        if value == f.default:
            continue
        if isinstance(value, Border):
            value = [value.style, value.color]
        out[f.name] = value
    return out


def style_from_dict(data: dict) -> Style:
    known = {f.name for f in fields(Style)}
    kw = {}
    for k, v in data.items():
        if k not in known:
            continue
        if k in ("left", "right", "top", "bottom", "diagonal_up", "diagonal_down") and v is not None:
            v = Border(*v)
        kw[k] = v
    return Style(**kw)


def sheet_to_dict(sheet) -> dict:
    wb = sheet.workbook
    local: dict[int, int] = {0: 0}
    styles = [{}]
    cells = []
    for (row, col), cell in sorted(sheet.cells.items()):
        if cell.empty():
            continue                    # a spilled value: its formula makes it again
        index = local.get(cell.style)
        if index is None:
            index = len(styles)
            local[cell.style] = index
            styles.append(style_to_dict(wb.styles.get(cell.style)))
        entry = [row, col, cell.input, index]
        if cell.comment:
            entry.append(cell.comment)
        cells.append(entry)
    return {
        "name": sheet.name, "kind": sheet.kind,
        "size": list(sheet.size) if sheet.size else None,
        "cells": cells, "styles": styles,
        "widths": {str(k): v for k, v in sorted(sheet.widths.items())},
        "heights": {str(k): v for k, v in sorted(sheet.heights.items())},
        "hidden_rows": sorted(sheet.hidden_rows), "hidden_cols": sorted(sheet.hidden_cols),
        "merges": [list(m) for m in sheet.merges],
        "default_width": sheet.default_width, "default_height": sheet.default_height,
        "gridlines": sheet.show_gridlines, "headings": sheet.show_headings,
        "names": names_homed_on(sheet),
        "cond_rules": sheet.cond_rules, "validations": sheet.validations,
        "filter": sheet.filter, "filtered_rows": sorted(sheet.filtered_rows),
        "page": sheet.page,
    }


def names_homed_on(sheet) -> list:
    """The defined names kept, saved and undone with this sheet: those whose
    cells are on it, and those naming no cells that were made here.
    Each: [name, refers to, local to this sheet, comment]."""
    from . import formula as F

    out = []
    for dn in sheet.workbook.names.values():
        try:
            tokens = F.tokenize(dn.refers_to)
        except F.FormulaError:
            continue
        first = next((t for t in tokens if t.kind == "ref" and t.ref.sheet is not None), None)
        if first is not None:
            homed = first.ref.sheet.lower() == sheet.name.lower()
        else:
            homed = (dn.home if dn.home is not None else dn.sheet) == sheet.id
        if homed:
            out.append([dn.name, dn.refers_to, dn.sheet == sheet.id, dn.comment])
    return out


def load_sheet(sheet, data: dict) -> None:
    """Put a recorded sheet's contents into ``sheet`` (replacing what it
    held), calculated once at the end, with no undo step of its own."""
    wb = sheet.workbook
    journal, wb.journal = wb.journal, False
    try:
        with wb.transaction("Load"):
            for (row, col) in list(sheet.cells):
                wb._set_state(sheet, row, col, ("", 0, None))
            styles = [wb.styles.add(style_from_dict(s)) for s in data.get("styles", [{}])] or [0]
            for entry in data.get("cells", []):
                row, col, text, index = entry[:4]
                comment = entry[4] if len(entry) > 4 else None
                style = styles[index] if 0 <= index < len(styles) else 0
                wb._set_state(sheet, int(row), int(col), (text, style, comment))
            size = data.get("size")
            sheet.size = tuple(size) if size else None
            sheet.widths = {int(k): float(v) for k, v in data.get("widths", {}).items()}
            sheet.heights = {int(k): float(v) for k, v in data.get("heights", {}).items()}
            sheet.hidden_rows = set(data.get("hidden_rows", []))
            sheet.hidden_cols = set(data.get("hidden_cols", []))
            sheet.merges = [tuple(m) for m in data.get("merges", [])]
            sheet.default_width = float(data.get("default_width", sheet.default_width))
            sheet.default_height = float(data.get("default_height", sheet.default_height))
            sheet.show_gridlines = bool(data.get("gridlines", sheet.show_gridlines))
            sheet.show_headings = bool(data.get("headings", sheet.show_headings))
            import copy as _copy
            sheet.cond_rules = _copy.deepcopy(data.get("cond_rules", []))
            sheet.validations = _copy.deepcopy(data.get("validations", []))
            sheet.filter = _copy.deepcopy(data.get("filter"))
            if sheet.filter is not None:
                sheet.filter["criteria"] = {int(k): v for k, v in sheet.filter.get("criteria", {}).items()}
            sheet.filtered_rows = set(data.get("filtered_rows", []))
            sheet.page = _copy.deepcopy(data.get("page", {}))
            for entry in data.get("names", []):
                name, refers_to = entry[0], entry[1]
                local = bool(entry[2]) if len(entry) > 2 else False
                comment = entry[3] if len(entry) > 3 else ""
                key = (name.lower(), sheet.id if local else None)
                if key not in wb.names:
                    from .workbook import DefinedName
                    wb.names[key] = DefinedName(name, refers_to, sheet.id if local else None,
                                                comment or "", sheet.id)
                    wb._name_dirty(key[0])
    finally:
        wb.journal = journal
