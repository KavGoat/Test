"""Geometric markups: rectangles, ellipses, polylines, clouds, ink and highlighter."""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPolygonF

from PySide6.QtGui import QFontMetricsF

from ..core.units import format_quantity, parse_unit
from .base import (HANDLE_SIZE, MarkupItem, Style, arrow_path, cloud_path,
                   register_item)


def _smooth_path(points: list[QPointF], tension: float = 0.42) -> QPainterPath:
    """Catmull-Rom style smoothing so freehand ink does not look faceted."""
    path = QPainterPath()
    if not points:
        return path
    path.moveTo(points[0])
    if len(points) == 1:
        path.lineTo(points[0] + QPointF(0.01, 0.01))
        return path
    if len(points) == 2:
        path.lineTo(points[1])
        return path
    for index in range(len(points) - 1):
        p0 = points[max(index - 1, 0)]
        p1 = points[index]
        p2 = points[index + 1]
        p3 = points[min(index + 2, len(points) - 1)]
        c1 = p1 + (p2 - p0) * (tension / 3.0)
        c2 = p2 - (p3 - p1) * (tension / 3.0)
        path.cubicTo(c1, c2, p2)
    return path


# ---------------------------------------------------------------------------
# Rectangle-based shapes
# ---------------------------------------------------------------------------

@register_item
class RectItem(MarkupItem):
    """Rectangle, ellipse, rounded rectangle, revision cloud or highlight block."""

    TYPE = "rect"
    NAME = "Rectangle"
    KINDS = ("rect", "ellipse", "cloud", "highlight", "redact", "marquee")

    def __init__(self, kind: str = "rect", rect: Optional[QRectF] = None):
        super().__init__()
        self.kind = kind
        self._rect = QRectF(rect) if rect else QRectF(0, 0, 120, 70)
        self.cloud_radius = 9.0
        # A rectangle reports its real size when the page carries a scale, so it
        # can be used to set out an area rather than only to draw a box.
        # Off: a rectangle drawn on a drawing is a rectangle, not a dimension.
        # Its size is in the properties panel and in the markups list, and the
        # right-click menu writes it on the shape for anyone who wants it there.
        self.show_size = False
        self.size_text = ""
        self.width_value = None
        self.height_value = None
        if kind == "highlight":
            self.style = Style(stroke="", fill="#ffe066", fill_opacity=0.55,
                               blend="multiply", width=0.0)
        elif kind == "redact":
            self.style = Style(stroke="#000000", fill="#000000", fill_opacity=1.0, width=0.8)
        elif kind == "marquee":
            # The snapshot region: drawn while dragging, never kept. The same
            # dashed blue as the selection marquee, because it is the same
            # gesture meaning the same thing — this part of the page.
            self.style = Style(stroke="#1971c2", fill="#1971c2", fill_opacity=0.11,
                               width=0.0, line_style="dash")

    @property
    def NAME_FOR_KIND(self) -> str:
        return {"rect": "Rectangle", "ellipse": "Ellipse", "cloud": "Cloud",
                "highlight": "Highlight", "redact": "Redaction",
                "marquee": "Snapshot region"}.get(self.kind, "Shape")

    def display_name(self) -> str:
        return self.label or self.NAME_FOR_KIND

    def local_rect(self) -> QRectF:
        return QRectF(self._rect)

    def set_local_rect(self, rect: QRectF) -> None:
        self._rect = QRectF(rect)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        rect = self._rect.normalized()
        grow = max(self.style.width, 4.0)
        if self.kind == "ellipse":
            path.addEllipse(rect.adjusted(-grow, -grow, grow, grow))
        else:
            path.addRect(rect.adjusted(-grow, -grow, grow, grow))
        return path

    # -- real-world size ---------------------------------------------------
    def page_scale(self):
        scene = self.scene()
        page = getattr(scene, "page", None) if scene is not None else None
        if page is not None:
            return page.scale
        from ..core.document import PageScale
        return PageScale()

    def refresh(self, workspace=None, page=None) -> None:
        """Work out the size to write on the rectangle.

        A scaled page gives real dimensions; an unscaled one still gives the
        paper size in millimetres, because a rectangle that says nothing at all
        is the one complaint everybody has about drawing one.
        """
        scale = page.scale if page is not None else self.page_scale()
        rect = self._rect.normalized()
        # A rectangle and an ellipse are both drawn to a size somebody cares
        # about; a cloud or a highlight is drawn around something else.
        if self.kind not in ("rect", "ellipse"):
            self.size_text = ""
            self.width_value = self.height_value = None
            self.update()
            return
        try:
            from ..core.units import Q_, convert
            from ..core.document import MM_TO_PT
            if scale.is_calibrated():
                self.width_value = convert(scale.length(rect.width()), scale.display_unit)
                self.height_value = convert(scale.length(rect.height()), scale.display_unit)
                digits = max(scale.precision, 0)
            else:
                self.width_value = Q_(rect.width() / MM_TO_PT, "mm")
                self.height_value = Q_(rect.height() / MM_TO_PT, "mm")
                digits = 1
            self.size_text = (f"{format_quantity(self.width_value, digits, 'fixed')}"
                              f" × {format_quantity(self.height_value, digits, 'fixed')}")
        except Exception:
            self.size_text = ""
            self.width_value = self.height_value = None
        self.update()

    def set_real_size(self, width_text: str, height_text: str, page=None) -> bool:
        """Resize to an exact real-world width and height."""
        scale = page.scale if page is not None else self.page_scale()
        width = parse_unit(width_text)
        height = parse_unit(height_text)
        if width is None or height is None:
            return False
        try:
            if scale.is_calibrated():
                per_point = scale.length(1.0)
                points_wide = float((width / per_point).to("dimensionless").magnitude)
                points_high = float((height / per_point).to("dimensionless").magnitude)
            else:
                from ..core.document import MM_TO_PT
                points_wide = float(width.to("mm").magnitude) * MM_TO_PT
                points_high = float(height.to("mm").magnitude) * MM_TO_PT
        except Exception:
            return False
        if points_wide <= 0 or points_high <= 0:
            return False
        self.prepareGeometryChange()
        rect = self._rect.normalized()
        self._rect = QRectF(rect.x(), rect.y(), points_wide, points_high)
        self.refresh(page=page)
        return True

    def boundingRect(self) -> QRectF:
        """Room for the size written under the rectangle."""
        rect = super().boundingRect()
        if self.show_size and self.size_text:
            rect = rect.adjusted(0, 0, 0, self.style.font_size + 6)
        return rect

    @property
    def value_text(self) -> str:
        """What the takeoff list reports for this shape — its size.

        Reported whether or not the size is written on the shape: the list is
        where a takeoff is read from, and a shape that says nothing on the
        drawing still has a size.
        """
        return self.size_text

    def summary(self) -> str:
        return self.comment or self.size_text or self.label

    def paint_content(self, painter: QPainter) -> None:
        rect = self._rect.normalized()
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = self.style.pen() if self.style.stroke else QPen(Qt.NoPen)
        painter.setPen(pen)
        painter.setBrush(self.style.brush())
        if self.kind == "ellipse":
            painter.drawEllipse(rect)
        elif self.kind == "cloud":
            polygon = QPolygonF([rect.topLeft(), rect.topRight(),
                                 rect.bottomRight(), rect.bottomLeft()])
            path = cloud_path(polygon, self.cloud_radius)
            if self.style.fill:
                filled = QPainterPath(path)
                filled.closeSubpath()
                painter.fillPath(filled, self.style.brush())
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
        elif self.style.corner_radius > 0:
            painter.drawRoundedRect(rect, self.style.corner_radius, self.style.corner_radius)
        else:
            painter.drawRect(rect)
        if self.show_size and self.size_text:
            self._paint_size(painter, rect)

    def _paint_size(self, painter: QPainter, rect: QRectF) -> None:
        """Write the size under the rectangle, the way a dimension is written.

        Inside the shape it covered whatever was being marked up and collided
        with a thick border; a dimension belongs outside the thing it measures.
        """
        from ..core.typography import set_size

        painter.save()
        font = set_size(self.style.font(), max(self.style.font_size * 0.82, 5.0))
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        gap = max(self.style.width, 0.5) + 2.5
        box = QRectF(rect.center().x() - metrics.horizontalAdvance(self.size_text) / 2,
                     rect.bottom() + gap,
                     metrics.horizontalAdvance(self.size_text), metrics.height())
        painter.setPen(QPen(QColor(self.style.stroke or self.style.text_color)))
        painter.setBrush(Qt.NoBrush)
        painter.drawText(box, Qt.AlignCenter, self.size_text)
        painter.restore()

    def serialize(self) -> dict:
        data = self.base_dict()
        data.update({"kind": self.kind, "rect": [self._rect.x(), self._rect.y(),
                                                 self._rect.width(), self._rect.height()],
                     "cloud_radius": self.cloud_radius,
                     "show_size": self.show_size})
        return data

    def deserialize(self, data: dict) -> None:
        self.kind = data.get("kind", "rect")
        values = data.get("rect", [0, 0, 100, 60])
        self._rect = QRectF(*values)
        self.cloud_radius = float(data.get("cloud_radius", 9.0))
        self.show_size = bool(data.get("show_size", False))
        self.load_base(data)


# ---------------------------------------------------------------------------
# Point-based shapes
# ---------------------------------------------------------------------------

def _arc_path(points: list[QPointF]) -> QPainterPath:
    """A curve through the points given.

    Two points make a shallow bow — an arc has to bend somewhere, and bending
    it a fixed fraction of its own length is what looks like an arc rather
    than a line that has gone wrong. A third point says where to bend it to,
    and the curve is drawn through that.
    """
    start, end = points[0], points[-1]
    if len(points) >= 3:
        through = points[1]
    else:
        middle = QPointF((start.x() + end.x()) / 2, (start.y() + end.y()) / 2)
        dx, dy = end.x() - start.x(), end.y() - start.y()
        length = math.hypot(dx, dy) or 1.0
        bow = length * 0.22
        through = QPointF(middle.x() - dy / length * bow,
                          middle.y() + dx / length * bow)
    # The control point that makes a quadratic curve pass through *through*.
    control = QPointF(2 * through.x() - (start.x() + end.x()) / 2,
                      2 * through.y() - (start.y() + end.y()) / 2)
    path = QPainterPath(start)
    path.quadTo(control, end)
    return path


@register_item
class PolyItem(MarkupItem):
    """Lines, arrows, polylines, polygons, clouds, freehand ink and highlighter."""

    TYPE = "poly"
    NAME = "Line"
    KINDS = ("line", "arrow", "polyline", "polygon", "cloud", "ink",
             "highlighter", "arc")
    VERTEX_KINDS = ("line", "arrow", "polyline", "polygon", "cloud", "arc")

    def __init__(self, kind: str = "line", points: Optional[list[QPointF]] = None):
        super().__init__()
        self.kind = kind
        self.points: list[QPointF] = [QPointF(p) for p in (points or [])]
        self.cloud_radius = 9.0
        self.smooth = kind in ("ink", "highlighter")
        if kind == "arrow":
            self.style = Style(arrow_end="arrow", width=1.6)
        elif kind == "highlighter":
            self.style = Style(stroke="#ffe066", width=12.0, blend="multiply", opacity=0.6)
        elif kind == "ink":
            self.style = Style(stroke="#e03131", width=1.6)

    # -- identity ----------------------------------------------------------
    @property
    def NAME_FOR_KIND(self) -> str:
        return {"line": "Line", "arrow": "Arrow", "polyline": "Polyline",
                "polygon": "Polygon", "cloud": "Cloud", "ink": "Pen",
                "highlighter": "Highlighter", "arc": "Arc"}.get(self.kind, "Shape")

    def display_name(self) -> str:
        return self.label or self.NAME_FOR_KIND

    @property
    def uses_vertex_handles(self) -> bool:
        return self.kind in self.VERTEX_KINDS and len(self.points) <= 40

    @property
    def closed(self) -> bool:
        return self.kind in ("polygon", "cloud")

    # -- geometry ----------------------------------------------------------
    def local_rect(self) -> QRectF:
        if not self.points:
            return QRectF(0, 0, 1, 1)
        xs = [p.x() for p in self.points]
        ys = [p.y() for p in self.points]
        return QRectF(min(xs), min(ys), max(max(xs) - min(xs), 0.5),
                      max(max(ys) - min(ys), 0.5))

    def set_local_rect(self, rect: QRectF) -> None:
        old = self.local_rect()
        if old.width() <= 0 or old.height() <= 0:
            return
        sx = rect.width() / old.width()
        sy = rect.height() / old.height()
        self.points = [QPointF(rect.x() + (p.x() - old.x()) * sx,
                               rect.y() + (p.y() - old.y()) * sy) for p in self.points]

    def build_path(self) -> QPainterPath:
        path = QPainterPath()
        if len(self.points) < 2:
            if self.points:
                path.addEllipse(self.points[0], 0.6, 0.6)
            return path
        if self.kind == "cloud":
            return cloud_path(QPolygonF(self.points), self.cloud_radius, closed=True)
        if self.kind == "arc" and len(self.points) >= 2:
            return _arc_path(self.points)
        if self.smooth:
            path = _smooth_path(self.points)
        else:
            path.moveTo(self.points[0])
            for point in self.points[1:]:
                path.lineTo(point)
        if self.closed:
            path.closeSubpath()
        return path

    def shape(self) -> QPainterPath:
        from PySide6.QtGui import QPainterPathStroker
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self.style.width, 6.0) + 4)
        stroker.setCapStyle(Qt.RoundCap)
        path = stroker.createStroke(self.build_path())
        if self.closed and self.style.fill:
            path.addPath(self.build_path())
        return path

    def boundingRect(self) -> QRectF:
        margin = self.style.width + HANDLE_SIZE + 12
        return self.local_rect().adjusted(-margin, -margin, margin, margin)

    # -- handles -----------------------------------------------------------
    def handle_points(self) -> dict[str, QPointF]:
        if self.uses_vertex_handles:
            handles = {f"v{index}": QPointF(point) for index, point in enumerate(self.points)}
            if self.kind in ("polyline", "polygon", "cloud") and len(self.points) > 2:
                rect = self.local_rect()
                handles["rot"] = QPointF(rect.center().x(), rect.top() - 22)
            return handles
        return super().handle_points()

    def move_handle(self, key: str, local_pos: QPointF, keep_ratio: bool = False) -> None:
        if key.startswith("v"):
            index = int(key[1:])
            if 0 <= index < len(self.points):
                if keep_ratio and len(self.points) >= 2:
                    anchor = self.points[index - 1] if index else self.points[1]
                    local_pos = _constrain(anchor, local_pos)
                self.prepareGeometryChange()
                self.points[index] = QPointF(local_pos)
                self.touch()
                self.geometryChanged.emit()
            return
        super().move_handle(key, local_pos, keep_ratio)

    def insert_point(self, local_pos: QPointF) -> int:
        """Insert a vertex on the nearest segment; returns its index."""
        best_index, best_distance = 1, float("inf")
        for index in range(len(self.points) - 1):
            distance = _segment_distance(self.points[index], self.points[index + 1], local_pos)
            if distance < best_distance:
                best_distance, best_index = distance, index + 1
        self.prepareGeometryChange()
        self.points.insert(best_index, QPointF(local_pos))
        self.geometryChanged.emit()
        return best_index

    def delete_point(self, index: int) -> None:
        if len(self.points) > 2 and 0 <= index < len(self.points):
            self.prepareGeometryChange()
            del self.points[index]
            self.geometryChanged.emit()

    # -- painting ----------------------------------------------------------
    def paint_content(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        path = self.build_path()
        if self.closed and self.style.fill:
            filled = QPainterPath(path)
            filled.closeSubpath()
            painter.fillPath(filled, self.style.brush())
        if self.kind == "highlighter":
            # A highlighter lays down one flat band of ink. Stroking the path
            # would draw every part of it separately, so where the stroke
            # crosses itself the colour doubles up and the round ends leave
            # notches behind — which is what a real highlighter never does.
            # Merging the whole stroke into a single outline and filling that
            # once gives one even band, whichever way it was drawn.
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(self.highlight_colour()))
            painter.drawPath(self.band_path(path))
            self._paint_arrows(painter)
            return
        painter.setPen(self.style.pen())
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        self._paint_arrows(painter)

    def highlight_colour(self) -> QColor:
        colour = QColor(self.style.stroke or "#ffd43b")
        colour.setAlphaF(max(0.0, min(1.0, self.style.opacity)))
        return colour

    def band_path(self, path: QPainterPath) -> QPainterPath:
        """The whole stroke as one outline, with the overlaps merged away."""
        from PySide6.QtGui import QPainterPathStroker

        stroker = QPainterPathStroker()
        stroker.setWidth(max(self.style.width, 0.4))
        stroker.setCapStyle(Qt.FlatCap)
        stroker.setJoinStyle(Qt.RoundJoin)
        return stroker.createStroke(path).simplified()

    def _paint_arrows(self, painter: QPainter) -> None:
        if len(self.points) < 2:
            return
        size = max(self.style.width * 4.0, 7.0)
        colour = QColor(self.style.stroke or "#000000")
        colour.setAlphaF(self.style.opacity)
        painter.setBrush(QBrush(colour))
        pen = QPen(colour)
        pen.setWidthF(max(self.style.width * 0.9, 0.5))
        painter.setPen(pen)
        if self.style.arrow_end != "none":
            tip = self.points[-1]
            previous = self.points[-2]
            angle = math.atan2(tip.y() - previous.y(), tip.x() - previous.x())
            painter.drawPath(arrow_path(tip, angle, size, self.style.arrow_end))
        if self.style.arrow_start != "none":
            tip = self.points[0]
            following = self.points[1]
            angle = math.atan2(tip.y() - following.y(), tip.x() - following.x())
            painter.drawPath(arrow_path(tip, angle, size, self.style.arrow_start))

    def paint_handles(self, painter: QPainter) -> None:
        # The same three guards the base draws under: not selected, handles
        # turned off while something else is going on, and one member of a
        # group, where the view draws one box round the lot and a vertex
        # handle here would be a control point nobody can use.
        if not self.isSelected() or not self._handles_visible or self.group:
            return
        if self.locked:
            return
        if not self.uses_vertex_handles:
            super().paint_handles(painter)
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor(20, 90, 200), 0.9))
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        half = HANDLE_SIZE / 2
        for key, point in self.handle_points().items():
            if key == "rot":
                painter.setBrush(QBrush(QColor(120, 200, 120)))
                painter.drawEllipse(point, half, half)
                painter.setBrush(QBrush(QColor(255, 255, 255)))
            else:
                painter.drawRect(QRectF(point.x() - half, point.y() - half,
                                        HANDLE_SIZE, HANDLE_SIZE))
        painter.restore()

    # -- serialisation -----------------------------------------------------
    def serialize(self) -> dict:
        data = self.base_dict()
        data.update({
            "kind": self.kind,
            "points": [[round(p.x(), 3), round(p.y(), 3)] for p in self.points],
            "cloud_radius": self.cloud_radius,
            "smooth": self.smooth,
        })
        return data

    def deserialize(self, data: dict) -> None:
        self.kind = data.get("kind", "line")
        self.points = [QPointF(x, y) for x, y in data.get("points", [])]
        self.cloud_radius = float(data.get("cloud_radius", 9.0))
        self.smooth = bool(data.get("smooth", self.kind in ("ink", "highlighter")))
        self.load_base(data)


def _segment_distance(a: QPointF, b: QPointF, p: QPointF) -> float:
    dx, dy = b.x() - a.x(), b.y() - a.y()
    if dx == 0 and dy == 0:
        return math.hypot(p.x() - a.x(), p.y() - a.y())
    t = max(0.0, min(1.0, ((p.x() - a.x()) * dx + (p.y() - a.y()) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p.x() - (a.x() + t * dx), p.y() - (a.y() + t * dy))


def _constrain(anchor: QPointF, point: QPointF) -> QPointF:
    """Snap a point to 15 degree increments from *anchor* (shift-drag)."""
    dx, dy = point.x() - anchor.x(), point.y() - anchor.y()
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return QPointF(point)
    angle = math.radians(round(math.degrees(math.atan2(dy, dx)) / 15.0) * 15.0)
    return QPointF(anchor.x() + math.cos(angle) * length,
                   anchor.y() + math.sin(angle) * length)


# ---------------------------------------------------------------------------
# Drawn artwork brought in from somewhere else
# ---------------------------------------------------------------------------

@register_item
class SketchItem(MarkupItem):
    """A piece of drawn artwork: many strokes, each with its own colours.

    Bluebeam's steel-section tools are stamps whose picture is a PDF drawing —
    a UB in section, a weld symbol, a bolt — and a section is not a rectangle
    or a polyline, so none of the other markups can hold one. This can: it
    keeps the strokes as they were drawn, each with the colour, fill and width
    it was drawn with, inside a box that can be moved and resized like
    anything else. The drawing scales with the box, so it stays a drawing
    rather than becoming a photograph of one.

    It is not drawn by hand — there is no sketch tool. It exists so that
    artwork imported from a tool set has somewhere to live.
    """

    TYPE = "sketch"
    NAME = "Drawing"

    def __init__(self, strokes: Optional[list[dict]] = None,
                 rect: Optional[QRectF] = None):
        super().__init__()
        # Each stroke: {"path": [(op, x, y, …)], "stroke": "#rrggbb" or "",
        #               "fill": "#rrggbb" or "", "width": float}
        self.strokes: list[dict] = [dict(s) for s in (strokes or [])]
        self._cache: Optional[list[tuple[QPainterPath, dict]]] = None
        self.source_box = QRectF(rect) if rect else self._strokes_box()
        self._rect = QRectF(self.source_box)
        self.style = Style(stroke="", fill="", width=0.0)

    # -- geometry ----------------------------------------------------------
    def _strokes_box(self) -> QRectF:
        box = QRectF()
        for path, _ in self.paths():
            box = path.boundingRect() if box.isNull() else box.united(path.boundingRect())
        return box if not box.isNull() else QRectF(0, 0, 1, 1)

    def local_rect(self) -> QRectF:
        return QRectF(self._rect)

    def set_local_rect(self, rect: QRectF) -> None:
        self.prepareGeometryChange()
        self._rect = QRectF(rect)

    def paths(self) -> list[tuple[QPainterPath, dict]]:
        """The strokes as painter paths, in the coordinates they were drawn in."""
        if self._cache is None:
            self._cache = [(_sketch_path(stroke.get("path", ())), stroke)
                           for stroke in self.strokes]
        return self._cache

    def _transform(self) -> tuple[float, float, float, float]:
        """How the drawn box maps onto the box on the page: (sx, sy, dx, dy)."""
        source = self.source_box
        target = self._rect.normalized()
        sx = target.width() / source.width() if source.width() else 1.0
        sy = target.height() / source.height() if source.height() else 1.0
        return sx, sy, target.x() - source.x() * sx, target.y() - source.y() * sy

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self._rect.normalized())
        return path

    # -- painting ----------------------------------------------------------
    def paint_content(self, painter: QPainter) -> None:
        if not self.strokes:
            return
        sx, sy, dx, dy = self._transform()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setOpacity(self.style.opacity)
        painter.translate(dx, dy)
        painter.scale(sx, sy)
        # The pen is scaled with the drawing, so a hairline stays a hairline
        # rather than growing into a band when the section is made bigger.
        thickness = max(abs(sx), abs(sy), 0.01)
        for path, stroke in self.paths():
            fill = stroke.get("fill", "")
            painter.setBrush(QBrush(QColor(fill)) if fill else Qt.NoBrush)
            colour = stroke.get("stroke", "")
            if colour:
                pen = QPen(QColor(colour))
                pen.setWidthF(max(float(stroke.get("width", 1.0)), 0.1) / thickness)
                pen.setCosmetic(False)
                pen.setJoinStyle(Qt.RoundJoin)
                pen.setCapStyle(Qt.RoundCap)
                painter.setPen(pen)
            else:
                painter.setPen(Qt.NoPen)
            painter.drawPath(path)
        painter.restore()

    # -- serialisation -----------------------------------------------------
    def serialize(self) -> dict:
        data = self.base_dict()
        box = self.source_box
        data.update({
            "strokes": [dict(s) for s in self.strokes],
            "source_box": [box.x(), box.y(), box.width(), box.height()],
            "rect": [self._rect.x(), self._rect.y(),
                     self._rect.width(), self._rect.height()],
        })
        return data

    def deserialize(self, data: dict) -> None:
        self.strokes = [dict(s) for s in data.get("strokes", [])]
        self._cache = None
        box = data.get("source_box")
        self.source_box = QRectF(*box) if box else self._strokes_box()
        self._rect = QRectF(*data.get("rect", [0, 0, 1, 1]))
        self.load_base(data)


def _sketch_path(commands) -> QPainterPath:
    """A painter path from the flat command list a sketch stores.

    ``["m", x, y]`` moves, ``["l", x, y]`` draws, ``["c", …six…]`` curves and
    ``["z"]`` closes — the same four the drawing came in as, so nothing has to
    be worked out twice or guessed at on the way back in.
    """
    path = QPainterPath()
    for command in commands or ():
        if not command:
            continue
        op = command[0]
        try:
            if op == "m":
                path.moveTo(float(command[1]), float(command[2]))
            elif op == "l":
                path.lineTo(float(command[1]), float(command[2]))
            elif op == "c":
                path.cubicTo(*[float(v) for v in command[1:7]])
            elif op == "z":
                path.closeSubpath()
        except (IndexError, TypeError, ValueError):
            continue
    return path
