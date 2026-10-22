"""Freeze Panes in the workbook view, as Excel's (docs/qa/excel_audit.md, J1).

View ▸ Spreadsheet ▸ Freeze Panes keeps the rows above and the columns
left of the active cell in sight as the sheet scrolls (Freeze Top Row,
Freeze First Column, Unfreeze Panes too): one undo step each, saved, and
read from an Excel file. The frozen cells are drawn over the scrolled
ones; a click on them is on the cells drawn there; keys keep the active
cell in sight below and right of them; Ctrl+Home goes to the first cell
not frozen.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication

openpyxl = pytest.importorskip("openpyxl")

from calcforge.items.sheetpage import SheetRunItem  # noqa: E402
from calcforge.items.table import HEADING_H, ROWNUM_W  # noqa: E402
from calcforge.ui import sheetpages  # noqa: E402
from calcforge.ui.sheetfreeze import FREEZE_LINE, frozen  # noqa: E402
from tests.test_workbook_sections import pump, w  # noqa: E402,F401

_ = w


def shown_run(w) -> SheetRunItem:
    uid = w.scene.sheet_view
    return next(i for i in w.view.scene().items() if isinstance(i, SheetRunItem)
                and i.uid == uid)


@pytest.fixture
def sheet(w):
    sheetpages.insert_sheet_page(w, 0, new_sheet=True)
    pump()
    w.go_to_page(1)
    pump()
    run = shown_run(w)
    for r in range(80):
        for c in range(12):
            run.sheet.workbook.set_input(run.sheet, r, c, f"{r},{c}")
    pump()
    w.view.setFocus()
    return shown_run(w)


def send(w, kind, point, buttons=Qt.NoButton, button=Qt.NoButton):
    vp = w.view.viewport()
    p = QPointF(point)
    QApplication.sendEvent(vp, QMouseEvent(kind, p, QPointF(vp.mapToGlobal(p.toPoint())),
                                           button, buttons, Qt.NoModifier))
    pump()


def click(w, point):
    send(w, QEvent.MouseButtonPress, point, Qt.LeftButton, Qt.LeftButton)
    send(w, QEvent.MouseButtonRelease, point, Qt.NoButton, Qt.LeftButton)


def key(w, k, mods=Qt.NoModifier, text=""):
    target = w.view.tables.editor or w.view
    QApplication.sendEvent(target, QKeyEvent(QEvent.KeyPress, k, mods, text))
    pump()


def cell_point(w, run, row, col) -> QPoint:
    return w.view.mapFromScene(run.mapToScene(run.cell_rect(row, col).center()))


def scroll_by(w, dx, dy):
    w.view.horizontalScrollBar().setValue(w.view.horizontalScrollBar().value() + dx)
    w.view.verticalScrollBar().setValue(w.view.verticalScrollBar().value() + dy)
    pump()


def frozen_spot(w, run, row, col) -> QPoint:
    """Where frozen cell (row, col) is drawn in the window, whatever the scroll."""
    k = w.view.zoom()
    rect = run.cell_rect(row, col)
    return QPoint(int(ROWNUM_W * k + rect.center().x() * k),
                  int(HEADING_H * k + rect.center().y() * k))


def test_freeze_panes_at_the_active_cell_one_undo_step(w, sheet):
    click(w, cell_point(w, sheet, 2, 2))                    # C3
    steps = w.undo_stack.count()
    w.act_freeze_panes.trigger()
    pump()
    assert frozen(shown_run(w)) == (2, 2), "rows 1-2 and columns A-B"
    assert w.undo_stack.count() == steps + 1
    w.undo_stack.undo()
    pump()
    assert frozen(shown_run(w)) == (0, 0)
    w.undo_stack.redo()
    pump()
    assert frozen(shown_run(w)) == (2, 2)
    # again: Unfreeze Panes
    w.act_freeze_panes.trigger()
    pump()
    assert frozen(shown_run(w)) == (0, 0)


def test_the_frozen_cells_stay_in_sight_and_take_the_clicks(w, sheet):
    click(w, cell_point(w, sheet, 2, 2))
    w.act_freeze_panes.trigger()
    pump()
    scroll_by(w, 300, 500)
    run = shown_run(w)
    panes = w.view._frozen_panes
    assert panes.isVisible() and len(panes._pieces) == 5
    # Excel's freeze line where the frozen rows end
    picture = w.view.grab().toImage()
    k = w.view.zoom()
    xs, ys = run.edges()
    y = panes.geometry().top() + int(round(HEADING_H * k + ys[2] * k))
    assert picture.pixelColor(panes.geometry().left() + int(ROWNUM_W * k + xs[2] * k) + 40,
                              y) == FREEZE_LINE
    # a click on B1 where it is drawn picks B1, and nothing scrolls
    bars = (w.view.horizontalScrollBar().value(), w.view.verticalScrollBar().value())
    click(w, frozen_spot(w, run, 0, 1))
    assert w.view.tables.active == (0, 1)
    assert (w.view.horizontalScrollBar().value(), w.view.verticalScrollBar().value()) == bars
    # typed into, the box is over it where it is drawn
    key(w, 0, Qt.NoModifier, "x")
    editor = w.view.tables.editor
    assert editor is not None and editor.geometry().contains(frozen_spot(w, run, 0, 1))
    key(w, Qt.Key_Escape)


def test_keys_keep_the_active_cell_below_and_right_of_the_freeze(w, sheet):
    click(w, cell_point(w, sheet, 2, 2))
    w.act_freeze_panes.trigger()
    pump()
    key(w, Qt.Key_Home, Qt.ControlModifier)
    assert w.view.tables.active == (2, 2), "Ctrl+Home: the first cell not frozen"
    for _ in range(40):
        key(w, Qt.Key_Down)
    run = shown_run(w)
    k = w.view.zoom()
    xs, ys = run.edges()
    freeze_y = HEADING_H * k + ys[2] * k
    cell = w.view.mapFromScene(run.mapToScene(run.cell_rect(42, 2).topLeft()))
    assert cell.y() >= freeze_y - 1 and cell.y() < w.view.viewport().height()
    for _ in range(38):
        key(w, Qt.Key_Up)
    run = shown_run(w)
    cell = w.view.mapFromScene(run.mapToScene(run.cell_rect(4, 2).topLeft()))
    assert cell.y() >= freeze_y - 1, "not under the frozen rows"


def test_top_row_first_column_and_unfreeze(w, sheet):
    w.act_freeze_top_row.trigger()
    pump()
    assert frozen(shown_run(w)) == (1, 0)
    w.act_freeze_first_column.trigger()
    pump()
    assert frozen(shown_run(w)) == (0, 1)
    w.act_unfreeze_panes.trigger()
    pump()
    assert frozen(shown_run(w)) == (0, 0)
    assert not getattr(w.view, "_frozen_panes").isVisible()


def test_frozen_panes_are_saved_and_come_in_from_excel(w, sheet, tmp_path):
    from tests.test_calc_saving import reopen, save_to
    w.act_freeze_top_row.trigger()
    pump()
    saved = str(tmp_path / "frozen.pdf")
    save_to(w, saved)
    reopen(w, saved)
    pump()
    w.go_to_page(1)
    pump()
    assert frozen(shown_run(w)) == (1, 0)
    # an Excel file's
    path = tmp_path / "Frozen.xlsx"
    book = openpyxl.Workbook()
    book.active.title = "Frozen"
    book.active["A1"] = "head"
    book.active.freeze_panes = "B3"
    book.save(path)
    assert w.insert_workbook(str(path), 0)
    pump()
    run = next(i for i in w.view.scene().items() if isinstance(i, SheetRunItem)
               and i.sheet is not None and i.sheet.name == "Frozen")
    assert frozen(run) == (2, 1)
