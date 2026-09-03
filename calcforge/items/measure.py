"""Measurement and takeoff markups: length, area, angle, radius and counts."""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFontMetricsF, QPainter, QPainterPath,
                           QPen, QPolygonF)

from ..core.units import Q_, convert, format_quantity, parse_unit
from .base import HANDLE_SIZE, MarkupItem, Style, arrow_path, register_item

DIMENSION = "dimension"
LENGTH = "length"
POLYLENGTH = "polylength"
AREA = "area"
PERIMETER = "perimeter"
ANGLE = "angle"
RADIUS = "radius"
DIAMETER = "diameter"
VOLUME = "volume"
CALIBRATE = "calibrate"

MEASURE_NAMES = {
    DIMENSION: "Dimension", LENGTH: "Length", POLYLENGTH: "Polyline length", AREA: "Area",
    PERIMETER: "Perimeter", ANGLE: "Angle", RADIUS: "Radius",
    DIAMETER: "Diameter", VOLUME: "Volume", CALIBRATE: "Calibration",
}


def _distance(a: QPointF, b: QPointF) -> float:
    return math.hypot(b.x() - a.x(), b.y() - a.y())


def _polygon_area(points: list[QPointF]) -> float:
    """Shoelace area in square points."""
    if len(points) < 3:
        return 0.0
    total = 0.0
    for index in range(len(points)):
        a = points[index]
        b = points[(index + 1) % len(points)]
        total += a.x() * b.y() - b.x() * a.y()
    return abs(total) / 2.0


def _centroid(points: list[QPointF]) -> QPointF:
    if not points:
        return QPointF(0, 0)
    return QPointF(sum(p.x() for p in points) / len(points),
                   sum(p.y() for p in points) / len(points))


@register_item
class MeasureItem(MarkupItem):
    """A scaled measurement drawn on the page, with a live value label."""

    TYPE = "measure"
    NAME = "Measurement"
    ROTATABLE = False

    def __init__(self, kind: str = LENGTH, points: Optional[list[QPointF]] = None):
        super().__init__()
        self.kind = kind
        self.points: list[QPointF] = [QPointF(p) for p in (points or [])]
        # A dimension's text sits on the line, in line with it, the way a
        # dimension is drawn; every other measurement's sits above it.
        self.label_offset = QPointF(0, 0) if kind == DIMENSION else QPointF(0, -14)
        # None means "follow the line"; a number means the author turned it.
        self.label_angle: Optional[float] = None
        self.depth_text = ""            # for volume: e.g. "150 mm"
        # A dimension carries whatever text the author wants on it — "varies",
        # "2 no. @ 300 c/c" — instead of the measured value.
        self.custom_label = ""
        self.show_label = True
        # Holes taken out of an area: a slab less its lift shafts. Each is a
        # ring of points in this measurement's own coordinates.
        self.cutouts: list[list[QPointF]] = []
        self.value = None               # last computed quantity
        self.value_text = ""
        self.measured_text = ""
        self.subject = MEASURE_NAMES.get(kind, "Measurement")
        self.style = Style(stroke="#1971c2", fill="#1971c2", fill_opacity=0.18,
                           width=1.2, font_size=8.0, text_color="#0b3d91",
                           arrow_start="arrow", arrow_end="arrow")
        if kind in (AREA, VOLUME, PERIMETER):
            self.style.arrow_start = "none"
            self.style.arrow_end = "none"
        if kind == DIMENSION:
            self.subject = "Dimension"

    # -- identity ----------------------------------------------------------
    def display_name(self) -> str:
        return self.label or MEASURE_NAMES.get(self.kind, "Measurement")

    def summary(self) -> str:
        parts = [self.value_text]
        if self.comment:
            parts.append(self.comment)
        return " · ".join(p for p in parts if p)

    @property
    def closed(self) -> bool:
        return self.kind in (AREA, PERIMETER, VOLUME)

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
        sx, sy = rect.width() / old.width(), rect.height() / old.height()
        self.points = [QPointF(rect.x() + (p.x() - old.x()) * sx,
                               rect.y() + (p.y() - old.y()) * sy) for p in self.points]

    def boundingRect(self) -> QRectF:
        rect = self.local_rect()
        if self.show_label:
            centre = self._label_anchor() + self.label_offset
            half_width = max(len(self.value_text), 6) * self.style.font_size * 0.42
            half_height = self.style.font_size * 1.1
            rect = rect.united(QRectF(centre.x() - half_width, centre.y() - half_height,
                                      half_width * 2, half_height * 2))
        margin = self.style.width + HANDLE_SIZE + 12
        return rect.adjusted(-margin, -margin, margin, margin)

    def build_path(self) -> QPainterPath:
        path = QPainterPath()
        if len(self.points) < 2:
            return path
        if self.kind in (RADIUS, DIAMETER):
            centre, edge = self.points[0], self.points[1]
            radius = _distance(centre, edge)
            path.addEllipse(centre, radius, radius)
            path.moveTo(centre)
            path.lineTo(edge)
            return path
        path.moveTo(self.points[0])
        for point in self.points[1:]:
            path.lineTo(point)
        if self.closed:
            path.closeSubpath()
        return path

    def shape(self) -> QPainterPath:
        from PySide6.QtGui import QPainterPathStroker
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self.style.width, 6.0) + 6)
        path = stroker.createStroke(self.build_path())
        if self.closed:
            polygon = QPainterPath()
            polygon.addPolygon(QPolygonF(self.points))
            path.addPath(polygon)
        return path

    # -- handles -----------------------------------------------------------
    def handle_points(self) -> dict[str, QPointF]:
        handles = {f"v{index}": QPointF(point) for index, point in enumerate(self.points)}
        if self.show_label:
            centre = self._label_anchor() + self.label_offset
            handles["lbl"] = centre
            # A second handle to turn the text by, out along its own angle.
            angle = math.radians(self.label_rotation())
            reach = max(self.style.font_size * 2.2, 16.0)
            handles["lblrot"] = QPointF(centre.x() + math.cos(angle) * reach,
                                        centre.y() + math.sin(angle) * reach)
        return handles

    def label_rotation(self) -> float:
        """How the text is turned: with the line, unless it was turned by hand."""
        if self.label_angle is not None:
            return self.label_angle
        if self.kind not in (DIMENSION, LENGTH, CALIBRATE) or len(self.points) < 2:
            return 0.0
        a, b = self.points[0], self.points[1]
        angle = math.degrees(math.atan2(b.y() - a.y(), b.x() - a.x()))
        # Kept the right way up: nobody reads a dimension upside down.
        if angle > 90:
            angle -= 180
        elif angle < -90:
            angle += 180
        return angle

    def label_is_off_the_line(self) -> bool:
        """True when the text has been moved away from where it belongs."""
        offset = self.label_offset
        return math.hypot(offset.x(), offset.y()) > max(self.style.font_size, 8.0)

    def move_handle(self, key: str, local_pos: QPointF, keep_ratio: bool = False) -> None:
        if key == "lbl":
            self.prepareGeometryChange()
            self.label_offset = local_pos - self._label_anchor()
            self.update()
            return
        if key == "lblrot":
            anchor = self._label_anchor() + self.label_offset
            self.prepareGeometryChange()
            angle = math.degrees(math.atan2(local_pos.y() - anchor.y(),
                                            local_pos.x() - anchor.x()))
            step = 15 if keep_ratio else 1
            self.label_angle = round(angle / step) * step
            self.update()
            return
        if key.startswith("v"):
            index = int(key[1:])
            if 0 <= index < len(self.points):
                if keep_ratio and len(self.points) >= 2:
                    anchor = self.points[index - 1] if index else self.points[1]
                    local_pos = _snap_angle(anchor, local_pos)
                self.prepareGeometryChange()
                self.points[index] = QPointF(local_pos)
                self.refresh()
                self.geometryChanged.emit()
            return
        super().move_handle(key, local_pos, keep_ratio)

    def _label_anchor(self) -> QPointF:
        if not self.points:
            return QPointF(0, 0)
        if self.kind in (AREA, PERIMETER, VOLUME):
            return _centroid(self.points)
        if self.kind == ANGLE and len(self.points) >= 2:
            return self.points[1]
        if len(self.points) >= 2:
            mid = len(self.points) // 2
            if len(self.points) == 2:
                return (self.points[0] + self.points[1]) / 2
            return self.points[mid]
        return self.points[0]

    # -- vertices ----------------------------------------------------------
    @property
    def uses_vertex_handles(self) -> bool:
        """Only the measurements drawn as a chain of points take vertices."""
        return self.kind in (POLYLENGTH, AREA, PERIMETER, VOLUME)

    def insert_point(self, local_pos: QPointF) -> int:
        """Add a vertex on the nearest segment; returns where it went.

        Double-clicking a run of points adds one, the same as it does on a
        polygon — an area take-off is redrawn far more often than it is drawn.
        """
        from .shapes import _segment_distance

        if len(self.points) < 2:
            return 0
        best_index, best_distance = 1, float("inf")
        segments = list(zip(self.points, self.points[1:]))
        if self.closed:
            segments.append((self.points[-1], self.points[0]))
        for index, (start, end) in enumerate(segments):
            distance = _segment_distance(start, end, local_pos)
            if distance < best_distance:
                best_distance, best_index = distance, index + 1
        self.prepareGeometryChange()
        self.points.insert(best_index, QPointF(local_pos))
        self.geometryChanged.emit()
        return best_index

    def delete_point(self, index: int) -> None:
        least = 3 if self.closed else 2
        if len(self.points) > least and 0 <= index < len(self.points):
            self.prepareGeometryChange()
            del self.points[index]
            self.geometryChanged.emit()

    # -- measurement -------------------------------------------------------
    def page_scale(self):
        scene = self.scene()
        page = getattr(scene, "page", None) if scene is not None else None
        if page is not None:
            return page.scale
        from ..core.document import PageScale
        return PageScale()

    def raw_measure(self) -> tuple[str, float]:
        """Return (kind of quantity, value in page points or degrees)."""
        points = self.points
        if self.kind in (LENGTH, CALIBRATE, DIMENSION) and len(points) >= 2:
            return "length", _distance(points[0], points[1])
        if self.kind == POLYLENGTH and len(points) >= 2:
            return "length", sum(_distance(a, b) for a, b in zip(points, points[1:]))
        if self.kind == PERIMETER and len(points) >= 2:
            total = sum(_distance(a, b) for a, b in zip(points, points[1:]))
            total += _distance(points[-1], points[0])
            return "length", total
        if self.kind in (AREA, VOLUME) and len(points) >= 3:
            # Every hole taken out of it: a slab with two lift shafts in it is
            # the slab less the shafts, which is the number the concrete is
            # ordered against.
            covered = _polygon_area(points)
            for hole in self.cutouts:
                if len(hole) >= 3:
                    covered -= _polygon_area(hole)
            return "area", max(covered, 0.0)
        if self.kind == ANGLE and len(points) >= 3:
            a, b, c = points[0], points[1], points[2]
            v1 = QPointF(a.x() - b.x(), a.y() - b.y())
            v2 = QPointF(c.x() - b.x(), c.y() - b.y())
            dot = v1.x() * v2.x() + v1.y() * v2.y()
            magnitudes = math.hypot(v1.x(), v1.y()) * math.hypot(v2.x(), v2.y())
            if magnitudes < 1e-9:
                return "angle", 0.0
            return "angle", math.degrees(math.acos(max(-1.0, min(1.0, dot / magnitudes))))
        if self.kind in (RADIUS, DIAMETER) and len(points) >= 2:
            radius = _distance(points[0], points[1])
            return "length", radius * (2 if self.kind == DIAMETER else 1)
        return "none", 0.0

    def refresh(self, workspace=None, page=None) -> None:
        scale = page.scale if page is not None else self.page_scale()
        kind, raw = self.raw_measure()
        digits = max(scale.precision, 0)
        try:
            if kind == "length":
                quantity = convert(scale.length(raw), scale.display_unit)
            elif kind == "area":
                quantity = convert(scale.area(raw), scale.area_unit)
                if self.kind == VOLUME and self.depth_text:
                    depth = parse_unit(self.depth_text)
                    if depth is not None:
                        quantity = (quantity * depth).to_reduced_units()
            elif kind == "angle":
                quantity = Q_(raw, "degree")
            else:
                quantity = None
        except Exception:
            quantity = None
        self.value = quantity
        measured = format_quantity(quantity, digits, "fixed") if quantity is not None else ""
        self.value_text = self.custom_label or measured
        self.measured_text = measured
        self.update()

    # -- painting ----------------------------------------------------------
    def _paint_cutouts(self, painter: QPainter) -> None:
        """The holes, outlined so it is obvious what has been taken out."""
        if not self.cutouts:
            return
        pen = QPen(QColor(self.style.stroke or "#1971c2"))
        pen.setWidthF(max(self.style.width, 0.6))
        pen.setStyle(Qt.DashLine)
        painter.save()
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        for hole in self.cutouts:
            if len(hole) >= 3:
                painter.drawPolygon(QPolygonF(hole))
        painter.restore()

    def paint_content(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        path = self.build_path()
        if self.closed and self.style.fill:
            filled = QPainterPath()
            filled.addPolygon(QPolygonF(self.points))
            filled.closeSubpath()
            painter.fillPath(filled, self.style.brush())
        painter.setPen(self.style.pen())
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

        if self.kind == ANGLE and len(self.points) >= 3:
            self._paint_angle_arc(painter)
        if self.kind in (LENGTH, CALIBRATE, DIMENSION) and len(self.points) >= 2:
            self._paint_extension_ticks(painter)
        self._paint_cutouts(painter)
        self._paint_arrows(painter)
        if self.show_label and self.value_text:
            self._paint_label(painter)

    def _paint_angle_arc(self, painter: QPainter) -> None:
        a, b, c = self.points[0], self.points[1], self.points[2]
        radius = min(_distance(a, b), _distance(c, b)) * 0.35
        if radius < 2:
            return
        start = math.degrees(math.atan2(-(a.y() - b.y()), a.x() - b.x()))
        end = math.degrees(math.atan2(-(c.y() - b.y()), c.x() - b.x()))
        span = (end - start + 540) % 360 - 180
        rect = QRectF(b.x() - radius, b.y() - radius, radius * 2, radius * 2)
        pen = self.style.pen()
        pen.setStyle(Qt.SolidLine)
        painter.setPen(pen)
        painter.drawArc(rect, int(start * 16), int(span * 16))

    def _paint_extension_ticks(self, painter: QPainter) -> None:
        a, b = self.points[0], self.points[1]
        length = _distance(a, b)
        if length < 1e-6:
            return
        nx = -(b.y() - a.y()) / length
        ny = (b.x() - a.x()) / length
        size = max(self.style.width * 3.0, 4.0)
        pen = self.style.pen()
        painter.setPen(pen)
        for point in (a, b):
            painter.drawLine(QPointF(point.x() - nx * size, point.y() - ny * size),
                             QPointF(point.x() + nx * size, point.y() + ny * size))

    def _paint_arrows(self, painter: QPainter) -> None:
        if len(self.points) < 2 or self.closed:
            return
        size = max(self.style.width * 4.5, 7.0)
        colour = QColor(self.style.stroke)
        colour.setAlphaF(self.style.opacity)
        painter.setBrush(QBrush(colour))
        painter.setPen(QPen(colour, max(self.style.width * 0.8, 0.4)))
        if self.style.arrow_end != "none":
            tip, previous = self.points[-1], self.points[-2]
            painter.drawPath(arrow_path(tip, math.atan2(tip.y() - previous.y(),
                                                        tip.x() - previous.x()),
                                        size, self.style.arrow_end))
        if self.style.arrow_start != "none":
            tip, following = self.points[0], self.points[1]
            painter.drawPath(arrow_path(tip, math.atan2(tip.y() - following.y(),
                                                        tip.x() - following.x()),
                                        size, self.style.arrow_start))

    def _paint_label(self, painter: QPainter) -> None:
        """The text, in line with what it measures — or on a leader if moved."""
        anchor = self._label_anchor()
        position = anchor + self.label_offset
        font = self.style.font()
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        text = self.value_text
        width = metrics.horizontalAdvance(text) + 8
        height = metrics.height() + 4

        if self.label_is_off_the_line():
            # Moved away from the line, so it needs a leader back to it.
            pen = QPen(QColor(self.style.stroke), max(self.style.width * 0.6, 0.4))
            pen.setStyle(Qt.SolidLine)
            painter.setPen(pen)
            painter.drawLine(anchor, position)

        painter.save()
        painter.translate(position)
        painter.rotate(self.label_rotation())
        box = QRectF(-width / 2, -height / 2, width, height)
        painter.setBrush(QBrush(QColor(255, 255, 255, 215)))
        painter.setPen(QPen(QColor(self.style.stroke), 0.5))
        painter.drawRoundedRect(box, 2.5, 2.5)
        painter.setPen(QPen(self.style.text_qcolor()))
        painter.drawText(box, Qt.AlignCenter, text)
        painter.restore()

    # -- serialisation -----------------------------------------------------
    def serialize(self) -> dict:
        data = self.base_dict()
        data.update({
            "kind": self.kind,
            "points": [[round(p.x(), 3), round(p.y(), 3)] for p in self.points],
            "label_offset": [self.label_offset.x(), self.label_offset.y()],
            "label_angle": self.label_angle,
            "custom_label": self.custom_label,
            "depth_text": self.depth_text,
            "show_label": self.show_label,
            "cutouts": [[[round(p.x(), 3), round(p.y(), 3)] for p in hole]
                        for hole in self.cutouts],
        })
        return data

    def deserialize(self, data: dict) -> None:
        self.kind = data.get("kind", LENGTH)
        self.points = [QPointF(x, y) for x, y in data.get("points", [])]
        offset = data.get("label_offset", [0, -14])
        self.label_offset = QPointF(offset[0], offset[1])
        angle = data.get("label_angle")
        self.label_angle = float(angle) if angle is not None else None
        self.depth_text = data.get("depth_text", "")
        self.custom_label = data.get("custom_label", "")
        self.show_label = bool(data.get("show_label", True))
        self.cutouts = [[QPointF(x, y) for x, y in hole]
                        for hole in data.get("cutouts", [])]
        self.load_base(data)
        self.refresh()


@register_item
class CountItem(MarkupItem):
    """A single count marker; markers sharing a subject are totalled together."""

    TYPE = "count"
    NAME = "Count"
    RESIZABLE = False
    ROTATABLE = False
    SIZE = 16.0

    SYMBOLS = ("circle", "square", "triangle", "diamond", "cross", "star")

    def __init__(self, subject: str = "Count", index: int = 1, symbol: str = "circle"):
        super().__init__()
        self.subject = subject
        self.index = index
        self.symbol = symbol
        self.show_index = True
        self.style = Style(stroke="#c2255c", fill="#c2255c", fill_opacity=0.25,
                           width=1.2, font_size=7.0, text_color="#c2255c")

    def local_rect(self) -> QRectF:
        half = self.SIZE / 2
        return QRectF(-half, -half, self.SIZE, self.SIZE)

    def display_name(self) -> str:
        return self.label or f"Count · {self.subject}"

    def summary(self) -> str:
        return self.comment or f"#{self.index}"

    def paint_content(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.local_rect()
        painter.setPen(self.style.pen())
        painter.setBrush(self.style.brush())
        if self.symbol == "square":
            painter.drawRect(rect)
        elif self.symbol == "triangle":
            painter.drawPolygon(QPolygonF([QPointF(0, rect.top()), rect.bottomLeft(),
                                           rect.bottomRight()]))
        elif self.symbol == "diamond":
            painter.drawPolygon(QPolygonF([QPointF(0, rect.top()), QPointF(rect.right(), 0),
                                           QPointF(0, rect.bottom()), QPointF(rect.left(), 0)]))
        elif self.symbol == "cross":
            painter.drawLine(rect.topLeft(), rect.bottomRight())
            painter.drawLine(rect.topRight(), rect.bottomLeft())
        elif self.symbol == "star":
            path = QPainterPath()
            for step in range(10):
                angle = math.pi / 2 + step * math.pi / 5
                radius = rect.width() / 2 * (1.0 if step % 2 == 0 else 0.45)
                point = QPointF(math.cos(angle) * radius, -math.sin(angle) * radius)
                path.lineTo(point) if step else path.moveTo(point)
            path.closeSubpath()
            painter.drawPath(path)
        else:
            painter.drawEllipse(rect)
        if self.show_index:
            font = self.style.font()
            painter.setFont(font)
            painter.setPen(QPen(self.style.text_qcolor()))
            painter.drawText(QRectF(rect.left(), rect.bottom() + 1, rect.width(), 10),
                             Qt.AlignHCenter | Qt.AlignTop, str(self.index))

    def serialize(self) -> dict:
        data = self.base_dict()
        data.update({"index": self.index, "symbol": self.symbol,
                     "show_index": self.show_index})
        return data

    def deserialize(self, data: dict) -> None:
        self.index = int(data.get("index", 1))
        self.symbol = data.get("symbol", "circle")
        self.show_index = bool(data.get("show_index", True))
        self.load_base(data)


def _snap_angle(anchor: QPointF, point: QPointF) -> QPointF:
    dx, dy = point.x() - anchor.x(), point.y() - anchor.y()
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return QPointF(point)
    angle = math.radians(round(math.degrees(math.atan2(dy, dx)) / 15.0) * 15.0)
    return QPointF(anchor.x() + math.cos(angle) * length,
                   anchor.y() + math.sin(angle) * length)
