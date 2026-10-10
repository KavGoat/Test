"""Named ranges and dynamic arrays in tables, through the real window
(spreadsheet phase 5): the Name Box, Create from Selection, the Name
Manager, names saved with their sheet, equations reading a named block, and
a spilled block shown in its table."""
from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from calcforge.sheet.refs import parse_cell
from calcforge.ui import names
from tests.test_tables import enter, key, make_table, pump, type_text


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.view.set_zoom(1.0)
    return window


def put(table, a1, text):
    r = parse_cell(a1)
    table.sheet.workbook.set_input(table.sheet, r.row, r.col, text)


def get(table, a1):
    r = parse_cell(a1)
    cell = table.sheet.cells.get((r.row, r.col))
    return None if cell is None else cell.value


def loads(w):
    table = make_table(w, width=48 * 3, height=15 * 5)
    w.view.tables.open(table, (0, 0))
    for a1, text in (("A1", "Member"), ("B1", "Load"), ("C1", "Span"), ("A2", "B1"), ("B2", "10"),
                     ("C2", "4"), ("A3", "B2"), ("B3", "20"), ("C3", "5"), ("A4", "B3"),
                     ("B4", "30"), ("C4", "6")):
        put(table, a1, text)
    return table


def test_the_name_box_names_the_selection_and_goes_back_to_it(w):
    table = loads(w)
    tables = w.view.tables
    tables.select((1, 1), (3, 1))
    tables.bar.name.setText("W_all")
    tables.bar._go()
    wb = table.sheet.workbook
    assert wb.find_name("W_all", None).refers_to.endswith("!$B$2:$B$4")
    assert tables.bar.name.text() == "W_all"
    tables.select((0, 0))
    tables.go_to("W_all")
    assert tables.selection() == (1, 1, 3, 1)
    put(table, "D1", "=SUM(W_all)")
    assert get(table, "D1") == 60
    # one undo step takes the name away again
    w.undo_stack.undo()
    pump()
    (table,) = [t for t in tables._all_tables()]
    assert table.sheet.workbook.find_name("W_all", None) is None


def test_create_from_selection_uses_the_headings(w):
    table = loads(w)
    tables = w.view.tables
    tables.select((0, 1), (3, 2))
    made = names.create_from_selection(tables, top_row=True)
    assert made == ["Load", "Span"]
    put(table, "D1", "=SUMPRODUCT(Load,Span)")
    assert get(table, "D1") == 10 * 4 + 20 * 5 + 30 * 6
    assert names.name_from_label("Load (kN)") == "Load_kN"
    assert names.name_from_label("2nd") == "_2nd"


def test_name_manager_new_edit_delete_with_scope_and_comment(w):
    table = loads(w)
    tables = w.view.tables
    w.interactive_prompts = False
    names.name_manager(tables)
    manager = w._last_data_dialog
    manager.open_editor(None)
    editor = w._last_name_dialog
    editor.name.setText("gee")
    editor.refers.setText("=9.81")
    editor.comment.setText("gravity")
    assert manager.apply_editor(editor) is None
    wb = table.sheet.workbook
    dn = wb.find_name("gee", None)
    assert dn.refers_to == "9.81" and dn.comment == "gravity"
    assert manager.table.item(0, 1).text() == "9.81"
    # local to this table
    manager.open_editor(None)
    editor = w._last_name_dialog
    editor.name.setText("Lmax")
    editor.refers.setText(f"=MAX({table.name}!$C$2:$C$4)")
    editor.scope.setCurrentIndex(editor.scope.findData(table.sheet.id))
    manager.apply_editor(editor)
    assert wb.find_name("Lmax", table.sheet) is not None
    assert wb.find_name("Lmax", None) is None
    put(table, "D1", "=Lmax*gee")
    assert get(table, "D1") == pytest.approx(6 * 9.81)
    # edit, then delete
    rows = [manager.table.item(i, 0).text() for i in range(manager.table.rowCount())]
    manager.table.selectRow(rows.index("gee"))
    manager.open_editor(manager.chosen())
    editor = w._last_name_dialog
    editor.refers.setText("=10")
    manager.apply_editor(editor, manager.chosen())
    (table,) = tables._all_tables()
    assert get(table, "D1") == pytest.approx(60)
    rows = [manager.table.item(i, 0).text() for i in range(manager.table.rowCount())]
    manager.table.selectRow(rows.index("gee"))
    manager.delete_chosen()
    (table,) = tables._all_tables()
    assert get(table, "D1").code == "#NAME?"
    # a bad formula is refused in the dialog
    manager.open_editor(None)
    editor = w._last_name_dialog
    editor.name.setText("bad name")
    editor._check()
    assert editor.problem.text()


def test_names_are_saved_with_their_table(w, tmp_path):
    from tests.test_calc_saving import reopen, save_to
    table = loads(w)
    tables = w.view.tables
    tables.select((1, 2), (3, 2))
    names.define(tables, "Spans", f"{table.name}!$C$2:$C$4")
    names.define(tables, "phi", "0.9", scope=table.sheet, comment="factor")
    path = str(tmp_path / "names.pdf")
    tables.close()
    save_to(w, path)
    reopen(w, path)
    pump()
    from calcforge.items.table import TableItem
    (table,) = [i for i in w.view.scene().items() if type(i) is TableItem]
    wb = table.sheet.workbook
    assert wb.find_name("Spans", None) is not None
    local = wb.find_name("phi", table.sheet)
    assert local is not None and local.sheet == table.sheet.id and local.comment == "factor"
    assert wb.find_name("phi", None) is None


def test_equations_read_a_named_block_as_a_vector(w):
    from tests.test_calc_saving import answer, write_lines
    table = loads(w)
    tables = w.view.tables
    tables.select((1, 1), (3, 1))
    names.define(tables, "Wl", f"{table.name}!$B$2:$B$4")
    tables.close()
    write_lines(w, ["S:sum(Wl)", "S="], y=400)
    assert answer(w, "S=") == "60"


def test_a_spilled_block_shows_in_its_table(w):
    table = loads(w)
    tables = w.view.tables
    tables.select((0, 2))
    put(table, "C2", "")
    put(table, "C3", "")
    put(table, "C4", "")
    tables.select((1, 2))
    type_text(w, "=SORT(B2:B4,,-1)")
    enter(w)
    assert [get(table, a) for a in ("C2", "C3", "C4")] == [30, 20, 10]
    assert table.sheet.input(2, 2) == ""
    tables.select((2, 2))
    assert table.sheet.workbook.spill_block(table.sheet, 2, 2) == (1, 2, 3, 2)
    assert tables.bar.edit.placeholderText() == "=SORT(B2:B4,,-1)"
    # typing over it: #SPILL! until it is cleared
    type_text(w, "x")
    enter(w)
    assert get(table, "C2").code == "#SPILL!"
    tables.select((2, 2))
    key(w, Qt.Key_Delete)
    assert get(table, "C2") == 30
    # it doesn't spill out of its table
    tables.select((3, 0))
    type_text(w, "=SEQUENCE(3)")
    enter(w)
    assert get(table, "A4").code == "#SPILL!"
