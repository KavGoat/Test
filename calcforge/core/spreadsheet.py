"""Spreadsheet engine with dependency-ordered recalculation.

Supports Excel-style formulas, unit-aware cells, and integration
with the calculation variable context.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .units import Quantity, make_quantity, add_quantities, multiply_quantities
from .evaluator import EvalContext


@dataclass
class CellRef:
    col: int
    row: int
    abs_col: bool = False
    abs_row: bool = False

    @property
    def label(self) -> str:
        c = "$" if self.abs_col else ""
        r = "$" if self.abs_row else ""
        return f"{c}{_col_letter(self.col)}{r}{self.row + 1}"


def _col_letter(col: int) -> str:
    result = ""
    c = col
    while True:
        result = chr(ord('A') + c % 26) + result
        c = c // 26 - 1
        if c < 0:
            break
    return result


def _parse_col(s: str) -> int:
    result = 0
    for ch in s.upper():
        result = result * 26 + (ord(ch) - ord('A') + 1)
    return result - 1


_CELL_RE = re.compile(r'(\$?)([A-Za-z]+)(\$?)(\d+)')


def parse_cell_ref(s: str) -> Optional[CellRef]:
    m = _CELL_RE.fullmatch(s.strip())
    if not m:
        return None
    return CellRef(
        col=_parse_col(m.group(2)),
        row=int(m.group(4)) - 1,
        abs_col=bool(m.group(1)),
        abs_row=bool(m.group(3)),
    )


def parse_range(s: str) -> Optional[tuple[CellRef, CellRef]]:
    parts = s.split(':')
    if len(parts) != 2:
        return None
    a = parse_cell_ref(parts[0])
    b = parse_cell_ref(parts[1])
    if a is None or b is None:
        return None
    return (a, b)


@dataclass
class Cell:
    raw: str = ""
    value: Any = None
    display: str = ""
    error: Optional[str] = None
    display_unit: Optional[str] = None
    name: Optional[str] = None

    @property
    def is_formula(self) -> bool:
        return self.raw.startswith("=")

    @property
    def formula(self) -> str:
        return self.raw[1:] if self.is_formula else ""


@dataclass
class Table:
    rows: int = 10
    cols: int = 5
    cells: dict[tuple[int, int], Cell] = field(default_factory=dict)
    col_widths: list[float] = field(default_factory=list)
    row_heights: list[float] = field(default_factory=list)
    publish_columns: bool = False
    col_headers: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.col_widths:
            self.col_widths = [100.0] * self.cols
        if not self.row_heights:
            self.row_heights = [24.0] * self.rows
        if not self.col_headers:
            self.col_headers = [_col_letter(i) for i in range(self.cols)]

    def get_cell(self, row: int, col: int) -> Cell:
        if (row, col) not in self.cells:
            self.cells[(row, col)] = Cell()
        return self.cells[(row, col)]

    def set_cell(self, row: int, col: int, raw: str):
        cell = self.get_cell(row, col)
        cell.raw = raw
        cell.error = None

    def ensure_size(self, rows: int, cols: int):
        if rows > self.rows:
            self.row_heights.extend([24.0] * (rows - self.rows))
            self.rows = rows
        if cols > self.cols:
            self.col_widths.extend([100.0] * (cols - self.cols))
            self.col_headers.extend([_col_letter(i) for i in range(self.cols, cols)])
            self.cols = cols

    def cell_range(self, start: CellRef, end: CellRef) -> list[Cell]:
        cells = []
        for r in range(min(start.row, end.row), max(start.row, end.row) + 1):
            for c in range(min(start.col, end.col), max(start.col, end.col) + 1):
                cells.append(self.get_cell(r, c))
        return cells

    def to_dict(self) -> dict:
        cell_data = {}
        for (r, c), cell in self.cells.items():
            if cell.raw:
                key = f"{r},{c}"
                cell_data[key] = {
                    "raw": cell.raw,
                    "name": cell.name,
                    "display_unit": cell.display_unit,
                }
        return {
            "rows": self.rows,
            "cols": self.cols,
            "cells": cell_data,
            "col_widths": self.col_widths,
            "row_heights": self.row_heights,
            "publish_columns": self.publish_columns,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Table":
        t = cls(
            rows=d.get("rows", 10),
            cols=d.get("cols", 5),
            col_widths=d.get("col_widths", []),
            row_heights=d.get("row_heights", []),
            publish_columns=d.get("publish_columns", False),
        )
        for key, cd in d.get("cells", {}).items():
            r, c = map(int, key.split(","))
            cell = t.get_cell(r, c)
            cell.raw = cd.get("raw", "")
            cell.name = cd.get("name")
            cell.display_unit = cd.get("display_unit")
        return t


_FUNC_RE = re.compile(r'([A-Z_]+)\s*\(', re.IGNORECASE)
_REF_RE = re.compile(r'\$?[A-Za-z]+\$?\d+(?::\$?[A-Za-z]+\$?\d+)?')


class SpreadsheetEvaluator:
    """Evaluates table cells in dependency order."""

    def __init__(self, table: Table, calc_ctx: Optional[EvalContext] = None):
        self.table = table
        self.calc_ctx = calc_ctx or EvalContext()

    def evaluate_all(self):
        for (r, c), cell in self.table.cells.items():
            self._eval_cell(cell, r, c, set())

    def _eval_cell(self, cell: Cell, row: int, col: int, visiting: set):
        if (row, col) in visiting:
            cell.error = "Circular reference"
            cell.display = "#CIRC!"
            return
        if not cell.raw:
            cell.value = None
            cell.display = ""
            return
        if not cell.is_formula:
            cell.value, cell.display = self._parse_literal(cell.raw)
            cell.error = None
            return
        visiting = visiting | {(row, col)}
        try:
            result = self._eval_formula(cell.formula, row, col, visiting)
            cell.value = result
            cell.error = None
            if isinstance(result, Quantity):
                cell.display = repr(result.auto_display())
            elif isinstance(result, bool):
                cell.display = str(result).upper()
            elif isinstance(result, (int, float)):
                cell.display = f"{result:g}"
            else:
                cell.display = str(result)
        except Exception as e:
            cell.error = str(e)
            cell.display = f"#ERR: {e}"

    def _parse_literal(self, raw: str) -> tuple[Any, str]:
        raw = raw.strip()
        try:
            v = float(raw)
            return v, f"{v:g}"
        except ValueError:
            pass
        parts = raw.split()
        if len(parts) == 2:
            try:
                v = float(parts[0])
                from .units import parse_unit
                u = parse_unit(parts[1])
                if u:
                    q = Quantity(v, u, u, True)
                    return q, repr(q)
            except ValueError:
                pass
        if raw.upper() in ("TRUE", "FALSE"):
            return raw.upper() == "TRUE", raw.upper()
        return raw, raw

    def _eval_formula(self, formula: str, row: int, col: int, visiting: set) -> Any:
        formula = formula.strip()
        func_match = _FUNC_RE.match(formula)
        if func_match:
            return self._eval_function(formula, row, col, visiting)
        ref_match = _REF_RE.fullmatch(formula)
        if ref_match:
            return self._resolve_ref(formula, visiting)
        for op in ('>=', '<=', '<>', '!=', '>', '<', '='):
            if op in formula:
                parts = formula.split(op, 1)
                if len(parts) == 2:
                    left = self._eval_formula(parts[0], row, col, visiting)
                    right = self._eval_formula(parts[1], row, col, visiting)
                    return self._compare(left, right, op)
        for op in ('+', '-'):
            idx = formula.rfind(op)
            if idx > 0:
                left = self._eval_formula(formula[:idx], row, col, visiting)
                right = self._eval_formula(formula[idx + 1:], row, col, visiting)
                lv = self._to_float(left)
                rv = self._to_float(right)
                return (lv + rv) if op == '+' else (lv - rv)
        if '*' in formula:
            parts = formula.rsplit('*', 1)
            left = self._eval_formula(parts[0], row, col, visiting)
            right = self._eval_formula(parts[1], row, col, visiting)
            return self._to_float(left) * self._to_float(right)
        if '/' in formula:
            parts = formula.rsplit('/', 1)
            left = self._eval_formula(parts[0], row, col, visiting)
            right = self._eval_formula(parts[1], row, col, visiting)
            rv = self._to_float(right)
            if rv == 0:
                raise ZeroDivisionError("Division by zero")
            return self._to_float(left) / rv
        formula = formula.strip()
        if formula and formula[0] == '(' and formula[-1] == ')':
            return self._eval_formula(formula[1:-1], row, col, visiting)
        try:
            return float(formula)
        except ValueError:
            pass
        if self.calc_ctx:
            val = self.calc_ctx.lookup(formula)
            if val is not None:
                return val.value
        raise ValueError(f"Cannot evaluate: {formula}")

    def _resolve_ref(self, ref_str: str, visiting: set) -> Any:
        ref = parse_cell_ref(ref_str)
        if ref:
            cell = self.table.get_cell(ref.row, ref.col)
            self._eval_cell(cell, ref.row, ref.col, visiting)
            return cell.value if cell.value is not None else 0
        return 0

    def _eval_function(self, formula: str, row: int, col: int, visiting: set) -> Any:
        func_match = _FUNC_RE.match(formula)
        if not func_match:
            raise ValueError(f"Not a function: {formula}")
        name = func_match.group(1).upper()
        inner = formula[func_match.end():]
        depth = 1
        i = 0
        while i < len(inner) and depth > 0:
            if inner[i] == '(':
                depth += 1
            elif inner[i] == ')':
                depth -= 1
            i += 1
        args_str = inner[:i - 1]
        args = self._split_args(args_str)
        if name == "SUM":
            return self._fn_aggregate(args, row, col, visiting, sum)
        if name == "AVERAGE":
            vals = self._fn_collect(args, row, col, visiting)
            return sum(vals) / len(vals) if vals else 0
        if name == "COUNT":
            return len(self._fn_collect(args, row, col, visiting))
        if name == "MIN":
            vals = self._fn_collect(args, row, col, visiting)
            return min(vals) if vals else 0
        if name == "MAX":
            vals = self._fn_collect(args, row, col, visiting)
            return max(vals) if vals else 0
        if name == "ROUND":
            val = self._eval_formula(args[0], row, col, visiting)
            digits = int(self._eval_formula(args[1], row, col, visiting)) if len(args) > 1 else 0
            return round(self._to_float(val), digits)
        if name == "IF":
            cond = self._eval_formula(args[0], row, col, visiting)
            if self._is_truthy(cond):
                return self._eval_formula(args[1], row, col, visiting)
            return self._eval_formula(args[2], row, col, visiting) if len(args) > 2 else 0
        if name == "IFERROR":
            try:
                return self._eval_formula(args[0], row, col, visiting)
            except Exception:
                return self._eval_formula(args[1], row, col, visiting) if len(args) > 1 else 0
        if name == "ABS":
            return abs(self._to_float(self._eval_formula(args[0], row, col, visiting)))
        if name in ("CONCAT", "CONCATENATE"):
            parts = [str(self._eval_formula(a, row, col, visiting)) for a in args]
            return "".join(parts)
        if name == "TEXT":
            val = self._eval_formula(args[0], row, col, visiting)
            return str(val)
        raise ValueError(f"Unknown function: {name}")

    def _fn_aggregate(self, args, row, col, visiting, fn):
        vals = self._fn_collect(args, row, col, visiting)
        return fn(vals) if vals else 0

    def _fn_collect(self, args, row, col, visiting) -> list[float]:
        vals = []
        for a in args:
            rng = parse_range(a.strip())
            if rng:
                cells = self.table.cell_range(rng[0], rng[1])
                for c in cells:
                    if c.raw:
                        ref = parse_cell_ref(f"{_col_letter(0)}{1}")
                        self._eval_cell(c, 0, 0, visiting)
                        if c.value is not None:
                            try:
                                vals.append(self._to_float(c.value))
                            except (ValueError, TypeError):
                                pass
            else:
                val = self._eval_formula(a, row, col, visiting)
                try:
                    vals.append(self._to_float(val))
                except (ValueError, TypeError):
                    pass
        return vals

    def _split_args(self, s: str) -> list[str]:
        args = []
        depth = 0
        current = []
        for ch in s:
            if ch == ',' and depth == 0:
                args.append("".join(current).strip())
                current = []
            else:
                if ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
                current.append(ch)
        if current:
            args.append("".join(current).strip())
        return args

    def _to_float(self, val: Any) -> float:
        if isinstance(val, Quantity):
            return val.value
        if isinstance(val, bool):
            return 1.0 if val else 0.0
        return float(val)

    def _is_truthy(self, val: Any) -> bool:
        if isinstance(val, bool):
            return val
        if isinstance(val, (int, float)):
            return val != 0
        if isinstance(val, str):
            return val.upper() == "TRUE"
        return bool(val)

    def _compare(self, left, right, op: str) -> bool:
        lv = self._to_float(left)
        rv = self._to_float(right)
        ops = {
            '=': lv == rv, '<>': lv != rv, '!=': lv != rv,
            '<': lv < rv, '>': lv > rv,
            '<=': lv <= rv, '>=': lv >= rv,
        }
        return ops.get(op, False)
