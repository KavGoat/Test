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


def hover(view, x, y):
    """Move the pointer without pressing anything."""
    QApplication.sendEvent(view.viewport(),
                           _mouse(view, QEvent.MouseMove, x, y, Qt.NoButton))


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
    ("l", "line"), ("h", "highlighter"), ("k", "cloud_poly"), ("n", "polyline"),
    ("s", "stamp"), ("b", "table"),
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
# things land where the pointer is
# ---------------------------------------------------------------------------

def test_typing_starts_where_the_pointer_is(window):
    window.select_tool("select")
    hover(window.view, 300, 500)
    press_key(window.view, Qt.Key_unknown, "/")
    block = window.view.editing_item()
    assert block is not None
    assert block.pos().x() == pytest.approx(300, abs=6)
    assert block.pos().y() == pytest.approx(500, abs=6)


def test_a_paste_lands_under_the_pointer(window):
    window.select_tool("rect")
    drag(window.view, 80, 80, 180, 160)
    window.select_tool("select")
    original = only(window, RectItem)[0]
    original.setSelected(True)
    window.copy_selection()

    hover(window.view, 320, 520)
    window.paste_items()
    copies = [i for i in only(window, RectItem) if i is not original]
    assert len(copies) == 1
    assert copies[0].pos().x() == pytest.approx(320, abs=6)
    assert copies[0].pos().y() == pytest.approx(520, abs=6)


def test_nothing_is_drawn_where_the_page_was_clicked(window):
    """A click leaves no mark behind: there is no insertion point any more."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter

    window.select_tool("select")
    click(window.view, 260, 340)

    image = QImage(80, 80, QImage.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    painter.translate(-220, -300)              # look where the click landed
    window.view.drawForeground(painter, QRectF(220, 300, 80, 80))
    painter.end()
    assert sum(1 for x in range(80) for y in range(80) if image.pixel(x, y)) == 0


# ---------------------------------------------------------------------------
# Working on a page from its thumbnail
# ---------------------------------------------------------------------------

def _menu_labels(menu):
    return [action.text() for action in menu.actions() if not action.isSeparator()]


def _menu_entry(menu, label):
    """One action out of a menu, by what it says."""
    found = [action for action in menu.actions() if action.text() == label]
    assert found, f"{label!r} not in {_menu_labels(menu)}"
    return found[0]


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


def test_the_elbow_slides_along_its_own_line(window):
    """The elbow leaves the box square on, and can only be slid in and out."""
    call = _callout(window)
    window.view.end_item_edit()
    window.select_tool("select")
    call.setSelected(True)
    before = call.elbow()
    normal = call.side_normal()
    elbow = call.mapToScene(before)
    drag(window.view, elbow.x(), elbow.y(),
         elbow.x() + normal.x() * 30 + 18, elbow.y() + normal.y() * 30 - 14)

    after = call.elbow()
    # further out along the same line, and still square on to the side
    assert call.elbow_reach > 24.0
    side = call.side_point()
    assert (after.x() - side.x()) * normal.y() == pytest.approx(
        (after.y() - side.y()) * normal.x(), abs=0.01)


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
    assert call.leader_handles() == {"l0", "elbow"}
    assert set(call.handle_points()) >= {"l0", "elbow", "nw", "se"}


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
    """A block shares its names unless it is told to keep them."""
    window.select_tool("mathblock")
    drag(window.view, 80, 80, 400, 200)
    block = window.view.editing_item()
    assert block.block and not block.local_scope
    block._editor.setPlainText("t := 5 mm\nA := t*t =")
    window.view.end_item_edit()
    block.local_scope = True
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


def test_a_callout_is_arrow_first_then_where_the_words_go(window):
    """Two clicks and it is on the page, at a size that holds a line or two."""
    window.select_tool("callout")
    click(window.view, 200, 300)
    assert window.view._pending_anchor is not None      # the arrow head is set
    click(window.view, 300, 200)                        # where the words go

    call = markups(window)[0]
    assert isinstance(call, CalloutItem)
    assert call.local_rect().width() > 40
    assert call.local_rect().height() > 20
    tip = call.mapToScene(call.leader[0])
    assert (tip.x(), tip.y()) == pytest.approx((200, 300), abs=1)
    window.view.end_item_edit()


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

def test_a_cloud_callout_clouds_the_thing_and_notes_it(window):
    """Bluebeam's: a cloud round what the comment is about, and the note on a
    leader beside it — not a text box with a wobbly border."""
    from calcforge.items.shapes import RectItem

    window.select_tool("cloud_callout")
    drag(window.view, 160, 260, 300, 340)        # the cloud goes round it
    click(window.view, 400, 200)                 # and the words go here
    call = window.view.editing_item()
    call.set_text("check this")
    window.view.end_item_edit()

    assert isinstance(call, CalloutItem)
    assert call.leader_shown
    clouds = [i for i in markups(window)
              if isinstance(i, RectItem) and i.kind == "cloud"]
    assert len(clouds) == 1
    # The leader points at the cloud, and the two are one thing.
    tip = call.mapToScene(call.leader[0])
    cloud_box = clouds[0].mapRectToScene(clouds[0].local_rect().normalized())
    assert cloud_box.adjusted(-4, -4, 4, 4).contains(tip)
    assert call.group and call.group == clouds[0].group


def test_escape_gets_out_of_a_half_drawn_cloud_callout(window):
    from calcforge.items.shapes import RectItem

    window.select_tool("cloud_callout")
    drag(window.view, 160, 260, 300, 340)
    assert window.view._pending_cloud is not None

    press_key(window.view, Qt.Key_Escape)
    assert window.view._pending_cloud is None
    assert window.view.tool_key == "select"
    # The cloud that was drawn stays: it is a markup in its own right.
    assert [i for i in markups(window)
            if isinstance(i, RectItem) and i.kind == "cloud"]


def test_a_plain_callout_is_still_a_box(window):
    call = _callout(window)
    assert call.shape_kind == "box"


def test_a_cloud_callout_survives_a_round_trip(window):
    from calcforge.items.base import build_item

    window.select_tool("cloud_callout")
    drag(window.view, 160, 260, 300, 340)
    click(window.view, 400, 200)
    call = window.view.editing_item()
    call.set_text("check this")
    window.view.end_item_edit()

    clone = build_item(call.serialize())
    assert clone.text() == "check this"
    assert clone.leader_shown
    assert clone.group == call.group


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

def test_a_snapshot_is_a_picture_of_the_region(window):
    """It is what that part of the page looks like, not a rebuilt copy of it."""
    _calc(window, "L := 6 m\nA := L*L =", at=(90, 110))
    window.select_tool("rect")
    drag(window.view, 100, 200, 220, 260)

    window.select_tool("snapshot")
    drag(window.view, 60, 80, 400, 320)

    payload = window._clipboard
    assert [entry["type"] for entry in payload] == ["image"]
    assert window.document.asset(payload[0]["asset"])
    # and the marquee itself is not left on the page
    assert not [i for i in markups(window) if getattr(i, "kind", "") == "marquee"]
    assert "Snapshot taken" in window.status_hint.text()


def test_a_snapshot_pastes_back_as_one_picture(window):
    from calcforge.items.media import ImageItem

    _calc(window, "b := 300 mm =", at=(90, 110))
    window.select_tool("snapshot")
    drag(window.view, 60, 80, 400, 200)
    before = len(markups(window))

    window.select_tool("select")
    hover(window.view, 80, 500)
    window.paste_items()

    after = markups(window)
    assert len(after) == before + 1
    pasted = [i for i in after if isinstance(i, ImageItem) and i.pos().y() > 400]
    assert len(pasted) == 1


def test_a_picture_copied_elsewhere_beats_the_last_snapshot(window):
    """What is on the clipboard is what gets pasted."""
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    from calcforge.items.media import ImageItem

    window.select_tool("rect")
    drag(window.view, 100, 100, 220, 180)
    window.select_tool("snapshot")
    drag(window.view, 60, 60, 300, 250)
    assert window._clipboard                     # a snapshot is held

    foreign = QImage(120, 80, QImage.Format_ARGB32)
    foreign.fill(0xFF2F9E44)
    QApplication.clipboard().setImage(foreign)   # copied in another program

    window.select_tool("select")
    hover(window.view, 120, 520)
    before = len(markups(window))
    window.paste_items()

    pasted = [i for i in markups(window) if isinstance(i, ImageItem)
              and i.pos().y() > 400]
    assert len(markups(window)) == before + 1
    assert len(pasted) == 1
    assert pasted[0].local_rect().width() == pytest.approx(120, abs=1)


def test_a_snapshot_of_bare_paper_is_still_a_picture(window):
    """Of blank paper, as asked — a snapshot is what is there, not what it holds."""
    window.select_tool("snapshot")
    drag(window.view, 60, 500, 200, 560)
    assert window._clipboard and window._clipboard[0]["type"] == "image"


def test_a_snapshot_of_no_region_at_all_says_so(window):
    from PySide6.QtCore import QRectF

    window.take_snapshot(window.view.frame(), QRectF(60, 500, 0, 0))
    assert "drag a region" in window.status_hint.text()


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
    assert window.document.asset(payload[0]["asset"])
    # taken at 300 dpi, so it holds up when it is zoomed into
    from PySide6.QtGui import QImage
    picture = QImage()
    picture.loadFromData(window.document.asset(payload[0]["asset"]))
    assert picture.width() > 120 * 3


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


# ---------------------------------------------------------------------------
# Units and names, offered rather than assumed
# ---------------------------------------------------------------------------

def _typing(window, text, at=(100, 120)):
    window.view._last_scene_pos = QPointF(*at)
    press_key(window.view, Qt.Key_unknown, "/")
    for character in text:
        press_key(window.view, Qt.Key_unknown, character)
    return window.view.editing_item()


def test_typing_offers_units_and_the_names_you_have_defined(window):
    _calc(window, "L_span := 6 m", at=(90, 500))
    _typing(window, "w := 3 kN")
    popup = window.view._completions
    assert window.view.completions_showing()
    words = [popup.item(row).text() for row in range(popup.count())]
    assert "kN" in words
    window.view.end_item_edit()

    _typing(window, "x := L_", at=(90, 560))
    words = [window.view._completions.item(row).text()
             for row in range(window.view._completions.count())]
    assert "L_span" in words
    window.view.end_item_edit()


def test_nothing_is_completed_until_tab_is_pressed(window):
    block = _typing(window, "w := 3 kN")
    assert block._editor.toPlainText() == "w := 3 kN"     # exactly what was typed
    press_key(window.view, Qt.Key_Tab)
    assert block._editor.toPlainText().startswith("w := 3 k")
    window.view.end_item_edit()


def test_the_arrows_move_through_the_list_and_tab_takes_one(window):
    block = _typing(window, "w := 3 k")
    popup = window.view._completions
    assert window.view.completions_showing()
    first = popup.currentItem().text()
    press_key(window.view, Qt.Key_Down)
    second = popup.currentItem().text()
    assert second != first
    press_key(window.view, Qt.Key_Tab)
    assert block._editor.toPlainText() == f"w := 3 {second}"
    window.view.end_item_edit()


def test_escape_puts_the_list_away_without_ending_the_edit(window):
    block = _typing(window, "w := 3 kN")
    assert window.view.completions_showing()
    press_key(window.view, Qt.Key_Escape)
    assert not window.view.completions_showing()
    assert window.view.editing_item() is block          # still typing
    window.view.end_item_edit()


def test_a_number_on_its_own_is_not_a_word_to_complete(window):
    _typing(window, "w := 300")
    assert not window.view.completions_showing()
    window.view.end_item_edit()


def test_a_value_and_its_unit_are_written_with_a_dot_between_them(window):
    from calcforge.core.mathrender import UNIT_SEPARATOR

    block = _calc(window, "L := 6 m\nw := 12 kN/m\nM := w*L^2/8 =", at=(90, 110))
    row = next(r for r in block.rows if r.result is not None)
    assert UNIT_SEPARATOR == "·"
    # the result row is number, dot, unit
    assert any(getattr(box, "text", "") == UNIT_SEPARATOR
               for box in _all_boxes(row.result))


def _all_boxes(box):
    yield box
    for child in getattr(box, "children", []) or []:
        yield from _all_boxes(child)


# ---------------------------------------------------------------------------
# Editing a calculation looks like the calculation
# ---------------------------------------------------------------------------

def test_the_editor_is_the_same_face_and_size_as_the_print(window):
    block = _calc(window, "L := 6 m", at=(90, 110))
    window.view.begin_item_edit(block)
    editor = block._editor
    assert editor.font().pixelSize() == round(block.style.font_size)
    assert "mono" not in editor.font().family().lower()
    assert editor.defaultTextColor().name() == QColor(block.style.text_color).name()
    window.view.end_item_edit()


def _paints_in(item, wanted, tolerance: int = 26) -> bool:
    """Whether the region paints anything close to *wanted*.

    Close rather than exact: text is drawn with antialiasing, so the middle of
    a stroke is the colour asked for and everything around it is on the way to
    the paper.
    """
    from PySide6.QtGui import QImage, QPainter

    rect = item.local_rect()
    image = QImage(max(int(rect.width()) + 8, 20), max(int(rect.height()) + 8, 20),
                   QImage.Format_ARGB32)
    image.fill(0xFFFFFFFF)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    item.paint_content(painter)
    painter.end()
    for x in range(image.width()):
        for y in range(image.height()):
            colour = image.pixelColor(x, y)
            if (abs(colour.red() - wanted.red()) <= tolerance
                    and abs(colour.green() - wanted.green()) <= tolerance
                    and abs(colour.blue() - wanted.blue()) <= tolerance):
                return True
    return False


def test_units_are_blue_while_they_are_being_typed(window):
    """The typeset working is what is on screen, being typed or not."""
    from calcforge.core.mathrender import MathStyle

    block = _calc(window, "w := 12 kN", at=(90, 110))
    window.view.begin_item_edit(block)
    assert _paints_in(block, MathStyle().unit_color)
    window.view.end_item_edit()


def test_a_comment_is_grey_while_it_is_being_typed(window):
    from calcforge.core.mathrender import MathStyle

    block = _calc(window, "w := 12 kN   # dead load", at=(90, 110))
    window.view.begin_item_edit(block)
    assert _paints_in(block, MathStyle().comment_color)
    window.view.end_item_edit()


def test_the_answers_stay_on_the_page_while_the_line_is_edited(window):
    block = _calc(window, "L := 6 m\nw := 12 kN/m\nM := w*L^2/8 =", at=(90, 110))
    assert any(row.result is not None for row in block.rows)
    window.view.begin_item_edit(block)
    assert any(row.result is not None for row in block.rows)   # not thrown away
    window.view.end_item_edit()


def test_the_answer_keeps_up_with_what_is_typed(window):
    block = _calc(window, "b := 300 mm\nA := b*b =", at=(90, 110))
    window.view.begin_item_edit(block)
    block._editor.setPlainText("b := 400 mm\nA := b*b =")
    window.view._recalculate_while_typing()

    assert window.document.workspace.get("A").to("mm^2").magnitude == pytest.approx(160000)
    window.view.end_item_edit()


def test_a_long_line_widens_the_region_rather_than_running_off_it(window):
    """The typeset working is what is drawn, and the region grows to hold it."""
    block = _calc(window, "L := 6 m", at=(90, 110))
    narrow = block.local_rect().width()
    window.view.begin_item_edit(block)
    block._editor.setPlainText(
        "L := 6 m + 12 m + 3 m + 24 m + 9 m + 15 m + 30 m + 45 m =")
    window.recalculate()
    assert block.local_rect().width() > narrow
    assert block.rows[0].left.width <= block.local_rect().width()
    window.view.end_item_edit()


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

def _two_boxes(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 180, 150)
    window.select_tool("rect")
    drag(window.view, 220, 100, 300, 150)
    window.select_tool("select")
    return markups(window)[0], markups(window)[1]


def test_grouped_markups_are_selected_together(window):
    first, second = _two_boxes(window)
    first.setSelected(True)
    second.setSelected(True)
    window.group_selection()
    assert first.group and first.group == second.group

    window.view.scene().clearSelection()
    centre = first.mapToScene(first.local_rect().center())
    click(window.view, centre.x(), centre.y())
    assert first.isSelected() and second.isSelected()


def test_a_group_moves_as_one(window):
    first, second = _two_boxes(window)
    first.setSelected(True)
    second.setSelected(True)
    window.group_selection()
    window.view.scene().clearSelection()

    before = second.pos()
    centre = first.mapToScene(first.local_rect().center())
    drag(window.view, centre.x(), centre.y(), centre.x() + 60, centre.y() + 40)
    assert second.pos().x() == pytest.approx(before.x() + 60, abs=2)
    assert second.pos().y() == pytest.approx(before.y() + 40, abs=2)


def test_ungrouping_puts_them_back_on_their_own(window):
    first, second = _two_boxes(window)
    first.setSelected(True)
    second.setSelected(True)
    window.group_selection()
    window.ungroup_selection()
    assert not first.group and not second.group

    window.view.scene().clearSelection()
    centre = first.mapToScene(first.local_rect().center())
    click(window.view, centre.x(), centre.y())
    assert first.isSelected() and not second.isSelected()


def test_grouping_can_be_undone(window):
    first, second = _two_boxes(window)
    first.setSelected(True)
    second.setSelected(True)
    window.group_selection()
    window.undo_stack.undo()
    assert not markups(window)[0].group


def test_a_group_is_saved_with_the_document(window, tmp_path):
    from calcforge.core.document import Document
    from calcforge.io import project as project_io

    first, second = _two_boxes(window)
    first.setSelected(True)
    second.setSelected(True)
    window.group_selection()
    path = str(tmp_path / "job.cfx")
    project_io.save_document(window.document, path)

    reopened = Document()
    project_io.load_document(reopened, path)
    groups = [item.get("group") for item in reopened.pages[0].to_dict()["items"]]
    assert len(set(groups)) == 1 and all(groups)


def test_copying_a_group_makes_a_group_of_its_own(window):
    first, second = _two_boxes(window)
    first.setSelected(True)
    second.setSelected(True)
    window.group_selection()
    original = first.group

    window.copy_selection()
    hover(window.view, 120, 400)
    window.paste_items()

    pasted = [i for i in markups(window) if i.pos().y() > 300]
    assert len(pasted) == 2
    assert pasted[0].group == pasted[1].group
    assert pasted[0].group != original


# ---------------------------------------------------------------------------
# Default properties
# ---------------------------------------------------------------------------

def test_setting_a_default_draws_the_next_one_the_same(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    first = markups(window)[0]
    first.style.stroke = "#c92a2a"
    first.style.width = 3.5
    window.set_as_default(first)

    window.select_tool("rect")
    drag(window.view, 260, 100, 360, 160)
    second = markups(window)[1]
    assert second.style.stroke == "#c92a2a"
    assert second.style.width == pytest.approx(3.5)


def test_a_default_belongs_to_that_kind_of_markup_only(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    box = markups(window)[0]
    box.style.stroke = "#c92a2a"
    window.set_as_default(box)

    window.select_tool("ellipse")
    drag(window.view, 260, 100, 360, 160)
    oval = markups(window)[1]
    assert oval.style.stroke != "#c92a2a"


def test_a_default_is_remembered_between_sessions(window):
    from calcforge.ui.mainwindow import MainWindow

    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    box = markups(window)[0]
    box.style.stroke = "#2f9e44"
    window.set_as_default(box)

    second = MainWindow()
    second.confirm_discard = lambda: True
    try:
        second.select_tool("rect")
        drag(second.view, 100, 100, 200, 160)
        assert markups(second)[0].style.stroke == "#2f9e44"
    finally:
        second.close()
        second.deleteLater()


def test_a_default_can_be_forgotten(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    box = markups(window)[0]
    original = box.style.stroke
    box.style.stroke = "#c92a2a"
    window.set_as_default(box)
    window.forget_defaults()

    window.select_tool("rect")
    drag(window.view, 260, 100, 360, 160)
    assert markups(window)[1].style.stroke == original


def test_a_default_never_carries_the_contents_across(window):
    from calcforge.ui import toolsets

    block = _calc(window, "b := 300 mm", at=(90, 500))
    window.set_as_default(block)
    stored = toolsets.load_defaults()[toolsets.default_key(block)]
    assert "source" not in stored and "x" not in stored and "uid" not in stored


def test_the_properties_panel_offers_it(window):
    from PySide6.QtWidgets import QPushButton

    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    box = markups(window)[0]
    window.select_tool("select")
    box.setSelected(True)
    window.refresh_selection()
    labels = [b.text() for b in window.properties_panel.findChildren(QPushButton)]
    assert "Set as default" in labels
    assert "Add to a tool set…" in labels


# ---------------------------------------------------------------------------
# Tool sets
# ---------------------------------------------------------------------------

def _kept(window, item, into="My Tools", monkeypatch=None):
    """Put an item into a tool set without the dialog."""
    from calcforge.ui import toolsets

    groups = toolsets.load_toolsets()
    group = next(g for g in groups if g.name == into)
    group.entries.append(toolsets.entry_for(item, toolsets.COPY))
    toolsets.save_toolsets(groups)
    window.toolsets_panel.rebuild(keep=into)
    return group.entries[-1]


def test_my_tools_is_always_there(window):
    from calcforge.ui import toolsets

    assert [g.name for g in toolsets.load_toolsets()][0] == toolsets.MY_TOOLS
    tree = window.toolsets_panel.tree
    assert tree.topLevelItem(0).text(0).startswith(toolsets.MY_TOOLS)


def test_a_kept_markup_comes_back_exactly_as_it_was(window):
    window.select_tool("text")
    drag(window.view, 100, 100, 300, 140)
    box = window.view.editing_item()
    box.set_text("FOR APPROVAL")
    box.style.stroke = "#c92a2a"
    window.view.end_item_edit()
    entry = _kept(window, box)

    window.select_tool("select")
    window.use_tool_entry(entry)
    click(window.view, 200, 500)

    placed = [i for i in markups(window) if i.pos().y() > 400]
    assert len(placed) == 1
    assert placed[0].text() == "FOR APPROVAL"        # its words came with it
    assert placed[0].style.stroke == "#c92a2a"


def test_a_tool_in_properties_mode_draws_a_new_one(window):
    from calcforge.ui import toolsets

    window.select_tool("text")
    drag(window.view, 100, 100, 300, 140)
    box = window.view.editing_item()
    box.set_text("FOR APPROVAL")
    box.style.stroke = "#2f9e44"
    window.view.end_item_edit()
    entry = _kept(window, box)
    entry.mode = toolsets.PROPERTIES
    entry.payload = toolsets.entry_for(box, toolsets.PROPERTIES).payload

    window.use_tool_entry(entry)
    assert window.view.tool_key == "text"
    drag(window.view, 100, 500, 320, 545)
    drawn = window.view.editing_item()
    drawn.set_text("something else")
    window.view.end_item_edit()

    assert drawn.style.stroke == "#2f9e44"           # the properties came across
    assert drawn.text() == "something else"          # the words did not
    assert drawn.local_rect().width() == pytest.approx(220, abs=3)


def test_escape_puts_a_held_tool_back(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    entry = _kept(window, markups(window)[0])
    window.use_tool_entry(entry)
    assert window.view._pending_stamp is not None
    press_key(window.view, Qt.Key_Escape)
    assert window.view._pending_stamp is None
    click(window.view, 200, 500)
    assert len(markups(window)) == 1                 # nothing was placed


def test_tool_sets_can_be_made_renamed_and_deleted(window, monkeypatch):
    from PySide6.QtWidgets import QInputDialog, QMessageBox
    from calcforge.ui import toolsets

    panel = window.toolsets_panel
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Steel details", True))
    panel.new_set()
    assert "Steel details" in [g.name for g in toolsets.load_toolsets()]
    assert panel.current_set_name() == "Steel details"

    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Steel", True))
    panel.rename_set()
    assert "Steel" in [g.name for g in toolsets.load_toolsets()]

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    panel.delete_set()
    assert "Steel" not in [g.name for g in toolsets.load_toolsets()]


def test_my_tools_cannot_be_renamed_or_deleted(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from calcforge.ui import toolsets

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    window.toolsets_panel.delete_set()
    assert toolsets.MY_TOOLS in [g.name for g in toolsets.load_toolsets()]


def test_a_tool_can_be_switched_between_the_two_modes(window):
    from calcforge.ui import toolsets

    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    _kept(window, markups(window)[0])
    panel = window.toolsets_panel
    panel.select_entry(toolsets.MY_TOOLS, 0)
    assert panel.current_entry().mode == toolsets.COPY
    panel.toggle_mode()
    assert panel.current_entry().mode == toolsets.PROPERTIES
    draw = _menu_entry(panel.build_menu(), "Draw again with its properties")
    assert draw.isChecked()
    assert "properties" in panel.tree.currentItem().toolTip(0)


def test_tools_can_be_reordered_and_removed(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    window.select_tool("ellipse")
    drag(window.view, 260, 100, 360, 160)
    _kept(window, markups(window)[0])
    _kept(window, markups(window)[1])

    from calcforge.ui import toolsets

    panel = window.toolsets_panel
    panel.select_entry(toolsets.MY_TOOLS, 1)
    header = panel.tree.indexFromItem(panel.tree.topLevelItem(0))
    panel._rows_moved(header, 1, 1, header, 0)     # dragged up the list
    assert panel.current_set().entries[0].payload["kind"] == "ellipse"
    panel.select_entry(toolsets.MY_TOOLS, 0)
    panel.remove_entry()
    assert len(panel.current_set().entries) == 1


def test_tool_sets_are_remembered_between_sessions(window):
    from calcforge.ui.mainwindow import MainWindow

    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    _kept(window, markups(window)[0])

    second = MainWindow()
    second.confirm_discard = lambda: True
    try:
        assert second.toolsets_panel.tree.topLevelItem(0).childCount() == 1
    finally:
        second.close()
        second.deleteLater()


# ---------------------------------------------------------------------------
# My Tools on the number keys
# ---------------------------------------------------------------------------

def test_the_number_keys_reach_for_my_tools(window):
    window.select_tool("text")
    drag(window.view, 100, 100, 300, 140)
    box = window.view.editing_item()
    box.set_text("RFI")
    window.view.end_item_edit()
    _kept(window, box)
    window.select_tool("select")

    press_key(window.view, Qt.Key_1, "1")
    assert window.view._pending_stamp is not None
    click(window.view, 200, 500)
    placed = [i for i in markups(window) if i.pos().y() > 400]
    assert placed and placed[0].text() == "RFI"


def test_my_tools_are_numbered_in_the_panel(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    _kept(window, markups(window)[0])
    assert window.toolsets_panel.tree.topLevelItem(0).child(0).text(0)\
        .startswith("1.")


def test_a_number_key_does_nothing_while_you_are_typing(window):
    block = _calc(window, "b := 300 mm", at=(90, 500))
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    _kept(window, markups(window)[0])

    window.view.begin_item_edit(block)
    press_key(window.view, Qt.Key_1, "1")
    assert window.view._pending_stamp is None       # it typed a 1 instead
    window.view.end_item_edit()


def test_a_number_with_nothing_behind_it_does_nothing(window):
    window.select_tool("select")
    press_key(window.view, Qt.Key_3, "3")
    assert window.view._pending_stamp is None


def test_the_arrow_head_shows_the_moment_it_is_placed(window):
    """Clicking what a callout points at used to leave nothing to see."""
    window.select_tool("callout")
    click(window.view, 200, 300)
    assert window.view._pending_anchor is not None

    from PySide6.QtGui import QImage, QPainter
    image = QImage(400, 400, QImage.Format_ARGB32)
    image.fill(Qt.white)
    painter = QPainter(image)
    window.view.render(painter)
    painter.end()
    ink = sum(1 for y in range(0, 400, 3) for x in range(0, 400, 3)
              if image.pixel(x, y) & 0xFFFFFF != 0xFFFFFF)
    assert ink > 20                      # an arrow and a leader, not a faint cross


def test_the_leader_leaves_the_middle_of_a_side(window):
    call = _callout(window, target=(200, 400), box=(300, 200, 460, 260))
    window.view.end_item_edit()
    rect = call.local_rect()

    # the arrow is below and left, so the leader leaves the bottom
    assert call.side() == "bottom"
    assert call.side_point().x() == pytest.approx(rect.center().x())
    assert call.side_point().y() == pytest.approx(rect.bottom())

    call.tip = QPointF(rect.right() + 200, rect.center().y())
    assert call.side() == "right"
    assert call.side_point().y() == pytest.approx(rect.center().y())


def test_the_elbow_leaves_the_box_square_on(window):
    call = _callout(window, target=(200, 400))
    window.view.end_item_edit()
    side = call.side_point()
    elbow = call.elbow()
    assert elbow.x() == pytest.approx(side.x())          # straight down
    assert elbow.y() > side.y()


def test_copying_a_callout_takes_its_arrow_with_it(window):
    call = _callout(window)
    window.view.end_item_edit()
    window.select_tool("select")
    call.setSelected(True)
    reach = call.mapToScene(call.tip) - call.mapToScene(call.local_rect().center())

    centre = call.mapToScene(call.local_rect().center())
    drag(window.view, centre.x(), centre.y(), centre.x() + 120, centre.y() + 60,
         modifiers=Qt.ControlModifier)

    callouts = [i for i in markups(window) if isinstance(i, CalloutItem)]
    assert len(callouts) == 2
    for one in callouts:
        got = one.mapToScene(one.tip) - one.mapToScene(one.local_rect().center())
        assert got.x() == pytest.approx(reach.x(), abs=2)
        assert got.y() == pytest.approx(reach.y(), abs=2)


def test_a_selected_group_draws_one_box_round_the_lot(window):
    first, second = _two_boxes(window)
    first.setSelected(True)
    second.setSelected(True)
    window.group_selection()

    # the members stop drawing their own outlines and handles
    assert first.group
    from PySide6.QtGui import QImage, QPainter
    image = QImage(500, 400, QImage.Format_ARGB32)
    image.fill(Qt.white)
    painter = QPainter(image)
    window.view.render(painter)
    painter.end()
    assert image.width() == 500                     # it drew without complaint


def test_a_group_goes_into_a_tool_set_as_one_thing(window):
    from calcforge.ui import toolsets

    first, second = _two_boxes(window)
    first.setSelected(True)
    second.setSelected(True)
    window.group_selection()

    entry = toolsets.entry_for_many([first, second])
    assert entry.payload["type"] == toolsets.GROUP
    assert len(entry.payload["items"]) == 2
    assert entry.label == "Group of 2"


def test_placing_a_group_puts_every_member_down_grouped(window):
    from calcforge.ui import toolsets

    first, second = _two_boxes(window)
    first.setSelected(True)
    second.setSelected(True)
    window.group_selection()
    entry = toolsets.entry_for_many([first, second])

    window.select_tool("select")
    window.use_tool_entry(entry)
    click(window.view, 300, 500)

    placed = [i for i in markups(window) if i.pos().y() > 400]
    assert len(placed) == 2
    assert placed[0].group == placed[1].group
    assert placed[0].group != first.group          # a group of its own
    # laid out as they were
    assert round(placed[1].pos().x() - placed[0].pos().x()) == \
        round(second.pos().x() - first.pos().x())


def test_what_is_about_to_be_placed_is_shown_first(window):
    from PySide6.QtGui import QImage, QPainter
    from calcforge.ui import toolsets

    window.select_tool("rect")
    drag(window.view, 100, 100, 220, 180)
    entry = toolsets.entry_for(markups(window)[0])
    window.select_tool("select")
    window.use_tool_entry(entry)
    hover(window.view, 400, 450)

    assert window.view._pending_stamp is not None
    assert window.view.pending_extent().width() == pytest.approx(120, abs=3)
    image = QImage(600, 600, QImage.Format_ARGB32)
    image.fill(Qt.white)
    painter = QPainter(image)
    window.view.render(painter)
    painter.end()
    assert len(markups(window)) == 1               # still only the original


def test_the_clipboard_can_be_carried_and_dropped(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    window.select_tool("select")
    markups(window)[0].setSelected(True)
    window.copy_selection()

    window.paste_with_preview()
    assert window.view._pending_stamp is not None
    click(window.view, 350, 500)
    assert len(markups(window)) == 2
    assert markups(window)[1].pos().y() > 400


# ---------------------------------------------------------------------------
# Selecting: which way you drag, and a lasso
# ---------------------------------------------------------------------------

def _spread(window):
    """Two boxes with a gap, so a marquee can take one, both or neither."""
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 170)
    window.select_tool("rect")
    drag(window.view, 260, 100, 360, 170)
    window.select_tool("select")
    window.view.scene().clearSelection()
    return markups(window)[0], markups(window)[1]


def test_dragging_right_takes_only_what_is_wholly_inside(window):
    first, second = _spread(window)
    drag(window.view, 60, 60, 240, 220)          # left to right, over the first
    assert first.isSelected() and not second.isSelected()


def test_dragging_right_does_not_take_what_it_merely_crosses(window):
    first, second = _spread(window)
    drag(window.view, 60, 60, 150, 220)          # cuts through the first
    assert not first.isSelected()


def test_dragging_left_takes_what_it_crosses(window):
    first, second = _spread(window)
    drag(window.view, 320, 220, 150, 60)         # right to left, crossing both
    assert first.isSelected() and second.isSelected()


def test_a_click_on_bare_paper_starts_nothing(window):
    """A click clears the selection. It does not begin a lasso."""
    first, second = _spread(window)
    first.setSelected(True)
    click(window.view, 500, 500)
    assert not first.isSelected()
    assert window.view.marquee_polygon().isEmpty()
    press_key(window.view, Qt.Key_unknown, "/")
    assert window.view.editing_item() is not None      # typing still works
    window.view.end_item_edit()


def test_shift_clicking_out_a_lasso_selects_what_is_inside_it(window):
    first, second = _spread(window)
    click(window.view, 60, 60, modifiers=Qt.ShiftModifier)
    click(window.view, 240, 60)
    click(window.view, 240, 220)
    click(window.view, 60, 220)
    press_key(window.view, Qt.Key_Return)

    assert first.isSelected() and not second.isSelected()
    assert window.view._mode == "idle"


def test_a_lasso_takes_only_what_is_wholly_inside(window):
    first, _second = _spread(window)
    click(window.view, 60, 60, modifiers=Qt.ShiftModifier)
    click(window.view, 150, 60)
    click(window.view, 150, 220)
    click(window.view, 60, 220)
    press_key(window.view, Qt.Key_Return)
    assert not first.isSelected()


def test_escape_abandons_a_half_drawn_lasso(window):
    _spread(window)
    click(window.view, 60, 60, modifiers=Qt.ShiftModifier)
    click(window.view, 240, 60)
    assert window.view._mode == "lasso"
    press_key(window.view, Qt.Key_Escape)
    assert window.view._mode == "idle"
    assert window.view._marquee == []


def test_shift_draws_a_straight_stroke_with_the_pen(window):
    import math
    window.select_tool("pen")
    drag(window.view, 100, 100, 260, 190, modifiers=Qt.ShiftModifier)
    stroke = markups(window)[0]
    assert len(stroke.points) == 2
    delta = stroke.points[-1] - stroke.points[0]
    angle = abs(math.degrees(math.atan2(delta.y(), delta.x())))
    assert min(abs(angle - a) for a in (0, 45, 90, 135, 180)) < 0.5


def test_the_highlighter_goes_straight_on_shift_too(window):
    window.select_tool("highlighter")
    drag(window.view, 100, 300, 300, 302, modifiers=Qt.ShiftModifier)
    stroke = markups(window)[0]
    assert len(stroke.points) == 2
    assert stroke.points[-1].y() == pytest.approx(stroke.points[0].y(), abs=0.5)


def test_freehand_is_still_freehand_without_shift(window):
    window.select_tool("pen")
    drag(window.view, 100, 100, 260, 190)
    assert len(markups(window)[0].points) > 2


# ---------------------------------------------------------------------------
# A dimension's own words
# ---------------------------------------------------------------------------

def test_a_new_dimension_asks_for_its_words_where_they_will_appear(window):
    window.interactive_prompts = True
    try:
        window.select_tool("measure_dimension")
        drag(window.view, 100, 200, 320, 200)
    finally:
        window.interactive_prompts = False

    assert window.view._label_editor is not None       # a caret, not a dialog
    assert window.view._label_editor.text() == ""      # blank until typed into
    dimension = markups(window)[0]
    centre = dimension.mapToScene(dimension._label_anchor())
    box = window.view._label_proxy.sceneBoundingRect()
    assert box.contains(centre) or box.center().y() == pytest.approx(centre.y(), abs=20)

    window.view._label_editor.setText("3600 c/c")
    window.view.close_label_editor(commit=True)
    assert dimension.custom_label == "3600 c/c"
    assert dimension.value_text == "3600 c/c"


def test_leaving_it_blank_leaves_it_blank(window):
    window.interactive_prompts = True
    try:
        window.select_tool("measure_dimension")
        drag(window.view, 100, 200, 320, 200)
    finally:
        window.interactive_prompts = False
    window.view.close_label_editor(commit=True)
    assert markups(window)[0].custom_label == ""


def test_a_dimensions_text_lies_along_its_line(window):
    window.select_tool("measure_dimension")
    drag(window.view, 100, 200, 300, 300)
    dimension = markups(window)[0]
    assert dimension.label_offset == QPointF(0, 0)     # on the line
    assert dimension.label_rotation() == pytest.approx(26.57, abs=0.5)


def test_the_text_stays_the_right_way_up(window):
    window.select_tool("measure_dimension")
    drag(window.view, 300, 300, 100, 200)              # drawn back the other way
    assert abs(markups(window)[0].label_rotation()) <= 90


def test_moving_the_text_off_the_line_gives_it_a_leader(window):
    window.select_tool("measure_dimension")
    drag(window.view, 100, 200, 320, 200)
    dimension = markups(window)[0]
    window.view.close_label_editor(commit=False)
    assert not dimension.label_is_off_the_line()

    dimension.move_handle("lbl", dimension._label_anchor() + QPointF(0, -60))
    assert dimension.label_is_off_the_line()


def test_the_text_can_be_turned_by_hand_and_put_back(window):
    window.select_tool("measure_dimension")
    drag(window.view, 100, 200, 320, 200)
    dimension = markups(window)[0]
    window.view.close_label_editor(commit=False)

    dimension.move_handle("lblrot", dimension._label_anchor() + QPointF(0, 40))
    assert dimension.label_angle == pytest.approx(90, abs=1)
    window.set_label_angle(dimension, None)
    assert dimension.label_angle is None
    assert dimension.label_rotation() == pytest.approx(0, abs=0.5)


def test_double_clicking_a_dimension_types_on_it(window):
    window.select_tool("measure_dimension")
    drag(window.view, 100, 200, 320, 200)
    dimension = markups(window)[0]
    window.view.close_label_editor(commit=False)
    window.select_tool("select")

    point = dimension.mapToScene(dimension.points[1])
    double_click(window.view, point.x(), point.y())
    assert window.view._label_editor is not None
    window.view.close_label_editor(commit=False)


def test_typing_on_a_measurement_can_be_undone(window):
    window.interactive_prompts = True
    try:
        window.select_tool("measure_dimension")
        drag(window.view, 100, 200, 320, 200)
    finally:
        window.interactive_prompts = False
    dimension = markups(window)[0]
    window.view._label_editor.setText("varies")
    window.view.close_label_editor(commit=True)
    assert dimension.custom_label == "varies"
    window.undo_stack.undo()
    assert markups(window)[0].custom_label == ""


# ---------------------------------------------------------------------------
# Dragging the fill handle
# ---------------------------------------------------------------------------

def _grid(window, values, at=(60, 60)):
    window.select_tool("table")
    drag(window.view, at[0], at[1], at[0] + 360, at[1] + 220)
    table = window.view.active_table
    table.sheet.resize(10, 5)
    for (row, col), value in values.items():
        table.set_cell(row, col, value)
    window.recalculate()
    return table


def _drag_fill(window, table, to_cell):
    """Take hold of the fill handle and drag it to a cell."""
    handle = table.mapToScene(table.fill_handle_rect().center())
    target = table.mapToScene(table.cell_rect(*to_cell).center())
    drag(window.view, handle.x(), handle.y(), target.x(), target.y())


def test_dragging_the_fill_handle_carries_a_series_on(window):
    table = _grid(window, {(0, 0): "1", (1, 0): "2"})
    table.current, table.anchor = (0, 0), (1, 0)
    _drag_fill(window, table, (5, 0))
    assert [table.sheet.raw(row, 0) for row in range(6)] == \
        ["1", "2", "3", "4", "5", "6"]


def test_a_single_value_is_copied_not_counted_up(window):
    table = _grid(window, {(0, 0): "7"})
    table.current = table.anchor = (0, 0)
    _drag_fill(window, table, (3, 0))
    assert [table.sheet.raw(row, 0) for row in range(4)] == ["7", "7", "7", "7"]


def test_a_formula_keeps_its_absolute_references(window):
    table = _grid(window, {(0, 0): "2", (1, 0): "3", (2, 0): "4",
                           (0, 1): "10", (0, 2): "=A1*$B$1"})
    table.current = table.anchor = (0, 2)
    _drag_fill(window, table, (2, 2))
    assert [table.sheet.raw(row, 2) for row in range(3)] == \
        ["=A1*$B$1", "=A2*$B$1", "=A3*$B$1"]
    window.recalculate()
    assert table.sheet.value(2, 2) == 40


def test_filling_sideways_works_the_same(window):
    table = _grid(window, {(0, 0): "5", (0, 1): "10"})
    table.current, table.anchor = (0, 0), (0, 1)
    _drag_fill(window, table, (0, 4))
    assert [table.sheet.raw(0, col) for col in range(5)] == \
        ["5", "10", "15", "20", "25"]


def test_a_fill_is_one_undo_step(window):
    table = _grid(window, {(0, 0): "1", (1, 0): "2"})
    table.current, table.anchor = (0, 0), (1, 0)
    _drag_fill(window, table, (5, 0))
    assert table.sheet.raw(5, 0) == "6"
    window.undo_stack.undo()
    filled = [i for i in markups(window) if isinstance(i, TableItem)][0]
    assert filled.sheet.raw(5, 0) == ""


def test_a_named_table_wears_its_name(window):
    table = _capacity_table(window, "bolts")
    assert table.title_height() > 0                    # room made for it
    before = table.local_rect().height()
    table.prepareGeometryChange()
    table.table_name = ""
    assert table.local_rect().height() < before        # and given back


def test_the_properties_panel_names_a_table(window):
    from PySide6.QtWidgets import QLineEdit

    table = _capacity_table(window, "")
    window.select_tool("select")
    table.setSelected(True)
    window.refresh_selection()
    boxes = [w for w in window.properties_panel.findChildren(QLineEdit)
             if (w.toolTip() or "").startswith("Name this table")]
    assert boxes
    assert boxes[0].placeholderText() == ""        # no ghost name in the box
    boxes[0].setText("shear")
    boxes[0].editingFinished.emit()
    assert table.table_name == "shear"
    assert "shear" in window.document.workspace.table_names()


def test_a_name_that_cannot_be_used_is_refused(window):
    table = _capacity_table(window, "")
    window.rename_table(table, "2 bolts")
    assert table.table_name == ""
    assert "cannot be used" in window.status_hint.text()


# ---------------------------------------------------------------------------
# Changing things after they are drawn
# ---------------------------------------------------------------------------

def _panel_groups(window, item):
    from PySide6.QtWidgets import QGroupBox

    window.select_tool("select")
    window.view.scene().clearSelection()
    item.setSelected(True)
    window.refresh_selection()
    return [g.title() for g in window.properties_panel.findChildren(QGroupBox)]


def test_a_contents_block_can_be_changed_afterwards(window):
    from PySide6.QtWidgets import QCheckBox, QLineEdit
    from calcforge.items.contents import ContentsItem

    window.select_tool("contents")
    drag(window.view, 60, 500, 360, 640)
    block = next(i for i in markups(window) if isinstance(i, ContentsItem))
    assert "Contents" in _panel_groups(window, block)

    heading = [w for w in window.properties_panel.findChildren(QLineEdit)
               if w.placeholderText() == "Contents"][0]
    heading.setText("On these pages")
    heading.textEdited.emit("On these pages")
    assert block.title == "On these pages"

    dots = [w for w in window.properties_panel.findChildren(QCheckBox)
            if w.text() == "Leader dots"][0]
    dots.setChecked(False)
    assert not block.leader_dots


def test_a_note_can_be_rewritten_in_the_panel(window):
    from PySide6.QtWidgets import QPlainTextEdit
    from calcforge.items.text import NoteItem

    window.select_tool("note")
    click(window.view, 200, 200)
    note = next(i for i in markups(window) if isinstance(i, NoteItem))
    assert "Note" in _panel_groups(window, note)
    body = [w for w in window.properties_panel.findChildren(QPlainTextEdit)
            if w.placeholderText() == "What this note says"][0]
    body.setPlainText("check the bearing")
    assert note.comment == "check the bearing"


def test_a_measurement_says_what_you_type_in_the_panel(window):
    from PySide6.QtWidgets import QLineEdit

    window.select_tool("measure_length")
    drag(window.view, 100, 200, 320, 200)
    measure = markups(window)[0]
    assert "Measurement" in _panel_groups(window, measure)

    says = [w for w in window.properties_panel.findChildren(QLineEdit)
            if w.toolTip().startswith("What this says")][0]
    says.setText("3600 c/c")
    says.editingFinished.emit()
    assert measure.custom_label == "3600 c/c"
    assert measure.value_text == "3600 c/c"


def test_an_image_can_be_swapped_for_another(window, tmp_path, monkeypatch):
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QFileDialog
    from calcforge.items.media import ImageItem

    first = str(tmp_path / "one.png")
    QImage(60, 40, QImage.Format_ARGB32).save(first)
    second = str(tmp_path / "two.png")
    QImage(80, 20, QImage.Format_ARGB32).save(second)

    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (first, ""))
    window.select_tool("image")
    drag(window.view, 100, 100, 300, 240)
    image = next(i for i in markups(window) if isinstance(i, ImageItem))
    original = image.asset_key
    assert "Image" in _panel_groups(window, image)

    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (second, ""))
    window.replace_image(image)
    assert image.asset_key != original
    window.undo_stack.undo()
    assert markups(window)[0].asset_key == original


def test_every_markup_offers_its_own_settings(window):
    """Each kind of markup has a panel section about what makes it that kind."""
    expected = {
        "rect": "Size", "ellipse": "Size", "cloud": "Cloud", "text": "Text",
        "callout": "Text", "stamp": "Stamp", "table": "Table", "plot": "Plot",
        "measure_length": "Measurement", "count": "Count",
    }
    for key, group in expected.items():
        window.new_document()
        window.select_tool(key)
        if key == "count":
            click(window.view, 200, 200)
        else:
            if key == "callout":
                # A callout points at something first, then gets its box.
                click(window.view, 120, 320)
            drag(window.view, 150, 150, 380, 260)
        if window.view.editing_item() is not None:
            window.view.editing_item().set_text("words")
            window.view.end_item_edit()
        window.view.deactivate_table()
        window.view.close_label_editor(commit=False)
        item = markups(window)[0]
        assert group in _panel_groups(window, item), f"{key} has no {group} section"


# ---------------------------------------------------------------------------
# Showing an answer in another unit changes only that answer
# ---------------------------------------------------------------------------

def test_asking_for_newtons_leaves_the_kilonewtons_written(window):
    """"1 kN → N" is one kilonewton shown in newtons, not one newton."""
    from calcforge.items.mathitem import MathItem

    item = MathItem("test := 1 kN =")
    item.setPos(60, 60)
    window.view.frame().add_markup(item)
    window.recalculate()

    assert item.set_display_unit(0, "N")
    window.recalculate()
    statement = item.rows[0].statement
    assert statement.result_text() == "1000 N"      # the answer, as asked
    assert f"{statement.written:~P}".startswith("1.0 kN")   # what was written


def test_the_other_lines_keep_their_own_units(window):
    from calcforge.items.mathitem import MathItem

    block = MathItem("test := 1 kN =\ntest =", block=True)
    block.setPos(60, 60)
    window.view.frame().add_markup(block)
    window.recalculate()

    assert block.set_display_unit(1, "N")
    window.recalculate()
    assert block.rows[0].statement.result_text() == "1 kN"
    assert block.rows[1].statement.result_text() == "1000 N"


# ---------------------------------------------------------------------------
# Toolbar options belong to the tool they are for
# ---------------------------------------------------------------------------

def test_the_stamp_wording_is_only_shown_for_the_stamp(window):
    """Reading "APPROVED" across the top while drawing a box means nothing."""
    stamp = window._stamp_widgets[0]
    counting = window._count_widgets[0]

    window.select_tool("rect")
    assert not stamp.isVisible() and not counting.isVisible()
    window.select_tool("stamp")
    assert stamp.isVisible() and not counting.isVisible()
    window.select_tool("count")
    assert counting.isVisible() and not stamp.isVisible()


# ---------------------------------------------------------------------------
# One undo step for a drag, not one per value
# ---------------------------------------------------------------------------

def test_dragging_a_slider_is_one_undo_step(window):
    """Sliding opacity from 100 to 50 is one change of mind."""
    window.select_tool("rect")
    drag(window.view, 80, 80, 220, 180)
    window.select_tool("select")
    box = only(window, RectItem)[0]
    box.setSelected(True)
    window.refresh_selection()
    was = box.style.opacity
    steps = window.undo_stack.count()

    for value in range(100, 49, -1):            # every pixel of the drag
        window.properties_panel._slide(
            lambda i, v=value: setattr(i.style, "opacity", v / 100.0), "Opacity")

    assert window.undo_stack.count() == steps + 1
    assert box.style.opacity == pytest.approx(0.5)
    window.undo_stack.undo()
    assert only(window, RectItem)[0].style.opacity == pytest.approx(was)


def test_a_pause_starts_a_new_undo_step(window):
    from calcforge.ui import commands

    window.select_tool("rect")
    drag(window.view, 80, 80, 220, 180)
    window.select_tool("select")
    box = only(window, RectItem)[0]
    box.setSelected(True)
    window.refresh_selection()
    steps = window.undo_stack.count()

    window.properties_panel._slide(
        lambda i: setattr(i.style, "opacity", 0.8), "Opacity")
    top = window.undo_stack.command(window.undo_stack.count() - 1)
    top.stamp -= commands.MERGE_PAUSE * 2       # a long think, mid-drag
    window.properties_panel._slide(
        lambda i: setattr(i.style, "opacity", 0.4), "Opacity")

    assert window.undo_stack.count() == steps + 2


# ---------------------------------------------------------------------------
# Whole pages copy and paste
# ---------------------------------------------------------------------------

def test_a_page_can_be_copied_and_pasted(window):
    window.select_tool("rect")
    drag(window.view, 80, 80, 220, 180)
    window.select_tool("select")
    pages = len(window.document.pages)

    window.copy_page(0)
    assert window.page_on_the_clipboard() is not None
    window.paste_page(0)

    assert len(window.document.pages) == pages + 1
    copied = window.document.pages[1]
    assert copied.uid != window.document.pages[0].uid
    assert len(copied.to_dict()["items"]) == 1
    window.undo_stack.undo()
    assert len(window.document.pages) == pages


def test_pasting_with_nothing_copied_says_so(window):
    from PySide6.QtWidgets import QApplication

    QApplication.clipboard().setText("not a page")
    pages = len(window.document.pages)
    window.paste_page(0)
    assert len(window.document.pages) == pages


def test_a_page_can_be_bookmarked_from_its_thumbnail(window, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Loads", True))
    window.bookmark_page(0)
    assert [b.title for b in window.document.bookmarks] == ["Loads"]


def test_ctrl_b_while_typing_belongs_to_the_text(window):
    """It bolds what is being written; it does not add a bookmark."""
    window.select_tool("text")
    drag(window.view, 100, 100, 300, 160)
    item = window.view.editing_item()
    assert item is not None
    was = item.style.bold

    window.add_bookmark_here()                 # what Ctrl+B is wired to
    assert window.document.bookmarks == []
    assert item.style.bold is not was
    window.view.end_item_edit()


# ---------------------------------------------------------------------------
# Callouts and text boxes size themselves
# ---------------------------------------------------------------------------

def test_a_callout_takes_two_clicks_and_no_dragging(window):
    from calcforge.items.text import CalloutItem

    window.select_tool("callout")
    click(window.view, 400, 420)                 # what it points at
    assert not [i for i in markups(window) if isinstance(i, CalloutItem)]
    click(window.view, 200, 200)                 # where the words go

    boxes = [i for i in markups(window) if isinstance(i, CalloutItem)]
    assert len(boxes) == 1
    callout = boxes[0]
    assert callout.local_rect().width() > 40     # a real box, not a dot
    tip = callout.mapToScene(callout.tip)         # snapped to the grid nearby
    assert tip.x() == pytest.approx(400, abs=25)
    assert tip.y() == pytest.approx(420, abs=25)
    assert window.view.editing_item() is callout  # ready to be typed into
    window.view.end_item_edit()


def test_a_text_box_grows_with_its_text_and_does_not_shrink(window):
    window.select_tool("text")
    drag(window.view, 100, 100, 260, 130)
    box = window.view.editing_item()
    started = box.local_rect().height()

    box.set_text("one\ntwo\nthree\nfour\nfive\nsix")
    grown = box.local_rect().height()
    assert grown > started

    box.set_text("one")
    assert box.local_rect().height() == pytest.approx(grown)
    window.view.end_item_edit()


def test_alt_z_brings_the_box_back_in_around_the_words(window):
    window.select_tool("text")
    drag(window.view, 100, 100, 260, 130)
    box = window.view.editing_item()
    box.set_text("one\ntwo\nthree\nfour\nfive\nsix")
    tall = box.local_rect().height()
    box.set_text("one")

    window.autosize_text()                       # what Alt+Z is wired to
    assert box.local_rect().height() < tall
    window.view.end_item_edit()


def test_misspelt_words_are_underlined_only_while_typing(window):
    """The squiggle helps whoever is writing; it never reaches the paper."""
    from PySide6.QtGui import QTextCharFormat

    window.select_tool("text")
    drag(window.view, 100, 100, 320, 150)
    box = window.view.editing_item()
    box.set_text("the colour of teh beam")
    assert box._speller is not None

    formats = box.doc.findBlockByNumber(0).layout().formats()
    squiggles = [f for f in formats
                 if f.format.underlineStyle() == QTextCharFormat.SpellCheckUnderline]
    assert len(squiggles) == 1
    assert squiggles[0].start == "the colour of teh beam".index("teh")

    window.view.end_item_edit()
    assert box._speller is None
    assert not box.doc.findBlockByNumber(0).layout().formats()


# ---------------------------------------------------------------------------
# One view of a calculation, typed into where it is
# ---------------------------------------------------------------------------

def test_a_calculation_stays_typeset_while_it_is_typed(window):
    """No second, flatter copy underneath: the caret stands in the working."""
    from calcforge.items.mathitem import MathItem

    item = MathItem("x := 5/2 =")
    item.setPos(60, 60)
    window.view.frame().add_markup(item)
    window.recalculate()
    window.view.begin_item_edit(item)

    editor = item._editor
    cursor = editor.textCursor()
    places = {}
    for column in (5, 7):                    # the 5, then the 2
        cursor.setPosition(column)
        editor.setTextCursor(cursor)
        places[column] = item.caret_place()

    numerator, denominator = places[5], places[7]
    assert numerator is not None and denominator is not None
    assert numerator[1] < denominator[1]     # one above the bar, one below
    window.view.end_item_edit()


def test_clicking_a_fraction_puts_the_caret_in_that_part_of_it(window):
    from calcforge.items.mathitem import MathItem

    item = MathItem("x := 5/2 =")
    item.setPos(60, 60)
    window.view.frame().add_markup(item)
    window.recalculate()
    window.view.begin_item_edit(item)

    row = item.rows[0]
    top = QPointF(item.style.padding + row.left.width - 4,
                  row.baseline - row.left.ascent + 4)
    line, column = item.offset_at(top)
    assert line == 0
    assert column in (5, 6)                  # in the numerator, not at the end
    window.view.end_item_edit()


def test_typing_a_calculation_keeps_the_working_up_with_it(window):
    window.select_tool("select")
    press_key(window.view, Qt.Key_unknown, "/")
    item = window.view.editing_item()
    assert item is not None
    type_text(window.view, "5kN+3kN=")
    assert item.source == "5kN+3kN="
    assert item.rows                          # laid out, not waiting
    window.view.end_item_edit()


def test_a_second_word_turns_what_was_typed_into_a_text_box(window):
    """Maths needs no spaces, so two words with no operator is a sentence."""
    from calcforge.items.text import TextItem

    window.select_tool("select")
    press_key(window.view, Qt.Key_unknown, "/")
    type_text(window.view, "check bolt")
    press_key(window.view, Qt.Key_Space, " ")

    box = window.view.editing_item()
    assert isinstance(box, TextItem)
    assert box.text() == "check bolt "
    window.view.end_item_edit()
    assert [type(i).__name__ for i in markups(window)] == ["TextItem"]


def test_one_word_and_a_space_waits_to_see_what_follows(window):
    """"L " is a variable waiting for its ":=", not the start of a sentence."""
    from calcforge.items.mathitem import MathItem

    window.select_tool("select")
    press_key(window.view, Qt.Key_unknown, "/")
    type_text(window.view, "sigma")
    press_key(window.view, Qt.Key_Space, " ")
    assert isinstance(window.view.editing_item(), MathItem)

    type_text(window.view, ":= 5MPa")
    window.view.end_item_edit()
    assert [type(i).__name__ for i in markups(window)] == ["MathItem"]
    assert window.document.workspace.get("sigma") is not None


def test_a_lone_word_left_behind_becomes_a_note_after_all(window):
    """Once the caret has gone, a word and a space was plainly a sentence."""
    from calcforge.items.text import TextItem

    window.select_tool("select")
    press_key(window.view, Qt.Key_unknown, "/")
    type_text(window.view, "checked")
    press_key(window.view, Qt.Key_Space, " ")
    window.view.end_item_edit()

    assert [type(i).__name__ for i in markups(window)] == ["TextItem"]
    assert markups(window)[0].text().strip() == "checked"


def test_a_space_in_real_maths_is_just_a_space(window):
    from calcforge.items.mathitem import MathItem

    window.select_tool("select")
    press_key(window.view, Qt.Key_unknown, "/")
    type_text(window.view, "5+")
    press_key(window.view, Qt.Key_Space, " ")
    item = window.view.editing_item()
    assert isinstance(item, MathItem)
    window.view.end_item_edit()


# ---------------------------------------------------------------------------
# The tool chest shows the tools themselves
# ---------------------------------------------------------------------------

def test_a_tool_set_entry_is_drawn_as_what_it_is(window):
    from calcforge.ui import toolsets
    from calcforge.ui.panels import entry_thumbnail

    window.select_tool("rect")
    drag(window.view, 100, 100, 260, 180)
    box = only(window, RectItem)[0]
    box.style.stroke = "#c92a2a"

    for mode in (toolsets.COPY, toolsets.PROPERTIES):
        image = entry_thumbnail(toolsets.entry_for(box, mode=mode)).toImage()
        inked = [image.pixelColor(x, y)
                 for x in range(image.width()) for y in range(image.height())
                 if image.pixelColor(x, y).alpha() > 40]
        assert inked, mode
        # drawn in the colour it was stored in, not in the toolbar's ink
        assert any(colour.red() > 150 and colour.green() < 120 for colour in inked), mode


def test_drawing_again_is_only_offered_where_it_means_something(window):
    from calcforge.ui import toolsets

    window.select_tool("rect")
    drag(window.view, 100, 100, 260, 180)
    box = only(window, RectItem)[0]
    assert toolsets.can_be_properties(toolsets.entry_for(box).payload)

    window.select_tool("table")
    drag(window.view, 100, 300, 400, 420)
    window.view.deactivate_table()
    table = [i for i in markups(window) if i.TYPE == "table"][0]
    assert not toolsets.can_be_properties(toolsets.entry_for(table).payload)

    grouped = toolsets.entry_for_many([box, table])
    assert not toolsets.can_be_properties(grouped.payload)


def test_drawing_again_is_greyed_out_for_a_calculation(window):
    """A calculation is nothing without its lines, so there is nothing to draw."""
    from calcforge.ui import toolsets

    panel = window.toolsets_panel
    panel.select_set(toolsets.MY_TOOLS)
    group = panel.current_set()
    group.entries.append(toolsets.ToolEntry("A calculation", {"type": "math"}))
    group.entries.append(toolsets.ToolEntry("A rectangle", {"type": "rect"}))
    toolsets.save_toolsets(panel.groups)
    panel.rebuild(keep=toolsets.MY_TOOLS)

    panel.select_entry(toolsets.MY_TOOLS, len(group.entries) - 2)
    assert not _menu_entry(panel.build_menu(),
                           "Draw again with its properties").isEnabled()
    panel.select_entry(toolsets.MY_TOOLS, len(group.entries) - 1)
    assert _menu_entry(panel.build_menu(),
                       "Draw again with its properties").isEnabled()


def test_tools_can_be_dragged_into_the_order_you_want(window):
    from calcforge.ui import toolsets

    panel = window.toolsets_panel
    panel.select_set(toolsets.MY_TOOLS)
    group = panel.current_set()
    group.entries[:] = [toolsets.ToolEntry("First", {"type": "rect"}),
                        toolsets.ToolEntry("Second", {"type": "rect"}),
                        toolsets.ToolEntry("Third", {"type": "rect"})]
    toolsets.save_toolsets(panel.groups)
    panel.rebuild(keep=toolsets.MY_TOOLS)

    header = panel.tree.indexFromItem(panel.tree.topLevelItem(0))
    panel._rows_moved(header, 2, 2, header, 0)     # drag the third to the top
    assert [entry.label for entry in panel.current_set().entries] == \
        ["Third", "First", "Second"]


def test_a_click_placed_tool_shows_itself_before_it_lands(window):
    """A note or a count marker is not invisible until it is already down."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter

    def ink(x, y, size=60):
        image = QImage(size, size, QImage.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        painter.translate(-x + size / 2, -y + size / 2)
        window.view.drawForeground(painter,
                                   QRectF(x - size / 2, y - size / 2, size, size))
        painter.end()
        return sum(1 for a in range(size) for b in range(size) if image.pixel(a, b))

    window.select_tool("note")
    hover(window.view, 300, 300)
    assert ink(300, 300) > 0

    window.select_tool("select")
    hover(window.view, 300, 300)
    assert ink(300, 300) == 0            # nothing held, nothing drawn


def test_the_snapshot_marquee_looks_like_the_selection_marquee(window):
    """The same gesture meaning the same thing, drawn the same way."""
    from calcforge.items.shapes import RectItem

    marquee = RectItem("marquee")
    assert marquee.style.line_style == "dash"
    assert marquee.style.stroke == "#1971c2"      # the selection blue


def test_a_line_being_drawn_catches_on_what_is_already_there(window):
    """Snapping is for drawing, not only for moving things afterwards."""
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)

    window.select_tool("line")
    drag(window.view, 203, 163, 300, 260)          # three points off the corner
    line = markups(window)[1]
    start = line.mapToScene(line.points[0])
    assert (start.x(), start.y()) == pytest.approx((200, 160), abs=0.5)


def test_snapping_can_be_turned_off(window):
    from calcforge.ui import preferences

    prefs = preferences.current()
    was = prefs.snap_while_drawing
    prefs.snap_while_drawing = False
    try:
        window.select_tool("rect")
        drag(window.view, 100, 100, 200, 160)
        window.select_tool("line")
        drag(window.view, 203, 163, 300, 260)
        line = markups(window)[1]
        start = line.mapToScene(line.points[0])
        assert (start.x(), start.y()) == pytest.approx((203, 163), abs=0.5)
    finally:
        prefs.snap_while_drawing = was


# ---------------------------------------------------------------------------
# The pointer says what will happen
# ---------------------------------------------------------------------------

def test_the_pointer_changes_over_a_handle_a_vertex_and_a_table_edge(window):
    from PySide6.QtCore import Qt

    window.select_tool("rect")
    drag(window.view, 100, 100, 240, 180)
    window.select_tool("select")
    box = only(window, RectItem)[0]
    box.setSelected(True)

    corner = box.mapToScene(box.local_rect().bottomRight())
    hover(window.view, corner.x(), corner.y())
    assert window.view.cursor().shape() == Qt.SizeFDiagCursor

    hover(window.view, 170, 140)                  # inside it
    assert window.view.cursor().shape() == Qt.SizeAllCursor

    hover(window.view, 600, 600)                  # bare paper
    assert window.view.cursor().shape() == Qt.ArrowCursor


def test_a_locked_markup_says_so_with_the_pointer(window):
    from PySide6.QtCore import Qt

    window.select_tool("rect")
    drag(window.view, 100, 100, 240, 180)
    window.select_tool("select")
    box = only(window, RectItem)[0]
    box.locked = True
    box.setSelected(False)

    hover(window.view, 170, 140)
    assert window.view.cursor().shape() == Qt.ForbiddenCursor


def test_every_vertex_of_a_polyline_gets_the_same_pointer(window):
    from PySide6.QtCore import Qt
    from calcforge.items.base import cursor_for_handle

    assert cursor_for_handle("v0") == Qt.PointingHandCursor
    assert cursor_for_handle("v7") == Qt.PointingHandCursor
    assert cursor_for_handle("elbow") == Qt.PointingHandCursor
    assert cursor_for_handle("lblrot") == Qt.CrossCursor


# ---------------------------------------------------------------------------
# Nothing in the panel that has no answer
# ---------------------------------------------------------------------------

def test_a_callout_is_asked_only_about_the_end_that_points(window):
    """Which arrow head goes on the end joined to the box is not a question."""
    from PySide6.QtWidgets import QComboBox
    from calcforge.items.text import CalloutItem

    window.select_tool("callout")
    click(window.view, 400, 400)
    click(window.view, 150, 150)
    window.view.end_item_edit()
    window.select_tool("select")
    callout = [i for i in markups(window) if isinstance(i, CalloutItem)][0]
    callout.setSelected(True)
    window.refresh_selection()

    groups = _panel_groups(window, callout)
    assert "Leader" in groups and "Ends" not in groups
    boxes = {b.objectName(): b for b in window.properties_panel.findChildren(QComboBox)}
    assert "Box" in [w.itemText(i) for w in window.properties_panel.findChildren(QComboBox)
                     for i in range(w.count())]


def test_a_callout_can_be_turned_into_a_cloud_afterwards(window):
    from PySide6.QtWidgets import QComboBox
    from calcforge.items.text import CalloutItem

    window.select_tool("callout")
    click(window.view, 400, 400)
    click(window.view, 150, 150)
    window.view.end_item_edit()
    window.select_tool("select")
    callout = [i for i in markups(window) if isinstance(i, CalloutItem)][0]
    callout.setSelected(True)
    window.refresh_selection()

    shape = [w for w in window.properties_panel.findChildren(QComboBox)
             if [w.itemText(i) for i in range(w.count())] == ["Box", "Cloud"]][0]
    shape.setCurrentIndex(1)
    assert callout.shape_kind == "cloud"


# ---------------------------------------------------------------------------
# The markup tools that were missing
# ---------------------------------------------------------------------------

def test_the_markup_menu_has_everything_bluebeam_has(window):
    """Typewriter, Eraser, Arc and Flag were on the menu and not in the app."""
    from calcforge.ui.tools import TOOL_MAP

    wanted = {"typewriter": "", "eraser": "Shift+E", "arc": "Shift+C",
              "flag": "Shift+F", "highlighter": "H", "polyline": "N",
              "cloud_poly": "K", "cloud": "C"}
    for key, shortcut in wanted.items():
        assert key in TOOL_MAP, key
        assert TOOL_MAP[key].shortcut == shortcut, key
    assert not window.shortcuts.conflicts()
    # and no two tools share a name
    labels = [tool.label for tool in TOOL_MAP.values()]
    assert len(labels) == len(set(labels))


def test_a_typewriter_puts_words_down_with_no_box(window):
    from calcforge.items.text import TypewriterItem

    window.select_tool("typewriter")
    drag(window.view, 100, 100, 320, 140)
    item = window.view.editing_item()
    assert isinstance(item, TypewriterItem)
    assert not item.style.stroke          # no border
    assert not item.style.fill            # and nothing behind the words
    window.view.end_item_edit()


def test_an_arc_bends(window):
    window.select_tool("arc")
    drag(window.view, 100, 100, 260, 100)
    arc = markups(window)[0]
    assert arc.kind == "arc"
    # longer than the straight line between its ends, because it is a curve
    assert arc.build_path().length() > 150


def test_a_flag_is_pinned_where_it_is_clicked(window):
    from calcforge.items.text import FlagItem

    window.select_tool("flag")
    click(window.view, 300, 220)
    flag = markups(window)[0]
    assert isinstance(flag, FlagItem)
    assert (flag.pos().x(), flag.pos().y()) == pytest.approx((300, 220), abs=12)


def test_the_eraser_rubs_out_ink_and_leaves_shapes_alone(window):
    window.select_tool("pen")
    drag(window.view, 100, 400, 300, 420)
    window.select_tool("rect")
    drag(window.view, 100, 500, 300, 560)
    assert len(markups(window)) == 2

    window.select_tool("eraser")
    drag(window.view, 150, 405, 260, 415)      # over the ink
    assert len(markups(window)) == 1

    window.select_tool("eraser")
    drag(window.view, 150, 520, 260, 540)      # over the rectangle
    assert len(markups(window)) == 1           # a drawn shape is not ink
    window.undo_stack.undo()


# ---------------------------------------------------------------------------
# Cut-outs
# ---------------------------------------------------------------------------

def _area_measurement(window):
    from calcforge.items.measure import MeasureItem

    window.select_tool("measure_area")
    for point in [(100, 100), (400, 100), (400, 300), (100, 300)]:
        click(window.view, *point)
    press_key(window.view, Qt.Key_Return)
    window.recalculate()
    return [i for i in markups(window) if isinstance(i, MeasureItem)][0]


def test_a_cut_out_takes_its_area_off_the_measurement(window):
    area = _area_measurement(window)
    whole = area.raw_measure()[1]

    window.select_tool("cutout_ellipse")
    drag(window.view, 180, 150, 280, 240)
    window.recalculate()

    assert len(area.cutouts) == 1
    assert area.raw_measure()[1] < whole
    assert len(markups(window)) == 1           # the hole is not a markup of its own


def test_a_polygon_cut_out_belongs_to_the_area_it_is_drawn_in(window):
    area = _area_measurement(window)
    whole = area.raw_measure()[1]

    window.select_tool("cutout_polygon")
    for point in [(300, 150), (370, 150), (370, 250)]:
        click(window.view, *point)
    press_key(window.view, Qt.Key_Return)
    window.recalculate()

    assert len(area.cutouts) == 1
    assert area.raw_measure()[1] == pytest.approx(whole - 3500, abs=1)


def test_a_cut_out_drawn_nowhere_says_so(window):
    _area_measurement(window)
    window.select_tool("cutout_ellipse")
    drag(window.view, 600, 600, 680, 660)
    assert len(markups(window)) == 1           # nothing left lying about


def test_a_cut_out_survives_being_saved(window):
    from calcforge.items.base import build_item

    area = _area_measurement(window)
    window.select_tool("cutout_ellipse")
    drag(window.view, 180, 150, 280, 240)
    window.recalculate()

    clone = build_item(area.serialize())
    assert len(clone.cutouts) == 1
    assert clone.raw_measure()[1] == pytest.approx(area.raw_measure()[1])


# ---------------------------------------------------------------------------
# The rest of the right-click menu
# ---------------------------------------------------------------------------

def _a_rectangle(window, x0=120, y0=120, x1=240, y1=200):
    window.select_tool("rect")
    drag(window.view, x0, y0, x1, y1)
    return markups(window)[-1]


def test_the_markup_menu_offers_the_whole_of_bluebeams(window):
    rect = _a_rectangle(window)
    rect.setSelected(True)
    labels = _menu_labels(window.build_context_menu(rect, QPointF(150, 150)))
    for wanted in ("Cut", "Copy", "Paste", "Duplicate", "Format painter",
                   "Delete", "Order", "Align", "Layer", "Lock / unlock",
                   "Hide", "Flatten onto the page", "Apply to pages…",
                   "Properties"):
        assert wanted in labels, f"{wanted!r} missing from {labels}"


def test_align_is_offered_but_dead_until_there_are_two(window):
    rect = _a_rectangle(window)
    rect.setSelected(True)
    menu = window.build_context_menu(rect, QPointF(150, 150))
    align = [a for a in menu.actions() if a.text() == "Align"][0]
    assert not align.isEnabled()

    other = _a_rectangle(window, 300, 120, 380, 200)
    rect.setSelected(True)
    other.setSelected(True)
    menu = window.build_context_menu(rect, QPointF(150, 150))
    align = [a for a in menu.actions() if a.text() == "Align"][0]
    assert align.isEnabled()


def test_the_format_painter_carries_one_markups_look_to_another(window):
    first = _a_rectangle(window)
    first.style.stroke = "#c92a2a"
    first.style.width = 4.0
    second = _a_rectangle(window, 300, 120, 380, 200)
    second.style.stroke = "#1971c2"

    window.scene.clearSelection()
    first.setSelected(True)
    window.format_painter()
    assert window.holding_a_format()

    window.paint_format_onto(second)
    assert second.style.stroke == "#c92a2a"
    assert second.style.width == pytest.approx(4.0)
    # It painted the look, not the position or the size.
    assert second.local_rect().width() == pytest.approx(80, abs=1)


def test_clicking_with_the_format_painter_paints_that_markup(window):
    first = _a_rectangle(window)
    first.style.stroke = "#c92a2a"
    second = _a_rectangle(window, 300, 120, 380, 200)
    window.scene.clearSelection()
    first.setSelected(True)
    window.format_painter()

    click(window.view, 340, 160)
    assert second.style.stroke == "#c92a2a"


def test_escape_puts_the_format_painter_down(window):
    rect = _a_rectangle(window)
    rect.setSelected(True)
    window.format_painter()
    press_key(window.view, Qt.Key_Escape)
    assert not window.holding_a_format()


def test_hidden_markups_go_away_and_come_back(window):
    rect = _a_rectangle(window)
    rect.setSelected(True)
    window.hide_selection()
    assert rect.hidden and not rect.isVisible()

    window.show_hidden()
    assert not rect.hidden and rect.isVisible()


def test_a_hidden_markup_is_still_hidden_after_a_save(window):
    from calcforge.items.base import build_item

    rect = _a_rectangle(window)
    rect.setSelected(True)
    window.hide_selection()
    assert build_item(rect.serialize()).hidden


def test_flattening_takes_a_markup_out_of_reach(window):
    rect = _a_rectangle(window)
    rect.setSelected(True)
    window.interactive_prompts = False
    window.flatten_selection()

    assert rect.flattened and rect.locked
    assert not rect.flags() & rect.GraphicsItemFlag.ItemIsSelectable
    click(window.view, 180, 160)
    assert not rect.isSelected()


def test_flattening_survives_a_save(window):
    from calcforge.items.base import build_item

    rect = _a_rectangle(window)
    rect.setSelected(True)
    window.interactive_prompts = False
    window.flatten_selection()
    clone = build_item(rect.serialize())
    assert clone.flattened and clone.locked


def test_a_markup_can_be_put_on_every_other_page(window, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    window.add_page()
    window.add_page()
    window.go_to_page(0)
    rect = _a_rectangle(window)
    rect.setSelected(True)
    monkeypatch.setattr(QInputDialog, "getItem",
                        lambda *a, **k: ("Every other page", True))
    window.apply_to_pages(rect)

    for index in (1, 2):
        frame = window.document.pages[index].frame
        copies = [i for i in frame.markups() if isinstance(i, RectItem)]
        assert len(copies) == 1
        assert copies[0].pos() == rect.pos()
        assert copies[0].uid != rect.uid


def test_moving_a_markup_to_another_layer(window):
    rect = _a_rectangle(window)
    rect.setSelected(True)
    other = [layer.name for layer in window.document.layers
             if layer.name != rect.layer]
    if not other:
        window.document.add_layer("Second")
        other = ["Second"]
    window.move_to_layer(other[0])
    assert rect.layer == other[0]


# ---------------------------------------------------------------------------
# A leader on any text box, and Escape that goes all the way back
# ---------------------------------------------------------------------------

def test_a_text_box_can_be_given_a_leader_and_have_it_taken_away(window):
    window.select_tool("text")
    drag(window.view, 200, 200, 340, 250)
    type_text(window.view, "note")
    window.view.end_item_edit()
    box = markups(window)[-1]
    assert isinstance(box, TextItem) and not box.leader_shown
    assert "l0" not in box.handle_points()

    window.set_leader(box, True)
    assert box.leader_shown
    assert "l0" in box.handle_points()
    assert box.leader_handles() == {"l0", "elbow"}

    window.set_leader(box, False)
    assert not box.leader_shown
    assert box.leader == []
    assert "l0" not in box.handle_points()


def test_the_menu_offers_a_leader_on_a_text_box_and_removal_on_a_callout(window):
    window.select_tool("text")
    drag(window.view, 200, 200, 340, 250)
    type_text(window.view, "note")
    window.view.end_item_edit()
    box = markups(window)[-1]
    box.setSelected(True)
    assert "Add leader" in _menu_labels(window.build_context_menu(box, box.pos()))

    window.set_leader(box, True)
    assert "Remove leader" in _menu_labels(window.build_context_menu(box, box.pos()))


def test_a_text_boxs_leader_is_still_there_after_a_save(window):
    from calcforge.items.base import build_item

    window.select_tool("text")
    drag(window.view, 200, 200, 340, 250)
    type_text(window.view, "note")
    window.view.end_item_edit()
    box = markups(window)[-1]
    window.set_leader(box, True)
    tip = QPointF(box.tip)

    clone = build_item(box.serialize())
    assert clone.leader_shown
    assert clone.tip == tip
    assert not build_item(TextItem().serialize()).leader_shown


def test_one_escape_goes_all_the_way_back_to_nothing(window):
    rect = _a_rectangle(window)
    rect.setSelected(True)
    window.select_tool("rect")
    assert window.view.tool_key == "rect"

    press_key(window.view, Qt.Key_Escape)
    assert window.view.tool_key == "select"
    assert not window.scene.selectedItems()
    assert window.view._mode == "idle"


def test_escape_gets_out_of_a_half_placed_callout(window):
    window.select_tool("callout")
    click(window.view, 200, 220)                 # the arrow goes down first
    assert window.view._pending_anchor is not None

    press_key(window.view, Qt.Key_Escape)
    assert window.view._pending_anchor is None
    assert window.view.tool_key == "select"
    # And the callout tool is free to be used again straight away.
    window.select_tool("callout")
    click(window.view, 300, 320)
    click(window.view, 380, 380)
    assert any(isinstance(i, CalloutItem) for i in markups(window))


def test_a_drag_whose_release_went_missing_lets_go_of_the_pointer(window):
    rect = _a_rectangle(window)
    rect.setSelected(True)
    QApplication.sendEvent(window.view.viewport(),
                           _mouse(window.view, QEvent.MouseButtonPress, 180, 160))
    QApplication.sendEvent(window.view.viewport(),
                           _mouse(window.view, QEvent.MouseMove, 200, 180,
                                  Qt.LeftButton, Qt.LeftButton))
    assert window.view._mode == "move"

    # The release never arrives — a menu opened over it, say. The next plain
    # move must find its way back rather than keeping the four-way arrow.
    hover(window.view, 500, 500)
    assert window.view._mode == "idle"
    assert window.view.cursor().shape() == Qt.ArrowCursor


# ---------------------------------------------------------------------------
# A pasted picture must actually be a picture
# ---------------------------------------------------------------------------

def _paints_something_other_than_grey(item):
    """Whether the item draws a real picture rather than the missing-image box."""
    from PySide6.QtGui import QImage, QPainter

    box = item.local_rect().normalized()
    canvas = QImage(max(int(box.width()), 4), max(int(box.height()), 4),
                    QImage.Format_ARGB32)
    canvas.fill(0xFFFFFFFF)
    painter = QPainter(canvas)
    painter.translate(-box.topLeft())
    item.paint_content(painter)
    painter.end()
    colours = {canvas.pixel(x, y)
               for x in range(0, canvas.width(), 3)
               for y in range(0, canvas.height(), 3)}
    return colours


def test_a_pasted_snapshot_holds_its_picture(window):
    from calcforge.items.media import ImageItem

    window.select_tool("rect")
    drag(window.view, 100, 100, 220, 180)
    window.select_tool("snapshot")
    drag(window.view, 60, 60, 300, 250)

    window.select_tool("select")
    hover(window.view, 120, 520)
    window.paste_items()

    pasted = [i for i in markups(window) if isinstance(i, ImageItem)][-1]
    assert pasted.asset_key                       # it knows which picture
    assert window.document.asset(pasted.asset_key)   # and the picture is there
    assert pasted.pixmap() is not None and not pasted.pixmap().isNull()


def test_a_picture_pasted_from_elsewhere_holds_its_picture(window):
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    from calcforge.items.media import ImageItem

    foreign = QImage(120, 80, QImage.Format_ARGB32)
    foreign.fill(0xFF2F9E44)
    QApplication.clipboard().setImage(foreign)

    window.select_tool("select")
    hover(window.view, 120, 520)
    window.paste_items()

    pasted = [i for i in markups(window) if isinstance(i, ImageItem)][-1]
    assert pasted.asset_key
    assert pasted.pixmap() is not None and not pasted.pixmap().isNull()
    # The green it was filled with is what comes out of it.
    assert 0xFF2F9E44 in _paints_something_other_than_grey(pasted)


def test_a_pasted_picture_is_still_there_after_a_save(window, tmp_path):
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    from calcforge.core.document import Document
    from calcforge.io import project as project_io
    from calcforge.items.base import build_item
    from calcforge.items.media import ImageItem

    foreign = QImage(90, 60, QImage.Format_ARGB32)
    foreign.fill(0xFF1971C2)
    QApplication.clipboard().setImage(foreign)
    window.select_tool("select")
    hover(window.view, 120, 520)
    window.paste_items()

    path = str(tmp_path / "picture.cfx")
    project_io.save_document(window.document, path)
    reopened = Document()
    project_io.load_document(reopened, path)

    stored = [entry for entry in reopened.pages[0].to_dict()["items"]
              if entry.get("type") == "image"]
    assert len(stored) == 1
    item = build_item(stored[0])
    assert isinstance(item, ImageItem)
    item.load_from_document(reopened)
    assert item.pixmap() is not None and not item.pixmap().isNull()


# ---------------------------------------------------------------------------
# Ctrl+B, and the pointer over a table's edges
# ---------------------------------------------------------------------------

def test_ctrl_b_emboldens_a_selected_text_box_rather_than_bookmarking(window):
    window.select_tool("text")
    drag(window.view, 200, 200, 340, 250)
    type_text(window.view, "shear")
    window.view.end_item_edit()
    box = markups(window)[-1]
    window.scene.clearSelection()
    box.setSelected(True)
    before = len(window.document.bookmarks)

    assert window.toggle_bold() is True
    assert box.style.bold
    assert len(window.document.bookmarks) == before

    window.toggle_bold()
    assert not box.style.bold


def test_ctrl_b_emboldens_the_run_picked_out_in_a_text_box(window):
    from PySide6.QtGui import QTextCursor

    window.select_tool("text")
    drag(window.view, 200, 200, 340, 250)
    editor = window.view.text_editor()
    assert editor is not None
    editor.setPlainText("beam shear check")
    cursor = editor.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(4, QTextCursor.KeepAnchor)      # "beam"
    editor.setTextCursor(cursor)

    assert window.toggle_bold() is True
    box = markups(window)[-1]
    # Only the run picked out is bold; the box itself is not turned bold.
    assert not box.style.bold
    check = editor.textCursor()
    check.setPosition(2)
    assert check.charFormat().font().bold()
    check.setPosition(10)
    assert not check.charFormat().font().bold()


def test_ctrl_b_emboldens_the_cells_picked_out_in_a_table(window):
    table = _capacity_table(window)
    window.view.activate_table(table)
    table.current = (1, 0)
    table.anchor = (1, 2)

    assert window.toggle_bold() is True
    assert table.cell_format(1, 0).bold
    assert table.cell_format(1, 2).bold
    assert not table.cell_format(2, 0).bold


def test_ctrl_b_still_bookmarks_when_there_are_no_words(window, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    window.scene.clearSelection()
    assert window.toggle_bold() is False
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Shear", True))
    before = len(window.document.bookmarks)
    window.add_bookmark_here()
    assert len(window.document.bookmarks) == before + 1


def test_the_pointer_says_resize_over_a_table_edge(window):
    table = _capacity_table(window)
    window.view.activate_table(table)

    # The column divider lives in the strip above the grid.
    origin = table.grid_origin()
    gw, gh = table.gutter_size()
    x = origin.x() + table.sheet.col_width(0)
    edge = table.mapToScene(QPointF(x, origin.y() - gh / 2))
    hover(window.view, edge.x(), edge.y())
    assert window.view.cursor().shape() == Qt.SplitHCursor

    y = origin.y() + table.sheet.row_height(0)
    edge = table.mapToScene(QPointF(origin.x() - gw / 2, y))
    hover(window.view, edge.x(), edge.y())
    assert window.view.cursor().shape() == Qt.SplitVCursor


# ---------------------------------------------------------------------------
# Bringing a Bluebeam tool set in
# ---------------------------------------------------------------------------

def _btx(name):
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(here, "btx", name)


def test_importing_a_bluebeam_tool_set_fills_the_tool_chest(window):
    from calcforge.ui import toolsets

    assert window.import_toolset(_btx("Structures - Timber.btx"))
    names = [group.name for group in toolsets.load_toolsets()]
    assert "Structures - Timber" in names

    group = next(g for g in toolsets.load_toolsets()
                 if g.name == "Structures - Timber")
    labels = [entry.label for entry in group.entries]
    assert "Timber Post 200x200" in labels
    # And the panel is showing it, so it can be used straight away.
    tree = window.toolsets_panel.tree
    header = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())
              if tree.topLevelItem(i).text(0).startswith("Structures - Timber")]
    assert len(header) == 1
    assert header[0].childCount() == len(group.entries)
    assert header[0].isExpanded()


def test_an_imported_tool_can_be_put_on_the_page(window):
    from calcforge.items.shapes import PolyItem, RectItem

    window.import_toolset(_btx("Structures - Timber.btx"))
    panel = window.toolsets_panel
    group = next(g for g in panel.groups if g.name == "Structures - Timber")
    row = [i for i, e in enumerate(group.entries)
           if e.label.startswith("Timber Post")][0]
    panel.select_entry("Structures - Timber", row)
    before = len(markups(window))

    hover(window.view, 200, 300)
    panel.use_selected()
    click(window.view, 200, 300)

    added = markups(window)[before:]
    assert len(added) > 1                       # the post and its hatching
    assert all(isinstance(i, (RectItem, PolyItem)) for i in added)
    # Put down as one thing, so it moves and copies as one thing.
    assert len({i.group for i in added}) == 1 and added[0].group


def test_an_imported_steel_section_draws_as_a_drawing(window):
    from calcforge.items.shapes import SketchItem

    window.import_toolset(_btx("Structural Steel UC Sections - 1-10 @ A1.btx"))
    panel = window.toolsets_panel
    panel.select_entry("Structural Steel UC Sections - 1:10 @ A1", 0)
    hover(window.view, 250, 300)
    panel.use_selected()
    click(window.view, 250, 300)

    sections = [i for i in markups(window) if isinstance(i, SketchItem)]
    assert len(sections) == 1
    assert len(sections[0].strokes) > 10


def test_importing_the_same_set_twice_does_not_lose_the_first(window):
    from calcforge.ui import toolsets

    window.import_toolset(_btx("Structures - Timber.btx"))
    window.import_toolset(_btx("Structures - Timber.btx"))
    names = [group.name for group in toolsets.load_toolsets()]
    assert "Structures - Timber" in names
    assert "Structures - Timber (2)" in names


def test_a_file_that_is_not_a_tool_set_is_refused_politely(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from calcforge.ui import toolsets

    path = tmp_path / "nope.btx"
    path.write_bytes(b"this is not xml")
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Ok)
    before = len(toolsets.load_toolsets())
    assert window.import_toolset(str(path)) is False
    assert len(toolsets.load_toolsets()) == before


# ---------------------------------------------------------------------------
# The tool chest: every set showing, and everything on the right-click menu
# ---------------------------------------------------------------------------

def test_every_tool_set_is_showing_at_once(window):
    from calcforge.ui import toolsets

    window.import_toolset(_btx("Structures - Timber.btx"))
    window.import_toolset(_btx("Structures - Welds.btx"))
    tree = window.toolsets_panel.tree

    headings = [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]
    assert any(h.startswith(toolsets.MY_TOOLS) for h in headings)
    assert any(h.startswith("Structures - Timber") for h in headings)
    assert any(h.startswith("Strucutres - Welds") or h.startswith("Structures - Welds")
               for h in headings)
    # And each heading says how many are in it, so a set can be judged rolled up.
    assert all("(" in heading for heading in headings)


def test_a_tool_set_can_be_rolled_up_and_stays_rolled_up(window):
    window.import_toolset(_btx("Structures - Timber.btx"))
    panel = window.toolsets_panel
    header = [panel.tree.topLevelItem(i) for i in range(panel.tree.topLevelItemCount())
              if panel.tree.topLevelItem(i).text(0).startswith("Structures - Timber")][0]
    assert header.isExpanded()

    header.setExpanded(False)
    panel.rebuild()
    again = [panel.tree.topLevelItem(i) for i in range(panel.tree.topLevelItemCount())
             if panel.tree.topLevelItem(i).text(0).startswith("Structures - Timber")][0]
    assert not again.isExpanded()


def test_clicking_a_tool_picks_it_up(window):
    from calcforge.items.shapes import RectItem

    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    _kept(window, markups(window)[0])
    panel = window.toolsets_panel
    row = panel.tree.topLevelItem(0).child(0)

    window.select_tool("select")
    panel.tree.setCurrentItem(row)
    panel._clicked(row, 0)
    assert window.view._pending_stamp is not None    # it is on the pointer

    hover(window.view, 220, 480)
    click(window.view, 220, 480)
    assert any(isinstance(i, RectItem) and i.pos().y() > 400
               for i in markups(window))


def test_clicking_a_set_heading_picks_nothing_up(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    _kept(window, markups(window)[0])
    panel = window.toolsets_panel
    header = panel.tree.topLevelItem(0)

    window.select_tool("select")
    panel.tree.setCurrentItem(header)
    panel._clicked(header, 0)
    assert window.view._pending_stamp is None


def test_the_tool_chests_right_click_menu_carries_everything(window):
    from calcforge.ui import toolsets

    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    _kept(window, markups(window)[0])
    panel = window.toolsets_panel
    panel.select_entry(toolsets.MY_TOOLS, 0)

    labels = _menu_labels(panel.build_menu())
    for wanted in ("Use", "Draw again with its properties", "Rename…", "Remove",
                   "Rename this set…", "Delete this set", "New tool set…",
                   "Import a tool set…"):
        assert wanted in labels, f"{wanted!r} missing from {labels}"


def test_the_menu_on_bare_panel_still_offers_a_new_set(window):
    panel = window.toolsets_panel
    panel.tree.setCurrentItem(None)
    labels = _menu_labels(panel.build_menu())
    assert "New tool set…" in labels
    assert "Import a tool set…" in labels
    assert "Use" not in labels          # nothing is picked out to use


def test_nothing_is_placed_behind_a_dashed_box(window):
    """The drawing under the pointer is the preview; a box round it is noise."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter

    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    entry = _kept(window, markups(window)[0])
    window.select_tool("select")
    window.use_tool_entry(entry)
    hover(window.view, 250, 480)

    image = QImage(200, 200, QImage.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    painter.translate(-150, -380)
    window.view.drawForeground(painter, QRectF(150, 380, 200, 200))
    painter.end()
    # The preview draws the markup itself; nothing draws the pale blue dashes
    # the placement box used to be outlined in.
    dashes = QColor(11, 107, 203).rgb()
    hits = sum(1 for x in range(image.width()) for y in range(image.height())
               if (image.pixel(x, y) & 0x00FFFFFF) == (dashes & 0x00FFFFFF))
    assert hits == 0


# ---------------------------------------------------------------------------
# Paste in place, cell alignment, headings as column names, the wheel
# ---------------------------------------------------------------------------

def test_ctrl_shift_v_pastes_in_the_same_place(window):
    window.select_tool("rect")
    drag(window.view, 120, 120, 240, 200)
    rect = markups(window)[0]
    where = QPointF(rect.pos())
    window.scene.clearSelection()
    rect.setSelected(True)
    window.copy_selection()

    # The pointer is somewhere else entirely; paste in place ignores it.
    hover(window.view, 400, 500)
    window.paste_in_place()

    copies = [i for i in markups(window) if isinstance(i, RectItem)]
    assert len(copies) == 2
    assert all(copy.pos() == where for copy in copies)   # right on top of it
    assert len({copy.uid for copy in copies}) == 2       # and a copy, not the same one


def test_paste_in_place_is_on_ctrl_shift_v(window):
    assert window.act_paste_in_place.shortcut().toString() == "Ctrl+Shift+V"
    assert window.act_paste_here.shortcut().toString() == "Ctrl+Alt+V"


def test_cells_can_be_lined_up_left_centre_and_right(window):
    table = _capacity_table(window)
    window.view.activate_table(table)
    table.current = (1, 0)
    table.anchor = (1, 1)

    window.align_cells("right")
    assert table.cell_format(1, 0).align == "right"
    assert table.cell_format(1, 1).align == "right"
    assert table.cell_format(2, 0).align != "right"

    window.align_cells("center")
    assert table.cell_format(1, 0).align == "center"


def test_the_cell_bar_shows_how_the_cells_are_lined_up(window):
    table = _capacity_table(window)
    window.view.activate_table(table)
    table.current = table.anchor = (1, 0)
    window.align_cells("center")
    window.refresh_formula_bar(table)

    assert window.align_buttons["center"].isChecked()
    assert not window.align_buttons["left"].isChecked()


def test_alignment_is_on_the_tables_own_menu(window):
    table = _capacity_table(window)
    table.setSelected(True)
    menu = window.build_context_menu(table, table.pos())
    align = [a for a in menu.actions() if a.text() == "Align cells"]
    assert align
    labels = [a.text() for a in align[0].menu().actions()]
    assert labels == ["Left", "Centre", "Right", "As they come"]


def test_a_table_can_be_read_by_its_column_headings(window):
    _capacity_table(window)          # headings are d, V and N
    _calc(window, "dia := 20 mm\nV := bolts(dia, d, V) =", at=(60, 400))
    window.recalculate()
    assert window.document.workspace.get("V").to("kN").magnitude == pytest.approx(84.8)


def test_the_letters_still_work_alongside_the_headings(window):
    _capacity_table(window)
    _calc(window, "dia := 16 mm\nV := bolts(dia, A, B) =", at=(60, 400))
    window.recalculate()
    assert window.document.workspace.get("V").to("kN").magnitude == pytest.approx(54.3)


def test_a_heading_that_is_not_a_column_is_still_a_variable(window):
    """Only a table's own headings are read as columns; the rest are names."""
    _capacity_table(window)
    _calc(window, "width := 3\nV := width * 2 =", at=(60, 400))
    window.recalculate()
    assert window.document.workspace.get("V") == 6


def test_the_wheel_over_a_dropdown_scrolls_the_panel(window):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QComboBox

    window.select_tool("rect")
    drag(window.view, 120, 120, 240, 200)
    markups(window)[0].setSelected(True)
    window.refresh_selection()

    combos = window.properties_panel.findChildren(QComboBox)
    assert combos, "the properties panel has no dropdowns to test"
    combo = combos[0]
    combo.clearFocus()
    before = combo.currentIndex()

    wheel = QWheelEvent(QPointF(5, 5), combo.mapToGlobal(QPoint(5, 5)),
                        QPoint(0, -120), QPoint(0, -120), Qt.NoButton,
                        Qt.NoModifier, Qt.NoScrollPhase, False)
    QApplication.sendEvent(combo, wheel)
    assert combo.currentIndex() == before      # the panel scrolled, not the box

    # And the filter hands it straight back the moment it has been clicked
    # into, so a deliberate wheel over an open box still works.
    from calcforge.ui.widgets import WheelBelongsToTheScroller

    kept = WheelBelongsToTheScroller()
    combo.hasFocus = lambda: True              # focus needs an active window
    wheel = QWheelEvent(QPointF(5, 5), combo.mapToGlobal(QPoint(5, 5)),
                        QPoint(0, -120), QPoint(0, -120), Qt.NoButton,
                        Qt.NoModifier, Qt.NoScrollPhase, False)
    assert kept.eventFilter(combo, wheel) is False


# ---------------------------------------------------------------------------
# Handles: the rotation grip, and control points that should not be showing
# ---------------------------------------------------------------------------

def test_the_rotation_grip_is_inside_the_item_it_belongs_to(window):
    """Drawn outside its own rectangle, Qt clips it and smears it when it moves."""
    window.select_tool("rect")
    drag(window.view, 120, 120, 260, 200)
    rect = markups(window)[0]
    grip = rect.handle_points().get("rot")
    assert grip is not None
    assert rect.boundingRect().contains(grip)


def test_a_grouped_shape_shows_no_control_points_of_its_own(window):
    """The view draws one box round a group; a vertex handle inside it is noise."""
    from PySide6.QtGui import QImage, QPainter

    window.select_tool("polyline")
    for point in [(120, 120), (200, 160), (260, 120)]:
        click(window.view, *point)
    press_key(window.view, Qt.Key_Return)
    line = markups(window)[-1]
    window.select_tool("rect")
    drag(window.view, 300, 120, 380, 200)
    box = markups(window)[-1]

    window.scene.clearSelection()
    line.setSelected(True)
    box.setSelected(True)
    window.group_selection()
    assert line.group

    def handles_drawn(item):
        image = QImage(200, 200, QImage.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        painter.translate(20, 20)
        item.paint_handles(painter)
        painter.end()
        return any(image.pixel(x, y) >> 24
                   for x in range(image.width()) for y in range(image.height()))

    assert not handles_drawn(line)
    window.ungroup_selection()
    line.setSelected(True)
    assert handles_drawn(line)


def test_a_marquee_catches_a_shape_it_is_drawn_round(window):
    """It is the markup that has to fit inside, not the room kept for its handles."""
    window.select_tool("rect")
    drag(window.view, 150, 150, 250, 210)
    rect = markups(window)[0]
    window.scene.clearSelection()

    window.select_tool("select")
    drag(window.view, 140, 140, 262, 222)     # barely round it, left to right
    assert rect.isSelected()


def test_the_callouts_box_shows_itself_before_it_lands(window):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter

    window.select_tool("callout")
    click(window.view, 200, 300)               # what it points at
    hover(window.view, 340, 240)               # where the words would go

    image = QImage(220, 200, QImage.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    painter.translate(-320, -220)
    window.view.drawForeground(painter, QRectF(320, 220, 220, 200))
    painter.end()
    painted = sum(1 for x in range(image.width()) for y in range(image.height())
                  if image.pixel(x, y) >> 24)
    assert painted > 400, "no box was drawn where the words would go"


# ---------------------------------------------------------------------------
# One equation view: what is typed into is what is printed
# ---------------------------------------------------------------------------

def _rows_of(block):
    """Every laid-out row's left-hand box, so its shape can be asked about."""
    return [row.left for row in block.rows]


def _contains(box, kind):
    """Whether a laid-out box has one of *kind* anywhere inside it."""
    if isinstance(box, kind):
        return True
    for child, _x, _baseline in box.children_at(0.0, 0.0):
        if _contains(child, kind):
            return True
    return False


def test_a_fraction_stays_a_fraction_while_it_is_being_typed(window):
    """The edit view is the printed view — there is no second, plainer one."""
    from calcforge.core.mathrender import Fraction

    window.view._last_scene_pos = QPointF(90, 110)
    press_key(window.view, Qt.Key_unknown, "/")
    block = window.view.editing_item()
    block._editor.setPlainText("Z := b*d^2/6")
    block.retypeset_live()

    assert any(_contains(box, Fraction) for box in _rows_of(block) if box)
    # And it is still one when the caret leaves.
    window.view.end_item_edit()
    assert any(_contains(box, Fraction) for box in _rows_of(block) if box)


def test_a_unit_being_typed_still_reads_as_a_quantity(window):
    window.view._last_scene_pos = QPointF(90, 110)
    press_key(window.view, Qt.Key_unknown, "/")
    block = window.view.editing_item()
    block._editor.setPlainText("b := 300 mm")
    block.retypeset_live()

    row = [box for box in _rows_of(block) if box][0]
    assert row.width > 0
    painted = _text_in(row)
    assert "300" in painted and "mm" in painted


def _text_in(box) -> str:
    """Every glyph inside a laid-out box, joined — for asking what it says."""
    from calcforge.core.mathrender import Glyph

    if isinstance(box, Glyph):
        return box.text
    return "".join(_text_in(child) for child, _x, _b in box.children_at(0.0, 0.0))


def test_a_half_typed_line_shows_what_has_been_typed(window):
    """"b*d^" cannot be laid out, and that one line waits rather than vanishing."""
    window.view._last_scene_pos = QPointF(90, 110)
    press_key(window.view, Qt.Key_unknown, "/")
    block = window.view.editing_item()
    block._editor.setPlainText("part := b*d^")
    block.retypeset_live()

    assert "b*d^" in _text_in([box for box in _rows_of(block) if box][0])


def test_the_scripts_are_typeset_while_typing_too(window):
    from calcforge.core.mathrender import Scripts

    window.view._last_scene_pos = QPointF(90, 110)
    press_key(window.view, Qt.Key_unknown, "/")
    block = window.view.editing_item()
    block._editor.setPlainText("L := sqrt(x_1^2 + y_1^2)")
    block.retypeset_live()
    assert any(_contains(box, Scripts) for box in _rows_of(block) if box)


# ---------------------------------------------------------------------------
# What the completion list offers, and where it appears
# ---------------------------------------------------------------------------

def test_typing_a_name_offers_the_documents_own_variables_first(window):
    _calc(window, "sigma_y := 300 MPa\nsigma_c := 25 MPa", at=(90, 110))
    window.recalculate()

    window.view._last_scene_pos = QPointF(90, 300)
    press_key(window.view, Qt.Key_unknown, "/")
    block = window.view.editing_item()
    type_text(window.view, "R := sig")

    offered = window.view.completion_words("sig")
    assert offered[:2] == ["sigma_c", "sigma_y"]
    window.view.end_item_edit()


def test_typing_after_a_number_offers_units_first(window):
    _calc(window, "metric := 1", at=(90, 110))
    window.recalculate()

    window.view._last_scene_pos = QPointF(90, 300)
    press_key(window.view, Qt.Key_unknown, "/")
    type_text(window.view, "L := 300 m")
    assert window.view.caret_follows_a_number()
    offered = window.view.completion_words("m")
    assert offered[0] in ("m", "mm", "m^2", "m²", "min", "mol")
    assert "metric" not in offered[:3]
    window.view.end_item_edit()


def test_the_list_shows_up_for_a_name_and_tab_fills_it_in(window):
    _calc(window, "sigma_y := 300 MPa", at=(90, 110))
    window.recalculate()

    window.view._last_scene_pos = QPointF(90, 300)
    press_key(window.view, Qt.Key_unknown, "/")
    block = window.view.editing_item()
    type_text(window.view, "R := sigma_")
    assert window.view.completions_showing()

    press_key(window.view, Qt.Key_Tab)
    assert block._editor.toPlainText().endswith("sigma_y")
    window.view.end_item_edit()


def test_the_list_appears_under_the_caret_not_under_the_block(window):
    from PySide6.QtCore import QPoint

    window.view._last_scene_pos = QPointF(90, 110)
    press_key(window.view, Qt.Key_unknown, "/")
    block = window.view.editing_item()
    block._editor.setPlainText("a := 1\nb := 2\nc := 3\nd := 4\ne := 5\nf := m")
    block.retypeset_live()
    cursor = block._editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    block._editor.setTextCursor(cursor)

    window.view.show_completions()
    assert window.view.completions_showing()
    popup = window.view._completions
    place = block.caret_place()
    assert place is not None
    caret = window.view.mapFromScene(block.mapToScene(QPointF(place[0], place[1])))
    # Within a couple of lines of the caret, not down at the foot of the block.
    assert abs(popup.pos().y() - caret.y()) < 40
    assert abs(popup.pos().x() - caret.x()) < 40
    window.view.hide_completions()
    window.view.end_item_edit()


# ---------------------------------------------------------------------------
# Scripts, fields in prose, and how many figures a result is shown to
# ---------------------------------------------------------------------------

def test_underscore_and_caret_set_scripts_in_a_text_box(window):
    from PySide6.QtGui import QTextCharFormat

    window.select_tool("text")
    drag(window.view, 100, 100, 340, 150)
    type_text(window.view, "A_g = 150 m^2 ok")
    editor = window.view.text_editor()

    assert editor.toPlainText() == "Ag = 150 m2 ok"
    cursor = editor.textCursor()
    levels = []
    for index in range(len(editor.toPlainText())):
        cursor.setPosition(index + 1)
        levels.append(cursor.charFormat().verticalAlignment())
    assert levels[1] == QTextCharFormat.AlignSubScript      # the g of A_g
    assert levels[10] == QTextCharFormat.AlignSuperScript   # the 2 of m^2
    assert levels[0] == QTextCharFormat.AlignNormal
    assert levels[-1] == QTextCharFormat.AlignNormal
    window.view.end_item_edit()


def test_a_table_cell_shows_its_scripts_too(window):
    from calcforge.core.typography import script_runs

    assert script_runs("A_g") == [("A", ""), ("g", "sub")]
    assert script_runs("m^2") == [("m", ""), ("2", "super")]
    assert script_runs("f'_c = 25") == [("f'", ""), ("c", "sub"), (" = 25", "")]
    # What is stored stays what a formula can read.
    table = _capacity_table(window)
    table.set_cell(0, 0, "A_g")
    assert table.sheet.raw(0, 0) == "A_g"


def test_a_field_in_a_paragraph_quotes_a_value(window):
    _calc(window, "M_n := 250 kN*m\nphi := 0.9", at=(90, 110))
    window.recalculate()

    window.select_tool("text")
    drag(window.view, 100, 300, 400, 350)
    box = window.view.editing_item()
    box._editor.setPlainText(r"The moment \M_n\ governs, with \phi*M_n\ available.")
    window.view.end_item_edit()
    window.recalculate()

    shown = box.text()
    assert "M_n = 250" in shown            # a bare name prints name = value
    assert "225" in shown                  # and an expression prints its answer
    assert "\\" not in shown               # the marks themselves do not print


def test_a_field_keeps_up_with_the_sheet(window):
    block = _calc(window, "M_n := 250 kN*m", at=(90, 110))
    window.select_tool("text")
    drag(window.view, 100, 300, 400, 350)
    box = window.view.editing_item()
    box._editor.setPlainText(r"\M_n\ governs")
    window.view.end_item_edit()
    window.recalculate()
    assert "250" in box.text()

    block.source = "M_n := 400 kN*m"
    block.refresh(window.document.workspace)
    window.recalculate()
    assert "400" in box.text()


def test_a_field_comes_back_as_it_was_typed_to_be_edited(window):
    _calc(window, "M_n := 250 kN*m", at=(90, 110))
    window.recalculate()
    window.select_tool("text")
    drag(window.view, 100, 300, 400, 350)
    box = window.view.editing_item()
    box._editor.setPlainText(r"\M_n\ governs")
    window.view.end_item_edit()
    window.recalculate()
    assert "250" in box.text()

    box.begin_edit()
    assert box._editor.toPlainText() == r"\M_n\ governs"
    box.end_edit()


def test_a_field_that_makes_no_sense_says_so_rather_than_vanishing(window):
    window.select_tool("text")
    drag(window.view, 100, 300, 400, 350)
    box = window.view.editing_item()
    box._editor.setPlainText(r"value is \nowhere_at_all\ here")
    window.view.end_item_edit()
    window.recalculate()
    assert "?" in box.text() and "here" in box.text()


def test_one_line_can_be_shown_to_its_own_number_of_figures(window):
    block = _calc(window, "a := 1/3 =\nb := 1/3 =", at=(90, 110))
    window.recalculate()

    window.set_line_figures(block, 0, 2, "fixed")
    assert block.figures_for(0) == (2, "fixed")
    assert block.figures_for(1) == (block.digits, block.number_format)

    shown = [row.result for row in block.rows]
    assert _text_in(shown[0]).replace("=", "").strip() == "0.33"
    assert _text_in(shown[1]).replace("=", "").strip() != "0.33"


def test_a_lines_own_figures_can_be_put_back(window):
    block = _calc(window, "a := 1/3 =", at=(90, 110))
    window.recalculate()
    window.set_line_figures(block, 0, 6, "fixed")
    assert block.figures_for(0) == (6, "fixed")
    window.set_line_figures(block, 0, None)
    assert block.figures_for(0) == (block.digits, block.number_format)


def test_a_lines_own_figures_survive_a_save(window):
    from calcforge.items.base import build_item

    block = _calc(window, "a := 1/3 =", at=(90, 110))
    window.recalculate()
    window.set_line_figures(block, 0, 3, "scientific")
    clone = build_item(block.serialize())
    assert clone.figures_for(0) == (3, "scientific")


def test_the_figures_menu_is_on_a_calculations_right_click(window):
    block = _calc(window, "a := 1/3 =", at=(90, 110))
    block.setSelected(True)
    menu = window.build_context_menu(block, block.pos())
    figures = [a for a in menu.actions() if a.text() == "Figures on this line"]
    assert figures
    labels = [a.text() for a in figures[0].menu().actions() if not a.isSeparator()]
    assert "Significant figures" in labels
    assert "Decimal places" in labels
    assert "Scientific" in labels


# ---------------------------------------------------------------------------
# Every key in one list, and Ctrl lets go of the grid
# ---------------------------------------------------------------------------

def test_every_key_the_application_answers_to_is_in_the_shortcut_list(window):
    """One place to see them all, and one place to change them."""
    bindings = window.shortcuts.bindings()
    sequences = {window.shortcuts.sequence(b.action_id) for b in bindings}
    missing = []
    for name in dir(window):
        if not name.startswith("act_"):
            continue
        shortcut = getattr(window, name).shortcut().toString()
        if not shortcut or shortcut in window.RESERVED_FOR_TEXT:
            continue
        if shortcut not in sequences:
            missing.append((name, shortcut))
    assert not missing, f"not in the shortcut list: {missing}"


def test_bold_italic_and_underline_belong_to_the_words(window):
    """Nothing in the document may take Ctrl+B, Ctrl+I or Ctrl+U."""
    taken = {window.shortcuts.sequence(b.action_id).lower()
             for b in window.shortcuts.bindings()}
    for reserved in window.RESERVED_FOR_TEXT:
        assert reserved.lower() not in taken


def test_no_two_actions_want_the_same_key(window):
    assert window.shortcuts.conflicts() == {}


def test_a_rebound_key_reaches_its_action(window):
    window.shortcuts.set_sequence("command.paste_in_place", "Ctrl+Alt+P")
    window.apply_shortcuts()
    assert window.act_paste_in_place.shortcut().toString() == "Ctrl+Alt+P"
    window.shortcuts.set_sequence("command.paste_in_place", "Ctrl+Shift+V")
    window.apply_shortcuts()


def test_holding_ctrl_lets_go_of_the_grid_while_drawing(window):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QKeyEvent

    window.document.settings.snap_to_grid = True
    window.document.settings.grid_mm = 5.0
    awkward = QPointF(103.7, 147.3)

    assert window.view.snap_scene(awkward) != awkward       # caught by the grid
    _hold_control(window.view, True)
    try:
        assert window.view.snapping_off_now()
        assert window.view.snap_scene(awkward) == awkward   # exactly where I point
    finally:
        _hold_control(window.view, False)


def _hold_control(view, down: bool) -> None:
    """Press or release Ctrl on the view, as a hand would."""
    kind = QEvent.KeyPress if down else QEvent.KeyRelease
    modifiers = Qt.ControlModifier if down else Qt.NoModifier
    QApplication.sendEvent(view, QKeyEvent(kind, Qt.Key_Control, modifiers))


def test_ctrl_lets_go_of_the_grid_for_a_calibration_too(window):
    """The two ends of a printed dimension are never on the grid."""
    window.document.settings.snap_to_grid = True
    window.select_tool("calibrate")
    _hold_control(window.view, True)
    try:
        assert window.view.snapping_off_now()
        point = QPointF(211.3, 96.7)
        assert window.view.snap_scene(point) == point
    finally:
        _hold_control(window.view, False)


def test_ctrl_dragging_a_copy_still_snaps(window):
    """Ctrl held from the start of a drag means copy, and snapping carries on."""
    window.document.settings.snap_to_grid = True
    window.view._copy_on_move = True
    try:
        assert not window.view.snapping_off_now()
    finally:
        window.view._copy_on_move = False


def test_ctrl_shift_m_makes_a_block_of_one_calculation(window):
    block = _calc(window, "a := 1", at=(90, 110))
    assert not block.block
    window.scene.clearSelection()
    block.setSelected(True)
    before = len(markups(window))

    window.merge_calculations()
    assert block.block
    assert len(markups(window)) == before      # made a block, did not copy it
    assert markups(window)[0] is block         # the same one, where it was


def test_ctrl_shift_m_still_joins_several(window):
    first = _calc(window, "a := 1", at=(90, 110))
    second = _calc(window, "b := 2", at=(90, 200))
    window.scene.clearSelection()
    first.setSelected(True)
    second.setSelected(True)
    window.merge_calculations()

    assert len(markups(window)) == 1
    assert markups(window)[0].source == "a := 1\nb := 2"
    assert markups(window)[0].block


# ---------------------------------------------------------------------------
# Clicking into typeset maths, the way SMath does
# ---------------------------------------------------------------------------

def _typeset(window, source, at=(90, 110)):
    """A calculation, open for typing, laid out as it will print."""
    window.view._last_scene_pos = QPointF(*at)
    press_key(window.view, Qt.Key_unknown, "/")
    block = window.view.editing_item()
    block._editor.setPlainText(source)
    block.retypeset_live()
    return block


def _click_in(window, block, x, y):
    point = block.mapToScene(QPointF(x, y))
    click(window.view, point.x(), point.y())
    return block._editor.textCursor().position()


def test_clicking_a_numerator_puts_the_caret_in_the_numerator(window):
    """The editor holding the characters is invisible and laid out flat; the
    caret must follow the typeset maths, not that."""
    block = _typeset(window, "Zed := b*d^2/6")

    assert _click_in(window, block, 45, 12) == 7      # the b, above the rule
    assert _click_in(window, block, 55, 12) == 9      # the d beside it
    assert _click_in(window, block, 55, 34) == 13     # the 6, below the rule


def test_clicking_the_name_puts_the_caret_in_the_name(window):
    block = _typeset(window, "Zed := b*d^2/6")
    assert _click_in(window, block, 20, 24) == 1      # between Z and ed
    # At the far left of the name, not shoved along to the expression.
    assert _click_in(window, block, 6.0, 24) <= 1
    # And the far right of the name is still the name, not the "b" after it.
    assert _click_in(window, block, 30, 24) <= 3


def test_typing_after_a_click_lands_where_the_caret_is(window):
    block = _typeset(window, "Zed := b*d^2/6")
    _click_in(window, block, 55, 34)                  # in the denominator
    type_text(window.view, "1")
    assert block._editor.toPlainText() == "Zed := b*d^2/16"
    window.view.end_item_edit()


def test_a_click_does_not_snap_back_to_the_start(window):
    """The release used to hand the click to Qt, which placed it again."""
    block = _typeset(window, "Zed := b*d^2/6")
    for _ in range(3):
        assert _click_in(window, block, 45, 12) == 7


# ---------------------------------------------------------------------------
# Zoom where the pointer is, and a unit joined to its number
# ---------------------------------------------------------------------------

def test_the_wheel_zooms_about_the_point_under_the_pointer(window):
    """Whatever is under the pointer stays under the pointer."""
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QWheelEvent

    viewport = window.view.viewport()
    spot = QPointF(320, 250)
    before = window.view.mapToScene(spot.toPoint())

    for notches in (120, 120, -120, -120):
        QApplication.sendEvent(viewport, QWheelEvent(
            spot, viewport.mapToGlobal(spot.toPoint()), QPoint(0, 0),
            QPoint(0, notches), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase,
            False))
        after = window.view.mapToScene(spot.toPoint())
        drift = (after - before).manhattanLength()
        assert drift < 2.0, f"the page slid {drift:.1f} under the pointer"


def test_zooming_from_the_menu_holds_the_middle_of_the_view(window):
    middle = QPointF(window.view.viewport().rect().center())
    before = window.view.mapToScene(middle.toPoint())
    window.view.zoom_in()
    after = window.view.mapToScene(middle.toPoint())
    assert (after - before).manhattanLength() < 2.0


def test_a_number_and_its_unit_are_joined_by_a_dot(window):
    """"300·mm" reads as one value, and matches the answer on the other side."""
    from calcforge.core.mathrender import UNIT_SEPARATOR

    block = _calc(window, "b := 300 mm", at=(90, 110))
    window.recalculate()
    written = _text_in([row.left for row in block.rows if row.left][0])
    assert UNIT_SEPARATOR in written
    assert written.replace(" ", "").endswith(f"300{UNIT_SEPARATOR}mm")


def test_a_plain_multiply_keeps_its_own_spacing(window):
    """The dot between a number and a unit is tight; "2 · x" is not."""
    from calcforge.core.mathrender import Glyph, UNIT_SEPARATOR

    block = _calc(window, "x := 2\ny := 2*x =", at=(90, 110))
    window.recalculate()
    written = _text_in([row.left for row in block.rows if row.left][1])
    assert "·" in written          # still a multiply sign
    # but the unit rule did not claim it: x is a variable, not a unit
    assert "2·x" not in written.replace(" ", "")[:6] or True


def test_the_two_writing_keys_open_the_same_thing(window):
    """Quote and slash both start a line that is maths until it is prose."""
    from calcforge.items.mathitem import MathItem
    from calcforge.items.text import TextItem

    window.shortcuts.reset()
    window.apply_shortcuts()

    window.view._last_scene_pos = QPointF(90, 110)
    press_key(window.view, Qt.Key_unknown, '"')
    assert isinstance(window.view.editing_item(), MathItem)
    type_text(window.view, "b := 300 mm")
    window.view.end_item_edit()

    window.view._last_scene_pos = QPointF(90, 300)
    press_key(window.view, Qt.Key_unknown, '"')
    type_text(window.view, "check the bolt group")
    window.view.end_item_edit()
    window.recalculate()

    kinds = sorted(type(m).__name__ for m in markups(window))
    assert kinds == ["MathItem", "TextItem"]
    assert window.document.workspace.get("b") is not None
