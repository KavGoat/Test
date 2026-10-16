"""Markup styles (the user's design, 2026-10-15).

Pick a tool, press 1 and the next markup is drawn in that tool's style 1; it
is back to the default after that one. Styles live in the app's settings,
are shown on the Markup Styles toolbar for the tool in hand, and are edited
like Revu's Properties Mode: click one and the Properties toolbar and panel
change it. The number keys never take a digit from something being typed.

Keys go through QTest.keyClick on the canvas, so Qt's shortcut map sees them
as it sees a real keyboard.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from calcforge.items.shapes import RectItem
from calcforge.items.text import CalloutItem, TextItem
from calcforge.ui import markupstyles, preferences
from calcforge.ui.markupstyles import MarkupStyle
from tests.test_revu_keys import _type_into_a_text_box, pump, win  # noqa: F401
from tests.test_usability import click, drag, on_page, only

RED, GREEN = "#ff0000", "#00aa00"


def press(win, k, mods=Qt.NoModifier):
    QTest.keyClick(win.view.viewport(), k, mods)
    pump()


def look(win, key, **style):
    """A style payload for *key*: its default look with *style* changed."""
    item = win.markup_styles.sample(key)
    for name, value in style.items():
        setattr(item.style, name, value)
    return markupstyles.payload_of(item)


def define(win, key, *looks):
    markupstyles.set_styles_for(
        key, [MarkupStyle(f"Look {n}", payload) for n, payload in enumerate(looks, 1)])
    win.markup_styles.bar.refresh(force=True)


def draw_rect(win, x=100, y=150):
    drag(win.view, *on_page(win, 0, x, y), *on_page(win, 0, x + 120, y + 80))
    pump()
    return only(win, RectItem)[-1]


def bar_numbers(win):
    return [b.number for b in win.markup_styles.bar.buttons]


# -- drawing --------------------------------------------------------------------

def test_r_then_1_draws_style_1_and_the_next_one_is_the_default(win):
    define(win, "rect", look(win, "rect", stroke=RED, width=5.0))
    press(win, Qt.Key_R)
    assert win.view.tool_key == "rect"
    press(win, Qt.Key_1)
    assert win.view.markup_style == 1
    assert win.markup_styles.bar.buttons[1].isChecked()
    undo_before = win.undo_stack.count()
    styled = draw_rect(win)
    assert styled.style.stroke.lower() == RED and styled.style.width == 5.0
    assert win.undo_stack.count() == undo_before + 1, "one undo step for the drawing"
    assert win.view.markup_style == 0
    assert win.markup_styles.bar.buttons[0].isChecked()

    press(win, Qt.Key_Escape)
    press(win, Qt.Key_R)
    plain = draw_rect(win, y=300)
    assert plain.style.stroke.lower() != RED and plain.style.width != 5.0

    win.act_undo.trigger()
    pump()
    assert len(only(win, RectItem)) == 1


def test_a_held_tool_goes_back_to_the_default_after_each_markup(win):
    define(win, "rect", look(win, "rect", stroke=RED))
    win.toggle_sticky(True)
    press(win, Qt.Key_R)
    press(win, Qt.Key_1)
    first = draw_rect(win)
    assert win.view.tool_key == "rect"
    second = draw_rect(win, y=300)
    assert first.style.stroke.lower() == RED
    assert second.style.stroke.lower() != RED
    # 1 again for the next one; the letter again, or 0, is the default
    press(win, Qt.Key_1)
    assert win.view.markup_style == 1
    press(win, Qt.Key_R)
    assert win.view.markup_style == 0 and win.view.tool_key == "rect"
    press(win, Qt.Key_1)
    press(win, Qt.Key_0)
    assert win.view.markup_style == 0
    press(win, Qt.Key_1)
    press(win, Qt.Key_Escape)
    assert win.view.markup_style == 0
    win.toggle_sticky(False)


def test_q_then_1_draws_a_callout_in_style_1_and_digits_then_type(win):
    define(win, "callout", look(win, "callout", stroke=GREEN, width=3.0))
    press(win, Qt.Key_Q)
    press(win, Qt.Key_1)
    assert win.view.markup_style == 1
    click(win.view, *on_page(win, 0, 120, 200))
    pump()
    click(win.view, *on_page(win, 0, 300, 120))
    pump()
    callout = only(win, CalloutItem)[-1]
    assert callout.style.stroke.lower() == GREEN and callout.style.width == 3.0
    assert win.view.is_editing() and win.view.markup_style == 0
    QTest.keyClicks(win.view.viewport(), "12")
    pump()
    assert win.view._editing_item._editor.toPlainText().endswith("12")


def test_an_undefined_style_does_nothing(win):
    define(win, "rect", look(win, "rect", stroke=RED))
    press(win, Qt.Key_R)
    press(win, Qt.Key_2)
    assert win.view.markup_style == 0 and win.view.tool_key == "rect"
    assert "no style 2" in win.status_hint.text()
    plain = draw_rect(win)
    assert plain.style.stroke.lower() != RED


def test_digits_still_type_into_a_text_box(win):
    define(win, "text", look(win, "text", stroke=RED))
    editor = _type_into_a_text_box(win)
    QTest.keyClicks(win.view.viewport(), "123")
    pump()
    assert editor.toPlainText().endswith("123")
    assert win.view.markup_style == 0


def test_the_preference_turns_the_number_keys_off(win):
    define(win, "rect", look(win, "rect", stroke=RED))
    prefs = preferences.current()
    prefs.markup_style_keys = False
    try:
        press(win, Qt.Key_R)
        press(win, Qt.Key_1)
        assert win.view.markup_style == 0
        # the toolbar still works
        win.markup_styles.bar.buttons[1].click()
        assert win.view.markup_style == 1
    finally:
        prefs.markup_style_keys = True
        preferences.forget()


def test_the_preferences_dialog_has_the_tick(win):
    from calcforge.ui.dialogs import PreferencesDialog
    dialog = PreferencesDialog(preferences.current(), win)
    assert dialog.style_keys.text() == "Number keys pick markup styles"
    assert dialog.style_keys.isChecked()
    dialog.style_keys.setChecked(False)
    assert dialog.result_preferences().markup_style_keys is False
    dialog.deleteLater()


# -- the toolbar ----------------------------------------------------------------

def test_the_toolbar_follows_the_tool_in_hand(win):
    define(win, "rect", look(win, "rect", stroke=RED), look(win, "rect", stroke=GREEN))
    define(win, "callout", look(win, "callout", stroke=GREEN))
    bar = win.markup_styles.bar
    press(win, Qt.Key_R)
    assert "Rectangle" in bar.title.text() and bar_numbers(win) == [0, 1, 2]
    assert not bar.buttons[1].icon().isNull()
    assert "Look 1" in bar.buttons[1].toolTip() and "1" in bar.buttons[1].toolTip()
    win.select_tool("callout")
    assert "Callout" in bar.title.text() and bar_numbers(win) == [0, 1]
    win.select_tool("pan")
    assert bar.buttons == []
    hints = [w for w in bar.findChildren(QWidget) if w.objectName() == "markupStylesHint"]
    assert hints and not hints[-1].isEnabled()
    # Select in hand, a rectangle selected: the rectangle's styles
    win.select_tool("rect")
    item = draw_rect(win)
    win.select_tool("select")
    win.view.scene().clearSelection()
    item.setSelected(True)
    win.view.selectionChanged.emit()
    pump()
    assert bar_numbers(win) == [0, 1, 2]
    # clicking a style picks the tool up with that style
    bar.buttons[2].click()
    pump()
    assert win.view.tool_key == "rect" and win.view.markup_style == 2


def test_the_toolbar_is_in_tools_toolbars(win):
    bar = win.markup_styles.bar
    menus = [m for m in win.findChildren(QMenu) if m.title() == "Toolbars"]
    assert any(bar.toggleViewAction() in m.actions() for m in menus)
    assert bar.toggleViewAction().text() == "Markup Styles"
    bar.toggleViewAction().trigger()
    assert not bar.isVisible()
    bar.toggleViewAction().trigger()
    assert bar.isVisible()


def test_plus_saves_the_current_look_and_the_style_bar_edits_it(win):
    press(win, Qt.Key_R)
    before = win.default_style.stroke
    win.markup_styles.bar.add_button.click()
    pump()
    assert len(markupstyles.styles_for("rect")) == 1
    assert win.view.markup_style == 1, "the new style is the one being edited"
    win._style_stroke(RED)
    win._style_width(4.0)
    stored = markupstyles.styles_for("rect")[0].payload["style"]
    assert stored["stroke"].lower() == RED and stored["width"] == 4.0
    assert win.default_style.stroke == before, "the default look is untouched"
    assert win.stroke_button.color().lower() == RED
    # and the Properties panel edits it too, outside the document's undo
    panel = win.properties_panel
    assert panel._style_edit is not None and "Style 1" in panel._style_title
    undo_before = win.undo_stack.count()
    panel._apply(lambda item: setattr(item.style, "stroke", GREEN), "Line colour")
    assert markupstyles.styles_for("rect")[0].payload["style"]["stroke"].lower() == GREEN
    assert win.undo_stack.count() == undo_before
    assert draw_rect(win).style.stroke.lower() == GREEN


def test_styles_survive_a_new_window(win, qapp):
    define(win, "rect", look(win, "rect", stroke=RED))
    from calcforge.ui.mainwindow import MainWindow
    second = MainWindow()
    try:
        second.select_tool("rect")
        second.markup_styles.bar.refresh(force=True)
        assert [b.number for b in second.markup_styles.bar.buttons] == [0, 1]
        assert markupstyles.styles_for("rect")[0].payload["style"]["stroke"].lower() == RED
    finally:
        second.confirm_discard = lambda: True
        second.document.modified = False
        second.close()
        second.deleteLater()


def test_rename_update_remove_and_reorder(win):
    define(win, "rect", look(win, "rect", stroke=RED), look(win, "rect", stroke=GREEN),
           look(win, "rect", stroke="#0000ff"))
    styles = win.markup_styles
    press(win, Qt.Key_R)
    menu = styles.build_menu(1)
    assert [a.text() for a in menu.actions() if a.text()] == [
        "Rename…", "Update from Selected Markup", "Remove", "Move Left", "Move Right"]
    assert not menu.actions()[3 + 1].isEnabled(), "style 1 cannot move left"
    menu.deleteLater()

    assert styles.rename(2, "Green")
    assert markupstyles.styles_for("rect")[1].name == "Green"

    assert styles.move(1, 1)          # red goes after green
    assert [s.name for s in markupstyles.styles_for("rect")] == ["Green", "Look 1", "Look 3"]
    press(win, Qt.Key_3)
    assert styles.move_to(3, 1)       # the held style keeps being held
    assert win.view.markup_style == 1
    assert [s.name for s in markupstyles.styles_for("rect")] == ["Look 3", "Green", "Look 1"]

    assert styles.remove(2)
    assert [s.name for s in markupstyles.styles_for("rect")] == ["Look 3", "Look 1"]
    assert bar_numbers(win) == [0, 1, 2]

    # Update from Selected Markup takes a selected rectangle's look
    item = draw_rect(win)
    win.select_tool("select")
    win.view.scene().clearSelection()
    item.setSelected(True)
    item.style.stroke = "#123456"
    menu = styles.build_menu(2)
    assert menu.actions()[1].isEnabled()
    menu.actions()[1].trigger()        # Update from Selected Markup
    menu.deleteLater()
    assert markupstyles.styles_for("rect")[1].payload["style"]["stroke"] == "#123456"


def test_a_style_can_be_dragged_along_the_bar(win):
    define(win, "rect", look(win, "rect", stroke=RED), look(win, "rect", stroke=GREEN))
    press(win, Qt.Key_R)
    bar = win.markup_styles.bar
    pump()
    first, second = bar.buttons[1], bar.buttons[2]
    start = first.rect().center()
    end = first.mapFromGlobal(second.mapToGlobal(second.rect().center()))
    QTest.mousePress(first, Qt.LeftButton, Qt.NoModifier, start)
    for point in (start + QPoint(6, 0), end):
        QApplication.sendEvent(first, QMouseEvent(
            QEvent.MouseMove, QPointF(point), QPointF(first.mapToGlobal(point)),
            Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
    QTest.mouseRelease(first, Qt.LeftButton, Qt.NoModifier, end)
    pump()
    assert [s.name for s in markupstyles.styles_for("rect")] == ["Look 2", "Look 1"]


def test_style_previews_read_in_both_themes(win):
    """Each preview is drawn on its own scrap of white paper, so a black line
    shows on the dark bar as well as the light one."""
    define(win, "rect", look(win, "rect", stroke="#000000"))
    image = markupstyles.preview_pixmap(markupstyles.styles_for("rect")[0].payload).toImage()
    middle = image.pixelColor(image.width() // 2, 4)
    assert middle.lightness() > 200 and middle.alpha() == 255
    dark = [image.pixelColor(x, y) for x in range(image.width())
            for y in range(image.height())]
    assert any(c.lightness() < 130 and c.alpha() > 200 for c in dark), "the line shows"


def test_no_number_key_in_calc_mode(win):
    define(win, "rect", look(win, "rect", stroke=RED))
    win.select_tool("rect")
    win.toggle_calc_mode(True)
    try:
        press(win, Qt.Key_1)
        assert win.view.markup_style == 0
    finally:
        win.toggle_calc_mode(False)
    assert isinstance(QApplication.instance(), QApplication)


def test_text_tool_styles_apply_to_a_text_box(win):
    define(win, "text", look(win, "text", text_color=RED, font_size=20.0))
    press(win, Qt.Key_T)
    press(win, Qt.Key_1)
    drag(win.view, *on_page(win, 0, 100, 140), *on_page(win, 0, 400, 200))
    pump()
    box = only(win, TextItem)[-1]
    assert box.style.text_color.lower() == RED and box.style.font_size == 20.0
