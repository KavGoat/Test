"""Mathematical expression renderer for SMath Studio GUI.

Renders AST nodes on a tkinter Canvas with proper mathematical typesetting:
fractions, superscripts, subscripts, radicals, matrices, integral signs, etc.
"""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import font as tkfont
from dataclasses import dataclass
from typing import Any, Optional

from ..expression import (
    ASTNode, Number, Variable, UnitRef, StringLiteral,
    BinaryOp, UnaryOp, FunctionCall, Evaluation,
)
from ..units import Quantity

import numpy as np


# ---------------------------------------------------------------------------
# Rendering result
# ---------------------------------------------------------------------------

@dataclass
class RenderBox:
    """Result of rendering a node: the space it occupies and its baseline."""
    width: float
    height: float
    baseline: float  # distance from top to the math baseline (center line)


# ---------------------------------------------------------------------------
# Style constants matching SMath Studio settings.prop
# ---------------------------------------------------------------------------

_NUMBER_COLOR = "#000000"
_STRING_COLOR = "#a31515"
_BUILTIN_VAR_COLOR = "#000080"
_USER_VAR_COLOR = "#000000"
_UNIT_COLOR = "#0000ff"
_OPERATOR_COLOR = "#000000"
_FUNCTION_COLOR = "#000080"
_ERROR_COLOR = "#ff0000"
_RESULT_COLOR = "#0000ff"
_ERROR_BG_COLOR = "#fff0f0"
_ERROR_BORDER_COLOR = "#cc0000"

_OP_HPAD = 4       # horizontal padding around binary operators
_FRAC_HPAD = 6     # horizontal padding inside fraction bar
_FRAC_VPAD = 3     # vertical padding above/below fraction bar
_SUP_SCALE = 0.70  # superscript size ratio
_SUB_SCALE = 0.75  # subscript size ratio
_SUP_RAISE = 0.38  # superscript vertical shift (fraction of parent height)
_SUB_DROP = 0.25   # subscript vertical shift
_PAREN_HPAD = 2    # padding inside parentheses
_MATRIX_CELL_PAD = 8  # padding between matrix cells
_MATRIX_BRACKET_W = 5  # width of matrix brackets

# Built-in function names recognized by SMath Studio
_BUILTIN_FUNCTIONS = {
    "sin", "cos", "tan", "asin", "acos", "atan", "cot", "sec", "csc",
    "acot", "asec", "acsc", "sinh", "cosh", "tanh", "asinh", "acosh", "atanh",
    "tg", "ctg", "sh", "ch", "th", "cth", "cosec", "arcsec", "arccosec",
    "arctg", "arcctg", "arcsin", "arccos",
    "ln", "log", "lg", "exp", "sqrt", "nthroot", "abs", "sign", "ceil", "floor", "round",
    "max", "min", "mod", "sum", "product", "nintegrate", "diff", "nderiv",
    "lim", "int", "sys",
    "det", "invert", "transpose", "identity", "el", "rows", "cols",
    "mean", "median", "stdev", "sort", "reverse", "length",
    "if", "for", "while", "line", "range", "eval", "mat",
    "re", "im", "arg", "conj", "Gamma", "Beta", "erf",
    "polyroots", "solve", "augment", "stack", "col", "submatrix",
    "csort", "rsort", "tr", "num2str", "str2num",
}

# Built-in variable / constant names
_BUILTIN_VARS = {
    "π", "pi", "e", "i", "∞", "inf",
    "g.e", "c", "m.e", "m.p", "m.n", "u",
    "G.N", "h", "N.A", "k", "R.m",
    "ε.0", "μ.0",
}

_GREEK_DISPLAY = {
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

# Operators that render as special symbols
_DISPLAY_OPS = {
    "*": "·",
    "-": "−",
    "≤": "≤",
    "≥": "≥",
    "≠": "≠",
    "≡": "≡",
    ":": ":=",
    "&": "∧",
    "|": "∨",
    "±": "±",
    "⇔": "⇔",
    "→": "→",
    "←": "←",
    "⇒": "⇒",
}


class MathRenderer:
    """Renders math AST nodes onto a tkinter Canvas with proper typesetting."""

    def __init__(self, canvas: Optional[tk.Canvas] = None):
        self._font_cache: dict[tuple[str, int, str], tkfont.Font] = {}
        self._measure_cache: dict[tuple, RenderBox] = {}
        self._font_family = "serif"
        self._canvas: Optional[tk.Canvas] = canvas
        if canvas is not None:
            self._detect_font(canvas)

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def render(
        self,
        canvas: tk.Canvas,
        math_data_or_node: Any,
        x: float,
        y: float,
        eval_result: Any = None,
        *,
        font_size: int = 12,
        color: str = "#000000",
        context: Any = None,
        trailing_zeros: bool = False,
        exp_threshold: int = 5,
        fractions_mode: str = "decimal",
    ) -> list[int]:
        """Render a math region or AST node on *canvas*.

        Accepts either a MathRegion (from parser) or a bare ASTNode.
        Returns a list of canvas item IDs for easy deletion/management.
        """
        self._canvas = canvas
        self._detect_font(canvas)

        items_before = set(canvas.find_all())

        from ..parser import MathRegion
        if isinstance(math_data_or_node, MathRegion):
            node = math_data_or_node.input_expr
            if node is None:
                return []
            precision = math_data_or_node.decimal_places or 4
            if isinstance(node, BinaryOp) and node.operator in (":", "=", "≡"):
                if eval_result is not None and math_data_or_node.result_elements:
                    self.render_with_result(
                        canvas, node, eval_result, x, y,
                        font_size=font_size, context=context, precision=precision,
                        trailing_zeros=trailing_zeros, exp_threshold=exp_threshold,
                        fractions_mode=fractions_mode,
                    )
                else:
                    self._render_node(canvas, node, x, y, font_size, context)
            elif eval_result is not None:
                self.render_with_result(
                    canvas, node, eval_result, x, y,
                    font_size=font_size, context=context, precision=precision,
                    trailing_zeros=trailing_zeros, exp_threshold=exp_threshold,
                    fractions_mode=fractions_mode,
                )
            elif math_data_or_node.result_expr is not None:
                self.render_with_result(
                    canvas, node, math_data_or_node.result_expr, x, y,
                    font_size=font_size, context=context, precision=precision,
                    trailing_zeros=trailing_zeros, exp_threshold=exp_threshold,
                    fractions_mode=fractions_mode,
                )
            else:
                self._render_node(canvas, node, x, y, font_size, context)
        elif isinstance(math_data_or_node, ASTNode):
            self._render_node(canvas, math_data_or_node, x, y, font_size, context)
        else:
            return []

        # Render descriptions if present
        if hasattr(math_data_or_node, 'descriptions'):
            for desc in getattr(math_data_or_node, 'descriptions', []):
                if desc.active and desc.text:
                    f = self._get_font(canvas, max(font_size - 1, 8))
                    my_items = list(set(canvas.find_all()) - items_before)
                    bbox = canvas.bbox(*my_items) if my_items else None
                    desc_x = (bbox[2] + 10) if bbox else (x + 200)
                    canvas.create_text(
                        desc_x, y + 2, text=desc.text, anchor="nw",
                        font=f, fill="#666666",
                    )

        items_after = set(canvas.find_all())
        return list(items_after - items_before)

    def render_node(
        self,
        canvas: tk.Canvas,
        node: ASTNode,
        x: float,
        y: float,
        font_size: int = 12,
        context: Any = None,
    ) -> RenderBox:
        """Render a single AST node. Returns the bounding box."""
        self._canvas = canvas
        self._detect_font(canvas)
        return self._render_node(canvas, node, x, y, font_size, context)

    def measure(
        self,
        canvas: tk.Canvas,
        node: ASTNode,
        font_size: int = 12,
        context: Any = None,
    ) -> RenderBox:
        """Measure how much space *node* would occupy without drawing."""
        self._canvas = canvas
        self._detect_font(canvas)
        return self._measure_node(node, font_size, context)

    # -----------------------------------------------------------------
    # Font helpers
    # -----------------------------------------------------------------

    def _detect_font(self, canvas: tk.Canvas):
        """Pick the best available math font."""
        for family in ("Cambria Math", "STIX Two Math", "STIX",
                       "Times New Roman", "DejaVu Serif", "Liberation Serif",
                       "serif"):
            try:
                f = tkfont.Font(root=canvas, family=family, size=12)
                if f.actual("family"):
                    self._font_family = family
                    return
            except Exception:
                continue
        self._font_family = "serif"

    def _get_font(self, canvas: tk.Canvas, size: int, style: str = "") -> tkfont.Font:
        key = (self._font_family, size, style)
        if key not in self._font_cache:
            weight = "bold" if "bold" in style else "normal"
            slant = "italic" if "italic" in style else "roman"
            self._font_cache[key] = tkfont.Font(
                root=canvas, family=self._font_family,
                size=max(size, 6), weight=weight, slant=slant,
            )
        return self._font_cache[key]

    def _text_size(self, canvas: tk.Canvas, text: str, size: int, style: str = ""):
        f = self._get_font(canvas, size, style)
        w = f.measure(text)
        h = f.metrics("linespace")
        return w, h

    # -----------------------------------------------------------------
    # Measure (no drawing)
    # -----------------------------------------------------------------

    def _measure_node(self, node: ASTNode, fs: int, ctx: Any = None) -> RenderBox:
        c = self._canvas
        if isinstance(node, Number):
            return self._measure_number(c, node, fs)
        if isinstance(node, Variable):
            return self._measure_variable(c, node, fs)
        if isinstance(node, UnitRef):
            return self._measure_unit(c, node, fs)
        if isinstance(node, StringLiteral):
            return self._measure_string(c, node, fs)
        if isinstance(node, UnaryOp):
            return self._measure_unary(c, node, fs, ctx)
        if isinstance(node, BinaryOp):
            return self._measure_binary(c, node, fs, ctx)
        if isinstance(node, FunctionCall):
            return self._measure_function(c, node, fs, ctx)
        if isinstance(node, Evaluation):
            return self._measure_node(node.expression, fs, ctx)
        w, h = self._text_size(c, str(node), fs)
        return RenderBox(w, h, h / 2)

    def _measure_number(self, c, node: Number, fs: int) -> RenderBox:
        txt = _format_number(node.value)
        w, h = self._text_size(c, txt, fs)
        return RenderBox(w, h, h / 2)

    def _measure_variable(self, c, node: Variable, fs: int) -> RenderBox:
        style = "bold" if node.name in _BUILTIN_VARS else "italic"
        if "." in node.name:
            parts = node.name.split(".", 1)
            base = _GREEK_DISPLAY.get(parts[0], parts[0])
            sub = _GREEK_DISPLAY.get(parts[1], parts[1])
            bw, bh = self._text_size(c, base, fs, style)
            sub_fs = max(int(fs * _SUB_SCALE), 6)
            sw, sh = self._text_size(c, sub, sub_fs, style)
            w = bw + sw
            sub_y_off = bh * 0.55
            h = max(bh, sub_y_off + sh)
            return RenderBox(w, h, bh / 2)
        display = _GREEK_DISPLAY.get(node.name, node.name)
        w, h = self._text_size(c, display, fs, style)
        return RenderBox(w, h, h / 2)

    def _measure_unit(self, c, node: UnitRef, fs: int) -> RenderBox:
        w, h = self._text_size(c, node.name, fs)
        return RenderBox(w, h, h / 2)

    def _measure_string(self, c, node: StringLiteral, fs: int) -> RenderBox:
        txt = f'"{node.value}"'
        w, h = self._text_size(c, txt, fs)
        return RenderBox(w, h, h / 2)

    def _measure_unary(self, c, node: UnaryOp, fs: int, ctx) -> RenderBox:
        inner = self._measure_node(node.operand, fs, ctx)
        if node.operator == "-":
            mw, _ = self._text_size(c, "−", fs)
            return RenderBox(mw + inner.width, inner.height, inner.baseline)
        if node.operator == "!":
            ew, _ = self._text_size(c, "!", fs)
            return RenderBox(inner.width + ew, inner.height, inner.baseline)
        if node.operator == "%":
            ew, _ = self._text_size(c, "%", fs)
            return RenderBox(inner.width + ew, inner.height, inner.baseline)
        return inner

    def _measure_binary(self, c, node: BinaryOp, fs: int, ctx) -> RenderBox:
        if node.operator == "/":
            return self._measure_fraction(c, node, fs, ctx)
        if node.operator == "^":
            return self._measure_superscript(c, node, fs, ctx)
        if node.operator == ":":
            return self._measure_assignment(c, node, fs, ctx)
        if node.operator == "=" or node.operator == "≡":
            return self._measure_equals(c, node, fs, ctx)

        left = self._measure_node(node.left, fs, ctx)
        right = self._measure_node(node.right, fs, ctx)
        op_text = _DISPLAY_OPS.get(node.operator, node.operator)
        if node.operator == "*" and _is_implicit_mult(node):
            ow, oh = self._text_size(c, " ", fs)
        else:
            ow, oh = self._text_size(c, f" {op_text} ", fs)
        lp = _needs_parens(node.left, node.operator, False)
        rp = _needs_parens(node.right, node.operator, True)
        pw, _ = self._text_size(c, "(", fs)
        paren_extra = (pw * 2 if lp else 0) + (pw * 2 if rp else 0)
        w = left.width + ow + right.width + paren_extra
        bl = max(left.baseline, right.baseline, oh / 2)
        desc = max(left.height - left.baseline, right.height - right.baseline, oh / 2)
        h = bl + desc
        return RenderBox(w, h, bl)

    def _measure_fraction(self, c, node: BinaryOp, fs: int, ctx) -> RenderBox:
        num = self._measure_node(node.left, fs, ctx)
        den = self._measure_node(node.right, fs, ctx)
        w = max(num.width, den.width) + 2 * _FRAC_HPAD
        h = num.height + den.height + 2 * _FRAC_VPAD + 2
        return RenderBox(w, h, num.height + _FRAC_VPAD + 1)

    def _measure_superscript(self, c, node: BinaryOp, fs: int, ctx) -> RenderBox:
        base = self._measure_node(node.left, fs, ctx)
        sup_fs = max(int(fs * _SUP_SCALE), 6)
        exp = self._measure_node(node.right, sup_fs, ctx)
        w = base.width + exp.width
        raise_amt = base.height * _SUP_RAISE
        h = raise_amt + base.height
        h = max(h, exp.height)
        return RenderBox(w, h, raise_amt + base.baseline)

    def _measure_assignment(self, c, node: BinaryOp, fs: int, ctx) -> RenderBox:
        left = self._measure_node(node.left, fs, ctx)
        right = self._measure_node(node.right, fs, ctx)
        ow, oh = self._text_size(c, " := ", fs)
        w = left.width + ow + right.width
        h = max(left.height, right.height, oh)
        return RenderBox(w, h, max(left.baseline, right.baseline))

    def _measure_equals(self, c, node: BinaryOp, fs: int, ctx) -> RenderBox:
        left = self._measure_node(node.left, fs, ctx)
        right = self._measure_node(node.right, fs, ctx)
        sym = " ≡ " if node.operator == "≡" else " = "
        ow, oh = self._text_size(c, sym, fs)
        w = left.width + ow + right.width
        h = max(left.height, right.height, oh)
        return RenderBox(w, h, max(left.baseline, right.baseline))

    def _measure_function(self, c, node: FunctionCall, fs: int, ctx) -> RenderBox:
        name = node.name
        if name == "sqrt" and len(node.args) == 1:
            return self._measure_sqrt(c, node, fs, ctx)
        if name == "nthroot" and len(node.args) == 2:
            return self._measure_nthroot(c, node, fs, ctx)
        if name == "abs" and len(node.args) == 1:
            return self._measure_abs(c, node, fs, ctx)
        if name == "mat":
            return self._measure_matrix(c, node, fs, ctx)
        if name in ("sum", "product") and len(node.args) == 4:
            return self._measure_bigop(c, node, fs, ctx)
        if name in ("nintegrate", "int") and len(node.args) >= 3:
            return self._measure_integral(c, node, fs, ctx)
        if name == "int" and len(node.args) == 2:
            return self._measure_indef_integral(c, node, fs, ctx)
        if name == "lim" and len(node.args) == 3:
            return self._measure_lim(c, node, fs, ctx)
        if name in ("diff", "nderiv") and len(node.args) == 2:
            return self._measure_derivative(c, node, fs, ctx)
        if name == "if" and len(node.args) >= 2:
            return self._measure_if(c, node, fs, ctx)
        if name == "for" and len(node.args) >= 4:
            return self._measure_for(c, node, fs, ctx)
        if name == "while" and len(node.args) >= 2:
            return self._measure_while(c, node, fs, ctx)
        if name == "range" and 2 <= len(node.args) <= 3:
            return self._measure_range(c, node, fs, ctx)
        if name == "sys" and len(node.args) >= 3:
            return self._measure_sys(c, node, fs, ctx)
        if name == "log" and len(node.args) == 2:
            return self._measure_log_base(c, node, fs, ctx)

        style = "" if name in _BUILTIN_FUNCTIONS else "italic"
        nw, nh = self._text_size(c, name, fs, style)
        pw, ph = self._text_size(c, "(", fs)

        args_w = 0.0
        arg_measures = [self._measure_node(a, fs, ctx) for a in node.args]
        max_bl = max((m.baseline for m in arg_measures), default=nh / 2)
        max_bl = max(max_bl, nh / 2)
        max_desc = max((m.height - m.baseline for m in arg_measures), default=nh / 2)
        max_desc = max(max_desc, nh / 2)
        for i, a in enumerate(arg_measures):
            args_w += a.width
            if i < len(node.args) - 1:
                cw, _ = self._text_size(c, ", ", fs)
                args_w += cw

        total_h = max_bl + max_desc
        w = nw + pw + args_w + pw
        return RenderBox(w, total_h, max_bl)

    def _measure_sqrt(self, c, node: FunctionCall, fs: int, ctx) -> RenderBox:
        inner = self._measure_node(node.args[0], fs, ctx)
        pad = 3
        rad_w = max(int(fs * 0.7), 10)
        w = rad_w + inner.width + 4
        h = inner.height + pad + 1
        return RenderBox(w, h, pad + 1 + inner.baseline)

    def _measure_nthroot(self, c, node: FunctionCall, fs: int, ctx) -> RenderBox:
        inner = self._measure_node(node.args[0], fs, ctx)
        idx_fs = max(int(fs * 0.6), 6)
        idx = self._measure_node(node.args[1], idx_fs, ctx)
        pad = 3
        rad_w = max(int(fs * 0.7), 10)
        idx_offset = max(idx.width - rad_w * 0.4, 0)
        w = idx_offset + rad_w + inner.width + 4
        h = inner.height + pad + 1
        return RenderBox(w, h, pad + 1 + inner.baseline)

    def _measure_abs(self, c, node: FunctionCall, fs: int, ctx) -> RenderBox:
        inner = self._measure_node(node.args[0], fs, ctx)
        bar_w = 2
        pad = 3
        return RenderBox(inner.width + bar_w * 2 + pad * 2, inner.height, inner.baseline)

    def _measure_matrix(self, c, node: FunctionCall, fs: int, ctx) -> RenderBox:
        rows, cols = _matrix_dims(node)
        cells = _matrix_cells(node, rows, cols)
        cell_w = 0
        cell_h = 0
        for r in range(rows):
            for col_idx in range(cols):
                cm = self._measure_node(cells[r][col_idx], fs, ctx)
                cell_w = max(cell_w, cm.width)
                cell_h = max(cell_h, cm.height)
        w = cols * (cell_w + _MATRIX_CELL_PAD) - _MATRIX_CELL_PAD + 2 * _MATRIX_BRACKET_W + 8
        h = rows * (cell_h + _MATRIX_CELL_PAD) - _MATRIX_CELL_PAD + 8
        return RenderBox(w, h, h / 2)

    def _measure_bigop(self, c, node: FunctionCall, fs: int, ctx) -> RenderBox:
        sym = "Σ" if node.name == "sum" else "Π"
        sw, sh = self._text_size(c, sym, int(fs * 1.5))
        body = self._measure_node(node.args[3], fs, ctx)
        sub_fs = max(int(fs * _SUB_SCALE), 6)
        lo = self._measure_node(node.args[1], sub_fs, ctx)
        hi = self._measure_node(node.args[2], sub_fs, ctx)
        sym_w = max(sw, lo.width, hi.width) + 4
        w = sym_w + body.width + 4
        h = max(sh + lo.height + hi.height, body.height)
        return RenderBox(w, h, h / 2)

    def _integral_args(self, node: FunctionCall):
        if node.name == "int" and len(node.args) >= 4:
            return node.args[0], node.args[2], node.args[3], node.args[1]
        return node.args[0], node.args[1], node.args[2], (node.args[3] if len(node.args) >= 4 else None)

    def _measure_integral(self, c, node: FunctionCall, fs: int, ctx) -> RenderBox:
        body_node, lo_node, hi_node, var_node = self._integral_args(node)
        int_w = max(int(fs * 0.8), 12)
        int_h = max(int(fs * 1.8), 20)
        body = self._measure_node(body_node, fs, ctx)
        sub_fs = max(int(fs * _SUB_SCALE), 6)
        lo = self._measure_node(lo_node, sub_fs, ctx)
        hi = self._measure_node(hi_node, sub_fs, ctx)
        sym_w = max(int_w, lo.width, hi.width) + 4
        dx_w = 0
        if var_node is not None:
            dw, _ = self._text_size(c, "d", fs)
            var_m = self._measure_node(var_node, fs, ctx)
            dx_w = 4 + dw + var_m.width
        w = sym_w + body.width + dx_w + 8
        h = max(int_h + lo.height + hi.height + 4, body.height)
        return RenderBox(w, h, h / 2)

    def _measure_range(self, c, node: FunctionCall, fs: int, ctx) -> RenderBox:
        start_m = self._measure_node(node.args[0], fs, ctx)
        end_m = self._measure_node(node.args[1], fs, ctx)
        dot_w, _ = self._text_size(c, " .. ", fs)
        w = start_m.width + dot_w + end_m.width
        if len(node.args) == 3:
            step_m = self._measure_node(node.args[2], fs, ctx)
            comma_w, _ = self._text_size(c, ", ", fs)
            w += comma_w + step_m.width
        h = max(start_m.height, end_m.height)
        return RenderBox(w, h, h / 2)

    def _measure_for(self, c, node: FunctionCall, fs: int, ctx) -> RenderBox:
        kw_w, kw_h = self._text_size(c, "for ", fs, "bold")
        var_m = self._measure_node(node.args[1], fs, ctx)
        start_m = self._measure_node(node.args[2], fs, ctx)
        end_m = self._measure_node(node.args[3], fs, ctx)
        body_m = self._measure_node(node.args[0], fs, ctx)
        header_w = kw_w + var_m.width + 20 + start_m.width + 20 + end_m.width
        header_h = max(kw_h, var_m.height, start_m.height, end_m.height)
        total_w = max(header_w, 16 + body_m.width)
        total_h = header_h + 4 + body_m.height
        return RenderBox(total_w, total_h, header_h / 2)

    def _measure_while(self, c, node: FunctionCall, fs: int, ctx) -> RenderBox:
        kw_w, kw_h = self._text_size(c, "while ", fs, "bold")
        cond_m = self._measure_node(node.args[1], fs, ctx)
        body_m = self._measure_node(node.args[0], fs, ctx)
        header_w = kw_w + cond_m.width
        header_h = max(kw_h, cond_m.height)
        total_w = max(header_w, 16 + body_m.width)
        total_h = header_h + 4 + body_m.height
        return RenderBox(total_w, total_h, header_h / 2)

    def _measure_if(self, c, node: FunctionCall, fs: int, ctx) -> RenderBox:
        total_h = 0.0
        max_w = 0.0
        for i in range(0, len(node.args), 2):
            vm = self._measure_node(node.args[i], fs, ctx)
            cm = self._measure_node(node.args[i + 1], fs, ctx) if i + 1 < len(node.args) else None
            row_h = max(vm.height, cm.height if cm else 0) + 4
            total_h += row_h
            row_w = vm.width + 20 + (cm.width if cm else 0) + 30
            max_w = max(max_w, row_w)
        return RenderBox(max_w + 16, total_h, total_h / 2)

    def _measure_derivative(self, c, node: FunctionCall, fs: int, ctx) -> RenderBox:
        body = self._measure_node(node.args[0], fs, ctx)
        var = self._measure_node(node.args[1], fs, ctx)
        dw, dh = self._text_size(c, "d", fs, "italic")
        frac_w = max(dw + body.width, dw + var.width) + 8
        h = body.height + var.height + dh * 2 + 8
        return RenderBox(frac_w, h, body.height + dh + 4)

    # -----------------------------------------------------------------
    # Stretchy delimiters
    # -----------------------------------------------------------------

    def _draw_stretchy_paren(self, c: tk.Canvas, ch: str, x: float, y: float,
                             content_h: float, fs: int):
        _, char_h = self._text_size(c, ch, fs)
        if content_h <= char_h * 1.3:
            f = self._get_font(c, fs)
            py = y + (content_h - char_h) / 2
            c.create_text(x, py, text=ch, anchor="nw", font=f, fill=_OPERATOR_COLOR)
            return
        pad = 1
        lw = 1.2 if content_h > char_h * 2 else 1
        if ch == "(":
            cx = x + 4
            c.create_line(cx + 4, y + pad,
                         cx + 2, y + content_h * 0.08,
                         cx, y + content_h * 0.2,
                         cx - 1, y + content_h * 0.35,
                         cx - 1, y + content_h * 0.5,
                         cx - 1, y + content_h * 0.65,
                         cx, y + content_h * 0.8,
                         cx + 2, y + content_h * 0.92,
                         cx + 4, y + content_h - pad,
                         smooth=True, fill=_OPERATOR_COLOR, width=lw)
        elif ch == ")":
            cx = x + 2
            c.create_line(cx, y + pad,
                         cx + 2, y + content_h * 0.08,
                         cx + 4, y + content_h * 0.2,
                         cx + 5, y + content_h * 0.35,
                         cx + 5, y + content_h * 0.5,
                         cx + 5, y + content_h * 0.65,
                         cx + 4, y + content_h * 0.8,
                         cx + 2, y + content_h * 0.92,
                         cx, y + content_h - pad,
                         smooth=True, fill=_OPERATOR_COLOR, width=lw)

    def _draw_curly_brace(self, c: tk.Canvas, x: float, y: float,
                          h: float, fs: int):
        _, char_h = self._text_size(c, "{", fs)
        if h <= char_h * 1.3:
            f = self._get_font(c, fs)
            py = y + (h - char_h) / 2
            c.create_text(x, py, text="{", anchor="nw", font=f, fill=_OPERATOR_COLOR)
            return
        pad = 1
        cx = x + 6
        mid = y + h * 0.5
        tip_x = cx - 5
        lw = 1.2 if h > char_h * 2 else 1
        c.create_line(cx + 4, y + pad,
                     cx + 2, y + h * 0.04,
                     cx, y + h * 0.1,
                     cx - 1, y + h * 0.2,
                     cx - 1, mid - h * 0.08,
                     tip_x, mid,
                     cx - 1, mid + h * 0.08,
                     cx - 1, y + h * 0.8,
                     cx, y + h * 0.9,
                     cx + 2, y + h * 0.96,
                     cx + 4, y + h - pad,
                     smooth=True, fill=_OPERATOR_COLOR, width=lw)

    # -----------------------------------------------------------------
    # Render (draw on canvas)
    # -----------------------------------------------------------------

    def _render_node(self, c: tk.Canvas, node: ASTNode, x: float, y: float,
                     fs: int, ctx: Any) -> RenderBox:
        if isinstance(node, Number):
            return self._render_number(c, node, x, y, fs)
        if isinstance(node, Variable):
            return self._render_variable(c, node, x, y, fs)
        if isinstance(node, UnitRef):
            return self._render_unit(c, node, x, y, fs)
        if isinstance(node, StringLiteral):
            return self._render_string(c, node, x, y, fs)
        if isinstance(node, UnaryOp):
            return self._render_unary(c, node, x, y, fs, ctx)
        if isinstance(node, BinaryOp):
            return self._render_binary(c, node, x, y, fs, ctx)
        if isinstance(node, FunctionCall):
            return self._render_function(c, node, x, y, fs, ctx)
        if isinstance(node, Evaluation):
            return self._render_node(c, node.expression, x, y, fs, ctx)
        # Fallback
        txt = str(node)
        f = self._get_font(c, fs)
        c.create_text(x, y, text=txt, anchor="nw", font=f, fill=_NUMBER_COLOR)
        w, h = self._text_size(c, txt, fs)
        return RenderBox(w, h, h / 2)

    # -- Atoms --

    def _render_number(self, c, node: Number, x, y, fs) -> RenderBox:
        txt = _format_number(node.value)
        f = self._get_font(c, fs)
        c.create_text(x, y, text=txt, anchor="nw", font=f, fill=_NUMBER_COLOR)
        w, h = self._text_size(c, txt, fs)
        return RenderBox(w, h, h / 2)

    def _render_variable(self, c, node: Variable, x, y, fs) -> RenderBox:
        is_builtin = node.name in _BUILTIN_VARS
        is_greek = node.name in _GREEK_DISPLAY or (
            "." in node.name and node.name.split(".", 1)[0] in _GREEK_DISPLAY)
        style = "bold" if is_builtin else "italic"
        color = _BUILTIN_VAR_COLOR if is_builtin else _USER_VAR_COLOR

        if "." in node.name:
            parts = node.name.split(".", 1)
            base = _GREEK_DISPLAY.get(parts[0], parts[0])
            sub = _GREEK_DISPLAY.get(parts[1], parts[1])
            f_base = self._get_font(c, fs, style)
            c.create_text(x, y, text=base, anchor="nw", font=f_base, fill=color)
            bw, bh = self._text_size(c, base, fs, style)

            sub_fs = max(int(fs * _SUB_SCALE), 6)
            f_sub = self._get_font(c, sub_fs, style)
            sub_y = y + bh * 0.55
            c.create_text(x + bw, sub_y, text=sub, anchor="nw", font=f_sub, fill=color)
            sw, sh = self._text_size(c, sub, sub_fs, style)

            w = bw + sw
            h = max(bh, sub_y - y + sh)
            return RenderBox(w, h, bh / 2)
        else:
            display = _GREEK_DISPLAY.get(node.name, node.name)
            f = self._get_font(c, fs, style)
            c.create_text(x, y, text=display, anchor="nw", font=f, fill=color)
            w, h = self._text_size(c, display, fs, style)
            return RenderBox(w, h, h / 2)

    def _render_unit(self, c, node: UnitRef, x, y, fs) -> RenderBox:
        f = self._get_font(c, fs)
        c.create_text(x, y, text=node.name, anchor="nw", font=f, fill=_UNIT_COLOR)
        w, h = self._text_size(c, node.name, fs)
        return RenderBox(w, h, h / 2)

    def _render_string(self, c, node: StringLiteral, x, y, fs) -> RenderBox:
        txt = f'"{node.value}"'
        f = self._get_font(c, fs)
        c.create_text(x, y, text=txt, anchor="nw", font=f, fill=_STRING_COLOR)
        w, h = self._text_size(c, txt, fs)
        return RenderBox(w, h, h / 2)

    # -- Unary --

    def _render_unary(self, c, node: UnaryOp, x, y, fs, ctx) -> RenderBox:
        if node.operator == "-":
            f = self._get_font(c, fs)
            minus = "−"
            c.create_text(x, y, text=minus, anchor="nw", font=f, fill=_OPERATOR_COLOR)
            mw, mh = self._text_size(c, minus, fs)
            inner = self._render_node(c, node.operand, x + mw, y, fs, ctx)
            w = mw + inner.width
            h = max(mh, inner.height)
            return RenderBox(w, h, max(mh / 2, inner.baseline))
        if node.operator in ("!", "%"):
            f = self._get_font(c, fs)
            inner = self._render_node(c, node.operand, x, y, fs, ctx)
            sym = node.operator
            c.create_text(x + inner.width, y, text=sym, anchor="nw", font=f, fill=_OPERATOR_COLOR)
            sw, sh = self._text_size(c, sym, fs)
            return RenderBox(inner.width + sw, max(inner.height, sh), inner.baseline)
        return self._render_node(c, node.operand, x, y, fs, ctx)

    # -- Binary --

    def _render_binary(self, c, node: BinaryOp, x, y, fs, ctx) -> RenderBox:
        if node.operator == "/":
            return self._render_fraction(c, node, x, y, fs, ctx)
        if node.operator == "^":
            return self._render_superscript(c, node, x, y, fs, ctx)
        if node.operator == ":":
            return self._render_assignment(c, node, x, y, fs, ctx)
        if node.operator == "=" or node.operator == "≡":
            return self._render_equals(c, node, x, y, fs, ctx)

        total = self._measure_binary(c, node, fs, ctx)
        left_m = self._measure_node(node.left, fs, ctx)
        right_m = self._measure_node(node.right, fs, ctx)

        lp = _needs_parens(node.left, node.operator, False)
        rp = _needs_parens(node.right, node.operator, True)
        pw, _ = self._text_size(c, "(", fs)

        bl = total.baseline
        cx_pos = x
        if lp:
            self._draw_stretchy_paren(c, "(", cx_pos, y, total.height, fs)
            cx_pos += pw
        left_y = y + bl - left_m.baseline
        lb = self._render_node(c, node.left, cx_pos, left_y, fs, ctx)
        cx_pos += lb.width
        if lp:
            self._draw_stretchy_paren(c, ")", cx_pos, y, total.height, fs)
            cx_pos += pw

        op_text = _DISPLAY_OPS.get(node.operator, node.operator)
        display = f" {op_text} "

        if node.operator == "*" and _is_implicit_mult(node):
            display = " "

        f = self._get_font(c, fs)
        ow, oh = self._text_size(c, display, fs)
        op_y = y + bl - oh / 2
        c.create_text(cx_pos, op_y, text=display, anchor="nw", font=f, fill=_OPERATOR_COLOR)
        cx_pos += ow

        if rp:
            self._draw_stretchy_paren(c, "(", cx_pos, y, total.height, fs)
            cx_pos += pw
        right_y = y + bl - right_m.baseline
        rb = self._render_node(c, node.right, cx_pos, right_y, fs, ctx)
        cx_pos += rb.width
        if rp:
            self._draw_stretchy_paren(c, ")", cx_pos, y, total.height, fs)
            cx_pos += pw

        w = cx_pos - x
        h = total.height
        return RenderBox(w, h, bl)

    def _render_fraction(self, c, node: BinaryOp, x, y, fs, ctx) -> RenderBox:
        num_m = self._measure_node(node.left, fs, ctx)
        den_m = self._measure_node(node.right, fs, ctx)

        bar_w = max(num_m.width, den_m.width) + 2 * _FRAC_HPAD
        bar_y = y + num_m.height + _FRAC_VPAD

        num_x = x + (bar_w - num_m.width) / 2
        self._render_node(c, node.left, num_x, y, fs, ctx)

        line_w = 1.2 if fs >= 10 else 1
        c.create_line(x, bar_y, x + bar_w, bar_y, fill=_OPERATOR_COLOR, width=line_w)

        den_y = bar_y + _FRAC_VPAD + 2
        den_x = x + (bar_w - den_m.width) / 2
        self._render_node(c, node.right, den_x, den_y, fs, ctx)

        h = num_m.height + den_m.height + 2 * _FRAC_VPAD + 2
        return RenderBox(bar_w, h, bar_y - y)

    def _render_superscript(self, c, node: BinaryOp, x, y, fs, ctx) -> RenderBox:
        base_m = self._measure_node(node.left, fs, ctx)
        sup_fs = max(int(fs * _SUP_SCALE), 6)
        exp_m = self._measure_node(node.right, sup_fs, ctx)

        raise_amt = base_m.height * _SUP_RAISE
        exp_y = y
        base_y = y + raise_amt
        total_h = max(base_y + base_m.height, exp_y + exp_m.height) - y

        bb = self._render_node(c, node.left, x, base_y, fs, ctx)
        self._render_node(c, node.right, x + bb.width, exp_y, sup_fs, ctx)

        w = bb.width + exp_m.width
        return RenderBox(w, total_h, base_y - y + base_m.baseline)

    def _render_assignment(self, c, node: BinaryOp, x, y, fs, ctx) -> RenderBox:
        total = self._measure_assignment(c, node, fs, ctx)
        bl = total.baseline

        left_m = self._measure_node(node.left, fs, ctx)
        left_y = y + bl - left_m.baseline
        lb = self._render_node(c, node.left, x, left_y, fs, ctx)

        f = self._get_font(c, fs)
        ow, oh = self._text_size(c, " := ", fs)
        ox = x + lb.width
        op_y = y + bl - oh / 2
        sp_w, _ = self._text_size(c, " ", fs)
        colon_w, _ = self._text_size(c, ":", fs)
        eq_w, _ = self._text_size(c, "=", fs)
        c.create_text(ox + sp_w, op_y, text=":", anchor="nw", font=f, fill=_OPERATOR_COLOR)
        c.create_text(ox + sp_w + colon_w, op_y, text="=", anchor="nw", font=f, fill=_OPERATOR_COLOR)

        right_m = self._measure_node(node.right, fs, ctx)
        right_y = y + bl - right_m.baseline
        self._render_node(c, node.right, ox + ow, right_y, fs, ctx)

        return total

    def _render_equals(self, c, node: BinaryOp, x, y, fs, ctx) -> RenderBox:
        total = self._measure_equals(c, node, fs, ctx)
        bl = total.baseline

        left_m = self._measure_node(node.left, fs, ctx)
        left_y = y + bl - left_m.baseline
        lb = self._render_node(c, node.left, x, left_y, fs, ctx)

        sym = " ≡ " if node.operator == "≡" else " = "
        f = self._get_font(c, fs)
        ow, oh = self._text_size(c, sym, fs)
        ox = x + lb.width
        op_y = y + bl - oh / 2
        c.create_text(ox, op_y, text=sym, anchor="nw", font=f, fill=_OPERATOR_COLOR)

        right_m = self._measure_node(node.right, fs, ctx)
        right_y = y + bl - right_m.baseline
        self._render_node(c, node.right, ox + ow, right_y, fs, ctx)

        return total

    # -- Functions --

    def _render_function(self, c, node: FunctionCall, x, y, fs, ctx) -> RenderBox:
        name = node.name

        if name == "sqrt" and len(node.args) == 1:
            return self._render_sqrt(c, node, x, y, fs, ctx)
        if name == "nthroot" and len(node.args) == 2:
            return self._render_nthroot(c, node, x, y, fs, ctx)
        if name == "abs" and len(node.args) == 1:
            return self._render_abs(c, node, x, y, fs, ctx)
        if name == "mat":
            return self._render_matrix(c, node, x, y, fs, ctx)
        if name in ("sum", "product") and len(node.args) == 4:
            return self._render_bigop(c, node, x, y, fs, ctx)
        if name in ("nintegrate", "int") and len(node.args) >= 3:
            return self._render_integral(c, node, x, y, fs, ctx)
        if name == "int" and len(node.args) == 2:
            return self._render_indef_integral(c, node, x, y, fs, ctx)
        if name == "lim" and len(node.args) == 3:
            return self._render_lim(c, node, x, y, fs, ctx)
        if name in ("diff", "nderiv") and len(node.args) == 2:
            return self._render_derivative(c, node, x, y, fs, ctx)
        if name == "if" and len(node.args) >= 2:
            return self._render_if(c, node, x, y, fs, ctx)
        if name == "for" and len(node.args) >= 4:
            return self._render_for(c, node, x, y, fs, ctx)
        if name == "while" and len(node.args) >= 2:
            return self._render_while(c, node, x, y, fs, ctx)
        if name == "range" and 2 <= len(node.args) <= 3:
            return self._render_range(c, node, x, y, fs, ctx)
        if name == "line":
            return self._render_line_block(c, node, x, y, fs, ctx)
        if name == "sys" and len(node.args) >= 3:
            return self._render_sys(c, node, x, y, fs, ctx)
        if name == "log" and len(node.args) == 2:
            return self._render_log_base(c, node, x, y, fs, ctx)

        # General function: name(arg1, arg2, ...)
        is_builtin = name in _BUILTIN_FUNCTIONS
        style = "" if is_builtin else "italic"
        f_name = self._get_font(c, fs, style)
        f_paren = self._get_font(c, fs)

        nw, nh = self._text_size(c, name, fs, style)
        pw, ph = self._text_size(c, "(", fs)
        cw_comma, _ = self._text_size(c, ", ", fs)

        arg_measures = [self._measure_node(a, fs, ctx) for a in node.args]
        max_bl = max((m.baseline for m in arg_measures), default=nh / 2)
        max_bl = max(max_bl, nh / 2)
        max_desc = max((m.height - m.baseline for m in arg_measures), default=nh / 2)
        max_desc = max(max_desc, nh / 2)
        total_h = max_bl + max_desc

        name_y = y + max_bl - nh / 2
        c.create_text(x, name_y, text=name, anchor="nw", font=f_name, fill=_FUNCTION_COLOR)

        cx = x + nw
        self._draw_stretchy_paren(c, "(", cx, y, total_h, fs)
        cx += pw

        for i, (arg, am) in enumerate(zip(node.args, arg_measures)):
            arg_y = y + max_bl - am.baseline
            self._render_node(c, arg, cx, arg_y, fs, ctx)
            cx += am.width
            if i < len(node.args) - 1:
                comma_y = y + max_bl - ph / 2
                c.create_text(cx, comma_y, text=", ", anchor="nw", font=f_paren, fill=_OPERATOR_COLOR)
                cx += cw_comma

        self._draw_stretchy_paren(c, ")", cx, y, total_h, fs)
        cx += pw

        return RenderBox(cx - x, total_h, max_bl)

    def _render_sqrt(self, c, node: FunctionCall, x, y, fs, ctx) -> RenderBox:
        inner_m = self._measure_node(node.args[0], fs, ctx)
        pad = 3
        content_h = inner_m.height + pad
        rad_w = max(int(fs * 0.7), 10)
        inner_x = x + rad_w
        inner_y = y + pad + 1

        ib = self._render_node(c, node.args[0], inner_x, inner_y, fs, ctx)

        total_h = ib.height + pad + 1
        self._draw_radical(c, x, y, rad_w, total_h, inner_m.width + 4)

        w = rad_w + ib.width + 4
        return RenderBox(w, total_h, inner_y - y + inner_m.baseline)

    def _draw_radical(self, c: tk.Canvas, x: float, y: float,
                      rad_w: float, h: float, bar_len: float):
        tail_x = x + 1
        tail_y = y + h * 0.55
        notch_x = x + rad_w * 0.3
        notch_y = y + h * 0.45
        bottom_x = x + rad_w * 0.5
        bottom_y = y + h - 1
        top_x = x + rad_w - 1
        top_y = y + 1
        c.create_line(tail_x, tail_y, notch_x, notch_y,
                     fill=_OPERATOR_COLOR, width=0.8)
        c.create_line(notch_x, notch_y, bottom_x, bottom_y,
                     fill=_OPERATOR_COLOR, width=1.5)
        c.create_line(bottom_x, bottom_y, top_x, top_y,
                     fill=_OPERATOR_COLOR, width=1.5)
        c.create_line(top_x, top_y, top_x + bar_len + 1, top_y,
                     fill=_OPERATOR_COLOR, width=0.8)

    def _render_nthroot(self, c, node: FunctionCall, x, y, fs, ctx) -> RenderBox:
        inner_m = self._measure_node(node.args[0], fs, ctx)
        idx_fs = max(int(fs * 0.6), 6)
        pad = 3
        rad_w = max(int(fs * 0.7), 10)

        idx_m = self._measure_node(node.args[1], idx_fs, ctx)
        idx_offset = max(idx_m.width - rad_w * 0.4, 0)

        self._render_node(c, node.args[1], x + idx_offset - idx_m.width + rad_w * 0.3, y, idx_fs, ctx)

        rx = x + idx_offset
        inner_x = rx + rad_w
        inner_y = y + pad + 1
        ib = self._render_node(c, node.args[0], inner_x, inner_y, fs, ctx)

        total_h = ib.height + pad + 1
        self._draw_radical(c, rx, y, rad_w, total_h, inner_m.width + 4)

        w = idx_offset + rad_w + ib.width + 4
        return RenderBox(w, total_h, inner_y - y + inner_m.baseline)

    def _render_abs(self, c, node: FunctionCall, x, y, fs, ctx) -> RenderBox:
        inner_m = self._measure_node(node.args[0], fs, ctx)
        bar_w = 2
        pad = 3
        h = inner_m.height + 2
        ext = 1

        c.create_line(x + 1, y - ext, x + 1, y + h + ext, fill=_OPERATOR_COLOR, width=1.5)
        ix = x + bar_w + pad
        ib = self._render_node(c, node.args[0], ix, y + 1, fs, ctx)
        rx = ix + ib.width + pad
        c.create_line(rx + 1, y - ext, rx + 1, y + h + ext, fill=_OPERATOR_COLOR, width=1.5)

        w = bar_w + pad + ib.width + pad + bar_w
        return RenderBox(w, h, inner_m.baseline + 1)

    def _render_matrix(self, c, node: FunctionCall, x, y, fs, ctx) -> RenderBox:
        rows, cols = _matrix_dims(node)
        cells = _matrix_cells(node, rows, cols)

        # Measure all cells to find max widths/heights per column/row
        col_widths = [0.0] * cols
        row_heights = [0.0] * rows
        cell_measures = [[None] * cols for _ in range(rows)]

        for r in range(rows):
            for col_idx in range(cols):
                cm = self._measure_node(cells[r][col_idx], fs, ctx)
                cell_measures[r][col_idx] = cm
                col_widths[col_idx] = max(col_widths[col_idx], cm.width)
                row_heights[r] = max(row_heights[r], cm.height)

        # Total dimensions
        inner_w = sum(col_widths) + (cols - 1) * _MATRIX_CELL_PAD
        inner_h = sum(row_heights) + (rows - 1) * _MATRIX_CELL_PAD

        total_w = inner_w + 2 * _MATRIX_BRACKET_W + 8
        total_h = inner_h + 8

        bx = x
        bw = _MATRIX_BRACKET_W
        lw = 1.2
        c.create_line(bx + bw, y + 1, bx + 1, y + 1, fill=_OPERATOR_COLOR, width=lw)
        c.create_line(bx + 1, y + 1, bx + 1, y + total_h - 1, fill=_OPERATOR_COLOR, width=lw)
        c.create_line(bx + 1, y + total_h - 1, bx + bw, y + total_h - 1, fill=_OPERATOR_COLOR, width=lw)

        rx = x + total_w - bw
        c.create_line(rx, y + 1, rx + bw - 1, y + 1, fill=_OPERATOR_COLOR, width=lw)
        c.create_line(rx + bw - 1, y + 1, rx + bw - 1, y + total_h - 1, fill=_OPERATOR_COLOR, width=lw)
        c.create_line(rx + bw - 1, y + total_h - 1, rx, y + total_h - 1, fill=_OPERATOR_COLOR, width=lw)

        # Render cells
        cy = y + 4
        for r in range(rows):
            cx = x + _MATRIX_BRACKET_W + 4
            for col_idx in range(cols):
                cm = cell_measures[r][col_idx]
                # Center in cell
                cell_x = cx + (col_widths[col_idx] - cm.width) / 2
                cell_y = cy + (row_heights[r] - cm.height) / 2
                self._render_node(c, cells[r][col_idx], cell_x, cell_y, fs, ctx)
                cx += col_widths[col_idx] + _MATRIX_CELL_PAD
            cy += row_heights[r] + _MATRIX_CELL_PAD

        return RenderBox(total_w, total_h, total_h / 2)

    def _render_bigop(self, c, node: FunctionCall, x, y, fs, ctx) -> RenderBox:
        """Render sum/product with big sigma/pi and limits."""
        sym = "Σ" if node.name == "sum" else "Π"
        big_fs = int(fs * 1.5)
        f_sym = self._get_font(c, big_fs)
        sw, sh = self._text_size(c, sym, big_fs)

        sub_fs = max(int(fs * _SUB_SCALE), 6)
        # node.args: [var, lower, upper, body]
        var_node = node.args[0]
        lo_node = node.args[1]
        hi_node = node.args[2]
        body_node = node.args[3]

        lo_m = self._measure_node(lo_node, sub_fs, ctx)
        hi_m = self._measure_node(hi_node, sub_fs, ctx)
        body_m = self._measure_node(body_node, fs, ctx)

        sym_col_w = max(sw, lo_m.width, hi_m.width) + 4

        # Position: hi on top, symbol in middle, lo on bottom
        hi_y = y
        sym_y = hi_y + hi_m.height + 2
        lo_y = sym_y + sh + 2

        total_h = lo_y + lo_m.height - y
        body_y = y + (total_h - body_m.height) / 2

        # Draw upper limit (centered above symbol)
        hi_x = x + (sym_col_w - hi_m.width) / 2
        self._render_node(c, hi_node, hi_x, hi_y, sub_fs, ctx)

        # Draw symbol
        sym_x = x + (sym_col_w - sw) / 2
        c.create_text(sym_x, sym_y, text=sym, anchor="nw", font=f_sym, fill=_OPERATOR_COLOR)

        # Draw lower limit (var=lo, centered below symbol)
        lo_x = x + (sym_col_w - lo_m.width) / 2
        self._render_node(c, lo_node, lo_x, lo_y, sub_fs, ctx)

        # Draw body
        body_x = x + sym_col_w + 4
        self._render_node(c, body_node, body_x, body_y, fs, ctx)

        total_w = sym_col_w + 4 + body_m.width
        return RenderBox(total_w, total_h, total_h / 2)

    def _render_integral(self, c, node: FunctionCall, x, y, fs, ctx) -> RenderBox:
        """Render integral sign with limits."""
        body_node, lo_node, hi_node, var_node = self._integral_args(node)

        sub_fs = max(int(fs * _SUB_SCALE), 6)
        lo_m = self._measure_node(lo_node, sub_fs, ctx)
        hi_m = self._measure_node(hi_node, sub_fs, ctx)
        body_m = self._measure_node(body_node, fs, ctx)

        int_w = max(int(fs * 0.8), 12)
        int_h = max(int(fs * 1.8), body_m.height)
        sym_col_w = max(int_w, lo_m.width, hi_m.width) + 4

        hi_y = y
        sym_y = hi_y + hi_m.height + 2
        lo_y = sym_y + int_h + 2
        total_h = lo_y + lo_m.height - y
        body_y = y + (total_h - body_m.height) / 2

        hi_x = x + (sym_col_w - hi_m.width) / 2
        self._render_node(c, hi_node, hi_x, hi_y, sub_fs, ctx)

        sym_cx = x + sym_col_w / 2
        self._draw_integral_sign(c, sym_cx, sym_y, int_h, int_w)

        lo_x = x + (sym_col_w - lo_m.width) / 2
        self._render_node(c, lo_node, lo_x, lo_y, sub_fs, ctx)

        body_x = x + sym_col_w + 4
        self._render_node(c, body_node, body_x, body_y, fs, ctx)

        dx_w = 0
        if var_node is not None:
            f_d = self._get_font(c, fs, "italic")
            dx_x = body_x + body_m.width + 4
            c.create_text(dx_x, body_y, text="d", anchor="nw", font=f_d, fill=_OPERATOR_COLOR)
            dw, _ = self._text_size(c, "d", fs, "italic")
            self._render_node(c, var_node, dx_x + dw, body_y, fs, ctx)
            var_m = self._measure_node(var_node, fs, ctx)
            dx_w = 4 + dw + var_m.width

        total_w = sym_col_w + 4 + body_m.width + dx_w
        return RenderBox(total_w, total_h, total_h / 2)

    def _draw_integral_sign(self, c: tk.Canvas, cx: float, y: float,
                            h: float, w: float):
        r = w * 0.28
        lw = max(1.5, w * 0.08)
        c.create_line(
            cx + r * 1.2, y + h * 0.01,
            cx + r * 0.8, y + h * 0.02,
            cx + r * 0.3, y + h * 0.05,
            cx, y + h * 0.12,
            cx - r * 0.1, y + h * 0.25,
            cx - r * 0.1, y + h * 0.5,
            cx, y + h * 0.75,
            cx + r * 0.1, y + h * 0.88,
            cx - r * 0.3, y + h * 0.95,
            cx - r * 0.8, y + h * 0.98,
            cx - r * 1.2, y + h * 0.99,
            smooth=True, fill=_OPERATOR_COLOR, width=lw)

    def _measure_indef_integral(self, c, node: FunctionCall, fs: int, ctx) -> RenderBox:
        int_w = max(int(fs * 0.8), 12)
        int_h = max(int(fs * 1.8), 20)
        body = self._measure_node(node.args[0], fs, ctx)
        dw, _ = self._text_size(c, "d", fs)
        var_m = self._measure_node(node.args[1], fs, ctx)
        w = int_w + 4 + body.width + 4 + dw + var_m.width
        h = max(int_h, body.height)
        return RenderBox(w, h, h / 2)

    def _render_indef_integral(self, c, node: FunctionCall, x, y, fs, ctx) -> RenderBox:
        int_w = max(int(fs * 0.8), 12)
        int_h = max(int(fs * 1.8), 20)
        body_m = self._measure_node(node.args[0], fs, ctx)
        total_h = max(int_h, body_m.height)

        sym_cx = x + int_w / 2
        sym_y = y + (total_h - int_h) / 2
        self._draw_integral_sign(c, sym_cx, sym_y, int_h, int_w)

        body_x = x + int_w + 4
        body_y = y + (total_h - body_m.height) / 2
        self._render_node(c, node.args[0], body_x, body_y, fs, ctx)

        f_d = self._get_font(c, fs, "italic")
        dw, _ = self._text_size(c, "d", fs, "italic")
        dx_x = body_x + body_m.width + 4
        c.create_text(dx_x, body_y, text="d", anchor="nw", font=f_d, fill=_OPERATOR_COLOR)
        self._render_node(c, node.args[1], dx_x + dw, body_y, fs, ctx)
        var_m = self._measure_node(node.args[1], fs, ctx)

        total_w = int_w + 4 + body_m.width + 4 + dw + var_m.width
        return RenderBox(total_w, total_h, total_h / 2)

    def _measure_lim(self, c, node: FunctionCall, fs: int, ctx) -> RenderBox:
        sub_fs = max(int(fs * _SUB_SCALE), 6)
        kw, kh = self._text_size(c, "lim", fs)
        var_m = self._measure_node(node.args[1], sub_fs, ctx)
        arrow_w, _ = self._text_size(c, "→", sub_fs)
        val_m = self._measure_node(node.args[2], sub_fs, ctx)
        sub_w = var_m.width + arrow_w + val_m.width
        lim_col_w = max(kw, sub_w)
        body_m = self._measure_node(node.args[0], fs, ctx)
        w = lim_col_w + 6 + body_m.width
        h = kh + max(var_m.height, val_m.height) + 2
        h = max(h, body_m.height)
        return RenderBox(w, h, kh * 0.5)

    def _render_lim(self, c, node: FunctionCall, x, y, fs, ctx) -> RenderBox:
        sub_fs = max(int(fs * _SUB_SCALE), 6)
        f_kw = self._get_font(c, fs)
        kw, kh = self._text_size(c, "lim", fs)
        var_m = self._measure_node(node.args[1], sub_fs, ctx)
        arrow_w, arrow_h = self._text_size(c, "→", sub_fs)
        val_m = self._measure_node(node.args[2], sub_fs, ctx)
        sub_w = var_m.width + arrow_w + val_m.width
        lim_col_w = max(kw, sub_w)

        c.create_text(x + (lim_col_w - kw) / 2, y, text="lim",
                       anchor="nw", font=f_kw, fill=_FUNCTION_COLOR)

        sub_y = y + kh + 2
        sub_x = x + (lim_col_w - sub_w) / 2
        self._render_node(c, node.args[1], sub_x, sub_y, sub_fs, ctx)
        f_arrow = self._get_font(c, sub_fs)
        c.create_text(sub_x + var_m.width, sub_y, text="→",
                       anchor="nw", font=f_arrow, fill=_OPERATOR_COLOR)
        self._render_node(c, node.args[2], sub_x + var_m.width + arrow_w, sub_y, sub_fs, ctx)

        total_h = kh + max(var_m.height, val_m.height) + 2
        body_m = self._measure_node(node.args[0], fs, ctx)
        total_h = max(total_h, body_m.height)
        body_x = x + lim_col_w + 6
        body_y = y + (kh - body_m.height) / 2
        self._render_node(c, node.args[0], body_x, body_y, fs, ctx)

        total_w = lim_col_w + 6 + body_m.width
        return RenderBox(total_w, total_h, kh * 0.5)

    def _measure_log_base(self, c, node: FunctionCall, fs: int, ctx) -> RenderBox:
        sub_fs = max(int(fs * _SUB_SCALE), 6)
        nw, nh = self._text_size(c, "log", fs)
        base_m = self._measure_node(node.args[1], sub_fs, ctx)
        pw, ph = self._text_size(c, "(", fs)
        val_m = self._measure_node(node.args[0], fs, ctx)
        sub_y_off = nh * 0.55
        w = nw + base_m.width + pw + val_m.width + pw
        h = max(nh, sub_y_off + base_m.height, val_m.height)
        return RenderBox(w, h, max(nh / 2, val_m.baseline))

    def _render_log_base(self, c, node: FunctionCall, x, y, fs, ctx) -> RenderBox:
        sub_fs = max(int(fs * _SUB_SCALE), 6)
        f = self._get_font(c, fs)
        nw, nh = self._text_size(c, "log", fs)
        base_m = self._measure_node(node.args[1], sub_fs, ctx)
        pw, ph = self._text_size(c, "(", fs)
        val_m = self._measure_node(node.args[0], fs, ctx)
        sub_y_off = nh * 0.55

        total_h = max(nh, sub_y_off + base_m.height, val_m.height)
        bl = max(nh / 2, val_m.baseline)

        c.create_text(x, y + bl - nh / 2, text="log", anchor="nw", font=f, fill=_FUNCTION_COLOR)
        cx = x + nw
        self._render_node(c, node.args[1], cx, y + sub_y_off, sub_fs, ctx)
        cx += base_m.width
        self._draw_stretchy_paren(c, "(", cx, y, total_h, fs)
        cx += pw
        self._render_node(c, node.args[0], cx, y + bl - val_m.baseline, fs, ctx)
        cx += val_m.width
        self._draw_stretchy_paren(c, ")", cx, y, total_h, fs)
        cx += pw

        return RenderBox(cx - x, total_h, bl)

    def _render_derivative(self, c, node: FunctionCall, x, y, fs, ctx) -> RenderBox:
        body_node = node.args[0]
        var_node = node.args[1]

        body_m = self._measure_node(body_node, fs, ctx)
        var_m = self._measure_node(var_node, fs, ctx)

        f_italic = self._get_font(c, fs, "italic")
        dw, dh = self._text_size(c, "d", fs, "italic")

        num_w = dw + body_m.width
        den_w = dw + var_m.width
        frac_w = max(num_w, den_w) + 8

        num_y = y
        bar_y = y + max(dh, body_m.height) + 2
        den_y = bar_y + 4

        # Numerator: d + body
        nx = x + (frac_w - num_w) / 2
        c.create_text(nx, num_y, text="d", anchor="nw", font=f_italic, fill=_OPERATOR_COLOR)
        self._render_node(c, body_node, nx + dw, num_y, fs, ctx)

        # Fraction bar
        c.create_line(x, bar_y, x + frac_w, bar_y, fill=_OPERATOR_COLOR, width=1)

        # Denominator: d + var
        dx = x + (frac_w - den_w) / 2
        c.create_text(dx, den_y, text="d", anchor="nw", font=f_italic, fill=_OPERATOR_COLOR)
        self._render_node(c, var_node, dx + dw, den_y, fs, ctx)

        total_h = den_y + max(dh, var_m.height) - y
        return RenderBox(frac_w, total_h, bar_y - y)

    def _render_range(self, c, node: FunctionCall, x, y, fs, ctx) -> RenderBox:
        """Render range(start, end) or range(start, end, step) as start .. end."""
        f = self._get_font(c, fs)
        start_b = self._render_node(c, node.args[0], x, y, fs, ctx)
        cx = x + start_b.width
        if len(node.args) == 3:
            comma_w, _ = self._text_size(c, ", ", fs)
            c.create_text(cx, y, text=", ", anchor="nw", font=f, fill=_OPERATOR_COLOR)
            cx += comma_w
            step_b = self._render_node(c, node.args[2], cx, y, fs, ctx)
            cx += step_b.width
        dot_text = " .. "
        dot_w, _ = self._text_size(c, dot_text, fs)
        c.create_text(cx, y, text=dot_text, anchor="nw", font=f, fill=_OPERATOR_COLOR)
        cx += dot_w
        end_b = self._render_node(c, node.args[1], cx, y, fs, ctx)
        total_w = cx + end_b.width - x
        total_h = max(start_b.height, end_b.height)
        return RenderBox(total_w, total_h, total_h / 2)

    def _render_for(self, c, node: FunctionCall, x, y, fs, ctx) -> RenderBox:
        """Render for(body, var, start, end) as 'for var ∈ start..end' with body below."""
        f = self._get_font(c, fs, "bold")
        f_norm = self._get_font(c, fs)
        kw = "for "
        kw_w, kw_h = self._text_size(c, kw, fs, "bold")
        c.create_text(x, y, text=kw, anchor="nw", font=f, fill=_FUNCTION_COLOR)

        cx = x + kw_w
        var_b = self._render_node(c, node.args[1], cx, y, fs, ctx)
        cx += var_b.width
        eq_text = " ∈ "
        eq_w, _ = self._text_size(c, eq_text, fs)
        c.create_text(cx, y, text=eq_text, anchor="nw", font=f_norm, fill=_OPERATOR_COLOR)
        cx += eq_w
        start_b = self._render_node(c, node.args[2], cx, y, fs, ctx)
        cx += start_b.width
        dot_text = " .. "
        dot_w, _ = self._text_size(c, dot_text, fs)
        c.create_text(cx, y, text=dot_text, anchor="nw", font=f_norm, fill=_OPERATOR_COLOR)
        cx += dot_w
        end_b = self._render_node(c, node.args[3], cx, y, fs, ctx)

        header_w = cx + end_b.width - x
        header_h = max(kw_h, var_b.height, start_b.height, end_b.height)

        body_y = y + header_h + 4
        indent = 16
        body_b = self._render_node(c, node.args[0], x + indent, body_y, fs, ctx)

        total_w = max(header_w, indent + body_b.width)
        total_h = header_h + 4 + body_b.height
        return RenderBox(total_w, total_h, header_h / 2)

    def _render_while(self, c, node: FunctionCall, x, y, fs, ctx) -> RenderBox:
        """Render while(body, condition) as 'while condition' with body below."""
        f = self._get_font(c, fs, "bold")
        kw = "while "
        kw_w, kw_h = self._text_size(c, kw, fs, "bold")
        c.create_text(x, y, text=kw, anchor="nw", font=f, fill=_FUNCTION_COLOR)

        cond_b = self._render_node(c, node.args[1], x + kw_w, y, fs, ctx)
        header_w = kw_w + cond_b.width
        header_h = max(kw_h, cond_b.height)

        body_y = y + header_h + 4
        indent = 16
        body_b = self._render_node(c, node.args[0], x + indent, body_y, fs, ctx)

        total_w = max(header_w, indent + body_b.width)
        total_h = header_h + 4 + body_b.height
        return RenderBox(total_w, total_h, header_h / 2)

    def _render_if(self, c, node: FunctionCall, x, y, fs, ctx) -> RenderBox:
        """Render an if() as a piecewise block with curly brace."""
        cases = []
        for i in range(0, len(node.args) - 1, 2):
            val_node = node.args[i]
            cond_node = node.args[i + 1] if i + 1 < len(node.args) else None
            cases.append((val_node, cond_node))
        if len(node.args) % 2 == 1:
            cases.append((node.args[-1], None))

        line_h = 0.0
        case_data = []
        for val_node, cond_node in cases:
            vm = self._measure_node(val_node, fs, ctx)
            cm = self._measure_node(cond_node, fs, ctx) if cond_node else None
            row_h = max(vm.height, cm.height if cm else 0) + 4
            line_h += row_h
            case_data.append((val_node, cond_node, vm, cm, row_h))

        brace_w = 12
        self._draw_curly_brace(c, x, y, line_h, fs)

        cx = x + brace_w + 4
        cy = y
        max_val_w = 0.0
        for val_node, cond_node, vm, cm, row_h in case_data:
            self._render_node(c, val_node, cx, cy + (row_h - vm.height) / 2, fs, ctx)
            max_val_w = max(max_val_w, vm.width)
            cy += row_h

        if_w = max_val_w + 8
        cy = y
        f = self._get_font(c, fs)
        for val_node, cond_node, vm, cm, row_h in case_data:
            if cond_node:
                cw, _ = self._text_size(c, "if ", fs)
                c.create_text(cx + if_w, cy + (row_h - (cm.height if cm else 0)) / 2,
                              text="if ", anchor="nw", font=f, fill=_FUNCTION_COLOR)
                self._render_node(c, cond_node, cx + if_w + cw,
                                  cy + (row_h - (cm.height if cm else 0)) / 2, fs, ctx)
            else:
                c.create_text(cx + if_w, cy + (row_h - vm.height) / 2,
                              text="otherwise", anchor="nw", font=f, fill=_FUNCTION_COLOR)
            cy += row_h

        total_w = brace_w + 4 + if_w + max(
            (cm.width if cm else 0) + 20 for _, _, _, cm, _ in case_data
        )
        return RenderBox(total_w, line_h, line_h / 2)

    def _measure_sys(self, c, node: FunctionCall, fs: int, ctx) -> RenderBox:
        n_eqs = int(node.args[-2].value) if hasattr(node.args[-2], 'value') else len(node.args) - 2
        eqs = node.args[:n_eqs]
        brace_w = max(int(fs * 0.8), 10)
        row_pad = 4
        total_h = 0.0
        max_w = 0.0
        for eq in eqs:
            em = self._measure_node(eq, fs, ctx)
            max_w = max(max_w, em.width)
            total_h += em.height + row_pad
        total_h -= row_pad if eqs else 0
        total_h = max(total_h, self._text_size(c, "X", fs)[1])
        return RenderBox(brace_w + 4 + max_w, total_h, total_h / 2)

    def _render_sys(self, c, node: FunctionCall, x, y, fs, ctx) -> RenderBox:
        n_eqs = int(node.args[-2].value) if hasattr(node.args[-2], 'value') else len(node.args) - 2
        eqs = node.args[:n_eqs]
        brace_w = max(int(fs * 0.8), 10)
        row_pad = 4
        content_x = x + brace_w + 4
        row_data = []
        total_h = 0.0
        max_w = 0.0
        for eq in eqs:
            em = self._measure_node(eq, fs, ctx)
            row_data.append(em)
            max_w = max(max_w, em.width)
            total_h += em.height + row_pad
        total_h -= row_pad if eqs else 0
        total_h = max(total_h, self._text_size(c, "X", fs)[1])
        self._draw_curly_brace(c, x, y, total_h, fs)
        cy = y
        for eq, em in zip(eqs, row_data):
            self._render_node(c, eq, content_x, cy, fs, ctx)
            cy += em.height + row_pad
        return RenderBox(brace_w + 4 + max_w, max(total_h, 1), total_h / 2)

    def _render_line_block(self, c, node: FunctionCall, x, y, fs, ctx) -> RenderBox:
        """Render a line() block as system of equations with curly brace."""
        brace_w = max(int(fs * 0.8), 10)
        row_pad = 4
        content_x = x + brace_w + 4
        row_data = []
        total_h = 0.0
        max_w = 0.0
        for arg in node.args:
            am = self._measure_node(arg, fs, ctx)
            row_data.append(am)
            max_w = max(max_w, am.width)
            total_h += am.height + row_pad
        total_h -= row_pad if node.args else 0
        total_h = max(total_h, self._text_size(c, "X", fs)[1])
        self._draw_curly_brace(c, x, y, total_h, fs)
        cy = y
        for arg, am in zip(node.args, row_data):
            self._render_node(c, arg, content_x, cy, fs, ctx)
            cy += am.height + row_pad
        return RenderBox(brace_w + 4 + max_w, max(total_h, 1), total_h / 2)

    # -----------------------------------------------------------------
    # Scientific notation rendering
    # -----------------------------------------------------------------

    def _render_sci_number(self, c: tk.Canvas, text: str, x: float, y: float,
                           fs: int, color: str = _RESULT_COLOR) -> RenderBox:
        """Render a number, using ·10ⁿ notation for scientific notation."""
        import re
        m = re.match(r'^(-?\d+\.?\d*)[eE]([+-]?\d+)$', text)
        if not m:
            f = self._get_font(c, fs)
            c.create_text(x, y, text=text, anchor="nw", font=f, fill=color)
            w, h = self._text_size(c, text, fs)
            return RenderBox(w, h, h / 2)

        mantissa = m.group(1)
        exponent = m.group(2)
        if exponent.startswith('+'):
            exponent = exponent[1:]
        if exponent.startswith('0') and len(exponent) > 1:
            exponent = exponent.lstrip('0') or '0'

        f = self._get_font(c, fs)
        sup_fs = max(int(fs * _SUP_SCALE), 6)
        f_sup = self._get_font(c, sup_fs)

        cx = x
        mw, mh = self._text_size(c, mantissa, fs)
        c.create_text(cx, y, text=mantissa, anchor="nw", font=f, fill=color)
        cx += mw

        dot_text = "·10"
        dw, dh = self._text_size(c, dot_text, fs)
        c.create_text(cx, y, text=dot_text, anchor="nw", font=f, fill=color)
        cx += dw

        ew, eh = self._text_size(c, exponent, sup_fs)
        c.create_text(cx, y, text=exponent, anchor="nw", font=f_sup, fill=color)
        cx += ew

        total_w = cx - x
        total_h = max(mh, dh, eh)
        return RenderBox(total_w, total_h, total_h / 2)

    # -----------------------------------------------------------------
    # Result rendering
    # -----------------------------------------------------------------

    def render_with_result(
        self,
        canvas: tk.Canvas,
        node: ASTNode,
        result: Any,
        x: float,
        y: float,
        font_size: int = 12,
        context: Any = None,
        precision: int = 4,
        trailing_zeros: bool = False,
        exp_threshold: int = 5,
        fractions_mode: str = "decimal",
    ) -> RenderBox:
        """Render an expression, then `` = result`` after it."""
        self._canvas = canvas
        self._detect_font(canvas)

        # Render the expression first
        expr_box = self._render_node(canvas, node, x, y, font_size, context)

        if isinstance(result, Exception):
            if isinstance(result, NameError):
                return expr_box
            f = self._get_font(canvas, font_size)
            eq_text = " = "
            ew, eh = self._text_size(canvas, eq_text, font_size)
            ex = x + expr_box.width
            eq_y = y + expr_box.baseline - eh / 2
            canvas.create_text(ex, eq_y, text=eq_text, anchor="nw", font=f, fill=_OPERATOR_COLOR)
            err_text = str(result)
            if len(err_text) > 50:
                err_text = err_text[:47] + "..."
            rw, rh = self._text_size(canvas, err_text, font_size)
            err_x = ex + ew
            pad = 3
            canvas.create_rectangle(
                err_x - pad, eq_y - pad,
                err_x + rw + pad, eq_y + rh + pad,
                fill=_ERROR_BG_COLOR, outline=_ERROR_BORDER_COLOR, width=1,
            )
            canvas.create_text(err_x, eq_y, text=err_text, anchor="nw", font=f, fill=_ERROR_COLOR)
            total_w = expr_box.width + ew + rw + 2 * pad
            total_h = max(expr_box.height, eh, rh + 2 * pad)
            return RenderBox(total_w, total_h, expr_box.baseline)

        if result is not None and not isinstance(result, str):
            f = self._get_font(canvas, font_size)
            eq_text = " = "
            ew, eh = self._text_size(canvas, eq_text, font_size)
            ex = x + expr_box.width
            eq_y = y + expr_box.baseline - eh / 2
            canvas.create_text(ex, eq_y, text=eq_text, anchor="nw", font=f, fill=_OPERATOR_COLOR)

            res_x = ex + ew

            # If result is an AST node (from result_expr), render it as math
            if isinstance(result, ASTNode):
                rb = self._render_node(canvas, result, res_x, y, font_size, context)
            else:
                try:
                    if isinstance(result, np.ndarray):
                        rb = self._render_matrix_value(canvas, result, res_x, y, font_size)
                    elif isinstance(result, Quantity):
                        rb = self._render_quantity_result(canvas, result, res_x, eq_y, font_size, precision, trailing_zeros, exp_threshold, fractions_mode)
                    else:
                        frac = _to_fraction(result, precision) if fractions_mode == "fraction" else None
                        if frac is not None:
                            rb = self._render_fraction_result(canvas, frac[0], frac[1], res_x, eq_y, font_size)
                        else:
                            res_text = _format_result(result, precision, trailing_zeros, exp_threshold)
                            rb = self._render_sci_number(canvas, res_text, res_x, eq_y, font_size)
                except Exception:
                    res_text = _format_result(result, precision, trailing_zeros, exp_threshold)
                    rb = self._render_sci_number(canvas, res_text, res_x, eq_y, font_size)

            total_w = expr_box.width + ew + rb.width
            total_h = max(expr_box.height, eh, rb.height)
            return RenderBox(total_w, total_h, expr_box.baseline)

        return expr_box

    def _render_quantity_result(self, c: tk.Canvas, qty: Quantity, x, y, fs, precision=4, trailing_zeros=False, exp_threshold=5, fractions_mode="decimal") -> RenderBox:
        """Render a Quantity with the number in blue and the unit in blue."""
        frac = _to_fraction(qty.value, precision) if fractions_mode == "fraction" else None
        if frac is not None:
            num_box = self._render_fraction_result(c, frac[0], frac[1], x, y, fs)
        else:
            num_text = _format_result(qty.value, precision, trailing_zeros, exp_threshold)
        unit_str = qty.display_unit if hasattr(qty, 'display_unit') else str(qty.unit)

        if frac is None:
            num_box = self._render_sci_number(c, num_text, x, y, fs)
        nw, nh = num_box.width, num_box.height

        total_w = nw
        total_h = nh
        if unit_str:
            sp_w, _ = self._text_size(c, " ", fs)
            ux = x + nw + sp_w
            ub = self._render_unit_string(c, unit_str, ux, y, fs)
            total_w = nw + sp_w + ub.width
            total_h = max(nh, ub.height)

        return RenderBox(total_w, total_h, total_h / 2)

    def _render_unit_string(self, c: tk.Canvas, unit_str: str, x: float, y: float, fs: int) -> RenderBox:
        """Render a unit string like 'm^3/(kg·s^2)' with proper superscripts."""
        import re
        f = self._get_font(c, fs)
        sup_fs = max(int(fs * _SUP_SCALE), 6)
        f_sup = self._get_font(c, sup_fs)
        _, base_h = self._text_size(c, "M", fs)
        cx = x
        max_h = base_h
        i = 0
        while i < len(unit_str):
            if unit_str[i] == '^':
                i += 1
                exp_text = ""
                while i < len(unit_str) and (unit_str[i].isdigit() or unit_str[i] in "+-"):
                    exp_text += unit_str[i]
                    i += 1
                if exp_text:
                    ew, eh = self._text_size(c, exp_text, sup_fs)
                    c.create_text(cx, y, text=exp_text, anchor="nw", font=f_sup, fill=_UNIT_COLOR)
                    cx += ew
                    max_h = max(max_h, eh)
            elif unit_str[i:i+2] == '·' or unit_str[i] == '·':
                c.create_text(cx, y, text="·", anchor="nw", font=f, fill=_UNIT_COLOR)
                dw, _ = self._text_size(c, "·", fs)
                cx += dw
                i += 1
            else:
                chunk = ""
                while i < len(unit_str) and unit_str[i] not in "^·":
                    chunk += unit_str[i]
                    i += 1
                if chunk:
                    c.create_text(cx, y, text=chunk, anchor="nw", font=f, fill=_UNIT_COLOR)
                    cw, _ = self._text_size(c, chunk, fs)
                    cx += cw
        return RenderBox(cx - x, max_h, max_h / 2)

    def _render_fraction_result(self, c: tk.Canvas, num: int, den: int, x: float, y: float, fs: int) -> RenderBox:
        """Render a fraction result as a proper fraction with bar."""
        f = self._get_font(c, fs)
        num_text = str(abs(num))
        den_text = str(den)
        nw, nh = self._text_size(c, num_text, fs)
        dw, dh = self._text_size(c, den_text, fs)
        bar_w = max(nw, dw) + 2 * _FRAC_HPAD
        total_h = nh + dh + 2 * _FRAC_VPAD + 1
        sign_w = 0
        if num < 0:
            sign_text = "−"
            sw, sh = self._text_size(c, sign_text, fs)
            sign_w = sw + 3
            c.create_text(x, y + total_h / 2 - sh / 2, text=sign_text, anchor="nw", font=f, fill=_RESULT_COLOR)
        sx = x + sign_w
        num_x = sx + (bar_w - nw) / 2
        den_x = sx + (bar_w - dw) / 2
        c.create_text(num_x, y, text=num_text, anchor="nw", font=f, fill=_RESULT_COLOR)
        bar_y = y + nh + _FRAC_VPAD
        c.create_line(sx, bar_y, sx + bar_w, bar_y, fill=_RESULT_COLOR, width=1)
        c.create_text(den_x, bar_y + _FRAC_VPAD, text=den_text, anchor="nw", font=f, fill=_RESULT_COLOR)
        return RenderBox(sign_w + bar_w, total_h, bar_y)

    def _render_matrix_value(self, c, arr: np.ndarray, x, y, fs) -> RenderBox:
        """Render a numpy array as a bracketed matrix."""
        if arr.ndim == 1:
            arr = arr.reshape(-1, 1)
        rows, cols = arr.shape

        f = self._get_font(c, fs)
        cell_w = 0.0
        cell_h = 0.0
        texts = []
        for r in range(rows):
            row_texts = []
            for col_idx in range(cols):
                val = arr[r, col_idx]
                txt = _format_result(val, 4)
                w, h = self._text_size(c, txt, fs)
                cell_w = max(cell_w, w)
                cell_h = max(cell_h, h)
                row_texts.append(txt)
            texts.append(row_texts)

        inner_w = cols * (cell_w + _MATRIX_CELL_PAD) - _MATRIX_CELL_PAD
        inner_h = rows * (cell_h + _MATRIX_CELL_PAD) - _MATRIX_CELL_PAD
        total_w = inner_w + 2 * _MATRIX_BRACKET_W + 8
        total_h = inner_h + 8

        bw = _MATRIX_BRACKET_W
        lw = 1.2
        c.create_line(x + bw, y + 1, x + 1, y + 1, fill=_OPERATOR_COLOR, width=lw)
        c.create_line(x + 1, y + 1, x + 1, y + total_h - 1, fill=_OPERATOR_COLOR, width=lw)
        c.create_line(x + 1, y + total_h - 1, x + bw, y + total_h - 1, fill=_OPERATOR_COLOR, width=lw)
        rx = x + total_w - bw
        c.create_line(rx, y + 1, rx + bw - 1, y + 1, fill=_OPERATOR_COLOR, width=lw)
        c.create_line(rx + bw - 1, y + 1, rx + bw - 1, y + total_h - 1, fill=_OPERATOR_COLOR, width=lw)
        c.create_line(rx + bw - 1, y + total_h - 1, rx, y + total_h - 1, fill=_OPERATOR_COLOR, width=lw)

        # Cells
        cy = y + 4
        for r in range(rows):
            cx = x + _MATRIX_BRACKET_W + 4
            for col_idx in range(cols):
                txt = texts[r][col_idx]
                tw, th = self._text_size(c, txt, fs)
                cell_x = cx + (cell_w - tw) / 2
                cell_y = cy + (cell_h - th) / 2
                c.create_text(cell_x, cell_y, text=txt, anchor="nw", font=f, fill=_RESULT_COLOR)
                cx += cell_w + _MATRIX_CELL_PAD
            cy += cell_h + _MATRIX_CELL_PAD

        return RenderBox(total_w, total_h, total_h / 2)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_number(val) -> str:
    """Format a number for display."""
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        if val == int(val) and abs(val) < 1e15:
            return str(int(val))
        if abs(val) < 1e-4 or abs(val) >= 1e6:
            return f"{val:.4e}"
        formatted = f"{val:.6g}"
        return formatted
    return str(val)



def _to_fraction(val: float, precision: int = 4) -> tuple[int, int] | None:
    """Try to express a float as a simple fraction p/q.
    
    Returns (numerator, denominator) or None if no simple fraction exists.
    SMath Studio displays fractions when the denominator is reasonably small
    and the fraction is exact to the display precision.
    """
    if not isinstance(val, (int, float)):
        return None
    if isinstance(val, int):
        return None  # integers don't need fraction display
    if val != val or val == float('inf') or val == float('-inf'):
        return None
    if val == int(val):
        return None
    from fractions import Fraction
    try:
        frac = Fraction(val).limit_denominator(1000)
        if frac.denominator == 1:
            return None
        if frac.denominator > 100:
            return None
        if abs(float(frac) - val) < 10 ** (-(precision + 2)):
            return (frac.numerator, frac.denominator)
    except (ValueError, OverflowError, ZeroDivisionError):
        pass
    return None


def _format_result(val: Any, precision: int = 4, trailing_zeros: bool = False, exp_threshold: int = 5) -> str:
    """Format an evaluation result for display."""
    if isinstance(val, Quantity):
        num = _format_result(val.value, precision, trailing_zeros, exp_threshold)
        unit_str = val.display_unit if hasattr(val, 'display_unit') else str(val.unit)
        return f"{num} {unit_str}".strip()
    if isinstance(val, np.ndarray):
        return f"[{val.shape[0]}×{val.shape[1] if val.ndim > 1 else 1} matrix]"
    if isinstance(val, complex):
        rp = _format_result(val.real, precision, trailing_zeros, exp_threshold)
        ip = _format_result(abs(val.imag), precision, trailing_zeros, exp_threshold)
        if val.imag == 0:
            return rp
        if val.real == 0:
            sign = "-" if val.imag < 0 else ""
            return f"{sign}{ip}i" if ip != "1" else f"{sign}i"
        sign = " - " if val.imag < 0 else " + "
        return f"{rp}{sign}{ip}i"
    if isinstance(val, float):
        if val != val:
            return "NaN"
        if val == float('inf'):
            return "∞"
        if val == float('-inf'):
            return "-∞"
        if val == int(val) and abs(val) < 1e15:
            if trailing_zeros and precision > 0:
                return f"{val:.{precision}f}"
            return str(int(val))
        exp_lo = 10.0 ** (-exp_threshold)
        exp_hi = 10.0 ** exp_threshold
        if abs(val) < exp_lo or abs(val) >= exp_hi:
            return f"{val:.{precision}e}"
        result = f"{val:.{precision}f}"
        if not trailing_zeros:
            result = result.rstrip("0").rstrip(".")
        return result
    if isinstance(val, bool):
        return "1" if val else "0"
    if isinstance(val, int):
        if trailing_zeros and precision > 0:
            return f"{float(val):.{precision}f}"
        return str(val)
    if isinstance(val, str):
        return val
    return str(val)


_PRECEDENCE = {
    "|": 1, "&": 2,
    "=": 3, "≡": 3, "≠": 3, "<": 3, ">": 3, "≤": 3, "≥": 3,
    "+": 4, "-": 4, "±": 4,
    "*": 5, "·": 5,
    "/": 6, "^": 7, ":": 0,
}


def _needs_parens(child: ASTNode, parent_op: str, is_right: bool) -> bool:
    if not isinstance(child, BinaryOp):
        return False
    if child.operator in ("/", "^", ":"):
        return False
    child_prec = _PRECEDENCE.get(child.operator, 10)
    parent_prec = _PRECEDENCE.get(parent_op, 10)
    if child_prec < parent_prec:
        return True
    if child_prec == parent_prec and is_right and parent_op in ("-", "/"):
        return True
    return False


def _is_implicit_mult(node: BinaryOp) -> bool:
    """Check if multiplication should be rendered implicitly (thin space, no dot)."""
    if isinstance(node.right, UnitRef):
        return True
    if isinstance(node.left, Number) and isinstance(node.right, (Variable, FunctionCall)):
        return True
    if isinstance(node.left, Number) and isinstance(node.right, BinaryOp) and node.right.operator == "^":
        if isinstance(node.right.left, (Variable, FunctionCall)):
            return True
    return False


def _matrix_dims(node: FunctionCall) -> tuple[int, int]:
    """Extract matrix dimensions from a mat() function call.

    The last two args of mat() are rows and cols counts.
    """
    if len(node.args) < 2:
        return (1, 1)
    rows_node = node.args[-2]
    cols_node = node.args[-1]
    rows = int(rows_node.value) if isinstance(rows_node, Number) else 1
    cols = int(cols_node.value) if isinstance(cols_node, Number) else 1
    return (rows, cols)


def _matrix_cells(node: FunctionCall, rows: int, cols: int) -> list[list[ASTNode]]:
    """Extract cell nodes from a mat() call, organized as rows x cols."""
    data_args = node.args[: rows * cols]
    cells: list[list[ASTNode]] = []
    idx = 0
    for r in range(rows):
        row = []
        for col_idx in range(cols):
            if idx < len(data_args):
                row.append(data_args[idx])
            else:
                row.append(Number(0))
            idx += 1
        cells.append(row)
    return cells
