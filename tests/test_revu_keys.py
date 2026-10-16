"""Revu's keys, found missing or wrong by QA (2026-10-15).

Home and End go to the first and last page; Ctrl+Right and Ctrl+Left turn
the page (beside Ctrl+PgDown and Ctrl+PgUp) but never out of something being
typed into; Ctrl+Y redoes; V is Select and Shift+V is Pan; Flatten…,
Unflatten, Dark Mode and Lock have Revu's keys; and the page's right-click
menu has Revu's entries.

Keys go through QTest.keyClick, so Qt's shortcut map sees them as it sees a
real keyboard: the window has to be shown and active for that.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from calcforge.items.shapes import RectItem
from calcforge.items.text import FlagItem, NoteItem
from tests.test_usability import drag, on_page, only

CTRL, SHIFT = Qt.ControlModifier, Qt.ShiftModifier
PAGES = 5


def pump():
    QApplication.instance().processEvents()


@pytest.fixture
def win(window, tmp_path):
    """A shown, active window with a five-page PDF open."""
    import pymupdf

    path = tmp_path / "five pages.pdf"
    made = pymupdf.open()
    for number in range(1, PAGES + 1):
        page = made.new_page(width=612, height=792)
        page.insert_text((72, 72), f"Page {number}", fontsize=30)
    made.save(str(path))
    made.close()
    window.show()
    window.activateWindow()
    window.open_from_command_line(str(path))
    pump()
    window.view.setFocus()
    pump()
    assert len(window.document.pages) == PAGES
    return window


def key(window, k, mods=Qt.NoModifier):
    QTest.keyClick(QApplication.focusWidget() or window.view, k, mods)
    pump()


def page_box(window) -> int:
    return window.page_spin.value()


def top_of_page_in_view(window, index) -> bool:
    view = window.view
    frame = window.document.pages[index].frame
    top = frame.mapToScene(QPointF(0, 0)).y()
    seen = view.mapToScene(view.viewport().rect()).boundingRect()
    return seen.top() <= top <= seen.top() + seen.height() / 2


# -- 1. Home and End ------------------------------------------------------------------

def test_home_and_end_go_to_the_first_and_last_page(win):
    win.view.fit_page()
    pump()
    key(win, Qt.Key_Home)
    assert win.current_index == 0 and page_box(win) == 1, \
        "at Fit Page, Home went forward to page 2"
    key(win, Qt.Key_End)
    assert win.current_index == PAGES - 1 and page_box(win) == PAGES
    assert top_of_page_in_view(win, PAGES - 1)
    win.go_to_page(2)
    key(win, Qt.Key_Home)
    assert win.current_index == 0 and page_box(win) == 1
    assert top_of_page_in_view(win, 0)


def test_home_brings_back_the_top_of_the_first_page(win):
    """Half-way down page one, Home still goes to its top."""
    win.view.set_zoom(2.0)
    win.go_to_page(1)
    win.go_to_page(0)
    bar = win.view.verticalScrollBar()
    bar.setValue(bar.value() + 400)
    pump()
    assert win.current_index == 0 and not top_of_page_in_view(win, 0)
    key(win, Qt.Key_Home)
    assert win.current_index == 0 and top_of_page_in_view(win, 0)


def test_home_and_end_at_a_small_zoom_keep_the_page_box_honest(win):
    """Zoomed out, the middle of the window is on a later page than the one
    Home went to; the page box still says page 1."""
    win.view.set_zoom(0.15)
    pump()
    key(win, Qt.Key_End)
    assert win.current_index == PAGES - 1 and page_box(win) == PAGES
    key(win, Qt.Key_Home)
    assert win.current_index == 0 and page_box(win) == 1


def test_ctrl_home_and_ctrl_end_still_reach_the_ends(win):
    bar = win.view.verticalScrollBar()
    key(win, Qt.Key_End, CTRL)
    assert bar.value() == bar.maximum()
    assert win.current_index == PAGES - 1 and page_box(win) == PAGES
    key(win, Qt.Key_Home, CTRL)
    assert bar.value() == bar.minimum()
    assert win.current_index == 0 and page_box(win) == 1


# -- 2. Next and Previous Page ----------------------------------------------------------

def test_ctrl_right_and_left_turn_the_page(win):
    key(win, Qt.Key_Right, CTRL)
    assert win.current_index == 1 and page_box(win) == 2
    key(win, Qt.Key_Right, CTRL)
    assert win.current_index == 2
    key(win, Qt.Key_Left, CTRL)
    assert win.current_index == 1 and page_box(win) == 2


def test_ctrl_page_down_and_up_still_turn_the_page(win):
    key(win, Qt.Key_PageDown, CTRL)
    assert win.current_index == 1
    key(win, Qt.Key_PageUp, CTRL)
    assert win.current_index == 0


def test_the_page_keys_are_on_the_actions_revus_first(win):
    shown = [s.toString() for s in win.act_next_page.shortcuts()]
    assert shown == ["Ctrl+Right", "Ctrl+PgDown"]
    shown = [s.toString() for s in win.act_prev_page.shortcuts()]
    assert shown == ["Ctrl+Left", "Ctrl+PgUp"]


def _type_into_a_text_box(win):
    win.view.set_zoom(1.0)
    win.view.go_to_page_top(0)
    pump()
    win.select_tool("text")
    drag(win.view, *on_page(win, 0, 100, 140), *on_page(win, 0, 400, 200))
    pump()
    assert win.view.is_editing()
    QTest.keyClicks(win.view.viewport(), "one two three")
    pump()
    editor = win.view._editing_item._editor
    return editor


def test_ctrl_right_in_a_text_box_moves_the_caret_not_the_page(win):
    editor = _type_into_a_text_box(win)
    cursor = editor.textCursor()
    cursor.setPosition(0)
    editor.setTextCursor(cursor)
    key(win, Qt.Key_Right, CTRL)
    assert win.current_index == 0, "Ctrl+Right turned the page out of the words"
    assert win.view.is_editing()
    assert editor.textCursor().position() > 0, "Ctrl+Right is the next word there"
    end = len(editor.toPlainText())
    cursor.setPosition(end)
    editor.setTextCursor(cursor)
    key(win, Qt.Key_Left, CTRL)
    assert win.current_index == 0 and win.view.is_editing()
    assert editor.textCursor().position() < end


def test_ctrl_right_in_a_panel_field_stays_in_the_field(win):
    win.find_in_document("Page")
    pump()
    field = win.search_panel.query
    field.setFocus()
    field.setCursorPosition(0)
    pump()
    QTest.keyClick(field, Qt.Key_Right, CTRL)
    pump()
    assert win.current_index == 0
    assert field.cursorPosition() > 0


def test_ctrl_right_in_an_equation_stays_in_the_equation(win):
    win.view.set_zoom(1.0)
    win.view.go_to_page_top(0)
    win.toggle_calc_mode(True)
    p = QPointF(*on_page(win, 0, 100, 160))
    from tests.test_usability import click
    click(win.view, p.x(), p.y())
    QTest.keyClicks(win.view.viewport(), "abc")
    pump()
    assert win.view.calc.editing()
    key(win, Qt.Key_Left, CTRL)
    key(win, Qt.Key_Right, CTRL)
    assert win.current_index == 0 and win.view.calc.editing()


def test_ctrl_right_in_an_open_table_is_excels(win):
    from tests.test_tables import make_table

    win.view.set_zoom(1.0)
    win.view.go_to_page_top(0)
    pump()
    make_table(win, y=160)
    tabs = win.view.tables
    tabs.select((0, 0))
    win.view.setFocus()
    key(win, Qt.Key_Right, CTRL)
    assert win.current_index == 0, "an open table keeps Excel's Ctrl+arrows"
    assert tabs.active[1] > 0


# -- 3. Redo ----------------------------------------------------------------------------

def test_ctrl_y_and_ctrl_shift_z_both_redo(win):
    win.view.set_zoom(1.0)
    win.view.go_to_page_top(0)
    win.select_tool("rect")
    drag(win.view, *on_page(win, 0, 100, 140), *on_page(win, 0, 220, 240))
    win.select_tool("select")
    assert len(only(win, RectItem)) == 1
    key(win, Qt.Key_Z, CTRL)
    assert only(win, RectItem) == []
    key(win, Qt.Key_Y, CTRL)
    assert len(only(win, RectItem)) == 1, "Ctrl+Y is Revu's redo"
    key(win, Qt.Key_Z, CTRL)
    key(win, Qt.Key_Z, CTRL | SHIFT)
    assert len(only(win, RectItem)) == 1, "and Ctrl+Shift+Z still redoes"
    assert [s.toString() for s in win.act_redo.shortcuts()] == ["Ctrl+Y", "Ctrl+Shift+Z"]


# -- 4. Revu's other keys ---------------------------------------------------------------

def test_v_is_select_and_shift_v_is_pan(win):
    win.select_tool("select")
    key(win, Qt.Key_V, SHIFT)
    assert win.view.current_tool().key == "pan"
    key(win, Qt.Key_V)
    assert win.view.current_tool().key == "select"
    win.select_tool("rect")
    key(win, Qt.Key_V)
    assert win.view.current_tool().key == "select", "V puts a drawing tool down"
    win.select_tool("rect")
    key(win, Qt.Key_Escape)
    assert win.view.current_tool().key == "select", "and so does Escape still"
    assert "V" in win.tool_actions["select"].toolTip()


def test_v_types_a_v_in_a_text_box(win):
    editor = _type_into_a_text_box(win)
    QTest.keyClicks(win.view.viewport(), "vV")
    pump()
    assert editor.toPlainText().endswith("vV")
    assert win.view.current_tool().key not in ("pan",) and win.view.is_editing()


def test_revus_keys_for_flatten_dark_mode_and_lock(win):
    def keys(action):
        return [s.toString() for s in action.shortcuts()]

    assert keys(win.act_flatten_document) == ["Ctrl+Shift+M"]
    assert keys(win.act_recover_flattened) == ["Ctrl+Shift+U"]
    assert keys(win.act_dark) == ["Ctrl+3"]
    assert keys(win.act_lock) == ["Ctrl+Shift+L", "Ctrl+L"]
    # unchanged on purpose
    assert keys(win.act_duplicate) == ["Ctrl+D"]
    assert keys(win.act_array) == ["Ctrl+Shift+D"]
    assert win.shortcuts.sequence("tool.stamp") == "S"
    assert win.shortcuts.sequence("tool.measure_length") == "M"
    assert win.shortcuts.conflicts() == {}


def test_lock_answers_to_both_keys(win):
    win.view.set_zoom(1.0)
    win.view.go_to_page_top(0)
    win.select_tool("rect")
    drag(win.view, *on_page(win, 0, 100, 140), *on_page(win, 0, 220, 240))
    win.select_tool("select")
    (item,) = only(win, RectItem)
    item.setSelected(True)
    key(win, Qt.Key_L, CTRL | SHIFT)
    assert item.locked
    key(win, Qt.Key_L, CTRL)
    assert not item.locked


def test_a_second_key_can_be_changed_like_any_other(win):
    win.shortcuts.set_sequence("command.next_page.also", "Ctrl+Alt+N")
    win.apply_shortcuts()
    assert [s.toString() for s in win.act_next_page.shortcuts()] == \
        ["Ctrl+Alt+N", "Ctrl+PgDown"]
    win.shortcuts.set_sequence("command.next_page.also", "")
    win.apply_shortcuts()
    assert [s.toString() for s in win.act_next_page.shortcuts()] == ["Ctrl+PgDown"]
    win.shortcuts.reset("command.next_page.also")
    win.apply_shortcuts()
    assert win.act_next_page.shortcut() == QKeySequence("Ctrl+Right")


# -- 5. The page's right-click menu -----------------------------------------------------

def test_the_page_menu_has_revus_entries(win):
    point = QPointF(*on_page(win, 0, 300, 400))
    menu = win.build_context_menu(None, point)
    labels = [a.text() for a in menu.actions() if a.text()]
    for wanted in ("Paste", "Add Note", "Add Bookmark", "Add Flag", "Next Page",
                   "Previous Page", "Select All", "Print…", "Search",
                   # and ours, kept
                   "Paste in Place", "Paste Here…", "Insert Here", "Page Setup…",
                   "Set Scale…"):
        assert wanted in labels, f"{wanted} is missing from the page menu"
    # Revu's order: the adds, then the page keys, then Select All, Print and Search
    assert labels.index("Paste") < labels.index("Add Note") < labels.index("Add Bookmark") \
        < labels.index("Add Flag") < labels.index("Next Page") \
        < labels.index("Previous Page") < labels.index("Select All") \
        < labels.index("Print…") < labels.index("Search")
    # the window's own actions, not copies of them
    actions = menu.actions()
    assert win.act_bookmark in actions and win.act_next_page in actions
    assert win.act_prev_page in actions and win.act_print in actions
    assert win.act_find_text in actions
    menu.deleteLater()


def test_add_note_and_add_flag_land_where_the_page_was_clicked(win):
    point = QPointF(*on_page(win, 0, 300, 400))
    menu = win.build_context_menu(None, point)
    by_text = {a.text(): a for a in menu.actions() if a.text()}
    by_text["Add Flag"].trigger()
    win.view.escape_everything()
    by_text["Add Note"].trigger()
    win.view.escape_everything()
    (flag,) = only(win, FlagItem)
    (note,) = only(win, NoteItem)
    page = win.document.pages[0].frame
    for item in (flag, note):
        assert page.isAncestorOf(item) or item.parentItem() is page
    menu.deleteLater()
