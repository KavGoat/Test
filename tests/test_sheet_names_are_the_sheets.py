"""A spreadsheet's named cells are the sheet's own (the user, 2026-10-21:
"It's not a variable name I can access outside by itself, only
Sheet.name. So don't show the name of spreadsheet named cells above the
cell; only show it if it's a CalcForge variable named cell").

* A spreadsheet's own name (Define Name, the Name Box, the Name Manager,
  Create from Selection) is read by the equations only as Sheet.name; a
  bare name in an equation does not reach it.
* A cell named as a CalcForge variable (its right-click Variable box) is
  read bare, and carries its name tag; a spreadsheet's own name has none.
* The Name Manager lists both.
"""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from calcforge.items import nametags
from calcforge.ui import names
from tests.calc.test_definition_order import a_document, a_sheet, answer, on_page
from tests.test_tables import make_table, shown


def test_a_spreadsheet_name_is_read_only_as_sheet_dot_name():
    _doc, calc, book = a_document()
    sheet = a_sheet(book, 0, cells={(0, 0): "4"})
    book.workbook.define_name("x", "Sheet1!$A$1")
    bare = on_page(calc, 1, 20, "x=")
    qualified = on_page(calc, 1, 60, "Sheet1.x=")
    calc.recalculate()
    assert answer(bare) == "x - not defined."
    assert answer(qualified) == "4"
    assert book.written_as(book.workbook.names[("x", None)]) == "Sheet1.x"
    assert sheet.workbook.find_name("x", sheet) is not None, "the cells read it bare, as Excel's"


def test_the_sheet_is_the_one_whose_cells_it_names():
    _doc, calc, book = a_document()
    first = a_sheet(book, 0, name="Sheet1", cells={(0, 0): "1"})
    a_sheet(book, 0, y=200, name="Loads", cells={(0, 0): "7"}, uid="u-loads")
    # made while Sheet1 was open (the Name Manager's home), naming Loads' cell
    book.workbook.define_name("y", "Loads!$A$1", home=first)
    asked = on_page(calc, 1, 20, "Loads.y=")
    other = on_page(calc, 1, 60, "Sheet1.y+0=")
    calc.recalculate()
    assert answer(asked) == "7"
    assert answer(other) == "Sheet1.y - not defined."
    assert book.written_as(book.workbook.names[("y", None)]) == "Loads.y"


def test_a_calcforge_variable_named_cell_is_read_bare():
    _doc, calc, book = a_document()
    a_sheet(book, 0, cells={(0, 0): "4"}, names={"x": "Sheet1!$A$1"})
    bare = on_page(calc, 1, 20, "x=")
    calc.recalculate()
    assert answer(bare) == "4"
    assert book.written_as(book.workbook.names[("x", None)]) == "x"


def test_the_equations_autocomplete_offers_sheet_dot_name():
    _doc, _calc, book = a_document()
    a_sheet(book, 0, cells={(0, 0): "4", (1, 0): "5"}, names={"v": "Sheet1!$A$2"})
    book.workbook.define_name("x", "Sheet1!$A$1")
    offered = book.equation_names()
    assert "Sheet1.x" in offered and "x" not in offered and "v" in offered


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.view.set_zoom(1.0)
    return window


def test_only_a_calcforge_variable_carries_a_name_tag(w):
    table = make_table(w, width=48 * 3, height=15 * 4)
    tables = w.view.tables
    wb = table.sheet.workbook
    wb.set_input(table.sheet, 0, 0, "4")
    wb.set_input(table.sheet, 1, 0, "5")
    # the Name Box: a spreadsheet's own name
    tables.select((0, 0))
    assert names.go_to_name(tables, "x_sheet")
    # the cell's Variable box: a CalcForge variable
    tables.select((1, 0))
    assert tables.name_selection("x_calc")
    assert not wb.names[("x_sheet", None)].variable
    assert wb.names[("x_calc", None)].variable
    assert [n for n, _b in nametags.named_blocks(table.sheet)] == ["x_calc"]
    # the Variable box shows only the CalcForge variable
    tables.select((0, 0))
    assert tables.selection_name() is None
    assert tables.selection_name(variable=False).name == "x_sheet"
    tables.select((1, 0))
    assert tables.selection_name().name == "x_calc"
    # the Name Manager lists both, and says which is the CalcForge variable
    manager = names.NameManagerDialog(tables)
    listed = {manager.table.item(i, 0).text(): manager.table.item(i, 3).text()
              for i in range(manager.table.rowCount())}
    assert listed == {"x_calc": "Workbook (CalcForge variable)", "x_sheet": "Workbook"}
    manager.reject()
    # edited in the Name Manager, a variable stays one
    assert names.define(tables, "x_calc2", f"{table.name}!$A$2",
                        replacing=wb.names[("x_calc", None)]) is None
    assert wb.names[("x_calc2", None)].variable
    tables.close()
    QApplication.instance().processEvents()
    assert shown(table, "A1") == "4"


def test_the_kind_of_name_is_saved(w, tmp_path):
    table = make_table(w, width=48 * 3, height=15 * 4)
    tables = w.view.tables
    wb = table.sheet.workbook
    wb.set_input(table.sheet, 0, 0, "4")
    wb.set_input(table.sheet, 1, 0, "5")
    tables.select((0, 0))
    assert names.go_to_name(tables, "x_sheet")
    tables.select((1, 0))
    assert tables.name_selection("x_calc")
    tables.close()
    path = str(tmp_path / "names.pdf")
    w.document.path = path
    assert w.save_document()
    w.open_path(path)
    QApplication.instance().processEvents()
    from calcforge.items.table import TableItem
    (again,) = [t for t in w.view.scene().items() if isinstance(t, TableItem)]
    got = again.sheet.workbook.names
    assert not got[("x_sheet", None)].variable and got[("x_calc", None)].variable
    assert [n for n, _b in nametags.named_blocks(again.sheet)] == ["x_calc"]
