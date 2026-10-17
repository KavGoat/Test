"""Which definition an equation reads, whatever kind it is (the user's
report, 2026-10-17): test:=5 kN on page 1, a sheet on page 2 with a cell 2
named test, and test= on page 3 gave 5 kN. As in SMath, definitions are
read in document order — page by page, top to bottom — and the latest one
before the equation wins: equations, named cells and defined names,
Table.Column and Table.D12, table lookups, measurement variables,
calculation-block members and globals after section breaks alike.

At the engine: the document's worksheet (calc/docsheet.py) and its
workbook (sheet/docbook.py), with a stand-in document of plain pages."""
from __future__ import annotations

from types import SimpleNamespace

from calcforge.calc.docsheet import STRIDE, sheet_for
from calcforge.calc.engine.evaluator import TABLES
from calcforge.sheet.docbook import book_for
from calcforge.sheet.numfmt import format_value
from tests.calc.test_block_scope import region, shown


def a_document(pages=4):
    doc = SimpleNamespace(
        pages=[SimpleNamespace(uid=f"p{i}", section_break=False) for i in range(pages)],
        settings=SimpleNamespace(calc_format={}))
    calc = sheet_for(doc)
    book = book_for(doc)
    return doc, calc, book


def on_page(calc, page, y, text, x=36):
    """An equation typed at (x, y) px on a page (0 is the first)."""
    return region(calc.worksheet, page * STRIDE + y, text, x=x)


def a_sheet(book, page, y=0, name="Sheet1", cells=(), names=(), kind="sheet", uid=None):
    """A sheet (or table) at (36, y) px on a page, holding *cells* {(row, col): text}
    and defined names {name: refers_to}."""
    uid = uid or f"u-{name}"
    sheet = book.attach(uid, name, kind)
    wb = book.workbook
    for (row, col), text in dict(cells).items():
        wb.set_input(sheet, row, col, text)
    for defined, refers in dict(names).items():
        wb.define_name(defined, refers)
    book.place(uid, f"p{page}", 36.0, float(y))
    return sheet


def answer(r):
    return r.error.message if r.error is not None else shown(r)


# -- the report ----------------------------------------------------------------------------

def test_a_named_cell_after_an_equation_wins():
    _doc, calc, book = a_document()
    on_page(calc, 0, 20, "test:5'kN")
    a_sheet(book, 1, cells={(0, 0): "2"}, names={"test": "Sheet1!$A$1"})
    asked = on_page(calc, 2, 20, "test=")
    calc.recalculate()
    assert answer(asked) == "2", "the sheet's test is the latest before test="


def test_an_equation_after_a_named_cell_wins():
    """The reverse: the cell named test above test:=5 kN."""
    _doc, calc, book = a_document()
    a_sheet(book, 0, cells={(0, 0): "2"}, names={"test": "Sheet1!$A$1"})
    on_page(calc, 1, 20, "test:5'kN")
    asked = on_page(calc, 2, 20, "test=")
    calc.recalculate()
    assert answer(asked) == "5 kN"


def test_each_equation_reads_the_latest_before_it():
    _doc, calc, book = a_document()
    on_page(calc, 0, 20, "test:5'kN")
    first = on_page(calc, 0, 60, "test=")
    a_sheet(book, 1, cells={(0, 0): "2"}, names={"test": "Sheet1!$A$1"})
    second = on_page(calc, 2, 20, "test=")
    on_page(calc, 2, 60, "test:7'm")
    third = on_page(calc, 2, 100, "test=")
    calc.recalculate()
    assert [answer(first), answer(second), answer(third)] == ["5 kN", "2", "7 m"]


def test_redefinition_on_the_same_page():
    """A table on the same page as the equations: its top-left is its place."""
    _doc, calc, book = a_document()
    on_page(calc, 0, 20, "test:5'kN")
    above = on_page(calc, 0, 60, "test=")
    a_sheet(book, 0, y=100, kind="table", name="T1", cells={(0, 0): "2"},
            names={"test": "T1!$A$1"})
    below = on_page(calc, 0, 300, "test=")
    on_page(calc, 0, 340, "test:9")
    last = on_page(calc, 0, 380, "test=")
    calc.recalculate()
    assert [answer(above), answer(below), answer(last)] == ["5 kN", "2", "9"]


def test_a_table_moved_past_the_equations_changes_what_they_read():
    _doc, calc, book = a_document()
    a_sheet(book, 0, y=0, kind="table", name="T1", cells={(0, 0): "2"},
            names={"test": "T1!$A$1"}, uid="t1")
    on_page(calc, 0, 100, "test:5'kN")
    asked = on_page(calc, 0, 300, "test=")
    calc.recalculate()
    assert answer(asked) == "5 kN"
    book.place("t1", "p0", 36.0, 200.0)            # between the definition and test=
    assert answer(asked) == "2"
    book.place("t1", "p0", 36.0, 0.0)
    assert answer(asked) == "5 kN"


def test_the_number_is_dimensionless():
    _doc, calc, book = a_document()
    on_page(calc, 0, 20, "test:5'kN")
    a_sheet(book, 1, cells={(0, 0): "2"}, names={"test": "Sheet1!$A$1"})
    asked = on_page(calc, 2, 20, "test*2=")
    calc.recalculate()
    assert answer(asked) == "4", "2 has no unit, so test·2 = 4, not kN"


# -- every kind of definition ----------------------------------------------------------------

def test_table_columns_and_cells_follow_reading_order():
    _doc, calc, book = a_document()
    on_page(calc, 0, 20, "T1.A2:100")
    a_sheet(book, 1, kind="table", name="T1",
            cells={(0, 0): "Load", (1, 0): "3", (2, 0): "4"})
    cell = on_page(calc, 2, 20, "T1.A2=")
    column = on_page(calc, 2, 60, "sum(T1.Load)=")
    calc.recalculate()
    assert answer(cell) == "3", "the table's A2 is the later definition"
    assert answer(column) == "7"


def test_a_table_lookup_follows_reading_order():
    _doc, calc, book = a_document()
    on_page(calc, 0, 20, "bolts(x):x*1000")
    before = on_page(calc, 0, 60, "bolts(2)=")
    a_sheet(book, 1, kind="table", name="bolts",
            cells={(0, 0): "d", (0, 1): "A", (1, 0): "1", (1, 1): "10", (2, 0): "3", (2, 1): "30"})
    after = on_page(calc, 2, 20, "bolts(2)=")
    on_page(calc, 2, 60, "bolts(x):x*5")
    again = on_page(calc, 2, 100, "bolts(2)=")
    calc.recalculate()
    assert [answer(before), answer(after), answer(again)] == ["2000", "20", "10"]


def test_a_measurement_variable_is_an_equation_definition():
    """A named measurement defines its variable with an ordinary region where
    it is (items/calc.py MeasureVariable): typed as L:6250'mm."""
    _doc, calc, book = a_document()
    a_sheet(book, 0, cells={(0, 0): "2"}, names={"L": "Sheet1!$A$1"})
    on_page(calc, 1, 20, "L:6250'mm")
    asked = on_page(calc, 2, 20, "L=")
    calc.recalculate()
    assert answer(asked) == "6.25 m"


def test_inside_a_self_contained_block():
    """A block reads everything above it, a sheet's names included, whichever
    is latest; its own definitions stay inside it."""
    _doc, calc, book = a_document()
    on_page(calc, 0, 20, "test:5'kN")
    a_sheet(book, 1, cells={(0, 0): "2"}, names={"test": "Sheet1!$A$1"})
    inside_first = on_page(calc, 2, 120, "test=")
    on_page(calc, 2, 160, "test:8")
    inside_last = on_page(calc, 2, 200, "test=")
    outside = on_page(calc, 2, 400, "test=")
    ws = calc.worksheet
    ws.set_scopes({inside_first.id: "b", ws.ordered()[-3].id: "b", inside_last.id: "b"})
    ws.calculate()
    assert answer(inside_first) == "2", "the sheet's test, defined above the block"
    assert answer(inside_last) == "8", "the block's own"
    assert answer(outside) == "2", "the block's own stays inside it"


def test_a_block_member_after_the_sheet_wins():
    _doc, calc, book = a_document()
    a_sheet(book, 0, cells={(0, 0): "2"}, names={"test": "Sheet1!$A$1"})
    member = on_page(calc, 1, 120, "test:5'kN")
    inside = on_page(calc, 1, 160, "test=")
    ws = calc.worksheet
    ws.set_scopes({member.id: "b", inside.id: "b"})
    ws.calculate()
    assert answer(inside) == "5 kN"


def test_after_a_section_break_a_global_cell_takes_its_turn():
    doc, calc, book = a_document()
    on_page(calc, 0, 20, "test:5'kN")
    calc.worksheet.ordered()[0].is_global = True
    sheet = a_sheet(book, 1, cells={(0, 0): "2"}, names={"test": "Sheet1!$A$1"})
    doc.pages[2].section_break = True
    asked = on_page(calc, 2, 20, "test=")
    calc.recalculate()
    assert answer(asked) == "5 kN", "the sheet's cell is not global: the global equation"
    sheet.page = {"global_cells": [(0, 0, 0, 0)]}
    calc.recalculate()
    assert answer(asked) == "2", "made global, the later cell wins"


def test_after_a_section_break_the_sections_own_definition_wins():
    doc, calc, book = a_document()
    sheet = a_sheet(book, 0, cells={(0, 0): "2"}, names={"test": "Sheet1!$A$1"})
    sheet.page = {"global_cells": [(0, 0, 0, 0)]}
    doc.pages[1].section_break = True
    on_page(calc, 1, 20, "test:5'kN")
    asked = on_page(calc, 1, 60, "test=")
    calc.recalculate()
    assert answer(asked) == "5 kN"


def test_with_nothing_before_a_table_after_still_answers():
    """Dependencies win over reading order (docs/SPREADSHEET_DESIGN.md): with
    no definition before it, an equation reads a table below it."""
    _doc, calc, book = a_document()
    asked = on_page(calc, 0, 20, "test=")
    a_sheet(book, 1, cells={(0, 0): "2"}, names={"test": "Sheet1!$A$1"})
    calc.recalculate()
    assert answer(asked) == "2"


def test_a_built_in_constant_gives_way_only_to_a_definition_before():
    _doc, calc, book = a_document()
    above = on_page(calc, 0, 20, "e=")
    a_sheet(book, 1, cells={(0, 0): "3"}, names={"e": "Sheet1!$A$1"})
    below = on_page(calc, 2, 20, "e=")
    calc.recalculate()
    assert answer(above).startswith("2.71"), "the built-in e, as before"
    assert answer(below) == "3", "the cell named e is defined before it"


def test_a_cell_reads_the_latest_equation_definition_above_it():
    _doc, calc, book = a_document()
    on_page(calc, 0, 20, "w:5'kN")
    on_page(calc, 1, 20, "w:3'kN")
    sheet = a_sheet(book, 2, cells={(0, 0): "=w*2"})
    on_page(calc, 3, 20, "w:100'kN")
    calc.recalculate()
    book.workbook.outside_changed(None)
    assert format_value(sheet.value(0, 0)).text == "6 kN", "w:3 kN, the latest above the sheet"


def test_the_entry_in_force_says_which_kind():
    """IndexedContext.entry, which the Variables panel asks too."""
    _doc, calc, book = a_document()
    first = on_page(calc, 0, 20, "test:5'kN")
    a_sheet(book, 1, cells={(0, 0): "2"}, names={"test": "Sheet1!$A$1"})
    asked = on_page(calc, 2, 20, "test=")
    calc.recalculate()
    ws = calc.worksheet
    assert ws._context_before(asked).entry("test")[1] is TABLES
    second = ws._context_before(first)
    assert second.entry("test") is None
