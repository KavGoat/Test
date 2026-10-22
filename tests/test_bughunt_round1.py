"""Bug hunt, round 1 (2026-10-16): regression tests for what it fixed.

Driven through the real window with events on the viewport, as a mouse does.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from calcforge.items.table import ROWNUM_W
from tests.test_sheet_pages import sheet_page
from tests.test_tables import cell_scene, click, pump
from tests.test_usability import _mouse


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.view.set_zoom(1.0)
    return window


def row_number(run, row):
    """The middle of row *row*'s number, in the strip left of the cells."""
    _xs, ys = run.edges()
    return run.mapToScene(QPointF(-ROWNUM_W / 2, (ys[row] + ys[row + 1]) / 2))


def column_letter(run, col):
    from calcforge.items.table import HEADING_H
    xs, _ys = run.edges()
    return run.mapToScene(QPointF((xs[col] + xs[col + 1]) / 2, -HEADING_H / 2))


def drag_scene(w, a, b):
    vp = w.view.viewport()
    QApplication.sendEvent(vp, _mouse(w.view, QEvent.MouseButtonPress, a.x(), a.y()))
    for t in (0.25, 0.5, 0.75, 1.0):
        QApplication.sendEvent(vp, _mouse(w.view, QEvent.MouseMove, a.x() + (b.x() - a.x()) * t,
                                          a.y() + (b.y() - a.y()) * t, Qt.NoButton, Qt.LeftButton))
    QApplication.sendEvent(vp, _mouse(w.view, QEvent.MouseButtonRelease, b.x(), b.y()))
    pump()


def a_closed_sheet(w, mode):
    run = sheet_page(w)
    w.select_tool("select")
    w.toggle_calc_mode(mode == "calc")
    w.view.tables.close()
    w.view.centerOn(cell_scene(run, "B3"))
    pump()
    assert w.view.tables.item is None and not run.opened
    return run


@pytest.mark.parametrize("mode", ["markup", "calc"])
def test_a_sheet_pages_row_numbers_pick_rows_before_any_cell_is_clicked(w, mode):
    """The user: "in calc mode can't select rows". A spreadsheet page always
    shows its row numbers and column letters, but until a cell had been
    clicked they did nothing at all, in either mode."""
    run = a_closed_sheet(w, mode)
    click(w, row_number(run, 3))
    assert w.view.tables.item is run
    # (the click opened the workbook view, whose grid fills the window)
    last = run.size[1] - 1
    assert w.view.tables.selection() == (3, 0, 3, last)

    w.view.tables.close()
    drag_scene(w, row_number(run, 2), row_number(run, 5))
    assert w.view.tables.selection() == (2, 0, 5, last)
    click(w, row_number(run, 7), Qt.ShiftModifier)
    assert w.view.tables.selection() == (2, 0, 7, last)

    w.view.tables.close()
    click(w, column_letter(run, 2))
    assert w.view.tables.selection() == (0, 2, run.size[0] - 1, 2)


@pytest.mark.parametrize("mode", ["markup", "calc"])
def test_right_clicking_a_closed_sheets_row_number_gives_the_row_menu(w, mode):
    run = a_closed_sheet(w, mode)
    seen = []

    def look():
        popup = QApplication.activePopupWidget()
        if popup is not None:
            seen.append([a.text() for a in popup.actions() if a.text()])
            popup.close()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(look)
    timer.start(100)
    point = w.view.mapFromScene(row_number(run, 4))
    QTest.mouseClick(w.view.viewport(), Qt.RightButton, Qt.NoModifier, point)
    pump()
    if not seen:     # the platform sends the context-menu event itself on some
        from PySide6.QtGui import QContextMenuEvent
        vp = w.view.viewport()
        timer.start(100)
        QApplication.sendEvent(vp, QContextMenuEvent(QContextMenuEvent.Mouse, point,
                                                     vp.mapToGlobal(point)))
        pump()
    assert w.view.tables.selection() == (4, 0, 4, run.size[1] - 1)
    assert seen and "Insert Rows Above" in seen[0] and "Delete Rows" in seen[0]


@pytest.mark.parametrize("opened", [False, True])
@pytest.mark.parametrize("mode", ["markup", "calc"])
def test_the_kept_headings_pick_a_row_without_scrolling_the_sheet(w, mode, opened):
    """Scrolled down and across a sheet, its row numbers stay down the left of
    the canvas. A click on one picked the row and then scrolled the canvas
    back to column A — or, with the sheet not open yet, up to A1 and down
    again — so the row clicked was no longer under the pointer. Excel never
    scrolls for a heading."""
    run = sheet_page(w)
    w.select_tool("select")
    w.toggle_calc_mode(mode == "calc")
    if opened:
        click(w, cell_scene(run, "B2"))
    else:
        w.view.tables.close()
    w.view.set_zoom(2.0)
    w.view.centerOn(cell_scene(run, "H40"))
    pump()
    headings = w.view.sheet_headings
    headings.refresh()
    pump()
    strips = [rect for _run, kind, rect in headings._strips if kind == "row"]
    assert strips, "the row numbers are kept in view"
    where = QPointF(strips[0].center())
    _run, (_kind, row) = headings.hit(where)
    h, v = w.view.horizontalScrollBar().value(), w.view.verticalScrollBar().value()
    click(w, w.view.mapToScene(where.toPoint()))
    assert w.view.tables.selection() == (row, 0, row, run.size[1] - 1)
    if opened:
        assert (w.view.horizontalScrollBar().value(),
                w.view.verticalScrollBar().value()) == (h, v)
    # (closed, the click opened the workbook view: the pages round the sheet
    # went, and the sheet stayed where it was on the screen)
    assert headings.hit(where)[1] == ("row", row), "the row clicked is still under the pointer"


# -- function keys while typing in a box -------------------------------------------------------
def _search_field(w):
    w.find_in_document()
    pump()
    field = QApplication.focusWidget()
    return field, field.text


def _formula_bar(w, part):
    run = sheet_page(w)
    click(w, cell_scene(run, "C3"))
    edit = getattr(w.view.tables.bar, part)
    edit.setFocus()
    pump()
    return edit, edit.text


def _size_field(w):
    from tests.test_usability import click as press
    from calcforge.core.document import PageScale
    # the size box rides only Sketch to Scale's shapes (the user, 2026-10-17)
    w.current_page().scale = PageScale.from_ratio(50)
    w.select_tool("sketch_rect")
    press(w.view, 150, 300)
    pump()
    assert w.view._size_editor is not None
    return w.view._size_width, w.view._size_width.text


def _dimension_words(w):
    from tests.test_usability import drag
    from calcforge.core.document import PageScale
    # a dimension asks for a scale on a page with none (exercise round 1, F-19)
    w.current_page().scale = PageScale.from_ratio(50)
    w.interactive_prompts = True
    try:
        w.select_tool("measure_dimension")
        drag(w.view, 100, 200, 320, 200)
    finally:
        w.interactive_prompts = False
    pump()
    editor = w.view._label_editor
    assert editor is not None
    return editor, editor.text


def _properties_field(w):
    from PySide6.QtCore import QRectF
    from PySide6.QtWidgets import QLineEdit
    from calcforge.items.shapes import RectItem
    box = RectItem("rect", QRectF(0, 0, 40, 30))
    w.document.pages[0].frame.add_markup(box, QPointF(200, 200))
    box.setSelected(True)
    w.view.selectionChanged.emit()
    w.show_properties_panel()
    pump()
    field = w.findChild(QLineEdit, "markupSubject")
    field.setFocus()
    pump()
    return field, field.text


@pytest.mark.parametrize("where", ["search", "formula bar", "name box", "typed size",
                                   "dimension words", "properties"])
def test_function_keys_belong_to_the_box_being_typed_in(w, where):
    """F12 switched to Calc mode, F11 went full screen, F9 calculated and F7
    opened the spelling check in the middle of a word typed into a box —
    though a cell, an equation and a text box already kept them. Every box
    keeps them now; F1 (Help) still works."""
    field, text = {"search": _search_field,
                   "formula bar": lambda w: _formula_bar(w, "edit"),
                   "name box": lambda w: _formula_bar(w, "name"),
                   "typed size": _size_field,
                   "dimension words": _dimension_words,
                   "properties": _properties_field}[where](w)
    fired = []
    for action in (w.act_calc_mode, w.act_calculate, w.act_full_screen, w.act_check_spelling):
        action.triggered.connect(lambda *_a, a=action: fired.append(a.text()))
    mode = w.view.calc.mode
    for key in (Qt.Key_F12, Qt.Key_F11, Qt.Key_F9, Qt.Key_F7):
        QTest.keyClick(QApplication.focusWidget() or field, key)
        pump()
    assert w.view.calc.mode == mode and not w.isFullScreen()
    assert not fired
    QTest.keyClick(QApplication.focusWidget() or field, "7")
    pump()
    assert "7" in text(), "and the box still takes what is typed"


# -- the crash log, after the application has closed ------------------------------------------
def test_closing_the_app_hands_back_the_error_hook_and_the_crash_dump(qapp, tmp_path, monkeypatch):
    """main() pointed faulthandler and the error hook at crash.log, then
    closed the file and left both pointing at it. Every Python error after
    that came out as "I/O operation on closed file", and a hard crash wrote
    its dump to whatever had been given the file's descriptor since — which
    is why a worker that died in the test suite left no dump behind."""
    import faulthandler
    import io
    import sys
    from calcforge import app as entry
    from calcforge.ui.mainwindow import MainWindow

    def run_briefly(self=None):
        for window in QApplication.topLevelWidgets():
            if isinstance(window, MainWindow):
                window.confirm_discard = lambda: True
                window.document.modified = False
                window.close()
        return 0

    monkeypatch.setattr(entry, "crash_log_path", lambda: str(tmp_path / "crash.log"))
    monkeypatch.setattr(entry, "build_application", lambda argv: QApplication.instance())
    monkeypatch.setattr(QApplication, "exec", run_briefly)
    monkeypatch.setattr(MainWindow, "offer_recovery", lambda self: None)
    hook, was_on = sys.excepthook, faulthandler.is_enabled()
    try:
        assert entry.main(["calcforge"]) == 0
        assert sys.excepthook is hook, "the error hook is handed back"
        assert faulthandler.is_enabled() == was_on
        said = io.StringIO()
        monkeypatch.setattr(sys, "stderr", said)
        try:
            raise RuntimeError("after the window has gone")
        except RuntimeError:
            sys.excepthook(*sys.exc_info())
        assert "closed file" not in said.getvalue()
        assert "closed normally (0)" in (tmp_path / "crash.log").read_text(encoding="utf-8")
    finally:
        sys.excepthook = hook
        if not was_on and faulthandler.is_enabled():
            faulthandler.disable()
