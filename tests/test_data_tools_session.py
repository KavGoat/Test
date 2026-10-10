"""Every Data and Conditional Formatting tool on the table's right-click
menu, used in the real window on a beam schedule (2026-10-10): the text,
date and formula rules, the Rules Manager, a two-level sort with headings,
sorting from a filter's drop-down, Clear Filter, and Find & Replace across
tables — each one undone again."""
from __future__ import annotations

from PySide6.QtWidgets import QMenu

from calcforge.sheet import condfmt
from calcforge.sheet.dates import serial_from_date
from calcforge.ui import datatools
from tests.test_tables import make_table, pump, shown, tables, typed, w  # noqa: F401


def schedule(w):
    table = make_table(w, width=48 * 4, height=15 * 7)
    wb, s = table.sheet.workbook, table.sheet
    rows = [("Member", "Span", "Grade", "Due"),
            ("B1", "6 m", "S355", "2026-10-09"),
            ("B2", "4 m", "S275", "2026-10-10"),
            ("B3", "6 m", "S275", "2026-11-02"),
            ("C1", "3 m", "S355", "2026-10-10"),
            ("C2", "4 m", "S355", "2025-01-01")]
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            wb.set_input(s, r, c, text)
    w.view.tables.open(table, (0, 0))
    return table


def looks(table, a1_cells):
    from calcforge.sheet.refs import parse_cell
    lk = condfmt.looks_for(table.sheet)
    out = []
    for a1 in a1_cells:
        ref = parse_cell(a1)
        out.append(lk.look(ref.row, ref.col).get("format", {}).get("fill"))
    return out


def test_the_menu_holds_every_tool(w):
    schedule(w)
    menu = QMenu()
    datatools.fill_menu(menu, w.view.tables)
    titles = [a.text() for a in menu.actions()]
    assert titles[:3] == ["Conditional Formatting", "Data", "Comment"]
    data = menu.actions()[1].menu()
    labels = [a.text() for a in data.actions() if a.text()]
    assert labels == ["Sort A to Z", "Sort Z to A", "Custom Sort…", "Filter", "Clear Filter",
                      "Data Validation…", "Circle Invalid Data", "Clear Validation Circles"]
    assert not data.actions()[4].isEnabled(), "nothing filtered yet"


def test_text_date_and_formula_rules(w):
    table = schedule(w)
    tabs = w.view.tables
    tabs.select((1, 2), (5, 2))
    d = datatools.text_rule_dialog(tabs)
    d.how.setCurrentIndex(d.how.findData("ends"))
    d.text.setText("355")
    d.look.setCurrentIndex(2)                       # green
    d.accept()
    assert looks(table, ["C2", "C3", "C5"]) == ["#c6efce", None, "#c6efce"]

    today = serial_from_date(__import__("datetime").date.today())
    table.sheet.workbook.set_input(table.sheet, 2, 3, str(int(today)))
    tabs.select((1, 3), (5, 3))
    d = datatools.date_rule_dialog(tabs)
    d.when.setCurrentIndex(d.when.findData("today"))
    d.accept()
    assert looks(table, ["D3"]) == ["#ffc7ce"] and looks(table, ["D6"]) == [None]

    # a row whose span is 6 m: a formula for the top-left cell, moved down the rows
    tabs.select((1, 0), (5, 0))
    d = datatools.formula_rule_dialog(tabs)
    d.formula.setText("B2=6 m")
    d.accept()
    assert table.sheet.cond_rules[0]["formula"] == "=B2=6 m"
    assert looks(table, ["A2", "A3", "A4"]) == ["#ffc7ce", None, "#ffc7ce"]
    assert len(table.sheet.cond_rules) == 3
    for _ in range(3):
        w.undo_stack.undo()
    assert tables(w)[0].sheet.cond_rules == []


def test_rules_manager_orders_moves_and_deletes(w):
    table = schedule(w)
    tabs = w.view.tables
    tabs.select((1, 1), (5, 1))
    datatools.add_rule(tabs, {"type": "duplicate", "format": {"fill": "#ffc7ce"}})
    datatools.add_rule(tabs, {"type": "top", "n": 1, "format": {"fill": "#c6efce"}})
    m = datatools.manage_rules_dialog(tabs)
    assert m.table.rowCount() == 2
    assert m.table.cellWidget(0, 1).text() == "B2:B6"
    m.table.setCurrentCell(1, 0)
    m.move(-1)                                       # duplicates first
    m.table.cellWidget(0, 1).setText("B2:B4")        # and only over three rows
    m.table.cellWidget(0, 2).setChecked(True)
    m.accept()
    rules = tables(w)[0].sheet.cond_rules
    assert [r["type"] for r in rules] == ["duplicate", "top"]
    assert rules[0]["ranges"] == [[1, 1, 3, 1]] and rules[0]["stop"]
    assert looks(table, ["B2", "B4", "B6"]) == ["#ffc7ce", "#ffc7ce", None]
    m = datatools.manage_rules_dialog(tabs)
    m.table.setCurrentCell(0, 0)
    m.delete()
    m.accept()
    assert [r["type"] for r in tables(w)[0].sheet.cond_rules] == ["top"]
    w.undo_stack.undo()
    assert len(tables(w)[0].sheet.cond_rules) == 2


def test_two_level_sort_with_headings(w):
    table = schedule(w)
    tabs = w.view.tables
    tabs.select((0, 0))
    d = datatools.sort_dialog(tabs)
    assert d.header.isChecked(), "text over values: the first row is headings"
    assert [d.rows[0][0].itemText(i) for i in range(4)] == ["Member", "Span", "Grade", "Due"]
    d.rows[0][0].setCurrentIndex(2)                 # Grade A→Z
    d.add_level(1, ascending=False)                 # then Span, largest first
    d.accept()
    got = [(typed(table, f"A{r}"), typed(table, f"C{r}"), shown(table, f"B{r}")) for r in range(2, 7)]
    assert got == [("B3", "S275", "6 m"), ("B2", "S275", "4 m"),
                   ("B1", "S355", "6 m"), ("C2", "S355", "4 m"), ("C1", "S355", "3 m")]
    assert typed(table, "A1") == "Member", "the headings stay put"
    w.undo_stack.undo()
    assert typed(tables(w)[0], "A2") == "B1"


def test_filter_dropdown_sort_and_clear_filter(w):
    table = schedule(w)
    tabs = w.view.tables
    datatools.toggle_filter(tabs)
    d = datatools.values_dialog(tabs, 2)
    d.set_checked(["S355"])
    d.accept()
    assert table.sheet.filtered_rows == {2, 3}
    menu = datatools.filter_menu(tabs, 0, None)
    next(a for a in menu.actions() if a.text() == "Sort Z to A").trigger()
    table = tables(w)[0]
    assert [typed(table, f"A{r}") for r in range(2, 7)][:2] == ["C2", "C1"]
    assert typed(table, "A1") == "Member"
    menu = QMenu()
    datatools.fill_menu(menu, tabs)
    data = menu.actions()[1].menu()
    clear = next(a for a in data.actions() if a.text() == "Clear Filter")
    assert clear.isEnabled()
    clear.trigger()
    assert tables(w)[0].sheet.filtered_rows == set()
    assert tables(w)[0].sheet.filter is not None, "the drop-downs stay; only the criteria go"


def test_find_and_replace_across_tables(w):
    first = schedule(w)
    w.view.tables.close()
    from tests.test_tables import drag, page_to_scene
    w.insert_table()
    a, z = page_to_scene(w, 72, 300), page_to_scene(w, 216, 360)
    w.view.centerOn(a)
    drag(w.view, a.x(), a.y(), z.x(), z.y())
    pump()
    (second,) = [t for t in tables(w) if t is not first]
    second.sheet.workbook.set_input(second.sheet, 0, 0, "S275 plate")
    w.view.tables.open(first, (0, 0))
    f = datatools.find_dialog(w.view.tables)
    f.what.setText("S275")
    f.within.setCurrentIndex(1)
    assert len(f.find_all()) == 3
    f.with_.setText("S355")
    assert f.replace_all() == 3
    pump()
    a, b = sorted(tables(w), key=lambda t: t.pos().y())
    assert typed(a, "C3") == "S355" and typed(b, "A1") == "S355 plate"
    w.undo_stack.undo()
    a, b = sorted(tables(w), key=lambda t: t.pos().y())
    assert typed(a, "C3") == "S275" and typed(b, "A1") == "S275 plate", "one undo for all of it"
