"""SMath's filler in a cell's unit boxes (the user, 2026-10-19: "spreadsheet
custom unit entry for a cell does not have the filler unit like smath
(currently says wrong unit)").

As in SMath's unit box, in the three places a cell's unit is typed — the
formula bar's unit box, the unit box after the selected cell's result and
Format Cells' "Show quantities in" — an empty or unfinished unit shows
SMath's black placeholder (drawn as the equations draw theirs), nothing is
said while it is typed, and only a finished unit that is refused is flagged:
drawn in SMath's error red, with why.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QToolTip

from calcforge.ui.cellunits import box_at, unit_slot
from tests.test_tables import click, make_table


def settle():
    for _ in range(4):
        QApplication.instance().processEvents()


def inked(box, colour, left=0, right=None) -> int:
    """Pixels of *colour* (within a few levels) drawn in *box*, between x
    *left* and *right*."""
    image = box.grab().toImage()
    right = image.width() if right is None else right
    want = QColor(colour)
    n = 0
    for x in range(max(0, left), min(image.width(), right)):
        for y in range(image.height()):
            c = image.pixelColor(x, y)
            if abs(c.red() - want.red()) < 40 and abs(c.green() - want.green()) < 40 and \
                    abs(c.blue() - want.blue()) < 40:
                n += 1
    return n


def black_slot(box) -> int:
    """Pixels of SMath's placeholder (black; a dark theme's text colour on
    a dark box), where unit_slot puts it."""
    from calcforge.ui.cellunits import x_of
    at = unit_slot(box.text())
    if at is None:
        at = len(box.text())       # where it would be: nothing drawn there
    x = int(x_of(box, at))
    return inked(box, box.slot_colour().name(), x + 3, x + 18)     # past the caret


def red(box) -> int:
    return inked(box, "#ff0000", 0, None)


def a_force_cell(w):
    w.show()
    w.view.set_zoom(2.0)
    table = make_table(w)
    wb = table.sheet.workbook
    wb.set_input(table.sheet, 0, 0, "12.5 kN")
    w.view.tables.select((0, 0))
    settle()
    return table, wb


def test_where_smaths_placeholder_goes():
    # a box holding only a unit: empty, or ending where more must come
    assert unit_slot("") == 0 and unit_slot("  ") == 0
    assert unit_slot("kN/") == 3 and unit_slot("kN*") == 3 and unit_slot("m^") == 2
    assert unit_slot("kN") is None and unit_slot("kN/m") is None and unit_slot("frobs") is None
    # a cell's own entry: after a number alone, after SMath's apostrophe,
    # after a unit's operator
    assert box_at("5") == 1 and box_at("5'") == 2 and box_at("5 kN/") == 5
    assert box_at("=B2*5'") == 6
    assert box_at("5 kN") is None and box_at("5 k") is None
    assert box_at("='Sheet") is None, "a sheet's name in quotes is no unit"
    assert box_at('="5\'') is None, "nor an apostrophe in a string"


def test_the_formula_bars_unit_box(window):
    w = window
    table, wb = a_force_cell(w)
    box = w.formula_bar.unit
    hint = w.status_hint.text()
    # empty: SMath's black placeholder, focused or not
    assert box.text() == "" and black_slot(box) > 6
    box.setFocus()
    settle()
    assert black_slot(box) > 6, "still there with the caret in it"
    # typed key by key: never flagged, never a word said; the placeholder
    # while the unit is unfinished
    for ch in "kN/":
        QTest.keyClick(box, ch)
        settle()
        assert box.flagged() is None and red(box) == 0, box.text()
        assert w.status_hint.text() == hint
        assert not QToolTip.isVisible()
    assert black_slot(box) > 6, "kN/ waits for more: the placeholder after it"
    QTest.keyClick(box, Qt.Key_Backspace)
    settle()
    assert box.text() == "kN" and black_slot(box) == 0
    # a finished unit of the cell's kind is taken
    if box.completer().popup().isVisible():
        box.completer().popup().hide()
    QTest.keyClick(box, Qt.Key_Return)
    settle()
    assert wb.style_of(table.sheet, 0, 0).unit == "kN" and box.flagged() is None
    # a finished unit that is not one is flagged red, with why, and not taken
    box.setFocus()
    box.selectAll()
    for ch in "frobs":
        QTest.keyClick(box, ch)
        settle()
        assert box.flagged() is None and red(box) == 0
    if box.completer().popup().isVisible():
        box.completer().popup().hide()
    QTest.keyClick(box, Qt.Key_Return)
    settle()
    assert box.flagged() == "frobs - not defined.", "as SMath says it"
    assert box.text() == "frobs" and red(box) > 10, "drawn in SMath's error red"
    assert w.status_hint.text() == "frobs - not defined."
    assert wb.style_of(table.sheet, 0, 0).unit == "kN", "the cell keeps its unit"
    # typed into again: no longer red
    QTest.keyClick(box, Qt.Key_Backspace)
    settle()
    assert box.flagged() is None and red(box) == 0
    # another cell picked: its own unit, nothing flagged
    box.setText("frobs")
    box.flag("x")
    w.view.tables.select((1, 0))
    settle()
    assert box.flagged() is None and box.text() == ""


def _open_result_unit(w, table):
    tables = w.view.tables
    tables.select((0, 0))
    settle()
    kind, rect = table.unit_box_rect(0, 0)
    w.view.centerOn(table.mapToScene(rect.center()))
    settle()
    click(w, table.mapToScene(rect.center()))
    settle()
    box = tables._result_unit
    assert box is not None and box.isVisible()
    return box


def test_the_unit_box_after_the_cells_result(window):
    w = window
    table, wb = a_force_cell(w)
    box = _open_result_unit(w, table)
    hint = w.status_hint.text()
    assert box.text() == "" and black_slot(box) > 6, "empty: SMath's placeholder"
    for ch in "kN":
        QTest.keyClick(box, ch)
        settle()
        assert box.isVisible() and box.flagged() is None and red(box) == 0
        assert w.status_hint.text() == hint
    box.list.hide()
    QTest.keyClick(box, Qt.Key_Return)
    settle()
    assert not box.isVisible() and wb.style_of(table.sheet, 0, 0).unit == "kN"
    # a finished name that is no unit: kept in the box in red, with why
    box = _open_result_unit(w, table)
    box.selectAll()
    for ch in "kNxyz":
        QTest.keyClick(box, ch)
        settle()
        assert box.flagged() is None
    box.list.hide()
    QTest.keyClick(box, Qt.Key_Return)
    settle()
    assert box.isVisible() and box.flagged() == "kNxyz - not defined."
    assert red(box) > 10
    assert w.status_hint.text() == box.flagged()
    assert wb.style_of(table.sheet, 0, 0).unit == "kN"
    # put right, it is taken
    for _ in range(3):
        QTest.keyClick(box, Qt.Key_Backspace)
        settle()
    assert box.flagged() is None and box.text() == "kN"
    assert black_slot(box) == 0
    QTest.keyClick(box, Qt.Key_Backspace)
    QTest.keyClick(box, Qt.Key_Backspace)
    settle()
    for ch in "N":
        QTest.keyClick(box, ch)
    settle()
    box.list.hide()
    QTest.keyClick(box, Qt.Key_Return)
    settle()
    assert not box.isVisible() and wb.style_of(table.sheet, 0, 0).unit == "N"
    # Esc leaves it as it was, even when red
    box = _open_result_unit(w, table)
    box.setText("frobs")
    QTest.keyClick(box, Qt.Key_Return)
    settle()
    assert box.flagged()
    QTest.keyClick(box, Qt.Key_Escape)
    settle()
    assert not box.isVisible() and wb.style_of(table.sheet, 0, 0).unit == "N"


def test_format_cells_show_quantities_in(window):
    w = window
    table, wb = a_force_cell(w)
    QTest.keyClick(w.view, Qt.Key_1, Qt.ControlModifier)
    settle()
    dialog = w._last_format_dialog
    dialog.show()
    settle()
    field = dialog.unit
    assert field.text() == "" and black_slot(field) > 6, "empty: SMath's placeholder"
    assert "blank: as typed" in field.toolTip()
    field.setFocus()
    settle()
    # "k" alone is a unit of another kind (Boltzmann's): nothing said while typed
    for ch in "kN/":
        QTest.keyClick(field, ch)
        settle()
        assert field.flagged() is None and red(field) == 0, field.text()
    assert black_slot(field) > 6
    QTest.keyClick(field, Qt.Key_Backspace)
    settle()
    assert dialog.sample.text().replace(" ", " ").startswith("12.5")
    # finished (Tab on) as a name that is no unit: red, with why
    field.setText("frobs")
    field.editingFinished.emit()
    settle()
    assert field.flagged() == "frobs - not defined."
    assert field.toolTip() == field.flagged() and red(field) > 10
    assert dialog.changes().get("unit") in (None, "") or "unit" not in dialog.changes()
    # typed into again: not red; a good unit goes in
    field.selectAll()
    for ch in "MN":
        QTest.keyClick(field, ch)
    settle()
    assert field.flagged() is None and "blank: as typed" in field.toolTip()
    field.editingFinished.emit()
    assert field.flagged() is None
    assert dialog.changes()["unit"] == "MN"
    dialog.reject()
