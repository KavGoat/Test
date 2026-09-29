"""The worksheet: regions on a page, evaluated in reading order.

SMath evaluates regions top to bottom (then left to right); a region only
sees definitions from regions before it, so moving a line above the
definition it uses makes it fail with "x - not defined.".

Recalculation follows SMath Cloud: the region being edited is re-evaluated on
every keystroke; when it is left, the worksheet is brought up to date.  To
stay instant on worksheets with thousands of regions, definitions live in a
:class:`DefinitionIndex` keyed by reading order, every region remembers the
names it uses and defines, and leaving a region re-evaluates only the regions
below it that depend (directly or through other definitions) on what changed.
"""
from __future__ import annotations

import bisect
import itertools
from dataclasses import dataclass, field
from typing import Optional

from .editor import MathEditor
from .engine import ast as A
from .engine.display import display_value
from .engine.errors import SMathError, err
from .engine.evaluator import Context, DefinitionIndex, Evaluator, IndexedContext
from .engine.numformat import NumberFormat
from .engine.parser import ParseError, parse_row
from .engine.model import Program, Row
from .engine.units import Quantity, unit_offset
from .engine.values import Matrix, Q, need_scalar
from .plot import PlotState

_ids = itertools.count(1)


@dataclass(eq=False)
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
    plot: Optional[PlotState] = None  # set for 2-D plot regions
    curves: list = field(default_factory=list)  # parsed plot inputs
    plot_ctx: object = None  # definitions visible to the plot
    # bookkeeping for incremental recalculation
    defined_vars: dict = field(default_factory=dict)
    defined_funcs: dict = field(default_factory=dict)
    uses: frozenset = frozenset()

    @property
    def key(self):
        return (self.y, self.x, self.id)

    @property
    def kind(self) -> str:
        return "plot" if self.plot is not None else self.editor.kind

    def plot_rows(self) -> list:
        """The plot's input expressions (one row per curve)."""
        items = self.editor.root.items
        if len(items) == 1 and isinstance(items[0], Program) and items[0].name == "sys":
            return items[0].rows
        return [self.editor.root]

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
        self.index = DefinitionIndex()
        self.changed: set = set()  # ids of regions whose shown result changed
        self._keys: dict = {}  # region id -> key it was indexed under
        self._order_cache = None
        self._order_keys: list = []

    # -- regions ----------------------------------------------------------------
    def add_region(self, x: float, y: float, editor: Optional[MathEditor] = None) -> Region:
        r = Region(x, y)
        r.editor = editor or MathEditor()
        r.editor.is_defined = lambda name, nargs=None, reg=r: self.is_defined_before(reg, name, nargs)
        self.regions.append(r)
        if self._order_cache is not None:
            i = bisect.bisect_left(self._order_keys, r.key)
            self._order_cache.insert(i, r)
            self._order_keys.insert(i, r.key)
        return r

    def add_plot(self, x: float, y: float) -> Region:
        """A new 2-D plot with an empty input (typing a comma adds curves)."""
        ed = MathEditor(Row([Program("sys", Row())]))
        ed.plot_input = True
        MathEditor._fix_parents(ed.root)
        ed.set_cursor(ed.root.items[0].rows[0], 0)
        r = self.add_region(x, y, ed)
        r.plot = PlotState()
        return r

    def remove_region(self, region: Region) -> None:
        self.regions.remove(region)
        self._order_cache = None

    def ordered(self) -> list[Region]:
        """Regions in reading order (cached; rebuilt after moves/removals)."""
        if self._order_cache is None:
            self._order_cache = sorted(self.regions, key=lambda r: r.key)
            self._order_keys = [r.key for r in self._order_cache]
        return self._order_cache

    def invalidate_order(self) -> None:
        self._order_cache = None

    # -- definitions visible to a region -----------------------------------------
    def is_defined_before(self, region: Region, name: str, nargs=None) -> bool:
        from .engine import builtins
        from .engine.evaluator import BUILTIN_CONSTANTS

        key = region.key
        if nargs is None:
            return self.index.var_before(name, key) is not None or name in BUILTIN_CONSTANTS
        if self.index.func_before(name, nargs, key) is not None:
            return True
        return builtins.has_overload(name, nargs)

    def _context_before(self, region: Region) -> Context:
        return IndexedContext(self.index, region.key)

    @property
    def context(self) -> Context:
        """Everything defined anywhere on the page (for styling)."""
        return IndexedContext(self.index, (float("inf"),))

    # -- calculation ----------------------------------------------------------------
    def calculate(self) -> None:
        """Recalculate the whole page from scratch (F9, loading, moving regions)."""
        self.index.clear()
        self._keys.clear()
        self.invalidate_order()
        for r in self.ordered():
            self._evaluate(r, commit=True)

    def calculate_region(self, region: Region) -> None:
        """Re-evaluate one region against what is defined above it.

        Observed on SMath Cloud: while a region is being edited only that
        region is recalculated (its result follows every keystroke); the rest
        of the worksheet is recalculated when the region loses focus.
        """
        self._evaluate(region, commit=False)

    def update_after_edit(self, region: Region) -> None:
        """Bring the page up to date after a region was edited and left.

        Only regions after it that use a name whose definition changed are
        re-evaluated; a region that is re-evaluated passes on the names it
        defines, so chains of definitions update in one pass.
        """
        # a moved region changes the reading order: recalculate everything
        if self._keys.get(region.id) not in (None, region.key) or region not in self.regions:
            self.calculate()
            return
        before = set(region.defined_vars) | {n for n, _ in region.defined_funcs}
        self._evaluate(region, commit=True)
        changed = before | set(region.defined_vars) | {n for n, _ in region.defined_funcs}
        self._propagate(region.key, changed)

    def region_removed(self, region: Region) -> None:
        key = self._keys.pop(region.id, None)
        if key is None:
            return
        self.index.remove(key, region.defined_vars, region.defined_funcs)
        changed = set(region.defined_vars) | {n for n, _ in region.defined_funcs}
        self._propagate(key, changed)

    def _propagate(self, key, changed: set) -> None:
        if not changed:
            return
        order = self.ordered()
        start = bisect.bisect_right(self._order_keys, key)
        for r in order[start:]:
            if r.uses & changed:
                self._evaluate(r, commit=True)
                changed |= set(r.defined_vars) | {n for n, _ in r.defined_funcs}

    def _evaluate(self, r: Region, commit: bool) -> None:
        before = (_shown(r.display), r.error.message if r.error else None)
        if commit and r.id in self._keys:
            self.index.remove(self._keys.pop(r.id), r.defined_vars, r.defined_funcs)
        ctx = IndexedContext(self.index, r.key)
        self._run(r, ctx, record=True)
        if commit:
            r.defined_vars, r.defined_funcs = dict(ctx.vars), dict(ctx.funcs)
            self.index.add(r.key, r.defined_vars, r.defined_funcs)
            self._keys[r.id] = r.key
        if (_shown(r.display), r.error.message if r.error else None) != before or r.plot is not None:
            self.changed.add(r.id)

    def take_changed(self) -> set:
        out, self.changed = self.changed, set()
        return out

    def _run(self, r: Region, ctx: Context, record: bool) -> None:
        if record:
            r.value = r.display = r.error = None
        if r.plot is not None:
            if record and r.enabled:
                self._run_plot(r, ctx)
            return
        if r.kind != "math" or not r.enabled:
            r.uses = frozenset()
            return
        items = r.editor.expression_items()
        if not items:
            r.uses = frozenset()
            return
        expr_row = r.expression_row()
        try:
            node = parse_row(expr_row)
        except ParseError as e:
            if record:
                r.error = SMathError("Syntax is incorrect.", None)
                r.error.src = _rebase(e.src, expr_row, r.editor.root)
            r.uses = frozenset(_row_names(expr_row))
            return
        # the expression row is a copy of the root's items: point error
        # locations back at the editor's own row so they can be drawn
        for n in A.walk(node):
            if n.src is not None:
                n.src = _rebase(n.src, expr_row, r.editor.root)
        r.uses = frozenset(_used_names(node) | _row_names(r.editor.unit))
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

    def _run_plot(self, r: Region, ctx: Context) -> None:
        r.curves = []
        r.plot_ctx = ctx
        uses = set()
        for row in r.plot_rows():
            if row.is_empty():
                continue
            try:
                node = parse_row(row)
                r.curves.append(node)
                uses |= _used_names(node)
            except ParseError as e:
                r.error = SMathError("Syntax is incorrect.", None)
                r.error.src = e.src
        r.uses = frozenset(uses)

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

    def recalc_if_auto(self) -> None:
        if self.auto_calculation:
            self.calculate()


def _rebase(src, old: Row, new: Row):
    if src is not None and src[0] is old:
        return (new, src[1], src[2])
    return src


def _shown(display):
    return repr(display) if display is not None else None


def _used_names(node) -> set:
    """Names an expression refers to (variables and functions)."""
    out = set()
    for n in A.walk(node):
        if isinstance(n, A.Var):
            out.add(n.name)
        elif isinstance(n, A.Call):
            out.add(n.name)
    return out


def _row_names(r: Row) -> set:
    """Identifiers in a row (used when it does not parse)."""
    from .engine.model import walk_rows

    out = set()
    for row in walk_rows(r):
        word = []
        for it in row.items + [" "]:
            if isinstance(it, str) and (it.isalnum() or it in "._" or it in "αβγδεζηθικλμνξοπρστυφχψωΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ"):
                word.append(it)
            else:
                if word and not word[0].isdigit():
                    out.add("".join(word))
                word = []
    return out
