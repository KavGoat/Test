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


def test_a_rectangle_knows_its_paper_size_without_a_scale(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 100 + 4 * MM_TO_PT * 10, 100 + 2 * MM_TO_PT * 10)
    rect = only(window, RectItem)[0]
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


# ---------------------------------------------------------------------------
# Cells from another spreadsheet
# ---------------------------------------------------------------------------

def _table(window, x=80, y=80):
    window.select_tool("table")
    drag(window.view, x, y, x + 340, y + 160)
    return window.view.active_table


def test_a_block_pasted_over_an_open_cell_still_spreads_out(window):
    """Ctrl+V in the middle of typing must not stuff the sheet into one cell."""
    from PySide6.QtWidgets import QApplication

    table = _table(window)
    table.sheet.resize(8, 5)
    table.current = table.anchor = (0, 0)
    window.view.open_cell_editor()
    QApplication.clipboard().setText("1\t2\n3\t4")
    press_key(window.view, Qt.Key_V, "v", Qt.ControlModifier)

    assert window.view._cell_editor is None
    assert table.sheet.raw(0, 0) == "1"
    assert table.sheet.raw(0, 1) == "2"
    assert table.sheet.raw(1, 0) == "3"
    assert table.sheet.raw(1, 1) == "4"


def test_one_cell_pasted_while_typing_still_goes_into_the_text(window):
    from PySide6.QtWidgets import QApplication

    table = _table(window)
    table.current = table.anchor = (0, 0)
    window.view.open_cell_editor()
    window.view._cell_editor.setText("")
    QApplication.clipboard().setText("42")
    press_key(window.view, Qt.Key_V, "v", Qt.ControlModifier)
    assert window.view._cell_editor is not None


def test_cells_land_in_the_table_you_have_picked_out(window):
    from PySide6.QtWidgets import QApplication

    table = _table(window)
    table.sheet.resize(8, 5)
    window.view.deactivate_table()
    window.select_tool("select")
    table.setSelected(True)
    before = len(window.view.scene().ordered_markups())

    QApplication.clipboard().setText("7\t8\n9\t10")
    window.paste_items()

    assert len(window.view.scene().ordered_markups()) == before   # no second table
    assert table.sheet.raw(0, 0) == "7"
    assert table.sheet.raw(1, 1) == "10"


def test_cells_with_nothing_selected_still_become_a_table(window):
    from PySide6.QtWidgets import QApplication

    QApplication.clipboard().setText("a\tb\n1\t2")
    window.view.scene().clearSelection()
    window.paste_items()
    tables = [i for i in window.view.scene().ordered_markups()
              if isinstance(i, TableItem)]
    assert len(tables) == 1
    assert tables[0].sheet.raw(1, 0) == "1"


def test_a_pasted_block_grows_the_table_to_fit(window):
    from PySide6.QtWidgets import QApplication

    table = _table(window)
    table.sheet.resize(2, 2)
    table.current = table.anchor = (0, 0)
    QApplication.clipboard().setText("1\t2\t3\n4\t5\t6\n7\t8\t9")
    window.paste_items()
    assert table.sheet.rows >= 3 and table.sheet.cols >= 3
    assert table.sheet.raw(2, 2) == "9"


def test_formulas_pasted_as_text_stay_formulas(window):
    from PySide6.QtWidgets import QApplication

    table = _table(window)
    table.sheet.resize(6, 4)
    table.current = table.anchor = (0, 0)
    QApplication.clipboard().setText("2\t3\t=A1+B1")
    window.paste_items()
    window.recalculate()
    assert table.sheet.raw(0, 2) == "=A1+B1"
    assert table.sheet.value(0, 2) == 5


def test_copied_cells_beat_markups_copied_earlier(window):
    """Copying cells replaces what a paste puts down, markups and all."""
    from PySide6.QtWidgets import QApplication

    window.select_tool("rect")
    drag(window.view, 400, 400, 480, 450)
    window.select_tool("select")
    click(window.view, 440, 425)
    window.copy_selection()
    assert window._clipboard

    table = _table(window)
    table.sheet.resize(6, 4)
    table.set_cell(0, 0, "5")
    table.current = table.anchor = (0, 0)
    window.copy_selection()
    assert not window._clipboard

    table.current = table.anchor = (2, 0)
    window.paste_items()
    assert table.sheet.raw(2, 0) == "5"


def test_relative_formulas_follow_a_copy_between_tables(window):
    first = _table(window, 60, 60)
    first.sheet.resize(6, 4)
    first.set_cell(0, 0, "2")
    first.set_cell(0, 1, "3")
    first.set_cell(0, 2, "=A1+B1")
    window.recalculate()
    first.current, first.anchor = (0, 0), (0, 2)
    window.copy_selection()

    second = _table(window, 60, 300)
    second.sheet.resize(6, 4)
    second.current = second.anchor = (2, 0)
    window.paste_items()
    window.recalculate()
    assert second.sheet.raw(2, 2) == "=A3+B3"
    assert second.sheet.value(2, 2) == 5


# ---------------------------------------------------------------------------
# Maths symbols on a key
# ---------------------------------------------------------------------------

def test_every_maths_symbol_is_a_binding_you_can_change(window):
    from calcforge.ui.shortcuts import SYMBOL

    symbols = [b for b in window.shortcuts.bindings() if b.kind == SYMBOL]
    assert [b.payload for b in symbols][:2] == ["×", "÷"]
    assert all(b.category == "Symbols" for b in symbols)
    assert all(b.action_id in window.symbol_actions for b in symbols)
    # every one of them is on a key out of the box, and no two share it
    keys = [b.default for b in symbols]
    assert all(keys) and len(set(keys)) == len(keys)


def test_the_multiply_key_types_a_multiply_sign(window):
    window.view._last_scene_pos = QPointF(120, 120)
    press_key(window.view, Qt.Key_unknown, "/")
    block = window.view.editing_item()
    type_text(window.view, "a := 4 ")
    window.symbol_actions["symbol.multiply"].trigger()
    type_text(window.view, " 3")
    window.view.end_item_edit()
    assert "×" in block.source
    assert window.document.workspace.get("a") == 12


def test_the_root_key_brings_its_bracket_and_leaves_room_inside(window):
    window.view._last_scene_pos = QPointF(120, 260)
    press_key(window.view, Qt.Key_unknown, "/")
    block = window.view.editing_item()
    type_text(window.view, "r := ")
    window.symbol_actions["symbol.root"].trigger()
    type_text(window.view, "16")
    window.view.end_item_edit()
    assert block.source == "r := √(16)"
    assert window.document.workspace.get("r") == 4


def test_a_symbol_goes_into_a_cell_being_edited(window):
    table = _table(window, 60, 400)
    table.current = table.anchor = (0, 0)
    window.view.open_cell_editor()
    window.view._cell_editor.setText("2")
    window.view._cell_editor.setCursorPosition(1)
    window.symbol_actions["symbol.degree"].trigger()
    assert window.view._cell_editor.text() == "2°"


def test_a_symbol_with_nothing_open_says_so_rather_than_vanishing(window):
    window.view.end_item_edit()
    window.symbol_actions["symbol.pi"].trigger()
    assert "nowhere to go" in window.status_hint.text()


def test_symbol_keys_survive_being_rebound_and_reopened(window):
    from calcforge.ui.mainwindow import MainWindow
    from PySide6.QtGui import QKeySequence

    window.shortcuts.set_sequence("symbol.multiply", "Ctrl+Alt+9")
    window.apply_shortcuts()
    assert window.symbol_actions["symbol.multiply"].shortcut() == QKeySequence("Ctrl+Alt+9")

    second = MainWindow()
    second.confirm_discard = lambda: True
    try:
        assert second.shortcuts.sequence("symbol.multiply") == "Ctrl+Alt+9"
        assert second.symbol_actions["symbol.multiply"].shortcut() == \
            QKeySequence("Ctrl+Alt+9")
    finally:
        second.close()
        second.deleteLater()


def test_a_symbol_bound_to_a_bare_key_still_types_itself(window):
    window.shortcuts.set_sequence("symbol.pi", ";")
    window.apply_shortcuts()
    try:
        window.view._last_scene_pos = QPointF(120, 320)
        press_key(window.view, Qt.Key_unknown, "/")
        block = window.view.editing_item()
        type_text(window.view, "c := 2 ")
        assert window.run_typed_binding(";", Qt.NoModifier, QPointF(0, 0))
        window.view.end_item_edit()
        assert "π" in block.source
    finally:
        window.shortcuts.reset("symbol.pi")
        window.apply_shortcuts()


def test_symbol_keys_are_live_while_you_type(window):
    """Unlike tool keys, a symbol key must not be swallowed mid-calculation."""
    from PySide6.QtGui import QKeySequence

    window.view._last_scene_pos = QPointF(120, 380)
    press_key(window.view, Qt.Key_unknown, "/")
    assert window.view.is_editing()
    assert not window.shortcuts.is_canvas_binding(QKeySequence("Ctrl+Alt+8"))
    assert window.shortcuts.is_canvas_binding(QKeySequence("R"))
    window.view.end_item_edit()


# ---------------------------------------------------------------------------
# A calculation prints what it was asked to print
# ---------------------------------------------------------------------------

def _calc(window, text, at=(90, 110)):
    window.view._last_scene_pos = QPointF(*at)
    press_key(window.view, Qt.Key_unknown, "/")
    block = window.view.editing_item()
    block._editor.setPlainText(text)
    window.view.end_item_edit()
    window.recalculate()
    return block


def _shown(block) -> list[str]:
    return [row.result_text() if hasattr(row, "result_text") else ""
            for row in block.statements]


def test_a_quiet_line_shows_no_answer_but_still_defines_it(window):
    block = _calc(window, "L := 6 m\nw := 12 kN/m\nM := w*L^2/8")
    assert not any(block._wants_result(s) for s in block.statements)
    assert window.document.workspace.get("M").to("kN*m").magnitude == pytest.approx(54)


def test_asking_with_a_trailing_equals_prints_the_answer(window):
    block = _calc(window, "L := 6 m\nw := 12 kN/m\nM := w*L^2/8 =")
    printed = [s for s in block.statements if block._wants_result(s)]
    assert [s.name for s in printed] == ["M"]
    assert "54" in printed[0].result_text()


def test_typing_the_equals_later_makes_the_answer_appear(window):
    block = _calc(window, "b := 300 mm\nA := b*b")
    assert not any(block._wants_result(s) for s in block.statements)

    window.view.begin_item_edit(block)
    block._editor.setPlainText("b := 300 mm\nA := b*b =")
    window.view.end_item_edit()
    window.recalculate()
    assert [s.name for s in block.statements if block._wants_result(s)] == ["A"]


def test_a_region_told_to_show_everything_still_does(window):
    block = _calc(window, "b := 300 mm\nA := b*b")
    block.show_definition_results = True
    block.relayout()
    assert [s.name for s in block.statements if block._wants_result(s)] == ["A"]


# ---------------------------------------------------------------------------
# Changing the unit a result is shown in
# ---------------------------------------------------------------------------

def _result_point(window, block, row=None):
    """A scene point on a printed answer."""
    if row is None:
        row = next(i for i, r in enumerate(block.rows) if r.result is not None)
    return block.mapToScene(block.result_rect(row).center())


def test_double_clicking_an_answer_opens_its_unit(window):
    block = _calc(window, "L := 6 m\nw := 12 kN/m\nM := w*L^2/8 =")
    window.select_tool("select")
    point = _result_point(window, block)
    double_click(window.view, point.x(), point.y())

    assert window.view._unit_editor is not None
    assert window.view.editing_item() is None          # not the source editor
    assert window.view._unit_editor.text() == "kN·m"


def test_typing_a_unit_changes_what_the_answer_reads(window):
    block = _calc(window, "L := 6 m\nw := 12 kN/m\nM := w*L^2/8 =")
    window.view.open_unit_editor(block, block.result_at(
        block.result_rect(2).center()))
    window.view._unit_editor.setText("N*m")
    window.view.close_unit_editor(commit=True)

    assert "→ N*m" in block.source
    assert block.source.rstrip().endswith("=")          # still asking for it
    statement = block.statements[2]
    assert statement.target_unit == "N*m"
    assert "54000" in statement.result_text().replace(" ", "").replace(" ", "") \
        or "5.4" in statement.result_text()


def test_emptying_the_unit_lets_it_choose_again(window):
    block = _calc(window, "L := 6 m\nw := 12 kN/m\nM := w*L^2/8 → N*m =")
    assert block.statements[2].target_unit == "N*m"
    window.view.open_unit_editor(block, 2)
    window.view._unit_editor.setText("")
    window.view.close_unit_editor(commit=True)
    assert "→" not in block.source
    assert block.statements[2].target_unit == ""


def test_a_unit_that_makes_no_sense_is_refused(window):
    block = _calc(window, "L := 6 m\nw := 12 kN/m\nM := w*L^2/8 =")
    before = block.source
    window.view.open_unit_editor(block, 2)
    window.view._unit_editor.setText("bananas")
    window.view.close_unit_editor(commit=True)
    assert block.source == before


def test_escape_leaves_the_unit_alone(window):
    block = _calc(window, "b := 300 mm\nA := b*b =")
    before = block.source
    window.view.open_unit_editor(block, 1)
    window.view._unit_editor.setText("cm^2")
    press_key(window.view, Qt.Key_Escape)
    assert window.view._unit_editor is None
    assert block.source == before


def test_changing_the_unit_can_be_undone(window):
    block = _calc(window, "b := 300 mm\nA := b*b =")
    before = block.source
    window.view.open_unit_editor(block, 1)
    window.view._unit_editor.setText("cm^2")
    window.view.close_unit_editor(commit=True)
    assert block.source != before
    window.undo_stack.undo()
    assert window.view.scene().ordered_markups()[0].source == before


def test_the_unit_box_offers_units_and_the_names_you_have_defined(window):
    block = _calc(window, "b := 300 mm\nA := b*b =")
    window.view.open_unit_editor(block, 1)
    completer = window.view._unit_editor.completer()
    words = [completer.model().data(completer.model().index(row, 0))
             for row in range(completer.model().rowCount())]
    assert "kN*m" in words and "mm^2" in words
    assert "b" in words and "A" in words
    window.view.close_unit_editor(commit=False)


def test_the_unit_box_counts_as_typing(window):
    block = _calc(window, "b := 300 mm\nA := b*b =")
    window.view.open_unit_editor(block, 1)
    assert window.view.is_editing()
    window.view.close_unit_editor(commit=False)
    assert not window.view.is_editing()


def test_the_menu_can_change_the_unit_too(window):
    block = _calc(window, "b := 300 mm\nA := b*b =")
    window.select_tool("select")
    point = _result_point(window, block)
    menu = window.build_context_menu(block, point)
    labels = [action.text() for action in menu.actions()]
    assert "Show this result in…" in labels


# ---------------------------------------------------------------------------
# Drawing: click-by-click, and Shift
# ---------------------------------------------------------------------------

def test_a_measure_tool_no_longer_invents_a_measurement(window):
    """A click used to drop a 120 pt measurement out of nowhere."""
    window.select_tool("measure_length")
    click(window.view, 120, 200)
    assert window.view._mode == "draw_click"      # waiting for the second point
    assert window.view._draft is not None
    assert window.view._draft.points[-1] == QPointF(0, 0)


def test_two_clicks_draw_a_measurement(window):
    window.select_tool("measure_length")
    click(window.view, 120, 200)
    hover(window.view, 260, 200)
    click(window.view, 260, 200)

    drawn = markups(window)
    assert len(drawn) == 1
    assert isinstance(drawn[0], MeasureItem)
    assert drawn[0].points[-1].x() == pytest.approx(140, abs=2)
    assert window.view._mode == "idle"


def test_two_clicks_in_the_same_place_draw_nothing(window):
    window.select_tool("measure_length")
    click(window.view, 120, 200)
    click(window.view, 120, 200)
    assert markups(window) == []


def test_dragging_still_draws_in_one_gesture(window):
    window.select_tool("measure_length")
    drag(window.view, 120, 240, 300, 240)
    assert len(markups(window)) == 1
    assert window.view._mode == "idle"


def test_escape_abandons_a_click_started_drawing(window):
    window.select_tool("rect")
    click(window.view, 100, 100)
    hover(window.view, 200, 180)
    press_key(window.view, Qt.Key_Escape)
    assert markups(window) == []
    assert window.view._mode == "idle"


def test_two_clicks_draw_a_rectangle_the_size_of_the_two_clicks(window):
    window.select_tool("rect")
    click(window.view, 100, 400)
    hover(window.view, 220, 470)
    click(window.view, 220, 470)
    box = markups(window)[0]
    assert box.local_rect().width() == pytest.approx(120, abs=2)
    assert box.local_rect().height() == pytest.approx(70, abs=2)


def test_shift_squares_a_rectangle_in_every_direction(window):
    for start, end in (((300, 300), (420, 350)), ((300, 600), (200, 540))):
        window.select_tool("rect")
        drag(window.view, *start, *end, modifiers=Qt.ShiftModifier)
    boxes = [i for i in markups(window) if isinstance(i, RectItem)]
    assert len(boxes) == 2
    for box in boxes:
        rect = box.local_rect()
        assert rect.width() == pytest.approx(rect.height(), abs=1.5)
        assert rect.width() > 40


def test_shift_holds_a_line_to_forty_five_degrees(window):
    import math
    window.select_tool("line")
    drag(window.view, 100, 100, 240, 190, modifiers=Qt.ShiftModifier)
    line = markups(window)[0]
    delta = line.points[-1] - line.points[0]
    angle = abs(math.degrees(math.atan2(delta.y(), delta.x())))
    assert min(abs(angle - a) for a in (0, 45, 90, 135, 180)) < 0.5


def test_an_ellipse_carries_its_size(window):
    window.select_tool("ellipse")
    drag(window.view, 100, 500, 260, 580)
    oval = markups(window)[0]
    oval.refresh(page=window.current_page())
    assert oval.size_text
    assert "×" in oval.size_text
    assert oval.value_text == oval.size_text


def test_shift_makes_the_ellipse_a_circle(window):
    window.select_tool("ellipse")
    drag(window.view, 120, 620, 300, 680, modifiers=Qt.ShiftModifier)
    rect = markups(window)[0].local_rect()
    assert rect.width() == pytest.approx(rect.height(), abs=1.5)


def test_an_ellipse_can_be_set_out_to_an_exact_size(window):
    window.select_tool("ellipse")
    drag(window.view, 100, 700, 200, 760)
    oval = markups(window)[0]
    assert oval.set_real_size("50 mm", "30 mm", window.current_page())
    oval.refresh(page=window.current_page())
    assert "50" in oval.size_text and "30" in oval.size_text


# ---------------------------------------------------------------------------
# Setting the page scale
# ---------------------------------------------------------------------------

def test_the_scale_dialog_offers_picking_two_points_from_a_standing_start(window):
    from calcforge.ui import dialogs

    from PySide6.QtWidgets import QPushButton

    dialog = dialogs.ScaleDialog(window.current_page().scale, None, window)
    try:
        picks = [b for b in dialog.findChildren(QPushButton)
                 if "pick two points" in b.text().lower()]
        assert picks and picks[0].isEnabled()
    finally:
        dialog.deleteLater()


def test_choosing_to_pick_points_starts_the_calibrate_tool(window, monkeypatch):
    from calcforge.ui import dialogs

    monkeypatch.setattr(dialogs.ScaleDialog, "exec",
                        lambda self: dialogs.ScaleDialog.PICK)
    window.calibrate_scale(None)
    assert window.view.tool_key == "calibrate"
    assert "click one end" in window.status_hint.text().lower()


def test_two_clicks_and_a_length_set_the_scale(window, monkeypatch):
    from calcforge.ui import dialogs

    asked = {}

    class Stub(dialogs.ScaleDialog):
        def exec(self):
            asked["measured"] = self.measured_pt
            self.known.setText("10 m")
            return dialogs.QDialog.Accepted

    monkeypatch.setattr(dialogs, "ScaleDialog", Stub)
    window.select_tool("calibrate")
    click(window.view, 100, 300)
    click(window.view, 300, 300)

    assert asked["measured"] == pytest.approx(200, abs=2)
    scale = window.current_page().scale
    assert scale.is_calibrated()
    assert scale.length(200.0).to("m").magnitude == pytest.approx(10, rel=1e-3)


def test_a_calibration_line_is_not_left_on_the_page(window, monkeypatch):
    from calcforge.ui import dialogs
    monkeypatch.setattr(dialogs.ScaleDialog, "exec",
                        lambda self: dialogs.QDialog.Rejected)
    window.select_tool("calibrate")
    drag(window.view, 100, 300, 300, 300)
    assert markups(window) == []


def test_the_page_list_says_what_scale_each_page_is_at(window):
    from calcforge.core.document import PageScale

    window.load_sample()
    window.document.pages[1].scale = PageScale.from_ratio(50)
    window.pages_panel.rebuild(window.document, 0)

    entries = [window.pages_panel.list.item(row).text()
               for row in range(window.pages_panel.list.count())]
    assert entries[0] == "1"                    # no scale, no clutter
    assert "1:50" in entries[1]
    assert "Scale 1:50" in window.pages_panel.list.item(1).toolTip()


def test_the_page_menu_can_set_the_scale(window):
    labels = [action.text() for action in window.page_menu(0).actions()]
    assert "Page scale…" in labels


# ---------------------------------------------------------------------------
# Turning a page and changing its paper
# ---------------------------------------------------------------------------

def test_a_page_can_be_turned_a_quarter_turn(window):
    page = window.current_page()
    width, height = page.setup.width_mm, page.setup.height_mm
    window.rotate_page(0, clockwise=True)
    assert page.setup.width_mm == pytest.approx(height)
    assert page.setup.height_mm == pytest.approx(width)
    assert page.setup.orientation == "landscape"


def test_turning_a_page_turns_what_is_drawn_on_it(window):
    window.select_tool("rect")
    drag(window.view, 80, 120, 180, 200)
    box = markups(window)[0]
    height = window.current_page().setup.height_pt
    before = box.pos()

    window.rotate_page(0, clockwise=True)
    after = box.pos()
    assert after.x() == pytest.approx(height - before.y(), abs=0.5)
    assert after.y() == pytest.approx(before.x(), abs=0.5)
    assert box.rotation() % 360 == pytest.approx(90)


def test_turning_a_page_turns_its_background_sheet(window, tmp_path, monkeypatch):
    from PySide6.QtGui import QImage
    from calcforge.io import pdfio

    document = window.document
    photo = QImage(200, 100, QImage.Format_ARGB32)
    photo.fill(0xFF3366AA)
    path = str(tmp_path / "sheet.png")
    photo.save(path)
    pdfio.import_image(document, path, at=1)
    window.rebuild_scenes()
    page = document.pages[1]
    before = page.background_key

    window.rotate_page(1, clockwise=True)
    assert page.background_key != before
    turned = QImage()
    turned.loadFromData(document.asset(page.background_key))
    assert (turned.width(), turned.height()) == (100, 200)


def test_turning_a_page_back_and_forth_leaves_it_as_it_was(window):
    page = window.current_page()
    before = (page.setup.width_mm, page.setup.height_mm, page.setup.margin_left,
              page.setup.margin_top, page.setup.margin_right, page.setup.margin_bottom)
    window.rotate_page(0, clockwise=True)
    window.rotate_page(0, clockwise=False)
    after = (page.setup.width_mm, page.setup.height_mm, page.setup.margin_left,
             page.setup.margin_top, page.setup.margin_right, page.setup.margin_bottom)
    assert after == pytest.approx(before)


def test_rotating_can_be_undone(window):
    window.rotate_page(0, clockwise=True)
    assert window.current_page().setup.orientation == "landscape"
    window.undo_stack.undo()
    assert window.document.pages[0].setup.orientation == "portrait"


def test_one_page_can_be_put_on_a_different_sheet(window):
    window.load_sample()
    window.set_page_size(1, "A3")
    assert window.document.pages[1].setup.size_name == "A3"
    assert window.document.pages[0].setup.size_name == "A4"


def test_the_page_menu_offers_rotating_and_paper_sizes(window):
    menu = window.page_menu(0)
    labels = [action.text() for action in menu.actions()]
    assert "Rotate clockwise" in labels and "Rotate anticlockwise" in labels
    paper = next(action.menu() for action in menu.actions()
                 if action.text() == "Paper size")
    sizes = [action.text() for action in paper.actions()]
    assert "A4" in sizes and "A3" in sizes
    assert next(a for a in paper.actions() if a.text() == "A4").isChecked()


def test_a_new_table_asks_how_many_rows_and_columns(window, monkeypatch):
    from calcforge.ui import dialogs

    window.interactive_prompts = True
    monkeypatch.setattr(dialogs.TableSizeDialog, "exec",
                        lambda self: dialogs.QDialog.Accepted)
    monkeypatch.setattr(dialogs.TableSizeDialog, "values",
                        lambda self: (9, 3, True))
    try:
        window.select_tool("table")
        drag(window.view, 80, 80, 420, 240)
    finally:
        window.interactive_prompts = False
    table = window.view.active_table
    assert (table.sheet.rows, table.sheet.cols) == (9, 3)
    assert table.sheet.header_row


def test_saying_no_to_the_size_leaves_the_default(window, monkeypatch):
    from calcforge.ui import dialogs

    window.interactive_prompts = True
    monkeypatch.setattr(dialogs.TableSizeDialog, "exec",
                        lambda self: dialogs.QDialog.Rejected)
    try:
        window.select_tool("table")
        drag(window.view, 80, 300, 420, 460)
    finally:
        window.interactive_prompts = False
    table = window.view.active_table
    assert (table.sheet.rows, table.sheet.cols) == (6, 4)


# ---------------------------------------------------------------------------
# The callout's arrow
# ---------------------------------------------------------------------------

def _callout(window, target=(200, 300), box=(300, 200, 460, 260), text="note"):
    window.select_tool("callout")
    click(window.view, *target)
    drag(window.view, *box)
    item = window.view.editing_item()
    if text:
        item.set_text(text)
    return item


def test_the_arrow_can_be_moved_straight_after_drawing_it(window):
    """Reaching for the arrow used to make the whole callout disappear."""
    call = _callout(window, text="")
    tip = call.mapToScene(call.leader[0])
    drag(window.view, tip.x(), tip.y(), tip.x() - 60, tip.y() + 40)

    assert call in markups(window)                 # still there
    moved = call.mapToScene(call.leader[0])
    assert moved.x() == pytest.approx(tip.x() - 60, abs=2)
    assert moved.y() == pytest.approx(tip.y() + 40, abs=2)


def test_the_arrow_can_be_moved_once_the_callout_is_finished(window):
    call = _callout(window)
    window.view.end_item_edit()
    window.select_tool("select")
    call.setSelected(True)
    tip = call.mapToScene(call.leader[0])
    drag(window.view, tip.x(), tip.y(), tip.x() + 40, tip.y() - 30)
    moved = call.mapToScene(call.leader[0])
    assert moved.x() == pytest.approx(tip.x() + 40, abs=2)


def test_the_elbow_of_the_leader_moves_too(window):
    call = _callout(window)
    window.view.end_item_edit()
    window.select_tool("select")
    call.setSelected(True)
    elbow = call.mapToScene(call.leader[1])
    drag(window.view, elbow.x(), elbow.y(), elbow.x() - 20, elbow.y() + 25)
    moved = call.mapToScene(call.leader[1])
    assert moved.y() == pytest.approx(elbow.y() + 25, abs=2)


def test_moving_the_box_leaves_the_arrow_pointing_at_the_same_thing(window):
    call = _callout(window)
    window.view.end_item_edit()
    window.select_tool("select")
    call.setSelected(True)
    aimed_at = call.mapToScene(call.leader[0])

    centre = call.mapToScene(call.local_rect().center())
    drag(window.view, centre.x(), centre.y(), centre.x() + 80, centre.y() - 50)

    assert call.mapToScene(call.leader[0]).x() == pytest.approx(aimed_at.x(), abs=1)
    assert call.mapToScene(call.leader[0]).y() == pytest.approx(aimed_at.y(), abs=1)


def test_nudging_a_callout_leaves_its_arrow_alone(window):
    call = _callout(window)
    window.view.end_item_edit()
    window.select_tool("select")
    call.setSelected(True)
    aimed_at = call.mapToScene(call.leader[0])
    for _ in range(3):
        press_key(window.view, Qt.Key_Right)
    assert call.mapToScene(call.leader[0]).x() == pytest.approx(aimed_at.x(), abs=1)


def test_the_arrow_handles_are_marked_out_as_the_arrow(window):
    call = _callout(window)
    assert call.leader_handles() == {"l0", "l1"}
    assert set(call.handle_points()) >= {"l0", "l1", "nw", "se"}


def test_an_empty_text_box_is_still_dropped(window):
    window.select_tool("text")
    drag(window.view, 100, 600, 260, 640)
    window.view.end_item_edit()
    assert markups(window) == []


# ---------------------------------------------------------------------------
# What a graph plots
# ---------------------------------------------------------------------------

def _plot(window, monkeypatch, curves=(("sin(x)", "wave"),), accept=True):
    from calcforge.ui import dialogs

    def fake_exec(self):
        self.curves.setRowCount(0)
        for expression, label in curves:
            self._add_row(expression, label)
        self.x_from.setText("0")
        self.x_to.setText("6")
        return dialogs.QDialog.Accepted if accept else dialogs.QDialog.Rejected

    monkeypatch.setattr(dialogs.PlotDialog, "exec", fake_exec)


def test_a_new_graph_asks_what_it_plots(window, monkeypatch):
    _plot(window, monkeypatch)
    window.interactive_prompts = True
    try:
        window.select_tool("plot")
        drag(window.view, 80, 80, 400, 280)
    finally:
        window.interactive_prompts = False
    plot = markups(window)[0]
    assert [s.expression for s in plot.series] == ["sin(x)"]
    assert [s.label for s in plot.series] == ["wave"]
    assert plot.x_to == "6"


def test_double_clicking_a_graph_edits_what_it_plots(window, monkeypatch):
    window.select_tool("plot")
    drag(window.view, 80, 80, 400, 280)
    plot = markups(window)[0]
    window.select_tool("select")

    _plot(window, monkeypatch, curves=(("x^2", ""), ("2*x", "line")))
    centre = plot.mapToScene(plot.local_rect().center())
    double_click(window.view, centre.x(), centre.y())
    assert [s.expression for s in plot.series] == ["x^2", "2*x"]


def test_editing_a_graph_can_be_undone(window, monkeypatch):
    window.select_tool("plot")
    drag(window.view, 80, 80, 400, 280)
    plot = markups(window)[0]
    before = [s.expression for s in plot.series]

    _plot(window, monkeypatch, curves=(("x^3", ""),))
    window.edit_plot(plot)
    assert [s.expression for s in plot.series] == ["x^3"]
    window.undo_stack.undo()
    assert [s.expression for s in markups(window)[0].series] == before


def test_the_graph_menu_offers_editing_it(window):
    window.select_tool("plot")
    drag(window.view, 80, 80, 400, 280)
    plot = markups(window)[0]
    labels = [a.text() for a in window.build_context_menu(plot, plot.pos()).actions()]
    assert "Edit plot…" in labels


def test_the_plot_dialog_offers_the_names_you_have_defined(window):
    from calcforge.ui import dialogs

    _calc(window, "L := 6 m\nw := 12 kN/m", at=(90, 500))
    window.select_tool("plot")
    drag(window.view, 80, 80, 400, 280)
    plot = markups(window)[0]
    workspace = window.document.workspace
    dialog = dialogs.PlotDialog(plot, set(workspace.variables) | set(workspace.functions))
    try:
        model = dialog.curves.cellWidget(0, 0).completer().model()
        words = [model.data(model.index(row, 0)) for row in range(model.rowCount())]
        assert "L" in words and "w" in words
    finally:
        dialog.deleteLater()


# ---------------------------------------------------------------------------
# Looking a value up in a table from a calculation
# ---------------------------------------------------------------------------

def _capacity_table(window, name="bolts"):
    window.select_tool("table")
    drag(window.view, 60, 60, 400, 220)
    table = window.view.active_table
    table.sheet.resize(4, 3)
    table.sheet.header_row = True
    rows = [["d", "V", "N"],
            ["12 mm", "29.4 kN", "2"],
            ["16 mm", "54.3 kN", "3"],
            ["20 mm", "84.8 kN", "4"]]
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            table.set_cell(r, c, value)
    table.table_name = name
    window.view.deactivate_table()
    window.recalculate()
    return table


def test_a_calculation_can_read_a_named_table(window):
    _capacity_table(window)
    block = _calc(window, "d := 16 mm\nV := bolts(d, A, B) =", at=(60, 400))
    window.recalculate()
    assert not block.statements[1].error
    assert window.document.workspace.get("V").to("kN").magnitude == pytest.approx(54.3)


def test_a_size_between_two_rows_is_interpolated(window):
    _capacity_table(window)
    _calc(window, "d := 14 mm\nV := bolts(d, A, B) =", at=(60, 400))
    window.recalculate()
    assert window.document.workspace.get("V").to("kN").magnitude == \
        pytest.approx((29.4 + 54.3) / 2)


def test_the_column_letters_are_columns_not_variables(window):
    """A is a column of the table here, not an ampere and not somebody's area."""
    _capacity_table(window)
    _calc(window, "A := 500 mm^2\nd := 16 mm\nV := bolts(d, A, B) =", at=(60, 400))
    window.recalculate()
    assert window.document.workspace.get("V").to("kN").magnitude == pytest.approx(54.3)
    assert window.document.workspace.get("A").to("mm^2").magnitude == pytest.approx(500)


def test_column_headers_work_as_well_as_letters(window):
    _capacity_table(window)
    _calc(window, 'd := 20 mm\nV := bolts(d, "d", "V") =', at=(60, 400))
    window.recalculate()
    assert window.document.workspace.get("V").to("kN").magnitude == pytest.approx(84.8)


def test_asking_outside_the_table_is_a_problem_not_a_number(window):
    _capacity_table(window)
    block = _calc(window, "d := 30 mm\nV := bolts(d, A, B) =", at=(60, 400))
    window.recalculate()
    assert "extrapolated" in block.statements[1].error


def test_a_table_name_is_kept_when_the_document_is_saved(window, tmp_path):
    from calcforge.core.document import Document
    from calcforge.io import project as project_io

    _capacity_table(window, "shear")
    path = str(tmp_path / "job.cfx")
    project_io.save_document(window.document, path)

    reopened = Document()
    project_io.load_document(reopened, path)
    names = [item.get("table_name") for item in reopened.pages[0].to_dict()["items"]
             if item.get("type") == "table"]
    assert names == ["shear"]


def test_naming_a_table_is_offered_on_its_menu(window):
    table = _capacity_table(window)
    labels = [a.text() for a in window.build_context_menu(table, table.pos()).actions()]
    assert "Name this table…" in labels


def test_a_named_table_shows_up_as_something_the_document_knows(window):
    table = _capacity_table(window)
    assert "bolts" in table.declared_names()
    assert "bolts" in window.document.workspace.table_names()


# ---------------------------------------------------------------------------
# A calculation line and a calculation block are different things
# ---------------------------------------------------------------------------

def test_the_two_calculation_tools_are_offered_separately(window):
    from calcforge.ui.tools import TOOL_MAP
    assert TOOL_MAP["math"].label == "Calculation line"
    assert TOOL_MAP["mathblock"].label == "Calculation block"
    assert "math" in window.tool_actions and "mathblock" in window.tool_actions


def test_a_block_keeps_its_working_to_itself(window):
    window.select_tool("mathblock")
    drag(window.view, 80, 80, 400, 200)
    block = window.view.editing_item()
    assert block.block and block.local_scope
    block._editor.setPlainText("t := 5 mm\nA := t*t =")
    window.view.end_item_edit()
    window.recalculate()
    assert block.scoped
    assert window.document.workspace.get("t") is None


def test_a_line_defines_for_the_whole_document(window):
    window.select_tool("math")
    drag(window.view, 80, 300, 400, 330)
    line = window.view.editing_item()
    assert not line.block and not line.local_scope
    line._editor.setPlainText("t := 5 mm")
    window.view.end_item_edit()
    window.recalculate()
    assert window.document.workspace.get("t").to("mm").magnitude == pytest.approx(5)


def test_enter_in_a_block_makes_another_line_not_another_region(window):
    window.select_tool("mathblock")
    drag(window.view, 80, 80, 400, 200)
    block = window.view.editing_item()
    type_text(window.view, "a := 1")
    press_key(window.view, Qt.Key_Return)
    type_text(window.view, "b := 2")
    assert window.view.editing_item() is block
    window.view.end_item_edit()
    assert len([l for l in block.source.split("\n") if l.strip()]) == 2
    assert len([i for i in markups(window) if isinstance(i, MathItem)]) == 1


def test_enter_in_a_line_opens_the_next_line_below(window):
    window.view._last_scene_pos = QPointF(100, 100)
    press_key(window.view, Qt.Key_unknown, "/")
    first = window.view.editing_item()
    type_text(window.view, "a := 1")
    press_key(window.view, Qt.Key_Return)
    assert window.view.editing_item() is not first
    window.view.end_item_edit()


def test_a_line_can_be_turned_into_a_block_and_back(window):
    window.select_tool("math")
    drag(window.view, 80, 300, 400, 330)
    line = window.view.editing_item()
    line._editor.setPlainText("a := 1")
    window.view.end_item_edit()
    line.setSelected(True)

    window.set_block_kind(True)
    assert line.block
    window.set_block_kind(False)
    assert not line.block and not line.local_scope


def test_merging_lines_makes_a_block(window):
    window.select_tool("math")
    drag(window.view, 80, 300, 400, 330)
    window.view.editing_item()._editor.setPlainText("a := 1")
    window.view.end_item_edit()
    window.select_tool("math")
    drag(window.view, 80, 380, 400, 410)
    window.view.editing_item()._editor.setPlainText("b := 2")
    window.view.end_item_edit()

    for item in markups(window):
        item.setSelected(True)
    window.merge_calculations()
    merged = [i for i in markups(window) if isinstance(i, MathItem)]
    assert len(merged) == 1 and merged[0].block


def test_splitting_a_block_gives_lines(window):
    window.select_tool("mathblock")
    drag(window.view, 80, 80, 400, 200)
    block = window.view.editing_item()
    block._editor.setPlainText("a := 1\nb := 2")
    window.view.end_item_edit()
    block.setSelected(True)
    window.split_calculation()
    pieces = [i for i in markups(window) if isinstance(i, MathItem)]
    assert len(pieces) == 2
    assert not any(piece.block for piece in pieces)


def test_an_older_document_keeps_the_behaviour_it_was_written_with(window):
    from calcforge.items.base import build_item

    item = build_item({"type": "math", "source": "a := 1\nb := 2", "x": 0, "y": 0})
    assert item.block                       # several lines: it was a block
    single = build_item({"type": "math", "source": "a := 1", "x": 0, "y": 0})
    assert not single.block


def test_resizing_a_callout_leaves_the_arrow_where_it_points(window):
    """The arrow points at something on the drawing; resizing must not move it."""
    call = _callout(window)
    window.view.end_item_edit()
    window.select_tool("select")
    call.setSelected(True)
    aimed_at = call.mapToScene(call.leader[0])

    for handle in ("topLeft", "bottomRight"):
        corner = call.mapToScene(getattr(call.local_rect(), handle)())
        drag(window.view, corner.x(), corner.y(),
             corner.x() + (-40 if handle == "topLeft" else 50),
             corner.y() + (-30 if handle == "topLeft" else 20))
        moved = call.mapToScene(call.leader[0])
        assert moved.x() == pytest.approx(aimed_at.x(), abs=0.5), handle
        assert moved.y() == pytest.approx(aimed_at.y(), abs=0.5), handle


def test_a_callout_is_drawn_arrow_first_then_like_a_rectangle(window):
    window.select_tool("callout")
    click(window.view, 200, 300)
    assert window.view._pending_anchor is not None      # the arrow head is set
    click(window.view, 300, 200)                        # first corner
    assert window.view._mode == "draw_click"
    hover(window.view, 460, 260)
    click(window.view, 460, 260)                        # second corner

    call = markups(window)[0]
    assert isinstance(call, CalloutItem)
    assert call.local_rect().width() == pytest.approx(160, abs=2)
    assert call.local_rect().height() == pytest.approx(60, abs=2)
    tip = call.mapToScene(call.leader[0])
    assert (tip.x(), tip.y()) == pytest.approx((200, 300), abs=1)


# ---------------------------------------------------------------------------
# A rectangle is a rectangle, not a dimension
# ---------------------------------------------------------------------------

def test_a_rectangle_does_not_write_its_size_on_the_drawing(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 260, 180)
    box = markups(window)[0]
    assert not box.show_size
    box.refresh(page=window.current_page())
    assert box.size_text                       # it knows its size
    assert box.value_text == box.size_text     # and the takeoff list gets it


def test_the_properties_panel_reports_the_size(window):
    from PySide6.QtWidgets import QLabel

    window.select_tool("rect")
    drag(window.view, 100, 100, 260, 180)
    box = markups(window)[0]
    window.select_tool("select")
    box.setSelected(True)
    window.refresh_selection()

    labels = [w.text() for w in window.properties_panel.findChildren(QLabel)]
    assert any("mm" in text for text in labels)


def test_the_size_can_still_be_written_on_it_if_you_want(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 260, 180)
    box = markups(window)[0]
    window.set_size_visible(box, True)
    assert box.show_size
    assert box.value_text


# ---------------------------------------------------------------------------
# Ctrl to copy, Ctrl to let go of the grid
# ---------------------------------------------------------------------------

def test_ctrl_dragging_leaves_a_copy_behind(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    window.select_tool("select")
    box = markups(window)[0]
    box.setSelected(True)

    centre = box.mapToScene(box.local_rect().center())
    drag(window.view, centre.x(), centre.y(), centre.x() + 120, centre.y() + 60,
         modifiers=Qt.ControlModifier)

    boxes = [i for i in markups(window) if isinstance(i, RectItem)]
    assert len(boxes) == 2
    positions = sorted(round(i.pos().x()) for i in boxes)
    assert positions[0] == 100                       # one stayed where it was
    assert positions[1] == pytest.approx(220, abs=3)


def test_a_ctrl_click_does_not_copy_anything(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    window.select_tool("select")
    box = markups(window)[0]
    centre = box.mapToScene(box.local_rect().center())
    click(window.view, centre.x(), centre.y(), modifiers=Qt.ControlModifier)
    assert len([i for i in markups(window) if isinstance(i, RectItem)]) == 1
    assert box.isSelected()


def test_a_copy_can_be_undone_in_one_go(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    window.select_tool("select")
    box = markups(window)[0]
    box.setSelected(True)
    centre = box.mapToScene(box.local_rect().center())
    drag(window.view, centre.x(), centre.y(), centre.x() + 120, centre.y(),
         modifiers=Qt.ControlModifier)
    assert len(markups(window)) == 2
    window.undo_stack.undo()
    assert len(markups(window)) == 1


def test_ctrl_taken_hold_of_mid_move_lets_go_of_the_grid(window):
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    window.document.settings.snap_to_grid = True
    window.document.settings.grid_mm = 10.0
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    window.select_tool("select")
    box = markups(window)[0]
    box.setSelected(True)

    centre = box.mapToScene(box.local_rect().center())
    QApplication.sendEvent(window.view.viewport(),
                           _mouse(window.view, QEvent.MouseButtonPress, centre.x(), centre.y()))
    QApplication.sendEvent(window.view.viewport(), _mouse(
        window.view, QEvent.MouseMove, centre.x() + 33, centre.y() + 17,
        Qt.NoButton, Qt.LeftButton, Qt.ControlModifier))
    off_grid = box.pos()
    QApplication.sendEvent(window.view.viewport(), _mouse(
        window.view, QEvent.MouseMove, centre.x() + 33, centre.y() + 17,
        Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
    on_grid = box.pos()
    QApplication.sendEvent(window.view.viewport(), _mouse(
        window.view, QEvent.MouseButtonRelease, centre.x() + 33, centre.y() + 17))

    step = 10.0 * MM_TO_PT
    assert abs(round(on_grid.x() / step) * step - on_grid.x()) < 0.01
    assert off_grid != on_grid                      # it was free while Ctrl was held


# ---------------------------------------------------------------------------
# Snapping to what is already drawn
# ---------------------------------------------------------------------------

def test_dragging_catches_the_corner_of_another_markup(window):
    window.document.settings.snap_to_items = True
    window.select_tool("rect")
    drag(window.view, 100, 100, 220, 180)          # the one to line up with
    window.select_tool("rect")
    drag(window.view, 300, 400, 380, 460)          # the one to move
    window.select_tool("select")
    first, second = markups(window)[0], markups(window)[1]
    second.setSelected(True)

    # aim the moving box's top-left a few points off the other box's corner
    corner = first.mapToScene(first.local_rect().bottomRight())
    grab = second.mapToScene(second.local_rect().center())
    offset = second.mapToScene(second.local_rect().center()) - \
        second.mapToScene(second.local_rect().topLeft())
    drag(window.view, grab.x(), grab.y(),
         corner.x() + offset.x() + 4, corner.y() + offset.y() - 3)

    landed = second.mapToScene(second.local_rect().topLeft())
    assert landed.x() == pytest.approx(corner.x(), abs=0.5)
    assert landed.y() == pytest.approx(corner.y(), abs=0.5)


def test_snapping_to_items_can_be_turned_off(window):
    window.document.settings.snap_to_items = False
    window.select_tool("rect")
    drag(window.view, 100, 100, 220, 180)
    window.select_tool("rect")
    drag(window.view, 300, 400, 380, 460)
    window.select_tool("select")
    first, second = markups(window)[0], markups(window)[1]
    second.setSelected(True)

    corner = first.mapToScene(first.local_rect().bottomRight())
    grab = second.mapToScene(second.local_rect().center())
    offset = second.mapToScene(second.local_rect().center()) - \
        second.mapToScene(second.local_rect().topLeft())
    drag(window.view, grab.x(), grab.y(),
         corner.x() + offset.x() + 4, corner.y() + offset.y() - 3)

    landed = second.mapToScene(second.local_rect().topLeft())
    assert landed.x() == pytest.approx(corner.x() + 4, abs=0.5)


def test_drawing_catches_a_line_end(window):
    window.document.settings.snap_to_items = True
    window.select_tool("line")
    drag(window.view, 100, 100, 260, 200)
    window.select_tool("line")
    end = markups(window)[0]
    tip = end.mapToScene(end.points[-1])
    drag(window.view, tip.x() + 5, tip.y() - 4, 400, 300)

    started = markups(window)[1].scenePos()
    assert started.x() == pytest.approx(tip.x(), abs=0.5)
    assert started.y() == pytest.approx(tip.y(), abs=0.5)


def test_the_snap_menu_entry_is_there_and_on(window):
    assert window.act_snap_items.isChecked()
    window.act_snap_items.setChecked(False)
    assert not window.document.settings.snap_to_items
    window.act_snap_items.setChecked(True)
    assert window.document.settings.snap_to_items


# ---------------------------------------------------------------------------
# A cloud callout, and a highlight that goes over anything
# ---------------------------------------------------------------------------

def test_a_cloud_callout_is_a_cloud_with_a_leader(window):
    window.select_tool("cloud_callout")
    click(window.view, 200, 300)
    drag(window.view, 300, 200, 460, 260)
    call = window.view.editing_item()
    call.set_text("check this")
    window.view.end_item_edit()

    assert isinstance(call, CalloutItem)
    assert call.shape_kind == "cloud"
    tip = call.mapToScene(call.leader[0])
    assert (tip.x(), tip.y()) == pytest.approx((200, 300), abs=1)
    # the scallops bulge out past the box, and the item makes room for them
    assert call.boundingRect().width() > call.local_rect().width() + call.cloud_radius


def test_a_plain_callout_is_still_a_box(window):
    call = _callout(window)
    assert call.shape_kind == "box"


def test_a_cloud_callout_survives_a_round_trip(window):
    from calcforge.items.base import build_item

    window.select_tool("cloud_callout")
    click(window.view, 200, 300)
    drag(window.view, 300, 200, 460, 260)
    call = window.view.editing_item()
    call.set_text("check this")
    window.view.end_item_edit()

    clone = build_item(call.serialize())
    assert clone.shape_kind == "cloud"
    assert clone.text() == "check this"


def test_the_highlight_goes_over_whatever_is_under_it(window):
    from calcforge.items.shapes import RectItem

    window.select_tool("highlight")
    drag(window.view, 100, 100, 300, 140)
    mark = markups(window)[0]
    assert isinstance(mark, RectItem) and mark.kind == "highlight"
    assert mark.style.blend == "multiply"       # darkens, does not cover
    assert mark.style.fill_opacity < 1.0


def test_the_highlight_and_the_cloud_callout_are_on_keys(window):
    from calcforge.ui.tools import TOOL_MAP
    assert TOOL_MAP["highlight"].shortcut == "J"
    assert TOOL_MAP["cloud_callout"].shortcut == "Shift+Q"
    assert not window.shortcuts.conflicts()


# ---------------------------------------------------------------------------
# Bookmarks and a contents block
# ---------------------------------------------------------------------------

def test_a_bookmark_is_added_where_you_are(window, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    window.load_sample()
    window.go_to_page(2)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Foundation", True))
    window.add_bookmark_here()

    marks = window.document.bookmarks
    assert [m.title for m in marks] == ["Foundation"]
    assert window.document.page_index_of(marks[0].page_uid) == 2


def test_bookmarks_are_listed_in_page_order(window):
    window.load_sample()
    window.document.add_bookmark("Third", 2)
    window.document.add_bookmark("First", 0)
    window.bookmarks_changed()

    tree = window.bookmarks_panel.tree
    titles = [tree.topLevelItem(row).text(0).strip() for row in range(tree.topLevelItemCount())]
    pages = [tree.topLevelItem(row).text(1) for row in range(tree.topLevelItemCount())]
    assert titles == ["First", "Third"]
    assert pages == ["1", "3"]


def test_a_bookmark_follows_its_page_when_pages_move(window):
    window.load_sample()
    window.document.add_bookmark("Foundation", 2)
    window.move_page(2, 0)
    assert window.document.contents_entries()[0][1] == 0


def test_a_bookmark_whose_page_has_gone_is_left_out(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    window.load_sample()
    window.document.add_bookmark("Foundation", 2)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    window.delete_page(2)
    assert window.document.contents_entries() == []
    window.bookmarks_panel.rebuild(window.document)
    assert window.bookmarks_panel.tree.topLevelItemCount() == 0


def test_double_clicking_a_bookmark_goes_there(window):
    window.load_sample()
    window.document.add_bookmark("Foundation", 2)
    window.bookmarks_changed()
    tree = window.bookmarks_panel.tree
    tree.setCurrentItem(tree.topLevelItem(0))
    window.bookmarks_panel._activate(tree.topLevelItem(0))
    assert window.current_index == 2


def test_a_contents_block_lists_the_bookmarks(window):
    from calcforge.items.contents import ContentsItem

    window.load_sample()
    window.document.add_bookmark("Beam design", 0)
    window.document.add_bookmark("Foundation", 2)

    window.select_tool("contents")
    drag(window.view, 60, 500, 360, 640)
    block = next(i for i in markups(window) if isinstance(i, ContentsItem))
    assert [mark.title for mark, _ in block.entries()] == ["Beam design", "Foundation"]

    window.document.pages[0].frame.render_image(dpi=48.0)      # lays the rows out
    assert len(block.rows) == 2


def test_clicking_a_contents_line_goes_to_that_page(window):
    window.load_sample()
    window.document.add_bookmark("Beam design", 0)
    window.document.add_bookmark("Foundation", 2)
    from calcforge.items.contents import ContentsItem

    window.select_tool("contents")
    drag(window.view, 60, 500, 360, 640)
    block = next(i for i in markups(window) if isinstance(i, ContentsItem))
    window.select_tool("select")
    window.view.scene().clearSelection()
    window.document.pages[0].frame.render_image(dpi=48.0)

    row, index, _y = block.rows[1]
    point = block.mapToScene(row.center())
    click(window.view, point.x(), point.y())
    assert window.current_index == index == 2


def test_bookmarks_are_saved_with_the_document(window, tmp_path):
    from calcforge.core.document import Document
    from calcforge.io import project as project_io

    window.load_sample()
    window.document.add_bookmark("Foundation", 2, y=120.0)
    path = str(tmp_path / "job.cfx")
    project_io.save_document(window.document, path)

    reopened = Document()
    project_io.load_document(reopened, path)
    assert [m.title for m in reopened.bookmarks] == ["Foundation"]
    assert reopened.bookmarks[0].y == pytest.approx(120.0)
    assert reopened.page_index_of(reopened.bookmarks[0].page_uid) == 2


def test_there_is_a_key_for_bookmarking_where_you_are(window):
    from PySide6.QtGui import QKeySequence
    assert window.act_bookmark.shortcut() == QKeySequence("Ctrl+B")


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

def test_a_snapshot_copies_what_is_in_the_region_as_itself(window):
    from calcforge.items.mathitem import MathItem

    _calc(window, "L := 6 m\nA := L*L =", at=(90, 110))
    window.select_tool("rect")
    drag(window.view, 100, 200, 220, 260)

    window.select_tool("snapshot")
    drag(window.view, 60, 80, 400, 320)

    payload = window._clipboard
    kinds = [entry["type"] for entry in payload]
    assert "math" in kinds and "rect" in kinds
    # and the marquee itself is not left on the page
    assert not [i for i in markups(window) if getattr(i, "kind", "") == "marquee"]
    assert "copied" in window.status_hint.text()


def test_a_snapshot_pastes_back_as_real_markups(window):
    from calcforge.items.mathitem import MathItem

    _calc(window, "b := 300 mm =", at=(90, 110))
    window.select_tool("snapshot")
    drag(window.view, 60, 80, 400, 200)
    before = len(markups(window))

    window.select_tool("select")
    window.view.set_insert_point(QPointF(80, 500))
    window.paste_items()

    after = markups(window)
    assert len(after) == before + 1
    pasted = [i for i in after if isinstance(i, MathItem) and i.pos().y() > 400]
    assert len(pasted) == 1
    assert "b :=" in pasted[0].source            # the calculation, not a picture


def test_a_snapshot_of_nothing_says_so(window):
    window.select_tool("snapshot")
    drag(window.view, 60, 500, 200, 560)
    assert "Nothing in that region" in window.status_hint.text()


def test_a_snapshot_takes_the_drawing_underneath_with_it(window, tmp_path, monkeypatch):
    from PySide6.QtGui import QImage
    from calcforge.io import pdfio

    photo = QImage(400, 300, QImage.Format_ARGB32)
    photo.fill(0xFF3366AA)
    path = str(tmp_path / "sheet.png")
    photo.save(path)
    pdfio.import_image(window.document, path, at=1)
    window.rebuild_scenes()
    window.go_to_page(1)

    from PySide6.QtCore import QRectF

    frame = window.document.pages[1].frame
    window.take_snapshot(frame, QRectF(20, 20, 120, 90))
    payload = window._clipboard
    assert payload and payload[0]["type"] == "image"
    assert window.document.asset(payload[0]["asset_key"])


def test_a_snapshot_puts_a_picture_on_the_clipboard_for_other_apps(window):
    from PySide6.QtWidgets import QApplication

    window.select_tool("rect")
    drag(window.view, 100, 100, 220, 180)
    window.select_tool("snapshot")
    drag(window.view, 60, 60, 300, 250)

    image = QApplication.clipboard().image()
    assert not image.isNull()
    assert image.width() > 100


def test_the_snapshot_tool_is_on_g(window):
    from calcforge.ui.tools import TOOL_MAP
    assert TOOL_MAP["snapshot"].shortcut == "G"
    assert TOOL_MAP["plot"].shortcut == "Shift+G"
    assert not window.shortcuts.conflicts()


# ---------------------------------------------------------------------------
# Changing the colours of a drawing
# ---------------------------------------------------------------------------

def _sheet_page(window, tmp_path, colour=0xFF000000):
    """A page whose background is a white sheet with one dark line."""
    from PySide6.QtGui import QColor, QImage
    from calcforge.io import pdfio

    image = QImage(60, 40, QImage.Format_ARGB32)
    image.fill(QColor("white"))
    for x in range(60):
        image.setPixelColor(x, 20, QColor.fromRgba(colour))
    path = str(tmp_path / "sheet.png")
    image.save(path)
    pdfio.import_image(window.document, path, at=1)
    window.rebuild_scenes()
    return window.document.pages[1]


def test_the_lines_of_a_page_can_be_pushed_to_another_colour(window, tmp_path, monkeypatch):
    from PySide6.QtGui import QColor, QImage
    from calcforge.ui import dialogs

    page = _sheet_page(window, tmp_path)
    before = page.background_key

    def choose(self):
        self.lines_mode.setChecked(True)
        self.line_target = QColor("#888888")
        return dialogs.QDialog.Accepted

    monkeypatch.setattr(dialogs.RecolourDialog, "exec", choose)
    window.recolour_page(1)

    assert page.background_key != before
    image = QImage()
    image.loadFromData(window.document.asset(page.background_key))
    assert QColor(image.pixel(5, 20)).name() == "#888888"     # the line
    assert QColor(image.pixel(5, 5)).name() == "#ffffff"      # the paper


def test_one_colour_can_be_swapped_for_another(window, tmp_path, monkeypatch):
    from PySide6.QtGui import QColor, QImage
    from calcforge.ui import dialogs

    page = _sheet_page(window, tmp_path)

    def choose(self):
        self.swap_mode.setChecked(True)
        index = self.from_colour.findText("#000000")
        self.from_colour.setCurrentIndex(max(index, 0))
        self.to_target = QColor("#c92a2a")
        return dialogs.QDialog.Accepted

    monkeypatch.setattr(dialogs.RecolourDialog, "exec", choose)
    window.recolour_page(1)

    image = QImage()
    image.loadFromData(window.document.asset(page.background_key))
    assert QColor(image.pixel(5, 20)).name() == "#c92a2a"


def test_recolouring_a_page_can_be_undone(window, tmp_path, monkeypatch):
    from PySide6.QtGui import QColor
    from calcforge.ui import dialogs

    page = _sheet_page(window, tmp_path)
    before = page.background_key
    monkeypatch.setattr(dialogs.RecolourDialog, "exec",
                        lambda self: dialogs.QDialog.Accepted)
    window.recolour_page(1)
    assert page.background_key != before
    window.undo_stack.undo()
    assert window.document.pages[1].background_key == before


def test_a_blank_page_says_there_is_nothing_to_recolour(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    said = {}
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *a, **k: said.setdefault("text", a[2]))
    window.recolour_page(0)
    assert "no drawing" in said.get("text", "")


def test_the_page_menu_only_offers_it_where_there_is_a_drawing(window, tmp_path):
    _sheet_page(window, tmp_path)
    blank = {a.text(): a for a in window.page_menu(0).actions()}
    sheet = {a.text(): a for a in window.page_menu(1).actions()}
    assert not blank["Change colours…"].isEnabled()
    assert sheet["Change colours…"].isEnabled()


# ---------------------------------------------------------------------------
# Writing a formula by pointing at cells
# ---------------------------------------------------------------------------

def _sheet(window):
    window.select_tool("table")
    drag(window.view, 60, 60, 420, 240)
    table = window.view.active_table
    table.sheet.resize(6, 4)
    table.set_cell(0, 0, "2")
    table.set_cell(0, 1, "3")
    return table


def test_clicking_a_cell_while_typing_a_formula_refers_to_it(window):
    table = _sheet(window)
    table.current = table.anchor = (2, 0)
    window.view.open_cell_editor(initial="=")

    target = table.mapToScene(table.cell_rect(0, 1).center())
    click(window.view, target.x(), target.y())

    assert window.view._cell_editor is not None       # still typing
    assert window.view._cell_editor.text() == "=B1"
    assert table.pointing == (0, 1)


def test_the_arrow_keys_choose_the_cell_to_refer_to(window):
    table = _sheet(window)
    table.current = table.anchor = (2, 2)
    window.view.open_cell_editor(initial="=")

    press_key(window.view, Qt.Key_Up)
    assert window.view._cell_editor.text() == "=C2"
    press_key(window.view, Qt.Key_Up)
    assert window.view._cell_editor.text() == "=C1"   # replaced, not appended
    press_key(window.view, Qt.Key_Left)
    assert window.view._cell_editor.text() == "=B1"


def test_a_pointed_formula_works_out(window):
    table = _sheet(window)
    table.current = table.anchor = (2, 0)
    window.view.open_cell_editor(initial="=")
    first = table.mapToScene(table.cell_rect(0, 0).center())
    click(window.view, first.x(), first.y())
    press_key(window.view, Qt.Key_Plus, "+")
    second = table.mapToScene(table.cell_rect(0, 1).center())
    click(window.view, second.x(), second.y())
    window.view.close_cell_editor(commit=True)
    window.recalculate()

    assert table.sheet.raw(2, 0) == "=A1+B1"
    assert table.sheet.value(2, 0) == 5


def test_the_arrows_still_move_the_caret_in_ordinary_text(window):
    table = _sheet(window)
    table.current = table.anchor = (2, 0)
    window.view.open_cell_editor(initial="hello")
    editor = window.view._cell_editor
    editor.setCursorPosition(5)
    press_key(window.view, Qt.Key_Left)
    assert editor.text() == "hello"
    assert table.pointing is None


def test_the_arrows_move_the_caret_once_a_reference_is_finished(window):
    table = _sheet(window)
    table.current = table.anchor = (2, 0)
    window.view.open_cell_editor(initial="=A1")
    editor = window.view._cell_editor
    editor.setCursorPosition(3)
    press_key(window.view, Qt.Key_Left)
    assert editor.text() == "=A1"                    # not a reference to another cell


def test_typing_after_pointing_finishes_the_reference(window):
    table = _sheet(window)
    table.current = table.anchor = (2, 0)
    window.view.open_cell_editor(initial="=")
    press_key(window.view, Qt.Key_Up)
    assert window.view._point_span is not None
    press_key(window.view, Qt.Key_Asterisk, "*")
    assert window.view._point_span is None
    assert table.pointing is None
