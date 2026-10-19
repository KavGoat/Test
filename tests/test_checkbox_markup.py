"""The Checkbox markup (the user, 2026-10-19): options with boxes to tick, as
one markup typed like a text box.

Driven through the real window — the tool, the mouse on its boxes, the keys
typed into it, the Properties panel and toolbar, the Markups List, Alt+Z —
and saved to PDF, read back here and drawn by another reader (MuPDF).
"""
from __future__ import annotations

import pymupdf
import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QListWidget, QToolButton

from calcforge.items.checkbox import CheckboxItem, _ticks_after
from tests.test_calc_saving import reopen, save_to
from tests.test_usability import click, double_click, drag, markups, on_page, press_key, \
    type_text


def checkboxes(window):
    return [i for i in markups(window) if isinstance(i, CheckboxItem)]


def place(window, x=100, y=100, words=None):
    """A Checkbox put down with a click of its tool; *words* typed over its
    one default option."""
    window.select_tool("checkbox")
    click(window.view, *on_page(window, 0, x, y))
    (item,) = checkboxes(window)
    if words is not None:
        assert window.view.editing_item() is item
        for number, line in enumerate(words):
            if number:
                press_key(window.view, Qt.Key_Return)
            type_text(window.view, line)
    window.view.end_item_edit()
    QApplication.processEvents()
    return item


def box_point(window, item, index):
    """Where option *index*'s box is, on the canvas."""
    box = item.box_rects()[index]
    point = item.mapToScene(box.center())
    return point.x(), point.y()


def word_point(window, item, index):
    box = item.box_rects()[index]
    point = item.mapToScene(QPointF(box.right() + item.gutter() * 1.5, box.center().y()))
    return point.x(), point.y()


def picture_of(item, scale=4.0) -> QImage:
    """The item drawn on its own, on white."""
    rect = item.boundingRect()
    image = QImage(int(rect.width() * scale) + 2, int(rect.height() * scale) + 2,
                   QImage.Format_ARGB32)
    image.fill(QColor("#ffffff"))
    painter = QPainter(image)
    painter.scale(scale, scale)
    painter.translate(-rect.left(), -rect.top())
    item.paint_content(painter)
    painter.end()
    return image


def dark_in(image: QImage, rect: QRectF, item, scale=4.0) -> int:
    """How many dark pixels the image has inside *rect* (item coordinates)."""
    origin = item.boundingRect().topLeft()
    left = int((rect.left() - origin.x()) * scale)
    top = int((rect.top() - origin.y()) * scale)
    right = int((rect.right() - origin.x()) * scale)
    bottom = int((rect.bottom() - origin.y()) * scale)
    count = 0
    for x in range(max(left, 0), min(right, image.width())):
        for y in range(max(top, 0), min(bottom, image.height())):
            if QColor(image.pixel(x, y)).lightness() < 128:
                count += 1
    return count


# -- placing and typing ----------------------------------------------------

def test_a_click_places_one_option_ready_to_type_over(window):
    """The user, 2026-10-19: "place a checkbox with one entry only and no
    drag to place"."""
    window.select_tool("checkbox")
    click(window.view, *on_page(window, 0, 100, 100))
    (item,) = checkboxes(window)
    assert item.options() == ["Option 1"]
    assert item.ticks() == [False]
    assert item.subject == "Checkbox"
    assert window.view.editing_item() is item
    width, height = item.natural_size()
    assert item.local_rect().width() == pytest.approx(width, abs=0.5)
    assert item.local_rect().height() == pytest.approx(height, abs=0.5)
    # typed over: the options are what was typed
    type_text(window.view, "Satisfactory")
    press_key(window.view, Qt.Key_Return)
    type_text(window.view, "Unsatisfactory")
    window.view.end_item_edit()
    assert item.options() == ["Satisfactory", "Unsatisfactory"]
    window.undo_stack.undo()
    assert not checkboxes(window), "one undo takes back the Checkbox and its words"


def test_a_drag_places_it_where_it_began_at_its_own_size(window):
    window.select_tool("checkbox")
    drag(window.view, *on_page(window, 0, 100, 100), *on_page(window, 0, 300, 160))
    (item,) = checkboxes(window)
    width, height = item.natural_size()
    assert item.local_rect().width() == pytest.approx(width, abs=0.5), "not the size dragged"
    assert item.options() == ["Option 1"]


def test_enter_adds_an_option_backspace_joins_and_ticks_stay_with_their_option(window):
    item = place(window, words=["A", "B", "C"])
    item.set_checked(1, True)                          # B
    window.view.begin_item_edit(item)
    editor = item._editor
    cursor = editor.textCursor()
    cursor.setPosition(0)
    editor.setTextCursor(cursor)
    press_key(window.view, Qt.Key_Return)              # a new first line
    assert item.options() == ["", "A", "B", "C"]
    assert item.ticks() == [False, False, True, False], "B keeps its tick"
    press_key(window.view, Qt.Key_Up)                  # onto the new line
    type_text(window.view, "Z")
    assert item.options() == ["Z", "A", "B", "C"]
    assert item.ticks() == [False, False, True, False]
    # Backspace at the start of B joins it to A: the joined option is ticked
    cursor = editor.textCursor()
    cursor.setPosition(item.doc.findBlockByNumber(2).position())
    editor.setTextCursor(cursor)
    press_key(window.view, Qt.Key_Backspace)
    assert item.options() == ["Z", "AB", "C"]
    assert item.ticks() == [False, True, False]
    # Enter in the middle: the first half keeps the tick
    cursor.setPosition(item.doc.findBlockByNumber(1).position() + 1)
    editor.setTextCursor(cursor)
    press_key(window.view, Qt.Key_Return)
    assert item.options() == ["Z", "A", "B", "C"]
    assert item.ticks() == [False, True, False, False]
    window.view.end_item_edit()


def test_ticks_follow_their_words():
    assert _ticks_after(["a", "b"], [True, False], ["x", "a", "b"]) == [False, True, False]
    assert _ticks_after(["a", "b", "c"], [False, True, False], ["a", "c"]) == [False, False]
    assert _ticks_after(["a", "b"], [False, True], ["ab"]) == [True]
    assert _ticks_after(["ab"], [True], ["a", "b"]) == [True, False]
    assert _ticks_after(["a"], [True], ["a typed"]) == [True]


# -- ticking -----------------------------------------------------------------

def test_a_click_on_a_box_ticks_it_as_one_undo_step(window):
    item = place(window, words=["Satisfactory", "Unsatisfactory", "N/A"])
    window.select_tool("select")
    window.scene.clearSelection()
    steps = window.undo_stack.count()
    click(window.view, *box_point(window, item, 0))
    assert item.ticks() == [True, False, False]
    assert item.isSelected(), "and it picks the markup out"
    assert window.undo_stack.count() == steps + 1
    assert item.checked_text() == "Satisfactory"
    click(window.view, *box_point(window, item, 2))
    assert item.checked_text() == "Satisfactory; N/A", "several, by default"
    window.undo_stack.undo()
    assert item_now(window).ticks() == [True, False, False]
    click(window.view, *box_point(window, item_now(window), 0))
    assert item_now(window).ticks() == [False, False, False], "a second click unticks"


def item_now(window):
    (item,) = checkboxes(window)            # undo rebuilds the page's markups
    return item


def test_a_click_off_the_boxes_only_selects(window):
    item = place(window, words=["A", "B"])
    window.select_tool("select")
    window.scene.clearSelection()
    steps = window.undo_stack.count()
    click(window.view, *word_point(window, item, 0))
    assert item.isSelected()
    assert item.ticks() == [False, False]
    assert window.undo_stack.count() == steps
    double_click(window.view, *word_point(window, item, 1))
    assert window.view.editing_item() is item, "a double-click on the words edits them"
    window.view.end_item_edit()


def test_a_locked_checkbox_is_not_ticked(window):
    item = place(window, words=["A", "B"])
    window.select_tool("select")
    item.set_locked(True)
    click(window.view, *box_point(window, item, 0))
    assert item.ticks() == [False, False]


def test_single_selection_unticks_the_others(window):
    item = place(window, words=["A", "B", "C"])
    window.select_tool("select")
    click(window.view, *box_point(window, item, 0))
    click(window.view, *box_point(window, item_now(window), 2))
    assert item_now(window).ticks() == [True, False, True]
    window.scene.clearSelection()
    item = item_now(window)
    item.setSelected(True)
    window.refresh_selection()
    panel = window.properties_panel
    several = panel.body.findChild(QCheckBox, "checkboxMultiple")
    several.setChecked(False)
    item = item_now(window)
    assert item.multiple is False
    assert item.ticks() == [True, False, False], "only the first ticked stays"
    click(window.view, *box_point(window, item, 1))
    assert item_now(window).ticks() == [False, True, False], "radio-like"


def test_a_box_in_a_group_still_ticks(window):
    place(window, words=["A", "B"])
    window.select_tool("rect")
    drag(window.view, *on_page(window, 0, 300, 100), *on_page(window, 0, 380, 160))
    window.select_tool("select")
    for markup in markups(window):
        markup.setSelected(True)
    window.group_selection()
    assert item_now(window).group
    window.scene.clearSelection()
    click(window.view, *box_point(window, item_now(window), 1))
    assert item_now(window).ticks() == [False, True]
    assert all(m.isSelected() for m in markups(window)), "the group is picked"
    # the group moves as one, the Checkbox with it
    before = item_now(window).scenePos()
    drag(window.view, *word_point(window, item_now(window), 0),
         *(QPointF(*word_point(window, item_now(window), 0)) + QPointF(40, 30)).toTuple())
    assert item_now(window).scenePos().x() == pytest.approx(before.x() + 40, abs=1)
    window.ungroup_selection()
    assert not item_now(window).group
    # a locked group is not ticked
    for markup in markups(window):
        markup.set_locked(True)
    click(window.view, *box_point(window, item_now(window), 0))
    assert item_now(window).ticks() == [False, True]


# -- the look ----------------------------------------------------------------

@pytest.mark.parametrize("shape", ["square", "rounded", "circle", "diamond"])
@pytest.mark.parametrize("mark", ["tick", "cross", "filled", "dot"])
def test_shapes_and_marks_draw(qapp, shape, mark):
    item = CheckboxItem("A\nB")
    item.box_shape, item.mark = shape, mark
    item.set_checked(0, True)
    image = picture_of(item)
    ticked, empty = item.box_rects()
    assert dark_in(image, empty, item) > 10, "the empty box's outline"
    inside = empty.adjusted(empty.width() * 0.3, empty.height() * 0.3,
                            -empty.width() * 0.3, -empty.height() * 0.3)
    assert dark_in(image, inside, item) == 0, "an empty box is empty"
    middle = ticked.adjusted(ticked.width() * 0.3, ticked.height() * 0.3,
                             -ticked.width() * 0.3, -ticked.height() * 0.3)
    assert dark_in(image, middle, item) > 0, f"the {mark} shows in the ticked box"


def test_the_tick_runs_out_past_its_box(qapp):
    item = CheckboxItem("A")
    item.set_checked(0, True)
    image = picture_of(item)
    (box,) = item.box_rects()
    side = box.width()
    # just past the top right-hand corner, as on the stamp — not far out
    beyond = QRectF(box.right() + side * 0.02, box.top() - side * 0.05, side * 0.12, side * 0.2)
    assert dark_in(image, beyond, item) > 0, "past the top right-hand corner"
    far = QRectF(box.right() + side * 0.3, box.top() - side * 0.4, side * 0.3, side * 0.3)
    assert dark_in(image, far, item) == 0, "not running far out (too steep before)"


def test_narrower_wraps_without_changing_the_boxes_and_a_bigger_font_grows_them(window):
    item = place(window, words=["A long option that wraps", "B"])
    side = item.box_size()
    left = item.box_rects()[0].left()
    lines = item.doc.firstBlock().layout().lineCount()
    item.set_local_rect(QRectF(0, 0, 60, item.local_rect().height()))
    assert item.doc.firstBlock().layout().lineCount() > lines, "the words wrap"
    assert item.box_size() == side, "the boxes keep their size"
    assert item.box_rects()[0].left() == pytest.approx(left)
    # the second line hangs under the words, not under the box
    layout = item.doc.firstBlock().layout()
    assert layout.lineAt(1).x() == pytest.approx(layout.lineAt(0).x())
    assert item.text_rect().left() > item.box_rects()[0].right()
    item.style.font_size = 20.0
    item.apply_style()
    assert item.box_size() == pytest.approx(side * 2)


def test_alt_z_fits_it_round_its_options(window):
    window.select_tool("checkbox")
    drag(window.view, *on_page(window, 0, 100, 100), *on_page(window, 0, 450, 300))
    window.view.end_item_edit()
    (item,) = checkboxes(window)
    item.setSelected(True)
    window.act_autosize.trigger()
    width, height = item.natural_size()
    assert item.local_rect().width() == pytest.approx(width, abs=1.5)
    assert item.local_rect().height() == pytest.approx(height, abs=1.5)


def test_rows_are_about_one_and_a_half_text_heights_apart(qapp):
    item = CheckboxItem("A\nB")
    first, second = item.box_rects()
    pitch = second.top() - first.top()
    assert 1.4 * 10 < pitch < 1.8 * 10
    item.style.line_spacing = 1.5
    item.apply_style()
    first, second = item.box_rects()
    assert second.top() - first.top() > pitch * 1.2, "the line spacing spaces them"


# -- the Markups List and the Properties panel --------------------------------

def test_checked_column_and_properties_show_the_ticked_options(window):
    item = place(window, words=["A", "B", "C"])
    window.select_tool("select")
    click(window.view, *box_point(window, item, 0))
    click(window.view, *box_point(window, item_now(window), 2))
    window.refresh_lists()
    panel = window.markups_panel
    column = panel.COLUMNS.index("Checked")
    row = panel.row_for(0, item_now(window))
    assert row[column] == "A; C"
    assert row[panel.COLUMNS.index("Subject")] == "Checkbox"
    assert row[panel.COLUMNS.index("Type")] == "Checkbox"
    options = window.properties_panel.body.findChild(QListWidget, "checkboxOptions")
    assert [options.item(n).text() for n in range(options.count())] == ["A", "B", "C"]
    assert [options.item(n).checkState() == Qt.Checked
            for n in range(options.count())] == [True, False, True]


def test_the_properties_panel_manages_the_options(window):
    item = place(window, words=["A", "B"])
    item.setSelected(True)
    window.refresh_selection()
    panel = window.properties_panel

    def options():
        return panel.body.findChild(QListWidget, "checkboxOptions")

    def press(name):
        steps = window.undo_stack.count()
        panel.body.findChild(QToolButton, name).click()
        QApplication.processEvents()
        assert window.undo_stack.count() == steps + 1, f"{name}: one undo step"

    options().setCurrentRow(1)
    press("checkboxAddOption")
    assert item_now(window).options() == ["A", "B", "Option 3"]
    options().item(2).setText("C")
    assert item_now(window).options() == ["A", "B", "C"]
    options().item(2).setCheckState(Qt.Checked)
    assert item_now(window).ticks() == [False, False, True]
    options().setCurrentRow(2)
    press("checkboxMoveUp")
    assert item_now(window).options() == ["A", "C", "B"]
    assert item_now(window).ticks() == [False, True, False], "the tick moves with it"
    options().setCurrentRow(1)
    press("checkboxMoveDown")
    assert item_now(window).options() == ["A", "B", "C"]
    options().setCurrentRow(0)
    press("checkboxRemoveOption")
    assert item_now(window).options() == ["B", "C"]
    assert item_now(window).ticks() == [False, True]
    shape = panel.body.findChild(QComboBox, "checkboxShape")
    shape.setCurrentIndex(shape.findData("circle"))
    assert item_now(window).box_shape == "circle"
    mark = panel.body.findChild(QComboBox, "checkboxMark")
    mark.setCurrentIndex(mark.findData("cross"))
    assert item_now(window).mark == "cross"
    window.undo_stack.undo()
    assert item_now(window).mark == "tick"


def test_the_properties_toolbar_sets_shape_mark_and_multiple(window):
    item = place(window, words=["A", "B"])
    item.setSelected(True)
    window.refresh_selection()
    for control in (window.checkbox_shape_combo, window.checkbox_mark_combo,
                    window.checkbox_multiple_button):
        assert window._style_action[control].isVisible()
    assert window.checkbox_multiple_button.isChecked()
    window.checkbox_shape_combo.setCurrentIndex(window.checkbox_shape_combo.findData("diamond"))
    assert item_now(window).box_shape == "diamond"
    window.checkbox_mark_combo.setCurrentIndex(window.checkbox_mark_combo.findData("filled"))
    assert item_now(window).mark == "filled"
    window.checkbox_multiple_button.setChecked(False)
    assert item_now(window).multiple is False


# -- saving, and other readers ---------------------------------------------------

def a_ticked_checkbox(window):
    item = place(window, 120, 140, words=["Satisfactory", "Unsatisfactory", "N/A"])
    item = item_now(window)
    item.set_checked(0, True)
    item.box_shape = "rounded"
    item.style.font_size = 14.0
    item.apply_style()
    item.size_to_text()
    return item


def test_saved_and_reopened_it_is_the_same_checkbox(window, tmp_path):
    item = a_ticked_checkbox(window)
    before = {key: value for key, value in item.serialize().items()
              if key not in ("modified",)}
    path = str(tmp_path / "checkbox.pdf")
    save_to(window, path)
    reopen(window, path)
    again = item_now(window)
    after = {key: value for key, value in again.serialize().items()
             if key not in ("modified",)}
    for key in ("box_shape", "mark", "multiple", "checked", "rect", "written", "uid"):
        assert after[key] == before[key], key
    assert again.options() == ["Satisfactory", "Unsatisfactory", "N/A"]
    assert again.style.font_size == 14.0


def test_another_reader_shows_it_as_drawn_and_cannot_change_its_words(window, tmp_path):
    item = a_ticked_checkbox(window)
    path = str(tmp_path / "checkbox.pdf")
    save_to(window, path)
    with pymupdf.open(path) as document:
        page = document[0]
        (annotation,) = [a for a in page.annots()
                         if document.xref_get_key(a.xref, "NM")[1] == item.uid]
        assert document.xref_get_key(annotation.xref, "Subtype")[1] == "/Stamp"
        flags = int(document.xref_get_key(annotation.xref, "F")[1])
        assert flags & 4 and flags & 512, "printed, contents locked"
        assert annotation.info["subject"] == "Checkbox"
        assert annotation.info["content"].splitlines() == [
            "☑ Satisfactory", "☐ Unsatisfactory", "☐ N/A"]
        assert "Satisfactory" in page.get_text(), "its words are in the drawing"
        # drawn by MuPDF: the boxes and the tick where CalcForge draws them
        zoom = 4
        picture = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
        frame = window.document.pages[0].frame
        boxes = [item.mapToParent(box.center()) for box in item.box_rects()]
        side = item.box_size()

        def dark(x, y, w, h):
            found = 0
            for px in range(int(x * zoom), int((x + w) * zoom)):
                for py in range(int(y * zoom), int((y + h) * zoom)):
                    if sum(picture.pixel(px, py)[:3]) < 3 * 110:
                        found += 1
            return found
        ticked, empty = boxes[0], boxes[1]
        assert dark(ticked.x() - side * 0.2, ticked.y() - side * 0.2, side * 0.4, side * 0.4) > 0
        assert dark(empty.x() - side * 0.2, empty.y() - side * 0.2, side * 0.4, side * 0.4) == 0
        assert dark(empty.x() - side * 0.6, empty.y() - side * 0.2, side * 0.2, side * 0.4) > 0, \
            "the empty box's outline"
        assert frame is not None


def test_moved_and_resized_elsewhere_it_comes_back_where_it_was_put(window, tmp_path):
    item = a_ticked_checkbox(window)
    uid = item.uid
    width = item.local_rect().width()
    path = str(tmp_path / "moved.pdf")
    save_to(window, path)
    with pymupdf.open(path) as document:
        page = document[0]
        (annotation,) = [a for a in page.annots()
                         if document.xref_get_key(a.xref, "NM")[1] == uid]
        rect = annotation.rect
        # moved 100 pt right and 50 down, and made 40 pt wider, as another
        # editor would: the Rect changes, the appearance is scaled into it
        x0, y0, x1, y1 = rect.x0 + 100, rect.y0 + 50, rect.x1 + 140, rect.y1 + 50
        height = page.rect.height
        document.xref_set_key(annotation.xref, "Rect",
                              f"[{x0} {height - y1} {x1} {height - y0}]")
        document.save(path + ".x", garbage=1, deflate=True)
    import os
    os.replace(path + ".x", path)
    reopen(window, path)
    again = item_now(window)
    assert again.uid == uid
    assert again.options() == ["Satisfactory", "Unsatisfactory", "N/A"]
    assert again.ticks() == [True, False, False]
    assert again.box_shape == "rounded"
    assert again.mapToParent(again.local_rect().topLeft()).x() == pytest.approx(
        item_left(item) + 100, abs=2)
    assert again.local_rect().width() > width + 20, "and the width it was given"


def item_left(item):
    return item.mapToParent(item.local_rect().topLeft()).x()


def test_read_back_from_the_annotation_alone(window, tmp_path):
    """Without CalcForge's record (copied into another file, say), the
    stamp's own key still makes it a Checkbox."""
    item = a_ticked_checkbox(window)
    path = str(tmp_path / "alone.pdf")
    save_to(window, path)
    from calcforge.io import pdfmarkups, pdfvector
    made = pdfmarkups.markups_of_page(pdfvector.PdfFile.open(path), 0)
    (payload,) = [p for p in made if p.get("type") == "checkbox"]
    assert payload["checked"] == [True, False, False]
    assert payload["box_shape"] == "rounded"
    assert payload["x"] == pytest.approx(item.pos().x(), abs=0.5)


# -- styles and copies ------------------------------------------------------------

def test_a_markup_style_keeps_shape_mark_and_multiple(window):
    from calcforge.ui import toolsets
    item = place(window, words=["A", "B"])
    item = item_now(window)
    item.box_shape, item.mark = "circle", "dot"
    item.set_multiple(False)
    item.set_checked(1, True)
    properties = toolsets.properties_of(item)
    assert "checked" not in properties, "which are ticked is content, not a look"
    fresh = CheckboxItem()
    toolsets.apply_properties(fresh, properties)
    assert (fresh.box_shape, fresh.mark, fresh.multiple) == ("circle", "dot", False)
    assert fresh.ticks() == [False]
    from calcforge.ui import markupstyles
    assert markupstyles.styled("checkbox")


def test_copy_and_paste_keeps_the_ticks(window):
    item = place(window, words=["A", "B"])
    item = item_now(window)
    item.set_checked(1, True)
    window.scene.clearSelection()
    item.setSelected(True)
    window.act_copy.trigger()
    window.act_paste.trigger()
    copies = checkboxes(window)
    assert len(copies) == 2
    assert all(copy.ticks() == [False, True] for copy in copies)
