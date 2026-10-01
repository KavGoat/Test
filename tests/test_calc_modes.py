"""Calc and Markup modes, and the keyboard (phase 3; decisions 5, 6, 7).

Everything through real key events: QTest.keyClick goes through Qt's
shortcut machinery as a keyboard does, so a window shortcut that would steal
a key is caught here.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest

from calcforge.calc.engine.display import display_text
from calcforge.items.calc import CalcItem, CalcTextItem
from calcforge.items.text import TextItem
from calcforge.ui import calcdialogs
from tests.test_usability import click, hover, press_key


@pytest.fixture
def win(window):
    window.show()
    window.activateWindow()
    window.view.setFocus()
    yield window
    calcdialogs.ANSWERS.clear()


def keys(window, key, mods=Qt.NoModifier):
    """A key as Qt's shortcut map delivers it (offscreen Qt does not run the
    map for synthetic keys): ShortcutOverride first — claimed, the key goes to
    the focus widget; otherwise the window action on that key fires."""
    from PySide6.QtCore import QEvent, QKeyCombination
    from PySide6.QtGui import QAction, QKeyEvent, QKeySequence
    from PySide6.QtWidgets import QApplication
    target = QApplication.focusWidget() or window.view
    text = QKeySequence(key).toString().lower() if Qt.Key_A <= key <= Qt.Key_Z and \
        not mods & (Qt.ControlModifier | Qt.AltModifier) else ""
    override = QKeyEvent(QEvent.ShortcutOverride, key, mods, text)
    QApplication.sendEvent(target, override)
    wanted = QKeySequence(QKeyCombination(mods, key))
    if not override.isAccepted():
        for action in window.findChildren(QAction):
            if action.isEnabled() and any(s == wanted for s in action.shortcuts()):
                action.trigger()
                return
    QApplication.sendEvent(target, QKeyEvent(QEvent.KeyPress, key, mods, text))


def typed(window, text):
    for ch in text:
        QTest.keyClicks(window.view.viewport(), ch)


def at(window, x, y):
    return window.document.pages[0].frame.mapToScene(QPointF(x, y))


def equations(window):
    return [i for i in window.view.scene().items() if isinstance(i, CalcItem)]


def calc_texts(window):
    return [i for i in window.view.scene().items() if isinstance(i, CalcTextItem)]


def into_calc_mode(window, x=100, y=120):
    window.toggle_calc_mode(True)
    p = at(window, x, y)
    click(window.view, p.x(), p.y())


# -- the modes --------------------------------------------------------------------------

def test_the_status_bar_shows_the_mode_and_f12_switches_it(win):
    assert win.mode_switch.text() == "Markup" and not win.mode_switch.isChecked()
    keys(win, Qt.Key_F12)
    assert win.view.calc.mode == "calc" and win.mode_switch.text() == "Calc"
    keys(win, Qt.Key_F12)
    assert win.view.calc.mode == "markup" and win.mode_switch.text() == "Markup"


def test_file_new_is_one_blank_a4_portrait_page_in_markup_mode(win):
    win.toggle_calc_mode(True)
    win.new_document(confirm=False)
    assert len(win.document.pages) == 1
    setup = win.document.pages[0].setup
    assert setup.size_name == "A4" and setup.orientation == "portrait"
    assert win.view.calc.mode == "markup" and win.mode_switch.text() == "Markup"


# -- Calc mode: every tool key is off ----------------------------------------------------

def test_calc_mode_letters_start_equations_not_tools(win):
    into_calc_mode(win)
    typed(win, "q")                                   # Q is the callout tool in Markup mode
    assert win.view.current_tool().key == "select"
    assert win.view.calc.item is not None and win.view.calc.item.text() == "q"


def test_calc_mode_shift_letter_types_a_capital_not_the_eraser(win):
    into_calc_mode(win)
    QTest.keyClicks(win.view.viewport(), "E")        # Shift+E is the eraser in Markup mode
    assert win.view.current_tool().key == "select"
    assert win.view.calc.item is not None and win.view.calc.item.text() == "E"


def test_calc_mode_alt_tool_keys_are_silent(win):
    into_calc_mode(win)
    keys(win, Qt.Key_P, Qt.AltModifier)              # Alt+P is the pen in Markup mode
    assert win.view.current_tool().key == "select"
    assert equations(win) == []


def test_calc_mode_number_keys_are_numbers_not_my_tools(win):
    into_calc_mode(win)
    typed(win, "1")
    assert win.view.calc.item is not None and win.view.calc.item.text() == "1"


def test_markup_mode_keeps_calcforges_tool_keys(win):
    p = at(win, 100, 120)
    click(win.view, p.x(), p.y())
    typed(win, "r")
    assert win.view.current_tool().key == "rect"
    assert equations(win) == []


# -- starting things ----------------------------------------------------------------------

def test_markup_mode_apostrophe_starts_an_equation_at_the_pointer(win):
    p = at(win, 200, 300)
    hover(win.view, p.x(), p.y())
    typed(win, "'")
    item = win.view.calc.item
    assert item is not None
    assert abs(item.pos().x() - 200) < 7 and abs(item.pos().y() - 300) < 7
    typed(win, "2+2=")
    press_key(win.view, Qt.Key_Return)
    assert display_text(item.region.display) == "4"


def test_inside_an_equation_apostrophe_still_means_unit_follows(win):
    into_calc_mode(win)
    typed(win, "5'kN=")
    item = win.view.calc.item
    press_key(win.view, Qt.Key_Return)
    assert display_text(item.region.display) == "5 kN"


def test_quote_is_calculation_text_in_calc_mode_and_a_text_box_in_markup_mode(win):
    into_calc_mode(win)
    typed(win, '"')
    (made,) = calc_texts(win)
    assert win.view.editing_item() is made
    typed(win, "Beam check")
    press_key(win.view, Qt.Key_Escape)
    assert "Beam check" in made.text()
    win.toggle_calc_mode(False)
    p = at(win, 100, 400)
    hover(win.view, p.x(), p.y())
    typed(win, '"')
    boxes = [i for i in win.view.scene().items()
             if isinstance(i, TextItem) and not isinstance(i, CalcTextItem)]
    assert len(boxes) == 1


def test_a_word_and_a_space_become_calculation_text_and_undo_brings_the_equation_back(win):
    into_calc_mode(win)
    typed(win, "Check ")
    assert equations(win) == []
    (made,) = calc_texts(win)
    assert made.text().startswith("Check")
    press_key(win.view, Qt.Key_Escape)
    win.undo_something()
    assert calc_texts(win) == []
    (back,) = equations(win)
    assert back.text() == "Check"


def test_calculation_text_never_takes_a_leader(win):
    into_calc_mode(win)
    typed(win, '"')
    typed(win, "note")
    press_key(win.view, Qt.Key_Escape)
    (made,) = calc_texts(win)
    win.set_leader(made, True)
    assert not made.leaders
    assert win.becomes_a_callout(made) is made
    assert made.style.stroke == "" and made.style.fill == ""   # plain by default


def test_calculation_text_is_saved_as_a_text_annotation(win, tmp_path):
    into_calc_mode(win)
    typed(win, '"')
    typed(win, "design note")
    press_key(win.view, Qt.Key_Escape)
    from tests.test_output import _pdf
    printed = _pdf(win.document, tmp_path)
    assert [str(m["/Subtype"]) for m in printed.markups()] == ["/FreeText"]


# -- keys inside an equation: editing decides (decision 6) ------------------------------

def test_ctrl_1_is_transpose_in_an_equation_and_fit_width_outside(win):
    into_calc_mode(win)
    typed(win, "M")
    keys(win, Qt.Key_1, Qt.ControlModifier)
    assert win.view.calc.item.text().startswith("Mtranspose(") or \
        "transpose(" in win.view.calc.item.text()
    win.view.calc.leave()   # Esc keeps the equation open, as in WebSMath
    win.view.set_zoom(3.0)
    keys(win, Qt.Key_1, Qt.ControlModifier)
    assert win.view._zoom != 3.0, "fit width outside an equation"


def test_ctrl_b_emboldens_the_equation_and_adds_no_bookmark(win):
    into_calc_mode(win)
    typed(win, "x:1")
    item = win.view.calc.item
    marks = len(win.document.bookmarks)
    keys(win, Qt.Key_B, Qt.ControlModifier)
    assert item.region.bold
    assert len(win.document.bookmarks) == marks


def test_ctrl_e_inserts_a_function_in_an_equation(win):
    into_calc_mode(win)
    typed(win, "1+")
    calcdialogs.ANSWERS["Insert function"] = "sin"
    keys(win, Qt.Key_E, Qt.ControlModifier)
    assert win.view.calc.item.text() == "1+sin()" or win.view.calc.item.text().startswith("1+sin(")


def test_ctrl_shift_d_is_the_double_check_in_an_equation(win):
    into_calc_mode(win)
    typed(win, "2*3=")
    calcdialogs.ANSWERS["Double-check"] = None
    keys(win, Qt.Key_D, Qt.ControlModifier | Qt.ShiftModifier)
    assert calcdialogs.ANSWERS["Double-check"] is not None
    assert "agree" in win.status_hint.text()


def test_ctrl_a_in_an_equation_selects_every_equation(win):
    into_calc_mode(win)
    typed(win, "a:1")
    press_key(win.view, Qt.Key_Return)
    typed(win, "b:2")
    keys(win, Qt.Key_A, Qt.ControlModifier)
    assert win.view.calc.item is None
    assert len(equations(win)) == 2 and all(i.isSelected() for i in equations(win))


def test_symbol_keys_type_their_maths_meaning_in_an_equation(win):
    into_calc_mode(win)
    typed(win, "2*")
    keys(win, Qt.Key_P, Qt.ControlModifier | Qt.AltModifier)    # π
    typed(win, "=")
    item = win.view.calc.item
    assert item.text() == "2*π="
    press_key(win.view, Qt.Key_Return)
    assert display_text(item.region.display) == "6.2832"


def test_smath_keys_can_be_rebound(win):
    from calcforge.ui import dialogs
    dialog = dialogs.ShortcutManagerDialog(win.shortcuts, win)
    dialog.editors["smath.at_least"].setText("Ctrl+Shift+0")
    dialog.apply()
    into_calc_mode(win)
    typed(win, "3")
    keys(win, Qt.Key_0, Qt.ControlModifier | Qt.ShiftModifier)
    typed(win, "2")
    assert win.view.calc.item.text() == "3≥2"


def test_the_shortcut_manager_has_an_smath_section_and_checks_clashes_by_where(win):
    from calcforge.ui import dialogs
    from calcforge.ui.shortcuts import BY_ID
    dialog = dialogs.ShortcutManagerDialog(win.shortcuts, win)
    smath = [b for b in win.shortcuts.bindings() if b.category == "SMath"]
    assert {"smath.at_least", "smath.transpose", "smath.insert_function", "command.calc_mode",
            "insert.equation", "insert.calc_text"} <= {b.action_id for b in smath}
    assert dialog.clashes() == [], "the defaults are all right: editing decides"
    # a real clash: two things on one key in the same place
    dialog.editors["smath.transpose"].setText("Ctrl+3")
    assert dialog.clashes()
    dialog.editors["smath.transpose"].setText("Ctrl+1")
    # " is Calculation text in Calc mode and a text box in Markup mode: not a clash
    assert BY_ID["insert.calc_text"].default == BY_ID["insert.text"].default == '"'
    assert dialog.clashes() == []


def test_f9_calculates_and_ctrl_m_inserts_a_matrix(win):
    into_calc_mode(win)
    calcdialogs.ANSWERS["Insert matrix"] = (2, 2)
    keys(win, Qt.Key_M, Qt.ControlModifier)
    item = win.view.calc.item
    assert item is not None and "mat(" in item.text()
    win.view.calc.leave()   # Esc keeps the equation open, as in WebSMath
    keys(win, Qt.Key_F9)
    assert win.status_hint.text() == "Calculated"
