"""Excel's Formula AutoComplete in a table (2026-10-10): typing a formula
lists the functions, defined names and tables starting with the word typed;
Up/Down choose, Tab puts the function in with its bracket, Escape closes
the list only, Enter still enters the cell; inside brackets a tip shows the
arguments with the one being typed in bold. In the cell and in the formula
bar alike."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from calcforge.ui.formulahelp import arguments, call_at
from tests.test_tables import make_table, pump, tables, type_text, typed, value, w  # noqa: F401


def key(w, k, text="", target=None):
    QApplication.sendEvent(target or w.view.tables.editor or w.view,
                           QKeyEvent(QKeyEvent.KeyPress, k, Qt.NoModifier, text))
    pump()


def shown(h):
    return [h.list.item(i).text() for i in range(h.list.count())] if h.list.isVisible() else []


def test_arguments_read_from_the_functions():
    assert arguments("PMT") == ["rate", "nper", "pv", "[fv]", "[type]"], "Excel's names"
    assert arguments("SUMIF") == ["range", "criteria", "[sum_range]"]
    assert arguments("SUM") == ["number1", "[number2]", "…"]
    assert arguments("NOW") == []
    assert arguments("KURT") == ["value1", "[value2]", "…"], "from the function itself, in plain words"
    assert call_at('SUM(A1,IF(B1>2,"a,b",', 21) == ("IF", 2), "commas in text don't count"
    assert call_at("SUM({1,2,3},", 12) == ("SUM", 1), "nor in an array"
    assert call_at("A1+B2", 5) is None


def test_typing_lists_choosing_inserts_and_the_tip_follows(w):
    table = make_table(w)
    table.sheet.workbook.define_name("Span_main", f"{table.name}!$A$1")
    tabs = w.view.tables
    for r, v in ((0, "2"), (1, "3"), (2, "4")):
        table.sheet.workbook.set_input(table.sheet, r, 0, v)
    tabs.select((3, 1))
    type_text(w, "=su")
    h = tabs.help
    assert shown(h)[:3] == ["SUBSTITUTE", "SUBTOTAL", "SUM"]
    key(w, Qt.Key_Down)
    key(w, Qt.Key_Down)
    key(w, Qt.Key_Tab)
    assert tabs.editor.text() == "=SUM(" and not h.list.isVisible(), "Tab took SUM, not the next cell"
    assert h.tip.isVisible() and "<b>number1</b>" in h.tip.text()
    type_text(w, "A1:A3,sp")
    assert shown(h) == ["Span_main"] and "<b>[number2]</b>" in h.tip.text()
    key(w, Qt.Key_Escape)
    assert not h.list.isVisible() and tabs.editor is not None, "Escape closed the list only"
    type_text(w, "an_main)")
    assert not h.tip.isVisible(), "out of the brackets: no tip"
    key(w, Qt.Key_Return)
    assert value(tables(w)[0], "B4") == 2 + 3 + 4 + 2
    assert not h.list.isVisible() and not h.tip.isVisible()


def test_nothing_offered_in_text_numbers_or_plain_entries(w):
    make_table(w)
    tabs = w.view.tables
    tabs.select((0, 0))
    type_text(w, "su")
    assert shown(tabs.help) == [], "not a formula"
    key(w, Qt.Key_Escape)
    type_text(w, '="su')
    assert shown(tabs.help) == [], "inside quotes"
    key(w, Qt.Key_Escape)
    type_text(w, "=A1+12")
    assert shown(tabs.help) == []


def test_the_formula_bar_offers_the_same(w):
    make_table(w)
    tabs = w.view.tables
    tabs.select((0, 0))
    bar = tabs.bar.edit
    bar.setFocus()
    pump()
    for ch in "=avera":
        QApplication.sendEvent(bar, QKeyEvent(QKeyEvent.KeyPress, 0, Qt.NoModifier, ch))
        pump()
    assert shown(tabs.help)[:2] == ["AVERAGE", "AVERAGEA"]
    key(w, Qt.Key_Tab, target=bar)
    assert bar.text() == "=AVERAGE(" and tabs.editor.text() == "=AVERAGE("
    assert typed(tables(w)[0], "A1") == ""


def test_a_function_without_arguments_has_a_tip_too(w):
    make_table(w)
    w.view.tables.select((0, 0))
    type_text(w, "=NOW(")
    assert w.view.tables.help.tip.text() == "NOW()"
