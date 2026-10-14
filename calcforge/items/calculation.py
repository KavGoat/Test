"""Calculation region — unit-aware, typeset math expressions."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPen, QColor, QFont

from .base import PageItem
from ..core.document import Region
from ..core.evaluator import EvalContext, eval_line, EvalResult
from ..core.mathrender import MathLayout, MathPainter, TextBox


class CalculationItem(PageItem):
    """A calculation region on the page."""

    def __init__(self, region: Region, parent=None):
        super().__init__(region, parent)
        self.lines: list[str] = region.data.get("lines", [""])
        self.results: list[EvalResult] = []
        self.editing = False
        self.cursor_line = 0
        self.cursor_pos = 0
        self._math_layout = MathLayout(14.0)
        self._math_painter = MathPainter()

    def evaluate(self, ctx: EvalContext) -> list[EvalResult]:
        self.results = []
        for line in self.lines:
            result = eval_line(line, ctx)
            self.results.append(result)
        self._update_size()
        return self.results

    def _update_size(self):
        line_h = 22.0
        total_h = max(line_h * len(self.lines), line_h)
        max_w = 100.0
        font = QFont("serif", 14)
        font.setPixelSize(14)
        from PySide6.QtGui import QFontMetricsF
        fm = QFontMetricsF(font)
        for i, line in enumerate(self.lines):
            display = self.results[i].display_text if i < len(self.results) else line
            w = fm.horizontalAdvance(display) + 20
            max_w = max(max_w, w)
        self.region.width = max_w
        self.region.height = total_h
        self.setRect(QRectF(0, 0, max_w, total_h))

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        line_h = 22.0
        font_normal = QFont("serif", 14)
        font_normal.setPixelSize(14)
        font_normal.setItalic(True)
        font_result = QFont("serif", 14)
        font_result.setPixelSize(14)
        for i, line in enumerate(self.lines):
            y = i * line_h
            if i < len(self.results):
                result = self.results[i]
                if result.error:
                    painter.setPen(QPen(QColor(200, 0, 0)))
                    painter.setFont(font_normal)
                    painter.drawText(QRectF(4, y, self.rect().width() - 8, line_h),
                                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                                     f"{line}  → Error: {result.error}")
                elif result.defined_name:
                    painter.setPen(QPen(QColor(0, 0, 0)))
                    painter.setFont(font_normal)
                    parts = line.split(":=") if ":=" in line else line.split(":", 1)
                    lhs = parts[0].strip()
                    painter.drawText(QRectF(4, y, self.rect().width() - 8, line_h),
                                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                                     f"{lhs} := {result.display_text}")
                else:
                    painter.setPen(QPen(QColor(0, 0, 0)))
                    painter.setFont(font_normal)
                    expr_text = line.split("->")[0].strip() if "->" in line else line
                    display = result.display_text
                    eq = "≤" if "<=" in line else ("≥" if ">=" in line else "=")
                    if result.is_bool:
                        label = "true" if result.value.value else "false"
                        color = QColor(0, 128, 0) if result.value.value else QColor(200, 0, 0)
                        painter.drawText(QRectF(4, y, self.rect().width() - 8, line_h),
                                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                                         f"{expr_text} = ")
                        painter.setPen(QPen(color))
                        bw = painter.fontMetrics().horizontalAdvance(f"{expr_text} = ")
                        painter.drawText(QRectF(4 + bw, y, self.rect().width(), line_h),
                                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                                         label)
                    else:
                        painter.drawText(QRectF(4, y, self.rect().width() - 8, line_h),
                                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                                         f"{expr_text} = {display}")
            else:
                painter.setPen(QPen(QColor(0, 0, 0)))
                painter.setFont(font_normal)
                painter.drawText(QRectF(4, y, self.rect().width() - 8, line_h),
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                                 line)
        if self.editing:
            painter.setPen(QPen(QColor(0, 120, 215), 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.rect().adjusted(-1, -1, 1, 1))
        self.paint_selection(painter)

    def set_lines(self, lines: list[str]):
        self.lines = lines
        self.region.data["lines"] = lines

    def add_line(self, text: str = ""):
        self.lines.append(text)
        self.region.data["lines"] = self.lines

    def start_edit(self):
        self.editing = True
        self.update()

    def end_edit(self):
        self.editing = False
        self.region.data["lines"] = self.lines
        self.update()
