"""An equation's editable source, as plain JSON for the document record.

CalcForge saves no ``.sm`` files (decision 2). What it keeps instead, inside
the PDF's embedded record, is exactly what the equation editor edits: the tree
of rows and boxes (fractions, powers, matrices, program blocks…), the unit box
after the result, and every per-equation option SMath has — format,
evaluation, units, font and colour — plus a plot's view. Reading it back gives
the same editor state, so the same parse and the same result.

A row is a list; a one-character token stays a string; a box is a dict naming
its kind, its child rows and any attributes of its own (a matrix's size, a
program block's name).
"""
from __future__ import annotations

from dataclasses import asdict, fields
from typing import Optional

from .editor import MathEditor
from .engine.model import Abs, Box, Frac, Index, Matrix, Paren, Pow, Program, Root, Row, Sqrt
from .engine.numformat import NumberFormat
from .plot import PlotState

FORMAT_VERSION = 1

_BOXES = {cls.kind: cls for cls in (Frac, Pow, Index, Sqrt, Root, Paren, Abs, Matrix, Program)}
# Attributes every box carries that are structure, not data.
_STRUCTURE = {"rows", "parent_row", "parent"}
_SCALARS = (str, int, float, bool, type(None))


def row_to_data(row: Row) -> list:
    out = []
    for item in row.items:
        if isinstance(item, str):
            out.append(item)
            continue
        box = {"b": item.kind, "r": [row_to_data(r) for r in item.rows]}
        extra = {k: v for k, v in item.__dict__.items()
                 if k not in _STRUCTURE and isinstance(v, _SCALARS)}
        if extra:
            box["a"] = extra
        out.append(box)
    return out


def row_from_data(data: list) -> Row:
    row = Row()
    for item in data:
        if isinstance(item, str):
            row.append(item)
            continue
        cls = _BOXES[item["b"]]
        rows = [row_from_data(r) for r in item.get("r", [])]
        box = object.__new__(cls)
        Box.__init__(box, *rows)
        for key, value in item.get("a", {}).items():
            setattr(box, key, value)
        row.append(box)
    return row


# The region options that belong to the equation, with SMath's defaults.
_REGION_FIELDS = ("enabled", "show_input", "ignore_units", "optimization", "font_size",
                  "font_family", "bold", "italic", "underline", "color", "bg_color",
                  "border", "text_width")


def region_to_data(region) -> dict:
    """Everything needed to rebuild *region*, except where it sits."""
    editor = region.editor
    data = {
        "v": FORMAT_VERSION,
        "kind": editor.kind,
        "root": row_to_data(editor.root),
        "unit": row_to_data(editor.unit),
    }
    if editor.kind == "text":
        data["text"] = editor.text
    if editor.confirmed_words:
        data["confirmed"] = sorted(editor.confirmed_words)
    if editor.plot_input:
        data["plot_input"] = True
    for name in _REGION_FIELDS:
        data[name] = getattr(region, name)
    if region.fmt is not None:
        data["fmt"] = asdict(region.fmt)
    if region.plot is not None:
        data["plot"] = asdict(region.plot)
    if region.line_runs:
        data["line_runs"] = [[[t, dict(st or {})] for t, st in line] for line in region.line_runs]
    return data


def editor_from_data(data: dict, is_defined=None) -> MathEditor:
    editor = MathEditor(row_from_data(data.get("root", [])), is_defined=is_defined)
    editor.unit = row_from_data(data.get("unit", []))
    MathEditor._fix_parents(editor.unit)
    editor.kind = data.get("kind", "math")
    editor.text = data.get("text", "")
    editor.text_pos = len(editor.text)
    editor.evaluate = any(item == "=" for item in editor.root.items)
    editor.confirmed_words = set(data.get("confirmed", ()))
    editor.plot_input = bool(data.get("plot_input", False))
    editor.cursor.row = editor.root
    editor.cursor.pos = len(editor.root)
    return editor


def apply_region_data(region, data: dict) -> None:
    """Set *region*'s options from *data* (its editor is built separately)."""
    for name in _REGION_FIELDS:
        if name in data:
            setattr(region, name, data[name])
    fmt = data.get("fmt")
    region.fmt = None if fmt is None else NumberFormat(
        **{f.name: fmt[f.name] for f in fields(NumberFormat) if f.name in fmt})
    plot = data.get("plot")
    region.plot = None if plot is None else PlotState(
        **{f.name: plot[f.name] for f in fields(PlotState) if f.name in plot})
    region.line_runs = [[(t, st) for t, st in line] for line in data.get("line_runs", [])]


def add_region_from_data(worksheet, x: float, y: float, data: dict):
    """A new region on *worksheet* at worksheet position (x, y), from *data*."""
    editor = editor_from_data(data)
    if data.get("plot") is not None:
        editor.plot_input = True
    # add_region wires the editor's is_defined to this region's place in the
    # reading order, which is what decides whether "=" defines or evaluates
    region = worksheet.add_region(x, y, editor)
    apply_region_data(region, data)
    return region


def region_text(data: dict) -> Optional[str]:
    """The equation as linear text (for search and plain-text copying)."""
    if data.get("kind") == "text":
        return data.get("text", "")
    from .engine.model import to_text
    return to_text(row_from_data(data.get("root", [])))


def defined_names(payloads) -> set:
    """The variable and function names the equations in *payloads* (saved
    ``calc`` items) define — what goes undefined if they go."""
    from .worksheet import Worksheet

    worksheet = Worksheet()
    for order, payload in enumerate(payloads):
        data = payload.get("calc") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            continue
        try:
            add_region_from_data(worksheet, 0.0, order * 100.0, data)
        except Exception:                              # noqa: BLE001
            continue
    worksheet.calculate()                  # what a region defines is known once it has run
    names: set = set()
    for region in worksheet.regions:
        names |= set(region.defined_vars) | {name for name, _ in region.defined_funcs}
    return names
