"""The user's 2026-10-30 round, in a window: every markup built as a
document opens (the lazy loading of 29 Oct reverted); the active cell's box
inside the grid, never over the headings; Delete with pages picked in
Thumbnails and nothing on the canvas; a workbook dragged over the pages
marks where it will go; the caret shows in a text box being typed in; a key
typed in a box is looked up in the shortcut table, not scanned for."""
from __future__ import annotations

import time

import numpy as np
import pytest
from PySide6.QtCore import QMimeData, QPointF, QRectF, Qt, QUrl
from PySide6.QtGui import QDragMoveEvent, QImage, QPainter
from PySide6.QtWidgets import QApplication

pymupdf = pytest.importorskip("pymupdf")


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


PAGES, EACH = 6, 8


def marked_set(path) -> str:
    doc = pymupdf.open()
    for p in range(PAGES):
        page = doc.new_page(width=842, height=595)
        for k in range(EACH):
            x, y = 40 + (k % 4) * 180, 40 + (k // 4) * 160
            if k % 2:
                note = page.add_rect_annot(pymupdf.Rect(x, y, x + 120, y + 80))
            else:
                note = page.add_freetext_annot(pymupdf.Rect(x, y, x + 150, y + 36),
                                               f"Note {p}-{k}", fontsize=10)
            note.update()
    doc.save(str(path))
    return str(path)


def test_every_markup_is_built_as_a_document_opens(w, tmp_path):
    """No page holds its markups back any more (the user, 2026-10-30: "the
    lazy load is trash")."""
    w._open_chosen(marked_set(tmp_path / "set.pdf"))
    frames = w.scene.frames
    assert len(frames) == PAGES
    assert [len(frame.markups()) for frame in frames] == [EACH] * PAGES
    assert not hasattr(w, "_loading_behind") or not w._loading_behind
    assert not hasattr(frames[0], "held")
    assert w.status_hint.text() == "" or "Loading markups" not in w.status_hint.text()


def test_the_active_cells_box_stays_inside_the_grid(w):
    """A1 picked, the green box's outer pixel used to lie over the row and
    column headings (the user, 2026-10-30)."""
    from calcforge.items.table import EXCEL_GREEN, HEADING_H, ROWNUM_W
    from tests.test_tables import make_table
    table = make_table(w)
    w.view.tables.open(table, (0, 0))
    pump(0.2)
    assert table.opened and table.active == (0, 0)
    scale = 4.0
    xs, ys = table.edges()
    width, height = xs[-1] + ROWNUM_W + 20, ys[-1] + HEADING_H + 20
    image = QImage(int(width * scale), int(height * scale), QImage.Format_RGB32)
    image.fill(Qt.white)
    from PySide6.QtWidgets import QStyleOptionGraphicsItem
    option = QStyleOptionGraphicsItem()
    option.exposedRect = table.boundingRect()
    painter = QPainter(image)
    painter.scale(scale, scale)
    painter.translate(ROWNUM_W + 2, HEADING_H + 2)
    table.paint(painter, option, None)
    painter.end()
    raw = np.frombuffer(bytes(image.constBits()), np.uint8)
    pixels = raw.reshape(image.height(), image.bytesPerLine())[:, :image.width() * 4] \
        .reshape(image.height(), image.width(), 4)[:, :, :3]
    green = np.array([EXCEL_GREEN.blue(), EXCEL_GREEN.green(), EXCEL_GREEN.red()])
    is_green = (np.abs(pixels.astype(int) - green).sum(axis=2) < 40)
    grid_top = int((HEADING_H + 2) * scale)
    grid_left = int((ROWNUM_W + 2) * scale)
    assert is_green[grid_top:, grid_left:].any(), "the box is drawn inside the grid"
    # (the picked column's letter and row's number are green, as Excel's: the
    # band of the headings along the grid's edge is what the box must not reach)
    band = int(2 * scale)
    assert not is_green[grid_top - band:grid_top, :].any(), "nothing green over the column headings"
    assert not is_green[:, grid_left - band:grid_left].any(), "nothing green over the row numbers"


def test_delete_takes_the_pages_picked_in_thumbnails_when_nothing_on_the_canvas_is(w):
    """Delete with pages (or a workbook) picked in Thumbnails and the
    keyboard focus on the canvas (the user, 2026-10-30: "sometimes works
    and sometimes does not")."""
    for _ in range(3):
        w.quick_add_page(len(w.document.pages) - 1)
    pump(0.1)
    assert len(w.document.pages) == 4
    strip = w.pages_panel.list
    strip.clearSelection()
    strip.item(1).setSelected(True)
    strip.item(2).setSelected(True)
    pump(0.1)
    assert w.pages_panel.picked_rows() == [1, 2]
    w.scene.clearSelection()
    w.view.setFocus()
    w.delete_selection()                      # the Delete key's action, focus on the canvas
    pump(0.3)
    assert len(w.document.pages) == 2


def a_workbook(path) -> str:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"] = 1
    wb.save(str(path))
    return str(path)


def test_a_workbook_dragged_over_the_pages_marks_the_page_it_goes_in_after(w, tmp_path):
    path = a_workbook(tmp_path / "loads.xlsx")
    for _ in range(2):
        w.quick_add_page(len(w.document.pages) - 1)
    pump(0.1)
    w.go_to_page(1)
    pump(0.2)
    view = w.view
    frame = w.scene.frames[1]
    where = view.mapFromScene(frame.mapToScene(frame.boundingRect().center()))
    data = QMimeData()
    data.setUrls([QUrl.fromLocalFile(path)])
    event = QDragMoveEvent(where, Qt.CopyAction, data, Qt.LeftButton, Qt.NoModifier)
    view.dragMoveEvent(event)
    assert event.isAccepted()
    assert view._drop_after is frame, "the line goes under the page under the pointer"
    assert "after page 2" in w.status_hint.text()
    # in the gap below it: still after it
    paper = frame.mapToScene(frame.page_rect()).boundingRect()
    below = view.mapFromScene(QPointF(paper.center().x(), paper.bottom() + 2))
    view.dragMoveEvent(QDragMoveEvent(below, Qt.CopyAction, data, Qt.LeftButton, Qt.NoModifier))
    assert view._drop_after is frame
    from PySide6.QtGui import QDragLeaveEvent
    view.dragLeaveEvent(QDragLeaveEvent())
    assert view._drop_after is None and w.status_hint.text() == ""
    # a PDF opens in a tab of its own: nothing to mark
    pdf = QMimeData()
    pdf.setUrls([QUrl.fromLocalFile(str(tmp_path / "sheet.pdf"))])
    view.dragMoveEvent(QDragMoveEvent(where, Qt.CopyAction, pdf, Qt.LeftButton, Qt.NoModifier))
    assert view._drop_after is None


def test_the_caret_shows_in_a_white_text_box_being_typed_in(w):
    """Qt's own caret inverts what is under it, and the words are drawn
    into a clear picture first: it came out white on a white box (the user,
    2026-10-30: "can't see cursor")."""
    from calcforge.items.text import TextItem
    frame = w.document.pages[0].frame
    box = TextItem("Hello", QRectF(0, 0, 200, 40))
    frame.add_markup(box, QPointF(60, 60))
    box.apply_style()
    pump(0.2)
    view = w.view
    view.set_zoom(2.0)
    view.centerOn(box.mapToScene(box.boundingRect().center()))
    view.begin_item_edit(box)
    pump(0.3)
    editor = box._editor
    assert editor is not None and editor.hasFocus()
    cursor = editor.textCursor()
    block = cursor.block()
    line = block.layout().lineForTextPosition(cursor.positionInBlock())
    x = block.layout().position().x() + line.cursorToX(cursor.positionInBlock())[0]
    y = block.layout().position().y() + line.y() + line.height() / 2
    point = view.mapFromScene(editor.mapToScene(QPointF(x, y)))
    image = view.viewport().grab().toImage().convertToFormat(QImage.Format_RGB32)
    ratio = view.viewport().devicePixelRatioF()
    px, py = int(point.x() * ratio), int(point.y() * ratio)
    raw = np.frombuffer(bytes(image.constBits()), np.uint8)
    pixels = raw.reshape(image.height(), image.bytesPerLine())[:, :image.width() * 4] \
        .reshape(image.height(), image.width(), 4)[:, :, :3].mean(axis=2)
    around = pixels[max(py - 2, 0):py + 3, max(px - 3, 0):px + 4]
    assert around.min() < 120, f"no dark caret pixel near the caret: {around.round()}"
    view.end_item_edit()


def test_a_key_typed_in_a_box_is_looked_up_not_scanned_for(w):
    """Every key typed in a text box, a cell or an equation asks the window's
    shortcut table whose it is (the ShortcutOverride): walking the eight
    hundred bindings and spelling each one's key took a millisecond a
    keystroke. The table is a lookup now, built once per change, and it
    answers as the walk did."""
    from PySide6.QtGui import QKeySequence
    from calcforge.ui.shortcuts import EQUATION, TABLE
    shortcuts = w.shortcuts

    def by_walking(sequence, scopes=None):
        wanted = sequence.toString(QKeySequence.PortableText).lower()
        ordered = sorted(shortcuts.bindings(), key=lambda b: b.scope in (EQUATION, TABLE))
        for binding in ordered:
            if scopes is not None and binding.scope not in scopes:
                continue
            current = shortcuts.sequence(binding.action_id)
            if current and QKeySequence(current).toString(
                    QKeySequence.PortableText).lower() == wanted:
                return binding
        return None

    bound = [QKeySequence(shortcuts.sequence(b.action_id)) for b in shortcuts.bindings()
             if shortcuts.sequence(b.action_id)]
    assert len(bound) > 100                     # a couple of hundred have a key
    for sequence in bound:
        assert shortcuts.binding_for(sequence) is by_walking(sequence)
        assert shortcuts.binding_for(sequence, scopes=(EQUATION,)) \
            is by_walking(sequence, scopes=(EQUATION,))
    assert shortcuts.binding_for(QKeySequence("Ctrl+Alt+Shift+F35")) is None
    # built once: a second key is answered from the same table
    table = shortcuts._lookup()
    shortcuts.binding_for(QKeySequence("M"))
    assert shortcuts._lookup() is table
    # and built again when a key is changed
    spare = QKeySequence("Ctrl+Alt+Shift+F34")
    assert shortcuts.binding_for(spare) is None
    victim = next(b for b in shortcuts.bindings() if shortcuts.sequence(b.action_id))
    was = shortcuts.sequence(victim.action_id)
    try:
        shortcuts.set_sequence(victim.action_id, spare.toString(QKeySequence.PortableText))
        assert shortcuts.binding_for(spare) is victim
        assert shortcuts.binding_for(QKeySequence(was)) is not victim
    finally:
        shortcuts.set_sequence(victim.action_id, was)
    assert shortcuts.binding_for(QKeySequence(was)) is victim
    assert shortcuts.binding_for(spare) is None
