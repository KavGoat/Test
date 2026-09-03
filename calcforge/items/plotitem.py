"""An X–Y plot of functions, expressions and vectors from the workspace."""
from __future__ import annotations

import math
from typing import Any, Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFontMetricsF, QPainter, QPainterPath,
                           QPen)

from ..core import engine
from ..core.typography import page_font
from ..core.units import (Quantity, format_number, format_unit, preferred_unit)
from .base import MarkupItem, Style, register_item

SERIES_COLOURS = ["#1971c2", "#e8590c", "#2f9e44", "#c2255c", "#7048e8",
                  "#0ca678", "#f59f00", "#495057"]

DEFAULT_SAMPLES = 120


class Series:
    """One curve: its source text, its sampled points and any error."""

    __slots__ = ("expression", "label", "colour", "xs", "ys", "error")

    def __init__(self, expression: str = "", label: str = "", colour: str = ""):
        self.expression = expression
        self.label = label
        self.colour = colour
        self.xs: list[float] = []
        self.ys: list[float] = []
        self.error = ""

    def to_dict(self) -> dict:
        return {"expression": self.expression, "label": self.label, "colour": self.colour}

    @classmethod
    def from_dict(cls, data: dict) -> "Series":
        return cls(data.get("expression", ""), data.get("label", ""), data.get("colour", ""))


def _nice_step(span: float, target: int = 5) -> float:
    """A round axis step close to span/target — 1, 2, 2.5 or 5 times a power of ten."""
    if span <= 0 or not math.isfinite(span):
        return 1.0
    raw = span / max(target, 1)
    magnitude = 10 ** math.floor(math.log10(raw))
    for factor in (1, 2, 2.5, 5, 10):
        if raw <= factor * magnitude:
            return factor * magnitude
    return 10 * magnitude


@register_item
class PlotItem(MarkupItem):
    """A 2-D plot driven by the same variables and functions as the sheet."""

    TYPE = "plot"
    NAME = "Plot"
    ROTATABLE = False

    def __init__(self, expressions: Optional[list[str]] = None, variable: str = "x"):
        super().__init__()
        self.series: list[Series] = [Series(e) for e in (expressions or [""])]
        self.variable = variable
        self.x_from = "0"
        self.x_to = "10"
        self.samples = DEFAULT_SAMPLES
        self.title = ""
        self.x_label = ""
        self.y_label = ""
        self.x_unit = ""
        self.y_unit = ""
        self.show_grid = True
        self.show_legend = True
        self.show_markers = False
        self._rect = QRectF(0, 0, 280, 190)
        self._x_display = ""
        self._y_display = ""
        self.error = ""
        self.style = Style(stroke="#adb5bd", fill="#ffffff", fill_opacity=1.0,
                           width=0.7, font_size=7.5, text_color="#3d4550", padding=6.0)
        self.layer = "Calculations"

    # -- identity ----------------------------------------------------------
    def display_name(self) -> str:
        if self.label:
            return self.label
        first = next((s.expression for s in self.series if s.expression), "")
        return f"Plot · {first[:32]}" if first else "Plot"

    def summary(self) -> str:
        return self.comment or ", ".join(s.expression for s in self.series if s.expression)

    # -- geometry ----------------------------------------------------------
    def local_rect(self) -> QRectF:
        return QRectF(self._rect)

    def set_local_rect(self, rect: QRectF) -> None:
        self._rect = QRectF(rect)

    def plot_rect(self) -> QRectF:
        """The data area, inside the axis labels."""
        rect = self._rect.normalized()
        left = self.style.padding + self.style.font_size * 4.4
        bottom = self.style.padding + self.style.font_size * 2.8
        top = self.style.padding + (self.style.font_size * 1.9 if self.title else 0.0)
        right = self.style.padding + 4
        return QRectF(rect.left() + left, rect.top() + top,
                      max(rect.width() - left - right, 10.0),
                      max(rect.height() - top - bottom, 10.0))

    # -- evaluation --------------------------------------------------------
    def refresh(self, workspace=None, page=None) -> None:
        if workspace is None:
            scene = self.scene()
            workspace = getattr(scene, "workspace", None) if scene is not None else None
        if workspace is None:
            return
        self.error = ""
        try:
            low = workspace.evaluate(self.x_from) if self.x_from.strip() else 0.0
            high = workspace.evaluate(self.x_to) if self.x_to.strip() else 1.0
        except Exception as exc:  # noqa: BLE001
            self.error = f"Range: {engine.friendly_error(exc)}"
            for series in self.series:
                series.xs, series.ys = [], []
            self.update()
            return

        # A range that starts at zero says nothing about the unit to use, so
        # fall back to the far end of the axis.
        x_unit = (self.x_unit or preferred_unit(low) or preferred_unit(high)
                  or self._written_unit(low) or self._written_unit(high) or "")
        self._x_display = x_unit
        samples = max(int(self.samples), 2)
        y_unit = self.y_unit
        for index, series in enumerate(self.series):
            series.error = ""
            series.xs, series.ys = [], []
            if not series.expression.strip():
                continue
            if not series.colour:
                series.colour = SERIES_COLOURS[index % len(SERIES_COLOURS)]
            try:
                code = self._compile(series.expression, workspace)
            except Exception as exc:  # noqa: BLE001
                series.error = engine.friendly_error(exc)
                continue
            mismatched = False
            for step in range(samples):
                position = low + (high - low) * step / (samples - 1)
                try:
                    value = self._sample(code, workspace, position)
                except Exception as exc:  # noqa: BLE001
                    series.error = engine.friendly_error(exc)
                    continue
                # The first curve fixes the y axis; later ones have to share it.
                if not y_unit and isinstance(value, Quantity):
                    y_unit = preferred_unit(value) or format_unit(value.units)
                x_plain = self._plain(position, x_unit)
                y_plain = self._plain(value, y_unit)
                if y_plain is None and isinstance(value, Quantity) and y_unit:
                    mismatched = True
                    break
                if x_plain is None or y_plain is None:
                    continue
                if not (math.isfinite(x_plain) and math.isfinite(y_plain)):
                    continue
                series.xs.append(x_plain)
                series.ys.append(y_plain)
            if mismatched:
                series.xs, series.ys = [], []
                series.error = (f"{series.expression} is not in {y_unit} — "
                                "a plot has one y axis, so every curve must share its unit")
        self._y_display = self.y_unit or y_unit or ""
        self.update()

    def _compile(self, expression: str, workspace):
        """Compile *expression*; a bare function name becomes a call on the axis."""
        text = expression.strip()
        if text in workspace.functions:
            text = f"{text}({self.variable})"
        code, tree = engine.compile_expression(text)
        return code, tree

    def _sample(self, compiled, workspace, position) -> Any:
        code, tree = compiled
        namespace = workspace.namespace()
        namespace[self.variable] = position
        workspace.resolve_units(code, namespace, tree)
        return engine.evaluate_code(code, namespace)

    @staticmethod
    def _written_unit(value: Any) -> str:
        return format_unit(value.units) if isinstance(value, Quantity) else ""

    @staticmethod
    def _plain(value: Any, unit: str) -> Optional[float]:
        try:
            if isinstance(value, Quantity):
                return float(value.to(unit).magnitude) if unit else float(value.magnitude)
            return float(value)
        except Exception:
            return None

    def bounds(self) -> tuple[float, float, float, float]:
        xs = [x for series in self.series for x in series.xs]
        ys = [y for series in self.series for y in series.ys]
        if not xs or not ys:
            return 0.0, 1.0, 0.0, 1.0
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        if x_max - x_min < 1e-12:
            x_min, x_max = x_min - 0.5, x_max + 0.5
        if y_max - y_min < 1e-12:
            y_min, y_max = y_min - 0.5, y_max + 0.5
        pad = (y_max - y_min) * 0.06
        return x_min, x_max, y_min - pad, y_max + pad

    # -- painting ----------------------------------------------------------
    def paint_content(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self._rect.normalized()
        painter.setBrush(self.style.brush())
        painter.setPen(self.style.pen() if self.style.stroke else Qt.NoPen)
        painter.drawRect(rect)

        area = self.plot_rect()
        x_min, x_max, y_min, y_max = self.bounds()
        font = page_font("", self.style.font_size)
        painter.setFont(font)
        metrics = QFontMetricsF(font)

        if self.title:
            title_font = page_font("", self.style.font_size * 1.15, bold=True)
            painter.setFont(title_font)
            painter.setPen(QPen(QColor(self.style.text_color)))
            painter.drawText(QRectF(rect.left(), rect.top() + 2, rect.width(),
                                    self.style.font_size * 1.8),
                             Qt.AlignCenter, self.title)
            painter.setFont(font)

        self._paint_axes(painter, area, metrics, x_min, x_max, y_min, y_max)
        self._paint_series(painter, area, x_min, x_max, y_min, y_max)
        if self.show_legend:
            self._paint_legend(painter, area, metrics)
        messages = [self.error] + [s.error for s in self.series if s.error]
        messages = [m for m in messages if m]
        if messages:
            painter.setPen(QPen(QColor("#b3261e")))
            painter.drawText(area.adjusted(4, 4, -4, -4),
                             Qt.AlignTop | Qt.AlignLeft | Qt.TextWordWrap,
                             "\n".join(messages))

    def _map(self, area: QRectF, x: float, y: float, x_min: float, x_max: float,
             y_min: float, y_max: float) -> QPointF:
        fx = (x - x_min) / (x_max - x_min) if x_max > x_min else 0.5
        fy = (y - y_min) / (y_max - y_min) if y_max > y_min else 0.5
        return QPointF(area.left() + fx * area.width(),
                       area.bottom() - fy * area.height())

    def _paint_axes(self, painter: QPainter, area: QRectF, metrics: QFontMetricsF,
                    x_min: float, x_max: float, y_min: float, y_max: float) -> None:
        grid_pen = QPen(QColor(0, 0, 0, 34))
        grid_pen.setWidthF(0.4)
        axis_pen = QPen(QColor(self.style.text_color))
        axis_pen.setWidthF(max(self.style.width, 0.6))
        text_pen = QPen(QColor(self.style.text_color))

        step_x = _nice_step(x_max - x_min)
        step_y = _nice_step(y_max - y_min)

        tick = math.ceil(x_min / step_x) * step_x
        while tick <= x_max + step_x * 1e-6:
            point = self._map(area, tick, y_min, x_min, x_max, y_min, y_max)
            if self.show_grid:
                painter.setPen(grid_pen)
                painter.drawLine(QPointF(point.x(), area.top()),
                                 QPointF(point.x(), area.bottom()))
            painter.setPen(axis_pen)
            painter.drawLine(QPointF(point.x(), area.bottom()),
                             QPointF(point.x(), area.bottom() + 2.5))
            painter.setPen(text_pen)
            label = format_number(tick, 4)
            painter.drawText(QRectF(point.x() - 26, area.bottom() + 3, 52,
                                    self.style.font_size * 1.4),
                             Qt.AlignHCenter | Qt.AlignTop, label)
            tick += step_x

        tick = math.ceil(y_min / step_y) * step_y
        while tick <= y_max + step_y * 1e-6:
            point = self._map(area, x_min, tick, x_min, x_max, y_min, y_max)
            if self.show_grid:
                painter.setPen(grid_pen)
                painter.drawLine(QPointF(area.left(), point.y()),
                                 QPointF(area.right(), point.y()))
            painter.setPen(axis_pen)
            painter.drawLine(QPointF(area.left() - 2.5, point.y()),
                             QPointF(area.left(), point.y()))
            painter.setPen(text_pen)
            painter.drawText(QRectF(area.left() - 60, point.y() - self.style.font_size,
                                    56, self.style.font_size * 2),
                             Qt.AlignRight | Qt.AlignVCenter, format_number(tick, 4))
            tick += step_y

        painter.setPen(axis_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(area)

        painter.setPen(text_pen)
        x_caption = self.x_label or self.variable
        if self._x_display:
            x_caption = f"{x_caption} [{self._x_display}]"
        painter.drawText(QRectF(area.left(), area.bottom() + self.style.font_size * 1.5,
                                area.width(), self.style.font_size * 1.6),
                         Qt.AlignHCenter | Qt.AlignTop, x_caption)
        y_caption = self.y_label or ""
        if self._y_display:
            y_caption = f"{y_caption} [{self._y_display}]".strip()
        if y_caption:
            painter.save()
            painter.translate(area.left() - self.style.font_size * 3.6,
                              area.center().y())
            painter.rotate(-90)
            painter.drawText(QRectF(-area.height() / 2, -self.style.font_size,
                                    area.height(), self.style.font_size * 2),
                             Qt.AlignCenter, y_caption)
            painter.restore()

    def _paint_series(self, painter: QPainter, area: QRectF, x_min: float, x_max: float,
                      y_min: float, y_max: float) -> None:
        painter.save()
        painter.setClipRect(area.adjusted(-1, -1, 1, 1))
        for index, series in enumerate(self.series):
            if len(series.xs) < 2:
                continue
            colour = QColor(series.colour or SERIES_COLOURS[index % len(SERIES_COLOURS)])
            pen = QPen(colour)
            pen.setWidthF(max(self.style.width * 2.0, 1.1))
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            path = QPainterPath()
            for position, (x, y) in enumerate(zip(series.xs, series.ys)):
                point = self._map(area, x, y, x_min, x_max, y_min, y_max)
                path.moveTo(point) if position == 0 else path.lineTo(point)
            painter.drawPath(path)
            if self.show_markers:
                painter.setBrush(QBrush(colour))
                for x, y in zip(series.xs, series.ys):
                    painter.drawEllipse(self._map(area, x, y, x_min, x_max, y_min, y_max),
                                        1.2, 1.2)
        painter.restore()

    def _paint_legend(self, painter: QPainter, area: QRectF,
                      metrics: QFontMetricsF) -> None:
        entries = [(s, s.label or s.expression) for s in self.series
                   if s.expression.strip() and s.xs]
        if len(entries) < 2:
            return
        width = max(metrics.horizontalAdvance(text) for _s, text in entries) + 22
        height = len(entries) * (self.style.font_size * 1.5) + 6
        box = QRectF(area.right() - width - 5, area.top() + 5, width, height)
        painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
        painter.setPen(QPen(QColor(0, 0, 0, 45), 0.5))
        painter.drawRoundedRect(box, 2, 2)
        y = box.top() + 4
        for series, text in entries:
            colour = QColor(series.colour)
            pen = QPen(colour)
            pen.setWidthF(1.6)
            painter.setPen(pen)
            painter.drawLine(QPointF(box.left() + 4, y + self.style.font_size * 0.7),
                             QPointF(box.left() + 15, y + self.style.font_size * 0.7))
            painter.setPen(QPen(QColor(self.style.text_color)))
            painter.drawText(QRectF(box.left() + 18, y, box.width() - 20,
                                    self.style.font_size * 1.5),
                             Qt.AlignLeft | Qt.AlignVCenter, text)
            y += self.style.font_size * 1.5

    # -- serialisation -----------------------------------------------------
    def serialize(self) -> dict:
        data = self.base_dict()
        data.update({
            "rect": [self._rect.x(), self._rect.y(), self._rect.width(), self._rect.height()],
            "series": [s.to_dict() for s in self.series],
            "variable": self.variable,
            "x_from": self.x_from, "x_to": self.x_to, "samples": self.samples,
            "title": self.title, "x_label": self.x_label, "y_label": self.y_label,
            "x_unit": self.x_unit, "y_unit": self.y_unit,
            "show_grid": self.show_grid, "show_legend": self.show_legend,
            "show_markers": self.show_markers,
        })
        return data

    def deserialize(self, data: dict) -> None:
        self._rect = QRectF(*data.get("rect", [0, 0, 280, 190]))
        self.series = [Series.from_dict(entry) for entry in data.get("series", [])] or [Series()]
        self.variable = data.get("variable", "x")
        self.x_from = data.get("x_from", "0")
        self.x_to = data.get("x_to", "10")
        self.samples = int(data.get("samples", DEFAULT_SAMPLES))
        self.title = data.get("title", "")
        self.x_label = data.get("x_label", "")
        self.y_label = data.get("y_label", "")
        self.x_unit = data.get("x_unit", "")
        self.y_unit = data.get("y_unit", "")
        self.show_grid = bool(data.get("show_grid", True))
        self.show_legend = bool(data.get("show_legend", True))
        self.show_markers = bool(data.get("show_markers", False))
        self.load_base(data)
