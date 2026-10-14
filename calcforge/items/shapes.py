"""Drawing shapes — lines, rectangles, ellipses, arrows, etc."""
from __future__ import annotations

import math
from PySide6.QtCore import QRectF, QPointF, QLineF, Qt
from PySide6.QtGui import (
    QPainter, QPen, QColor, QBrush, QPainterPath, QPolygonF,
)

from .base import PageItem
from ..core.document import Region


class LineItem(PageItem):
    def __init__(self, region: Region, parent=None):
        super().__init__(region, parent)
        self.line_color = QColor(region.data.get("color", "#000000"))
        self.line_width = region.data.get("line_width", 1.5)
        self.dash = region.data.get("dash", False)

    def paint(self, painter: QPainter, option, widget=None):
        pen = QPen(self.line_color, self.line_width)
        if self.dash:
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        r = self.rect()
        painter.drawLine(QPointF(r.left(), r.top()), QPointF(r.right(), r.bottom()))
        self.paint_selection(painter)


class ArrowItem(LineItem):
    def paint(self, painter: QPainter, option, widget=None):
        super().paint(painter, option, widget)
        r = self.rect()
        end = QPointF(r.right(), r.bottom())
        start = QPointF(r.left(), r.top())
        angle = math.atan2(end.y() - start.y(), end.x() - start.x())
        arrow_size = 10
        p1 = QPointF(
            end.x() - arrow_size * math.cos(angle - math.pi / 6),
            end.y() - arrow_size * math.sin(angle - math.pi / 6),
        )
        p2 = QPointF(
            end.x() - arrow_size * math.cos(angle + math.pi / 6),
            end.y() - arrow_size * math.sin(angle + math.pi / 6),
        )
        painter.setBrush(QBrush(self.line_color))
        painter.drawPolygon(QPolygonF([end, p1, p2]))


class RectangleItem(PageItem):
    def __init__(self, region: Region, parent=None):
        super().__init__(region, parent)
        self.line_color = QColor(region.data.get("color", "#000000"))
        self.fill_color = QColor(region.data.get("fill_color", "#ffffff"))
        self.fill_color.setAlpha(region.data.get("fill_alpha", 0))
        self.line_width = region.data.get("line_width", 1.5)
        self.corner_radius = region.data.get("corner_radius", 0)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setPen(QPen(self.line_color, self.line_width))
        painter.setBrush(QBrush(self.fill_color) if self.fill_color.alpha() > 0 else Qt.BrushStyle.NoBrush)
        if self.corner_radius > 0:
            painter.drawRoundedRect(self.rect(), self.corner_radius, self.corner_radius)
        else:
            painter.drawRect(self.rect())
        self.paint_selection(painter)


class EllipseItem(PageItem):
    def __init__(self, region: Region, parent=None):
        super().__init__(region, parent)
        self.line_color = QColor(region.data.get("color", "#000000"))
        self.fill_color = QColor(region.data.get("fill_color", "#ffffff"))
        self.fill_color.setAlpha(region.data.get("fill_alpha", 0))
        self.line_width = region.data.get("line_width", 1.5)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setPen(QPen(self.line_color, self.line_width))
        painter.setBrush(QBrush(self.fill_color) if self.fill_color.alpha() > 0 else Qt.BrushStyle.NoBrush)
        painter.drawEllipse(self.rect())
        self.paint_selection(painter)


class PolygonItem(PageItem):
    def __init__(self, region: Region, parent=None):
        super().__init__(region, parent)
        self.points: list[QPointF] = []
        for pt in region.data.get("points", []):
            self.points.append(QPointF(pt[0], pt[1]))
        self.line_color = QColor(region.data.get("color", "#000000"))
        self.fill_color = QColor(region.data.get("fill_color", "#ffffff"))
        self.fill_color.setAlpha(region.data.get("fill_alpha", 0))
        self.line_width = region.data.get("line_width", 1.5)
        self.closed = region.data.get("closed", True)

    def paint(self, painter: QPainter, option, widget=None):
        if not self.points:
            return
        painter.setPen(QPen(self.line_color, self.line_width))
        painter.setBrush(QBrush(self.fill_color) if self.fill_color.alpha() > 0 else Qt.BrushStyle.NoBrush)
        if self.closed:
            painter.drawPolygon(QPolygonF(self.points))
        else:
            for i in range(len(self.points) - 1):
                painter.drawLine(self.points[i], self.points[i + 1])
        self.paint_selection(painter)


class CloudItem(PageItem):
    """Revision cloud annotation."""
    def __init__(self, region: Region, parent=None):
        super().__init__(region, parent)
        self.line_color = QColor(region.data.get("color", "#ff0000"))
        self.line_width = region.data.get("line_width", 1.5)
        self.arc_size = region.data.get("arc_size", 15)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setPen(QPen(self.line_color, self.line_width))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        r = self.rect()
        path = QPainterPath()
        arc = self.arc_size
        x, y = r.left(), r.top()
        while x < r.right() - arc:
            path.moveTo(x, y)
            path.arcTo(QRectF(x, y - arc / 2, arc, arc), 180, -180)
            x += arc
        y = r.top()
        x = r.right()
        while y < r.bottom() - arc:
            path.moveTo(x, y)
            path.arcTo(QRectF(x - arc / 2, y, arc, arc), 90, -180)
            y += arc
        painter.drawPath(path)
        self.paint_selection(painter)
