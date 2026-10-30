"""Equations inside a text box (the user, 2026-10-29 and 2026-10-30): \\
typed while writing opens SMath's equation editor at the caret, Enter puts
the caret back in the words after it; the equation sits in the text drawn
as an equation, with an equation's own right-click menu (Show Expression,
Decimal Places …); it defines for the equations after the box; it survives
a save; a document saved with the {\\5+2=} codes of 29 Oct still reads
(items/inline_equations.py)."""
from __future__ import annotations

import time

import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu

from calcforge.items.fields import shown_text
from calcforge.items.inline_equations import PLACEHOLDER
from calcforge.items.text import TextItem
from tests.test_usability import press_key, type_text


def pump(seconds=0.0):
    end = time.monotonic() + seconds
    QApplication.processEvents()
    while time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.01)


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.interactive_prompts = False
    window.confirm_discard = lambda: True
    pump()
    return window


def a_box(w, text, y=60.0, page=0):
    frame = w.document.pages[page].frame
    item = TextItem(text, QRectF(0, 0, 260, 40))
    frame.add_markup(item, QPointF(60, y))
    item.apply_style()                      # as the Text tool leaves a new box
    pump(0.2)
    return item


def equation(w, y, text, page=0):
    from tests.test_calc_editing import type_line
    frame = w.document.pages[page].frame
    w.toggle_calc_mode(True)
    w.view.calc.place_cross(frame, QPointF(60, y))
    type_line(w, text)
    w.toggle_calc_mode(False)
    pump(0.2)


def result_of(w, starts_with):
    from calcforge.calc.docsheet import sheet_for
    from tests.test_definition_order_window import shown
    item = next(i for i in sheet_for(w.document).items.values()
                if i.region.editor.root.text().startswith(starts_with))
    return shown(item)


def render_box(box, scale: float = 3.0):
    """The box painted on its own, as a grey picture (rows, columns) at
    *scale* pixels to the point, with its top-left at the picture's."""
    import numpy as np
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QStyleOptionGraphicsItem
    bounds = box.boundingRect()
    image = QImage(int(bounds.width() * scale) + 2, int(bounds.height() * scale) + 2,
                   QImage.Format_RGB32)
    image.fill(Qt.white)
    option = QStyleOptionGraphicsItem()
    option.exposedRect = bounds
    painter = QPainter(image)
    painter.scale(scale, scale)
    painter.translate(-bounds.topLeft())
    box.paint(painter, option, None)
    painter.end()
    raw = np.frombuffer(bytes(image.constBits()), np.uint8)
    grey = raw.reshape(image.height(), image.bytesPerLine())[:, :image.width() * 4] \
        .reshape(image.height(), image.width(), 4)[:, :, :3].mean(axis=2)
    return grey, scale


def typed_into_box(w, box, keys: str):
    """\\ at the end of *box*'s words, *keys* typed into the equation that
    opens, Enter: the equation, with the caret back in the words."""
    view = w.view
    view.begin_item_edit(box)
    pump(0.1)
    QTest.keyClicks(view.viewport(), "\\")
    pump(0.2)                                   # the editor opens once the key is done with
    assert view.calc.editing(), "SMath's editor opened"
    item = view.calc.item
    assert getattr(item, "INLINE", False) and item.host is box
    assert view.editing_item() is None, "the words' editor stood aside"
    type_text(view, keys)
    press_key(view, Qt.Key_Return)
    pump(0.3)
    assert not view.calc.editing()
    return item


def test_a_backslash_opens_smaths_editor_and_enter_puts_the_caret_back_in_the_words(w):
    box = a_box(w, "Load ")
    item = typed_into_box(w, box, "5+2=")
    view = w.view
    assert view.editing_item() is box, "back in the words"
    editor = box._editor
    assert box.text() == "Load " + PLACEHOLDER
    assert editor.textCursor().position() == len("Load ") + 1, "after the equation"
    QTest.keyClicks(view.viewport(), " kN")
    view.end_item_edit()
    pump(0.3)
    assert box.inline_items() == [item]
    assert shown_text(box) == "Load 5+2 = 7 kN"
    # the equation is drawn in the words where its placeholder is: the
    # layout says where, and drawing the box draws it there, typeset
    image, scale = render_box(box)
    rect = box.inline_rect(item.inline_uid)                # in the box's coordinates
    assert rect is not None and rect.width() > 10 and rect.height() > 5
    assert item.pos().x() > 10, "after the word Load"
    assert (item.pos() - rect.topLeft()).manhattanLength() < 0.1
    origin = -box.boundingRect().topLeft()
    left = int((origin.x() + rect.left()) * scale)
    top = int((origin.y() + rect.top()) * scale)
    inside = image[top:top + int(rect.height() * scale), left:left + int(rect.width() * scale)]
    assert inside.size and inside.min() < 100, "ink where the equation is"


def test_show_expression_is_on_the_equations_own_menu_and_not_the_boxs(w):
    from calcforge.ui import calcmenu
    box = a_box(w, "Load ")
    item = typed_into_box(w, box, "5+2=")
    w.view.end_item_edit()
    pump(0.2)
    # the equation under the pointer is the item its menu is built for
    point = item.mapToScene(item.local_rect().center())
    assert w.view.markup_at(point) is item
    menu = w.build_context_menu(item, point)
    names = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert "Show Expression" in names and "Decimal Places" in names
    assert "Significant Figures" in names and "Equation" in names
    assert "Bookmark" not in names and "Insert Field" not in names
    own = QMenu()
    w._text_box_menu(own, box, box.mapToScene(QPointF(2, 2)))
    box_names = [a.text() for a in own.actions() if not a.isSeparator()]
    assert "Bookmark" in box_names and "Show Expression" not in box_names
    # the result alone, then the expression with it again
    shown = next(a for a in menu.actions() if a.text() == "Show Expression")
    assert shown.isChecked()
    shown.trigger()
    pump(0.3)
    assert item.region.show_input is False
    assert shown_text(box) == "Load 7"
    menu = QMenu()
    calcmenu.fill(w, menu, item)
    next(a for a in menu.actions() if a.text() == "Show Expression").trigger()
    pump(0.3)
    assert shown_text(box) == "Load 5+2 = 7"
    # and the equation's decimal places, as any equation's
    menu = QMenu()
    calcmenu.fill(w, menu, item)
    places = next(a for a in menu.actions() if a.text() == "Decimal Places").menu()
    two = next(a for a in places.actions() if a.text().split()[:1] == ["2"])
    two.trigger()
    pump(0.3)
    assert item.region.fmt is not None and item.region.fmt.decimals == 2


def test_an_equation_in_a_box_defines_for_the_equations_after_the_box(w):
    from calcforge.calc.docsheet import sheet_for
    from calcforge.ui.variablespanel import variable_rows
    box = a_box(w, "With ")
    typed_into_box(w, box, "t:5")
    w.view.end_item_edit()
    pump(0.2)
    assert shown_text(box) == "With t := 5"
    rows = [r for r in variable_rows(w.document) if r.name == "t"]
    assert rows and rows[0].source == "Text box" and rows[0].value == "5"
    equation(w, 200, "t*2=")
    assert result_of(w, "t*2") == "10"
    box.setPos(QPointF(60, 400))                      # moved below: no longer defined above
    sheet_for(w.document).settle()
    pump(0.3)
    assert "not defined" in result_of(w, "t*2")
    box.setPos(QPointF(60, 60))
    sheet_for(w.document).settle()
    pump(0.3)
    assert result_of(w, "t*2") == "10"
    # the box deleted: its definition goes with it
    w.scene.clearSelection()
    box.setSelected(True)
    w.delete_selection()
    pump(0.3)
    assert "not defined" in result_of(w, "t*2")
    assert not [r for r in variable_rows(w.document) if r.name == "t"]


def test_a_mistake_is_said_and_the_equation_reads_a_variable_defined_above(w):
    equation(w, 30, "test:7")
    box = a_box(w, "Area ", y=120)
    item = typed_into_box(w, box, "test*test=")
    w.view.end_item_edit()
    pump(0.3)
    assert shown_text(box) == "Area test*test = 49"
    other = a_box(w, "Load ", y=200)
    bad = typed_into_box(w, other, "zz*2=")
    w.view.end_item_edit()
    pump(0.3)
    assert bad.region.error is not None
    assert shown_text(other).startswith("Load zz*2: ")
    assert item.region.error is None


def test_clicking_the_equation_opens_it_for_typing_again(w):
    box = a_box(w, "Load ")
    item = typed_into_box(w, box, "5+2=")
    w.view.end_item_edit()
    pump(0.2)
    view = w.view
    point = item.mapToScene(item.local_rect().center())
    assert view.calc.calc_item_at(point) is item
    view.calc.focus(item, point)
    pump(0.1)
    assert view.calc.editing() and view.calc.item is item and item.focused
    press_key(view, Qt.Key_End)
    type_text(view, "+1")
    press_key(view, Qt.Key_Return)
    pump(0.3)
    assert shown_text(box) == "Load 5+2+1 = 8"
    assert view.editing_item() is box, "Enter puts the caret back in the words"
    view.end_item_edit()
    pump(0.1)


def test_an_empty_equation_left_goes_and_a_placeholder_typed_away_takes_its_equation(w):
    from calcforge.ui.variablespanel import variable_rows
    box = a_box(w, "Load ")
    view = w.view
    view.begin_item_edit(box)
    pump(0.1)
    QTest.keyClicks(view.viewport(), "\\")
    pump(0.2)
    assert view.calc.editing()
    press_key(view, Qt.Key_Return)                   # nothing typed: no equation
    pump(0.3)
    assert box.inline_items() == [] and box.text() == "Load "
    assert view.editing_item() is box
    view.end_item_edit()
    pump(0.1)
    typed_into_box(w, box, "t:5")
    assert [r for r in variable_rows(w.document) if r.name == "t"]
    editor = box._editor                             # the caret is after the equation
    press_key(view, Qt.Key_Backspace)
    pump(0.2)
    assert box.inline_items() == [] and PLACEHOLDER not in box.text()
    assert not [r for r in variable_rows(w.document) if r.name == "t"], "gone with it"
    editor.document().undo()
    pump(0.2)
    assert len(box.inline_items()) == 1 and PLACEHOLDER in box.text(), "undo brings it back"
    assert [r for r in variable_rows(w.document) if r.name == "t"]
    view.end_item_edit()
    pump(0.1)


def test_an_inline_equation_survives_a_save_and_reopen(w, tmp_path):
    from calcforge.ui.mainwindow import MainWindow
    box = a_box(w, "Span ")
    typed_into_box(w, box, "5+2=")
    QTest.keyClicks(w.view.viewport(), " m ")
    pump(0.1)
    QTest.keyClicks(w.view.viewport(), "\\")
    pump(0.2)
    type_text(w.view, "t:5")
    press_key(w.view, Qt.Key_Return)
    pump(0.3)
    w.view.end_item_edit()
    pump(0.2)
    equation(w, 200, "t*2=")
    assert result_of(w, "t*2") == "10"
    assert shown_text(box) == "Span 5+2 = 7 m t := 5"
    out = tmp_path / "boxes.pdf"
    w.document.path = str(out)
    assert w.save_document()
    other = MainWindow()
    other.confirm_discard = lambda: True
    other.interactive_prompts = False
    try:
        other.show()
        other._open_chosen(str(out))
        pump(0.5)
        box = next(i for i in other.scene.frames[0].markups() if isinstance(i, TextItem))
        assert len(box.inline_items()) == 2
        assert shown_text(box) == "Span 5+2 = 7 m t := 5"
        assert result_of(other, "t*2") == "10"
    finally:
        other.close()
        other.deleteLater()
        pump()


def test_a_document_saved_with_the_codes_of_29_october_still_reads(w):
    from calcforge.items.base import build_item
    frame = w.document.pages[0].frame
    record = TextItem("x", QRectF(0, 0, 260, 40)).serialize()
    record.pop("html", None)
    record["text"] = "Load {\\5+2=} kN and {\\t:=5} here"
    record["written"] = record["text"]
    record["x"], record["y"] = 60.0, 60.0
    box = build_item(record)
    frame.add_markup(box, QPointF(60, 60))
    pump(0.3)
    assert len(box.inline_items()) == 2
    assert PLACEHOLDER in box.text() and "{\\" not in box.text()
    assert shown_text(box) == "Load 7 kN and t := 5 here", "a code showed its result alone"
    equation(w, 200, "t*2=")
    assert result_of(w, "t*2") == "10"
