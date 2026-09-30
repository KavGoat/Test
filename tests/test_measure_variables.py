"""Phase 7 (decision 24): a measurement given a variable name feeds the
calculations live, read at the top-left of its box like an equation there;
deleting it says which names stop being defined. Driven through the real
window."""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QLineEdit

from markforge.calc.docsheet import PT_PER_PX
from markforge.items.measure import LENGTH, MeasureItem
from tests.test_calc_blocks import equations, settle, shown, v  # noqa: F401


def a_length(v, x0=150, y0=300, x1=250, y1=300):
    """A length measurement drawn across the page (points are page points)."""
    frame = v.frame
    item = MeasureItem(LENGTH, [QPointF(0, 0), QPointF(x1 - x0, y1 - y0)])
    v.view.begin_snapshot([frame])
    frame.add_markup(item, QPointF(x0, y0))
    v.view.commit_snapshot("Measure")
    return item


def type_line(v, y_pt, keys, x_pt=36):
    v.type_at(x_pt / PT_PER_PX, y_pt / PT_PER_PX, "")
    v.keys(keys)
    v.press(Qt.Key_Return)
    v.calc.leave()
    return next(i for i in equations(v.window) if abs(i.pos().y() - y_pt) < 8)


def test_a_named_measurement_is_a_variable_below_it(v):
    measure = a_length(v)
    assert v.window.set_measure_variable(measure, "L_b")
    below = type_line(v, 400, "L_b=")
    above = type_line(v, 150, "L_b+0=")
    settle(v.window)
    # 100 pt at the page's 1:1 scale is 35.28 mm, kept in the measurement's
    # own unit (m) to full precision, shown as SMath shows it
    assert shown(below) == "0.0353 m"
    assert "not defined" in shown(above), "above its top-left it is not defined yet"
    assert measure.value_text.startswith("L_b = "), "the label says what it is called"


def test_it_follows_the_measurement_live(v):
    measure = a_length(v)
    v.window.set_measure_variable(measure, "L_b")
    doubled = type_line(v, 400, "L_b*2=")
    assert shown(doubled) == "0.0706 m"
    measure.points[1] = QPointF(200, 0)                 # twice as long
    measure.refresh()
    settle(v.window)
    assert shown(doubled) == "0.1411 m"


def test_moving_it_below_an_equation_takes_the_value_away_from_it(v):
    measure = a_length(v)
    v.window.set_measure_variable(measure, "L_b")
    use = type_line(v, 400, "L_b=")
    assert "not defined" not in shown(use)
    measure.setPos(QPointF(150, 600))
    settle(v.window)
    assert "not defined" in shown(use)


def test_the_properties_panel_names_it(v):
    measure = a_length(v)
    v.view.scene().clearSelection()
    measure.setSelected(True)
    v.window.refresh_selection()
    field = v.window.properties_panel.findChild(QLineEdit, "measureVariable")
    assert field is not None
    field.setText("span")
    field.editingFinished.emit()
    assert measure.variable == "span"
    use = type_line(v, 400, "span=")
    assert "not defined" not in shown(use)
    v.window.set_measure_variable(measure, "2bad")
    assert measure.variable == "span", "not a name SMath takes"
    assert "not a variable name" in v.window.status_hint.text()


def test_it_is_in_the_variables_panel(v):
    measure = a_length(v)
    v.window.set_measure_variable(measure, "L_b")
    v.window.show_panel("dock_variables", True)
    panel = v.window.variables_panel
    panel.refresh()
    (row,) = [r for r in panel.rows if r.name == "L_b"]
    assert row.source == "Measurement" and row.page == 1 and not row.error
    node = panel.tree.topLevelItem(panel.rows.index(row))
    panel.go_to(node)
    assert v.window.selected_items() == [measure]


def test_deleting_it_says_what_is_no_longer_defined(v):
    measure = a_length(v)
    v.window.set_measure_variable(measure, "L_b")
    use = type_line(v, 400, "L_b=")
    v.view.scene().clearSelection()
    measure.setSelected(True)
    v.window.delete_selection()
    settle(v.window)
    assert v.window.status_hint.text() == "L_b is no longer defined"
    assert "not defined" in shown(use)
    v.window.undo_stack.undo()
    settle(v.window)
    use = next(i for i in equations(v.window) if abs(i.pos().y() - 400) < 8)
    assert "not defined" not in shown(use)


def test_the_name_is_saved_with_it(v, tmp_path):
    from tests.test_calc_saving import reopen, save_to
    measure = a_length(v)
    v.window.set_measure_variable(measure, "L_b")
    type_line(v, 400, "L_b=")
    path = str(tmp_path / "measured.pdf")
    save_to(v.window, path)
    reopen(v.window, path)
    settle(v.window)
    (use,) = equations(v.window)
    assert "not defined" not in shown(use)
    measures = [i for i in v.window.view.scene().items() if isinstance(i, MeasureItem)]
    assert [m.variable for m in measures] == ["L_b"]
