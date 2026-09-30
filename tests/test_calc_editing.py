"""Typing equations on the canvas, through the real Qt event queue.

Calc mode behaves like SMath (decision 5): a click on bare paper puts down
the red cross, typing starts an equation there, Enter leaves it with the cross
underneath, and the result appears when the equation is left. A click on an
equation puts the cursor in it; one undo history covers keystrokes and the
document (the brief).
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest

from markforge.calc.engine.display import display_text
from markforge.items.calc import CalcItem
from tests.test_usability import click, drag, press_key, type_text


def calc_mode(window):
    window.view.calc.mode = "calc"


def equations(window):
    return sorted((i for i in window.view.scene().items() if isinstance(i, CalcItem)),
                  key=lambda i: (i.parentItem().page.uid != window.document.pages[0].uid,
                                 i.pos().y(), i.pos().x()))


def shown(item) -> str:
    region = item.region
    if region.error is not None and not region.pending:
        return "error: " + str(region.error)
    return display_text(region.display) if region.display is not None else ""


def type_line(window, text):
    """Keys as they are typed, then Enter."""
    type_text(window.view, text)
    press_key(window.view, Qt.Key_Return)


def end_of(item):
    """A point just inside the right-hand end of an equation, on the canvas."""
    r = item.local_rect()
    return item.mapToScene(QPointF(r.right() - 2, r.center().y()))


def at(window, x, y):
    return window.document.pages[0].frame.mapToScene(QPointF(x, y))


def test_typing_on_paper_starts_an_equation_at_the_red_cross(window):
    calc_mode(window)
    p = at(window, 100, 120)
    click(window.view, p.x(), p.y())
    assert window.view.calc.cross is not None
    type_line(window, "Len:7.2'm")
    type_line(window, "Len*2=")
    first, second = equations(window)
    assert "7.2" in first.text()
    assert shown(second) == "14.4 m"
    assert second.pos().y() > first.pos().y(), "Enter leaves the cross under the equation"
    assert abs(second.pos().x() - first.pos().x()) < 1e-6


def test_the_cross_and_equations_sit_on_smaths_grid(window):
    calc_mode(window)
    p = at(window, 101.3, 122.9)
    click(window.view, p.x(), p.y())
    type_line(window, "a:1")
    item = equations(window)[0]
    for v in (item.pos().x(), item.pos().y()):
        assert abs(v / 6.75 - round(v / 6.75)) < 1e-9


def test_markup_mode_leaves_letters_to_markforge(window):
    p = at(window, 100, 120)
    click(window.view, p.x(), p.y())
    type_text(window.view, "x")
    assert equations(window) == []


def test_a_click_on_an_equation_puts_the_cursor_in_it(window):
    calc_mode(window)
    p = at(window, 100, 120)
    click(window.view, p.x(), p.y())
    type_line(window, "b:2")
    type_line(window, "b+1=")
    define, use = equations(window)
    assert shown(use) == "3"
    p = end_of(define)
    click(window.view, p.x(), p.y())
    assert window.view.calc.item is define
    press_key(window.view, Qt.Key_Backspace)
    type_text(window.view, "5")
    press_key(window.view, Qt.Key_Escape)
    assert window.view.calc.item is None
    assert shown(use) == "6"


def test_one_undo_history_for_keystrokes_and_the_document(window):
    calc_mode(window)
    p = at(window, 100, 120)
    click(window.view, p.x(), p.y())
    type_line(window, "c:3")
    assert len(equations(window)) == 1
    window.undo_something()
    assert equations(window) == [], "Ctrl+Z takes the whole new equation back"
    window.redo_something()
    assert len(equations(window)) == 1
    # while typing, it is the keystrokes that go first
    item = equations(window)[0]
    p = end_of(item)
    click(window.view, p.x(), p.y())
    type_text(window.view, "4")
    assert item.text().endswith("34")
    window.undo_something()
    assert item.text().endswith("3") and not item.text().endswith("34")


def test_an_equation_left_empty_disappears(window):
    calc_mode(window)
    p = at(window, 100, 120)
    click(window.view, p.x(), p.y())
    type_text(window.view, "x")
    press_key(window.view, Qt.Key_Backspace)
    press_key(window.view, Qt.Key_Escape)
    assert equations(window) == []


def test_ctrl_0_is_smaths_at_least_inside_an_equation(window):
    """Decision 6: inside an equation SMath's key wins; elsewhere MarkForge's."""
    calc_mode(window)
    window.show()
    window.view.setFocus()
    p = at(window, 100, 120)
    click(window.view, p.x(), p.y())
    type_text(window.view, "3")
    zoom = window.view._zoom
    QTest.keyClick(window.view, Qt.Key_0, Qt.ControlModifier)
    type_text(window.view, "2")
    item = window.view.calc.item
    assert item.text() == "3≥2"
    assert window.view._zoom == zoom, "fit page did not fire"
    press_key(window.view, Qt.Key_Escape)


def test_dragging_an_equation_moves_it_and_recalculates_on_release(window):
    calc_mode(window)
    p = at(window, 100, 120)
    click(window.view, p.x(), p.y())
    type_line(window, "d:2")
    type_line(window, "d+0=")
    define, use = equations(window)
    assert shown(use) == "2"
    box = define.sceneBoundingRect()
    start = QPointF(box.center())
    drag(window.view, start.x(), start.y(), start.x(), start.y() + 150)
    assert define.pos().y() > use.pos().y()
    assert shown(use).startswith("error")
    window.undo_something()
    assert shown(equations(window)[1]) == "2"


def test_tab_and_up_down_step_through_the_reading_order(window):
    calc_mode(window)
    p = at(window, 100, 120)
    click(window.view, p.x(), p.y())
    for line in ("e1:1", "e2:2", "e3:3"):
        type_line(window, line)
    first, second, third = equations(window)
    p = end_of(first)
    click(window.view, p.x(), p.y())
    press_key(window.view, Qt.Key_Tab)
    assert window.view.calc.item is second
    press_key(window.view, Qt.Key_Down)
    assert window.view.calc.item is third
    press_key(window.view, Qt.Key_Up)
    assert window.view.calc.item is second
