"""Workbooks in Thumbnails (the user, 2026-10-23): "Inserting a spreadsheet
names it sheet 1 in thumbnail and inserting another names it workbook (2)";
"select box for workbooks is weird"; "the insert preview line is quite long
and not like Bluebeam"; "zooming in and out in the page panel should resize
the grid".
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication

from calcforge.ui import sheetview
from calcforge.ui.sheetpages import sections
from tests.test_workbook_sections import pump, w  # noqa: F401

_ = w


def entries(w) -> list:
    strip = w.pages_panel.list
    return [strip.item(r).text().split("\n")[0] for r in strip.shown_rows()]


def insert_workbook_after(w, page: int) -> None:
    w.go_to_page(page)
    pump()
    w.act_add_sheet_page.trigger()
    pump()
    sheetview.leave(w)
    pump()


def test_every_workbook_made_here_is_named_as_a_workbook(w):
    insert_workbook_after(w, 0)
    assert entries(w)[1] == "▸ Workbook", "not its one sheet's name"
    sheetview.enter(w, sections(w.document)[0].runs[0])
    pump()
    assert w.sheet_tabs.title.book.text().startswith("Workbook"), "the strip over the grid too"
    sheetview.leave(w)
    pump()
    insert_workbook_after(w, 1)
    assert entries(w)[1:] == ["▸ Workbook", "▸ Workbook (2)"]
    assert [s.name for s in sections(w.document)] == ["Workbook", "Workbook (2)"]
    # a plain page between, then another sheet made on it: its own workbook, named on
    w.add_page(len(w.document.pages) - 1)
    pump()
    w.insert_sheet_page(len(w.document.pages) - 1)
    pump()
    sheetview.leave(w)
    pump()
    assert [s.name for s in sections(w.document)] == ["Workbook", "Workbook (2)", "Workbook (3)"]
    # its copy is the next free number, never "Workbook (2) (2)"
    w.duplicate_page(sections(w.document)[1].first)
    pump()
    assert "Workbook (4)" in [s.name for s in sections(w.document)]
    assert not [s.name for s in sections(w.document) if s.name.count("(") > 1]


def test_a_picked_workbook_is_framed_all_round_its_stack(w):
    insert_workbook_after(w, 0)
    strip = w.pages_panel.list
    row = strip.shown_rows()[1]
    strip.setCurrentRow(row)
    strip.item(row).setSelected(True)
    pump()
    page = strip.picture_rect(row)
    d = strip.delegate
    image = strip.viewport().grab().toImage()
    ratio = image.devicePixelRatio()

    def blue(x, y):
        c = image.pixelColor(int(x * ratio), int(y * ratio))
        return c.blue() > 150 and c.red() < 80
    stack_top = page.top() - 2 * d.STACK
    stack_right = page.right() + 2 * d.STACK
    mid_x, mid_y = page.center().x(), page.center().y()
    # the frame shows on all four sides: left, bottom, and now top and right too
    assert blue(page.left() - 2, mid_y) and blue(mid_x, page.bottom() + 2)
    assert blue(mid_x, stack_top - 2), "along the top of the stack"
    assert blue(stack_right + 2, mid_y), "down the right of the stack"
    # all of it in the entry's own cell: the stack stood out of the cell's
    # top and its frame was cut off there (the user, 2026-10-24, a photo)
    cell = strip.visualItemRect(strip.item(row))
    frame = d.stack_rect(page, True).adjusted(-d.FRAME, -d.FRAME, d.FRAME, d.FRAME)
    assert cell.contains(frame), (cell, frame)
    strip.set_in_view(row)
    assert cell.contains(strip.in_view_frame()), (cell, strip.in_view_frame())


def test_the_drop_line_is_as_long_as_a_page_in_the_gap(w):
    for _ in range(5):
        w.add_page()
        pump()
    dock = w.pages_panel.parentWidget()
    while dock is not None and not hasattr(dock, "setFloating"):
        dock = dock.parentWidget()
    w.resizeDocks([dock], [520], Qt.Horizontal)
    pump()
    strip = w.pages_panel.list
    assert strip.uses_horizontal_slots()
    shown = strip.shown_rows()
    row = shown[1]
    start, end = strip.drop_indicator_line(row)
    page = strip.picture_rect(row)
    before = strip.picture_rect(shown[0])
    assert start.x() == end.x(), "upright, between two pages side by side"
    assert (start.y(), end.y()) == (page.top(), page.bottom()), "as tall as the page, no more"
    assert before.right() < start.x() < page.left(), "in the gap between them"
    assert abs((start.x() - before.right()) - (page.left() - start.x())) <= 1, "half way"


def test_zoomed_in_on_a_narrow_strip_the_pages_fit_it(w):
    for _ in range(2):
        w.add_page()
        pump()
    dock = w.pages_panel.parentWidget()
    while dock is not None and not hasattr(dock, "setFloating"):
        dock = dock.parentWidget()
    w.resizeDocks([dock], [230], Qt.Horizontal)
    pump()
    strip = w.pages_panel.list
    at = QPointF(strip.viewport().rect().center())

    def wheel(dy, times):
        for _ in range(times):
            QApplication.sendEvent(strip.viewport(), QWheelEvent(
                at, QPointF(strip.viewport().mapToGlobal(at.toPoint())), QPoint(0, 0),
                QPoint(0, dy), Qt.NoButton, Qt.ControlModifier, Qt.NoScrollPhase, False))
            pump()
    wheel(120, 12)                                  # as big as they go
    width = strip.viewport().width()
    for row in strip.shown_rows():
        page = strip.picture_rect(row)
        assert 0 <= page.left() and page.right() < width, "the whole page inside the strip"
    narrow = strip.iconSize()
    w.resizeDocks([dock], [700], Qt.Horizontal)     # wider again: as big as zoomed
    pump()
    assert strip.iconSize().width() > narrow.width()
    wheel(-120, 12)                                 # zoomed out: more to a row
    xs = {strip.visualItemRect(strip.item(r)).left() for r in strip.shown_rows()}
    assert len(xs) > 1
