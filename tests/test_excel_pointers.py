"""Pointers and the mouse in the workbook view as Excel's
(docs/qa/excel_audit.md, B1-B9, G1, G2, H2; the user, 2026-10-22: "issues
with cursors").

* Normal view: the page lines are only lines — a drag over one picks
  cells; in Page Break Preview they are dragged, with the plain double
  arrow.
* The headings kept in sight as the sheet scrolls size columns and rows
  from their edges, the size of the sheet's own.
* The selection's border: Excel's arrow with the move sign, with Ctrl the
  arrow with the +; the band is the border's own width inside it.
* Pointers drawn for the screen's scale; the white cross on the corner.
* A sheet's HYPERLINK cell: a click follows it, a press held picks it.
* Shift + drag of the border inserts the cells there; a column's edge
  dragged says its width in characters.
"""
from __future__ import annotations

import re

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from calcforge.items.sheetpage import SheetRunItem
from calcforge.items.table import HEADING_H
from calcforge.sheet.pagination import options
from calcforge.ui import sheetpages
from calcforge.ui.cursors import COPY, MOVE, is_revu_cursor
from tests.test_workbook_sections import pump, w  # noqa: F401

_ = w


def shown_run(w) -> SheetRunItem:
    uid = w.scene.sheet_view
    return next(i for i in w.view.scene().items() if isinstance(i, SheetRunItem)
                and i.uid == uid)


@pytest.fixture
def sheet(w):
    """A new sheet with numbers in A1:D40, in the workbook view."""
    sheetpages.insert_sheet_page(w, 0, new_sheet=True)
    pump()
    w.go_to_page(1)
    pump()
    run = shown_run(w)
    for r in range(40):
        for c in range(4):
            run.sheet.workbook.set_input(run.sheet, r, c, str(r * 4 + c))
    pump()
    return shown_run(w)


def at(w, run, x, y) -> QPoint:
    """The window point of a point of the sheet."""
    return w.view.mapFromScene(run.mapToScene(QPointF(x, y)))


def send(w, kind, point, buttons=Qt.NoButton, button=Qt.NoButton, mods=Qt.NoModifier):
    vp = w.view.viewport()
    p = QPointF(point)
    QApplication.sendEvent(vp, QMouseEvent(kind, p, QPointF(vp.mapToGlobal(p.toPoint())),
                                           button, buttons, mods))
    pump()


def move(w, point, buttons=Qt.NoButton, mods=Qt.NoModifier):
    send(w, QEvent.MouseMove, point, buttons, Qt.NoButton, mods)


def drag(w, start, end, mods=Qt.NoModifier):
    send(w, QEvent.MouseButtonPress, start, Qt.LeftButton, Qt.LeftButton, mods)
    for step in (0.3, 0.7, 1.0):
        move(w, QPointF(start) + (QPointF(end) - QPointF(start)) * step, Qt.LeftButton, mods)
    send(w, QEvent.MouseButtonRelease, end, Qt.NoButton, Qt.LeftButton, mods)


def cursor(w):
    return w.view.viewport().cursor()


def is_cell_cross(c) -> bool:
    from calcforge.ui.view import excel_cursor
    return c.shape() == Qt.BitmapCursor and \
        c.pixmap().cacheKey() == excel_cursor("cell").pixmap().cacheKey()


# -- B1, B5: the page lines in Normal view and in Page Break Preview -------------------------------
def test_in_normal_view_the_print_areas_edge_drags_straight_away(w, sheet):
    """The user, 2026-10-22: "the print area blue lines ... I should be able
    to drag etc straight away like how it used to be when I had paged sheets
    before" — Normal view too, not only Page Break Preview."""
    run = sheet
    assert run.normal_view
    xs, ys = run.edges()
    edge = run.paging.last_col + 1             # the print area's right edge (J|K)
    on_line = at(w, run, xs[edge], (ys[9] + ys[10]) / 2)
    move(w, on_line)
    assert cursor(w).shape() == Qt.SizeHorCursor, "Excel's double arrow over the line"
    drag(w, on_line, at(w, run, xs[edge + 2] + 2, (ys[9] + ys[10]) / 2))
    run = shown_run(w)
    assert options(run.sheet)["print_area"][3] == edge + 1, "the print area a column wider"


def test_in_page_break_preview_it_drags_with_the_plain_double_arrow(w, sheet):
    w.act_sheet_break_preview.trigger()
    pump()
    run = shown_run(w)
    assert not run.normal_view
    xs, ys = run.edges()
    edge = run.paging.last_col + 1
    on_line = at(w, run, xs[edge], (ys[9] + ys[10]) / 2)
    move(w, on_line)
    assert cursor(w).shape() == Qt.SizeHorCursor
    drag(w, on_line, at(w, run, xs[edge + 2] + 2, (ys[9] + ys[10]) / 2))
    run = shown_run(w)
    assert options(run.sheet)["print_area"][3] == edge + 1


# -- B2, H2: the headings kept in sight ------------------------------------------------------------
def test_the_kept_headings_size_columns_from_their_edges(w, sheet):
    bar = w.view.verticalScrollBar()
    bar.setValue(bar.value() + 400)
    pump()
    headings = w.view.sheet_headings
    headings.refresh()
    k = w.view.zoom()
    strip = next(rect for _run, kind, rect in headings._strips if kind == "col")
    assert strip.height() == round(HEADING_H * k), "the sheet's own heading height (H2)"
    assert "corner" in [kind for _run, kind, _rect in headings._strips], \
        "the corner over the row numbers, not a row's number showing through"
    run = shown_run(w)
    xs, _ys = run.edges()
    edge = QPoint(at(w, run, xs[2], 0).x(), strip.center().y())     # B|C
    move(w, edge)
    assert cursor(w).shape() == Qt.SplitHCursor
    width = run.sheet.width(1)
    drag(w, edge, edge + QPoint(30, 0))
    assert shown_run(w).sheet.width(1) == pytest.approx(width + 30 / k, abs=1.5)
    # across a column's middle: the ↓ arrow, and a click picks the column
    run = shown_run(w)
    xs, _ys = run.edges()
    middle = QPoint(at(w, run, (xs[3] + xs[4]) / 2, 0).x(), strip.center().y())
    move(w, middle)
    assert cursor(w).shape() == Qt.BitmapCursor and not is_cell_cross(cursor(w))


# -- B3, B4: the selection's border ---------------------------------------------------------------
def test_the_border_shows_excels_move_arrow_and_with_ctrl_the_copy_arrow(w, sheet):
    run = sheet
    w.view.tables.select((1, 1), (2, 2))
    pump()
    xs, ys = run.edges()
    border = at(w, run, xs[3] + 1.0, (ys[1] + ys[3]) / 2)
    move(w, border)
    assert is_revu_cursor(cursor(w), MOVE)
    w.view.setFocus()
    QTest.keyPress(w.view, Qt.Key_Control)
    pump()
    assert is_revu_cursor(cursor(w), COPY), "Ctrl held: a drag copies"
    QTest.keyRelease(w.view, Qt.Key_Control)
    pump()
    assert is_revu_cursor(cursor(w), MOVE)


def test_inside_a_cell_near_its_edge_a_drag_picks_cells(w, sheet):
    run = sheet
    w.view.tables.select((4, 1))
    pump()
    xs, ys = run.edges()
    k = w.view.zoom()
    inside = at(w, run, (xs[1] + xs[2]) / 2, ys[4] + 3.5 / k)     # 3 px in from the top
    move(w, inside)
    assert is_cell_cross(cursor(w))
    drag(w, inside, at(w, run, (xs[3] + xs[4]) / 2, (ys[4] + ys[5]) / 2))
    assert w.view.tables.selection() == (4, 1, 4, 3)
    assert run.sheet.cells[(4, 1)].input == "17", "nothing moved"


# -- B6, B9: drawn for the screen; the corner ----------------------------------------------------
def test_excels_pointers_are_drawn_for_the_screens_scale(monkeypatch):
    from calcforge.ui import cursors
    from calcforge.ui.view import excel_cursor
    monkeypatch.setattr(cursors, "screen_ratio", lambda: 2.0)
    made = excel_cursor("col")
    assert made.pixmap().devicePixelRatio() == pytest.approx(2.0)
    assert made.pixmap().width() == 64


def test_over_the_select_all_corner_the_white_cross(w, sheet):
    run = sheet
    move(w, at(w, run, *run.corner_rect().center().toTuple()))
    assert is_cell_cross(cursor(w))


# -- B7: a sheet's HYPERLINK cell --------------------------------------------------------------------
def test_a_click_follows_a_link_and_a_press_held_picks_the_cell(w, sheet, monkeypatch):
    from PySide6.QtGui import QDesktopServices
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString())
                        or True)
    run = sheet
    run.sheet.workbook.set_input(run.sheet, 5, 5, '=HYPERLINK("https://example.com/spec","spec")')
    pump()
    run = shown_run(w)
    point = at(w, run, *run.cell_rect(5, 5).center().toTuple())
    move(w, point)
    assert cursor(w).shape() == Qt.PointingHandCursor
    send(w, QEvent.MouseButtonPress, point, Qt.LeftButton, Qt.LeftButton)
    send(w, QEvent.MouseButtonRelease, point, Qt.NoButton, Qt.LeftButton)
    assert opened == ["https://example.com/spec"], "a click follows it"
    send(w, QEvent.MouseButtonPress, point, Qt.LeftButton, Qt.LeftButton)
    QTest.qWait(650)
    send(w, QEvent.MouseButtonRelease, point, Qt.NoButton, Qt.LeftButton)
    assert opened == ["https://example.com/spec"] and w.view.tables.active == (5, 5), \
        "held: the cell picked, not followed"


# -- G1, G2 ---------------------------------------------------------------------------------------
def test_shift_drag_of_the_border_cuts_and_inserts(w, sheet):
    run = sheet
    for r, text in enumerate("abcd"):
        run.sheet.workbook.set_input(run.sheet, r, 6, text)
    pump()
    run = shown_run(w)
    w.view.tables.select((0, 6))
    pump()
    xs, ys = run.edges()
    grab = at(w, run, xs[7] - 1.0, (ys[0] + ys[1]) / 2)        # its right border, inside
    drop = at(w, run, xs[7] - 1.0, ys[2] + (ys[3] - ys[2]) * 0.8)
    steps = w.undo_stack.count()
    drag(w, grab, drop, Qt.ShiftModifier)
    run = shown_run(w)
    assert [run.sheet.cells[(r, 6)].input for r in range(4)] == ["b", "c", "a", "d"]
    assert w.undo_stack.count() == steps + 1, "one undo step"
    assert w.view.tables.selection() == (2, 6, 2, 6), "it is picked where it went"


def test_a_column_edge_dragged_says_its_width_as_excel_does(w, sheet):
    said = []
    w.view.statusMessage.connect(said.append)
    run = sheet
    xs, _ys = run.edges()
    edge = at(w, run, xs[1], -HEADING_H / 2)
    send(w, QEvent.MouseButtonPress, edge, Qt.LeftButton, Qt.LeftButton)
    move(w, edge + QPoint(1, 0), Qt.LeftButton)
    tips = [t for t in said if t.startswith("Width:")]
    assert tips and re.fullmatch(r"Width: \d+\.\d\d \(\d+ pixels\)", tips[-1])
    assert tips[-1].startswith("Width: 8.") or tips[-1].startswith("Width: 9."), \
        "a default column is 8.43 characters"
    send(w, QEvent.MouseButtonRelease, edge + QPoint(1, 0), Qt.NoButton, Qt.LeftButton)
