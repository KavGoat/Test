"""Cells take SMath's units (the user's choice, 2026-10-11): 5'kN as SMath
writes a unit, custom units the equations define (kip_s := 5'kN, then
2'kip_s in a cell), and SMath's unit box after the value in the formula bar
to show the cells' quantities in a unit."""
from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

import tests.calc.test_calcforge_window as cw
from calcforge.sheet import values
from calcforge.sheet.inputs import read_value
from calcforge.sheet.values import Qty, UnitTextError, unit_parts
from tests.test_calc_sections import on_page, pump
from tests.test_table_equations import table_at


def test_smaths_apostrophe_marks_a_unit_and_is_not_shown():
    got, _fmt = read_value("5'kN")
    assert isinstance(got, Qty) and got.si == 5000.0 and got.unit == "kN"
    got, _fmt = read_value("2.5'kN/m^2")
    assert got.unit == "kN/m^2"


def test_a_custom_unit_from_the_hook(monkeypatch):
    force = unit_parts("kN")[1]
    monkeypatch.setattr(values, "CUSTOM_UNITS",
                        lambda name: (5000.0, force) if name == "kip_s" else None)
    assert unit_parts("kip_s")[:2] == (5000.0, force)
    assert unit_parts("kip_s/m")[1] == unit_parts("kN/m")[1]
    got, _fmt = read_value("2'kip_s")
    assert isinstance(got, Qty) and got.si == 10000.0 and got.unit == "kip_s"
    # in plain typing, a custom name needs the apostrophe: words stay text
    assert read_value("2 kip_s")[0] == "2 kip_s"
    monkeypatch.setattr(values, "CUSTOM_UNITS", None)
    with pytest.raises(UnitTextError):
        unit_parts("kip_s")


@pytest.fixture
def v(window):
    window.show()
    window.activateWindow()
    window.interactive_prompts = False
    return cw.Sheet(window)


def test_cells_use_the_documents_custom_units_and_the_unit_box(v):
    on_page(v, 0, 40, "kip_s:5'kN")
    table_at(v, 120, [["Load"], ["2'kip_s"], ["3 kN"]], name="Loads")
    pump()
    table = next(t for t in v.window.view.tables._all_tables() if t.sheet.name == "Loads")
    wb = table.sheet.workbook
    got = wb.value(table.sheet, 1, 0)
    assert isinstance(got, Qty) and got.si == 10000.0
    # SMath's unit box after the value: the selection shown in kip_s
    tables = v.window.view.tables
    tables.open(table, (2, 0))
    tables.select((2, 0))
    pump()
    box = v.window.formula_bar.unit
    assert box.isVisible() and box.isEnabled() and box.text() == ""
    assert "kip_s" in __import__("calcforge.ui.unitbox", fromlist=["x"]).unit_names(v.window)
    box.setText("kip_s")
    box.editingFinished.emit()
    pump()
    from calcforge.sheet.numfmt import format_value
    st = wb.style_of(table.sheet, 2, 0)
    assert st.unit == "kip_s"
    assert format_value(wb.value(table.sheet, 2, 0), None, st.unit).text == "0.6 kip_s"
    # a unit that isn't one is refused
    box.setText("frobs")
    box.editingFinished.emit()
    pump()
    assert wb.style_of(table.sheet, 2, 0).unit == "kip_s"
    tables.close()
    pump()
    assert not box.isEnabled()


def test_a_cell_typed_before_its_unit_is_defined_is_read_again(v):
    table_at(v, 40, [["7'brick"]], name="Wall")
    pump()
    table = next(t for t in v.window.view.tables._all_tables() if t.sheet.name == "Wall")
    wb = table.sheet.workbook
    assert wb.value(table.sheet, 0, 0) == "7'brick"           # text until it is a unit
    on_page(v, 0, 160, "brick:0.25'm")
    pump()
    got = wb.value(table.sheet, 0, 0)
    assert isinstance(got, Qty) and abs(got.si - 1.75) < 1e-9 and got.unit == "brick"
    v.press(Qt.Key_Escape)


def test_a_formula_uses_a_custom_unit_written_smaths_way(v):
    table_at(v, 40, [["=3*'kip_s", "=w"]], name="Uses")
    on_page(v, 0, 160, "kip_s:5'kN")
    on_page(v, 0, 200, "w:2'kN")
    pump()
    table = next(t for t in v.window.view.tables._all_tables() if t.sheet.name == "Uses")
    wb = table.sheet.workbook
    got = wb.value(table.sheet, 0, 0)
    assert isinstance(got, Qty) and got.si == 15000.0
    # a bare name is never a unit: w is a variable defined after the table
    assert getattr(wb.value(table.sheet, 0, 1), "code", None) == "#NAME?"
