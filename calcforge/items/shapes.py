"""Geometric markups: rectangles, ellipses, polylines, clouds, ink and highlighter."""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPolygonF

from PySide6.QtGui import QFontMetricsF

from ..core.units import Unit, format_quantity, parse_unit
from .base import (CLOUD_SIZE, HANDLE_SIZE, SELECT_BLUE, MarkupItem, Style,
                   handle_zoom, paint_control_point, paint_rotate_handle,
                   cloud_path, draw_head, register_item, round_the_joins)
from . import complexlines

# Page refreshes construct two lengths per rectangle; the unit is built once.
_MILLIMETRES = Unit((("mm", 1),))


# ---------------------------------------------------------------------------
# Paper units: what a plain shape's size is given in (Revu's "Document Width"
# and "Document Height"), following the rulers' units (ui/rulers.py).
# ---------------------------------------------------------------------------

#: Points in one of each paper unit, how it is written, and its decimals.
PAPER_UNITS = {"in": (72.0, "in", 2), "cm": (72.0 / 2.54, "cm", 2),
               "mm": (72.0 / 25.4, "mm", 1), "pt": (1.0, "pt", 1),
               "pica": (12.0, "pica", 2)}
_paper = {"unit": None}


def paper_unit() -> str:
    """The paper unit in use: the rulers' (cm until they are set)."""
    if _paper["unit"] is None:
        try:
            from ..settings import app_settings
            unit = str(app_settings().value("view/ruler_unit", "cm") or "cm")
        except Exception:  # noqa: BLE001 - no settings: the rulers' default
            unit = "cm"
        _paper["unit"] = unit if unit in PAPER_UNITS else "cm"
    return _paper["unit"]


def set_paper_unit(unit: Optional[str]) -> None:
    """The rulers changed unit (None: read it again from the settings)."""
    _paper["unit"] = unit if unit in PAPER_UNITS else None


def paper_number(points: float, unit: Optional[str] = None) -> float:
    """A length on the paper, in points, as a number of paper units."""
    return points / PAPER_UNITS[unit or paper_unit()][0]


def paper_text(points: float, unit: Optional[str] = None) -> str:
    """A length on the paper, in paper units: "4.00 cm"."""
    per, name, digits = PAPER_UNITS[unit or paper_unit()]
    return f"{points / per:.{digits}f} {name}"


def paper_points(text: str, unit: Optional[str] = None) -> Optional[float]:
    """A typed paper length as points: a bare number is in the paper unit;
    one with a unit of its own (25 mm, 2 in, 12 pt, 3 pica) is read as that."""
    import re
    stripped = (text or "").strip()
    if not stripped:
        return None
    match = re.fullmatch(r"([+]?(?:\d+(?:\.\d*)?|\.\d+))\s*([A-Za-z]*)", stripped)
    if match:
        number, name = float(match.group(1)), match.group(2).lower()
        if not name:
            return number * PAPER_UNITS[unit or paper_unit()][0]
        if name in PAPER_UNITS:
            return number * PAPER_UNITS[name][0]
        if name in ("inch", "inches"):
            return number * 72.0
    quantity = parse_unit(stripped)
    if quantity is None:
        return None
    try:
        from ..core.document import MM_TO_PT
        return float(quantity.to("mm").magnitude) * MM_TO_PT
    except Exception:  # noqa: BLE001 - not a length
        return None


#: The box-shaped markups drawn to a size: they carry it (Width and Height).
SIZED_KINDS = ("rect", "ellipse")


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
    SCALE_BOX = True

    def __init__(self, kind: str = "rect", rect: Optional[QRectF] = None,
                 to_scale: bool = False):
        super().__init__()
        self.kind = kind
        self._rect = QRectF(rect) if rect else QRectF(0, 0, 120, 70)
        self.cloud_size = CLOUD_SIZE
        # Revu's two kinds of rectangle and ellipse: the plain markup, sized
        # on the paper (Document Width and Height, in the rulers' units), and
        # Sketch to Scale's, which asks for a page scale and is sized in real
        # dimensions — 3 m × 1.5 m at 1:50 (the user, 2026-10-16).
        self.to_scale = bool(to_scale) and kind in SIZED_KINDS
        # A rectangle reports its real size when the page carries a scale, so it
        # can be used to set out an area rather than only to draw a box.
        # Off: a rectangle drawn on a drawing is a rectangle, not a dimension.
        # Its size is in the properties panel and in the markups list, and the
        # right-click menu writes it on the shape for anyone who wants it there.
        self.show_size = False
        self.size_text = ""
        self.width_value = None
        self.height_value = None
        # A Sketch to Scale shape's Units ▾ and Caption ▾, as a measurement's
        # (Revu's): its own units by "length" and "area" — one not given is
        # the page's — and which values its caption writes (empty: its size).
        self.units: dict[str, str] = {}
        self.caption_parts: list[str] = []
        self.caption_text = ""
        # Revu's Show Segment Values and Show Centroid (Sketch to Scale)
        self.segment_values = False
        self.segment_align = "segment"
        self.show_centroid = False
        self.segment_texts: list[str] = []
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
        name = {"rect": "Rectangle", "ellipse": "Ellipse", "cloud": "Cloud",
                "highlight": "Highlight", "redact": "Redaction",
                "marquee": "Snapshot region"}.get(self.kind, "Shape")
        return f"Sketch to Scale {name}" if getattr(self, "to_scale", False) else name

    def display_name(self) -> str:
        return self.label or self.NAME_FOR_KIND

    def local_rect(self) -> QRectF:
        return QRectF(self._rect)

    def set_local_rect(self, rect: QRectF) -> None:
        self._rect = QRectF(rect)

    # -- the outline, for the four corners and the four sides ---------------
    #
    # A rectangle is four corners and four sides like any other closed shape,
    # and everything offered on a polygon's outline — a point in or out, a
    # corner rounded off, a side bent into an arc, a break symbol — is offered
    # on a rectangle's. It stops being a rectangle at that moment, of course:
    # a shape with five corners, or one rounded corner, is a polygon, and that
    # is what it turns into. An ellipse has no corners and is left out.
    CORNERED = ("rect", "cloud", "highlight", "redact")

    def has_corners(self) -> bool:
        return self.kind in self.CORNERED

    def corner_points(self) -> list[QPointF]:
        """Its four corners, going round, in item coordinates."""
        box = self._rect.normalized()
        return [QPointF(box.topLeft()), QPointF(box.topRight()),
                QPointF(box.bottomRight()), QPointF(box.bottomLeft())]

    def segment_count(self) -> int:
        return 4 if self.has_corners() else 0

    def segment_ends(self, index: int) -> tuple[QPointF, QPointF]:
        corners = self.corner_points()
        return corners[index % 4], corners[(index + 1) % 4]

    # A rectangle's corners are all square and its sides are all straight —
    # that is what makes it one. The menu asks anyway, because it asks the
    # same questions of every shape, and this is the honest answer.
    def is_rounded(self, vertex: int) -> bool:
        return False

    def is_curved(self, segment: int) -> bool:
        return False

    @property
    def broken(self) -> dict:
        return {}

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        rect = self._rect.normalized()
        # a Double, Tracks or Road line is wider than its pen: picked on it
        grow = max(self.style.width, 4.0) + complexlines.reach(self.style)
        if self.kind == "ellipse":
            path.addEllipse(rect.adjusted(-grow, -grow, grow, grow))
        else:
            path.addRect(rect.adjusted(-grow, -grow, grow, grow))
        return path

    # -- real-world size ---------------------------------------------------
    def page_scale(self):
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
        """The page's scale at the middle of this shape — a viewport's there."""
        from .base import scale_where
        return scale_where(self, page, self._rect.normalized().center())

    def measures_real(self, page=None) -> bool:
        """True when its size is a real one: a Sketch to Scale shape on a
        page (or viewport) with a scale. A plain shape is always sized on
        the paper, scale or no scale."""
        if not self.to_scale:
            return False
        scale = self.scale_on(page) if page is not None else self.page_scale()
        return bool(scale.is_calibrated())

    def size_unit(self, page=None) -> str:
        """The unit its size is typed and shown in."""
        if self.measures_real(page):
            scale = self.scale_on(page) if page is not None else self.page_scale()
            return self.units.get("length") or scale.display_unit
        return PAPER_UNITS[paper_unit()][1]

    # -- Units ▾ and Caption ▾ of a Sketch to Scale shape (Revu's) ----------
    def set_unit(self, key: str, unit: str) -> None:
        if unit:
            self.units[key] = unit
        else:
            self.units.pop(key, None)

    def primary_part(self) -> str:
        return "dimensions"

    def caption_choices(self) -> tuple:
        """What its Caption ▾ offers: its label, its size, area and perimeter."""
        return ("label", "dimensions", "area", "perimeter") if self.to_scale else ()

    def caption_available(self, part: str) -> bool:
        return part in self.caption_choices()

    def caption_shown(self) -> list:
        if not self.caption_parts:
            return [self.primary_part()]
        order = list(self.caption_choices())
        return sorted((p for p in self.caption_parts if p in order), key=order.index)

    def set_caption_part(self, part: str, on: bool) -> None:
        shown = set(self.caption_shown())
        if on:
            shown.add(part)
        else:
            shown.discard(part)
        if not shown - {"label"}:
            shown.add(self.primary_part())        # never a caption of nothing
        order = list(self.caption_choices())
        parts = sorted((p for p in shown if p in order), key=order.index)
        self.caption_parts = [] if parts == [self.primary_part()] else parts

    # -- Show Segment Values and Show Centroid (Revu's) ----------------------
    def offers_segments(self) -> bool:
        return bool(self.to_scale) and self.kind == "rect"

    def offers_centroid(self) -> bool:
        return bool(self.to_scale) and self.kind in SIZED_KINDS

    def segment_runs(self) -> list:
        corners = self.corner_points()
        return [(corners[i], corners[(i + 1) % 4]) for i in range(4)]

    def inside_region(self):
        region = self.hatch_region()
        if region is None and self.kind in SIZED_KINDS:
            region = self.outline_path()
        return region

    def centroid_point(self):
        from .segments import centroid_of
        holes = self.clipped_holes_path() if self.cutouts else None
        return centroid_of(self.outline_path(), self.corner_points(), holes)

    def _work_out_segments(self, page=None) -> None:
        """Each side's length: across, down, across, down."""
        self.segment_texts = []
        if not self.offers_segments():
            return
        if self.measures_real(page) and self.width_value is not None:
            scale = self.scale_on(page) if page is not None else self.page_scale()
            digits = max(scale.precision, 0)
            wide = format_quantity(self.width_value, digits, "fixed")
            high = format_quantity(self.height_value, digits, "fixed")
        else:
            rect = self._rect.normalized()
            wide, high = paper_text(rect.width()), paper_text(rect.height())
        self.segment_texts = [wide, high, wide, high]

    def _paint_extras(self, painter: QPainter) -> None:
        from .segments import paint_centroid, paint_values
        if self.segment_values and self.offers_segments():
            paint_values(painter, self.style, self.segment_runs(), self.segment_texts,
                         self.segment_align, self._rect.normalized().center())
        if self.show_centroid and self.offers_centroid():
            paint_centroid(painter, self.style, self.centroid_point())

    def _raw_area(self) -> float:
        """What it covers, in square points, its cut-outs taken out."""
        rect = self._rect.normalized()
        path = QPainterPath()
        if self.kind == "ellipse":
            path.addEllipse(rect)
        elif self.style.corner_radius > 0:
            path.addRoundedRect(rect, self.style.corner_radius, self.style.corner_radius)
        else:
            path.addRect(rect)
        from .segments import path_area
        total = path_area(path)
        if self.cutouts:
            # less what its holes take out of it (each hole a ring of its own)
            total -= path_area(path.intersected(self.clipped_holes_path()))
        return max(total, 0.0)

    def area_value(self, page=None):
        """Its real area, in its own area unit or the page's — None when the
        page has no scale (Revu's Scale Not Set)."""
        if not self.measures_real(page):
            return None
        from ..core.units import convert
        scale = self.scale_on(page) if page is not None else self.page_scale()
        try:
            return convert(scale.area(self._raw_area()),
                           self.units.get("area") or scale.area_unit)
        except Exception:  # noqa: BLE001 - a scale whose units do not convert
            return None

    def perimeter_value(self, page=None):
        """Its real perimeter (an ellipse's by Ramanujan), or None unscaled."""
        if not self.measures_real(page):
            return None
        from ..core.units import convert
        scale = self.scale_on(page) if page is not None else self.page_scale()
        rect = self._rect.normalized()
        try:
            wide = scale.length(rect.width())
            high = scale.height(rect.height())
            if self.kind == "ellipse":
                a, b = wide / 2, high / 2
                around = math.pi * (3 * (a + b) - ((3 * a + b) * (a + 3 * b)) ** 0.5)
            else:
                around = 2 * (wide + high)
            return convert(around, self.units.get("length") or scale.display_unit)
        except Exception:  # noqa: BLE001
            return None

    def _caption(self, page=None) -> str:
        """The words Caption ▾ asks for: its size, or the values picked."""
        shown = self.caption_shown()
        if shown == ["dimensions"] or not self.to_scale:
            return self.size_text
        scale = self.scale_on(page) if page is not None else self.page_scale()
        digits = max(getattr(scale, "precision", 2), 0)
        several = len([p for p in shown if p != "label"]) > 1
        lines = []
        for part in shown:
            if part == "label":
                if self.label:
                    lines.append(self.label)
                continue
            if part == "dimensions":
                text = self.size_text
            else:
                value = self.area_value(page) if part == "area" else self.perimeter_value(page)
                text = format_quantity(value, digits, "fixed") if value is not None else ""
            if text:
                short = {"dimensions": "", "area": "A = ", "perimeter": "P = "}[part]
                lines.append(f"{short if several else ''}{text}")
        return "  ".join(lines) or self.size_text

    def refresh(self, workspace=None, page=None) -> None:
        """Work out the size to write on the rectangle.

        A Sketch to Scale shape on a scaled page gives real dimensions; a
        plain one — and a sketch on a page with no scale — gives its size on
        the paper, in the rulers' units (Revu's Document Width and Height).
        """
        rect = self._rect.normalized()
        # A rectangle and an ellipse are both drawn to a size somebody cares
        # about; a cloud or a highlight is drawn around something else.
        if self.kind not in SIZED_KINDS:
            self.size_text = ""
            self.width_value = self.height_value = None
            self.update()
            return
        try:
            from ..core.units import Q_, convert
            from ..core.document import MM_TO_PT
            scale = None
            if self.to_scale:
                scale = self.scale_on(page) if page is not None else self.page_scale()
            if scale is not None and scale.is_calibrated():
                unit = self.units.get("length") or scale.display_unit   # Units ▾
                self.width_value = convert(scale.length(rect.width()), unit)
                self.height_value = convert(scale.height(rect.height()), unit)
                digits = max(scale.precision, 0)
                if hasattr(scale, "format_length"):
                    # to the scale's Precision, a fraction or decimals (Set Scale)
                    self.size_text = (f"{scale.format_length(self.width_value, digits)}"
                                      f" × {scale.format_length(self.height_value, digits)}")
                else:
                    self.size_text = (f"{format_quantity(self.width_value, digits, 'fixed')}"
                                      f" × {format_quantity(self.height_value, digits, 'fixed')}")
            else:
                self.width_value = Q_(rect.width() / MM_TO_PT, _MILLIMETRES)
                self.height_value = Q_(rect.height() / MM_TO_PT, _MILLIMETRES)
                self.size_text = f"{paper_text(rect.width())} × {paper_text(rect.height())}"
        except Exception:
            self.size_text = ""
            self.width_value = self.height_value = None
        try:
            self.caption_text = self._caption(page)
        except Exception:  # noqa: BLE001 - a caption is never worth a crash
            self.caption_text = self.size_text
        try:
            self._work_out_segments(page)
        except Exception:  # noqa: BLE001
            self.segment_texts = []
        self.update()

    def size_texts(self, page=None) -> tuple[str, str]:
        """Its width and height as they are shown and typed: real ones with
        the scale's unit, or paper ones in the rulers' unit."""
        rect = self._rect.normalized()
        if self.measures_real(page):
            self.refresh(page=page)
            scale = self.scale_on(page) if page is not None else self.page_scale()
            digits = max(scale.precision, 0)
            return (format_quantity(self.width_value, digits, "fixed"),
                    format_quantity(self.height_value, digits, "fixed"))
        return paper_text(rect.width()), paper_text(rect.height())

    def set_real_size(self, width_text: str, height_text: str, page=None) -> bool:
        """Resize to an exact width and height: real-world ones for a Sketch
        to Scale shape on a scaled page, paper ones otherwise."""
        scale = self.scale_on(page) if page is not None else self.page_scale()
        try:
            if self.measures_real(page):
                width = parse_unit(width_text)
                height = parse_unit(height_text)
                if width is None or height is None:
                    return False
                per_point = scale.length(1.0)
                points_wide = float((width / per_point).to("dimensionless").magnitude)
                points_high = float((height / per_point).to("dimensionless").magnitude) \
                    / (getattr(scale, "y_factor", 1.0) or 1.0)
            else:
                points_wide = paper_points(width_text)
                points_high = paper_points(height_text)
                if points_wide is None or points_high is None:
                    return False
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
        if self.segment_values and self.offers_segments():
            from .segments import reach
            more = reach(self.style, self.segment_texts)
            rect = rect.adjusted(-more, -more, more, more)
        if self.show_size and self.size_text:
            under = self.style.font_size + 6
            if self.segment_values and self.offers_segments():
                under += self.style.font_size * 1.4 + 2      # below the bottom's length
            rect = rect.adjusted(0, 0, 0, under)
            words = self._shown_size()
            if words != self.size_text:
                # a longer caption (its area, its perimeter) reaches wider
                from ..core.typography import set_size
                font = set_size(self.style.font(), max(self.style.font_size * 0.82, 5.0))
                spare = (QFontMetricsF(font).horizontalAdvance(words) - rect.width()) / 2
                if spare > 0:
                    rect = rect.adjusted(-spare, 0, spare, 0)
        return rect

    def _shown_size(self) -> str:
        """What is written under it: its caption, or its size."""
        return self.caption_text or self.size_text

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

    def hatch_region(self) -> Optional[QPainterPath]:
        if self.kind not in ("rect", "ellipse", "cloud"):
            return None
        rect = self._rect.normalized()
        path = QPainterPath()
        if self.kind == "ellipse":
            path.addEllipse(rect)
        elif self.kind == "cloud":
            path = cloud_path(QPolygonF([rect.topLeft(), rect.topRight(),
                                         rect.bottomRight(), rect.bottomLeft()]),
                              self.cloud_radius, inverted=self.cloud_invert)
            path.closeSubpath()
        elif self.style.corner_radius > 0:
            path.addRoundedRect(rect, self.style.corner_radius, self.style.corner_radius)
        else:
            path.addRect(rect)
        if self.cutouts:
            path = path.subtracted(self.clipped_holes_path())
        return path

    def paint_content(self, painter: QPainter) -> None:
        rect = self._rect.normalized()
        painter.setRenderHint(QPainter.Antialiasing, True)
        if self.kind == "marquee":
            # The selection marquee, dashed: a one-pixel line whatever the
            # zoom, never the pen of whatever rectangle was drawn last.
            pen = QPen(QColor("#1971c2"))
            pen.setWidthF(0)
            pen.setCosmetic(True)
            pen.setStyle(Qt.DashLine)
            painter.setPen(pen)
            fill = QColor("#1971c2")
            fill.setAlpha(28)
            painter.setBrush(fill)
            painter.drawRect(rect)
            return
        pen = self.style.pen() if self.style.stroke else QPen(Qt.NoPen)
        painter.setPen(pen)
        painter.setBrush(self.style.brush())
        if self.cutouts and self.style.paints_inside() and self.kind in ("rect", "ellipse"):
            # A hole in a filled shape has to be a hole in the fill, or the
            # only sign of it is the dashed outline sitting on solid colour.
            solid = QPainterPath()
            if self.kind == "ellipse":
                solid.addEllipse(rect)
            elif self.style.corner_radius > 0:
                solid.addRoundedRect(rect, self.style.corner_radius,
                                     self.style.corner_radius)
            else:
                solid.addRect(rect)
            painter.fillPath(solid.subtracted(self.clipped_holes_path()),
                             self.style.brush())
            painter.setBrush(Qt.NoBrush)
        if complexlines.is_complex(self.style.line_style) and self.style.stroke:
            # Revu's complex lines (Double, Gas, Zig Zag…) along the outline
            outline = QPainterPath()
            if self.kind == "ellipse":
                outline.addEllipse(rect)
            elif self.kind == "cloud":
                outline = cloud_path(QPolygonF([rect.topLeft(), rect.topRight(),
                                                rect.bottomRight(), rect.bottomLeft()]),
                                     self.cloud_radius, inverted=self.cloud_invert)
            elif self.style.corner_radius > 0:
                outline.addRoundedRect(rect, self.style.corner_radius,
                                       self.style.corner_radius)
            else:
                outline.addRect(rect)
            complexlines.draw(painter, outline, self.style)
        elif self.kind == "ellipse":
            painter.drawEllipse(rect)
        elif self.kind == "cloud":
            polygon = QPolygonF([rect.topLeft(), rect.topRight(),
                                 rect.bottomRight(), rect.bottomLeft()])
            path = cloud_path(polygon, self.cloud_radius, inverted=self.cloud_invert)
            if self.style.paints_inside():
                filled = QPainterPath(path)
                filled.closeSubpath()
                painter.fillPath(filled, self.style.brush())
            painter.setBrush(Qt.NoBrush)
            round_the_joins(painter)
            painter.drawPath(path)
        elif self.style.corner_radius > 0:
            painter.drawRoundedRect(rect, self.style.corner_radius, self.style.corner_radius)
        else:
            painter.drawRect(rect)
        self.paint_cutouts(painter)
        self._paint_extras(painter)
        if self.show_size and self.size_text:
            self._paint_size(painter, rect)

    def outline_ring(self) -> list:
        """A rectangle, a rounded rectangle and an ellipse all enclose something."""
        rect = self._rect.normalized()
        if rect.width() <= 0 or rect.height() <= 0:
            return []
        if self.kind == "ellipse":
            steps = 48
            centre, rx, ry = rect.center(), rect.width() / 2, rect.height() / 2
            return [QPointF(centre.x() + math.cos(2 * math.pi * i / steps) * rx,
                            centre.y() + math.sin(2 * math.pi * i / steps) * ry)
                    for i in range(steps)]
        if self.kind in ("rect", "cloud"):
            return [rect.topLeft(), rect.topRight(),
                    rect.bottomRight(), rect.bottomLeft()]
        return []

    def outline_path(self) -> QPainterPath:
        """Use the exact visible outline when clipping holes."""
        path = QPainterPath()
        rect = self._rect.normalized()
        if self.kind == "ellipse":
            path.addEllipse(rect)
        elif self.kind == "rect" and self.style.corner_radius > 0:
            path.addRoundedRect(rect, self.style.corner_radius,
                                self.style.corner_radius)
        elif self.kind in ("rect", "cloud"):
            path.addRect(rect)
        return path

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
        if self.segment_values and self.offers_segments():
            # below the bottom side's own length, not over it
            from .segments import text_font
            gap += QFontMetricsF(text_font(self.style)).height() + 1.0
        words = self._shown_size()
        box = QRectF(rect.center().x() - metrics.horizontalAdvance(words) / 2,
                     rect.bottom() + gap,
                     metrics.horizontalAdvance(words), metrics.height())
        painter.setPen(QPen(QColor(self.style.stroke or self.style.text_color)))
        painter.setBrush(Qt.NoBrush)
        painter.drawText(box, Qt.AlignCenter, words)
        painter.restore()

    def serialize(self) -> dict:
        data = self.base_dict()
        data.update({"kind": self.kind, "rect": [self._rect.x(), self._rect.y(),
                                                 self._rect.width(), self._rect.height()],
                     "show_size": self.show_size})
        if self.to_scale:
            data["to_scale"] = True
            if self.units:
                data["units"] = dict(self.units)
            if self.caption_parts:
                data["caption_parts"] = list(self.caption_parts)
            from .measure import _extras_to
            _extras_to(self, data)
        self.cloud_to_dict(data)
        if self.cutouts:
            data["cutouts"] = self.cutouts_as_data()
        return data

    def deserialize(self, data: dict) -> None:
        self.kind = data.get("kind", "rect")
        values = data.get("rect", [0, 0, 100, 60])
        self._rect = QRectF(*values)
        self.show_size = bool(data.get("show_size", False))
        # written before Sketch to Scale existed: a plain shape
        self.to_scale = bool(data.get("to_scale", False)) and self.kind in SIZED_KINDS
        self.units = {str(k): str(v) for k, v in (data.get("units") or {}).items() if v}
        self.caption_parts = [str(p) for p in (data.get("caption_parts") or [])]
        from .measure import _extras_from
        _extras_from(self, data)
        self.cutouts_from_data(data)
        self.load_base(data)
        self.cloud_from_dict(data)


# ---------------------------------------------------------------------------
# Point-based shapes
# ---------------------------------------------------------------------------

def _arc_through(points: list[QPointF]) -> QPointF:
    """The visible bend point for an Arc, explicit or naturally inferred."""
    start, end = points[0], points[-1]
    if len(points) >= 3:
        return QPointF(points[1])
    middle = QPointF((start.x() + end.x()) / 2, (start.y() + end.y()) / 2)
    dx, dy = end.x() - start.x(), end.y() - start.y()
    length = math.hypot(dx, dy) or 1.0
    bow = length * 0.22
    return QPointF(middle.x() - dy / length * bow,
                   middle.y() + dx / length * bow)


def _arc_path(points: list[QPointF]) -> QPainterPath:
    """A curve through its endpoints and editable bend point."""
    start, end = points[0], points[-1]
    through = _arc_through(points)
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
        self.cloud_size = CLOUD_SIZE
        self.smooth = kind in ("ink", "highlighter")
        # A shape does not have to be all straight lines. Each corner can be
        # rounded off, each segment can be bowed into an arc, and any segment
        # can carry a drafting break symbol — the three things a structural
        # drawing needs and a plain polygon cannot do.
        #
        # rounded: vertex index -> the radius of that corner, in points.
        # curved:  segment index -> (how far it bows, where the apex sits
        #          along it from 0 to 1). Two numbers, so an arc has the two
        #          handles Bluebeam's has: one for the depth of the curve and
        #          one for where it leans.
        # broken:  segment index -> True, for the break symbol.
        self.rounded: dict[int, float] = {}
        self.curved: dict[int, tuple[float, float]] = {}
        # bezier:  segment index -> its two control points exactly, as
        #          Bluebeam's /Curves gives them: a section's rounded root
        #          is a cubic curve, and a quadratic bow is only near it.
        self.bezier: dict[int, tuple[QPointF, QPointF]] = {}
        self.broken: dict[int, bool] = {}
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

    def has_scale_box(self) -> bool:
        """Polygons, polylines and clouds have Bluebeam's scale box; a
        line, an arrow or an arc has its two ends and nothing else."""
        return (self.kind in ("polyline", "polygon", "cloud") and len(self.points) > 2
                and not self.locked)

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
        def moved(p: QPointF) -> QPointF:
            return QPointF(rect.x() + (p.x() - old.x()) * sx,
                           rect.y() + (p.y() - old.y()) * sy)
        self.points = [moved(p) for p in self.points]
        self.bezier = {side: (moved(a), moved(b)) for side, (a, b) in self.bezier.items()}

    # -- corners, curves and breaks ----------------------------------------
    def corner_points(self) -> list[QPointF]:
        """Its corners, going round — the same question a rectangle answers."""
        return self.points

    @classmethod
    def from_rectangle(cls, box) -> "PolyItem":
        """The same shape, drawn as a polygon rather than as a rectangle.

        What comes back stands exactly where the rectangle stood and looks
        exactly like it — but it has four corners that can be moved, taken
        out, added to, rounded off or bent, which a rectangle has not. A cloud
        stays a cloud; everything else becomes a plain polygon.
        """
        kind = "cloud" if box.kind == "cloud" else "polygon"
        # an ellipse goes round its curve closely, as Revu's conversion does
        # (exercise round 1, F-10: it gave the bounding box)
        # — 32 vertices, few enough that each keeps its own handle
        if box.kind == "ellipse":
            rect = box.local_rect().normalized()
            centre, rx, ry = rect.center(), rect.width() / 2, rect.height() / 2
            points = [QPointF(centre.x() + math.cos(2 * math.pi * i / 32) * rx,
                              centre.y() + math.sin(2 * math.pi * i / 32) * ry)
                      for i in range(32)]
        else:
            points = box.corner_points()
        shape = cls(kind, [QPointF(p) for p in points])
        shape.style = box.style.copy()
        shape.cloud_size = box.cloud_size
        shape.cloud_invert = box.cloud_invert
        shape.from_drawing = box.from_drawing
        shape.author = box.author
        shape.label = box.label
        shape.locked = box.locked
        shape.printable = box.printable
        shape.setPos(box.pos())
        shape.setTransformOriginPoint(box.transformOriginPoint())   # turned about the same point
        shape.setRotation(box.rotation())
        shape.setZValue(box.zValue())
        return shape

    def segment_count(self) -> int:
        """How many segments the shape has, the closing one included."""
        if len(self.points) < 2:
            return 0
        return len(self.points) if self.closed else len(self.points) - 1

    def segment_ends(self, index: int) -> tuple[QPointF, QPointF]:
        """The two ends of segment *index*."""
        start = self.points[index % len(self.points)]
        end = self.points[(index + 1) % len(self.points)]
        return QPointF(start), QPointF(end)

    def is_rounded(self, vertex: int) -> bool:
        return self.rounded.get(vertex, 0.0) > 0.01

    def is_curved(self, segment: int) -> bool:
        return abs(self.curved.get(segment, (0.0, 0.5))[0]) > 0.01

    def round_corner(self, vertex: int, radius: Optional[float] = None) -> None:
        """Round this corner off, or sharpen it again."""
        self.prepareGeometryChange()
        if radius is None:
            radius = 0.0 if self.is_rounded(vertex) else self._natural_radius(vertex)
        if radius <= 0.01:
            self.rounded.pop(vertex, None)
        else:
            self.rounded[vertex] = float(radius)
        self.touch()
        self.geometryChanged.emit()

    def curve_segment(self, segment: int, bow: Optional[float] = None,
                      along: Optional[float] = None) -> None:
        """Bow this segment into an arc, or straighten it again."""
        self.prepareGeometryChange()
        current = self.curved.get(segment, (0.0, 0.5))
        if bow is None:
            bow = 0.0 if self.is_curved(segment) else self._natural_bow(segment)
        if along is None:
            along = current[1]
        if abs(bow) <= 0.01:
            self.curved.pop(segment, None)
        else:
            self.curved[segment] = (float(bow), max(0.1, min(0.9, float(along))))
        self.touch()
        self.geometryChanged.emit()

    def break_segment(self, segment: int, wanted: Optional[bool] = None) -> None:
        """Put the drafting break symbol on this segment, or take it off."""
        self.prepareGeometryChange()
        if wanted is None:
            wanted = not self.broken.get(segment)
        if wanted:
            self.broken[segment] = True
        else:
            self.broken.pop(segment, None)
        self.touch()
        self.geometryChanged.emit()

    def _natural_radius(self, vertex: int) -> float:
        """A first radius that suits the corner: a fifth of its shorter edge."""
        if len(self.points) < 3:
            return 8.0
        before = self.points[(vertex - 1) % len(self.points)]
        corner = self.points[vertex % len(self.points)]
        after = self.points[(vertex + 1) % len(self.points)]
        reach = min(_distance(before, corner), _distance(corner, after))
        return max(min(reach / 5.0, 40.0), 2.0)

    def _natural_bow(self, segment: int) -> float:
        """A first bow that reads as a curve: a fifth of the segment."""
        start, end = self.segment_ends(segment)
        return max(_distance(start, end) * 0.2, 4.0)

    def curve_apex(self, segment: int) -> QPointF:
        """Where a bowed segment reaches out to."""
        start, end = self.segment_ends(segment)
        bow, along = self.curved.get(segment, (0.0, 0.5))
        return _offset_along(start, end, along, bow)

    def curve_lean(self, segment: int) -> QPointF:
        """The second handle: it slides the apex along the segment."""
        start, end = self.segment_ends(segment)
        bow, along = self.curved.get(segment, (0.0, 0.5))
        return _offset_along(start, end, along, bow * 0.45)

    def radius_handle(self, vertex: int) -> QPointF:
        """The handle that sets a rounded corner's radius."""
        radius = self.rounded.get(vertex, 0.0)
        corner = self.points[vertex % len(self.points)]
        before = self.points[(vertex - 1) % len(self.points)]
        after = self.points[(vertex + 1) % len(self.points)]
        inward = _unit(_towards(corner, before)) + _unit(_towards(corner, after))
        length = math.hypot(inward.x(), inward.y())
        if length < 1e-6:
            inward, length = QPointF(0, 1), 1.0
        reach = radius * 1.15 + 2
        return QPointF(corner.x() + inward.x() / length * reach,
                       corner.y() + inward.y() / length * reach)

    def _path_signature(self) -> tuple:
        """Everything the outline is made from. Qt asks for a markup's
        bounding box thousands of times a frame, and a cloud's arcs were
        worked out afresh every time — the main cost of dragging on a sheet
        full of somebody's clouds (Calcs.pdf, 2026-10-01)."""
        # the points themselves: compared by value, in C++, one by one (nothing
        # moves a point in place; a moved point is a new one)
        return (self.kind, tuple(self.points), self.cloud_radius, self.cloud_invert,
                self.smooth, self.closed, repr(sorted(self.rounded.items())),
                repr(sorted(self.curved.items())), repr(sorted(self.broken.items())),
                repr(sorted(self.bezier.items())), self.style.width)

    def build_path(self) -> QPainterPath:
        """The shape's geometry, with its rounded corners and its curves
        (worked out once for each shape it has; see _path_signature)."""
        signature = self._path_signature()
        cached = self.__dict__.get("_path_cache")
        if cached is not None and cached[0] == signature:
            return QPainterPath(cached[1])
        path = self._build_path()
        self._path_cache = (signature, QPainterPath(path))
        return path

    def _build_path(self) -> QPainterPath:
        path = QPainterPath()
        if len(self.points) < 2:
            if self.points:
                path.addEllipse(self.points[0], 0.6, 0.6)
            return path
        if self.kind == "cloud":
            return cloud_path(QPolygonF(self.points), self.cloud_radius, closed=True,
                              inverted=self.cloud_invert)
        if self.kind == "arc" and len(self.points) >= 2:
            return _arc_path(self.points)
        if self.smooth:
            path = _smooth_path(self.points)
            if self.closed:
                path.closeSubpath()
            return path
        if not self.rounded and not self.curved and not self.broken and not self.bezier:
            path.moveTo(self.points[0])
            for point in self.points[1:]:
                path.lineTo(point)
            if self.closed:
                path.closeSubpath()
            return path
        return self._shaped_path()

    def _shaped_path(self) -> QPainterPath:
        """Walk the shape segment by segment, rounding and bowing as told.

        A rounded corner eats a little off the end of each edge that meets
        it and turns through the gap; a bowed segment is a curve through the
        point its handles put out to the side. Everything else is a line.
        """
        path = QPainterPath()
        count = self.segment_count()
        first_start, _ = self.segment_ends(0)
        path.moveTo(self._corner_exit(0, first_start))
        for index in range(count):
            start, end = self.segment_ends(index)
            leaves = self._corner_exit(index, start)
            arrives = self._corner_entry(index, end)
            if index in self.bezier:
                first, second = self.bezier[index]
                path.cubicTo(first, second, arrives)
            elif self.is_curved(index):
                apex = self.curve_apex(index)
                control = QPointF(2 * apex.x() - (leaves.x() + arrives.x()) / 2,
                                  2 * apex.y() - (leaves.y() + arrives.y()) / 2)
                path.quadTo(control, arrives)
            elif self.broken.get(index):
                width, height, position = self.break_settings(index)
                jink = _break_symbol(leaves, arrives, width, height, position)
                if jink.isEmpty():
                    path.lineTo(arrives)
                else:
                    path.connectPath(jink)
            else:
                path.lineTo(arrives)
            # Turn the corner at the far end, when it is rounded and there is
            # another segment to turn into.
            vertex = (index + 1) % len(self.points)
            if self.is_rounded(vertex) and (self.closed or index < count - 1):
                path.quadTo(end, self._corner_exit(index + 1, end))
        if self.closed:
            path.closeSubpath()
        return path

    def break_size(self) -> float:
        """How big the break symbol is drawn: with the line, not fixed."""
        return max(self.style.width * 2.4, 5.0)

    def break_settings(self, segment: int) -> tuple[float, float, float]:
        value = self.broken.get(segment)
        if isinstance(value, (list, tuple)):
            if len(value) == 3:
                return tuple(value)
            if len(value) == 2:
                return (value[0] * 2.8, value[0] * 2, value[1])
        size = self.break_size()
        return (size * 2.8, size * 2, 0.5)

    def set_break_settings(self, segment: int, width: float, height: float,
                           position: float) -> None:
        self.prepareGeometryChange()
        self.broken[segment] = (max(1.4, float(width)), max(1.0, float(height)),
                                max(0.05, min(0.95, float(position))))
        self.touch()
        self.geometryChanged.emit()

    def _corner_exit(self, segment: int, start: QPointF) -> QPointF:
        """Where a segment starts, allowing for a rounded corner behind it."""
        vertex = segment % len(self.points)
        radius = self.rounded.get(vertex, 0.0)
        if radius <= 0.01 or (not self.closed and segment == 0):
            return QPointF(start)
        _, end = self.segment_ends(segment)
        return _towards_by(start, end, min(radius, _distance(start, end) / 2.2))

    def _corner_entry(self, segment: int, end: QPointF) -> QPointF:
        """Where a segment stops, allowing for a rounded corner ahead of it."""
        vertex = (segment + 1) % len(self.points)
        radius = self.rounded.get(vertex, 0.0)
        last = (not self.closed and segment == self.segment_count() - 1)
        if radius <= 0.01 or last:
            return QPointF(end)
        start, _ = self.segment_ends(segment)
        return _towards_by(end, start, min(radius, _distance(start, end) / 2.2))

    def shape(self) -> QPainterPath:
        from PySide6.QtGui import QPainterPathStroker
        signature = (self._path_signature(), self.style.paints_inside(),
                     complexlines.reach(self.style))
        cached = self.__dict__.get("_shape_cache")
        if cached is not None and cached[0] == signature:
            return QPainterPath(cached[1])
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self.style.width, 6.0) + 4 + 2 * complexlines.reach(self.style))
        stroker.setCapStyle(Qt.RoundCap)
        outline = self.build_path()
        path = stroker.createStroke(outline)
        if self.closed and self.style.paints_inside():
            path.addPath(outline)
        self._shape_cache = (signature, QPainterPath(path))
        return path

    def boundingRect(self) -> QRectF:
        margin = self.style.width + HANDLE_SIZE + 12 + complexlines.reach(self.style)
        rect = self.local_rect().united(self.build_path().boundingRect())
        return self._with_scale_box(rect.adjusted(-margin, -margin, margin, margin))

    # -- handles -----------------------------------------------------------
    def handle_half_px(self, key: str) -> float:
        """A break's width and height handles are drawn as larger squares."""
        if key[:1] in ("w", "z") and key[1:].isdigit():
            return 3.5
        return super().handle_half_px(key)

    def handle_points(self) -> dict[str, QPointF]:
        if self.uses_vertex_handles:
            if self.kind == "arc" and len(self.points) >= 2:
                # Arc endpoints remain ordinary vertices. Its middle control
                # point is always visible, even before the inferred bend has
                # been moved and stored explicitly.
                return {"v0": QPointF(self.points[0]),
                        f"v{len(self.points) - 1}": QPointF(self.points[-1]),
                        "c0": _arc_through(self.points)}
            handles = {f"v{index}": QPointF(point) for index, point in enumerate(self.points)}
            # A rounded corner gets a handle for its radius, and a bowed
            # segment gets two: how far it curves, and which way it leans.
            for vertex in sorted(self.rounded):
                if 0 <= vertex < len(self.points) and self.is_rounded(vertex):
                    handles[f"r{vertex}"] = self.radius_handle(vertex)
            for segment in sorted(self.curved):
                if 0 <= segment < self.segment_count() and self.is_curved(segment):
                    handles[f"c{segment}"] = self.curve_apex(segment)
                    handles[f"n{segment}"] = self.curve_lean(segment)
            for segment in sorted(self.broken):
                if 0 <= segment < self.segment_count():
                    start, end = self.segment_ends(segment)
                    width, height, position = self.break_settings(segment)
                    centre = start + (end - start) * position
                    direction = _unit(end - start)
                    handles[f"b{segment}"] = centre
                    handles[f"w{segment}"] = centre + direction * (width / 2)
                    handles[f"z{segment}"] = centre + QPointF(-direction.y(), direction.x()) * (height / 2)
            if self.kind in ("polyline", "polygon", "cloud") and len(self.points) > 2:
                rect = self.local_rect()
                top = self.scale_box().top() if self.has_scale_box() else rect.top()
                handles["rot"] = QPointF(rect.center().x(), top - 22)
            return handles
        return super().handle_points()

    def move_handle(self, key: str, local_pos: QPointF, keep_ratio: bool = False) -> None:
        if key.startswith(("b", "w", "z")) and key[1:].isdigit():
            segment = int(key[1:])
            if segment in self.broken:
                start, end = self.segment_ends(segment)
                width, height, position = self.break_settings(segment)
                along, sideways = _project(start, end, local_pos)
                if key[0] == "w":
                    width = 2 * abs(along - position) * _distance(start, end)
                elif key[0] == "z":
                    height = 2 * abs(sideways)
                else:
                    position = along
                self.set_break_settings(segment, width, height, position)
                return
        if self.kind == "arc" and key == "c0" and len(self.points) >= 2:
            self.prepareGeometryChange()
            if len(self.points) == 2:
                self.points.insert(1, QPointF(local_pos))
            else:
                self.points[1] = QPointF(local_pos)
            self.touch()
            self.geometryChanged.emit()
            return
        if key.startswith("v"):
            index = int(key[1:])
            if 0 <= index < len(self.points):
                if keep_ratio and len(self.points) >= 2:
                    anchor = self.points[index - 1] if index else self.points[1]
                    local_pos = _constrain(anchor, local_pos)
                self.prepareGeometryChange()
                moved = QPointF(local_pos) - self.points[index]
                self.points[index] = QPointF(local_pos)
                # A curved side's handle at this corner goes with the corner.
                if self.bezier:
                    count = self.segment_count()
                    after, before = index, (index - 1) % max(len(self.points), 1)
                    if after in self.bezier and after < count:
                        first, second = self.bezier[after]
                        self.bezier[after] = (first + moved, second)
                    if before in self.bezier and before < count and \
                            (before + 1) % len(self.points) == index:
                        first, second = self.bezier[before]
                        self.bezier[before] = (first, second + moved)
                self.touch()
                self.geometryChanged.emit()
            return
        if key.startswith("r") and key != "rot":
            # The radius controller: how far from the corner it is dragged is
            # how big the rounding is.
            vertex = int(key[1:]) % max(len(self.points), 1)
            corner = self.points[vertex]
            self.round_corner(vertex, max(_distance(corner, local_pos) - 2, 0.0) / 1.15)
            return
        if key.startswith("c") or key.startswith("n"):
            # The two arc handles. The first says how deep the curve is and
            # where its apex sits; the second only slides the apex along.
            segment = int(key[1:])
            if not 0 <= segment < self.segment_count():
                return
            start, end = self.segment_ends(segment)
            along, sideways = _project(start, end, local_pos)
            bow, was = self.curved.get(segment, (0.0, 0.5))
            if key.startswith("c"):
                self.curve_segment(segment, sideways, along)
            else:
                self.curve_segment(segment, bow, along)
            return
        super().move_handle(key, local_pos, keep_ratio)

    def insert_point(self, local_pos: QPointF) -> int:
        """Insert a vertex on the nearest side; returns its index.

        Every side, the closing one included: a point put on the bottom edge
        of a four-cornered shape used to be inserted somewhere up the side,
        because the run back to the first corner was not looked at.
        """
        best_segment, best_distance = 0, float("inf")
        for segment in range(self.segment_count()):
            start, end = self.segment_ends(segment)
            distance = _segment_distance(start, end, local_pos)
            if distance < best_distance:
                best_distance, best_segment = distance, segment
        where = best_segment + 1
        self.prepareGeometryChange()
        self.points.insert(where, QPointF(local_pos))
        # Everything remembered about a corner or a side is remembered by its
        # number, and every number after this one has just moved along. The
        # side that was split is not either of the two halves, so whatever it
        # was carrying goes with it.
        self.rounded = {(vertex if vertex < where else vertex + 1): radius
                        for vertex, radius in self.rounded.items()}
        self.curved = {(side if side < best_segment else side + 1): bow
                       for side, bow in self.curved.items() if side != best_segment}
        self.bezier = {(side if side < best_segment else side + 1): pair
                       for side, pair in self.bezier.items() if side != best_segment}
        self.broken = {(side if side < best_segment else side + 1): on
                       for side, on in self.broken.items() if side != best_segment}
        self.geometryChanged.emit()
        return where

    def delete_point(self, index: int) -> None:
        """Take a corner out, and everything that was hanging off it."""
        if not (len(self.points) > 2 and 0 <= index < len(self.points)):
            return
        self.prepareGeometryChange()
        gone = self.segment_count()
        before = (index - 1) % max(gone, 1)
        del self.points[index]
        self.rounded = {(vertex if vertex < index else vertex - 1): radius
                        for vertex, radius in self.rounded.items()
                        if vertex != index}
        # The two sides that met at that corner become one, so neither of
        # them keeps its curve or its break symbol.
        merged = {index, before}
        self.curved = {(side if side < index else side - 1): bow
                       for side, bow in self.curved.items() if side not in merged}
        self.bezier = {(side if side < index else side - 1): pair
                       for side, pair in self.bezier.items() if side not in merged}
        self.broken = {(side if side < index else side - 1): on
                       for side, on in self.broken.items() if side not in merged}
        self.geometryChanged.emit()

    # -- painting ----------------------------------------------------------
    def paint_content(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        path = self.build_path()
        if self.closed and self.style.paints_inside():
            filled = QPainterPath(path)
            filled.closeSubpath()
            if self.cutouts:
                filled = filled.subtracted(self.clipped_holes_path())
            painter.fillPath(filled, self.style.brush())
        if self.kind == "highlighter":
            # A highlighter lays down one flat band of ink. Stroking the path
            # would draw every part of it separately, so where the stroke
            # crosses itself the colour doubles up and the round ends leave
            # notches behind — which is what a real highlighter never does.
            # Merging the whole stroke into a single outline and filling that
            # once gives one even band, whichever way it was drawn.
            #
            painter.setPen(Qt.NoPen)
            colour = self.highlight_colour()
            # Darken with an opaque marker colour has the two properties a
            # highlighter needs: darker drawing lines remain visible, while a
            # second marker stroke cannot darken the first one again. The old
            # half-transparent Multiply pass composited every markup
            # separately, making crossings visibly darker.
            colour.setAlpha(255)
            painter.setCompositionMode(QPainter.CompositionMode_Darken)
            painter.setBrush(QBrush(colour))
            painter.drawPath(self.band_path(path))
            self._paint_arrows(painter)
            return
        painter.setPen(self.style.pen())
        if self.kind == "cloud":
            round_the_joins(painter)
        painter.setBrush(Qt.NoBrush)
        if not complexlines.draw(painter, path, self.style):
            painter.drawPath(path)
        self.paint_cutouts(painter)
        self._paint_arrows(painter)

    def hatch_region(self) -> Optional[QPainterPath]:
        path = self.outline_path()
        if path.isEmpty():
            return None
        if self.cutouts:
            path = path.subtracted(self.clipped_holes_path())
        return path

    def outline_ring(self) -> list:
        """A closed polygon encloses something; an open polyline does not."""
        return list(self.points) if self.closed and len(self.points) >= 3 else []

    def outline_path(self) -> QPainterPath:
        """The built polygon, including its edited curved sides."""
        if not self.closed or len(self.points) < 3:
            return QPainterPath()
        path = self.build_path()
        path.closeSubpath()
        return path

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
        base = max(self.style.width * 4.0, 7.0)
        size = base * max(self.style.arrow_size, 0.1)
        start_size = base * max(self.style.start_size(), 0.1)
        colour = QColor(self.style.stroke or "#000000")
        colour.setAlphaF(self.style.opacity)
        # a filled end in the line-end colour (Revu's Fill Color), the line's
        # own unless it was given one
        painter.setBrush(self.style.end_brush())
        pen = QPen(colour)
        pen.setWidthF(max(self.style.width * 0.9, 0.5))
        pen.setJoinStyle(Qt.MiterJoin)
        pen.setMiterLimit(8.0)
        painter.setPen(pen)
        if self.style.arrow_end != "none":
            tip = self.points[-1]
            previous = self.points[-2]
            angle = math.atan2(tip.y() - previous.y(), tip.x() - previous.x())
            draw_head(painter, tip, angle, size, self.style.arrow_end)
        if self.style.arrow_start != "none":
            tip = self.points[0]
            following = self.points[1]
            angle = math.atan2(tip.y() - following.y(), tip.x() - following.x())
            draw_head(painter, tip, angle, start_size, self.style.arrow_start)

    def paint_handles(self, painter: QPainter) -> None:
        # The same three guards the base draws under: not selected, handles
        # turned off while something else is going on, and one member of a
        # group, where the view draws one box round the lot and a vertex
        # handle here would be a control point nobody can use.
        if not self.isSelected() or not self._handles_visible or self.group:
            return
        if self.locked:
            self.paint_locked_selection(painter)       # F-32
            return
        if not self.uses_vertex_handles:
            super().paint_handles(painter)
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        zoom = handle_zoom(painter)
        self.paint_scale_box(painter, zoom)
        rect = self.local_rect()
        for key, point in self.handle_points().items():
            if key == "rot":
                top = self.scale_box().top() if self.has_scale_box() else rect.top()
                paint_rotate_handle(painter, point, QPointF(rect.center().x(), top), zoom)
            elif key.startswith("b") and key[1:].isdigit():
                paint_control_point(painter, point, zoom, colour=SELECT_BLUE)
            elif key[:1] in ("w", "z") and key[1:].isdigit():
                extent = 3.5 / zoom
                painter.setPen(QPen(SELECT_BLUE.darker(130), 0.6 / zoom))
                painter.setBrush(QBrush(QColor(255, 255, 255)))
                painter.drawRect(QRectF(point.x() - extent, point.y() - extent,
                                        2 * extent, 2 * extent))
                if key[0] == "w":
                    painter.drawLine(QPointF(point.x() - extent * 0.6, point.y()),
                                     QPointF(point.x() + extent * 0.6, point.y()))
                else:
                    painter.drawLine(QPointF(point.x(), point.y() - extent * 0.6),
                                     QPointF(point.x(), point.y() + extent * 0.6))
            else:
                # a vertex, a radius, a bow: Bluebeam's gold control points
                paint_control_point(painter, point, zoom)
        painter.restore()

    # -- serialisation -----------------------------------------------------
    def serialize(self) -> dict:
        data = self.base_dict()
        data.update({
            "kind": self.kind,
            "points": [[round(p.x(), 3), round(p.y(), 3)] for p in self.points],
            "smooth": self.smooth,
        })
        self.cloud_to_dict(data)
        if self.rounded:
            data["rounded"] = {str(k): round(v, 3) for k, v in self.rounded.items()}
        if self.curved:
            data["curved"] = {str(k): [round(v[0], 3), round(v[1], 3)]
                              for k, v in self.curved.items()}
        if self.bezier:
            data["bezier"] = {str(k): [round(a.x(), 4), round(a.y(), 4),
                                       round(b.x(), 4), round(b.y(), 4)]
                              for k, (a, b) in self.bezier.items()}
        if self.broken:
            data["broken"] = sorted(self.broken)
            data["break_settings"] = {str(k): list(self.break_settings(k)) for k in self.broken}
        if self.cutouts:
            data["cutouts"] = self.cutouts_as_data()
        return data

    def deserialize(self, data: dict) -> None:
        self.kind = data.get("kind", "line")
        self.points = [QPointF(x, y) for x, y in data.get("points", [])]
        self.smooth = bool(data.get("smooth", self.kind in ("ink", "highlighter")))
        self.rounded = {int(k): float(v)
                        for k, v in (data.get("rounded") or {}).items()}
        self.curved = {int(k): (float(v[0]), float(v[1]))
                       for k, v in (data.get("curved") or {}).items()}
        self.bezier = {int(k): (QPointF(float(v[0]), float(v[1])),
                                QPointF(float(v[2]), float(v[3])))
                       for k, v in (data.get("bezier") or {}).items() if len(v) >= 4}
        self.broken = {int(k): True for k in (data.get("broken") or [])}
        for key, value in (data.get("break_settings") or {}).items():
            if int(key) in self.broken and len(value) in (2, 3):
                width, height, position = (value if len(value) == 3 else
                                           (value[0] * 2.8, value[0] * 2, value[1]))
                self.broken[int(key)] = (max(1.4, float(width)),
                                         max(1.0, float(height)),
                                         max(0.05, min(0.95, float(position))))
        self.cutouts_from_data(data)
        self.load_base(data)
        self.cloud_from_dict(data)


def _distance(a: QPointF, b: QPointF) -> float:
    return math.hypot(b.x() - a.x(), b.y() - a.y())


def _towards(a: QPointF, b: QPointF) -> QPointF:
    return QPointF(b.x() - a.x(), b.y() - a.y())


def _unit(vector: QPointF) -> QPointF:
    length = math.hypot(vector.x(), vector.y()) or 1.0
    return QPointF(vector.x() / length, vector.y() / length)


def _towards_by(start: QPointF, end: QPointF, distance: float) -> QPointF:
    """*distance* along the way from *start* to *end*."""
    step = _unit(_towards(start, end))
    return QPointF(start.x() + step.x() * distance,
                   start.y() + step.y() * distance)


def _offset_along(start: QPointF, end: QPointF, along: float,
                  sideways: float) -> QPointF:
    """A point *along* the segment, pushed *sideways* off it."""
    on = QPointF(start.x() + (end.x() - start.x()) * along,
                 start.y() + (end.y() - start.y()) * along)
    step = _unit(_towards(start, end))
    return QPointF(on.x() - step.y() * sideways, on.y() + step.x() * sideways)


def _project(start: QPointF, end: QPointF, point: QPointF) -> tuple[float, float]:
    """Where *point* falls on the segment: how far along, and how far off."""
    span = _towards(start, end)
    length = math.hypot(span.x(), span.y()) or 1.0
    along = _unit(span)
    across = QPointF(-along.y(), along.x())
    offset = _towards(start, point)
    forward = (offset.x() * along.x() + offset.y() * along.y()) / length
    sideways = offset.x() * across.x() + offset.y() * across.y()
    return max(0.1, min(0.9, forward)), sideways


def _break_symbol(start: QPointF, end: QPointF, width: float, height: float,
                  position: float = 0.5) -> QPainterPath:
    """The drafting break: the line stops, jinks across itself and goes on.

    The symbol every structural drawing uses to say "this carries on, and the
    middle of it is not drawn to length".
    """
    length = _distance(start, end)
    if length < width * 1.07:
        return QPainterPath()
    along = _unit(_towards(start, end))
    across = QPointF(-along.y(), along.x())
    position = max(width / (2 * length), min(1 - width / (2 * length), position))
    middle = start + (end - start) * position

    def at(forward: float, sideways: float) -> QPointF:
        return QPointF(middle.x() + along.x() * forward + across.x() * sideways,
                       middle.y() + along.y() * forward + across.y() * sideways)

    path = QPainterPath(start)
    path.lineTo(at(-width / 2, 0))
    path.lineTo(at(-width / 5.6, height / 2))
    path.lineTo(at(width / 5.6, -height / 2))
    path.lineTo(at(width / 2, 0))
    path.lineTo(end)
    return path


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
                pen.setJoinStyle(Qt.MiterJoin)
                pen.setCapStyle(Qt.FlatCap)
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
