"""The workbook view's footer, formula bar, keys and selection as Excel's
(docs/qa/excel_audit.md, D1, D2, E1-E3, F1-F5).

* The footer: Ready / Enter / Edit / Point and the Average, Count and Sum
  of the cells picked; Normal, Page Layout and Page Break Preview; a zoom
  slider; the paper's controls away until the pages are shown again.
* The Name Box says "4R × 3C" only while the mouse picks; ✗ and ✓ while a
  cell is typed in; fx starts a formula; the Name Box widens by its dots.
* After F2 the arrows move the caret; Esc never puts the sheet down.
* Ctrl+click adds a block; Ctrl+↓ in an empty column goes to row
  1,048,576; Ctrl+A picks the block of data first; Page Down a screenful.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from calcforge.items.sheetpage import SheetRunItem
from calcforge.ui import sheetpages
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
    w.view.setFocus()
    return shown_run(w)


def at(w, run, row, col) -> QPoint:
    return w.view.mapFromScene(run.mapToScene(run.cell_rect(row, col).center()))


def send(w, kind, point, buttons=Qt.NoButton, button=Qt.NoButton, mods=Qt.NoModifier):
    vp = w.view.viewport()
    p = QPointF(point)
    QApplication.sendEvent(vp, QMouseEvent(kind, p, QPointF(vp.mapToGlobal(p.toPoint())),
                                           button, buttons, mods))
    pump()


def click(w, point, mods=Qt.NoModifier):
    send(w, QEvent.MouseButtonPress, point, Qt.LeftButton, Qt.LeftButton, mods)
    send(w, QEvent.MouseButtonRelease, point, Qt.NoButton, Qt.LeftButton, mods)


def drag(w, start, end, mods=Qt.NoModifier):
    send(w, QEvent.MouseButtonPress, start, Qt.LeftButton, Qt.LeftButton, mods)
    for step in (0.5, 1.0):
        send(w, QEvent.MouseMove, QPointF(start) + (QPointF(end) - QPointF(start)) * step,
             Qt.LeftButton, Qt.NoButton, mods)
    send(w, QEvent.MouseButtonRelease, end, Qt.NoButton, Qt.LeftButton, mods)


def key(w, k, mods=Qt.NoModifier, text=""):
    target = w.view.tables.editor or w.view
    QApplication.sendEvent(target, QKeyEvent(QEvent.KeyPress, k, mods, text))
    pump()


def typed(w, text):
    for ch in text:
        key(w, 0, Qt.NoModifier, ch)


def footer(w):
    return w._sheet_status


# -- D1, D2: the footer ---------------------------------------------------------------------------
def test_the_footer_says_the_mode_and_the_sums_of_the_cells_picked(w, sheet):
    run = sheet
    made = footer(w)
    assert made["mode"].text() == "Ready" and made["mode"].isVisible()
    for name in ("status_position", "status_scale", "status_snap", "status_scroll",
                 "window_sync", "status_size"):
        assert getattr(w, name).isHidden(), f"{name}: the paper's, put away"
    drag(w, at(w, run, 1, 0), at(w, run, 3, 2))
    pump()
    assert made["stats"].text() == "Average: 9    Count: 9    Sum: 81"
    click(w, at(w, run, 1, 0))
    pump()
    assert made["stats"].text() == "", "one cell: no sums"
    typed(w, "5")
    assert made["mode"].text() == "Enter"
    key(w, Qt.Key_Escape)
    key(w, Qt.Key_F2)
    assert made["mode"].text() == "Edit"
    key(w, Qt.Key_Escape)
    typed(w, "=1+")
    assert made["mode"].text() == "Point"
    key(w, Qt.Key_Escape)
    assert made["mode"].text() == "Ready"
    # the pages again: the paper's footer, as it was
    w.sheet_tabs.close_sheet_view()
    pump()
    assert not made["mode"].isVisible()
    assert not w.status_scale.isHidden() or "status_scale" in [
        x.objectName() for x in w.statusBar().dropped()]


def test_the_view_buttons_and_the_slider(w, sheet):
    made = footer(w)
    buttons = made["buttons"]
    assert buttons["normal"].isChecked()
    QTest.mouseClick(buttons["break_preview"], Qt.LeftButton)
    pump()
    assert not shown_run(w).normal_view and buttons["break_preview"].isChecked()
    QTest.mouseClick(buttons["normal"], Qt.LeftButton)
    pump()
    assert shown_run(w).normal_view
    slider = made["slider"]
    slider.setValue(150)
    pump()
    assert w.zoom_combo.currentText() == "150%"
    QTest.mouseClick(buttons["page_layout"], Qt.LeftButton)
    pump()
    assert w.scene.sheet_view is None, "Page Layout: the sheet's pages"
    assert w.document.pages[w.current_index].sheet is not None


def test_page_break_preview_greys_what_does_not_print(w, sheet):
    from PySide6.QtGui import QImage, QPainter
    from calcforge.items.sheetpage import SCRATCH
    w.act_sheet_break_preview.trigger()
    pump()
    run = shown_run(w)
    image = QImage(1200, 400, QImage.Format_ARGB32)
    image.fill(Qt.black)
    painter = QPainter(image)
    run._paint_paper(painter, 0, 5)
    painter.end()
    xs, ys = run.edges()
    inside = image.pixelColor(int(xs[1]), int(ys[2]))
    outside = image.pixelColor(int(xs[run.paging.last_col + 2]) + 2, int(ys[2]))
    assert inside.name() == "#ffffff" and outside == SCRATCH
    # saved with the sheet: Excel keeps the view a sheet was left in
    assert run.sheet.page["view"] == "break_preview"


# -- E1-E3: the Name Box and the formula bar ---------------------------------------------------------
def test_the_name_box_says_rows_by_columns_only_while_the_mouse_picks(w, sheet):
    run = sheet
    bar = w.formula_bar
    start, end = at(w, run, 1, 1), at(w, run, 4, 3)
    send(w, QEvent.MouseButtonPress, start, Qt.LeftButton, Qt.LeftButton)
    send(w, QEvent.MouseMove, end, Qt.LeftButton)
    assert bar.name.text() == "4R × 3C"
    send(w, QEvent.MouseButtonRelease, end, Qt.NoButton, Qt.LeftButton)
    assert bar.name.text() == "B2"


def test_cancel_enter_and_fx_beside_the_formula(w, sheet):
    run = sheet
    bar = w.formula_bar
    click(w, at(w, run, 0, 6))
    assert not bar.cancel_button.isEnabled() and not bar.enter_button.isEnabled()
    typed(w, "42")
    assert bar.cancel_button.isEnabled() and bar.enter_button.isEnabled()
    QTest.mouseClick(bar.cancel_button, Qt.LeftButton)
    pump()
    assert run.sheet.cells.get((0, 6)) is None or run.sheet.cells[(0, 6)].input == ""
    typed(w, "42")
    QTest.mouseClick(bar.enter_button, Qt.LeftButton)
    pump()
    assert shown_run(w).sheet.cells[(0, 6)].input == "42"
    assert w.view.tables.active == (0, 6), "✓ stays on the cell, as Excel's"
    click(w, at(w, run, 1, 6))
    QTest.mouseClick(bar.fx, Qt.LeftButton)
    pump()
    assert w.view.tables.editor is not None and w.view.tables.editor.text() == "="


def test_the_name_box_widens_by_its_dots(w, sheet):
    bar = w.formula_bar
    grip = bar.name_grip
    before = bar.name.width()
    start = grip.mapToGlobal(grip.rect().center())
    QTest.mousePress(grip, Qt.LeftButton, Qt.NoModifier, grip.rect().center())
    QTest.mouseMove(grip, grip.mapFromGlobal(start + QPoint(60, 0)))
    QTest.mouseRelease(grip, Qt.LeftButton, Qt.NoModifier, grip.mapFromGlobal(start + QPoint(60, 0)))
    pump()
    assert bar.name.width() == pytest.approx(before + 60, abs=2)
    assert grip.cursor().shape() == Qt.SplitHCursor


def test_after_f2_the_arrows_move_the_caret(w, sheet):
    run = sheet
    click(w, at(w, run, 4, 5))
    typed(w, "=D5")
    key(w, Qt.Key_F2)                        # Edit mode
    key(w, Qt.Key_Left)
    editor = w.view.tables.editor
    assert editor.text() == "=D5" and editor.cursorPosition() == 2, "the caret moved"


# -- F1: Esc --------------------------------------------------------------------------------------
def test_esc_never_puts_the_sheet_down_and_typing_goes_on(w, sheet):
    run = sheet
    click(w, at(w, run, 2, 6))
    key(w, Qt.Key_Escape)
    tables = w.view.tables
    assert tables.item is shown_run(w) and tables.active == (2, 6)
    assert w.formula_bar.name.text() == "G3"
    typed(w, "7")
    key(w, Qt.Key_Return)
    assert shown_run(w).sheet.cells[(2, 6)].input == "7"


# -- F2-F5: picking -------------------------------------------------------------------------------
def test_ctrl_click_adds_a_block_summed_cleared_and_formatted_together(w, sheet):
    run = sheet
    drag(w, at(w, run, 0, 0), at(w, run, 1, 0))           # A1:A2  (0, 4)
    drag(w, at(w, run, 0, 2), at(w, run, 1, 2), Qt.ControlModifier)   # + C1:C2 (2, 6)
    tables = w.view.tables
    assert tables.extra_ranges == [(0, 0, 1, 0)] and tables.selection() == (0, 2, 1, 2)
    assert footer(w)["stats"].text() == "Average: 3    Count: 4    Sum: 12"
    said = []
    w.view.statusMessage.connect(said.append)
    key(w, Qt.Key_C, Qt.ControlModifier)
    assert "This command cannot be used on multiple selections" in said
    steps = w.undo_stack.count()
    key(w, Qt.Key_B, Qt.ControlModifier)                   # bold, both blocks
    run = shown_run(w)
    wb = run.sheet.workbook
    assert wb.style_of(run.sheet, 0, 0).bold and wb.style_of(run.sheet, 1, 2).bold
    key(w, Qt.Key_Delete)
    run = shown_run(w)
    assert all(run.sheet.input(r, c) == "" for r in (0, 1) for c in (0, 2))
    assert run.sheet.input(0, 1) == "1", "between them: left"
    assert w.undo_stack.count() == steps + 2, "one undo step each"
    # a plain click: one block again
    click(w, at(w, run, 5, 5))
    assert w.view.tables.extra_ranges == []


def test_ctrl_down_in_an_empty_column_goes_to_excels_last_row(w, sheet):
    run = sheet
    click(w, at(w, run, 0, 8))
    key(w, Qt.Key_Down, Qt.ControlModifier)
    assert w.view.tables.active == (1_048_575, 8)
    assert w.formula_bar.name.text() == "I1048576"
    key(w, Qt.Key_Up, Qt.ControlModifier)
    assert w.view.tables.active == (0, 8)
    pump()
    assert w.scene.sheet_extent[0] < 10_000, "back at the top: the grid as it was"


def test_ctrl_a_picks_the_block_of_data_then_the_sheet(w, sheet):
    run = sheet
    click(w, at(w, run, 5, 1))
    key(w, Qt.Key_A, Qt.ControlModifier)
    assert w.view.tables.selection() == (0, 0, 39, 3)
    key(w, Qt.Key_A, Qt.ControlModifier)
    rows, cols = shown_run(w).size
    assert w.view.tables.selection() == (0, 0, rows - 1, cols - 1)


def test_page_down_moves_a_screenful_and_the_window_with_it(w, sheet):
    from calcforge.ui.sheetview import page_rows
    run = sheet
    click(w, at(w, run, 3, 1))
    rows = page_rows(w.view, shown_run(w))
    bar = w.view.verticalScrollBar()
    before = bar.value()
    top_cell = at(w, run, 3, 1).y()
    key(w, Qt.Key_PageDown)
    assert w.view.tables.active == (3 + rows, 1) and rows > 10
    assert bar.value() > before
    run = shown_run(w)
    assert at(w, run, 3 + rows, 1).y() == pytest.approx(top_cell, abs=3), \
        "the cell where the last one was on the screen"
