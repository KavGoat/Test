"""What a chart shows, worked out from its cells (no drawing here).

The user's choices (docs/SPREADSHEET_DESIGN.md, phase 5): XY scatter, line
and column charts with log axes, error bars and trendlines, in Excel's
default look, units from the cells shown in the axis titles.

* :func:`read_series` — a series' values from its ranges (formula text such
  as ``Loads!$B$2:$B$9``), quantities in the unit they are shown in;
* :func:`nice_scale` / :func:`log_scale` — Excel's automatic axis bounds and
  major unit;
* :func:`fit_trend` — Excel's trendlines (linear, polynomial, exponential,
  logarithmic, power, moving average) with their equation and R²;
* :func:`error_amounts` — Excel's error bars (fixed, percentage, standard
  deviation, standard error, custom ranges).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .values import BLANK, Array, ErrorValue, Qty, default_unit, general_number

OFFICE = ("#4472C4", "#ED7D31", "#A5A5A5", "#FFC000", "#5B9BD5", "#70AD47",
          "#264478", "#9E480E", "#636363", "#997300", "#255E91", "#43682B")


@dataclass
class Series:
    name: str = ""
    xs: list = field(default_factory=list)          # numbers (scatter) or None
    ys: list = field(default_factory=list)          # numbers, None where there is no number
    categories: list = field(default_factory=list)  # labels for line and column charts
    x_unit: str = ""
    y_unit: str = ""
    problem: str = ""


def _evaluate(wb, text: str, home=None):
    """A range or value written as a formula (without "=")."""
    from . import formula as F
    from .evaluate import Ctx, RefValue, ev
    from .values import SheetError

    text = (text or "").strip().lstrip("=")
    if not text:
        return None
    try:
        tree = F.parse(text).tree
    except F.FormulaError:
        return ErrorValue("#NAME?")
    sheet = home or (wb.sheets[0] if wb.sheets else None)
    if sheet is None:
        return ErrorValue("#REF!")
    try:
        got = ev(tree, Ctx(wb, sheet, 0, 0))
    except SheetError as e:
        return e.error
    if isinstance(got, RefValue):
        got = got.value_at(0, 0) if got.single else got.to_array()
    return got


def _flat(value) -> list:
    if value is None:
        return []
    if isinstance(value, Array):
        return list(value.values())
    return [value]


def _number(v) -> tuple:
    """(number in its shown unit, unit) of a cell value, or (None, "")."""
    if isinstance(v, bool):
        return None, ""
    if isinstance(v, (int, float)):
        return float(v), ""
    if isinstance(v, Qty):
        unit = v.unit or default_unit(v.dims)
        return float(v.shown()), unit
    return None, ""


def label_text(v) -> str:
    from .numfmt import format_value
    if v is None or v is BLANK:
        return ""
    if isinstance(v, str):
        return v
    return format_value(v).text


def read_series(wb, spec: dict, numeric_x: bool) -> Series:
    """One series of a chart: its name, x values (numbers for a scatter
    chart, labels otherwise) and y values."""
    out = Series()
    name = spec.get("name", "")
    if isinstance(name, str) and name.startswith("="):
        got = _evaluate(wb, name)
        out.name = label_text(_flat(got)[0] if _flat(got) else "")
    else:
        out.name = name or ""
    ys_raw = _flat(_evaluate(wb, spec.get("y", "")))
    xs_raw = _flat(_evaluate(wb, spec.get("x", ""))) if spec.get("x") else []
    if any(isinstance(v, ErrorValue) for v in ys_raw[:1]) and len(ys_raw) == 1:
        out.problem = ys_raw[0].code
        return out
    units = set()
    for v in ys_raw:
        n, unit = _number(v)
        out.ys.append(n)
        if unit:
            units.add(unit)
    out.y_unit = units.pop() if len(units) == 1 else ""
    if numeric_x:
        if xs_raw:
            units = set()
            for v in xs_raw[:len(out.ys)]:
                n, unit = _number(v)
                out.xs.append(n)
                if unit:
                    units.add(unit)
            out.x_unit = units.pop() if len(units) == 1 else ""
            while len(out.xs) < len(out.ys):
                out.xs.append(None)
        else:
            out.xs = [float(i + 1) for i in range(len(out.ys))]
    else:
        out.categories = [label_text(v) for v in xs_raw] if xs_raw else \
            [str(i + 1) for i in range(len(out.ys))]
    return out


# -- axes ---------------------------------------------------------------------------------------
def nice_step(span: float, ticks: float) -> float:
    raw = span / max(ticks, 1.0)
    if raw <= 0 or not math.isfinite(raw):
        return 1.0
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 5, 10):
        if raw <= m * mag * 1.0000001:
            return m * mag
    return 10 * mag


def nice_scale(lo: float, hi: float, ticks: float = 6, fixed_min=None, fixed_max=None,
               major=None) -> tuple:
    """(min, max, major unit) as Excel chooses them: zero kept when the data
    are well clear of it, a little room above the top value, round steps."""
    if lo is None or hi is None:
        lo, hi = 0.0, 1.0
    if lo > hi:
        lo, hi = hi, lo
    if lo == hi:
        pad = abs(lo) * 0.1 or 1.0
        lo, hi = lo - pad, hi + pad
        if lo < 0 <= lo + pad:
            lo = 0.0
    if fixed_min is None:
        if lo >= 0 and hi > 0 and (hi - lo) / hi > 1 / 6:
            lo = 0.0
    if fixed_max is None:
        if hi <= 0 and lo < 0 and (hi - lo) / -lo > 1 / 6:
            hi = 0.0
    a = fixed_min if fixed_min is not None else lo
    b = fixed_max if fixed_max is not None else hi
    step = major or nice_step(b - a, ticks)
    if fixed_max is None and hi != 0:
        b = b + 0.05 * (b - a)              # Excel's room above the highest value
    if fixed_min is None:
        a = math.floor(a / step + 1e-9) * step
    if fixed_max is None:
        b = math.ceil(b / step - 1e-9) * step
    if b <= a:
        b = a + step
    return a, b, step


def log_scale(lo: float, hi: float, fixed_min=None, fixed_max=None) -> tuple:
    """(min, max) of a base-10 log axis: whole decades round the data."""
    lo = lo if lo and lo > 0 else 1.0
    hi = hi if hi and hi > 0 else lo * 10
    a = fixed_min if fixed_min and fixed_min > 0 else 10 ** math.floor(math.log10(lo) + 1e-9)
    b = fixed_max if fixed_max and fixed_max > 0 else 10 ** math.ceil(math.log10(hi) - 1e-9)
    if b <= a:
        b = a * 10
    return a, b


def ticks(a: float, b: float, step: float) -> list:
    out = []
    n = int(round((b - a) / step))
    for i in range(min(n, 200) + 1):
        v = a + i * step
        out.append(0.0 if abs(v) < step * 1e-9 else v)
    return out


def log_ticks(a: float, b: float) -> list:
    out = []
    k = math.floor(math.log10(a) + 1e-9)
    while 10 ** k <= b * 1.0000001:
        out.append(10.0 ** k)
        k += 1
    return out


def tick_label(v: float, step: Optional[float] = None) -> str:
    """An axis number as Excel's General shows it."""
    if step is not None and step < 1 and v != 0:
        places = max(0, -int(math.floor(math.log10(step) + 1e-9)))
        return f"{v:.{places}f}"
    if v == int(v) and abs(v) < 1e15:
        return str(int(v))
    return general_number(v)


# -- trendlines ----------------------------------------------------------------------------------
@dataclass
class Trend:
    kind: str
    f: object                 # callable(x) -> y, or None (moving average)
    label: str                # the equation as Excel shows it
    r2: Optional[float]
    points: list = field(default_factory=list)    # moving average: (x, y)


def _num(v: float) -> str:
    if v == 0:
        return "0"
    mag = abs(v)
    if mag >= 1e5 or mag < 1e-3:
        return f"{v:.4E}".replace("E+0", "E+").replace("E-0", "E-")
    return f"{v:.4f}".rstrip("0").rstrip(".")


def _r2(ys, fitted) -> float:
    mean = sum(ys) / len(ys)
    tot = sum((y - mean) ** 2 for y in ys)
    res = sum((y - f) ** 2 for y, f in zip(ys, fitted))
    return 1.0 - res / tot if tot > 0 else 1.0


def fit_trend(xs: list, ys: list, kind: str, order: int = 2, period: int = 2,
              intercept: Optional[float] = None) -> Optional[Trend]:
    """Excel's trendline of a series (points without a number left out)."""
    import numpy as np

    pts = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if kind == "moving":
        period = max(2, int(period))
        if len(pts) < period:
            return None
        out = []
        for i in range(period - 1, len(pts)):
            window = pts[i - period + 1:i + 1]
            out.append((pts[i][0], sum(p[1] for p in window) / period))
        return Trend(kind, None, f"{period} per. Mov. Avg.", None, out)
    if len(pts) < 2:
        return None
    x = np.array([p[0] for p in pts], dtype=float)
    y = np.array([p[1] for p in pts], dtype=float)
    if kind == "linear":
        if intercept is not None:
            m = float(np.sum(x * (y - intercept)) / np.sum(x * x)) if np.sum(x * x) else 0.0
            b = float(intercept)
        else:
            m, b = (float(v) for v in np.polyfit(x, y, 1))
        f = lambda t, m=m, b=b: m * t + b       # noqa: E731
        sign = "+" if b >= 0 else "-"
        label = f"y = {_num(m)}x {sign} {_num(abs(b))}" if b != 0 else f"y = {_num(m)}x"
        return Trend(kind, f, label, _r2(y, m * x + b))
    if kind == "poly":
        order = max(2, min(6, int(order)))
        if len(pts) <= order:
            return None
        c = [float(v) for v in np.polyfit(x, y, order)]
        f = lambda t, c=c: sum(k * t ** (len(c) - 1 - i) for i, k in enumerate(c))  # noqa: E731
        terms = []
        for i, k in enumerate(c):
            p = len(c) - 1 - i
            body = _num(abs(k)) + ("x" if p >= 1 else "") + (f"{_sup(p)}" if p >= 2 else "")
            terms.append(("-" if k < 0 else "+", body))
        label = "y = " + ("-" if terms[0][0] == "-" else "") + terms[0][1]
        for sign, body in terms[1:]:
            label += f" {sign} {body}"
        return Trend(kind, f, label, _r2(y, np.array([f(t) for t in x])))
    if kind == "exp":
        if np.any(y <= 0):
            return None
        bb, ln_a = (float(v) for v in np.polyfit(x, np.log(y), 1))
        a = math.exp(ln_a)
        f = lambda t, a=a, bb=bb: a * math.exp(bb * t)  # noqa: E731
        # Excel's R² for an exponential fit is that of ln y
        return Trend(kind, f, f"y = {_num(a)}e{_sup_text(_num(bb) + 'x')}",
                     _r2(np.log(y), ln_a + bb * x))
    if kind == "log":
        if np.any(x <= 0):
            return None
        a, b = (float(v) for v in np.polyfit(np.log(x), y, 1))
        f = lambda t, a=a, b=b: a * math.log(t) + b if t > 0 else float("nan")  # noqa: E731
        sign = "+" if b >= 0 else "-"
        return Trend(kind, f, f"y = {_num(a)}ln(x) {sign} {_num(abs(b))}", _r2(y, a * np.log(x) + b))
    if kind == "power":
        if np.any(x <= 0) or np.any(y <= 0):
            return None
        bb, ln_a = (float(v) for v in np.polyfit(np.log(x), np.log(y), 1))
        a = math.exp(ln_a)
        f = lambda t, a=a, bb=bb: a * t ** bb if t > 0 else float("nan")  # noqa: E731
        return Trend(kind, f, f"y = {_num(a)}x{_sup_text(_num(bb))}",
                     _r2(np.log(y), ln_a + bb * np.log(x)))
    return None


_SUP = str.maketrans("0123456789-.E+x", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻·ᴱ⁺ˣ")


def _sup(p: int) -> str:
    return str(p).translate(_SUP)


def _sup_text(text: str) -> str:
    return text.translate(_SUP)


# -- error bars -------------------------------------------------------------------------------------
def error_amounts(wb, values: list, spec: Optional[dict]) -> list:
    """(minus, plus) for each value, as Excel's error bars: fixed value,
    percentage, standard deviation (centred on the mean, as Excel draws
    them), standard error, or custom ranges."""
    if not spec or not spec.get("type"):
        return [None] * len(values)
    kind = spec["type"]
    nums = [v for v in values if v is not None]
    amount = float(spec.get("value", 0) or 0)
    if kind == "fixed":
        return [(amount, amount) if v is not None else None for v in values]
    if kind == "percent":
        return [(abs(v) * amount / 100, abs(v) * amount / 100) if v is not None else None
                for v in values]
    if kind in ("stddev", "stderr"):
        if len(nums) < 2:
            return [None] * len(values)
        mean = sum(nums) / len(nums)
        sd = math.sqrt(sum((v - mean) ** 2 for v in nums) / (len(nums) - 1))
        if kind == "stderr":
            se = sd / math.sqrt(len(nums))
            return [(se, se) if v is not None else None for v in values]
        k = amount or 1.0
        # drawn round the series' mean, not each point (Excel)
        return [("mean", mean, k * sd) if v is not None else None for v in values]
    if kind == "custom":
        plus = [_number(v)[0] for v in _flat(_evaluate(wb, spec.get("plus", "")))]
        minus = [_number(v)[0] for v in _flat(_evaluate(wb, spec.get("minus", "")))]
        out = []
        for i, v in enumerate(values):
            if v is None:
                out.append(None)
                continue
            p = plus[i] if i < len(plus) else (plus[0] if len(plus) == 1 else 0.0)
            m = minus[i] if i < len(minus) else (minus[0] if len(minus) == 1 else 0.0)
            out.append((abs(m or 0.0), abs(p or 0.0)))
        return out
    return [None] * len(values)


def sheets_read(spec: dict) -> set:
    """The sheet names a chart's ranges read (lower case)."""
    from . import formula as F
    out = set()
    for s in spec.get("series", []):
        for key in ("x", "y", "name"):
            text = (s.get(key) or "")
            if not isinstance(text, str):
                continue
            try:
                tokens = F.tokenize(text.lstrip("="))
            except F.FormulaError:
                continue
            for t in tokens:
                if t.kind == "ref" and t.ref.sheet:
                    out.add(t.ref.sheet.lower())
                elif t.kind == "struct" and t.ref.table:
                    out.add(t.ref.table.lower())
        for key in ("plus", "minus"):
            text = (s.get("error") or {}).get(key) or ""
            try:
                for t in F.tokenize(text.lstrip("=")):
                    if t.kind == "ref" and t.ref.sheet:
                        out.add(t.ref.sheet.lower())
            except F.FormulaError:
                pass
    return out
