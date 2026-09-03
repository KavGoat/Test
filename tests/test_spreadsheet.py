"""Spreadsheet formulas, references and workspace integration."""
import pytest

from calcforge.core.engine import Workspace, evaluate_source
from calcforge.core.spreadsheet import (CellError, Sheet, column_index, column_letter,
                                        make_ref, parse_ref, prepare_formula)


def build(rows, workspace=None):
    sheet = Sheet(len(rows), max(len(row) for row in rows))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            sheet.set_raw(r, c, value)
    sheet.recalculate(workspace or Workspace())
    return sheet


def test_column_letters():
    assert column_letter(0) == "A"
    assert column_letter(26) == "AA"
    assert column_index("AA") == 26
    assert parse_ref("$B$3") == (2, 1)
    assert make_ref(2, 1, True, True) == "$B$3"


def test_literals_parse_numbers_units_and_text():
    sheet = build([["12", "3.5 kN", "hello", "TRUE"]])
    assert sheet.value(0, 0) == 12
    assert sheet.value(0, 1).to("kN").magnitude == pytest.approx(3.5)
    assert sheet.value(0, 2) == "hello"
    assert sheet.value(0, 3) is True


def test_cell_reference_and_range():
    sheet = build([["2"], ["3"], ["=SUM(A1:A2)"], ["=A3*2"]])
    assert sheet.value(2, 0) == 5
    assert sheet.value(3, 0) == 10


def test_units_propagate_through_formulas():
    sheet = build([["300 mm", "500 mm", "=A1*B1"]])
    assert sheet.value(0, 2).to("mm**2").magnitude == pytest.approx(150000)


def test_display_unit_per_column():
    sheet = Sheet(1, 2)
    sheet.set_raw(0, 0, "1500 mm")
    sheet.column_units[0] = "m"
    sheet.recalculate(Workspace())
    assert sheet.display_text(0, 0) == "1.5 m"


def test_workspace_variables_available_in_cells():
    workspace = Workspace()
    evaluate_source("gamma := 24 kN/m^3", workspace)
    sheet = build([["2 m^3", "=A1*gamma"]], workspace)
    assert sheet.value(0, 1).to("kN").magnitude == pytest.approx(48)


def test_excel_style_comparison_and_if():
    sheet = build([["5", '=IF(A1>3,"big","small")', '=IF(A1<>5,1,2)']])
    assert sheet.value(0, 1) == "big"
    assert sheet.value(0, 2) == 2


def test_iferror_is_lazy():
    sheet = build([["0", '=IFERROR(1/A1,"n/a")']])
    assert sheet.value(0, 1) == "n/a"


def test_concatenation_operator():
    sheet = build([["7", '="n=" & A1']])
    assert sheet.value(0, 1) == "n=7"


def test_circular_reference_detected():
    sheet = build([["=B1", "=A1"]])
    assert isinstance(sheet.value(0, 0), CellError)
    assert sheet.display_text(0, 0) == "#CIRC"


def test_fill_translates_relative_references():
    sheet = Sheet(4, 3)
    sheet.set_raw(0, 0, "1")
    sheet.set_raw(1, 0, "2")
    sheet.set_raw(0, 2, "=A1*2")
    sheet.fill((0, 2), [(1, 2)])
    assert sheet.raw(1, 2) == "=A2*2"
    sheet.recalculate(Workspace())
    assert sheet.value(1, 2) == 4


def test_absolute_reference_survives_fill():
    sheet = Sheet(3, 2)
    sheet.set_raw(0, 1, "=A1*$B$3")
    sheet.fill((0, 1), [(1, 1)])
    assert sheet.raw(1, 1) == "=A2*$B$3"


def test_lookup_functions():
    sheet = build([["10", "a"], ["20", "b"], ["30", "c"],
                   ["=VLOOKUP(20,A1:A3,B1:B3)", "=MATCH(30,A1:A3)"]])
    assert sheet.value(3, 0) == "b"
    assert sheet.value(3, 1) == 3


def test_statistics_and_conditional_aggregates():
    sheet = build([["1"], ["2"], ["3"],
                   ["=AVERAGE(A1:A3)"], ["=COUNTIF(A1:A3,\">1\")"], ["=SUMPRODUCT(A1:A3,A1:A3)"]])
    assert sheet.value(3, 0) == pytest.approx(2)
    assert sheet.value(4, 0) == 2
    assert sheet.value(5, 0) == 14


def test_insert_and_delete_rows_move_cells():
    sheet = Sheet(3, 2)
    sheet.set_raw(2, 0, "x")
    sheet.insert_rows(0)
    assert sheet.raw(3, 0) == "x"
    sheet.delete_rows(0)
    assert sheet.raw(2, 0) == "x"


def test_header_names_and_column_values():
    sheet = build([["Load Case"], ["3 kN"], ["4 kN"]])
    assert sheet.header_name(0) == "Load_Case"
    assert len(sheet.column_values(0)) == 2


def test_prepare_formula_marks_dependencies():
    prepared, deps = prepare_formula("SUM(A1:B2)+C3", 5, 5)
    assert "_range(0,0,1,1)" in prepared
    assert (2, 2) in deps


def test_round_trip_serialisation():
    sheet = build([["1", "=A1+1"]])
    clone = Sheet.from_dict(sheet.to_dict())
    clone.recalculate(Workspace())
    assert clone.value(0, 1) == 2


def test_sumif_sums_every_match():
    sheet = build([["10", "a"], ["20", "b"], ["30", "a"],
                   ['=SUMIF(B1:B3,"a",A1:A3)'], ['=SUMIF(A1:A3,">15")']])
    assert sheet.value(3, 0) == 40
    assert sheet.value(4, 0) == 50


def test_sumif_keeps_units():
    sheet = build([["10 kN", "a"], ["20 kN", "a"], ['=SUMIF(B1:B2,"a",A1:A2)']])
    assert sheet.value(2, 0).to("kN").magnitude == pytest.approx(30)


def test_cell_ratios_reduce_to_plain_numbers():
    sheet = build([["6 m", "200 mm", "=A1/B1"], ["138 MPa", "355 MPa", "=A2/B2"]])
    assert sheet.value(0, 2) == pytest.approx(30)
    assert sheet.display_text(0, 2) == "30"
    assert sheet.value(1, 2) == pytest.approx(0.3887, rel=1e-3)


def test_cell_angles_keep_their_unit():
    sheet = build([["30 deg"]])
    assert sheet.display_text(0, 0) == "30 deg"


def test_cells_choose_a_readable_unit_too():
    sheet = build([["150 mm", "24 kN/m^3", "=A1*B1"],
                   ["60 mm", "22 kN/m^3", "=A2*B2"],
                   ["", "", "=SUM(C1:C2)"]])
    assert sheet.display_text(0, 2) == "3.6 kPa"
    assert sheet.display_text(2, 2) == "4.92 kPa"


def test_typed_cell_values_keep_a_sensible_unit():
    sheet = build([["150 mm", "896 cm^3", "7200 mm", "355 MPa"]])
    assert sheet.display_text(0, 0) == "150 mm"
    assert sheet.display_text(0, 1) == "896 cm³"
    assert sheet.display_text(0, 2) == "7.2 m"        # out of range for mm
    assert sheet.display_text(0, 3) == "355 MPa"


def test_an_explicit_column_unit_still_wins():
    sheet = Sheet(1, 2)
    sheet.set_raw(0, 0, "150 mm")
    sheet.set_raw(0, 1, "=A1*24 kN/m^3")
    sheet.column_units[1] = "kN/m^2"
    sheet.recalculate(Workspace())
    assert sheet.display_text(0, 1) == "3.6 kN/m²"


# ---------------------------------------------------------------------------
# clipboard from Excel
# ---------------------------------------------------------------------------

def test_a_grid_is_read_from_tab_separated_clipboard_text():
    from calcforge.core.spreadsheet import parse_clipboard_grid
    grid = parse_clipboard_grid("Item\tThickness\nSlab\t150 mm\nScreed\t60 mm\n")
    assert grid == [["Item", "Thickness"], ["Slab", "150 mm"], ["Screed", "60 mm"]]


def test_excel_quoting_survives_the_trip():
    from calcforge.core.spreadsheet import parse_clipboard_grid
    grid = parse_clipboard_grid('a\t"two\nlines"\tc\nd\t"say ""hi"""\tf')
    assert grid == [["a", "two\nlines", "c"], ["d", 'say "hi"', "f"]]


def test_thousands_separators_are_removed_so_numbers_stay_numbers():
    from calcforge.core.spreadsheet import parse_clipboard_grid, parse_literal
    grid = parse_clipboard_grid("1,234.5\t12,000\t1,2,3\tabc,def")
    assert grid == [["1234.5", "12000", "1,2,3", "abc,def"]]
    assert parse_literal(grid[0][0]) == pytest.approx(1234.5)
    assert parse_literal(grid[0][1]) == 12000


def test_a_single_value_is_not_a_grid():
    from calcforge.core.spreadsheet import looks_like_a_grid
    assert not looks_like_a_grid("42")
    assert not looks_like_a_grid("")
    assert looks_like_a_grid("a\tb")
    assert looks_like_a_grid("a\nb")


def test_pasting_text_into_a_sheet_keeps_units_and_formulas():
    sheet = Sheet(4, 3)
    sheet.paste_text("Slab\t150 mm\t=B1*2\nScreed\t60 mm\t=B2*2", 0, 0)
    sheet.recalculate()
    assert sheet.value(0, 1).to("mm").magnitude == pytest.approx(150)
    assert sheet.value(0, 2).to("mm").magnitude == pytest.approx(300)
    assert sheet.value(1, 2).to("mm").magnitude == pytest.approx(120)


# ---------------------------------------------------------------------------
# Named tables a calculation can look values up in
# ---------------------------------------------------------------------------

def _capacity_sheet():
    from calcforge.core.engine import Workspace
    from calcforge.core.spreadsheet import Sheet

    sheet = Sheet(5, 3)
    sheet.header_row = True
    rows = [["d", "V", "N"],
            ["12 mm", "29.4 kN", "2"],
            ["16 mm", "54.3 kN", "3"],
            ["20 mm", "84.8 kN", "4"]]
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            sheet.set_raw(r, c, value)
    sheet.recalculate(Workspace())
    return sheet


def test_a_named_table_gives_back_the_value_beside_the_one_asked_for():
    from calcforge.core.spreadsheet import LookupTable
    from calcforge.core.units import Q_

    bolts = LookupTable("bolts", _capacity_sheet())
    assert bolts(Q_(16, "mm"), "A", "B").to("kN").magnitude == pytest.approx(54.3)


def test_a_value_between_two_rows_is_interpolated():
    from calcforge.core.spreadsheet import LookupTable
    from calcforge.core.units import Q_

    bolts = LookupTable("bolts", _capacity_sheet())
    # halfway between 12 mm (29.4 kN) and 16 mm (54.3 kN)
    got = bolts(Q_(14, "mm"), "A", "B").to("kN").magnitude
    assert got == pytest.approx((29.4 + 54.3) / 2)


def test_columns_can_be_named_by_letter_by_header_or_by_number():
    from calcforge.core.spreadsheet import LookupTable
    from calcforge.core.units import Q_

    bolts = LookupTable("bolts", _capacity_sheet())
    wanted = bolts(Q_(20, "mm"), "A", "B")
    assert bolts(Q_(20, "mm"), "d", "V") == wanted
    assert bolts(Q_(20, "mm"), 1, 2) == wanted


def test_looking_outside_the_table_says_so_rather_than_guessing():
    from calcforge.core.spreadsheet import LookupTable
    from calcforge.core.units import Q_

    bolts = LookupTable("bolts", _capacity_sheet())
    with pytest.raises(ValueError, match="above"):
        bolts(Q_(30, "mm"), "A", "B")
    with pytest.raises(ValueError, match="below"):
        bolts(Q_(6, "mm"), "A", "B")


def test_an_exact_match_is_never_interpolated():
    from calcforge.core.spreadsheet import LookupTable
    from calcforge.core.units import Q_

    bolts = LookupTable("bolts", _capacity_sheet())
    assert bolts(Q_(12, "mm"), "A", "C") == 2       # the row's own value, not 2.0-ish


def test_a_column_that_is_not_there_is_reported():
    from calcforge.core.spreadsheet import LookupTable
    from calcforge.core.units import Q_

    bolts = LookupTable("bolts", _capacity_sheet())
    with pytest.raises(ValueError, match="no column"):
        bolts(Q_(16, "mm"), "A", "Z")


def test_an_arrow_key_puts_the_value_in_and_moves_on(window):
    """A column of numbers is typed the way it is in Excel."""
    from tests.test_usability import double_click, drag, press_key
    from PySide6.QtCore import Qt

    window.select_tool("table")
    drag(window.view, 100, 100, 400, 260)
    table = window.view.scene().ordered_markups()[0]
    double_click(window.view, 140, 130)
    assert window.view.active_table is table
    table.current = (0, 0)

    window.view.open_cell_editor(initial="12")
    press_key(window.view, Qt.Key_Down)
    assert window.view._cell_editor is None
    assert table.sheet.raw(0, 0) == "12"
    assert table.current == (1, 0)


def test_the_cell_editor_lines_up_the_way_the_cell_does(window):
    from tests.test_usability import double_click, drag
    from PySide6.QtCore import Qt

    window.select_tool("table")
    drag(window.view, 100, 100, 400, 260)
    table = window.view.scene().ordered_markups()[0]
    table.sheet.set_raw(1, 0, "42")
    table.current = (1, 0)
    double_click(window.view, 140, 130)
    window.view.active_table = table
    table.current = (1, 0)

    window.view.open_cell_editor()
    assert window.view._cell_editor.alignment() & Qt.AlignRight
    window.view.close_cell_editor(commit=False)


# ---------------------------------------------------------------------------
# Formulas follow the cells they read
# ---------------------------------------------------------------------------

def test_inserting_a_row_moves_the_references_with_it():
    from calcforge.core.spreadsheet import Sheet

    sheet = Sheet(rows=6, cols=4)
    sheet.set_raw(1, 0, "12")
    sheet.set_raw(2, 0, "=A2*2")
    sheet.set_raw(3, 0, "=$A$2+1")

    sheet.insert_rows(1)
    assert sheet.raw(3, 0) == "=A3*2"          # the 12 is on row 3 now
    assert sheet.raw(4, 0) == "=$A$3+1"        # absolute, but still the same cell
    sheet.recalculate()
    assert sheet.value(3, 0) == 24


def test_deleting_a_row_brings_the_references_back():
    from calcforge.core.spreadsheet import Sheet

    sheet = Sheet(rows=6, cols=4)
    sheet.set_raw(1, 0, "12")
    sheet.set_raw(2, 0, "=A2*2")
    sheet.insert_rows(1)
    sheet.delete_rows(1)
    assert sheet.raw(2, 0) == "=A2*2"
    sheet.recalculate()
    assert sheet.value(2, 0) == 24


def test_deleting_the_cell_a_formula_reads_says_so():
    """#REF!, as in Excel: the cell really is gone, and pretending is worse."""
    from calcforge.core.spreadsheet import Sheet

    sheet = Sheet(rows=6, cols=4)
    sheet.set_raw(1, 0, "12")
    sheet.set_raw(0, 2, "=A2*2")
    sheet.delete_cols(0)
    assert "#REF!" in sheet.raw(0, 1)


def test_inserting_a_column_moves_the_references_across():
    from calcforge.core.spreadsheet import Sheet

    sheet = Sheet(rows=6, cols=4)
    sheet.set_raw(1, 1, "8")
    sheet.set_raw(1, 2, "=B2*3")
    sheet.insert_cols(0)
    assert sheet.raw(1, 3) == "=C2*3"
    sheet.recalculate()
    assert sheet.value(1, 3) == 24
