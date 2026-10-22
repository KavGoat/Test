"""The workbook view (the user, 2026-10-22): "Don't let me scroll from sheet
to sheet: like Excel, when I click a workbook it opens a [spreadsheet] with
tabs at the bottom" — "Not full window, fits the document panel completely".

* Going to a workbook — its entry in Thumbnails, a click on one of its
  cells, a sheet tab, the page box — shows the sheet alone filling the
  canvas: an endless grid from A1, scrolling within that sheet only, the
  tabs at the bottom, a × to go back to the page you came from.
* Leaving: another page in Thumbnails or the page box, Ctrl+Page Down / Up
  past the last or first sheet (between sheets they change sheet), the ×.
* Each workbook keeps its zoom; Ctrl+wheel zooms the grid.
* Page breaks show as Excel's Normal view's dashed lines; "Page N" on a
  sheet's pages is its number in the document, none on a page that
  doesn't print.

And the two bugs: stuck in a workbook — a click on its entry in Thumbnails
from its second (Don't Print) sheet went nowhere; and tabs left showing
outside a workbook.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

pytest.importorskip("openpyxl")

from calcforge.items.sheetpage import SheetRunItem  # noqa: E402
from calcforge.ui import sheetpages  # noqa: E402
from tests.test_tables import cell_scene, click, enter, type_text  # noqa: E402
from tests.test_workbook_sections import (bar_shown, pump, sheet_pages, w,  # noqa: E402,F401
                                          with_loads)


def run_named(w, name: str):
    return next(i for i in w.view.scene().items()
                if isinstance(i, SheetRunItem) and i.sheet is not None and i.sheet.name == name)


def shown(w):
    return w.scene.sheet_view


def click_thumbnail(w, row: int) -> None:
    listed = w.pages_panel.list
    QTest.mouseClick(listed.viewport(), Qt.LeftButton, Qt.NoModifier,
                     listed.picture_rect(row).center())
    pump()


def seen_rect(w):
    view = w.view
    return view.mapToScene(view.viewport().rect()).boundingRect()


def others_in_sight(w) -> list:
    """Pages other than the sheet shown that are on the screen."""
    seen = seen_rect(w)
    return [f for f in w.scene.frames if f.page.sheet != shown(w)
            and f.isVisible() and f.sceneBoundingRect().intersects(seen)]


@pytest.fixture
def wb(w, tmp_path):
    w.show_panel("dock_pages", True)
    pump()
    section = with_loads(w, tmp_path, no_print=("Factors",))
    w.go_to_page(0)
    w.activateWindow()                          # (after the import window)
    QTest.qWaitForWindowActive(w)
    pump()
    return section


def key(w, k, mods=Qt.NoModifier) -> None:
    """A key pressed where a person's keyboard goes: the window's shortcuts
    (the page keys) first."""
    w.view.setFocus()
    pump()
    QTest.keyClick(QApplication.focusWidget() or w.view, k, mods)
    pump()


# -- going in -------------------------------------------------------------------------------------
def test_its_entry_in_thumbnails_shows_the_sheet_alone_filling_the_canvas(w, wb):
    tabs = w.sheet_tabs
    assert shown(w) is None and tabs.isHidden() and not bar_shown(w)
    click_thumbnail(w, wb.first)
    loads = run_named(w, "Loads")
    assert shown(w) == loads.uid
    assert tabs.isVisible() and bar_shown(w)
    assert [name for _uid, name in tabs.entries] == ["Loads", "Factors"]
    assert w.view.tables.item is loads and w.view.tables.active == (0, 0), "A1, as Excel opens"
    # the canvas is the grid alone: A1's headings at the top left, nothing else
    corner = loads.mapToScene(loads.grid_rect().topLeft())
    assert w.view.mapFromScene(corner) == QPoint(0, 0)
    assert w.view.sceneRect().topLeft() == corner
    assert not others_in_sight(w)
    assert w.view.sceneRect().width() >= seen_rect(w).width() - 1
    assert w.view.sceneRect().height() >= seen_rect(w).height() - 1
    # its pages are still the document's
    assert len(w.document.pages) == 7 and w.current_index == wb.first


def test_scrolling_stays_in_the_sheet_and_the_grid_has_no_end(w, wb):
    click_thumbnail(w, wb.first)
    loads = run_named(w, "Loads")
    bar = w.view.verticalScrollBar()
    rows_before = loads.size[0]
    for _ in range(6):
        QTest.keyClick(w.view, Qt.Key_PageDown)       # (a cell is active: it moves down)
        bar.setValue(bar.maximum())                   # and the bar dragged to its end
        pump()
        assert not others_in_sight(w), "never onto another page"
        assert w.current_index in sheet_pages(w, "Loads")
    assert loads.size[0] > rows_before + 40, "more grid as it is scrolled"
    assert len(w.document.pages) == 7, "scrolling adds no pages"
    across = w.view.horizontalScrollBar()
    across.setValue(across.maximum())
    pump()
    assert not others_in_sight(w)
    # a cell typed into far down: its rows get pages, as typing always did
    far = loads.size[0] - 5
    w.view.tables.select((far, 0))
    type_text(w, "far")
    enter(w)
    pump()
    loads = run_named(w, "Loads")
    assert loads.sheet.cells[(far, 0)].input == "far"
    assert len(sheet_pages(w, "Loads")) > 4 and shown(w) == loads.uid


def test_a_click_on_a_cell_on_its_page_opens_the_workbook_view_at_that_cell(w, wb):
    loads = run_named(w, "Loads")
    w.view.centerOn(cell_scene(loads, "B3"))
    pump()
    click(w, cell_scene(loads, "B3"))
    pump()
    pump()
    assert shown(w) == loads.uid and w.sheet_tabs.isVisible()
    assert w.view.tables.item is loads and w.view.tables.active == (2, 1)
    rect = loads.mapRectToScene(loads.cell_rect(2, 1))
    assert seen_rect(w).contains(rect), "the cell clicked is in view"


def test_the_close_button_goes_back_to_the_page_you_came_from(w, wb):
    view = w.view
    view.set_zoom(0.6)
    w.go_to_page(len(w.document.pages) - 1)
    pump()
    before = (view.zoom(), view.horizontalScrollBar().value(),
              view.verticalScrollBar().value(), w.current_index)
    click_thumbnail(w, wb.first)
    assert shown(w) is not None and view.zoom() == pytest.approx(1.0)
    QTest.mouseClick(w.sheet_tabs.close_button, Qt.LeftButton)
    pump()
    assert shown(w) is None and w.sheet_tabs.isHidden() and not bar_shown(w)
    assert (view.zoom(), view.horizontalScrollBar().value(),
            view.verticalScrollBar().value(), w.current_index) == pytest.approx(before)
    assert w.view.tables.item is None


def test_tabs_change_sheet_and_other_pages_leave(w, wb):
    tabs = w.sheet_tabs
    click_thumbnail(w, wb.first)
    factors = run_named(w, "Factors")
    QTest.mouseClick(tabs.bar, Qt.LeftButton, Qt.NoModifier, tabs.bar.tabRect(1).center())
    pump()
    assert shown(w) == factors.uid and tabs.bar.currentIndex() == 1
    assert w.current_index == sheet_pages(w, "Factors")[0]
    assert not others_in_sight(w), "Loads' pages are not in view either"
    # the page box: a page out of the workbook
    w.page_spin.setValue(1)
    QTest.keyClick(w.page_spin, Qt.Key_Return)
    pump()
    assert shown(w) is None and tabs.isHidden() and w.current_index == 0
    # and back by the page box onto one of its pages
    w.page_spin.setValue(wb.first + 2)
    QTest.keyClick(w.page_spin, Qt.Key_Return)
    pump()
    assert shown(w) == run_named(w, "Loads").uid and w.current_index == wb.first + 1


def test_ctrl_page_keys_go_sheet_by_sheet_and_out_past_the_ends(w, wb):
    click_thumbnail(w, wb.first)
    loads, factors = run_named(w, "Loads"), run_named(w, "Factors")
    key(w, Qt.Key_PageDown, Qt.ControlModifier)
    assert shown(w) == factors.uid
    key(w, Qt.Key_PageDown, Qt.ControlModifier)
    assert shown(w) is None and w.current_index == wb.last + 1, "past the last sheet: out"
    w.go_to_page(wb.first)
    pump()
    assert shown(w) == loads.uid
    key(w, Qt.Key_PageUp, Qt.ControlModifier)
    assert shown(w) is None and w.current_index == wb.first - 1, "before the first: out"


def wheel(w, notches: int, mods=Qt.ControlModifier) -> None:
    view = w.view
    at = QPointF(view.viewport().rect().center())
    event = QWheelEvent(at, QPointF(view.viewport().mapToGlobal(at.toPoint())), QPoint(0, 0),
                        QPoint(0, 120 * notches), Qt.NoButton, mods, Qt.NoScrollPhase, False)
    QApplication.sendEvent(view.viewport(), event)
    view.finish_scrolling()
    pump()


def test_each_workbook_keeps_its_zoom(w, wb):
    view = w.view
    view.set_zoom(0.7)
    click_thumbnail(w, wb.first)
    assert view.zoom() == pytest.approx(1.0)
    wheel(w, 2)
    zoomed = view.zoom()
    assert zoomed > 1.0
    assert not others_in_sight(w)
    click_thumbnail(w, 0)                       # out: the pages' own zoom
    assert shown(w) is None and view.zoom() == pytest.approx(0.7)
    click_thumbnail(w, wb.first)                # in again: the workbook's
    assert view.zoom() == pytest.approx(zoomed)
    wheel(w, -6)                                # zoomed right out: still all grid
    assert view.sceneRect().height() >= seen_rect(w).height() - 1
    assert not others_in_sight(w)


def test_page_breaks_show_dashed_and_no_page_numbers_in_the_workbook_view(w, wb):
    loads = run_named(w, "Loads")
    assert loads._page_numbers() == (2, 3, 4, 5)
    assert run_named(w, "Factors")._page_numbers() == (0,), "it doesn't print: no number"
    drawn = paper_words(loads)
    assert drawn == ["Page 2", "Page 3", "Page 4", "Page 5"]
    assert paper_words(run_named(w, "Factors")) == []
    click_thumbnail(w, wb.first)
    loads = run_named(w, "Loads")
    assert loads.alone and paper_words(loads) == [], "the workbook view: no page numbers"
    pens = break_pens(loads)
    assert pens and all(pen.style() == Qt.DashLine and pen.widthF() <= 1.0 for pen in pens)


def paper_words(item) -> list:
    """What the sheet's paper says (its "Page N"), drawn for real."""
    from PySide6.QtGui import QImage, QPainter
    said = []

    class Listening(QPainter):
        def drawText(self, *args):
            said.append(args[-1])
            return super().drawText(*args)
    image = QImage(400, 400, QImage.Format_ARGB32)
    painter = Listening(image)
    rows = item.sheet_rows
    item._paint_paper(painter, 0, rows - 1)
    painter.end()
    return [s for s in said if isinstance(s, str)]


def break_pens(item) -> list:
    from PySide6.QtGui import QImage, QPainter
    pens = []

    class Listening(QPainter):
        def drawLine(self, *args):
            pens.append(QPainter.pen(self))
            return super().drawLine(*args)
    image = QImage(400, 400, QImage.Format_ARGB32)
    painter = Listening(image)
    item._paint_breaks(painter)
    painter.end()
    return pens


# -- the two bugs --------------------------------------------------------------------------------
def test_from_a_dont_print_sheet_its_entry_and_other_pages_can_be_clicked(w, wb):
    """Stuck in a workbook (the user, 2026-10-22): on its second sheet,
    which doesn't print, a click on the workbook's entry in Thumbnails went
    nowhere — its entry was already the current row."""
    factors = sheet_pages(w, "Factors")[0]
    w.go_to_page(factors)
    pump()
    assert shown(w) == run_named(w, "Factors").uid
    assert not w.document.pages[factors].printable
    click_thumbnail(w, wb.first)
    assert w.current_index == wb.first and shown(w) == run_named(w, "Loads").uid
    w.go_to_page(factors)
    pump()
    click_thumbnail(w, 0)
    assert w.current_index == 0 and shown(w) is None
    # with its pages shown one by one, too
    w.pages_panel.set_expanded(wb.key, True)
    w.go_to_page(factors)
    pump()
    click_thumbnail(w, wb.first + 1)
    assert w.current_index == wb.first + 1 and shown(w) == run_named(w, "Loads").uid
    click_thumbnail(w, len(w.document.pages) - 1)
    assert shown(w) is None and w.current_index == len(w.document.pages) - 1


def tabs_shown(w) -> bool:
    return not w.sheet_tabs.isHidden()


def test_the_tabs_never_show_outside_a_workbook(w, wb, tmp_path):
    """Tabs seen when not in a workbook (the user, 2026-10-22): whatever
    happens, the strip shows only while its view shows a sheet alone."""
    tabs = w.sheet_tabs
    click_thumbnail(w, wb.first)
    assert tabs_shown(w)
    # its sheet deleted from its tab, while shown: out, no tabs
    w.go_to_page(sheet_pages(w, "Factors")[0])
    pump()
    tabs.delete_sheet(1)
    pump()
    assert shown(w) is None and not tabs_shown(w)
    w.undo_stack.undo()
    pump()
    assert not tabs_shown(w), "undone: the pages, no tabs till it is gone to"
    # leaving while a cell is being typed in
    click_thumbnail(w, wb.first)
    type_text(w, "12")
    assert w.view.tables.editor is not None
    click_thumbnail(w, 0)
    assert shown(w) is None and not tabs_shown(w) and not bar_shown(w)
    assert run_named(w, "Loads").sheet.cells[(0, 0)].input == "12", "what was typed is kept"
    # another document's tab, and back
    click_thumbnail(w, wb.first)
    w.open_in_new_tab()
    pump()
    assert not tabs_shown(w) and not bar_shown(w)
    w.document_tabs.setCurrentIndex(0)
    pump()
    assert shown(w) is not None and tabs_shown(w), "its workbook view, as it was left"
    # a file opened: its own pages
    from tests.test_calc_saving import save_to
    path = str(tmp_path / "plain.pdf")
    w.open_in_new_tab()
    pump()
    save_to(w, path)
    w.open_from_command_line(path)
    pump()
    assert not tabs_shown(w)
    # the pages moved under it: still its tabs only while it is shown
    w.document_tabs.setCurrentIndex(0)
    pump()
    assert tabs_shown(w)
    w.move_page(0, len(w.document.pages) - 1)
    pump()
    assert tabs_shown(w) == (shown(w) is not None)


def test_split_view_each_pane_shows_tabs_for_its_own_view(w, wb):
    click_thumbnail(w, wb.first)
    w.open_in_new_tab()
    pump()
    pane = w.split_document(0)                 # the workbook's document beside the new one
    pump()
    assert w.sheet_tabs is pane.sheet_tabs
    assert tabs_shown(w), "the workbook's pane: its tabs"
    other = next(p for p in w._panes if p is not pane)
    assert other.sheet_tabs.isHidden(), "the new document's pane: none"
    w.activate_pane(other)
    pump()
    assert other.sheet_tabs.isHidden() and not pane.sheet_tabs.isHidden()


def test_saved_and_opened_in_the_workbook_view(w, wb, tmp_path):
    import pymupdf

    from tests.test_calc_saving import reopen, save_to
    click_thumbnail(w, wb.first)
    loads = run_named(w, "Loads")
    w.view.tables.select((1, 3))
    type_text(w, "kept")
    enter(w)
    pump()
    saved = str(tmp_path / "view.pdf")
    save_to(w, saved)
    with pymupdf.open(saved) as pdf:
        assert pdf.page_count == len(w.document.pages) - 1, "Factors doesn't print: held back"
        assert "Page" not in pdf[1].get_text(), "no watermark in the file"
    reopen(w, saved)
    pump()
    assert shown(w) is None, "opened: the pages"
    loads = run_named(w, "Loads")
    assert loads.sheet.cells[(1, 3)].input == "kept"
    w.go_to_page(sheetpages.sections(w.document)[0].first)
    pump()
    assert shown(w) == loads.uid
