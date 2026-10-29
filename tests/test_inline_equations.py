"""Equations inside a text box (the user, 2026-10-29): \\ opens one while
typing; {\\5+2=} shows 7, {\\t:=5} defines t for the equations after the
box, {\\!t*t=} shows the working; right-click ▸ Show Expression, a
double-click picks the equation out to retype (items/inline_equations.py)."""
from __future__ import annotations

import time

import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from calcforge.items.fields import shown_text
from calcforge.items.inline_equations import expression_text, inline_fields, keys_for
from calcforge.items.text import TextItem


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


def test_the_keys_and_the_expression_an_inline_equation_is_shown_with():
    assert [body for _m, body in inline_fields("Load {\\5+2=} kN and {\\!t*t=} {page}")] == \
        ["5+2=", "!t*t="]
    assert keys_for("t:=5") == "t:5" and keys_for("5+2=") == "5+2=" and keys_for("!a*b=") == "a*b="
    assert keys_for("  ") is None
    assert expression_text("!t*t=") == "t*t" and expression_text("t:=5") == "t := 5"


def test_an_inline_equation_shows_its_result_and_defines_for_the_equations_after(w):
    from calcforge.ui.variablespanel import variable_rows
    box = a_box(w, "Span {\\5+2=} m, with {\\t:=5} for the rest")
    assert shown_text(box) == "Span 7 m, with t := 5 for the rest"
    rows = [r for r in variable_rows(w.document) if r.name == "t"]
    assert rows and rows[0].source == "Text box" and rows[0].value == "5"
    # an equation below the box reads t; moved above it, it can't
    equation(w, 200, "t*2=")
    assert result_of(w, "t*2") == "10"
    box.setPos(QPointF(60, 400))
    from calcforge.calc.docsheet import sheet_for
    sheet_for(w.document).settle()
    pump(0.3)
    assert "not defined" in result_of(w, "t*2")
    box.setPos(QPointF(60, 60))
    sheet_for(w.document).settle()
    pump(0.3)
    assert result_of(w, "t*2") == "10"
    # retyped, the old definition goes with the old words
    box.set_text("Nothing to work out here")
    pump(0.2)
    assert not [r for r in variable_rows(w.document) if r.name == "t"]
    assert "not defined" in result_of(w, "t*2")


def test_show_expression_puts_the_working_beside_the_result(w):
    equation(w, 30, "test:7")
    box = a_box(w, "Area {\\test*test=} m2", y=120)
    assert shown_text(box) == "Area 49 m2"
    w.set_inline_expression_shown(box, 0, True)
    pump(0.1)
    assert box.text() == "Area {\\!test*test=} m2"
    assert shown_text(box) == "Area test*test = 49 m2"
    w.undo_something()
    pump(0.2)
    box = next(i for i in w.document.pages[0].frame.built_markups() if isinstance(i, TextItem))
    assert shown_text(box) == "Area 49 m2", "one undo step"
    w.set_inline_expression_shown(box, 0, True)
    w.set_inline_expression_shown(box, 0, False)
    assert box.text() == "Area {\\test*test=} m2"


def test_a_mistake_is_said_in_the_box(w):
    box = a_box(w, "Load {\\zz*2=} kN")
    said = shown_text(box)
    assert said.startswith("Load zz*2: ") and "kN" in said


def test_typing_a_backslash_opens_an_equation_and_enter_steps_out_of_it(w):
    box = a_box(w, "Load ")
    view = w.view
    view.begin_item_edit(box)
    pump(0.1)
    editor = box._editor
    assert editor is not None
    QTest.keyClicks(view.viewport(), "\\")
    pump(0.05)
    assert box.doc.toPlainText() == "Load {\\}"
    assert editor.textCursor().position() == len("Load {\\")
    QTest.keyClicks(view.viewport(), "5+2=")
    QTest.keyClick(view.viewport(), Qt.Key_Return)
    pump(0.05)
    assert box.doc.toPlainText() == "Load {\\5+2=}", "Enter steps out, no new line"
    assert editor.textCursor().position() == len("Load {\\5+2=}")
    QTest.keyClicks(view.viewport(), " kN")
    view.end_item_edit()
    pump(0.3)
    assert shown_text(box) == "Load 7 kN"


def test_a_double_click_on_an_inline_equation_picks_it_out_to_retype(w):
    box = a_box(w, "Load {\\5+2=} kN")
    pump(0.2)
    box.update()
    pump(0.1)
    shown_text(box)                                   # the fields' places are noted
    # the 7 sits after "Load ": a point in it, on the page
    doc = box._fields_shown[2]
    cursor = __import__("PySide6.QtGui", fromlist=["QTextCursor"]).QTextCursor(doc)
    cursor.setPosition(5)
    at = doc.documentLayout().blockBoundingRect(cursor.block()).topLeft()
    line = cursor.block().layout().lineForTextPosition(5)
    x = line.cursorToX(5)[0] + 2.0
    point = box.mapToScene(box.text_origin() + QPointF(at.x() + x, at.y() + line.height() / 2))
    field = box.inline_field_at(point)
    assert field is not None and field[0] == 0 and field[3] == "5+2="
    w.view.begin_item_edit(box)
    assert box.select_field(0)
    assert box._editor.textCursor().selectedText() == "5+2="
    w.view.end_item_edit()
    pump(0.2)
    # the window's menu for a right-click there offers Show Expression
    from PySide6.QtWidgets import QMenu
    menu = QMenu()
    w._text_box_menu(menu, box, point)
    names = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert names[:2] == ["Show Expression", "Edit Equation"]
    off = box.mapToScene(box.text_origin() + QPointF(2.0, 6.0))      # on "Load"
    menu = QMenu()
    w._text_box_menu(menu, box, off)
    assert "Show Expression" not in [a.text() for a in menu.actions()]


def test_an_inline_equation_survives_a_save_and_reopen(w, tmp_path):
    from calcforge.ui.mainwindow import MainWindow
    a_box(w, "Span {\\5+2=} m {\\t:=5}")
    equation(w, 200, "t*2=")
    assert result_of(w, "t*2") == "10"
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
        assert box.text() == "Span {\\5+2=} m {\\t:=5}", "the codes are what is saved"
        assert shown_text(box) == "Span 7 m t := 5"
        assert result_of(other, "t*2") == "10"
    finally:
        other.close()
        other.deleteLater()
        pump()
