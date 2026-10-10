"""Every command on an open table's right-click menu, and on a spreadsheet
page's, chosen one after another on a filled-in table the way an engineer
clicks through them (2026-10-10): none may fail, and each that changes the
table is one undo step."""
from __future__ import annotations

import sys

import pytest
from PySide6.QtWidgets import QInputDialog, QMenu

from calcforge.items.sheetpage import SheetRunItem
from tests.test_tables import make_table, pump, tables, w  # noqa: F401


def leaves(menu, path=()):
    for action in menu.actions():
        if action.isSeparator():
            continue
        if action.menu() is not None:
            yield from leaves(action.menu(), path + (action.text(),))
        else:
            yield path + (action.text(),), action


@pytest.fixture
def caught(monkeypatch):
    errors = []
    monkeypatch.setattr(sys, "excepthook", lambda *exc: errors.append(exc))
    monkeypatch.setattr(QInputDialog, "getDouble", staticmethod(lambda *a, **k: (20.0, True)))
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Loads", True)))
    menus = []

    class Recorded(QMenu):
        def exec(self, *_a):
            menus.append(self)
    monkeypatch.setattr("calcforge.ui.tableedit.QMenu", Recorded)
    return errors, menus


def fill(table):
    wb, s = table.sheet.workbook, table.sheet
    for (r, c), text in {(0, 0): "x", (0, 1): "y", (1, 0): "1", (1, 1): "2 kN",
                         (2, 0): "2", (2, 1): "=B2*2", (3, 0): "3", (3, 1): "5 kN"}.items():
        wb.set_input(s, r, c, text)


def click_through(w, item, caught, select):
    errors, menus = caught
    tabs = w.view.tables
    tabs.open(item, (1, 0))
    select(tabs)
    tabs.context_menu(None)
    (menu,) = menus
    names = [path for path, _a in leaves(menu)]
    assert len(names) > 60
    for path, _action in list(leaves(menu)):
        menus.clear()
        current = next((i for i in w.view.scene().items() if type(i) is type(item)), None)
        if tabs.item is None:
            tabs.open(current, (1, 0))
        select(tabs)
        tabs.context_menu(None)
        action = dict(leaves(menus[0]))[path]
        if not action.isEnabled():
            continue
        before = w.undo_stack.count()
        action.trigger()
        pump()
        assert not errors, f"{' ▸ '.join(path)}: {errors[0][1]!r}"
        assert w.undo_stack.count() - before <= 1, f"{' ▸ '.join(path)} took more than one undo step"
    return names


def test_every_table_command(w, caught):
    table = make_table(w, width=48 * 3, height=15 * 6)
    fill(table)
    names = click_through(w, table, caught, lambda tabs: tabs.select((1, 0), (3, 1)))
    assert ("Rename Table…",) in names and ("Insert Chart", "XY Scatter") in names
    assert w.undo_stack.count() > 20
    while w.undo_stack.canUndo():
        w.undo_stack.undo()
    pump()
    assert tables(w) == [], "everything undone, back to the empty page"


def test_every_spreadsheet_page_command(w, caught):
    w.insert_sheet_page(0)
    pump()
    (run,) = [i for i in w.view.scene().items() if isinstance(i, SheetRunItem)]
    fill(run)
    names = click_through(w, run, caught, lambda tabs: tabs.select((2, 0), (3, 1)))
    assert ("Page Layout", "Insert Page Break") in names and ("Rename Sheet…",) in names
