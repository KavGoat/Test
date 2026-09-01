"""A unit-aware spreadsheet engine that shares the document's variable workspace.

Cells accept plain numbers, quantities with units (``5 kN``), text, or formulas
beginning with ``=``.  Formulas may reference other cells (``A1``, ``$B$2``),
ranges (``A1:C10``), the usual Excel function set, *and* any variable or
function defined in a math region of the same document.
"""
from __future__ import annotations

import io
import keyword
import re
import string
import tokenize
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Optional

from . import functions as fnlib
from .engine import (Workspace, compile_expression, evaluate_code,
                     friendly_error, normalise)

import ast


class _ConcatOperator(ast.NodeTransformer):
    """Turn Excel's ``&`` string-join operator into a ``concat()`` call."""

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.op, ast.BitAnd):
            return ast.copy_location(
                ast.Call(func=ast.Name(id="concat", ctx=ast.Load()),
                         args=[node.left, node.right], keywords=[]), node)
        return node


SHEET_TRANSFORMERS = (_ConcatOperator(),)
from .units import Quantity, convert, format_quantity, simplify_units, ureg

MAX_COLS = 702          # A .. ZZ
MAX_ROWS = 20000

_REF_RE = re.compile(r"^([A-Za-z]{1,3})([0-9]{1,5})$")
_ABS_RE = re.compile(r"\$([A-Za-z]{1,3})\$?([0-9]{1,5})|([A-Za-z]{1,3})\$([0-9]{1,5})")


def column_letter(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    letters = ""
    index += 1
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = string.ascii_uppercase[remainder] + letters
    return letters


def column_index(letters: str) -> int:
    value = 0
    for char in letters.upper():
        value = value * 26 + (ord(char) - 64)
    return value - 1


def parse_ref(ref: str) -> Optional[tuple[int, int]]:
    """``B3`` -> (row=2, col=1); returns None when the text is not a reference."""
    match = _REF_RE.match(ref.replace("$", ""))
    if not match:
        return None
    return int(match.group(2)) - 1, column_index(match.group(1))


def make_ref(row: int, col: int, abs_row: bool = False, abs_col: bool = False) -> str:
    return f"{'$' if abs_col else ''}{column_letter(col)}{'$' if abs_row else ''}{row + 1}"


# ---------------------------------------------------------------------------
# Spreadsheet-only functions
# ---------------------------------------------------------------------------

def _numbers(values: Iterable[Any]) -> list[Any]:
    out = []
    for value in fnlib._flatten([list(values)]):
        if isinstance(value, str) or value is None or isinstance(value, bool):
            continue
        out.append(value)
    return out


def _blank(value) -> bool:
    return value is None or value == ""


def sheet_sum(*args):
    values = _numbers(args)
    return fnlib.sum_(values) if values else 0


def sheet_average(*args):
    values = _numbers(args)
    return fnlib.mean(values) if values else 0


def sheet_count(*args):
    return len(_numbers(args))


def sheet_counta(*args):
    return len([v for v in fnlib._flatten([list(args)]) if not _blank(v)])


def sheet_countblank(*args):
    return len([v for v in fnlib._flatten([list(args)]) if _blank(v)])


def _match_criterion(value, criterion) -> bool:
    if isinstance(criterion, str):
        text = criterion.strip()
        for operator in (">=", "<=", "<>", "!=", ">", "<", "="):
            if text.startswith(operator):
                target = text[len(operator):].strip()
                try:
                    target_value = float(target)
                    left = value.magnitude if isinstance(value, Quantity) else value
                    left = float(left)
                except (TypeError, ValueError):
                    target_value, left = target, str(value)
                return {
                    ">=": left >= target_value, "<=": left <= target_value,
                    ">": left > target_value, "<": left < target_value,
                    "=": left == target_value, "<>": left != target_value,
                    "!=": left != target_value,
                }[operator]
        return str(value) == text
    return value == criterion


def sheet_sumif(range_values, criterion, sum_values=None):
    source = fnlib._flatten([range_values])
    target = fnlib._flatten([sum_values]) if sum_values is not None else source
    matched = [target[index] for index, value in enumerate(source)
               if index < len(target) and _match_criterion(value, criterion)]
    return fnlib.sum_(matched) if matched else 0


def sheet_countif(range_values, criterion):
    return sum(1 for value in fnlib._flatten([range_values])
               if _match_criterion(value, criterion))


def sheet_sumproduct(*ranges):
    columns = [fnlib._flatten([r]) for r in ranges]
    if not columns:
        return 0
    length = min(len(c) for c in columns)
    total = None
    for index in range(length):
        term = columns[0][index]
        for column in columns[1:]:
            term = term * column[index]
        total = term if total is None else total + term
    return total if total is not None else 0


def sheet_index(values, position, column=None):
    flat = fnlib._flatten([values])
    position = int(fnlib.as_float(position))
    if column is not None:
        # two-dimensional index over a rectangular range is flattened row-major
        raise ValueError("INDEX with two axes needs a rectangular range")
    if not 1 <= position <= len(flat):
        raise IndexError("INDEX position out of range")
    return flat[position - 1]


def sheet_match(needle, values, mode=0):
    flat = fnlib._flatten([values])
    mode = int(fnlib.as_float(mode))
    if mode == 0:
        for index, value in enumerate(flat):
            if value == needle:
                return index + 1
        raise ValueError("MATCH found no exact match")
    best = None
    for index, value in enumerate(flat):
        try:
            if mode == 1 and fnlib._cmp_key(value) <= fnlib._cmp_key(needle):
                best = index + 1
            if mode == -1 and fnlib._cmp_key(value) >= fnlib._cmp_key(needle):
                best = index + 1
        except TypeError:
            continue
    if best is None:
        raise ValueError("MATCH found no match")
    return best


def sheet_vlookup(needle, keys, values, approximate=False):
    key_list = fnlib._flatten([keys])
    value_list = fnlib._flatten([values])
    if approximate:
        best_index = None
        for index, key in enumerate(key_list):
            try:
                if fnlib._cmp_key(key) <= fnlib._cmp_key(needle):
                    best_index = index
            except TypeError:
                continue
        if best_index is None:
            raise ValueError("VLOOKUP found no match")
        return value_list[best_index]
    for index, key in enumerate(key_list):
        if key == needle and index < len(value_list):
            return value_list[index]
    raise ValueError("VLOOKUP found no match")


def sheet_iferror(value, fallback):
    return fallback if isinstance(value, CellError) else value


def sheet_concat(*args):
    parts = []
    for value in fnlib._flatten([list(args)]):
        parts.append(value if isinstance(value, str) else format_quantity(value, 6))
    return "".join(parts)


def sheet_text(value, digits=2):
    return format_quantity(value, int(fnlib.as_float(digits)) + 1, "fixed")


SHEET_FUNCTIONS: dict[str, Any] = {
    "sum": sheet_sum, "average": sheet_average, "count": sheet_count,
    "counta": sheet_counta, "countblank": sheet_countblank,
    "sumif": sheet_sumif, "countif": sheet_countif, "sumproduct": sheet_sumproduct,
    "index": sheet_index, "match": sheet_match, "vlookup": sheet_vlookup,
    "iferror": sheet_iferror, "concat": sheet_concat, "concatenate": sheet_concat,
    "text": sheet_text, "len": lambda v: len(str(v)),
    "upper": lambda v: str(v).upper(), "lower": lambda v: str(v).lower(),
    "trim": lambda v: str(v).strip(),
    "sumsq": lambda *a: fnlib.sum_([v * v for v in _numbers(a)]),
}

# Everything callable from a cell, keyed lower-case for case-insensitive lookup.
CELL_FUNCTION_NAMES = {name.lower() for name in fnlib.FUNCTIONS} | set(SHEET_FUNCTIONS)


class CellError(Exception):
    """Marker value stored in a cell whose formula failed."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code
        self.detail = detail

    def __str__(self) -> str:
        return self.code


# ---------------------------------------------------------------------------
# Cells
# ---------------------------------------------------------------------------

@dataclass
class CellFormat:
    bold: bool = False
    italic: bool = False
    align: str = "auto"            # auto | left | center | right
    background: str = ""
    color: str = ""
    digits: Optional[int] = None
    number_format: str = ""        # '' inherits, else auto/fixed/scientific/engineering
    unit: str = ""                 # display-unit override
    border_top: bool = False
    border_bottom: bool = False
    border_left: bool = False
    border_right: bool = False
    wrap: bool = False

    def is_default(self) -> bool:
        return self == CellFormat()

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v not in (False, "", None)}

    @classmethod
    def from_dict(cls, data: dict) -> "CellFormat":
        known = {f: data[f] for f in cls.__dataclass_fields__ if f in data}
        return cls(**known)


@dataclass
class Cell:
    raw: str = ""
    value: Any = None
    error: str = ""
    fmt: CellFormat = field(default_factory=CellFormat)

    @property
    def is_formula(self) -> bool:
        return self.raw.startswith("=")

    @property
    def blank(self) -> bool:
        return not self.raw.strip()


# ---------------------------------------------------------------------------
# Formula preparation
# ---------------------------------------------------------------------------

def _strip_absolute(text: str) -> str:
    return re.sub(r"\$(?=[A-Za-z0-9])", "", text)


def prepare_formula(body: str, rows: int, cols: int) -> tuple[str, set[tuple[int, int]]]:
    """Rewrite cell/range references into resolver calls and collect dependencies."""
    body = _strip_absolute(normalise(body))
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(body).readline))
    except (tokenize.TokenError, IndentationError):
        return body, set()

    usable = [t for t in tokens if t.type not in (
        tokenize.ENCODING, tokenize.NEWLINE, tokenize.NL, tokenize.INDENT,
        tokenize.DEDENT, tokenize.ENDMARKER, tokenize.COMMENT)]

    output: list[str] = []
    dependencies: set[tuple[int, int]] = set()
    index = 0
    while index < len(usable):
        token = usable[index]
        text = token.string
        if token.type == tokenize.NAME:
            ref = parse_ref(text)
            is_ref = ref is not None and 0 <= ref[0] < rows and 0 <= ref[1] < cols
            following = usable[index + 1] if index + 1 < len(usable) else None
            after = usable[index + 2] if index + 2 < len(usable) else None
            # range: A1:B5
            if (is_ref and following is not None and following.string == ":"
                    and after is not None and after.type == tokenize.NAME):
                end = parse_ref(after.string)
                if end is not None:
                    r0, c0 = ref
                    r1, c1 = end
                    for row in range(min(r0, r1), min(max(r0, r1), rows - 1) + 1):
                        for col in range(min(c0, c1), min(max(c0, c1), cols - 1) + 1):
                            dependencies.add((row, col))
                    output.append(f'_range({r0},{c0},{r1},{c1})')
                    index += 3
                    continue
            if is_ref:
                dependencies.add(ref)
                output.append(f'_cell({ref[0]},{ref[1]})')
                index += 1
                continue
            # Case-insensitive function names: SUM(...) -> sum(...).  Names that
            # collide with Python keywords use their underscore alias: IF -> if_.
            lowered = text.lower()
            if following is not None and following.string == "(" and lowered in CELL_FUNCTION_NAMES:
                if keyword.iskeyword(lowered):
                    output.append(lowered + "_")
                    index += 1
                    continue
                if text != lowered:
                    output.append(lowered)
                    index += 1
                    continue
        elif token.type == tokenize.OP:
            # Excel comparison spellings: "=" means equality, "<>" means not-equal.
            following = usable[index + 1] if index + 1 < len(usable) else None
            if text == "<" and following is not None and following.string == ">":
                output.append("!=")
                index += 2
                continue
            if text == "=":
                previous = output[-1] if output else ""
                if previous not in ("<", ">", "!", "="):
                    output.append("==")
                    index += 1
                    continue
        output.append(text)
        index += 1
    return " ".join(output), dependencies


def parse_literal(raw: str, workspace: Optional[Workspace] = None) -> Any:
    """Interpret a non-formula entry as a number, quantity, boolean or text."""
    text = raw.strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered in ("true", "yes"):
        return True
    if lowered in ("false", "no"):
        return False
    try:
        if re.fullmatch(r"[-+]?\d+", text):
            return int(text)
        return float(text)
    except ValueError:
        pass
    if re.fullmatch(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?\s*%", text):
        return float(text.rstrip("%").strip()) / 100.0
    # A quantity such as "5 kN" or "2.4 kN/m^2"
    if re.match(r"^[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?\s*[A-Za-zΩμ°]", text):
        try:
            value = ureg.parse_expression(text.replace("^", "**"))
            if isinstance(value, (int, float, Quantity)):
                return value
        except Exception:
            pass
    return text


# ---------------------------------------------------------------------------
# Sheet
# ---------------------------------------------------------------------------

DEFAULT_COL_WIDTH = 74.0
DEFAULT_ROW_HEIGHT = 17.0


class Sheet:
    """A rectangular grid of cells with dependency-ordered recalculation."""

    def __init__(self, rows: int = 8, cols: int = 5):
        self.rows = max(1, min(rows, MAX_ROWS))
        self.cols = max(1, min(cols, MAX_COLS))
        self.cells: dict[tuple[int, int], Cell] = {}
        self.col_widths: dict[int, float] = {}
        self.row_heights: dict[int, float] = {}
        self.header_row = True
        self.banded = False
        self.grid_lines = True
        self.digits = 4
        self.number_format = "auto"
        self.column_units: dict[int, str] = {}
        self.frozen_header = True

    # -- structure ---------------------------------------------------------
    def col_width(self, col: int) -> float:
        return self.col_widths.get(col, DEFAULT_COL_WIDTH)

    def row_height(self, row: int) -> float:
        return self.row_heights.get(row, DEFAULT_ROW_HEIGHT)

    def total_width(self) -> float:
        return sum(self.col_width(c) for c in range(self.cols))

    def total_height(self) -> float:
        return sum(self.row_height(r) for r in range(self.rows))

    def cell(self, row: int, col: int, create: bool = False) -> Cell:
        key = (row, col)
        found = self.cells.get(key)
        if found is None:
            found = Cell()
            if create:
                self.cells[key] = found
        return found

    def set_raw(self, row: int, col: int, raw: str) -> None:
        key = (row, col)
        if not raw.strip() and key in self.cells and self.cells[key].fmt.is_default():
            del self.cells[key]
            return
        cell = self.cells.setdefault(key, Cell())
        cell.raw = raw

    def raw(self, row: int, col: int) -> str:
        cell = self.cells.get((row, col))
        return cell.raw if cell else ""

    def value(self, row: int, col: int) -> Any:
        cell = self.cells.get((row, col))
        return cell.value if cell else None

    def insert_rows(self, at: int, count: int = 1) -> None:
        moved: dict[tuple[int, int], Cell] = {}
        for (row, col), cell in self.cells.items():
            moved[(row + count if row >= at else row, col)] = cell
        self.cells = moved
        heights = {}
        for row, height in self.row_heights.items():
            heights[row + count if row >= at else row] = height
        self.row_heights = heights
        self.rows += count

    def insert_cols(self, at: int, count: int = 1) -> None:
        moved: dict[tuple[int, int], Cell] = {}
        for (row, col), cell in self.cells.items():
            moved[(row, col + count if col >= at else col)] = cell
        self.cells = moved
        widths = {}
        for col, width in self.col_widths.items():
            widths[col + count if col >= at else col] = width
        self.col_widths = widths
        units = {}
        for col, unit in self.column_units.items():
            units[col + count if col >= at else col] = unit
        self.column_units = units
        self.cols += count

    def delete_rows(self, at: int, count: int = 1) -> None:
        count = min(count, self.rows - 1)
        if count <= 0:
            return
        moved: dict[tuple[int, int], Cell] = {}
        for (row, col), cell in self.cells.items():
            if at <= row < at + count:
                continue
            moved[(row - count if row >= at + count else row, col)] = cell
        self.cells = moved
        self.row_heights = {(r - count if r >= at + count else r): h
                            for r, h in self.row_heights.items()
                            if not at <= r < at + count}
        self.rows -= count

    def delete_cols(self, at: int, count: int = 1) -> None:
        count = min(count, self.cols - 1)
        if count <= 0:
            return
        moved: dict[tuple[int, int], Cell] = {}
        for (row, col), cell in self.cells.items():
            if at <= col < at + count:
                continue
            moved[(row, col - count if col >= at + count else col)] = cell
        self.cells = moved
        self.col_widths = {(c - count if c >= at + count else c): w
                           for c, w in self.col_widths.items()
                           if not at <= c < at + count}
        self.column_units = {(c - count if c >= at + count else c): u
                             for c, u in self.column_units.items()
                             if not at <= c < at + count}
        self.cols -= count

    def resize(self, rows: int, cols: int) -> None:
        rows = max(1, min(rows, MAX_ROWS))
        cols = max(1, min(cols, MAX_COLS))
        self.cells = {(r, c): cell for (r, c), cell in self.cells.items()
                      if r < rows and c < cols}
        self.rows, self.cols = rows, cols

    # -- fill --------------------------------------------------------------
    def translate_formula(self, formula: str, delta_row: int, delta_col: int) -> str:
        """Shift relative references in *formula* (used by fill down / right)."""
        if not formula.startswith("="):
            return formula
        def replace(match: re.Match) -> str:
            text = match.group(0)
            abs_col = text.startswith("$")
            body = text[1:] if abs_col else text
            if "$" in body:
                letters, digits = body.split("$")
                abs_row = True
            else:
                m = _REF_RE.match(body)
                if not m:
                    return text
                letters, digits = m.group(1), m.group(2)
                abs_row = False
            col = column_index(letters) + (0 if abs_col else delta_col)
            row = int(digits) - 1 + (0 if abs_row else delta_row)
            if row < 0 or col < 0:
                return "#REF!"
            return make_ref(row, col, abs_row, abs_col)
        return "=" + re.sub(r"\$?[A-Za-z]{1,3}\$?[0-9]{1,5}", replace, formula[1:])

    def fill(self, source: tuple[int, int], targets: list[tuple[int, int]]) -> None:
        origin = self.cells.get(source)
        if origin is None:
            return
        for row, col in targets:
            raw = self.translate_formula(origin.raw, row - source[0], col - source[1])
            self.set_raw(row, col, raw)
            cell = self.cells.get((row, col))
            if cell is not None:
                cell.fmt = CellFormat.from_dict(origin.fmt.to_dict())

    # -- evaluation --------------------------------------------------------
    def recalculate(self, workspace: Optional[Workspace] = None) -> None:
        """Evaluate every cell in dependency order, flagging circular chains."""
        workspace = workspace or Workspace()
        formulas: dict[tuple[int, int], tuple[str, set[tuple[int, int]]]] = {}

        for key, cell in self.cells.items():
            cell.error = ""
            if cell.is_formula:
                body = cell.raw[1:]
                prepared, dependencies = prepare_formula(body, self.rows, self.cols)
                formulas[key] = (prepared, dependencies)
                cell.value = None
            else:
                cell.value = parse_literal(cell.raw, workspace)

        order, cyclic = _topological_order(formulas)
        for key in cyclic:
            cell = self.cells[key]
            cell.value = CellError("#CIRC", "circular reference")
            cell.error = "Circular reference"

        resolver = _Resolver(self)
        for key in order:
            cell = self.cells[key]
            prepared, _deps = formulas[key]
            try:
                code, _tree = compile_expression(prepared, SHEET_TRANSFORMERS)
                namespace = workspace.namespace()
                namespace.update(SHEET_FUNCTIONS)
                namespace["_cell"] = resolver.cell_value
                namespace["_range"] = resolver.range_values
                workspace.resolve_units(code, namespace)
                value = evaluate_code(code, namespace)
                unit = self.cell_unit(*key)
                if unit and isinstance(value, Quantity):
                    value = convert(value, unit)
                else:
                    value = simplify_units(value)
                cell.value = value
            except CellError as exc:
                cell.value = exc
                cell.error = exc.detail or exc.code
            except Exception as exc:  # noqa: BLE001
                cell.value = CellError("#ERR", friendly_error(exc))
                cell.error = friendly_error(exc)

    def cell_unit(self, row: int, col: int) -> str:
        cell = self.cells.get((row, col))
        if cell is not None and cell.fmt.unit:
            return cell.fmt.unit
        return self.column_units.get(col, "")

    def display_text(self, row: int, col: int) -> str:
        cell = self.cells.get((row, col))
        if cell is None or cell.blank:
            return ""
        value = cell.value
        if isinstance(value, CellError):
            return value.code
        if value is None:
            return cell.raw
        if isinstance(value, str):
            return value
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        digits = cell.fmt.digits if cell.fmt.digits is not None else self.digits
        mode = cell.fmt.number_format or self.number_format
        unit = self.cell_unit(row, col)
        return format_quantity(value, digits, mode, unit or None, thousands=True)

    # -- variable publishing ----------------------------------------------
    def header_name(self, col: int) -> str:
        if not self.header_row:
            return ""
        raw = self.raw(0, col).strip()
        cleaned = re.sub(r"[^\w]", "_", raw).strip("_")
        if cleaned and not cleaned[0].isdigit():
            return cleaned
        return ""

    def column_values(self, col: int, skip_header: bool = True) -> list[Any]:
        start = 1 if (skip_header and self.header_row) else 0
        values = []
        for row in range(start, self.rows):
            cell = self.cells.get((row, col))
            if cell is None or cell.blank:
                continue
            if isinstance(cell.value, CellError):
                continue
            values.append(cell.value)
        return values

    # -- serialisation -----------------------------------------------------
    def to_dict(self) -> dict:
        cells = {}
        for (row, col), cell in self.cells.items():
            entry: dict[str, Any] = {}
            if cell.raw:
                entry["raw"] = cell.raw
            fmt = cell.fmt.to_dict()
            if fmt:
                entry["fmt"] = fmt
            if entry:
                cells[f"{row},{col}"] = entry
        return {
            "rows": self.rows, "cols": self.cols, "cells": cells,
            "col_widths": {str(k): v for k, v in self.col_widths.items()},
            "row_heights": {str(k): v for k, v in self.row_heights.items()},
            "column_units": {str(k): v for k, v in self.column_units.items()},
            "header_row": self.header_row, "banded": self.banded,
            "grid_lines": self.grid_lines, "digits": self.digits,
            "number_format": self.number_format,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Sheet":
        sheet = cls(int(data.get("rows", 8)), int(data.get("cols", 5)))
        for key, entry in data.get("cells", {}).items():
            row, col = (int(part) for part in key.split(","))
            cell = Cell(raw=entry.get("raw", ""))
            cell.fmt = CellFormat.from_dict(entry.get("fmt", {}))
            sheet.cells[(row, col)] = cell
        sheet.col_widths = {int(k): float(v) for k, v in data.get("col_widths", {}).items()}
        sheet.row_heights = {int(k): float(v) for k, v in data.get("row_heights", {}).items()}
        sheet.column_units = {int(k): v for k, v in data.get("column_units", {}).items()}
        sheet.header_row = bool(data.get("header_row", True))
        sheet.banded = bool(data.get("banded", False))
        sheet.grid_lines = bool(data.get("grid_lines", True))
        sheet.digits = int(data.get("digits", 4))
        sheet.number_format = data.get("number_format", "auto")
        return sheet


class _Resolver:
    """Supplies cell and range values to compiled formulas."""

    def __init__(self, sheet: Sheet):
        self.sheet = sheet

    def cell_value(self, row: int, col: int) -> Any:
        cell = self.sheet.cells.get((row, col))
        if cell is None or cell.blank:
            return 0
        if isinstance(cell.value, CellError):
            raise CellError(cell.value.code, cell.value.detail)
        return cell.value if cell.value is not None else 0

    def range_values(self, r0: int, c0: int, r1: int, c1: int) -> list[Any]:
        values = []
        for row in range(min(r0, r1), max(r0, r1) + 1):
            for col in range(min(c0, c1), max(c0, c1) + 1):
                cell = self.sheet.cells.get((row, col))
                if cell is None or cell.blank:
                    continue
                if isinstance(cell.value, CellError):
                    raise CellError(cell.value.code, cell.value.detail)
                values.append(cell.value)
        return values


def _topological_order(formulas: dict[tuple[int, int], tuple[str, set]]
                       ) -> tuple[list[tuple[int, int]], set]:
    """Order formula cells so dependencies evaluate first; detect cycles."""
    order: list[tuple[int, int]] = []
    state: dict[tuple[int, int], int] = {}     # 0 visiting, 1 done
    cyclic: set = set()

    def visit(key, stack: set) -> None:
        if state.get(key) == 1 or key in cyclic:
            return
        if key in stack:
            cyclic.update(stack)
            cyclic.add(key)
            return
        if key not in formulas:
            return
        stack.add(key)
        for dependency in formulas[key][1]:
            if dependency in formulas:
                visit(dependency, stack)
        stack.discard(key)
        if key not in cyclic:
            state[key] = 1
            order.append(key)

    for key in list(formulas):
        visit(key, set())
    return [k for k in order if k not in cyclic], cyclic
