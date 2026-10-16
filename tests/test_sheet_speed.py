"""Spreadsheets as smooth as markups (2026-10-16): timings and repaint counts
through the real window, with thresholds two to three times the budgets in
docs/AGENT_PROMPT.md so that a loaded machine does not make them flake.

What they hold down, each found by measuring:
- a cell being typed in no longer repaints the canvas without end (its text
  box's style sheet was set again on every repaint, which repainted it);
- a key typed, a cell picked or an arrow key redraws only around it, not
  every cell of the table;
- undo and redo of a cell put back only the cells that differ, instead of
  rebuilding the sheet and calculating every cell again;
- calculating a column of running totals does not walk each block it reads;
- a screenful of cells is drawn from what was worked out for it before.
"""
from __future__ import annotations

import statistics
import time

import pytest
from PySide6.QtCore import QEvent, QObject, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from calcforge.items.sheetpage import SheetRunItem
from calcforge.items.table import TableItem
from tests.test_tables import click, make_table


def idle():
    """The events of the moment handled, and the page's drawing tiles all in.

    A tile arriving repaints what lies over it, the table included, so a
    count of cells drawn taken while tiles were still coming (a loaded
    machine, the full suite in parallel) counted the tiles, not the key."""
    import time
    from calcforge.io import pdftiles
    app = QApplication.instance()
    deadline = time.monotonic() + 10
    while True:
        for _ in range(4):
            app.processEvents()
        if not pdftiles.TILES._waiting and not pdftiles.TILES.held():
            break
        if time.monotonic() > deadline:
            break
        time.sleep(0.02)


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.view.set_zoom(1.0)
    idle()
    return window


def timed(action, n=5, setup=None, fastest=False) -> float:
    """Median (or, *fastest*, least) milliseconds of action() and the events
    it leaves."""
    times = []
    for _ in range(n):
        if setup is not None:
            setup()
            idle()
        start = time.perf_counter()
        action()
        idle()
        times.append((time.perf_counter() - start) * 1000)
    return min(times) if fastest else statistics.median(times)


def key(w, k, mods=Qt.NoModifier, text=""):
    target = w.view.tables.editor or w.view
    QApplication.sendEvent(target, QKeyEvent(QKeyEvent.KeyPress, k, mods, text))


def type_in(w, text):
    for ch in text:
        key(w, 0, text=ch)
        idle()


class Paints(QObject):
    """Paint events reaching a widget."""

    def __init__(self, widget):
        super().__init__()
        self.count = 0
        widget.installEventFilter(self)

    def eventFilter(self, _obj, event):
        if event.type() == QEvent.Paint:
            self.count += 1
        return False


class Calls:
    """How often a method is called (patched for the test)."""

    def __init__(self, monkeypatch, owner, name, only=None):
        """*only*: count calls on that object alone. Windows left by earlier
        tests in the same worker still paint their own tables, and counting
        those made a loaded, parallel run fail on someone else's cells."""
        self.count = 0
        original = getattr(owner, name)

        def counted(*args, **kwargs):
            if only is None or (args and args[0] is only):
                self.count += 1
            return original(*args, **kwargs)
        monkeypatch.setattr(owner, name, counted)


def the_run(w):
    (run,) = [i for i in w.view.scene().items() if isinstance(i, SheetRunItem)]
    return run


def sheet_with_formulas(w, n=300):
    """A spreadsheet page with n quantities, n formulas with units, and 300
    formulas reading F1; its pages all there and the undo history clear."""
    w.insert_sheet_page(0)
    idle()
    run = the_run(w)
    sheet = run.sheet
    wb = sheet.workbook
    with wb.transaction("Fill"):
        for r in range(n):
            wb.set_input(sheet, r, 0, f"{r + 1} kN")
            wb.set_input(sheet, r, 1, f"{(r % 7) + 1} m")
            wb.set_input(sheet, r, 2, f"=A{r + 1}*B{r + 1}")
            wb.set_input(sheet, r, 6, f"=$F$1*C{r + 1}")
        wb.set_input(sheet, 0, 5, "2")
    from calcforge.ui import sheetpages
    short = sheetpages.short_runs(w)
    if short:
        sheetpages.add_run_pages(w, short)
    idle()
    w.undo_stack.clear()
    return the_run(w)


def open_cell(w, item, row, col):
    pos = item.mapToScene(item.cell_rect(row, col).center())
    w.view.centerOn(pos)
    idle()
    click(w, pos)
    idle()
    assert w.view.tables.item is item


def a_table(w, rows=40, cols=10):
    table = make_table(w, 72, 100, 48 * 3, 15 * 4)
    table.resize_table(rows, cols)
    sheet = table.sheet
    wb = sheet.workbook
    with wb.transaction("Fill"):
        for r in range(rows):
            wb.set_input(sheet, r, 0, f"{r + 1} kN")
            wb.set_input(sheet, r, 2, f"=A{r + 1}*2")
    idle()
    pos = table.mapToScene(table.cell_rect(1, 1).center())
    w.view.centerOn(pos)
    idle()
    click(w, pos, double=True)
    idle()
    if w.view.tables.editor is not None:
        key(w, Qt.Key_Escape)
        idle()
    assert w.view.tables.item is table
    return table


# -- typing -------------------------------------------------------------------------------------
def test_a_cell_being_typed_in_does_not_repaint_the_canvas_without_end(w):
    run = sheet_with_formulas(w, 40)
    open_cell(w, run, 3, 1)
    type_in(w, "12")
    idle()
    paints = Paints(w.view.viewport())
    for _ in range(10):
        QApplication.instance().processEvents()
    assert paints.count == 0          # was one a turn of the event loop, forever


def test_a_key_typed_into_a_cell_is_quick_and_redraws_no_cells(w, monkeypatch):
    run = sheet_with_formulas(w)
    open_cell(w, run, 30, 1)
    type_in(w, "1")
    drawn = Calls(monkeypatch, TableItem, "_paint_text")
    ms = timed(lambda: type_in(w, "2"), n=7)
    assert ms < 100                    # budget: 50 ms
    assert drawn.count == 0            # the sheet's pictures are not drawn again


def test_a_key_typed_into_a_table_markup_redraws_only_the_cell(w, monkeypatch):
    table = a_table(w)
    w.view.tables.select((20, 1))
    idle()
    type_in(w, "1")
    drawn = Calls(monkeypatch, TableItem, "_paint_text", only=table)
    per_key = []

    def key_once():
        before = drawn.count
        type_in(w, "2")
        idle()
        per_key.append(drawn.count - before)
    ms = timed(key_once, n=7)
    assert ms < 100
    # 80 filled cells: all of them for each of 8 repaints a key, before. The
    # typical key is judged: in the full parallel suite one key in a few
    # also met an unrelated full repaint (findings 7.6)
    assert statistics.median(per_key) < 20, per_key


def test_enter_and_300_dependent_formulas_recalculate_within_budget(w):
    run = sheet_with_formulas(w)
    open_cell(w, run, 0, 5)
    values = iter(range(3, 100))

    def start():
        w.view.tables.select((0, 5))
        type_in(w, str(next(values)))
    ms = timed(lambda: key(w, Qt.Key_Return), setup=start)
    assert ms < 250                     # budget: 100 ms for 300 formulas
    sheet = run.sheet
    assert sheet.value(299, 6).si == pytest.approx(sheet.value(0, 5) * sheet.value(299, 2).si)


# -- undo ------------------------------------------------------------------------------------------
def test_undo_and_redo_of_a_cell_put_back_only_that_cell(w):
    run = sheet_with_formulas(w)
    open_cell(w, run, 30, 0)
    type_in(w, "77 kN")
    key(w, Qt.Key_Return)
    idle()
    sheet = run.sheet
    typed = sheet.value(30, 2)
    stack = w.undo_stack
    te = w.view.tables
    undo = timed(stack.undo, n=1)
    assert the_run(w) is run           # not rebuilt
    assert sheet.input(30, 0) == "31 kN" and sheet.value(30, 2) != typed
    assert te.item is run and te.bar.edit.text() == sheet.input(*te.active)
    redo = timed(stack.redo, n=1)
    assert sheet.input(30, 0) == "77 kN" and sheet.value(30, 2) == typed
    # rebuilt, it was 115 ms here, and 6.5 s in a workbook of 3000 rows
    assert max(undo, redo) < 250


def test_undo_of_a_table_markup_keeps_the_table(w):
    table = a_table(w, rows=12, cols=4)
    w.view.tables.select((3, 1))
    type_in(w, "5")
    key(w, Qt.Key_Return)
    idle()
    w.undo_stack.undo()
    idle()
    (now,) = [i for i in w.view.scene().items() if isinstance(i, TableItem)]
    assert now is table and table.sheet.input(3, 1) == ""
    w.undo_stack.redo()
    idle()
    assert table.sheet.input(3, 1) == "5"


# -- calculating -------------------------------------------------------------------------------------
def test_running_totals_are_ordered_without_walking_their_blocks(monkeypatch):
    """=SUM($D$1:D2), =SUM($D$1:D3)...: ordering them walked every block
    they read, square in the column's length (3.9 s for one value typed above
    3000 of them, 1.1 s now)."""
    from calcforge.sheet.workbook import Sheet, Workbook
    wb = Workbook()
    s = wb.add_sheet()
    n = 600
    with wb.transaction():
        for r in range(1, n + 1):
            wb.set_input(s, r - 1, 1, str(r * 1.5))
            wb.set_input(s, r - 1, 3, f"=B{r}*2")
            wb.set_input(s, r - 1, 4, f"=SUM($D$1:D{r})")
    walked = [0]
    original = Sheet.positions_in

    def counting(self, *args):
        for got in original(self, *args):
            walked[0] += 1
            yield got
    monkeypatch.setattr(Sheet, "positions_in", counting)
    start = time.perf_counter()
    wb.set_input(s, 10, 1, "7")
    took = time.perf_counter() - start
    assert s.value(n - 1, 4) == pytest.approx(sum((r * 1.5) * 2 for r in range(1, n + 1))
                                              - 11 * 1.5 * 2 + 7 * 2)
    assert walked[0] < 5000             # was n * n / 2 * 2 = 360 000 here
    assert took < 1.0


# -- drawing -----------------------------------------------------------------------------------------
def test_a_screenful_of_cells_is_drawn_from_what_was_worked_out_before(w, monkeypatch):
    run = sheet_with_formulas(w)
    xs, ys = run.edges()
    picture = QPixmap(int(xs[-1]), int(ys[48]))

    def draw():
        painter = QPainter(picture)
        run._paint_rows(painter, 0, 47)
        painter.end()
    draw()
    from calcforge.sheet import numfmt
    fits = Calls(monkeypatch, numfmt, "general_fit")
    # the fastest of five measures the drawing; the median measured the
    # machine, and a loaded full run made a 12 ms draw take 78 ms
    ms = timed(draw, n=5, fastest=True)
    assert fits.count == 0             # numbers too wide are fitted once, not every picture
    assert ms < 60                      # 39 ms before, 12 ms now


def test_picking_cells_in_a_table_markup_redraws_only_around_them(w, monkeypatch):
    table = a_table(w)
    cells = iter([(3, 1), (4, 2)] * 10)

    def pick():
        r, c = next(cells)
        click(w, table.mapToScene(table.cell_rect(r, c).center()))
    # The first click opens the table, which draws all of it once (and twice
    # on a loaded machine, as its repaints are coalesced less): picking cells
    # is what is counted, so the table is open before counting starts.
    pick()
    idle()
    drawn = Calls(monkeypatch, TableItem, "_paint_text", only=table)
    ms = timed(pick, n=6)
    assert ms < 100
    assert drawn.count / 6 < 25        # every one of its 80 filled cells, before
    arrows = timed(lambda: key(w, Qt.Key_Down), n=6)
    assert arrows < 100


# -- moving about --------------------------------------------------------------------------------------
def test_clicks_arrows_zoom_and_pages_within_budget(w):
    run = sheet_with_formulas(w)
    open_cell(w, run, 2, 1)
    te = w.view.tables
    cells = iter([(3, 1), (4, 2)] * 10)

    def pick():
        r, c = next(cells)
        click(w, run.mapToScene(run.cell_rect(r, c).center()))
    assert timed(pick) < 100            # budget 50 ms
    assert timed(lambda: key(w, Qt.Key_Down), n=9) < 100
    zooms = iter([1.25, 1.0] * 5)
    assert timed(lambda: w.view.set_zoom(next(zooms)), n=4) < 250      # budget 100 ms
    w.view.set_zoom(1.0)
    pages = iter([1, 0] * 5)
    assert timed(lambda: w.go_to_page(next(pages)), n=4) < 150          # budget 50 ms
    # Calc mode (F12): a click still goes to the cell
    w.toggle_calc_mode(True)
    idle()
    target = run.mapToScene(run.cell_rect(6, 2).center())
    w.view.centerOn(target)
    idle()
    click(w, target)
    idle()
    assert te.item is run and te.active == (6, 2)
    w.toggle_calc_mode(False)
