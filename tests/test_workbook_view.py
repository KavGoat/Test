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
  sheet's pages is its number as printed, none on a page that doesn't
  print (tests/test_workbook_pages.py).

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
from calcforge.ui.sheetview import EXCEL_SCALE  # noqa: E402
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
    # Excel's 100 % (the user, H1): cells drawn at 96 px an inch
    assert shown(w) is not None and view.zoom() == pytest.approx(EXCEL_SCALE)
    assert w.zoom_combo.currentText() == "100%"
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
    assert view.zoom() == pytest.approx(EXCEL_SCALE)
    wheel(w, 2)
    zoomed = view.zoom()
    assert zoomed > EXCEL_SCALE
    assert not others_in_sight(w)
    click_thumbnail(w, 0)                       # out: the pages' own zoom
    assert shown(w) is None and view.zoom() == pytest.approx(0.7)
    click_thumbnail(w, wb.first)                # in again: the workbook's
    assert view.zoom() == pytest.approx(zoomed)
    wheel(w, -6)                                # zoomed right out: still all grid
    assert view.sceneRect().height() >= seen_rect(w).height() - 1
    assert not others_in_sight(w)


def test_page_breaks_show_dashed_and_the_page_numbers_stay_in_the_workbook_view(w, wb):
    loads = run_named(w, "Loads")
    assert loads._page_numbers() == (2, 3, 4, 5)
    assert run_named(w, "Factors")._page_numbers() == (0,), "it doesn't print: no number"
    drawn = paper_words(loads)
    assert drawn == ["Page 2", "Page 3", "Page 4", "Page 5"]
    assert paper_words(run_named(w, "Factors")) == []
    click_thumbnail(w, wb.first)
    loads = run_named(w, "Loads")
    # "the background page number thing is lost" (the user, 2026-10-22)
    assert loads.alone and paper_words(loads) == drawn, "the workbook view: numbered too"
    pens = break_pens(loads)
    assert pens and all(pen.style() == Qt.DashLine for pen in pens), "the pages' dashed blue breaks"


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


# -- the user, 2026-10-22 (night): "a page on insert (why, I asked for the
# canvas)"; the page rulers over the cells; "horizontal scroll ... too small"

def test_insert_spreadsheet_page_opens_the_new_sheet_alone(w):
    from calcforge.ui.sheetview import run_shown
    pages = len(w.document.pages)
    w.act_add_sheet_page.trigger()
    pump()
    assert len(w.document.pages) == pages + 1
    page = w.document.pages[w.current_index]
    assert page.sheet is not None
    assert run_shown(w.scene) is not None, "the new sheet is shown alone, as Excel opens one"
    assert w.view.tables.item is not None and w.view.tables.active == (0, 0)


def test_no_page_rulers_over_a_sheet_shown_alone(w):
    w.act_rulers.setChecked(True)
    pump()
    assert w.view.rulers.on
    w.act_add_sheet_page.trigger()
    pump()
    assert shown(w) is not None
    assert not w.view.rulers.on, "Excel's Normal view has no rulers"
    w.act_rulers.setChecked(False)
    w.act_rulers.setChecked(True)          # turned on while there: still none
    pump()
    assert not w.view.rulers.on
    from calcforge.ui import sheetview
    sheetview.leave(w)
    pump()
    assert w.view.rulers.on, "back on the pages, the rulers are back"
    w.act_rulers.setChecked(False)


def test_a_new_sheets_scroll_thumbs_are_big(w):
    w.act_add_sheet_page.trigger()
    pump()
    for bar in (w.view.horizontalScrollBar(), w.view.verticalScrollBar()):
        span = bar.maximum() - bar.minimum() + bar.pageStep()
        assert bar.pageStep() / span >= 0.45, "the thumb is about half the bar or more"
    # scrolled into, the grid grows; and Page Down goes a whole screenful
    bar = w.view.verticalScrollBar()
    before = bar.maximum()
    bar.setValue(bar.maximum())
    pump()
    assert bar.maximum() > before


def _edges(get, first, last):
    """Where a line darker than both its neighbours two pixels away is."""
    found = []
    for i in range(first + 2, last - 2):
        here = get(i)
        if here + 10 < get(i - 2) and here + 10 < get(i + 2) and (not found or i - found[-1] > 2):
            found.append(i)
    return found


@pytest.mark.parametrize("zoom", [1.0, 1.15, 1.45, 2.5, 3.3])
def test_the_kept_headings_edges_are_on_the_grids_lines(w, zoom):
    """The user, 2026-10-22: zoomed in, "Excel top left is still not
    aligning correctly" — the headings kept at the top and left were drawn
    rounded to whole pixels, a pixel or two off the grid's lines. Each row
    number's edge is on its grid line's pixel, scrolled or not."""
    w.act_add_sheet_page.trigger()
    pump()
    view = w.view
    view.set_zoom(EXCEL_SCALE * zoom)
    QTest.qWait(700)                       # the zoom settled: the grid drawn sharp
    for down in (0, 53, 97):
        view.verticalScrollBar().setValue(view.verticalScrollBar().minimum() + down)
        QTest.qWait(80)
        pump()
        image = view.grab(view.viewport().geometry()).toImage()
        light = lambda x, y: image.pixelColor(x, y).lightness()   # noqa: E731
        top = int(60 * zoom)
        numbers = _edges(lambda y: light(3, y), top, image.height() - 20)[:6]
        grid = _edges(lambda y: light(image.width() // 2 + 3, y), top, image.height() - 20)[:6]
        assert numbers and numbers == grid, f"scrolled {down}: {numbers} against {grid}"


def _top_left_cell(w):
    """(the cell at the grid's top left, where its corner is in the view)."""
    from calcforge.ui.sheetview import zoom_anchor
    view = w.view
    item = next(i for i in view.scene().items() if isinstance(i, SheetRunItem)
                and i.uid == shown(w))
    at = zoom_anchor(view)
    cell = item.cell_at(item.mapFromScene(view.mapToScene((at + QPointF(2, 2)).toPoint())))
    corner = view.mapFromScene(item.mapToScene(item.cell_rect(*cell).topLeft()))
    return cell, corner


def test_a_zoom_keeps_the_top_left_cell_where_it_is_as_excels(w):
    """The user, 2026-10-22: "doesn't zoom where I would expect it to, try
    Excel's zoom and compare". Excel grows the sheet down and to the right
    from the cell at the top left; it zoomed about the pointer, as a drawing
    does. The Ctrl+wheel, the zoom box and the slider alike."""
    w.act_add_sheet_page.trigger()
    pump()
    view = w.view
    view.verticalScrollBar().setValue(view.verticalScrollBar().minimum() + 400)
    view.horizontalScrollBar().setValue(view.horizontalScrollBar().minimum() + 300)
    pump()
    view.tables.select(_top_left_cell(w)[0])      # the active cell in sight, at the top left
    pump()
    from calcforge.ui.sheetview import zoom_anchor
    before, _corner = _top_left_cell(w)           # (picking it brought it wholly in)
    point = view.mapToScene(zoom_anchor(view).toPoint())
    wheel(w, 2)                                   # Ctrl+wheel in, pointer mid-window
    after, _landed = _top_left_cell(w)
    assert after == before, "the same cell at the top left"
    # the very point of the sheet that was at the headings' corner still is
    # (they grow with the zoom, as Excel's do)
    now = view.mapToScene(zoom_anchor(view).toPoint())
    slack = 1.5 / view.zoom()
    assert abs(now.x() - point.x()) <= slack and abs(now.y() - point.y()) <= slack
    for zoom in (lambda: wheel(w, -1), lambda: wheel(w, -1), lambda: wheel(w, -1),
                 lambda: view.set_zoom(view.zoom() * 1.3)):     # the zoom box, the slider
        zoom()
        pump()
        now = view.mapToScene(zoom_anchor(view).toPoint())
        slack = 1.5 / view.zoom()
        assert abs(now.x() - point.x()) <= slack and abs(now.y() - point.y()) <= slack, \
            "a run of zooms never creeps away from it"


def test_a_zoom_brings_the_active_cell_back_into_sight(w):
    w.act_add_sheet_page.trigger()
    pump()
    view = w.view
    tables = view.tables
    # an active cell at the bottom right of the window: zoomed in, it would go
    port = view.viewport().rect()
    item = tables.item
    cell = item.cell_at(item.mapFromScene(view.mapToScene(port.width() - 60, port.height() - 40)))
    tables.select(cell)
    pump()
    wheel(w, 4)
    rect = view.mapFromScene(item.mapToScene(item.cell_rect(*cell))).boundingRect()
    assert port.adjusted(-1, -1, 1, 1).intersects(rect) and rect.height() > 4, \
        "still in sight after the zoom"
