"""What a Shift- or Ctrl-click on a selected outline would do, drawn on it.

Revu shows a plus or a minus on the pointer while Shift is held over an
outline. The user found that hard to read — "it's not clear where the point
is added or removed, confusing with the + or −" (2026-10-20) — so the pointer
keeps saying move (or copy, with Ctrl), and the outline itself shows what a
click would do:

- add: a hollow point where the new point goes, on the side under the pointer;
- delete: the point that goes, ringed and crossed out in red, and the outline
  without it, dashed;
- round: the corner rounded off (or sharpened again), dashed;
- curve: the side bent into an arc (or straightened again), dashed.

A drag never does any of this: pressed and dragged, Shift and Ctrl mean what
they mean for any move. The preview repaints only the pixels it covers, where
it was and where it is, so nothing is left behind when it goes.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Optional

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import QApplication

#: the new point's ring and the crossed-out point's, in screen pixels
POINT_RADIUS_PX = 5.0
#: room round what is drawn for the pen and its halo, in screen pixels
PAD_PX = 6


def nearest_on_segment(start: QPointF, end: QPointF, point: QPointF) -> QPointF:
    """The point of the straight run *start*–*end* nearest *point*."""
    dx, dy = end.x() - start.x(), end.y() - start.y()
    length = dx * dx + dy * dy
    if length <= 1e-12:
        return QPointF(start)
    t = ((point.x() - start.x()) * dx + (point.y() - start.y()) * dy) / length
    t = max(0.0, min(1.0, t))
    return QPointF(start.x() + dx * t, start.y() + dy * t)


def reshaped_copy(item, what: str, index: int, local: Optional[QPointF] = None):
    """A copy of *item*, off the canvas, with the reshaping done to it — or
    None when it cannot be made. A rectangle comes back as the polygon it
    would become."""
    from ..items.base import build_item
    from ..items.shapes import PolyItem, RectItem

    try:
        if isinstance(item, RectItem):
            shape = PolyItem.from_rectangle(item)
        else:
            shape = build_item(dict(deepcopy(item.serialize()), uid="preview"))
        if not isinstance(shape, PolyItem):
            return None
        if what == "delete":
            shape.delete_point(index)
        elif what == "add" and local is not None:
            shape.insert_point(local)
        elif what == "round":
            shape.round_corner(index)
        elif what == "curve":
            shape.curve_segment(index)
        return shape
    except (RuntimeError, AttributeError, KeyError, TypeError, ValueError, IndexError):
        return None


def _signature(item) -> tuple:
    """Everything the outline is made from, to tell when it has changed."""
    transform = item.sceneTransform()
    return (tuple((p.x(), p.y()) for p in item.corner_points()),
            repr(sorted(getattr(item, "rounded", {}).items())),
            repr(sorted(getattr(item, "curved", {}).items())),
            repr(sorted(getattr(item, "bezier", {}).items())),
            transform.m11(), transform.m12(), transform.m21(), transform.m22(),
            transform.dx(), transform.dy())


class ReshapePreview:
    """The on-canvas preview of a Shift- or Ctrl-click's reshaping."""

    def __init__(self, view):
        self.view = view
        self.what: Optional[str] = None
        #: in scene coordinates: the point added, or the point that goes
        self.point: Optional[QPointF] = None
        #: in scene coordinates: the outline as it would be, dashed (or None)
        self.path: Optional[QPainterPath] = None
        #: in scene coordinates: the part of it that changes, when that is
        #: only a corner or one side (the rest is as drawn already)
        self.area: Optional[QPainterPath] = None
        self._key = None

    def showing(self) -> bool:
        return self.what is not None

    def show(self, item, what: str, index: int, scene_pos: QPointF) -> None:
        """Preview *what* the click would do to *item* (see shaping_target)."""
        try:
            local = item.mapFromScene(scene_pos)
            new_point = None
            if what == "add":
                start, end = item.segment_ends(index)
                new_point = nearest_on_segment(start, end, local)
            key = (id(item), what, index, _signature(item),
                   None if new_point is None
                   else (round(new_point.x(), 3), round(new_point.y(), 3)))
        except RuntimeError:
            self.hide()
            return
        if key == self._key:
            return
        self._dirty()
        self._key = key
        self.what = what
        transform = item.sceneTransform()
        self.point = None
        self.path = None
        self.area = None
        if what == "add":
            self.point = transform.map(new_point)
            # A point put into a bent side straightens both halves of it:
            # show that too, or the click would change more than it promised.
            bent = item.is_curved(index) or index in getattr(item, "bezier", {})
            if bent:
                shape = reshaped_copy(item, what, index, new_point)
                if shape is not None:
                    self.path = transform.map(shape.build_path())
        else:
            if what == "delete":
                self.point = transform.map(QPointF(item.corner_points()[index]))
            shape = reshaped_copy(item, what, index)
            if shape is not None:
                self.path = transform.map(shape.build_path())
                area = self._changed_area(item, shape, what, index)
                if area is not None:
                    self.area = transform.map(area)
        self._dirty()

    @staticmethod
    def _changed_area(item, shape, what: str, index: int) -> Optional[QPainterPath]:
        """Round the corner that is rounded, or along the side that is bent:
        where the dashed outline is worth drawing (in item coordinates)."""
        if what == "round":
            corner = QPointF(item.corner_points()[index])
            radius = max(shape.rounded.get(index, 0.0),
                         getattr(item, "rounded", {}).get(index, 0.0), 2.0)
            reach = radius * 2.5 + 2.0
            area = QPainterPath()
            area.addRect(QRectF(corner.x() - reach, corner.y() - reach, 2 * reach, 2 * reach))
            return area
        if what == "curve":
            start, end = item.segment_ends(index)
            bent = shape if shape.is_curved(index) else item
            apex = bent.curve_apex(index) if bent.is_curved(index) else (start + end) / 2
            # (not QRectF.united: a straight side's box has no height, and a
            # rectangle with none is left out of a union)
            xs = [start.x(), end.x(), apex.x()]
            ys = [start.y(), end.y(), apex.y()]
            box = QRectF(QPointF(min(xs), min(ys)), QPointF(max(xs), max(ys)))
            area = QPainterPath()
            area.addRect(box.adjusted(-3, -3, 3, 3))
            return area
        return None

    def hide(self) -> None:
        if self.what is None and self._key is None:
            return
        self._dirty()
        self.what = None
        self.point = None
        self.path = None
        self._key = None

    # -- where it is drawn --------------------------------------------------
    def pixel_rect(self) -> QRect:
        """The viewport pixels the preview covers now (empty when hidden)."""
        if self.what is None:
            return QRect()
        to_view = self.view.viewportTransform()
        box = QRectF()
        if self.path is not None:
            box = to_view.map(self.path).boundingRect()
            if self.area is not None:
                box = box.intersected(to_view.map(self.area).boundingRect())
        if self.point is not None:
            at = to_view.map(self.point)
            reach = POINT_RADIUS_PX + 2
            box = box.united(QRectF(at.x() - reach, at.y() - reach, 2 * reach, 2 * reach))
        return box.toAlignedRect().adjusted(-PAD_PX, -PAD_PX, PAD_PX, PAD_PX)

    def _dirty(self) -> None:
        rect = self.pixel_rect()
        if not rect.isEmpty():
            self.view.viewport().update(rect)

    # -- drawing --------------------------------------------------------------
    @staticmethod
    def colours() -> tuple[QColor, QColor, QColor]:
        """(preview, taken out, halo): the theme's accent and its warning red,
        as its selection and its warnings are drawn in the light and the dark;
        the halo is the paper's white, which the page is in either theme, so
        the preview stands off a dark drawing without darkening a light one."""
        palette = QApplication.palette()
        return (palette.color(QPalette.Highlight), palette.color(QPalette.BrightText),
                QColor(255, 255, 255, 210))

    def paint(self, painter: QPainter) -> None:
        """Called from the view's foreground, in scene coordinates."""
        if self.what is None:
            return
        accent, danger, halo = self.colours()
        to_view = self.view.viewportTransform()
        painter.save()
        painter.resetTransform()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setBrush(Qt.NoBrush)
        if self.path is not None:
            path = to_view.map(self.path)
            if self.area is not None:
                painter.setClipPath(to_view.map(self.area))
            painter.setPen(QPen(halo, 3.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPath(path)
            dashed = QPen(accent, 1.6, Qt.CustomDashLine, Qt.FlatCap, Qt.RoundJoin)
            dashed.setDashPattern([4.0, 3.0])
            painter.setPen(dashed)
            painter.drawPath(path)
            painter.setClipping(False)
        if self.point is not None:
            at = to_view.map(self.point)
            radius = POINT_RADIUS_PX
            colour = danger if self.what == "delete" else accent
            painter.setPen(QPen(halo, 3.6))
            painter.drawEllipse(at, radius, radius)
            painter.setPen(QPen(colour, 1.8))
            painter.drawEllipse(at, radius, radius)
            if self.what == "delete":
                arm = radius * 0.62
                for pen in (QPen(halo, 3.4, Qt.SolidLine, Qt.RoundCap),
                            QPen(colour, 1.6, Qt.SolidLine, Qt.RoundCap)):
                    painter.setPen(pen)
                    painter.drawLine(QPointF(at.x() - arm, at.y() - arm),
                                     QPointF(at.x() + arm, at.y() + arm))
                    painter.drawLine(QPointF(at.x() - arm, at.y() + arm),
                                     QPointF(at.x() + arm, at.y() - arm))
        painter.restore()
