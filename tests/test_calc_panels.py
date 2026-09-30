"""Phase 5: the Calculation toolbar and the Maths panel (decisions 18, 19),
driven by clicking their buttons in the real window."""
from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from calcforge.calc.engine.display import display_text
from calcforge.items.calc import CalcItem, CalcTextItem
from calcforge.ui import calcdialogs
from tests.test_calc_modes import at, into_calc_mode, typed
from tests.test_usability import click, press_key


@pytest.fixture
def win(window):
    window.show()
    window.activateWindow()
    window.view.setFocus()
    yield window
    calcdialogs.ANSWERS.clear()


def toolbar_button(window, text):
    action = next(a for a in window.calculation_bar.actions() if a.text() == text)
    return window.calculation_bar.widgetForAction(action)


def equations(window):
    return [i for i in window.view.scene().items() if isinstance(i, CalcItem)]


def src(item):
    return item.text().replace("≔", ":")


# -- the toolbar -----------------------------------------------------------------------

def test_the_calculation_toolbar_has_smaths_commands(win):
    names = [a.text() for a in win.calculation_bar.actions() if a.text()]
    assert names == ["Calculate", "Auto-calc", "Plot", "Matrix", "Calc text", "Block",
                     "If", "For", "While", "Line"]
    for action in win.calculation_bar.actions():
        if action.text():
            assert action.toolTip(), f"{action.text()} explains itself"
            assert not action.icon().isNull()


def test_plot_on_the_toolbar_puts_a_plot_at_the_red_cross(win):
    into_calc_mode(win, 120, 200)
    QTest.mouseClick(toolbar_button(win, "Plot"), Qt.LeftButton)
    (plot,) = equations(win)
    assert plot.region.plot is not None
    assert abs(plot.pos().x() - 120) < 7 and abs(plot.pos().y() - 200) < 7


def test_calc_text_on_the_toolbar(win):
    into_calc_mode(win, 100, 300)
    QTest.mouseClick(toolbar_button(win, "Calc text"), Qt.LeftButton)
    typed(win, "Beam B1")
    press_key(win.view, Qt.Key_Escape)
    (made,) = [i for i in win.view.scene().items() if isinstance(i, CalcTextItem)]
    assert "Beam B1" in made.text()


def test_matrix_and_calculate_on_the_toolbar(win):
    into_calc_mode(win)
    calcdialogs.ANSWERS["Insert matrix"] = (2, 1)
    QTest.mouseClick(toolbar_button(win, "Matrix"), Qt.LeftButton)
    assert "mat(" in win.view.calc.item.text()
    press_key(win.view, Qt.Key_Escape)
    QTest.mouseClick(toolbar_button(win, "Calculate"), Qt.LeftButton)
    assert win.status_hint.text() == "Calculated"


def test_auto_calc_off_waits_for_calculate(win):
    into_calc_mode(win)
    typed(win, "w3:2")
    press_key(win.view, Qt.Key_Return)
    typed(win, "w3*3=")
    press_key(win.view, Qt.Key_Return)
    press_key(win.view, Qt.Key_Escape)
    toolbar_button(win, "Auto-calc").click()
    assert not win.act_auto_calc.isChecked()
    (first,) = [i for i in equations(win) if src(i) == "w3:2"]
    win.view.calc.focus(first, first.sceneBoundingRect().center())
    press_key(win.view, Qt.Key_End)
    typed(win, "0")
    press_key(win.view, Qt.Key_Escape)
    (result,) = [i for i in equations(win) if src(i) == "w3*3="]
    assert display_text(result.region.display) == "6", "not yet: auto-calc is off"
    QTest.mouseClick(toolbar_button(win, "Calculate"), Qt.LeftButton)
    assert display_text(result.region.display) == "60"


@pytest.mark.parametrize("name, kind", [("If", "if"), ("For", "for"), ("While", "while")])
def test_program_blocks_on_the_toolbar(win, name, kind):
    into_calc_mode(win)
    typed(win, "r4:")
    QTest.mouseClick(toolbar_button(win, name), Qt.LeftButton)
    assert kind in win.view.calc.item.text()


def test_line_adds_a_line_to_a_program(win):
    into_calc_mode(win)
    typed(win, "r5:")
    QTest.mouseClick(toolbar_button(win, "If"), Qt.LeftButton)
    before = win.view.calc.item.text()
    QTest.mouseClick(toolbar_button(win, "Line"), Qt.LeftButton)
    assert win.view.calc.item.text() != before


# -- the Maths panel -------------------------------------------------------------------

def test_the_maths_panel_is_on_the_rail_with_smaths_sections(win):
    assert "dock_maths" in win.right_rail.order()
    win.show_panel("dock_maths", True)
    assert win.dock_maths.isVisible()
    assert [s.title for s in win.maths_panel.sections] == [
        "Arithmetic", "Matrices", "Boolean", "Functions", "Plot", "Programming",
        "Units", "Constants"]


def test_maths_buttons_type_into_the_equation(win):
    win.show_panel("dock_maths", True)
    into_calc_mode(win)
    typed(win, "2")
    panel = win.maths_panel
    arithmetic = panel.section("Arithmetic")
    for label in ("×", "π", "="):
        QTest.mouseClick(arithmetic.button(label), Qt.LeftButton)
    item = win.view.calc.item
    assert item.text() == "2*π="
    press_key(win.view, Qt.Key_Return)
    assert display_text(item.region.display) == "6.2832"


def test_a_maths_button_starts_an_equation_at_the_red_cross(win):
    win.show_panel("dock_maths", True)
    into_calc_mode(win, 150, 260)
    QTest.mouseClick(win.maths_panel.section("Functions").button("sin"), Qt.LeftButton)
    item = win.view.calc.item
    assert item is not None and item.text().startswith("sin(")
    assert abs(item.pos().x() - 150) < 7


def test_units_and_constants_from_the_panel(win):
    win.show_panel("dock_maths", True)
    into_calc_mode(win)
    typed(win, "L6:3")
    units = win.maths_panel.section("Units")
    units.set_collapsed(False)
    QTest.mouseClick(units.button("kN"), Qt.LeftButton)
    press_key(win.view, Qt.Key_Return)
    typed(win, "L6=")
    press_key(win.view, Qt.Key_Return)
    (shown,) = [i for i in equations(win) if src(i) == "L6="]
    assert display_text(shown.region.display) == "3 kN"
    calcdialogs.ANSWERS["Insert unit"] = "MPa"
    typed(win, "s6:4")
    win.insert_unit()
    assert win.view.calc.item.text().endswith("MPa")


def test_panel_sections_fold_away(win):
    win.show_panel("dock_maths", True)
    section = win.maths_panel.section("Boolean")
    assert section.collapsed and not section.body.isVisible()
    QTest.mouseClick(section.header, Qt.LeftButton)
    assert not section.collapsed and section.body.isVisible()


# -- an equation's settings: the right-click menu (decision 20) -------------------------

def menu_action(menu, *path):
    """The action at *path* in a menu (titles, a trailing ' *' ignored)."""
    for title in path[:-1]:
        menu = next(a.menu() for a in menu.actions()
                    if a.menu() is not None and a.text() == title)
    return next(a for a in menu.actions() if a.text().rstrip(" *") == path[-1])


def right_click(window, item):
    from PySide6.QtCore import QPointF
    window.view.calc.leave()
    window.view.scene().clearSelection()
    item.setSelected(True)
    return window.build_context_menu(item, item.sceneBoundingRect().center())


def an_equation(window, text, x=100, y=120):
    into_calc_mode(window, x, y)
    typed(window, text)
    item = window.view.calc.item
    press_key(window.view, Qt.Key_Return)
    press_key(window.view, Qt.Key_Escape)
    return item


def test_decimal_places_from_the_right_click_menu_and_undo(win):
    item = an_equation(win, "2/3=")
    assert display_text(item.region.display) == "0.6667"
    menu_action(right_click(win, item), "Equation", "Decimal places", "2").trigger()
    assert display_text(item.region.display) == "0.67"
    win.undo_something()
    (again,) = equations(win)
    assert display_text(again.region.display) == "0.6667"


def test_fractions_and_trailing_zeros(win):
    item = an_equation(win, "1/4=")
    menu_action(right_click(win, item), "Equation", "Fractions", "Fraction").trigger()
    assert display_text(item.region.display) == "1/4"
    menu_action(right_click(win, item), "Equation", "Fractions", "Default").trigger()
    menu_action(right_click(win, item), "Equation", "Decimal places", "Trailing zeros").trigger()
    assert display_text(item.region.display) == "0.2500"


def test_disable_evaluation_undefines_what_it_defined(win):
    first = an_equation(win, "p7:5", y=120)
    used = an_equation(win, "p7*2=", y=160)
    assert display_text(used.region.display) == "10"
    menu_action(right_click(win, first), "Equation", "Disable evaluation").trigger()
    assert not first.region.enabled
    assert used.region.error is not None, "p7 is no longer defined"
    menu_action(right_click(win, first), "Equation", "Disable evaluation").trigger()
    assert display_text(used.region.display) == "10"


def test_a_setting_applies_to_every_selected_equation(win):
    a = an_equation(win, "1/3=", y=120)
    b = an_equation(win, "2/7=", y=160)
    win.view.scene().clearSelection()
    a.setSelected(True)
    b.setSelected(True)
    menu = win.build_context_menu(a, a.sceneBoundingRect().center())
    menu_action(menu, "Equation", "Decimal places", "1").trigger()
    assert display_text(a.region.display) == "0.3"
    assert display_text(b.region.display) == "0.3"


def test_font_colour_and_they_survive_saving(win, tmp_path):
    from calcforge.ui import calcmenu
    from tests.test_calc_saving import reopen, save_to
    item = an_equation(win, "f8:12")
    menu_action(right_click(win, item), "Equation", "Font", "14 pt").trigger()
    menu_action(right_click(win, item), "Equation", "Font", "Bold").trigger()
    calcmenu.ANSWERS["Colour"] = "#2b8a3e"
    try:
        menu_action(right_click(win, item), "Equation", "Colour…").trigger()
    finally:
        calcmenu.ANSWERS.clear()
    assert item.region.font_size == 14 and item.region.bold and item.region.color == "#2b8a3e"
    path = str(tmp_path / "styled.pdf")
    save_to(win, path)
    reopen(win, path)
    (back,) = [i for i in equations(win) if src(i) == "f8:12"]
    assert back.region.font_size == 14 and back.region.bold
    assert back.region.color == "#2b8a3e"


def test_go_to_definition(win):
    first = an_equation(win, "q9:3", y=120)
    used = an_equation(win, "q9+1=", y=200)
    menu_action(right_click(win, used), "Equation", "Go to definition").trigger()
    assert win.view.calc.item is first


def test_plot_settings_from_the_menu(win):
    from calcforge.ui import calcmenu
    into_calc_mode(win, 100, 150)
    QTest.mouseClick(toolbar_button(win, "Plot"), Qt.LeftButton)
    typed(win, "x")
    press_key(win.view, Qt.Key_Escape)
    (plot,) = equations(win)
    menu_action(right_click(win, plot), "Grid").trigger()
    assert plot.region.plot.grid is False
    calcmenu.ANSWERS["Plot settings"] = ([-2, 2, -1, 1], True, True, True)
    try:
        menu_action(right_click(win, plot), "Plot settings…").trigger()
    finally:
        calcmenu.ANSWERS.clear()
    assert plot.region.plot.points and plot.region.plot.x_range() == pytest.approx((-2, 2))


# -- and in the Properties panel ----------------------------------------------------------

def test_equation_settings_in_the_properties_panel(win):
    from PySide6.QtWidgets import QDoubleSpinBox, QSpinBox
    item = an_equation(win, "5/7=")
    win.view.scene().clearSelection()
    item.setSelected(True)
    win.refresh_selection()
    panel = win.properties_panel
    decimals = panel.findChild(QSpinBox, "equationDecimals")
    assert decimals is not None and decimals.value() == 4
    decimals.setValue(2)
    assert display_text(item.region.display) == "0.71"
    size = panel.findChild(QDoubleSpinBox, "equationFontSize")
    size.setValue(16)
    assert item.region.font_size == 16
    win.undo_something()
    (back,) = equations(win)
    assert back.region.font_size == 10 and display_text(back.region.display) == "0.71"


# -- defaults in Preferences ---------------------------------------------------------------

@pytest.fixture
def prefs():
    from calcforge.ui import preferences
    kept = preferences.current()
    yield preferences
    preferences.apply(kept)


def test_result_defaults_in_preferences_change_this_document(win, prefs):
    import dataclasses
    item = an_equation(win, "1/3=")
    assert display_text(item.region.display) == "0.3333"
    before = prefs.current().result_format()
    win.apply_preferences(dataclasses.replace(prefs.current(), result_decimals=2,
                                              result_trailing_zeros=True), before)
    assert display_text(item.region.display) == "0.33"
    assert win.document.settings.calc_format["decimals"] == 2
    one = an_equation(win, "1/2=", y=200)
    assert display_text(one.region.display) == "0.50", "trailing zeros, two places"


def test_new_equations_take_the_preferred_size_and_colour(win, prefs):
    import dataclasses
    prefs.apply(dataclasses.replace(prefs.current(), equation_font_size=14.0,
                                    equation_colour="#1864ab"))
    item = an_equation(win, "z1:1")
    assert item.region.font_size == 14.0 and item.region.color == "#1864ab"


def test_a_documents_result_format_travels_with_it(win, prefs, tmp_path):
    import dataclasses
    from tests.test_calc_saving import reopen, save_to
    before = prefs.current().result_format()
    win.apply_preferences(dataclasses.replace(prefs.current(), result_decimals=1), before)
    an_equation(win, "2/3=")
    path = str(tmp_path / "fmt.pdf")
    save_to(win, path)
    # somebody else's machine: four decimals by preference
    prefs.apply(dataclasses.replace(prefs.current(), result_decimals=4))
    reopen(win, path)
    (item,) = equations(win)
    assert display_text(item.region.display) == "0.7", "the document says one place"
    win.new_document(confirm=False)
    win.rebuild_scenes()
    assert win.document.settings.calc_format["decimals"] == 4, "a new one takes Preferences'"


def test_the_preferences_dialog_has_the_calculation_defaults(win, prefs):
    from PySide6.QtWidgets import QSpinBox
    from calcforge.ui import dialogs
    dialog = dialogs.PreferencesDialog(prefs.current(), win)
    spin = dialog.findChild(QSpinBox, "resultDecimals")
    spin.setValue(3)
    chosen = dialog.result_preferences()
    assert chosen.result_decimals == 3 and chosen.result_format()["decimals"] == 3


# -- a plot's mouse: SMath's once double-clicked into ------------------------------------

def wheel_at(window, scene_point, notches=1, modifiers=Qt.NoModifier):
    from PySide6.QtCore import QPoint, QPointF
    from PySide6.QtGui import QWheelEvent
    at = QPointF(window.view.mapFromScene(scene_point))
    event = QWheelEvent(at, QPointF(window.view.viewport().mapToGlobal(at.toPoint())),
                        QPoint(0, 0), QPoint(0, 120 * notches), Qt.NoButton, modifiers,
                        Qt.NoScrollPhase, False)
    window.view.wheelEvent(event)


def a_plot(window):
    into_calc_mode(window, 100, 150)
    QTest.mouseClick(toolbar_button(window, "Plot"), Qt.LeftButton)
    typed(window, "sin(x)")
    (plot,) = equations(window)
    return plot


def inside(plot, fx=0.5, fy=0.5):
    """A scene point inside the plot's graph."""
    from calcforge.calc.docsheet import PT_PER_PX
    rect = plot._view.plot_rect()
    x = (rect.left() + rect.width() * fx) * PT_PER_PX
    y = (rect.top() + rect.height() * fy) * PT_PER_PX
    from PySide6.QtCore import QPointF
    return plot.mapToScene(QPointF(x, y))


def test_a_plot_just_made_is_entered_drag_pans_and_the_wheel_zooms(win):
    from tests.test_usability import drag
    plot = a_plot(win)
    state = plot.region.plot
    assert win.view.calc.item is plot
    pan, ppu, where = (state.pan_x, state.pan_y), (state.ppu_x, state.ppu_y), plot.pos()
    a, b = inside(plot, 0.4, 0.4), inside(plot, 0.6, 0.6)
    drag(win.view, a.x(), a.y(), b.x(), b.y())
    assert (state.pan_x, state.pan_y) != pan, "dragging inside pans the graph"
    assert plot.pos() == where, "and does not move the plot"
    wheel_at(win, inside(plot), 2)
    assert state.ppu_x > ppu[0] and state.ppu_y > ppu[1], "the wheel zooms"
    x_before, y_before = state.ppu_x, state.ppu_y
    wheel_at(win, inside(plot), 1, Qt.ControlModifier)
    assert state.ppu_x > x_before and state.ppu_y == y_before, "Ctrl: x only"
    wheel_at(win, inside(plot), 1, Qt.ShiftModifier)
    assert state.ppu_y > y_before, "Shift: y only"


def test_the_scale_tool_zooms_by_dragging(win):
    from tests.test_usability import drag
    plot = a_plot(win)
    win.show_panel("dock_maths", True)
    plot_section = win.maths_panel.section("Plot")
    plot_section.set_collapsed(False)
    QTest.mouseClick(plot_section.button("⤢"), Qt.LeftButton)
    state = plot.region.plot
    ppu = state.ppu_x
    a, b = inside(plot, 0.3, 0.7), inside(plot, 0.7, 0.3)
    drag(win.view, a.x(), a.y(), b.x(), b.y())
    assert state.ppu_x > ppu, "up and right zooms in"
    win.plot_tool("move")


def test_until_double_clicked_a_plot_is_a_markup(win):
    from tests.test_usability import click, double_click, drag
    plot = a_plot(win)
    press_key(win.view, Qt.Key_Escape)
    assert win.view.calc.item is None
    state = plot.region.plot
    ppu, where = state.ppu_x, plot.pos()
    wheel_at(win, inside(plot), 2)
    assert state.ppu_x == ppu, "the wheel is the page's, not the plot's"
    p = inside(plot)
    click(win.view, p.x(), p.y())
    assert win.view.calc.item is None and plot.isSelected(), "one click picks it up"
    drag(win.view, p.x(), p.y(), p.x() + 60, p.y() + 40)
    assert plot.pos() != where, "and dragging moves it"
    q = inside(plot)
    double_click(win.view, q.x(), q.y())
    assert win.view.calc.item is plot, "double-clicked into"
    wheel_at(win, inside(plot), 1)
    assert state.ppu_x > ppu


def test_the_plot_corner_resizes_it(win):
    from tests.test_usability import drag
    plot = a_plot(win)
    state = plot.region.plot
    width = state.width
    corner = inside(plot, 0.995, 0.995)
    drag(win.view, corner.x(), corner.y(), corner.x() + 40, corner.y() + 30)
    assert state.width > width


# -- Search finds variable names and equation text ------------------------------------

def test_search_finds_equations_by_what_was_typed_and_what_they_show(win):
    an_equation(win, "Mu:45.2'kN*'m", y=120)
    an_equation(win, "Mu=", y=160)
    panel = win.search_panel
    win.find_in_document("Mu:")
    hits = [h for h in panel.hits if h.get("field") == "equation"]
    assert len(hits) == 1, "the definition, as it is typed"
    win.find_in_document("Mu")
    assert len([h for h in panel.hits if h.get("field") == "equation"]) == 2
    win.find_in_document("45.2")
    assert any(h.get("field") == "result" for h in panel.hits), "the shown result too"
    assert "in equations" in panel.summary.text()
    # an equation is not changed by Replace
    panel.replacement.setText("XX")
    assert panel.replace_all() == 0


def test_calculation_text_is_spell_checked(win):
    into_calc_mode(win)
    QTest.mouseClick(toolbar_button(win, "Calc text"), Qt.LeftButton)
    typed(win, "The beem is fine")
    press_key(win.view, Qt.Key_Escape)
    from calcforge.core.spelling import shared
    if not shared().ready():
        pytest.skip("no dictionary here")
    words = [w for _item, _s, _l, w in win.spelling_mistakes()]
    assert words == ["beem"]


def test_calculation_text_lands_on_the_grid_when_moved(win):
    from tests.test_usability import drag
    from calcforge.ui.calcedit import GRID_PT
    into_calc_mode(win)
    QTest.mouseClick(toolbar_button(win, "Calc text"), Qt.LeftButton)
    typed(win, "Note")
    press_key(win.view, Qt.Key_Escape)
    (text,) = [i for i in win.view.scene().items() if isinstance(i, CalcTextItem)]
    win.toggle_calc_mode(False)
    edge = text.sceneBoundingRect()
    start = edge.center()
    drag(win.view, start.x(), start.y(), start.x() + 23.3, start.y() + 17.1)
    x, y = text.pos().x(), text.pos().y()
    assert abs(x / GRID_PT - round(x / GRID_PT)) < 1e-6
    assert abs(y / GRID_PT - round(y / GRID_PT)) < 1e-6


# -- copying equations out: a picture plus plain text (decision 26) ------------------------

def test_copied_equations_are_text_and_a_picture_outside_and_live_inside(win):
    from PySide6.QtWidgets import QApplication
    span = an_equation(win, "sp:6'm", y=120)
    load = an_equation(win, "wl:9'kN/'m", y=160)
    moment = an_equation(win, "Mu:wl*sp*sp/8", y=200)
    shown = an_equation(win, "Mu=", y=240)
    assert display_text(shown.region.display) == "40.5 kN m"
    win.view.scene().clearSelection()
    for item in (span, moment, shown):
        item.setSelected(True)
    win.copy_selection()
    mime = QApplication.clipboard().mimeData()
    text = mime.text()
    assert "sp := 6 m" in text
    assert "Mu = 40.5 kN·m" in text, text
    assert mime.hasImage() and not QApplication.clipboard().image().isNull()
    assert not text.lstrip().startswith("{"), "not CalcForge's own data as text"
    # pasted here (from the clipboard, as another window would): live equations
    win._clipboard = []
    before = len(equations(win))
    win.paste_items()
    assert len(equations(win)) == before + 3
    pasted = [i for i in equations(win) if i.isSelected()]
    assert len(pasted) == 3 and all(i.region is not None for i in pasted), "live"


def test_plain_text_of_equations():
    from calcforge.calc.record import plain_units
    assert plain_units("54 kN m") == "54 kN·m"
    assert plain_units("12.25 m^2") == "12.25 m²"
    assert plain_units("9.81 m s^-2") == "9.81 m·s⁻²"
