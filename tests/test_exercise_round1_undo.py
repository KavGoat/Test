"""Exercise round 1 (docs/qa/exercise_round1.md): typed fields, undo steps,
menus while an equation is open, feedback, and the smaller faults — each
driven the way a person does it, with the mouse and the keyboard in the real
window.

F-06 typed numbers and words are one undo step, applied on Enter
F-07 Alt and a menu's letter while an equation is being typed
F-08 Program blocks, a matrix, a link, bookmarks, conditional formatting: undo
F-15 a blank document property shows as «its name»
F-22 the Page panel never scrolls sideways
F-24 search snippets keep their words whole; Replace says why it cannot
F-27 Colour Processing's preview is there as it opens
F-29 spell check offers "The" for "Teh" and leaves the selection as it was
F-35 commands that said nothing now say what happened
F-36, F-37 the smaller faults and dark-mode contrast
and the user's two of 2026-10-16: a markup style's text look, and an
equation's Decimal Places, Significant Figures and Global at the top.
"""
from __future__ import annotations

import os
import sys

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QDialog, QDialogButtonBox,
                               QInputDialog, QLineEdit, QMenu, QMessageBox, QSpinBox)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from tests.test_calc_modes import into_calc_mode, typed  # noqa: E402
from tests.test_usability import drag, press_key  # noqa: E402


@pytest.fixture
def win(window):
    window.show()
    window.activateWindow()
    window.view.setFocus()
    QApplication.processEvents()
    yield window


def ex():
    from tools.qa import exercise
    if exercise.APP is None:
        exercise.APP = QApplication.instance()     # its helpers, not its recorders
    return exercise


def pump(times=3):
    for _ in range(times):
        QApplication.processEvents()


def line_of(spin):
    return spin.findChild(QLineEdit)


def type_into(widget, text, enter=True):
    """Click a box, select what is in it and type, as a person does."""
    field = line_of(widget) if isinstance(widget, QAbstractSpinBox) else widget
    QTest.mouseClick(field, Qt.LeftButton, Qt.NoModifier, field.rect().center())
    QTest.keyClick(field, Qt.Key_A, Qt.ControlModifier)
    QTest.keyClicks(field, text)
    if enter:
        QTest.keyClick(field, Qt.Key_Return)
    pump()


def back_to(window):
    """The window active again after a dialog, as a window manager makes it
    (the offscreen platform leaves no window active)."""
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)   # dialogs let go
    window.activateWindow()
    window.view.setFocus()
    pump()


def undo_key(window):
    back_to(window)
    QTest.keyClick(window.view, Qt.Key_Z, Qt.ControlModifier)
    pump()


def a_rectangle(window):
    ex().look_at(window)
    (item,) = ex().draw(window, "rect")
    ex().pick(window, [item])
    return item


def answer_next_dialog(press, then=None, tries=60):
    """Answer the modal dialog the next step opens: *press* is a button's
    text, or a key."""
    def look():
        dialog = QApplication.activeModalWidget()
        if dialog is None:
            if look.tries > 0:
                look.tries -= 1
                QTimer.singleShot(50, look)
            return
        if then is not None:
            then(dialog)
        if isinstance(press, str):
            button = next(b for b in dialog.findChildren(
                __import__("PySide6.QtWidgets", fromlist=["QAbstractButton"]).QAbstractButton)
                if b.text().replace("&", "") == press and b.isVisible())
            QTest.mouseClick(button, Qt.LeftButton)
        else:
            QTest.keyClick(dialog, press)
    look.tries = tries
    QTimer.singleShot(50, look)


# ---------------------------------------------------------------------------
# F-06: typed fields
# ---------------------------------------------------------------------------

def test_a_typed_line_width_is_applied_on_enter_as_one_undo_step(win):
    item = a_rectangle(win)
    before, steps = item.style.width, win.undo_stack.count()
    field = line_of(win.width_spin)
    QTest.mouseClick(field, Qt.LeftButton, Qt.NoModifier, field.rect().center())
    QTest.keyClick(field, Qt.Key_A, Qt.ControlModifier)
    QTest.keyClicks(field, "2.5")
    pump()
    assert item.style.width == before, "nothing half-typed is drawn"
    assert win.undo_stack.count() == steps
    QTest.keyClick(field, Qt.Key_Return)
    pump()
    assert item.style.width == pytest.approx(2.5)
    assert win.undo_stack.count() == steps + 1
    undo_key(win)
    (back,) = ex().markups(win)
    assert back.style.width == pytest.approx(before)


def test_the_arrows_of_a_style_box_still_apply_at_once(win):
    item = a_rectangle(win)
    before = item.style.opacity
    field = line_of(win.opacity_spin)
    QTest.mouseClick(field, Qt.LeftButton, Qt.NoModifier, field.rect().center())
    QTest.keyClick(field, Qt.Key_Down)
    pump()
    assert item.style.opacity < before


@pytest.mark.parametrize("name", ["markupSubject", "markupAuthor", "markupLabel"])
def test_typing_in_a_properties_field_is_one_undo_step_however_slow(win, name, monkeypatch):
    from calcforge.ui import commands
    monkeypatch.setattr(commands, "MERGE_PAUSE", 0.0)      # every key a pause apart
    item = a_rectangle(win)
    field = win.properties_panel.findChild(QLineEdit, name)
    attribute = name.replace("markup", "").lower()
    was, steps = getattr(item, attribute), win.undo_stack.count()
    type_into(field, "Test 1")
    (now,) = ex().markups(win)
    assert getattr(now, attribute) == "Test 1"
    assert win.undo_stack.count() == steps + 1
    undo_key(win)
    (back,) = ex().markups(win)
    assert getattr(back, attribute) == was


def test_every_number_in_the_properties_panel_applies_on_enter(win):
    a_rectangle(win)
    spins = win.properties_panel.body.findChildren(QAbstractSpinBox)
    assert spins and not any(spin.keyboardTracking() for spin in spins)


def test_the_page_width_waits_for_enter_and_is_one_step(win):
    dock = win.dock_page
    dock.show()
    dock.raise_()
    pump()
    panel = win.page_panel
    page = win.current_page()
    width, steps = page.setup.width_mm, win.undo_stack.count()
    field = line_of(panel.width_mm)
    QTest.mouseClick(field, Qt.LeftButton, Qt.NoModifier, field.rect().center())
    QTest.keyClick(field, Qt.Key_A, Qt.ControlModifier)
    QTest.keyClicks(field, "300")
    pump()
    assert win.current_page().setup.width_mm == width
    QTest.keyClick(field, Qt.Key_Return)
    pump()
    assert win.current_page().setup.width_mm == pytest.approx(300)
    assert win.undo_stack.count() == steps + 1


# ---------------------------------------------------------------------------
# F-22: the Page panel keeps its labels whole
# ---------------------------------------------------------------------------

def test_the_page_panel_never_scrolls_its_labels_away(win):
    dock = win.dock_page
    dock.show()
    dock.raise_()
    pump()
    panel = win.page_panel
    assert panel.widget().width() <= panel.viewport().width()
    for box in (panel.width_mm, panel.height_mm, panel.precision):
        field = line_of(box)
        QTest.mouseClick(field, Qt.LeftButton, Qt.NoModifier, field.rect().center())
        pump()
        assert panel.horizontalScrollBar().value() == 0


# ---------------------------------------------------------------------------
# F-07: menus while an equation is typed
# ---------------------------------------------------------------------------

def test_alt_and_a_menu_letter_opens_the_menu_while_an_equation_is_typed(win):
    ex().look_at(win)
    into_calc_mode(win, 100, 140)
    typed(win, "x:3")
    assert win.view.calc.editing()
    QTest.keyClick(win, Qt.Key_C, Qt.AltModifier)
    pump()
    menu = QApplication.activePopupWidget()
    assert isinstance(menu, QMenu) and menu.title().replace("&", "") == "Calculation"
    QTest.keyClick(menu, Qt.Key_Escape)
    pump()
    if QApplication.activePopupWidget() is not None:          # the bar keeps focus
        QTest.keyClick(QApplication.activePopupWidget(), Qt.Key_Escape)
    win.view.setFocus()
    typed(win, "+1")
    assert win.view.calc.editing()
    assert "3+1" in win.view.calc.item.text().replace(" ", "")


def test_equation_keys_still_work_around_a_menu_opened_by_alt(win):
    ex().look_at(win)
    into_calc_mode(win, 100, 140)
    typed(win, "y:2")
    QTest.keyClick(win, Qt.Key_E, Qt.AltModifier)                # Edit opens…
    pump()
    assert isinstance(QApplication.activePopupWidget(), QMenu)
    while QApplication.activePopupWidget() is not None:          # …and is closed again
        QTest.keyClick(QApplication.activePopupWidget(), Qt.Key_Escape)
        pump()
    back_to(win)
    assert win.view.calc.editing()
    text = win.view.calc.item.text().replace(" ", "")
    assert "e" not in text.lower().replace("y", ""), "Alt+E typed no letter"
    QTest.keyClick(win.view.viewport(), Qt.Key_Backspace)        # the editor's keys
    typed(win, "5")
    assert win.view.calc.item.text().replace(" ", "").replace("≔", ":").endswith("y:5")
    QTest.keyClick(win.view.viewport(), Qt.Key_Z, Qt.ControlModifier)   # one keystroke back
    pump()
    assert win.view.calc.editing()
    assert not win.view.calc.item.text().replace(" ", "").endswith("5")


# ---------------------------------------------------------------------------
# F-08: undo steps
# ---------------------------------------------------------------------------

def _click_menu_path(win, *path):
    """The menu bar by mouse: its title, then each item down the path."""
    back_to(win)
    bar = win.menuBar()
    top = next(a for a in bar.actions() if a.text().replace("&", "") == path[0])
    QTest.mouseClick(bar, Qt.LeftButton, Qt.NoModifier, bar.actionGeometry(top).center())
    pump()
    menu = top.menu()
    for title in path[1:]:
        assert menu is not None and menu.isVisible(), f"no menu open for {title!r}"
        names = [a.text().replace("&", "") for a in menu.actions()]
        action = next((a for a in menu.actions() if a.text().replace("&", "") == title), None)
        assert action is not None, f"{title!r} not in {names}"
        # from off the item and onto it, so the menu sees the pointer arrive
        QTest.mouseMove(menu, QPoint(1, 1))
        QTest.mouseMove(menu, menu.actionGeometry(action).center())
        QTest.mouseClick(menu, Qt.LeftButton, Qt.NoModifier,
                         menu.actionGeometry(action).center())
        pump(6)
        menu = action.menu()


@pytest.mark.parametrize("which", ["If", "For", "While", "Line"])
def test_a_program_block_from_the_menu_goes_with_one_undo(win, which):
    ex().look_at(win)
    into_calc_mode(win, 100, 140)
    press_key(win.view, Qt.Key_Escape)
    before = ex().doc_signature(win)
    _click_menu_path(win, "Calculation", "Program", which)
    assert ex().equations(win), f"{which} started an equation"
    undo_key(win)
    assert not ex().equations(win)
    assert ex().doc_signature(win) == before


def test_a_plot_from_the_menu_goes_with_one_undo(win):
    ex().look_at(win)
    into_calc_mode(win, 100, 140)
    press_key(win.view, Qt.Key_Escape)
    _click_menu_path(win, "Calculation", "Plot")
    assert ex().equations(win)
    undo_key(win)
    assert not ex().equations(win)


def test_insert_matrix_ok_goes_with_one_undo(win):
    win.interactive_prompts = True
    ex().look_at(win)
    into_calc_mode(win, 100, 140)
    press_key(win.view, Qt.Key_Escape)

    def two_by_two(dialog):
        for spin in dialog.findChildren(QSpinBox):
            spin.setValue(2)
    answer_next_dialog("OK", two_by_two)
    _click_menu_path(win, "Calculation", "Matrix")
    pump()
    assert len(ex().equations(win)) == 1, "the matrix went into a new equation"
    undo_key(win)
    assert not ex().equations(win)


def test_a_link_cancelled_leaves_nothing_and_one_ok_is_one_undo(win):
    win.interactive_prompts = True
    ex().look_at(win)
    page = ex().page_point
    before = ex().doc_signature(win)
    steps = win.undo_stack.count()
    win.select_tool("link")
    a, b = page(win, 100, 100), page(win, 220, 160)
    answer_next_dialog(Qt.Key_Escape)
    drag(win.view, a.x(), a.y(), b.x(), b.y())
    pump()
    assert not [i for i in ex().markups(win) if getattr(i, "TYPE", "") == "link"]
    assert ex().doc_signature(win) == before and win.undo_stack.count() == steps
    win.select_tool("link")
    answer_next_dialog("OK")
    drag(win.view, a.x(), a.y(), b.x(), b.y())
    pump()
    assert [i for i in ex().markups(win) if getattr(i, "TYPE", "") == "link"]
    assert win.undo_stack.count() == steps + 1
    undo_key(win)
    assert not [i for i in ex().markups(win) if getattr(i, "TYPE", "") == "link"]


def test_add_bookmark_rename_and_delete_are_undone(win):
    win.interactive_prompts = True
    def named(dialog):
        dialog.findChild(QLineEdit).setText("Beams")
    answer_next_dialog("OK", named)
    _click_menu_path(win, "Document", "Add Bookmark")
    pump()
    assert [m.title for m in win.document.bookmarks] == ["Beams"]
    undo_key(win)
    assert not win.document.bookmarks
    back_to(win)
    QTest.keyClick(win.view, Qt.Key_Y, Qt.ControlModifier)
    pump()
    assert [m.title for m in win.document.bookmarks] == ["Beams"]
    panel = win.bookmarks_panel
    panel.tree.setCurrentItem(panel.tree.topLevelItem(0))
    delete = next(b for b in panel.findChildren(
        __import__("PySide6.QtWidgets", fromlist=["QPushButton"]).QPushButton)
        if b.text() == "Delete")
    QTest.mouseClick(delete, Qt.LeftButton)
    pump()
    assert not win.document.bookmarks
    undo_key(win)
    assert [m.title for m in win.document.bookmarks] == ["Beams"]


def test_bookmark_rename_and_delete_wait_for_a_bookmark(win):
    from PySide6.QtWidgets import QPushButton
    panel = win.bookmarks_panel
    buttons = {b.text(): b for b in panel.findChildren(QPushButton)}
    assert not buttons["Rename"].isEnabled() and not buttons["Delete"].isEnabled()
    assert buttons["Add"].isEnabled()


def test_conditional_formatting_cancel_changes_nothing_and_ok_is_one_undo(win):
    from calcforge.ui import condformat
    win.interactive_prompts = True
    win.document.settings.calc_rules = {}
    before = ex().doc_signature(win)
    answer_next_dialog("Cancel")
    _click_menu_path(win, "Calculation", "Conditional Formatting…")
    pump()
    assert win.document.settings.calc_rules == {}
    assert ex().doc_signature(win) == before
    steps = win.undo_stack.count()

    def a_preset(dialog):
        dialog.new_preset("DCR")
    answer_next_dialog("OK", a_preset)
    # (the offscreen menu takes a second click on the same item as no move:
    # the command itself, as the menu item runs it)
    back_to(win)
    win.act_calc_rules.trigger()
    pump()
    assert "DCR" in win.document.settings.calc_rules["presets"]
    assert win.undo_stack.count() == steps + 1
    undo_key(win)
    assert not condformat._store(win.document)["presets"]


def test_rename_and_delete_preset_wait_for_a_preset(win):
    from PySide6.QtWidgets import QPushButton
    from calcforge.ui.condformat import DocumentRulesDialog
    win.document.settings.calc_rules = {}
    dialog = DocumentRulesDialog(win)
    buttons = {b.text(): b for b in dialog.findChildren(QPushButton)}
    assert not buttons["Rename"].isEnabled() and not buttons["Delete"].isEnabled()
    dialog.new_preset("P")
    assert buttons["Rename"].isEnabled() and buttons["Delete"].isEnabled()
    dialog.reject()


# ---------------------------------------------------------------------------
# F-15: a blank property shows its name
# ---------------------------------------------------------------------------

def test_a_blank_author_field_shows_its_name_on_screen_only(win):
    from calcforge.items.fields import shown_document
    ex().look_at(win)
    win.document.author = ""
    (box,) = ex().draw(win, "text", text="By ")
    menu = win.build_context_menu(box, box.sceneBoundingRect().center())
    fields = next(a.menu() for a in menu.actions() if a.text() == "Insert Field")
    next(a for a in fields.actions() if a.text() == "Author").trigger()
    pump()
    (box,) = ex().markups(win)
    assert "«Author»" in shown_document(box, on_screen=True).toPlainText()
    assert "«" not in shown_document(box).toPlainText(), "on paper it is still blank"


# ---------------------------------------------------------------------------
# F-24: search
# ---------------------------------------------------------------------------

@pytest.fixture
def drawing(tmp_path):
    import pymupdf
    path = str(tmp_path / "drawing.pdf")
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 100), "Sheet 1: beam TBC", fontsize=11)
    page.draw_rect(pymupdf.Rect(60, 200, 300, 400), color=(0, 0, 0), width=2)
    document.save(path)
    document.close()
    return path


def test_search_snippets_keep_their_first_word_whole(win, drawing):
    win.open_from_command_line(drawing)
    pump()
    panel = win.search_panel
    win.dock_search.show()
    type_into(panel.query, "TBC")
    hits = [h for h in panel.hits if h["kind"] == "drawing"]
    assert hits and hits[0]["context"].startswith("Sheet 1:")
    assert panel.results.topLevelItem(0).text(1).startswith("Sheet")


def test_replace_on_the_drawings_text_says_why_it_cannot(win, drawing):
    from PySide6.QtWidgets import QPushButton
    win.open_from_command_line(drawing)
    pump()
    panel = win.search_panel
    win.dock_search.show()
    type_into(panel.query, "TBC")
    type_into(panel.replacement, "OK", enter=False)
    replace_all = next(b for b in panel.findChildren(QPushButton) if b.text() == "Replace all")
    QTest.mouseClick(replace_all, Qt.LeftButton)
    pump()
    assert "cannot be replaced" in panel.summary.text()
    panel.results.setCurrentItem(panel.results.topLevelItem(0))
    replace = next(b for b in panel.findChildren(QPushButton) if b.text() == "Replace")
    QTest.mouseClick(replace, Qt.LeftButton)
    pump()
    assert "cannot be replaced" in panel.summary.text()


def test_a_markup_snippet_starts_on_a_whole_word():
    from calcforge.ui.searchpanel import _around
    text = "The quick brown foxes jumped over the lazy dog and found TBC beside it"
    start = text.index("TBC")
    shown = _around(text, start, start + 3)
    assert shown.startswith("…") and shown.lstrip("…").split()[0] in text.split()


# ---------------------------------------------------------------------------
# F-27: Colour Processing preview
# ---------------------------------------------------------------------------

def test_colour_processing_shows_before_as_it_opens(win, drawing):
    from calcforge.ui.colorprocess import color_processing
    win.open_from_command_line(drawing)
    pump()
    win.interactive_prompts = False
    dialog = color_processing(win)
    pixmap = dialog.before.pixmap()
    assert pixmap is not None and not pixmap.isNull()
    dialog.reject()


# ---------------------------------------------------------------------------
# F-29: spelling
# ---------------------------------------------------------------------------

def test_teh_is_offered_the_first(win):
    from calcforge.core.spelling import shared
    checker = shared()
    if not checker.ready():
        pytest.skip("no dictionary on this machine")
    assert checker.suggestions("Teh")[0] == "The"
    assert checker.suggestions("teh")[0] == "the"


def test_check_spelling_leaves_the_selection_as_it_was(win):
    from calcforge.core.spelling import shared
    if not shared().ready():
        pytest.skip("no dictionary on this machine")
    ex().look_at(win)
    ex().draw(win, "text", text="Teh beam")
    win.view.scene().clearSelection()
    win.interactive_prompts = True
    answer_next_dialog(Qt.Key_Escape)
    QTest.keyClick(win, Qt.Key_F7)
    pump()
    assert not win.view.scene().selectedItems()


# ---------------------------------------------------------------------------
# F-35: commands say what they did
# ---------------------------------------------------------------------------

def test_save_all_with_nothing_to_save_says_so(win):
    _click_menu_path(win, "File", "Save All")
    assert "nothing to save" in win.status_hint.text()


def test_a_cut_out_with_no_area_says_where_to_draw_it(win):
    ex().look_at(win)
    win.select_tool("cutout_ellipse")
    a, b = ex().page_point(win, 100, 100), ex().page_point(win, 200, 180)
    drag(win.view, a.x(), a.y(), b.x(), b.y())
    pump()
    assert "Area measurement" in win.status_hint.text()


def test_insert_equation_here_opens_an_equation(win):
    ex().look_at(win)
    win.toggle_calc_mode(True)
    spot = ex().page_point(win, 120, 300)
    menu = win.build_context_menu(None, spot)
    here = next(a.menu() for a in menu.actions() if a.text() == "Insert Here")
    next(a for a in here.actions() if a.text() == "Equation").trigger()
    pump()
    assert win.view.calc.editing()
    typed(win, "z:5")
    assert "z" in win.view.calc.item.text()


def test_viewports_with_none_offers_the_tool(win):
    win.interactive_prompts = True
    answer_next_dialog("Draw a Viewport")
    _click_menu_path(win, "Tools", "Measure", "Viewports…")
    pump()
    assert win.view.tool_key == "viewport"


def test_bookmarking_a_text_box_says_so(win):
    ex().look_at(win)
    (box,) = ex().draw(win, "text", text="Beam schedule")
    menu = win.build_context_menu(box, box.sceneBoundingRect().center())
    next(a for a in menu.actions() if a.text() == "Bookmark").trigger()
    assert "Beam schedule" in win.status_hint.text()


# ---------------------------------------------------------------------------
# F-36: the smaller faults
# ---------------------------------------------------------------------------

def test_fractions_ticks_one_choice(win):
    from tests.test_calc_panels import an_equation
    ex().look_at(win)
    item = an_equation(win, "1/4=")
    win.toggle_calc_mode(False)
    menu = win.build_context_menu(item, item.sceneBoundingRect().center())
    equation = next(a.menu() for a in menu.actions() if a.text() == "Equation")
    fractions = next(a.menu() for a in equation.actions() if a.text() == "Fractions")
    ticked = [a.text() for a in fractions.actions() if a.isCheckable() and a.isChecked()
              and a.text() != "Use Mixed Numbers"]
    assert ticked == ["Default"]


def test_a_triangle_keeps_its_three_corners(win):
    from calcforge.items.shapes import PolyItem
    ex().look_at(win)
    (item,) = ex().draw(win, "polygon", (100, 100), (200, 180))
    if not isinstance(item, PolyItem) or len(item.points) != 3:
        pytest.skip("the polygon gesture did not make a triangle")
    corner = item.mapToScene(item.points[0])
    menu = win.build_context_menu(item, corner)
    points = next(a.menu() for a in menu.actions() if a.text() == "Control Point")
    assert "Subtract Control Point" not in [a.text() for a in points.actions()]


def test_about_says_which_version(win):
    from calcforge import __version__
    from calcforge.ui.dialogs import AboutDialog
    from PySide6.QtWidgets import QLabel
    dialog = AboutDialog(win)
    assert __version__ in dialog.findChild(QLabel, "aboutVersion").text()


def test_data_validation_opens_only_what_the_choice_uses(win):
    from calcforge.ui.datatools import ValidationDialog
    from tests.test_tables import make_table
    table = make_table(win)
    win.view.tables.open(table)
    dialog = ValidationDialog(win.view.tables)
    dialog.kind.setCurrentIndex(dialog.kind.findData("any"))
    assert not dialog.a.isEnabled() and not dialog.source.isEnabled()
    dialog.kind.setCurrentIndex(dialog.kind.findData("list"))
    assert dialog.source.isEnabled() and not dialog.a.isEnabled()
    dialog.kind.setCurrentIndex(dialog.kind.findData("whole"))
    assert dialog.a.isEnabled() and dialog.b.isEnabled()
    dialog.reject()


def test_an_empty_text_rule_is_not_accepted(win):
    from calcforge.ui.datatools import TextRuleDialog
    from tests.test_tables import make_table
    table = make_table(win)
    win.view.tables.open(table)
    rules = len(table.sheet.cond_formats) if hasattr(table.sheet, "cond_formats") else None
    dialog = TextRuleDialog(win.view.tables)
    ok = dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok)
    dialog.show()
    QTest.mouseClick(ok, Qt.LeftButton)
    assert dialog.isVisible(), "it waits for the text"
    if rules is not None:
        assert len(table.sheet.cond_formats) == rules
    dialog.reject()


def test_whiteout_and_crop_bars_wear_no_style(win):
    for key in ("whiteout", "crop"):
        win.select_tool(key)
        pump()
        assert not win.width_spin.isEnabled(), key


# ---------------------------------------------------------------------------
# F-37: dark mode
# ---------------------------------------------------------------------------

def test_the_font_colour_shows_on_white_in_either_theme(win):
    from calcforge.ui.datatools import _FormatPicker
    picker = _FormatPicker({"fill": "#ffc7ce", "color": "#9c0006"})
    assert "background:#ffffff" in picker.color_button.styleSheet()
    assert "#9c0006" in picker.color_button.styleSheet()


def test_dark_greyed_words_read_on_charcoal():
    from PySide6.QtGui import QColor
    from calcforge import theme

    def luminance(colour):
        def channel(c):
            c /= 255
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        shade = QColor(colour)
        return (0.2126 * channel(shade.red()) + 0.7152 * channel(shade.green())
                + 0.0722 * channel(shade.blue()))
    values = theme.tokens(theme.DARK)
    faint, ground = luminance(values["ink_faint"]), luminance(values["surface"])
    assert (faint + 0.05) / (ground + 0.05) >= 4.5


# ---------------------------------------------------------------------------
# the user, 2026-10-16: a markup style's text look is what is drawn
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind, key", [("text", Qt.Key_T), ("callout", Qt.Key_Q)])
@pytest.mark.parametrize("how", ["keys", "button"])
def test_a_markup_styles_text_look_is_drawn(win, kind, key, how):
    from calcforge.ui import markupstyles
    from calcforge.ui.tools import TOOL_MAP
    from tests.test_usability import type_text
    ex().look_at(win)
    markupstyles.set_styles_for(kind, [])
    (first,) = ex().draw(win, kind, text="Plain")
    ex().pick(win, [first])
    for name in ("bold", "italic", "underline"):
        QTest.mouseClick(win.font_buttons[name], Qt.LeftButton)
    win.text_colour_button.colorChanged.emit("#2f9e44")
    type_into(win.font_spin.lineEdit(), "16")
    win.text_align_combo.setCurrentText("center")
    pump()
    number = win.markup_styles.save_markup(first)
    assert number == 1
    win.view.scene().clearSelection()
    win.select_tool("select")
    pump()
    if how == "keys":
        win.view.setFocus()
        QTest.keyClick(win.view, key)          # the tool
        QTest.keyClick(win.view, Qt.Key_1)     # its style 1
    else:
        win.select_tool(kind)
        pump()
        button = [b for b in win.markup_styles.bar.findChildren(markupstyles.StyleButton)][1]
        QTest.mouseClick(button, Qt.LeftButton, Qt.NoModifier, button.rect().center())
    pump()
    assert win.view.tool_key == kind and win.view.markup_style == 1
    before = {id(i) for i in ex().markups(win)}
    ex().gesture(win, None, TOOL_MAP[kind].mode, (100, 300), (260, 360))
    if win.view.editing_item() is not None:
        type_text(win.view, "Styled words")
    pump()
    (new,) = [i for i in ex().markups(win) if id(i) not in before]
    cursor = QTextCursor(new.doc)
    cursor.setPosition(3)
    font = cursor.charFormat().font()
    assert font.bold() and font.italic() and font.underline()
    assert new.style.font_size == pytest.approx(16)
    assert new.style.text_color.lower() == "#2f9e44"
    assert new.style.align == "center"
    assert new.doc.defaultTextOption().alignment() & Qt.AlignHCenter


# ---------------------------------------------------------------------------
# the user, 2026-10-16: an equation's variable settings first
# ---------------------------------------------------------------------------

def test_a_definitions_menu_starts_with_its_variable_settings(win):
    from calcforge.calc.engine.display import display_text
    from tests.test_calc_panels import an_equation
    ex().look_at(win)
    definition = an_equation(win, "x:2/3")
    shown = an_equation(win, "x=", y=200)
    win.toggle_calc_mode(False)
    menu = win.build_context_menu(definition, definition.sceneBoundingRect().center())
    first = [a.text() for a in menu.actions()][:3]
    assert first == ["Decimal Places", "Significant Figures",
                     "Global"]
    equation = next(a.menu() for a in menu.actions() if a.text() == "Equation")
    assert "Decimal places" not in [a.text() for a in equation.actions()], "moved, not copied"
    places = menu.actions()[0].menu()
    next(a for a in places.actions() if a.text().rstrip(" *") == "2").trigger()
    pump()
    menu = win.build_context_menu(shown, shown.sceneBoundingRect().center())
    places = menu.actions()[0].menu()
    next(a for a in places.actions() if a.text().rstrip(" *") == "2").trigger()
    pump()
    (_, again) = sorted(ex().equations(win), key=lambda i: i.pos().y())
    assert display_text(again.region.display) == "0.67"
    undo_key(win)
    (_, again) = sorted(ex().equations(win), key=lambda i: i.pos().y())
    assert display_text(again.region.display) == "0.6667"


def test_the_choose_values_filter_has_select_all(win):
    from PySide6.QtWidgets import QCheckBox
    from calcforge.ui.datatools import ValuesDialog
    from tests.test_tables import make_table, type_text, enter
    table = make_table(win)
    tables = win.view.tables
    tables.open(table)
    for row, word in enumerate(("Beam", "Joist", "Post")):
        tables.select((row, 0))
        type_text(win, word)
        enter(win)
    tables.select((0, 0))
    from calcforge.ui.datatools import toggle_filter
    toggle_filter(tables)                       # Data ▸ Filter, then the arrow's list
    dialog = ValuesDialog(tables, 0)
    dialog.show()
    every = dialog.findChild(QCheckBox, "filterSelectAll")
    assert every.checkState() == Qt.Checked
    box = QPoint(7, every.height() // 2)          # on its tick box
    QTest.mouseClick(every, Qt.LeftButton, Qt.NoModifier, box)
    assert all(dialog.list.item(i).checkState() == Qt.Unchecked
               for i in range(dialog.list.count()))
    QTest.mouseClick(every, Qt.LeftButton, Qt.NoModifier, box)
    assert all(dialog.list.item(i).checkState() == Qt.Checked
               for i in range(dialog.list.count()))
    dialog.reject()


def test_top_10_asks_before_it_filters(win):
    from calcforge.ui.datatools import filter_menu, toggle_filter
    from tests.test_tables import make_table, type_text, enter
    table = make_table(win)
    tables = win.view.tables
    tables.open(table)
    for row, word in enumerate(("Load", "3", "5", "4")):
        tables.select((row, 0))
        type_text(win, word)
        enter(win)
    tables.select((0, 0))
    toggle_filter(tables)
    win.interactive_prompts = True

    def bottom_two(dialog):
        dialog.which.setCurrentIndex(1)
        dialog.count.setValue(2)
    answer_next_dialog("OK", bottom_two)
    menu = filter_menu(tables, 0, None)
    next(a for a in menu.actions() if a.text() == "Top 10\u2026").trigger()
    pump()
    crit = table.sheet.filter["criteria"][0]
    assert crit == {"kind": "top", "n": 2, "bottom": True}
