"""A cell's own unit (the black unit box) taken as SMath takes the unit typed
into an equation's unit placeholder (the user, 2026-10-21: "imagine the
answer is in kN, but the custom unit I typed is N^2: the spreadsheet says
wrong unit, but SMath doesn't and fills in the missing unit").

* Any unit expression is taken. Of the value's dimension it converts; of
  another, the units still needed go before the typed unit, so the number
  times them times the typed unit is the value — the equations' own code
  (calc/engine/display.in_unit_box) does it for both, so a cell shows what
  an equation shows for the same quantity and unit.
* A name that is no unit, a unit written wrongly and a temperature with an
  offset on another kind of quantity are refused with SMath's words.
* While typed, the box shows the unit as SMath's does: N², m⁻¹, kN·m.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from calcforge.calc.engine.display import display_text
from calcforge.sheet.numfmt import BOX_GAP, format_value, unit_runs
from calcforge.sheet.values import _written, with_unit
from calcforge.ui.cellunits import output_unit_refusal
from tests.calc.test_behaviour import error, sheet
from tests.test_tables import click, make_table, shown

def settle():
    for _ in range(4):
        QApplication.instance().processEvents()


def equation_in(value: str, keys: str):
    """What an equation shows for *value* with *keys* typed into its unit
    placeholder: (its display, its error)."""
    _ws, (_a, b) = sheet(f"F:{value}", ["F", "=", "RIGHT"] + list(keys))
    return b.display, error(b)


def number_of(display) -> float:
    n = display.value.num
    x = float(n.mantissa) * (10.0 ** int(n.exponent) if n.exponent else 1.0)
    return -x if n.negative else x


# (the value, as a cell holds it and as an equation defines it; the unit as a
# cell's box takes it; the same unit typed into an equation's placeholder)
CASES = [
    ((12.5, "kN"), "12.5'kN", "N^2", "'N^2"),
    ((12.5, "kN"), "12.5'kN", "kN*m", "'kN*'m"),
    ((12.5, "kN"), "12.5'kN", "m", "'m"),
    ((12.5, "kN"), "12.5'kN", "s", "'s"),
    ((12.5, "kN"), "12.5'kN", "kg", "'kg"),
    ((12.5, "kN*m"), "12.5'kN*'m", "kN", "'kN"),
    ((12.5, "kN"), "12.5'kN", "N", "'N"),
    ((12.5, "kN*m"), "12.5'kN*'m", "N*mm", "'N*'mm"),
]


@pytest.mark.parametrize("cell,typed_value,unit,keys", CASES)
def test_a_cell_shows_what_an_equation_shows_for_the_same_unit(cell, typed_value, unit, keys):
    eq, why = equation_in(typed_value, keys)
    assert why is None
    got = format_value(with_unit(*cell), None, unit)
    typed = unit.replace("*", "·")
    if eq.unit is None:
        # the same dimension: converted, the typed unit alone
        assert got.unit == typed
    else:
        # SMath's: the units it fills in, before the unit typed
        assert got.unit == _written(eq.unit) + BOX_GAP + typed
    number = float(got.text[:-len(got.unit)].strip())
    assert number == pytest.approx(number_of(eq), rel=1e-4)


def test_a_force_in_kn_with_n_squared_typed():
    eq, _why = equation_in("12.5'kN", "'N^2")
    assert display_text(eq) == "12500 s^2/kg m"          # then N², SMath's box
    got = format_value(with_unit(12.5, "kN"), None, "N^2")
    assert got.text == "12500 s^2/(kg·m)" + BOX_GAP + "N^2"
    # drawn as SMath draws it: powers raised, a gap before the typed unit
    assert unit_runs(got.unit) == [("s", False), ("2", True), ("/(kg·m) N", False), ("2", True)]


def test_matching_units_convert():
    assert format_value(with_unit(12.5, "kN"), None, "N").text == "12500 N"
    assert format_value(with_unit(12.5, "kN*m"), None, "N*mm").text == "12500000 N·mm"
    assert format_value(with_unit(250, "MPa"), None, "N/mm^2").text == "250 N/mm^2"


def test_what_smath_refuses_is_refused_in_its_words():
    force = with_unit(12.5, "kN")
    # a name that is no unit: as an equation's box says of it
    _eq, why = equation_in("12.5'kN", "frobs")
    assert why == "frobs - not defined."
    assert output_unit_refusal("frobs", force) == why
    # a temperature with an offset on a force
    _eq, why = equation_in("12.5'kN", "'°C")
    assert why == "Units don't match."
    assert output_unit_refusal("°C", force) == why
    # written wrongly; two units run together, with how to write them
    assert output_unit_refusal("kN//m", force) == "Syntax is incorrect."
    assert output_unit_refusal("Nm", force).startswith("Nm - not defined.")
    # any other unit is taken
    for unit in ("N^2", "kN*m", "m^-1", "kg", "N/m"):
        assert output_unit_refusal(unit, force) is None, unit


def test_a_stored_unit_and_the_editors_row_go_both_ways():
    from calcforge.ui.unitedit import row_unit_text, unit_row
    for unit in ("N^2", "kN*m^-1", "kN/m^2", "s^2/(kg*m)", "m^0.5", "kN/m*s", "kN", ""):
        assert row_unit_text(unit_row(unit)) == unit
    assert unit_row("kN/m^2").items[0].kind == "frac"


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.view.set_zoom(2.0)
    return window


def a_force(w):
    table = make_table(w)
    wb = table.sheet.workbook
    wb.set_input(table.sheet, 0, 0, "12.5 kN")
    w.view.tables.select((0, 0))
    settle()
    return table, wb


def open_unit_box(w, table):
    tables = w.view.tables
    tables.select((0, 0))
    settle()
    _kind, rect = table.unit_box_rect(0, 0)
    w.view.centerOn(table.mapToScene(rect.center()))
    settle()
    click(w, table.mapToScene(rect.center()))
    settle()
    box = tables._result_unit
    assert box is not None and box.isVisible()
    return box


# keys typed into a cell's unit box; an equation's unit placeholder gets the
# same keys with SMath's ' before each unit, as its unit list puts one in
R, L, U, B = Qt.Key_Right, Qt.Key_Left, Qt.Key_Up, Qt.Key_Backspace
KEYS = [
    list("N^2"),
    list("kN/m^2"),
    list("N^2") + [R] + list("*m"),
    list("kN*m^-1"),
    list("kN/m") + [B, B, B],
    list("m^2") + [L, L, R] + list("3"),
    list("kN/m") + [U] + list("*m"),
    list("kN/m^2") + [R, R] + list("*s"),
]


def _with_marks(keys):
    out, word = [], False
    for k in keys:
        letter = isinstance(k, str) and k.isalpha()
        if letter and not word:
            out.append("'")
        word = letter
        out.append(k)
    return out


def _state(editor):
    """What the unit placeholder holds, and where its cursor is."""
    from calcforge.calc.engine.model import walk_rows
    rows = list(walk_rows(editor.unit))
    where = next((k for k, r in enumerate(rows) if r is editor.row), None)
    return repr(editor.unit), where, editor.pos


def _press(widget, k):
    if isinstance(k, str):
        QTest.keyClicks(widget, k)
    else:
        QTest.keyClick(widget, k)
    settle()


def equation_states(w, keys):
    """An equation's unit placeholder typed into, key by key, in the window:
    what it holds after each key (the unit's own keys only)."""
    from tests.test_calc_modes import into_calc_mode, typed
    into_calc_mode(w, 100, 500)
    typed(w, "5=")
    _press(w.view.viewport(), R)
    item = w.view.calc.item
    assert item.region.editor.in_unit
    states = []
    for k in _with_marks(keys):
        if w.view.calc.suggestions.isVisible() and not isinstance(k, str):
            w.view.calc.hide_suggestions()
        _press(w.view.viewport(), k)
        if k != "'":
            states.append(_state(item.region.editor))
    QTest.keyClick(w.view.viewport(), Qt.Key_Escape)
    w.view.calc.leave()
    settle()
    return states


@pytest.mark.parametrize("keys", KEYS, ids=lambda keys: "".join(
    k if isinstance(k, str) else {R: "→", L: "←", U: "↑", B: "⌫"}[k] for k in keys))
def test_the_cells_unit_box_types_as_an_equations_unit_placeholder(w, keys):
    wanted = equation_states(w, keys)
    assert len(wanted) == len(keys) and wanted[-1][0] != "Row('')"
    table, wb = a_force(w)
    box = open_unit_box(w, table)
    got = []
    for k in keys:
        if box.list.isVisible() and not isinstance(k, str):
            box.list.hide()
        _press(box, k)
        got.append(_state(box.unit_editor))
    assert got == wanted
    box.list.hide()
    QTest.keyClick(box, Qt.Key_Escape)
    settle()


def test_n_squared_typed_into_the_cells_unit_box(w):
    from calcforge.calc.engine.model import Pow
    table, wb = a_force(w)
    box = open_unit_box(w, table)
    _press(box, "N")
    _press(box, "^")
    editor = box.unit_editor
    assert isinstance(editor.row.parent, Pow), "^ puts the cursor up in the exponent"
    assert "^" not in "".join(i for i in editor.unit.items if isinstance(i, str))
    assert black_slot_in(box) > 0, "SMath's black square, raised, where the power goes"
    _press(box, "2")
    assert editor.row.items == ["2"] and isinstance(editor.row.parent, Pow)
    assert box.text() == "N^2", "stored plainly"
    _press(box, R)
    assert editor.row is editor.unit, "→ comes back down"
    box.list.hide()
    QTest.keyClick(box, Qt.Key_Return)
    settle()
    assert not box.isVisible() and box.flagged() is None
    assert wb.style_of(table.sheet, 0, 0).unit == "N^2"
    assert shown(table, "A1") == "12500 s^2/(kg·m)" + BOX_GAP + "N^2"
    # opened again, it holds N with its raised 2
    box = open_unit_box(w, table)
    assert box.text() == "N^2" and isinstance(box.unit_editor.unit.items[-1], Pow)
    QTest.keyClick(box, Qt.Key_Escape)
    settle()


def black_slot_in(box) -> int:
    from tests.test_unit_filler import black_slot
    return black_slot(box)


def test_the_formula_bars_unit_box_types_as_smath_too(w):
    from calcforge.calc.engine.model import Frac
    table, wb = a_force(w)
    box = w.formula_bar.unit
    box.setFocus()
    box.selectAll()
    for k in list("kN/m^2"):
        _press(box, k)
    assert isinstance(box.unit_editor.unit.items[0], Frac), "/ makes SMath's fraction"
    assert box.text() == "kN/m^2"
    if box.completer().popup().isVisible():
        box.completer().popup().hide()
    QTest.keyClick(box, Qt.Key_Return)
    settle()
    assert wb.style_of(table.sheet, 0, 0).unit == "kN/m^2"
    # 12.5 kN in kN/m²: SMath fills in the m² before it
    assert shown(table, "A1") == "12.5 m^2" + BOX_GAP + "kN/m^2"
    # another cell, then this one again: its unit, as SMath draws it
    w.view.tables.select((1, 0))
    settle()
    w.view.tables.select((0, 0))
    settle()
    assert box.text() == "kN/m^2" and isinstance(box.unit_editor.unit.items[0], Frac)


def test_the_unit_is_kept_when_saved_and_opened_again(w, tmp_path):
    table, wb = a_force(w)
    w.view.tables.select((0, 0))
    w.view.tables.format(unit="N^2")
    w.view.tables.close()
    path = str(tmp_path / "units.pdf")
    w.document.path = path
    assert w.save_document()
    w.open_path(path)
    settle()
    from calcforge.items.table import TableItem
    (again,) = [t for t in w.view.scene().items() if isinstance(t, TableItem)]
    assert again.sheet.workbook.style_of(again.sheet, 0, 0).unit == "N^2"
    assert shown(again, "A1") == "12500 s^2/(kg·m)" + BOX_GAP + "N^2"
