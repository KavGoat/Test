"""An open table driven from the keyboard alone, with Excel's shortcuts
(2026-10-10): moving and selecting (Home, Ctrl+Home, Ctrl+End, PageDown,
Ctrl/Shift+Space, Shift+Tab, Shift+Enter), Backspace and F2, Ctrl+D and
Ctrl+R, Alt+= AutoSum, Ctrl+; today's date, Ctrl+B/I/U/5, Ctrl+9 and
Ctrl+0 to hide, Ctrl+- and Ctrl++ to delete and insert, Ctrl+Z/Y, Ctrl+1,
Ctrl+F, Ctrl+F3 and Shift+F2."""
from __future__ import annotations

import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from tests.test_tables import enter, make_table, pump, tables, type_text, typed, value, w  # noqa: F401

CTRL, SHIFT, ALT = Qt.ControlModifier, Qt.ShiftModifier, Qt.AltModifier


def key(w, k, text="", mods=Qt.NoModifier):
    """A key press where the keyboard sends it: the cell editor while one is open."""
    QApplication.sendEvent(w.view.tables.editor or w.view, QKeyEvent(QKeyEvent.KeyPress, k, mods, text))
    pump()


def loads(w):
    table = make_table(w, width=48 * 4, height=15 * 6)
    w.view.tables.select((0, 0))
    for row in (("1", "2", "3"), ("4", "5", "6"), ("7", "8", "9")):
        for text in row:
            type_text(w, text)
            key(w, Qt.Key_Tab)
        enter(w)
    return table


def test_moving_and_selecting(w):
    loads(w)
    tabs = w.view.tables
    tabs.select((2, 2))
    key(w, Qt.Key_Home)
    assert tabs.active == (2, 0)
    key(w, Qt.Key_End, mods=CTRL)
    assert tabs.active == (5, 3), "the last cell used, borders included (Excel)"
    key(w, Qt.Key_Home, mods=CTRL)
    assert tabs.active == (0, 0)
    key(w, Qt.Key_Right, mods=CTRL)
    assert tabs.active == (0, 2), "Ctrl+→ to the edge of the data"
    key(w, Qt.Key_Down, mods=CTRL | SHIFT)
    assert tabs.selection() == (0, 2, 2, 2)
    key(w, Qt.Key_Space, mods=CTRL)
    assert tabs.selection()[1::2] == (2, 2) and tabs.selection()[0] == 0, "the whole column"
    tabs.select((1, 1))
    key(w, Qt.Key_Space, " ", SHIFT)
    assert tabs.selection() == (1, 0, 1, 3), "the whole row"
    tabs.select((1, 1))
    key(w, Qt.Key_Backtab, mods=SHIFT)
    assert tabs.active == (1, 0)
    key(w, Qt.Key_Return, mods=SHIFT)
    assert tabs.active == (0, 0), "Shift+Enter goes up"
    key(w, Qt.Key_PageDown)
    assert tabs.active[0] > 1 and tabs.active[1] == 0
    key(w, Qt.Key_A, mods=CTRL)
    assert tabs.selection() == (0, 0, 5, 3)


def test_editing_keys(w):
    table = loads(w)
    tabs = w.view.tables
    tabs.select((0, 0))
    key(w, Qt.Key_Backspace)
    assert tabs.editor is not None and tabs.editor.text() == ""
    type_text(w, "10")
    enter(w)
    assert value(tables(w)[0], "A1") == 10
    tabs.select((1, 1))
    key(w, Qt.Key_F2)
    assert tabs.editor.text() == "5" and not tabs.enter_mode, "F2 edits what is there"
    type_text(w, "0")
    enter(w)
    assert value(tables(w)[0], "B2") == 50
    # Ctrl+D copies the top row of the selection down; Ctrl+R the left column across
    tabs.select((0, 0), (2, 0))
    key(w, Qt.Key_D, mods=CTRL)
    assert [value(tables(w)[0], a) for a in ("A2", "A3")] == [10, 10]
    tabs.select((0, 0), (0, 2))
    key(w, Qt.Key_R, mods=CTRL)
    assert value(tables(w)[0], "C1") == 10
    # Alt+= sums the numbers above
    tabs.select((3, 1))
    key(w, Qt.Key_Equal, "=", ALT)
    assert tabs.editor.text() == "=SUM(B1:B3)"
    enter(w)
    assert value(tables(w)[0], "B4") == 10 + 50 + 8      # B1 got 10 from Ctrl+R
    # Ctrl+; today's date
    tabs.select((4, 0))
    key(w, Qt.Key_Semicolon, ";", CTRL)
    assert tabs.editor.text() == datetime.date.today().isoformat()
    key(w, Qt.Key_Escape)
    assert typed(tables(w)[0], "A5") == ""
    del table


def test_format_hide_insert_delete_and_undo(w):
    loads(w)
    tabs = w.view.tables
    tabs.select((0, 0), (0, 1))
    for k in (Qt.Key_B, Qt.Key_I, Qt.Key_U, Qt.Key_5):
        key(w, k, mods=CTRL)
    table = tables(w)[0]
    st = table.sheet.workbook.style_of(table.sheet, 0, 1)
    assert st.bold and st.italic and st.underline and st.strike
    key(w, Qt.Key_B, mods=CTRL)
    assert not tables(w)[0].sheet.workbook.style_of(tables(w)[0].sheet, 0, 0).bold
    # Ctrl+9 hides the rows, Ctrl+Shift+9 brings them back
    tabs.select((1, 0))
    key(w, Qt.Key_9, mods=CTRL)
    assert 1 in tables(w)[0].sheet.hidden_rows
    tabs.select((0, 0), (2, 0))
    key(w, Qt.Key_9, mods=CTRL | SHIFT)
    assert 1 not in tables(w)[0].sheet.hidden_rows
    tabs.select((0, 1))
    key(w, Qt.Key_0, mods=CTRL)
    assert 1 in tables(w)[0].sheet.hidden_cols
    key(w, Qt.Key_Z, mods=CTRL)
    assert 1 not in tables(w)[0].sheet.hidden_cols
    key(w, Qt.Key_Y, mods=CTRL)
    assert 1 in tables(w)[0].sheet.hidden_cols
    key(w, Qt.Key_Z, mods=CTRL)
    # Ctrl+- on a whole row deletes it; Ctrl++ inserts one
    tabs.select((0, 0))
    key(w, Qt.Key_Space, " ", SHIFT)
    key(w, Qt.Key_Minus, "-", CTRL)
    assert typed(tables(w)[0], "A1") == "4"
    key(w, Qt.Key_Space, " ", SHIFT)
    key(w, Qt.Key_Plus, "+", CTRL | SHIFT)
    assert typed(tables(w)[0], "A1") == "" and typed(tables(w)[0], "A2") == "4"


def test_dialog_shortcuts(w):
    loads(w)
    tabs = w.view.tables
    key(w, Qt.Key_1, mods=CTRL)
    assert getattr(w, "_last_format_dialog", None) is not None, "Ctrl+1 Format Cells"
    w._last_data_dialog = None
    key(w, Qt.Key_F, mods=CTRL)
    assert type(w._last_data_dialog).__name__ == "FindDialog"
    w._last_data_dialog = None
    key(w, Qt.Key_F2, mods=SHIFT)
    assert type(w._last_data_dialog).__name__ == "CommentDialog"
    w._last_names_dialog = None
    key(w, Qt.Key_F3, mods=CTRL)
    pump()
    assert tabs.item is not None
