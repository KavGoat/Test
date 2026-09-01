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
