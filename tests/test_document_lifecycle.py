"""What belongs to a document goes with it; undo puts things back as they
were seen (QA exercise round 1: F-01, F-02, F-04, F-09, F-14, F-21, F-23,
F-28, F-31, F-34).

Everything here is driven the way a person does it: keys through the
shortcut map (``QTest.keyClick``), drags and clicks on the canvas, the real
menus, and the dialogs' own buttons.
"""
from __future__ import annotations

import gc
import sys
import traceback

import pytest
import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QWidget

from calcforge.items.calc import CalcItem
from calcforge.items.shapes import RectItem
from calcforge.ui.mainwindow import MainWindow

#: Revu's step for a duplicate of a drawn markup (mainwindow.COPY_NUDGE)
COPY_NUDGE = 12.0
from tests.test_calc_panels import an_equation
from tests.test_usability import click, drag, hover, on_page


def settle(times: int = 4):
    app = QApplication.instance()
    for _ in range(times):
        app.processEvents()


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.view.set_zoom(1.0)
    settle()
    return window


@pytest.fixture
def errors(monkeypatch):
    """Python errors raised in Qt's callbacks (they never reach pytest)."""
    seen = []
    monkeypatch.setattr(sys, "excepthook",
                        lambda *info: seen.append("".join(traceback.format_exception(*info))))
    return seen


def key(w, k, mods=Qt.NoModifier):
    QTest.keyClick(w.view, k, mods)
    settle()


def rects(w):
    return [i for i in w.view.scene().ordered_markups() if isinstance(i, RectItem)]


def draw_rect(w, x=100, y=100, width=120, height=80):
    key(w, Qt.Key_R)
    a = on_page(w, w.current_index, x, y)
    b = on_page(w, w.current_index, x + width, y + height)
    drag(w.view, *a, *b)
    settle()
    if w.view.tool_key != "select":
        key(w, Qt.Key_V)


def pick(w, item):
    """Click the item where it is drawn, with Select in hand (an equation:
    drag a box round it, as a click goes into its words)."""
    w.view.set_tool("select")
    if isinstance(item, CalcItem):
        w.view.scene().clearSelection()
        box = item.sceneBoundingRect().adjusted(-6, -6, 6, 6)
        drag(w.view, box.left(), box.top(), box.right(), box.bottom())
        settle()
        assert item.isSelected() and not w.view.calc.editing()
        return
    centre = item.mapToScene(item.local_rect().topLeft() + QPointF(1, 1))
    w.view.scene().clearSelection()
    click(w.view, centre.x(), centre.y())
    settle()
    if not item.isSelected():                      # a fill-less shape is picked by its edge
        item.setSelected(True)
    assert item.isSelected()


def menu_click(w, title, *path):
    """Open the menu bar's *title* menu by mouse and click down *path*."""
    bar = w.menuBar()
    top = next(a for a in bar.actions() if a.text().replace("&", "") == title)
    QTest.mouseClick(bar, Qt.LeftButton, Qt.NoModifier, bar.actionGeometry(top).center())
    settle()
    menu = top.menu()
    for name in path:
        assert menu.isVisible()
        entry = next(a for a in menu.actions() if a.text().replace("&", "") == name)
        QTest.mouseMove(menu, menu.actionGeometry(entry).center())
        settle()
        QTest.mouseClick(menu, Qt.LeftButton, Qt.NoModifier, menu.actionGeometry(entry).center())
        settle()
        menu = entry.menu()


def new_pdf(w):
    key(w, Qt.Key_N, Qt.ControlModifier)
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    gc.collect()
    settle()


# -- F-01: an Offset (or any other gesture) does not outlive its document ------------------
def test_offset_then_new_pdf_then_a_drag_draws(w, errors):
    draw_rect(w)
    (box,) = rects(w)
    pick(w, box)
    key(w, Qt.Key_O)                      # Edit ▸ Offset
    assert w._offset is not None
    new_pdf(w)                            # File ▸ New PDF, Offset still under way
    assert w._offset is None
    assert not w.offset_toolbar().isVisible()
    draw_rect(w)                          # crashed the application before
    assert len(rects(w)) == 1
    assert not errors


def test_escape_on_the_canvas_ends_offset(w):
    draw_rect(w)
    (box,) = rects(w)
    pick(w, box)
    key(w, Qt.Key_O)
    assert w._offset is not None
    key(w, Qt.Key_Escape)                 # Esc reaches the view, not its viewport
    assert w._offset is None
    assert not w.offset_toolbar().isVisible()


def test_offset_then_another_tab_then_a_drag_draws(w, errors):
    draw_rect(w)
    (box,) = rects(w)
    pick(w, box)
    key(w, Qt.Key_O)
    key(w, Qt.Key_T, Qt.ControlModifier)  # File ▸ New Tab
    assert w._offset is None
    draw_rect(w)
    assert len(rects(w)) == 1
    assert not errors


@pytest.mark.parametrize("gesture", ["drawing", "equation", "crop", "paste_here", "multiply"])
def test_nothing_under_way_survives_new_pdf(w, errors, gesture):
    """Offset's siblings: whatever is half done goes with the canvas."""
    if gesture == "drawing":
        key(w, Qt.Key_R)
        a = on_page(w, 0, 100, 100)
        b = on_page(w, 0, 200, 200)
        QTest.mousePress(w.view.viewport(), Qt.LeftButton, Qt.NoModifier,
                         w.view.mapFromScene(QPointF(*a)))
        QTest.mouseMove(w.view.viewport(), w.view.mapFromScene(QPointF(*b)))
    elif gesture == "equation":
        an_equation(w, "a:=2")
        w.view.calc.enter_item(next(i for i in w.view.scene().items() if isinstance(i, CalcItem))) \
            if hasattr(w.view.calc, "enter_item") else None
    elif gesture == "crop":
        w.select_tool("crop")
        a = on_page(w, 0, 100, 100)
        QTest.mousePress(w.view.viewport(), Qt.LeftButton, Qt.NoModifier,
                         w.view.mapFromScene(QPointF(*a)))
    elif gesture == "paste_here":
        draw_rect(w)
        pick(w, rects(w)[0])
        key(w, Qt.Key_C, Qt.ControlModifier)
        key(w, Qt.Key_V, Qt.ControlModifier | Qt.AltModifier)   # Paste Here…, held
    elif gesture == "multiply":
        draw_rect(w)
        pick(w, rects(w)[0])
    new_pdf(w)
    QTest.mouseRelease(w.view.viewport(), Qt.LeftButton)
    settle()
    draw_rect(w, 300, 300)
    assert len(rects(w)) == 1
    assert w.view.scene().document is w.document
    assert not errors


# -- F-02: Ctrl+Z after Undo then New PDF ---------------------------------------------------
def test_undo_works_after_an_undo_then_new_pdf(w):
    draw_rect(w)
    key(w, Qt.Key_Z, Qt.ControlModifier)
    assert not rects(w) and not w.act_undo.isEnabled()
    new_pdf(w)
    draw_rect(w)
    assert len(rects(w)) == 1
    assert w.act_undo.isEnabled()         # stayed greyed for good before
    key(w, Qt.Key_Z, Qt.ControlModifier)
    assert not rects(w)
    assert w.act_redo.isEnabled()
    key(w, Qt.Key_Y, Qt.ControlModifier)  # Revu's redo
    assert len(rects(w)) == 1


def test_undo_follows_the_tab_in_hand(w):
    draw_rect(w)
    key(w, Qt.Key_Z, Qt.ControlModifier)
    key(w, Qt.Key_T, Qt.ControlModifier)  # New Tab: a history of its own
    draw_rect(w)
    assert w.act_undo.isEnabled()
    w.document_tabs.setCurrentIndex(0)
    settle()
    assert not w.act_undo.isEnabled() and w.act_redo.isEnabled()


# -- F-04: search marks belong to their document --------------------------------------------
def a_drawing(path):
    import fitz
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_text((100, 120), "beam TBC here", fontsize=14)
    document.save(str(path))
    document.close()
    return str(path)


def search_for(w, words):
    w.dock_search.show()
    box = w.search_panel.query
    box.setFocus()
    QTest.mouseClick(box, Qt.LeftButton)
    box.selectAll()
    QTest.keyClicks(box, words)
    QTest.keyClick(box, Qt.Key_Return)
    settle()


@pytest.mark.parametrize("leave", ["new_pdf", "new_tab", "close"])
def test_search_marks_go_with_their_document(w, tmp_path, leave):
    w.open_from_command_line(a_drawing(tmp_path / "drawing.pdf"))
    settle()
    search_for(w, "TBC")
    assert w.search_panel.hits and w.view._search_marks
    if leave == "new_pdf":
        new_pdf(w)
    elif leave == "new_tab":
        key(w, Qt.Key_T, Qt.ControlModifier)
    else:
        w.close_document_tab(w._active_tab)
        settle()
    assert not w.view._search_marks
    assert not w.search_panel.hits and w.search_panel.results.topLevelItemCount() == 0
    # the words stay: Find again searches the document now in view
    assert w.search_panel.query.text() == "TBC"


# -- F-09: the view's turn is the document's -------------------------------------------------
def test_view_rotation_belongs_to_the_document(w):
    key(w, Qt.Key_Period, Qt.ControlModifier | Qt.ShiftModifier)   # View ▸ Rotate Clockwise
    assert w.view.view_turn() == 90 and w.scene.reading_turn == 90
    key(w, Qt.Key_T, Qt.ControlModifier)                           # New Tab
    assert w.view.view_turn() == 0 and w.scene.reading_turn == 0
    key(w, Qt.Key_Period, Qt.ControlModifier | Qt.ShiftModifier)
    assert w.view.view_turn() == 90                                # not 180, upside down
    w.act_turn_view_reset.trigger()
    assert w.view.view_turn() == 0 and w.scene.reading_turn == 0
    w.document_tabs.setCurrentIndex(0)                             # back to the first
    settle()
    assert w.view.view_turn() == 90 and w.scene.reading_turn == 90
    new_pdf(w)                                                     # File ▸ New in its place
    assert w.view.view_turn() == 0 and w.scene.reading_turn == 0
    w.act_turn_view_reset.trigger()                                # does nothing now
    assert w.scene.reading_turn == 0


# -- F-14: a closed window is gone, and the next one is as quick as the first ---------------
def test_closed_windows_are_taken_down(w, errors):
    import time
    before = len(QApplication.topLevelWidgets())
    times = []
    for _ in range(4):
        w.activateWindow()
        settle()
        start = time.perf_counter()
        if not times:
            menu_click(w, "File", "New Window")      # by mouse
        else:                                        # and by its key
            QTest.keyClick(w, Qt.Key_N, Qt.ControlModifier | Qt.AltModifier | Qt.ShiftModifier)
            settle()
        times.append(time.perf_counter() - start)
        others = [x for x in MainWindow._windows if x is not w]
        assert len(others) == 1, (len(times), MainWindow._windows)
        other = others[0]
        other.confirm_discard = lambda: True
        draw_rect(other)
        other.toggle_split_view(True)
        settle()
        other.close()
        settle()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        gc.collect()
        settle()
        assert not shiboken6.isValid(other)
        assert MainWindow._windows == [w]
    assert len(QApplication.topLevelWidgets()) <= before + 2
    # every window was restyled with each new one, and closed ones were kept:
    # 2.3 s, 3.6, 5.3, 7.4 … 35 s by the twelfth (QA F-14)
    assert times[-1] < max(3 * times[0], 2.5), times
    # and the timers of the windows taken down fire into nothing
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.start(300)
    while deadline.isActive():
        QApplication.instance().processEvents()
    assert not errors


def test_a_new_window_does_not_restyle_the_application(w, monkeypatch):
    calls = []
    app = QApplication.instance()
    original = app.setStyleSheet
    monkeypatch.setattr(app, "setStyleSheet", lambda sheet: (calls.append(1), original(sheet)))
    other = w.open_new_window()
    settle()
    try:
        assert calls == []
        assert other.act_dark.isChecked() == w.act_dark.isChecked()
    finally:
        other.confirm_discard = lambda: True
        other.close()
    # a real change of theme still restyles
    w.act_dark.trigger()
    assert calls
    w.act_dark.trigger()


# -- F-21: undoing a page change puts the view back -----------------------------------------
def view_state(w):
    return (round(w.view.zoom(), 4), w.view.horizontalScrollBar().value(),
            w.view.verticalScrollBar().value(), w.current_index)


@pytest.mark.parametrize("change", ["paper_a0", "insert_page", "rotate_page", "delete_page"])
def test_undo_of_a_page_change_returns_the_view(w, change):
    w.add_page()                              # two pages
    w.undo_stack.clear()
    w.go_to_page(1 if change == "delete_page" else 0)
    w.view.set_zoom(1.0)
    w.view.verticalScrollBar().setValue(w.view.verticalScrollBar().value() + 40)
    settle()
    seen = view_state(w)
    if change == "paper_a0":
        menu = w.page_menu(0)
        paper = next(a.menu() for a in menu.actions() if a.text() == "Paper Size")
        next(a for a in paper.actions() if a.text() == "A0").trigger()
        assert w.view.zoom() < 0.5            # Revu fits the new paper
    elif change == "insert_page":
        w.add_page(0)
    elif change == "rotate_page":
        w.act_rotate_pages_cw.trigger()
    else:
        w.delete_page(1)
    settle()
    after = view_state(w)
    key(w, Qt.Key_Z, Qt.ControlModifier)
    assert view_state(w) == seen
    key(w, Qt.Key_Y, Qt.ControlModifier)
    assert view_state(w) == after


# -- F-28: Page Setup OK with nothing changed changes nothing --------------------------------
def answer_dialog(button):
    def press():
        dialog = QApplication.activeModalWidget()
        if not isinstance(dialog, QDialog):
            QTimer.singleShot(20, press)
            return
        box = dialog.findChild(QDialogButtonBox)
        target = box.button(button)
        QTest.mouseClick(target, Qt.LeftButton)
    QTimer.singleShot(0, press)


def test_page_setup_ok_with_no_change_is_no_step(w):
    w.undo_stack.clear()
    seen = view_state(w)
    answer_dialog(QDialogButtonBox.Ok)
    w.act_page_setup.trigger()                # Document ▸ Page Setup…
    settle()
    assert w.undo_stack.count() == 0
    assert view_state(w) == seen
    assert not w.document.modified or w.undo_stack.isClean()


def test_paper_size_as_it_is_is_no_step(w):
    w.undo_stack.clear()
    seen = view_state(w)
    menu = w.page_menu(0)
    paper = next(a.menu() for a in menu.actions() if a.text() == "Paper Size")
    next(a for a in paper.actions() if a.isChecked()).trigger()   # the size it already is
    settle()
    assert w.undo_stack.count() == 0
    assert view_state(w) == seen


# -- F-31: a copy lands clear of its original -----------------------------------------------
def box_of(item):
    from calcforge.items.base import covered_rect
    return covered_rect(item)


def test_duplicate_of_an_equation_is_readable(w):
    item = an_equation(w, "a:=2")
    w.toggle_calc_mode(False)
    pick(w, item)
    key(w, Qt.Key_J, Qt.ControlModifier)      # Edit ▸ Duplicate
    copies = [i for i in w.view.scene().ordered_markups() if isinstance(i, CalcItem)]
    assert len(copies) == 2
    original, copy = sorted(copies, key=lambda i: i.pos().y())
    assert not box_of(original).intersects(box_of(copy))
    assert copy.isSelected() and not original.isSelected()
    assert abs(copy.pos().x() - original.pos().x()) < 0.5        # straight below


def test_duplicate_of_a_markup_steps_down_and_right(w):
    draw_rect(w)
    (box,) = rects(w)
    pick(w, box)
    key(w, Qt.Key_J, Qt.ControlModifier)
    original, copy = sorted(rects(w), key=lambda i: i.pos().x())
    assert copy.pos() - original.pos() == QPointF(COPY_NUDGE, COPY_NUDGE)
    # and a second Duplicate steps on from the copy
    key(w, Qt.Key_J, Qt.ControlModifier)
    third = max(rects(w), key=lambda i: i.pos().x())
    assert third.pos() - copy.pos() == QPointF(COPY_NUDGE, COPY_NUDGE)


def test_paste_lands_under_the_pointer_or_clear_of_the_original(w):
    item = an_equation(w, "a:=2")
    w.toggle_calc_mode(False)
    pick(w, item)
    key(w, Qt.Key_C, Qt.ControlModifier)
    # the pointer on the page: under it (Revu)
    there = on_page(w, 0, 300, 400)
    hover(w.view, *there)
    key(w, Qt.Key_V, Qt.ControlModifier)
    pasted = [i for i in w.view.scene().ordered_markups() if isinstance(i, CalcItem)
              and i is not item]
    assert len(pasted) == 1
    landed = pasted[0].mapToScene(QPointF(0, 0))
    assert abs(landed.x() - there[0]) < 1 and abs(landed.y() - there[1]) < 1
    # the pointer gone from the page in view: beside the original, readable
    w.view._last_scene_pos = QPointF(-10_000, -10_000)
    key(w, Qt.Key_V, Qt.ControlModifier)
    third = [i for i in w.view.scene().ordered_markups() if isinstance(i, CalcItem)
             and i is not item and i is not pasted[0]]
    assert len(third) == 1
    assert not box_of(third[0]).intersects(box_of(item))


def test_multiply_offers_one_copy_beside_the_original(w):
    draw_rect(w, width=120)
    (box,) = rects(w)
    pick(w, box)
    seen = {}

    def look():
        dialog = QApplication.activeModalWidget()
        if dialog is None:
            QTimer.singleShot(20, look)
            return
        seen["across"] = dialog.dx.text()
        QTest.mouseClick(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok),
                         Qt.LeftButton)
    QTimer.singleShot(0, look)
    key(w, Qt.Key_M, Qt.ControlModifier)      # Edit ▸ Multiply…
    assert seen["across"].endswith(" mm") and float(seen["across"].split()[0]) > 40
    original, copy = sorted(rects(w), key=lambda i: i.pos().x())
    assert not box_of(original).intersects(box_of(copy))


# -- F-34: undo picks again what it gives back -----------------------------------------------
@pytest.mark.parametrize("command", ["delete", "cut", "hide", "duplicate", "nudge"])
def test_undo_reselects(w, command):
    draw_rect(w)
    (box,) = rects(w)
    pick(w, box)
    uid = box.uid
    if command == "delete":
        key(w, Qt.Key_Delete)
    elif command == "cut":
        key(w, Qt.Key_X, Qt.ControlModifier)
    elif command == "hide":
        w.act_hide.trigger()
        settle()
    elif command == "duplicate":
        key(w, Qt.Key_J, Qt.ControlModifier)
        assert len(rects(w)) == 2
    else:
        key(w, Qt.Key_Right)
    key(w, Qt.Key_Z, Qt.ControlModifier)
    (back,) = [i for i in rects(w) if i.isVisible()]
    assert back.uid == uid
    assert back.isSelected()                  # came back unselected before
    assert [i.uid for i in w.selected_items()] == [uid]
    key(w, Qt.Key_Y, Qt.ControlModifier)      # and redo picks what the step left picked
    if command == "duplicate":
        (copy,) = [i for i in rects(w) if i.uid != uid]
        assert copy.isSelected() and not next(i for i in rects(w) if i.uid == uid).isSelected()
    elif command == "nudge":
        assert rects(w)[0].isSelected()


# -- F-23: a long hint is cut short before the footer's buttons ------------------------------
def test_a_hovered_menu_items_tip_stays_in_the_hint(w):
    w.resize(900, 700)
    settle()
    bar = w.menuBar()
    calc = next(a for a in bar.actions() if a.text().replace("&", "") == "Calculation")
    QTest.mouseClick(bar, Qt.LeftButton, Qt.NoModifier, bar.actionGeometry(calc).center())
    settle()
    menu = calc.menu()
    assert menu.isVisible()
    longest = max((a for a in menu.actions() if a.statusTip() and a.isEnabled()
                   and not a.menu()), key=lambda a: len(a.statusTip()))
    QTest.mouseMove(menu, menu.actionGeometry(longest).center())
    settle()
    tip = w.status_tip
    assert tip.isVisible() and tip.text() == longest.statusTip()
    assert w.statusBar().currentMessage() == ""        # Qt's own message, drawn over all
    # after the grid and snap buttons, standing in for the page navigation
    # (as Qt's message does) and no further, cut short with "…"
    assert tip.geometry().left() > w.status_toggles.geometry().right()
    dimmer = w.statusBar().findChild(QWidget, "statusDimmer")
    assert tip.geometry().right() < dimmer.geometry().left()   # the controls on the right
    shown = tip.fontMetrics().elidedText(tip.text(), Qt.ElideRight, tip.contentsRect().width())
    assert shown.endswith("…")
    menu.hide()
    settle()
    QApplication.sendEvent(w, __import__("PySide6.QtGui", fromlist=["QStatusTipEvent"])
                           .QStatusTipEvent(""))           # the pointer has left it
    assert not tip.isVisible()
