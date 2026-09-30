"""2-D plot regions."""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.calc.smfile import dumps, load_sm, loads
from calcforge.calc.plot import PlotState, axis_layout, sample
from calcforge.calc.worksheet import Worksheet

EXAMPLES = Path(__file__).resolve().parents[2] / "SMath Studio" / "examples"


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


def test_styled_points_matrix_as_smath():
    """SMath's styled points: rows of (x, y, "marker or text", size px, "colour")."""
    from calcforge.calc.engine.values import Matrix, Q, String
    from calcforge.calc.plot import PlotState, marks

    st = PlotState()
    m = Matrix(2, 5, [Q(1.0), Q(2.0), String("o"), Q(8.0), String("Red"),
                      Q(-1.0), Q(0.0), String("F1"), Q(10.0), String("Green")])
    got = marks(m, st)
    assert [(t, s, c) for _x, _y, t, s, c in got] == [("o", 8.0, "Red"), ("F1", 10.0, "Green")]
    assert got[0][:2] == st.to_px(1.0, 2.0)
    assert marks(Matrix(1, 2, [Q(1.0), Q(2.0)]), st) == []  # plain points are lines, not marks


def test_fit_ranges():
    from calcforge.calc.plot import PlotState, fit_ranges

    st = PlotState()
    fit_ranges(st, -2.0, 8.0, -1.0, 4.0)
    assert st.x_range() == pytest.approx((-2.0, 8.0)) and st.y_range() == pytest.approx((-1.0, 4.0))
    with pytest.raises(ValueError):
        fit_ranges(st, 1.0, 1.0, 0.0, 1.0)


def test_sys_of_point_sets_is_split_into_parts():
    """Beam.sm plots sys(points, points, ..., styled marks): each part is drawn."""
    from calcforge.calc.engine.values import Matrix, Q, String
    from calcforge.calc.plot import PlotState, marks, parts, point_lines

    st = PlotState()
    a = Matrix(2, 2, [Q(0.0), Q(0.0), Q(1.0), Q(1.0)])
    m = Matrix(1, 5, [Q(1.0), Q(2.0), String("A"), Q(10.0), String("Red")])
    both = Matrix(2, 1, [a, m])
    got = parts(both)
    assert got == [a, m]
    assert point_lines(got[0], st) == [[st.to_px(0.0, 0.0), st.to_px(1.0, 1.0)]]
    assert point_lines(got[1], st) is None and len(marks(got[1], st)) == 1
    assert parts(a) == [a]
