"""2-D plot regions (Qt-free part): view state, axis ticks and curve sampling.

Matches SMath's 2-D plot as rendered by SMath Cloud: a white area with a black
frame, light grey (#d3d3d3) grid lines, black axes through the origin labelled
x and y, grey (#808080) 8pt tick numbers along the bottom and left edges, and
curves coloured blue, red, green... in the order they are listed.  The input
(one expression, or several joined by commas and shown with a brace) sits
under the plot; each expression is a function of x, or a matrix of points
(n×2: x in the first column, y in the second).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .engine.errors import SMathError
from .engine.values import Matrix, Q
from .engine.units import Quantity

# SMath stores scale_x/scale_y; one unit is this many pixels per scale step
# (MaclaurinSeries.sm: scale 1.6347 draws 20.5 px per unit).
PX_PER_SCALE = 12.54
CURVE_COLORS = ["#0000ff", "#ff0000", "#008000", "#ff00ff", "#ffa500", "#00ffff", "#800000", "#000080"]
GRID_COLOR = "#d3d3d3"
LABEL_COLOR = "#808080"


@dataclass
class PlotState:
    width: float = 300.0
    height: float = 200.0
    ppu_x: float = 20.5  # pixels per unit
    ppu_y: float = 20.5
    pan_x: float = 0.0  # origin offset from the centre, pixels
    pan_y: float = 0.0
    grid: bool = True
    axes: bool = True
    points: bool = False  # "Graph by points" instead of lines

    # -- mapping ------------------------------------------------------------------
    @property
    def origin(self) -> tuple[float, float]:
        return self.width / 2 + self.pan_x, self.height / 2 + self.pan_y

    def to_px(self, x: float, y: float) -> tuple[float, float]:
        ox, oy = self.origin
        return ox + x * self.ppu_x, oy - y * self.ppu_y

    def from_px(self, px: float, py: float) -> tuple[float, float]:
        ox, oy = self.origin
        return (px - ox) / self.ppu_x, (oy - py) / self.ppu_y

    def x_range(self) -> tuple[float, float]:
        return self.from_px(0, 0)[0], self.from_px(self.width, 0)[0]

    def y_range(self) -> tuple[float, float]:
        return self.from_px(0, self.height)[1], self.from_px(0, 0)[1]

    def zoom(self, factor: float, px: float, py: float, x: bool = True, y: bool = True) -> None:
        """Zoom by factor keeping the point under (px, py) fixed."""
        ux, uy = self.from_px(px, py)
        if x:
            self.ppu_x = min(1e9, max(1e-9, self.ppu_x * factor))
        if y:
            self.ppu_y = min(1e9, max(1e-9, self.ppu_y * factor))
        nx, ny = self.to_px(ux, uy)
        self.pan_x += px - nx
        self.pan_y += py - ny

    # -- .sm attributes ---------------------------------------------------------------
    @property
    def scale_x(self) -> float:
        return self.ppu_x / PX_PER_SCALE

    @property
    def scale_y(self) -> float:
        return self.ppu_y / PX_PER_SCALE


def nice_step(ppu: float, min_px: float) -> float:
    """Smallest 1/2/5·10^k step that is at least min_px pixels long."""
    raw = min_px / ppu
    k = math.floor(math.log10(raw))
    for m in (1, 2, 5, 10):
        step = m * 10 ** k
        if step * ppu >= min_px - 1e-9:
            return step
    return 10 ** (k + 1)


def ticks(lo: float, hi: float, step: float) -> list[float]:
    start = math.ceil(lo / step)
    end = math.floor(hi / step)
    out = []
    for i in range(start, end + 1):
        v = i * step
        out.append(0.0 if abs(v) < step * 1e-9 else v)
    return out


def tick_label(v: float, step: float) -> str:
    if step >= 1:
        return str(int(round(v)))
    digits = max(0, -math.floor(math.log10(step)))
    return f"{v:.{digits}f}"


def axis_layout(state: PlotState) -> dict:
    """Grid lines and labelled ticks (SMath: grid every unit at 20 px/unit,
    y labels every unit, x labels every 2 units - x labels need more room)."""
    x0, x1 = state.x_range()
    y0, y1 = state.y_range()
    gx = nice_step(state.ppu_x, 15)
    gy = nice_step(state.ppu_y, 15)
    lx = nice_step(state.ppu_x, 34)
    ly = nice_step(state.ppu_y, 18)
    return {
        "grid_x": ticks(x0, x1, gx), "grid_y": ticks(y0, y1, gy),
        "label_x": [(v, tick_label(v, lx)) for v in ticks(x0, x1, lx)],
        "label_y": [(v, tick_label(v, ly)) for v in ticks(y0, y1, ly)],
    }


def fit_ranges(state: PlotState, x0: float, x1: float, y0: float, y1: float) -> None:
    """Show exactly x0..x1 across and y0..y1 up (Plot settings)."""
    if not (x1 > x0 and y1 > y0):
        raise ValueError("empty range")
    state.ppu_x = state.width / (x1 - x0)
    state.ppu_y = state.height / (y1 - y0)
    state.pan_x = -x0 * state.ppu_x - state.width / 2
    state.pan_y = y1 * state.ppu_y - state.height / 2


# SMath's styled points (a matrix of 5 or more columns): x, y, "marker or text",
# size in pixels, "colour".  The markers are x, *, . and o; any other text is
# written at the point.  Colours are .NET colour names ("Red", "Green"...).
MARKERS = {"x", "*", ".", "o"}


def marks(value, state: PlotState) -> list:
    """(px, py, text, size, colour) for each row of a styled-points matrix,
    or [] when the value is not one."""
    from .engine.values import String

    if not isinstance(value, Matrix) or value.ncols < 5:
        return []
    out = []
    for i in range(value.nrows):
        x, y = _scalar(value.get(i, 0)), _scalar(value.get(i, 1))
        if x is None or y is None:
            continue
        t = value.get(i, 2)
        text = t.text if isinstance(t, String) else (f"{_scalar(t):g}" if _scalar(t) is not None else "")
        size = _scalar(value.get(i, 3)) or 5.0
        c = value.get(i, 4)
        colour = c.text if isinstance(c, String) else "Black"
        out.append((*state.to_px(x, y), text, max(1.0, float(size)), colour))
    return out


def parts(value) -> list:
    """The plots inside a sys(...) or a matrix of matrices (SMath draws each
    one), or [value] itself."""
    if isinstance(value, Matrix) and value.items and all(isinstance(x, Matrix) for x in value.items):
        out = []
        for x in value.items:
            out.extend(parts(x))
        return out
    return [value]


def point_lines(value, state: PlotState):
    """The polyline of a two-column matrix of points, or None."""
    if isinstance(value, Matrix) and value.ncols == 2 and value.nrows >= 1:
        pts = []
        for i in range(value.nrows):
            x, y = _scalar(value.get(i, 0)), _scalar(value.get(i, 1))
            if x is not None and y is not None:
                pts.append(state.to_px(x, y))
        return [pts]
    return None


def _scalar(v):
    if isinstance(v, Quantity):
        return v.real if not isinstance(v.value, complex) or v.value.imag == 0 else None
    if isinstance(v, Matrix) and v.nrows == v.ncols == 1:
        return _scalar(v.items[0])
    return None


def sample(node, ctx, evaluator, state: PlotState, var: str = "x"):
    """Polylines (lists of (px, py)) for one input expression.

    A function of x is sampled once per pixel; gaps are left where it cannot
    be evaluated or jumps off the plot.  A matrix with two columns is drawn
    as connected points.
    """
    from .engine.evaluator import Context

    # a matrix of points does not depend on x
    try:
        const = evaluator.eval(node, ctx)
    except SMathError:
        const = None
    if isinstance(const, Matrix) and const.ncols >= 5:
        return [], None  # styled points: drawn by marks()
    if isinstance(const, Matrix) and len(parts(const)) > 1:
        return [], None  # several plots: drawn part by part (see parts())
    pts = point_lines(const, state)
    if pts is not None:
        return pts, None

    local = Context(ctx)
    lines, cur = [], []
    first_error = None
    n = max(2, int(state.width))
    limit = state.height * 20
    prev_py = None
    for i in range(n + 1):
        px = state.width * i / n
        x, _ = state.from_px(px, 0)
        local.vars[var] = Q(x)
        try:
            y = _scalar(evaluator.eval(node, local))
        except SMathError as e:
            y = None
            if first_error is None:
                first_error = e
        except (ValueError, OverflowError, ZeroDivisionError):
            y = None
        if y is None or not math.isfinite(y):
            if cur:
                lines.append(cur)
            cur, prev_py = [], None
            continue
        _, py = state.to_px(x, y)
        if abs(py) > limit or (prev_py is not None and abs(py - prev_py) > state.height * 4):
            # a pole: break the line rather than draw a vertical stroke
            if cur:
                lines.append(cur)
            cur = []
            prev_py = py
            if abs(py) > limit:
                prev_py = None
                continue
        cur.append((px, py))
        prev_py = py
    if cur:
        lines.append(cur)
    if not any(len(l) > 1 for l in lines) and first_error is not None:
        return [], first_error
    return lines, None

