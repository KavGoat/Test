"""A spreadsheet's names coloured while a formula is typed, as Excel colours
its references (the user, 2026-10-22: "do cell highlight in formula edit
mode for named cells, like how A2 would be highlighted a colour if A2 is
referenced — do the same for named cells (not variable cells)").

The name in the formula's text takes a colour, and its cells are outlined
in the same colour, in turn with the cell references; a CalcForge variable
(a cell named with its Variable box) is neither.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from calcforge.ui.tableedit import REF_COLOURS
from tests.test_tables import cell_scene, click, make_table, type_text


def pump():
    for _ in range(4):
        QApplication.instance().processEvents()


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.view.set_zoom(2.0)
    return window


def named_sheet(w):
    """A1:A3 named loads with the Name Box (the spreadsheet's own), B1
    named P with its Variable box (a CalcForge variable)."""
    table = make_table(w, width=48 * 4, height=15 * 5)
    tables = w.view.tables
    wb = table.sheet.workbook
    for row, text in enumerate(("10", "20", "30")):
        wb.set_input(table.sheet, row, 0, text)
    wb.set_input(table.sheet, 0, 1, "5")
    click(w, cell_scene(table, "A1"))
    tables.select((0, 0), (2, 0))
    box = w.formula_bar.name
    QTest.mouseClick(box, Qt.LeftButton, Qt.NoModifier, QPoint(10, box.height() // 2))
    box.selectAll()
    QTest.keyClicks(box, "loads")
    QTest.keyClick(box, Qt.Key_Return)
    pump()
    tables.select((0, 1))
    assert tables.name_selection("P")
    assert not wb.names[("loads", None)].variable and wb.names[("p", None)].variable
    return table


def colour_in(image, colour: str, rect=None) -> int:
    want = QColor(colour)
    n = 0
    left, top, right, bottom = (0, 0, image.width(), image.height()) if rect is None else \
        (max(0, rect.left()), max(0, rect.top()), min(image.width(), rect.right()),
         min(image.height(), rect.bottom()))
    for x in range(left, right):
        for y in range(top, bottom):
            c = image.pixelColor(x, y)
            if abs(c.red() - want.red()) < 40 and abs(c.green() - want.green()) < 40 and \
                    abs(c.blue() - want.blue()) < 40:
                n += 1
    return n


def test_a_named_range_is_coloured_and_outlined_as_a_reference(w):
    table = named_sheet(w)
    tables = w.view.tables
    w.view.set_zoom(4.0)
    w.view.centerOn(cell_scene(table, "B2"))
    pump()
    click(w, cell_scene(table, "C2"))
    type_text(w, "=SUM(loads)+A2+P")
    pump()
    editor = tables.editor
    assert editor is not None and editor.text() == "=SUM(loads)+A2+P"
    marks = tables.formula_marks(editor.text())
    # loads first, in the first colour, outlining A1:A3; then A2; P is not one
    assert [(editor.text()[a:b], colour, block) for a, b, colour, block in marks] == [
        ("loads", REF_COLOURS[0], (0, 0, 2, 0)), ("A2", REF_COLOURS[1], (1, 0, 1, 0))]
    # the outline on the cells, in the name's colour
    w.view.centerOn(cell_scene(table, "A2"))
    pump()
    image = w.view.viewport().grab().toImage()
    block = w.view.mapFromScene(table.mapToScene(table.block_rect(0, 0, 2, 0))).boundingRect()
    assert colour_in(image, REF_COLOURS[0], block.adjusted(-3, -3, 3, 3)) > 40
    # and the name in the formula's text, in the same colour (the cell's box
    # and the formula bar alike)
    assert colour_in(editor.grab().toImage(), REF_COLOURS[0]) > 10
    assert colour_in(w.formula_bar.edit.grab().toImage(), REF_COLOURS[0]) > 10
    tables.cancel()
    pump()


def test_a_name_of_another_sheet_is_coloured_and_a_variable_is_not(w):
    table = named_sheet(w)
    tables = w.view.tables
    click(w, cell_scene(table, "C3"))
    type_text(w, "=P*2")
    pump()
    assert tables.formula_marks(tables.editor.text()) == [], "a CalcForge variable: no colour"
    tables.cancel()
    pump()
    click(w, cell_scene(table, "C3"))
    type_text(w, f"={table.name}!loads")
    pump()
    marks = tables.formula_marks(tables.editor.text())
    assert [(colour, block) for _a, _b, colour, block in marks] == [(REF_COLOURS[0], (0, 0, 2, 0))]
    tables.cancel()
    pump()
