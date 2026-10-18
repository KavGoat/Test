"""Measurement and takeoff markups: length, area, angle, radius and counts."""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFontMetricsF, QPainter, QPainterPath,
                           QPen, QPolygonF)

from ..core.units import Q_, convert, format_quantity, parse_unit
from .base import HANDLE_SIZE, MarkupItem, Style, draw_head, register_item
from . import complexlines

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

# The measurements drawn the way a dimension is drawn on a drawing: two points,
# an arrow at each end, and the value written along the line between them. What
# the value says is the only difference between them — the measurement, or
# whatever the author typed instead.
DIMENSIONED = (LENGTH, DIMENSION, CALIBRATE)

# How far a witness line runs past the dimension line it reaches, and how far
# it stands off the point it comes from — both the small conventions that stop
# a dimension from touching what it measures.
WITNESS_OVERSHOOT = 4.0
WITNESS_GAP = 2.0


#: Revu's Units ▾: the units a measurement can be written in, beside the page's.
LENGTH_UNITS = ("mm", "cm", "m", "km", "in", "ft", "yd", "mi")
AREA_UNITS = tuple(f"{unit}^2" for unit in LENGTH_UNITS)
VOLUME_UNITS = ("mm^3", "cm^3", "m^3", "in^3", "ft^3", "yd^3")

#: Revu's Caption ▾ values, in its order, and what each is called there. An
#: area can show its perimeter too, and with a depth its volume and wall
#: area; a volume its area, perimeter and wall area; a perimeter its wall area.
CAPTION_PARTS = (("label", "Label"), ("length", "Length"), ("area", "Area"),
                 ("perimeter", "Perimeter"), ("volume", "Volume"),
                 ("wall_area", "Wall Area"))
#: Their short names, written before each value when more than one is shown.
CAPTION_SHORT = {"length": "L", "area": "A", "perimeter": "P", "volume": "V",
                 "wall_area": "WA"}


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


def _path_area(path: QPainterPath) -> float:
    """Area covered by a painter path, including clipped polygon fragments."""
    return sum(_polygon_area(list(polygon)) for polygon in path.toFillPolygons())


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
        # Anything drawn as a dimension has its value written along the line,
        # the way a dimension is drawn — whether the value is what was measured
        # or what the author typed instead. Every other measurement's sits
        # above what it measures, where there is no line to write along.
        self.label_offset = QPointF(0, 0) if kind in DIMENSIONED else QPointF(0, -14)
        # None means "follow the line"; a number means the author turned it.
        self.label_angle: Optional[float] = None
        self.depth_text = ""            # for volume: e.g. "150 mm"
        # A dimension carries whatever text the author wants on it — "varies",
        # "2 no. @ 300 c/c" — instead of the measured value.
        self.custom_label = ""
        # How far the dimension line stands off the two points it measures.
        # Dragging the control dot on the value sets it — the dot travels
        # perpendicular to the dimension and nowhere else — and the witness
        # lines then run out from the measured points to reach the line, the
        # way a dimension is drawn on a drawing.
        self.witness_reach = 0.0
        self.show_label = True
        # Holes taken out of an area: a slab less its lift shafts. Each is a
        # ring of points in this measurement's own coordinates.
        # cutouts live on MarkupItem now, shared with every other closed shape
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
        # A variable name (decision 24): the measurement then defines it for
        # the calculations, live, as an equation at the top-left of its box.
        self.variable = ""
        self._variable_link = None
        # Revu's Units ▾: the units this one is written in, by "length",
        # "area" and "volume"; one not given is the page's.
        self.units: dict[str, str] = {}
        # Revu's Caption ▾: which values are written, by CAPTION_PARTS name.
        # Empty is the measurement's own value alone, as it always was.
        self.caption_parts: list[str] = []

    # -- units and caption (Revu's Units ▾ and Caption ▾) -------------------
    def set_unit(self, key: str, unit: str) -> None:
        if unit:
            self.units[key] = unit
        else:
            self.units.pop(key, None)

    def primary_part(self) -> str:
        """The value this kind of measurement is about."""
        if self.kind in (AREA,):
            return "area"
        if self.kind == VOLUME:
            return "volume"
        if self.kind == PERIMETER:
            return "perimeter"
        return "length"

    def caption_choices(self) -> tuple:
        """The values Caption ▾ offers for this kind (Revu's)."""
        if self.kind == AREA:
            return ("label", "area", "perimeter", "volume", "wall_area")
        if self.kind == VOLUME:
            return ("label", "volume", "area", "perimeter", "wall_area")
        if self.kind == PERIMETER:
            return ("label", "perimeter", "wall_area")
        if self.kind in (ANGLE, CALIBRATE, DIMENSION):
            return ()
        return ("label", "length")

    def caption_available(self, part: str) -> bool:
        """Volume and wall area need a depth to be worked out from."""
        if part in ("volume", "wall_area") and self.kind != VOLUME:
            return bool(self.depth_text)
        if part == "wall_area":
            return bool(self.depth_text)
        return part in self.caption_choices()

    def caption_shown(self) -> list:
        """The values written on the drawing, in Revu's order."""
        if not self.caption_parts:
            return [self.primary_part()]
        order = [part for part, _words in CAPTION_PARTS]
        return sorted((p for p in self.caption_parts if p in self.caption_choices()),
                      key=order.index)

    def set_caption_part(self, part: str, on: bool) -> None:
        shown = set(self.caption_shown())
        if on:
            shown.add(part)
        else:
            shown.discard(part)
        if not shown & {p for p in self.caption_choices() if p != "label"}:
            shown.add(self.primary_part())        # never a caption of nothing
        order = [p for p, _words in CAPTION_PARTS]
        parts = sorted(shown, key=order.index)
        self.caption_parts = [] if parts == [self.primary_part()] else parts

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
    def outline_ring(self) -> list:
        """An area or volume measurement encloses something; the others do not."""
        if self.kind in (AREA, VOLUME) and len(self.points) >= 3:
            return list(self.points)
        return []

    def hatch_region(self) -> Optional[QPainterPath]:
        """An area or a volume is hatched as Revu's are: inside its outline,
        less its cut-outs."""
        if self.kind not in (AREA, VOLUME) or len(self.points) < 3:
            return None
        path = QPainterPath()
        path.addPolygon(QPolygonF(self.points))
        path.closeSubpath()
        if self.cutouts:
            path = path.subtracted(self.clipped_holes_path())
        return path

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
        if self.kind in (RADIUS, DIAMETER) and len(self.points) >= 2:
            rect = rect.united(self.build_path().boundingRect())
        if self.is_dimensioned() and abs(self.witness_reach) > 1e-9:
            start, end = self.dimension_ends()
            rect = rect.united(QRectF(start, end).normalized())
        if self.show_label:
            centre = self._label_anchor() + self.label_offset
            lines = (self.value_text or "").split("\n")
            half_width = max(max(len(line) for line in lines), 6) * self.style.font_size * 0.42
            half_height = self.style.font_size * 1.1 * len(lines)
            rect = rect.united(QRectF(centre.x() - half_width, centre.y() - half_height,
                                      half_width * 2, half_height * 2))
        margin = self.style.width + HANDLE_SIZE + 12 + complexlines.reach(self.style)
        return rect.adjusted(-margin, -margin, margin, margin)

    # -- the shape of a dimension -----------------------------------------
    def is_dimensioned(self) -> bool:
        """Whether this is drawn as a dimension: arrow to arrow, value along it."""
        return self.kind in DIMENSIONED and len(self.points) >= 2

    def dimension_normal(self) -> QPointF:
        """The direction the dimension line moves when the dot is dragged."""
        if len(self.points) < 2:
            return QPointF(0, 0)
        a, b = self.points[0], self.points[1]
        length = _distance(a, b)
        if length < 1e-9:
            return QPointF(0, 0)
        return QPointF(-(b.y() - a.y()) / length, (b.x() - a.x()) / length)

    def dimension_direction(self) -> QPointF:
        """Along the dimension, from the first measured point to the second."""
        if len(self.points) < 2:
            return QPointF(1, 0)
        a, b = self.points[0], self.points[1]
        length = _distance(a, b)
        if length < 1e-9:
            return QPointF(1, 0)
        return QPointF((b.x() - a.x()) / length, (b.y() - a.y()) / length)

    def dimension_ends(self) -> tuple[QPointF, QPointF]:
        """Where the arrows sit: the measured points, pushed out by the reach."""
        if len(self.points) < 2:
            return QPointF(0, 0), QPointF(0, 0)
        a, b = self.points[0], self.points[1]
        if not self.is_dimensioned() or abs(self.witness_reach) < 1e-9:
            return QPointF(a), QPointF(b)
        normal = self.dimension_normal()
        push = QPointF(normal.x() * self.witness_reach,
                       normal.y() * self.witness_reach)
        return a + push, b + push

    def build_path(self) -> QPainterPath:
        path = QPainterPath()
        if len(self.points) < 2:
            return path
        if self.is_dimensioned():
            start, end = self.dimension_ends()
            path.moveTo(start)
            path.lineTo(end)
            return path
        if self.kind in (RADIUS, DIAMETER):
            start, edge = self.points[0], self.points[1]
            if self.kind == DIAMETER:
                centre = (start + edge) / 2
                radius = _distance(start, edge) / 2
            else:
                centre, radius = start, _distance(start, edge)
            path.addEllipse(centre, radius, radius)
            path.moveTo(start)
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
        stroker.setWidth(max(self.style.width, 6.0) + 6 + 2 * complexlines.reach(self.style))
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
            # The control dot stands just before the value, in line with it.
            # Dragging it pulls the dimension line off what it measures;
            # Shift and dragging it takes the value away onto a leader. One
            # dot, both of the things a dimension is ever asked to do. It
            # used to sit on the middle of the value, and with the turning
            # handle beside it the answer could not be read (novice finding
            # 10): the handles stand clear of the words, either side of them.
            handles["lbl"] = centre + self._label_dot_shift()
            # A second handle to turn the text by, out along its own angle,
            # just past the end of the words.
            angle = math.radians(self.label_rotation())
            reach = self._label_half_width() + self._handle_gap()
            handles["lblrot"] = QPointF(centre.x() + math.cos(angle) * reach,
                                        centre.y() + math.sin(angle) * reach)
        return handles

    def _label_half_width(self) -> float:
        """Half the width the value is written across (as _paint_label)."""
        metrics = QFontMetricsF(self.style.font())
        return (max(metrics.horizontalAdvance(line)
                    for line in (self.value_text or "").split("\n")) + 8) / 2

    def _handle_gap(self) -> float:
        """How far a handle's centre stands off the words: its own radius,
        at the zoom it is seen at, and a little room."""
        from .base import CONTROL_HALF_PX, view_zoom
        return CONTROL_HALF_PX / view_zoom(self) + 1.5

    def _label_dot_shift(self) -> QPointF:
        """From the middle of the value to its control dot, before the words."""
        angle = math.radians(self.label_rotation())
        reach = self._label_half_width() + self._handle_gap()
        return QPointF(-math.cos(angle) * reach, -math.sin(angle) * reach)

    def control_dots(self) -> set[str]:
        """The dot on the value, which is what a dimension is adjusted by."""
        return {"lbl"} if self.is_dimensioned() and self.show_label else set()

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
            if self.is_dimensioned() and not keep_ratio:
                # The dot travels perpendicular to the dimension and nowhere
                # else, so the line it carries stays parallel to what it
                # measures however carelessly the pointer wanders.
                self.prepareGeometryChange()
                normal = self.dimension_normal()
                middle = (self.points[0] + self.points[1]) / 2
                away = local_pos - self._label_dot_shift() - middle
                self.witness_reach = away.x() * normal.x() + away.y() * normal.y()
                self.label_offset = QPointF(0, 0)
                self.update()
                self.geometryChanged.emit()
                return
            self.prepareGeometryChange()
            # the dot is grabbed beside the words: they keep their distance
            self.label_offset = local_pos - self._label_dot_shift() - self._label_anchor()
            self.update()
            return
        if key == "lbltext":
            # the words themselves, taken hold of (Shift on the value)
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

    def label_rect(self) -> QRectF:
        """The box the value is written in, so it can be clicked on."""
        centre = self._label_anchor() + self.label_offset
        lines = (self.value_text or "").split("\n")
        half_width = max(max(len(line) for line in lines), 3) * self.style.font_size * 0.34
        half_height = self.style.font_size * 0.8 * len(lines)
        return QRectF(centre.x() - half_width, centre.y() - half_height,
                      half_width * 2, half_height * 2)

    def label_at(self, local_pos: QPointF) -> bool:
        """Whether the pointer is on the value itself."""
        return bool(self.show_label and self.value_text
                    and self.label_rect().contains(local_pos))

    def _label_anchor(self) -> QPointF:
        if not self.points:
            return QPointF(0, 0)
        if self.kind in (AREA, PERIMETER, VOLUME):
            return _centroid(self.points)
        if self.kind == ANGLE and len(self.points) >= 2:
            return self.points[1]
        if self.is_dimensioned():
            # The middle of the dimension line, wherever the dot has put it,
            # so the value travels with the line rather than being left behind
            # on the thing it measures.
            start, end = self.dimension_ends()
            return (start + end) / 2
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
        """What the page this is drawn on is a drawing of.

        The page belongs to the frame this markup sits on, not to the scene:
        one canvas holds every page of the document, so asking the scene got a
        default scale back every time and a measurement written out with it
        said 1:1 whatever the drawing was actually at.
        """
        frame = self.parentItem()
        page = getattr(frame, "page", None) if frame is not None else None
        if page is None:
            scene = self.scene()
            page = getattr(scene, "page", None) if scene is not None else None
        if page is not None:
            return self.scale_on(page)
        from ..core.document import PageScale
        return PageScale()

    def scale_on(self, page):
        """The page's scale here — a viewport's, when the first point is in one."""
        from .base import scale_where
        anchor = self.points[0] if self.points else QPointF()
        return scale_where(self, page, anchor)

    def raw_measure(self, stretch: float = 1.0) -> tuple[str, float]:
        """Return (kind of quantity, value in page points or degrees).

        *stretch* is the page's Y scale over its X scale: lengths and angles
        are read with the drawing stretched down the page by it, so a sheet
        at different scales across and down measures true. Areas are not
        stretched here; ``PageScale.area`` allows for it.
        """
        points = self.points
        if abs(stretch - 1.0) > 1e-9 and self.kind not in (AREA, VOLUME):
            points = [QPointF(p.x(), p.y() * stretch)
                      for p in (self.mapToParent(q) for q in self.points)]
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
            covered -= _path_area(self.clipped_holes_path())
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
            # A radius is drawn from the centre out to the edge; a diameter
            # from one edge straight across to the other, so what was drawn is
            # what is reported.
            return "length", _distance(points[0], points[1])
        return "none", 0.0

    def refresh(self, workspace=None, page=None) -> None:
        scale = self.scale_on(page) if page is not None else self.page_scale()
        stretch = getattr(scale, "y_factor", 1.0)
        kind, raw = self.raw_measure(stretch)
        digits = max(scale.precision, 0)
        # Revu's Units ▾: this measurement's own units, else the page's
        length_unit = self.units.get("length") or scale.display_unit
        area_unit = self.units.get("area") or scale.area_unit
        try:
            if kind == "length":
                quantity = convert(scale.length(raw), length_unit)
            elif kind == "area":
                quantity = convert(scale.area(raw), area_unit)
                if self.kind == VOLUME and self.depth_text:
                    volume = self._volume(scale, raw)
                    if volume is not None:
                        quantity = volume
            elif kind == "angle":
                quantity = Q_(raw, "deg")
            else:
                quantity = None
        except Exception:
            quantity = None
        self.value = quantity

        def written(value, as_length: bool) -> str:
            if value is None:
                return ""
            if as_length and hasattr(scale, "format_length"):
                # a length is written to the scale's Precision, which may be
                # a fraction (Revu's Set Scale; the user, 2026-10-15)
                return scale.format_length(value, digits)
            return format_quantity(value, digits, "fixed")
        measured = written(quantity, kind == "length")
        self.measured_text = measured
        shown = self.caption_shown()
        primary = self.primary_part()
        if shown == [primary]:
            named = f"{self.variable} = {measured}" if self.variable and measured else measured
        else:
            values = self._caption_values(scale, stretch, quantity, length_unit, area_unit)
            several = len([p for p in shown if p != "label"]) > 1
            lines = []
            for part in shown:
                if part == "label":
                    if self.label:
                        lines.append(self.label)
                    continue
                text = written(values.get(part), part in ("length", "perimeter"))
                if not text:
                    continue
                if part == primary and self.variable:
                    lines.append(f"{self.variable} = {text}")
                elif several:
                    lines.append(f"{CAPTION_SHORT[part]} = {text}")
                else:
                    lines.append(text)
            named = "\n".join(lines)
        self.value_text = self.custom_label or named
        self.update()
        self.sync_variable()

    def _volume(self, scale, raw: float):
        """The area times the depth, in this measurement's volume unit — or,
        without one, as it always was: the page's area unit times the depth."""
        depth = parse_unit(self.depth_text) if self.depth_text else None
        if depth is None:
            return None
        volume = (convert(scale.area(raw), scale.area_unit) * depth).to_reduced_units()
        unit = self.units.get("volume")
        return convert(volume, unit) if unit else volume

    def _caption_values(self, scale, stretch: float, own, length_unit: str,
                        area_unit: str) -> dict:
        """Every value Caption ▾ can show for this one, worked out."""
        values = {self.primary_part(): own}
        if not self.closed or len(self.points) < 2:
            return values
        try:
            points = self.points
            if abs(stretch - 1.0) > 1e-9:
                points = [QPointF(p.x(), p.y() * stretch)
                          for p in (self.mapToParent(q) for q in self.points)]
            around = sum(_distance(a, b) for a, b in zip(points, points[1:]))
            around += _distance(points[-1], points[0])
            perimeter = convert(scale.length(around), length_unit)
            values["perimeter"] = perimeter
            if self.kind in (AREA, VOLUME) and len(self.points) >= 3:
                _kind, raw = self.raw_measure(stretch)
                area = convert(scale.area(raw), area_unit)
                values["area"] = area
                values["volume"] = self._volume(scale, raw)
            depth = parse_unit(self.depth_text) if self.depth_text else None
            if depth is not None:
                values["wall_area"] = convert(perimeter * depth, area_unit)
        except Exception:                          # noqa: BLE001 — units that do not mix
            pass
        return values

    # -- a measurement as a variable (decision 24) -------------------------------
    def sync_variable(self) -> None:
        """Keep the variable it defines in step with its value and place."""
        from .calc import MeasureVariable

        if self._variable_link is None:
            if not self.variable:
                return
            self._variable_link = MeasureVariable(self)
        self._variable_link.sync()

    @property
    def variable_region(self):
        link = self._variable_link
        return link.region if link is not None else None

    @property
    def variable_region_id(self):
        region = self.variable_region
        return region.id if region is not None else None

    def set_variable(self, name: str) -> None:
        self.variable = name.strip()
        self.touch()
        self.refresh()

    def itemChange(self, change, value):
        result = super().itemChange(change, value)
        from PySide6.QtWidgets import QGraphicsItem
        if change in (QGraphicsItem.ItemParentHasChanged, QGraphicsItem.ItemSceneHasChanged,
                      QGraphicsItem.ItemPositionHasChanged,
                      QGraphicsItem.ItemRotationHasChanged) \
                and self._variable_link is not None:
            self._variable_link.sync()
        return result

    # -- painting ----------------------------------------------------------
    def paint_content(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        if self.kind == CALIBRATE:
            if len(self.points) >= 2:
                pen = QPen(QColor(self.style.stroke or "#268bd2"))
                pen.setWidthF(1.0)
                pen.setCosmetic(True)
                pen.setStyle(Qt.DashLine)
                painter.setPen(pen)
                painter.drawLine(self.points[0], self.points[-1])
            return
        path = self.build_path()
        if self.closed and self.style.paints_inside():
            filled = QPainterPath()
            filled.addPolygon(QPolygonF(self.points))
            filled.closeSubpath()
            if self.cutouts:
                filled = filled.subtracted(self.clipped_holes_path())
            painter.fillPath(filled, self.style.brush())
        if self.is_dimensioned():
            self._paint_dimension_line(painter)
        else:
            painter.setPen(self.style.pen())
            painter.setBrush(Qt.NoBrush)
            if not complexlines.draw(painter, path, self.style):
                painter.drawPath(path)

        if self.kind == ANGLE and len(self.points) >= 3:
            self._paint_angle_arc(painter)
        if self.kind in (LENGTH, CALIBRATE, DIMENSION) and len(self.points) >= 2:
            self._paint_extension_ticks(painter)
        self.paint_cutouts(painter)
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
        """The witness lines, or the ticks that stand in for them.

        A dimension line sitting on the two points it measures needs nothing
        more than a tick at each end. Pull it off them with the control dot and
        the ticks become real witness lines: they start a little clear of the
        point, so the dimension never touches what it measures, and run a
        little past the line they reach.
        """
        a, b = self.points[0], self.points[1]
        length = _distance(a, b)
        if length < 1e-6:
            return
        normal = self.dimension_normal()
        pen = self.style.pen()
        painter.setPen(pen)
        reach = self.witness_reach if self.is_dimensioned() else 0.0
        if abs(reach) < 1e-9:
            size = max(self.style.width * 3.0, 4.0)
            for point in (a, b):
                painter.drawLine(
                    QPointF(point.x() - normal.x() * size, point.y() - normal.y() * size),
                    QPointF(point.x() + normal.x() * size, point.y() + normal.y() * size))
            return
        way = 1.0 if reach > 0 else -1.0
        near = min(abs(reach), WITNESS_GAP) * way
        far = (abs(reach) + WITNESS_OVERSHOOT) * way
        for point in (a, b):
            painter.drawLine(
                QPointF(point.x() + normal.x() * near, point.y() + normal.y() * near),
                QPointF(point.x() + normal.x() * far, point.y() + normal.y() * far))

    def _paint_arrows(self, painter: QPainter) -> None:
        if len(self.points) < 2 or self.closed:
            return
        base = max(self.style.width * 4.5, 7.0)
        size = base * max(self.style.arrow_size, 0.1)
        start_size = base * max(self.style.start_size(), 0.1)
        colour = QColor(self.style.stroke)
        colour.setAlphaF(self.style.opacity)
        painter.setBrush(QBrush(colour))
        pen = QPen(colour, max(self.style.width * 0.8, 0.4))
        pen.setJoinStyle(Qt.MiterJoin)
        pen.setMiterLimit(8.0)
        painter.setPen(pen)
        if self.is_dimensioned():
            start, end = self.dimension_ends()
            if self.style.arrow_end != "none":
                draw_head(
                    painter,
                    end, math.atan2(end.y() - start.y(), end.x() - start.x()),
                    size, self.style.arrow_end)
            if self.style.arrow_start != "none":
                draw_head(
                    painter,
                    start, math.atan2(start.y() - end.y(), start.x() - end.x()),
                    start_size, self.style.arrow_start)
            return
        if self.style.arrow_end != "none":
            tip, previous = self.points[-1], self.points[-2]
            draw_head(painter, tip, math.atan2(tip.y() - previous.y(),
                                                        tip.x() - previous.x()),
                                        size, self.style.arrow_end)
        if self.style.arrow_start != "none":
            tip, following = self.points[0], self.points[1]
            draw_head(painter, tip, math.atan2(tip.y() - following.y(),
                                                        tip.x() - following.x()),
                                        start_size, self.style.arrow_start)

    def _paint_label(self, painter: QPainter) -> None:
        """The text, in line with what it measures — or on a leader if moved."""
        anchor = self._label_anchor()
        position = anchor + self.label_offset
        font = self.style.font()
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        text = self.value_text
        lines = text.split("\n")
        if len(lines) > 1:
            # Revu's caption of several values: one to a line, centred
            painter.save()
            painter.translate(position)
            painter.rotate(self.label_rotation())
            painter.setPen(QPen(self.style.text_qcolor()))
            step = metrics.height()
            top = -step * len(lines) / 2
            for row, line in enumerate(lines):
                box = QRectF(-metrics.horizontalAdvance(line) / 2 - 4, top + row * step,
                             metrics.horizontalAdvance(line) + 8, step)
                painter.drawText(box, Qt.AlignCenter, line)
            painter.restore()
            return
        width = metrics.horizontalAdvance(text) + 8
        height = metrics.height() + 4

        if self.is_dimensioned() and self.label_is_off_the_line():
            pen = QPen(QColor(self.style.stroke), max(self.style.width * 0.6, 0.4))
            pen.setStyle(Qt.SolidLine)
            painter.setPen(pen)
            painter.drawPolyline(QPolygonF(self.leader_path()))

        # Every value is written the way a dimension's is: plain words, no
        # box and no tail back to where it came from. An area's value, a
        # radius and a diameter are moved by dragging the words themselves.
        painter.save()
        painter.translate(position)
        painter.rotate(self.label_rotation())
        box = QRectF(-width / 2, -height / 2, width, height)
        painter.setPen(QPen(self.style.text_qcolor()))
        named = self._named_parts(text)
        if named is None:
            painter.drawText(box, Qt.AlignCenter, text)
        else:
            # L.beam = 6.25 m, with "beam" as a subscript — as SMath writes it
            base, sub, rest = named
            # The subscript is the same font drawn at 72%: a smaller font set
            # in points (the label's is set in pixels, so it had no point size
            # and fell back to a fixed 7 pt) came out enormous in the PDF the
            # label is written into — "beam" towering over its L in Bluebeam
            # (the user, 2026-10-01).
            shrink = 0.72
            whole = (metrics.horizontalAdvance(base) + metrics.horizontalAdvance(sub) * shrink
                     + metrics.horizontalAdvance(rest))
            x = -whole / 2
            baseline = metrics.ascent() / 2 - metrics.descent() / 2
            painter.drawText(QPointF(x, baseline), base)
            x += metrics.horizontalAdvance(base)
            painter.save()
            painter.translate(x, baseline + metrics.ascent() * 0.28)
            painter.scale(shrink, shrink)
            painter.drawText(QPointF(0, 0), sub)
            painter.restore()
            x += metrics.horizontalAdvance(sub) * shrink
            painter.drawText(QPointF(x, baseline), rest)
        painter.restore()

    def _named_parts(self, text: str):
        """(base, subscript, the rest) when the label starts with a subscripted
        variable name (L.beam = …); None otherwise."""
        name = self.variable
        if not name or "." not in name or self.custom_label or not text.startswith(name + " = "):
            return None
        base, sub = name.split(".", 1)
        return base, sub, text[len(name):]

    def leader_path(self) -> list:
        """From the dimension line out to a value that has been moved off it.

        Perpendicular away from the dimension first, then a section parallel to
        it into the text — the hinged leader a drawing uses, rather than a
        straight line cutting across at whatever angle the text ended up.
        """
        anchor = self._label_anchor()
        position = anchor + self.label_offset
        normal = self.dimension_normal()
        along = self.dimension_direction()
        away = position - anchor
        out = away.x() * normal.x() + away.y() * normal.y()
        elbow = QPointF(anchor.x() + normal.x() * out, anchor.y() + normal.y() * out)
        # The parallel section stops at the near side of the text rather than
        # running under it.
        sideways = away.x() * along.x() + away.y() * along.y()
        stop = max(abs(sideways) - self.label_rect().width() / 2, 0.0)
        way = 1.0 if sideways >= 0 else -1.0
        end = QPointF(elbow.x() + along.x() * stop * way,
                      elbow.y() + along.y() * stop * way)
        return [anchor, elbow, end]

    def _paint_dimension_line(self, painter: QPainter) -> None:
        """The dimension line, broken where the value is written across it."""
        start, end = self.dimension_ends()
        painter.setPen(self.style.pen())
        painter.setBrush(Qt.NoBrush)
        if not (self.show_label and self.value_text) or self.label_is_off_the_line():
            self._dimension_piece(painter, start, end)
            return
        along = self.dimension_direction()
        middle = (start + end) / 2
        # The break is measured off the text itself, so the line stops exactly
        # where the value starts rather than near it.
        metrics = QFontMetricsF(self.style.font())
        gap = metrics.horizontalAdvance(self.value_text) / 2 + 3.0
        span = _distance(start, end)
        if gap * 2 >= span:
            self._dimension_piece(painter, start, end)
            return
        before = QPointF(middle.x() - along.x() * gap, middle.y() - along.y() * gap)
        after = QPointF(middle.x() + along.x() * gap, middle.y() + along.y() * gap)
        self._dimension_piece(painter, start, before)
        self._dimension_piece(painter, after, end)

    def _dimension_piece(self, painter: QPainter, start: QPointF, end: QPointF) -> None:
        """One run of the dimension line, in its line style — a complex one
        (Double, Zig Zag…) drawn along it."""
        if complexlines.is_complex(self.style.line_style):
            run = QPainterPath(start)
            run.lineTo(end)
            complexlines.draw(painter, run, self.style)
            return
        painter.drawLine(start, end)

    # -- serialisation -----------------------------------------------------
    def serialize(self) -> dict:
        data = self.base_dict()
        data.update({
            "kind": self.kind,
            "points": [[round(p.x(), 3), round(p.y(), 3)] for p in self.points],
            "label_offset": [self.label_offset.x(), self.label_offset.y()],
            "label_angle": self.label_angle,
            "custom_label": self.custom_label,
            "witness_reach": round(self.witness_reach, 3),
            "depth_text": self.depth_text,
            "show_label": self.show_label,
            "cutouts": self.cutouts_as_data(),
        })
        if self.variable:
            data["variable"] = self.variable
        if self.units:
            data["units"] = dict(self.units)
        if self.caption_parts:
            data["caption_parts"] = list(self.caption_parts)
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
        self.witness_reach = float(data.get("witness_reach", 0.0) or 0.0)
        self.show_label = bool(data.get("show_label", True))
        self.variable = str(data.get("variable", "") or "")
        self.units = {str(k): str(v) for k, v in (data.get("units") or {}).items() if v}
        self.caption_parts = [str(p) for p in data.get("caption_parts") or []]
        self.cutouts_from_data(data)
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

    def index_rect(self) -> QRectF:
        """Where the number under the marker goes, sized to the number.

        It used to be a box fixed at the symbol's width and ten points tall
        whatever the font said. At the size it ships in that just fits, so the
        number looked right until somebody made it bigger — and then it was
        cut off at the bottom, and past about eleven points it was drawn
        outside the item altogether and Qt clipped it.
        """
        metrics = QFontMetricsF(self.style.font())
        text = str(self.index)
        width = max(metrics.horizontalAdvance(text) + 2.0, self.SIZE)
        rect = self.local_rect()
        return QRectF(-width / 2, rect.bottom() + 1, width, metrics.height())

    def boundingRect(self) -> QRectF:
        # The number hangs below the symbol, so the item has to own that space
        # too or it is painted outside its own rectangle and clipped.
        box = super().boundingRect()
        return box.united(self.index_rect()) if self.show_index else box

    def display_name(self) -> str:
        return self.label or f"Count · {self.subject}"

    def summary(self) -> str:
        return self.comment or f"#{self.index}"

    def hatch_region(self):
        path = QPainterPath()
        rect = self.local_rect()
        if self.symbol == "square":
            path.addRect(rect)
        else:
            path.addEllipse(rect)
        return path

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
            painter.drawText(self.index_rect(),
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
