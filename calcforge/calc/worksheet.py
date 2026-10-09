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

import os

import bisect
import itertools
from dataclasses import dataclass, field
from typing import Optional

from .editor import MathEditor
from .engine import ast as A
from .engine.display import DExpr, display_value
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
    enabled: bool = True  # right-click > Disable evaluation (unchecked)
    fmt: Optional[NumberFormat] = None  # per-region override (right-click menu)
    # right-click menu options of a math region (SMath Cloud)
    show_input: bool = True  # "Display input data": off shows only the result
    ignore_units: bool = False  # "Ignore units"
    # "symbolic", "numeric" or "none"; "" = SMath's default (numeric for an
    # evaluation, symbolic for a definition)
    optimization: str = ""
    plot: Optional[PlotState] = None  # set for 2-D plot regions
    curves: list = field(default_factory=list)  # parsed plot inputs
    plot_ctx: object = None  # definitions visible to the plot
    # formatting (Format toolbar / region properties, as in SMath)
    font_size: float = 10.0
    font_family: str = ""  # text regions (toolbar font box); "" = default
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: str = "#000000"
    bg_color: str = "#ffffff"
    border: bool = False
    # bookkeeping for incremental recalculation
    defined_vars: dict = field(default_factory=dict)
    defined_funcs: dict = field(default_factory=dict)
    uses: frozenset = frozenset()
    dynamic: bool = False  # uses eval/str2num...: depends on anything
    pending: bool = False  # edited since last calculated (result shows the box)
    _parsed: object = field(default=None, repr=False)  # (signature, node, uses, dynamic)

    @property
    def key(self):
        return (self.y, self.x, self.id)

    # SMath's separators, areas and pictures: CalcForge makes none of them
    # (MarkForge's lines and images, and calculation blocks, instead); kept
    # because WebSMath's drawing code, byte for byte, reads them.
    special: Optional[str] = None  # "separator", "area" or "picture"
    image: bytes = b""  # picture regions: the encoded image (PNG/JPEG)
    image_format: str = "png"
    pic_w: float = 0.0  # picture regions: size shown on the page
    pic_h: float = 0.0
    # text regions: formatting per line, as runs [(text, {"bold":..,"italic":..,"underline":..})]
    # (SMath's rich text: <p style>, <span style>, <br/>); empty = the region's own style
    line_runs: list = field(default_factory=list)
    text_width: float = 0.0  # text regions with a fixed width wrap their lines
    field_code: str = ""  # header/footer math regions holding a field (\[TITLE]\ ...)
    area_height: float = 0.0  # an area's extent below its top line
    collapsed: bool = False

    @property
    def kind(self) -> str:
        if self.special:
            return self.special
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
    # names offered by the document's tables and sheets (CalcForge), or None
    external = None

    def __init__(self):
        self.regions: list[Region] = []
        self.format = NumberFormat()
        self.auto_calculation = True
        self.evaluator = Evaluator()
        self.index = DefinitionIndex()
        # Calculation blocks with Self-contained on (CalcForge decision 10):
        # region id -> the block it is inside. What such a region defines goes
        # into its block's own index, seen only inside that block; the block
        # still sees everything defined above it.
        self.scope_of: dict = {}
        self._scoped: dict = {}             # block -> DefinitionIndex
        self._scope_indexed: dict = {}      # region id -> block it was indexed in
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

        from .engine import evaluator as _evaluator
        _evaluator.EXTERNAL = self.external
        ctx = self._context_before(region)
        if nargs is None:
            return ctx.has(name) or name in BUILTIN_CONSTANTS
        if ctx.function(name, nargs) is not None:
            return True
        from .engine import evaluator

        if evaluator.EXTERNAL is not None and evaluator.EXTERNAL.function(name, nargs) is not None:
            return True
        return builtins.has_overload(name, nargs)

    def _context_before(self, region: Region) -> Context:
        scope = self.scope_of.get(region.id)
        if scope is not None:
            return ScopedContext(self.index, region.key, self._scoped.get(scope))
        return IndexedContext(self.index, region.key)

    # -- calculation blocks (Self-contained) -----------------------------------------
    def _index_for(self, scope) -> DefinitionIndex:
        if scope is None:
            return self.index
        return self._scoped.setdefault(scope, DefinitionIndex())

    def set_scopes(self, scopes: dict) -> bool:
        """Which self-contained block each region is inside (region id ->
        block). Says whether anything changed; the caller recalculates."""
        scopes = {rid: scope for rid, scope in scopes.items() if scope is not None}
        if scopes == self.scope_of:
            return False
        self.scope_of = scopes
        return True

    @property
    def context(self) -> Context:
        """Everything defined anywhere on the page (for styling)."""
        return IndexedContext(self.index, (float("inf"),))

    # -- calculation ----------------------------------------------------------------
    def calculate(self) -> None:
        """Recalculate the whole page from scratch (F9, loading, moving regions)."""
        self.index.clear()
        self._scoped.clear()
        self._scope_indexed.clear()
        self._keys.clear()
        self.invalidate_order()
        for r in self.ordered():
            self._evaluate(r, commit=True)

    _live = False  # evaluating the region being typed (see _display)

    def calculate_region(self, region: Region) -> None:
        """Re-evaluate one region against what is defined above it.

        Observed on SMath Cloud: while a region is being edited only that
        region is recalculated (its result follows every keystroke); the rest
        of the worksheet is recalculated when the region loses focus.
        """
        self._live = True
        try:
            self._evaluate(region, commit=False)
        finally:
            self._live = False

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
        if region.id in self._keys and \
                self.scope_of.get(region.id) != self._scope_indexed.get(region.id):
            self.calculate()              # moved into or out of a self-contained block
            return
        before = set(region.defined_vars) | {n for n, _ in region.defined_funcs}
        self._evaluate(region, commit=True)
        changed = before | set(region.defined_vars) | {n for n, _ in region.defined_funcs}
        self._propagate(region.key, changed)

    def region_removed(self, region: Region) -> None:
        key = self._keys.pop(region.id, None)
        if key is None:
            return
        self._index_for(self._scope_indexed.pop(region.id, None)).remove(
            key, region.defined_vars, region.defined_funcs)
        changed = set(region.defined_vars) | {n for n, _ in region.defined_funcs}
        self._propagate(key, changed)

    def _propagate(self, key, changed: set) -> None:
        """Re-evaluate, in reading order, only the regions after `key` that
        use a changed name.  A re-evaluated region passes on only the names
        whose value really changed (a:=2.1 -> 2.2 leaves r:=round(a) at 2,
        so nothing after r is touched); function definitions always count as
        changed, since a function reads outside names each time it is called.
        Regions whose dependencies cannot be seen (eval, str2num...) are
        re-evaluated on any change."""
        if not changed:
            return
        changed = set(changed)
        order = self.ordered()
        start = bisect.bisect_right(self._order_keys, key)
        for r in order[start:]:
            if r.dynamic or r.uses & changed:
                old_vars, old_funcs = r.defined_vars, r.defined_funcs
                self._evaluate(r, commit=True)
                changed |= _changed_names(old_vars, old_funcs, r.defined_vars, r.defined_funcs)

    def _evaluate(self, r: Region, commit: bool) -> None:
        from .engine import files, sym

        # importData / exportData: relative names are relative to the worksheet's folder
        files.base_dir = os.path.dirname(getattr(self, "filename", "") or "")
        sym.defined_above = lambda r=r: self.names_defined_above(r)
        from .engine import evaluator as _evaluator
        _evaluator.EXTERNAL = self.external     # this document's tables
        r.pending = False
        before = (_shown(r.display), r.error.message if r.error else None)
        if commit and r.id in self._keys:
            self._index_for(self._scope_indexed.pop(r.id, None)).remove(
                self._keys.pop(r.id), r.defined_vars, r.defined_funcs)
        ctx = self._context_before(r)
        self.evaluator.start_clock()
        try:
            self._run(r, ctx, record=True)
        except RecursionError:
            r.error = err("recursion")
        except SMathError as e:
            r.error = e
        except Exception as e:  # never let one odd region break the page
            import logging

            logging.getLogger(__name__).exception("evaluating %s", r.editor.root.text())
            r.error = err("cannot_evaluate")
        if commit:
            r.defined_vars, r.defined_funcs = dict(ctx.vars), dict(ctx.funcs)
            scope = self.scope_of.get(r.id)
            self._index_for(scope).add(r.key, r.defined_vars, r.defined_funcs)
            self._keys[r.id] = r.key
            if scope is not None:
                self._scope_indexed[r.id] = scope
        if (_shown(r.display), r.error.message if r.error else None) != before or r.plot is not None:
            self.changed.add(r.id)

    def names_defined_above(self, region: Region) -> set:
        """Every name a region above this one defines (variables, functions,
        matrices assigned element by element, also inside programs) -
        whether or not the definition worked."""
        out = set()
        for r in self.ordered():
            if r.key >= region.key:
                break
            if r.kind != "math":
                continue
            try:
                node = parse_row(r.expression_row())
            except Exception:
                continue
            for m in A.walk(node):
                if isinstance(m, A.Define):
                    t = m.target
                    if isinstance(t, A.IndexOp):
                        t = t.base
                    name = getattr(t, "name", None)
                    if name:
                        out.add(name)
        return out

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
        ed = r.editor
        # the parsed expression is kept while the region is unchanged: the key
        # is the full text of the equation and its unit box, so any change -
        # typed, pasted, or made to the rows directly - means a fresh parse
        sig = (ed.root.text(), ed.unit.text(), ed.evaluate)
        cached = r._parsed if r._parsed is not None and r._parsed[0] == sig else None
        if cached is not None:
            node, r.uses, r.dynamic = cached[1], cached[2], cached[3]
        else:
            node = self._parse_region(r)
            if node is None:
                return
            r._parsed = (sig, node, r.uses, r.dynamic)
        self._run_node(r, node, ctx, record)

    def _parse_region(self, r: Region):
        """Parse a region's expression (None and a syntax error if it does not
        parse), recording the names it uses."""
        items = r.editor.expression_items()
        if not items:
            r.uses = frozenset()
            return None
        expr_row = r.expression_row()
        record = True
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
        # one pass: rebase error locations, collect the names used, and spot
        # calls whose dependencies cannot be seen
        root = r.editor.root
        names, dynamic = set(), False
        for n in A.walk(node):
            src = n.src
            if src is not None and src[0] is expr_row:
                n.src = (root, src[1], src[2])
            t = type(n)
            if t is A.Var:
                names.add(n.name)
            elif t is A.Call:
                names.add(n.name)
                if n.name in DYNAMIC_CALLS:
                    dynamic = True
        if not r.editor.unit.is_empty():
            names |= _row_names(r.editor.unit)
        r.uses = frozenset(names)
        r.dynamic = dynamic
        return node

    def _run_node(self, r: Region, node, ctx: Context, record: bool) -> None:
        self.evaluator.ignore_units = r.ignore_units
        reads = self.evaluator.reads = set()
        try:
            if isinstance(node, A.Define):
                self.evaluator.define(node, ctx)
                if r.editor.evaluate and isinstance(node.target, A.Var) and r.optimization != "none":
                    # x := expression = value: SMath Studio desktop defines
                    # and shows the value in one region
                    value = self.evaluator.eval(A.Var(node.target.name), ctx)
                    if record:
                        r.value = value
                        r.display = self._display(r, value, ctx)
                return
            if not r.editor.evaluate:
                # a bare expression (no "=" or ":=") runs - a for loop in it
                # still assigns - but shows no error: observed, "test", "x+1"
                # and "100kg*g.e" while typing are error-free on SMath Cloud
                # until "=" is typed
                if record and not isinstance(node, A.Placeholder):
                    try:
                        self.evaluator.eval(node, ctx)
                    except SMathError:
                        pass
                return
            if r.optimization == "none":
                # no evaluation: the input is shown again after "="
                if record:
                    r.display = DExpr(r.expression_row())
                return
            value = self.evaluator.eval(node, ctx)
            if record:
                r.value = value
                r.display = self._display(r, value, ctx)
        except SMathError as e:
            if record:
                r.error = e
        finally:
            self.evaluator.ignore_units = False
            self.evaluator.reads = None
            # names reached while evaluating (a symbolic definition's names, a
            # called function's outside names) are dependencies too
            r.uses = r.uses | reads

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
        try:
            unode = parse_row(unit_row)
            uval = need_scalar(self.evaluator.eval(unode, ctx))
        except (SMathError, ParseError) as e:
            if self._live:
                # a unit still being typed ("k" of kN): show the result as if
                # the box were empty, not a stray conversion.  As on SMath
                # Cloud a unit gets into the box from the list (Tab), which
                # inserts 'kN; a plain word stays a name ("cm - not defined.")
                return display_value(value, fmt)
            if isinstance(e, ParseError):
                raise err("syntax")
            raise
        q = value
        # non-linear temperature units (°C, °F): subtract the offset
        offset = 0.0
        if isinstance(unode, A.UnitRef):
            offset = unit_offset(unode.name)
        if isinstance(q, Quantity):
            if q.dims != uval.dims:
                if offset:
                    raise err("units_mismatch", node=unode)
                # SMath keeps the unit typed in the box at the end and fills
                # the gap with the units still needed: 980.665 N with kg in
                # the box shows 9.8066 m/s² kg
                rest = tuple(a - b for a, b in zip(q.dims, uval.dims))
                return display_value(Q(q.value / uval.value, rest), fmt)
            shown = Q((q.value - offset) / uval.value)
            return display_value(shown, fmt)
        if isinstance(q, Matrix):
            if any(x.dims != uval.dims for x in q.items):
                if offset:
                    raise err("units_mismatch", node=unode)
                return display_value(Matrix(q.nrows, q.ncols, [
                    Q(x.value / uval.value, tuple(a - b for a, b in zip(x.dims, uval.dims))) for x in q.items]), fmt)
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


# calls whose dependencies are not visible in the expression
DYNAMIC_CALLS = {"eval", "str2num", "IsDefined", "Clear", "rfile", "importData"}


def _same_value(a, b) -> bool:
    from .engine.evaluator import Lazy

    if isinstance(a, Lazy) or isinstance(b, Lazy) or type(a) is not type(b):
        return False
    if isinstance(a, Quantity):
        return a.dims == b.dims and (a.value == b.value or (a.value != a.value and b.value != b.value))
    if isinstance(a, Matrix):
        return (a.nrows, a.ncols) == (b.nrows, b.ncols) and all(_same_value(x, y) for x, y in zip(a.items, b.items))
    return a == b


def _changed_names(old_vars, old_funcs, new_vars, new_funcs) -> set:
    out = {n for n, _ in old_funcs} | {n for n, _ in new_funcs}
    for n in set(old_vars) | set(new_vars):
        if n not in old_vars or n not in new_vars or not _same_value(old_vars[n], new_vars[n]):
            out.add(n)
    return out


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


class ScopedContext(IndexedContext):
    """What a region inside a self-contained calculation block sees: the
    worksheet's definitions above it and its own block's, whichever of the
    two is the more recent in reading order (CalcForge decision 10)."""

    def __init__(self, index: DefinitionIndex, key, own: Optional[DefinitionIndex]):
        super().__init__(index, key)
        self.own = own if own is not None else DefinitionIndex()

    @staticmethod
    def _last(lst, key):
        if not lst:
            return None
        i = bisect.bisect_left(lst, key, key=lambda e: e[0])
        return lst[i - 1] if i else None

    def _latest(self, table: str, name):
        mine = self._last(getattr(self.own, table).get(name), self.key)
        theirs = self._last(getattr(self.index, table).get(name), self.key)
        if mine is None:
            return theirs[1] if theirs is not None else None
        if theirs is None or mine[0] > theirs[0]:
            return mine[1]
        return theirs[1]

    def lookup(self, name: str):
        if name in self.vars:
            return self.vars[name]
        return self._latest("vars", name)

    def has(self, name: str) -> bool:
        from .engine import evaluator

        if name in self.vars or self._latest("vars", name) is not None:
            return True
        return evaluator.EXTERNAL is not None and evaluator.EXTERNAL.has(name)

    def function(self, name: str, nargs: int):
        f = self.funcs.get((name, nargs))
        return f if f is not None else self._latest("funcs", (name, nargs))

    def any_function(self, name: str):
        for (n, k), f in self.funcs.items():
            if n == name:
                return f
        for table in (self.own.funcs, self.index.funcs):
            for (n, k), lst in table.items():
                if n == name and lst[0][0] < self.key:
                    return lst[0][1]
        return None

    def names(self) -> set:
        return super().names() | self.own.names_before(self.key)

    def function_arities(self) -> dict:
        out = {n: k for (n, k), lst in self.own.funcs.items() if lst[0][0] < self.key}
        out.update(super().function_arities())
        return out
