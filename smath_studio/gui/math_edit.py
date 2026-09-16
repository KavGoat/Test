"""WYSIWYG math editor for SMath Studio GUI.

Provides a canvas-based inline math editor that renders typed expressions
as proper mathematical notation in real-time, matching SMath Studio's
editing experience: fraction layout on /, superscripts on ^, Tab navigation
between slots, blinking cursor, and live evaluation preview.
"""

from __future__ import annotations

import math as _math
import tkinter as tk
from tkinter import font as tkfont
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..expression import (
    ASTNode, Number, Variable, UnitRef, StringLiteral,
    BinaryOp, UnaryOp, FunctionCall, Evaluation,
)

_FUNCTION_NAMES = sorted([
    "sin", "cos", "tan", "asin", "acos", "atan", "cot", "sec", "csc",
    "sinh", "cosh", "tanh", "asinh", "acosh", "atanh",
    "ln", "log", "exp", "sqrt", "abs", "sign", "ceil", "floor", "round",
    "max", "min", "mod", "sum", "product", "nintegrate", "diff", "nderiv",
    "det", "invert", "transpose", "identity", "el", "rows", "cols",
    "mean", "median", "stdev", "sort", "reverse", "length",
    "if", "for", "while", "line", "range", "eval", "mat",
    "re", "im", "arg", "conj", "Gamma", "Beta", "erf",
    "polyroots", "solve", "augment", "stack", "col", "submatrix",
    "csort", "rsort", "tr", "num2str", "str2num",
])


# ---- Edit tree nodes ----

class EditItem:
    pass


@dataclass
class EText(EditItem):
    text: str = ""


@dataclass
class EOp(EditItem):
    op: str = ""


@dataclass
class EFraction(EditItem):
    numerator: EditSlot = field(default_factory=lambda: EditSlot())
    denominator: EditSlot = field(default_factory=lambda: EditSlot())


@dataclass
class ESuperscript(EditItem):
    exponent: EditSlot = field(default_factory=lambda: EditSlot())


@dataclass
class EParens(EditItem):
    inner: EditSlot = field(default_factory=lambda: EditSlot())


@dataclass
class ESqrt(EditItem):
    radicand: EditSlot = field(default_factory=lambda: EditSlot())


@dataclass
class EAbs(EditItem):
    inner: EditSlot = field(default_factory=lambda: EditSlot())


@dataclass
class EUnit(EditItem):
    name: str = ""


@dataclass
class EMatrix(EditItem):
    rows: int = 2
    cols: int = 2
    cells: list = field(default_factory=list)

    def __post_init__(self):
        if not self.cells:
            self.cells = [[EditSlot() for _ in range(self.cols)] for _ in range(self.rows)]


@dataclass
class ESummation(EditItem):
    var_slot: EditSlot = field(default_factory=lambda: EditSlot())
    lower_slot: EditSlot = field(default_factory=lambda: EditSlot())
    upper_slot: EditSlot = field(default_factory=lambda: EditSlot())
    body_slot: EditSlot = field(default_factory=lambda: EditSlot())


@dataclass
class EProduct(EditItem):
    var_slot: EditSlot = field(default_factory=lambda: EditSlot())
    lower_slot: EditSlot = field(default_factory=lambda: EditSlot())
    upper_slot: EditSlot = field(default_factory=lambda: EditSlot())
    body_slot: EditSlot = field(default_factory=lambda: EditSlot())


@dataclass
class EIntegral(EditItem):
    body_slot: EditSlot = field(default_factory=lambda: EditSlot())
    var_slot: EditSlot = field(default_factory=lambda: EditSlot())
    lower_slot: EditSlot = field(default_factory=lambda: EditSlot())
    upper_slot: EditSlot = field(default_factory=lambda: EditSlot())


@dataclass
class ERange(EditItem):
    start_slot: EditSlot = field(default_factory=lambda: EditSlot())
    step_slot: EditSlot = field(default_factory=lambda: EditSlot())
    end_slot: EditSlot = field(default_factory=lambda: EditSlot())
    has_step: bool = False


@dataclass
class EDerivative(EditItem):
    body_slot: EditSlot = field(default_factory=lambda: EditSlot())
    var_slot: EditSlot = field(default_factory=lambda: EditSlot())


@dataclass
class ESystem(EditItem):
    """System of equations block - curly brace with stacked rows."""
    rows: list = field(default_factory=list)

    def __post_init__(self):
        if not self.rows:
            self.rows = [EditSlot(), EditSlot()]


@dataclass
class EditSlot:
    items: list[EditItem] = field(default_factory=list)
    cursor_pos: int = 0


@dataclass
class _Box:
    width: float = 0
    height: float = 0
    baseline: float = 0


# ---- Style constants matching SMath Studio ----

_NUMBER_COLOR = "#000000"
_UNIT_COLOR = "#0000ff"
_OPERATOR_COLOR = "#000000"
_STRING_COLOR = "#a31515"
_CURSOR_COLOR = "#000000"
_PLACEHOLDER_COLOR = "#999999"
_RESULT_COLOR = "#000000"
_ERROR_COLOR = "#ff0000"

_OP_DISPLAY = {
    ":": " := ",
    "+": " + ",
    "-": " − ",
    "*": " · ",
    "=": " = ",
    ",": ", ",
    "<": " < ",
    ">": " > ",
    "≤": " ≤ ",
    "≥": " ≥ ",
    "≠": " ≠ ",
    "!": "!",
}

_BUILTIN_VARS = {
    "π", "pi", "e", "i", "∞", "inf",
    "g.e", "c", "m.e", "m.p", "m.n", "u",
    "G.N", "h", "N.A", "k", "R.m",
    "ε.0", "μ.0",
}

_GREEK_MAP = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ",
    "epsilon": "ε", "zeta": "ζ", "eta": "η", "theta": "θ",
    "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ",
    "nu": "ν", "xi": "ξ", "omicron": "ο", "pi": "π",
    "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ",
    "phi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ",
    "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
    "inf": "∞",
}

_GREEK_DISPLAY = {v: v for v in _GREEK_MAP.values()}
for k, v in _GREEK_MAP.items():
    _GREEK_DISPLAY[k] = v

_SUP_SCALE = 0.72
_FRAC_HPAD = 6
_FRAC_VPAD = 2

_FUNCTION_HINTS = {
    "sin": "sin(x)", "cos": "cos(x)", "tan": "tan(x)",
    "asin": "asin(x)", "acos": "acos(x)", "atan": "atan(x)",
    "cot": "cot(x)", "sec": "sec(x)", "csc": "csc(x)",
    "sinh": "sinh(x)", "cosh": "cosh(x)", "tanh": "tanh(x)",
    "asinh": "asinh(x)", "acosh": "acosh(x)", "atanh": "atanh(x)",
    "ln": "ln(x)", "log": "log(x, base)", "exp": "exp(x)",
    "sqrt": "sqrt(x)", "abs": "abs(x)", "sign": "sign(x)",
    "ceil": "ceil(x)", "floor": "floor(x)", "round": "round(x, digits)",
    "max": "max(a, b, ...)", "min": "min(a, b, ...)", "mod": "mod(x, y)",
    "sum": "sum(expr, var, from, to)", "product": "product(expr, var, from, to)",
    "nintegrate": "nintegrate(expr, var, from, to)",
    "diff": "diff(expr, var)", "nderiv": "nderiv(expr, var)",
    "det": "det(M)", "invert": "invert(M)", "transpose": "transpose(M)",
    "identity": "identity(n)", "el": "el(M, row, col)",
    "rows": "rows(M)", "cols": "cols(M)",
    "mean": "mean(list)", "median": "median(list)", "stdev": "stdev(list)",
    "sort": "sort(list)", "reverse": "reverse(list)", "length": "length(list)",
    "if": "if(val, cond, ...)", "for": "for(body, var, start, end)",
    "while": "while(body, cond)", "line": "line(expr1, expr2, ...)",
    "range": "range(start, end, [step])", "eval": "eval(expr)",
    "mat": "mat(v1, ..., rows, cols)",
    "re": "re(z)", "im": "im(z)", "arg": "arg(z)", "conj": "conj(z)",
    "Gamma": "Gamma(x)", "Beta": "Beta(a, b)", "erf": "erf(x)",
    "solve": "solve(expr, var, guess)",
    "augment": "augment(M1, M2)", "stack": "stack(M1, M2)",
    "col": "col(M, index)", "submatrix": "submatrix(M, r1, c1, r2, c2)",
    "tr": "tr(M)", "num2str": "num2str(x)", "str2num": "str2num(s)",
}


class MathEditor:
    """Canvas-based WYSIWYG math expression editor."""

    def __init__(
        self,
        canvas: tk.Canvas,
        x: int,
        y: int,
        font_size: int = 12,
        eval_callback: Optional[Callable[[str], Any]] = None,
        precision: int = 4,
    ):
        self.canvas = canvas
        self.x = x
        self.y = y
        self.font_size = font_size
        self._eval_callback = eval_callback
        self._precision = precision

        self.root = EditSlot()
        self._active_slot: EditSlot = self.root
        self._slot_stack: list[EditSlot] = []

        self._eval_result: Any = None
        self._eval_error: Optional[str] = None

        self._items: list[int] = []
        self._cursor_item: Optional[int] = None
        self._cursor_visible = True
        self._blink_id: Optional[str] = None

        self._cursor_rx: Optional[float] = None
        self._cursor_ry: Optional[float] = None
        self._cursor_rh: Optional[float] = None

        self._font_family = "serif"
        self._font_cache: dict[tuple, tkfont.Font] = {}
        self._detect_font()

        # Autocomplete state
        self._ac_visible = False
        self._ac_items: list[int] = []
        self._ac_suggestions: list[str] = []
        self._ac_selected: int = 0
        self._ac_prefix: str = ""

        # Function hint state
        self._hint_items: list[int] = []

        self.render()
        self._start_blink()

    # ================================================================
    # Font helpers
    # ================================================================

    def _detect_font(self):
        for family in ("Cambria Math", "STIX Two Math", "DejaVu Serif",
                       "Liberation Serif", "serif"):
            try:
                f = tkfont.Font(root=self.canvas, family=family, size=12)
                if f.actual("family"):
                    self._font_family = family
                    return
            except Exception:
                continue

    def _get_font(self, size: int, style: str = "") -> tkfont.Font:
        key = (self._font_family, size, style)
        if key not in self._font_cache:
            weight = "bold" if "bold" in style else "normal"
            slant = "italic" if "italic" in style else "roman"
            self._font_cache[key] = tkfont.Font(
                root=self.canvas, family=self._font_family,
                size=max(size, 6), weight=weight, slant=slant,
            )
        return self._font_cache[key]

    def _text_size(self, text: str, size: int, style: str = "") -> tuple[float, float]:
        f = self._get_font(size, style)
        return f.measure(text), f.metrics("linespace")

    def _line_height(self, fs: int) -> float:
        _, h = self._text_size("Xg", fs)
        return h

    # ================================================================
    # Key handling
    # ================================================================

    def handle_key(self, event: tk.Event) -> str:
        """Handle a key event. Returns 'commit', 'cancel', or 'consumed'."""
        keysym = event.keysym
        char = event.char

        ctrl = event.state & 0x4

        if keysym in ("Return", "KP_Enter"):
            return "commit"
        if keysym == "Escape":
            return "cancel"

        if ctrl and keysym.lower() == "m":
            self._do_matrix()
            self._update_eval()
            self.render()
            return "consumed"

        if ctrl and keysym.lower() == "d":
            self._do_derivative()
            self._update_eval()
            self.render()
            return "consumed"

        if ctrl and keysym.lower() == "i":
            self._do_integral()
            self._update_eval()
            self.render()
            return "consumed"

        shift = event.state & 0x1
        if ctrl and shift and keysym.lower() == "s":
            self._do_summation()
            self._update_eval()
            self.render()
            return "consumed"

        if ctrl and shift and keysym.lower() == "p":
            self._do_product()
            self._update_eval()
            self.render()
            return "consumed"

        if keysym == "BackSpace":
            self._do_backspace()
        elif keysym == "Delete":
            self._do_delete()
        elif keysym == "Left":
            self._move_left()
        elif keysym == "Right":
            self._move_right()
        elif keysym == "Up":
            if self._ac_visible and self._ac_suggestions:
                self._ac_selected = max(0, self._ac_selected - 1)
                self._hide_autocomplete()
                self._show_autocomplete()
            else:
                self._move_up()
        elif keysym == "Down":
            if self._ac_visible and self._ac_suggestions:
                self._ac_selected = min(len(self._ac_suggestions) - 1, self._ac_selected + 1)
                self._hide_autocomplete()
                self._show_autocomplete()
            else:
                self._move_down()
        elif keysym == "Tab":
            if not (event.state & 0x1) and self._ac_visible:
                self._accept_autocomplete()
            elif event.state & 0x1:
                self._tab_prev()
            else:
                self._tab_next()
        elif keysym == "Home":
            self._active_slot.cursor_pos = 0
        elif keysym == "End":
            self._active_slot.cursor_pos = len(self._active_slot.items)
        elif char and ord(char) >= 32:
            self._insert_char(char)
        else:
            return "consumed"

        self._update_eval()
        self.render()
        return "consumed"

    # ---- Character insertion ----

    def _insert_char(self, ch: str):
        slot = self._active_slot
        pos = slot.cursor_pos

        if ch == ".":
            if pos > 0 and isinstance(slot.items[pos - 1], EText):
                prev_text = slot.items[pos - 1].text
                if prev_text.endswith("."):
                    slot.items[pos - 1].text = prev_text[:-1]
                    if not slot.items[pos - 1].text:
                        slot.items.pop(pos - 1)
                        pos -= 1
                    self._do_range()
                    return
            if pos > 0 and isinstance(slot.items[pos - 1], EText):
                slot.items[pos - 1].text += ch
            else:
                slot.items.insert(pos, EText(ch))
                slot.cursor_pos = pos + 1
            return

        if ch == "/":
            self._do_fraction()
            return
        if ch == "^":
            self._do_superscript()
            return
        if ch == "(":
            self._do_open_paren()
            return
        if ch == ")":
            self._do_close_paren()
            return

        if ch == ":":
            slot.items.insert(pos, EOp(":"))
            slot.cursor_pos = pos + 1
            return

        if ch == "=":
            if pos > 0 and isinstance(slot.items[pos - 1], EOp):
                prev = slot.items[pos - 1]
                if prev.op == "<":
                    prev.op = "≤"
                    return
                if prev.op == ">":
                    prev.op = "≥"
                    return
                if prev.op == "!":
                    prev.op = "≠"
                    return
                if prev.op == ":":
                    return
            slot.items.insert(pos, EOp("="))
            slot.cursor_pos = pos + 1
            return

        if ch in ("+", "-", "*", "<", ">", "!"):
            slot.items.insert(pos, EOp(ch))
            slot.cursor_pos = pos + 1
            return

        if ch == ",":
            slot.items.insert(pos, EOp(","))
            slot.cursor_pos = pos + 1
            return

        if ch == ";":
            if self._slot_stack:
                parent = self._slot_stack[-1]
                for item in parent.items:
                    if isinstance(item, EMatrix):
                        for r_idx, row in enumerate(item.cells):
                            if self._active_slot in row:
                                if r_idx + 1 < item.rows:
                                    self._active_slot = item.cells[r_idx + 1][0]
                                    self._active_slot.cursor_pos = 0
                                    return
                    if isinstance(item, ESystem):
                        for r_idx, row in enumerate(item.rows):
                            if self._active_slot is row:
                                if r_idx + 1 < len(item.rows):
                                    self._active_slot = item.rows[r_idx + 1]
                                    self._active_slot.cursor_pos = 0
                                else:
                                    new_row = EditSlot()
                                    item.rows.append(new_row)
                                    self._active_slot = new_row
                                    self._active_slot.cursor_pos = 0
                                return
            slot.items.insert(pos, EOp(","))
            slot.cursor_pos = pos + 1
            return

        if ch == "{":
            self._do_system()
            return

        if ch == "\\":
            self._do_sqrt()
            return

        if ch == "|":
            self._do_abs()
            return

        if ch == "'":
            if pos > 0 and isinstance(slot.items[pos - 1], EUnit):
                return
            unit = EUnit("")
            slot.items.insert(pos, unit)
            slot.cursor_pos = pos + 1
            return

        if ch == "}":
            if self._slot_stack:
                parent = self._slot_stack[-1]
                for i, item in enumerate(parent.items):
                    if isinstance(item, ESystem):
                        if self._active_slot in item.rows:
                            self._active_slot = self._slot_stack.pop()
                            self._active_slot.cursor_pos = i + 1
                            return
            return

        if pos > 0 and isinstance(slot.items[pos - 1], EText):
            prev_text = slot.items[pos - 1].text
            if ch.isalpha() and prev_text and prev_text[-1].isdigit():
                unit = EUnit(ch)
                slot.items.insert(pos, unit)
                slot.cursor_pos = pos + 1
            else:
                slot.items[pos - 1].text += ch
        elif pos > 0 and isinstance(slot.items[pos - 1], EUnit):
            slot.items[pos - 1].name += ch
        else:
            slot.items.insert(pos, EText(ch))
            slot.cursor_pos = pos + 1

    def _do_fraction(self):
        slot = self._active_slot
        pos = slot.cursor_pos
        frac = EFraction()

        if pos > 0 and isinstance(slot.items[pos - 1], (EText, EParens, ESuperscript)):
            prev = slot.items.pop(pos - 1)
            pos -= 1
            frac.numerator.items.append(prev)
            frac.numerator.cursor_pos = len(frac.numerator.items)

        slot.items.insert(pos, frac)
        slot.cursor_pos = pos + 1
        self._slot_stack.append(slot)
        self._active_slot = frac.denominator
        self._active_slot.cursor_pos = 0

    def _do_superscript(self):
        slot = self._active_slot
        pos = slot.cursor_pos
        sup = ESuperscript()
        slot.items.insert(pos, sup)
        slot.cursor_pos = pos + 1
        self._slot_stack.append(slot)
        self._active_slot = sup.exponent
        self._active_slot.cursor_pos = 0

    def _do_open_paren(self):
        slot = self._active_slot
        pos = slot.cursor_pos
        parens = EParens()
        slot.items.insert(pos, parens)
        slot.cursor_pos = pos + 1
        self._slot_stack.append(slot)
        self._active_slot = parens.inner
        self._active_slot.cursor_pos = 0

    def _do_close_paren(self):
        if self._slot_stack:
            parent = self._slot_stack[-1]
            for i, item in enumerate(parent.items):
                if isinstance(item, EParens) and item.inner is self._active_slot:
                    self._active_slot = self._slot_stack.pop()
                    self._active_slot.cursor_pos = i + 1
                    return
                if isinstance(item, ESqrt) and item.radicand is self._active_slot:
                    self._active_slot = self._slot_stack.pop()
                    self._active_slot.cursor_pos = i + 1
                    return
                if isinstance(item, EAbs) and item.inner is self._active_slot:
                    self._active_slot = self._slot_stack.pop()
                    self._active_slot.cursor_pos = i + 1
                    return
                if isinstance(item, EMatrix):
                    for row in item.cells:
                        if self._active_slot in row:
                            idx = row.index(self._active_slot)
                            r_idx = item.cells.index(row)
                            if idx + 1 < item.cols:
                                self._active_slot = row[idx + 1]
                                self._active_slot.cursor_pos = 0
                                return
                            elif r_idx + 1 < item.rows:
                                self._active_slot = item.cells[r_idx + 1][0]
                                self._active_slot.cursor_pos = 0
                                return
                            else:
                                self._active_slot = self._slot_stack.pop()
                                self._active_slot.cursor_pos = i + 1
                                return
            self._active_slot = self._slot_stack.pop()

    def _do_abs(self):
        slot = self._active_slot
        pos = slot.cursor_pos
        absv = EAbs()
        slot.items.insert(pos, absv)
        slot.cursor_pos = pos + 1
        self._slot_stack.append(slot)
        self._active_slot = absv.inner
        self._active_slot.cursor_pos = 0

    def _do_sqrt(self):
        slot = self._active_slot
        pos = slot.cursor_pos
        sq = ESqrt()
        slot.items.insert(pos, sq)
        slot.cursor_pos = pos + 1
        self._slot_stack.append(slot)
        self._active_slot = sq.radicand
        self._active_slot.cursor_pos = 0

    def _do_derivative(self):
        slot = self._active_slot
        pos = slot.cursor_pos
        d = EDerivative()
        if pos > 0 and isinstance(slot.items[pos - 1], (EText, EParens)):
            prev = slot.items.pop(pos - 1)
            pos -= 1
            d.body_slot.items.append(prev)
            d.body_slot.cursor_pos = len(d.body_slot.items)
        slot.items.insert(pos, d)
        slot.cursor_pos = pos + 1
        self._slot_stack.append(slot)
        if d.body_slot.items:
            self._active_slot = d.var_slot
        else:
            self._active_slot = d.body_slot
        self._active_slot.cursor_pos = 0

    def _do_integral(self):
        slot = self._active_slot
        pos = slot.cursor_pos
        ig = EIntegral()
        slot.items.insert(pos, ig)
        slot.cursor_pos = pos + 1
        self._slot_stack.append(slot)
        self._active_slot = ig.body_slot
        self._active_slot.cursor_pos = 0

    def _do_summation(self):
        slot = self._active_slot
        pos = slot.cursor_pos
        s = ESummation()
        slot.items.insert(pos, s)
        slot.cursor_pos = pos + 1
        self._slot_stack.append(slot)
        self._active_slot = s.body_slot
        self._active_slot.cursor_pos = 0

    def _do_product(self):
        slot = self._active_slot
        pos = slot.cursor_pos
        p = EProduct()
        slot.items.insert(pos, p)
        slot.cursor_pos = pos + 1
        self._slot_stack.append(slot)
        self._active_slot = p.body_slot
        self._active_slot.cursor_pos = 0

    def _do_range(self):
        slot = self._active_slot
        pos = slot.cursor_pos
        r = ERange()
        if pos > 0 and isinstance(slot.items[pos - 1], EText):
            prev = slot.items.pop(pos - 1)
            pos -= 1
            r.start_slot.items.append(prev)
            r.start_slot.cursor_pos = len(r.start_slot.items)
        slot.items.insert(pos, r)
        slot.cursor_pos = pos + 1
        self._slot_stack.append(slot)
        self._active_slot = r.end_slot
        self._active_slot.cursor_pos = 0

    def _do_system(self):
        slot = self._active_slot
        pos = slot.cursor_pos
        sys = ESystem()
        if pos > 0:
            prev_items = slot.items[:pos]
            slot.items = slot.items[pos:]
            sys.rows[0].items = prev_items
            sys.rows[0].cursor_pos = len(prev_items)
            pos = 0
        slot.items.insert(pos, sys)
        slot.cursor_pos = pos + 1
        self._slot_stack.append(slot)
        if sys.rows[0].items:
            self._active_slot = sys.rows[1]
        else:
            self._active_slot = sys.rows[0]
        self._active_slot.cursor_pos = 0

    def _do_matrix(self, rows: int = 2, cols: int = 2):
        slot = self._active_slot
        pos = slot.cursor_pos
        mat = EMatrix(rows=rows, cols=cols)
        slot.items.insert(pos, mat)
        slot.cursor_pos = pos + 1
        self._slot_stack.append(slot)
        self._active_slot = mat.cells[0][0]
        self._active_slot.cursor_pos = 0

    # ---- Deletion ----

    def _do_backspace(self):
        slot = self._active_slot
        pos = slot.cursor_pos

        if pos > 0:
            item = slot.items[pos - 1]
            if isinstance(item, EText) and len(item.text) > 1:
                item.text = item.text[:-1]
            elif isinstance(item, EUnit) and len(item.name) > 1:
                item.name = item.name[:-1]
            elif isinstance(item, (EFraction, ESuperscript, EParens, ESqrt, EAbs,
                                    EMatrix, ESummation, EProduct, EIntegral,
                                    ERange, EDerivative, ESystem)):
                contents = self._flatten_structure(item)
                slot.items.pop(pos - 1)
                for j, c in enumerate(contents):
                    slot.items.insert(pos - 1 + j, c)
                slot.cursor_pos = pos - 1 + len(contents)
            else:
                slot.items.pop(pos - 1)
                slot.cursor_pos = pos - 1
        elif self._slot_stack:
            self._active_slot = self._slot_stack.pop()

    def _do_delete(self):
        slot = self._active_slot
        pos = slot.cursor_pos
        if pos < len(slot.items):
            item = slot.items[pos]
            if isinstance(item, EText) and len(item.text) > 1:
                item.text = item.text[1:]
            elif isinstance(item, EUnit) and len(item.name) > 1:
                item.name = item.name[1:]
            else:
                slot.items.pop(pos)

    def _flatten_structure(self, item: EditItem) -> list[EditItem]:
        if isinstance(item, EFraction):
            result = list(item.numerator.items)
            if item.denominator.items:
                result.append(EOp("/"))
                result.extend(item.denominator.items)
            return result if result else []
        if isinstance(item, ESuperscript):
            return list(item.exponent.items)
        if isinstance(item, EParens):
            return list(item.inner.items)
        if isinstance(item, ESqrt):
            return list(item.radicand.items)
        if isinstance(item, EAbs):
            return list(item.inner.items)
        if isinstance(item, EMatrix):
            result = []
            for row in item.cells:
                for cell in row:
                    result.extend(cell.items)
            return result
        if isinstance(item, (ESummation, EProduct)):
            result = list(item.body_slot.items)
            return result if result else []
        if isinstance(item, EIntegral):
            result = list(item.body_slot.items)
            return result if result else []
        if isinstance(item, EDerivative):
            result = list(item.body_slot.items)
            return result if result else []
        if isinstance(item, ERange):
            result = list(item.start_slot.items)
            result.extend(item.end_slot.items)
            return result if result else []
        if isinstance(item, ESystem):
            result = []
            for row in item.rows:
                result.extend(row.items)
            return result if result else []
        return [item]

    # ---- Navigation ----

    def _get_child_slots(self, item: EditItem) -> list[EditSlot]:
        if isinstance(item, EFraction):
            return [item.numerator, item.denominator]
        if isinstance(item, ESuperscript):
            return [item.exponent]
        if isinstance(item, EParens):
            return [item.inner]
        if isinstance(item, ESqrt):
            return [item.radicand]
        if isinstance(item, EAbs):
            return [item.inner]
        if isinstance(item, EMatrix):
            slots = []
            for row in item.cells:
                slots.extend(row)
            return slots
        if isinstance(item, ESummation):
            return [item.var_slot, item.lower_slot, item.upper_slot, item.body_slot]
        if isinstance(item, EProduct):
            return [item.var_slot, item.lower_slot, item.upper_slot, item.body_slot]
        if isinstance(item, EIntegral):
            return [item.body_slot, item.var_slot, item.lower_slot, item.upper_slot]
        if isinstance(item, ERange):
            slots = [item.start_slot]
            if item.has_step:
                slots.append(item.step_slot)
            slots.append(item.end_slot)
            return slots
        if isinstance(item, EDerivative):
            return [item.body_slot, item.var_slot]
        if isinstance(item, ESystem):
            return list(item.rows)
        return []

    def _move_left(self):
        slot = self._active_slot
        if slot.cursor_pos > 0:
            slot.cursor_pos -= 1
            item = slot.items[slot.cursor_pos]
            if isinstance(item, EFraction):
                self._slot_stack.append(slot)
                self._active_slot = item.denominator
                self._active_slot.cursor_pos = len(self._active_slot.items)
            elif isinstance(item, ESuperscript):
                self._slot_stack.append(slot)
                self._active_slot = item.exponent
                self._active_slot.cursor_pos = len(self._active_slot.items)
            elif isinstance(item, EParens):
                self._slot_stack.append(slot)
                self._active_slot = item.inner
                self._active_slot.cursor_pos = len(self._active_slot.items)
            elif isinstance(item, ESqrt):
                self._slot_stack.append(slot)
                self._active_slot = item.radicand
                self._active_slot.cursor_pos = len(self._active_slot.items)
            elif isinstance(item, EAbs):
                self._slot_stack.append(slot)
                self._active_slot = item.inner
                self._active_slot.cursor_pos = len(self._active_slot.items)
            elif isinstance(item, (ESummation, EProduct)):
                self._slot_stack.append(slot)
                self._active_slot = item.body_slot
                self._active_slot.cursor_pos = len(self._active_slot.items)
            elif isinstance(item, EDerivative):
                self._slot_stack.append(slot)
                self._active_slot = item.body_slot
                self._active_slot.cursor_pos = len(self._active_slot.items)
            elif isinstance(item, EIntegral):
                self._slot_stack.append(slot)
                self._active_slot = item.body_slot
                self._active_slot.cursor_pos = len(self._active_slot.items)
            elif isinstance(item, ERange):
                self._slot_stack.append(slot)
                self._active_slot = item.end_slot
                self._active_slot.cursor_pos = len(self._active_slot.items)
            elif isinstance(item, ESystem):
                self._slot_stack.append(slot)
                self._active_slot = item.rows[-1]
                self._active_slot.cursor_pos = len(self._active_slot.items)
        elif self._slot_stack:
            parent = self._slot_stack[-1]
            for i, item in enumerate(parent.items):
                children = self._get_child_slots(item)
                if slot in children:
                    idx = children.index(slot)
                    if idx > 0:
                        self._active_slot = children[idx - 1]
                        self._active_slot.cursor_pos = len(self._active_slot.items)
                        return
                    self._active_slot = self._slot_stack.pop()
                    self._active_slot.cursor_pos = i
                    return
            self._active_slot = self._slot_stack.pop()

    def _move_right(self):
        slot = self._active_slot
        if slot.cursor_pos < len(slot.items):
            item = slot.items[slot.cursor_pos]
            if isinstance(item, EFraction):
                self._slot_stack.append(slot)
                self._active_slot = item.numerator
                self._active_slot.cursor_pos = 0
            elif isinstance(item, ESuperscript):
                self._slot_stack.append(slot)
                self._active_slot = item.exponent
                self._active_slot.cursor_pos = 0
            elif isinstance(item, EParens):
                self._slot_stack.append(slot)
                self._active_slot = item.inner
                self._active_slot.cursor_pos = 0
            elif isinstance(item, ESqrt):
                self._slot_stack.append(slot)
                self._active_slot = item.radicand
                self._active_slot.cursor_pos = 0
            elif isinstance(item, EAbs):
                self._slot_stack.append(slot)
                self._active_slot = item.inner
                self._active_slot.cursor_pos = 0
            elif isinstance(item, (ESummation, EProduct)):
                self._slot_stack.append(slot)
                self._active_slot = item.var_slot
                self._active_slot.cursor_pos = 0
            elif isinstance(item, EIntegral):
                self._slot_stack.append(slot)
                self._active_slot = item.body_slot
                self._active_slot.cursor_pos = 0
            elif isinstance(item, EDerivative):
                self._slot_stack.append(slot)
                self._active_slot = item.body_slot
                self._active_slot.cursor_pos = 0
            elif isinstance(item, ERange):
                self._slot_stack.append(slot)
                self._active_slot = item.start_slot
                self._active_slot.cursor_pos = 0
            elif isinstance(item, ESystem):
                self._slot_stack.append(slot)
                self._active_slot = item.rows[0]
                self._active_slot.cursor_pos = 0
            else:
                slot.cursor_pos += 1
        elif self._slot_stack:
            parent = self._slot_stack[-1]
            for i, item in enumerate(parent.items):
                children = self._get_child_slots(item)
                if slot in children:
                    idx = children.index(slot)
                    if idx + 1 < len(children):
                        self._active_slot = children[idx + 1]
                        self._active_slot.cursor_pos = 0
                        return
                    self._active_slot = self._slot_stack.pop()
                    self._active_slot.cursor_pos = i + 1
                    return
            self._active_slot = self._slot_stack.pop()
            self._active_slot.cursor_pos = min(
                self._active_slot.cursor_pos + 1,
                len(self._active_slot.items),
            )

    def _move_up(self):
        if self._slot_stack:
            parent = self._slot_stack[-1]
            for item in parent.items:
                if isinstance(item, EFraction):
                    if self._active_slot is item.denominator:
                        self._active_slot = item.numerator
                        self._active_slot.cursor_pos = min(
                            self._active_slot.cursor_pos,
                            len(self._active_slot.items),
                        )
                        return
                if isinstance(item, ESystem):
                    for r_idx, row in enumerate(item.rows):
                        if self._active_slot is row and r_idx > 0:
                            self._active_slot = item.rows[r_idx - 1]
                            self._active_slot.cursor_pos = min(
                                self._active_slot.cursor_pos,
                                len(self._active_slot.items),
                            )
                            return

    def _move_down(self):
        if self._slot_stack:
            parent = self._slot_stack[-1]
            for item in parent.items:
                if isinstance(item, EFraction):
                    if self._active_slot is item.numerator:
                        self._active_slot = item.denominator
                        self._active_slot.cursor_pos = min(
                            self._active_slot.cursor_pos,
                            len(self._active_slot.items),
                        )
                        return
                if isinstance(item, ESystem):
                    for r_idx, row in enumerate(item.rows):
                        if self._active_slot is row and r_idx + 1 < len(item.rows):
                            self._active_slot = item.rows[r_idx + 1]
                            self._active_slot.cursor_pos = min(
                                self._active_slot.cursor_pos,
                                len(self._active_slot.items),
                            )
                            return

    def _tab_next(self):
        if not self._slot_stack:
            return
        parent = self._slot_stack[-1]
        for i, item in enumerate(parent.items):
            children = self._get_child_slots(item)
            if self._active_slot in children:
                idx = children.index(self._active_slot)
                if idx + 1 < len(children):
                    self._active_slot = children[idx + 1]
                    self._active_slot.cursor_pos = len(self._active_slot.items)
                    return
                self._active_slot = self._slot_stack.pop()
                self._active_slot.cursor_pos = i + 1
                return
        self._active_slot = self._slot_stack.pop()

    def _tab_prev(self):
        if not self._slot_stack:
            return
        parent = self._slot_stack[-1]
        for i, item in enumerate(parent.items):
            children = self._get_child_slots(item)
            if self._active_slot in children:
                idx = children.index(self._active_slot)
                if idx > 0:
                    self._active_slot = children[idx - 1]
                    self._active_slot.cursor_pos = len(self._active_slot.items)
                    return
                self._active_slot = self._slot_stack.pop()
                self._active_slot.cursor_pos = i
                return
        self._active_slot = self._slot_stack.pop()

    # ================================================================
    # Live evaluation
    # ================================================================

    def _update_eval(self):
        if not self._eval_callback:
            self._eval_result = None
            self._eval_error = None
            return

        text = self.to_text().strip()
        if text.endswith("="):
            expr_text = text[:-1].strip()
            if expr_text:
                try:
                    self._eval_result = self._eval_callback(expr_text)
                    self._eval_error = None
                except Exception as ex:
                    self._eval_result = None
                    self._eval_error = str(ex)[:60]
            else:
                self._eval_result = None
                self._eval_error = None
        else:
            self._eval_result = None
            self._eval_error = None

    # ================================================================
    # Rendering
    # ================================================================

    def render(self):
        for item_id in self._items:
            try:
                self.canvas.delete(item_id)
            except Exception:
                pass
        self._items.clear()
        self._cursor_rx = None
        self._cursor_ry = None
        self._cursor_rh = None

        pre_box = self._measure_slot_only(self.root, self.font_size)
        total_w = pre_box.width + 8
        if self._eval_result is not None or self._eval_error:
            total_w += 80
        bg_id = self.canvas.create_rectangle(
            self.x - 2, self.y - 2,
            self.x + max(total_w, 20), self.y + max(pre_box.height, 16) + 2,
            fill="#fffff0", outline="#c0c0c0", width=1, dash=(2, 2),
        )
        self._items.append(bg_id)

        box = self._render_slot(self.root, self.x, self.y, self.font_size)

        if self._eval_result is not None or self._eval_error:
            self._render_eval_result(self.x + box.width + 4, self.y, box)

        if self._cursor_visible and self._cursor_rx is not None:
            self._draw_cursor()

        self._update_autocomplete()
        self._update_function_hint()

    def _measure_slot_only(self, slot: EditSlot, fs: int) -> _Box:
        return self._measure_slot(slot, fs)

    def _render_eval_result(self, rx: float, ry: float, box: _Box):
        from ..units import Quantity

        f = self._get_font(self.font_size)
        base_y = ry + box.baseline - self._line_height(self.font_size) * 0.6

        if self._eval_error:
            tid = self.canvas.create_text(
                rx, base_y, text=self._eval_error,
                anchor="nw", font=f, fill=_ERROR_COLOR)
            self._items.append(tid)
            return

        val = self._eval_result
        if isinstance(val, Quantity):
            val_text = self._fmt(val.value)
            unit_str = val.display_unit if hasattr(val, "display_unit") else str(val.unit)
            tid = self.canvas.create_text(
                rx, base_y, text=val_text, anchor="nw", font=f, fill=_RESULT_COLOR)
            self._items.append(tid)
            if unit_str:
                vw, _ = self._text_size(val_text, self.font_size)
                sp, _ = self._text_size(" ", self.font_size)
                uid = self.canvas.create_text(
                    rx + vw + sp, base_y, text=unit_str,
                    anchor="nw", font=f, fill=_UNIT_COLOR)
                self._items.append(uid)
        else:
            res_text = self._fmt(val)
            tid = self.canvas.create_text(
                rx, base_y, text=res_text,
                anchor="nw", font=f, fill=_RESULT_COLOR)
            self._items.append(tid)

    def _render_slot(self, slot: EditSlot, x: float, y: float, fs: int) -> _Box:
        if not slot.items:
            ph_w = max(fs * 0.8, 8)
            ph_h = self._line_height(fs)
            if slot is self._active_slot:
                self._cursor_rx = x
                self._cursor_ry = y
                self._cursor_rh = ph_h
            else:
                rid = self.canvas.create_rectangle(
                    x + 1, y + 2, x + ph_w - 1, y + ph_h - 2,
                    outline=_PLACEHOLDER_COLOR, fill="", dash=(2, 2))
                self._items.append(rid)
            return _Box(ph_w, ph_h, ph_h * 0.6)

        measures = [self._measure_item(it, fs) for it in slot.items]
        max_bl = max(m.baseline for m in measures) if measures else 0
        max_desc = max(m.height - m.baseline for m in measures) if measures else 0
        total_h = max_bl + max_desc
        if total_h < 1:
            total_h = self._line_height(fs)
            max_bl = total_h * 0.6

        cx = x
        for i, (item, mbox) in enumerate(zip(slot.items, measures)):
            if slot is self._active_slot and i == slot.cursor_pos:
                self._cursor_rx = cx
                self._cursor_ry = y
                self._cursor_rh = total_h

            item_y = y + max_bl - mbox.baseline
            self._render_item(item, cx, item_y, fs)
            cx += mbox.width

        if slot is self._active_slot and slot.cursor_pos == len(slot.items):
            self._cursor_rx = cx
            self._cursor_ry = y
            self._cursor_rh = total_h

        return _Box(cx - x, total_h, max_bl)

    # ---- Measure ----

    def _measure_item(self, item: EditItem, fs: int) -> _Box:
        if isinstance(item, EText):
            style = self._text_style(item.text)
            text = item.text
            if "." in text and style == "italic" and text and not text[0].isdigit():
                parts = text.split(".", 1)
                dp0 = _GREEK_DISPLAY.get(parts[0], parts[0])
                dp1 = _GREEK_DISPLAY.get(parts[1], parts[1])
                base_w, base_h = self._text_size(dp0, fs, style)
                sub_fs = max(int(fs * 0.70), 6)
                sub_w, sub_h = self._text_size(dp1, sub_fs, style)
                w = base_w + sub_w
                h = max(base_h, base_h * 0.45 + sub_h)
                return _Box(w, h, base_h * 0.6)
            display = _GREEK_DISPLAY.get(text, text)
            w, h = self._text_size(display, fs, style)
            return _Box(w, h, h * 0.6)
        if isinstance(item, EOp):
            display = _OP_DISPLAY.get(item.op, f" {item.op} ")
            w, h = self._text_size(display, fs)
            return _Box(w, h, h * 0.6)
        if isinstance(item, EFraction):
            return self._measure_fraction(item, fs)
        if isinstance(item, ESuperscript):
            return self._measure_sup(item, fs)
        if isinstance(item, EParens):
            return self._measure_parens(item, fs)
        if isinstance(item, ESqrt):
            return self._measure_sqrt(item, fs)
        if isinstance(item, EAbs):
            return self._measure_abs(item, fs)
        if isinstance(item, EUnit):
            sp_w, _ = self._text_size(" ", fs)
            w, h = self._text_size(item.name or " ", fs)
            return _Box(sp_w + w, h, h * 0.6)
        if isinstance(item, EMatrix):
            return self._measure_matrix(item, fs)
        if isinstance(item, ESummation):
            return self._measure_sum_prod(item, fs)
        if isinstance(item, EProduct):
            return self._measure_sum_prod(item, fs)
        if isinstance(item, EIntegral):
            return self._measure_integral(item, fs)
        if isinstance(item, ERange):
            return self._measure_range(item, fs)
        if isinstance(item, EDerivative):
            return self._measure_derivative(item, fs)
        if isinstance(item, ESystem):
            return self._measure_system(item, fs)
        return _Box(0, 0, 0)

    def _measure_sqrt(self, item: ESqrt, fs: int) -> _Box:
        rb = self._measure_slot(item.radicand, fs)
        sym_w, sym_h = self._text_size("√", fs)
        w = sym_w + rb.width + 4
        h = max(rb.height + 4, sym_h)
        return _Box(w, h, max(rb.baseline + 2, sym_h * 0.6))

    def _measure_abs(self, item: EAbs, fs: int) -> _Box:
        ib = self._measure_slot(item.inner, fs)
        bw, bh = self._text_size("|", fs)
        w = bw + ib.width + bw + 4
        h = max(bh, ib.height)
        return _Box(w, h, max(bh * 0.6, ib.baseline))

    def _measure_slot(self, slot: EditSlot, fs: int) -> _Box:
        if not slot.items:
            ph_w = max(fs * 0.8, 8)
            ph_h = self._line_height(fs)
            return _Box(ph_w, ph_h, ph_h * 0.6)
        total_w = 0.0
        max_bl = 0.0
        max_desc = 0.0
        for item in slot.items:
            m = self._measure_item(item, fs)
            total_w += m.width
            max_bl = max(max_bl, m.baseline)
            max_desc = max(max_desc, m.height - m.baseline)
        return _Box(total_w, max_bl + max_desc, max_bl)

    def _measure_fraction(self, item: EFraction, fs: int) -> _Box:
        nb = self._measure_slot(item.numerator, fs)
        db = self._measure_slot(item.denominator, fs)
        w = max(nb.width, db.width) + 2 * _FRAC_HPAD
        h = nb.height + db.height + 2 * _FRAC_VPAD + 2
        return _Box(w, h, nb.height + _FRAC_VPAD + 1)

    def _measure_sup(self, item: ESuperscript, fs: int) -> _Box:
        sup_fs = max(int(fs * _SUP_SCALE), 6)
        eb = self._measure_slot(item.exponent, sup_fs)
        base_h = self._line_height(fs)
        raise_amt = base_h * 0.35
        w = eb.width + 1
        h = max(base_h, eb.height + raise_amt)
        return _Box(w, h, h * 0.6)

    def _measure_parens(self, item: EParens, fs: int) -> _Box:
        ib = self._measure_slot(item.inner, fs)
        pw, ph = self._text_size("(", fs)
        w = pw + ib.width + pw
        h = max(ph, ib.height)
        return _Box(w, h, max(ph * 0.6, ib.baseline))

    def _measure_matrix(self, item: EMatrix, fs: int) -> _Box:
        col_widths = [0.0] * item.cols
        row_heights = [0.0] * item.rows
        for r in range(item.rows):
            for c in range(item.cols):
                cb = self._measure_slot(item.cells[r][c], fs)
                col_widths[c] = max(col_widths[c], cb.width)
                row_heights[r] = max(row_heights[r], cb.height)
        cell_pad = 6
        bracket_w = 6
        total_w = sum(col_widths) + cell_pad * (item.cols - 1) + 2 * bracket_w + 8
        total_h = sum(row_heights) + cell_pad * (item.rows - 1) + 8
        return _Box(total_w, total_h, total_h * 0.5)

    # ---- Render items ----

    def _render_item(self, item: EditItem, x: float, y: float, fs: int):
        if isinstance(item, EText):
            self._render_text(item, x, y, fs)
        elif isinstance(item, EOp):
            self._render_op(item, x, y, fs)
        elif isinstance(item, EFraction):
            self._render_fraction(item, x, y, fs)
        elif isinstance(item, ESuperscript):
            self._render_sup(item, x, y, fs)
        elif isinstance(item, EParens):
            self._render_parens(item, x, y, fs)
        elif isinstance(item, ESqrt):
            self._render_sqrt(item, x, y, fs)
        elif isinstance(item, EAbs):
            self._render_abs(item, x, y, fs)
        elif isinstance(item, EUnit):
            self._render_unit(item, x, y, fs)
        elif isinstance(item, EMatrix):
            self._render_matrix(item, x, y, fs)
        elif isinstance(item, ESummation):
            self._render_sum_prod(item, x, y, fs, "∑")
        elif isinstance(item, EProduct):
            self._render_sum_prod(item, x, y, fs, "∏")
        elif isinstance(item, EIntegral):
            self._render_integral(item, x, y, fs)
        elif isinstance(item, ERange):
            self._render_range(item, x, y, fs)
        elif isinstance(item, EDerivative):
            self._render_derivative(item, x, y, fs)
        elif isinstance(item, ESystem):
            self._render_system(item, x, y, fs)

    def _render_text(self, item: EText, x: float, y: float, fs: int):
        style = self._text_style(item.text)
        color = _NUMBER_COLOR
        text = item.text
        display = _GREEK_DISPLAY.get(text, text)

        if "." in text and style == "italic" and text and not text[0].isdigit():
            parts = text.split(".", 1)
            dp0 = _GREEK_DISPLAY.get(parts[0], parts[0])
            dp1 = _GREEK_DISPLAY.get(parts[1], parts[1])
            f = self._get_font(fs, style)
            tid = self.canvas.create_text(x, y, text=dp0, anchor="nw",
                                           font=f, fill=color)
            self._items.append(tid)
            base_w, _ = self._text_size(dp0, fs, style)
            sub_fs = max(int(fs * 0.70), 6)
            sf = self._get_font(sub_fs, style)
            base_h = self._line_height(fs)
            sub_y = y + base_h * 0.45
            sid = self.canvas.create_text(x + base_w, sub_y, text=dp1,
                                            anchor="nw", font=sf, fill=color)
            self._items.append(sid)
            return

        f = self._get_font(fs, style)
        tid = self.canvas.create_text(x, y, text=display, anchor="nw",
                                       font=f, fill=color)
        self._items.append(tid)

    def _render_op(self, item: EOp, x: float, y: float, fs: int):
        display = _OP_DISPLAY.get(item.op, f" {item.op} ")
        f = self._get_font(fs)
        tid = self.canvas.create_text(x, y, text=display, anchor="nw",
                                       font=f, fill=_OPERATOR_COLOR)
        self._items.append(tid)

    def _render_fraction(self, item: EFraction, x: float, y: float, fs: int):
        nb = self._measure_slot(item.numerator, fs)
        db = self._measure_slot(item.denominator, fs)
        bar_w = max(nb.width, db.width) + 2 * _FRAC_HPAD

        num_x = x + (bar_w - nb.width) / 2
        self._render_slot(item.numerator, num_x, y, fs)

        bar_y = y + nb.height + _FRAC_VPAD
        lid = self.canvas.create_line(x, bar_y, x + bar_w, bar_y,
                                       fill=_OPERATOR_COLOR, width=1)
        self._items.append(lid)

        den_y = bar_y + _FRAC_VPAD + 2
        den_x = x + (bar_w - db.width) / 2
        self._render_slot(item.denominator, den_x, den_y, fs)

    def _render_sup(self, item: ESuperscript, x: float, y: float, fs: int):
        sup_fs = max(int(fs * _SUP_SCALE), 6)
        self._render_slot(item.exponent, x, y, sup_fs)

    def _render_parens(self, item: EParens, x: float, y: float, fs: int):
        ib = self._measure_slot(item.inner, fs)
        f = self._get_font(fs)
        pw, ph = self._text_size("(", fs)

        lp = self.canvas.create_text(x, y, text="(", anchor="nw",
                                      font=f, fill=_OPERATOR_COLOR)
        self._items.append(lp)

        inner_y = y + max(0, (ph - ib.height) / 2)
        self._render_slot(item.inner, x + pw, inner_y, fs)

        rp = self.canvas.create_text(x + pw + ib.width, y, text=")",
                                      anchor="nw", font=f, fill=_OPERATOR_COLOR)
        self._items.append(rp)

    def _render_sqrt(self, item: ESqrt, x: float, y: float, fs: int):
        rb = self._measure_slot(item.radicand, fs)
        f = self._get_font(fs)
        sym_w, sym_h = self._text_size("√", fs)

        tid = self.canvas.create_text(x, y, text="√", anchor="nw",
                                        font=f, fill=_OPERATOR_COLOR)
        self._items.append(tid)

        rad_x = x + sym_w
        rad_y = y + 2
        self._render_slot(item.radicand, rad_x, rad_y, fs)

        lid = self.canvas.create_line(
            rad_x - 1, y, rad_x + rb.width + 2, y,
            fill=_OPERATOR_COLOR, width=1)
        self._items.append(lid)

    def _render_abs(self, item: EAbs, x: float, y: float, fs: int):
        ib = self._measure_slot(item.inner, fs)
        f = self._get_font(fs)
        bw, bh = self._text_size("|", fs)

        lp = self.canvas.create_text(x, y, text="|", anchor="nw",
                                      font=f, fill=_OPERATOR_COLOR)
        self._items.append(lp)

        inner_y = y + max(0, (bh - ib.height) / 2)
        self._render_slot(item.inner, x + bw + 2, inner_y, fs)

        rp = self.canvas.create_text(x + bw + 2 + ib.width + 2, y, text="|",
                                      anchor="nw", font=f, fill=_OPERATOR_COLOR)
        self._items.append(rp)

    def _render_matrix(self, item: EMatrix, x: float, y: float, fs: int):
        col_widths = [0.0] * item.cols
        row_heights = [0.0] * item.rows
        for r in range(item.rows):
            for c in range(item.cols):
                cb = self._measure_slot(item.cells[r][c], fs)
                col_widths[c] = max(col_widths[c], cb.width)
                row_heights[r] = max(row_heights[r], cb.height)
        cell_pad = 6
        bracket_w = 6
        total_w = sum(col_widths) + cell_pad * (item.cols - 1) + 2 * bracket_w + 8
        total_h = sum(row_heights) + cell_pad * (item.rows - 1) + 8

        # Left bracket
        lid = self.canvas.create_line(
            x + 2, y, x + bracket_w, y, x + bracket_w - 4, y,
            x + bracket_w - 4, y + total_h, x + bracket_w, y + total_h,
            x + 2, y + total_h,
            fill=_OPERATOR_COLOR, width=1)
        self._items.append(lid)

        # Right bracket
        rx = x + total_w - bracket_w
        rid = self.canvas.create_line(
            rx + bracket_w - 2, y, rx, y, rx + 4, y,
            rx + 4, y + total_h, rx, y + total_h,
            rx + bracket_w - 2, y + total_h,
            fill=_OPERATOR_COLOR, width=1)
        self._items.append(rid)

        # Render cells
        cy = y + 4
        for r in range(item.rows):
            cx = x + bracket_w + 4
            for c in range(item.cols):
                self._render_slot(item.cells[r][c], cx, cy, fs)
                cx += col_widths[c] + cell_pad
            cy += row_heights[r] + cell_pad

    def _measure_derivative(self, item: EDerivative, fs: int) -> _Box:
        db = self._measure_slot(item.body_slot, fs)
        vb = self._measure_slot(item.var_slot, fs)
        d_w, d_h = self._text_size("d", fs, "italic")
        frac_w = max(d_w + db.width, d_w + vb.width) + 2 * _FRAC_HPAD
        h = db.height + vb.height + d_h * 2 + 2 * _FRAC_VPAD + 4
        return _Box(frac_w, h, db.height + d_h + _FRAC_VPAD + 1)

    def _render_derivative(self, item: EDerivative, x: float, y: float, fs: int):
        db = self._measure_slot(item.body_slot, fs)
        vb = self._measure_slot(item.var_slot, fs)
        d_w, d_h = self._text_size("d", fs, "italic")
        frac_w = max(d_w + db.width, d_w + vb.width) + 2 * _FRAC_HPAD
        f = self._get_font(fs, "italic")
        # Numerator: d + body
        num_w = d_w + db.width
        nx = x + (frac_w - num_w) / 2
        tid = self.canvas.create_text(nx, y, text="d", anchor="nw", font=f, fill=_OPERATOR_COLOR)
        self._items.append(tid)
        self._render_slot(item.body_slot, nx + d_w, y, fs)
        # Fraction bar
        bar_y = y + max(db.height, d_h) + _FRAC_VPAD
        lid = self.canvas.create_line(x, bar_y, x + frac_w, bar_y,
                                       fill=_OPERATOR_COLOR, width=1)
        self._items.append(lid)
        # Denominator: d + var
        den_y = bar_y + _FRAC_VPAD + 2
        den_w = d_w + vb.width
        dx = x + (frac_w - den_w) / 2
        tid2 = self.canvas.create_text(dx, den_y, text="d", anchor="nw", font=f, fill=_OPERATOR_COLOR)
        self._items.append(tid2)
        self._render_slot(item.var_slot, dx + d_w, den_y, fs)

    def _measure_integral(self, item: EIntegral, fs: int) -> _Box:
        small_fs = max(int(fs * 0.65), 6)
        sym_w, sym_h = self._text_size("∫", int(fs * 1.6))
        lb = self._measure_slot(item.lower_slot, small_fs)
        ub = self._measure_slot(item.upper_slot, small_fs)
        bb = self._measure_slot(item.body_slot, fs)
        vb = self._measure_slot(item.var_slot, fs)
        dw, _ = self._text_size("d", fs, "italic")
        col_w = max(sym_w, lb.width, ub.width)
        w = col_w + bb.width + dw + vb.width + 6
        h = max(ub.height + sym_h + lb.height + 4, bb.height)
        return _Box(w, h, ub.height + sym_h * 0.6)

    def _render_integral(self, item: EIntegral, x: float, y: float, fs: int):
        small_fs = max(int(fs * 0.65), 6)
        big_fs = int(fs * 1.6)
        sym_w, sym_h = self._text_size("∫", big_fs)
        ub = self._measure_slot(item.upper_slot, small_fs)
        lb = self._measure_slot(item.lower_slot, small_fs)
        bb = self._measure_slot(item.body_slot, fs)
        col_w = max(sym_w, lb.width, ub.width)
        uy = y
        self._render_slot(item.upper_slot, x + (col_w - ub.width) / 2, uy, small_fs)
        sy = uy + ub.height + 2
        f = self._get_font(big_fs)
        tid = self.canvas.create_text(
            x + (col_w - sym_w) / 2, sy, text="∫",
            anchor="nw", font=f, fill=_OPERATOR_COLOR)
        self._items.append(tid)
        ly = sy + sym_h + 2
        self._render_slot(item.lower_slot, x + (col_w - lb.width) / 2, ly, small_fs)
        body_y = sy + (sym_h - bb.height) / 2
        bx = x + col_w + 4
        self._render_slot(item.body_slot, bx, body_y, fs)
        # Render "d" + var
        dx = bx + bb.width + 2
        df = self._get_font(fs, "italic")
        did = self.canvas.create_text(
            dx, body_y, text="d", anchor="nw", font=df, fill=_OPERATOR_COLOR)
        self._items.append(did)
        dw, _ = self._text_size("d", fs, "italic")
        self._render_slot(item.var_slot, dx + dw, body_y, fs)

    def _measure_range(self, item: ERange, fs: int) -> _Box:
        sb = self._measure_slot(item.start_slot, fs)
        eb = self._measure_slot(item.end_slot, fs)
        dots_w, dots_h = self._text_size(" .. ", fs)
        w = sb.width + dots_w + eb.width
        if item.has_step:
            stb = self._measure_slot(item.step_slot, fs)
            comma_w, _ = self._text_size(", ", fs)
            w += comma_w + stb.width
        h = max(sb.height, eb.height, dots_h)
        return _Box(w, h, h * 0.6)

    def _render_range(self, item: ERange, x: float, y: float, fs: int):
        f = self._get_font(fs)
        cx = x
        sb = self._render_slot(item.start_slot, cx, y, fs)
        cx += sb.width
        if item.has_step:
            comma_w, _ = self._text_size(", ", fs)
            tid = self.canvas.create_text(cx, y, text=", ", anchor="nw", font=f, fill=_OPERATOR_COLOR)
            self._items.append(tid)
            cx += comma_w
            stb = self._render_slot(item.step_slot, cx, y, fs)
            cx += stb.width
        dots_w, _ = self._text_size(" .. ", fs)
        tid = self.canvas.create_text(cx, y, text=" .. ", anchor="nw", font=f, fill=_OPERATOR_COLOR)
        self._items.append(tid)
        cx += dots_w
        self._render_slot(item.end_slot, cx, y, fs)

    def _measure_system(self, item: ESystem, fs: int) -> _Box:
        brace_w = max(int(fs * 0.8), 10)
        row_pad = 4
        max_w = 0.0
        total_h = 0.0
        for row in item.rows:
            rb = self._measure_slot(row, fs)
            max_w = max(max_w, rb.width)
            total_h += rb.height + row_pad
        total_h -= row_pad
        total_h = max(total_h, self._line_height(fs))
        return _Box(brace_w + 4 + max_w, total_h, total_h * 0.5)

    def _render_system(self, item: ESystem, x: float, y: float, fs: int):
        brace_w = max(int(fs * 0.8), 10)
        row_pad = 4
        row_boxes = []
        total_h = 0.0
        for row in item.rows:
            rb = self._measure_slot(row, fs)
            row_boxes.append(rb)
            total_h += rb.height + row_pad
        total_h -= row_pad
        total_h = max(total_h, self._line_height(fs))
        # Draw curly brace
        brace_fs = max(int(total_h * 0.7), fs)
        f = self._get_font(brace_fs)
        tid = self.canvas.create_text(
            x, y + total_h * 0.15, text="{",
            anchor="nw", font=f, fill=_OPERATOR_COLOR)
        self._items.append(tid)
        # If brace doesn't span full height, draw vertical lines
        if total_h > self._line_height(fs) * 1.5:
            mid_y = y + total_h * 0.5
            lid = self.canvas.create_line(
                x + 3, y + 2, x + 3, mid_y - 4,
                fill=_OPERATOR_COLOR, width=1)
            self._items.append(lid)
            lid2 = self.canvas.create_line(
                x + 3, mid_y + 4, x + 3, y + total_h - 2,
                fill=_OPERATOR_COLOR, width=1)
            self._items.append(lid2)
        content_x = x + brace_w + 4
        cy = y
        for row, rb in zip(item.rows, row_boxes):
            self._render_slot(row, content_x, cy, fs)
            cy += rb.height + row_pad

    def _measure_sum_prod(self, item, fs: int) -> _Box:
        small_fs = max(int(fs * 0.65), 6)
        sym_w, sym_h = self._text_size("∑", int(fs * 1.5))
        lb = self._measure_slot(item.lower_slot, small_fs)
        ub = self._measure_slot(item.upper_slot, small_fs)
        bb = self._measure_slot(item.body_slot, fs)
        col_w = max(sym_w, lb.width, ub.width)
        w = col_w + bb.width + 4
        h = ub.height + sym_h + lb.height + 4
        return _Box(w, h, ub.height + sym_h * 0.6)

    def _render_sum_prod(self, item, x: float, y: float, fs: int, symbol: str):
        small_fs = max(int(fs * 0.65), 6)
        big_fs = int(fs * 1.5)
        sym_w, sym_h = self._text_size(symbol, big_fs)
        ub = self._measure_slot(item.upper_slot, small_fs)
        lb = self._measure_slot(item.lower_slot, small_fs)
        bb = self._measure_slot(item.body_slot, fs)
        col_w = max(sym_w, lb.width, ub.width)
        uy = y
        self._render_slot(item.upper_slot, x + (col_w - ub.width) / 2, uy, small_fs)
        sy = uy + ub.height + 2
        f = self._get_font(big_fs)
        tid = self.canvas.create_text(
            x + (col_w - sym_w) / 2, sy, text=symbol,
            anchor="nw", font=f, fill=_OPERATOR_COLOR)
        self._items.append(tid)
        ly = sy + sym_h + 2
        self._render_slot(item.lower_slot, x + (col_w - lb.width) / 2, ly, small_fs)
        body_y = sy + (sym_h - bb.height) / 2
        self._render_slot(item.body_slot, x + col_w + 4, body_y, fs)

    def _render_unit(self, item: EUnit, x: float, y: float, fs: int):
        f = self._get_font(fs)
        name = item.name or " "
        sp_w, _ = self._text_size(" ", fs)
        tid = self.canvas.create_text(x + sp_w, y, text=name, anchor="nw",
                                       font=f, fill=_UNIT_COLOR)
        self._items.append(tid)

    # ---- Cursor ----

    def _draw_cursor(self):
        if self._cursor_rx is None:
            return
        x = self._cursor_rx
        y = self._cursor_ry
        h = self._cursor_rh or self._line_height(self.font_size)
        self._cursor_item = self.canvas.create_line(
            x, y, x, y + h, fill=_CURSOR_COLOR, width=2)
        self._items.append(self._cursor_item)

    def _start_blink(self):
        self._cursor_visible = True
        if self._cursor_rx is not None:
            self._draw_cursor()
        try:
            self._blink_id = self.canvas.after(530, self._blink)
        except Exception:
            pass

    def _blink(self):
        self._cursor_visible = not self._cursor_visible
        if self._cursor_item is not None:
            try:
                fill = _CURSOR_COLOR if self._cursor_visible else ""
                self.canvas.itemconfigure(self._cursor_item, fill=fill)
            except Exception:
                pass
        try:
            self._blink_id = self.canvas.after(530, self._blink)
        except Exception:
            pass

    def stop_blink(self):
        if self._blink_id:
            try:
                self.canvas.after_cancel(self._blink_id)
            except Exception:
                pass
            self._blink_id = None

    # ---- Helpers ----

    def _text_style(self, text: str) -> str:
        if not text:
            return "italic"
        if text[0].isdigit() or text[0] == ".":
            return ""
        if text in _BUILTIN_VARS:
            return "bold"
        return "italic"

    def _fmt(self, val: Any) -> str:
        p = self._precision
        if isinstance(val, float):
            if _math.isnan(val):
                return "NaN"
            if _math.isinf(val):
                return "∞" if val > 0 else "-∞"
            if val == int(val) and abs(val) < 1e15:
                return str(int(val))
            return f"{val:.{p}g}"
        if isinstance(val, int):
            return str(val)
        try:
            import numpy as np
            if isinstance(val, np.ndarray):
                with np.printoptions(precision=p, suppress=True):
                    return str(val)
        except ImportError:
            pass
        return str(val)

    # ================================================================
    # Text conversion
    # ================================================================

    def to_text(self) -> str:
        return self._slot_to_text(self.root)

    def _slot_to_text(self, slot: EditSlot) -> str:
        parts: list[str] = []
        for item in slot.items:
            if isinstance(item, EText):
                parts.append(item.text)
            elif isinstance(item, EOp):
                if item.op == ":":
                    parts.append(" := ")
                elif item.op in ("+", "-", "*", "=", "<", ">",
                                 "≤", "≥", "≠"):
                    parts.append(f" {item.op} ")
                elif item.op == ",":
                    parts.append(", ")
                else:
                    parts.append(item.op)
            elif isinstance(item, EFraction):
                num = self._slot_to_text(item.numerator) or "0"
                den = self._slot_to_text(item.denominator) or "1"
                parts.append(f"({num})/({den})")
            elif isinstance(item, ESuperscript):
                exp = self._slot_to_text(item.exponent) or "1"
                parts.append(f"^({exp})")
            elif isinstance(item, EParens):
                inner = self._slot_to_text(item.inner) or "0"
                parts.append(f"({inner})")
            elif isinstance(item, ESqrt):
                rad = self._slot_to_text(item.radicand) or "0"
                parts.append(f"sqrt({rad})")
            elif isinstance(item, EAbs):
                inner = self._slot_to_text(item.inner) or "0"
                parts.append(f"abs({inner})")
            elif isinstance(item, EMatrix):
                cell_texts = []
                for row in item.cells:
                    for cell in row:
                        cell_texts.append(self._slot_to_text(cell) or "0")
                cell_texts.append(str(item.rows))
                cell_texts.append(str(item.cols))
                parts.append(f"mat({', '.join(cell_texts)})")
            elif isinstance(item, ESummation):
                body = self._slot_to_text(item.body_slot) or "0"
                var = self._slot_to_text(item.var_slot) or "i"
                lo = self._slot_to_text(item.lower_slot) or "1"
                hi = self._slot_to_text(item.upper_slot) or "n"
                parts.append(f"sum({body}, {var}, {lo}, {hi})")
            elif isinstance(item, EProduct):
                body = self._slot_to_text(item.body_slot) or "0"
                var = self._slot_to_text(item.var_slot) or "i"
                lo = self._slot_to_text(item.lower_slot) or "1"
                hi = self._slot_to_text(item.upper_slot) or "n"
                parts.append(f"product({body}, {var}, {lo}, {hi})")
            elif isinstance(item, EIntegral):
                body = self._slot_to_text(item.body_slot) or "0"
                var = self._slot_to_text(item.var_slot) or "x"
                lo = self._slot_to_text(item.lower_slot) or "0"
                hi = self._slot_to_text(item.upper_slot) or "1"
                parts.append(f"nintegrate({body}, {var}, {lo}, {hi})")
            elif isinstance(item, ERange):
                s = self._slot_to_text(item.start_slot) or "0"
                e = self._slot_to_text(item.end_slot) or "1"
                if item.has_step:
                    st = self._slot_to_text(item.step_slot) or "0.1"
                    parts.append(f"range({s}, {e}, {st})")
                else:
                    parts.append(f"range({s}, {e})")
            elif isinstance(item, EDerivative):
                body = self._slot_to_text(item.body_slot) or "f"
                var = self._slot_to_text(item.var_slot) or "x"
                parts.append(f"diff({body}, {var})")
            elif isinstance(item, ESystem):
                row_texts = []
                for row in item.rows:
                    rt = self._slot_to_text(row) or "0"
                    row_texts.append(rt)
                parts.append("line(" + ", ".join(row_texts) + ")")
            elif isinstance(item, EUnit):
                parts.append(f"'{item.name}'")
        return "".join(parts)

    # ================================================================
    # Load from AST
    # ================================================================

    def from_ast(self, node: ASTNode, has_result: bool = False):
        self.root = EditSlot()
        self._active_slot = self.root
        self._slot_stack = []
        self._ast_to_slot(node, self.root)
        if has_result and not (isinstance(node, BinaryOp) and node.operator == ":"):
            self.root.items.append(EOp("="))
        self.root.cursor_pos = len(self.root.items)
        self._update_eval()
        self.render()

    def _ast_to_slot(self, node: ASTNode, slot: EditSlot):
        if isinstance(node, Number):
            v = node.value
            if isinstance(v, float) and v == int(v) and abs(v) < 1e15:
                slot.items.append(EText(str(int(v))))
            else:
                slot.items.append(EText(str(v)))
        elif isinstance(node, Variable):
            slot.items.append(EText(node.name))
        elif isinstance(node, UnitRef):
            slot.items.append(EUnit(node.name))
        elif isinstance(node, StringLiteral):
            slot.items.append(EText(f'"{node.value}"'))
        elif isinstance(node, UnaryOp):
            if node.operator == "-":
                slot.items.append(EOp("-"))
            self._ast_to_slot(node.operand, slot)
        elif isinstance(node, BinaryOp):
            if node.operator == "/":
                frac = EFraction()
                self._ast_to_slot(node.left, frac.numerator)
                frac.numerator.cursor_pos = len(frac.numerator.items)
                self._ast_to_slot(node.right, frac.denominator)
                frac.denominator.cursor_pos = len(frac.denominator.items)
                slot.items.append(frac)
            elif node.operator == "^":
                self._ast_to_slot(node.left, slot)
                sup = ESuperscript()
                self._ast_to_slot(node.right, sup.exponent)
                sup.exponent.cursor_pos = len(sup.exponent.items)
                slot.items.append(sup)
            elif node.operator == ":":
                self._ast_to_slot(node.left, slot)
                slot.items.append(EOp(":"))
                self._ast_to_slot(node.right, slot)
            elif node.operator == "*" and isinstance(node.right, UnitRef):
                self._ast_to_slot(node.left, slot)
                slot.items.append(EOp("*"))
                self._ast_to_slot(node.right, slot)
            else:
                self._ast_to_slot(node.left, slot)
                slot.items.append(EOp(node.operator))
                self._ast_to_slot(node.right, slot)
        elif isinstance(node, FunctionCall):
            if node.name == "sqrt" and len(node.args) == 1:
                sq = ESqrt()
                self._ast_to_slot(node.args[0], sq.radicand)
                sq.radicand.cursor_pos = len(sq.radicand.items)
                slot.items.append(sq)
            elif node.name == "abs" and len(node.args) == 1:
                ab = EAbs()
                self._ast_to_slot(node.args[0], ab.inner)
                ab.inner.cursor_pos = len(ab.inner.items)
                slot.items.append(ab)
            elif node.name in ("diff", "nderiv") and len(node.args) == 2:
                d = EDerivative()
                self._ast_to_slot(node.args[0], d.body_slot)
                d.body_slot.cursor_pos = len(d.body_slot.items)
                self._ast_to_slot(node.args[1], d.var_slot)
                d.var_slot.cursor_pos = len(d.var_slot.items)
                slot.items.append(d)
            elif node.name in ("nintegrate", "int") and len(node.args) == 4:
                ig = EIntegral()
                self._ast_to_slot(node.args[0], ig.body_slot)
                ig.body_slot.cursor_pos = len(ig.body_slot.items)
                self._ast_to_slot(node.args[1], ig.var_slot)
                ig.var_slot.cursor_pos = len(ig.var_slot.items)
                self._ast_to_slot(node.args[2], ig.lower_slot)
                ig.lower_slot.cursor_pos = len(ig.lower_slot.items)
                self._ast_to_slot(node.args[3], ig.upper_slot)
                ig.upper_slot.cursor_pos = len(ig.upper_slot.items)
                slot.items.append(ig)
            elif node.name == "sum" and len(node.args) == 4:
                s = ESummation()
                self._ast_to_slot(node.args[0], s.body_slot)
                s.body_slot.cursor_pos = len(s.body_slot.items)
                self._ast_to_slot(node.args[1], s.var_slot)
                s.var_slot.cursor_pos = len(s.var_slot.items)
                self._ast_to_slot(node.args[2], s.lower_slot)
                s.lower_slot.cursor_pos = len(s.lower_slot.items)
                self._ast_to_slot(node.args[3], s.upper_slot)
                s.upper_slot.cursor_pos = len(s.upper_slot.items)
                slot.items.append(s)
            elif node.name == "product" and len(node.args) == 4:
                p = EProduct()
                self._ast_to_slot(node.args[0], p.body_slot)
                p.body_slot.cursor_pos = len(p.body_slot.items)
                self._ast_to_slot(node.args[1], p.var_slot)
                p.var_slot.cursor_pos = len(p.var_slot.items)
                self._ast_to_slot(node.args[2], p.lower_slot)
                p.lower_slot.cursor_pos = len(p.lower_slot.items)
                self._ast_to_slot(node.args[3], p.upper_slot)
                p.upper_slot.cursor_pos = len(p.upper_slot.items)
                slot.items.append(p)
            elif node.name == "line" and len(node.args) >= 2:
                sys = ESystem()
                sys.rows = []
                for arg in node.args:
                    row_slot = EditSlot()
                    self._ast_to_slot(arg, row_slot)
                    row_slot.cursor_pos = len(row_slot.items)
                    sys.rows.append(row_slot)
                slot.items.append(sys)
            else:
                slot.items.append(EText(node.name))
                parens = EParens()
                for i, arg in enumerate(node.args):
                    if i > 0:
                        parens.inner.items.append(EOp(","))
                    self._ast_to_slot(arg, parens.inner)
                parens.inner.cursor_pos = len(parens.inner.items)
                slot.items.append(parens)
        elif isinstance(node, Evaluation):
            self._ast_to_slot(node.expression, slot)
            slot.items.append(EOp("="))

    def from_text(self, text: str):
        from ..infix_parser import parse_infix
        ast = parse_infix(text)
        if ast is not None:
            has_result = text.strip().endswith("=")
            self.from_ast(ast, has_result=has_result)
        elif text.strip():
            self.root = EditSlot()
            self.root.items.append(EText(text.strip()))
            self.root.cursor_pos = 1
            self._active_slot = self.root
            self._slot_stack = []
            self.render()

    # ================================================================
    # Autocomplete
    # ================================================================

    def _update_autocomplete(self):
        self._hide_autocomplete()
        slot = self._active_slot
        pos = slot.cursor_pos
        if pos == 0:
            return
        item = slot.items[pos - 1]
        if not isinstance(item, EText):
            return
        text = item.text
        if not text or text[0].isdigit():
            return
        if len(text) < 2:
            return
        matches = [n for n in _FUNCTION_NAMES if n.startswith(text) and n != text]
        if not matches:
            return
        self._ac_suggestions = matches[:8]
        self._ac_selected = 0
        self._ac_prefix = text
        self._show_autocomplete()

    def _show_autocomplete(self):
        if not self._ac_suggestions:
            return
        self._ac_visible = True
        cx = self._cursor_rx or self.x
        cy = (self._cursor_ry or self.y) + (self._cursor_rh or 16) + 2
        f = self._get_font(self.font_size - 1)
        max_w = 0
        for s in self._ac_suggestions:
            w, _ = self._text_size(s, self.font_size - 1)
            max_w = max(max_w, w)
        row_h = self._line_height(self.font_size - 1) + 2
        total_h = row_h * len(self._ac_suggestions) + 4
        bg = self.canvas.create_rectangle(
            cx, cy, cx + max_w + 12, cy + total_h,
            fill="#ffffff", outline="#cccccc", width=1)
        self._ac_items.append(bg)
        for i, name in enumerate(self._ac_suggestions):
            ry = cy + 2 + i * row_h
            if i == self._ac_selected:
                sel_bg = self.canvas.create_rectangle(
                    cx + 1, ry, cx + max_w + 11, ry + row_h,
                    fill="#3366cc", outline="")
                self._ac_items.append(sel_bg)
                color = "#ffffff"
            else:
                color = "#000000"
            tid = self.canvas.create_text(
                cx + 4, ry + 1, text=name, anchor="nw",
                font=f, fill=color)
            self._ac_items.append(tid)

    def _hide_autocomplete(self):
        for item_id in self._ac_items:
            try:
                self.canvas.delete(item_id)
            except Exception:
                pass
        self._ac_items.clear()
        self._ac_visible = False
        self._ac_suggestions = []

    def _accept_autocomplete(self):
        if not self._ac_visible or not self._ac_suggestions:
            return False
        chosen = self._ac_suggestions[self._ac_selected]
        slot = self._active_slot
        pos = slot.cursor_pos
        if pos > 0 and isinstance(slot.items[pos - 1], EText):
            slot.items[pos - 1].text = chosen
        self._hide_autocomplete()
        self._insert_char("(")
        return True

    # ================================================================
    # Function hints
    # ================================================================

    def _update_function_hint(self):
        self._hide_function_hint()
        if self._ac_visible:
            return
        func_name = self._find_enclosing_function()
        if func_name and func_name in _FUNCTION_HINTS:
            hint_text = _FUNCTION_HINTS[func_name]
            cx = self._cursor_rx or self.x
            cy = (self._cursor_ry or self.y) - self._line_height(self.font_size) - 4
            if cy < self.y - 20:
                cy = (self._cursor_ry or self.y) + (self._cursor_rh or 16) + 2
            f = self._get_font(max(self.font_size - 2, 8))
            tw, th = self._text_size(hint_text, max(self.font_size - 2, 8))
            bg = self.canvas.create_rectangle(
                cx - 2, cy - 1, cx + tw + 6, cy + th + 2,
                fill="#ffffcc", outline="#cccc88", width=1)
            self._hint_items.append(bg)
            tid = self.canvas.create_text(
                cx + 2, cy, text=hint_text, anchor="nw",
                font=f, fill="#666666")
            self._hint_items.append(tid)

    def _hide_function_hint(self):
        for item_id in self._hint_items:
            try:
                self.canvas.delete(item_id)
            except Exception:
                pass
        self._hint_items.clear()

    def _find_enclosing_function(self) -> Optional[str]:
        if not self._slot_stack:
            return None
        parent = self._slot_stack[-1]
        for i, item in enumerate(parent.items):
            if isinstance(item, EParens) and item.inner is self._active_slot:
                if i > 0 and isinstance(parent.items[i - 1], EText):
                    name = parent.items[i - 1].text
                    if name in _FUNCTION_HINTS:
                        return name
        return None

    # ================================================================
    # Cleanup
    # ================================================================

    def destroy(self):
        self._hide_autocomplete()
        self._hide_function_hint()
        self.stop_blink()
        for item_id in self._items:
            try:
                self.canvas.delete(item_id)
            except Exception:
                pass
        self._items.clear()

    def get_items(self) -> list[int]:
        return list(self._items)
