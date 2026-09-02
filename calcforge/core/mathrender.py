"""Two-dimensional maths typesetting.

Expressions are laid out as a tree of boxes (fractions, radicals, super/sub
scripts, matrices, scaled brackets) and painted directly with ``QPainter``.
This is what gives a CalcForge sheet its hand-written-calculation look instead
of a line of program source.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen

from .typography import SERIF, page_font
from .units import (Quantity, format_number, format_quantity, format_unit,
                    is_unit_name)

# ---------------------------------------------------------------------------
# Symbols
# ---------------------------------------------------------------------------

# Between a number and its unit, the way SMath separates the two.
UNIT_SEPARATOR = "·"

GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "zeta": "ζ", "eta": "η", "theta": "θ", "iota": "ι", "kappa": "κ",
    "lamda": "λ", "lambda_": "λ", "mu": "μ", "nu": "ν", "xi": "ξ",
    "omicron": "ο", "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ",
    "upsilon": "υ", "phi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ",
    "Pi": "Π", "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
    "nabla": "∇", "partial": "∂", "infinity": "∞", "inf": "∞",
}

OPERATORS = {
    ast.Add: "+", ast.Sub: "−", ast.Mult: "·", ast.Div: "/", ast.Mod: "mod",
    ast.Pow: "^", ast.FloorDiv: "÷", ast.MatMult: "×",
}

COMPARISONS = {
    ast.Eq: "=", ast.NotEq: "≠", ast.Lt: "<", ast.LtE: "≤",
    ast.Gt: ">", ast.GtE: "≥", ast.In: "∈", ast.NotIn: "∉",
}

# Function names that get their own visual treatment.
ROMAN_FUNCTIONS = {
    "sin", "cos", "tan", "asin", "acos", "atan", "atan2", "sinh", "cosh",
    "tanh", "ln", "log", "log2", "log10", "exp", "min", "max", "mean", "sum",
    "median", "stdev", "if", "mod", "det", "inv", "round", "floor", "ceil",
}


@dataclass
class MathStyle:
    """Fonts and metrics for one typeset expression."""

    family: str = "Cambria Math"
    fallback: str = "DejaVu Serif"
    size: float = 10.0
    color: QColor = field(default_factory=lambda: QColor(20, 20, 24))
    result_color: QColor = field(default_factory=lambda: QColor(20, 20, 24))
    error_color: QColor = field(default_factory=lambda: QColor(190, 40, 40))
    comment_color: QColor = field(default_factory=lambda: QColor(110, 120, 130))
    unit_color: QColor = field(default_factory=lambda: QColor(60, 90, 150))
    script_ratio: float = 0.68
    min_size: float = 4.5

    def font(self, size: float, italic: bool = False, bold: bool = False) -> QFont:
        return page_font(self.family, max(size, self.min_size), bold, italic,
                         fallbacks=[self.fallback] + SERIF)


# ---------------------------------------------------------------------------
# Box model
# ---------------------------------------------------------------------------

class Box:
    """A laid-out fragment with a width and an ascent/descent about its baseline."""

    width: float = 0.0
    ascent: float = 0.0
    descent: float = 0.0

    @property
    def height(self) -> float:
        return self.ascent + self.descent

    def draw(self, painter: QPainter, x: float, baseline: float) -> None:
        raise NotImplementedError


class Glyph(Box):
    def __init__(self, text: str, font: QFont, color: QColor):
        self.text = text
        self.font = font
        self.color = color
        metrics = QFontMetricsF(font)
        self.width = metrics.horizontalAdvance(text)
        self.ascent = metrics.ascent()
        self.descent = metrics.descent()

    def draw(self, painter: QPainter, x: float, baseline: float) -> None:
        painter.setFont(self.font)
        painter.setPen(QPen(self.color))
        painter.drawText(QPointF(x, baseline), self.text)


class Spacer(Box):
    def __init__(self, width: float, ascent: float = 0.0, descent: float = 0.0):
        self.width = width
        self.ascent = ascent
        self.descent = descent

    def draw(self, painter: QPainter, x: float, baseline: float) -> None:
        return


class Row(Box):
    """Horizontal sequence sharing one baseline."""

    def __init__(self, children: list[Box]):
        self.children = [c for c in children if c is not None]
        self.width = sum(c.width for c in self.children)
        self.ascent = max((c.ascent for c in self.children), default=0.0)
        self.descent = max((c.descent for c in self.children), default=0.0)

    def draw(self, painter: QPainter, x: float, baseline: float) -> None:
        for child in self.children:
            child.draw(painter, x, baseline)
            x += child.width


class Shifted(Box):
    """A box moved vertically relative to the baseline (super/subscripts)."""

    def __init__(self, child: Box, dy: float):
        self.child = child
        self.dy = dy
        self.width = child.width
        self.ascent = max(child.ascent - dy, 0.0)
        self.descent = max(child.descent + dy, 0.0)

    def draw(self, painter: QPainter, x: float, baseline: float) -> None:
        self.child.draw(painter, x, baseline + self.dy)


class Fraction(Box):
    def __init__(self, numerator: Box, denominator: Box, style: MathStyle, size: float,
                 color: QColor):
        self.num = numerator
        self.den = denominator
        self.color = color
        self.pad = size * 0.28
        self.rule = max(size * 0.075, 0.6)
        self.gap = size * 0.22
        axis = size * 0.32                     # height of the fraction bar
        self.width = max(numerator.width, denominator.width) + 2 * self.pad
        self.ascent = axis + self.rule / 2 + self.gap + numerator.height
        self.descent = -axis + self.rule / 2 + self.gap + denominator.height
        self.axis = axis

    def draw(self, painter: QPainter, x: float, baseline: float) -> None:
        bar_y = baseline - self.axis
        centre = x + self.width / 2
        self.num.draw(painter, centre - self.num.width / 2,
                      bar_y - self.rule / 2 - self.gap - self.num.descent)
        self.den.draw(painter, centre - self.den.width / 2,
                      bar_y + self.rule / 2 + self.gap + self.den.ascent)
        pen = QPen(self.color)
        pen.setWidthF(self.rule)
        painter.setPen(pen)
        painter.drawLine(QPointF(x + self.pad * 0.4, bar_y),
                         QPointF(x + self.width - self.pad * 0.4, bar_y))


class Radical(Box):
    def __init__(self, child: Box, style: MathStyle, size: float, color: QColor,
                 index: Optional[Box] = None):
        self.child = child
        self.color = color
        self.index = index
        self.pad = size * 0.16
        self.rule = max(size * 0.06, 0.5)
        self.hook = size * 0.62
        self.gap = size * 0.22
        index_width = (index.width * 0.9 if index else 0.0)
        self.lead = self.hook + index_width * 0.55
        self.width = self.lead + child.width + self.pad * 2
        self.ascent = child.ascent + self.gap + self.rule * 2
        self.descent = child.descent + self.pad * 0.5

    def draw(self, painter: QPainter, x: float, baseline: float) -> None:
        top = baseline - self.ascent + self.rule
        bottom = baseline + self.descent
        pen = QPen(self.color)
        pen.setWidthF(self.rule * 1.4)
        pen.setJoinStyle(Qt.MiterJoin)
        painter.setPen(pen)
        path = QPainterPath()
        path.moveTo(x + self.lead * 0.05, bottom - (bottom - top) * 0.45)
        path.lineTo(x + self.lead * 0.32, bottom - (bottom - top) * 0.28)
        path.lineTo(x + self.lead * 0.62, bottom)
        path.lineTo(x + self.lead * 0.95, top)
        path.lineTo(x + self.width, top)
        painter.strokePath(path, pen)
        if self.index is not None:
            self.index.draw(painter, x, top + (bottom - top) * 0.42)
        self.child.draw(painter, x + self.lead + self.pad, baseline)


class Bracket(Box):
    """Vertically scaled bracket pair around a child box."""

    def __init__(self, child: Box, kind: str, size: float, color: QColor):
        self.child = child
        self.kind = kind
        self.color = color
        self.pen_width = max(size * 0.06, 0.5)
        self.thickness = max(size * 0.22, 2.2)
        self.width = child.width + 2 * self.thickness
        self.ascent = child.ascent + size * 0.10
        self.descent = child.descent + size * 0.10

    def _paint(self, painter: QPainter, x: float, top: float, bottom: float, opening: bool) -> None:
        pen = QPen(self.color)
        pen.setWidthF(self.pen_width)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        height = bottom - top
        bulge = self.thickness * 0.75
        path = QPainterPath()
        if self.kind == "paren":
            if opening:
                path.moveTo(x + bulge, top)
                path.cubicTo(x - bulge * 0.25, top + height * 0.28,
                             x - bulge * 0.25, bottom - height * 0.28,
                             x + bulge, bottom)
            else:
                path.moveTo(x, top)
                path.cubicTo(x + bulge * 1.25, top + height * 0.28,
                             x + bulge * 1.25, bottom - height * 0.28,
                             x, bottom)
        elif self.kind == "square":
            if opening:
                path.moveTo(x + bulge, top)
                path.lineTo(x + bulge * 0.15, top)
                path.lineTo(x + bulge * 0.15, bottom)
                path.lineTo(x + bulge, bottom)
            else:
                path.moveTo(x, top)
                path.lineTo(x + bulge * 0.85, top)
                path.lineTo(x + bulge * 0.85, bottom)
                path.lineTo(x, bottom)
        else:  # vertical bars for absolute value / determinant
            path.moveTo(x + bulge * 0.5, top)
            path.lineTo(x + bulge * 0.5, bottom)
        painter.strokePath(path, pen)

    def draw(self, painter: QPainter, x: float, baseline: float) -> None:
        top = baseline - self.ascent
        bottom = baseline + self.descent
        self._paint(painter, x, top, bottom, True)
        self.child.draw(painter, x + self.thickness, baseline)
        self._paint(painter, x + self.thickness + self.child.width, top, bottom, False)


class Stack(Box):
    """Vertically stacked rows (matrices, multi-line results)."""

    def __init__(self, rows: list[Box], gap: float, align: str = "center"):
        self.rows = rows
        self.gap = gap
        self.align = align
        self.width = max((r.width for r in rows), default=0.0)
        total = sum(r.height for r in rows) + gap * max(len(rows) - 1, 0)
        # Centre the stack on the maths axis rather than on the baseline.
        self.ascent = total * 0.5 + gap
        self.descent = total - self.ascent

    def draw(self, painter: QPainter, x: float, baseline: float) -> None:
        y = baseline - self.ascent
        for row in self.rows:
            if self.align == "center":
                rx = x + (self.width - row.width) / 2
            elif self.align == "right":
                rx = x + self.width - row.width
            else:
                rx = x
            row.draw(painter, rx, y + row.ascent)
            y += row.height + self.gap


# ---------------------------------------------------------------------------
# AST -> boxes
# ---------------------------------------------------------------------------

_PRECEDENCE = {
    ast.Or: 1, ast.And: 2, ast.Compare: 3,
    ast.Add: 4, ast.Sub: 4,
    ast.Mult: 5, ast.Div: 5, ast.Mod: 5, ast.MatMult: 5, ast.FloorDiv: 5,
    ast.USub: 6, ast.UAdd: 6, ast.Pow: 7,
}


def split_name(name: str) -> tuple[str, str]:
    """Split ``sigma_c,max`` into a base symbol and a subscript."""
    if "_" not in name:
        return GREEK.get(name, name), ""
    base, _, sub = name.partition("_")
    if not sub:
        return GREEK.get(base, base), ""
    base_text = GREEK.get(base, base)
    sub_text = GREEK.get(sub, sub.replace("_", ","))
    return base_text, sub_text


class Typesetter:
    """Builds a :class:`Box` tree from a Python AST."""

    def __init__(self, style: MathStyle, color: Optional[QColor] = None,
                 variables: Optional[set[str]] = None):
        self.style = style
        self.color = color or style.color
        # Names the document has defined; anything else that the unit registry
        # recognises is drawn upright, the way units are set in print.
        self.variables = variables or set()

    def is_unit(self, name: str) -> bool:
        return name not in self.variables and name not in GREEK and is_unit_name(name)

    # -- primitives --------------------------------------------------------
    def text(self, text: str, size: float, italic: bool = False, bold: bool = False,
             color: Optional[QColor] = None) -> Box:
        return Glyph(text, self.style.font(size, italic, bold), color or self.color)

    def name_box(self, name: str, size: float, italic: bool = True,
                 color: Optional[QColor] = None) -> Box:
        base, sub = split_name(name)
        glyph = self.text(base, size, italic and len(base) <= 2, color=color)
        if not sub:
            return glyph
        sub_size = max(size * self.style.script_ratio, self.style.min_size)
        sub_box = self.text(sub, sub_size, False, color=color)
        return Row([glyph, Shifted(sub_box, size * 0.24)])

    def bracket(self, child: Box, size: float, kind: str = "paren") -> Box:
        return Bracket(child, kind, size, self.color)

    # -- dispatch ----------------------------------------------------------
    def build(self, node: ast.AST, size: float) -> Box:
        method = getattr(self, "_build_" + type(node).__name__, None)
        if method is None:
            return self.text(_unparse(node), size)
        return method(node, size)

    def _wrap(self, node: ast.AST, size: float, parent_precedence: int,
              right: bool = False) -> Box:
        box = self.build(node, size)
        precedence = self._precedence(node)
        if precedence is None:
            return box
        if precedence < parent_precedence or (right and precedence == parent_precedence):
            return self.bracket(box, size)
        return box

    @staticmethod
    def _precedence(node: ast.AST) -> Optional[int]:
        if isinstance(node, ast.BinOp):
            return _PRECEDENCE.get(type(node.op))
        if isinstance(node, ast.UnaryOp):
            return _PRECEDENCE.get(type(node.op))
        if isinstance(node, ast.BoolOp):
            return _PRECEDENCE.get(type(node.op))
        if isinstance(node, ast.Compare):
            return 3
        if isinstance(node, ast.IfExp):
            return 0
        return None

    # -- node handlers -----------------------------------------------------
    def _build_Expression(self, node: ast.Expression, size: float) -> Box:
        return self.build(node.body, size)

    def _build_Name(self, node: ast.Name, size: float) -> Box:
        if node.id in GREEK and "_" not in node.id:
            return self.text(GREEK[node.id], size, italic=False)
        if self.is_unit(node.id):
            return self.text(node.id, size, italic=False, color=self.style.unit_color)
        return self.name_box(node.id, size)

    def _build_Constant(self, node: ast.Constant, size: float) -> Box:
        value = node.value
        if isinstance(value, bool):
            return self.text("true" if value else "false", size)
        if isinstance(value, (int, float)):
            return self.text(format_number(value, 10), size)
        if isinstance(value, str):
            return self.text(f"“{value}”", size)
        return self.text(str(value), size)

    def _build_BinOp(self, node: ast.BinOp, size: float) -> Box:
        op = type(node.op)
        if op is ast.Div:
            small = size * 0.98
            num = self.build(node.left, small)
            den = self.build(node.right, small)
            return Fraction(num, den, self.style, size, self.color)
        if op is ast.Pow:
            base = self._wrap(node.left, size, 8)
            exp_size = max(size * self.style.script_ratio, self.style.min_size)
            exponent = self.build(node.right, exp_size)
            return Row([base, Shifted(exponent, -size * 0.48)])

        if op is ast.Mult and isinstance(node.left, ast.Constant) and isinstance(node.right, ast.Name):
            # "5 m" reads better than "5 · m"
            return Row([self.build(node.left, size), Spacer(size * 0.22),
                        self.build(node.right, size)])

        precedence = _PRECEDENCE.get(op, 4)
        left = self._wrap(node.left, size, precedence)
        right = self._wrap(node.right, size, precedence, right=op in (ast.Sub, ast.Div))
        symbol = OPERATORS.get(op, "?")
        pad = size * (0.16 if op is ast.Mult else 0.26)
        return Row([left, Spacer(pad), self.text(symbol, size), Spacer(pad), right])

    def _build_UnaryOp(self, node: ast.UnaryOp, size: float) -> Box:
        if isinstance(node.op, ast.USub):
            return Row([self.text("−", size), self._wrap(node.operand, size, 6)])
        if isinstance(node.op, ast.UAdd):
            return self._wrap(node.operand, size, 6)
        return Row([self.text("¬", size), Spacer(size * 0.12),
                    self._wrap(node.operand, size, 6)])

    def _build_BoolOp(self, node: ast.BoolOp, size: float) -> Box:
        symbol = "∧" if isinstance(node.op, ast.And) else "∨"
        parts: list[Box] = []
        for index, value in enumerate(node.values):
            if index:
                parts += [Spacer(size * 0.3), self.text(symbol, size), Spacer(size * 0.3)]
            parts.append(self._wrap(value, size, 2))
        return Row(parts)

    def _build_Compare(self, node: ast.Compare, size: float) -> Box:
        parts = [self._wrap(node.left, size, 4)]
        for op, comparator in zip(node.ops, node.comparators):
            symbol = COMPARISONS.get(type(op), "?")
            parts += [Spacer(size * 0.3), self.text(symbol, size), Spacer(size * 0.3),
                      self._wrap(comparator, size, 4)]
        return Row(parts)

    def _build_IfExp(self, node: ast.IfExp, size: float) -> Box:
        return Row([
            self.build(node.body, size), Spacer(size * 0.3),
            self.text("if", size), Spacer(size * 0.3),
            self.build(node.test, size), Spacer(size * 0.3),
            self.text("otherwise", size), Spacer(size * 0.3),
            self.build(node.orelse, size),
        ])

    def _build_Call(self, node: ast.Call, size: float) -> Box:
        name = _unparse(node.func)
        args = list(node.args)

        if name in ("sqrt",) and len(args) == 1:
            return Radical(self.build(args[0], size), self.style, size, self.color)
        if name == "root" and len(args) == 2:
            index_size = max(size * 0.55, self.style.min_size)
            return Radical(self.build(args[0], size), self.style, size, self.color,
                           index=self.build(args[1], index_size))
        if name in ("abs", "norm") and len(args) == 1:
            return Bracket(self.build(args[0], size), "bar", size, self.color)
        if name == "det" and len(args) == 1:
            return Bracket(self.build(args[0], size), "bar", size, self.color)
        if name == "exp" and len(args) == 1:
            exp_size = max(size * self.style.script_ratio, self.style.min_size)
            return Row([self.text("e", size, italic=True),
                        Shifted(self.build(args[0], exp_size), -size * 0.48)])
        if name == "to" and len(args) == 2:
            return Row([self.build(args[0], size), Spacer(size * 0.3),
                        self.text("→", size), Spacer(size * 0.3),
                        self.build(args[1], size)])

        italic = name not in ROMAN_FUNCTIONS
        head = self.name_box(name, size, italic=italic)
        inner: list[Box] = []
        for index, arg in enumerate(args):
            if index:
                inner += [self.text(",", size), Spacer(size * 0.24)]
            inner.append(self.build(arg, size))
        for kw in node.keywords:
            if inner:
                inner += [self.text(",", size), Spacer(size * 0.24)]
            inner += [self.text(f"{kw.arg}=", size), self.build(kw.value, size)]
        return Row([head, self.bracket(Row(inner), size)])

    def _build_Subscript(self, node: ast.Subscript, size: float) -> Box:
        base = self.build(node.value, size)
        sub_size = max(size * self.style.script_ratio, self.style.min_size)
        index = self.build(node.slice, sub_size)
        return Row([base, Shifted(index, size * 0.24)])

    def _build_Tuple(self, node: ast.Tuple, size: float) -> Box:
        return self._sequence(node.elts, size, "paren")

    def _build_List(self, node: ast.List, size: float) -> Box:
        if node.elts and all(isinstance(e, ast.List) for e in node.elts):
            rows = [self._row_of(e.elts, size) for e in node.elts]
            return Bracket(Stack(rows, size * 0.3, "center"), "square", size, self.color)
        return self._sequence(node.elts, size, "square")

    def _row_of(self, elements: list[ast.AST], size: float) -> Box:
        parts: list[Box] = []
        for index, element in enumerate(elements):
            if index:
                parts.append(Spacer(size * 0.8))
            parts.append(self.build(element, size))
        return Row(parts)

    def _sequence(self, elements: list[ast.AST], size: float, kind: str) -> Box:
        parts: list[Box] = []
        for index, element in enumerate(elements):
            if index:
                parts += [self.text(",", size), Spacer(size * 0.24)]
            parts.append(self.build(element, size))
        return Bracket(Row(parts), kind, size, self.color)

    # -- values ------------------------------------------------------------
    def value_box(self, value: Any, size: float, digits: int = 4, mode: str = "auto",
                  color: Optional[QColor] = None, unit_color: Optional[QColor] = None) -> Box:
        """Typeset an evaluated result, keeping the unit visually distinct."""
        color = color or self.style.result_color
        unit_color = unit_color or self.style.unit_color

        if isinstance(value, Quantity):
            magnitude = value.magnitude
            unit_text = format_unit(value.units)
            body = self.value_box(magnitude, size, digits, mode, color, unit_color)
            if not unit_text or unit_text == "dimensionless":
                return body
            # SMath writes a small dot between a value and its unit, and it
            # earns its place: "5·kN" reads as one quantity where "5 kN" can
            # read as two things that happen to be next to each other.
            return Row([body, Spacer(size * 0.16),
                        self.text(UNIT_SEPARATOR, size * 0.8, color=unit_color),
                        Spacer(size * 0.16),
                        self._unit_box(unit_text, size, unit_color)])

        if isinstance(value, np.ndarray):
            array = np.atleast_2d(value)
            rows = []
            for row in array:
                cells: list[Box] = []
                for index, cell in enumerate(row):
                    if index:
                        cells.append(Spacer(size * 0.9))
                    cells.append(self.text(format_number(cell, digits, mode), size, color=color))
                rows.append(Row(cells))
            return Bracket(Stack(rows, size * 0.3), "square", size, color)

        if isinstance(value, (list, tuple)):
            parts: list[Box] = []
            for index, item in enumerate(value):
                if index:
                    parts += [self.text(",", size, color=color), Spacer(size * 0.24)]
                parts.append(self.value_box(item, size, digits, mode, color, unit_color))
            return Bracket(Row(parts), "paren", size, color)

        return self.text(format_quantity(value, digits, mode), size, color=color)

    def unit_text_box(self, unit_source: str, size: float, color: Optional[QColor] = None) -> Box:
        """Typeset a unit written as source (``kN*m``, ``mm^3``) prettily."""
        from .units import format_unit, parse_unit

        text = unit_source
        try:
            quantity = parse_unit(unit_source)
            if quantity is not None:
                text = format_unit(quantity.units)
        except Exception:
            pass
        return self._unit_box(text, size, color or self.style.unit_color)

    def _unit_box(self, unit_text: str, size: float, color: QColor) -> Box:
        """Render ``kN·m²`` with real superscripts."""
        parts: list[Box] = []
        buffer = ""
        index = 0
        while index < len(unit_text):
            ch = unit_text[index]
            if ch in "⁰¹²³⁴⁵⁶⁷⁸⁹⁻":
                if buffer:
                    parts.append(self.text(buffer, size, italic=False, color=color))
                    buffer = ""
                run = ""
                while index < len(unit_text) and unit_text[index] in "⁰¹²³⁴⁵⁶⁷⁸⁹⁻":
                    run += unit_text[index]
                    index += 1
                plain = run.translate(str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-"))
                exp_size = max(size * self.style.script_ratio, self.style.min_size)
                parts.append(Shifted(self.text(plain, exp_size, color=color), -size * 0.42))
                continue
            buffer += ch
            index += 1
        if buffer:
            parts.append(self.text(buffer, size, italic=False, color=color))
        return Row(parts)


def _unparse(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return "?"


def typeset_expression(source_or_tree, style: MathStyle, size: Optional[float] = None) -> Box:
    """Convenience wrapper: text or AST in, laid-out :class:`Box` out."""
    from .engine import compile_expression

    size = size if size is not None else style.size
    setter = Typesetter(style)
    tree = source_or_tree
    if isinstance(source_or_tree, str):
        try:
            _code, tree = compile_expression(source_or_tree)
        except Exception:
            return setter.text(source_or_tree, size)
    return setter.build(tree, size)
