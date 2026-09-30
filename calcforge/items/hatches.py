"""The hatch library: named patterns drawn as real linework.

Most patterns are families of parallel lines, the way AutoCAD's and
Bluebeam's .pat patterns are written: each family has an angle, an origin, a
shift along the line and a spacing across it between one line and the next,
and an optional dash pattern. A few that are not straight lines — batt
insulation, timber grain, gravel, sand, concrete — are drawn by hand here.

Every size is in points at a hatch scale of one, and scales with the style's
hatch scale. Lines are drawn clipped to the shape, so they stay sharp at any
zoom and are written into a PDF as strokes.
"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QLineF, QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

#: The weight of hatch lines, in points.
HATCH_WIDTH = 0.5
#: Past this many pieces a hatch is drawn as an even tint instead: lines that
#: close merge into one anyway, and a repaint must not stall on them.
MOST_PIECES = 20000


def _family(angle, x0=0.0, y0=0.0, dx=0.0, dy=8.0, dashes=()):
    return (float(angle), float(x0), float(y0), float(dx), float(dy),
            tuple(float(d) for d in dashes))


# name -> (families, special)
LIBRARY: dict[str, tuple[tuple, str]] = {
    "": ((), ""),
    "solid": ((), ""),
    # -- the plain line patterns ------------------------------------------
    "horizontal": ((_family(0),), ""),
    "vertical": ((_family(90),), ""),
    "cross": ((_family(0), _family(90)), ""),
    "up": ((_family(45, dy=8 / math.sqrt(2)),), ""),
    "down": ((_family(135, dy=8 / math.sqrt(2)),), ""),
    "diagonal cross": ((_family(45, dy=8 / math.sqrt(2)),
                        _family(135, dy=8 / math.sqrt(2))), ""),
    "dots": ((), "dots"),
    "dense": ((), "dense dots"),
    # -- materials ---------------------------------------------------------
    "steel": ((_family(45, dy=6), _family(45, x0=0, y0=1.6, dy=6)), ""),
    "masonry": ((_family(45, dy=4),), ""),
    "aluminium": ((_family(45, dy=6), _family(45, x0=0, y0=1.5, dy=6,
                                              dashes=(3, -2))), ""),
    "bronze": ((_family(45, dy=8), _family(45, x0=0, y0=4, dy=8, dashes=(6, -2, 0, -2))), ""),
    "lead": ((_family(45, dy=6, dashes=(4, -2)), _family(135, dy=6, dashes=(4, -2))), ""),
    "plastic": ((_family(45, dy=8), _family(45, y0=1.5, dy=8), _family(45, y0=4.5, dy=8,
                                                                   dashes=(3, -3))), ""),
    "rubber": ((_family(45, dy=6, dashes=(8, -3)),), ""),
    "glass": ((_family(45, dy=12, dashes=(4, -12)), _family(45, y0=1.5, dy=12,
                                                            dashes=(2, -14))), ""),
    "brick": ((_family(0, dy=8), _family(90, dx=8, dy=8, dashes=(8, -8))), ""),
    "block": ((_family(0, dy=12), _family(90, dx=12, dy=12, dashes=(12, -12))), ""),
    "stone": ((_family(0, dy=10), _family(90, dx=10, dy=14, dashes=(10, -10)),
               _family(45, y0=3, dy=14, dashes=(3, -17))), ""),
    "tiles": ((_family(0, dy=10), _family(90, dy=10)), ""),
    "earth": ((_family(0, dx=8, dy=8, dashes=(8, -8)),
               _family(0, y0=3, dx=8, dy=8, dashes=(8, -8)),
               _family(0, y0=6, dx=8, dy=8, dashes=(8, -8)),
               _family(90, x0=1, y0=7, dx=8, dy=8, dashes=(8, -8)),
               _family(90, x0=4, y0=7, dx=8, dy=8, dashes=(8, -8)),
               _family(90, x0=7, y0=7, dx=8, dy=8, dashes=(8, -8))), ""),
    "hardcore": ((_family(45, dy=10, dashes=(6, -4)), _family(135, dy=10, dashes=(6, -4)),
                  _family(0, dy=10, dashes=(2, -8))), ""),
    "honeycomb": ((_family(0, dx=6, dy=3.464, dashes=(4, -8)),
                   _family(120, dx=6, dy=3.464, dashes=(4, -8)),
                   _family(60, x0=4, dx=6, dy=3.464, dashes=(4, -8))), ""),
    "grating": ((_family(0, dy=3), _family(90, dy=24)), ""),
    "chequer plate": ((_family(45, dy=12, dashes=(4, -12)),
                       _family(135, x0=6, dy=12, dashes=(4, -12))), ""),
    "concrete": ((), "concrete"),
    "gravel": ((), "gravel"),
    "sand": ((), "sand"),
    "batt insulation": ((), "batt"),
    "rigid insulation": ((_family(45, dy=6), _family(135, dy=6), _family(0, dy=24)), ""),
    "timber": ((), "grain"),
    "timber end": ((), "end grain"),
}

#: Names offered in the lists, in order: plain patterns first, then materials.
NAMES = [name for name in LIBRARY if name not in ("", "solid")]
_PLAIN = {"horizontal", "vertical", "cross", "up", "down", "diagonal cross", "dots",
          "dense"}
MATERIALS = [name for name in NAMES if name not in _PLAIN]

# Qt's own brush patterns, which older files and Bluebeam tool sets name
# through hatch_named, as the library pattern that looks like each.
_FROM_QT = {
    Qt.HorPattern: "horizontal", Qt.VerPattern: "vertical", Qt.CrossPattern: "cross",
    Qt.BDiagPattern: "up", Qt.FDiagPattern: "down",
    Qt.DiagCrossPattern: "diagonal cross", Qt.Dense5Pattern: "dots",
    Qt.Dense3Pattern: "dense",
}


def key_for(name: str) -> str:
    """The library pattern *name* means: its own entry, or Bluebeam's word."""
    if not name:
        return ""
    lowered = name.strip().lower()
    if lowered in LIBRARY:
        return lowered
    words = set(_words(name))
    # A material named in so many words — "Hatch-Concrete", "Steel section".
    for key in MATERIALS:
        if set(key.split()) <= words:
            return key
    from .base import hatch_named
    return _FROM_QT.get(hatch_named(name), "")


def _words(name: str) -> list[str]:
    """"Hatch-DiagonalUp" as ["hatch", "diagonal", "up"]."""
    spaced = []
    for index, character in enumerate(name or ""):
        if not character.isalpha():
            spaced.append(" ")
            continue
        if index and character.isupper() and name[index - 1].islower():
            spaced.append(" ")
        spaced.append(character)
    return "".join(spaced).lower().split()


def is_hatch(name: str) -> bool:
    return key_for(name) not in ("", "solid")


def paint(painter: QPainter, region: QPainterPath, name: str, scale: float,
          ink: QColor) -> None:
    """Draw pattern *name* over *region* in *ink*, clipped to it."""
    key = key_for(name)
    families, special = LIBRARY.get(key, ((), ""))
    if region is None or region.isEmpty() or (not families and not special):
        return
    box = region.boundingRect()
    scale = max(float(scale or 1.0), 1e-12)
    painter.save()
    painter.setClipPath(region, Qt.IntersectClip)
    painter.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(ink, HATCH_WIDTH)
    pen.setCapStyle(Qt.FlatCap)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    if special:
        drawn = _SPECIALS[special](painter, box, scale, ink)
    else:
        drawn = _paint_families(painter, box, families, scale)
    if not drawn:
        # Too dense to draw a line at a time: the even tint it would make.
        tint = QColor(ink)
        tint.setAlphaF(ink.alphaF() * min(1.0, 0.25 + 0.5 / scale))
        painter.fillPath(region, tint)
    painter.restore()


#: The most tiles drawn one by one before a tiled hatch becomes a tint.
MOST_TILES = 6000

_TILE_PATHS: dict = {}


def _tile_path(tile: dict):
    """A tile's lines as one path, and the widest line in it; cached."""
    key = id(tile.get("strokes"))
    found = _TILE_PATHS.get(key)
    if found is not None and found[2] is tile.get("strokes"):
        return found[0], found[1]
    from PySide6.QtGui import QPainterPath
    path = QPainterPath()
    widest = 0.0
    for stroke in tile.get("strokes") or []:
        widest = max(widest, float(stroke.get("width", 0.0) or 0.0))
        for command in stroke.get("path") or []:
            op, values = command[0], [float(v) for v in command[1:]]
            if op == "m" and len(values) >= 2:
                path.moveTo(values[0], values[1])
            elif op == "l" and len(values) >= 2:
                path.lineTo(values[0], values[1])
            elif op == "c" and len(values) >= 6:
                path.cubicTo(values[0], values[1], values[2], values[3],
                             values[4], values[5])
            elif op == "h":
                path.closeSubpath()
    if len(_TILE_PATHS) > 64:
        _TILE_PATHS.clear()
    _TILE_PATHS[key] = (path, widest, tile.get("strokes"))
    return path, widest


def paint_tile(painter: QPainter, region: QPainterPath, tile: dict, scale: float,
               ink: QColor) -> None:
    """Fill *region* with copies of *tile*'s linework, *scale* times its size."""
    if region is None or region.isEmpty():
        return
    step_x = float(tile.get("step_x", 0) or 0)
    step_y = float(tile.get("step_y", 0) or 0)
    if step_x <= 0 or step_y <= 0:
        return
    scale = max(float(scale or 1.0), 1e-12)
    path, widest = _tile_path(tile)
    box = region.boundingRect()
    across, down = step_x * scale, step_y * scale
    first_x = math.floor(box.left() / across)
    first_y = math.floor(box.top() / down)
    last_x = math.ceil(box.right() / across)
    last_y = math.ceil(box.bottom() / down)
    painter.save()
    painter.setClipPath(region, Qt.IntersectClip)
    painter.setRenderHint(QPainter.Antialiasing, True)
    if (last_x - first_x) * (last_y - first_y) > MOST_TILES:
        tint = QColor(ink)
        tint.setAlphaF(ink.alphaF() * 0.35)
        painter.fillPath(region, tint)
        painter.restore()
        return
    pen = QPen(ink, max(widest, 0.1))
    pen.setCapStyle(Qt.FlatCap)
    pen.setCosmetic(False)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    origin_x = float(tile.get("x", 0.0) or 0.0)
    origin_y = float(tile.get("y", 0.0) or 0.0)
    for column in range(first_x, last_x + 1):
        for row in range(first_y, last_y + 1):
            painter.save()
            painter.translate(column * across, row * down)
            painter.scale(scale, scale)
            painter.translate(-origin_x, -origin_y)
            painter.drawPath(path)
            painter.restore()
    painter.restore()


def _paint_families(painter, box, families, scale) -> bool:
    corners = [box.topLeft(), box.topRight(), box.bottomLeft(), box.bottomRight()]
    lines: list[QLineF] = []
    budget = MOST_PIECES
    for angle, x0, y0, dx, dy, dashes in families:
        radians = math.radians(angle)
        # Angles turn anticlockwise on the page, which is y-down.
        u = QPointF(math.cos(radians), -math.sin(radians))
        # To the left of the line, as .pat patterns measure it (y up).
        n = QPointF(u.y(), -u.x())
        spacing = dy * scale
        if spacing <= 1e-9:
            continue
        origin = QPointF(x0 * scale, -y0 * scale)
        shift = dx * scale

        def dot(a, b):
            return a.x() * b.x() + a.y() * b.y()

        across = [dot(corner, n) for corner in corners]
        along = [dot(corner, u) for corner in corners]
        base = dot(origin, n)
        first = math.floor((min(across) - base) / spacing)
        last = math.ceil((max(across) - base) / spacing)
        if (last - first) > budget:
            return False
        low, high = min(along), max(along)
        period = sum(abs(d) for d in dashes) * scale
        for k in range(first, last + 1):
            start = origin + n * (k * spacing) + u * (k * shift)
            offset = dot(start, u)
            foot = start - u * offset             # the point on this line at t = 0
            if not dashes or period <= 1e-9:
                lines.append(QLineF(foot + u * low, foot + u * high))
                continue
            if (high - low) / period * len(dashes) > budget:
                return False
            t = offset + math.floor((low - offset) / period) * period
            while t < high:
                for dash in dashes:
                    length = abs(dash) * scale
                    if dash > 0:
                        lines.append(QLineF(foot + u * t, foot + u * (t + length)))
                    elif dash == 0:
                        tip = foot + u * t
                        lines.append(QLineF(tip, tip + u * (HATCH_WIDTH * 0.8)))
                    t += length
            if len(lines) > budget:
                return False
    if lines:
        painter.drawLines(lines)
    return True


def _cells(box, step):
    """Every (column, row, x, y) of a grid of *step* covering *box*."""
    first_x, first_y = math.floor(box.left() / step), math.floor(box.top() / step)
    last_x, last_y = math.ceil(box.right() / step), math.ceil(box.bottom() / step)
    if (last_x - first_x) * (last_y - first_y) > MOST_PIECES:
        return None
    return [(cx, cy, cx * step, cy * step)
            for cy in range(first_y, last_y + 1) for cx in range(first_x, last_x + 1)]


def _noise(cx: int, cy: int, salt: int) -> float:
    """A repeatable number in [0, 1) for one cell, so the pattern never flickers."""
    value = (cx * 73856093) ^ (cy * 19349663) ^ (salt * 83492791)
    value = (value ^ (value >> 13)) * 1274126177
    return ((value ^ (value >> 16)) & 0xFFFF) / 65536.0


def _dots(painter, box, scale, ink, step, radius, stagger=False) -> bool:
    cells = _cells(box, step * scale)
    if cells is None:
        return False
    painter.setPen(Qt.NoPen)
    painter.setBrush(ink)
    for cx, cy, x, y in cells:
        shift = step * scale / 2 if stagger and cy % 2 else 0.0
        painter.drawEllipse(QPointF(x + shift, y), radius, radius)
    return True


def _scatter(painter, box, scale, ink, step, shapes) -> bool:
    cells = _cells(box, step * scale)
    if cells is None:
        return False
    for cx, cy, x, y in cells:
        for index, (kind, size) in enumerate(shapes):
            px = x + _noise(cx, cy, 2 * index) * step * scale
            py = y + _noise(cx, cy, 2 * index + 1) * step * scale
            s = size * scale
            if kind == "dot":
                painter.setPen(Qt.NoPen)
                painter.setBrush(ink)
                painter.drawEllipse(QPointF(px, py), s, s)
                painter.setBrush(Qt.NoBrush)
            elif kind == "ring":
                painter.setPen(QPen(ink, HATCH_WIDTH))
                painter.drawEllipse(QPointF(px, py), s, s * 0.8)
            elif kind == "triangle":
                painter.setPen(QPen(ink, HATCH_WIDTH))
                turn = _noise(cx, cy, 9 + index) * math.tau
                points = [QPointF(px + math.cos(turn + a) * s, py + math.sin(turn + a) * s)
                          for a in (0, 2.1, 4.2)]
                path = QPainterPath(points[0])
                for point in points[1:]:
                    path.lineTo(point)
                path.closeSubpath()
                painter.drawPath(path)
    return True


def _waves(painter, box, scale, ink, spacing, length, amplitude) -> bool:
    step = spacing * scale
    rows = math.ceil(box.height() / step) + 2
    wave = length * scale
    if rows * math.ceil(box.width() / wave + 2) > MOST_PIECES:
        return False
    path = QPainterPath()
    top = math.floor(box.top() / step) * step
    for row in range(rows):
        y = top + row * step
        x = math.floor(box.left() / wave) * wave - wave
        path.moveTo(x, y)
        while x < box.right() + wave:
            path.cubicTo(x + wave * 0.25, y - amplitude * scale,
                         x + wave * 0.75, y + amplitude * scale, x + wave, y)
            x += wave
    painter.drawPath(path)
    return True


def _batt(painter, box, scale, ink) -> bool:
    # The looping line of batt insulation: arcs back and forth across a band.
    height = 12 * scale
    loop = 6 * scale
    bands = math.ceil(box.height() / height) + 1
    if bands * math.ceil(box.width() / loop + 2) > MOST_PIECES:
        return False
    path = QPainterPath()
    top = math.floor(box.top() / height) * height
    for band in range(bands):
        y0 = top + band * height
        x = math.floor(box.left() / loop) * loop - loop
        path.moveTo(x, y0 + height)
        up = True
        while x < box.right() + loop:
            y = y0 if up else y0 + height
            path.cubicTo(x - loop * 0.6, y, x + loop * 1.6, y, x + loop, y0 + height
                         if up else y0)
            x += loop
            up = not up
    painter.drawPath(path)
    return True


def _end_grain(painter, box, scale, ink) -> bool:
    # Growth rings round the middle of the shape.
    middle = box.center()
    step = 4 * scale
    reach = math.hypot(box.width(), box.height()) / 2
    if reach / step > MOST_PIECES:
        return False
    radius = step
    while radius < reach:
        painter.drawEllipse(middle, radius, radius * 0.8)
        radius += step
    return True


_SPECIALS = {
    "dots": lambda p, b, s, i: _dots(p, b, s, i, 8, 0.9),
    "dense dots": lambda p, b, s, i: _dots(p, b, s, i, 4, 0.7, stagger=True),
    "sand": lambda p, b, s, i: _scatter(p, b, s, i, 4, [("dot", 0.35), ("dot", 0.3)]),
    "gravel": lambda p, b, s, i: _scatter(p, b, s, i, 10, [("ring", 1.6), ("ring", 1.1),
                                                            ("dot", 0.4)]),
    "concrete": lambda p, b, s, i: _scatter(p, b, s, i, 12, [("triangle", 1.8),
                                                              ("dot", 0.45), ("dot", 0.35),
                                                              ("dot", 0.3)]),
    "grain": lambda p, b, s, i: _waves(p, b, s, i, 5, 60, 1.8),
    "batt": _batt,
    "end grain": _end_grain,
}


def sample_icon(name: str, colour: str, width: int = 76, height: int = 22):
    """A swatch of the pattern, for the pattern lists."""
    from PySide6.QtGui import QIcon, QPixmap
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    ink = QColor(colour or "#748096")
    painter.setPen(QPen(ink.darker(135), 1))
    painter.drawRect(3, 3, width - 7, height - 7)
    region = QPainterPath()
    region.addRect(3, 3, width - 7, height - 7)
    paint(painter, region, name, 0.8, ink)
    painter.end()
    return QIcon(pixmap)
