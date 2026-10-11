"""Typing a unit into a cell exactly as into an equation (the user's choice,
2026-10-11): SMath's black unit box after a number, the unit in SMath's blue,
and SMath's own unit list (entries, order, icons, descriptions) under it."""
from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

import tests.calc.test_calcforge_window as cw
from calcforge.sheet.values import Qty
from calcforge.ui.cellunits import box_at, unit_spans, unit_word
from tests.test_calc_sections import on_page, pump
from tests.test_tables import make_table, type_text


def key(w, k):
    """A key as the keyboard sends it: to the cell being typed in."""
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication
    QApplication.sendEvent(w.view.tables.editor or w.view, QKeyEvent(QKeyEvent.KeyPress, k, Qt.NoModifier))
    pump()


def test_where_the_units_are():
    assert box_at("5") == 1 and box_at(" 12.5 ") == 5
    assert box_at("5 k") is None and box_at("=5") is None and box_at("text") is None
    assert unit_spans("5 kN") == [(2, 4)]
    assert unit_spans("2.5'kN/m^2") == [(3, 10)]
    assert unit_spans("12 bolts") == [(3, 8)]          # typed as a unit (black if it isn't one)
    assert unit_spans("=5 kN*B2") == [(3, 5)]
    assert unit_spans("=B2*'kip_s") == [(4, 10)]
    assert unit_spans("=B2+5") == [] and unit_spans("=SUM(A1:A3)") == []
    assert unit_spans('="5 kN"') == []                 # inside a string: text
    assert unit_word("5 k", 3) == (2, "k")
    assert unit_word("5 kN/m", 6) == (5, "m")
    assert unit_word("=5 kN", 5) == (3, "kN")
    assert unit_word("=SUM", 4) is None and unit_word("hello", 5) is None


@pytest.fixture
def v(window):
    window.show()
    window.activateWindow()
    window.interactive_prompts = False
    return cw.Sheet(window)


def test_a_cell_takes_a_unit_as_an_equation_does(window):
    w = window
    w.show()
    table = make_table(w)
    tables = w.view.tables
    tables.select((0, 0))
    type_text(w, "5")
    pump()
    editor = tables.editor
    assert editor is not None and box_at(editor.text()) == 1, "SMath's black box after the number"
    image = editor.grab().toImage()
    assert any(image.pixelColor(x, y) == QColor("#000000")
               for x in range(editor.width()) for y in range(editor.height())
               if editor.x_of(1) + 2 < x), "drawn after the number"
    type_text(w, " k")
    pump()
    units = tables.help.units
    assert units.visible(), "SMath's unit list"
    assert units.list.currentItem().text() == "kA"
    assert "Kiloampere" in units.list.tooltip.text()
    type_text(w, "N")
    pump()
    assert units.list.currentItem().text() == "kN"
    key(w, Qt.Key_Tab)                 # Tab takes the entry, as in SMath
    pump()
    assert editor.text() == "5 kN" and not units.visible()
    key(w, Qt.Key_Return)
    pump()
    got = table.sheet.workbook.value(table.sheet, 0, 0)
    assert isinstance(got, Qty) and got.si == 5000.0


def test_escape_closes_the_list_and_keeps_the_typing(window):
    w = window
    w.show()
    make_table(w)
    tables = w.view.tables
    tables.select((0, 0))
    type_text(w, "3 m")
    pump()
    assert tables.help.units.visible()
    key(w, Qt.Key_Escape)
    pump()
    assert not tables.help.units.visible()
    assert tables.editor is not None and tables.editor.text() == "3 m"


def test_custom_units_are_offered_and_written_smaths_way(v):
    on_page(v, 0, 40, "kip_s:5'kN")
    w = v.window
    from tests.test_table_equations import table_at
    table = table_at(v, 120, [["x"]], name="T")
    pump()
    table = next(t for t in w.view.tables._all_tables() if t.sheet.name == "T")
    tables = w.view.tables
    tables.open(table, (0, 0))
    tables.select((0, 0))
    tables.begin_edit("2", enter_mode=False)
    type_text(w, " kip_")
    pump()
    units = tables.help.units
    assert units.visible()
    names = [units.list.item(i).text() for i in range(units.list.count())]
    assert "kip_s" in names
    units.list.setCurrentRow(names.index("kip_s"))
    units.choose()
    pump()
    assert tables.editor.text() == "2 'kip_s"
    key(w, Qt.Key_Return)
    pump()
    got = table.sheet.workbook.value(table.sheet, 0, 0)
    assert isinstance(got, Qty) and got.si == 10000.0


def test_the_result_unit_box_on_the_selected_cell(window):
    """SMath's unit box after the selected cell's result (the user's choice,
    2026-10-11): black after a quantity, typed into to show it in another
    unit, with SMath's list; blank goes back to the unit as typed; only
    while selected, never printed."""
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication
    from tests.test_tables import cell_scene, click
    w = window
    w.show()
    w.view.set_zoom(2.0)
    table = make_table(w)
    wb = table.sheet.workbook
    wb.set_input(table.sheet, 0, 0, "5000 N")
    wb.set_input(table.sheet, 1, 0, "12")
    tables = w.view.tables
    tables.select((1, 0))
    assert table.unit_box_rect(1, 0) is None, "a plain number has no unit box"
    tables.select((0, 0))
    pump()
    kind, rect = table.unit_box_rect(0, 0)
    assert kind == "box" and rect.left() > table.cell_rect(0, 0).right() - 4
    # drawn on screen while selected, black
    image = w.view.viewport().grab().toImage()
    spot = w.view.mapFromScene(table.mapToScene(rect.center()))
    assert image.pixelColor(spot) == QColor("#000000")
    w.view.centerOn(table.mapToScene(rect.center()))
    pump()
    click(w, table.mapToScene(rect.center()))
    box = tables._result_unit
    assert box is not None and box.isVisible() and box.text() == ""
    for ch in "kN":
        QApplication.sendEvent(box, QKeyEvent(QKeyEvent.KeyPress, 0, Qt.NoModifier, ch))
        pump()
    assert box.list.isVisible() and box.list.currentItem().text() == "kN"
    box.list.hide()
    QApplication.sendEvent(box, QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))
    pump()
    assert not box.isVisible()
    assert wb.style_of(table.sheet, 0, 0).unit == "kN"
    kind, rect = table.unit_box_rect(0, 0)
    assert kind == "unit", "set: the unit itself is the box"
    # its unit clicked: typed into again; blank goes back to as typed
    click(w, table.mapToScene(rect.center()))
    assert box.isVisible() and box.text() == "kN"
    box.clear()
    QApplication.sendEvent(box, QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))
    pump()
    assert wb.style_of(table.sheet, 0, 0).unit in (None, "")
    # Esc leaves it as it was; not a unit is refused
    kind, rect = table.unit_box_rect(0, 0)
    click(w, table.mapToScene(rect.center()))
    box.setText("frobs")
    QApplication.sendEvent(box, QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))
    pump()
    assert wb.style_of(table.sheet, 0, 0).unit in (None, "")
    w.undo_stack.undo()
    pump()
    from calcforge.items.table import TableItem
    (table,) = [i for i in w.view.scene().items() if type(i) is TableItem]
    assert table.sheet.workbook.style_of(table.sheet, 0, 0).unit == "kN", "one undo step each"
