"""Interaction tests driven by the events Qt actually sends.

Everything here goes through the viewport as a real pointer or keyboard would:
press/release pairs, the four-event double-click sequence, context-menu events,
and key presses with their text.  Calling a handler directly would hide exactly
the bugs this file exists to catch.
"""
import pytest
from PySide6.QtCore import QEvent, QKeyCombination, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QContextMenuEvent, QKeyEvent, QMouseEvent
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


def on_page(window, index, x, y):
    """A point on page *index*, in canvas coordinates.

    The canvas holds every page stacked down it, so drawing on page three
    means aiming at the part of the canvas page three occupies.
    """
    frame = window.document.pages[index].frame
    point = frame.mapToScene(QPointF(x, y))
    return point.x(), point.y()


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
    press_key(window.view, Qt.Key_unknown, "/")
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


def test_q_draws_a_callout_pointing_at_what_was_clicked_first(window):
    """Bluebeam's order: click what it points at, then drag out the box."""
    window.select_tool("select")
    window.view._last_scene_pos = QPointF(200, 200)
    press_key(window.view, Qt.Key_unknown, "q")

    click(window.view, 180, 420)                 # the thing being pointed at
    assert only(window, CalloutItem) == []       # nothing drawn yet
    assert window.view._pending_anchor is not None

    drag(window.view, 300, 200, 460, 260)        # now the box
    callout = only(window, CalloutItem)[0]
    assert window.view._pending_anchor is None
    assert len(callout.leader) >= 2
    tip = callout.mapToScene(callout.leader[0])
    assert tip.x() == pytest.approx(180, abs=6)
    assert tip.y() == pytest.approx(420, abs=6)
    assert window.view.editing_item() is callout


def test_escape_abandons_a_half_drawn_callout(window):
    window.select_tool("callout")
    click(window.view, 180, 420)
    assert window.view._pending_anchor is not None
    press_key(window.view, Qt.Key_Escape)
    assert window.view._pending_anchor is None
    assert only(window, CalloutItem) == []


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
    window.current_page().frame.refresh_items()
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
    window.current_page().frame.refresh_items()
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
        assert page.frame.scene().itemIndexMethod() == QGraphicsScene.NoIndex


def test_a_markup_is_removed_from_the_page_it_is_actually_on(window):
    """A markup always leaves the page it is on, not the one being looked at."""
    from calcforge.ui.scene import detach

    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 200)
    window.select_tool("select")
    item = only(window, RectItem)[0]
    first_page = window.document.pages[0].frame
    assert item.parentItem() is first_page

    window.add_page()                      # now looking at a different page
    assert window.view.frame() is not first_page
    detach(item)
    assert item.scene() is None
    assert item not in first_page.markups()


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
    assert window.document.pages[0].frame.markups() == []


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


def test_a_note_can_be_placed_without_a_dialog_getting_in_the_way(window):
    from calcforge.items.text import NoteItem

    window.select_tool("note")               # interactive_prompts is off here
    click(window.view, 200, 200)
    notes = only(window, NoteItem)
    assert len(notes) == 1
    assert notes[0].comment == ""


def test_double_clicking_a_note_opens_what_it_says(window, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    from calcforge.items.text import NoteItem

    window.select_tool("note")
    click(window.view, 200, 200)
    note = only(window, NoteItem)[0]
    window.select_tool("select")

    monkeypatch.setattr(QInputDialog, "getMultiLineText",
                        staticmethod(lambda *a, **k: ("check the lap length", True)))
    double_click(window.view, 200 + note.SIZE / 2, 200 + note.SIZE / 2)
    assert note.comment == "check the lap length"
    assert "check the lap length" in note.summary()


def test_cancelling_the_note_dialog_leaves_it_as_it_was(window, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    from calcforge.items.text import NoteItem

    window.select_tool("note")
    click(window.view, 200, 200)
    note = only(window, NoteItem)[0]
    note.comment = "as built"
    window.select_tool("select")

    monkeypatch.setattr(QInputDialog, "getMultiLineText",
                        staticmethod(lambda *a, **k: ("ignored", False)))
    double_click(window.view, 200 + note.SIZE / 2, 200 + note.SIZE / 2)
    assert note.comment == "as built"


def test_double_clicking_an_area_measurement_adds_a_vertex(window):
    """A take-off is redrawn far more often than it is drawn."""
    page = scaled_page(window)
    window.select_tool("measure_area")
    for x, y in ((100, 400), (300, 400), (300, 600), (100, 600)):
        click(window.view, x, y)
        hover(window.view, x, y)
    window.view.finish_poly()
    area = [i for i in only(window, MeasureItem) if i.kind == "area"][0]
    window.select_tool("select")
    before = len(area.points)
    first = area.value.to("m**2").magnitude

    double_click(window.view, 200, 400)          # on the top edge
    assert len(area.points) == before + 1
    assert area.value is not None                # and it still measures
    assert area.value.to("m**2").magnitude == pytest.approx(first, rel=0.05)


def test_double_clicking_a_two_point_length_does_not_break(window):
    scaled_page(window)
    window.select_tool("measure_length")
    drag(window.view, 100, 400, 300, 400)
    length = [i for i in only(window, MeasureItem) if i.kind == "length"][0]
    window.select_tool("select")
    double_click(window.view, 200, 400)          # no vertices to add here
    assert len(length.points) == 2
    assert length.value is not None


def test_moving_a_calculation_changes_what_resolves_straight_away(window):
    """Reading order decides what is defined, so a move is an edit."""
    window.select_tool("math")
    drag(window.view, 80, 120, 320, 160)
    window.view.editing_item()._editor.setPlainText("L = 6 m")
    window.view.end_item_edit()

    window.select_tool("math")
    drag(window.view, 80, 400, 320, 440)
    user = window.view.editing_item()
    user._editor.setPlainText("M = L*2")
    window.view.end_item_edit()
    window.select_tool("select")

    assert window.document.workspace.get("M").to("m").magnitude == pytest.approx(12)
    assert [s.error for s in user.statements if s.error] == []

    # Drag the user of L above the line that defines it — without pressing F9.
    # Grab it in the middle: near an edge is a resize handle, not the body.
    centre = user.mapToScene(user.local_rect().center())
    click(window.view, centre.x(), centre.y())
    drag(window.view, centre.x(), centre.y(), centre.x(), 60)
    assert any("not defined" in s.error for s in user.statements if s.error), \
        "the page kept a result its position no longer supports"


def test_a_moved_document_still_re_derives(window):
    from calcforge.core.verify import verify_document

    window.select_tool("math")
    drag(window.view, 80, 120, 320, 160)
    window.view.editing_item()._editor.setPlainText("L = 6 m")
    window.view.end_item_edit()
    window.select_tool("math")
    drag(window.view, 80, 300, 320, 340)
    window.view.editing_item()._editor.setPlainText("L = 6 m")
    window.view.end_item_edit()
    window.select_tool("select")

    second = [i for i in only(window, MathItem) if i.pos().y() > 200][0]
    centre = second.mapToScene(second.local_rect().center())
    drag(window.view, centre.x(), centre.y(), centre.x(), 60)   # swap them over
    result = verify_document(window.document)
    disagreements = [p for p in result.problems if p.kind == "disagreement"]
    assert disagreements == [], [p.message for p in disagreements]


def test_two_markups_in_the_same_spot_always_read_the_same_way(window):
    """Order decides what is defined, so it cannot depend on luck."""
    from calcforge.ui.scene import reading_order

    window.select_tool("math")
    drag(window.view, 80, 120, 320, 160)
    window.view.editing_item()._editor.setPlainText("L = 6 m")
    window.view.end_item_edit()
    window.select_tool("select")
    only(window, MathItem)[0].setSelected(True)
    window.duplicate_selection()

    blocks = only(window, MathItem)
    assert len(blocks) == 2
    for item in blocks:                       # stack them exactly
        item.setPos(QPointF(80, 120))
    window.recalculate()

    first = [i.uid for i in reading_order(list(blocks))]
    for _ in range(20):
        assert [i.uid for i in reading_order(list(reversed(blocks)))] == first
    assert first == sorted(first) or first == sorted(first, reverse=True)


def test_a_document_re_derives_the_same_way_twice_running(window):
    """Two passes over the same sheet must agree — including on the ties."""
    from calcforge.core.verify import verify_document

    for index, source in enumerate(("L = 6 m", "L = 6 m", "w = 12 kN/m")):
        window.select_tool("math")
        drag(window.view, 80, 100 + index * 90, 320, 140 + index * 90)
        window.view.editing_item()._editor.setPlainText(source)
        window.view.end_item_edit()
    window.select_tool("select")
    # Put two of them at exactly the same place.
    blocks = only(window, MathItem)
    blocks[1].setPos(blocks[0].pos())
    window.recalculate()

    for _ in range(5):
        window.recalculate()
        result = verify_document(window.document)
        disagreements = [p for p in result.problems if p.kind == "disagreement"]
        assert disagreements == [], [p.message for p in disagreements]


# ---------------------------------------------------------------------------
# a tool key is a letter when you are writing
# ---------------------------------------------------------------------------

def chord(window, key, modifiers=Qt.NoModifier):
    """Send a key the way Qt delivers a shortcut, and say whether it fired.

    Qt asks with a ShortcutOverride first. If something accepts it the key
    belongs to whatever has focus and no shortcut runs; otherwise the matching
    action is triggered, as Qt's shortcut map would.
    """
    from PySide6.QtGui import QKeyEvent, QKeySequence

    target = QApplication.focusWidget() or window.view
    override = QKeyEvent(QEvent.ShortcutOverride, key, modifiers, "")
    QApplication.sendEvent(target, override)
    if override.isAccepted():
        QApplication.sendEvent(target, QKeyEvent(QEvent.KeyPress, key, modifiers, ""))
        return False
    wanted = QKeySequence(QKeyCombination(modifiers, key))
    for action in window.tool_actions.values():
        if not action.shortcut().isEmpty() and action.shortcut() == wanted:
            action.trigger()
            break
    return True


def swallowed(window, key, modifiers=Qt.NoModifier) -> bool:
    """True when the focus widget claims a key instead of letting it be a shortcut."""
    from PySide6.QtGui import QKeyEvent

    override = QKeyEvent(QEvent.ShortcutOverride, key, modifiers, "")
    QApplication.sendEvent(QApplication.focusWidget() or window.view, override)
    return override.isAccepted()


def test_a_tool_chord_does_not_change_tool_while_typing(window):
    window.select_tool("text")
    drag(window.view, 100, 100, 340, 150)
    box = window.view.editing_item()
    box.set_text("Check ")
    assert window.view.is_editing()

    assert not chord(window, Qt.Key_M, Qt.AltModifier), "the editor lost the key"
    assert window.view.current_tool().key == "select"
    assert window.view.editing_item() is box


def test_a_tool_chord_works_again_once_the_edit_is_over(window):
    window.select_tool("text")
    drag(window.view, 100, 100, 340, 150)
    window.view.end_item_edit()
    assert not window.view.is_editing()
    assert chord(window, Qt.Key_M, Qt.AltModifier)
    assert window.view.current_tool().key == "measure_dimension"


def test_tool_keys_are_silent_inside_a_table(window):
    window.select_tool("table")
    drag(window.view, 80, 80, 460, 240)
    assert window.view.is_editing()             # a table with the cursor in it
    assert not chord(window, Qt.Key_M, Qt.AltModifier)
    assert window.view.current_tool().key == "select"


def test_document_commands_stay_live_while_typing(window):
    """Save and zoom work mid-sentence, as they do in every other application.

    Ctrl+Z is deliberately not in this list: while the cursor is in a text box
    it undoes the typing, which is what a text box is supposed to do with it.
    """
    window.select_tool("text")
    drag(window.view, 100, 100, 340, 150)
    assert window.view.is_editing()
    assert not swallowed(window, Qt.Key_0, Qt.ControlModifier)
    assert not swallowed(window, Qt.Key_S, Qt.ControlModifier)
    assert not swallowed(window, Qt.Key_P, Qt.ControlModifier)


def test_a_bare_letter_types_rather_than_picking_a_tool(window):
    window.select_tool("text")
    drag(window.view, 100, 100, 340, 150)
    box = window.view.editing_item()
    box.set_text("")
    type_text(window.view, "mrc")
    assert box.text() == "mrc"
    assert window.view.current_tool().key == "select"


# ---------------------------------------------------------------------------
# clicking bare paper marks the spot
# ---------------------------------------------------------------------------

def test_clicking_empty_paper_marks_where_things_will_go(window):
    window.select_tool("select")
    assert window.view.insert_point() is None
    click(window.view, 260, 340)
    marked = window.view.insert_point()
    assert marked is not None
    assert marked.x() == pytest.approx(260, abs=4)
    assert marked.y() == pytest.approx(340, abs=4)


def test_typing_starts_where_the_page_was_clicked(window):
    window.select_tool("select")
    click(window.view, 300, 500)
    press_key(window.view, Qt.Key_unknown, "/")
    block = window.view.editing_item()
    assert block is not None
    assert block.pos().x() == pytest.approx(300, abs=6)
    assert block.pos().y() == pytest.approx(500, abs=6)


def test_a_paste_lands_where_the_page_was_clicked(window):
    window.select_tool("rect")
    drag(window.view, 80, 80, 180, 160)
    window.select_tool("select")
    original = only(window, RectItem)[0]
    original.setSelected(True)
    window.copy_selection()

    click(window.view, 320, 520)
    window.paste_items()
    copies = [i for i in only(window, RectItem) if i is not original]
    assert len(copies) == 1
    assert copies[0].pos().x() == pytest.approx(320, abs=6)
    assert copies[0].pos().y() == pytest.approx(520, abs=6)


def test_the_mark_is_drawn_on_the_canvas(window):
    """It is no use marking a spot the user cannot see."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter

    window.select_tool("select")
    click(window.view, 260, 340)

    def ink(view) -> int:
        image = QImage(80, 80, QImage.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        painter.translate(-220, -300)          # look at the marked spot
        view.drawForeground(painter, QRectF(220, 300, 80, 80))
        painter.end()
        return sum(1 for x in range(80) for y in range(80) if image.pixel(x, y))

    assert ink(window.view) > 0, "the insertion mark was not drawn"
    window.view.set_insert_point(None)
    assert ink(window.view) == 0, "the mark outstayed its welcome"


# ---------------------------------------------------------------------------
# Working on a page from its thumbnail
# ---------------------------------------------------------------------------

def _menu_labels(menu):
    return [action.text() for action in menu.actions() if not action.isSeparator()]


def test_the_page_menu_offers_everything_you_do_to_a_page(window):
    window.load_sample()
    labels = _menu_labels(window.page_menu(0))
    for wanted in ("Insert blank page before", "Insert blank page after",
                   "Duplicate page", "Insert PDF pages before…",
                   "Insert PDF pages after…", "Insert image before…",
                   "Insert image after…", "Delete page", "Page setup…"):
        assert wanted in labels


def test_the_page_menu_does_not_offer_impossible_moves(window):
    window.load_sample()
    last = len(window.document.pages) - 1
    top = {action.text(): action for action in window.page_menu(0).actions()}
    bottom = {action.text(): action for action in window.page_menu(last).actions()}
    assert not top["Move up"].isEnabled()
    assert top["Move down"].isEnabled()
    assert bottom["Move up"].isEnabled()
    assert not bottom["Move down"].isEnabled()


def test_the_only_page_cannot_be_deleted_from_the_menu(window):
    assert len(window.document.pages) == 1
    actions = {action.text(): action for action in window.page_menu(0).actions()}
    assert not actions["Delete page"].isEnabled()


def test_a_page_can_be_inserted_before_a_named_page(window):
    window.load_sample()
    first = window.document.pages[0].uid
    window.add_page(0, before=True)
    assert len(window.document.pages) == 4
    assert window.document.pages[1].uid == first
    assert window.current_index == 0


def test_a_page_can_be_inserted_after_a_named_page(window):
    window.load_sample()
    second = window.document.pages[1].uid
    window.add_page(0)
    assert window.document.pages[2].uid == second
    assert window.current_index == 1


def test_duplicating_works_on_the_page_you_right_clicked(window):
    window.load_sample()
    window.go_to_page(2)
    source = window.document.pages[0]
    source.frame.markups()  # the page is live
    window.duplicate_page(0)
    assert len(window.document.pages) == 4
    copy = window.document.pages[1]
    assert copy.uid != source.uid
    assert len(copy.to_dict()["items"]) == len(source.to_dict()["items"])


def test_deleting_works_on_the_page_you_right_clicked(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.Yes)
    window.load_sample()
    survivor = window.document.pages[1].uid
    window.delete_page(0)
    assert window.document.pages[0].uid == survivor


def test_a_page_command_ignores_the_checked_flag_from_a_button(window):
    """Buttons and actions send a bool; it must not be read as a page number."""
    window.load_sample()
    window.go_to_page(2)
    window.pages_panel.layout().itemAt(0).layout().itemAt(0).widget().click()
    assert window.current_index == 3
    assert len(window.document.pages) == 4


def test_an_image_goes_in_as_a_page_of_its_own(window, tmp_path, monkeypatch):
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QFileDialog

    path = str(tmp_path / "site.png")
    photo = QImage(400, 300, QImage.Format_RGB32)
    photo.fill(0xFF3366AA)
    assert photo.save(path)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (path, ""))

    window.load_sample()
    window.insert_image_page(0)
    assert len(window.document.pages) == 4
    page = window.document.pages[1]
    assert page.background_key
    assert window.document.asset(page.background_key)
    assert page.label == "site.png"
    # landscape photo, landscape page
    assert page.setup.width_mm > page.setup.height_mm
    assert window.current_index == 1


def test_inserting_an_image_page_can_be_undone(window, tmp_path, monkeypatch):
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QFileDialog

    path = str(tmp_path / "detail.png")
    photo = QImage(200, 400, QImage.Format_RGB32)
    photo.fill(0xFFFFFFFF)
    photo.save(path)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (path, ""))

    window.insert_image_page()
    assert len(window.document.pages) == 2
    window.undo_stack.undo()
    assert len(window.document.pages) == 1


def test_a_cancelled_image_insert_changes_nothing(window, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    window.insert_image_page()
    assert len(window.document.pages) == 1
