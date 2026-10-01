"""Phase 7 (decision 24): a measurement given a variable name feeds the
calculations live, read at the top-left of its box like an equation there;
deleting it says which names stop being defined. Driven through the real
window."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QLineEdit

from calcforge.calc.docsheet import PT_PER_PX
from calcforge.items.measure import LENGTH, MeasureItem
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
    assert v.window.set_measure_variable(measure, "L.b")
    below = type_line(v, 400, "L.b=")
    above = type_line(v, 150, "L.b+0=")
    settle(v.window)
    # 100 pt at the page's 1:1 scale is 35.28 mm, kept in the measurement's
    # own unit (m) to full precision, shown as SMath shows it
    assert shown(below) == "0.0353 m"
    assert "not defined" in shown(above), "above its top-left it is not defined yet"
    assert measure.value_text.startswith("L.b = "), "the label says what it is called"


def test_it_follows_the_measurement_live(v):
    measure = a_length(v)
    v.window.set_measure_variable(measure, "L.b")
    doubled = type_line(v, 400, "L.b*2=")
    assert shown(doubled) == "0.0706 m"
    measure.points[1] = QPointF(200, 0)                 # twice as long
    measure.refresh()
    settle(v.window)
    assert shown(doubled) == "0.1411 m"


def test_moving_it_below_an_equation_takes_the_value_away_from_it(v):
    measure = a_length(v)
    v.window.set_measure_variable(measure, "L.b")
    use = type_line(v, 400, "L.b=")
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
    v.window.set_measure_variable(measure, "L.b")
    v.window.show_panel("dock_variables", True)
    panel = v.window.variables_panel
    panel.refresh()
    (row,) = [r for r in panel.rows if r.name == "L.b"]
    assert row.source == "Measurement" and row.page == 1 and not row.error
    node = panel.tree.topLevelItem(panel.rows.index(row))
    panel.go_to(node)
    assert v.window.selected_items() == [measure]


def test_deleting_it_says_what_is_no_longer_defined(v):
    measure = a_length(v)
    v.window.set_measure_variable(measure, "L.b")
    use = type_line(v, 400, "L.b=")
    v.view.scene().clearSelection()
    measure.setSelected(True)
    v.window.delete_selection()
    settle(v.window)
    assert v.window.status_hint.text() == "L.b is no longer defined"
    assert "not defined" in shown(use)
    v.window.undo_stack.undo()
    settle(v.window)
    use = next(i for i in equations(v.window) if abs(i.pos().y() - 400) < 8)
    assert "not defined" not in shown(use)


def test_the_name_is_saved_with_it(v, tmp_path):
    from tests.test_calc_saving import reopen, save_to
    measure = a_length(v)
    v.window.set_measure_variable(measure, "L.b")
    type_line(v, 400, "L.b=")
    path = str(tmp_path / "measured.pdf")
    save_to(v.window, path)
    reopen(v.window, path)
    settle(v.window)
    (use,) = equations(v.window)
    assert "not defined" not in shown(use)
    measures = [i for i in v.window.view.scene().items() if isinstance(i, MeasureItem)]
    assert [m.variable for m in measures] == ["L.b"]


# -- it follows every way a measurement's value can change -----------------------------

def _value_mm(item):
    return float(shown(item).split()[0])


def test_dragging_an_end_point_updates_the_calculation(v):
    from calcforge.core.document import PageScale
    from tests.test_usability import drag
    v.window.current_page().scale = PageScale.from_ratio(100)
    v.window.apply_scale_change()
    measure = a_length(v, 150, 300, 250, 300)            # 100 pt at 1:100
    v.window.set_measure_variable(measure, "L.b")
    use = type_line(v, 400, "L.b=")
    before = shown(use)
    v.window.select_tool("select")
    v.view.scene().clearSelection()
    measure.setSelected(True)
    end = measure.mapToScene(measure.points[1])
    drag(v.view, end.x(), end.y(), end.x() + 100, end.y())    # twice as long
    settle(v.window)
    assert measure.points[1].x() > 190, "the end point moved"
    assert shown(use) != before
    # the calculation shows exactly what the measurement now measures (the
    # end point lands where snapping puts it, so not quite twice as long)
    assert float(shown(use).split()[0]) == pytest.approx(
        measure.value.to("m").magnitude, abs=5e-5)
    assert float(shown(use).split()[0]) > 1.9 * float(before.split()[0])


def test_changing_the_page_scale_updates_the_calculation(v):
    from calcforge.core.document import PageScale
    v.window.current_page().scale = PageScale.from_ratio(100)
    v.window.apply_scale_change()
    measure = a_length(v)
    v.window.set_measure_variable(measure, "L.b")
    use = type_line(v, 400, "L.b=")
    first = float(shown(use).split()[0])
    v.window.current_page().scale = PageScale.from_ratio(200)
    v.window.apply_scale_change()                   # what the Page setup panel calls
    settle(v.window)
    assert float(shown(use).split()[0]) == pytest.approx(first * 2, rel=1e-3)


def test_dragging_it_into_a_viewport_takes_the_viewports_scale(v):
    from PySide6.QtCore import QRectF

    from calcforge.core.document import PageScale
    from tests.test_usability import drag
    page = v.window.current_page()
    page.scale = PageScale.from_ratio(100)
    v.window.apply_scale_change()
    v.window.add_viewport(v.frame, QRectF(300, 40, 250, 200), PageScale.from_ratio(20), "A")
    measure = a_length(v, 150, 300, 250, 300)
    v.window.set_measure_variable(measure, "L.b")
    use = type_line(v, 400, "L.b=")
    at_1_100 = float(shown(use).split()[0])
    v.window.select_tool("select")
    v.view.scene().clearSelection()
    measure.setSelected(True)
    grab = measure.mapToScene(measure.points[0] + (measure.points[1] - measure.points[0]) / 5)
    drag(v.view, grab.x(), grab.y(), grab.x() + 200, grab.y() - 200)   # into the viewport
    settle(v.window)
    assert page.viewport_at(measure.pos().x() + 5, measure.pos().y())
    assert float(shown(use).split()[0]) == pytest.approx(at_1_100 / 5, rel=1e-2)


# -- SMath's names, and finding them ------------------------------------------------------------

def test_l_underscore_beam_becomes_smaths_l_dot_beam(v):
    measure = a_length(v)
    assert v.window.set_measure_variable(measure, "L_beam")
    assert measure.variable == "L.beam"
    use = type_line(v, 400, "L.beam=")
    assert shown(use) == "0.0353 m"
    assert measure.value_text.startswith("L.beam = ")
    assert measure._named_parts(measure.value_text) == ("L", "beam", " = 0.04 m")


def test_the_label_draws_the_subscript_smaller_and_lower(v):
    from PySide6.QtGui import QColor, QImage, QPainter
    measure = a_length(v)
    v.window.set_measure_variable(measure, "L.beam")

    def ink_rows(item):
        box = item.boundingRect()
        image = QImage(int(box.width() * 4) + 4, int(box.height() * 4) + 4, QImage.Format_ARGB32)
        image.fill(QColor("white"))
        painter = QPainter(image)
        painter.scale(4, 4)
        painter.translate(-box.topLeft())
        item.paint_visible(painter)
        painter.end()
        return image

    with_sub = ink_rows(measure)
    v.window.set_measure_variable(measure, "Lbeam")
    plain = ink_rows(measure)
    assert with_sub != plain, "the subscript is drawn, not the dot"


def test_right_click_on_an_area_offers_its_variable_first(v):
    from calcforge.items.measure import AREA
    frame = v.frame
    area = MeasureItem(AREA, [QPointF(0, 0), QPointF(120, 0), QPointF(120, 60), QPointF(0, 60)])
    v.view.begin_snapshot([frame])
    frame.add_markup(area, QPointF(150, 300))
    v.view.commit_snapshot("Area")
    menu = v.window.build_context_menu(area, area.sceneBoundingRect().center())
    texts = [a.text() for a in menu.actions() if a.text()]
    assert texts.index("Variable name…") < texts.index("Edit text…")
    v.window.set_measure_variable(area, "A.slab")
    menu = v.window.build_context_menu(area, area.sceneBoundingRect().center())
    texts = [a.text() for a in menu.actions() if a.text()]
    assert "Variable: A.slab…" in texts and "Show in Variables" in texts
    next(a for a in menu.actions() if a.text() == "Show in Variables").trigger()
    panel = v.window.variables_panel
    assert v.window.dock_variables.isVisible()
    assert panel.row_of(panel.tree.currentItem()).name == "A.slab"
