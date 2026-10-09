"""Phase 3's engine: conditional formatting, sort, filter, validation, find."""
from __future__ import annotations

from calcforge.sheet import condfmt, data, find, validation
from calcforge.sheet.refs import parse_cell
from calcforge.sheet.workbook import Workbook


def put(wb, s, **cells):
    with wb.transaction():
        for a1, text in cells.items():
            r = parse_cell(a1)
            wb.set_input(s, r.row, r.col, text)


def look(s, a1):
    r = parse_cell(a1)
    return condfmt.looks_for(s).look(r.row, r.col)


def fill_of(s, a1):
    return look(s, a1).get("format", {}).get("fill")


def test_highlight_rules_with_units():
    wb = Workbook()
    s = wb.add_sheet()
    put(wb, s, A1="250 kN", A2="0.1 MN", A3="5", A4="3 m")
    wb.set_cond_rules(s, [{"type": "cell", "op": "greater", "a": "200 kN", "ranges": [[0, 0, 3, 0]],
                           "format": {"fill": "#ff0000"}}])
    assert fill_of(s, "A1") == "#ff0000"
    assert fill_of(s, "A2") is None, "0.1 MN = 100 kN"
    assert fill_of(s, "A3") is None and fill_of(s, "A4") is None, "other units never match"
    wb.set_cond_rules(s, [{"type": "cell", "op": "greater", "a": "200", "ranges": [[0, 0, 3, 0]],
                           "format": {"fill": "#00ff00"}}])
    assert fill_of(s, "A1") == "#00ff00", "a plain number compares the number as shown"
    assert fill_of(s, "A2") is None


def test_priority_stop_and_formula_rules():
    wb = Workbook()
    s = wb.add_sheet()
    put(wb, s, A1="5", A2="15", B1="10")
    wb.set_cond_rules(s, [
        {"type": "formula", "formula": "=A1>$B$1", "ranges": [[0, 0, 1, 0]],
         "format": {"fill": "#ff0000", "bold": True}, "stop": True},
        {"type": "cell", "op": "greater", "a": "0", "ranges": [[0, 0, 1, 0]],
         "format": {"fill": "#00ff00", "italic": True}},
    ])
    assert look(s, "A2")["format"] == {"fill": "#ff0000", "bold": True}
    assert look(s, "A1")["format"] == {"fill": "#00ff00", "italic": True}


def test_top_average_duplicates_text_blanks():
    wb = Workbook()
    s = wb.add_sheet()
    put(wb, s, A1="1", A2="2", A3="3", A4="4", A5="10", B1="x", B2="Bolt M20", B3="x", C1="")
    rng = [[0, 0, 4, 0]]
    wb.set_cond_rules(s, [{"type": "top", "n": 2, "ranges": rng, "format": {"fill": "#1"}}])
    assert [fill_of(s, f"A{i}") for i in range(1, 6)] == [None, None, None, "#1", "#1"]
    wb.set_cond_rules(s, [{"type": "above", "ranges": rng, "format": {"fill": "#2"}}])
    assert [fill_of(s, f"A{i}") for i in range(1, 6)] == [None, None, None, None, "#2"]
    wb.set_cond_rules(s, [{"type": "duplicate", "ranges": [[0, 1, 2, 1]], "format": {"fill": "#3"}}])
    assert [fill_of(s, f"B{i}") for i in range(1, 4)] == ["#3", None, "#3"]
    wb.set_cond_rules(s, [{"type": "text", "how": "contains", "text": "m20", "ranges": [[0, 1, 2, 1]],
                           "format": {"fill": "#4"}}])
    assert fill_of(s, "B2") == "#4"
    wb.set_cond_rules(s, [{"type": "blanks", "ranges": [[0, 2, 1, 2]], "format": {"fill": "#5"}}])
    assert fill_of(s, "C2") == "#5"


def test_bars_scales_icons():
    wb = Workbook()
    s = wb.add_sheet()
    put(wb, s, A1="0", A2="5", A3="10")
    wb.set_cond_rules(s, [{"type": "databar", "ranges": [[0, 0, 2, 0]]},
                          {"type": "scale", "colors": ["#ff0000", "#00ff00"], "ranges": [[0, 0, 2, 0]]},
                          {"type": "icons", "set": "arrows", "ranges": [[0, 0, 2, 0]]}])
    assert look(s, "A3")["bar"][0] == 1.0 and look(s, "A2")["bar"][0] == 0.5
    assert look(s, "A1")["scale"] == "#ff0000" and look(s, "A3")["scale"] == "#00ff00"
    assert look(s, "A1")["icon"][0] == "▼" and look(s, "A3")["icon"][0] == "▲"


def test_rules_move_with_inserted_rows_and_undo():
    wb = Workbook()
    s = wb.add_sheet()
    put(wb, s, A1="5")
    wb.set_cond_rules(s, [{"type": "cell", "op": "greater", "a": "1", "ranges": [[0, 0, 0, 0]],
                           "format": {"fill": "#f00"}}])
    wb.insert_rows(s, 0, 2)
    assert s.cond_rules[0]["ranges"] == [[2, 0, 2, 0]] and fill_of(s, "A3") == "#f00"
    wb.undo()
    assert s.cond_rules[0]["ranges"] == [[0, 0, 0, 0]]


def test_sort_by_two_columns_keeps_row_formulas():
    wb = Workbook()
    s = wb.add_sheet()
    put(wb, s, A1="Name", B1="Load", C1="Twice",
        A2="b", B2="3", C2="=B2*2", A3="a", B3="3", C3="=B3*2", A4="c", B4="1", C4="=B4*2", A5="", B5="9")
    data.sort_block(wb, s, 0, 0, 4, 2, [(1, False), (0, True)], header=True)
    assert [s.input(r, 0) for r in range(1, 5)] == ["", "a", "b", "c"] or \
        [s.input(r, 0) for r in range(1, 5)] == ["a", "b", "c", ""]
    names = [s.input(r, 0) for r in range(1, 5)]
    loads = [s.value(r, 1) for r in range(1, 5)]
    assert loads == [9, 3, 3, 1] and names == ["", "a", "b", "c"]
    assert [s.value(r, 2) for r in range(2, 5)] == [6, 6, 2]
    assert s.input(2, 2) == "=B3*2"


def test_blanks_sort_last_both_ways():
    wb = Workbook()
    s = wb.add_sheet()
    put(wb, s, A1="2", A3="1", A4="text")
    data.sort_block(wb, s, 0, 0, 3, 0, [(0, False)])
    assert [s.input(r, 0) for r in range(4)] == ["text", "2", "1", ""]


def test_autofilter_hides_and_subtotal_skips():
    wb = Workbook()
    s = wb.add_sheet()
    put(wb, s, A1="Kind", B1="Load", A2="beam", B2="5", A3="col", B3="7", A4="beam", B4="9",
        C1="=SUBTOTAL(9,B2:B4)", C2="=SUM(B2:B4)")
    data.set_filter(wb, s, (0, 0, 3, 1))
    data.set_criteria(wb, s, 0, {"kind": "values", "values": ["beam"]})
    assert s.filtered_rows == {2} and s.height(2) == 0
    assert s.value(0, 2) == 14 and s.value(1, 2) == 21
    data.set_criteria(wb, s, 1, {"kind": "custom", "conditions": [">6"], "join": "and"})
    assert s.filtered_rows == {1, 2}
    assert data.column_values(s, 0) == ["beam", "col"]
    wb.undo()
    assert s.filtered_rows == {2}


def test_validation_lists_numbers_with_units_and_custom():
    wb = Workbook()
    s = wb.add_sheet()
    put(wb, s, D1="M16", D2="M20", D3="M24")
    s.validations = [
        {"ranges": [[0, 0, 0, 0]], "type": "list", "source": "=$D$1:$D$3"},
        {"ranges": [[1, 0, 1, 0]], "type": "decimal", "op": "between", "a": "0 kN", "b": "500 kN",
         "error": "Load must be 0 to 500 kN"},
        {"ranges": [[2, 0, 2, 0]], "type": "whole", "op": "greaterOrEqual", "a": "1"},
        {"ranges": [[3, 0, 3, 0]], "type": "custom", "formula": "=A4<=$D$5"},
        {"ranges": [[4, 0, 4, 0]], "type": "length", "op": "lessOrEqual", "a": "3"},
    ]
    put(wb, s, D5="10")
    assert validation.list_items(s, s.validations[0]) == ["M16", "M20", "M24"]
    assert validation.check(s, 0, 0, "m20") is None and validation.check(s, 0, 0, "M30")
    assert validation.check(s, 1, 0, "250 kN") is None
    assert validation.check(s, 1, 0, "0.6 MN") == "Load must be 0 to 500 kN"
    assert validation.check(s, 1, 0, "5 m") is not None
    assert validation.check(s, 2, 0, "2.5") is not None and validation.check(s, 2, 0, "3") is None
    assert validation.check(s, 3, 0, "7") is None and validation.check(s, 3, 0, "11") is not None
    assert validation.check(s, 4, 0, "abcd") is not None
    put(wb, s, A2="900 kN")
    assert (1, 0) in validation.invalid_cells(s)


def test_find_and_replace():
    wb = Workbook()
    s = wb.add_sheet()
    put(wb, s, A1="Bolt M20", A2="bolt M24", A3="=A1&\"x\"", B1="5 kN")
    assert find.find_all(s, "bolt") == [(0, 0), (1, 0)]
    assert find.find_all(s, "bolt", case=True) == [(1, 0)]
    assert find.find_all(s, "M2?", whole=False) == [(0, 0), (1, 0)]
    assert find.find_all(s, "5 kN", look_in="values", whole=True) == [(0, 1)]
    assert find.find_all(s, "A1") == [(2, 0)], "formulas are searched as typed"
    n = find.replace_all(s, "M20", "M30")
    assert n == 1 and s.input(0, 0) == "Bolt M30" and s.value(2, 0) == "Bolt M30x"


def test_everything_is_saved():
    from calcforge.sheet.store import load_sheet, sheet_to_dict
    wb = Workbook()
    s = wb.add_sheet()
    put(wb, s, A1="k", A2="1", A3="2")
    s.cond_rules = [{"type": "databar", "ranges": [[1, 0, 2, 0]]}]
    s.validations = [{"ranges": [[1, 0, 2, 0]], "type": "whole", "op": "greater", "a": "0"}]
    data.set_filter(wb, s, (0, 0, 2, 0))
    data.set_criteria(wb, s, 0, {"kind": "values", "values": ["1"]})
    wb.set_comment(s, 1, 0, "checked")
    saved = sheet_to_dict(s)
    import json
    saved = json.loads(json.dumps(saved))
    s2 = wb.add_sheet()
    load_sheet(s2, saved)
    assert s2.cond_rules == s.cond_rules and s2.validations == s.validations
    assert s2.filter["criteria"] == {0: {"kind": "values", "values": ["1"]}}
    assert s2.filtered_rows == {2} and s2.cell(1, 0).comment == "checked"
