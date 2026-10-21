"""References follow what is done to the cells, as Excel's formulas do —
in the tables' and sheets' own formulas and in the equations that read them
(the user, 2026-10-19: "Renaming a sheet or a cell getting moved should
update any equations ... like how Excel auto updates formulas, make sure
our spreadsheet also follow the smart Excel method").

Answers by pop-up the same day: a deleted cell an equation read becomes
#REF! (Loads.#REF, a red error until fixed; undo puts it back); a retyped
table heading is followed by equations (Loads.Load) and formulas
(Loads[Load]); text in quotes is left alone."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication

from calcforge.sheet.workbook import Workbook


# -- the spreadsheet itself ------------------------------------------------------------------------

def _book():
    wb = Workbook()
    a = wb.add_sheet("Loads", "table")
    b = wb.add_sheet("Other")
    return wb, a, b


def test_a_formula_reading_a_cell_a_block_lands_on_gives_ref_as_in_excel():
    wb, a, b = _book()
    wb.set_input(a, 0, 0, "1")
    wb.set_input(a, 4, 0, "5")
    wb.set_input(b, 0, 0, "=Loads!A5*2")          # reads the cell about to be replaced
    wb.set_input(b, 1, 0, "=Loads!A1*2")          # reads the cell that moves
    wb.recalculate()
    wb.move_block(a, 0, 0, 0, 0, a, 4, 0)         # A1 dragged onto A5
    assert b.cells[(0, 0)].input == "=Loads!#REF!*2"
    assert b.cells[(1, 0)].input == "=Loads!A5*2"
    wb.recalculate()
    assert b.value(1, 0) == 2


def test_renaming_a_defined_name_renames_it_in_every_formula():
    wb, a, b = _book()
    wb.set_input(a, 0, 0, "7")
    wb.define_name("W_total", "Loads!$A$1")
    wb.define_name("Twice", "W_total*2")
    wb.set_input(b, 0, 0, "=W_total+1")
    wb.set_input(b, 1, 0, "=SUM(W_total,W_totalx)")
    wb.recalculate()
    dn = wb.names[("w_total", None)]
    wb.rename_name(dn, "W_sum")
    assert b.cells[(0, 0)].input == "=W_sum+1"
    assert b.cells[(1, 0)].input == "=SUM(W_sum,W_totalx)", "only the name itself"
    assert wb.names[("twice", None)].refers_to == "W_sum*2"
    assert ("w_total", None) not in wb.names
    wb.recalculate()
    assert b.value(0, 0) == 8


def test_a_sheets_own_name_of_the_same_spelling_is_another_name():
    wb, a, b = _book()
    wb.define_name("k", "1")
    wb.define_name("k", "2", sheet=b)
    wb.set_input(a, 0, 0, "=k")                    # the document's k
    wb.set_input(b, 0, 0, "=k")                    # Other's own k
    wb.rename_name(wb.names[("k", None)], "k_doc")
    assert a.cells[(0, 0)].input == "=k_doc"
    assert b.cells[(0, 0)].input == "=k"


def test_retyping_a_tables_heading_renames_its_structured_references():
    wb, a, b = _book()
    a.size = (3, 2)
    wb.set_input(a, 0, 0, "Load")
    wb.set_input(a, 0, 1, "Span")
    wb.set_input(a, 1, 0, "5")
    wb.set_input(a, 2, 0, "7")
    wb.set_input(b, 0, 0, "=SUM(Loads[Load])")
    wb.set_input(b, 1, 0, '=COUNTIF(Loads[Load],"Load")')
    wb.recalculate()
    wb.set_input(a, 0, 0, "Load kN")
    assert b.cells[(0, 0)].input == "=SUM(Loads[Load kN])"
    assert b.cells[(1, 0)].input == '=COUNTIF(Loads[Load kN],"Load")', "text is left alone"
    wb.recalculate()
    assert b.value(0, 0) == 12


def test_a_heading_two_columns_share_is_not_followed():
    wb, a, b = _book()
    a.size = (2, 2)
    wb.set_input(a, 0, 0, "Load")
    wb.set_input(a, 0, 1, "Load")
    wb.set_input(b, 0, 0, "=SUM(Loads[Load])")
    wb.set_input(a, 0, 0, "Dead")
    assert b.cells[(0, 0)].input == "=SUM(Loads[Load])"


# -- the equations ---------------------------------------------------------------------------------

import tests.calc.test_calcforge_window as cw  # noqa: E402
from calcforge.calc.docsheet import PT_PER_PX, sheet_for  # noqa: E402
from calcforge.calc.engine.display import display_text  # noqa: E402
from calcforge.items.calc import CalcItem  # noqa: E402
from calcforge.items.table import TableItem  # noqa: E402


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


def table_at(v, y_px, rows, name):
    table = TableItem(len(rows), max(len(r) for r in rows))
    v.window.view.begin_snapshot([v.frame])
    v.frame.add_markup(table, QPointF(36 * PT_PER_PX, y_px * PT_PER_PX))
    wb = table.sheet.workbook
    for i, row in enumerate(rows):
        for j, text in enumerate(row):
            if text:
                wb.set_input(table.sheet, i, j, text)
    wb.rename_sheet(table.sheet, name)
    v.window.view.commit_snapshot("table")
    pump()
    return table


def equations(v) -> dict:
    """Each equation's text -> what it shows (its result, or its error)."""
    sheet_for(v.window.document).recalculate()
    pump()
    out = {}
    for item in v.window.view.scene().items():
        if isinstance(item, CalcItem) and item.region is not None:
            r = item.region
            out[r.editor.root.text()] = r.error.message if r.error else (
                display_text(r.display) if r.display is not None else None)
    return out


def tables_in(v) -> list:
    """The tables on the canvas now (undo puts back new items)."""
    return [i for i in v.window.view.scene().items() if isinstance(i, TableItem)]


def editing(v, table, cell):
    tables = v.window.view.tables
    tables.open(table, cell)
    return tables


def test_renaming_a_table_renames_it_in_the_equations_and_undo_puts_it_back(v):
    table = table_at(v, 18, [["5", "Load"], ["7", "3"]], "Loads")
    equation(v, 200, "P:Loads.A1*2")
    equation(v, 240, "P=")
    equation(v, 280, "Q:Loads.Load")
    equation(v, 320, "Q=")
    assert "P≔Loads.A1*2" in equations(v)
    assert v.window.view.tables.rename_to(table, "Beam loads")
    got = equations(v)
    assert "P≔Beam_loads.A1*2" in got and "Q≔Beam_loads.Load" in got
    assert got["P="] == "10" and got["Q="] == "3"
    v.window.undo_stack.undo()
    pump()
    assert [t.sheet.name for t in tables_in(v)] == ["Loads"]
    assert "P≔Loads.A1*2" in equations(v)


def test_inserting_and_deleting_rows_moves_what_the_equations_read(v):
    table = table_at(v, 18, [["1"], ["2"], ["3"]], "T")
    equation(v, 200, "a:T.A3")
    equation(v, 240, "a=")
    tables = editing(v, table, (0, 0))
    tables.insert_rows()                            # a row above A1
    got = equations(v)
    assert "a≔T.A4" in got and got["a="] == "3"
    tables.select((3, 0))
    tables.delete_rows()                            # the row a reads
    got = equations(v)
    assert got["a≔T.#REF"] == "T.#REF: the cell it read was deleted (#REF!).", \
        "a red error on the equation, until it is fixed"
    v.window.undo_stack.undo()
    pump()
    got = equations(v)
    assert "a≔T.A4" in got and got["a="] == "3"


def test_a_moved_cell_is_followed_by_the_equations(v):
    table = table_at(v, 18, [["4", ""], ["", ""]], "T")
    equation(v, 200, "b:T.A1+1")
    equation(v, 240, "b=")
    tables = editing(v, table, (0, 0))
    tables._change("Move cells", lambda wb, sheet: wb.move_block(sheet, 0, 0, 0, 0, sheet, 1, 1))
    got = equations(v)
    assert "b≔T.B2+1" in got and got["b="] == "5"


def test_renaming_a_defined_name_in_the_name_manager_renames_it_in_the_equations(v):
    from calcforge.ui import names

    table = table_at(v, 18, [["9"]], "T")
    wb = table.sheet.workbook
    # a spreadsheet's own name, read as Sheet.Name
    equation(v, 200, "w:T.W_total*2")
    equation(v, 240, "w=")
    # a CalcForge variable named cell, read bare
    equation(v, 280, "u:P*3")
    equation(v, 320, "u=")
    tables = editing(v, table, (0, 0))
    assert names.define(tables, "W_total", "T!$A$1") is None
    assert names.define(tables, "P", "T!$A$1", variable=True) is None
    assert equations(v)["w="] == "18" and equations(v)["u="] == "27"
    dn = wb.names[("w_total", None)]
    assert names.define(tables, "W_sum", "T!$A$1", replacing=dn) is None
    got = equations(v)
    assert "w≔T.W_sum*2" in got and got["w="] == "18"
    assert names.define(tables, "P_k", "T!$A$1", replacing=wb.names[("p", None)]) is None
    got = equations(v)
    assert "u≔P_k*3" in got and got["u="] == "27"
    assert wb.names[("p_k", None)].variable, "still a CalcForge variable"
    # the sheet renamed: Sheet.Name follows it
    tables._change("Rename", lambda wb, sheet: wb.rename_sheet(sheet, "Beam"))
    got = equations(v)
    assert "w≔Beam.W_sum*2" in got and got["w="] == "18"


def test_retyping_a_heading_renames_the_column_in_the_equations(v):
    table = table_at(v, 18, [["Load", "Span"], ["5", "2"], ["7", "3"]], "T")
    equation(v, 200, "s:sum(T.Load)")
    equation(v, 240, "s=")
    equation(v, 280, "k:T(6,\"Load\")")
    assert equations(v)["s="] == "12"
    tables = editing(v, table, (0, 0))
    tables._change("Typing", lambda wb, sheet: wb.set_input(sheet, 0, 0, "Load_kN"))
    got = equations(v)
    assert "s≔sum(T.Load_kN)" in got and got["s="] == "12"
    assert 'k≔T(6,"Load")' in got, "text in quotes is left alone"
