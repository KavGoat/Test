"""The user's 2026-11-15 report, in a window: an equation inside a text box
is the size of the words round it and follows them; a space in it goes back
to the words (a lone word as words); Right at its end acts like Enter, Left
at its start leaves before it, and Left/Right in the words step back into
it; a workbook dragged over the Thumbnails shows where it goes, and goes
there; what a drop would do is said beside the pointer, and a drag leaving
the canvas leaves it quietly."""
from __future__ import annotations

import time

import pytest
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl, qInstallMessageHandler
from PySide6.QtGui import QDragLeaveEvent, QDragMoveEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QToolTip

from calcforge.items.fields import shown_text
from calcforge.items.inline_equations import PLACEHOLDER
from tests.test_inline_equations import a_box, typed_into_box
from tests.test_usability import press_key, type_text


def pump(seconds=0.0):
    end = time.monotonic() + seconds
    QApplication.processEvents()
    while time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.01)


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.interactive_prompts = False
    window.confirm_discard = lambda: True
    pump()
    return window


def test_an_equation_in_a_box_is_the_size_of_the_words_round_it_and_follows_them(w):
    """The user, 2026-11-15: "equation in text box should follow font size
    of text there"."""
    box = a_box(w, "Load ")
    box.style.font_size = 14.0
    box.apply_style()
    pump(0.1)
    item = typed_into_box(w, box, "5+2=")
    assert item.region.font_size == pytest.approx(14.0), "typed at the words' size"
    w.view.end_item_edit()
    pump(0.2)
    # the box's size changed (the Properties toolbar): the equation follows
    box.style.font_size = 20.0
    box.apply_style()
    pump(0.2)
    assert item.region.font_size == pytest.approx(20.0)
    tall = box.inline_rect(item.inline_uid).height()
    box.style.font_size = 10.0
    box.apply_style()
    pump(0.2)
    assert item.region.font_size == pytest.approx(10.0)
    assert box.inline_rect(item.inline_uid).height() < tall, "and is drawn smaller"


def test_a_space_in_an_equation_in_a_box_goes_back_to_the_words(w):
    """The user, 2026-11-15: "space inside equation inside text box should
    swap back to normal text" (their traceback: the box taken for a page).
    A lone word goes back as words, as SMath makes a name and a space text;
    an expression stays an equation, with the space typed after it."""
    box = a_box(w, "Load ")
    view = w.view
    view.begin_item_edit(box)
    pump(0.1)
    QTest.keyClicks(view.viewport(), "\\")
    pump(0.2)
    assert view.calc.editing()
    type_text(view, "q")
    type_text(view, " ")
    pump(0.3)
    assert not view.calc.editing() and view.editing_item() is box, "back in the words"
    assert box.inline_items() == [] and box.text() == "Load q "
    assert box._editor.textCursor().position() == len("Load q ")
    QTest.keyClicks(view.viewport(), "\\")
    pump(0.2)
    assert view.calc.editing()
    type_text(view, "5+2=")
    type_text(view, " ")
    pump(0.3)
    assert not view.calc.editing() and view.editing_item() is box
    assert len(box.inline_items()) == 1, "an expression stays an equation"
    assert box.text() == "Load q " + PLACEHOLDER + " "
    assert box._editor.textCursor().position() == len("Load q ") + 2, "after the space"
    QTest.keyClicks(view.viewport(), "kN")
    view.end_item_edit()
    pump(0.3)
    assert shown_text(box) == "Load q 5+2 = 7 kN"


def test_the_arrows_step_out_of_an_equation_in_a_box_and_back_into_it(w):
    """The user, 2026-11-15: "left right arrow after typing enter should let
    me go back into edit mode", "right arrow after typing 5+2= should act
    like pressing enter"."""
    box = a_box(w, "Load ")
    item = typed_into_box(w, box, "5+2=")             # Enter: the caret after it
    view = w.view
    assert box._editor.textCursor().position() == len("Load ") + 1
    QTest.keyClick(view.viewport(), Qt.Key_Left)
    pump(0.3)
    assert view.calc.editing() and view.calc.item is item, "Left steps back into it"
    editor = item.region.editor
    assert editor.pos == len(editor.expression_items()), "at its end"
    press_key(view, Qt.Key_Right)
    pump(0.3)
    assert not view.calc.editing() and view.editing_item() is box, \
        "Right at the end acts like Enter"
    assert box._editor.textCursor().position() == len("Load ") + 1
    QTest.keyClick(view.viewport(), Qt.Key_Left)
    pump(0.3)
    assert view.calc.item is item
    press_key(view, Qt.Key_Home)
    press_key(view, Qt.Key_Left)
    pump(0.3)
    assert not view.calc.editing() and view.editing_item() is box, \
        "Left at the start leaves it"
    assert box._editor.textCursor().position() == len("Load "), "before the equation"
    QTest.keyClick(view.viewport(), Qt.Key_Right)
    pump(0.3)
    assert view.calc.item is item and item.region.editor.pos == 0, \
        "Right from the words before it steps in at its start"
    type_text(view, "1+")
    press_key(view, Qt.Key_Return)
    pump(0.3)
    assert shown_text(box) == "Load 1+5+2 = 8"
    assert view.editing_item() is box
    view.end_item_edit()
    pump(0.1)


def a_workbook(path) -> str:
    openpyxl = pytest.importorskip("openpyxl")
    book = openpyxl.Workbook()
    book.active["A1"] = 1
    book.save(str(path))
    return str(path)


def test_a_workbook_dragged_over_the_thumbnails_shows_where_it_goes_and_goes_there(w, tmp_path):
    """The user, 2026-11-15: "dragging an excel doesn't show where it will
    insert" — the Thumbnails welcomed PDFs and pictures only."""
    path = a_workbook(tmp_path / "loads.xlsx")
    w.quick_add_page(0)
    pump(0.2)
    assert len(w.document.pages) == 2
    panel = w.pages_panel
    data = QMimeData()
    data.setUrls([QUrl.fromLocalFile(path)])
    box = panel.list.visualItemRect(panel.list.item(1))
    at = QPoint(box.center().x(), box.top() + 2)
    event = QDragMoveEvent(at, Qt.CopyAction, data, Qt.LeftButton, Qt.NoModifier)
    panel._drag_move(event)
    assert event.isAccepted()
    assert panel.list.external_drop_row == 1, "the line between the pages"
    assert QToolTip.text() == "Insert as page 2", "said beside the pointer"
    assert w.status_hint.text() == "Drop to put the file in as page 2"
    panel._drag_leave(QDragLeaveEvent())
    assert panel.list.external_drop_row is None
    pump(0.5)
    assert not QToolTip.isVisible()
    before = [page.uid for page in w.document.pages]
    assert w.insert_files_at([path], 1) == 1
    pump(0.3)
    pages = w.document.pages
    assert len(pages) == 3 and pages[1].sheet is not None, "its sheet, where the line was"
    assert [pages[0].uid, pages[2].uid] == before


def test_a_drag_says_what_a_drop_does_beside_the_pointer_and_leaves_the_canvas_quietly(w, tmp_path):
    """The user, 2026-11-15: "drag a file from explorer says copy instead
    of open, depends on where I hover" — the OS cursor can only say Copy,
    so the words go beside the pointer; and no "drag leave received before
    drag enter" from Qt."""
    messages = []
    old = qInstallMessageHandler(lambda _mode, _context, message: messages.append(message))
    try:
        view = w.view
        frame = w.document.pages[0].frame
        data = QMimeData()
        data.setUrls([QUrl.fromLocalFile(str(tmp_path / "sheet.pdf"))])
        point = view.mapFromScene(frame.mapToScene(frame.page_rect().center()))
        event = QDragMoveEvent(point, Qt.CopyAction, data, Qt.LeftButton, Qt.NoModifier)
        view.dragEnterEvent(event)
        view.dragMoveEvent(event)
        pump()
        assert view._drop_after is frame
        assert QToolTip.text() == "Insert after page 1", "beside the pointer"
        assert w.status_hint.text() == "Drop to put the PDF's pages in after page 1"
        assert w.pages_panel.list.external_drop_row == 1, "and the Thumbnails show it too"
        view.dragLeaveEvent(QDragLeaveEvent())
        pump()
        assert view._drop_after is None and w.pages_panel.list.external_drop_row is None
        assert w.status_hint.text() == ""
        # over the window itself (the tab bar, a toolbar): it would open
        event = QDragMoveEvent(QPoint(5, 5), Qt.CopyAction, data, Qt.LeftButton, Qt.NoModifier)
        w.dragEnterEvent(event)
        w.dragMoveEvent(event)
        assert QToolTip.text() == "Open in a tab of its own"
        w.dragLeaveEvent(QDragLeaveEvent())
        pump(0.5)
        assert not QToolTip.isVisible()
    finally:
        qInstallMessageHandler(old)
    assert not [m for m in messages if "drag leave" in m], messages
