"""The workbook view by hand (the user, 2026-10-22, late at night):

* "Add the Excel double click to autofill drag formula thing": a double-click
  on the fill handle fills down as far as the column beside goes.
* "Sheet should auto scroll up or right if I am selecting cells and go past
  the viewport": held past an edge, the sheet scrolls and the pick follows.
* "Currently I cannot markup on sheet even with clicking on the icon": a
  markup tool draws over the cells, which are let go.
* "The x button to escape workbook should be top right, where is the sheet
  name easily visible": the strip over the grid says the sheet's name, its
  × at the right.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from calcforge.ui.sheetview import run_shown
from tests.test_excel_footer_keys import at, click, drag, send, sheet, shown_run  # noqa: F401
from tests.test_workbook_sections import pump, w  # noqa: F401

_ = (w, sheet)


def double_click(w, point) -> None:
    vp = w.view.viewport()
    p = QPointF(point)
    for kind, buttons in ((QEvent.MouseButtonPress, Qt.LeftButton),
                          (QEvent.MouseButtonRelease, Qt.NoButton),
                          (QEvent.MouseButtonDblClick, Qt.LeftButton),
                          (QEvent.MouseButtonRelease, Qt.NoButton)):
        QApplication.sendEvent(vp, QMouseEvent(kind, p, QPointF(vp.mapToGlobal(p.toPoint())),
                                               Qt.LeftButton, buttons, Qt.NoModifier))
        pump()


def test_a_double_click_on_the_fill_handle_fills_down_beside_the_numbers(w, sheet):
    run = sheet
    book = run.sheet.workbook
    book.set_input(run.sheet, 0, 4, "=A1*2")             # E1, beside D1:D40's numbers
    pump()
    click(w, at(w, run, 0, 4))
    run = shown_run(w)
    handle = run.fill_handle_rect()
    assert handle is not None
    steps = w.undo_stack.count()
    double_click(w, w.view.mapFromScene(run.mapToScene(handle.center())))
    run = shown_run(w)
    cells = run.sheet.cells
    assert cells[(39, 4)].input == "=A40*2", "down to the last row of numbers beside"
    assert (40, 4) not in cells or not cells[(40, 4)].input, "and no further"
    assert run.sheet.value(9, 4) == 72.0
    assert w.undo_stack.count() == steps + 1, "one undo step"
    assert w.view.tables.selection() == (0, 4, 39, 4), "the cells filled, picked"


def test_held_past_the_bottom_edge_the_sheet_scrolls_and_the_pick_grows(w, sheet):
    run = sheet
    view = w.view
    bar = view.verticalScrollBar()
    start = at(w, run, 2, 1)
    below = QPoint(start.x(), view.viewport().height() + 40)     # past the bottom edge
    send(w, QEvent.MouseButtonPress, start, Qt.LeftButton, Qt.LeftButton)
    send(w, QEvent.MouseMove, below, Qt.LeftButton)
    before, picked = bar.value(), view.tables.selection()
    QTest.qWait(400)                                    # held there
    assert bar.value() > before + 100, "it scrolls down by itself"
    assert view.tables.selection()[2] > picked[2], "the pick follows"
    send(w, QEvent.MouseButtonRelease, below, Qt.NoButton, Qt.LeftButton)
    held = bar.value()
    QTest.qWait(150)
    assert bar.value() == held, "let go, it stops"


def test_held_past_the_right_edge_it_scrolls_across(w, sheet):
    run = sheet
    view = w.view
    bar = view.horizontalScrollBar()
    start = at(w, run, 2, 1)
    beyond = QPoint(view.viewport().width() + 30, start.y())
    send(w, QEvent.MouseButtonPress, start, Qt.LeftButton, Qt.LeftButton)
    send(w, QEvent.MouseMove, beyond, Qt.LeftButton)
    before = bar.value()
    QTest.qWait(400)
    assert bar.value() > before + 50
    send(w, QEvent.MouseButtonRelease, beyond, Qt.NoButton, Qt.LeftButton)


def test_a_markup_tool_draws_on_the_sheet_with_its_cells_open(w, sheet):
    from calcforge.items.shapes import RectItem
    run = sheet
    click(w, at(w, run, 2, 1))
    assert w.view.tables.item is not None
    w.view.set_tool("rect")
    pump()
    before = [i for i in w.view.scene().items() if isinstance(i, RectItem)]
    drag(w, at(w, run, 4, 1), at(w, run, 9, 3))
    after = [i for i in w.view.scene().items() if isinstance(i, RectItem)]
    assert len(after) == len(before) + 1, "the rectangle drawn over the cells"
    assert run_shown(w.scene) == run.uid, "the sheet still shown alone"


def test_the_strip_over_the_grid_names_the_sheet_and_closes_it(w, sheet):
    run = sheet
    title = w.sheet_tabs.title
    assert title.isVisible()
    assert title.sheet.text() == run.sheet.name
    close = title.findChild(type(w.sheet_tabs.close_button), "sheetViewClose")
    assert close is w.sheet_tabs.close_button and close.isVisible()
    view = w.view
    # over the grid, its × at the top right of the sheet
    top_right = view.mapTo(w, QPoint(view.width(), 0))
    at_close = close.mapTo(w, QPoint(close.width(), close.height()))
    assert at_close.y() <= top_right.y() + 1, "above the grid"
    assert abs(at_close.x() - top_right.x()) < 30, "at its right"
    QTest.mouseClick(close, Qt.LeftButton)
    pump()
    assert run_shown(w.scene) is None and not title.isVisible()
