"""QA round 2 (2026-10-15), through the real window: General numbers fit
their column instead of ####; var(F) reads the equations' F though a cell is
named F; errors say what went wrong (status bar and tooltip); a column or
row dragged to nothing is hidden, and comes back; =DATE() and =TODAY() show
dates."""
from __future__ import annotations

import math

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QImage, QPainter

import tests.calc.test_calcforge_window as cw
from calcforge.items.table import HEADING_H, ROWNUM_W, TableItem, _metrics
from calcforge.sheet.numfmt import format_value
from calcforge.sheet.refs import parse_cell
from calcforge.sheet.values import DIV0, NAME, Qty
from tests.test_sheet_pages import open_at, put, runs, sheet_page
from tests.test_table_equations import equation
from tests.test_tables import enter, pump, type_text
from tests.test_usability import drag


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.view.set_zoom(1.0)
    window.document.settings.show_name_tags = False
    return window


class _Recorder:
    """A painter that notes every text drawn (and draws it)."""

    def __init__(self, painter):
        self._painter = painter
        self.texts = []

    def drawText(self, *args):
        self.texts.append(args[-1])
        return self._painter.drawText(*args)

    def __getattr__(self, name):
        return getattr(self._painter, name)


def drawn(item):
    """The texts the cells draw."""
    image = QImage(1200, 1600, QImage.Format_ARGB32)
    image.fill(0xFFFFFFFF)
    painter = QPainter(image)
    rec = _Recorder(painter)
    try:
        item.paint_content(rec)
    finally:
        painter.end()
    return rec.texts


def at(a1):
    r = parse_cell(a1)
    return r.row, r.col


def status(w):
    return w.status_hint.text()


# -- 1. General fits its column ---------------------------------------------------------------
TYPED = ["=1/3", "=PI()", "=2/3*1000000", "=STDEV(1,2,3,4)", "123.456789", "=5000000000"]


def test_general_numbers_round_to_fit_the_column_instead_of_hashes(w):
    run = sheet_page(w)
    open_at(w, run, "A1")
    tabs = w.view.tables
    tabs.select((0, 1))
    tabs.set_size("col", 64)
    for i, text in enumerate(TYPED):
        put(w, run, i, 1, text)
    assert run.sheet.width(1) == 64, "a column sized by hand keeps its width"
    texts = drawn(run)
    st = run.sheet.workbook.style_of(run.sheet, 0, 1)
    metrics = _metrics(st)
    room = 64 - 2 * 2.0
    shown = [TableItem._fitted(run.sheet.value(i, 1), st, metrics, room) for i in range(6)]
    assert "#" * 3 not in "".join(texts)
    for i, text in enumerate(shown):
        value = run.sheet.value(i, 1)
        assert text in texts, (TYPED[i], text, texts)
        assert "#" not in text and metrics.horizontalAdvance(text) <= room
        # the same number, rounded: General keeps as many digits as fit
        assert math.isclose(float(text), value, rel_tol=1e-3), (text, value)
        assert len(text) < len(format_value(value).text) or TYPED[i] == "=5000000000"
    # with DejaVu Sans for Calibri (Linux) 8 characters fit, as QA saw Excel do
    digit = metrics.horizontalAdvance("0")
    if digit * 8 <= room < digit * 9:
        assert shown == ["0.333333", "3.141593", "666666.7", "1.290994", "123.4568", "5E+09"]
    # the cell keeps every digit, and the formula bar what was typed
    assert run.sheet.value(0, 1) == 1 / 3
    tabs.select((4, 1))
    assert w.formula_bar.edit.text() == "123.456789"


def test_hashes_stay_for_a_set_format_and_a_column_too_narrow(w):
    run = sheet_page(w)
    open_at(w, run, "A1")
    tabs = w.view.tables
    put(w, run, 0, 1, "=5000000000")
    put(w, run, 1, 1, "=1/3")
    put(w, run, 2, 1, "=1/3")
    wb = run.sheet.workbook
    from dataclasses import replace
    style = wb.styles.add(replace(wb.style_of(run.sheet, 2, 1), number_format="0.000000000"))
    wb.set_style(run.sheet, 2, 1, style)
    tabs.select((0, 1))
    tabs.set_size("col", 18)
    texts = drawn(run)
    assert texts.count("#") == 3, "5E+09 can't fit in 14 pt, nor 1/3 but as 0: ####"
    tabs.set_size("col", 26)
    st = wb.style_of(run.sheet, 1, 1)
    one_third = TableItem._fitted(run.sheet.value(1, 1), st, _metrics(st), 26 - 4.0)
    assert one_third == "0.3" and one_third in drawn(run)
    tabs.set_size("col", 64)
    texts = drawn(run)
    assert "5E+09" in texts and "0.333333" in texts
    assert any(set(t) == {"#"} for t in texts), "0.000000000 is a set format: ####"


def test_a_quantity_keeps_its_unit_and_loses_decimals(w):
    run = sheet_page(w)
    open_at(w, run, "A1")
    tabs = w.view.tables
    tabs.select((0, 1))
    tabs.set_size("col", 64)
    put(w, run, 0, 1, "=10 kN/3")
    value = run.sheet.value(0, 1)
    assert isinstance(value, Qty)
    texts = drawn(run)
    # the number and its blue unit are drawn as runs ("3.3333 ", "kN")
    line = "".join(texts)
    assert line.endswith("kN") and "#" not in line and line.startswith("3.33"), texts
    assert len(line) < len(format_value(value).text)
    # the unit box sits after the shortened text, not after hashes
    kind, rect = run.unit_box_rect(0, 1)
    assert kind == "box" and rect.left() < run.cell_rect(0, 1).right() + 6


# -- 2. var(F) and a cell named F ----------------------------------------------------------
def test_var_reads_the_equation_variable_though_a_cell_has_its_name(w):
    v = cw.Sheet(w)
    equation(v, 18, "F:10'kN")
    w.insert_sheet_page(0)
    pump()
    pump()
    (run,) = runs(w)
    open_at(w, run, "A1")
    tabs = w.view.tables
    put(w, run, 0, 0, "4 m")
    tabs.select((0, 0))
    tabs.bar.name.setText("F")
    tabs.bar._go()
    pump()
    assert run.sheet.workbook.find_name("F", run.sheet) is not None
    put(w, run, 1, 0, "=var(F)")
    got = run.sheet.value(1, 0)
    assert isinstance(got, Qty) and abs(got.si - 10000) < 1e-6, got
    # no such variable or name: #NAME?, said
    put(w, run, 2, 0, "=var(Span)")
    assert run.sheet.value(2, 0) == NAME
    tabs.select((2, 0))
    assert "Span" in status(w) and "#NAME?" in status(w)
    # Excel's VAR still works
    for i, x in enumerate(["1", "2", "3", "4"]):
        put(w, run, i, 3, x)
    put(w, run, 5, 3, "=VAR(D1:D4)")
    assert abs(run.sheet.value(5, 3) - 5 / 3) < 1e-12


# -- 3. errors explained ---------------------------------------------------------------------
def test_an_error_says_what_went_wrong_in_the_status_bar_and_tooltip(w):
    run = sheet_page(w)
    open_at(w, run, "A1")
    tabs = w.view.tables
    for row, text in enumerate(["5 kN", "2 m", "=A1+A2", "0", "=10/A4", "=Spna*2", "=1+",
                                '="abc"*2', "=A3*2"]):
        put(w, run, row, 0, text)
    expect = {
        2: "A3: #UNITS! — kN and m can't be added (A1 + A2)",
        4: "A5: #DIV/0! — dividing by zero (A4 is 0)",
        5: "A6: #NAME? — 'Spna' isn't a function, a defined name or a variable from the equations",
        6: "A7: #NAME? — There's a problem with this formula.",
        8: "A9: #UNITS! — from A3: kN and m can't be added (A1 + A2)",
    }
    for row, message in expect.items():
        tabs.select((0, 2))
        tabs.select((row, 0))
        assert status(w) == message
    tabs.select((7, 0))
    assert status(w).startswith("A8: #VALUE! — “abc” is text, not a number")
    # the cell still shows only the error, and the errors still compare as errors
    assert format_value(run.sheet.value(4, 0)).text == "#DIV/0!"
    assert run.sheet.value(4, 0) == DIV0
    # =1+ is taken (Excel would refuse it) and says why as it is entered
    tabs.select((9, 0))
    type_text(w, "=1+")
    enter(w)
    assert status(w) == "A10: There's a problem with this formula."
    # hovering a cell with an error shows the same as its tooltip
    tabs._hover(run, run.mapToScene(run.cell_rect(4, 0).center()))
    assert tabs.hover_tip == "#DIV/0! — dividing by zero (A4 is 0)"
    tabs._hover(run, run.mapToScene(run.cell_rect(0, 0).center()))
    assert tabs.hover_tip is None


# -- 4. a column dragged to nothing is hidden --------------------------------------------------
def _drag(w, a, b):
    drag(w.view, a.x(), a.y(), b.x(), b.y())
    pump()


def _undo(w):
    """Undo, and the run again (undo puts back the page, so a new item)."""
    w.undo_stack.undo()
    pump()
    (run,) = runs(w)
    if w.view.tables.item is not run:
        open_at(w, run, "A1")
    return run


def test_a_column_dragged_to_nothing_is_hidden_and_comes_back(w):
    run = sheet_page(w)
    open_at(w, run, "A1")
    tabs = w.view.tables
    put(w, run, 0, 1, "hello")
    width_b = run.sheet.width(1)
    tabs.select((1, 1))
    xs, _ys = run.edges()
    edge = run.mapToScene(QPointF(xs[2], -HEADING_H / 2))
    _drag(w, edge, edge - QPointF(300, 0))
    sheet = run.sheet
    assert 1 in sheet.hidden_cols and sheet.width(1) == 0
    assert sheet.widths.get(1, sheet.default_width) == width_b, "its width kept for Unhide"
    assert "hello" not in drawn(run), "a hidden column's text isn't drawn over C"
    width_a = sheet.width(0)
    # just left of the double line is column A's edge
    xs, _ys = run.edges()
    left = run.mapToScene(QPointF(xs[2] - 2.0, -HEADING_H / 2))
    _drag(w, left, left + QPointF(10, 0))
    assert abs(sheet.width(0) - (width_a + 10)) < 2 and 1 in sheet.hidden_cols
    run = _undo(w)
    sheet = run.sheet
    assert sheet.width(0) == width_a and 1 in sheet.hidden_cols
    # just right of it, B opens again
    xs, _ys = run.edges()
    right = run.mapToScene(QPointF(xs[2] + 2.0, -HEADING_H / 2))
    _drag(w, right, right + QPointF(30, 0))
    assert 1 not in sheet.hidden_cols and abs(sheet.width(1) - 30.0) < 3
    assert sheet.width(0) == width_a
    assert "hello" in drawn(run)
    # hidden again, then Unhide gives back the width it had
    run = _undo(w)
    sheet = run.sheet
    assert 1 in sheet.hidden_cols
    w.view.tables.select((0, 0), (0, 2))
    w.view.tables.hide("col", False)
    assert 1 not in sheet.hidden_cols and sheet.width(1) == width_b


def test_a_row_dragged_to_nothing_is_hidden_and_unhides(w):
    run = sheet_page(w)
    open_at(w, run, "A1")
    put(w, run, 2, 0, "x")
    height = run.sheet.height(2)
    _xs, ys = run.edges()
    edge = run.mapToScene(QPointF(-ROWNUM_W / 2, ys[3]))
    _drag(w, edge, edge - QPointF(0, 200))
    sheet = run.sheet
    assert 2 in sheet.hidden_rows and sheet.height(2) == 0
    assert "x" not in drawn(run)
    _xs, ys = run.edges()
    below = run.mapToScene(QPointF(-ROWNUM_W / 2, ys[3] + 2.0))
    _drag(w, below, below + QPointF(0, 12))
    assert 2 not in sheet.hidden_rows and abs(sheet.height(2) - 12.0) < 2
    run = _undo(w)
    sheet = run.sheet
    assert 2 in sheet.hidden_rows
    w.view.tables.select((1, 0), (3, 0))
    w.view.tables.hide("row", False)
    assert 2 not in sheet.hidden_rows and sheet.height(2) == height


# -- 5. dates from formulas ----------------------------------------------------------------
def test_a_date_formula_gives_a_general_cell_a_date_format(w):
    run = sheet_page(w)
    open_at(w, run, "A1")
    put(w, run, 0, 0, "=DATE(2026,10,15)")
    put(w, run, 1, 0, "=TODAY()")
    put(w, run, 2, 0, "=A1-DATE(2026,1,1)")
    sheet = run.sheet
    st = sheet.workbook.style_of(sheet, 0, 0)
    assert format_value(sheet.value(0, 0), st.number_format).text == "15/10/2026"
    st = sheet.workbook.style_of(sheet, 1, 0)
    assert "/" in format_value(sheet.value(1, 0), st.number_format).text
    st = sheet.workbook.style_of(sheet, 2, 0)
    assert format_value(sheet.value(2, 0), st.number_format).text == "287", "days, a number"
