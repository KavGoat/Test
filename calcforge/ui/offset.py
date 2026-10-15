"""Revu's Offset (Edit ▸ Offset, O; the user's choice, 2026-10-15): a copy of
the selected markup, a set distance away, on whichever side the pointer is —
inside or outside a closed shape, either side of a line.

While it is on, the Offset toolbar shows Revu's Distance (in the page's
measurement units), Replace Markup (the original goes) and Angle Miter
Limit (how far a sharp corner may reach before it is cut off). A click puts
the copy down; Esc leaves it.
"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QEvent, QObject, QPointF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen
from PySide6.QtWidgets import (QCheckBox, QDoubleSpinBox, QGraphicsPathItem, QLabel,
                               QLineEdit, QToolBar)

from ..items.measure import MeasureItem
from ..items.shapes import PolyItem, RectItem


#: Markups whose points are not a line to run alongside.
UNOFFSETTABLE = ("ink", "arc", "angle", "radius", "diameter", "count")


# -- geometry ---------------------------------------------------------------------------------
def _normal(a: QPointF, b: QPointF) -> Optional[QPointF]:
    dx, dy = b.x() - a.x(), b.y() - a.y()
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return None
    return QPointF(-dy / length, dx / length)


def _meet(p: QPointF, u: QPointF, q: QPointF, v: QPointF) -> Optional[QPointF]:
    """Where the line through p along u meets the one through q along v."""
    cross = u.x() * v.y() - u.y() * v.x()
    if abs(cross) < 1e-9:
        return None
    t = ((q.x() - p.x()) * v.y() - (q.y() - p.y()) * v.x()) / cross
    return QPointF(p.x() + u.x() * t, p.y() + u.y() * t)


def offset_points(points: list, distance: float, closed: bool,
                  miter_limit: float = 5.0) -> list:
    """The points *distance* to the left of the line through *points* (a
    negative distance: to the right). A corner whose point would reach more
    than *miter_limit* × the distance from the corner is cut off (bevelled)."""
    pts = [QPointF(p) for p in points]
    # drop repeated points: they have no direction
    pts = [p for i, p in enumerate(pts) if i == 0 or (p - pts[i - 1]).manhattanLength() > 1e-9]
    if closed and len(pts) > 2 and (pts[0] - pts[-1]).manhattanLength() < 1e-9:
        pts.pop()
    n = len(pts)
    if n < 2:
        return pts
    segments = list(range(n if closed else n - 1))
    normals = [_normal(pts[i], pts[(i + 1) % n]) for i in segments]
    out: list = []

    def shifted(i: int, at: QPointF) -> QPointF:
        normal = normals[i]
        return QPointF(at.x() + normal.x() * distance, at.y() + normal.y() * distance)

    for k in range(n):
        if not closed and k == 0:
            out.append(shifted(0, pts[0]))
            continue
        if not closed and k == n - 1:
            out.append(shifted(n - 2, pts[-1]))
            continue
        before, after = (k - 1) % len(segments), k % len(segments)
        if normals[before] is None or normals[after] is None:
            continue
        a, b = shifted(before, pts[k]), shifted(after, pts[k])
        u = pts[k] - pts[(k - 1) % n]
        v = pts[(k + 1) % n] - pts[k]
        corner = _meet(a, u, b, v)
        if corner is None:
            out.append(a)
            continue
        reach = math.hypot(corner.x() - pts[k].x(), corner.y() - pts[k].y())
        if reach > abs(distance) * max(miter_limit, 0.0) + 1e-9:
            out.extend([a, b])                    # cut the sharp corner off
        else:
            out.append(corner)
    return out


def _area(points: list) -> float:
    total = 0.0
    for i, p in enumerate(points):
        q = points[(i + 1) % len(points)]
        total += p.x() * q.y() - q.x() * p.y()
    return total / 2.0


def offset_geometry(item, distance: float, outward: bool, miter_limit: float = 5.0):
    """The offset copy's geometry in *item*'s own coordinates: ("rect", QRectF)
    or ("points", [QPointF]); None when the markup cannot be offset."""
    if isinstance(item, RectItem):
        rect = item.local_rect().normalized()
        d = distance if outward else -distance
        grown = rect.adjusted(-d, -d, d, d)
        return ("rect", grown) if grown.width() > 0 and grown.height() > 0 else None
    points = list(getattr(item, "points", []) or [])
    if len(points) < 2 or not isinstance(item, (PolyItem, MeasureItem)):
        return None
    if getattr(item, "kind", "") in UNOFFSETTABLE:
        return None
    closed = _closed(item)
    if closed:
        # left of the line is outside for one winding, inside for the other
        sign = 1.0 if _area(points) < 0 else -1.0
        d = distance * sign * (1 if outward else -1)
    else:
        d = distance if outward else -distance
    moved = offset_points(points, d, closed, miter_limit)
    return ("points", moved) if len(moved) >= 2 else None


def _closed(item) -> bool:
    return bool(getattr(item, "closed", False))


def side_of(item, local: QPointF) -> bool:
    """True for "outward": outside a closed shape, or the left of a line."""
    if isinstance(item, RectItem):
        path = QPainterPath()
        if getattr(item, "kind", "") == "ellipse":
            path.addEllipse(item.local_rect().normalized())
        else:
            path.addRect(item.local_rect().normalized())
        return not path.contains(local)
    points = list(getattr(item, "points", []) or [])
    if _closed(item):
        path = QPainterPath(points[0])
        for p in points[1:]:
            path.lineTo(p)
        path.closeSubpath()
        return not path.contains(local)
    # the nearest segment, and which side of it the point lies
    best, side = float("inf"), True
    for a, b in zip(points, points[1:]):
        ab = b - a
        length2 = ab.x() ** 2 + ab.y() ** 2
        if length2 < 1e-12:
            continue
        t = max(0.0, min(1.0, ((local - a).x() * ab.x() + (local - a).y() * ab.y()) / length2))
        foot = QPointF(a.x() + ab.x() * t, a.y() + ab.y() * t)
        gap = math.hypot(local.x() - foot.x(), local.y() - foot.y())
        if gap < best:
            best = gap
            normal = _normal(a, b)
            side = ((local - foot).x() * normal.x() + (local - foot).y() * normal.y()) >= 0
    return side


def make_offset(item, distance: float, outward: bool, miter_limit: float = 5.0):
    """A copy of *item* moved out (or in) by *distance* points; None if not."""
    geometry = offset_geometry(item, distance, outward, miter_limit)
    if geometry is None:
        return None
    copy = item.clone()
    if copy is None:
        return None
    kind, shape = geometry
    copy.prepareGeometryChange()
    if kind == "rect":
        copy.set_local_rect(shape)
    else:
        copy.points = [QPointF(p) for p in shape]
        if hasattr(copy, "rounded"):
            copy.rounded = {}
    copy.setPos(item.pos())
    copy.setRotation(item.rotation())
    copy.setTransform(item.transform())
    return copy


def can_offset(item) -> bool:
    return offset_geometry(item, 1.0, True) is not None


# -- the session ------------------------------------------------------------------------------
class OffsetSession(QObject):
    """Offset under way on one markup: the toolbar, the preview, the click."""

    def __init__(self, window, item):
        super().__init__(window)
        self.window = window
        self.view = window.view
        self.item = item
        self.outward = True
        self.preview: Optional[QGraphicsPathItem] = None
        self.bar = window.offset_toolbar()
        self.bar.show()
        self.view.viewport().installEventFilter(self)
        self.view.viewport().setMouseTracking(True)
        window.status_hint.setText("Offset: move to the side for the copy and click — Esc stops")

    # the toolbar's values
    def distance(self) -> float:
        text = self.window.offset_distance.text().strip() or "0"
        try:
            return abs(self.window.distance_in_points(text, self.item_page()))
        except ValueError:
            return 0.0

    def item_page(self):
        frame = self.item.parentItem()
        return getattr(frame, "page", None) or self.window.current_page()

    def _redraw(self, scene_pos: QPointF) -> None:
        local = self.item.mapFromScene(scene_pos)
        self.outward = side_of(self.item, local)
        geometry = offset_geometry(self.item, self.distance(), self.outward,
                                   self.window.offset_miter.value())
        if self.preview is None:
            self.preview = QGraphicsPathItem()
            pen = QPen(QColor("#1971c2"), 0)
            pen.setStyle(Qt.DashLine)
            self.preview.setPen(pen)
            self.preview.setZValue(1e6)
            self.view.scene().addItem(self.preview)
        path = QPainterPath()
        if geometry is not None:
            kind, shape = geometry
            if kind == "rect":
                if getattr(self.item, "kind", "") == "ellipse":
                    path.addEllipse(shape)
                else:
                    path.addRect(shape)
            else:
                path.moveTo(shape[0])
                for p in shape[1:]:
                    path.lineTo(p)
                if _closed(self.item):
                    path.closeSubpath()
        self.preview.setPath(self.item.sceneTransform().map(path))

    def place(self, scene_pos: Optional[QPointF] = None) -> object:
        if scene_pos is not None:
            self.outward = side_of(self.item, self.item.mapFromScene(scene_pos))
        distance = self.distance()
        if distance <= 0:
            self.window.status_hint.setText("Offset: give a distance first")
            return None
        frame = self.item.parentItem()
        copy = make_offset(self.item, distance, self.outward, self.window.offset_miter.value())
        if copy is None or frame is None:
            self.window.status_hint.setText("Offset: this markup cannot be offset that far")
            return None
        self.view.begin_snapshot(self.view.involved_frames(self.item))
        if hasattr(copy, "load_from_document"):
            copy.load_from_document(self.window.document)
        frame.add_markup(copy)
        copy.refresh(page=getattr(frame, "page", None))
        if self.window.offset_replace.isChecked():
            self.item.setSelected(False)
            frame.remove_markup(self.item)
        self.view.commit_snapshot("Offset")
        self.finish()
        self.view.scene().clearSelection()
        copy.setSelected(True)
        self.window.refresh_selection()
        return copy

    def finish(self) -> None:
        self.view.viewport().removeEventFilter(self)
        if self.preview is not None and self.preview.scene() is not None:
            self.preview.scene().removeItem(self.preview)
        self.preview = None
        self.bar.hide()
        if getattr(self.window, "_offset", None) is self:
            self.window._offset = None
        self.window.status_hint.setText("Ready")

    def eventFilter(self, _watched, event) -> bool:
        kind = event.type()
        if kind == QEvent.MouseMove:
            self._redraw(self.view.mapToScene(event.position().toPoint()))
            return False
        if kind == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                self.place(self.view.mapToScene(event.position().toPoint()))
            else:
                self.finish()
            return True
        if kind == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            self.finish()
            return True
        return False


def build_toolbar(window) -> QToolBar:
    """Revu's Offset toolbar."""
    bar = QToolBar("Offset", window)
    bar.setObjectName("offsetToolbar")
    bar.addWidget(QLabel(" Distance: "))
    window.offset_distance = QLineEdit("10 mm")
    window.offset_distance.setObjectName("offsetDistance")
    window.offset_distance.setFixedWidth(90)
    window.offset_distance.setToolTip("How far from the markup the copy goes, in the page's "
                                      "measurement units (\"300 mm\", \"6 in\")")
    bar.addWidget(window.offset_distance)
    window.offset_replace = QCheckBox("Replace Markup")
    window.offset_replace.setToolTip("Delete the original when the offset copy is placed")
    bar.addWidget(window.offset_replace)
    bar.addWidget(QLabel("  Angle Miter Limit: "))
    window.offset_miter = QDoubleSpinBox()
    window.offset_miter.setObjectName("offsetMiter")
    window.offset_miter.setRange(0.0, 100.0)
    window.offset_miter.setSingleStep(0.5)
    window.offset_miter.setDecimals(1)
    window.offset_miter.setValue(5.0)
    window.offset_miter.setToolTip("How sharp a corner of the copy may be: higher keeps "
                                   "sharper points, lower cuts them off")
    bar.addWidget(window.offset_miter)
    bar.hide()
    return bar
