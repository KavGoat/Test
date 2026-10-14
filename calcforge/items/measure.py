"""Measurement annotations — length, area, angle, count."""
from __future__ import annotations

import math
from PySide6.QtCore import QRectF, QPointF, QLineF, Qt
from PySide6.QtGui import QPainter, QPen, QColor, QFont

from .base import PageItem
from ..core.document import Region
from ..core.typography import sans_family


class MeasureItem(PageItem):
    """A measurement annotation on the page."""

    def __init__(self, region: Region, parent=None):
        super().__init__(region, parent)
        self.measure_type = region.data.get("measure_type", "length")
        self.points: list[QPointF] = []
        for pt in region.data.get("points", []):
            self.points.append(QPointF(pt[0], pt[1]))
        self.scale = region.data.get("scale", 1.0)
        self.unit = region.data.get("unit", "m")
        self.precision = region.data.get("precision", 2)
        self.subject = region.data.get("subject", "")
        self.value: float = 0.0
        self._compute()

    def _compute(self):
        if self.measure_type == "length" and len(self.points) >= 2:
            total = 0.0
            for i in range(len(self.points) - 1):
                dx = self.points[i + 1].x() - self.points[i].x()
                dy = self.points[i + 1].y() - self.points[i].y()
                total += math.sqrt(dx * dx + dy * dy)
            self.value = total * self.scale
        elif self.measure_type == "area" and len(self.points) >= 3:
            area = 0.0
            n = len(self.points)
            for i in range(n):
                j = (i + 1) % n
                area += self.points[i].x() * self.points[j].y()
                area -= self.points[j].x() * self.points[i].y()
            self.value = abs(area) / 2.0 * self.scale * self.scale
        elif self.measure_type == "angle" and len(self.points) >= 3:
            p0, p1, p2 = self.points[0], self.points[1], self.points[2]
            a1 = math.atan2(p0.y() - p1.y(), p0.x() - p1.x())
            a2 = math.atan2(p2.y() - p1.y(), p2.x() - p1.x())
            self.value = abs(math.degrees(a2 - a1))
        elif self.measure_type == "count":
            self.value = len(self.points)

    @property
    def display_value(self) -> str:
        if self.measure_type == "angle":
            return f"{self.value:.{self.precision}f}°"
        if self.measure_type == "count":
            return str(int(self.value))
        return f"{self.value:.{self.precision}f} {self.unit}"

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(0, 150, 0)
        painter.setPen(QPen(color, 1.5))
        if len(self.points) >= 2:
            for i in range(len(self.points) - 1):
                painter.drawLine(self.points[i], self.points[i + 1])
            if self.measure_type == "area" and len(self.points) >= 3:
                painter.drawLine(self.points[-1], self.points[0])

        for pt in self.points:
            painter.setBrush(color)
            painter.drawEllipse(pt, 3, 3)

        font = QFont(sans_family(), 9)
        font.setPixelSize(9)
        painter.setFont(font)
        painter.setPen(QPen(color))
        if len(self.points) >= 2:
            mid = QPointF(
                (self.points[0].x() + self.points[-1].x()) / 2,
                (self.points[0].y() + self.points[-1].y()) / 2 - 8,
            )
            painter.drawText(mid, self.display_value)
        self.paint_selection(painter)
