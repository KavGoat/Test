"""A chart: XY scatter, line or column, drawn from cells in Excel's look.

The user's choices (docs/SPREADSHEET_DESIGN.md, phase 5): a chart goes
anywhere — on a spreadsheet page over its cells (moving with them) or on any
page beside the equations — and reads ranges of any sheet or table; the
engineering subset of chart types with log axes, error bars and trendlines;
Excel's default look (Office colours, light grey gridlines, title on top,
legend at the bottom) with the cells' units in the axis titles.

Like an equation or a table it is CalcForge's own drawing (the calc layer):
it prints and exports with the page and is rebuilt from the record when the
file is opened here. It follows its cells as they change, and its ranges
follow the sheets' renames and inserted or deleted rows and columns.
"""
from __future__ import annotations

import copy
import math
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem

from ..core.typography import page_font
from ..sheet import chartdata as CD
from .base import MarkupItem, register_item

TEXT = QColor("#595959")
GRID = QColor("#D9D9D9")
BORDER = QColor("#D9D9D9")
FONT = "Calibri"

KINDS = ("scatter", "line", "column")


def new_spec(kind: str = "scatter") -> dict:
    return {
        "kind": kind,                  # scatter, line or column
        "lines": kind == "line",       # scatter with lines / line chart
        "markers": kind != "line",     # scatter's markers / line with markers
        "title": "auto",               # "auto": the series' name; "" none
        "x_title": "auto",             # "auto": the x heading and its unit
        "y_title": "auto",
        "legend": "bottom",            # bottom, right, top, none
        "x_axis": {"min": None, "max": None, "major": None, "log": False,
                   "gridlines": kind == "scatter"},
        "y_axis": {"min": None, "max": None, "major": None, "log": False, "gridlines": True},
        "series": [],
    }


def new_series(x: str = "", y: str = "", name: str = "") -> dict:
    return {"name": name, "x": x, "y": y, "color": None, "error": None, "x_error": None,
            "trend": None}


@register_item
class ChartItem(MarkupItem):
    """A chart of cells."""

    TYPE = "chart"
    NAME = "Chart"
    ROTATABLE = False
    IS_CALC = True
    SHEET_PAGE_OK = True            # charts may sit on spreadsheet pages
    region = None

    def __init__(self, spec: Optional[dict] = None):
        super().__init__()
        self.spec = spec or new_spec()
        self.rect = QRectF(0, 0, 360, 216)      # Excel's 5 × 3 inches
        self._book = None
        self._data = None
        self.setZValue(1)

    # -- the cells behind it -----------------------------------------------------------------------
    def _page_frame(self):
        frame = self.parentItem()
        return frame if frame is not None and hasattr(frame, "document") else None

    def _attach(self) -> None:
        frame = self._page_frame()
        if frame is None or self.scene() is None:
            self._detach()
            return
        if self._book is not None:
            return
        from ..sheet.docbook import book_for

        book = book_for(frame.document)
        if book.later is None:
            from PySide6.QtCore import QTimer
            book.later = lambda run: QTimer.singleShot(0, run)
        self._book = book
        book.listeners.append(self._values_changed)
        book.workbook.outside_formulas.append(self)
        self._data = None

    def _detach(self) -> None:
        book = self._book
        if book is None:
            return
        if self._values_changed in book.listeners:
            book.listeners.remove(self._values_changed)
        if self in book.workbook.outside_formulas:
            book.workbook.outside_formulas.remove(self)
        self._book = None

    def itemChange(self, change, value):
        result = super().itemChange(change, value)
        if change in (QGraphicsItem.ItemParentHasChanged, QGraphicsItem.ItemSceneHasChanged):
            self._attach()
        return result

    @property
    def workbook(self):
        return self._book.workbook if self._book is not None else None

    def _values_changed(self, keys: set) -> None:
        wb = self.workbook
        if wb is None:
            return
        read = CD.sheets_read(self.spec)
        for k in keys:
            sheet = wb.sheet_by_id(k[1]) if k[0] == "layout" else wb.sheet_by_id(k[0]) \
                if isinstance(k[0], int) else None
            if sheet is None or sheet.name.lower() in read:
                self._data = None
                self.update()
                return

    # the workbook passes the ranges through renames and moved rows (workbook.py)
    def formula_texts(self) -> list:
        out = []
        for s in self.spec["series"]:
            out.append(s.get("x") or "")
            out.append(s.get("y") or "")
            name = s.get("name") or ""
            out.append(name[1:] if isinstance(name, str) and name.startswith("=") else "")
            err = s.get("error") or {}
            out.append(err.get("plus") or "")
            out.append(err.get("minus") or "")
        return out

    def set_formula_texts(self, texts: list) -> None:
        it = iter(texts)
        for s in self.spec["series"]:
            s["x"] = next(it)
            s["y"] = next(it)
            name = next(it)
            if isinstance(s.get("name"), str) and s["name"].startswith("="):
                s["name"] = "=" + name
            plus, minus = next(it), next(it)
            if s.get("error"):
                s["error"]["plus"], s["error"]["minus"] = plus, minus
        self._data = None
        self.update()

    def set_spec(self, spec: dict) -> None:
        self.spec = copy.deepcopy(spec)
        self._data = None
        self.touch()
        self.update()

    def data(self) -> list:
        """The series as read from their cells (kept until a cell changes)."""
        if self._data is None:
            wb = self.workbook
            numeric = self.spec["kind"] == "scatter"
            self._data = [CD.read_series(wb, s, numeric) for s in self.spec["series"]] \
                if wb is not None else []
        return self._data

    # -- geometry ----------------------------------------------------------------------------------
    def local_rect(self) -> QRectF:
        return QRectF(self.rect)

    def set_local_rect(self, rect: QRectF) -> None:
        rect = rect.normalized()
        self.prepareGeometryChange()
        self.rect = QRectF(0, 0, max(rect.width(), 72.0), max(rect.height(), 54.0))
        if rect.topLeft() != QPointF(0, 0):
            self.setPos(self.mapToParent(rect.topLeft()))
        self.update()

    def boundingRect(self) -> QRectF:
        return self.rect.adjusted(-6, -6, 6, 6)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self.rect)
        return path

    # -- drawing -----------------------------------------------------------------------------------
    def paint_content(self, painter: QPainter) -> None:
        draw_chart(painter, self.rect, self.spec, self.data(), self.workbook)

    # -- the record --------------------------------------------------------------------------------
    def serialize(self) -> dict:
        data = self.base_dict()
        data["chart"] = copy.deepcopy(self.spec)
        data["w"] = self.rect.width()
        data["h"] = self.rect.height()
        return data

    def deserialize(self, data: dict) -> None:
        self.spec = copy.deepcopy(data.get("chart") or new_spec())
        self.rect = QRectF(0, 0, float(data.get("w", 360)), float(data.get("h", 216)))
        self.load_base(data)

    def summary(self) -> str:
        kind = {"scatter": "XY scatter", "line": "Line", "column": "Column"}.get(self.spec["kind"], "")
        return f"{kind} chart — {len(self.spec['series'])} series"


# -- Excel's default chart, drawn ------------------------------------------------------------------
def _font(size: float, bold: bool = False):
    return page_font(FONT, size, bold)


def _title(spec, data) -> str:
    title = spec.get("title", "auto")
    if title == "auto":
        return data[0].name if len(data) == 1 and data[0].name else ("Chart Title" if not data else "")
    return title or ""


def _with_unit(heading: str, unit: str) -> str:
    """A heading and its unit: "Span (m)", unless the heading says it already."""
    heading = (heading or "").strip()
    if not unit:
        return heading
    if f"({unit})" in heading or f"[{unit}]" in heading or heading.endswith(f" {unit}"):
        return heading
    return f"{heading} ({unit})" if heading else f"({unit})"


def _one_unit(units: list) -> str:
    """The unit every series shares, or none when they differ."""
    found = {u for u in units if u}
    if len(found) != 1 or any(not u for u in units):
        return ""
    return found.pop()


def _axis_title(spec, data, which: str) -> str:
    title = spec.get(f"{which}_title", "auto")
    if title != "auto":
        return title or ""
    if which == "x":
        unit = _one_unit([d.x_unit for d in data if d.xs])
        return _with_unit(spec.get("x_heading", ""), unit)
    unit = _one_unit([d.y_unit for d in data])
    heading = data[0].name if len(data) == 1 else spec.get("y_heading", "")
    return _with_unit(heading, unit)


class _Axis:
    """Maps values to positions along one side of the plot area."""

    def __init__(self, lo, hi, log, step, a, b):
        self.lo, self.hi, self.log, self.step = lo, hi, log, step
        self.a, self.b = a, b       # pixel positions of lo and hi

    def at(self, v: float) -> Optional[float]:
        if v is None:
            return None
        if self.log:
            if v <= 0:
                return None
            t = (math.log10(v) - math.log10(self.lo)) / (math.log10(self.hi) - math.log10(self.lo))
        else:
            t = (v - self.lo) / ((self.hi - self.lo) or 1.0)
        return self.a + t * (self.b - self.a)

    def ticks(self) -> list:
        return CD.log_ticks(self.lo, self.hi) if self.log else CD.ticks(self.lo, self.hi, self.step)

    def label(self, v: float) -> str:
        if self.log:
            return CD.tick_label(v)
        return CD.tick_label(v, self.step)


def _value_range(values: list, log: bool) -> tuple:
    nums = [v for v in values if v is not None and (not log or v > 0)]
    if not nums:
        return (1.0, 10.0) if log else (0.0, 1.0)
    return min(nums), max(nums)


def _make_axis(spec_axis: dict, values: list, length: float, a: float, b: float,
               spacing: float) -> _Axis:
    log = bool(spec_axis.get("log"))
    lo, hi = _value_range(values, log)
    if log:
        mn, mx = CD.log_scale(lo, hi, spec_axis.get("min"), spec_axis.get("max"))
        return _Axis(mn, mx, True, None, a, b)
    mn, mx, step = CD.nice_scale(lo, hi, max(2.0, length / spacing), spec_axis.get("min"),
                                 spec_axis.get("max"), spec_axis.get("major"))
    return _Axis(mn, mx, False, step, a, b)


def draw_chart(painter: QPainter, rect: QRectF, spec: dict, data: list, wb=None) -> None:
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    # the chart area: white, a light grey border
    pen = QPen(BORDER, 0.75)
    painter.setPen(pen)
    painter.setBrush(QColor("white"))
    painter.drawRect(rect)
    inner = rect.adjusted(7, 7, -7, -7)
    kind = spec.get("kind", "scatter")
    colours = [s.get("color") or CD.OFFICE[i % len(CD.OFFICE)] for i, s in enumerate(spec["series"])]
    # title
    title = _title(spec, data)
    if title:
        f = _font(14)
        painter.setFont(f)
        painter.setPen(TEXT)
        h = QFontMetricsF(f).height()
        painter.drawText(QRectF(inner.left(), inner.top(), inner.width(), h), Qt.AlignCenter, title)
        inner.setTop(inner.top() + h + 4)
    # legend
    legend = spec.get("legend", "bottom")
    names = [(d.name or f"Series{i + 1}", colours[i]) for i, d in enumerate(data)]
    trend_names = []
    for i, s in enumerate(spec["series"]):
        t = s.get("trend")
        if t and t.get("type"):
            label = {"linear": "Linear", "poly": "Poly.", "exp": "Expon.", "log": "Log.",
                     "power": "Power", "moving": f"{t.get('period', 2)} per. Mov. Avg."}.get(t["type"], "")
            trend_names.append((f"{label} ({names[i][0]})", colours[i]))
    entries = names + trend_names
    lf = _font(9)
    lm = QFontMetricsF(lf)
    if legend != "none" and entries:
        widths = [lm.horizontalAdvance(n) + 22 for n, _c in entries]
        if legend in ("bottom", "top"):
            total = sum(widths) + 8 * (len(widths) - 1)
            h = lm.height() + 4
            y = inner.bottom() - h if legend == "bottom" else inner.top()
            x = inner.center().x() - total / 2
            for (name, colour), w, k in zip(entries, widths, range(len(entries))):
                _legend_key(painter, QRectF(x, y, 18, h), colour, kind, spec, k >= len(names))
                painter.setFont(lf)
                painter.setPen(TEXT)
                painter.drawText(QRectF(x + 20, y, w - 20, h), Qt.AlignVCenter | Qt.AlignLeft, name)
                x += w + 8
            if legend == "bottom":
                inner.setBottom(y - 4)
            else:
                inner.setTop(y + h + 4)
        else:
            w = max(widths)
            h = lm.height() + 2
            y = inner.center().y() - h * len(entries) / 2
            x = inner.right() - w
            for k, (name, colour) in enumerate(entries):
                _legend_key(painter, QRectF(x, y, 18, h), colour, kind, spec, k >= len(names))
                painter.setFont(lf)
                painter.setPen(TEXT)
                painter.drawText(QRectF(x + 20, y, w - 20, h), Qt.AlignVCenter | Qt.AlignLeft, name)
                y += h
            inner.setRight(x - 6)
    # axis titles
    tf = _font(10)
    tm = QFontMetricsF(tf)
    x_title = _axis_title(spec, data, "x")
    y_title = _axis_title(spec, data, "y")
    if x_title:
        h = tm.height()
        painter.setFont(tf)
        painter.setPen(TEXT)
        painter.drawText(QRectF(inner.left(), inner.bottom() - h, inner.width(), h), Qt.AlignCenter, x_title)
        inner.setBottom(inner.bottom() - h - 2)
    if y_title:
        h = tm.height()
        painter.save()
        painter.setFont(tf)
        painter.setPen(TEXT)
        painter.translate(inner.left() + h / 2, inner.center().y())
        painter.rotate(-90)
        painter.drawText(QRectF(-inner.height() / 2, -h / 2, inner.height(), h), Qt.AlignCenter, y_title)
        painter.restore()
        inner.setLeft(inner.left() + h + 2)
    if not data or all(not d.ys for d in data):
        painter.restore()
        return
    # the axes
    af = _font(9)
    am = QFontMetricsF(af)
    xa_spec, ya_spec = spec.get("x_axis", {}), spec.get("y_axis", {})
    ys_all = []
    for i, d in enumerate(data):
        ys_all += [v for v in d.ys if v is not None]
        err = CD.error_amounts(wb, d.ys, spec["series"][i].get("error"))
        for v, e in zip(d.ys, err):
            if v is None or e is None:
                continue
            if e[0] == "mean":
                ys_all += [e[1] - e[2], e[1] + e[2]]
            else:
                ys_all += [v - e[0], v + e[1]]
    # a first guess at the labels' room, then the axes themselves
    left_room = am.horizontalAdvance("0000") + 6
    bottom_room = am.height() + 4
    plot = QRectF(inner.left() + left_room, inner.top() + 4, inner.width() - left_room - 8,
                  inner.height() - bottom_room - 4)
    yaxis = _make_axis(ya_spec, ys_all, plot.height(), plot.bottom(), plot.top(), 26.0)
    if kind == "column" and not yaxis.log:
        yaxis = _make_axis(ya_spec, ys_all + [0.0], plot.height(), plot.bottom(), plot.top(), 26.0)
    widest = max((am.horizontalAdvance(yaxis.label(t)) for t in yaxis.ticks()), default=10)
    plot.setLeft(inner.left() + widest + 6)
    yaxis.a, yaxis.b = plot.bottom(), plot.top()
    if kind == "scatter":
        xs_all = [x for d in data for x in d.xs if x is not None]
        for i, d in enumerate(data):
            err = CD.error_amounts(wb, d.xs, spec["series"][i].get("x_error"))
            for v, e in zip(d.xs, err):
                if v is not None and e is not None and e[0] != "mean":
                    xs_all += [v - e[0], v + e[1]]
        xaxis = _make_axis(xa_spec, xs_all, plot.width(), plot.left(), plot.right(), 50.0)
        category = None
    else:
        xaxis = None
        category = max((len(d.ys) for d in data), default=0)
    painter.save()
    painter.setClipRect(rect)
    # gridlines and tick labels
    grid = QPen(GRID, 0.75)
    painter.setFont(af)
    for t in yaxis.ticks():
        y = yaxis.at(t)
        if y is None:
            continue
        if ya_spec.get("gridlines", True):
            painter.setPen(grid)
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
        painter.setPen(TEXT)
        painter.drawText(QRectF(inner.left(), y - am.height() / 2, plot.left() - inner.left() - 4,
                                am.height()), Qt.AlignRight | Qt.AlignVCenter, yaxis.label(t))
    if xaxis is not None:
        for t in xaxis.ticks():
            x = xaxis.at(t)
            if x is None:
                continue
            if xa_spec.get("gridlines", False):
                painter.setPen(grid)
                painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            painter.setPen(TEXT)
            text = xaxis.label(t)
            w = am.horizontalAdvance(text)
            painter.drawText(QRectF(x - w / 2 - 2, plot.bottom() + 3, w + 4, am.height()),
                             Qt.AlignCenter, text)
        zero = yaxis.at(0.0) if not yaxis.log and yaxis.lo < 0 < yaxis.hi else plot.bottom()
        painter.setPen(QPen(GRID, 0.75))
        painter.drawLine(QPointF(plot.left(), zero), QPointF(plot.right(), zero))
    else:
        band = plot.width() / max(category, 1)
        labels = next((d.categories for d in data if d.categories), [])
        painter.setPen(TEXT)
        step = max(1, int(math.ceil(max((am.horizontalAdvance(t) for t in labels), default=1)
                                     / max(band - 4, 1))))
        for i in range(category):
            if i % step:
                continue
            text = labels[i] if i < len(labels) else str(i + 1)
            painter.drawText(QRectF(plot.left() + band * i, plot.bottom() + 3, band * step,
                                    am.height()), Qt.AlignHCenter | Qt.AlignTop, text)
        base = yaxis.at(0.0) if not yaxis.log and yaxis.lo <= 0 <= yaxis.hi else plot.bottom()
        painter.setPen(QPen(GRID, 0.75))
        painter.drawLine(QPointF(plot.left(), base), QPointF(plot.right(), base))
    # the series
    painter.setClipRect(plot.adjusted(-6, -6, 6, 6))
    k = len(data)
    placed = []                     # every point drawn, so labels keep clear of them
    labels = []                     # trendlines' equations, placed once all is drawn
    for i, d in enumerate(data):
        colour = QColor(colours[i])
        s = spec["series"][i]
        if kind == "column":
            band = plot.width() / max(category, 1)
            w = band / (k + 0.27 * (k - 1) + 2.19)
            base = yaxis.at(0.0) if not yaxis.log and yaxis.lo <= 0 <= yaxis.hi else \
                (plot.bottom() if (yaxis.lo >= 0 or yaxis.log) else plot.top())
            points = []
            for j, v in enumerate(d.ys):
                x0 = plot.left() + band * j + (band - (k * w + (k - 1) * 0.27 * w)) / 2 + i * 1.27 * w
                y = yaxis.at(v)
                if y is None:
                    points.append(None)
                    continue
                painter.fillRect(QRectF(x0, min(y, base), w, abs(base - y)), colour)
                points.append(QPointF(x0 + w / 2, y))
        else:
            points = []
            for j, v in enumerate(d.ys):
                if kind == "scatter":
                    x = xaxis.at(d.xs[j]) if j < len(d.xs) else None
                else:
                    band = plot.width() / max(category, 1)
                    x = plot.left() + band * (j + 0.5)
                y = yaxis.at(v)
                points.append(QPointF(x, y) if x is not None and y is not None else None)
            lines = spec.get("lines", kind == "line")
            if lines:
                path = QPainterPath()
                started = False
                for p in points:
                    if p is None:
                        started = False
                        continue
                    if not started:
                        path.moveTo(p)
                        started = True
                    else:
                        path.lineTo(p)
                line = QPen(colour, 2.25)
                line.setCapStyle(Qt.RoundCap)
                line.setJoinStyle(Qt.RoundJoin)
                painter.setPen(line)
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(path)
            if spec.get("markers", kind != "line"):
                painter.setPen(QPen(colour, 0.75))
                painter.setBrush(QBrush(colour))
                for p in points:
                    if p is not None:
                        painter.drawEllipse(p, 2.5, 2.5)
        placed.append([p for p in points if p is not None])
        # error bars
        _error_bars(painter, wb, d.ys, s.get("error"), points, yaxis, vertical=True)
        if kind == "scatter":
            _error_bars(painter, wb, d.xs, s.get("x_error"), points, xaxis, vertical=False)
        # trendline
        trend = s.get("trend")
        if trend and trend.get("type"):
            xs = d.xs if kind == "scatter" else [float(j + 1) for j in range(len(d.ys))]
            label = _trendline(painter, xs, d.ys, trend, colour, xaxis, yaxis, plot, kind, category)
            if label:
                labels.append(label)
    if labels:
        _trend_labels(painter, labels, plot, [p for pts in placed for p in pts])
    painter.restore()
    painter.restore()


def _legend_key(painter, box: QRectF, colour: str, kind: str, spec: dict, trend: bool) -> None:
    painter.save()
    c = QColor(colour)
    mid = box.center()
    if trend:
        pen = QPen(c, 1.5, Qt.DotLine)
        painter.setPen(pen)
        painter.drawLine(QPointF(box.left() + 1, mid.y()), QPointF(box.right() - 1, mid.y()))
    elif kind == "column":
        painter.fillRect(QRectF(mid.x() - 3, mid.y() - 3, 6, 6), c)
    else:
        if spec.get("lines", kind == "line"):
            painter.setPen(QPen(c, 2.25))
            painter.drawLine(QPointF(box.left() + 1, mid.y()), QPointF(box.right() - 1, mid.y()))
        if spec.get("markers", kind != "line"):
            painter.setPen(QPen(c, 0.75))
            painter.setBrush(c)
            painter.drawEllipse(mid, 2.5, 2.5)
    painter.restore()


def _error_bars(painter, wb, values, err_spec, points, axis, vertical: bool) -> None:
    if not err_spec or not err_spec.get("type") or axis is None:
        return
    amounts = CD.error_amounts(wb, values, err_spec)
    direction = err_spec.get("direction", "both")      # both, plus, minus
    pen = QPen(QColor("#404040"), 0.75)
    painter.setPen(pen)
    cap = 3.0 if err_spec.get("cap", True) else 0.0
    for v, e, p in zip(values, amounts, points):
        if v is None or e is None or p is None:
            continue
        if e[0] == "mean":
            low, high = e[1] - e[2], e[1] + e[2]
        else:
            low, high = v - e[0], v + e[1]
        ends = []
        if direction in ("both", "plus"):
            ends.append(axis.at(high))
        if direction in ("both", "minus"):
            ends.append(axis.at(low))
        for end in ends:
            if end is None:
                continue
            if vertical:
                painter.drawLine(QPointF(p.x(), p.y() if e[0] != "mean" else axis.at(e[1])),
                                 QPointF(p.x(), end))
                if cap:
                    painter.drawLine(QPointF(p.x() - cap, end), QPointF(p.x() + cap, end))
            else:
                painter.drawLine(QPointF(p.x(), p.y()), QPointF(end, p.y()))
                if cap:
                    painter.drawLine(QPointF(end, p.y() - cap), QPointF(end, p.y() + cap))


def _trendline(painter, xs, ys, spec, colour, xaxis, yaxis, plot, kind, category) -> list:
    fit = CD.fit_trend(xs, ys, spec["type"], spec.get("order", 2), spec.get("period", 2),
                       spec.get("intercept"))
    if fit is None:
        return
    pen = QPen(colour, 1.5, Qt.DotLine)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    def at_x(x):
        if kind == "scatter":
            return xaxis.at(x)
        band = plot.width() / max(category, 1)
        return plot.left() + band * (x - 0.5)

    path = QPainterPath()
    if fit.f is None:
        started = False
        for x, y in fit.points:
            px, py = at_x(x), yaxis.at(y)
            if px is None or py is None:
                continue
            if not started:
                path.moveTo(px, py)
                started = True
            else:
                path.lineTo(px, py)
    else:
        nums = [x for x in xs if x is not None]
        lo, hi = min(nums), max(nums)
        if kind == "scatter" and xaxis.log:
            samples = [10 ** (math.log10(lo) + (math.log10(hi) - math.log10(lo)) * i / 100)
                       for i in range(101)] if lo > 0 else []
        else:
            samples = [lo + (hi - lo) * i / 100 for i in range(101)]
        started = False
        for x in samples:
            try:
                y = fit.f(x)
            except (ValueError, OverflowError, ZeroDivisionError):
                y = float("nan")
            px, py = at_x(x), yaxis.at(y) if math.isfinite(y) else None
            if px is None or py is None:
                started = False
                continue
            if not started:
                path.moveTo(px, py)
                started = True
            else:
                path.lineTo(px, py)
    painter.drawPath(path)
    lines = []
    if spec.get("equation") and fit.f is not None:
        lines.append(fit.label)
    if spec.get("r2") and fit.r2 is not None:
        lines.append(f"R² = {fit.r2:.4f}")
    return lines


def _trend_labels(painter, labels: list, plot: QRectF, points: list) -> None:
    """The trendlines' equations, each in the corner of the plot the data
    leave clearest."""
    f = _font(9)
    painter.setFont(f)
    painter.setPen(TEXT)
    m = QFontMetricsF(f)
    h = m.height()
    used = []
    for lines in labels:
        w = max(m.horizontalAdvance(t) for t in lines)
        tall = h * len(lines)
        corners = [QRectF(plot.right() - w - 6, plot.top() + 4, w + 4, tall),
                   QRectF(plot.left() + 6, plot.top() + 4, w + 4, tall),
                   QRectF(plot.right() - w - 6, plot.bottom() - 4 - tall, w + 4, tall),
                   QRectF(plot.left() + 6, plot.bottom() - 4 - tall, w + 4, tall)]
        free = [b for b in corners if not any(b.intersects(u) for u in used)] or corners
        box = min(free, key=lambda b: sum(1 for p in points if b.adjusted(-14, -14, 14, 14).contains(p)))
        used.append(box)
        left = box.left() < plot.center().x()
        for i, t in enumerate(lines):
            painter.drawText(QRectF(box.left(), box.top() + i * h, box.width(), h),
                             (Qt.AlignLeft if left else Qt.AlignRight) | Qt.AlignVCenter, t)
