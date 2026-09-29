"""The worksheet: regions on a page, evaluated in reading order.

SMath evaluates regions top to bottom (then left to right); a region only
sees definitions from regions before it, so moving a line above the
definition it uses makes it fail with "x - not defined.".  Evaluation runs
after every edit (auto calculation), which is why a result appears the moment
``=`` is typed.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Optional

from .editor import MathEditor
from .engine import ast as A
from .engine.display import display_value
from .engine.errors import SMathError, err
from .engine.evaluator import Context, Evaluator
from .engine.numformat import NumberFormat
from .engine.parser import ParseError, parse_row
from .engine.model import Row
from .engine.units import Quantity, unit_offset
from .engine.values import Matrix, Q, need_scalar

_ids = itertools.count(1)


@dataclass
class Region:
    x: float
    y: float
    editor: MathEditor = None
    id: int = field(default_factory=lambda: next(_ids))
    # results of the last calculation
    value: object = None  # evaluated value (for "=" regions)
    display: object = None  # display structure of the result
    error: Optional[SMathError] = None
    enabled: bool = True
    fmt: Optional[NumberFormat] = None  # per-region override

    @property
    def kind(self) -> str:
        return self.editor.kind

    def expression_row(self) -> Row:
        r = Row()
        r.items = list(self.editor.expression_items())
        return r


class Worksheet:
    def __init__(self):
        self.regions: list[Region] = []
        self.format = NumberFormat()
        self.auto_calculation = True
        self.evaluator = Evaluator()
        self.context = Context()

    # -- regions ----------------------------------------------------------------
    def add_region(self, x: float, y: float, editor: Optional[MathEditor] = None) -> Region:
        r = Region(x, y)
        r.editor = editor or MathEditor()
        r.editor.is_defined = lambda name, nargs=None, reg=r: self.is_defined_before(reg, name, nargs)
        self.regions.append(r)
        return r

    def remove_region(self, region: Region) -> None:
        self.regions.remove(region)

    def ordered(self) -> list[Region]:
        return sorted(self.regions, key=lambda r: (r.y, r.x))

    # -- definitions visible to a region -----------------------------------------
    def is_defined_before(self, region: Region, name: str, nargs=None) -> bool:
        from .engine import builtins
        from .engine.evaluator import BUILTIN_CONSTANTS

        ctx = self._context_before(region)
        if nargs is None:
            return ctx.has(name) or name in BUILTIN_CONSTANTS
        if ctx.function(name, nargs) is not None:
            return True
        return builtins.has_overload(name, nargs)

    def _context_before(self, region: Region) -> Context:
        ctx = Context()
        for r in self.ordered():
            if r is region:
                break
            self._run(r, ctx, record=False)
        return ctx

    # -- calculation ----------------------------------------------------------------
    def calculate(self) -> None:
        ctx = Context()
        for r in self.ordered():
            self._run(r, ctx, record=True)
        self.context = ctx

    def _run(self, r: Region, ctx: Context, record: bool) -> None:
        if record:
            r.value = r.display = r.error = None
        if r.kind != "math" or not r.enabled:
            return
        items = r.editor.expression_items()
        if not items:
            return
        expr_row = r.expression_row()
        try:
            node = parse_row(expr_row)
        except ParseError as e:
            if record:
                r.error = SMathError("Syntax is incorrect.", None)
                r.error.src = _rebase(e.src, expr_row, r.editor.root)
            return
        # the expression row is a copy of the root's items: point error
        # locations back at the editor's own row so they can be drawn
        for n in A.walk(node):
            if n.src is not None:
                n.src = _rebase(n.src, expr_row, r.editor.root)
        try:
            if isinstance(node, A.Define):
                self.evaluator.define(node, ctx)
                return
            if not r.editor.evaluate:
                # a bare expression is still evaluated (errors are shown)
                if record and not isinstance(node, A.Placeholder):
                    self.evaluator.eval(node, ctx)
                return
            value = self.evaluator.eval(node, ctx)
            if record:
                r.value = value
                r.display = self._display(r, value, ctx)
        except SMathError as e:
            if record:
                r.error = e

    def _display(self, r: Region, value, ctx: Context):
        fmt = r.fmt or self.format
        unit_row = r.editor.unit
        if unit_row.is_empty():
            return display_value(value, fmt)
        unode = parse_row(unit_row)
        uval = need_scalar(self.evaluator.eval(unode, ctx))
        q = value
        # non-linear temperature units (°C, °F): subtract the offset
        offset = 0.0
        if isinstance(unode, A.UnitRef):
            offset = unit_offset(unode.name)
        if isinstance(q, Quantity):
            if q.dims != uval.dims:
                raise err("units_mismatch", node=unode)
            shown = Q((q.value - offset) / uval.value)
            return display_value(shown, fmt)
        if isinstance(q, Matrix):
            if any(x.dims != uval.dims for x in q.items):
                raise err("units_mismatch", node=unode)
            return display_value(Matrix(q.nrows, q.ncols, [Q((x.value - offset) / uval.value) for x in q.items]), fmt)
        return display_value(value, fmt)

    def calculate_region(self, region: Region) -> None:
        """Re-evaluate one region against what is defined above it.

        Observed on SMath Cloud: while a region is being edited only that
        region is recalculated (its result follows every keystroke); the rest
        of the worksheet is recalculated when the region loses focus.
        """
        ctx = self._context_before(region)
        self._run(region, ctx, record=True)

    def recalc_if_auto(self) -> None:
        if self.auto_calculation:
            self.calculate()


def _rebase(src, old: Row, new: Row):
    if src is not None and src[0] is old:
        return (new, src[1], src[2])
    return src
