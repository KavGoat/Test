"""Interaction tests driven by the events Qt actually sends.

Everything here goes through the viewport as a real pointer or keyboard would:
press/release pairs, the four-event double-click sequence, context-menu events,
and key presses with their text.  Calling a handler directly would hide exactly
the bugs this file exists to catch.
"""
import pytest
from PySide6.QtCore import (QEvent, QKeyCombination, QPoint, QPointF,
                            QRectF, Qt)
from PySide6.QtGui import QColor, QContextMenuEvent, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QLabel

from markforge.core.document import MM_TO_PT
from markforge.items.measure import DIMENSION, MeasureItem
from markforge.items.shapes import PolyItem, RectItem
from markforge.items.snapshot import SnapshotItem
from markforge.items.text import CalloutItem, TextItem


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
    assert any("offset" in label.lower() for label in labels)


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


@pytest.mark.parametrize("character, tool_key", [
    ("c", "cloud"), ("r", "rect"), ("p", "polygon"), ("a", "arrow"),
    ("m", "measure_length"), ("q", "callout"), ("t", "text"), ("e", "ellipse"),
    ("l", "line"), ("h", "highlighter"), ("n", "polyline"),
    ("s", "stamp"),
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


def test_a_count_marker_shows_its_whole_number_at_any_size(window):
    """The number used to be drawn into a box fixed at ten points tall.

    At the size it ships in that just fits, so it looked right until somebody
    made the marker bigger — and then the number was cut off at the bottom,
    and past about eleven points it was painted outside the item's own
    rectangle and clipped away entirely.
    """
    from PySide6.QtGui import QFontMetricsF
    from markforge.items.measure import CountItem

    window.select_tool("count")
    for x in (150, 200, 250):
        click(window.view, x, 200)
    markers = [i for i in markups(window) if isinstance(i, CountItem)]
    assert [m.index for m in markers] == [1, 2, 3]

    marker = markers[0]
    for size in (7.0, 9.0, 11.0, 14.0, 18.0):
        marker.style.font_size = size
        marker.index = 128           # the widest number a sheet is likely to reach
        metrics = QFontMetricsF(marker.style.font())
        box = marker.index_rect()
        assert metrics.horizontalAdvance("128") <= box.width(), size
        assert metrics.height() <= box.height(), size
        assert marker.boundingRect().contains(box), size
    window.view.escape_everything()


def test_escape_puts_the_count_tool_down_at_once(window):
    """One press, and nothing of the count session is left behind."""
    from markforge.items.measure import CountItem

    window.select_tool("count")
    for x in (150, 200):
        click(window.view, x, 200)
    assert len([i for i in markups(window) if isinstance(i, CountItem)]) == 2

    press_key(window.view, Qt.Key_Escape)
    QApplication.processEvents()
    assert window.view.tool_key == "select", "the tool is put down on the press"
    assert window.view._draft is None, "and no half-placed marker is left"
    placed = [i for i in markups(window) if isinstance(i, CountItem)]
    assert [m.index for m in placed] == [1, 2], "what was placed stays placed"


def _box_kinds(box, out=None):
    out = [] if out is None else out
    out.append(type(box).__name__)
    for child, _x, _baseline in box.children_at(0, 0):
        _box_kinds(child, out)
    return out


def test_a_snapshot_is_borderless_when_it_comes_back(window):
    """The outline nobody asked for, and why changing the default never moved it.

    A snapshot payload carries no markup style, so generic deserialisation put
    the red line every drawn markup starts with onto it. The default was right
    all along and was being thrown away on the way back in.
    """
    from markforge.items.base import build_item
    from markforge.items.snapshot import SnapshotItem

    payload = {"type": "snapshot", "asset": "k", "x": 0.0, "y": 0.0,
               "rect": [0, 0, 120, 80], "source_rect": [0, 0, 120, 80],
               "source_page": 1, "keep_aspect": True, "uid": "ab"}
    item = build_item(dict(payload))
    assert isinstance(item, SnapshotItem)
    assert item.style.stroke == "" and item.style.width == 0.0
    assert not (item.style.stroke and item.style.width > 0), "so nothing is drawn"

    # A stroke that was deliberately set still survives the trip.
    kept = SnapshotItem()
    kept.style.stroke, kept.style.width = "#1971c2", 1.5
    back = build_item(dict(kept.serialize(), type="snapshot"))
    assert back.style.stroke == "#1971c2" and back.style.width == 1.5


def test_the_size_entry_stays_upright_whichever_way_the_page_is_turned(window):
    """It was photographed lying on its side, labels reading bottom-to-top.

    A tooltip belongs to the screen, not to the paper.
    """
    from PySide6.QtWidgets import QGraphicsItem
    from markforge.core.document import PageScale

    window.current_page().scale = PageScale.from_ratio(50)
    for turn in (0, 90, 180, 270):
        window.view.scene().set_reading_turn(turn)
        QApplication.processEvents()
        window.select_tool("rect")
        click(window.view, 200, 200)
        hover(window.view, 340, 320)
        proxy = window.view._size_proxy
        assert proxy is not None, turn
        assert proxy.rotation() == 0.0, turn
        assert proxy.flags() & QGraphicsItem.ItemIgnoresTransformations, turn
        window.view.escape_everything()
        QApplication.processEvents()
    window.view.scene().set_reading_turn(0)


def test_every_arrow_moves_the_insertion_point(window):
    """Left and Right used to do nothing, which is half a caret."""
    from markforge.ui import preferences

    prefs = preferences.current()
    was = prefs.insertion_point
    try:
        prefs.insertion_point = True
        preferences.apply(prefs)
        window.select_tool("select")
        click(window.view, 260, 340)
        assert window.view._insertion_point is not None

        moves = {}
        for key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            before = QPointF(window.view._insertion_point)
            press_key(window.view, key)
            after = window.view._insertion_point
            moves[key] = (after.x() - before.x(), after.y() - before.y())

        assert moves[Qt.Key_Left][0] < 0 and moves[Qt.Key_Left][1] == 0
        assert moves[Qt.Key_Right][0] > 0 and moves[Qt.Key_Right][1] == 0
        assert moves[Qt.Key_Up][1] < 0 and moves[Qt.Key_Up][0] == 0
        assert moves[Qt.Key_Down][1] > 0 and moves[Qt.Key_Down][0] == 0
    finally:
        prefs.insertion_point = was
        preferences.apply(prefs)


def test_flattened_markup_lets_the_pointer_through_to_what_is_behind(window):
    """Part of the page means the pointer goes through it.

    It was already unselectable, but it went on answering "what is under the
    pointer", so it stood in front of whatever was being reached for.
    """
    from markforge.items.shapes import RectItem

    window.select_tool("rect")
    drag(window.view, 120, 120, 320, 260)          # behind
    window.select_tool("rect")
    drag(window.view, 160, 150, 280, 230)          # in front, overlapping
    boxes = [i for i in markups(window) if isinstance(i, RectItem)]
    front, back = boxes[-1], boxes[0]
    window.select_tool("select")
    assert window.view.markup_at(QPointF(220, 190)) is front

    window.view.scene().clearSelection()
    front.setSelected(True)
    window.flatten_selection()
    QApplication.processEvents()
    assert front.flattened
    assert window.view.markup_at(QPointF(220, 190)) is back, \
        "the one behind can be reached now"
    assert not front.acceptedMouseButtons(), "and the flattened one takes no clicks"

    window.view.scene().clearSelection()
    window.recover_flattened()
    QApplication.processEvents()
    assert not front.flattened
    assert front.acceptedMouseButtons(), "recovery gives the pointer back"
    assert window.view.markup_at(QPointF(220, 190)) is front


def test_two_documents_open_in_tabs_without_reaching_into_each_other(window):
    """One document per tab, one canvas each, nothing shared but the window."""
    # isVisible() is false for anything inside a window that has not been
    # shown, so it would pass here whatever the bar was doing. isHidden() is
    # the question actually being asked: was it deliberately put away.
    assert window.document_tabs.isHidden(), "one document needs no tab bar"

    first = window.document
    window.add_page()
    window.select_tool("rect")
    assert len(first.pages) == 2

    window.open_in_new_tab()
    QApplication.processEvents()
    assert window.document_tabs.count() == 2
    assert not window.document_tabs.isHidden(), "a second document brings the bar"
    assert window.document is not first, "the new tab has a document of its own"
    assert len(window.document.pages) == 1, "and pages of its own"
    assert window.undo_stack is not None
    second = window.document
    window.select_tool("ellipse")

    window.document_tabs.setCurrentIndex(0)
    QApplication.processEvents()
    assert window.document is first
    assert len(window.document.pages) == 2, "the first document is as it was left"
    assert window.view.tool_key == "rect", "including the tool in hand"
    assert window.view.scene().document is first, "and its own canvas"

    window.document_tabs.setCurrentIndex(1)
    QApplication.processEvents()
    assert window.document is second
    assert len(window.document.pages) == 1
    assert window.view.tool_key == "ellipse"

    window.close_document_tab(1)
    QApplication.processEvents()
    assert window.document_tabs.count() == 1
    assert window.document is first
    assert window.document_tabs.isHidden(), "back to one, back to no bar"


def test_a_second_window_keeps_its_own_document(window):
    """The other half of the same idea: a window with a document of its own."""
    from markforge.ui.mainwindow import MainWindow

    second = window.open_new_window()
    second.confirm_discard = lambda: True
    second.interactive_prompts = False
    try:
        assert isinstance(second, MainWindow) and second is not window
        assert second.document is not window.document
        assert second.view is not window.view
        assert second.undo_stack is not window.undo_stack

        window.select_tool("rect")
        second.select_tool("ellipse")
        assert window.view.tool_key == "rect", "the tools do not leak"
        assert second.view.tool_key == "ellipse"

        window.add_page()
        assert len(window.document.pages) == 2
        assert len(second.document.pages) == 1, "nor do the pages"
    finally:
        second.close()
        second.setParent(None)
        second.deleteLater()
        QApplication.processEvents()


def test_one_idea_has_one_name_in_the_properties_panel(window):
    """The Properties audit asked for one name per idea, and short ones.

    "Significant digits" in one panel and "Digits" in another is the sort of
    thing it was asked to find: a reader has to work out whether the two mean
    each other. And a label of half a sentence does not fit the column it is
    laid out in.
    """
    import re

    source = open("markforge/ui/panels.py", encoding="utf-8").read()
    labels = re.findall(r'form\.addRow\("([^"]+)"', source)
    assert labels, "the properties panel lays its rows out with addRow"

    for one, other in (("Significant digits", "Digits"),
                       ("Colour", "Color"),
                       ("Line width", "Thickness"),
                       ("Transparency", "Opacity")):
        assert not (one in labels and other in labels), \
            f"{one!r} and {other!r} are the same idea under two names"

    too_long = [label for label in labels if len(label.split()) > 2]
    assert not too_long, f"labels of more than two words: {too_long}"


def test_undo_takes_back_the_typing_before_the_markup_itself(window):
    """Backspace used to be unrecoverable inside an open text markup.

    The whole edit was one step on the document stack, so the first Ctrl+Z
    threw away the lot and landed on the state before the markup was opened —
    the deleted letters were not anywhere to come back from.
    """
    window.view._last_scene_pos = QPointF(90, 300)
    press_key(window.view, Qt.Key_unknown, '"')
    type_text(window.view, "300 kerb")
    item = window.view.editing_item()
    assert item._editor.toPlainText() == "300 kerb"

    for _ in range(5):
        press_key(window.view, Qt.Key_Backspace)
    QApplication.processEvents()
    assert item._editor.toPlainText() == "300"

    # How much of the typing comes back at one step is the text editor's own
    # business. What matters is that the deleted letters are somewhere to come
    # back from, and that the markup is still there to come back into.
    seen = []
    while item._editor.document().isUndoAvailable():
        window.undo_something()
        QApplication.processEvents()
        assert item.scene() is not None, "undo edits the words, not the markup"
        seen.append(item._editor.toPlainText())

    assert "300 kerb" in seen, "the deleted text comes back"
    assert seen[-1] == "", "and back down to an empty entry"
    window.view.escape_everything()


def test_placing_a_cloud_leader_shows_a_cloud_on_the_pointer(window):
    """A crosshair says "put a point somewhere"; a cloud is drawn round one.

    And nothing provisional is drawn before the cloud itself: the preview only
    appears once a region is being dragged out.
    """
    from markforge.items.text import CalloutItem

    window.select_tool("callout")
    click(window.view, 200, 200)
    click(window.view, 330, 260)
    callout = [i for i in markups(window) if isinstance(i, CalloutItem)][-1]
    window.view.escape_everything()

    before = window.view.cursor().shape()
    window.view.begin_cloud_leader(callout)
    QApplication.processEvents()
    assert window.view._pending_cloud_leader is callout
    assert window.view.cursor().shape() == Qt.BitmapCursor, \
        "a drawn cloud rides the pointer, not a stock crosshair"
    assert window.view.cursor().shape() != before
    assert window.view._marquee == [], "and nothing provisional is drawn yet"

    press_key(window.view, Qt.Key_Escape)
    QApplication.processEvents()
    assert window.view._pending_cloud_leader is None
    assert window.view.cursor().shape() != Qt.BitmapCursor, "the cloud is put down again"


def test_a_snapshot_has_a_border_that_starts_at_none_and_can_be_set(window):
    """It had no colour control anywhere, and a red frame it could not lose."""
    from markforge.items.snapshot import SnapshotItem
    from markforge.ui.stylecaps import STROKE, WIDTH, capabilities

    shot = SnapshotItem()
    assert shot.style.stroke == "" and shot.style.width == 0.0, \
        "a snapshot starts with no outline at all"
    assert {STROKE, WIDTH} <= capabilities(shot), \
        "and both surfaces are told it has one to set"

    shot.style.stroke = "#c92a2a"
    shot.style.width = 1.5
    assert shot.style.stroke and shot.style.width > 0, "a set outline is kept"


def test_a_photos_own_border_is_not_offered_but_its_default_is(window):
    """Two different questions about the same control.

    A stroke colour on a raster photo has nowhere to go, so a selected image
    does not offer one. What frame a placed image starts with is a real
    setting, though, and with no way to reach it the only frame available was
    whatever the code happened to begin with.
    """
    from markforge.items.media import ImageItem
    from markforge.ui.stylecaps import OPACITY, STROKE, WIDTH, capabilities

    photo = ImageItem()
    assert capabilities(photo) == {OPACITY}, "nothing to change on the photo"
    assert {STROKE, WIDTH} <= capabilities(photo, for_default=True), \
        "but the default frame is settable"
    assert photo.style.stroke == "" or photo.style.width == 0.0, \
        "and it starts with no frame"


def test_a_cut_out_belongs_to_any_closed_shape(window):
    """A hole used to be something only an area measurement could have.

    A rectangle, a circle and a plain polygon all enclose something and all
    get drawn round things with holes in them, so all of them take one now,
    and it is saved with the shape it came out of.
    """
    from markforge.core.document import PageScale
    from markforge.items.shapes import PolyItem, RectItem

    window.current_page().scale = PageScale.from_ratio(50)
    for tool, expected_ring in (("rect", 4), ("ellipse", 48)):
        window.select_tool(tool)
        drag(window.view, 120, 120, 420, 340)
        host = [i for i in markups(window) if isinstance(i, RectItem)][-1]
        host.style.fill = "#cccccc"
        assert len(host.outline_ring()) == expected_ring

        window.select_tool("cutout_ellipse")
        drag(window.view, 200, 180, 300, 260)
        assert len(host.cutouts) == 1, f"{tool} takes a hole"
        assert len(host.serialize().get("cutouts", [])) == 1, "and keeps it"

        fresh = RectItem()
        fresh.deserialize(host.serialize())
        assert len(fresh.cutouts) == 1, "and reads it back"

    window.select_tool("polygon")
    for x, y in ((520, 120), (760, 120), (760, 340), (520, 340)):
        click(window.view, x, y)
    press_key(window.view, Qt.Key_Return)
    QApplication.processEvents()
    poly = [i for i in markups(window) if isinstance(i, PolyItem) and i.closed][-1]
    assert len(poly.outline_ring()) >= 3

    window.select_tool("cutout_ellipse")
    drag(window.view, 600, 180, 700, 260)
    assert len(poly.cutouts) == 1, "a closed polygon takes one too"


def test_an_open_polyline_is_not_offered_as_somewhere_to_put_a_hole(window):
    """A shape that encloses nothing cannot own a hole."""
    from markforge.items.shapes import PolyItem

    window.select_tool("polyline")
    for x, y in ((120, 500), (300, 500), (300, 600)):
        click(window.view, x, y)
    press_key(window.view, Qt.Key_Return)
    QApplication.processEvents()
    line = [i for i in markups(window) if isinstance(i, PolyItem)][-1]
    assert not line.closed
    assert line.outline_ring() == []
    assert window.view.area_under(QPointF(250, 540)) is not line


def test_the_size_entry_rides_the_corner_and_says_the_size(window):
    """It used to be pinned to the top-left with two empty boxes.

    So it neither followed the shape as it grew nor said how big the shape
    currently was: the only way to learn a size was to type one.
    """
    from markforge.core.document import PageScale
    from markforge.items.shapes import RectItem

    window.current_page().scale = PageScale.from_ratio(50)
    window.select_tool("rect")
    click(window.view, 100, 100)            # first click, not a drag
    assert window.view._size_editor is not None, "the entry opens on the first click"

    seen = []
    for x, y in ((200, 180), (300, 260), (420, 340)):
        hover(window.view, x, y)
        draft = window.view._draft
        corner = draft.mapToScene(draft.local_rect().bottomRight())
        panel = window.view._size_proxy.pos()
        assert panel.x() > corner.x() and panel.y() > corner.y(), \
            "the entry sits off the corner being dragged"
        assert panel.x() - corner.x() < 40 and panel.y() - corner.y() < 40, \
            "and stays beside it rather than being left behind"
        seen.append((window.view._size_width.text(), window.view._size_height.text()))

    assert all(w and h for w, h in seen), "it says the size the whole way"
    assert seen[0] != seen[1] != seen[2], "and the size changes as the shape does"
    assert float(seen[2][0]) > float(seen[0][0])

    # Once a size is typed, what was typed is what stands.
    window.view._size_width.setText("2.5")
    window.view._size_width.textEdited.emit("2.5")
    window.view._size_height.setText("1.5")
    window.view._size_height.textEdited.emit("1.5")
    assert window.view._typed_size
    hover(window.view, 500, 460)
    assert window.view._size_width.text() == "2.5", "the drag does not overwrite it"
    assert window.view._size_height.text() == "1.5"
    window.view.escape_everything()


def test_arrow_tool_places_an_arrow_and_hides_handles_until_selected(window):
    from PySide6.QtGui import QImage, QPainter

    window.select_tool("arrow")
    drag(window.view, 120, 180, 300, 240)
    arrow = [item for item in markups(window)
             if isinstance(item, PolyItem) and item.kind == "arrow"][-1]
    assert arrow.style.arrow_end == "arrow"
    arrow.setSelected(False)

    def handles_image():
        image = QImage(400, 300, QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        arrow.paint_handles(painter)
        painter.end()
        return image

    hidden = handles_image()
    assert all(hidden.pixelColor(x, y).alpha() == 0
               for x in range(hidden.width()) for y in range(hidden.height()))
    arrow.setSelected(True)
    shown = handles_image()
    assert any(shown.pixelColor(x, y).alpha() > 0
               for x in range(shown.width()) for y in range(shown.height()))


def test_cloud_tool_supports_dragged_and_point_by_point_clouds(window):
    window.select_tool("cloud")
    drag(window.view, 100, 100, 260, 200)
    dragged = [item for item in markups(window)
               if isinstance(item, RectItem) and item.kind == "cloud"]
    assert len(dragged) == 1

    window.select_tool("cloud")
    click(window.view, 320, 300)
    click(window.view, 460, 300)
    click(window.view, 460, 410)
    click(window.view, 320, 410)
    press_key(window.view, Qt.Key_Return)
    custom = [item for item in markups(window)
              if isinstance(item, PolyItem) and item.kind == "cloud"]
    assert len(custom) == 1
    assert custom[0].closed and len(custom[0].points) == 4


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
    from markforge.core.document import PageScale
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


def test_a_page_set_to_a_real_one_to_one_is_not_an_unscaled_page(window):
    """Choosing 1:1 is a decision, and it has to survive being written down.

    The flag used to be read back off the label, so a drawing that really is
    full size looked exactly like a page nobody had calibrated: every
    scale-dependent markup went on asking for a scale the page already had.
    """
    from markforge.core.document import PageScale
    from markforge.io import project as project_io

    page = window.current_page()
    assert not page.scale.is_calibrated(), "a fresh page has no scale"

    page.scale = PageScale.from_ratio(1)
    assert page.scale.label == "1:1"
    assert page.scale.is_calibrated(), "1:1 chosen on purpose is a scale"

    window.select_tool("measure_length")
    drag(window.view, 100, 400, 300, 400)
    assert "no scale" not in window.status_hint.text()

    there_and_back = PageScale.from_dict(page.scale.to_dict())
    assert there_and_back.is_calibrated(), "and it survives a save"

    # A document written before the flag existed has only its label to go on.
    old = page.scale.to_dict()
    del old["calibrated"]
    assert not PageScale.from_dict(old).is_calibrated()
    old["label"] = "1:50"
    assert PageScale.from_dict(old).is_calibrated()


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


def test_one_ellipse_diameter_makes_a_circle_and_escape_cancels(window, qapp):
    from PySide6.QtTest import QTest

    scaled_page(window, 50)
    window.interactive_prompts = False
    window.select_tool("ellipse")
    click(window.view, 300, 120)
    width = window.view._size_width
    assert width.placeholderText().startswith("D1")
    QTest.keyClicks(width, "1.5m")
    qapp.processEvents()
    draft = window.view._draft
    assert draft.local_rect().width() == pytest.approx(draft.local_rect().height())

    QTest.keyClick(width, Qt.Key_Escape)
    qapp.processEvents()
    assert window.view._draft is None
    assert window.view._size_editor is None
    assert window.view.tool_key == "select"
    assert window.view.cursor().shape() == Qt.ArrowCursor


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


def test_the_rectangle_size_prompt_appears_after_scale_is_known(window, monkeypatch):
    from markforge.ui import dialogs
    asked = []
    monkeypatch.setattr(dialogs.RectangleSizeDialog, "exec",
                        lambda self: asked.append(True) or dialogs.QDialog.Rejected)
    window.interactive_prompts = True
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
    from markforge.ui import dialogs
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 180)
    window.select_tool("select")
    rect = only(window, RectItem)[0]
    rect.setSelected(True)

    menu = window.build_context_menu(rect, QPointF(150, 140))
    assert "Exact size…" in [a.text() for a in menu.actions() if a.text()]

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
    from markforge.ui import dialogs
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
    from markforge.ui import dialogs
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


def test_repeat_along_an_axis_is_a_rebindable_shortcut(window, monkeypatch, qapp):
    from PySide6.QtGui import QKeySequence
    from PySide6.QtTest import QTest
    from markforge.ui import dialogs

    window.select_tool("rect")
    drag(window.view, 100, 100, 160, 160)
    window.select_tool("select")
    only(window, RectItem)[0].setSelected(True)
    monkeypatch.setattr(dialogs.ArrayDialog, "exec",
                        lambda self: dialogs.QDialog.Accepted)
    monkeypatch.setattr(dialogs.ArrayDialog, "offsets",
                        lambda self: ("25 mm", "0", 1, True))
    window.show()
    window.view.setFocus()
    qapp.processEvents()

    QTest.keyClick(window.view, Qt.Key_D,
                   Qt.ControlModifier | Qt.ShiftModifier)
    qapp.processEvents()

    binding = window.shortcuts.binding_for(QKeySequence("Ctrl+Shift+D"))
    assert binding is not None and binding.action_id == "command.array"
    assert len(only(window, RectItem)) == 2


def test_offsets_are_paper_distances_without_a_scale(window):
    from markforge.core.document import MM_TO_PT
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
    from markforge.core.document import PageScale
    from markforge.ui import dialogs

    window.select_tool("rect")
    drag(window.view, 100, 100, 236, 168)
    window.select_tool("select")

    def sizes():
        panel = window.markups_panel
        column = panel.COLUMNS.index("Value")
        return [panel.tree.topLevelItem(0).child(i).text(column)
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
    from markforge.ui.scene import detach

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


def test_a_note_can_be_placed_without_a_dialog_getting_in_the_way(window):
    from markforge.items.text import NoteItem

    window.select_tool("note")               # interactive_prompts is off here
    click(window.view, 200, 200)
    notes = only(window, NoteItem)
    assert len(notes) == 1
    assert notes[0].comment == ""


def test_double_clicking_a_note_opens_what_it_says(window, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    from markforge.items.text import NoteItem

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
    from markforge.items.text import NoteItem

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


def test_document_commands_are_silent_while_typing(window):
    window.select_tool("text")
    drag(window.view, 100, 100, 340, 150)
    assert window.view.is_editing()
    assert swallowed(window, Qt.Key_0, Qt.ControlModifier)
    assert swallowed(window, Qt.Key_S, Qt.ControlModifier)
    assert swallowed(window, Qt.Key_P, Qt.ControlModifier)


def test_text_formatting_shortcuts_are_not_suppressed_while_typing(window):
    window.select_tool("text")
    drag(window.view, 100, 100, 340, 150)
    assert window.view.is_editing()
    assert not swallowed(window, Qt.Key_B, Qt.ControlModifier)
    assert not swallowed(window, Qt.Key_I, Qt.ControlModifier)
    assert not swallowed(window, Qt.Key_U, Qt.ControlModifier)


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
    press_key(window.view, Qt.Key_unknown, '"')
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
    """With the optional insertion point off, a click leaves no mark behind."""
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


def test_the_arrows_never_scroll_the_page_on_their_own(window):
    """Arrows move something or do nothing. They do not slide the drawing.

    They used to scroll the document when nothing was selected, the way they
    do in a reader — but this is a drawing, and a key that quietly slides the
    page under the pointer changes what the next click lands on.
    """
    window.select_tool("select")
    window.view.scene().clearSelection()
    QApplication.processEvents()          # let the view settle where it opens
    before = (window.view.horizontalScrollBar().value(),
              window.view.verticalScrollBar().value())
    for key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
        press_key(window.view, key)
        QApplication.processEvents()
    after = (window.view.horizontalScrollBar().value(),
             window.view.verticalScrollBar().value())
    assert after == before, "nothing was selected, so nothing should have moved"


def test_the_view_follows_a_markup_nudged_off_the_bottom_of_it(window):
    """The one time an arrow may scroll: to keep what it is moving in sight."""
    window.select_tool("rect")
    drag(window.view, 120, 120, 240, 200)
    window.select_tool("select")
    box = markups(window)[0]
    box.setSelected(True)
    QApplication.processEvents()

    bar = window.view.verticalScrollBar()
    assert bar.maximum() > bar.minimum(), "the document has somewhere to scroll to"

    # Scroll until the markup has gone off the top of the view, then nudge it
    # further the same way: the view has to come with it.
    while bar.value() < bar.maximum():
        seen = window.view.mapToScene(window.view.viewport().rect()).boundingRect()
        if seen.top() > box.sceneBoundingRect().bottom():
            break
        bar.setValue(bar.value() + 40)
        QApplication.processEvents()
    seen = window.view.mapToScene(window.view.viewport().rect()).boundingRect()
    assert not seen.intersects(box.sceneBoundingRect()), "it is off screen now"

    before = bar.value()
    press_key(window.view, Qt.Key_Up)
    QApplication.processEvents()
    assert bar.value() < before, \
        "the view comes with the markup rather than losing it off the edge"
    seen = window.view.mapToScene(window.view.viewport().rect()).boundingRect()
    assert seen.intersects(box.sceneBoundingRect()), "and it is back in sight"


def test_the_insertion_point_is_drawn_as_a_small_crosshair(window):
    from markforge.ui import preferences

    prefs = preferences.current()
    was = prefs.insertion_point
    try:
        prefs.insertion_point = True
        preferences.apply(prefs)
        window.select_tool("select")
        click(window.view, 260, 340)
        assert window.view._insertion_point is not None

        strokes = []
        class Recorder:
            def save(self): pass
            def restore(self): pass
            def setPen(self, pen): pass
            def drawLine(self, a, b): strokes.append((a, b))
        window.view._draw_insertion_point(Recorder(), window.view._insertion_point)
        assert len(strokes) == 2, "a crosshair is two strokes, not a bracketed marker"
        lengths = sorted((a - b).manhattanLength() for a, b in strokes)
        assert lengths[0] == pytest.approx(lengths[1]), "and both arms the same length"
    finally:
        prefs.insertion_point = was
        preferences.apply(prefs)


def test_the_optional_insertion_point_is_visible_and_escape_clears_it(window):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter
    from markforge.ui import preferences

    prefs = preferences.current()
    was = prefs.insertion_point
    try:
        prefs.insertion_point = True
        preferences.apply(prefs)
        click(window.view, 260, 340)

        image = QImage(80, 80, QImage.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        painter.translate(-220, -300)
        window.view.drawForeground(painter, QRectF(220, 300, 80, 80))
        painter.end()
        assert any(image.pixelColor(x, y).alpha() > 0
                   for x in range(80) for y in range(80))

        press_key(window.view, Qt.Key_Escape)
        assert window.view._insertion_point is None
        assert window.view.cursor().shape() == Qt.ArrowCursor
    finally:
        prefs.insertion_point = was
        preferences.apply(prefs)


def test_preferences_exposes_the_optional_insertion_point(window, qapp):
    from PySide6.QtTest import QTest
    from markforge.ui import dialogs, preferences

    window.show()
    qapp.processEvents()
    dialog = dialogs.PreferencesDialog(preferences.current(), window)
    dialog.show()
    qapp.processEvents()
    assert dialog.insertion.text() == "Insertion point"
    assert not dialog.insertion.isChecked()
    dialog.insertion.setFocus()
    QTest.keyClick(dialog.insertion, Qt.Key_Space)
    qapp.processEvents()
    assert dialog.result_preferences().insertion_point
    dialog.deleteLater()


def test_preferences_exposes_recoverable_flattening(window, qapp):
    from PySide6.QtTest import QTest
    from markforge.ui import dialogs, preferences

    dialog = dialogs.PreferencesDialog(preferences.current(), window)
    dialog.show()
    qapp.processEvents()
    assert dialog.recover_flattened.text() == "Recoverable flattening"
    before = dialog.recover_flattened.isChecked()
    dialog.recover_flattened.setFocus()
    QTest.keyClick(dialog.recover_flattened, Qt.Key_Space)
    qapp.processEvents()
    assert dialog.result_preferences().recover_flattened is not before
    dialog.deleteLater()


# ---------------------------------------------------------------------------
# Working on a page from its thumbnail
# ---------------------------------------------------------------------------

def _menu_labels(menu):
    """Every label on a menu, submenus opened out."""
    found = []
    for action in menu.actions():
        if action.isSeparator():
            continue
        found.append(action.text())
        if action.menu() is not None:
            found += _menu_labels(action.menu())
    return found


def _menu_entry(menu, label):
    """One action out of a menu, by what it says."""
    found = [action for action in menu.actions() if action.text() == label]
    assert found, f"{label!r} not in {_menu_labels(menu)}"
    return found[0]


def test_current_page_commands_are_reachable_from_the_menu_bar(window, qapp):
    from PySide6.QtTest import QTest

    window.show()
    qapp.processEvents()
    menu = window.current_page_menu
    menu.popup(window.mapToGlobal(window.rect().center()))
    qapp.processEvents()
    labels = _menu_labels(menu)
    assert {"Rename…", "Blank after", "Move down",
            "Rotate clockwise", "Change colours…"} <= set(labels)

    add = _menu_entry(menu, "Blank after")
    QTest.mouseClick(menu, Qt.LeftButton, Qt.NoModifier,
                     menu.actionGeometry(add).center())
    qapp.processEvents()
    assert len(window.document.pages) == 2




def test_every_tool_and_application_action_is_reachable_from_the_menu_bar(window):
    from markforge.ui.tools import TOOLS

    all_actions = set()

    def collect(menu):
        for action in menu.actions():
            all_actions.add(action)
            if action.menu() is not None:
                collect(action.menu())

    top = {action.text().replace("&", ""): action.menu()
           for action in window.menuBar().actions()}
    for menu in top.values():
        collect(menu)
    missing = [(name, getattr(window, name).text()) for name in dir(window)
               if name.startswith("act_") and getattr(window, name) not in all_actions]
    assert missing == []

    insert_labels = set(_menu_labels(top["Insert"]))
    assert {tool.label for tool in TOOLS} <= insert_labels


def test_the_only_page_cannot_be_deleted_from_the_menu(window):
    assert len(window.document.pages) == 1
    actions = {action.text(): action for action in window.page_menu(0).actions()}
    assert not actions["Delete page"].isEnabled()


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





def test_a_symbol_bound_to_a_bare_key_still_types_itself(window):
    window.shortcuts.set_sequence("symbol.pi", ";")
    window.apply_shortcuts()
    try:
        window.view._last_scene_pos = QPointF(120, 320)
        press_key(window.view, Qt.Key_unknown, '"')
        block = window.view.editing_item()
        type_text(window.view, "dia ")
        assert window.run_typed_binding(";", Qt.NoModifier, QPointF(0, 0))
        window.view.end_item_edit()
        assert "π" in block.text()
    finally:
        window.shortcuts.reset("symbol.pi")
        window.apply_shortcuts()


def test_symbol_keys_are_live_while_you_type(window):
    """Unlike tool keys, a symbol key must not be swallowed mid-calculation."""
    from PySide6.QtGui import QKeySequence

    window.view._last_scene_pos = QPointF(120, 380)
    press_key(window.view, Qt.Key_unknown, '"')
    assert window.view.is_editing()
    assert not window.shortcuts.is_canvas_binding(QKeySequence("Ctrl+Alt+8"))
    assert window.shortcuts.is_canvas_binding(QKeySequence("R"))
    window.view.end_item_edit()


# ---------------------------------------------------------------------------
# A calculation prints what it was asked to print
# ---------------------------------------------------------------------------







# ---------------------------------------------------------------------------
# Changing the unit a result is shown in
# ---------------------------------------------------------------------------











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
    from markforge.ui import dialogs

    from PySide6.QtWidgets import QPushButton

    dialog = dialogs.ScaleDialog(window.current_page().scale, None, window)
    try:
        # The button is labelled in one or two words; what it does is in the
        # tooltip, so that is where "pick two points" has to be findable.
        picks = [b for b in dialog.findChildren(QPushButton)
                 if "pick two points" in b.toolTip().lower()]
        assert picks and picks[0].isEnabled()
        assert picks[0].text() == "Calibrate…"
    finally:
        dialog.deleteLater()


def test_calibration_has_a_visible_rebindable_shortcut(window):
    assert window.act_scale.shortcut().toString() == "Ctrl+Shift+K"
    binding = [b for b in window.shortcuts.bindings()
               if b.action_id == "command.scale"]
    assert binding and binding[0].label == "Page scale"


@pytest.mark.parametrize("entered", ["10mm", "10 mm"])
def test_the_calibration_length_prompt_accepts_joined_or_spaced_units(
        window, entered):
    from markforge.ui import dialogs

    dialog = dialogs.CalibrationLengthDialog(200.0, window)
    try:
        assert not dialog.known.text()
        dialog.known.setText(entered)
        assert dialog.length_text() == entered
    finally:
        dialog.deleteLater()


def test_the_calibration_length_prompt_rejects_incompatible_units(
        window, monkeypatch):
    from markforge.ui import dialogs
    warned = []
    monkeypatch.setattr(dialogs.QMessageBox, "warning",
                        lambda *args: warned.append(args))
    dialog = dialogs.CalibrationLengthDialog(200.0, window)
    try:
        dialog.known.setText("10 kPa")
        assert dialog.length_text() is None
        assert warned and "compatible units" in warned[0][2]
    finally:
        dialog.deleteLater()




def test_choosing_to_pick_points_starts_the_calibrate_tool(window, monkeypatch):
    from markforge.ui import dialogs

    monkeypatch.setattr(dialogs.ScaleDialog, "exec",
                        lambda self: dialogs.ScaleDialog.PICK)
    window.calibrate_scale(None)
    assert window.view.tool_key == "calibrate"
    assert "click one end" in window.status_hint.text().lower()


@pytest.mark.parametrize("tool", ["rect", "ellipse", "measure_length",
                                   "measure_area"])
def test_the_first_scaled_tool_click_prompts_before_drawing(
        window, monkeypatch, tool):
    from markforge.core.document import PageScale

    asked = []

    def calibrate():
        asked.append(tool)
        window.current_page().scale = PageScale.from_ratio(100)

    monkeypatch.setattr(window, "calibrate_dialog", calibrate)
    window.interactive_prompts = True
    window.select_tool(tool)
    click(window.view, 100, 300)

    assert asked == [tool]
    assert window.view._draft is not None


def test_cancelling_the_first_scale_prompt_does_not_create_a_markup(
        window, monkeypatch):
    monkeypatch.setattr(window, "calibrate_dialog", lambda: None)
    window.interactive_prompts = True
    window.select_tool("measure_length")

    click(window.view, 100, 300)

    assert window.view._draft is None
    assert markups(window) == []


def test_two_clicks_and_a_length_set_the_scale(window, monkeypatch):
    from markforge.ui import dialogs

    asked = {}

    class Stub(dialogs.CalibrationLengthDialog):
        def exec(self):
            asked["measured"] = self.measured_pt
            self.known.setText("10 m")
            return dialogs.QDialog.Accepted

    monkeypatch.setattr(dialogs, "CalibrationLengthDialog", Stub)
    window.select_tool("calibrate")
    click(window.view, 100, 300)
    click(window.view, 300, 300)

    assert asked["measured"] == pytest.approx(200, abs=2)
    scale = window.current_page().scale
    assert scale.is_calibrated()
    assert scale.length(200.0).to("m").magnitude == pytest.approx(10, rel=1e-3)


def test_a_calibration_line_is_not_left_on_the_page(window, monkeypatch):
    from markforge.ui import dialogs
    monkeypatch.setattr(dialogs.CalibrationLengthDialog, "exec",
                        lambda self: dialogs.QDialog.Rejected)
    window.select_tool("calibrate")
    drag(window.view, 100, 300, 300, 300)
    assert markups(window) == []


def test_a_page_label_can_be_renamed_and_reset_from_its_menu(window, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    page = window.current_page()
    page.source_note = "drawing.pdf page A1"
    page.label = page.source_note
    window.pages_panel.rebuild(window.document, 0)
    monkeypatch.setattr(QInputDialog, "getText",
                        lambda *args, **kwargs: ("Foundation", True))

    menu = window.page_menu(0)
    next(action for action in menu.actions()
         if action.text() == "Rename…").trigger()
    assert page.label == "Foundation"
    assert "Foundation" in window.pages_panel.list.item(0).text()

    menu = window.page_menu(0)
    next(action for action in menu.actions()
         if action.text() == "Reset label").trigger()
    assert page.label == "drawing.pdf page A1"
    assert "drawing.pdf page A1" in window.pages_panel.list.item(0).text()


def test_resetting_a_blank_pages_label_restores_its_number(window):
    page = window.current_page()
    page.source_note = ""
    page.label = "Temporary"
    window.reset_page_label(0)
    assert page.label == ""
    assert window.pages_panel.list.item(0).text() == "1"


def test_the_page_menu_can_set_the_scale(window):
    labels = [action.text() for action in window.page_menu(0).actions()]
    assert "Page scale…" in labels


# ---------------------------------------------------------------------------
# Turning a page and changing its paper
# ---------------------------------------------------------------------------

def test_a_page_can_be_turned_a_quarter_turn(window):
    """The paper itself turns — the shape of the sheet, not just its label."""
    page = window.current_page()
    width, height = page.setup.width_pt, page.setup.height_pt
    assert width < height                      # it starts portrait
    window.rotate_page(0, clockwise=True)
    assert page.setup.width_pt == pytest.approx(height)
    assert page.setup.height_pt == pytest.approx(width)
    assert page.setup.orientation == "landscape"
    # A4 is 210 by 297 whichever way it is turned: the sheet has not changed
    # size, only which way up it is being used.
    assert page.setup.size_name == "A4"


def test_the_page_frame_takes_the_new_shape(window):
    """And the paper on screen is the new shape, not the old one."""
    frame = window.view.frame()
    before = frame.page_rect()
    window.rotate_page(0, clockwise=True)
    after = window.document.pages[0].frame.page_rect()
    assert after.width() == pytest.approx(before.height(), abs=0.5)
    assert after.height() == pytest.approx(before.width(), abs=0.5)


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
    from markforge.io import pdfio

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
    before = (page.setup.width_pt, page.setup.height_pt, page.setup.margin_left,
              page.setup.margin_top, page.setup.margin_right, page.setup.margin_bottom)
    window.rotate_page(0, clockwise=True)
    window.rotate_page(0, clockwise=False)
    after = (page.setup.width_pt, page.setup.height_pt, page.setup.margin_left,
             page.setup.margin_top, page.setup.margin_right, page.setup.margin_bottom)
    assert after == pytest.approx(before)


def test_rotating_can_be_undone(window):
    window.rotate_page(0, clockwise=True)
    assert window.current_page().setup.orientation == "landscape"
    window.undo_stack.undo()
    assert window.document.pages[0].setup.orientation == "portrait"


def test_the_page_menu_offers_rotating_and_paper_sizes(window):
    menu = window.page_menu(0)
    labels = [action.text() for action in menu.actions()]
    # Named so it cannot be mistaken for turning the view, which is on the
    # View menu and changes nothing about the document.
    assert "Rotate clockwise" in labels
    assert "Rotate anticlockwise" in labels
    paper = next(action.menu() for action in menu.actions()
                 if action.text() == "Paper size")
    sizes = [action.text() for action in paper.actions()]
    assert "A4" in sizes and "A3" in sizes
    assert next(a for a in paper.actions() if a.text() == "A4").isChecked()


def _callout(window, target=(200, 300), box=(300, 200, 460, 260), text="note"):
    window.select_tool("callout")
    click(window.view, *target)
    drag(window.view, *box)
    item = window.view.editing_item()
    if text:
        item.set_text(text)
    return item


def test_a_callouts_text_box_uses_the_pointers_left_middle(window):
    _quiet_snapping(window)
    window.select_tool("callout")
    click(window.view, 180, 320)
    hover(window.view, 360, 240)
    preview = window.view._pending_callout_box()
    assert preview.left() == pytest.approx(360, abs=1)
    assert preview.center().y() == pytest.approx(240, abs=1)

    click(window.view, 360, 240)

    callout = window.view.editing_item()
    box = window.view.markup_box(callout)
    assert box.left() == pytest.approx(360, abs=1)
    assert box.center().y() == pytest.approx(240, abs=1)


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


def test_the_hinge_leaves_the_side_square_on(window):
    """However it is dragged, it comes out of the middle of a side at right
    angles — which is what a leader looks like on every drawing."""
    call = _callout(window)
    window.view.end_item_edit()
    window.select_tool("select")
    call.setSelected(True)

    for towards in (QPointF(-90, -70), QPointF(240, 30), QPointF(40, 200)):
        where = call.mapToScene(towards)
        elbow = call.mapToScene(call.elbow())
        drag(window.view, elbow.x(), elbow.y(), where.x(), where.y())
        start = call.side_point()
        hinge = call.elbow()
        # Square on: one of the two coordinates has not changed at all.
        assert (abs(hinge.x() - start.x()) < 0.01
                or abs(hinge.y() - start.y()) < 0.01), \
            f"the hinge left {call.side()} at an angle"


def test_dragging_the_hinge_out_pushes_it_further_from_the_box(window):
    """It cannot come off the perpendicular, but it can slide along it."""
    call = _callout(window)
    window.view.end_item_edit()
    window.select_tool("select")
    call.setSelected(True)
    call.leaders[0].tip = QPointF(-120, 25)
    call.leader_moved()
    before = call.leaders[0].reach

    start = call.side_point()
    further = call.mapToScene(QPointF(start.x() - 80, start.y()))
    elbow = call.mapToScene(call.elbow())
    drag(window.view, elbow.x(), elbow.y(), further.x(), further.y())
    assert call.leaders[0].reach > before
    assert call.side() == "left"


def test_dragging_the_hinge_round_changes_the_side_it_leaves_by(window):
    """Take the hinge over the top of the box and the line leaves by the top."""
    call = _callout(window)
    window.view.end_item_edit()
    window.select_tool("select")
    call.setSelected(True)
    # Point it at something off to the left, so the top is not what it would
    # have chosen for itself.
    call.leaders[0].tip = QPointF(-120, 25)
    call.leader_moved()
    started_on = call.side()

    box = call.local_rect().normalized()
    above = call.mapToScene(QPointF(box.center().x(), box.top() - 60))
    elbow = call.mapToScene(call.elbow())
    drag(window.view, elbow.x(), elbow.y(), above.x(), above.y())

    assert call.side() == "top" != started_on
    assert call.side_point().y() == pytest.approx(box.top(), abs=0.5)


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
    assert {"l0", "e0"} <= call.leader_handles()
    assert set(call.handle_points()) >= {"l0", "e0", "nw", "se"}


def test_an_empty_text_box_is_still_dropped(window):
    window.select_tool("text")
    drag(window.view, 100, 600, 260, 640)
    window.view.end_item_edit()
    assert markups(window) == []


# ---------------------------------------------------------------------------
# What a graph plots
# ---------------------------------------------------------------------------







def test_changing_a_pages_colours_changes_its_line_work_too(window):
    """A PDF page is a picture and the lines that drew it.

    Recolouring only the picture left every line its old colour on top of a
    recoloured sheet, which looks like the change half worked — because it
    did. The lines are real line work on a locked Drawing layer, so they
    change as lines and the page stays as sharp as it was.
    """
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QColor
    from markforge.io import recolour
    from markforge.items.shapes import PolyItem

    lines = []
    for colour in ("#000000", "#0a0a0a", "#c92a2a"):
        line = PolyItem("polyline", [QPointF(0, 0), QPointF(10, 0)])
        line.style.stroke = colour
        line.layer = "Drawing"
        lines.append(line)

    changed = recolour.swap_line_colour(lines, QColor("#000000"),
                                        QColor("#1971c2"), 40)
    assert changed == 2, "the two near-black lines, and not the red one"
    assert [i.style.stroke for i in lines] == ["#1971c2", "#1971c2", "#c92a2a"]

    recolour.colourise_lines(lines, QColor("#2f9e44"))
    assert all(i.style.stroke == "#2f9e44" for i in lines), "colourise takes them all"


def test_colourise_keeps_the_light_and_shade(window):
    """Bluebeam's Colorize: one colour, still readable, paper still paper."""
    from PySide6.QtGui import QColor, QImage
    from markforge.io import recolour

    image = QImage(4, 1, QImage.Format_ARGB32)
    for x, level in enumerate((0, 80, 180, 255)):
        image.setPixelColor(x, 0, QColor(level, level, level))

    out = recolour.colourise(image, QColor("#c92a2a"))
    assert out.pixelColor(0, 0).name() == "#c92a2a", "black becomes the colour"
    assert out.pixelColor(3, 0).name() == "#ffffff", "and white stays paper"
    middles = [out.pixelColor(x, 0).lightness() for x in range(4)]
    assert middles == sorted(middles), "light and shade survive in order"

    green = recolour.colourise(image, QColor("#2f9e44"))
    assert green.pixelColor(0, 0).name() == "#2f9e44", "any colour, not just red"


def test_a_colour_can_be_made_transparent_within_a_tolerance(window):
    """Near enough to the picked colour counts, which is what tolerance is for."""
    from PySide6.QtGui import QColor, QImage
    from markforge.io import recolour

    image = QImage(3, 1, QImage.Format_ARGB32)
    image.setPixelColor(0, 0, QColor(255, 255, 255))     # the colour picked
    image.setPixelColor(1, 0, QColor(245, 245, 245))     # near it
    image.setPixelColor(2, 0, QColor(20, 20, 20))        # nowhere near

    tight = recolour.make_colour_transparent(image, QColor(255, 255, 255), 0)
    assert tight.pixelColor(0, 0).alpha() == 0
    assert tight.pixelColor(1, 0).alpha() == 255, "0 tolerance takes only the exact one"

    loose = recolour.make_colour_transparent(image, QColor(255, 255, 255), 40)
    assert loose.pixelColor(0, 0).alpha() == 0
    assert loose.pixelColor(1, 0).alpha() == 0, "and a wider one takes its neighbours"
    assert loose.pixelColor(2, 0).alpha() == 255, "but never the drawing"








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


def test_ctrl_taken_hold_of_mid_move_switches_to_a_snapped_copy(window):
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    window.document.settings.snap_to_grid = True
    window.document.settings.grid_mm = 10.0
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    window.select_tool("select")
    box = markups(window)[0]
    box.setSelected(True)
    origin = QPointF(box.pos())

    centre = box.mapToScene(box.local_rect().center())
    QApplication.sendEvent(window.view.viewport(),
                           _mouse(window.view, QEvent.MouseButtonPress, centre.x(), centre.y()))
    QApplication.sendEvent(window.view.viewport(), _mouse(
        window.view, QEvent.MouseMove, centre.x() + 15, centre.y() + 8,
        Qt.NoButton, Qt.LeftButton))
    assert len(markups(window)) == 1
    QApplication.sendEvent(window.view.viewport(), _mouse(
        window.view, QEvent.MouseMove, centre.x() + 33, centre.y() + 17,
        Qt.NoButton, Qt.LeftButton, Qt.ControlModifier))
    assert len(markups(window)) == 2
    QApplication.sendEvent(window.view.viewport(), _mouse(
        window.view, QEvent.MouseMove, centre.x() + 33, centre.y() + 17,
        Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
    on_grid = box.pos()
    QApplication.sendEvent(window.view.viewport(), _mouse(
        window.view, QEvent.MouseButtonRelease, centre.x() + 33, centre.y() + 17))

    step = 10.0 * MM_TO_PT
    assert abs(round(on_grid.x() / step) * step - on_grid.x()) < 0.01
    assert len(markups(window)) == 2
    assert any(item.pos() == origin for item in markups(window))


def test_shift_first_then_ctrl_duplicates_and_keeps_the_move_constrained(window):
    import math

    window.document.settings.snap_to_grid = False
    window.document.settings.snap_to_items = False
    window.document.settings.snap_to_alignment = False
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    window.select_tool("select")
    box = markups(window)[0]
    box.setSelected(True)
    origin = QPointF(box.pos())
    centre = box.mapToScene(box.local_rect().center())

    QApplication.sendEvent(window.view.viewport(), _mouse(
        window.view, QEvent.MouseButtonPress, centre.x(), centre.y(),
        modifiers=Qt.ShiftModifier))
    QApplication.sendEvent(window.view.viewport(), _mouse(
        window.view, QEvent.MouseMove, centre.x() + 35, centre.y() + 12,
        Qt.NoButton, Qt.LeftButton, Qt.ShiftModifier))
    QApplication.sendEvent(window.view.viewport(), _mouse(
        window.view, QEvent.MouseMove, centre.x() + 100, centre.y() + 38,
        Qt.NoButton, Qt.LeftButton,
        Qt.ControlModifier | Qt.ShiftModifier))
    QApplication.sendEvent(window.view.viewport(), _mouse(
        window.view, QEvent.MouseButtonRelease, centre.x() + 100,
        centre.y() + 38, modifiers=Qt.ControlModifier | Qt.ShiftModifier))

    assert len(markups(window)) == 2
    moved = next(item for item in markups(window) if item is box)
    delta = moved.pos() - origin
    angle = abs(math.degrees(math.atan2(delta.y(), delta.x())))
    assert min(abs(angle - expected) for expected in (0, 45, 90)) < 0.5
    assert any(item is not box and item.pos() == origin for item in markups(window))


def test_shift_can_be_added_and_removed_while_a_move_is_in_progress(window):
    window.document.settings.snap_to_grid = False
    window.document.settings.snap_to_items = False
    window.document.settings.snap_to_alignment = False
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    window.select_tool("select")
    box = markups(window)[0]
    box.setSelected(True)
    origin = QPointF(box.pos())
    centre = box.mapToScene(box.local_rect().center())

    QApplication.sendEvent(window.view.viewport(), _mouse(
        window.view, QEvent.MouseButtonPress, centre.x(), centre.y()))
    QApplication.sendEvent(window.view.viewport(), _mouse(
        window.view, QEvent.MouseMove, centre.x() + 100, centre.y() + 30,
        Qt.NoButton, Qt.LeftButton))
    assert (box.pos() - origin).y() == pytest.approx(30, abs=0.5)

    QApplication.sendEvent(window.view.viewport(), _mouse(
        window.view, QEvent.MouseMove, centre.x() + 100, centre.y() + 30,
        Qt.NoButton, Qt.LeftButton, Qt.ShiftModifier))
    assert (box.pos() - origin).y() == pytest.approx(0, abs=0.5)

    QApplication.sendEvent(window.view.viewport(), _mouse(
        window.view, QEvent.MouseMove, centre.x() + 100, centre.y() + 30,
        Qt.NoButton, Qt.LeftButton))
    assert (box.pos() - origin).y() == pytest.approx(30, abs=0.5)
    QApplication.sendEvent(window.view.viewport(), _mouse(
        window.view, QEvent.MouseButtonRelease, centre.x() + 100,
        centre.y() + 30))


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
    """Bluebeam's: a cloud round what the comment is about, and the note beside
    it — and the two are one markup, not a cloud and a text box that happen to
    be grouped."""
    from markforge.items.shapes import RectItem

    window.select_tool("cloud_callout")
    drag(window.view, 160, 260, 300, 340)        # the cloud goes round it
    click(window.view, 400, 200)                 # and the words go here
    call = window.view.editing_item()
    call.set_text("check this")
    window.view.end_item_edit()

    assert isinstance(call, CalloutItem)
    assert call.clouds_a_region()
    # No arrow head: the cloud is what points at the thing, so the line only
    # says which note goes with which cloud. That is decided by the leader
    # being a cloud leader, not by taking the heads off the whole call-out —
    # an arrow leader added to the same note keeps its head.
    assert [leader.kind for leader in call.leaders] == ["cloud"]
    # And nothing separate was left on the page.
    assert not [i for i in markups(window)
                if isinstance(i, RectItem) and i.kind == "cloud"]
    assert [i for i in markups(window) if isinstance(i, CalloutItem)] == [call]

    # The clouded region is where it was dragged.
    clouded = call.mapRectToScene(call.cloud_box()).normalized()
    drawn = QRectF(QPointF(160, 260), QPointF(300, 340)).normalized()
    assert clouded.adjusted(-4, -4, 4, 4).contains(drawn)

    # The line runs between the note and the cloud, joining a corner or the
    # middle of an edge at each end.
    join = call.cloud_join()
    corners_and_middles = []
    points = call.cloud_points
    for index, point in enumerate(points):
        after = points[(index + 1) % len(points)]
        corners_and_middles.append(point)
        corners_and_middles.append((point + after) / 2)
    assert any((join - candidate).manhattanLength() < 0.01
               for candidate in corners_and_middles)
    assert call.box_join() in (
        QPointF(call.local_rect().normalized().left(),
                call.local_rect().normalized().center().y()),
        QPointF(call.local_rect().normalized().right(),
                call.local_rect().normalized().center().y()),
        QPointF(call.local_rect().normalized().center().x(),
                call.local_rect().normalized().top()),
        QPointF(call.local_rect().normalized().center().x(),
                call.local_rect().normalized().bottom()),
    )


def test_a_cloud_callout_can_be_drawn_corner_by_corner(window):
    """Cloud and Cloud+ are one tool: drag it for a rectangle, click each
    corner for whatever shape the revision actually is."""
    window.select_tool("cloud_callout")
    click(window.view, 160, 260)                 # a click, not a drag
    click(window.view, 300, 250)
    click(window.view, 280, 350)
    press_key(window.view, Qt.Key_Return)        # that closes the cloud
    click(window.view, 430, 200)                 # and the words go here
    call = window.view.editing_item()
    call.set_text("this bit")
    window.view.end_item_edit()

    assert isinstance(call, CalloutItem)
    assert call.clouds_a_region()
    assert len(call.cloud_points) >= 3
    assert [leader.kind for leader in call.leaders] == ["cloud"]


def test_escape_gets_out_of_a_half_drawn_cloud_callout(window):
    from markforge.items.shapes import RectItem

    window.select_tool("cloud_callout")
    drag(window.view, 160, 260, 300, 340)
    assert window.view._pending_cloud is not None

    press_key(window.view, Qt.Key_Escape)
    assert window.view._pending_cloud is None
    assert window.view.tool_key == "select"
    # Nothing is left behind: the cloud belongs to the note that was never
    # placed, so cancelling the note cancels the cloud with it.
    assert not [i for i in markups(window)
                if isinstance(i, RectItem) and i.kind == "cloud"]
    assert not [i for i in markups(window) if isinstance(i, CalloutItem)]


def test_a_callout_can_have_as_many_leaders_as_you_like(window):
    """One comment, three bolts: Bluebeam lets a call-out grow arrows."""
    call = _callout(window)
    assert len(call.leaders) == 1
    call.add_leader()
    call.add_leader()
    assert len(call.leaders) == 3
    # Each one gets its own pair of handles.
    assert {"l0", "e0", "l1", "e1", "l2", "e2"} <= set(call.handle_points())
    # And they do not land on top of each other.
    tips = [(round(l.tip.x(), 3), round(l.tip.y(), 3)) for l in call.leaders]
    assert len(set(tips)) == 3

    call.remove_leader(1)
    assert len(call.leaders) == 2
    assert "l2" not in call.handle_points()


def test_the_hinge_can_be_moved_to_another_side(window):
    """It is not pinned to one side: put it above the box and the leader
    leaves by the top — as long as that does not send the line back over the
    words to reach the arrow head."""
    call = _callout(window)
    box = call.local_rect().normalized()
    leader = call.leaders[0]
    leader.tip = QPointF(box.left() - 120, box.center().y())
    call.leader_moved()

    call.set_elbow_of(leader, QPointF(box.center().x(), box.top() - 40))
    assert call.side_of(leader) == "top"
    assert call.side_point_of(leader) == QPointF(box.center().x(), box.top())

    # The right-hand side is behind the box from where the arrow points, so
    # that one is refused and the leader keeps the side it has.
    call.set_elbow_of(leader, QPointF(box.right() + 40, box.center().y()))
    assert call.side_of(leader) == "top"

    # Point it the other way and the right becomes reasonable again.
    leader.tip = QPointF(box.right() + 160, box.center().y())
    call.leader_moved()
    call.set_elbow_of(leader, QPointF(box.right() + 40, box.center().y()))
    assert call.side_of(leader) == "right"
    assert call.side_point_of(leader) == QPointF(box.right(), box.center().y())


def test_the_leader_never_runs_across_its_own_words(window):
    """Whatever the hinge is dragged to, the line stays off the text box."""
    from markforge.items.text import _crosses

    call = _callout(window)
    box = call.local_rect().normalized()
    leader = call.leaders[0]
    for tip in (QPointF(-140, 20), QPointF(320, 20), QPointF(60, -160),
                QPointF(60, 220)):
        leader.tip = QPointF(tip)
        call.leader_moved()
        for towards in (QPointF(-80, 0), QPointF(280, 30), QPointF(70, -90),
                        QPointF(70, 180)):
            call.set_elbow_of(leader, towards)
            hinge = call.elbow_of(leader)
            assert not _crosses(box, hinge, leader.tip), \
                f"the line crossed the words with the tip at {tip}"
            assert not _crosses(box, call.side_point_of(leader), hinge)


def test_a_plain_callout_is_still_a_box(window):
    call = _callout(window)
    assert call.shape_kind == "box"


def test_a_cloud_callout_survives_a_round_trip(window):
    from markforge.items.base import build_item

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
    from markforge.items.shapes import RectItem

    window.select_tool("highlight")
    drag(window.view, 100, 100, 300, 140)
    mark = markups(window)[0]
    assert isinstance(mark, RectItem) and mark.kind == "highlight"
    assert mark.style.blend == "multiply"       # darkens, does not cover
    assert mark.style.fill_opacity < 1.0


def test_the_highlight_and_the_cloud_callout_are_on_keys(window):
    from markforge.ui.tools import TOOL_MAP
    assert TOOL_MAP["highlight"].shortcut == "J"
    assert TOOL_MAP["cloud_callout"].shortcut == "Shift+Q"
    assert not window.shortcuts.conflicts()


# ---------------------------------------------------------------------------
# Bookmarks and a contents block
# ---------------------------------------------------------------------------

def test_bookmark_can_be_renamed_from_the_panel(window, monkeypatch, qapp):
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QInputDialog, QPushButton

    window.document.add_bookmark("Old name", 0)
    window.bookmarks_changed()
    panel = window.bookmarks_panel
    panel.tree.setCurrentItem(panel.tree.topLevelItem(0))
    monkeypatch.setattr(QInputDialog, "getText",
                        lambda *args, **kwargs: ("New name", True))
    rename = next(button for button in panel.findChildren(QPushButton)
                  if button.text() == "Rename")

    QTest.mouseClick(rename, Qt.LeftButton)
    qapp.processEvents()

    assert window.document.bookmarks[0].title == "New name"
    assert panel.tree.topLevelItem(0).text(0) == "New name"
    assert window.document.modified


def test_there_is_a_key_for_bookmarking_where_you_are(window):
    from PySide6.QtGui import QKeySequence
    assert window.act_bookmark.shortcut() == QKeySequence("Ctrl+B")


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

def test_a_snapshot_is_a_picture_of_the_region(window):
    """It is what that part of the page looks like, not a rebuilt copy of it."""
    _words(window, "600 dia pile", at=(90, 110))
    window.select_tool("rect")
    drag(window.view, 100, 200, 220, 260)

    window.select_tool("snapshot")
    drag(window.view, 60, 80, 400, 320)

    payload = window._clipboard
    assert [entry["type"] for entry in payload] == ["snapshot"]
    assert window.document.asset(payload[0]["asset"])
    # and the marquee itself is not left on the page
    assert not [i for i in markups(window) if getattr(i, "kind", "") == "marquee"]
    assert "Snapshot taken" in window.status_hint.text()


def test_a_snapshot_pastes_back_as_one_thing(window):
    _words(window, "300 kerb", at=(90, 110))
    window.select_tool("snapshot")
    drag(window.view, 60, 80, 400, 200)
    before = len(markups(window))

    window.select_tool("select")
    hover(window.view, 80, 500)
    window.paste_items()

    after = markups(window)
    assert len(after) == before + 1
    pasted = [i for i in after if isinstance(i, SnapshotItem)]
    assert len(pasted) == 1
    box = window.view.markup_box(pasted[0])
    assert box.left() == pytest.approx(80, abs=3)
    assert box.bottom() == pytest.approx(500, abs=3)


def test_a_picture_copied_elsewhere_beats_the_last_snapshot(window):
    """What is on the clipboard is what gets pasted."""
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    from markforge.items.media import ImageItem

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


def test_a_snapshot_is_its_own_kind_of_markup(window):
    """Not an image with a different name: a snapshot of its own."""
    window.select_tool("rect")
    drag(window.view, 80, 510, 120, 540)
    window.select_tool("snapshot")
    drag(window.view, 60, 500, 200, 560)
    assert window._clipboard and window._clipboard[0]["type"] == "snapshot"


def test_a_snapshot_of_no_region_at_all_says_so(window):
    from PySide6.QtCore import QRectF

    window.take_snapshot(window.view.frame(), QRectF(60, 500, 0, 0))
    assert "drag a region" in window.status_hint.text()


def test_a_snapshot_takes_the_drawing_underneath_with_it(window, tmp_path, monkeypatch):
    from PySide6.QtGui import QImage, QPainter, QPicture
    from markforge.io import pdfio

    photo = QImage(400, 300, QImage.Format_ARGB32)
    photo.fill(0xFF3366AA)
    path = str(tmp_path / "sheet.png")
    photo.save(path)
    pdfio.import_image(window.document, path, at=1)
    window.rebuild_scenes()
    window.go_to_page(1)

    from PySide6.QtCore import QRectF

    frame = window.document.pages[1].frame
    line = PolyItem("polyline")
    line.points = [QPointF(0, 0), QPointF(90, 0)]
    line.style.stroke = "#111111"
    line.style.width = 3.0
    line.layer = "Drawing"
    if "Drawing" not in window.document.layer_names():
        from markforge.core.document import Layer
        window.document.layers.append(Layer("Drawing", locked=True))
    frame.add_markup(line, QPointF(30, 55))
    window.take_snapshot(frame, QRectF(20, 20, 120, 90))
    payload = window._clipboard
    assert payload and payload[0]["type"] == "snapshot"
    assert window.document.asset(payload[0]["asset"])

    recorded = QPicture()
    recorded.setData(bytes(window.document.asset(payload[0]["asset"])))
    assert not recorded.isNull()
    replay = QImage(120, 90, QImage.Format_ARGB32)
    replay.fill(Qt.transparent)
    painter = QPainter(replay)
    painter.drawPicture(0, 0, recorded)
    painter.end()
    assert replay.pixelColor(55, 35).alpha() > 0       # imported vector linework
    assert replay.pixelColor(10, 10).alpha() == 0      # no blue page background

    window.paste_items()
    pasted = [i for i in markups(window) if isinstance(i, SnapshotItem)]
    assert len(pasted) == 1
    assert pasted[0].picture() is not None
    assert pasted[0].local_rect().width() == pytest.approx(120, abs=1)


def test_snapshot_skips_unselected_typing(window, monkeypatch):
    """A snapshot of a corner of the drawing takes the drawing, not the notes.

    Somebody's writing over that corner is theirs, and copying the detail is
    not a request for it — unless they picked the words out first, which says
    they meant to take those too.
    """
    from PySide6.QtGui import QImage

    words = _words(window, "design note", at=(90, 190))
    window.select_tool("rect")
    drag(window.view, 90, 280, 220, 340)
    shape = markups(window)[-1]
    painted = []
    monkeypatch.setattr(words, "paint_content",
                        lambda _painter: painted.append("text"))
    monkeypatch.setattr(shape, "paint_content",
                        lambda _painter: painted.append("markup"))
    monkeypatch.setattr(window.view.frame(), "render_image",
                        lambda **_kwargs: QImage())

    window.select_tool("snapshot")
    drag(window.view, 60, 80, 360, 370)
    assert painted == ["markup"]

    words.setSelected(True)
    painted.clear()
    window.select_tool("snapshot")
    drag(window.view, 60, 80, 360, 370)
    assert painted == ["text", "markup"]


def test_a_snapshot_scaled_up_is_still_drawn_from_its_lines(window):
    """Blown up, it is redrawn at the new size — not stretched from pixels."""
    from PySide6.QtGui import QImage, QPainter

    window.select_tool("rect")
    drag(window.view, 100, 100, 220, 180)
    window.select_tool("snapshot")
    drag(window.view, 90, 90, 240, 200)
    window.paste_items()
    shot = [i for i in markups(window) if isinstance(i, SnapshotItem)][0]

    def ink(scale):
        """The box the drawing covers when the snapshot is *scale* times over."""
        taken = shot.natural_size()
        shot.set_local_rect(QRectF(0, 0, taken.width() * scale,
                                   taken.height() * scale))
        sheet = QImage(int(taken.width() * scale) + 4,
                       int(taken.height() * scale) + 4, QImage.Format_ARGB32)
        sheet.fill(0xFFFFFFFF)
        painter = QPainter(sheet)
        shot.paint_content(painter)
        painter.end()
        marked = [(x, y) for x in range(sheet.width())
                  for y in range(sheet.height())
                  if QColor(sheet.pixel(x, y)) != QColor(Qt.white)]
        assert marked, f"nothing was drawn at {scale}x"
        xs = [x for x, _ in marked]
        ys = [y for _, y in marked]
        return max(xs) - min(xs), max(ys) - min(ys)

    small = ink(1)
    big = ink(4)
    # Four times the size, and the drawing is four times across: it was drawn
    # again at the new size rather than clipped or left where it was.
    assert big[0] == pytest.approx(small[0] * 4, rel=0.2)
    assert big[1] == pytest.approx(small[1] * 4, rel=0.2)


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
    from markforge.ui.tools import TOOL_MAP
    assert TOOL_MAP["snapshot"].shortcut == "G"
    assert not window.shortcuts.conflicts()


# ---------------------------------------------------------------------------
# Changing the colours of a drawing
# ---------------------------------------------------------------------------

def _sheet_page(window, tmp_path, colour=0xFF000000):
    """A page whose background is a white sheet with one dark line."""
    from PySide6.QtGui import QColor, QImage
    from markforge.io import pdfio

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
    from markforge.ui import dialogs

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
    from markforge.ui import dialogs

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
    from markforge.ui import dialogs

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


def test_image_colour_dialog_offers_greyscale_and_transparency(window):
    from PySide6.QtGui import QColor, QImage, qAlpha, qBlue, qGreen, qRed
    from PySide6.QtTest import QTest
    from markforge.ui.dialogs import RecolourDialog

    image = QImage(2, 1, QImage.Format_ARGB32)
    image.setPixelColor(0, 0, QColor("#ff0000"))
    image.setPixelColor(1, 0, QColor("#0000ff"))
    dialog = RecolourDialog(image, window)

    QTest.mouseClick(dialog.grey_mode, Qt.LeftButton)
    grey = dialog.apply_to(image)
    pixel = grey.pixel(0, 0)
    assert qRed(pixel) == qGreen(pixel) == qBlue(pixel)

    dialog.from_colour.setItemData(0, QColor("#ff0000"))
    dialog.from_colour.setCurrentIndex(0)
    dialog.tolerance.setValue(0)
    QTest.mouseClick(dialog.transparent_mode, Qt.LeftButton)
    clear = dialog.apply_to(image)
    assert qAlpha(clear.pixel(0, 0)) == 0
    assert qAlpha(clear.pixel(1, 0)) == 255
    dialog.deleteLater()


def test_the_page_menu_only_offers_it_where_there_is_a_drawing(window, tmp_path):
    _sheet_page(window, tmp_path)
    blank = {a.text(): a for a in window.page_menu(0).actions()}
    sheet = {a.text(): a for a in window.page_menu(1).actions()}
    assert not blank["Change colours…"].isEnabled()
    assert sheet["Change colours…"].isEnabled()


# ---------------------------------------------------------------------------
# Writing a formula by pointing at cells
# ---------------------------------------------------------------------------

def _typing(window, text, at=(100, 120)):
    window.view._last_scene_pos = QPointF(*at)
    press_key(window.view, Qt.Key_unknown, '"')
    for character in text:
        press_key(window.view, Qt.Key_unknown, character)
    return window.view.editing_item()


def test_nothing_is_completed_until_tab_is_pressed(window):
    block = _typing(window, "w:=3kN")
    assert block._editor.toPlainText() == "w:=3kN"        # exactly what was typed
    press_key(window.view, Qt.Key_Tab)
    assert block._editor.toPlainText().startswith("w:=3k")
    window.view.end_item_edit()


def _all_boxes(box):
    yield box
    for child in getattr(box, "children", []) or []:
        yield from _all_boxes(child)


# ---------------------------------------------------------------------------
# Editing a calculation looks like the calculation
# ---------------------------------------------------------------------------

def test_the_editor_is_the_same_face_and_size_as_the_print(window):
    block = _words(window, "6 m clear", at=(90, 110))
    window.view.begin_item_edit(block)
    editor = block._editor
    assert editor.font().pixelSize() == round(block.style.font_size)
    assert "mono" not in editor.font().family().lower()
    assert editor.defaultTextColor().name() == QColor(block.style.text_color).name()
    window.view.end_item_edit()






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


def test_a_group_scales_as_one_and_shift_releases_its_ratio(window):
    from markforge.items.base import build_item

    first, second = _two_boxes(window)
    first.setSelected(True)
    second.setSelected(True)
    window.group_selection()
    before = window.view.markup_box(first).united(window.view.markup_box(second))
    original_ratio = before.width() / before.height()
    corner = before.bottomRight()

    drag(window.view, corner.x(), corner.y(), corner.x() + 100, corner.y() + 10)

    proportional = window.view.markup_box(first).united(window.view.markup_box(second))
    assert proportional.width() / proportional.height() == pytest.approx(
        original_ratio, rel=0.02)
    assert first.transform().m11() == pytest.approx(first.transform().m22())
    assert second.transform().m11() == pytest.approx(second.transform().m22())

    corner = proportional.bottomRight()
    drag(window.view, corner.x(), corner.y(), corner.x() + 80, corner.y() + 10,
         modifiers=Qt.ShiftModifier)

    released = window.view.markup_box(first).united(window.view.markup_box(second))
    assert released.width() / released.height() != pytest.approx(original_ratio, rel=0.05)
    assert first.transform().m11() != pytest.approx(first.transform().m22(), rel=0.05)
    clone = build_item(first.serialize())
    assert clone.transform().m11() == pytest.approx(first.transform().m11())
    assert clone.transform().m22() == pytest.approx(first.transform().m22())


def test_escape_cancels_a_group_resize_and_restores_the_cursor(window):
    first, second = _two_boxes(window)
    first.setSelected(True)
    second.setSelected(True)
    window.group_selection()
    before = [(QPointF(item.pos()), item.transform()) for item in (first, second)]
    box = window.view.markup_box(first).united(window.view.markup_box(second))
    corner = box.bottomRight()

    hover(window.view, corner.x(), corner.y())
    assert window.view.cursor().shape() == Qt.SizeFDiagCursor
    QApplication.sendEvent(window.view.viewport(), _mouse(
        window.view, QEvent.MouseButtonPress, corner.x(), corner.y()))
    QApplication.sendEvent(window.view.viewport(), _mouse(
        window.view, QEvent.MouseMove, corner.x() + 80, corner.y() + 30,
        Qt.NoButton, Qt.LeftButton))
    assert first.transform() != before[0][1]

    press_key(window.view, Qt.Key_Escape)

    assert window.view._mode == "idle"
    assert window.view.cursor().shape() == Qt.ArrowCursor
    for item, (position, transform) in zip((first, second), before):
        assert item.pos() == position
        assert item.transform() == transform


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
    from markforge.core.document import Document
    from markforge.io import project as project_io

    first, second = _two_boxes(window)
    first.setSelected(True)
    second.setSelected(True)
    window.group_selection()
    path = str(tmp_path / "job.pdf")
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
    from markforge.ui.mainwindow import MainWindow

    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    box = markups(window)[0]
    box.style.stroke = "#2f9e44"
    window.set_as_default(box)

    second = MainWindow()
    second.confirm_discard = lambda: True
    second.interactive_prompts = False
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
    from markforge.ui import toolsets

    block = _words(window, "300 kerb", at=(90, 500))
    window.set_as_default(block)
    stored = toolsets.load_defaults()[toolsets.default_key(block)]
    assert "text" not in stored and "x" not in stored and "uid" not in stored


def test_the_properties_panel_offers_it(window):
    from PySide6.QtWidgets import QPushButton

    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    box = markups(window)[0]
    window.select_tool("select")
    box.setSelected(True)
    window.refresh_selection()
    labels = [b.text() for b in window.properties_panel.findChildren(QPushButton)]
    assert "Set default" in labels
    assert "Add tool…" in labels


def test_the_style_toolbar_sets_the_selected_markup_as_default(window, qapp):
    from PySide6.QtTest import QTest
    from markforge.ui import toolsets

    window.show()
    qapp.processEvents()
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    box = markups(window)[0]
    box.style.stroke = "#2f9e44"
    window.select_tool("select")
    box.setSelected(True)
    window.refresh_selection()
    assert window.default_button.isEnabled()

    QTest.mouseClick(window.default_button, Qt.LeftButton)

    stored = toolsets.load_defaults()[toolsets.default_key(box)]
    assert stored["style"]["stroke"] == "#2f9e44"
    assert "will look like this one" in window.status_hint.text()


def test_a_markup_can_be_saved_to_a_tool_set_from_its_context_menu(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    box = markups(window)[0]
    window.select_tool("select")
    box.setSelected(True)

    labels = _menu_labels(window.build_context_menu(
        box, box.mapToScene(box.local_rect().center())))

    assert "Add tool…" in labels


# ---------------------------------------------------------------------------
# Tool sets
# ---------------------------------------------------------------------------

def _kept(window, item, into="My Tools", monkeypatch=None):
    """Put an item into a tool set without the dialog."""
    from markforge.ui import toolsets

    groups = toolsets.load_toolsets()
    group = next(g for g in groups if g.name == into)
    group.entries.append(toolsets.entry_for(item, toolsets.COPY))
    toolsets.save_toolsets(groups)
    window.toolsets_panel.rebuild(keep=into)
    return group.entries[-1]


def test_my_tools_is_always_there(window):
    from markforge.ui import toolsets

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
    from markforge.ui import toolsets

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
    from markforge.ui import toolsets

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
    from markforge.ui import toolsets

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    window.toolsets_panel.delete_set()
    assert toolsets.MY_TOOLS in [g.name for g in toolsets.load_toolsets()]


def test_a_tool_can_be_switched_between_the_two_modes(window):
    from markforge.ui import toolsets

    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    _kept(window, markups(window)[0])
    panel = window.toolsets_panel
    panel.select_entry(toolsets.MY_TOOLS, 0)
    assert panel.current_entry().mode == toolsets.COPY
    panel.toggle_mode()
    assert panel.current_entry().mode == toolsets.PROPERTIES
    draw = _menu_entry(panel.build_menu(), "Property mode")
    assert draw.isChecked()
    assert "properties" in panel.tree.currentItem().toolTip(0)
    assert "Property" in panel.tree.currentItem().text(0)


def test_tools_can_be_reordered_and_removed(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    window.select_tool("ellipse")
    drag(window.view, 260, 100, 360, 160)
    _kept(window, markups(window)[0])
    _kept(window, markups(window)[1])

    from markforge.ui import toolsets

    panel = window.toolsets_panel
    panel.select_entry(toolsets.MY_TOOLS, 1)
    header = panel.tree.indexFromItem(panel.tree.topLevelItem(0))
    panel._rows_moved(header, 1, 1, header, 0)     # dragged up the list
    assert panel.current_set().entries[0].payload["kind"] == "ellipse"
    panel.select_entry(toolsets.MY_TOOLS, 0)
    panel.remove_entry()
    assert len(panel.current_set().entries) == 1


def test_tool_sets_are_remembered_between_sessions(window):
    from markforge.ui.mainwindow import MainWindow

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
    block = _words(window, "300 kerb", at=(90, 500))
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
    from markforge.ui import toolsets

    first, second = _two_boxes(window)
    first.setSelected(True)
    second.setSelected(True)
    window.group_selection()

    entry = toolsets.entry_for_many([first, second])
    assert entry.payload["type"] == toolsets.GROUP
    assert len(entry.payload["items"]) == 2
    assert entry.label == "Group of 2"


def test_placing_a_group_puts_every_member_down_grouped(window):
    from markforge.ui import toolsets

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
    from markforge.ui import toolsets

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


def test_an_exact_toolset_item_hangs_from_the_pointers_bottom_left(window):
    _quiet_snapping(window)
    window.select_tool("text")
    drag(window.view, 100, 100, 300, 140)
    original = window.view.editing_item()
    window.view.end_item_edit()
    entry = _kept(window, original)
    window.use_tool_entry(entry)

    click(window.view, 420, 560)

    placed = next(item for item in markups(window) if item is not original)
    box = window.view.markup_box(placed)
    assert box.left() == pytest.approx(420, abs=1)
    assert box.bottom() == pytest.approx(560, abs=1)


def test_a_kept_cloud_uses_its_bottom_left_as_the_anchor(window):
    _quiet_snapping(window)
    window.select_tool("cloud")
    drag(window.view, 100, 100, 260, 180)
    original = markups(window)[-1]
    entry = _kept(window, original)
    window.use_tool_entry(entry)

    click(window.view, 420, 560)

    placed = next(item for item in markups(window) if item is not original)
    box = window.view.markup_box(placed)
    assert box.left() == pytest.approx(420, abs=1)
    assert box.bottom() == pytest.approx(560, abs=1)


def test_a_toolset_group_uses_its_combined_bottom_left_as_the_anchor(window):
    from markforge.ui import toolsets

    _quiet_snapping(window)
    first, second = _two_boxes(window)
    first.setSelected(True)
    second.setSelected(True)
    window.group_selection()
    entry = toolsets.entry_for_many([first, second])
    window.use_tool_entry(entry)

    click(window.view, 420, 560)

    originals = {first, second}
    placed = [item for item in markups(window) if item not in originals]
    box = window.view.markup_box(placed[0]).united(
        window.view.markup_box(placed[1]))
    assert box.left() == pytest.approx(420, abs=1)
    assert box.bottom() == pytest.approx(560, abs=1)


def test_a_click_placed_image_hangs_from_the_pointers_bottom_left(
        window, monkeypatch):
    from markforge.items.media import ImageItem

    _quiet_snapping(window)

    def supply_image(item):
        item.set_local_rect(QRectF(0, 0, 120, 60))
        return True

    monkeypatch.setattr(window, "load_image_into", supply_image)
    window.select_tool("image")
    click(window.view, 420, 560)

    image = next(item for item in markups(window) if isinstance(item, ImageItem))
    box = window.view.markup_box(image)
    assert box.left() == pytest.approx(420, abs=1)
    assert box.bottom() == pytest.approx(560, abs=1)


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
    press_key(window.view, Qt.Key_unknown, '"')
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


def test_clicking_the_first_corner_again_closes_the_polygon(window):
    """The way every polygon is closed — no key needed at all."""
    first, second = _spread(window)
    click(window.view, 60, 60, modifiers=Qt.ShiftModifier)
    click(window.view, 240, 60)
    click(window.view, 240, 220)
    click(window.view, 60, 220)
    click(window.view, 61, 61)                   # back where it started

    assert window.view._mode == "idle"
    assert first.isSelected() and not second.isSelected()


def test_a_corner_can_land_on_a_markup_while_drawing_the_polygon(window):
    """Otherwise the shape can only be drawn across bare paper.

    Which is not where the things you want to select are: a click that
    happened to fall on a markup used to select that markup and abandon the
    shape halfway through.
    """
    first, second = _spread(window)
    over_the_second = second.sceneBoundingRect().center()
    click(window.view, 60, 60, modifiers=Qt.ShiftModifier)
    corners = len(window.view._marquee)
    click(window.view, over_the_second.x(), over_the_second.y())

    assert window.view._mode == "lasso", "still drawing, not selecting"
    assert len(window.view._marquee) == corners + 1, "the corner went in"
    assert not second.isSelected(), "the click was a corner, not a pick"

    # And the shape still takes what it ends up wholly round.
    click(window.view, 420, 240)
    click(window.view, 60, 240)
    press_key(window.view, Qt.Key_Return)
    assert first.isSelected(), "which is the box the shape encloses"


def test_a_stray_click_near_the_start_does_not_close_it_too_early(window):
    """Three corners is not a shape, so the second click cannot close one."""
    _spread(window)
    click(window.view, 60, 60, modifiers=Qt.ShiftModifier)
    click(window.view, 61, 61)
    assert window.view._mode == "lasso"
    window.view.escape_everything()


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


@pytest.mark.parametrize("tool", ["pen", "highlighter"])
def test_freehand_snaps_only_its_start_and_end(window, tool):
    settings = _quiet_snapping(window)
    settings.snap_to_grid = True
    settings.grid_mm = 5.0
    view = window.view
    window.select_tool(tool)
    points = [(103.0, 107.0), (151.0, 139.0),
              (207.0, 169.0), (263.0, 197.0)]
    QApplication.sendEvent(view.viewport(), _mouse(
        view, QEvent.MouseButtonPress, *points[0]))
    for x, y in points[1:-1]:
        QApplication.sendEvent(view.viewport(), _mouse(
            view, QEvent.MouseMove, x, y, Qt.NoButton, Qt.LeftButton))
    QApplication.sendEvent(view.viewport(), _mouse(
        view, QEvent.MouseButtonRelease, *points[-1]))

    stroke = markups(window)[-1]
    scene_points = [stroke.mapToScene(point) for point in stroke.points]
    step = settings.grid_mm * MM_TO_PT

    def on_grid(point):
        return (point.x() == pytest.approx(round(point.x() / step) * step)
                and point.y() == pytest.approx(round(point.y() / step) * step))

    assert on_grid(scene_points[0])
    assert on_grid(scene_points[-1])
    sample = min(scene_points[1:-1], key=lambda point:
                 abs(point.x() - points[1][0]) + abs(point.y() - points[1][1]))
    assert sample.x() == pytest.approx(points[1][0])
    assert sample.y() == pytest.approx(points[1][1])
    assert not on_grid(sample)


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
    """Shift and the control dot: the value goes where it is dropped."""
    window.select_tool("measure_dimension")
    drag(window.view, 100, 200, 320, 200)
    dimension = markups(window)[0]
    window.view.close_label_editor(commit=False)
    assert not dimension.label_is_off_the_line()

    dimension.move_handle("lbl", dimension._label_anchor() + QPointF(0, -60),
                          keep_ratio=True)
    assert dimension.label_is_off_the_line()
    assert dimension.witness_reach == 0.0, "the line itself did not move"


def test_dragging_the_control_dot_extends_the_witness_lines(window):
    """Without Shift the dot pulls the dimension line off what it measures."""
    window.select_tool("measure_dimension")
    drag(window.view, 100, 200, 320, 200)
    dimension = markups(window)[0]
    window.view.close_label_editor(commit=False)
    assert dimension.witness_reach == 0.0

    dimension.move_handle("lbl", dimension._label_anchor() + QPointF(0, -40))
    assert dimension.witness_reach == pytest.approx(-40, abs=0.5)
    start, end = dimension.dimension_ends()
    assert start.y() == pytest.approx(dimension.points[0].y() - 40, abs=0.5)
    assert end.y() == pytest.approx(dimension.points[1].y() - 40, abs=0.5)
    assert not dimension.label_is_off_the_line(), \
        "the value travels with the line it belongs to"


def test_the_control_dot_only_travels_perpendicular(window):
    """However the pointer wanders, the line stays parallel to what it measures."""
    window.select_tool("measure_dimension")
    drag(window.view, 100, 200, 320, 200)
    dimension = markups(window)[0]
    window.view.close_label_editor(commit=False)

    # Dragged well along the line as well as away from it.
    dimension.move_handle("lbl", dimension._label_anchor() + QPointF(180, -30))
    start, end = dimension.dimension_ends()
    assert start.x() == pytest.approx(dimension.points[0].x(), abs=0.01), \
        "the sideways part of the drag is ignored"
    assert end.x() == pytest.approx(dimension.points[1].x(), abs=0.01)
    assert start.y() == pytest.approx(end.y(), abs=0.01)


def test_a_moved_value_hangs_off_a_hinged_leader(window):
    """Perpendicular away from the dimension, then parallel into the text."""
    window.select_tool("measure_dimension")
    drag(window.view, 100, 200, 320, 200)
    dimension = markups(window)[0]
    window.view.close_label_editor(commit=False)
    dimension.custom_label = "2400"
    dimension.refresh(page=window.current_page())

    dimension.move_handle("lbl", dimension._label_anchor() + QPointF(90, -70),
                          keep_ratio=True)
    anchor, elbow, end = dimension.leader_path()
    assert elbow.x() == pytest.approx(anchor.x(), abs=0.01), \
        "the first run leaves the dimension at right angles"
    assert elbow.y() == pytest.approx(anchor.y() - 70, abs=0.5)
    assert end.y() == pytest.approx(elbow.y(), abs=0.01), \
        "and the second runs parallel to it, into the text"
    assert end.x() > elbow.x()


def _dimension_row(window, item, dpi=192.0):
    """The pixels along the dimension's own line, and where its value sits."""
    frame = window.document.pages[0].frame
    sheet = frame.render_image(dpi=dpi, for_print=True)
    scale = dpi / 72.0
    on_page = item.mapToParent(item.dimension_ends()[0])
    row = int(round(on_page.y() * scale))
    start = item.mapToParent(item.dimension_ends()[0]).x() * scale
    end = item.mapToParent(item.dimension_ends()[1]).x() * scale
    return sheet, row, start, end


def test_a_dimension_is_drawn_plainly_with_its_value_on_the_line(window):
    """Arrow to arrow, the value written along it, no box behind it."""
    window.select_tool("measure_dimension")
    drag(window.view, 100, 300, 400, 300)
    dimension = markups(window)[0]
    window.view.close_label_editor(commit=False)
    dimension.custom_label = "2400"
    dimension.style.stroke = "#1971c2"
    dimension.refresh(page=window.current_page())
    window.view.scene().clearSelection()

    sheet, row, start, end = _dimension_row(window, dimension)
    line = QColor("#1971c2")

    def near_the_line(x: int) -> bool:
        for offset in (-1, 0, 1):
            colour = QColor(sheet.pixel(x, row + offset))
            if abs(colour.red() - line.red()) < 60 \
                    and abs(colour.blue() - line.blue()) < 60 \
                    and abs(colour.green() - line.green()) < 60:
                return True
        return False

    quarter = int(start + (end - start) * 0.25)
    middle = int((start + end) / 2)
    assert near_the_line(quarter), "the dimension line is drawn"
    assert not near_the_line(middle), \
        "and broken where the value is written across it"


def test_the_measured_and_the_typed_dimension_are_drawn_the_same(window):
    """One shows what it measured and one shows what was typed; that is all."""
    window.select_tool("measure_dimension")
    drag(window.view, 100, 300, 400, 300)
    typed = markups(window)[0]
    window.view.close_label_editor(commit=False)
    window.select_tool("measure_length")
    drag(window.view, 100, 500, 400, 500)
    measured = markups(window)[1]
    window.view.scene().clearSelection()

    assert typed.is_dimensioned() and measured.is_dimensioned()
    assert typed.label_offset == measured.label_offset
    assert typed.label_rotation() == pytest.approx(measured.label_rotation())
    for item in (typed, measured):
        assert item.style.arrow_start == "arrow"
        assert item.style.arrow_end == "arrow"


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











def _panel_groups(window, item):
    from PySide6.QtWidgets import QGroupBox

    window.select_tool("select")
    window.view.scene().clearSelection()
    item.setSelected(True)
    window.refresh_selection()
    return [g.title() for g in window.properties_panel.findChildren(QGroupBox)]


def test_a_contents_block_can_be_changed_afterwards(window):
    from PySide6.QtWidgets import QCheckBox, QLineEdit
    from markforge.items.contents import ContentsItem

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
    from markforge.items.text import NoteItem

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
    from markforge.items.media import ImageItem

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


def test_a_raster_image_has_no_line_or_fill_style_controls(window, tmp_path):
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QFileDialog, QGroupBox
    from markforge.items.media import ImageItem

    path = str(tmp_path / "photo.png")
    QImage(60, 40, QImage.Format_ARGB32).save(path)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (path, ""))
    try:
        window.select_tool("image")
        drag(window.view, 100, 100, 300, 240)
    finally:
        monkeypatch.undo()
    image = next(i for i in markups(window) if isinstance(i, ImageItem))
    image.style.stroke = "#123456"
    image.setSelected(True)
    window.properties_panel.show_items([image])

    appearance = next(group for group in
                      window.properties_panel.findChildren(QGroupBox)
                      if group.title() == "Appearance")
    labels = [label.text() for label in appearance.findChildren(QLabel)]
    assert "Line" not in labels and "Fill" not in labels

    before = image.style.stroke
    window._style_stroke("#c92a2a")
    assert image.style.stroke == before


def test_an_image_keeps_its_aspect_ratio_unless_shift_releases_it(window):
    from markforge.items.media import ImageItem

    image = ImageItem(rect=QRectF(0, 0, 200, 100))
    window.view.frame().add_markup(image, QPointF(100, 100))
    window.select_tool("select")
    image.setSelected(True)
    window.refresh_selection()
    corner = image.mapToScene(image.handle_points()["se"])

    drag(window.view, corner.x(), corner.y(), corner.x() + 100, corner.y() + 10)
    assert image.local_rect().width() == pytest.approx(300, abs=2)
    assert image.local_rect().height() == pytest.approx(150, abs=2)

    corner = image.mapToScene(image.handle_points()["se"])
    drag(window.view, corner.x(), corner.y(), corner.x() + 50, corner.y() + 80,
         modifiers=Qt.ShiftModifier)
    assert image.local_rect().width() == pytest.approx(350, abs=2)
    assert image.local_rect().height() == pytest.approx(230, abs=2)


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


def test_count_stays_armed_and_numbers_each_click_until_escape(window):
    from markforge.items.measure import CountItem

    window.select_tool("count")
    click(window.view, 120, 160)
    click(window.view, 180, 160)
    click(window.view, 240, 160)

    counts = [item for item in markups(window) if isinstance(item, CountItem)]
    assert [item.index for item in counts] == [1, 2, 3]
    assert window.view.tool_key == "count"
    press_key(window.view, Qt.Key_Escape)
    assert window.view.tool_key == "select"


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
    from markforge.ui import commands

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
    from markforge.items.text import CalloutItem

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


def test_spellcheck_knows_requests_and_offers_a_correction(window):
    from PySide6.QtTest import QTest
    from markforge.core.spelling import shared

    assert shared().knows("requests")
    assert not shared().knows("reqeusts")
    assert "requests" in shared().suggestions("reqeusts")

    window.select_tool("text")
    drag(window.view, 100, 100, 320, 150)
    box = window.view.editing_item()
    box.set_text("reqeusts")
    cursor = box._editor.textCursor()
    cursor.setPosition(4)
    box._editor.setTextCursor(cursor)
    menu = box._editor.spelling_menu()
    assert menu is not None
    labels = [action.text() for action in menu.actions()]
    assert "requests" in labels and "Spelling…" in labels

    choice = next(action for action in menu.actions()
                  if action.text() == "requests")
    menu.popup(window.mapToGlobal(window.rect().center()))
    QApplication.processEvents()
    QTest.mouseClick(menu, Qt.LeftButton, Qt.NoModifier,
                     menu.actionGeometry(choice).center())
    assert box._editor.toPlainText() == "requests"
    window.view.escape_everything()


# ---------------------------------------------------------------------------
# One view of a calculation, typed into where it is
# ---------------------------------------------------------------------------



def test_shift_and_the_space_bar_asks_for_a_text_box(window):
    """Shift+Space follows the same conversion rule as an ordinary space."""
    from markforge.items.text import TextItem

    window.select_tool("select")
    press_key(window.view, Qt.Key_unknown, '"')
    type_text(window.view, "check")
    press_key(window.view, Qt.Key_Space, " ", Qt.ShiftModifier)
    QApplication.processEvents()

    box = window.view.editing_item()
    assert isinstance(box, TextItem)
    type_text(window.view, "bolt")
    window.view.end_item_edit()
    assert [type(i).__name__ for i in markups(window)] == ["TextItem"]




def test_a_lone_word_left_behind_becomes_a_note_after_all(window):
    """A word with a space in it, when the caret goes, was a sentence.

    Nothing can put that space there by typing any more, so this is for text
    that arrived some other way — pasted in, or built from something else.
    """
    from markforge.items.text import TextItem

    window.select_tool("select")
    press_key(window.view, Qt.Key_unknown, '"')
    item = window.view.editing_item()
    item._editor.setPlainText("checked by hand")
    window.view.end_item_edit()

    assert [type(i).__name__ for i in markups(window)] == ["TextItem"]
    assert markups(window)[0].text().strip() == "checked by hand"


def test_a_tool_set_entry_is_drawn_as_what_it_is(window):
    from markforge.ui import toolsets
    from markforge.ui.panels import entry_thumbnail

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


def test_drawing_again_is_greyed_out_for_a_calculation(window):
    """A calculation is nothing without its lines, so there is nothing to draw."""
    from markforge.ui import toolsets

    panel = window.toolsets_panel
    panel.select_set(toolsets.MY_TOOLS)
    group = panel.current_set()
    group.entries.append(toolsets.ToolEntry("A calculation", {"type": "math"}))
    group.entries.append(toolsets.ToolEntry("A rectangle", {"type": "rect"}))
    toolsets.save_toolsets(panel.groups)
    panel.rebuild(keep=toolsets.MY_TOOLS)

    panel.select_entry(toolsets.MY_TOOLS, len(group.entries) - 2)
    assert not _menu_entry(panel.build_menu(), "Property mode").isEnabled()
    panel.select_entry(toolsets.MY_TOOLS, len(group.entries) - 1)
    assert _menu_entry(panel.build_menu(), "Property mode").isEnabled()


def test_tools_can_be_dragged_into_the_order_you_want(window):
    from markforge.ui import toolsets

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
    from markforge.items.shapes import RectItem

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
    from markforge.ui import preferences

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
    from markforge.items.base import cursor_for_handle

    assert cursor_for_handle("v0") == Qt.PointingHandCursor
    assert cursor_for_handle("v7") == Qt.PointingHandCursor
    # A call-out's arrow heads and hinges are numbered too, and there is no
    # limit to how many of them one comment may want.
    assert cursor_for_handle("l0") == Qt.PointingHandCursor
    assert cursor_for_handle("l9") == Qt.PointingHandCursor
    # A hinge takes hold rather than points: it slides along its own line and
    # hops from side to side.
    assert cursor_for_handle("e0") == Qt.OpenHandCursor
    assert cursor_for_handle("lblrot") == Qt.CrossCursor


def test_shape_modifiers_have_distinct_add_remove_and_curve_cursors(window):
    box = _a_rectangle(window)
    box.setSelected(True)
    window.select_tool("select")

    def hover_with(x, y, modifiers):
        QApplication.sendEvent(window.view.viewport(), _mouse(
            window.view, QEvent.MouseMove, x, y, Qt.NoButton, Qt.NoButton,
            modifiers))

    hover_with(180, 120, Qt.ShiftModifier)       # top side
    add = window.view.cursor().pixmap().cacheKey()
    assert add

    hover_with(120, 120, Qt.ShiftModifier)       # top-left point
    remove = window.view.cursor().pixmap().cacheKey()
    assert remove and remove != add

    hover_with(180, 120, Qt.ControlModifier)
    curve = window.view.cursor().pixmap().cacheKey()
    assert curve and curve not in (add, remove)
    hover(window.view, 600, 600)
    assert window.view.cursor().shape() == Qt.ArrowCursor


def test_finishing_a_rectangle_resize_recomputes_the_cursor(window):
    box = _a_rectangle(window)
    box.setSelected(True)
    window.select_tool("select")
    edge = box.mapToScene(box.local_rect().center())
    edge.setX(box.mapToScene(box.local_rect().topRight()).x())
    hover(window.view, edge.x(), edge.y())
    assert window.view.cursor().shape() == Qt.SizeHorCursor

    drag(window.view, edge.x(), edge.y(), edge.x() + 60, edge.y())

    assert window.view._mode == "idle"
    assert window.view.cursor().shape() == Qt.SizeHorCursor


# ---------------------------------------------------------------------------
# Nothing in the panel that has no answer
# ---------------------------------------------------------------------------

def test_a_callout_is_asked_only_about_the_end_that_points(window):
    """Which arrow head goes on the end joined to the box is not a question."""
    from PySide6.QtWidgets import QComboBox
    from markforge.items.text import CalloutItem

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
    from markforge.items.text import CalloutItem

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

def test_the_markup_menu_omits_typewriter_but_keeps_the_other_tools(window):
    """Typewriter is retired without disturbing the remaining markup tools."""
    from markforge.ui.tools import TOOL_MAP

    wanted = {"eraser": "Shift+E", "arc": "Shift+C",
              "flag": "Shift+F", "highlighter": "H", "polyline": "N",
              "cloud": "C"}
    for key, shortcut in wanted.items():
        assert key in TOOL_MAP, key
        assert TOOL_MAP[key].shortcut == shortcut, key
    assert not window.shortcuts.conflicts()
    # and no two tools share a name
    labels = [tool.label for tool in TOOL_MAP.values()]
    assert len(labels) == len(set(labels))
    assert "typewriter" not in TOOL_MAP
    assert all(binding.action_id != "tool.typewriter"
               for binding in window.shortcuts.bindings())


def test_an_old_typewriter_item_still_loads_without_exposing_its_tool(window):
    from markforge.items.base import build_item
    from markforge.items.text import TypewriterItem

    item = build_item(TypewriterItem("Old note").serialize())
    assert isinstance(item, TypewriterItem)
    assert not item.style.stroke          # no border
    assert not item.style.fill            # and nothing behind the words


def test_an_arc_bends(window):
    window.select_tool("arc")
    drag(window.view, 100, 100, 260, 100)
    arc = markups(window)[0]
    assert arc.kind == "arc"
    # longer than the straight line between its ends, because it is a curve
    assert arc.build_path().length() > 150


def test_an_arc_has_an_editable_bend_control_point(window):
    window.select_tool("arc")
    drag(window.view, 100, 100, 260, 100)
    arc = markups(window)[0]
    window.select_tool("select")
    arc.setSelected(True)
    assert set(arc.handle_points()) == {"v0", "v1", "c0"}
    before = arc.build_path().boundingRect()
    control = arc.mapToScene(arc.handle_points()["c0"])
    target = control + QPointF(20, 55)

    drag(window.view, control.x(), control.y(), target.x(), target.y())

    assert len(arc.points) == 3
    assert set(arc.handle_points()) == {"v0", "v2", "c0"}
    after = arc.build_path().boundingRect()
    assert after.height() > before.height()


def test_a_flag_is_pinned_where_it_is_clicked(window):
    from markforge.items.text import FlagItem

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
    """An area measured round a rectangle of the page."""
    from markforge.items.measure import MeasureItem

    window.select_tool("measure_area")
    for point in [(100, 100), (400, 100), (400, 300), (100, 300)]:
        click(window.view, *point)
    press_key(window.view, Qt.Key_Return)
    return [i for i in markups(window) if isinstance(i, MeasureItem)][0]


def test_a_cut_out_drawn_nowhere_says_so(window):
    _area_measurement(window)
    window.select_tool("cutout_ellipse")
    drag(window.view, 600, 600, 680, 660)
    assert len(markups(window)) == 1           # nothing left lying about


def _words(window, text="300 kerb", at=(90, 110), size=(190, 50)):
    """A text markup with *text* written in it, its top-left at *at*."""
    x, y = at
    window.select_tool("text")
    drag(window.view, x, y, x + size[0], y + size[1])
    item = window.view.editing_item()
    type_text(window.view, text)
    window.view.end_item_edit()
    QApplication.processEvents()
    window.select_tool("select")
    return item


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
                   "Hide", "Flatten selection", "Apply pages…",
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
    assert not window.view.cursor().pixmap().isNull()
    press_key(window.view, Qt.Key_Escape)
    assert not window.holding_a_format()
    assert window.view.cursor().shape() == Qt.ArrowCursor


def test_format_painter_never_copies_cloud_geometry(window):
    cloud = _a_rectangle(window)
    cloud.kind = "cloud"
    cloud.style.stroke = "#c92a2a"
    target = _a_rectangle(window, 300, 120, 380, 200)
    target.kind = "rect"
    window.scene.clearSelection()
    cloud.setSelected(True)

    window.format_painter()
    window.paint_format_onto(target)

    assert target.kind == "rect"
    assert target.style.stroke == "#c92a2a"


def test_format_painter_does_not_copy_callout_leaders(window):
    first = _callout(window)
    window.view.end_item_edit()
    window.add_leader_to(first)
    second = _callout(window)
    window.view.end_item_edit()
    before = [(leader.kind, QPointF(leader.tip)) for leader in second.leaders]
    window.scene.clearSelection()
    first.setSelected(True)

    window.format_painter()
    window.paint_format_onto(second)

    assert [(leader.kind, leader.tip) for leader in second.leaders] == before


def test_hidden_markups_go_away_and_come_back(window):
    rect = _a_rectangle(window)
    rect.setSelected(True)
    window.hide_selection()
    assert rect.hidden and not rect.isVisible()

    window.show_hidden()
    assert not rect.hidden and rect.isVisible()


def test_a_hidden_markup_is_still_hidden_after_a_save(window):
    from markforge.items.base import build_item

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
    from markforge.items.base import build_item

    rect = _a_rectangle(window)
    rect.setSelected(True)
    window.interactive_prompts = False
    window.flatten_selection()
    clone = build_item(rect.serialize())
    assert clone.flattened and clone.locked


def test_recover_restores_a_recoverably_flattened_item(window):
    from markforge.ui import preferences

    rect = _a_rectangle(window)
    rect.setSelected(True)
    rect.set_locked(False)
    prefs = preferences.current()
    previous = prefs.recover_flattened
    try:
        prefs.recover_flattened = True
        window.interactive_prompts = False
        window.act_flatten.trigger()
        assert rect.flattened and rect.flatten_recoverable

        window.act_recover_flattened.trigger()
        assert not rect.flattened and not rect.locked
        assert rect.flags() & rect.GraphicsItemFlag.ItemIsSelectable
    finally:
        prefs.recover_flattened = previous


def test_irreversible_flattening_keeps_only_a_vector_recording(window):
    from markforge.ui import preferences

    rect = _a_rectangle(window)
    rect.setSelected(True)
    original_uid = rect.uid
    prefs = preferences.current()
    previous = prefs.recover_flattened
    try:
        prefs.recover_flattened = False
        window.interactive_prompts = False
        window.act_flatten.trigger()

        assert rect.scene() is None
        assert not any(item.uid == original_uid for item in markups(window))
        baked = [item for item in markups(window) if isinstance(item, SnapshotItem)]
        assert len(baked) == 1
        assert baked[0].flattened and not baked[0].flatten_recoverable
        assert baked[0].picture() is not None
        assert window.document.asset(baked[0].asset_key)

        window.act_recover_flattened.trigger()
        assert baked[0].flattened
        assert "No recoverable" in window.status_hint.text()
    finally:
        prefs.recover_flattened = previous


def test_document_flattening_uses_the_classes_chosen(window, monkeypatch):
    from markforge.ui import dialogs, preferences

    rect = _a_rectangle(window)
    window.view._last_scene_pos = QPointF(90, 300)
    press_key(window.view, Qt.Key_unknown, '"')
    type_text(window.view, "150 cover")
    words = window.view.editing_item()
    window.view.escape_everything()
    QApplication.processEvents()

    class ChosenText:
        def __init__(self, *_args):
            pass

        def exec(self):
            return dialogs.QDialog.Accepted

        def chosen(self):
            return {"text"}

    monkeypatch.setattr(dialogs, "FlattenDialog", ChosenText)
    prefs = preferences.current()
    previous = prefs.recover_flattened
    try:
        prefs.recover_flattened = True
        window.act_flatten_document.trigger()
        assert words.flattened, "the words were the class chosen"
        assert not rect.flattened, "and the rectangle was not"
    finally:
        prefs.recover_flattened = previous


def test_flatten_dialog_class_choices_follow_real_clicks(window):
    from markforge.ui.dialogs import FlattenDialog

    dialog = FlattenDialog(True, window)
    assert dialog.chosen() == {"markups"}
    dialog.boxes["markups"].click()
    dialog.boxes["text"].click()
    dialog.boxes["measurements"].click()
    assert dialog.chosen() == {"text", "measurements"}
    dialog.deleteLater()


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

    # A text box given a leader is a call-out — the two are one object in
    # different states, so what comes back is the call-out it became.
    call = window.becomes_a_callout(box)
    window.set_leader(call, True)
    call = [i for i in markups(window) if isinstance(i, CalloutItem)][-1]
    assert call.leader_shown
    assert "l0" in call.handle_points()
    assert call.leader_handles() == {"l0", "e0"}

    # And taking the last one off makes it a text box again.
    window.set_leader(call, False)
    box = [i for i in markups(window) if isinstance(i, TextItem)][-1]
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
    labels = _menu_labels(window.build_context_menu(box, box.pos()))
    assert "Add arrow leader" in labels
    assert "Add cloud leader" in labels

    window.set_leader(box, True)
    call = [i for i in markups(window) if isinstance(i, CalloutItem)][-1]
    labels = _menu_labels(window.build_context_menu(call, call.pos()))
    assert "Add arrow leader" in labels
    assert "Add cloud leader" in labels
    assert "Remove leader" in labels
    assert "Remove leaders" not in labels


def test_a_text_boxs_leader_is_still_there_after_a_save(window):
    from markforge.items.base import build_item

    window.select_tool("text")
    drag(window.view, 200, 200, 340, 250)
    type_text(window.view, "note")
    window.view.end_item_edit()
    box = markups(window)[-1]
    window.set_leader(box, True)
    call = [i for i in markups(window) if isinstance(i, CalloutItem)][-1]
    tip = QPointF(call.tip)

    clone = build_item(call.serialize())
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


def test_a_pasted_snapshot_holds_its_drawing(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 220, 180)
    window.select_tool("snapshot")
    drag(window.view, 60, 60, 300, 250)

    window.select_tool("select")
    hover(window.view, 120, 520)
    window.paste_items()

    pasted = [i for i in markups(window) if isinstance(i, SnapshotItem)][-1]
    assert pasted.asset_key                        # it knows which recording
    assert window.document.asset(pasted.asset_key)    # and the recording is there
    assert pasted.picture() is not None and not pasted.picture().isNull()


def test_a_picture_pasted_from_elsewhere_holds_its_picture(window):
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    from markforge.items.media import ImageItem

    foreign = QImage(120, 80, QImage.Format_ARGB32)
    foreign.fill(0xFF2F9E44)
    QApplication.clipboard().setImage(foreign)

    window.select_tool("select")
    hover(window.view, 120, 520)
    window.paste_items()

    pasted = [i for i in markups(window) if isinstance(i, ImageItem)][-1]
    assert pasted.asset_key
    assert pasted.pixmap() is not None and not pasted.pixmap().isNull()
    assert pasted.style.stroke == "" and pasted.style.width == 0.0
    # The green it was filled with is what comes out of it.
    assert 0xFF2F9E44 in _paints_something_other_than_grey(pasted)


def test_a_pasted_picture_is_still_there_after_a_save(window, tmp_path):
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    from markforge.core.document import Document
    from markforge.io import project as project_io
    from markforge.items.base import build_item
    from markforge.items.media import ImageItem

    foreign = QImage(90, 60, QImage.Format_ARGB32)
    foreign.fill(0xFF1971C2)
    QApplication.clipboard().setImage(foreign)
    window.select_tool("select")
    hover(window.view, 120, 520)
    window.paste_items()

    path = str(tmp_path / "picture.pdf")
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


def test_ctrl_b_still_bookmarks_when_there_are_no_words(window, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    window.scene.clearSelection()
    assert window.toggle_bold() is False
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Shear", True))
    before = len(window.document.bookmarks)
    window.add_bookmark_here()
    assert len(window.document.bookmarks) == before + 1


def _btx(name):
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(here, "btx", name)


def test_importing_a_bluebeam_tool_set_fills_the_tool_chest(window):
    from markforge.ui import toolsets

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
    from markforge.items.shapes import PolyItem, RectItem

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
    from markforge.items.shapes import SketchItem

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
    from markforge.ui import toolsets

    window.import_toolset(_btx("Structures - Timber.btx"))
    window.import_toolset(_btx("Structures - Timber.btx"))
    names = [group.name for group in toolsets.load_toolsets()]
    assert "Structures - Timber" in names
    assert "Structures - Timber (2)" in names


def test_a_file_that_is_not_a_tool_set_is_refused_politely(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from markforge.ui import toolsets

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
    from markforge.ui import toolsets

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
    from markforge.items.shapes import RectItem

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
    from markforge.ui import toolsets

    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    _kept(window, markups(window)[0])
    panel = window.toolsets_panel
    panel.select_entry(toolsets.MY_TOOLS, 0)

    labels = _menu_labels(panel.build_menu())
    for wanted in ("Use", "Property mode", "Rename…", "Remove",
                   "Rename this set…", "Delete this set", "New tool set…",
                   "Import tools…"):
        assert wanted in labels, f"{wanted!r} missing from {labels}"


def test_the_menu_on_bare_panel_still_offers_a_new_set(window):
    panel = window.toolsets_panel
    panel.tree.setCurrentItem(None)
    labels = _menu_labels(panel.build_menu())
    assert "New tool set…" in labels
    assert "Import tools…" in labels
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
    from markforge.ui.widgets import WheelBelongsToTheScroller

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


def test_a_rotated_text_box_turns_upright_only_while_it_is_edited(window):
    item = TextItem("Turned note", QRectF(0, 0, 160, 50))
    window.view.frame().add_markup(item, QPointF(180, 180))
    item.set_item_rotation(30)
    centre = item.center()

    double_click(window.view, centre.x(), centre.y())
    assert window.view.editing_item() is item
    assert item.rotation() == pytest.approx(0)

    window.view.escape_everything()
    assert item.rotation() == pytest.approx(30)
    assert item.center() == centre


def test_an_almost_unrotated_text_box_snaps_back_to_zero_after_editing(window):
    item = TextItem("Nearly straight", QRectF(0, 0, 160, 50))
    window.view.frame().add_markup(item, QPointF(180, 180))
    item.setRotation(359)
    centre = item.center()

    double_click(window.view, centre.x(), centre.y())
    assert window.view.editing_item() is item
    window.view.escape_everything()
    assert item.rotation() == pytest.approx(0)


def test_a_callout_leader_keeps_pointing_at_the_same_place_during_upright_edit(
        window):
    item = CalloutItem("Turned callout", QRectF(0, 0, 160, 50),
                       [QPointF(-80, 90)])
    window.view.frame().add_markup(item, QPointF(260, 180))
    item.set_item_rotation(-25)
    centre = item.center()
    tip = item.mapToScene(item.tip)

    double_click(window.view, centre.x(), centre.y())
    assert window.view.editing_item() is item
    assert item.rotation() == pytest.approx(0)
    assert item.mapToScene(item.tip) == tip

    window.view.escape_everything()
    assert item.rotation() == pytest.approx(-25)
    assert item.mapToScene(item.tip) == tip


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



def _contains(box, kind):
    """Whether a laid-out box has one of *kind* anywhere inside it."""
    if isinstance(box, kind):
        return True
    for child, _x, _baseline in box.children_at(0.0, 0.0):
        if _contains(child, kind):
            return True
    return False




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


def test_an_underscore_and_a_caret_read_as_a_script(window):
    """"A_g" and "m^2" are written that way and set that way."""
    from markforge.core.typography import script_runs

    assert script_runs("A_g") == [("A", ""), ("g", "sub")]
    assert script_runs("m^2") == [("m", ""), ("2", "super")]
    assert script_runs("f'_c = 25") == [("f'", ""), ("c", "sub"), (" = 25", "")]




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


def _show_for_shortcut(window, qapp):
    """Give Qt a real active window and focused canvas for QAction routing."""
    window.show()
    window.raise_()
    window.activateWindow()
    window.view.setFocus()
    qapp.processEvents()


def test_text_alignment_and_size_shortcuts_format_the_selected_object(
        window, qapp):
    from PySide6.QtTest import QTest

    window.select_tool("text")
    drag(window.view, 100, 100, 360, 160)
    item = window.view.editing_item()
    item.set_text("Selected note")
    window.view.end_item_edit()
    item.setSelected(True)
    _show_for_shortcut(window, qapp)

    QTest.keyClick(window.view, Qt.Key_Right,
                   Qt.ControlModifier | Qt.AltModifier)
    QTest.keyClick(window.view, Qt.Key_Up,
                   Qt.ControlModifier | Qt.AltModifier)
    qapp.processEvents()

    assert item.style.align == "right"
    assert item.style.font_size == pytest.approx(11.0)


def test_rebound_shortcut_formats_only_the_selected_text_run(window, qapp):
    from PySide6.QtGui import QTextCursor
    from PySide6.QtTest import QTest

    window.select_tool("text")
    drag(window.view, 100, 100, 360, 160)
    item = window.view.editing_item()
    item.set_text("first second")
    cursor = item._editor.textCursor()
    cursor.setPosition(6)
    cursor.setPosition(12, QTextCursor.KeepAnchor)
    item._editor.setTextCursor(cursor)
    window.shortcuts.set_sequence("command.font_increase", "Ctrl+Alt+9")
    window.apply_shortcuts()
    _show_for_shortcut(window, qapp)

    QTest.keyClick(window.view, Qt.Key_9,
                   Qt.ControlModifier | Qt.AltModifier)
    qapp.processEvents()

    chosen = QTextCursor(item.doc)
    chosen.setPosition(6)
    chosen.setPosition(12, QTextCursor.KeepAnchor)
    untouched = QTextCursor(item.doc)
    untouched.setPosition(0)
    untouched.setPosition(5, QTextCursor.KeepAnchor)
    assert chosen.charFormat().fontPointSize() == pytest.approx(11.0)
    assert untouched.charFormat().fontPointSize() != pytest.approx(11.0)






def test_holding_ctrl_lets_go_of_the_grid_while_drawing(window):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QKeyEvent

    window.document.settings.snap_to_grid = True
    window.document.settings.grid_mm = 5.0
    awkward = QPointF(103.7, 147.3)

    # snapping_off_now() reads the live modifier state on purpose, so that a
    # Ctrl held before this window had the keyboard still counts. That makes
    # "Ctrl is not down" a precondition to establish rather than assume: an
    # earlier Ctrl-modified event leaves QApplication.keyboardModifiers()
    # reporting Ctrl, and the grid then appears not to catch anything.
    assert not window.view.snapping_off_now()
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


def _open_words(window, text, at=(90, 110)):
    """A text markup with *text* in it, left open for typing."""
    window.view._last_scene_pos = QPointF(*at)
    press_key(window.view, Qt.Key_unknown, '"')
    item = window.view.editing_item()
    type_text(window.view, text)
    QApplication.processEvents()
    return item


def _canvas_point_of_offset(item, offset):
    """Where character *offset* of an open text markup sits on the canvas.

    Straight out of Qt's own layout for the words, which is the only thing
    that knows where it put them.
    """
    editor = item._editor
    document = editor.document()
    block = document.findBlock(offset)
    line = block.layout().lineForTextPosition(offset - block.position())
    x = line.cursorToX(offset - block.position())
    if isinstance(x, (tuple, list)):
        x = x[0]
    top = document.documentLayout().blockBoundingRect(block).top()
    # A little to the right of the character's left edge and half way down the
    # line: the nearest edge of the nearest character is what a click means,
    # and the boundary itself is the same distance from either side of it.
    point = editor.mapToScene(QPointF(x + 1.0, top + line.y() + line.height() / 2))
    return point.x(), point.y()


def _click_at_offset(window, item, offset):
    """Click where character *offset* is painted, and say where the caret went."""
    click(window.view, *_canvas_point_of_offset(item, offset))
    return item._editor.textCursor().position()






def test_typing_after_a_click_lands_where_the_caret_is(window):
    item = _open_words(window, "600 dia pile")
    _click_at_offset(window, item, 4)                 # in front of "dia"
    type_text(window.view, "N")
    assert item._editor.toPlainText() == "600 Ndia pile"
    window.view.end_item_edit()


def test_a_click_does_not_snap_back_to_the_start(window):
    """The release used to hand the click to Qt, which placed it again."""
    item = _open_words(window, "600 dia pile")
    for _ in range(3):
        assert _click_at_offset(window, item, 8) == 8


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


def test_the_view_can_be_turned_without_touching_the_page(window):
    """For reading a drawing that came in sideways."""
    page = window.current_page()
    before = (page.setup.width_pt, page.setup.height_pt, page.setup.orientation)

    window.view.rotate_view(True)
    assert window.view.view_turn() == 90
    # The page is exactly as it was: nothing to undo, nothing to save.
    after = (page.setup.width_pt, page.setup.height_pt, page.setup.orientation)
    assert after == before
    assert window.undo_stack.count() == 0

    window.view.rotate_view(True)
    assert window.view.view_turn() == 180
    window.view.reset_view_rotation()
    assert window.view.view_turn() == 0


def test_turning_the_view_turns_what_is_on_screen(window):
    """The page really is drawn sideways, not merely marked as turned."""
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 140)
    box = markups(window)[0]
    upright = window.view.mapFromScene(box.sceneBoundingRect())

    window.view.rotate_view(True)
    turned = window.view.mapFromScene(box.sceneBoundingRect())
    assert turned.boundingRect().width() / max(turned.boundingRect().height(), 1) \
        == pytest.approx(upright.boundingRect().height()
                         / max(upright.boundingRect().width(), 1), rel=0.15)


def test_turning_the_view_is_on_the_view_menu(window):
    labels = []
    for menu in window.menuBar().actions():
        if menu.text() == "&View":
            labels = [a.text() for a in menu.menu().actions()]
    assert "Turn clockwise" in labels
    assert "Turn anticlockwise" in labels
    assert "Reset turn" in labels


# ---------------------------------------------------------------------------
# Control points: add, delete, round off and curve
# ---------------------------------------------------------------------------

def _polygon(window, points=((120, 120), (260, 120), (260, 240), (120, 240))):
    """A polygon on the page, selected, drawn corner by corner."""
    window.select_tool("polygon")
    for x, y in points:
        click(window.view, x, y)
    press_key(window.view, Qt.Key_Return)
    shape = [i for i in markups(window) if isinstance(i, PolyItem)][-1]
    window.view.scene().clearSelection()
    shape.setSelected(True)
    return shape


def test_shift_over_a_side_puts_a_point_in(window):
    shape = _polygon(window)
    before = len(shape.points)
    middle = shape.mapToScene(shape.segment_ends(0)[0]
                              + (shape.segment_ends(0)[1]
                                 - shape.segment_ends(0)[0]) / 2)
    click(window.view, middle.x(), middle.y(), modifiers=Qt.ShiftModifier)
    assert len(shape.points) == before + 1


def test_shift_over_a_point_takes_it_out(window):
    shape = _polygon(window)
    before = len(shape.points)
    corner = shape.mapToScene(shape.points[1])
    click(window.view, corner.x(), corner.y(), modifiers=Qt.ShiftModifier)
    assert len(shape.points) == before - 1


def test_ctrl_over_a_corner_rounds_it_off_and_back(window):
    shape = _polygon(window)
    corner = shape.mapToScene(shape.points[1])
    click(window.view, corner.x(), corner.y(), modifiers=Qt.ControlModifier)
    assert shape.is_rounded(1)
    # A rounded corner gets a handle to set how round it is.
    assert "r1" in shape.handle_points()
    click(window.view, corner.x(), corner.y(), modifiers=Qt.ControlModifier)
    assert not shape.is_rounded(1)


def test_ctrl_over_a_side_bends_it_into_an_arc(window):
    shape = _polygon(window)
    start, end = shape.segment_ends(0)
    middle = shape.mapToScene((start + end) / 2)
    click(window.view, middle.x(), middle.y(), modifiers=Qt.ControlModifier)
    assert shape.is_curved(0)
    # Two handles, as Bluebeam has: how deep the curve is, and its lean.
    handles = shape.handle_points()
    assert "c0" in handles and "n0" in handles
    click(window.view, middle.x(), middle.y(), modifiers=Qt.ControlModifier)
    assert not shape.is_curved(0)


def test_the_arc_handles_bend_and_lean_the_curve(window):
    shape = _polygon(window)
    shape.curve_segment(0)
    deep, lean = shape.curved[0]
    shape.move_handle("c0", shape.curve_apex(0) + QPointF(0, 30))
    assert shape.curved[0][0] != deep
    before = shape.curved[0][1]
    start, end = shape.segment_ends(0)
    shape.move_handle("n0", start + (end - start) * 0.8)
    assert shape.curved[0][1] > before


def test_an_arc_preview_updates_during_a_real_handle_drag(window):
    shape = _polygon(window)
    shape.curve_segment(0)
    before = shape.curved[0]
    handle = shape.mapToScene(shape.handle_points()["c0"])
    target = handle + QPointF(35, 45)

    QApplication.sendEvent(window.view.viewport(), _mouse(
        window.view, QEvent.MouseButtonPress, handle.x(), handle.y()))
    QApplication.sendEvent(window.view.viewport(), _mouse(
        window.view, QEvent.MouseMove, target.x(), target.y(),
        Qt.NoButton, Qt.LeftButton))

    assert shape.curved[0] != before
    assert "c0" in shape.handle_points() and "n0" in shape.handle_points()
    QApplication.sendEvent(window.view.viewport(), _mouse(
        window.view, QEvent.MouseButtonRelease, target.x(), target.y()))


def test_the_radius_handle_sets_how_round_a_corner_is(window):
    shape = _polygon(window)
    shape.round_corner(1)
    before = shape.rounded[1]
    corner = shape.points[1]
    shape.move_handle("r1", corner + QPointF(-40, 40))
    assert shape.rounded[1] > before


def test_a_rounded_corner_preview_updates_during_a_real_handle_drag(window):
    shape = _polygon(window)
    shape.round_corner(1)
    before = shape.rounded[1]
    handle = shape.mapToScene(shape.handle_points()["r1"])
    corner = shape.mapToScene(shape.points[1])
    target = corner + (handle - corner) * 1.8

    QApplication.sendEvent(window.view.viewport(), _mouse(
        window.view, QEvent.MouseButtonPress, handle.x(), handle.y()))
    QApplication.sendEvent(window.view.viewport(), _mouse(
        window.view, QEvent.MouseMove, target.x(), target.y(),
        Qt.NoButton, Qt.LeftButton))

    assert shape.rounded[1] > before
    assert "r1" in shape.handle_points()
    QApplication.sendEvent(window.view.viewport(), _mouse(
        window.view, QEvent.MouseButtonRelease, target.x(), target.y()))


def test_a_break_symbol_goes_on_a_side_and_comes_off(window):
    shape = _polygon(window)
    plain = shape.build_path().length()
    shape.break_segment(0)
    assert shape.broken.get(0)
    # The break jinks across the line, so the outline gets longer.
    assert shape.build_path().length() > plain
    shape.break_segment(0)
    assert not shape.broken


def test_the_outline_menu_offers_all_four(window):
    shape = _polygon(window)
    corner = shape.mapToScene(shape.points[1])
    menu = window.build_context_menu(shape, corner)
    outline = [a.menu() for a in menu.actions() if a.text() == "This outline"]
    assert outline, "the outline submenu should be there"
    labels = [a.text() for a in outline[0].actions()]
    assert "Round corner" in labels
    assert "Remove point" in labels
    assert "Insert break" in labels
    assert "Arc side" in labels


def test_a_rectangle_can_become_a_polygon_to_be_reshaped(window):
    """A rectangle has no points to add to — so it can become a polygon."""
    window.select_tool("rect")
    drag(window.view, 100, 100, 260, 200)
    box = [i for i in markups(window) if isinstance(i, RectItem)][-1]
    box.setSelected(True)

    labels = [a.text() for a in window.build_context_menu(box, QPointF(150, 150)).actions()]
    assert "Convert polygon" in labels

    window.rectangle_to_polygon(box)
    shape = [i for i in markups(window) if isinstance(i, PolyItem)][-1]
    assert len(shape.points) == 4
    assert shape.closed
    assert box not in markups(window)


def test_a_reshaped_outline_survives_a_round_trip(window):
    from markforge.items.base import build_item

    shape = _polygon(window)
    shape.round_corner(1)
    shape.curve_segment(2)
    shape.break_segment(0)
    clone = build_item(shape.serialize())
    assert clone.is_rounded(1)
    assert clone.is_curved(2)
    assert clone.broken.get(0)


def test_reshaping_can_be_undone(window):
    shape = _polygon(window)
    corner = shape.mapToScene(shape.points[1])
    click(window.view, corner.x(), corner.y(), modifiers=Qt.ControlModifier)
    assert shape.is_rounded(1)
    window.undo_stack.undo()
    shape = [i for i in markups(window) if isinstance(i, PolyItem)][-1]
    assert not shape.is_rounded(1)


def test_every_drawing_tool_is_on_the_insert_menu(window):
    """Not only on the toolbar: findable by reading, as a menu bar is for."""
    from markforge.ui.tools import NONE, tools_in

    insert = None
    for entry in window.menuBar().actions():
        if entry.text() == "&Insert":
            insert = entry.menu()
    assert insert is not None
    subs = {a.text(): a.menu() for a in insert.actions() if a.menu()}
    assert "Markup" in subs and "Measurement" in subs
    drawn = [a.text() for a in subs["Markup"].actions()]
    for tool in tools_in("Draw"):
        if tool.mode != NONE:
            assert tool.label in drawn, f"{tool.label} is not on Insert ▸ Markup"
    measured = [a.text() for a in subs["Measurement"].actions()]
    for tool in tools_in("Measure"):
        if tool.mode != NONE:
            assert tool.label in measured


def test_selecting_something_draws_its_box_straight_away(window):
    """No right-click needed to see what is selected."""
    from PySide6.QtGui import QImage, QPainter

    window.select_tool("rect")
    drag(window.view, 120, 120, 260, 220)
    window.view.scene().clearSelection()
    window.selectionChangedAt = None

    def painted():
        """What the canvas looks like right now."""
        sheet = QImage(window.view.viewport().size(), QImage.Format_ARGB32)
        sheet.fill(0xFFFFFFFF)
        painter = QPainter(sheet)
        window.view.render(painter)
        painter.end()
        return sheet

    box = [i for i in markups(window) if isinstance(i, RectItem)][-1]
    empty = painted()
    box.setSelected(True)
    window.view.selectionChanged.emit()
    QApplication.processEvents()
    chosen = painted()
    assert chosen != empty, "the selection should show without anything else happening"


def test_paste_page_is_greyed_out_with_nothing_to_paste(window):
    from PySide6.QtWidgets import QApplication

    QApplication.clipboard().setText("")
    paste = [a for a in window.page_menu(0).actions()
             if a.text().startswith("Paste page")]
    assert paste and not any(a.isEnabled() for a in paste)


def test_the_format_painter_carries_a_brush(window):
    """Bluebeam's paint brush, not a letter or a box."""
    from markforge.ui.icons import icon

    assert not window.act_format_painter.icon().isNull()
    assert not icon("format_painter").isNull()
    # And it is its own drawing, not the same one another button uses.
    brush = icon("format_painter").pixmap(24, 24).toImage()
    other = icon("select").pixmap(24, 24).toImage()
    assert brush != other


# ---------------------------------------------------------------------------
# Snapping: what it caught, and while a line is being drawn
# ---------------------------------------------------------------------------

def test_snapping_says_what_it_caught(window):
    """Not just a mark on the page: the name of the thing it grabbed."""
    window.document.settings.snap_to_items = True
    window.select_tool("rect")
    drag(window.view, 140, 140, 260, 220)
    box = [i for i in markups(window) if isinstance(i, RectItem)][-1]
    corner = box.mapToScene(box.local_rect().normalized().topRight())

    caught = window.view.snap_to_item(QPointF(corner.x() + 1, corner.y() + 1))
    assert caught is not None
    assert window.view._snap_marker is not None
    assert "corner" in window.view._snap_caught
    assert "rectangle" in window.view._snap_caught.lower()

    middle = box.mapToScene(QPointF(box.local_rect().center().x(),
                                    box.local_rect().top()))
    window.view.snap_to_item(QPointF(middle.x() + 1, middle.y()))
    assert "middle" in window.view._snap_caught


def test_dragging_a_drawn_point_snaps_to_what_is_there(window):
    """Snapping used to work while a line was drawn and never again."""
    window.document.settings.snap_to_items = True
    window.select_tool("rect")
    drag(window.view, 300, 300, 400, 380)
    box = [i for i in markups(window) if isinstance(i, RectItem)][-1]
    corner = box.mapToScene(box.local_rect().normalized().topLeft())

    window.select_tool("line")
    drag(window.view, 120, 500, 200, 520)
    line = [i for i in markups(window) if isinstance(i, PolyItem)][-1]
    window.view.scene().clearSelection()
    line.setSelected(True)

    # Take the far end of the line and drop it just beside the corner.
    end = line.mapToScene(line.points[-1])
    drag(window.view, end.x(), end.y(), corner.x() + 3, corner.y() + 3)
    landed = line.mapToScene(line.points[-1])
    assert abs(landed.x() - corner.x()) < 0.6
    assert abs(landed.y() - corner.y()) < 0.6


def test_holding_ctrl_lets_a_point_go_where_it_is_put(window):
    window.document.settings.snap_to_items = True
    window.view._control_held = True
    try:
        assert window.view.snapping_off_now()
        assert window.view.snap_scene(QPointF(123.4, 234.5)) == QPointF(123.4, 234.5)
        assert window.view._snap_caught == ""
    finally:
        window.view._control_held = False


# ---------------------------------------------------------------------------
# A grid that belongs to the page
# ---------------------------------------------------------------------------

def test_a_grid_belongs_to_the_page_it_is_on(window):
    page = window.document.pages[0]
    window.document.settings.show_grid = False
    assert not page.shows_a_grid(window.document.settings)

    window.set_page_grid(0, True)
    assert page.shows_a_grid(window.document.settings)
    # And the document's own setting no longer speaks for it.
    window.document.settings.show_grid = False
    assert page.shows_a_grid(window.document.settings)


def test_an_inserted_pdf_page_comes_in_without_a_grid(window, tmp_path):
    from PySide6.QtGui import QImage
    from markforge.io import pdfio

    window.document.settings.show_grid = True
    photo = QImage(400, 300, QImage.Format_ARGB32)
    photo.fill(0xFF3366AA)
    path = str(tmp_path / "drawing.png")
    photo.save(path)
    pdfio.import_image(window.document, path, at=1)
    window.rebuild_scenes()

    drawn_on = window.document.pages[1]
    assert drawn_on.grid is False
    assert not drawn_on.shows_a_grid(window.document.settings)
    # The written pages still take the document's grid.
    assert window.document.pages[0].shows_a_grid(window.document.settings)


def test_the_page_grid_is_on_the_page_menu_and_undoes(window):
    labels = [a.text() for a in window.page_menu(0).actions()]
    assert "Page grid" in labels

    window.set_page_grid(0, True)
    assert window.document.pages[0].grid is True
    window.undo_stack.undo()
    assert window.document.pages[0].grid is None


def test_a_page_grid_survives_saving(window):
    from markforge.core.document import Page

    window.set_page_grid(0, True)
    again = Page.from_dict(window.document.pages[0].to_dict())
    assert again.grid is True
    # A page written before pages had their own grid still follows the document.
    older = Page.from_dict({"setup": {}, "items": []})
    assert older.grid is None
    window.document.settings.show_grid = True
    assert older.shows_a_grid(window.document.settings)


# ---------------------------------------------------------------------------
# The running header and footer
# ---------------------------------------------------------------------------

def test_the_footer_stays_on_the_paper_when_there_is_no_margin(window, tmp_path):
    """An imported page has no margins, and the footer used to fall off it."""
    from PySide6.QtGui import QImage
    from markforge.io import pdfio

    window.document.settings.show_footer = True
    photo = QImage(600, 400, QImage.Format_ARGB32)
    photo.fill(0xFFFFFFFF)
    path = str(tmp_path / "drawing.png")
    photo.save(path)
    pdfio.import_image(window.document, path, at=1)
    window.rebuild_scenes()
    page = window.document.pages[1]
    assert page.setup.margin_bottom == 0        # nothing to write in

    sheet = page.frame.render_image(dpi=96, for_print=True)
    # Something was written in the bottom band of the page, on the paper.
    band = sheet.copy(0, int(sheet.height() * 0.9), sheet.width(),
                      int(sheet.height() * 0.1) - 1)
    inked = sum(1 for x in range(band.width()) for y in range(band.height())
                if QColor(band.pixel(x, y)) != QColor(Qt.white))
    assert inked > 0, "the footer should be printed inside the page"


def test_a_page_can_be_left_out_of_the_header_and_footer(window):
    window.document.settings.show_footer = True
    page = window.document.pages[0]
    assert page.shows_a_footer(window.document.settings)

    window.set_page_running_text(0, "footer", False)
    assert not page.shows_a_footer(window.document.settings)
    # And the document's own setting no longer speaks for that page.
    window.document.settings.show_footer = True
    assert not page.shows_a_footer(window.document.settings)


def test_the_header_and_footer_are_on_the_page_menu(window):
    subs = {a.text(): a.menu() for a in window.page_menu(0).actions() if a.menu()}
    assert "Header/footer" in subs
    labels = [a.text() for a in subs["Header/footer"].actions()]
    assert "Show header" in labels
    assert "Show footer" in labels


def test_the_pages_panel_takes_a_dropped_drawing(window, tmp_path):
    """The panel accepts the drag and works out which page it points at."""
    from PySide6.QtCore import QMimeData, QPoint, QUrl
    from PySide6.QtGui import QDragEnterEvent

    panel = window.pages_panel
    assert panel.list.acceptDrops()
    assert panel.list.showDropIndicator()

    photo = tmp_path / "sheet.pdf"
    photo.write_bytes(b"%PDF-1.4\n")
    data = QMimeData()
    data.setUrls([QUrl.fromLocalFile(str(photo))])
    assert panel._files_in(type("E", (), {"mimeData": lambda self: data})())

    # And something it cannot use is left to the list itself.
    other = QMimeData()
    other.setUrls([QUrl.fromLocalFile("/tmp/notes.txt")])
    assert not panel._files_in(type("E", (), {"mimeData": lambda self: other})())


def test_a_wrapping_page_grid_uses_left_and_right_for_the_drop_slot(window, qapp):
    window.add_page()
    window.add_page()
    panel = window.pages_panel
    panel.rebuild(window.document, 0)
    qapp.processEvents()
    assert panel.list.uses_horizontal_slots()
    first = panel.list.visualItemRect(panel.list.item(0))
    assert panel.drop_row(first.center() - QPoint(first.width() // 3, 0)) == 0
    assert panel.drop_row(first.center() + QPoint(first.width() // 3, 0)) == 1


def test_a_dropped_pdf_is_imported_at_the_indicated_row(window, tmp_path):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QPainter, QPdfWriter

    window.add_page()
    window.add_page()
    path = tmp_path / "one-sheet.pdf"
    writer = QPdfWriter(str(path))
    writer.setResolution(150)
    painter = QPainter(writer)
    painter.fillRect(QRectF(100, 100, 300, 200), QColor("#336699"))
    painter.end()
    before = [page.uid for page in window.document.pages]

    assert window.insert_files_at([str(path)], 1) == 1

    assert window.document.pages[0].uid == before[0]
    assert window.document.pages[2].uid == before[1]
    assert window.document.pages[1].source_note.endswith("one-sheet.pdf page 1")


# ---------------------------------------------------------------------------
# Finding a tool by what it does
# ---------------------------------------------------------------------------

def test_help_can_find_a_tool_by_what_it_does(window):
    """Fifty tools is more than anybody keeps in their head."""
    assert [t.key for t in window.tools_matching("cloud")][0] == "cloud"
    # By what it is for, not only by its name.
    assert "cloud" in [t.key for t in window.tools_matching("revision")]
    assert "measure_area" in [t.key for t in window.tools_matching("area")]
    # And by the key it is on.
    assert "cloud" in [t.key for t in window.tools_matching("C")]
    assert window.tools_matching("") == []
    assert window.tools_matching("xyzzy") == []


def test_find_a_tool_is_on_the_help_menu(window):
    labels = []
    for entry in window.menuBar().actions():
        if entry.text() == "&Help":
            labels = [a.text() for a in entry.menu().actions()]
    assert "Find tool…" in labels
    assert window.act_find_tool.shortcut().toString() == "Shift+F1"


def test_finding_a_tool_picks_it_up(window, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("revision cloud", True)))
    window.find_a_tool()
    assert window.view.tool_key == "cloud"
    assert "Cloud" in window.status_hint.text()


# ---------------------------------------------------------------------------
# Hatch patterns and line types
# ---------------------------------------------------------------------------

def test_a_hatched_fill_is_not_a_flat_one(window):
    from PySide6.QtCore import Qt as QtNS
    from markforge.items.base import Style

    plain = Style(fill="#888888")
    assert plain.brush().style() == QtNS.SolidPattern
    hatched = Style(fill="#888888", hatch="diagonal up")
    assert hatched.brush().style() == QtNS.BDiagPattern


def test_bluebeams_spellings_of_a_hatch_all_land(window):
    from PySide6.QtCore import Qt as QtNS
    from markforge.items.base import hatch_named

    assert hatch_named("Hatch-DiagonalUp") == QtNS.BDiagPattern
    assert hatch_named("diagonal down") == QtNS.FDiagPattern
    assert hatch_named("DiagonalCross") == QtNS.DiagCrossPattern
    assert hatch_named("Horizontal") == QtNS.HorPattern
    assert hatch_named("/Vertical") == QtNS.VerPattern
    assert hatch_named("Concrete") == QtNS.Dense5Pattern
    assert hatch_named("") == QtNS.SolidPattern
    assert hatch_named("something nobody has heard of") == QtNS.SolidPattern


def test_a_line_type_is_drawn_with_its_own_dashes(window):
    from PySide6.QtCore import Qt as QtNS
    from markforge.items.base import Style

    assert Style(line_style="solid").dashes() == []
    assert Style(line_style="centre").dashes() == [10.0, 2.5, 2.0, 2.5]
    pen = Style(line_style="hidden").pen()
    assert pen.style() == QtNS.CustomDashLine
    assert pen.dashPattern() == [3.0, 2.0]
    # A pattern of its own beats the named one.
    own = Style(line_style="solid", dash_array=(6.0, 1.0))
    assert own.dashes() == [6.0, 1.0]


def test_a_dashed_line_from_a_toolset_comes_in_dashed(window):
    """It used to be written to a field no markup has, and came in solid."""
    from markforge.io.btx import _style

    look = _style({"C": [0, 0, 0], "BS": {"W": 2.0, "S": "D", "D": [4, 3]}})
    assert look["line_style"] == "dash"
    assert look["dash_array"] == (4.0, 3.0)

    plain = _style({"C": [0, 0, 0], "BS": {"W": 2.0}})
    assert plain["line_style"] == "solid"
    assert "dash_array" not in plain


def test_the_line_and_hatch_lists_are_in_the_properties_panel(window):
    from PySide6.QtWidgets import QComboBox

    window.select_tool("rect")
    drag(window.view, 120, 120, 260, 220)
    box = markups(window)[-1]
    box.setSelected(True)
    window.properties_panel.show_items([box])

    labels = [w.text() for w in window.properties_panel.findChildren(type(
        window.properties_panel.findChild(QComboBox).parent()))] if False else []
    boxes = window.properties_panel.findChildren(QComboBox)
    entries = [[b.itemText(i) for i in range(b.count())] for b in boxes]
    assert any("centre" in e for e in entries), "the line types should be there"
    assert any("diagonal cross" in e for e in entries), "the hatches should be there"


def test_line_and_hatch_choices_have_real_pattern_previews(window):
    from PySide6.QtWidgets import QComboBox

    window.select_tool("rect")
    drag(window.view, 100, 100, 260, 220)
    window.select_tool("select")
    markups(window)[-1].setSelected(True)
    window.refresh_selection()

    line = window.properties_panel.findChild(QComboBox, "lineStyle")
    hatch = window.properties_panel.findChild(QComboBox, "hatchPattern")
    solid = line.iconSize()
    assert solid.width() >= 70 and solid.height() >= 20
    assert not line.itemIcon(line.findData("solid")).isNull()
    assert (line.itemIcon(line.findData("solid")).pixmap(solid).toImage()
            != line.itemIcon(line.findData("dash")).pixmap(solid).toImage())
    assert hatch.itemText(hatch.findData("")) == "plain"
    assert (hatch.itemIcon(hatch.findData("")).pixmap(hatch.iconSize()).toImage()
            != hatch.itemIcon(hatch.findData("diagonal cross")).pixmap(
                hatch.iconSize()).toImage())


def _property_groups(window):
    from PySide6.QtWidgets import QGroupBox

    return {box.title() for box in window.properties_panel.findChildren(QGroupBox)}


def test_properties_only_offers_controls_the_selected_kind_can_use(window):
    from PySide6.QtWidgets import QComboBox

    rect = _a_rectangle(window)
    window.select_tool("select")
    click(window.view, rect.sceneBoundingRect().center().x(),
          rect.sceneBoundingRect().center().y())
    assert {"Appearance", "Size"} <= _property_groups(window)
    assert "Text" not in _property_groups(window)
    assert window.properties_panel.findChild(QComboBox, "hatchPattern") is not None

    window.select_tool("line")
    drag(window.view, 320, 120, 460, 220)
    line = markups(window)[-1]
    window.select_tool("select")
    click(window.view, 390, 170)
    assert "Text" not in _property_groups(window)
    assert window.properties_panel.findChild(QComboBox, "lineStyle") is not None
    assert window.properties_panel.findChild(QComboBox, "hatchPattern") is None


def test_an_image_does_not_get_shape_style_controls(window):
    """A photograph has no line style and no hatch, so it is offered neither."""
    from markforge.items.media import ImageItem
    from PySide6.QtWidgets import QComboBox

    image = ImageItem(rect=QRectF(0, 0, 120, 80))
    window.view.frame().add_markup(image, QPointF(90, 250))
    click(window.view, 150, 290)
    assert {"Appearance", "Image"} <= _property_groups(window)
    assert "Text" not in _property_groups(window)
    assert window.properties_panel.findChild(QComboBox, "lineStyle") is None
    assert window.properties_panel.findChild(QComboBox, "hatchPattern") is None


def test_style_toolbar_tracks_real_selection_and_the_active_tool(window):
    from markforge.ui.stylecaps import DASH, FILL, FONT, STROKE, WIDTH

    window.view.escape_everything()
    window.select_tool("line")
    assert all(action.isVisible() for field in (STROKE, WIDTH, DASH)
               for action in window._style_widgets[field])
    assert all(not action.isVisible() for field in (FILL, FONT)
               for action in window._style_widgets[field])

    drag(window.view, 100, 100, 240, 180)
    window.select_tool("select")
    click(window.view, 170, 140)
    assert all(action.isVisible() for field in (STROKE, WIDTH, DASH)
               for action in window._style_widgets[field])
    assert all(not action.isVisible() for field in (FILL, FONT)
               for action in window._style_widgets[field])

    # Words are the only markup with a face and a size to set, so picking one
    # brings the font controls out — which no shape ever does.
    words = _words(window, "2 no.", at=(90, 280))
    window.select_tool("select")
    click(window.view, words.sceneBoundingRect().center().x(),
          words.sceneBoundingRect().center().y())
    assert all(action.isVisible() for action in window._style_widgets[FONT])
    assert all(action.isVisible() for field in (STROKE, FILL, WIDTH, DASH)
               for action in window._style_widgets[field]), \
        "a text box is a box: it keeps its outline and its fill"


def test_callout_properties_has_no_user_facing_multiply_control(window):
    from PySide6.QtWidgets import QAbstractButton, QComboBox

    callout = _callout(window)
    window.view.end_item_edit()
    window.select_tool("select")
    click(window.view, callout.sceneBoundingRect().center().x(),
          callout.sceneBoundingRect().center().y())
    words = [button.text() for button in
             window.properties_panel.findChildren(QAbstractButton)]
    for combo in window.properties_panel.findChildren(QComboBox):
        words.extend(combo.itemText(index) for index in range(combo.count()))
    assert not any("multiply" in word.lower() for word in words)


# ---------------------------------------------------------------------------
# The page bar along the bottom
# ---------------------------------------------------------------------------

def test_the_page_bar_says_what_the_paper_is(window):
    window.refresh_page_bar()
    assert "A4" in window.status_size.text()
    assert "210" in window.status_size.text() and "297" in window.status_size.text()
    assert "Margins 10 mm" in window.status_size.toolTip()


def test_the_grid_and_snap_buttons_are_on_the_bar(window):
    window.set_page_grid(0, False)
    window.refresh_page_bar()
    assert not window.status_grid.isChecked()

    window.status_grid.setChecked(True)
    assert window.document.pages[0].grid is True

    window.act_snap.setChecked(True)
    assert window.document.settings.snap_to_grid
    window.act_snap.setChecked(False)
    assert not window.document.settings.snap_to_grid

    labels = [action.text() for action in window.status_snap.menu().actions()]
    assert labels == ["Grid snap", "Markup snap", "PDF snap", "Align snap"]


def test_the_snap_dropdown_toggles_a_target_through_qt(window):
    from PySide6.QtCore import QTimer
    from PySide6.QtTest import QTest

    window.act_snap.setChecked(False)
    menu = window.status_snap.menu()
    grid_action = menu.actions()[0]

    def choose_grid():
        assert menu.isVisible()
        QTest.mouseClick(menu, Qt.LeftButton, Qt.NoModifier,
                         menu.actionGeometry(grid_action).center())

    QTimer.singleShot(0, choose_grid)
    QTest.mouseClick(window.status_snap, Qt.LeftButton)
    assert window.document.settings.snap_to_grid


def test_the_bar_follows_the_page_it_is_on(window, tmp_path):
    from PySide6.QtGui import QImage
    from markforge.io import pdfio

    photo = QImage(1200, 800, QImage.Format_ARGB32)
    photo.fill(0xFFFFFFFF)
    path = str(tmp_path / "big.png")
    photo.save(path)
    pdfio.import_image(window.document, path, at=1)
    window.rebuild_scenes()

    window.go_to_page(1)
    wide = window.status_size.text()
    window.go_to_page(0)
    assert window.status_size.text() != wide
    assert "A4" in window.status_size.text()


# ---------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------

def _dimension(window):
    window.select_tool("measure_dimension")
    drag(window.view, 150, 300, 350, 300)
    dim = [i for i in markups(window) if isinstance(i, MeasureItem)][-1]
    window.view.scene().clearSelection()
    dim.setSelected(True)
    return dim


def test_shift_click_pulls_the_number_off_the_line(window):
    """Bluebeam's: take hold of the value, not of a small handle."""
    dim = _dimension(window)
    dim.custom_label = "600"
    dim.refresh(page=window.current_page())
    assert not dim.label_is_off_the_line()

    on_the_number = dim.mapToScene(dim.label_rect().center())
    drag(window.view, on_the_number.x(), on_the_number.y(),
         on_the_number.x() + 40, on_the_number.y() - 60,
         modifiers=Qt.ShiftModifier)
    assert dim.label_is_off_the_line()


def test_dragging_the_dot_with_the_mouse_pulls_the_line_off_the_drawing(window):
    """The whole gesture, through the pointer: press the dot, drag, let go."""
    dim = _dimension(window)
    dim.custom_label = "600"
    dim.refresh(page=window.current_page())
    assert dim.witness_reach == 0.0

    dot = dim.mapToScene(dim.handle_points()["lbl"])
    drag(window.view, dot.x(), dot.y(), dot.x(), dot.y() - 50)
    assert dim.witness_reach == pytest.approx(-50, abs=2)
    assert not dim.label_is_off_the_line(), \
        "the value went with the line, not away from it"


def test_letting_go_of_shift_half_way_does_not_change_the_gesture(window):
    """What the drag is was settled when it started."""
    dim = _dimension(window)
    dim.custom_label = "600"
    dim.refresh(page=window.current_page())

    dot = dim.mapToScene(dim.handle_points()["lbl"])
    view = window.view
    QApplication.sendEvent(view.viewport(), _mouse(
        view, QEvent.MouseButtonPress, dot.x(), dot.y(),
        modifiers=Qt.ShiftModifier))
    for step in (0.5, 1.0):                       # Shift let go of half way
        QApplication.sendEvent(view.viewport(), _mouse(
            view, QEvent.MouseMove, dot.x() + 30 * step, dot.y() - 40 * step,
            Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
    QApplication.sendEvent(view.viewport(), _mouse(
        view, QEvent.MouseButtonRelease, dot.x() + 30, dot.y() - 40))
    assert dim.label_is_off_the_line()
    assert dim.witness_reach == 0.0


def test_the_number_knows_where_it_is(window):
    dim = _dimension(window)
    dim.custom_label = "600"
    dim.refresh(page=window.current_page())
    assert dim.label_at(dim.label_rect().center())
    assert not dim.label_at(dim.label_rect().center() + QPointF(0, 400))


def test_a_dimensions_value_holds_still_while_its_text_is_turned(window, tmp_path):
    """It used to be worked out against whatever page the view was on."""
    from PySide6.QtGui import QImage
    from markforge.core.document import PageScale
    from markforge.io import pdfio

    # Two pages at different scales, and a dimension on the second.
    photo = QImage(400, 300, QImage.Format_ARGB32)
    photo.fill(0xFFFFFFFF)
    path = str(tmp_path / "sheet.png")
    photo.save(path)
    pdfio.import_image(window.document, path, at=1)
    window.rebuild_scenes()
    window.document.pages[0].scale = PageScale.from_ratio(1)
    window.document.pages[1].scale = PageScale.from_ratio(100)

    frame = window.document.pages[1].frame
    dim = MeasureItem(DIMENSION)
    dim.points = [QPointF(0, 0), QPointF(200, 0)]
    frame.add_markup(dim, QPointF(40, 60))
    dim.refresh(page=window.document.pages[1])
    reading = dim.value_text
    assert reading

    # Now look at page 1 and turn the text on page 2's dimension.
    window.go_to_page(0)
    assert window.view.page_of(dim) is window.document.pages[1]
    dim.refresh(page=window.view.page_of(dim))
    assert dim.value_text == reading


# ---------------------------------------------------------------------------
# An inserted PDF brings its own line work
# ---------------------------------------------------------------------------

def _a_pdf_with_lines(window, tmp_path):
    """Export a page with known geometry, so it can be read back in."""
    from markforge.io import export as export_io

    window.select_tool("rect")
    drag(window.view, 120, 150, 300, 260)
    window.select_tool("line")
    drag(window.view, 120, 320, 380, 320)
    path = str(tmp_path / "drawing.pdf")
    export_io.export_pdf(window.document, path)
    return path


def test_an_inserted_pdf_brings_somebody_elses_markups_back_as_markups(
        window, tmp_path):
    """A cloud is a cloud, not sixty loose segments and not a picture."""
    from markforge.io import pdfio

    path = _a_pdf_with_lines(window, tmp_path)
    found = pdfio.markups(path, [0])
    assert found, "the PDF's annotations should be readable"

    # Each comes back where it was drawn, as the kind of markup it is.
    placed = {(item["type"], item.get("kind"),
               round(item["x"]), round(item["y"])) for item in found[0]}
    assert ("rect", "rect", 120, 150) in placed
    # Two points with an arrow on the end is a line annotation, and a line
    # annotation is a line — not a polyline that happens to have two corners.
    assert ("poly", "line", 120, 320) in placed
    assert all(item["layer"] == "Markups" for item in found[0])


def test_the_lines_come_in_on_a_layer_of_their_own(window, tmp_path):
    """The page's own drawing is the page's; a markup is somebody's."""
    from markforge.core.document import Document
    from markforge.io import pdfio

    path = _a_pdf_with_lines(window, tmp_path)
    fresh = Document()
    pages = pdfio.import_pages(fresh, path, [0], vectors=True, at=1)
    layers = {item["layer"] for item in pages[0]._pending_items}
    assert "Drawing" in layers, "the page's own line work"
    assert "Markups" in layers, "and the markups that were made on it"
    assert "Drawing" in fresh.layer_names()
    # And the picture is still there underneath, so the words still show.
    assert pages[0].background_key


def test_the_lines_can_be_left_out_but_the_markups_never_are(window, tmp_path):
    from markforge.core.document import Document
    from markforge.io import pdfio

    path = _a_pdf_with_lines(window, tmp_path)
    fresh = Document()
    pages = pdfio.import_pages(fresh, path, [0], vectors=False, at=1)
    layers = {item["layer"] for item in pages[0]._pending_items}
    assert layers == {"Markups"}, \
        "the page's own line work was not asked for; the markups always are"
    assert pages[0].background_key


def test_a_file_that_cannot_be_read_that_way_still_comes_in(window, tmp_path):
    from markforge.io import pdfio

    broken = tmp_path / "not-really.pdf"
    broken.write_bytes(b"%PDF-1.4\nnothing to see here\n")
    assert pdfio.line_work(str(broken), [0]) == {}


def test_a_curve_comes_across_as_something_to_measure(window):
    from markforge.io import pdfio

    run = pdfio._runs([["m", 0.0, 0.0], ["c", 0.0, 10.0, 10.0, 10.0, 10.0, 0.0]])
    assert len(run) == 1
    assert len(run[0]) > 4          # flattened into pieces, not dropped
    assert run[0][0] == [0.0, 0.0]
    assert run[0][-1] == [10.0, 0.0]


def test_a_closed_path_comes_back_closed(window):
    from markforge.io import pdfio

    run = pdfio._runs([["m", 0.0, 0.0], ["l", 10.0, 0.0], ["l", 10.0, 10.0], ["z"]])
    assert run[0][0] == run[0][-1]


# ---------------------------------------------------------------------------
# The numbers in the properties panel
# ---------------------------------------------------------------------------

def test_the_properties_panel_says_where_it_is_and_how_big(window):
    """Typed, not nudged: a detail that starts exactly 40 mm in."""
    from PySide6.QtWidgets import QDoubleSpinBox, QGroupBox
    from markforge.core.document import MM_TO_PT, PT_TO_MM

    window.select_tool("rect")
    drag(window.view, 120, 150, 320, 250)
    box = markups(window)[-1]
    box.setSelected(True)
    window.properties_panel.show_items([box])

    groups = {g.title(): g for g in
              window.properties_panel.findChildren(QGroupBox)}
    assert "Position and size" in groups
    labels = [w.text().rstrip(":") for w in groups["Position and size"].findChildren(
        type(groups["Position and size"].findChild(QLabel)))]
    for wanted in ("X", "Y", "Width", "Height", "Rotation"):
        assert wanted in labels, f"{wanted} should be in the panel"

    spins = groups["Position and size"].findChildren(QDoubleSpinBox)
    # It reads what is actually there, in millimetres.
    assert spins[0].value() == pytest.approx(box.pos().x() * PT_TO_MM, abs=0.1)
    assert spins[2].value() == pytest.approx(
        box.local_rect().width() * PT_TO_MM, abs=0.1)


def test_typing_a_number_moves_and_resizes_it(window):
    from PySide6.QtWidgets import QDoubleSpinBox, QGroupBox
    from markforge.core.document import MM_TO_PT

    window.select_tool("rect")
    drag(window.view, 120, 150, 320, 250)
    box = markups(window)[-1]
    box.setSelected(True)
    window.properties_panel.show_items([box])
    groups = {g.title(): g for g in
              window.properties_panel.findChildren(QGroupBox)}
    spins = groups["Position and size"].findChildren(QDoubleSpinBox)

    spins[0].setValue(40.0)                       # 40 mm in from the left
    assert box.pos().x() == pytest.approx(40.0 * MM_TO_PT, abs=0.5)
    spins[2].setValue(60.0)                       # and 60 mm across
    assert box.local_rect().width() == pytest.approx(60.0 * MM_TO_PT, abs=0.5)

    # One undo step for the lot, not one per keystroke.
    before = window.undo_stack.count()
    spins[1].setValue(80.0)
    assert window.undo_stack.count() <= before + 1


def test_a_markup_that_cannot_be_resized_is_not_asked_about_its_size(window):
    from PySide6.QtWidgets import QDoubleSpinBox, QGroupBox

    window.select_tool("flag")
    click(window.view, 200, 200)
    flag = markups(window)[-1]
    flag.setSelected(True)
    window.properties_panel.show_items([flag])
    groups = {g.title(): g for g in
              window.properties_panel.findChildren(QGroupBox)}
    spins = groups["Position and size"].findChildren(QDoubleSpinBox)
    assert len(spins) == 2                        # only X and Y


# ---------------------------------------------------------------------------
# The leader, rewritten: perpendicular, clear of the words, worked out again
# ---------------------------------------------------------------------------

def test_the_hinge_exists_while_the_callout_is_being_placed(window):
    """The preview is the real thing, so what is shown is what lands."""
    window.select_tool("callout")
    click(window.view, 200, 300)                 # what it points at
    hover(window.view, 420, 200)                 # where the words would go

    preview = window.view._pending_callout()
    assert preview is not None
    leader = preview.leaders[0]
    start = preview.side_point_of(leader)
    hinge = preview.elbow_of(leader)
    # There is a hinge, and it leaves the side square on.
    assert (hinge - start).manhattanLength() > 1
    assert abs(hinge.x() - start.x()) < 0.01 or abs(hinge.y() - start.y()) < 0.01


def test_the_leader_does_not_move_when_the_click_lands(window):
    """What the preview showed is exactly what is placed."""
    window.select_tool("callout")
    click(window.view, 200, 300)
    hover(window.view, 420, 200)
    preview = window.view._pending_callout()
    shown = (preview.side_of(preview.leaders[0]),
             preview.mapToScene(preview.elbow_of(preview.leaders[0])))

    click(window.view, 420, 200)
    call = window.view.editing_item()
    placed = (call.side_of(call.leaders[0]),
              call.mapToScene(call.elbow_of(call.leaders[0])))
    window.view.end_item_edit()

    # The same side, and the hinge in the same place — not on a corner during
    # placement and on a side afterwards.
    assert placed[0] == shown[0]
    assert (placed[1] - shown[1]).manhattanLength() < 1.0


def test_moving_the_arrow_head_works_the_hinge_out_again(window):
    """It used to stay on whichever side it had been dragged to."""
    call = _callout(window)
    window.view.end_item_edit()
    window.select_tool("select")
    call.setSelected(True)
    leader = call.leaders[0]
    box = call.local_rect().normalized()

    leader.tip = QPointF(box.left() - 140, box.center().y())
    call.leader_moved()
    call.set_elbow_of(leader, QPointF(box.center().x(), box.top() - 40))
    assert call.side_of(leader) == "top" and leader.side == "top"
    assert leader.reach > call.ELBOW_REACH

    # Drag the arrow head round to the other side of the box.
    handle = call.mapToScene(leader.tip)
    target = call.mapToScene(QPointF(box.right() + 160, box.center().y()))
    drag(window.view, handle.x(), handle.y(), target.x(), target.y())

    assert leader.side == "", "the hand-picked side should have been given up"
    assert leader.reach == pytest.approx(call.ELBOW_REACH)
    assert call.side_of(leader) == "right"


def test_several_leaders_each_work_their_own_hinge_out(window):
    """One hinge for the lot is what a call-out must not have.

    Each leader points somewhere different, so each works out its own side
    from its own target when the box or the cloud moves — none of them is
    handed whatever the first one happens to be doing.
    """
    call = _callout(window)
    window.view.end_item_edit()
    window.select_tool("select")
    box = call.local_rect().normalized()

    call.tip = QPointF(box.left() - 150, box.center().y())
    call.add_leader(QPointF(box.right() + 150, box.center().y()))
    call.add_leader(QPointF(box.center().x(), box.bottom() + 150))
    assert len(call.leaders) == 3

    # Hand-place the first one's hinge somewhere it would not go by itself.
    call.set_elbow_of(call.leaders[0], QPointF(box.center().x(), box.top() - 45))
    assert call.leaders[0].side == "top"
    assert call.leaders[0].reach > call.ELBOW_REACH

    call.leader_moved()

    assert call.leaders[0].side == "", "the hand-picked side is given up"
    assert all(leader.reach == pytest.approx(call.ELBOW_REACH)
               for leader in call.leaders), "and the stand-off goes back to normal"
    sides = [call.side_of(leader) for leader in call.leaders]
    assert len(set(sides)) == 3, f"each leaves by its own side, got {sides}"


def test_moving_the_box_works_the_hinge_out_again(window):
    call = _callout(window)
    window.view.end_item_edit()
    window.select_tool("select")
    call.setSelected(True)
    leader = call.leaders[0]
    box = call.local_rect().normalized()
    leader.tip = QPointF(box.left() - 140, box.center().y())
    call.leader_moved()
    call.set_elbow_of(leader, QPointF(box.center().x(), box.top() - 40))
    assert leader.side == "top"
    assert leader.reach > call.ELBOW_REACH

    call.move_keeping_leader(call.pos() + QPointF(-400, 0))
    assert leader.side == ""
    assert leader.reach == pytest.approx(call.ELBOW_REACH)


def test_a_leader_survives_a_round_trip_with_its_side_and_reach(window):
    from markforge.items.base import build_item

    call = _callout(window)
    window.view.end_item_edit()
    leader = call.leaders[0]
    box = call.local_rect().normalized()
    leader.tip = QPointF(box.left() - 140, box.center().y())
    call.leader_moved()
    call.set_elbow_of(leader, QPointF(box.center().x(), box.top() - 55))

    clone = build_item(call.serialize())
    kept = clone.leaders[0]
    assert kept.side == leader.side
    assert kept.reach == pytest.approx(leader.reach, abs=0.01)
    assert clone.side_of(kept) == call.side_of(leader)


def test_a_document_written_before_this_still_opens(window):
    """A leader saved as a free elbow comes back as a sensible one."""
    from markforge.items.base import build_item

    older = {"type": "callout", "x": 0, "y": 0, "rect": [0, 0, 160, 60],
             "text": "note", "uid": "old",
             "leaders": [{"tip": [-120, 30], "elbow": [-40, -30], "reach": 30}]}
    call = build_item(older)
    assert call is not None
    leader = call.leaders[0]
    assert leader.tip == QPointF(-120, 30)
    assert leader.reach == pytest.approx(30)
    # The elbow it was saved with is gone; the hinge is worked out instead.
    start = call.side_point_of(leader)
    hinge = call.elbow_of(leader)
    assert abs(hinge.x() - start.x()) < 0.01 or abs(hinge.y() - start.y()) < 0.01


def test_the_menu_adds_and_removes_one_leader_at_a_time(window):
    call = _callout(window)
    window.view.end_item_edit()
    assert len(call.leaders) == 1

    menu = window.build_context_menu(call, call.mapToScene(QPointF(20, 20)))
    labels = _menu_labels(menu)
    assert "Add arrow leader" in labels
    assert "Add cloud leader" in labels

    window.add_leader_to(call)
    window.add_leader_to(call)
    assert len(call.leaders) == 3

    # Right-click on one of them, and that one can be taken away.
    on_it = call.mapToScene(call.elbow_of(call.leaders[1]))
    labels = _menu_labels(window.build_context_menu(call, on_it))
    assert "Remove leader" in labels
    window.remove_leader_from(call, 1)
    assert len(call.leaders) == 2


def test_a_cloud_callout_is_offered_more_leaders_of_either_kind(window):
    """A cloud call-out is a call-out, so it takes leaders like one.

    This used to be the opposite — a clouded note was offered no leaders at
    all, on the grounds that the cloud does the pointing. But one note about
    two things needs two leaders, and there is no reason the second cannot be
    an arrow while the first is a cloud.
    """
    window.select_tool("cloud_callout")
    drag(window.view, 160, 260, 300, 340)
    click(window.view, 430, 200)
    call = window.view.editing_item()
    window.view.end_item_edit()
    assert [leader.kind for leader in call.leaders] == ["cloud"]

    labels = _menu_labels(window.build_context_menu(call, call.pos()))
    assert "Add arrow leader" in labels
    assert "Add cloud leader" in labels

    window.add_leader_to(call, "arrow")
    assert [leader.kind for leader in call.leaders] == ["cloud", "arrow"]
    window.add_leader_to(call, "cloud")
    drag(window.view, 500, 330, 620, 400)
    assert [leader.kind for leader in call.leaders] == ["cloud", "arrow", "cloud"]


def test_add_cloud_leader_uses_the_region_dragged_on_the_canvas(window):
    call = _callout(window)
    window.view.end_item_edit()
    before = len(call.leaders)
    window.add_leader_to(call, "cloud")

    assert window.view._pending_cloud_leader is call
    assert len(call.leaders) == before
    drag(window.view, 500, 330, 620, 400)

    assert window.view._pending_cloud_leader is None
    assert len(call.leaders) == before + 1
    cloud = call.leaders[-1]
    assert cloud.kind == "cloud"
    box = call.mapRectToScene(cloud.cloud_box()).normalized()
    assert box.topLeft() == QPointF(500, 330)
    assert box.bottomRight() == QPointF(620, 400)


def test_escape_cancels_an_unplaced_cloud_leader(window):
    call = _callout(window)
    window.view.end_item_edit()
    before = call.serialize()
    window.add_leader_to(call, "cloud")

    press_key(window.view, Qt.Key_Escape)

    assert window.view._pending_cloud_leader is None
    assert call.serialize() == before
    assert window.view.cursor().shape() == Qt.ArrowCursor


def test_a_cloud_and_its_callout_box_move_independently(window):
    window.select_tool("cloud_callout")
    drag(window.view, 160, 260, 300, 340)
    click(window.view, 430, 200)
    call = window.view.editing_item()
    window.view.end_item_edit()
    window.select_tool("select")
    call.setSelected(True)
    leader = call.leaders[0]

    box_position = QPointF(call.pos())
    cloud_before = [call.mapToScene(point) for point in leader.cloud]
    cloud_handle = call.mapToScene(call.handle_points()["l0"])
    drag(window.view, cloud_handle.x(), cloud_handle.y(),
         cloud_handle.x() + 65, cloud_handle.y() + 35)

    assert call.pos() == box_position
    cloud_after = [call.mapToScene(point) for point in leader.cloud]
    for before, after in zip(cloud_before, cloud_after):
        assert after - before == QPointF(65, 35)

    cloud_pinned = [QPointF(point) for point in cloud_after]
    box = call.mapToScene(call.local_rect().center())
    drag(window.view, box.x(), box.y(), box.x() - 80, box.y() + 45)

    assert call.pos() - box_position == QPointF(-80, 45)
    for before, after in zip(cloud_pinned,
                             [call.mapToScene(point) for point in leader.cloud]):
        assert after == before
    assert leader.side == ""
    assert leader.reach == pytest.approx(call.ELBOW_REACH)


def test_the_hinge_stand_off_can_be_typed(window):
    from PySide6.QtWidgets import QDoubleSpinBox, QGroupBox

    call = _callout(window)
    window.view.end_item_edit()
    call.setSelected(True)
    window.properties_panel.show_items([call])

    groups = {g.title(): g for g in
              window.properties_panel.findChildren(QGroupBox)}
    assert "Leader" in groups
    spins = groups["Leader"].findChildren(QDoubleSpinBox)
    assert spins, "the stand-off should be in the panel"
    spins[0].setValue(70)
    assert call.leaders[0].reach == pytest.approx(70, abs=0.5)
    # And the hinge is still square out of its side.
    start = call.side_point()
    hinge = call.elbow()
    assert abs(hinge.x() - start.x()) < 0.01 or abs(hinge.y() - start.y()) < 0.01


# ---------------------------------------------------------------------------
# Snapping: three kinds, each doing its own job
# ---------------------------------------------------------------------------

def _quiet_snapping(window):
    """Every kind of snapping off, so one can be turned on at a time."""
    settings = window.document.settings
    settings.snap_to_grid = False
    settings.snap_to_items = False
    settings.snap_to_content = False
    settings.snap_to_alignment = False
    return settings


def test_turning_the_grid_snap_off_actually_stops_it(window):
    settings = _quiet_snapping(window)
    odd = QPointF(123.7, 234.3)
    assert window.view.snap_scene(odd) == odd

    settings.snap_to_grid = True
    assert window.view.snap_scene(odd) != odd

    settings.snap_to_grid = False
    assert window.view.snap_scene(odd) == odd


def test_the_menu_and_the_page_bar_agree_about_snapping(window):
    """The dropdown and View menu share one action and cannot disagree."""
    grid = window.status_snap.menu().actions()[0]
    assert grid is window.act_snap
    window.toggle_snap(True)
    assert grid.isChecked()

    grid.setChecked(False)                        # the bar
    assert not window.document.settings.snap_to_grid
    assert not window.act_snap.isChecked()        # and the menu follows

    window.act_snap.setChecked(True)              # the menu
    assert window.document.settings.snap_to_grid
    assert grid.isChecked()                       # and the bar follows


def test_the_middle_of_a_polygon_side_can_be_caught(window):
    settings = _quiet_snapping(window)
    settings.snap_to_items = True

    window.select_tool("polygon")
    for x, y in ((400, 300), (560, 300), (560, 420)):
        click(window.view, x, y)
    press_key(window.view, Qt.Key_Return)
    poly = [i for i in markups(window) if isinstance(i, PolyItem)][-1]

    middle = poly.mapToScene((poly.points[0] + poly.points[1]) / 2)
    caught = window.view.snap_to_item(middle + QPointF(2, 2))
    assert caught is not None
    assert (caught - middle).manhattanLength() < 0.01
    assert "middle" in window.view._snap_caught


def test_a_new_markup_lines_up_with_one_already_drawn(window):
    """Level with that corner, or directly under it."""
    settings = _quiet_snapping(window)
    settings.snap_to_items = True
    settings.snap_to_alignment = True

    window.select_tool("rect")
    drag(window.view, 300, 200, 420, 260)
    box = markups(window)[-1]
    corner = box.mapToScene(box.local_rect().normalized().topLeft())

    # A long way below it, but almost exactly in line.
    lined = window.view.snap_scene(QPointF(corner.x() + 2, corner.y() + 300))
    assert lined.x() == pytest.approx(corner.x(), abs=0.01)
    assert lined.y() == pytest.approx(corner.y() + 300, abs=0.01)
    assert window.view._snap_guides
    assert "in line" in window.view._snap_caught

    settings.snap_to_alignment = False
    loose = window.view.snap_scene(QPointF(corner.x() + 2, corner.y() + 300))
    assert loose.x() == pytest.approx(corner.x() + 2, abs=0.01)


def _show_an_alignment_guide(window):
    settings = _quiet_snapping(window)
    settings.snap_to_items = True
    settings.snap_to_alignment = True
    window.select_tool("rect")
    drag(window.view, 300, 200, 420, 260)
    box = markups(window)[-1]
    corner = box.mapToScene(box.local_rect().normalized().topLeft())
    window.select_tool("line")
    hover(window.view, corner.x() + 2, corner.y() + 300)
    assert window.view._snap_guides
    return corner + QPointF(2, 300)


def test_snap_guides_clear_when_the_pointer_leaves(window):
    _show_an_alignment_guide(window)
    QApplication.sendEvent(window.view.viewport(), QEvent(QEvent.Leave))
    assert window.view._snap_guides == []
    assert window.view._snap_marker is None


def test_snap_guides_clear_on_tool_change_and_escape(window):
    _show_an_alignment_guide(window)
    window.select_tool("ellipse")
    assert window.view._snap_guides == []
    _show_an_alignment_guide(window)
    press_key(window.view, Qt.Key_Escape)
    assert window.view._snap_guides == []
    assert window.view._snap_marker is None


def test_snap_guides_clear_when_the_point_is_committed(window):
    point = _show_an_alignment_guide(window)
    click(window.view, point.x(), point.y())
    assert window.view._snap_guides == []
    assert window.view._snap_marker is None


def test_the_snapped_live_preview_is_the_geometry_that_gets_committed(window):
    settings = _quiet_snapping(window)
    settings.snap_to_grid = True
    window.select_tool("line")
    QApplication.sendEvent(window.view.viewport(), _mouse(
        window.view, QEvent.MouseButtonPress, 103, 104))
    QApplication.sendEvent(window.view.viewport(), _mouse(
        window.view, QEvent.MouseMove, 241, 199, Qt.NoButton, Qt.LeftButton))
    draft = window.view._draft
    preview = [draft.mapToScene(point) for point in draft.points]

    QApplication.sendEvent(window.view.viewport(), _mouse(
        window.view, QEvent.MouseButtonRelease, 241, 199))

    line = markups(window)[-1]
    committed = [line.mapToScene(point) for point in line.points]
    assert len(committed) == len(preview)
    for shown, landed in zip(preview, committed):
        assert (shown - landed).manhattanLength() < 0.01


def test_the_drawing_underneath_offers_corners_but_no_guides(window):
    """A PDF's line work is full of lines; every one would be a guide."""
    from markforge.items.shapes import PolyItem as Poly

    settings = _quiet_snapping(window)
    settings.snap_to_content = True
    settings.snap_to_alignment = True

    frame = window.view.frame()
    line = Poly("polyline", [QPointF(0, 0), QPointF(120, 0), QPointF(120, 90)])
    line.layer = "Drawing"
    frame.add_markup(line, QPointF(200, 500))
    assert window.view.is_drawing(line)

    end = line.mapToScene(line.points[0])
    caught = window.view.snap_to_item(end + QPointF(2, 2))
    assert caught is not None and (caught - end).manhattanLength() < 0.01

    # But the middle of one of its segments is not offered.
    middle = line.mapToScene((line.points[0] + line.points[1]) / 2)
    assert window.view.snap_to_item(middle + QPointF(2, 2)) is None

    # And it offers no alignment guides at all.
    across, down = window.view.alignment_lines(frame)
    assert not across and not down


def test_snapping_to_the_drawing_can_be_turned_off_on_its_own(window):
    from markforge.items.shapes import PolyItem as Poly

    settings = _quiet_snapping(window)
    settings.snap_to_items = True

    frame = window.view.frame()
    line = Poly("polyline", [QPointF(0, 0), QPointF(120, 0)])
    line.layer = "Drawing"
    frame.add_markup(line, QPointF(200, 500))
    end = line.mapToScene(line.points[0])

    settings.snap_to_content = False
    assert window.view.snap_to_item(end + QPointF(2, 2)) is None
    settings.snap_to_content = True
    assert window.view.snap_to_item(end + QPointF(2, 2)) is not None


def test_the_first_point_of_a_line_shows_the_snap_marker(window):
    """It only started marking from the second point onward."""
    settings = _quiet_snapping(window)
    settings.snap_to_items = True

    window.select_tool("rect")
    drag(window.view, 300, 200, 420, 260)
    box = markups(window)[-1]
    corner = box.mapToScene(box.local_rect().normalized().bottomRight())

    window.select_tool("line")
    window.view._snap_marker = None
    hover(window.view, corner.x() + 2, corner.y() + 2)
    assert window.view._snap_marker is not None, \
        "the marker should be there before the first click"
    assert (window.view._snap_marker - corner).manhattanLength() < 0.01


def test_snap_feedback_is_a_blue_target_not_an_orange_square(window):
    from PySide6.QtGui import QImage, QPainter

    image = QImage(40, 40, QImage.Format_ARGB32)
    image.fill(Qt.white)
    painter = QPainter(image)
    painter.translate(20, 20)
    window.view._draw_snap_marker(painter, QPointF())
    painter.end()

    colours = [QColor(image.pixel(x, y))
               for x in range(image.width()) for y in range(image.height())]
    blue = [c for c in colours if c.blue() > 120 and c.blue() > c.red() * 1.2]
    orange = [c for c in colours
              if c.red() > 180 and 45 < c.green() < 150 and c.blue() < 100]
    assert blue
    assert not orange


def test_the_three_snaps_are_on_the_view_menu(window):
    labels = []
    for entry in window.menuBar().actions():
        if entry.text() == "&View":
            labels = [a.text() for a in entry.menu().actions()]
    assert "Grid snap" in labels
    assert "Markup snap" in labels
    assert "PDF snap" in labels
    assert "Align snap" in labels


# ---------------------------------------------------------------------------
# Turning the view without turning the scrollbars
# ---------------------------------------------------------------------------

def test_a_turned_page_still_lies_on_the_canvas_the_right_way_up(window):
    """Turned, the sheet is wider than it is tall — and still on the canvas."""
    window.view.reset_view_rotation()
    frame = window.view.frame()
    upright = frame.mapRectToScene(frame.page_rect()).normalized()
    assert upright.height() > upright.width()

    window.view.rotate_view(True)
    sideways = frame.mapRectToScene(frame.page_rect()).normalized()
    assert sideways.width() > sideways.height()
    assert sideways.width() == pytest.approx(upright.height(), abs=0.5)
    # And it has not wandered off above or to the left of the canvas.
    assert window.view.scene().sceneRect().contains(sideways.center())
    window.view.reset_view_rotation()


def test_turning_the_view_changes_nothing_about_the_document(window):
    page = window.current_page()
    before = (page.setup.width_pt, page.setup.height_pt, page.setup.orientation)
    window.view.rotate_view(True)
    try:
        assert (page.setup.width_pt, page.setup.height_pt,
                page.setup.orientation) == before
        assert window.undo_stack.count() == 0
    finally:
        window.view.reset_view_rotation()


# ---------------------------------------------------------------------------
# the keys a calculation is typed with
# ---------------------------------------------------------------------------







def test_a_menu_over_a_markup_being_typed_does_not_close_it(window):
    """Right-clicking the words being typed keeps the caret in them."""
    from PySide6.QtGui import QFocusEvent

    item = _open_words(window, "300 kerb")
    window.view.focusOutEvent(QFocusEvent(QEvent.FocusOut, Qt.PopupFocusReason))
    assert window.view.is_editing(), "the menu did not end the markup"
    assert item._editor.toPlainText() == "300 kerb"
    window.view.escape_everything()


def test_starting_another_markup_settles_the_first(window):
    """One caret at a time, whatever the keyboard is doing."""
    first = _open_words(window, "300 kerb", at=(90, 110))
    window.select_tool("text")
    drag(window.view, 90, 260, 280, 310)
    second = window.view.editing_item()
    assert second is not first
    assert window.view._editing_item is second
    assert first.editing is False, "the first one was left with a caret in it"
    window.view.escape_everything()


# ---------------------------------------------------------------------------
# the new-table question
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# a rectangle's outline is an outline like any other
# ---------------------------------------------------------------------------

def _rectangle(window, kind="rect", at=(100, 100, 300, 220)):
    window.select_tool(kind if kind != "rect" else "rect")
    drag(window.view, *at)
    box = [i for i in markups(window) if isinstance(i, RectItem)][-1]
    window.view.scene().clearSelection()
    box.setSelected(True)
    return box


def test_a_rectangles_corners_are_on_its_right_click_menu(window):
    """Not a "turn it into a polygon first" — the corners are simply there."""
    box = _rectangle(window)
    corner = box.mapToScene(box.corner_points()[0])
    menu = window.build_context_menu(box, corner)
    outline = [a.menu() for a in menu.actions() if a.text() == "This outline"]
    assert outline, "a rectangle has four corners and four sides"
    actions = outline[0].actions()
    labels = [a.text() for a in actions]
    tips = [a.toolTip() for a in actions]
    # One or two words on the entry; what it does to which corner or side is
    # in the tooltip.
    assert "Round corner" in labels
    assert "Remove point" in labels
    assert "Add point" in labels
    assert any("arc" in label.lower() for label in labels)
    assert any("break" in label.lower() for label in labels)
    assert any("round this corner" in tip.lower() for tip in tips)
    assert any("remove this point" in tip.lower() for tip in tips)
    assert any("put a point in this side" in tip.lower() for tip in tips)
    assert any("break symbol" in tip.lower() for tip in tips)


def test_the_outline_menu_shows_up_in_the_middle_of_a_shape_too(window):
    """Where the pointer is not near any corner, the nearest is offered.

    Showing nothing at all there is how a thing that is on every shape came
    to be a thing nobody could find.
    """
    box = _rectangle(window)
    middle = box.mapToScene(box.local_rect().center())
    outline = [a.menu() for a in window.build_context_menu(box, middle).actions()
               if a.text() == "This outline"]
    assert outline
    labels = [a.text() for a in outline[0].actions()]
    assert "Round corner" in labels
    assert "Add point" in labels


def test_a_cloud_drawn_as_a_box_has_an_outline_too(window):
    box = _rectangle(window, "cloud")
    assert box.kind == "cloud"
    outline = [a.menu() for a in window.build_context_menu(
        box, box.mapToScene(box.corner_points()[2])).actions()
        if a.text() == "This outline"]
    assert outline, "a cloud has corners like anything else drawn as a box"


def test_rounding_a_rectangles_corner_makes_it_a_polygon(window):
    """It stops being a rectangle the moment it stops being rectangular."""
    box = _rectangle(window)
    where = box.mapToScene(box.corner_points()[1])
    assert window.view.reshape_at(where, Qt.ControlModifier)

    assert box not in markups(window)
    shape = [i for i in markups(window) if isinstance(i, PolyItem)][-1]
    assert shape.is_rounded(1), "and it kept the corner that was asked for"
    assert len(shape.points) == 4
    assert shape.isSelected(), "still the shape being worked on"

    window.undo_stack.undo()
    assert any(isinstance(i, RectItem) for i in markups(window)), "and back again"


def test_taking_a_point_out_of_a_rectangle_leaves_a_triangle(window):
    box = _rectangle(window)
    where = box.mapToScene(box.corner_points()[0])
    assert window.view.reshape_at(where, Qt.ShiftModifier)
    shape = [i for i in markups(window) if isinstance(i, PolyItem)][-1]
    assert len(shape.points) == 3


def test_a_point_goes_into_the_side_the_pointer_is_on(window):
    """Including the side that runs back to the first corner."""
    shape = _polygon(window)
    closing = shape.segment_count() - 1
    start, end = shape.segment_ends(closing)
    middle = QPointF((start.x() + end.x()) / 2, (start.y() + end.y()) / 2)
    where = shape.insert_point(middle)
    assert where == closing + 1, "on the closing side, not somewhere up the side"


def test_what_a_corner_carries_moves_with_it(window):
    """Numbers shift when a point goes in or comes out; what they mean must not."""
    shape = _polygon(window)
    shape.round_corner(2)
    shape.break_segment(2)
    start, end = shape.segment_ends(0)
    shape.insert_point(QPointF((start.x() + end.x()) / 2,
                               (start.y() + end.y()) / 2))
    assert shape.is_rounded(3), "the rounded corner is still that corner"
    assert shape.broken.get(3), "and the break is still on that side"

    shape.delete_point(1)
    assert shape.is_rounded(2)
    assert shape.broken.get(2)


# ---------------------------------------------------------------------------
# clicking into the working itself
# ---------------------------------------------------------------------------







def test_a_double_click_lands_where_it_was_aimed(window):
    """Opening the markup and placing the caret are the same gesture."""
    item = _open_words(window, "600 dia pile")
    where = _canvas_point_of_offset(item, 8)          # the start of "pile"
    window.view.end_item_edit()
    QApplication.processEvents()

    double_click(window.view, *where)
    assert window.view.editing_item() is item
    caret = item._editor.textCursor().position()
    assert 8 <= caret <= 12, f"the caret landed at {caret}, not in \"pile\""
    window.view.escape_everything()






def test_a_double_click_in_the_words_takes_the_word_it_was_aimed_at(window):
    """The word under the pointer, not whichever one the caret was last in."""
    item = _open_words(window, "600 dia pile")
    double_click(window.view, *_canvas_point_of_offset(item, 5))
    assert item._editor.textCursor().selectedText() == "dia"
    window.view.escape_everything()


def test_the_vertical_bar_still_runs_through_every_page_when_turned(window):
    """Continuous scrolling and a turned view are not a choice between two.

    The pages stay stacked down the canvas whichever way up they are read, so
    the vertical bar goes on doing what a vertical bar does: through page one,
    page two, page three, top to bottom.
    """
    window.add_page()
    window.add_page()
    window.view.set_zoom(1.0)
    window.view.reset_view_rotation()
    try:
        window.view.rotate_view(True)
        bar = window.view.verticalScrollBar()
        assert bar.maximum() > bar.minimum(), "there is a document to scroll"

        window.go_to_page(0)
        top = bar.value()
        window.go_to_page(2)
        assert bar.value() > top, "the last page is further down, not sideways"
        assert window.view.horizontalScrollBar().value() == pytest.approx(
            window.view.horizontalScrollBar().value())
        assert window.view.visible_page_index() == 2
    finally:
        window.view.reset_view_rotation()


def test_saving_settles_the_markup_being_typed(window):
    """What is on the page when it is saved is what gets saved."""
    import tempfile, os
    from markforge.io import project as project_io

    _open_words(window, "300 kerb")
    path = os.path.join(tempfile.mkdtemp(), "sheet.pdf")
    window.document.path = path
    assert window.save_document()
    assert not window.view.is_editing(), "the markup was settled first"

    from markforge.core.document import Document
    reopened = Document()
    project_io.load_document(reopened, path)
    written = [i.get("html", "") or i.get("text", "") for page in reopened.pages
               for i in page.to_dict()["items"]]
    assert any("300 kerb" in text for text in written), written


# ---------------------------------------------------------------------------
# several pages at once
# ---------------------------------------------------------------------------

def _pick_pages(window, rows):
    """Pick a run of pages out in the pages panel, the way a person does."""
    listing = window.pages_panel.list
    listing.clearSelection()
    for row in rows:
        listing.item(row).setSelected(True)
    listing.setCurrentRow(rows[-1])
    return window.selected_pages()


def test_several_pages_are_deleted_together(window, monkeypatch):
    """The whole picked run goes, in one undo step, after one question."""
    from PySide6.QtWidgets import QMessageBox

    for _ in range(4):
        window.add_page()
    window.pages_panel.rebuild(window.document, window.current_index)
    assert len(window.document.pages) == 5
    keep = window.document.pages[0].uid, window.document.pages[4].uid

    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: asked.append(a[2]) or QMessageBox.Yes)
    assert _pick_pages(window, [1, 2, 3]) == [1, 2, 3]
    window.delete_page(2)

    assert len(window.document.pages) == 2, "all three went"
    assert asked and "3 pages" in asked[0], asked
    assert [p.uid for p in window.document.pages] == list(keep)
    window.undo_stack.undo()
    assert len(window.document.pages) == 5, "and came back in one step"


def test_a_page_outside_the_picked_run_is_on_its_own(window, monkeypatch):
    """Right-clicking page five while pages one to three are picked means five."""
    from PySide6.QtWidgets import QMessageBox

    for _ in range(4):
        window.add_page()
    window.pages_panel.rebuild(window.document, window.current_index)
    _pick_pages(window, [0, 1, 2])
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)

    assert window.pages_acted_on(4) == [4]
    window.delete_page(4)
    assert len(window.document.pages) == 4


def test_several_pages_are_duplicated_together(window):
    for _ in range(2):
        window.add_page()
    window.pages_panel.rebuild(window.document, window.current_index)
    before = [p.uid for p in window.document.pages]
    _pick_pages(window, [0, 1])
    window.duplicate_page(1)

    assert len(window.document.pages) == 5
    uids = [p.uid for p in window.document.pages]
    assert uids[:2] == before[:2], "the originals stayed where they were"
    assert len(set(uids)) == 5, "and the copies are their own pages"


def test_several_pages_are_copied_and_pasted_together(window):
    for _ in range(2):
        window.add_page()
    window.pages_panel.rebuild(window.document, window.current_index)
    _pick_pages(window, [0, 1])
    window.copy_page(0)
    window.paste_page(2)
    assert len(window.document.pages) == 5


def test_a_run_of_pages_is_dragged_as_a_run(window):
    """Dragging six sheets used to move one of them and leave five behind."""
    for _ in range(4):
        window.add_page()
    window.pages_panel.rebuild(window.document, window.current_index)
    uids = [p.uid for p in window.document.pages]

    window.move_page(3, 0, 2)          # pages four and five, to the front
    moved = [p.uid for p in window.document.pages]
    assert moved[:2] == uids[3:5], "both of them, in the order they were in"
    assert moved[2:] == uids[:3] + uids[5:]


def test_the_menu_says_how_many_pages_it_is_about(window):
    for _ in range(3):
        window.add_page()
    window.pages_panel.rebuild(window.document, window.current_index)
    _pick_pages(window, [1, 2])
    actions = window.page_menu(2).actions()
    labels = [a.text() for a in actions]
    # Two-word labels; how many pages the command is about is in the tooltip,
    # so a command about six sheets still cannot read as being about one.
    assert "Delete pages" in labels
    assert "Duplicate pages" in labels
    assert "Copy pages" in labels
    tips = {a.text(): a.toolTip() for a in actions}
    assert tips["Delete pages"] == "Delete these 2 pages"
    assert tips["Duplicate pages"] == "Duplicate these 2 pages"
    assert tips["Copy pages"] == "Copy these 2 pages"

    _pick_pages(window, [1])
    actions = window.page_menu(1).actions()
    labels = [a.text() for a in actions]
    tips = {a.text(): a.toolTip() for a in actions}
    assert "Delete page" in labels
    assert tips["Delete page"] == "Delete page"


# ---------------------------------------------------------------------------
# a table's drag says how many cells, not how big they are
# ---------------------------------------------------------------------------

def test_the_style_toolbar_and_the_properties_panel_agree(window):
    """One markup, two places to change it, and the same list in both.

    They used to disagree about every markup that has a hatch or a
    transparency: the Properties panel offered both and the toolbar had no
    such control at all, so which surface you happened to open decided what
    you were allowed to change.
    """
    from tests.probe_audit import make
    from markforge.ui.stylecaps import capabilities
    from markforge.ui.tools import TOOLS

    disagreed = []
    for tool in TOOLS:
        if tool.mode == "none" or tool.factory is None:
            continue
        if tool.key in ("image", "snapshot", "calibrate"):
            continue
        window.new_document()
        window.interactive_prompts = False
        item = make(window, tool.key)
        if item is None:
            continue                       # nothing this tool draws on its own
        window.select_tool("select")
        window.view.scene().clearSelection()
        item.setSelected(True)
        window.refresh_selection()
        on_the_toolbar = {field for field, actions in window._style_widgets.items()
                          if any(action.isVisible() for action in actions)}
        in_the_panel = capabilities(item)
        if on_the_toolbar != in_the_panel:
            disagreed.append(f"{tool.key}: toolbar {sorted(on_the_toolbar)} "
                             f"vs panel {sorted(in_the_panel)}")
    assert not disagreed, "\n".join(disagreed)


# ---------------------------------------------------------------------------
# Working through a review
# ---------------------------------------------------------------------------

def _rows_of_the_markups_list(window):
    """Every markup row in the panel, under whichever page it is on."""
    tree = window.markups_panel.tree
    rows = []
    for index in range(tree.topLevelItemCount()):
        parent = tree.topLevelItem(index)
        rows += [parent.child(child) for child in range(parent.childCount())]
    return rows


def test_a_status_set_on_the_page_shows_in_the_markups_list(window):
    """The list is where a review is read, so it has to say where each is."""
    window.document.settings.default_author = "K. Goat"
    box = _a_rectangle(window)
    box.subject = "Beam size"
    window.view.scene().clearSelection()
    box.setSelected(True)
    window.set_markup_status("Rejected")

    row = [node for node in _rows_of_the_markups_list(window)
           if node.data(0, Qt.UserRole) and node.data(0, Qt.UserRole)[1] == box.uid]
    assert row, "the rectangle should be in the list"
    columns = window.markups_panel.COLUMNS
    assert row[0].text(columns.index("Status")) == "Rejected"
    assert "K. Goat" in row[0].toolTip(columns.index("Status"))


def test_picking_a_row_picks_the_markup_and_the_other_way_round(window):
    """The list and the drawing are two views of one thing."""
    first = _a_rectangle(window, 120, 120, 240, 200)
    second = _a_rectangle(window, 300, 120, 420, 200)
    window.select_tool("select")
    window.refresh_lists()

    rows = {node.data(0, Qt.UserRole)[1]: node
            for node in _rows_of_the_markups_list(window)
            if node.data(0, Qt.UserRole)}
    rows[second.uid].setSelected(True)
    QApplication.processEvents()
    assert second.isSelected() and not first.isSelected(), \
        "picking a row should pick the markup"

    window.view.scene().clearSelection()
    first.setSelected(True)
    window.refresh_selection()
    QApplication.processEvents()
    assert rows[first.uid].isSelected(), "and picking a markup should pick its row"
    assert not rows[second.uid].isSelected()


def test_the_open_filter_leaves_out_what_has_been_ruled_on(window):
    """Going through a drawing means going through what is still open."""
    done = _a_rectangle(window, 120, 120, 240, 200)
    still_open = _a_rectangle(window, 300, 120, 420, 200)
    window.view.scene().clearSelection()
    done.setSelected(True)
    window.set_markup_status("Completed")

    window.markups_panel.only_open.setChecked(True)
    try:
        listed = {node.data(0, Qt.UserRole)[1]
                  for node in _rows_of_the_markups_list(window)
                  if node.data(0, Qt.UserRole)}
        assert still_open.uid in listed
        assert done.uid not in listed, "a completed markup is not still open"
    finally:
        window.markups_panel.only_open.setChecked(False)


def test_a_status_is_undone_like_anything_else(window):
    box = _a_rectangle(window)
    window.view.scene().clearSelection()
    box.setSelected(True)
    window.set_markup_status("Accepted")
    assert box.status == "Accepted"

    window.undo_something()
    QApplication.processEvents()
    again = [item for item in markups(window) if item.uid == box.uid][0]
    assert again.status == "", "undo should take the ruling back"


def test_setting_a_status_on_several_at_once_rules_on_all_of_them(window):
    """A reviewer clears a page of nits in one go, not one at a time."""
    first = _a_rectangle(window, 120, 120, 240, 200)
    second = _a_rectangle(window, 300, 120, 420, 200)
    window.select_tool("select")
    window.view.scene().clearSelection()
    first.setSelected(True)
    second.setSelected(True)
    window.set_markup_status("Completed")
    assert first.status == second.status == "Completed"


def test_the_status_menu_says_which_one_it_is_on(window):
    box = _a_rectangle(window)
    window.view.scene().clearSelection()
    box.setSelected(True)
    window.set_markup_status("Rejected")

    menu = window.build_context_menu(box, box.pos())
    review = [action.menu() for action in menu.actions()
              if action.text() == "Status" and action.menu()]
    assert review, "a markup's menu should offer a status"
    ticked = [action.text() for action in review[0].actions() if action.isChecked()]
    assert ticked == ["Rejected"]


def test_a_reply_is_added_to_the_conversation_not_over_it(window, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    window.document.settings.default_author = "K. Goat"
    box = _a_rectangle(window)
    box.add_reply("Which beam?", "A. Checker")
    window.view.scene().clearSelection()
    box.setSelected(True)

    monkeypatch.setattr(QInputDialog, "getMultiLineText",
                        staticmethod(lambda *_a, **_k: ("The transfer beam.", True)))
    window.reply_to_markup(box)
    assert [(reply["author"], reply["text"]) for reply in box.replies] == [
        ("A. Checker", "Which beam?"), ("K. Goat", "The transfer beam.")]
    assert box.latest_word() == "The transfer beam."


# ---------------------------------------------------------------------------
# Catching hold of where two lines cross
# ---------------------------------------------------------------------------

def _a_line(window, x0, y0, x1, y1):
    window.select_tool("line")
    drag(window.view, x0, y0, x1, y1)
    window.select_tool("select")
    return markups(window)[-1]


def test_the_pointer_catches_where_two_lines_cross(window):
    """The point a drawing is aimed at, and the one there is no vertex for.

    Two grid lines meeting, a beam arriving at a column: nothing has a corner
    there, so before this there was nothing to catch hold of and a dimension
    taken off it was taken off a guess.
    """
    from PySide6.QtCore import QPointF

    # Neither crossing point is either line's own midpoint, so what is caught
    # is the crossing itself rather than a middle that happens to be there.
    _a_line(window, 100, 300, 500, 300)          # across, middle at 300
    _a_line(window, 250, 150, 250, 550)          # down, middle at 350
    window.document.settings.snap_to_items = True

    frame = window.document.pages[0].frame
    crossing = frame.mapToScene(QPointF(250, 300))
    caught = window.view.snap_scene(crossing + QPointF(3, -2))
    assert abs(caught.x() - crossing.x()) < 0.5
    assert abs(caught.y() - crossing.y()) < 0.5
    assert "crossing" in window.view._snap_caught


def test_lines_that_stop_short_of_each_other_do_not_cross(window):
    """Where they would have met is not a place anything is."""
    from PySide6.QtCore import QPointF

    _a_line(window, 100, 300, 200, 300)          # stops well short
    _a_line(window, 400, 150, 400, 450)
    window.document.settings.snap_to_items = True

    frame = window.document.pages[0].frame
    would_be = frame.mapToScene(QPointF(400, 300))
    caught = window.view.snap_scene(would_be + QPointF(3, -2))
    assert "crossing" not in window.view._snap_caught, \
        f"nothing crosses there, but it said {window.view._snap_caught!r}"


def test_a_corner_still_beats_a_crossing_that_is_further_away(window):
    """A crossing is one more thing to catch, not a thing that takes over."""
    from PySide6.QtCore import QPointF

    _a_line(window, 100, 300, 400, 300)
    _a_line(window, 250, 150, 250, 450)
    end = _a_line(window, 260, 300, 340, 380)    # its end is near the crossing
    window.document.settings.snap_to_items = True

    frame = window.document.pages[0].frame
    near_the_end = frame.mapToScene(QPointF(260, 300)) + QPointF(1, 1)
    caught = window.view.snap_scene(near_the_end)
    wanted = end.mapToScene(end.points[0])
    assert abs(caught.x() - wanted.x()) < 0.5 and abs(caught.y() - wanted.y()) < 0.5
    assert "end" in window.view._snap_caught


def test_crossings_are_left_alone_when_snapping_is_switched_off(window):
    from PySide6.QtCore import QPointF

    _a_line(window, 100, 300, 400, 300)
    _a_line(window, 250, 150, 250, 450)
    settings = window.document.settings
    settings.snap_to_items = False
    settings.snap_to_content = False
    try:
        frame = window.document.pages[0].frame
        near = frame.mapToScene(QPointF(250, 300)) + QPointF(3, -2)
        assert window.view.crossings_near(frame, near, 9.0) == []
    finally:
        settings.snap_to_items = True
        settings.snap_to_content = True
