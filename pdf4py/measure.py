"""Measurement tools: length, area, angle with per-page scale calibration."""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class PageScale:
    points_per_unit: float = 72.0
    unit: str = "in"

    def convert(self, points: float) -> float:
        if self.points_per_unit < 1e-9:
            return 0.0
        return points / self.points_per_unit

    def format_length(self, points: float) -> str:
        return f"{self.convert(points):.2f} {self.unit}"

    def format_area(self, sq_points: float) -> str:
        if self.points_per_unit < 1e-9:
            return "0.00"
        sq_units = sq_points / (self.points_per_unit ** 2)
        return f"{sq_units:.2f} {self.unit}²"


def length(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])


def polyline_length(points: list[tuple[float, float]]) -> float:
    total = 0.0
    for i in range(1, len(points)):
        total += length(points[i - 1], points[i])
    return total


def polygon_area(points: list[tuple[float, float]]) -> float:
    n = len(points)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += points[i][0] * points[j][1]
        area -= points[j][0] * points[i][1]
    return abs(area) / 2.0


def polygon_perimeter(points: list[tuple[float, float]]) -> float:
    if len(points) < 2:
        return 0.0
    total = polyline_length(points)
    if len(points) > 2:
        total += length(points[-1], points[0])
    return total


def angle_between(p1: tuple[float, float], vertex: tuple[float, float],
                  p2: tuple[float, float]) -> float:
    dx1, dy1 = p1[0] - vertex[0], p1[1] - vertex[1]
    dx2, dy2 = p2[0] - vertex[0], p2[1] - vertex[1]
    dot = dx1 * dx2 + dy1 * dy2
    mag1 = math.hypot(dx1, dy1)
    mag2 = math.hypot(dx2, dy2)
    if mag1 < 1e-9 or mag2 < 1e-9:
        return 0.0
    cos_a = max(-1.0, min(1.0, dot / (mag1 * mag2)))
    return math.degrees(math.acos(cos_a))


class MeasureEngine:

    def __init__(self) -> None:
        self._scales: dict[int, PageScale] = {}

    def scale_for(self, page_index: int) -> PageScale:
        return self._scales.get(page_index, PageScale())

    def set_scale(self, page_index: int, scale: PageScale) -> None:
        self._scales[page_index] = scale

    def calibrate(self, page_index: int, p1: tuple[float, float],
                  p2: tuple[float, float], real_length: float,
                  unit: str = "in") -> PageScale:
        measured = length(p1, p2)
        if measured < 1e-9 or real_length < 1e-9:
            return self.scale_for(page_index)
        ppu = measured / real_length
        scale = PageScale(points_per_unit=ppu, unit=unit)
        self._scales[page_index] = scale
        return scale

    def format_length(self, page_index: int, points: float) -> str:
        return self.scale_for(page_index).format_length(points)

    def format_area(self, page_index: int, sq_points: float) -> str:
        return self.scale_for(page_index).format_area(sq_points)
