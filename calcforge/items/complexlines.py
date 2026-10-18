"""Revu's complex line styles: lines that are more than dashes.

Fenceline Circle and Fenceline Square (a line broken by small open circles
or squares), Gas and Hot Water (a line broken by its label), Zig Zag,
Insulation (the looping line of batt insulation), Double (two parallel
lines), Tracks (two rails and their ties) and Road (two kerbs and a dashed
centre line) — the user's Revu 21 line-style list, 2026-10-18.

Each is drawn along whatever path a markup strokes, at the markup's own
line width: everything about it — its spacing, its symbols, how wide it is —
grows with the width, so a heavy line is a bigger version of a light one,
and a line thinner than a point is drawn at a point line's size with a thin
pen.
The repeats are spread evenly round a closed shape so they meet where it
starts, and centred on an open one. It is drawn with the painter, so it is
the same on the canvas, in a print, in a thumbnail and in the appearance
stream written into the PDF; the annotation's own border stays solid.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QFont, QPainter, QPainterPath, QPen, QTransform

#: The complex styles, in Revu's order.
COMPLEX = ("fenceline circle", "fenceline square", "gas", "hot water", "zig zag",
           "insulation", "double", "tracks", "road")

#: What a labelled line says.
LABELS = {"gas": "GAS", "hot water": "HW"}

#: How far either side of its path a complex line reaches, in sizes (see
#: :func:`unit`), past half the pen. Every style here keeps inside it.
REACH = 3.0


def is_complex(name: str) -> bool:
    return (name or "") in COMPLEX


def unit(width: float) -> float:
    """The size one complex line is built in: half as much again as its
    width, but never under a point and a half, so a hairline Double is still
    two lines and a 1 pt Gas line's label can be read."""
    return 1.5 * max(float(width or 0.0), 1.0)


def reach(style) -> float:
    """How far past its path *style*'s line is drawn, in points — 0 for a
    plain or dashed one, whose pen alone says that."""
    if not is_complex(getattr(style, "line_style", "")):
        return 0.0
    width = float(getattr(style, "width", 0.0) or 0.0)
    return REACH * unit(width) + width


# -- walking a path -------------------------------------------------------------

class _Walk:
    """One flattened subpath, measured along its length."""

    def __init__(self, points, closed: bool):
        kept = []
        for point in points:
            if not kept or _far(kept[-1], point):
                kept.append(QPointF(point))
        if closed and len(kept) > 2 and not _far(kept[0], kept[-1]):
            kept.pop()
        self.closed = closed and len(kept) > 2
        if self.closed:
            kept.append(QPointF(kept[0]))
        self.points = kept
        self.at_length = [0.0]
        for a, b in zip(kept, kept[1:]):
            self.at_length.append(self.at_length[-1] + math.hypot(b.x() - a.x(), b.y() - a.y()))
        self.length = self.at_length[-1]

    def _segment(self, s: float) -> int:
        lo, hi = 0, len(self.at_length) - 2
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.at_length[mid] <= s:
                lo = mid
            else:
                hi = mid - 1
        return lo

    def _fold(self, s: float) -> float:
        if self.closed and self.length > 0:
            return s % self.length
        return min(max(s, 0.0), self.length)

    def at(self, s: float):
        """The point *s* along, and the way the path goes there (a unit vector)."""
        s = self._fold(s)
        index = self._segment(s)
        a, b = self.points[index], self.points[index + 1]
        span = self.at_length[index + 1] - self.at_length[index]
        t = (s - self.at_length[index]) / span if span > 0 else 0.0
        dx, dy = b.x() - a.x(), b.y() - a.y()
        size = math.hypot(dx, dy) or 1.0
        return QPointF(a.x() + dx * t, a.y() + dy * t), QPointF(dx / size, dy / size)

    def smooth(self, s: float, across: float):
        """The point *s* along and the way the path goes there, that way
        eased over *across* either side, so what is set off the path turns a
        corner round its outside rather than jumping across it."""
        point, way = self.at(s)
        if across <= 0:
            return point, way
        _, before = self.at(s - across)
        _, after = self.at(s + across)
        mid = QPointF(before.x() + after.x(), before.y() + after.y())
        size = math.hypot(mid.x(), mid.y())
        return (point, QPointF(mid.x() / size, mid.y() / size)) if size > 1e-6 else (point, way)

    def piece(self, start: float, end: float) -> list:
        """The path from *start* to *end* along it, as points."""
        if end <= start:
            return []
        if not self.closed:
            start, end = max(start, 0.0), min(end, self.length)
            if end <= start:
                return []
        points = [self.at(start)[0]]
        s = start
        while True:
            folded = self._fold(s)
            index = self._segment(folded)
            corner = s + (self.at_length[index + 1] - folded)
            if corner >= end - 1e-9 or corner <= s + 1e-12:
                break
            points.append(self.at(corner)[0] if not self.closed
                          else QPointF(self.points[index + 1]))
            s = corner
        points.append(self.at(end)[0])
        return points

    def offset(self, distance: float, most: float) -> list:
        """The path moved *distance* to its left, its corners mitred — but
        never moved further than *most*, at a sharp corner."""
        points = self.points
        count = len(points)
        if count < 2:
            return []
        normals = []
        for a, b in zip(points, points[1:]):
            dx, dy = b.x() - a.x(), b.y() - a.y()
            size = math.hypot(dx, dy) or 1.0
            normals.append(QPointF(dy / size, -dx / size))
        moved = []
        for index in range(count):
            if self.closed:
                before = normals[index - 1] if index else normals[-1]
                after = normals[index] if index < len(normals) else normals[0]
            else:
                before = normals[max(index - 1, 0)]
                after = normals[min(index, len(normals) - 1)]
            mid = QPointF(before.x() + after.x(), before.y() + after.y())
            size = math.hypot(mid.x(), mid.y())
            if size < 1e-9:
                mid, stretch = after, 1.0
            else:
                mid = QPointF(mid.x() / size, mid.y() / size)
                cosine = mid.x() * after.x() + mid.y() * after.y()
                stretch = min(1.0 / max(cosine, 1e-6), most / max(abs(distance), 1e-9))
            moved.append(QPointF(points[index].x() + mid.x() * distance * stretch,
                                 points[index].y() + mid.y() * distance * stretch))
        return moved


def _far(a: QPointF, b: QPointF) -> bool:
    return abs(a.x() - b.x()) > 1e-6 or abs(a.y() - b.y()) > 1e-6


def _walks(path: QPainterPath, painter: QPainter) -> list:
    """*path*'s subpaths, flattened finely enough for the zoom it is drawn at."""
    transform = painter.worldTransform() if painter is not None else QTransform()
    zoom = max(math.hypot(transform.m11(), transform.m12()),
               math.hypot(transform.m21(), transform.m22()), 1.0)
    fine = min(zoom * 2.0, 64.0)
    walks = []
    for polygon in path.toSubpathPolygons(QTransform.fromScale(fine, fine)):
        points = [QPointF(p.x() / fine, p.y() / fine) for p in polygon]
        if len(points) < 2:
            continue
        closed = len(points) > 2 and not _far(points[0], points[-1])
        walk = _Walk(points, closed)
        if walk.length > 1e-6:
            walks.append(walk)
    return walks


def _spaced(walk: _Walk, period: float, least: float = 0.0) -> list:
    """Where repeats *period* apart go along *walk*: evenly round a closed
    one, centred on an open one; none on a path shorter than *least*."""
    length = walk.length
    if length < least or period <= 0:
        return []
    if walk.closed:
        count = max(1, round(length / period))
        step = length / count
        return [step * (k + 0.5) for k in range(count)]
    count = max(1, int(length // period))
    first = length / 2 - (count - 1) * period / 2
    return [first + k * period for k in range(count)]


#: A turn sharper than this is a corner: symbols and labels keep off it.
CORNER = math.radians(35.0)


def _on_the_sides(walk: _Walk, period: float, least: float) -> list:
    """Where symbols or labels *period* apart go: centred on each side of a
    shape with corners (none in a corner, where it would be bent round it),
    spread round a smooth closed one, centred on a smooth open one."""
    corners = []
    points = walk.points
    last = len(points) - 1
    for index in range(1, last + (1 if walk.closed else 0)):
        a, b = points[index - 1], points[index]
        c = points[index + 1] if index < last else points[1]
        turn = abs(math.remainder(math.atan2(c.y() - b.y(), c.x() - b.x())
                                  - math.atan2(b.y() - a.y(), b.x() - a.x()), math.tau))
        if turn > CORNER:
            corners.append(walk.at_length[index])
    if not corners:
        return _spaced(walk, period, least)
    if walk.closed:
        sides = list(zip(corners, corners[1:] + [corners[0] + walk.length]))
    else:
        sides = list(zip([0.0] + corners, corners + [walk.length]))
    found = []
    for start, end in sides:
        length = end - start
        if length < least:
            continue
        count = max(1, int(length // period))
        first = start + length / 2 - (count - 1) * period / 2
        found += [first + k * period for k in range(count)]
    return found


def _add_line(path: QPainterPath, points: list, closed: bool = False) -> None:
    if len(points) < 2:
        return
    path.moveTo(points[0])
    for point in points[1:]:
        path.lineTo(point)
    if closed:
        path.closeSubpath()


def _broken(path: QPainterPath, walk: _Walk, gaps: list) -> None:
    """*walk* drawn into *path*, left out over each (start, end) in *gaps*."""
    if not gaps:
        _add_line(path, walk.points, walk.closed)
        return
    gaps = sorted(gaps)
    if walk.closed:
        for (_, end), (start, _) in zip(gaps, gaps[1:] + [(gaps[0][0] + walk.length, 0)]):
            _add_line(path, walk.piece(end, start))
        return
    s = 0.0
    for start, end in gaps:
        _add_line(path, walk.piece(s, start))
        s = end
    _add_line(path, walk.piece(s, walk.length))


# -- the labels -----------------------------------------------------------------

_LABEL_PATHS: dict = {}


def _label_path(text: str) -> QPainterPath:
    """*text* as an outline a point high (its capitals), centred on 0, 0."""
    found = _LABEL_PATHS.get(text)
    if found is not None:
        return QPainterPath(found)
    font = QFont()
    font.setFamilies(["Arial", "Helvetica", "Liberation Sans", "DejaVu Sans"])
    font.setPixelSize(100)
    font.setKerning(False)
    path = QPainterPath()
    path.addText(QPointF(0, 0), font, text)
    box = path.boundingRect()
    height = max(box.height(), 1e-6)
    shape = QTransform()
    shape.scale(1.0 / height, 1.0 / height)
    shape.translate(-box.center().x(), -box.center().y())
    path = shape.map(path)
    _LABEL_PATHS[text] = QPainterPath(path)
    return path


# -- drawing ---------------------------------------------------------------------

def draw(painter: QPainter, path: QPainterPath, style) -> bool:
    """Stroke *path* in *style*'s complex line, with the painter's pen and
    filled with its brush. False, having drawn nothing, when the style is not
    a complex one — the caller strokes it as usual."""
    name = getattr(style, "line_style", "") or ""
    if not is_complex(name):
        return False
    if painter.brush().style() != Qt.NoBrush:
        inside = QPainterPath(path)
        inside.closeSubpath()
        painter.fillPath(inside, painter.brush())
    pen = QPen(painter.pen())
    if pen.style() == Qt.NoPen or path.isEmpty():
        return True
    width = pen.widthF()
    size = unit(width)
    stretch = max(float(getattr(style, "dash_scale", 1.0) or 1.0), 0.01)
    pen.setStyle(Qt.SolidLine)
    pen.setCapStyle(Qt.FlatCap)
    pen.setJoinStyle(Qt.MiterJoin)
    pen.setMiterLimit(3.0)
    painter.save()
    painter.setBrush(Qt.NoBrush)
    painter.setPen(pen)
    lines = QPainterPath()
    labels = QPainterPath()
    dashed = QPainterPath()
    for walk in _walks(path, painter):
        _DRAW[name](walk, size, stretch, lines, labels, dashed)
    if not lines.isEmpty():
        painter.drawPath(lines)
    if not dashed.isEmpty():
        centre = QPen(pen)
        centre.setStyle(Qt.CustomDashLine)
        thick = max(width, 0.01)
        centre.setDashPattern([2.0 * size * stretch / thick, 2.0 * size * stretch / thick])
        painter.setPen(centre)
        painter.drawPath(dashed)
    if not labels.isEmpty():
        painter.setPen(Qt.NoPen)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillPath(labels, pen.color())
    painter.restore()
    return True


def draw_rect(painter: QPainter, rect, style, radius: float = 0.0) -> bool:
    """:func:`draw` round a rectangle (its corners rounded by *radius*)."""
    if not is_complex(getattr(style, "line_style", "")):
        return False
    outline = QPainterPath()
    if radius > 0:
        outline.addRoundedRect(rect, radius, radius)
    else:
        outline.addRect(rect)
    return draw(painter, outline, style)


def _symbols(kind):
    def draw_them(walk, size, stretch, lines, _labels, _dashed):
        half = 2.0 * size if kind == "circle" else 1.75 * size
        at = _on_the_sides(walk, 24.0 * size * stretch, least=4 * half)
        _broken(lines, walk, [(s - half, s + half) for s in at])
        for s in at:
            point, way = walk.at(s)
            if kind == "circle":
                lines.addEllipse(point, half, half)
                continue
            across = QPointF(-way.y(), way.x())
            corners = [QPointF(point.x() + way.x() * a * half + across.x() * b * half,
                               point.y() + way.y() * a * half + across.y() * b * half)
                       for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            _add_line(lines, corners, closed=True)
    return draw_them


def _labelled(text):
    def draw_them(walk, size, stretch, lines, labels, _dashed):
        tall = 2.6 * size
        outline = _label_path(text)
        wide = outline.boundingRect().width() * tall
        half = wide / 2 + 1.2 * size
        at = _on_the_sides(walk, 30.0 * size * stretch + 2 * half, least=2 * half + 2 * size)
        _broken(lines, walk, [(s - half, s + half) for s in at])
        for s in at:
            point, way = walk.at(s)
            angle = math.degrees(math.atan2(way.y(), way.x()))
            if angle > 90.0 or angle <= -90.0:
                angle += 180.0                       # read from below or the right
            place = QTransform()
            place.translate(point.x(), point.y())
            place.rotate(angle)
            place.scale(tall, tall)
            labels.addPath(place.map(outline))
    return draw_them


def _zig_zag(walk, size, stretch, lines, _labels, _dashed):
    half = 4.0 * size * stretch                      # one stroke of the zigzag
    rise = 1.6 * size
    if walk.closed:
        count = max(2, 2 * round(walk.length / (2 * half)))
        step = walk.length / count
        points = []
        for k in range(count):
            point, way = walk.smooth(k * step, step / 2)
            side = rise if k % 2 else -rise
            points.append(QPointF(point.x() - way.y() * side, point.y() + way.x() * side))
        _add_line(lines, points, closed=True)
        return
    count = max(1, round(walk.length / half))
    step = walk.length / count
    points = [walk.at(0.0)[0]]
    for k in range(count):
        point, way = walk.smooth((k + 0.5) * step, step / 2)
        side = -rise if k % 2 == 0 else rise
        points.append(QPointF(point.x() - way.y() * side, point.y() + way.x() * side))
    points.append(walk.at(walk.length)[0])
    _add_line(lines, points)


def _insulation(walk, size, stretch, lines, _labels, _dashed):
    # A coil seen from the side: a prolate cycloid, its loops overlapping.
    loop = 2.1 * size                                # how far along a loop reaches
    tall = 1.9 * size                                # how far across
    period = 3.4 * size * stretch
    length = walk.length
    if walk.closed:
        turns = max(1, round(length / period))
        run, start = length, 0.0
    else:
        run = max(length - 2 * loop, 0.0)
        turns = max(1, round(run / period)) if run > 0 else 0
        start = loop
        if turns == 0:
            _add_line(lines, walk.points)
            return
    pace = run / (turns * math.tau)                  # along, per radian
    steps = turns * 24
    points = []
    for k in range(steps + 1):
        theta = math.tau * turns * k / steps
        along = start + pace * theta - loop * math.sin(theta)
        across = tall * math.cos(theta)
        point, way = walk.smooth(along, loop)
        points.append(QPointF(point.x() - way.y() * across, point.y() + way.x() * across))
    _add_line(lines, points, closed=walk.closed)


def _rails(walk, lines, apart, size):
    for side in (apart, -apart):
        _add_line(lines, walk.offset(side, REACH * size), walk.closed)


def _double(walk, size, stretch, lines, _labels, _dashed):
    _rails(walk, lines, 1.6 * size, size)


def _tracks(walk, size, stretch, lines, _labels, _dashed):
    apart = 1.6 * size
    _rails(walk, lines, apart, size)
    tie = 2.1 * size
    for s in _spaced(walk, 5.0 * size * stretch, least=0.0):
        point, way = walk.at(s)
        across = QPointF(-way.y() * tie, way.x() * tie)
        lines.moveTo(point - across)
        lines.lineTo(point + across)


def _road(walk, size, stretch, lines, _labels, dashed):
    _rails(walk, lines, 2.0 * size, size)
    _add_line(dashed, walk.points, walk.closed)


_DRAW = {
    "fenceline circle": _symbols("circle"),
    "fenceline square": _symbols("square"),
    "gas": _labelled("GAS"),
    "hot water": _labelled("HW"),
    "zig zag": _zig_zag,
    "insulation": _insulation,
    "double": _double,
    "tracks": _tracks,
    "road": _road,
}
