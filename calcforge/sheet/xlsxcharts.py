"""An Excel worksheet's charts and pictures as CalcForge's own markups.

The user, 2026-10-23: "the charts aren't pulling through". A chart Excel
draws as an XY scatter, a line or a column chart comes in as one of
CalcForge's: its series reading the same cells, its title, axis titles,
axis limits, log scales, gridlines and legend; placed where Excel anchors it
(the cell its corner is in and the offset into it) and as big as Excel shows
it, so it moves with the cells like any markup on a spreadsheet page. A
chart of another kind (pie, area, 3-D …) is left out, and said so. A picture
comes in as an image markup, placed and sized the same way.
"""
from __future__ import annotations

from typing import Callable, Optional

EMU_PER_PT = 12700

LEGEND = {"r": "right", "b": "bottom", "t": "top", "l": "right", "tr": "right"}


def _rich_text(title) -> Optional[str]:
    """A title's words, or None when it has none of its own (Excel's own
    words, the series' name, are shown then)."""
    if title is None or title.tx is None:
        return None
    tx = title.tx
    if tx.rich is not None:
        lines = []
        for p in tx.rich.p or []:
            lines.append("".join((r.t or "") for r in (p.r or [])))
        text = " ".join(line.strip() for line in lines if line.strip())
        return text or None
    if tx.strRef is not None and tx.strRef.f:
        return "=" + tx.strRef.f
    return None


def _ref_text(data_source) -> str:
    """The cells a series' values come from (Sheet!$A$1:$A$9), "" if none."""
    if data_source is None:
        return ""
    for kind in ("numRef", "strRef"):
        ref = getattr(data_source, kind, None)
        if ref is not None and ref.f:
            return ref.f
    return ""


def _series_name(series) -> str:
    tx = series.tx
    if tx is None:
        return ""
    if tx.strRef is not None and tx.strRef.f:
        return "=" + tx.strRef.f
    return tx.v or ""


def _colour(series) -> Optional[str]:
    sp = series.spPr
    for fill in (getattr(getattr(sp, "ln", None), "solidFill", None), getattr(sp, "solidFill", None)):
        rgb = getattr(fill, "srgbClr", None)
        value = getattr(rgb, "val", None) if rgb is not None else None
        if isinstance(value, str) and len(value) == 6:
            return "#" + value.upper()
    return None


def _line_shown(series) -> bool:
    ln = getattr(series.spPr, "ln", None) if series.spPr is not None else None
    return not (ln is not None and ln.noFill)


def _marker_shown(series, default: bool) -> bool:
    marker = series.marker
    if marker is None or marker.symbol is None:
        return default
    return marker.symbol != "none"


def _axis(axis, gridlines_default: bool) -> dict:
    out = {"min": None, "max": None, "major": None, "log": False, "gridlines": gridlines_default}
    if axis is None:
        return out
    scaling = getattr(axis, "scaling", None)
    if scaling is not None:
        out["min"] = float(scaling.min) if scaling.min is not None else None
        out["max"] = float(scaling.max) if scaling.max is not None else None
        out["log"] = bool(scaling.logBase)
    major = getattr(axis, "majorUnit", None)        # (a category axis has none)
    if major is not None:
        out["major"] = float(major)
    out["gridlines"] = getattr(axis, "majorGridlines", None) is not None
    return out


def chart_spec(chart, renamed: Callable[[str], str]) -> Optional[dict]:
    """The spec (items/chart.py new_spec) of an openpyxl chart, or None for
    a kind CalcForge does not draw."""
    kind = type(chart).__name__
    if kind == "ScatterChart":
        style = chart.scatterStyle or "marker"
        series = list(chart.series)
        lines = style != "marker" and any(_line_shown(s) for s in series)
        markers = any(_marker_shown(s, style in ("marker", "lineMarker", "smoothMarker", None))
                      for s in series) or not lines
        spec_kind = "scatter"
    elif kind == "LineChart":
        series = list(chart.series)
        lines = True
        markers = any(_marker_shown(s, bool(getattr(chart, "marker", True))) for s in series)
        spec_kind = "line"
    elif kind == "BarChart":
        series = list(chart.series)
        lines, markers = False, False
        spec_kind = "column"
    else:
        return None
    title = _rich_text(chart.title)
    if title is None:
        # no words of its own: Excel names a one-series chart after it,
        # unless the title was taken off
        title = "" if getattr(chart, "auto_title_deleted", None) or \
            getattr(chart, "autoTitleDeleted", None) or len(series) != 1 else "auto"
    legend = chart.legend
    spec = {
        "kind": spec_kind,
        "lines": lines,
        "markers": markers,
        "title": "=" + renamed(title[1:]) if title.startswith("=") else title,
        "x_title": _rich_text(chart.x_axis.title) or "",
        "y_title": _rich_text(chart.y_axis.title) or "",
        "legend": "none" if legend is None else LEGEND.get(legend.position or "r", "right"),
        "x_axis": _axis(chart.x_axis, spec_kind == "scatter"),
        "y_axis": _axis(chart.y_axis, True),
        "series": [],
    }
    for s in series:
        if spec_kind == "scatter":
            x, y = _ref_text(s.xVal), _ref_text(s.yVal)
        else:
            x, y = _ref_text(s.cat), _ref_text(s.val)
        if not y:
            continue
        name = _series_name(s)
        if name.startswith("="):
            name = "=" + renamed(name[1:])
        spec["series"].append({
            "name": name, "x": renamed(x) if x else "", "y": renamed(y),
            "color": _colour(s), "error": None, "x_error": None, "trend": None,
        })
    return spec if spec["series"] else None


def _edges(widths: dict, default: float, hidden: set) -> Callable[[int], float]:
    """Where column (or row) k starts, in points."""
    cache = {0: 0.0}

    def at(k: int) -> float:
        if k in cache:
            return cache[k]
        start = max(i for i in cache if i <= k)
        x = cache[start]
        for i in range(start, k):
            x += 0.0 if i in hidden else float(widths.get(str(i), default))
            cache[i + 1] = x
        return x
    return at


def _measures(data: dict) -> tuple:
    col_at = _edges(data.get("widths") or {}, float(data.get("default_width") or 48.0),
                    set(data.get("hidden_cols") or ()))
    row_at = _edges(data.get("heights") or {}, float(data.get("default_height") or 15.0),
                    set(data.get("hidden_rows") or ()))
    return col_at, row_at


def _placed(anchor, col_at, row_at, size_pt: tuple) -> Optional[tuple]:
    """([row, col, dx, dy], width, height) in points of a drawing Excel
    anchors at a cell (to another cell, or with a size of its own)."""
    start = getattr(anchor, "_from", None)
    if start is None:
        return None
    row, col = int(start.row), int(start.col)
    dx, dy = (start.colOff or 0) / EMU_PER_PT, (start.rowOff or 0) / EMU_PER_PT
    end = getattr(anchor, "to", None)
    ext = getattr(anchor, "ext", None)
    if end is not None:
        w = col_at(int(end.col)) + (end.colOff or 0) / EMU_PER_PT - col_at(col) - dx
        h = row_at(int(end.row)) + (end.rowOff or 0) / EMU_PER_PT - row_at(row) - dy
    elif ext is not None and ext.width and ext.height:
        w, h = ext.width / EMU_PER_PT, ext.height / EMU_PER_PT
    else:
        w, h = size_pt
    return [row, col, dx, dy], w, h


def charts_of(ws, data: dict, renamed: Callable[[str], str], left_out: list) -> list:
    """[{"spec", "anchor": [row, col, dx, dy], "w", "h"}] for the worksheet's
    charts (sizes in points), the kinds CalcForge can't draw put in
    *left_out*."""
    found = getattr(ws, "_charts", None) or []
    if not found:
        return []
    col_at, row_at = _measures(data)
    out, skipped = [], 0
    for chart in found:
        try:
            spec = chart_spec(chart, renamed)
        except Exception:  # noqa: BLE001  (a chart openpyxl half read)
            spec = None
        size = (float(chart.width or 15) * 72 / 2.54, float(chart.height or 7.5) * 72 / 2.54)
        placed = _placed(getattr(chart, "anchor", None), col_at, row_at, size)
        if spec is None or placed is None:
            skipped += 1
            continue
        anchor, w, h = placed
        out.append({"spec": spec, "anchor": anchor, "w": max(72.0, w), "h": max(54.0, h)})
    if skipped:
        left_out.append(f"{skipped} chart{'s' * (skipped > 1)} of a kind CalcForge doesn't draw "
                        f"on “{ws.title}”")
    return out


def pictures_of(ws, data: dict, left_out: list, drawn: Optional[list] = None) -> list:
    """[{"data": bytes, "suffix", "anchor", "w", "h"}] for the worksheet's
    pictures, as Excel places and sizes them: every picture of its drawing
    (*drawn*, sheet/xlsxpictures.py: metafiles, groups, cropped ones), else
    those openpyxl kept."""
    if drawn:
        from .xlsxpictures import placed_pictures
        return placed_pictures(ws.title, drawn, data, left_out)
    found = getattr(ws, "_images", None) or []
    if not found:
        return []
    col_at, row_at = _measures(data)
    out, skipped = [], 0
    for image in found:
        try:
            blob = image._data()
        except Exception:  # noqa: BLE001  (a picture openpyxl could not read)
            blob = None
        size = (float(image.width or 0) * 0.75, float(image.height or 0) * 0.75)
        placed = _placed(getattr(image, "anchor", None), col_at, row_at, size)
        if not blob or placed is None:
            skipped += 1
            continue
        anchor, w, h = placed
        suffix = str(getattr(image, "format", "") or "png").lower()
        out.append({"data": blob, "suffix": suffix, "anchor": anchor,
                    "w": max(4.0, w), "h": max(4.0, h)})
    if skipped:
        left_out.append(f"{skipped} picture{'s' * (skipped > 1)} on “{ws.title}”")
    return out
