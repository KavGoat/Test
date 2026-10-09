"""Tables and equations reading each other (docs/SPREADSHEET_DESIGN.md):
a table reads the variables defined before it; the equations read a table's
cells, named cells, columns by heading and the table as a lookup; where
reading order and dependencies disagree, dependencies win."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication

import tests.calc.test_calcforge_window as cw
from calcforge.calc.docsheet import PT_PER_PX, sheet_for
from calcforge.calc.engine.display import display_text
from calcforge.items.calc import CalcItem
from calcforge.items.table import TableItem
from calcforge.sheet.numfmt import format_value


@pytest.fixture
def v(window):
    window.show()
    window.activateWindow()
    return cw.Sheet(window)


def pump():
    QApplication.instance().processEvents()


def equation(v, y_px, keys):
    v.type_at(36, y_px, "")
    v.keys(keys)
    v.press(Qt.Key_Return)
    v.calc.leave()
    pump()


def answers(v):
    out = {}
    for item in v.window.view.scene().items():
        if isinstance(item, CalcItem) and item.region is not None:
            r = item.region
            text = r.error.message if r.error else (display_text(r.display) if r.display else None)
            out[item.region.editor.root.text().split("=")[0].split(":")[0]] = text
    return out


def table_at(v, y_px, rows, name=None):
    """A table at (36 px, y px) holding rows of typed entries."""
    table = TableItem(max(len(rows), 1), max(len(r) for r in rows))
    v.window.view.begin_snapshot([v.frame])
    v.frame.add_markup(table, QPointF(36 * PT_PER_PX, y_px * PT_PER_PX))
    wb = table.sheet.workbook
    for i, row in enumerate(rows):
        for j, text in enumerate(row):
            if text:
                wb.set_input(table.sheet, i, j, text)
    if name:
        wb.rename_sheet(table.sheet, name)
    v.window.view.commit_snapshot("table")
    pump()
    return table


def shown(table, row, col):
    st = table.sheet.workbook.style_of(table.sheet, row, col)
    return format_value(table.sheet.value(row, col), st.number_format, st.unit).text


def test_a_table_reads_variables_defined_before_it(v):
    equation(v, 18, "L:6'm")
    table = table_at(v, 100, [["=L*2", "=w"]])
    equation(v, 300, "w:3'kN")
    assert shown(table, 0, 0) == "12 m"
    assert shown(table, 0, 1) == "#NAME?", "w is defined after the table"
    equation(v, 18, "") if False else None


def test_equations_read_cells_names_columns_and_lookups(v):
    table = table_at(v, 18, [["d", "A", "B"], ["10 mm", "100", "5"], ["20 mm", "300", "9"]],
                     name="bolts")
    wb = table.sheet.workbook
    wb.define_name("A_big", "bolts!$B$3")
    sheet_for(v.window.document).recalculate()
    equation(v, 200, "x:bolts.B2")
    equation(v, 240, "x=")
    equation(v, 280, "y:A_big")
    equation(v, 320, "y=")
    equation(v, 360, "s:sum(bolts.A)")
    equation(v, 400, "s=")
    equation(v, 440, "k:bolts(15'mm,\"A\")")
    equation(v, 480, "k=")
    got = answers(v)
    assert got["x"] == "100" or got.get("x") is None
    found = {}
    for item in v.window.view.scene().items():
        if isinstance(item, CalcItem) and item.region is not None and item.region.display is not None:
            found[item.region.editor.root.text()] = display_text(item.region.display)
    assert found["x="] == "100"
    assert found["y="] == "300"
    assert found["s="] == "400"
    assert found["k="] == "200", "interpolated halfway between 100 and 300"


def test_a_table_value_change_recalculates_the_equations(v):
    table = table_at(v, 18, [["5 kN"]], name="Loads")
    equation(v, 200, "P:Loads.A1*2")
    equation(v, 240, "P=")
    table.sheet.workbook.set_input(table.sheet, 0, 0, "7 kN")
    pump()
    found = {item.region.editor.root.text(): display_text(item.region.display)
             for item in v.window.view.scene().items()
             if isinstance(item, CalcItem) and item.region and item.region.display is not None}
    assert found["P="] == "14 kN"


def test_dependencies_win_over_reading_order(v):
    """An equation above a table can read it; the table reads a variable
    defined between them."""
    equation(v, 18, "z:T1.A1+1")
    equation(v, 54, "z=")
    equation(v, 120, "a:10")
    table = table_at(v, 200, [["=a*3"]], name="T1")
    found = {item.region.editor.root.text(): display_text(item.region.display)
             for item in v.window.view.scene().items()
             if isinstance(item, CalcItem) and item.region and item.region.display is not None}
    assert table.sheet.value(0, 0) == 30
    assert found["z="] == "31"
