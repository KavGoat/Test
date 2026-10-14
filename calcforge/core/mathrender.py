"""Math typesetting renderer — lays out expressions as nested boxes.

Renders fractions, radicals, subscripts, superscripts and matrices
with QPainter, producing the handwritten-style math display.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from PySide6.QtCore import QRectF, QPointF, Qt
from PySide6.QtGui import (
    QPainter, QFont, QFontMetricsF, QPen, QColor, QPainterPath,
)

from .typography import serif_family


@dataclass
class Box:
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    ascent: float = 0.0
    descent: float = 0.0

    @property
    def baseline_y(self) -> float:
        return self.y + self.ascent

    @property
    def rect(self) -> QRectF:
        return QRectF(self.x, self.y, self.width, self.height)


@dataclass
class TextBox(Box):
    text: str = ""
    font_size: float = 14.0
    italic: bool = False
    bold: bool = False
    color: QColor = field(default_factory=lambda: QColor(0, 0, 0))
    is_unit: bool = False
    is_operator: bool = False


@dataclass
class FractionBox(Box):
    numerator: list[Box] = field(default_factory=list)
    denominator: list[Box] = field(default_factory=list)
    line_thickness: float = 1.0


@dataclass
class RadicalBox(Box):
    radicand: list[Box] = field(default_factory=list)
    index: Optional[list[Box]] = None


@dataclass
class ScriptBox(Box):
    base: list[Box] = field(default_factory=list)
    superscript: Optional[list[Box]] = None
    subscript: Optional[list[Box]] = None


@dataclass
class ParenBox(Box):
    content: list[Box] = field(default_factory=list)
    left_char: str = "("
    right_char: str = ")"


@dataclass
class MatrixBox(Box):
    rows: list[list[list[Box]]] = field(default_factory=list)
    row_count: int = 0
    col_count: int = 0


_GREEK_MAP = {
    "alpha": "α", "beta": "β", "gamma": "γ",
    "delta": "δ", "epsilon": "ε", "zeta": "ζ",
    "eta": "η", "theta": "θ", "iota": "ι",
    "kappa": "κ", "lambda": "λ", "mu": "μ",
    "nu": "ν", "xi": "ξ", "pi": "π",
    "rho": "ρ", "sigma": "σ", "tau": "τ",
    "upsilon": "υ", "phi": "φ", "chi": "χ",
    "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ",
    "Lambda": "Λ", "Sigma": "Σ", "Phi": "Φ",
    "Psi": "Ψ", "Omega": "Ω",
}

_OPERATORS = {'+', '-', '*', '/', '=', '<', '>', '≤', '≥',
              '×', '·', ':=', '→'}


class MathLayout:
    """Lays out a parsed expression into positioned boxes."""

    def __init__(self, base_font_size: float = 14.0):
        self.base_font_size = base_font_size
        self._font = QFont(serif_family(), int(base_font_size))
        self._fm = QFontMetricsF(self._font)

    def _make_font(self, size: float, italic: bool = False, bold: bool = False) -> QFont:
        f = QFont(serif_family(), int(size))
        f.setItalic(italic)
        f.setBold(bold)
        f.setPixelSize(int(size))
        return f

    def _text_metrics(self, text: str, size: float, italic: bool = False) -> tuple[float, float, float]:
        f = self._make_font(size, italic)
        fm = QFontMetricsF(f)
        w = fm.horizontalAdvance(text)
        a = fm.ascent()
        d = fm.descent()
        return w, a, d

    def layout_text(self, text: str, font_size: float = 0,
                    italic: bool = True, is_unit: bool = False,
                    is_operator: bool = False,
                    color: QColor = None) -> TextBox:
        fs = font_size or self.base_font_size
        display = _GREEK_MAP.get(text, text)
        if is_operator:
            italic = False
        if is_unit:
            italic = False
        w, a, d = self._text_metrics(display, fs, italic)
        if color is None:
            color = QColor(0, 0, 0)
        return TextBox(
            width=w, height=a + d, ascent=a, descent=d,
            text=display, font_size=fs, italic=italic,
            color=color, is_unit=is_unit, is_operator=is_operator,
        )

    def layout_fraction(self, num_boxes: list[Box], den_boxes: list[Box],
                        font_size: float = 0) -> FractionBox:
        fs = font_size or self.base_font_size
        nw = sum(b.width for b in num_boxes) + 2 * (len(num_boxes) - 1) if num_boxes else 10
        dw = sum(b.width for b in den_boxes) + 2 * (len(den_boxes) - 1) if den_boxes else 10
        bar_width = max(nw, dw) + 6
        nh = max((b.height for b in num_boxes), default=fs)
        dh = max((b.height for b in den_boxes), default=fs)
        gap = 3
        total_h = nh + gap + 1 + gap + dh
        num_x = (bar_width - nw) / 2
        for b in num_boxes:
            b.x = num_x
            b.y = 0
            num_x += b.width + 2
        den_x = (bar_width - dw) / 2
        for b in den_boxes:
            b.x = den_x
            b.y = nh + gap + 1 + gap
            den_x += b.width + 2
        return FractionBox(
            width=bar_width, height=total_h,
            ascent=nh + gap + 0.5,
            descent=dh + gap + 0.5,
            numerator=num_boxes, denominator=den_boxes,
        )

    def layout_radical(self, radicand: list[Box]) -> RadicalBox:
        rw = sum(b.width for b in radicand) + 2 * (len(radicand) - 1) if radicand else 10
        rh = max((b.height for b in radicand), default=self.base_font_size)
        sym_w = 12
        overline_gap = 3
        total_w = sym_w + rw + 4
        total_h = rh + overline_gap + 2
        x = sym_w + 2
        for b in radicand:
            b.x = x
            b.y = overline_gap + 2
            x += b.width + 2
        return RadicalBox(
            width=total_w, height=total_h,
            ascent=total_h * 0.7, descent=total_h * 0.3,
            radicand=radicand,
        )

    def layout_script(self, base: list[Box],
                      sup: Optional[list[Box]] = None,
                      sub: Optional[list[Box]] = None) -> ScriptBox:
        bw = sum(b.width for b in base) + 2 * (len(base) - 1) if base else 10
        bh = max((b.height for b in base), default=self.base_font_size)
        ba = max((b.ascent for b in base), default=self.base_font_size * 0.7)
        total_w = bw
        total_h = bh
        if sup:
            sw = sum(b.width for b in sup)
            sh = max((b.height for b in sup), default=self.base_font_size * 0.6)
            total_w = bw + sw + 1
            total_h = max(total_h, bh + sh * 0.4)
            sx = bw + 1
            for b in sup:
                b.x = sx
                b.y = 0
                sx += b.width
        if sub:
            sw = sum(b.width for b in sub)
            sh = max((b.height for b in sub), default=self.base_font_size * 0.6)
            total_w = max(total_w, bw + sw + 1)
            total_h = max(total_h, bh + sh * 0.4)
            sx = bw + 1
            for b in sub:
                b.x = sx
                b.y = bh - sh * 0.2
                sx += b.width
        return ScriptBox(
            width=total_w, height=total_h,
            ascent=ba, descent=total_h - ba,
            base=base, superscript=sup, subscript=sub,
        )


class MathPainter:
    """Renders laid-out math boxes using QPainter."""

    def paint(self, painter: QPainter, boxes: list[Box], origin_x: float, origin_y: float):
        for box in boxes:
            self._paint_box(painter, box, origin_x, origin_y)

    def _paint_box(self, painter: QPainter, box: Box, ox: float, oy: float):
        x = ox + box.x
        y = oy + box.y

        if isinstance(box, TextBox):
            font = QFont(serif_family(), int(box.font_size))
            font.setItalic(box.italic)
            font.setBold(box.bold)
            font.setPixelSize(int(box.font_size))
            painter.setFont(font)
            painter.setPen(QPen(box.color))
            painter.drawText(QPointF(x, y + box.ascent), box.text)

        elif isinstance(box, FractionBox):
            for b in box.numerator:
                self._paint_box(painter, b, x, y)
            bar_y = y + box.ascent
            painter.setPen(QPen(QColor(0, 0, 0), box.line_thickness))
            painter.drawLine(QPointF(x, bar_y), QPointF(x + box.width, bar_y))
            for b in box.denominator:
                self._paint_box(painter, b, x, y)

        elif isinstance(box, RadicalBox):
            painter.setPen(QPen(QColor(0, 0, 0), 1.2))
            path = QPainterPath()
            path.moveTo(x, y + box.height * 0.6)
            path.lineTo(x + 4, y + box.height * 0.5)
            path.lineTo(x + 8, y + box.height - 2)
            path.lineTo(x + 12, y + 2)
            path.lineTo(x + box.width, y + 2)
            painter.drawPath(path)
            for b in box.radicand:
                self._paint_box(painter, b, x, y)

        elif isinstance(box, ScriptBox):
            for b in box.base:
                self._paint_box(painter, b, x, y)
            if box.superscript:
                for b in box.superscript:
                    self._paint_box(painter, b, x, y)
            if box.subscript:
                for b in box.subscript:
                    self._paint_box(painter, b, x, y)

        elif isinstance(box, ParenBox):
            painter.setPen(QPen(QColor(0, 0, 0), 1.0))
            font = QFont(serif_family())
            font.setPixelSize(int(box.height * 0.9))
            painter.setFont(font)
            painter.drawText(QPointF(x, y + box.ascent), box.left_char)
            for b in box.content:
                self._paint_box(painter, b, x, y)
            painter.drawText(QPointF(x + box.width - 8, y + box.ascent), box.right_char)
