"""The workbook: cells kept calculated, Excel's rules for moving things,
undo, and the bridge to the document's equations."""
from __future__ import annotations

import pytest

from calcforge.sheet.numfmt import format_value
from calcforge.sheet.refs import parse_cell
from calcforge.sheet.values import NAME, REF, Qty
from calcforge.sheet.workbook import Workbook


def put(wb, sheet, **cells):
    with wb.transaction():
        for a1, text in cells.items():
            r = parse_cell(a1)
            wb.set_input(sheet, r.row, r.col, text)


def get(sheet, a1):
    r = parse_cell(a1)
    return sheet.value(r.row, r.col)


def text(sheet, a1):
    return format_value(get(sheet, a1)).text


def typed(sheet, a1):
    r = parse_cell(a1)
    return sheet.input(r.row, r.col)


@pytest.fixture
def wb():
    return Workbook()


def test_a_change_flows_through_every_reader(wb):
    s = wb.add_sheet()
    put(wb, s, A1="2", A2="=A1*3", A3="=A2+A1", B1="=SUM(A1:A3)")
    assert (get(s, "A2"), get(s, "A3"), get(s, "B1")) == (6, 8, 16)
    put(wb, s, A1="10")
    assert (get(s, "A2"), get(s, "A3"), get(s, "B1")) == (30, 40, 80)


def test_cells_are_worked_out_in_the_order_they_depend_on_each_other(wb):
    """A5 may be read above where it is, as in Excel."""
    s = wb.add_sheet()
    put(wb, s, A1="=A5*2", A5="=B5+1", B5="4")
    assert get(s, "A1") == 10


def test_listeners_hear_only_what_changed(wb):
    s = wb.add_sheet()
    put(wb, s, A1="1", A2="=A1+1", C1="7")
    heard = []
    wb.listeners.append(heard.append)
    put(wb, s, A1="5")
    assert heard[-1] == {(s.id, 0, 0), (s.id, 1, 0)}


def test_a_loop_is_a_circular_reference(wb):
    s = wb.add_sheet()
    put(wb, s, A1="=B1+1", B1="=A1+1", C1="=A1+10")
    assert wb.circular == [(s.id, 0, 0), (s.id, 0, 1)]
    assert get(s, "A1") == 0 and get(s, "C1") == 10
    put(wb, s, D1="5")
    assert wb.circular, "an unrelated edit doesn't forget the loop"
    put(wb, s, B1="3")
    assert wb.circular == [] and get(s, "A1") == 4 and get(s, "C1") == 14


def test_a_cell_reading_itself_is_circular(wb):
    s = wb.add_sheet()
    put(wb, s, A1="=A1+1")
    assert wb.circular == [(s.id, 0, 0)]


def test_undo_and_redo_are_whole_steps(wb):
    s = wb.add_sheet()
    put(wb, s, A1="1", A2="=A1*2")
    put(wb, s, A1="7", B1="x")
    assert get(s, "A2") == 14
    wb.undo()
    assert get(s, "A2") == 2 and typed(s, "B1") == ""
    wb.redo()
    assert get(s, "A2") == 14 and typed(s, "B1") == "x"


def test_inserting_rows_moves_cells_and_references(wb):
    s = wb.add_sheet()
    put(wb, s, A1="1", A2="2", A3="3", B1="=SUM(A1:A3)", B2="=$A$3*A2", C1="=A:A")
    wb.insert_rows(s, 1, 2)            # before row 2
    assert typed(s, "B1") == "=SUM(A1:A5)", "a range grows when rows go inside it"
    assert typed(s, "B4") == "=$A$5*A4", "$ references move with their cells too"
    assert typed(s, "C1") == "=A:A"
    assert get(s, "B1") == 6
    wb.undo()
    assert typed(s, "B1") == "=SUM(A1:A3)" and typed(s, "B2") == "=$A$3*A2" and get(s, "B1") == 6


def test_deleting_rows_shrinks_ranges_and_breaks_lost_references(wb):
    s = wb.add_sheet()
    put(wb, s, A1="1", A2="2", A3="3", A4="4", B1="=SUM(A1:A4)", B2="=A3", C1="=A3*2")
    wb.delete_rows(s, 2, 1)            # row 3
    assert typed(s, "B1") == "=SUM(A1:A3)"
    assert typed(s, "C1") == "=#REF!*2" and get(s, "C1") == REF
    assert get(s, "B1") == 7
    wb.undo()
    assert typed(s, "C1") == "=A3*2" and get(s, "C1") == 6


def test_inserting_and_deleting_columns(wb):
    s = wb.add_sheet()
    put(wb, s, A1="1", B1="2", C1="=A1+B1", D1="=SUM(A1:B1)")
    wb.insert_cols(s, 1, 1)
    assert typed(s, "D1") == "=A1+C1" and typed(s, "E1") == "=SUM(A1:C1)" and get(s, "D1") == 3
    wb.delete_cols(s, 0, 1)
    assert typed(s, "C1") == "=#REF!+B1"
    assert typed(s, "D1") == "=SUM(A1:B1)"


def test_references_from_other_sheets_follow_inserted_rows(wb):
    a, b = wb.add_sheet("Loads"), wb.add_sheet("Design")
    put(wb, a, A1="5")
    put(wb, b, A1="=Loads!A1*2")
    wb.insert_rows(a, 0, 3)
    assert typed(b, "A1") == "=Loads!A4*2" and get(b, "A1") == 10


def test_copying_moves_relative_references_only(wb):
    s = wb.add_sheet()
    put(wb, s, A1="1", A2="2", B1="=A1*$A$1+A$1")
    wb.copy_block(s, 0, 1, 0, 1, s, 1, 2)    # B1 -> C2
    assert typed(s, "C2") == "=B2*$A$1+B$1"
    wb.copy_block(s, 0, 1, 0, 1, s, 0, 0) if False else None


def test_copying_off_the_sheet_is_a_ref_error(wb):
    s = wb.add_sheet()
    put(wb, s, B2="=A1")
    wb.copy_block(s, 1, 1, 1, 1, s, 0, 0)    # B2 -> A1: A1's A1 is off the top-left
    assert typed(s, "A1") == "=#REF!"


def test_paste_special_values_and_formats(wb):
    s = wb.add_sheet()
    put(wb, s, A1="5 kN", B1="=A1*2", C1="12%")
    wb.copy_block(s, 0, 0, 0, 2, s, 2, 0, what="values")
    assert typed(s, "B3") == "10 kN" and typed(s, "A3") == "5 kN"
    wb.copy_block(s, 0, 2, 0, 2, s, 4, 0, what="formats")
    assert typed(s, "A5") == "" and wb.styles.get(s.cell(4, 0).style).number_format == "0%"


def test_moving_cells_keeps_their_readers_reading_them(wb):
    s = wb.add_sheet()
    put(wb, s, A1="3", A2="4", B1="=A1+A2", C1="=SUM(A1:A2)")
    wb.move_block(s, 0, 0, 1, 0, s, 5, 3)    # A1:A2 -> D6:D7
    assert typed(s, "B1") == "=D6+D7" and typed(s, "C1") == "=SUM(D6:D7)"
    assert get(s, "B1") == 7 and typed(s, "A1") == ""
    wb.undo()
    assert typed(s, "B1") == "=A1+A2" and get(s, "B1") == 7


def test_a_moved_formula_keeps_what_it_reads(wb):
    s = wb.add_sheet()
    put(wb, s, A1="3", B1="=A1*2")
    wb.move_block(s, 0, 1, 0, 1, s, 4, 4)
    assert typed(s, "E5") == "=A1*2" and get(s, "E5") == 6


def test_renaming_a_sheet_updates_every_formula(wb):
    a, b = wb.add_sheet("Sheet1"), wb.add_sheet()
    put(wb, a, A1="2")
    put(wb, b, A1="=Sheet1!A1+sheet1!A1")
    wb.rename_sheet(a, "Beam loads")
    assert typed(b, "A1") == "='Beam loads'!A1+'Beam loads'!A1" and get(b, "A1") == 4
    with pytest.raises(ValueError):
        wb.rename_sheet(b, "beam LOADS")
    wb.undo()
    assert a.name == "Sheet1" and typed(b, "A1") == "=Sheet1!A1+sheet1!A1"


def test_sheet_names_are_given_and_unique(wb):
    assert [wb.add_sheet().name, wb.add_sheet().name, wb.add_sheet(kind="table").name] == \
        ["Sheet1", "Sheet2", "Table1"]
    with pytest.raises(ValueError):
        wb.add_sheet("bad:name")


def test_a_deleted_sheet_leaves_ref_errors(wb):
    a, b = wb.add_sheet("A"), wb.add_sheet("B")
    put(wb, a, A1="2")
    put(wb, b, A1="=A!A1*2")
    assert get(b, "A1") == 4
    wb.remove_sheet(a)
    assert get(b, "A1") == REF
    wb.undo()
    assert get(b, "A1") == 4


def test_defined_names(wb):
    s = wb.add_sheet("Loads")
    put(wb, s, D12="12 kN", A1="1", A2="2", A3="3")
    wb.define_name("W_total", "Loads!$D$12")
    wb.define_name("Lengths", "Loads!$A$1:$A$3")
    wb.define_name("gamma", "1.35")
    put(wb, s, B1="=W_total*gamma", B2="=SUM(Lengths)")
    assert text(s, "B1") == "16.2 kN" and get(s, "B2") == 6
    put(wb, s, D12="20 kN")
    assert text(s, "B1") == "27 kN"
    wb.define_name("gamma", "1.5")
    assert text(s, "B1") == "30 kN"
    wb.insert_rows(s, 0, 1)
    assert wb.find_name("W_total", None).refers_to == "Loads!$D$13"


def test_document_variables_are_read_by_name(wb):
    """A name that is no cell and no defined name is a variable from the
    document's equations, asked for where the sheet sits."""
    from calcforge.calc.engine.units import Quantity

    s = wb.add_sheet()
    variables = {"L.beam": Quantity(6.0, (1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)), "M20": Quantity(3.0, (0,) * 11)}
    asked = []

    def outside(sheet, name):
        asked.append((sheet.name, name))
        return variables[name]

    wb.outside = outside
    put(wb, s, A1="=L.beam*2", A2="=var(M20)+1", A3="=M20", A4="=nothing")
    assert text(s, "A1") == "12 m" and get(s, "A2") == 4 and get(s, "A4") == NAME
    assert get(s, "A3") == 0, "M20 is the cell; var(M20) is the variable"
    variables["L.beam"] = Quantity(10.0, (1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0))
    wb.outside_changed({"L.beam"})
    assert text(s, "A1") == "20 m"
    assert {"l.beam", "m20", "nothing"} <= wb.outside_names_read()


def test_values_go_to_the_equations_as_quantities(wb):
    from calcforge.calc.engine.units import Quantity
    from calcforge.calc.engine.values import Matrix, String
    from calcforge.sheet.evaluate import to_engine

    s = wb.add_sheet()
    put(wb, s, A1="5 kN", A2="3", A3="abc")
    q = to_engine(get(s, "A1"))
    assert isinstance(q, Quantity) and q.value == 5000.0 and q.dims[0] == 1
    assert to_engine(get(s, "A2")).value == 3.0
    assert isinstance(to_engine(get(s, "A3")), String)
    from calcforge.sheet.evaluate import RefValue

    m = to_engine(RefValue(s, 0, 0, 1, 0).to_array())
    assert isinstance(m, Matrix) and (m.nrows, m.ncols) == (2, 1)


def test_typing_implies_a_number_format(wb):
    s = wb.add_sheet()
    put(wb, s, A1="12.5%", A2="$1,200.00", A3="2026-10-09", A4="1 1/2")
    fmt = lambda a1: wb.styles.get(s.cell(parse_cell(a1).row, parse_cell(a1).col).style).number_format
    assert (fmt("A1"), fmt("A2"), fmt("A3"), fmt("A4")) == ("0.0%", "$#,##0.00", "yyyy-mm-dd", "# ?/?")
    assert format_value(get(s, "A1"), fmt("A1")).text == "12.5%"
    assert format_value(get(s, "A3"), fmt("A3")).text == "2026-10-09"


def test_missing_brackets_are_closed(wb):
    s = wb.add_sheet()
    put(wb, s, A1="=SUM(1,2")
    assert typed(s, "A1") == "=SUM(1,2)" and get(s, "A1") == 3


def test_a_formula_that_cannot_be_read_says_name_error(wb):
    s = wb.add_sheet()
    put(wb, s, A1="=1+*2")
    assert get(s, "A1") == NAME and s.cell(0, 0).problem


def test_clear_contents_keeps_the_format(wb):
    s = wb.add_sheet()
    put(wb, s, A1="50%", B1="=A1*2")
    wb.clear(s, 0, 0, 0, 0)
    assert typed(s, "A1") == "" and s.cell(0, 0).style != 0 and get(s, "B1") == 0
    wb.clear(s, 0, 0, 0, 0, "all")
    assert s.cell(0, 0) is None


def test_whole_column_sums_only_walk_filled_cells(wb):
    import time

    s = wb.add_sheet()
    with wb.transaction():
        for r in range(2000):
            wb.set_input(s, r * 37, 0, "1")
        wb.set_input(s, 0, 1, "=SUM(A:A)")
    assert get(s, "B1") == 2000
    start = time.perf_counter()
    put(wb, s, A2="5")
    assert get(s, "B1") == 2005 and time.perf_counter() - start < 0.2


def test_a_big_sheet_edits_quickly(wb):
    import time

    s = wb.add_sheet()
    with wb.transaction():
        for r in range(5000):
            wb.set_input(s, r, 0, str(r))
            wb.set_input(s, r, 1, f"=A{r + 1}*2+1")
            wb.set_input(s, r, 2, f"=B{r + 1}/3")
        wb.set_input(s, 0, 3, "=SUM(C:C)")
    start = time.perf_counter()
    put(wb, s, A10="1000")
    assert time.perf_counter() - start < 0.1
    assert get(s, "C10") == pytest.approx((1000 * 2 + 1) / 3)
