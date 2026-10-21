"""Units in cells drawn as an equation draws them, and kept as the equation
shows them (the user, 2026-10-15):

* a variable read from the equations keeps the unit its equation shows
  (=M is 35 kN·m, not 35000 J), and arithmetic on it goes on in that unit;
* once entered, a cell's unit is drawn in SMath's unit blue, its powers
  raised (m², m⁻¹), products with a dot (kN·m) — on screen and on paper
  alike; what is stored, copied and pasted into Excel stays plain text;
* an output unit of another kind than the value (kN on a moment) is taken as
  SMath takes it (the units still needed before it); a non-unit (Nm) is
  refused with SMath's reason on the status bar.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QKeyEvent, QPainter
from PySide6.QtWidgets import QApplication

from calcforge.sheet.numfmt import format_value, unit_display, unit_runs
from calcforge.sheet.values import Qty
from tests.test_calc_panels import an_equation
from tests.test_sheet_pages import open_at, paper, put, sheet_page
from tests.test_tables import click, make_table, pump, shown

BLUE = QColor("#0000ff")


def _is_blue(c: QColor) -> bool:
    # anti-aliased edges blend with the white paper: blue clearly ahead
    return c.blue() > 150 and c.red() < 110 and c.green() < 110


def _is_dark(c: QColor) -> bool:
    return c.red() < 90 and c.green() < 90 and c.blue() < 90


def _drawn(item, scale=4.0) -> QImage:
    """The item's cells drawn on white, *scale* pixels to the point."""
    rect = item.boundingRect()
    image = QImage(int(rect.width() * scale) + 2, int(rect.height() * scale) + 2,
                   QImage.Format_RGB32)
    image.fill(0xFFFFFFFF)
    painter = QPainter(image)
    painter.scale(scale, scale)
    painter.translate(-rect.left(), -rect.top())
    item.paint(painter, None, None)
    painter.end()
    return image


def _pixels(image, rect: QRectF, scale, origin, test) -> list:
    """Pixels inside the cell *rect* (within its borders) passing *test*."""
    rect = rect.adjusted(1.5, 1.5, -1.5, -1.5)
    out = []
    for x in range(int((rect.left() - origin.x()) * scale), int((rect.right() - origin.x()) * scale)):
        for y in range(int((rect.top() - origin.y()) * scale), int((rect.bottom() - origin.y()) * scale)):
            if 0 <= x < image.width() and 0 <= y < image.height() and test(image.pixelColor(x, y)):
                out.append((x, y))
    return out


def _wide_table(w, tall=False):
    table = make_table(w)
    wb = table.sheet.workbook
    wb.set_widths(table.sheet, [0], 150.0)
    if tall:
        wb.set_heights(table.sheet, [0, 1, 2], 80.0)
    pump()
    return table


# -- equation variables keep the equation's unit ----------------------------------------------------

def test_an_equation_variable_shows_in_the_unit_its_equation_shows(window):
    w = window
    w.show()
    w.activateWindow()
    w.view.setFocus()
    y = 120
    for text in ("F:10'kN", "L:3.5'm", "M:F*L", "q:5'kN/'m", "A:q*L", "s:F/(2'm^2)"):
        an_equation(w, text, 100, y)
        y += 30
    w.toggle_calc_mode(False)
    run = sheet_page(w, 0)
    open_at(w, run, "A1")
    for i, formula in enumerate(["=M", "=F", "=s", "=A", "=F*2", "=10 kN*3.5 m"]):
        put(w, run, i, 0, formula)
    pump()
    assert [shown(run, f"A{i}") for i in range(1, 7)] == [
        "35 kN·m", "10 kN", "5 kPa", "17.5 kN", "20 kN", "35 kN·m"]
    m = run.sheet.cells[(0, 0)].value
    assert isinstance(m, Qty) and m.si == 35000.0 and m.unit == "kN·m"
    # =F*2 follows the rule a typed 10 kN*2 does: the operand's unit
    assert run.sheet.cells[(4, 0)].value.unit == "kN"


def test_from_engine_picks_the_equations_unit():
    from calcforge.calc.engine.units import Quantity
    from calcforge.calc.engine.values import Matrix
    from calcforge.sheet.evaluate import from_engine
    from calcforge.sheet.values import Array

    moment = (2, 1, -2) + (0,) * 8
    assert from_engine(Quantity(35000.0, moment)).unit == "kN·m"
    assert from_engine(Quantity(2.5e8, (-1, 1, -2) + (0,) * 8)).unit == "MPa"
    assert from_engine(Quantity(35000.0, moment), engineering=False).unit == "J"
    got = from_engine(Matrix(1, 2, [Quantity(5000.0, (1, 1, -2) + (0,) * 8),
                                    Quantity(5.0, (1, 1, -2) + (0,) * 8)]))
    assert isinstance(got, Array) and [v.unit for v in got.values()] == ["kN", "N"]
    # a unit with two parts under the line reads back as written
    viscosity = (-1, 1, -1) + (0,) * 8
    q = from_engine(Quantity(3.0, viscosity))
    assert format_value(q).text.startswith("3 ")


# -- drawn as an equation draws it --------------------------------------------------------------

def test_powers_are_raised_and_products_dotted():
    assert unit_runs("kN/m^2") == [("kN/m", False), ("2", True)]
    assert unit_runs("kN*m^2") == [("kN·m", False), ("2", True)]
    assert unit_runs("m^-1") == [("m", False), ("−1", True)]
    assert unit_runs("kg m/s^2") == [("kg·m/s", False), ("2", True)]
    assert unit_runs("m²") == [("m", False), ("2", True)]
    assert unit_display("kN/m^2") == "kN/m²" and unit_display("m^-1") == "m⁻¹"


def test_a_cells_unit_is_drawn_blue_with_a_raised_power(window):
    w = window
    w.show()
    table = _wide_table(w)
    wb = table.sheet.workbook
    wb.set_input(table.sheet, 0, 0, "3 kN/m^2")
    wb.set_input(table.sheet, 1, 0, "12")
    wb.set_input(table.sheet, 2, 0, "5 kN*m")
    pump()
    from calcforge.items.table import Drawn, cell_font
    st = wb.style_of(table.sheet, 0, 0)
    got = format_value(table.sheet.value(0, 0), st.number_format, st.unit)
    assert got.text == "3 kN/m^2" and got.unit == "kN/m^2", "the text stays plain"
    line = Drawn(got.text, got.unit, cell_font(st))
    assert line.runs == [("3 ", ""), ("kN/m", "unit"), ("2", "sup")], "m^2 is drawn as m²"
    assert shown(table, "A3") == "5 kN·m"
    scale = 4.0
    image = _drawn(table, scale)
    origin = table.boundingRect().topLeft()
    cell = table.cell_rect(0, 0)
    # the number in black, the unit in blue, right-aligned in the cell
    blue = _pixels(image, cell, scale, origin, _is_blue)
    dark = _pixels(image, cell, scale, origin, _is_dark)
    assert blue and dark, "a blue unit after a black number"
    assert min(x for x, _ in blue) > max(x for x, _ in dark), "the unit after the number"
    # the power: blue ink higher up than the top of the unit's letters
    letters = [p for p in blue if p[0] < max(x for x, _ in blue) - 3 * scale]
    power = [p for p in blue if p[0] >= max(x for x, _ in blue) - 2 * scale]
    assert min(y for _, y in power) < min(y for _, y in letters), "raised"
    # a plain number has no blue
    assert not _pixels(image, table.cell_rect(1, 0), scale, origin, _is_blue)


def test_printed_cells_look_as_on_screen(window):
    w = window
    w.show()
    w.document.settings.show_name_tags = False
    run = sheet_page(w, 0)
    wb = run.sheet.workbook
    wb.set_widths(run.sheet, [0], 150.0)
    wb.set_input(run.sheet, 0, 0, "3 kN/m^2")
    pump()
    frame = w.document.pages[1].frame
    image = paper(frame, 3.0)
    assert any(_is_blue(image.pixelColor(x, y)) for x in range(0, image.width() // 2, 1)
               for y in range(0, image.height() // 4, 1)), "the unit prints blue"


def test_the_unit_box_sits_on_the_drawn_unit(window):
    w = window
    w.show()
    table = _wide_table(w)
    wb = table.sheet.workbook
    wb.set_input(table.sheet, 0, 0, "31.25 kN*m^2")
    w.view.tables.select((0, 0))
    w.view.tables.format(unit="kN*m^2")
    pump()
    kind, rect = table.unit_box_rect(0, 0)
    assert kind == "unit"
    scale = 4.0
    image = _drawn(table, scale)
    origin = table.boundingRect().topLeft()
    blue = _pixels(image, table.cell_rect(0, 0), scale, origin, _is_blue)
    xs = [x / scale + origin.x() for x, _ in blue]
    assert rect.left() - 1 <= min(xs) and max(xs) <= rect.right() + 1, "over the blue unit"
    assert rect.left() > table.cell_rect(0, 0).left() + 10, "not over the number"


def test_hashes_measure_the_drawn_unit(window):
    w = window
    w.show()
    table = make_table(w)
    wb = table.sheet.workbook
    wb.set_input(table.sheet, 0, 0, "123456 kN/m^2")
    pump()
    image = _drawn(table, 4.0)
    assert not _pixels(image, table.cell_rect(0, 0), 4.0, table.boundingRect().topLeft(), _is_blue), \
        "#### has no unit"


def test_turned_wrapped_and_shrunk_cells_keep_the_blue_unit(window):
    w = window
    w.show()
    table = _wide_table(w, tall=True)
    wb = table.sheet.workbook
    tables = w.view.tables
    for row, fields in enumerate(({"rotation": 90}, {"wrap": True}, {"shrink": True})):
        wb.set_input(table.sheet, row, 0, "31.25 kN*m^2")
        tables.select((row, 0))
        tables.format(**fields)
    pump()
    image = _drawn(table, 4.0)
    origin = table.boundingRect().topLeft()
    for row in range(3):
        assert _pixels(image, table.cell_rect(row, 0), 4.0, origin, _is_blue), f"row {row + 1}"


def test_copied_text_keeps_the_unit_plain(window):
    from calcforge.sheet.clip import as_text
    w = window
    w.show()
    table = make_table(w)
    wb = table.sheet.workbook
    wb.set_input(table.sheet, 0, 0, "3 kN/m^2")
    assert as_text(table.sheet, 0, 0, 0, 0).strip() == "3 kN/m^2"


# -- an output unit of another kind is refused ---------------------------------------------------

def _type_into_result_unit(w, table, text):
    tables = w.view.tables
    kind, rect = table.unit_box_rect(0, 0)
    w.view.centerOn(table.mapToScene(rect.center()))
    pump()
    click(w, table.mapToScene(rect.center()))
    box = tables._result_unit
    assert box is not None and box.isVisible()
    box.setText(text)
    QApplication.sendEvent(box, QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))
    pump()


def test_an_output_unit_of_another_kind_is_filled_in_as_smath(window):
    w = window
    w.show()
    w.view.set_zoom(2.0)
    table = make_table(w)
    wb = table.sheet.workbook
    wb.set_input(table.sheet, 0, 0, "12.5 kN*m")
    w.view.tables.select((0, 0))
    pump()
    # kN on a moment: SMath puts the missing m before the kN typed
    _type_into_result_unit(w, table, "kN")
    assert wb.style_of(table.sheet, 0, 0).unit == "kN"
    assert shown(table, "A1") == "12.5 m\u2009kN"
    _type_into_result_unit(w, table, "Nm")
    assert wb.style_of(table.sheet, 0, 0).unit == "kN", "a non-unit is not taken"
    assert w.status_hint.text() == "Nm - not defined. For N times m write N*m (shown N·m)"
    # a force typed later: the kN converts
    wb.set_input(table.sheet, 0, 0, "3000 N")
    pump()
    assert shown(table, "A1") == "3 kN"
    # a unit of the same kind converts
    wb.set_input(table.sheet, 0, 0, "12.5 kN*m")
    pump()
    _type_into_result_unit(w, table, "N*m")
    assert wb.style_of(table.sheet, 0, 0).unit == "N*m"
    assert shown(table, "A1") == "12500 N·m"


def test_the_formula_bars_unit_box_takes_it_too(window):
    w = window
    w.show()
    table = make_table(w)
    wb = table.sheet.workbook
    wb.set_input(table.sheet, 0, 0, "12.5 kN*m")
    tables = w.view.tables
    tables.select((0, 0))
    pump()
    box = w.formula_bar.unit
    box.setText("kN")
    box.editingFinished.emit()
    pump()
    assert wb.style_of(table.sheet, 0, 0).unit == "kN"
    assert shown(table, "A1") == "12.5 m\u2009kN"
    # as SMath (the user, 2026-10-19): a name that is no unit stays, in red,
    # to be put right — the cell keeps the unit it has
    box.setText("frobs")
    box.editingFinished.emit()
    pump()
    assert w.status_hint.text() == "frobs - not defined."
    assert box.text() == "frobs" and box.flagged() == w.status_hint.text()
    assert wb.style_of(table.sheet, 0, 0).unit == "kN"
    box.setText("kN*m")
    assert box.flagged() is None
    box.editingFinished.emit()
    pump()
    assert wb.style_of(table.sheet, 0, 0).unit == "kN*m"
