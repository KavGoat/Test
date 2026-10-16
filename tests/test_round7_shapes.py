"""Round 7 (2026-10-16), the user's corrections to round 6, driven the way a
person drives them — real presses on the viewport where things are drawn,
menus opened from the menu bar, popups read from the one that opens:

1. no group resize: several selected markups each keep their own handles,
   and a handle resizes only its own markup;
2. Revu's Sketch to Scale Rectangle and Ellipse, which ask for a scale and
   are sized in real units, beside the plain ones, sized on the paper;
3. a text box is dragged out: a click alone places nothing.
"""
from __future__ import annotations

import time

import pytest
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QMenu

from calcforge.items.shapes import RectItem
from calcforge.items.text import TextItem
from tests.test_markup_interaction_round6 import (click, drag, heading, key, markups,
                                                  move, page, press, pump, release,
                                                  right_click_menu, scene_rect, screen,
                                                  vp, watching)


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.view.set_zoom(1.0)
    pump()
    return window


def newest(w, before):
    """The rectangle that was not there *before* (the list is in z order)."""
    (made,) = [m for m in markups(w, RectItem) if m not in before]
    return made


def draw(w, tool, x, y, width, height):
    before = set(markups(w, RectItem))
    w.select_tool(tool)
    drag(w, page(w, x, y), page(w, x + width, y + height))
    w.select_tool("select")
    return newest(w, before)


def scaled(w, ratio=50):
    from calcforge.core.document import PageScale
    w.current_page().scale = PageScale.from_ratio(ratio)
    w.refresh_page_measurements(w.current_page())


def menu_bar_pick(w, *path):
    """Open the menu bar's *path[0]* with the mouse, then each submenu, and
    click the last entry — the way a person does."""
    bar = w.menuBar()
    top = next(a for a in bar.actions() if a.text().replace("&", "") == path[0])
    QTest.mouseClick(bar, Qt.LeftButton, Qt.NoModifier, bar.actionGeometry(top).center())
    pump(3)
    menu = QApplication.activePopupWidget()
    assert isinstance(menu, QMenu), "the menu opened"
    for name in path[1:]:
        entry = next(a for a in menu.actions() if a.text().replace("&", "") == name)
        QTest.mouseMove(menu, menu.actionGeometry(entry).center())
        QTest.mouseClick(menu, Qt.LeftButton, Qt.NoModifier,
                         menu.actionGeometry(entry).center())
        pump(3)
        if entry.menu() is not None:
            menu = entry.menu()
            for _ in range(10):
                if menu.isVisible():
                    break
                pump()
            assert menu.isVisible(), f"{name} opened"
    pump()
    for _ in range(4):
        popup = QApplication.activePopupWidget()
        if popup is None:
            break
        popup.close()
        pump()
    from tests.test_markup_interaction_round6 import back_to_the_window
    back_to_the_window(w)


def form_rows(group) -> dict:
    """{label: field} in a Properties group."""
    from PySide6.QtWidgets import QFormLayout
    form = group.findChildren(QFormLayout)[0]
    rows = {}
    for row in range(form.rowCount()):
        label = form.itemAt(row, QFormLayout.LabelRole)
        field = form.itemAt(row, QFormLayout.FieldRole)
        if label is not None and label.widget() is not None and field is not None:
            rows[label.widget().text()] = field.widget()
    return rows


def group(w, title):
    from PySide6.QtWidgets import QGroupBox
    return next((g for g in w.properties_panel.findChildren(QGroupBox)
                 if g.title() == title and g.isVisibleTo(w.properties_panel)), None)


# -- 1. no group resize -------------------------------------------------------------

def test_several_selected_each_keep_their_own_handles_and_resize_alone(w):
    one = draw(w, "rect", 100, 200, 100, 60)
    two = draw(w, "rect", 300, 300, 100, 60)
    key(w, Qt.Key_A, Qt.ControlModifier)
    assert one.isSelected() and two.isSelected()
    assert w.view.scene().many_selected()
    assert not hasattr(w.view, "_selection_box"), "no box round the lot"
    # the corner of the second one's own handle resizes it, and only it
    size_one, size_two = scene_rect(one).size(), scene_rect(two).size()
    start_one = scene_rect(one).topLeft()
    corner = two.mapToScene(two.handle_points()["se"])
    drag(w, corner, corner + QPointF(40, 30))
    assert scene_rect(two).width() == pytest.approx(size_two.width() + 40, abs=1.5)
    assert scene_rect(two).height() == pytest.approx(size_two.height() + 30, abs=1.5)
    assert scene_rect(one).size() == size_one and scene_rect(one).topLeft() == start_one
    # the same on the first one's side handle
    side = one.mapToScene(one.handle_points()["e"])
    drag(w, side, side + QPointF(25, 0))
    assert scene_rect(one).width() == pytest.approx(size_one.width() + 25, abs=1.5)
    # both still selected, and the edge of either moves the pair together
    assert one.isSelected() and two.isSelected()
    before = [scene_rect(one).topLeft(), scene_rect(two).topLeft()]
    # its top stroke, a quarter of the way along: clear of its handles
    edge = one.mapToScene(QPointF(one.local_rect().left() + one.local_rect().width() / 4,
                                  one.local_rect().top()))
    drag(w, edge, edge + QPointF(20, 15))
    for was, item in zip(before, (one, two)):
        moved = scene_rect(item).topLeft() - was
        assert moved.x() == pytest.approx(20, abs=1.5) and moved.y() == pytest.approx(15, abs=1.5)
    # undo takes back the move, then each resize on its own
    key(w, Qt.Key_Z, Qt.ControlModifier)
    key(w, Qt.Key_Z, Qt.ControlModifier)
    one, two = markups(w, RectItem)
    assert scene_rect(one).width() == pytest.approx(size_one.width(), abs=0.5)
    assert scene_rect(two).width() == pytest.approx(size_two.width() + 40, abs=1.5)


def test_every_selected_markup_paints_its_own_control_points(w):
    one = draw(w, "rect", 100, 200, 100, 60)
    two = draw(w, "ellipse", 300, 300, 100, 60)
    click(w, scene_rect(one).center())
    click(w, scene_rect(two).center(), Qt.ShiftModifier)
    assert one.isSelected() and two.isSelected()
    pump(3)
    image = vp(w).grab().toImage()
    for item in (one, two):
        for name in ("nw", "se"):
            at = screen(w, item.mapToScene(item.handle_points()[name]))
            colour = image.pixelColor(at.x(), at.y())
            # a gold control point, not white paper
            assert colour.red() > 180 and colour.blue() < 120, (item, name, colour.name())
    # and nothing is drawn at the corner of a box round the pair
    both = scene_rect(one).united(scene_rect(two))
    at = screen(w, both.topRight())
    assert image.pixelColor(at.x(), at.y()).lightness() > 230


def test_a_handle_of_a_multi_selection_takes_the_press_only_on_its_square(w):
    one = draw(w, "rect", 100, 200, 120, 80)
    two = draw(w, "rect", 300, 200, 120, 80)
    key(w, Qt.Key_A, Qt.ControlModifier)
    w.view.set_zoom(3.0)
    w.view.centerOn(scene_rect(one).center())
    pump()
    size = scene_rect(one).size()
    start_two = scene_rect(two).topLeft()
    pixel = 1.0 / w.view.transform().m11()
    off = one.mapToScene(one.handle_points()["e"]) + QPointF(6 * pixel, 0)
    drag(w, off, off + QPointF(40, 0))
    # off the dot: on the stroke, so the pair moved and neither resized
    assert scene_rect(one).size() == size
    assert (scene_rect(two).topLeft() - start_two).x() == pytest.approx(40, abs=1.5)


def test_a_group_still_has_its_box(w):
    one = draw(w, "rect", 100, 200, 100, 60)
    two = draw(w, "rect", 300, 300, 100, 60)
    key(w, Qt.Key_A, Qt.ControlModifier)
    w.group_selection()
    pump()
    grouped = w.view._selected_group()
    assert grouped is not None
    _members, box = grouped
    drag(w, box.bottomRight(), box.bottomRight() + QPointF(box.width(), box.height()))
    one, two = markups(w, RectItem)
    whole = scene_rect(one).united(scene_rect(two))
    assert whole.width() == pytest.approx(2 * box.width(), abs=3)


# -- 2. plain shapes and Sketch to Scale ---------------------------------------------

def test_a_plain_rectangle_is_sized_on_the_paper_even_on_a_scaled_page(w):
    from calcforge.items.shapes import PAPER_UNITS
    w.interactive_prompts = True
    asked = []
    keep = watching(lambda d: (asked.append(d.windowTitle()), d.reject()))
    rect = draw(w, "rect", 100, 200, 4 * 72 / 2.54, 2 * 72 / 2.54)    # 4 cm × 2 cm
    keep.stop()
    assert asked == [] and not rect.to_scale
    assert rect.subject == "Rectangle" and rect.show_size is False
    scaled(w)
    rect.set_local_rect(QRectF(0, 0, 4 * 72 / 2.54, 2 * 72 / 2.54))
    rect.refresh(page=w.current_page())
    assert rect.size_text == "4.00 cm × 2.00 cm"            # the rulers' cm
    click(w, scene_rect(rect).center())
    assert heading(w) == "Rectangle Properties"
    layout = form_rows(group(w, "Layout"))
    assert "Document Width:" in layout and "Document Height:" in layout
    from PySide6.QtWidgets import QDoubleSpinBox
    width = layout["Document Width:"].findChild(QDoubleSpinBox)
    assert width.value() == pytest.approx(4.0, abs=0.01)
    assert [label.text() for label in layout["Document Width:"].findChildren(QLabel)] == ["cm"]
    assert group(w, "Sketch to Scale") is None
    # typing a Document Width resizes it on the paper
    width.selectAll()
    width.setFocus()
    QTest.keyClicks(width, "6")
    QTest.keyClick(width, Qt.Key_Return)
    pump()
    assert scene_rect(rect).width() == pytest.approx(6 * PAPER_UNITS["cm"][0], abs=0.2)


def test_the_paper_units_follow_the_rulers_right_click(w):
    rect = draw(w, "rect", 100, 200, 72, 36)
    rect.set_local_rect(QRectF(0, 0, 72, 36))              # 1 in × 0.5 in
    w.show_rulers(True)
    pump()
    click(w, scene_rect(rect).center())
    ruler = w.view.rulers.top
    got = {}

    def choose(menu):
        got["labels"] = [a.text() for a in menu.actions()]
        target = next(a for a in menu.actions() if a.text() == "Inches")
        QTest.mouseClick(menu, Qt.LeftButton, Qt.NoModifier,
                         menu.actionGeometry(target).center())
    keep = watching(choose)
    at = QPoint(ruler.width() // 2, ruler.height() // 2)
    QTest.mouseClick(ruler, Qt.RightButton, Qt.NoModifier, at)
    pump()
    if "labels" not in got:
        from PySide6.QtGui import QContextMenuEvent
        QApplication.sendEvent(ruler, QContextMenuEvent(
            QContextMenuEvent.Mouse, at, ruler.mapToGlobal(at)))
        pump()
    keep.stop()
    assert "Inches" in got.get("labels", [])
    pump(3)
    assert rect.size_text == "1.00 in × 0.50 in"
    layout = form_rows(group(w, "Layout"))
    assert [label.text() for label in layout["Document Width:"].findChildren(QLabel)] == ["in"]


def test_sketch_to_scale_is_on_the_tools_menu_and_asks_for_a_scale(w):
    w.interactive_prompts = True
    menu_bar_pick(w, "Tools", "Sketch to Scale", "Rectangle")      # Revu's names there
    assert w.view.tool_key == "sketch_rect"
    asked = []

    def cancel(dialog):
        asked.append(dialog.windowTitle())
        dialog.reject()
    keep = watching(cancel)
    drag(w, page(w, 150, 250), page(w, 300, 330))
    pump(3)
    keep.stop()
    assert len(asked) == 1, asked
    (rect,) = markups(w, RectItem)
    assert rect.to_scale and rect.subject == "Sketch to Scale Rectangle"
    assert not w.current_page().scale.is_calibrated()
    assert w.status_scale.text() == "Scale Not Set"
    click(w, scene_rect(rect).center())
    assert heading(w) == "Sketch to Scale Rectangle Properties"
    sketch = group(w, "Sketch to Scale")
    assert sketch is not None
    assert sketch.findChild(QLabel, "sketchNoScale") is not None
    # the ellipse, from the same menu
    menu_bar_pick(w, "Tools", "Sketch to Scale", "Ellipse")
    assert w.view.tool_key == "sketch_ellipse"


def test_sketch_to_scale_typed_in_real_units_while_drawing_and_in_properties(w):
    scaled(w, 50)
    w.select_tool("sketch_rect")
    click(w, page(w, 150, 250))                        # first corner; size bar opens
    editor = w.view._size_editor
    assert editor is not None and w.view._size_width.hasFocus()
    caption = [l.text() for l in editor.findChildren(QLabel)]
    assert "m" in caption
    # typed on the keyboard: the keys go where the focus is, the width field
    keyboard = QApplication.focusWidget()
    QTest.keyClicks(keyboard, "3")
    QTest.keyClick(keyboard, Qt.Key_Tab)
    pump()
    assert w.view._size_height.hasFocus()
    QTest.keyClicks(QApplication.focusWidget(), "1.5")
    QTest.keyClick(QApplication.focusWidget(), Qt.Key_Return)
    pump()
    (rect,) = markups(w, RectItem)
    assert rect.to_scale
    assert rect.size_text == "3.00 m × 1.50 m"
    click(w, scene_rect(rect).center())
    rows = form_rows(group(w, "Sketch to Scale"))
    assert rows["Width:"].text() == "3.00 m" and rows["Height:"].text() == "1.50 m"
    # typed in Properties, in real units
    width = rows["Width:"]
    QTest.mouseClick(width, Qt.LeftButton)
    width.selectAll()
    QTest.keyClicks(width, "4 m")
    QTest.keyClick(width, Qt.Key_Return)
    pump()
    (rect,) = markups(w, RectItem)
    assert rect.size_text == "4.00 m × 1.50 m"
    assert rect.local_rect().width() == pytest.approx(4000 / (50 * 25.4 / 72), rel=1e-3)
    # the plain rectangle drawn beside it, typed on the paper
    before = set(markups(w, RectItem))
    w.select_tool("rect")
    click(w, page(w, 150, 450))
    caption = [l.text() for l in w.view._size_editor.findChildren(QLabel)]
    assert "cm" in caption
    QTest.keyClicks(QApplication.focusWidget(), "5")
    QTest.keyClick(QApplication.focusWidget(), Qt.Key_Tab)
    pump()
    QTest.keyClicks(QApplication.focusWidget(), "2")
    QTest.keyClick(QApplication.focusWidget(), Qt.Key_Return)
    pump()
    plain = newest(w, before)
    assert not plain.to_scale and plain.size_text == "5.00 cm × 2.00 cm"


def test_sketch_to_scale_on_the_measure_toolbar_with_its_own_icons(w):
    from PySide6.QtWidgets import QToolButton
    from calcforge.ui.icons import icon
    measure = next(bar for bar in w.toolbars if bar.objectName() == "toolbar_measure")
    button = measure.findChild(QToolButton, "sketchToScaleButton")
    assert button is not None and button.isVisible()
    assert button.geometry().right() < measure.width()
    for key_, plain in (("sketch_rect", "rect"), ("sketch_ellipse", "ellipse")):
        action = w.tool_actions[key_]
        assert action in button.menu().actions()
        assert action.shortcut().isEmpty()
        mine = icon(key_).pixmap(22, 22).toImage()
        other = icon(plain).pixmap(22, 22).toImage()
        assert mine != other, f"{key_} has its own icon"
    # Main, Calculation and Measure still share a row at 1280 px
    main = next(bar for bar in w.toolbars if bar.objectName() == "toolbar_main")
    assert measure.y() == main.y()
    # the button itself picks the rectangle
    QTest.mouseClick(button, Qt.LeftButton, Qt.NoModifier, QPoint(10, button.height() // 2))
    pump()
    assert w.view.tool_key == "sketch_rect" and button.isChecked()
    # its arrow opens the list; the ellipse picked from it with the mouse
    got = {}

    def pick(menu):
        got["labels"] = [a.text() for a in menu.actions()]
        target = next(a for a in menu.actions() if a.text() == "Sketch to Scale Ellipse")
        QTest.mouseClick(menu, Qt.LeftButton, Qt.NoModifier,
                         menu.actionGeometry(target).center())
    keep = watching(pick)
    QTest.mouseClick(button, Qt.LeftButton, Qt.NoModifier,
                     QPoint(button.width() - 4, button.height() // 2))
    pump(3)
    keep.stop()
    assert got.get("labels") == ["Sketch to Scale Rectangle", "Sketch to Scale Ellipse"]
    assert w.view.tool_key == "sketch_ellipse"
    assert button.defaultAction() is w.tool_actions["sketch_ellipse"] and button.isChecked()
    # Customise Toolbars without the ellipse: the button keeps the rectangle
    w.visible_tools = [k for k in w.visible_tool_keys() if k != "sketch_ellipse"]
    w.apply_visible_tools()
    assert button.defaultAction() is w.tool_actions["sketch_rect"]
    w.visible_tools = [k for k in w.visible_tool_keys() if k != "sketch_rect"]
    w.apply_visible_tools()
    pump()
    assert not button.isVisible()


def test_sketch_to_scale_in_customise_toolbars_and_the_key_list(w):
    from calcforge.ui import dialogs
    from calcforge.ui.tools import TOOLS
    dialog = dialogs.ToolbarDialog(TOOLS, {t.key for t in TOOLS}, w)
    assert {"sketch_rect", "sketch_ellipse"} <= set(dialog.boxes)
    assert dialog.boxes["sketch_rect"].text() == "Sketch to Scale Rectangle"
    dialog.close()
    bindings = {b.action_id: b for b in w.shortcuts.bindings()}
    for key_ in ("sketch_rect", "sketch_ellipse"):
        assert f"tool.{key_}" in bindings
        assert bindings[f"tool.{key_}"].default == ""


def test_a_sketch_to_scale_rectangle_goes_to_the_tool_chest_and_back(w):
    from calcforge.ui import toolsets
    rect = draw(w, "sketch_rect", 100, 200, 100, 60)
    rect.style.stroke = "#2f9e44"
    centre = scene_rect(rect).center()
    click(w, centre)
    got = {}

    def keep_it(menu):
        got["labels"] = [a.text() for a in menu.actions() if a.text()]
        chest = next(a for a in menu.actions() if a.text() == "Add to Tool Chest")
        QTest.mouseMove(menu, menu.actionGeometry(chest).center())
        QTest.mouseClick(menu, Qt.LeftButton, Qt.NoModifier,
                         menu.actionGeometry(chest).center())
        sub = chest.menu()
        for _ in range(20):
            if sub.isVisible():
                break
            QApplication.processEvents()
        mine = next(a for a in sub.actions() if a.text() == toolsets.MY_TOOLS)
        QTest.mouseClick(sub, Qt.LeftButton, Qt.NoModifier,
                         sub.actionGeometry(mine).center())
    keep = watching(keep_it)
    from PySide6.QtGui import QContextMenuEvent
    local = screen(w, centre)
    QTest.mousePress(vp(w), Qt.RightButton, Qt.NoModifier, local)
    QTest.mouseRelease(vp(w), Qt.RightButton, Qt.NoModifier, local)
    pump()
    if "labels" not in got:
        QApplication.sendEvent(vp(w), QContextMenuEvent(
            QContextMenuEvent.Mouse, local, vp(w).mapToGlobal(local)))
        pump()
    keep.stop()
    assert "Add to Tool Chest" in got.get("labels", [])
    mine = next(g for g in toolsets.load_toolsets() if g.name == toolsets.MY_TOOLS)
    assert len(mine.entries) == 1
    # put down again from the Tool Chest: a Sketch to Scale rectangle still
    w.use_tool_entry(mine.entries[0])
    click(w, page(w, 400, 400))
    pump()
    copies = [m for m in markups(w, RectItem) if m is not rect]
    assert len(copies) == 1 and copies[0].to_scale and copies[0].style.stroke == "#2f9e44"
    # kept as properties, it draws with Sketch to Scale's tool
    entry = toolsets.entry_for(rect, toolsets.PROPERTIES)
    w.use_tool_entry(entry)
    assert w.view.tool_key == "sketch_rect"
    before = set(markups(w, RectItem))
    drag(w, page(w, 100, 500), page(w, 200, 560))
    drawn = newest(w, before)
    assert drawn.to_scale and drawn.style.stroke == "#2f9e44"
    plain = draw(w, "rect", 300, 200, 100, 60)
    assert w._tool_for_payload(toolsets.entry_for(plain, toolsets.PROPERTIES).payload) == "rect"
    # a plain rectangle's default never turns into Sketch to Scale's
    assert toolsets.default_key(rect) != toolsets.default_key(plain)
    toolsets.apply_properties(plain, toolsets.properties_of(rect))
    assert not plain.to_scale and plain.style.stroke == "#2f9e44"


def test_a_sketch_to_scale_rectangle_keeps_its_own_markup_styles(w):
    from calcforge.ui.markupstyles import styled, styles_for
    assert styled("sketch_rect") and styled("sketch_ellipse")
    rect = draw(w, "sketch_rect", 100, 200, 100, 60)
    centre = scene_rect(rect).center()
    click(w, centre)
    labels = right_click_menu(w, centre, pick="Save as Markup Style")
    assert "Save as Markup Style" in labels
    pump()
    assert len(styles_for("sketch_rect")) == 1 and styles_for("rect") == []
    w.select_tool("sketch_rect")
    key(w, Qt.Key_1)
    w.properties_panel.show_items([])
    assert heading(w) == "Sketch to Scale Rectangle Style 1"


def test_each_kind_reopens_as_itself_and_old_files_stay_plain(w, tmp_path):
    from tests.test_calc_saving import save_to
    scaled(w, 50)
    draw(w, "rect", 100, 100, 100, 60)
    draw(w, "sketch_rect", 100, 250, 100, 60)
    draw(w, "ellipse", 300, 100, 100, 60)
    draw(w, "sketch_ellipse", 300, 250, 100, 60)
    path = str(tmp_path / "shapes.pdf")
    save_to(w, path)
    w.open_from_command_line(path)
    pump(3)
    kinds = sorted((m.kind, m.to_scale) for m in markups(w, RectItem))
    assert kinds == [("ellipse", False), ("ellipse", True), ("rect", False), ("rect", True)]
    sketch = next(m for m in markups(w, RectItem) if m.to_scale and m.kind == "rect")
    sketch.refresh(page=w.current_page())
    assert sketch.size_text.endswith(" m")
    # written before Sketch to Scale existed: no flag, so a plain rectangle
    old = RectItem()
    data = sketch.serialize()
    data.pop("to_scale")
    old.deserialize(data)
    assert old.to_scale is False and old.NAME_FOR_KIND == "Rectangle"


# -- 3. a text box is dragged out ----------------------------------------------------

def test_a_click_with_the_text_box_tool_places_nothing_and_a_drag_does(w):
    click(w, page(w, 600, 600))
    key(w, Qt.Key_T)                              # Revu's key for the Text Box tool
    assert w.view.tool_key == "text"
    click(w, page(w, 200, 300))
    pump()
    assert markups(w, TextItem) == []
    assert w.view.editing_item() is None
    assert w.view.tool_key == "text", "the tool stays ready"
    # the drag makes the box at that size with the caret in it
    drag(w, page(w, 100, 400), page(w, 400, 460))
    box = w.view.editing_item()
    assert isinstance(box, TextItem)
    assert box.local_rect().width() == pytest.approx(300, abs=3)
    assert box.local_rect().height() == pytest.approx(60, abs=3)
    # what is typed next goes into the box, with no key taken as a tool's
    QTest.keyClicks(QApplication.focusWidget() or vp(w), "Hello there")
    pump()
    assert box.text() == "Hello there"
    assert w.view.tool_key in ("select", "text")
    key(w, Qt.Key_Escape)
    assert [m.text() for m in markups(w, TextItem)] == ["Hello there"]
    # and one undo takes the box and its words back (exercise round 1, F-05)
    key(w, Qt.Key_Z, Qt.ControlModifier)
    assert markups(w, TextItem) == []
