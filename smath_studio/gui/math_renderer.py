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
_BUILTIN_VAR_COLOR = "#000000"
_USER_VAR_COLOR = "#000000"
_UNIT_COLOR = "#0000ff"
_OPERATOR_COLOR = "#000000"
_FUNCTION_COLOR = "#000000"
_ERROR_COLOR = "#ff0000"

_OP_HPAD = 4       # horizontal padding around binary operators
_FRAC_HPAD = 3     # horizontal padding inside fraction bar
_FRAC_VPAD = 2     # vertical padding above/below fraction bar
_SUP_SCALE = 0.70  # superscript size ratio
_SUB_SCALE = 0.80  # subscript size ratio
_SUP_RAISE = 0.35  # superscript vertical shift (fraction of parent height)
_SUB_DROP = 0.25   # subscript vertical shift
_PAREN_HPAD = 2    # padding inside parentheses
_MATRIX_CELL_PAD = 6  # padding between matrix cells
_MATRIX_BRACKET_W = 4  # width of matrix brackets

# Built-in function names recognized by SMath Studio
_BUILTIN_FUNCTIONS = {
    "sin", "cos", "tan", "asin", "acos", "atan", "cot", "sec", "csc",
    "acot", "asec", "acsc", "sinh", "cosh", "tanh", "asinh", "acosh", "atanh",
    "ln", "log", "exp", "sqrt", "abs", "sign", "ceil", "floor", "round",
    "max", "min", "mod", "sum", "product", "nintegrate", "diff", "nderiv",
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
    "*": "·",   # middle dot ·
    "≤": "≤",
    "≥": "≥",
    "≠": "≠",
    "≡": "≡",
    ":": ":=",
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
                self._render_node(canvas, node, x, y, font_size, context)
            elif eval_result is not None:
                self.render_with_result(
                    canvas, node, eval_result, x, y,
                    font_size=font_size, context=context, precision=precision,
                )
            elif math_data_or_node.result_expr is not None:
                self.render_with_result(
                    canvas, node, math_data_or_node.result_expr, x, y,
                    font_size=font_size, context=context, precision=precision,
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
                    bbox = canvas.bbox("all")
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
        for family in ("Cambria Math", "STIX Two Math", "Times New Roman",
                       "DejaVu Serif", "Liberation Serif", "serif"):
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
            h = bh + sh * _SUB_DROP
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
        ow, oh = self._text_size(c, f" {op_text} ", fs)
        w = left.width + ow + right.width
        h = max(left.height, right.height, oh)
        bl = max(left.baseline, right.baseline, oh / 2)
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
        h = max(base.height, exp.height + raise_amt)
        return RenderBox(w, h, base.baseline)

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
        if name == "abs" and len(node.args) == 1:
            return self._measure_abs(c, node, fs, ctx)
        if name == "mat":
            return self._measure_matrix(c, node, fs, ctx)
        if name in ("sum", "product") and len(node.args) == 4:
            return self._measure_bigop(c, node, fs, ctx)
        if name == "nintegrate" and len(node.args) >= 3:
            return self._measure_integral(c, node, fs, ctx)
        if name in ("diff", "nderiv") and len(node.args) == 2:
            return self._measure_derivative(c, node, fs, ctx)
        if name == "if" and len(node.args) >= 2:
            return self._measure_if(c, node, fs, ctx)

        style = "" if name in _BUILTIN_FUNCTIONS else "italic"
        nw, nh = self._text_size(c, name, fs, style)
        pw, ph = self._text_size(c, "(", fs)

        args_w = 0
        args_h = nh
        for i, arg in enumerate(node.args):
            a = self._measure_node(arg, fs, ctx)
            args_w += a.width
            args_h = max(args_h, a.height)
            if i < len(node.args) - 1:
                cw, _ = self._text_size(c, ", ", fs)
                args_w += cw

        w = nw + pw + args_w + pw
        return RenderBox(w, args_h, args_h / 2)

    def _measure_sqrt(self, c, node: FunctionCall, fs: int, ctx) -> RenderBox:
        inner = self._measure_node(node.args[0], fs, ctx)
        sw, sh = self._text_size(c, "√", fs)
        w = sw + inner.width + 4
        h = inner.height + 4
        return RenderBox(w, h, h / 2)

    def _measure_abs(self, c, node: FunctionCall, fs: int, ctx) -> RenderBox:
        inner = self._measure_node(node.args[0], fs, ctx)
        bw, _ = self._text_size(c, "|", fs)
        return RenderBox(inner.width + bw * 2 + 4, inner.height, inner.baseline)

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

    def _measure_integral(self, c, node: FunctionCall, fs: int, ctx) -> RenderBox:
        sw, sh = self._text_size(c, "∫", int(fs * 1.6))
        body = self._measure_node(node.args[0], fs, ctx)
        sub_fs = max(int(fs * _SUB_SCALE), 6)
        lo = self._measure_node(node.args[1], sub_fs, ctx)
        hi = self._measure_node(node.args[2], sub_fs, ctx)
        sym_w = max(sw, lo.width, hi.width) + 4
        w = sym_w + body.width + 8
        h = max(sh + lo.height + hi.height, body.height)
        return RenderBox(w, h, h / 2)

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
        style = "bold" if is_builtin else "italic"
        color = _BUILTIN_VAR_COLOR

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

        # General infix operator
        total = self._measure_binary(c, node, fs, ctx)
        left_m = self._measure_node(node.left, fs, ctx)
        right_m = self._measure_node(node.right, fs, ctx)

        bl = total.baseline
        left_y = y + bl - left_m.baseline
        lb = self._render_node(c, node.left, x, left_y, fs, ctx)

        op_text = _DISPLAY_OPS.get(node.operator, node.operator)
        display = f" {op_text} "

        # For multiplication between a number/var and a unit, use thin space
        if node.operator == "*" and _is_implicit_mult(node):
            display = " "  # thin space

        f = self._get_font(c, fs)
        ox = x + lb.width
        ow, oh = self._text_size(c, display, fs)
        op_y = y + bl - oh / 2
        c.create_text(ox, op_y, text=display, anchor="nw", font=f, fill=_OPERATOR_COLOR)

        right_y = y + bl - right_m.baseline
        rb = self._render_node(c, node.right, ox + ow, right_y, fs, ctx)

        w = lb.width + ow + rb.width
        h = total.height
        return RenderBox(w, h, bl)

    def _render_fraction(self, c, node: BinaryOp, x, y, fs, ctx) -> RenderBox:
        num_m = self._measure_node(node.left, fs, ctx)
        den_m = self._measure_node(node.right, fs, ctx)

        bar_w = max(num_m.width, den_m.width) + 2 * _FRAC_HPAD
        bar_y = y + num_m.height + _FRAC_VPAD

        # Draw numerator (centered)
        num_x = x + (bar_w - num_m.width) / 2
        self._render_node(c, node.left, num_x, y, fs, ctx)

        # Draw fraction bar
        c.create_line(x, bar_y, x + bar_w, bar_y, fill=_OPERATOR_COLOR, width=1)

        # Draw denominator (centered)
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

        base_y = y + max(0, raise_amt + exp_m.height - base_m.height)
        bb = self._render_node(c, node.left, x, base_y, fs, ctx)

        exp_y = y
        self._render_node(c, node.right, x + bb.width, exp_y, sup_fs, ctx)

        w = bb.width + exp_m.width
        h = max(base_y + base_m.height, exp_y + exp_m.height) - y
        return RenderBox(w, h, base_y - y + base_m.baseline)

    def _render_assignment(self, c, node: BinaryOp, x, y, fs, ctx) -> RenderBox:
        total = self._measure_assignment(c, node, fs, ctx)
        bl = total.baseline

        left_m = self._measure_node(node.left, fs, ctx)
        left_y = y + bl - left_m.baseline
        lb = self._render_node(c, node.left, x, left_y, fs, ctx)

        f = self._get_font(c, fs)
        op_text = " := "
        ow, oh = self._text_size(c, op_text, fs)
        ox = x + lb.width
        op_y = y + bl - oh / 2
        c.create_text(ox, op_y, text=op_text, anchor="nw", font=f, fill=_OPERATOR_COLOR)

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
        if name == "abs" and len(node.args) == 1:
            return self._render_abs(c, node, x, y, fs, ctx)
        if name == "mat":
            return self._render_matrix(c, node, x, y, fs, ctx)
        if name in ("sum", "product") and len(node.args) == 4:
            return self._render_bigop(c, node, x, y, fs, ctx)
        if name == "nintegrate" and len(node.args) >= 3:
            return self._render_integral(c, node, x, y, fs, ctx)
        if name in ("diff", "nderiv") and len(node.args) == 2:
            return self._render_derivative(c, node, x, y, fs, ctx)
        if name == "if" and len(node.args) >= 2:
            return self._render_if(c, node, x, y, fs, ctx)
        if name == "line":
            return self._render_line_block(c, node, x, y, fs, ctx)

        # General function: name(arg1, arg2, ...)
        is_builtin = name in _BUILTIN_FUNCTIONS
        style = "" if is_builtin else "italic"
        f_name = self._get_font(c, fs, style)
        f_paren = self._get_font(c, fs)

        c.create_text(x, y, text=name, anchor="nw", font=f_name, fill=_FUNCTION_COLOR)
        nw, nh = self._text_size(c, name, fs, style)

        cx = x + nw
        c.create_text(cx, y, text="(", anchor="nw", font=f_paren, fill=_OPERATOR_COLOR)
        pw, ph = self._text_size(c, "(", fs)
        cx += pw

        total_h = nh
        for i, arg in enumerate(node.args):
            ab = self._render_node(c, arg, cx, y, fs, ctx)
            cx += ab.width
            total_h = max(total_h, ab.height)
            if i < len(node.args) - 1:
                c.create_text(cx, y, text=", ", anchor="nw", font=f_paren, fill=_OPERATOR_COLOR)
                cw, _ = self._text_size(c, ", ", fs)
                cx += cw

        c.create_text(cx, y, text=")", anchor="nw", font=f_paren, fill=_OPERATOR_COLOR)
        cx += pw

        return RenderBox(cx - x, total_h, total_h / 2)

    def _render_sqrt(self, c, node: FunctionCall, x, y, fs, ctx) -> RenderBox:
        inner_m = self._measure_node(node.args[0], fs, ctx)

        # Draw radical symbol
        f = self._get_font(c, int(fs * 1.2))
        radical = "√"
        c.create_text(x, y, text=radical, anchor="nw", font=f, fill=_OPERATOR_COLOR)
        sw, sh = self._text_size(c, radical, int(fs * 1.2))

        # Draw the inner expression
        inner_x = x + sw
        inner_y = y + 4
        ib = self._render_node(c, node.args[0], inner_x, inner_y, fs, ctx)

        # Draw vinculum (overline)
        line_y = y + 2
        c.create_line(inner_x - 2, line_y, inner_x + ib.width + 2, line_y,
                       fill=_OPERATOR_COLOR, width=1)

        w = sw + ib.width + 4
        h = max(sh, ib.height + 4)
        return RenderBox(w, h, h / 2)

    def _render_abs(self, c, node: FunctionCall, x, y, fs, ctx) -> RenderBox:
        inner_m = self._measure_node(node.args[0], fs, ctx)
        f = self._get_font(c, fs)
        bw, bh = self._text_size(c, "|", fs)

        # Left bar
        c.create_text(x, y, text="|", anchor="nw", font=f, fill=_OPERATOR_COLOR)

        # Inner
        ix = x + bw + 2
        ib = self._render_node(c, node.args[0], ix, y, fs, ctx)

        # Right bar
        rx = ix + ib.width + 2
        c.create_text(rx, y, text="|", anchor="nw", font=f, fill=_OPERATOR_COLOR)

        w = bw + 2 + ib.width + 2 + bw
        h = max(bh, ib.height)
        return RenderBox(w, h, h / 2)

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

        # Draw left bracket
        bx = x
        c.create_line(bx + _MATRIX_BRACKET_W, y + 2,
                       bx + 2, y + 2,
                       bx + 2, y + total_h - 2,
                       bx + _MATRIX_BRACKET_W, y + total_h - 2,
                       fill=_OPERATOR_COLOR, width=1.5)

        # Draw right bracket
        rx = x + total_w - _MATRIX_BRACKET_W
        c.create_line(rx, y + 2,
                       rx + _MATRIX_BRACKET_W - 2, y + 2,
                       rx + _MATRIX_BRACKET_W - 2, y + total_h - 2,
                       rx, y + total_h - 2,
                       fill=_OPERATOR_COLOR, width=1.5)

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
        big_fs = int(fs * 1.6)
        f_sym = self._get_font(c, big_fs)
        sym = "∫"
        sw, sh = self._text_size(c, sym, big_fs)

        sub_fs = max(int(fs * _SUB_SCALE), 6)
        body_node = node.args[0]
        lo_node = node.args[1]
        hi_node = node.args[2]

        lo_m = self._measure_node(lo_node, sub_fs, ctx)
        hi_m = self._measure_node(hi_node, sub_fs, ctx)
        body_m = self._measure_node(body_node, fs, ctx)

        sym_col_w = max(sw, lo_m.width, hi_m.width) + 4

        hi_y = y
        sym_y = hi_y + hi_m.height + 2
        lo_y = sym_y + sh + 2
        total_h = lo_y + lo_m.height - y
        body_y = y + (total_h - body_m.height) / 2

        # Upper limit
        hi_x = x + (sym_col_w - hi_m.width) / 2
        self._render_node(c, hi_node, hi_x, hi_y, sub_fs, ctx)

        # Integral symbol
        sym_x = x + (sym_col_w - sw) / 2
        c.create_text(sym_x, sym_y, text=sym, anchor="nw", font=f_sym, fill=_OPERATOR_COLOR)

        # Lower limit
        lo_x = x + (sym_col_w - lo_m.width) / 2
        self._render_node(c, lo_node, lo_x, lo_y, sub_fs, ctx)

        # Body
        body_x = x + sym_col_w + 4
        self._render_node(c, body_node, body_x, body_y, fs, ctx)

        # dx  (if there's a 4th arg for the variable)
        dx_w = 0
        if len(node.args) >= 4:
            var_node = node.args[3]
            f_d = self._get_font(c, fs)
            dx_x = body_x + body_m.width + 4
            c.create_text(dx_x, body_y, text="d", anchor="nw", font=f_d, fill=_OPERATOR_COLOR)
            dw, _ = self._text_size(c, "d", fs)
            self._render_node(c, var_node, dx_x + dw, body_y, fs, ctx)
            var_m = self._measure_node(var_node, fs, ctx)
            dx_w = 4 + dw + var_m.width

        total_w = sym_col_w + 4 + body_m.width + dx_w
        return RenderBox(total_w, total_h, total_h / 2)

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
        f_if = self._get_font(c, max(int(line_h * 0.8), fs))

        c.create_text(x, y + line_h * 0.3, text="{", anchor="nw", font=f_if, fill=_OPERATOR_COLOR)

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

    def _render_line_block(self, c, node: FunctionCall, x, y, fs, ctx) -> RenderBox:
        """Render a line() block (multi-line expression group)."""
        cy = y
        max_w = 0.0
        for arg in node.args:
            ab = self._render_node(c, arg, x, cy, fs, ctx)
            max_w = max(max_w, ab.width)
            cy += ab.height + 4
        total_h = cy - y - 4 if node.args else 0
        return RenderBox(max_w, max(total_h, 1), total_h / 2)

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
    ) -> RenderBox:
        """Render an expression, then `` = result`` after it."""
        self._canvas = canvas
        self._detect_font(canvas)

        # If the expression is an assignment (:), just render it without result
        if isinstance(node, BinaryOp) and node.operator == ":":
            return self._render_node(canvas, node, x, y, font_size, context)

        # If it's an evaluation or display, render expr = result
        expr_box = self._render_node(canvas, node, x, y, font_size, context)

        if isinstance(result, Exception):
            f = self._get_font(canvas, font_size)
            eq_text = " = "
            ew, eh = self._text_size(canvas, eq_text, font_size)
            ex = x + expr_box.width
            eq_y = y + expr_box.baseline - eh / 2
            canvas.create_text(ex, eq_y, text=eq_text, anchor="nw", font=f, fill=_OPERATOR_COLOR)
            err_text = str(result)
            if len(err_text) > 50:
                err_text = err_text[:47] + "..."
            canvas.create_text(ex + ew, eq_y, text=err_text, anchor="nw", font=f, fill=_ERROR_COLOR)
            rw, rh = self._text_size(canvas, err_text, font_size)
            total_w = expr_box.width + ew + rw
            total_h = max(expr_box.height, eh, rh)
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
                        rb = self._render_quantity_result(canvas, result, res_x, eq_y, font_size, precision)
                    else:
                        res_text = _format_result(result, precision)
                        canvas.create_text(res_x, eq_y, text=res_text, anchor="nw", font=f, fill=_NUMBER_COLOR)
                        rw, rh = self._text_size(canvas, res_text, font_size)
                        rb = RenderBox(rw, rh, rh / 2)
                except Exception:
                    res_text = _format_result(result, precision)
                    canvas.create_text(res_x, eq_y, text=res_text, anchor="nw", font=f, fill=_NUMBER_COLOR)
                    rw, rh = self._text_size(canvas, res_text, font_size)
                    rb = RenderBox(rw, rh, rh / 2)

            total_w = expr_box.width + ew + rb.width
            total_h = max(expr_box.height, eh, rb.height)
            return RenderBox(total_w, total_h, expr_box.baseline)

        return expr_box

    def _render_quantity_result(self, c: tk.Canvas, qty: Quantity, x, y, fs, precision=4) -> RenderBox:
        """Render a Quantity with the number in black and the unit in blue."""
        f = self._get_font(c, fs)
        num_text = _format_result(qty.value, precision)
        unit_str = qty.display_unit if hasattr(qty, 'display_unit') else str(qty.unit)

        # Render number
        c.create_text(x, y, text=num_text, anchor="nw", font=f, fill=_NUMBER_COLOR)
        nw, nh = self._text_size(c, num_text, fs)

        total_w = nw
        if unit_str:
            # Space before unit
            sp_w, _ = self._text_size(c, " ", fs)
            ux = x + nw + sp_w
            c.create_text(ux, y, text=unit_str, anchor="nw", font=f, fill=_UNIT_COLOR)
            uw, uh = self._text_size(c, unit_str, fs)
            total_w = nw + sp_w + uw

        return RenderBox(total_w, nh, nh / 2)

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

        # Left bracket
        c.create_line(x + _MATRIX_BRACKET_W, y + 2,
                       x + 2, y + 2,
                       x + 2, y + total_h - 2,
                       x + _MATRIX_BRACKET_W, y + total_h - 2,
                       fill=_OPERATOR_COLOR, width=1.5)
        # Right bracket
        rx = x + total_w - _MATRIX_BRACKET_W
        c.create_line(rx, y + 2,
                       rx + _MATRIX_BRACKET_W - 2, y + 2,
                       rx + _MATRIX_BRACKET_W - 2, y + total_h - 2,
                       rx, y + total_h - 2,
                       fill=_OPERATOR_COLOR, width=1.5)

        # Cells
        cy = y + 4
        for r in range(rows):
            cx = x + _MATRIX_BRACKET_W + 4
            for col_idx in range(cols):
                txt = texts[r][col_idx]
                tw, th = self._text_size(c, txt, fs)
                cell_x = cx + (cell_w - tw) / 2
                cell_y = cy + (cell_h - th) / 2
                c.create_text(cell_x, cell_y, text=txt, anchor="nw", font=f, fill=_NUMBER_COLOR)
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


def _format_result(val: Any, precision: int = 4) -> str:
    """Format an evaluation result for display."""
    if isinstance(val, Quantity):
        num = _format_result(val.value, precision)
        unit_str = val.display_unit if hasattr(val, 'display_unit') else str(val.unit)
        return f"{num} {unit_str}".strip()
    if isinstance(val, np.ndarray):
        return f"[{val.shape[0]}×{val.shape[1] if val.ndim > 1 else 1} matrix]"
    if isinstance(val, complex):
        rp = _format_result(val.real, precision)
        ip = _format_result(abs(val.imag), precision)
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
            return str(int(val))
        if abs(val) < 1e-4 or abs(val) >= 1e6:
            return f"{val:.{precision}e}"
        return f"{val:.{precision}f}".rstrip("0").rstrip(".")
    if isinstance(val, bool):
        return "1" if val else "0"
    if isinstance(val, int):
        return str(val)
    if isinstance(val, str):
        return val
    return str(val)


def _is_implicit_mult(node: BinaryOp) -> bool:
    """Check if multiplication should be rendered implicitly (no dot)."""
    if isinstance(node.right, UnitRef):
        return True
    if isinstance(node.left, (Number, Variable)) and isinstance(node.right, Variable):
        return False  # show dot between number and variable
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
