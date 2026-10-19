"""The same thing offered the same way everywhere (the user, 2026-10-19:
"the Properties panel doesn't show for a table in Calc mode or for
equations; cells don't have the decimal thing like equations in the
right-click menu. Look for other inconsistencies like that").

Driven as a person does: clicks on the page, keys, the real right-click
menus' builders, typing into the panel's boxes. The audit behind these is
docs/qa/consistency_2026-10-19.md.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (QAbstractSpinBox, QCheckBox, QLabel, QLineEdit, QPushButton,
                               QSpinBox)

from calcforge.calc.engine.display import display_text
from calcforge.items.calc import CalcBlockItem, CalcItem, CalcTextItem
from calcforge.sheet.numfmt import format_value, places_of, with_places
from calcforge.sheet.refs import parse_cell
from calcforge.ui import calcdialogs
from calcforge.ui.panels import PropertySection
from tests.test_calc_modes import into_calc_mode, keys, typed
from tests.test_calc_panels import an_equation
from tests.test_tables import cell_scene, click as cell_click, enter, make_table, pump, type_text
from tests.test_usability import click, markups, press_key


@pytest.fixture
def win(window):
    window.show()
    window.activateWindow()
    window.view.set_zoom(1.0)
    window.show_panel("dock_properties", True)
    window.view.setFocus()
    yield window
    calcdialogs.ANSWERS.clear()


# -- helpers ----------------------------------------------------------------------------

def panel(window):
    """(heading, section titles) the Properties panel shows."""
    pump()
    pump()
    body = window.properties_panel.body
    heads = [label.text() for label in body.findChildren(QLabel)
             if label.objectName() == "propHeading"]
    sections = [s.title() for s in body.findChildren(PropertySection)
                if s.parent() is body]
    return (heads[0] if heads else ""), sections


def child(window, kind, name):
    found = window.properties_panel.body.findChild(kind, name)
    assert found is not None, f"no {name} in the Properties panel"
    return found


def centre(item):
    return item.mapToScene(item.local_rect().center())


def click_on(window, item):
    point = centre(item)
    window.view.centerOn(point)
    pump()
    click(window.view, point.x(), point.y())
    pump()


def put_down(window):
    """Leave whatever is being typed in or opened, and pick nothing."""
    window.view.calc.leave()
    if window.view.editing_item() is not None:
        window.view.end_item_edit()
    window.view.tables.close()
    window.view.scene().clearSelection()
    pump()


def type_into(widget, text):
    """Select what a panel box holds and type over it, then Enter."""
    widget.setFocus()
    target = widget.lineEdit() if isinstance(widget, QAbstractSpinBox) else widget
    target.selectAll()
    QTest.keyClicks(target, text)
    QTest.keyClick(target, Qt.Key_Return)
    pump()


def tick(box):
    QTest.mouseClick(box, Qt.LeftButton, pos=box.rect().center()
                     if not isinstance(box, QCheckBox) else QPointF(8, box.height() / 2).toPoint())
    pump()


def shown(table, a1):
    """What a cell shows, as it is drawn (its significant figures too)."""
    r = parse_cell(a1)
    st = table.sheet.workbook.style_of(table.sheet, r.row, r.col)
    return format_value(table.sheet.value(r.row, r.col), st.number_format, st.unit,
                        significant=st.significant).text


def the_table(window):
    from calcforge.items.table import TableItem
    (table,) = [i for i in window.view.scene().items()
                if isinstance(i, TableItem) and not getattr(i, "SHEET_RUN", False)]
    return table


def menu_action(menu, *path):
    for title in path[:-1]:
        menu = next(a.menu() for a in menu.actions()
                    if a.menu() is not None and a.text() == title)
    return next(a for a in menu.actions() if a.text().rstrip(" *") == path[-1])


def steps(window):
    return window.undo_stack.index()


# -- 1. the Properties panel shows for each kind, in both modes ----------------------------

@pytest.mark.parametrize("calc_mode", [False, True])
def test_an_equation_clicked_shows_its_properties(win, calc_mode):
    item = an_equation(win, "d1:=2/3")
    put_down(win)
    win.toggle_calc_mode(calc_mode)
    click_on(win, item)
    assert win.view.calc.item is item, "a click opens it for typing"
    heading, sections = panel(win)
    assert heading == "Equation Properties"
    assert sections == ["General", "Result", "Equation", "Layout", "Options"]
    # the Properties toolbar names it too, as it does a picked one
    assert win.style_kind_label.text() == "Equation"
    press_key(win.view, Qt.Key_Escape)
    pump()
    assert panel(win)[0] == "", "left, the panel lets it go"


@pytest.mark.parametrize("calc_mode", [False, True])
def test_calculation_text_and_a_block_show_theirs(win, calc_mode):
    into_calc_mode(win, 100, 300)
    typed(win, '"some words')
    press_key(win.view, Qt.Key_Escape)
    put_down(win)
    (text,) = [i for i in win.view.scene().items() if isinstance(i, CalcTextItem)]
    win.view.calc.place_cross(win.document.pages[0].frame, QPointF(300, 600))
    win.insert_block()
    (block,) = [i for i in win.view.scene().items() if isinstance(i, CalcBlockItem)]
    put_down(win)
    win.toggle_calc_mode(calc_mode)
    click_on(win, text)
    heading, sections = panel(win)
    assert heading == "Calculation text Properties"
    assert sections == ["General", "Appearance", "Layout", "Options"]
    put_down(win)
    click_on(win, block)
    heading, sections = panel(win)
    assert heading == "Calculation block Properties"
    assert sections == ["General", "Calculation block", "Appearance", "Layout", "Options"]


@pytest.mark.parametrize("calc_mode", [False, True])
def test_a_table_shows_its_properties_and_its_cells(win, calc_mode):
    table = make_table(win)
    put_down(win)
    win.toggle_calc_mode(calc_mode)
    cell_click(win, cell_scene(table, "B2"))
    if not calc_mode:
        # Markup mode: a click picks the table; a double-click opens its cells
        assert panel(win) == ("Table1 Properties", ["General", "Table", "Layout", "Options"])
        cell_click(win, cell_scene(table, "B2"), double=True)
    assert win.view.tables.item is table
    heading, sections = panel(win)
    assert heading == "Table1 Properties"
    assert sections == ["General", "Table", "Cells", "Layout", "Options"]


def test_a_spreadsheet_page_shows_its_sheet_and_cells_but_no_layout(win):
    from tests.test_sheet_pages import open_at, sheet_page
    run = sheet_page(win)
    open_at(win, run, "B2")
    heading, sections = panel(win)
    assert heading == "Sheet1 Properties"
    assert sections == ["General", "Sheet", "Cells"]
    assert child(win, QLabel, "cellsSelection").text() == "B2"


@pytest.mark.parametrize("calc_mode", [False, True])
def test_markups_a_chart_and_a_picture_show_theirs_in_both_modes(win, calc_mode):
    from tests.test_charts import chart_of
    from tests.test_crop_image import _image
    from tests.test_every_command_is_bindable import _draw
    _draw(win, "rect", 60, 400, 140, 440)
    (rect,) = markups(win)
    table = make_table(win, x=300, y=100)
    win.view.tables.open(table, (0, 0))
    for text in ("1", "2", "3"):
        type_text(win, text)
        enter(win)
    chart = chart_of(win, table, block=(0, 0, 2, 0))
    picture = _image(win)
    put_down(win)
    win.toggle_calc_mode(calc_mode)
    for item, heading, wanted in (
            (rect, "Rectangle Properties", ["General", "Appearance", "Size", "Layout", "Options"]),
            (chart, "Chart Properties", ["General", "Chart", "Layout", "Options"]),
            (picture, "Image Properties", ["General", "Appearance", "Image", "Layout",
                                           "Options"])):
        put_down(win)
        click_on(win, item)
        assert panel(win) == (heading, wanted)


# -- 2. the cells' right-click: Decimal Places and Significant Figures, as an equation's ---

def a_number_in_b2(win, text="12.34567"):
    table = make_table(win)
    cell_click(win, cell_scene(table, "B2"))
    if win.view.tables.item is not table:
        cell_click(win, cell_scene(table, "B2"), double=True)
        press_key(win.view, Qt.Key_Escape)
    type_text(win, text)
    enter(win)
    cell_click(win, cell_scene(table, "B2"))
    assert win.view.tables.active == (1, 1)
    return table


def test_the_cells_menu_starts_as_an_equations_does(win):
    a_number_in_b2(win)
    menu = win.view.tables.cell_menu()
    top = [a.text() for a in menu.actions() if not a.isSeparator()][:4]
    assert top == ["", "Decimal Places", "Significant Figures",
                   "Global (Read by Later Calc Sections)"]     # "" is the Variable box
    equation = an_equation(win, "e1:=1/3", x=300, y=500)
    put_down(win)
    equation.setSelected(True)
    words = [a.text() for a in win.build_context_menu(equation, centre(equation)).actions()
             if not a.isSeparator()][:3]
    assert words == top[1:], "the same words in the same place"
    # and, as every markup's, Properties last
    actions = [a for a in menu.actions() if not a.isSeparator()]
    assert actions[-1].text() == "Properties"


def test_decimal_places_from_the_cells_menu_is_one_undo_step(win):
    table = a_number_in_b2(win)
    assert shown(table, "B2") == "12.34567"
    before = steps(win)
    menu_action(win.view.tables.cell_menu(), "Decimal Places", "2").trigger()
    pump()
    table = the_table(win)
    assert shown(table, "B2") == "12.35"
    assert steps(win) == before + 1
    # the formula bar still shows what was typed, as Excel's does
    assert win.formula_bar.edit.text() == "12.34567"
    ticks = [a.text() for a in menu_action(win.view.tables.cell_menu(), "Decimal Places",
                                           "2").parent().actions() if a.isChecked()]
    assert ticks == ["2"]
    win.undo_something()
    pump()
    assert shown(the_table(win), "B2") == "12.34567"


def test_significant_figures_from_the_cells_menu(win):
    table = a_number_in_b2(win, "12345.678")
    menu_action(win.view.tables.cell_menu(), "Decimal Places", "3").trigger()
    pump()
    assert shown(the_table(win), "B2") == "12345.678"
    before = steps(win)
    menu_action(win.view.tables.cell_menu(), "Significant Figures").trigger()
    pump()
    table = the_table(win)
    assert shown(table, "B2") == "12300", "three significant figures, as SMath shows them"
    assert steps(win) == before + 1
    assert menu_action(win.view.tables.cell_menu(), "Significant Figures").isChecked()
    win.undo_something()
    pump()
    assert shown(the_table(win), "B2") == "12345.678"


def test_significant_figures_on_a_general_cell_takes_the_equations_places(win):
    table = a_number_in_b2(win, "0.0123456")
    menu_action(win.view.tables.cell_menu(), "Significant Figures").trigger()
    pump()
    assert shown(the_table(win), "B2") == "0.01235"     # four, the equations' default


def test_a_quantitys_significant_figures_keep_its_unit(win):
    table = a_number_in_b2(win, "12.345 kN")
    menu_action(win.view.tables.cell_menu(), "Decimal Places", "2").trigger()
    menu_action(win.view.tables.cell_menu(), "Significant Figures").trigger()
    pump()
    assert shown(the_table(win), "B2") == "12 kN"


def test_the_cells_entries_are_bindable_commands(win):
    from calcforge.ui.bindable_list import COMMANDS
    for n in range(16):
        assert f"cell.decimal_places.{n}" in COMMANDS
    assert "cell.decimal_places.general" in COMMANDS
    assert "cell.significant_figures" in COMMANDS


# -- 3. the equation's rows in the panel change it, one undo step each ----------------------

def test_equation_rows_change_the_equation_one_step_each(win):
    item = an_equation(win, "2/3=")
    put_down(win)
    item.setSelected(True)
    win.refresh_selection()
    before = steps(win)
    type_into(child(win, QSpinBox, "equationDecimals"), "2")
    assert display_text(item.region.display) == "0.67"
    assert steps(win) == before + 1
    tick(child(win, QCheckBox, "equationSignificant"))
    assert item.region.fmt.significant
    assert steps(win) == before + 2
    win.undo_something()
    (back,) = [i for i in win.view.scene().items() if isinstance(i, CalcItem)]
    assert not (back.region.fmt and back.region.fmt.significant)
    assert display_text(back.region.display) == "0.67"


def test_global_and_the_result_unit_from_the_panel(win):
    item = an_equation(win, "f2:=3000'N", y=120)
    put_down(win)
    item.setSelected(True)
    win.refresh_selection()
    tick(child(win, QCheckBox, "equationGlobal"))
    assert item.region.is_global
    used = an_equation(win, "f2=", y=180)
    put_down(win)
    used.setSelected(True)
    win.refresh_selection()
    before = steps(win)
    assert display_text(used.region.display) == "3 kN"       # as worked out
    type_into(child(win, QLineEdit, "equationUnit"), "N")
    assert steps(win) == before + 1
    assert used.region.editor.unit.text() == "'N"             # a unit, as SMath's list puts it
    assert display_text(used.region.display).startswith("3000")
    assert child(win, QLineEdit, "equationUnit").text() == "N"


def test_a_panel_row_on_the_equation_being_typed_keeps_the_typing(win):
    """Opened by a click, the equation shows in Properties; a change there
    finishes the typing as its own step, then makes its own."""
    item = an_equation(win, "4/3=")
    put_down(win)
    click_on(win, item)
    assert win.view.calc.item is item
    keys(win, Qt.Key_Home)
    typed(win, "1+")                              # 1+4/3=
    before = steps(win)
    type_into(child(win, QSpinBox, "equationDecimals"), "1")
    (now,) = [i for i in win.view.scene().items() if isinstance(i, CalcItem)]
    assert display_text(now.region.display) == "2.3"
    assert steps(win) == before + 2, "the typing, then the setting"
    assert now.isSelected() and panel(win)[0] == "Equation Properties"
    win.undo_something()
    (now,) = [i for i in win.view.scene().items() if isinstance(i, CalcItem)]
    assert display_text(now.region.display) == "2.3333", "the typing stays"


# -- the panel's Cells section --------------------------------------------------------------

def test_the_cells_section_changes_the_cells_one_step_each(win):
    table = a_number_in_b2(win)
    before = steps(win)
    type_into(child(win, QSpinBox, "cellsDecimalPlaces"), "1")
    assert shown(the_table(win), "B2") == "12.3"
    assert steps(win) == before + 1
    tick(child(win, QCheckBox, "cellsBold"))
    st = the_table(win).sheet.workbook.style_of(the_table(win).sheet, 1, 1)
    assert st.bold and steps(win) == before + 2
    win.undo_something()
    pump()
    st = the_table(win).sheet.workbook.style_of(the_table(win).sheet, 1, 1)
    assert not st.bold and st.number_format == "0.0"


def test_the_cells_section_follows_the_active_cell(win):
    table = a_number_in_b2(win)
    menu_action(win.view.tables.cell_menu(), "Decimal Places", "3").trigger()
    pump()
    assert child(win, QSpinBox, "cellsDecimalPlaces").value() == 3
    keys(win, Qt.Key_Down)                       # to B3, in General
    pump()
    assert win.view.tables.active == (2, 1)
    assert child(win, QSpinBox, "cellsDecimalPlaces").text() == "General"
    assert child(win, QLabel, "cellsSelection").text() == "B3"


def test_the_cells_unit_in_the_panel_is_the_formula_bars(win):
    table = a_number_in_b2(win, "2500 N")
    type_into(child(win, QLineEdit, "cellsUnit"), "kN")
    assert shown(the_table(win), "B2") == "2.5 kN"
    assert win.formula_bar.unit.text() == "kN"
    # a unit of another kind is refused, and the cells keep theirs
    type_into(child(win, QLineEdit, "cellsUnit"), "m")
    assert shown(the_table(win), "B2") == "2.5 kN"


def test_the_cells_menus_properties_opens_the_panel_on_the_cells(win):
    a_number_in_b2(win)
    win.show_panel("dock_properties", False)
    menu_action(win.view.tables.cell_menu(), "Properties").trigger()
    pump()
    assert win.dock_properties.isVisible()
    assert "Cells" in panel(win)[1]


# -- 4. the other inconsistencies put right -------------------------------------------------

def test_a_blocks_panel_offers_its_menus_commands_in_its_words(win):
    win.view.calc.place_cross(win.document.pages[0].frame, QPointF(300, 600))
    win.insert_block()
    pump()
    texts = {b.text() for b in win.properties_panel.body.findChildren(QPushButton)}
    boxes = {b.text() for b in win.properties_panel.body.findChildren(QCheckBox)}
    assert {"Select Its Equations", "Remove Block, Keep Equations"} <= texts
    assert "Self-Contained" in boxes


def test_a_tables_and_a_charts_panel_buttons_say_what_their_menus_say(win):
    table = make_table(win)
    put_down(win)
    table.setSelected(True)
    win.refresh_selection()
    texts = {b.text() for b in win.properties_panel.body.findChildren(QPushButton)}
    assert "Edit Table" in texts and "Edit cells" not in texts


def test_the_equation_panel_rows_use_the_menus_words(win):
    item = an_equation(win, "3/7=")
    put_down(win)
    item.setSelected(True)
    win.refresh_selection()
    form_labels = {label.text() for label in win.properties_panel.body.findChildren(QLabel)}
    assert {"Decimal Places:", "Exponential Threshold:", "Result Unit:"} <= form_labels
    boxes = {b.text() for b in win.properties_panel.body.findChildren(QCheckBox)}
    assert {"Significant Figures", "Global", "Trailing Zeros"} <= boxes
    assert child(win, QPushButton, "equationConditionalFormatting").text() == \
        "Conditional Formatting…"


def test_places_and_significant_figures_of_a_number_format():
    assert places_of(None) is None and places_of("General") is None
    assert places_of("#,##0.00") == 2 and places_of("d/mm/yyyy") is None
    assert with_places(None, 2) == "0.00" and with_places("0.00", 0) == "0"
    assert with_places("#,##0", 3) == "#,##0.000"
    assert with_places("0.0%", 2) == "0.00%"
    assert with_places("0.00E+00", 1) == "0.0E+00"
    assert with_places("d/mm/yyyy", 1) == "0.0"
    for value, text in ((12.3456, "12.3"), (12345, "12300"), (0.0012345, "0.00123"),
                        (9.996, "10.0"), (-2.5, "-2.50")):
        assert format_value(value, "0.000", significant=True).text == text
    assert format_value(12345, "#,##0.000", significant=True).text == "12,300"


def test_significant_figures_survive_saving(win, tmp_path):
    from tests.test_calc_saving import reopen, save_to
    a_number_in_b2(win, "12345.678")
    menu_action(win.view.tables.cell_menu(), "Decimal Places", "3").trigger()
    menu_action(win.view.tables.cell_menu(), "Significant Figures").trigger()
    pump()
    path = str(tmp_path / "sig.pdf")
    save_to(win, path)
    reopen(win, path)
    assert shown(the_table(win), "B2") == "12300"
