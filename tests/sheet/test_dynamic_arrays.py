"""Dynamic arrays and structured references (spreadsheet phase 5): a block
result spills, #SPILL! when something is in the way, A1# reads the block,
and a table's columns are read by their headings."""
from __future__ import annotations

from calcforge.sheet.formula import rename_sheet_in
from calcforge.sheet.refs import parse_cell
from calcforge.sheet.store import load_sheet, sheet_to_dict
from calcforge.sheet.values import REF, SPILL, VALUE
from calcforge.sheet.workbook import Workbook


def put(wb, sheet, **cells):
    for a1, text in cells.items():
        r = parse_cell(a1)
        wb.set_input(sheet, r.row, r.col, text)


def get(sheet, a1):
    r = parse_cell(a1)
    cell = sheet.cells.get((r.row, r.col))
    return None if cell is None else cell.value


def fresh():
    wb = Workbook()
    return wb, wb.add_sheet("Sheet1")


def test_a_block_result_spills_down_and_across():
    wb, s = fresh()
    put(wb, s, A1="=SEQUENCE(3,2)")
    assert [get(s, a) for a in ("A1", "B1", "A2", "B2", "A3", "B3")] == [1, 2, 3, 4, 5, 6]
    assert get(s, "A4") is None
    assert s.spills[(0, 0)] == (3, 2)
    assert wb.spill_block(s, 2, 1) == (0, 0, 2, 1)
    # the spilled cells are read like any other
    put(wb, s, D1="=SUM(A1:B3)", D2="=B3*10")
    assert get(s, "D1") == 21 and get(s, "D2") == 60
    # the block grows and shrinks with its formula
    put(wb, s, A1="=SEQUENCE(4,2)")
    assert get(s, "B4") == 8 and get(s, "D1") == 21
    put(wb, s, A1="=SEQUENCE(2,2)")
    assert get(s, "A3") is None and get(s, "D2") == 0
    # and a plain value takes it all back
    put(wb, s, A1="5")
    assert s.spills == {} and get(s, "B1") is None


def test_something_in_the_way_is_spill_error_until_it_goes():
    wb, s = fresh()
    put(wb, s, B2="x", A1="=SEQUENCE(3,2)")
    assert get(s, "A1") is SPILL
    assert get(s, "A2") is None
    put(wb, s, B2="")
    assert get(s, "A1") == 1 and get(s, "B2") == 4
    # typing over a spilled cell blocks it again
    put(wb, s, A3="here")
    assert get(s, "A1") is SPILL and get(s, "A3") == "here"
    assert get(s, "B1") is None
    # two blocks may not overlap
    put(wb, s, A3="", D1="=SEQUENCE(2)", D2="")
    put(wb, s, C2="=SEQUENCE(1,3)")
    assert get(s, "C2") is SPILL and get(s, "D2") == 2


def test_the_spill_operator_reads_the_whole_block():
    wb, s = fresh()
    put(wb, s, A1="=SEQUENCE(4)", C1="=SUM(A1#)", C2="=ROWS(A1#)")
    assert get(s, "C1") == 10 and get(s, "C2") == 4
    put(wb, s, A1="=SEQUENCE(6)")
    assert get(s, "C1") == 21 and get(s, "C2") == 6
    put(wb, s, E1="=SORT(A1#,,-1)")
    assert [get(s, f"E{i}") for i in range(1, 7)] == [6, 5, 4, 3, 2, 1]
    put(wb, s, B9="7", C3="=B9#")
    assert get(s, "C3") is REF


def test_filter_unique_sort_spill_and_follow_their_data():
    wb, s = fresh()
    put(wb, s, A1="b", A2="a", A3="b", A4="c", B1="=UNIQUE(A1:A4)", C1="=SORT(UNIQUE(A1:A4))")
    assert [get(s, f"B{i}") for i in range(1, 4)] == ["b", "a", "c"]
    assert [get(s, f"C{i}") for i in range(1, 4)] == ["a", "b", "c"]
    put(wb, s, A4="d")
    assert get(s, "C3") == "d"


def test_inserted_rows_move_the_formula_and_its_block():
    wb, s = fresh()
    put(wb, s, A2="=SEQUENCE(3)", C1="=SUM(A2#)")
    wb.insert_rows(s, 0, 2)
    assert get(s, "A4") == 1 and get(s, "A6") == 3 and get(s, "A3") is None
    assert s.spills == {(3, 0): (3, 1)}
    assert get(s, "C3") == 6


def test_spilled_values_are_not_saved_but_come_back():
    wb, s = fresh()
    put(wb, s, A1="=SEQUENCE(3)")
    data = sheet_to_dict(s)
    assert [c[:3] for c in data["cells"]] == [[0, 0, "=SEQUENCE(3)"]]
    wb2 = Workbook()
    s2 = wb2.add_sheet("Sheet1")
    load_sheet(s2, data)
    wb2.recalculate(everything=True)
    assert get(s2, "A3") == 3


def test_undo_takes_a_spill_back():
    wb, s = fresh()
    wb.journal = True
    put(wb, s, A1="=SEQUENCE(3)")
    assert get(s, "A3") == 3
    wb.undo()
    assert get(s, "A3") is None and s.spills == {}
    wb.redo()
    assert get(s, "A3") == 3


def a_table(wb):
    t = wb.add_sheet("Loads", "table")
    t.size = (4, 3)
    rows = [("Member", "Load (kN)", "Span"), ("B1", "10", "4"), ("B2", "20", "5"), ("B3", "30", "6")]
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            wb.set_input(t, r, c, text)
    return t


def test_structured_references_read_a_tables_columns_by_heading():
    wb, s = fresh()
    t = a_table(wb)
    put(wb, s, A1="=SUM(Loads[Load (kN)])", A2="=SUM(Loads[[Load (kN)]:[Span]])",
        A3="=COUNTA(Loads[#Headers])", A4="=ROWS(Loads[#All])", A5="=ROWS(Loads[])",
        A6="=COUNTA(Loads[[#Headers],[Member]])", A7="=loads[span]")
    assert [get(s, f"A{i}") for i in range(1, 7)] == [60, 75, 3, 4, 3, 1]
    assert get(s, "A7") == 4          # a column of three in one cell spills… into A7:A9
    assert get(s, "A9") == 6
    # this row, inside the table
    t.size = (4, 4)
    put(wb, t, D1="Moment", D2="=[@[Load (kN)]]*[@Span]^2/8")
    for row in (2, 3):
        wb.set_input(t, row, 3, "=[@[Load (kN)]]*[@Span]^2/8")
    assert [get(t, f"D{i}") for i in (2, 3, 4)] == [20, 62.5, 135]
    # the values follow the cells
    put(wb, t, B3="40")
    assert get(s, "A1") == 80 and get(t, "D3") == 125
    # outside the table, this row means nothing
    put(wb, s, B1="=Loads[@Span]")
    assert get(s, "B1") is VALUE
    # a heading that isn't there, a totals row it hasn't got
    put(wb, s, B2="=SUM(Loads[Weight])", B3="=SUM(Loads[#Totals])")
    assert get(s, "B2") is REF and get(s, "B3") is REF


def test_structured_references_grow_with_the_table_and_follow_renames():
    wb, s = fresh()
    t = a_table(wb)
    put(wb, s, A1="=SUM(Loads[Span])")
    assert get(s, "A1") == 15
    wb.set_size(t, 5, 3)
    put(wb, t, A5="B4", B5="5", C5="10")
    assert get(s, "A1") == 25
    assert rename_sheet_in("SUM(Loads[Span])*Loads[@Span]", "Loads", "Beams") == \
        "SUM(Beams[Span])*Beams[@Span]"
