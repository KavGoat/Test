"""Plot region — 2D function/data plotting on the page."""
from __future__ import annotations

import math
from PySide6.QtCore import QRectF, QPointF, Qt
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QPainterPath

from .base import PageItem
from ..core.document import Region
from ..core.evaluator import EvalContext, evaluate, parse
from ..core.units import Quantity


class PlotItem(PageItem):
    """A 2D plot region."""

    COLORS = [
        QColor(0, 114, 189), QColor(217, 83, 25), QColor(237, 177, 32),
        QColor(126, 47, 142), QColor(119, 172, 48), QColor(77, 190, 238),
    ]

    def __init__(self, region: Region, parent=None):
        super().__init__(region, parent)
        self.expressions: list[str] = region.data.get("expressions", [])
        self.x_var = region.data.get("x_var", "x")
        self.x_min = region.data.get("x_min", 0.0)
        self.x_max = region.data.get("x_max", 10.0)
        self.y_min: float | None = region.data.get("y_min")
        self.y_max: float | None = region.data.get("y_max")
        self.x_label = region.data.get("x_label", "")
        self.y_label = region.data.get("y_label", "")
        self.title = region.data.get("title", "")
        self.grid = region.data.get("grid", True)
        self._curves: list[list[tuple[float, float]]] = []
        self._actual_y_min = 0.0
        self._actual_y_max = 1.0

    def evaluate(self, ctx: EvalContext):
        self._curves.clear()
        n_points = 200
        dx = (self.x_max - self.x_min) / n_points
        for expr_str in self.expressions:
            points = []
            for i in range(n_points + 1):
                xv = self.x_min + i * dx
                local_ctx = ctx.clone()
                local_ctx.define(self.x_var, Quantity(xv))
                try:
                    ast = parse(expr_str)
                    result = evaluate(ast, local_ctx)
                    yv = result.value
                    if math.isfinite(yv):
                        points.append((xv, yv))
                except Exception:
                    pass
            self._curves.append(points)
        all_y = [p[1] for curve in self._curves for p in curve]
        if all_y:
            self._actual_y_min = self.y_min if self.y_min is not None else min(all_y)
            self._actual_y_max = self.y_max if self.y_max is not None else max(all_y)
        if abs(self._actual_y_max - self._actual_y_min) < 1e-10:
            self._actual_y_min -= 1
            self._actual_y_max += 1

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        painter.fillRect(r, QColor(255, 255, 255))
        painter.setPen(QPen(QColor(200, 200, 200), 0.5))
        painter.drawRect(r)

        margin = 40
        plot_rect = QRectF(r.left() + margin, r.top() + 20,
                           r.width() - margin - 10, r.height() - margin - 20)

        if self.grid:
            painter.setPen(QPen(QColor(230, 230, 230), 0.5))
            for i in range(5):
                gy = plot_rect.top() + i * plot_rect.height() / 4
                painter.drawLine(QPointF(plot_rect.left(), gy), QPointF(plot_rect.right(), gy))
                gx = plot_rect.left() + i * plot_rect.width() / 4
                painter.drawLine(QPointF(gx, plot_rect.top()), QPointF(gx, plot_rect.bottom()))

        painter.setPen(QPen(QColor(0, 0, 0), 1.0))
        painter.drawLine(QPointF(plot_rect.left(), plot_rect.bottom()),
                         QPointF(plot_rect.right(), plot_rect.bottom()))
        painter.drawLine(QPointF(plot_rect.left(), plot_rect.top()),
                         QPointF(plot_rect.left(), plot_rect.bottom()))

        font = QFont("sans-serif", 8)
        font.setPixelSize(8)
        painter.setFont(font)
        for i in range(5):
            xv = self.x_min + i * (self.x_max - self.x_min) / 4
            px = plot_rect.left() + i * plot_rect.width() / 4
            painter.drawText(QPointF(px - 10, plot_rect.bottom() + 12), f"{xv:.4g}")
            yv = self._actual_y_max - i * (self._actual_y_max - self._actual_y_min) / 4
            py = plot_rect.top() + i * plot_rect.height() / 4
            painter.drawText(QPointF(plot_rect.left() - 35, py + 4), f"{yv:.4g}")

        x_range = self.x_max - self.x_min
        y_range = self._actual_y_max - self._actual_y_min
        for ci, curve in enumerate(self._curves):
            if not curve:
                continue
            color = self.COLORS[ci % len(self.COLORS)]
            painter.setPen(QPen(color, 1.5))
            path = QPainterPath()
            for i, (xv, yv) in enumerate(curve):
                px = plot_rect.left() + (xv - self.x_min) / x_range * plot_rect.width()
                py = plot_rect.bottom() - (yv - self._actual_y_min) / y_range * plot_rect.height()
                if i == 0:
                    path.moveTo(px, py)
                else:
                    path.lineTo(px, py)
            painter.drawPath(path)

        if self.title:
            title_font = QFont("sans-serif", 10)
            title_font.setPixelSize(10)
            title_font.setBold(True)
            painter.setFont(title_font)
            painter.setPen(QPen(QColor(0, 0, 0)))
            painter.drawText(QRectF(r.left(), r.top(), r.width(), 18),
                             Qt.AlignmentFlag.AlignCenter, self.title)
        self.paint_selection(painter)

    def save_data(self):
        self.region.data.update({
            "expressions": self.expressions,
            "x_var": self.x_var,
            "x_min": self.x_min,
            "x_max": self.x_max,
            "y_min": self.y_min,
            "y_max": self.y_max,
            "x_label": self.x_label,
            "y_label": self.y_label,
            "title": self.title,
            "grid": self.grid,
        })
