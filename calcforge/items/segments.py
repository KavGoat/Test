"""Revu's Show Segment Values and Show Centroid, shared by the markups that
offer them (a Sketch to Scale shape, an area, a perimeter, a volume, a
polyline length).

Show Segment Values writes each side's length on that side — along it
(Align to Segment) or level (Align Horizontally) — in the markup's own
font, size and colour. Show Centroid marks the middle of what it encloses
with a small target, as Revu draws it.
"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QPainter, QPainterPath, QPen

#: Segment value alignments (Revu's two radio buttons).
ALONG = "segment"
LEVEL = "horizontal"


def _moments(path: Optional[QPainterPath]) -> tuple:
    """(area, x moment, y moment) of what *path* covers, each of its rings
    counted as covered (a path with no holes in it)."""
    area = mx = my = 0.0
    if path is None or path.isEmpty():
        return area, mx, my
    for polygon in path.toFillPolygons():
        points = list(polygon)
        twice = cx = cy = 0.0
        for a, b in zip(points, points[1:] + points[:1]):
            cross = a.x() * b.y() - b.x() * a.y()
            twice += cross
            cx += (a.x() + b.x()) * cross
            cy += (a.y() + b.y()) * cross
        if abs(twice) < 1e-12:
            continue
        ring = abs(twice) / 2.0
        area += ring
        mx += ring * cx / (3 * twice)
        my += ring * cy / (3 * twice)
    return area, mx, my


def path_area(path: Optional[QPainterPath]) -> float:
    """What a path with no holes in it covers, in square points."""
    return _moments(path)[0]


def centroid_of(outline: Optional[QPainterPath], fallback: list,
                holes: Optional[QPainterPath] = None) -> Optional[QPointF]:
    """The centre of what *outline* encloses, less its *holes*, weighted by
    area; the points' average when it encloses nothing."""
    area, mx, my = _moments(outline)
    if holes is not None and outline is not None and not holes.isEmpty():
        less, lx, ly = _moments(outline.intersected(holes))
        area, mx, my = area - less, mx - lx, my - ly
    if area > 1e-9:
        return QPointF(mx / area, my / area)
    if not fallback:
        return None
    return QPointF(sum(p.x() for p in fallback) / len(fallback),
                   sum(p.y() for p in fallback) / len(fallback))


def text_font(style):
    """The font segment values are written in: the markup's own."""
    from ..core.typography import set_size
    return set_size(style.font(), max(float(style.font_size or 8.0), 4.0))


def reach(style, texts: list) -> float:
    """How far past its outline the written values can reach."""
    if not texts:
        return 0.0
    metrics = QFontMetricsF(text_font(style))
    widest = max(metrics.horizontalAdvance(text) for text in texts)
    return widest / 2 + metrics.height() * 1.5


def paint_values(painter: QPainter, style, runs: list, texts: list, align: str,
                 inside: Optional[QPointF] = None) -> None:
    """Each run's text at its middle, just outside the shape (away from
    *inside*), along the run or level."""
    if not runs or not texts:
        return
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    font = text_font(style)
    painter.setFont(font)
    metrics = QFontMetricsF(font)
    ink = QColor(style.text_color or style.stroke or "#000000")
    ink.setAlphaF(max(0.0, min(1.0, style.opacity)))
    painter.setPen(QPen(ink))
    painter.setBrush(Qt.NoBrush)
    gap = max(float(style.width or 0.0), 0.5) / 2 + 2.0
    for (a, b), text in zip(runs, texts):
        if not text:
            continue
        dx, dy = b.x() - a.x(), b.y() - a.y()
        length = math.hypot(dx, dy)
        if length < 1e-6:
            continue
        middle = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
        normal = QPointF(-dy / length, dx / length)
        if inside is not None:
            towards = QPointF(inside.x() - middle.x(), inside.y() - middle.y())
            if normal.x() * towards.x() + normal.y() * towards.y() > 0:
                normal = QPointF(-normal.x(), -normal.y())     # outwards
        wide, high = metrics.horizontalAdvance(text), metrics.height()
        painter.save()
        if align == LEVEL:
            # level, its box pushed off the side far enough to clear it
            push = gap + abs(normal.x()) * wide / 2 + abs(normal.y()) * high / 2
            centre = middle + normal * push
            painter.drawText(QRectF(centre.x() - wide / 2, centre.y() - high / 2, wide, high),
                             Qt.AlignCenter, text)
        else:
            angle = math.degrees(math.atan2(dy, dx))
            if angle > 90 or angle <= -90:
                angle += 180                     # never upside down
            centre = middle + normal * (gap + high / 2)
            painter.translate(centre)
            painter.rotate(angle)
            painter.drawText(QRectF(-wide / 2, -high / 2, wide, high), Qt.AlignCenter, text)
        painter.restore()
    painter.restore()


def paint_centroid(painter: QPainter, style, point: Optional[QPointF]) -> None:
    """Revu's centroid: a small target — a ring with a cross through it."""
    if point is None:
        return
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    ink = QColor(style.stroke or style.text_color or "#000000")
    ink.setAlphaF(max(0.0, min(1.0, style.opacity)))
    pen = QPen(ink, max(min(float(style.width or 1.0), 1.5), 0.6))
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    radius = 3.5
    painter.drawEllipse(point, radius, radius)
    arm = radius * 1.8
    painter.drawLine(QPointF(point.x() - arm, point.y()), QPointF(point.x() + arm, point.y()))
    painter.drawLine(QPointF(point.x(), point.y() - arm), QPointF(point.x(), point.y() + arm))
    painter.restore()


def written_length(scale, quantity, digits: int) -> str:
    """A length as the scale writes one (its Precision, a fraction or not)."""
    from ..core.units import format_quantity
    if quantity is None:
        return ""
    if hasattr(scale, "format_length"):
        return scale.format_length(quantity, digits)
    return format_quantity(quantity, digits, "fixed")
