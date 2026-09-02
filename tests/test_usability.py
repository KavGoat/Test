"""Interaction tests driven by the events Qt actually sends.

Everything here goes through the viewport as a real pointer or keyboard would:
press/release pairs, the four-event double-click sequence, context-menu events,
and key presses with their text.  Calling a handler directly would hide exactly
the bugs this file exists to catch.
"""
import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QContextMenuEvent, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication

from calcforge.core.document import MM_TO_PT
from calcforge.items.mathitem import MathItem
from calcforge.items.measure import DIMENSION, MeasureItem
from calcforge.items.shapes import PolyItem, RectItem
from calcforge.items.tableitem import TableItem
from calcforge.items.text import CalloutItem, TextItem


# ---------------------------------------------------------------------------
# input helpers — everything is posted to the viewport, like a real pointer
# ---------------------------------------------------------------------------

def _mouse(view, kind, x, y, button=Qt.LeftButton, buttons=None, modifiers=Qt.NoModifier):
    local = view.mapFromScene(QPointF(x, y))
    globally = view.viewport().mapToGlobal(local)
    if buttons is None:
        buttons = button if kind != QEvent.MouseButtonRelease else Qt.NoButton
    return QMouseEvent(kind, QPointF(local), QPointF(globally), button, buttons, modifiers)


def hover(view, x, y):
    QApplication.sendEvent(view.viewport(),
                           _mouse(view, QEvent.MouseMove, x, y, Qt.NoButton, Qt.NoButton))


def click(view, x, y, button=Qt.LeftButton, modifiers=Qt.NoModifier):
    for kind in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
        QApplication.sendEvent(view.viewport(),
                               _mouse(view, kind, x, y, button, modifiers=modifiers))


def double_click(view, x, y):
    for kind in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease,
                 QEvent.MouseButtonDblClick, QEvent.MouseButtonRelease):
        QApplication.sendEvent(view.viewport(), _mouse(view, kind, x, y))


def drag(view, x0, y0, x1, y1, modifiers=Qt.NoModifier):
    QApplication.sendEvent(view.viewport(),
                           _mouse(view, QEvent.MouseButtonPress, x0, y0, modifiers=modifiers))
    for step in (0.34, 0.67, 1.0):
        QApplication.sendEvent(view.viewport(), _mouse(
            view, QEvent.MouseMove, x0 + (x1 - x0) * step, y0 + (y1 - y0) * step,
            Qt.NoButton, Qt.LeftButton, modifiers))
    QApplication.sendEvent(view.viewport(),
                           _mouse(view, QEvent.MouseButtonRelease, x1, y1,
                                  modifiers=modifiers))


def right_click(view, x, y):
    local = view.mapFromScene(QPointF(x, y))
    QApplication.sendEvent(view, QContextMenuEvent(
        QContextMenuEvent.Mouse, local, view.viewport().mapToGlobal(local)))


def press_key(view, key, text="", modifiers=Qt.NoModifier):
    QApplication.sendEvent(view, QKeyEvent(QEvent.KeyPress, key, modifiers, text))


def type_text(view, text):
    for character in text:
        press_key(view, Qt.Key_unknown, character)


def markups(window):
    return window.view.scene().ordered_markups()


def only(window, kind):
    return [i for i in markups(window) if isinstance(i, kind)]


# ---------------------------------------------------------------------------
# pointer
# ---------------------------------------------------------------------------

def test_hovering_a_markup_changes_the_cursor(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 220, 200)
    window.select_tool("select")
    hover(window.view, 160, 150)
    assert window.view.cursor().shape() == Qt.SizeAllCursor
    hover(window.view, 500, 600)
    assert window.view.cursor().shape() == Qt.ArrowCursor


def test_click_selects_and_click_away_deselects(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 220, 200)
    window.select_tool("select")
    click(window.view, 160, 150)
    assert len(window.selected_items()) == 1
    click(window.view, 500, 600)
    assert window.selected_items() == []


def test_shift_click_adds_to_the_selection(window):
    for x in (100, 300):
        window.select_tool("rect")
        drag(window.view, x, 100, x + 90, 190)
    window.select_tool("select")
    click(window.view, 145, 145)
    click(window.view, 345, 145, modifiers=Qt.ShiftModifier)
    assert len(window.selected_items()) == 2


def test_dragging_moves_a_markup(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 220, 200)
    window.select_tool("select")
    item = markups(window)[0]
    origin = item.pos()
    drag(window.view, 160, 150, 260, 250)
    assert item.pos().x() == pytest.approx(origin.x() + 100, abs=2)


def test_right_click_offers_a_menu_for_the_item_under_it(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 220, 200)
    window.select_tool("select")
    menu = window.build_context_menu(markups(window)[0], QPointF(160, 150))
    labels = [a.text() for a in menu.actions() if a.text()]
    assert "Cut" in labels and "Duplicate" in labels
    assert any("offset" in label for label in labels)


def test_right_click_on_empty_paper_offers_insertions(window):
    menu = window.build_context_menu(None, QPointF(400, 400))
    assert any("Insert here" in a.text() for a in menu.actions() if a.text())


# ---------------------------------------------------------------------------
# keyboard
# ---------------------------------------------------------------------------

def test_arrows_nudge_a_selected_markup(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 220, 200)
    window.select_tool("select")
    item = markups(window)[0]
    click(window.view, 160, 150)
    origin = item.pos()
    press_key(window.view, Qt.Key_Right)
    press_key(window.view, Qt.Key_Down)
    assert item.pos().x() > origin.x() and item.pos().y() > origin.y()


def test_backspace_deletes_the_selection(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 220, 200)
    window.select_tool("select")
    click(window.view, 160, 150)
    press_key(window.view, Qt.Key_Backspace)
    assert markups(window) == []


def test_backspace_edits_text_rather_than_deleting_the_markup(window):
    window.select_tool("text")
    drag(window.view, 100, 100, 300, 140)
    box = window.view.editing_item()
    box.set_text("abcd")
    from PySide6.QtGui import QTextCursor
    cursor = box._editor.textCursor()
    cursor.movePosition(QTextCursor.End)
    box._editor.setTextCursor(cursor)
    press_key(window.view, Qt.Key_Backspace)
    assert box.text() == "abc"
    assert box in markups(window)


def test_enter_opens_the_next_calculation_line(window):
    window.view._last_scene_pos = QPointF(100, 100)
    press_key(window.view, Qt.Key_unknown, "\\")
    first = window.view.editing_item()
    type_text(window.view, "L = 6 m")
    press_key(window.view, Qt.Key_Return)
    second = window.view.editing_item()
    assert second is not first
    type_text(window.view, "w = 2 kN/m")
    window.view.end_item_edit()
    workspace = window.document.workspace
    assert workspace.get("L").to("m").magnitude == pytest.approx(6)
    assert workspace.get("w").to("kN/m").magnitude == pytest.approx(2)


def test_escape_leaves_editing_then_returns_to_select(window):
    window.select_tool("math")
    drag(window.view, 100, 100, 260, 130)
    window.view.editing_item()._editor.setPlainText("a = 1 m")
    press_key(window.view, Qt.Key_Escape)
    assert window.view.editing_item() is None
    window.select_tool("rect")
    press_key(window.view, Qt.Key_Escape)
    assert window.view.tool_key == "select"


# ---------------------------------------------------------------------------
# shortcuts, exactly as specified
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("character, tool_key", [
    ("c", "cloud"), ("r", "rect"), ("p", "polygon"), ("a", "arrow"),
    ("m", "measure_length"), ("q", "callout"), ("t", "text"), ("e", "ellipse"),
    ("l", "line"), ("k", "highlighter"), ("s", "stamp"), ("b", "table"),
])
def test_letter_keys_pick_their_tool(window, character, tool_key):
    window.select_tool("select")
    window.view._last_scene_pos = QPointF(200, 200)
    press_key(window.view, Qt.Key_unknown, character)
    assert window.view.tool_key == tool_key


def test_modifier_shortcuts_are_bound_where_asked(window):
    sequences = {binding.action_id: window.shortcuts.sequence(binding.action_id)
                 for binding in window.shortcuts.bindings()}
    assert sequences["tool.measure_dimension"] == "Alt+M"
    assert sequences["tool.measure_area"] == "Shift+Alt+A"
    assert sequences["tool.measure_length"] == "M"
    assert sequences["tool.polygon"] == "P"
    assert sequences["tool.callout"] == "Q"
    assert sequences["tool.cloud"] == "C"
    assert sequences["tool.rect"] == "R"
    assert sequences["tool.arrow"] == "A"
    assert window.shortcuts.conflicts() == {}


def test_the_modifier_tools_are_reachable_from_their_actions(window):
    window.tool_actions["measure_area"].trigger()
    assert window.view.tool_key == "measure_area"
    window.tool_actions["measure_dimension"].trigger()
    assert window.view.tool_key == "measure_dimension"


def test_q_draws_a_callout_with_a_leader(window):
    window.select_tool("select")
    window.view._last_scene_pos = QPointF(200, 200)
    press_key(window.view, Qt.Key_unknown, "q")
    drag(window.view, 200, 200, 360, 250)
    callout = only(window, CalloutItem)[0]
    assert len(callout.leader) >= 2
    assert window.view.editing_item() is callout


# ---------------------------------------------------------------------------
# scale, and which tools use it
# ---------------------------------------------------------------------------

def scaled_page(window, ratio=50):
    from calcforge.core.document import PageScale
    window.current_page().scale = PageScale.from_ratio(ratio)
    return window.current_page()


def test_a_page_starts_without_a_scale_and_can_be_given_one(window):
    page = window.current_page()
    assert not page.scale.is_calibrated()
    window.select_tool("measure_length")
    drag(window.view, 100, 400, 300, 400)
    assert "no scale" in window.status_hint.text()

    scaled_page(window)
    window.current_page().scene.refresh_items()
    measure = only(window, MeasureItem)[0]
    assert measure.value.to("m").magnitude == pytest.approx(3.53, rel=2e-2)


def test_length_and_area_read_real_dimensions(window):
    page = scaled_page(window)
    window.select_tool("measure_length")
    drag(window.view, 100, 400, 236, 400)          # 136 pt = 2.4 m at 1:50
    length = only(window, MeasureItem)[0]
    assert length.value.to("m").magnitude == pytest.approx(2.4, rel=2e-2)

    window.select_tool("measure_area")
    for x, y in ((100, 500), (236, 500), (236, 636), (100, 636)):
        click(window.view, x, y)
        hover(window.view, x, y)
    window.view.finish_poly()
    area = [i for i in only(window, MeasureItem) if i.kind == "area"][0]
    assert area.value.to("m**2").magnitude == pytest.approx(5.76, rel=3e-2)


def test_a_rectangle_reports_its_real_size_and_accepts_an_exact_one(window):
    page = scaled_page(window)
    window.select_tool("rect")
    drag(window.view, 100, 100, 236, 168)
    rect = only(window, RectItem)[0]
    assert "2.40 m" in rect.size_text

    assert rect.set_real_size("3 m", "1.5 m", page)
    assert rect.size_text == "3.00 m × 1.50 m"
    assert rect.local_rect().width() == pytest.approx(3000 / (50 * 25.4 / 72), rel=1e-6)


def test_a_polygon_is_not_scaled(window):
    scaled_page(window)
    window.select_tool("polygon")
    for x, y in ((100, 400), (220, 400), (160, 500)):
        click(window.view, x, y)
        hover(window.view, x, y)
    window.view.finish_poly()
    polygon = only(window, PolyItem)[0]
    assert polygon.kind == "polygon"
    assert not hasattr(polygon, "size_text")


def test_a_dimension_carries_its_own_text(window):
    scaled_page(window)
    window.select_tool("measure_dimension")
    drag(window.view, 100, 400, 236, 400)
    dimension = only(window, MeasureItem)[0]
    assert dimension.kind == DIMENSION
    assert dimension.measured_text.startswith("2.4")
    dimension.custom_label = "2 no. @ 300 c/c"
    dimension.refresh(page=window.current_page())
    assert dimension.value_text == "2 no. @ 300 c/c"
    dimension.custom_label = ""
    dimension.refresh(page=window.current_page())
    assert dimension.value_text == dimension.measured_text


def test_the_rectangle_prompt_only_appears_on_a_scaled_page(window, monkeypatch):
    from calcforge.ui import dialogs
    asked = []
    monkeypatch.setattr(dialogs.RectangleSizeDialog, "exec",
                        lambda self: asked.append(True) or dialogs.QDialog.Rejected)
    window.interactive_prompts = True

    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 180)
    assert asked == []                      # markup on an unscaled page: no nagging

    scaled_page(window)
    window.select_tool("rect")
    drag(window.view, 300, 100, 400, 180)
    assert asked == [True]


def test_a_rectangle_shows_its_paper_size_without_a_scale(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 100 + 4 * MM_TO_PT * 10, 100 + 2 * MM_TO_PT * 10)
    rect = only(window, RectItem)[0]
    assert rect.show_size
    assert rect.width_value.to("mm").magnitude == pytest.approx(40, abs=0.5)
    assert rect.height_value.to("mm").magnitude == pytest.approx(20, abs=0.5)
    assert "mm × " in rect.size_text


def test_an_exact_size_can_be_asked_for_from_the_right_click_menu(window, monkeypatch):
    from calcforge.ui import dialogs
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 180)
    window.select_tool("select")
    rect = only(window, RectItem)[0]
    rect.setSelected(True)

    menu = window.build_context_menu(rect, QPointF(150, 140))
    assert "Set exact size…" in [a.text() for a in menu.actions() if a.text()]

    monkeypatch.setattr(dialogs.RectangleSizeDialog, "exec",
                        lambda self: dialogs.QDialog.Accepted)
    monkeypatch.setattr(dialogs.RectangleSizeDialog, "values",
                        lambda self: ("50 mm", "25 mm"))
    window.set_rectangle_size(rect)
    assert rect.size_text == "50.0 mm × 25.0 mm"
    assert rect.local_rect().width() == pytest.approx(50 * MM_TO_PT, rel=1e-6)


def test_a_scale_turns_the_paper_size_into_a_real_one(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 236, 168)
    rect = only(window, RectItem)[0]
    assert "mm" in rect.size_text
    scaled_page(window)
    window.current_page().scene.refresh_items()
    assert "2.40 m" in rect.size_text


# ---------------------------------------------------------------------------
# move and duplicate by an offset
# ---------------------------------------------------------------------------

def test_duplicate_along_an_offset(window, monkeypatch):
    from calcforge.ui import dialogs
    scaled_page(window)
    window.select_tool("rect")
    drag(window.view, 100, 100, 160, 160)
    window.select_tool("select")
    original = only(window, RectItem)[0]
    original.setSelected(True)

    monkeypatch.setattr(dialogs.ArrayDialog, "exec", lambda self: dialogs.QDialog.Accepted)
    monkeypatch.setattr(dialogs.ArrayDialog, "offsets", lambda self: ("3 m", "0", 4, True))
    window.array_selection()

    rectangles = sorted(only(window, RectItem), key=lambda i: i.pos().x())
    assert len(rectangles) == 5
    step = 3000 / (50 * 25.4 / 72)
    for index, item in enumerate(rectangles):
        assert item.pos().x() == pytest.approx(original.pos().x() + index * step, abs=0.5)


def test_move_by_an_offset_leaves_no_copies(window, monkeypatch):
    from calcforge.ui import dialogs
    scaled_page(window)
    window.select_tool("rect")
    drag(window.view, 100, 100, 160, 160)
    window.select_tool("select")
    rect = only(window, RectItem)[0]
    rect.setSelected(True)
    origin = rect.pos()

    monkeypatch.setattr(dialogs.ArrayDialog, "exec", lambda self: dialogs.QDialog.Accepted)
    monkeypatch.setattr(dialogs.ArrayDialog, "offsets", lambda self: ("0", "2 m", 1, False))
    window.array_selection()

    assert len(only(window, RectItem)) == 1
    assert rect.pos().y() == pytest.approx(origin.y() + 2000 / (50 * 25.4 / 72), abs=0.5)


def test_offsets_are_paper_distances_without_a_scale(window):
    from calcforge.core.document import MM_TO_PT
    page = window.current_page()
    assert window.distance_in_points("25 mm", page) == pytest.approx(25 * MM_TO_PT)
    assert window.distance_in_points("0", page) == 0.0
    with pytest.raises(ValueError):
        window.distance_in_points("banana", page)


def test_offsets_follow_the_page_scale(window):
    page = scaled_page(window)
    assert window.distance_in_points("3 m", page) == pytest.approx(
        3000 / (50 * 25.4 / 72), rel=1e-6)


# ---------------------------------------------------------------------------
# modifier chords
# ---------------------------------------------------------------------------

def test_modifier_tool_shortcuts_are_registered_on_their_actions(window):
    assert window.tool_actions["measure_dimension"].shortcut().toString() == "Alt+M"
    assert window.tool_actions["measure_area"].shortcut().toString() == "Alt+Shift+A"
    # Single characters are the canvas's job, so they carry no action shortcut.
    for key in ("rect", "cloud", "callout", "arrow", "polygon", "measure_length"):
        assert window.tool_actions[key].shortcut().isEmpty()


def test_no_menu_mnemonic_shadows_a_tool_chord(window):
    """Alt+M on a menu title would make the dimension shortcut ambiguous."""
    from PySide6.QtGui import QKeySequence

    mnemonics = set()
    for action in window.menuBar().actions():
        title = action.text()
        index = title.find("&")
        if index != -1 and index + 1 < len(title):
            mnemonics.add(f"Alt+{title[index + 1].upper()}")

    for key, action in window.tool_actions.items():
        sequence = action.shortcut().toString()
        if sequence:
            assert sequence not in mnemonics, f"{key} is shadowed by a menu"
    assert "Alt+M" not in mnemonics


def test_changing_the_page_scale_updates_the_takeoff_list(window, monkeypatch):
    """A rectangle's size is in the markups list, so it has to be rebuilt."""
    from calcforge.core.document import PageScale
    from calcforge.ui import dialogs

    window.select_tool("rect")
    drag(window.view, 100, 100, 236, 168)
    window.select_tool("select")

    def sizes():
        panel = window.markups_panel
        return [panel.tree.topLevelItem(0).child(i).text(3)
                for i in range(panel.tree.topLevelItem(0).childCount())]

    window.refresh_lists()
    assert any("mm" in text for text in sizes())

    monkeypatch.setattr(dialogs.ScaleDialog, "exec",
                        lambda self: dialogs.QDialog.Accepted)
    monkeypatch.setattr(dialogs.ScaleDialog, "result_scale",
                        lambda self: PageScale.from_ratio(50))
    window.calibrate_dialog()
    assert any("2.4" in text and "m" in text for text in sizes())


# ---------------------------------------------------------------------------
# things found by driving the app at random for a long time
# ---------------------------------------------------------------------------

def test_the_scene_does_not_index_items_it_keeps_reshaping(window):
    """A bounding rect that changes behind Qt's index is a crash, not a glitch."""
    from PySide6.QtWidgets import QGraphicsScene

    for page in window.document.pages:
        assert page.scene.itemIndexMethod() == QGraphicsScene.NoIndex


def test_a_markup_is_removed_from_the_scene_it_is_actually_in(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 200)
    window.select_tool("select")
    item = only(window, RectItem)[0]
    first_scene = item.scene()

    window.add_page()                      # a second page, with its own scene
    assert window.view.scene() is not first_scene
    window.view.scene().remove_markup(item)
    assert item.scene() is None
    assert item not in first_scene.markups()


def test_turning_the_page_settles_whatever_was_half_drawn(window):
    window.add_page()
    window.go_to_page(0)
    window.select_tool("polygon")
    click(window.view, 100, 100)
    click(window.view, 200, 100)
    assert window.view._draft is not None

    window.go_to_page(1)
    assert window.view._draft is None
    assert window.view.editing_item() is None
    assert window.view.active_table is None
    # nothing was stranded on the page that was left
    assert window.document.pages[0].scene.markups() == []


def test_turning_the_page_while_typing_keeps_what_was_typed(window):
    window.add_page()
    window.go_to_page(0)
    window.select_tool("math")
    drag(window.view, 80, 80, 320, 130)
    window.view.editing_item()._editor.setPlainText("L = 6 m")

    window.go_to_page(1)
    assert window.view.editing_item() is None
    window.recalculate()
    assert window.document.workspace.get("L").to("m").magnitude == pytest.approx(6)
