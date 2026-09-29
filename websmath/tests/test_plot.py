"""2-D plot regions."""
from __future__ import annotations

from pathlib import Path

import pytest

from websmath.io.smfile import dumps, load_sm, loads
from websmath.plot import PlotState, axis_layout, sample
from websmath.worksheet import Worksheet

EXAMPLES = Path(__file__).resolve().parents[2] / "smath" / "SMath Studio" / "examples"


def plot_sheet(*keys_per_curve, defs=()):
    ws = Worksheet()
    for k, d in enumerate(defs):
        r = ws.add_region(18, 9 + 36 * k)
        for key in d:
            r.editor.key(key)
        ws.update_after_edit(r)
    p = ws.add_plot(18, 200)
    for n, keys in enumerate(keys_per_curve):
        if n:
            p.editor.key(",")
        for key in keys:
            p.editor.key(key)
    ws.calculate()
    return ws, p


def test_default_view_matches_smath_grid():
    st = PlotState()
    ax = axis_layout(st)
    # grid every unit, y labels every unit, x labels every 2 units (as SMath at 20.5 px/unit)
    assert ax["grid_x"][:3] == [-7, -6, -5]
    assert [v for v, _ in ax["label_x"]][:3] == [-6, -4, -2]
    assert [v for v, _ in ax["label_y"]][:3] == [-4, -3, -2]


def test_function_curve_is_sampled():
    ws, p = plot_sheet(list("sin(x"))
    lines, err = sample(p.curves[0], p.plot_ctx, ws.evaluator, p.plot)
    assert err is None and len(lines) == 1 and len(lines[0]) > 100
    ox, oy = p.plot.origin
    mid = min(lines[0], key=lambda pt: abs(pt[0] - ox))
    assert abs(mid[1] - oy) < 1.5  # sin(0) = 0


def test_pole_breaks_the_line():
    ws, p = plot_sheet(list("1/x"))
    lines, _ = sample(p.curves[0], p.plot_ctx, ws.evaluator, p.plot)
    assert len(lines) == 2


def test_several_curves_and_user_function():
    ws, p = plot_sheet(list("f(x") + ["RIGHT"], ["x", "^", "2"],
                       defs=[["f", "(", "x", "RIGHT", ":", "2", "*", "x"]])
    assert len(p.curves) == 2
    lines, err = sample(p.curves[0], p.plot_ctx, ws.evaluator, p.plot)
    assert err is None and lines


def test_matrix_of_points():
    ws, p = plot_sheet(["P"], defs=[["P", ":", "m", "a", "t", "(", "0", "RIGHT", "0", "RIGHT", "1", "RIGHT", "1"]])
    lines, err = sample(p.curves[0], p.plot_ctx, ws.evaluator, p.plot)
    assert len(lines) == 1 and len(lines[0]) == 2


def test_zoom_keeps_point_under_mouse():
    st = PlotState()
    before = st.from_px(200, 50)
    st.zoom(1.5, 200, 50)
    after = st.from_px(200, 50)
    assert abs(before[0] - after[0]) < 1e-9 and abs(before[1] - after[1]) < 1e-9
    assert st.ppu_x == pytest.approx(20.5 * 1.5)


def test_plot_round_trip():
    ws, p = plot_sheet(list("sin(x") + ["RIGHT"], ["x", "^", "2"])
    p.plot.pan_x, p.plot.ppu_y = 30, 40
    again = loads(dumps(ws))
    q = [r for r in again.regions if r.kind == "plot"][0]
    assert [r.text() for r in q.plot_rows()] == ["sin(x)", "x^(2)"]
    assert q.plot.pan_x == 30 and q.plot.ppu_y == pytest.approx(40)


@pytest.mark.skipif(not EXAMPLES.exists(), reason="SMath Studio examples not present")
def test_smath_example_plot_loads():
    ws = load_sm(EXAMPLES / "MaclaurinSeries.sm")
    plots = [r for r in ws.regions if r.kind == "plot"]
    assert len(plots) == 1
    assert [r.text() for r in plots[0].plot_rows()] == ["f(x)", "fmc(x)"]
    assert plots[0].plot.ppu_x == pytest.approx(20.5, rel=0.01)
