"""Snapping engine for markup placement and editing.

Supports grid snapping and snapping to existing markup corners, centers,
and midpoints — the same approach MarkForge uses to guide the cursor onto
nearby geometry with visual feedback.
"""
from __future__ import annotations

from dataclasses import dataclass

GRID_SIZE = 10.0
SNAP_DISTANCE = 8.0


@dataclass
class SnapResult:
    x: float
    y: float
    snapped_x: bool = False
    snapped_y: bool = False
    label: str = ""


class SnapEngine:

    def __init__(self) -> None:
        self.grid_enabled = False
        self.markup_snap_enabled = True
        self.grid_size = GRID_SIZE
        self._targets: list[tuple[float, float, str]] = []

    def set_targets(self, targets: list[tuple[float, float, str]]) -> None:
        self._targets = list(targets)

    def snap(self, x: float, y: float, zoom: float = 1.0) -> SnapResult:
        threshold = SNAP_DISTANCE / max(zoom, 0.1)
        best_x, best_y = x, y
        snapped_x = snapped_y = False
        label = ""
        min_dx = threshold
        min_dy = threshold

        if self.grid_enabled:
            gx = round(x / self.grid_size) * self.grid_size
            gy = round(y / self.grid_size) * self.grid_size
            if abs(x - gx) < min_dx:
                best_x, min_dx, snapped_x = gx, abs(x - gx), True
                label = "grid"
            if abs(y - gy) < min_dy:
                best_y, min_dy, snapped_y = gy, abs(y - gy), True
                label = "grid"

        if self.markup_snap_enabled:
            for tx, ty, tl in self._targets:
                dx = abs(x - tx)
                dy = abs(y - ty)
                if dx < min_dx:
                    best_x, min_dx, snapped_x = tx, dx, True
                    label = tl
                if dy < min_dy:
                    best_y, min_dy, snapped_y = ty, dy, True
                    label = tl

        return SnapResult(best_x, best_y, snapped_x, snapped_y, label)

    def collect_targets(self, markups, exclude_xrefs=None) -> None:
        exclude = set(exclude_xrefs or [])
        targets: list[tuple[float, float, str]] = []
        for m in markups:
            if m.xref in exclude:
                continue
            cx = (m.x0 + m.x1) / 2
            cy = (m.y0 + m.y1) / 2
            targets.extend([
                (m.x0, m.y0, "corner"), (m.x1, m.y0, "corner"),
                (m.x0, m.y1, "corner"), (m.x1, m.y1, "corner"),
                (cx, cy, "center"),
                (cx, m.y0, "midpoint"), (cx, m.y1, "midpoint"),
                (m.x0, cy, "midpoint"), (m.x1, cy, "midpoint"),
            ])
        self._targets = targets
