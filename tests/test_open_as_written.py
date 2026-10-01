"""A PDF opens exactly as it was written (the user, 2026-10-01): its markups
are drawn by the file itself and nothing is converted. A markup becomes
CalcForge's only when it is actually edited — moved, resized, retyped,
restyled — and undoing that edit gives the file's own drawing back.
Picking one out (a click, the properties showing) changes nothing."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from tests.test_format import _a_drawing_marked_up_elsewhere
from tests.test_usability import click, double_click, drag


@pytest.fixture
def sheet(window, tmp_path):
    path = str(tmp_path / "marked.pdf")
    _a_drawing_marked_up_elsewhere(path)
    window.show()
    window.open_path(path)
    window.rebuild_scenes()
    window.select_tool("select")
    if hasattr(window, "toggle_calc_mode"):
        window.toggle_calc_mode(False)
    QApplication.instance().processEvents()
    return window


def marks(window):
    page = window.document.pages[0]
    return [i for i in page.frame.ordered_markups() if not getattr(i, "from_drawing", False)]


def by_kind(window, kind):
    for item in marks(window):
        if kind == "cloud" and getattr(item, "kind", "") == "cloud":
            return item
        if kind == "typed" and item.TYPE == "text":
            return item
        if kind == "callout" and item.TYPE == "callout":
            return item
    raise AssertionError(kind)


def all_as_written(window):
    page = window.document.pages[0]
    return all(i.still_theirs for i in marks(window)) and page.frame.left_to_us() == ()


def centre(item):
    return item.mapToScene(item.local_rect().center())


def test_opening_converts_nothing(sheet):
    assert len(marks(sheet)) == 3
    assert all_as_written(sheet)
    assert sheet.undo_stack.count() == 0
    assert not sheet.document.modified


def test_picking_one_out_changes_nothing(sheet):
    cloud = by_kind(sheet, "cloud")
    edge = cloud.mapToScene(cloud.local_rect().topLeft() + QPointF(0, 30))
    click(sheet.view, edge.x(), edge.y())
    assert cloud.isSelected()
    sheet.refresh_selection()                       # properties and style bar fill in
    QApplication.instance().processEvents()
    assert all_as_written(sheet), "selected, still drawn by its own file"
    assert sheet.undo_stack.count() == 0
    click(sheet.view, 560, 800)                     # and let go of it
    assert all_as_written(sheet)


def test_a_click_with_a_tremble_is_not_a_move(sheet):
    cloud = by_kind(sheet, "cloud")
    was = QPointF(cloud.pos())
    edge = cloud.mapToScene(cloud.local_rect().topLeft() + QPointF(0, 30))
    drag(sheet.view, edge.x(), edge.y(), edge.x() + 1, edge.y() + 1)
    assert cloud.pos() == was and all_as_written(sheet)


def test_moving_one_makes_it_ours_and_undo_gives_the_original_back(sheet):
    cloud = by_kind(sheet, "cloud")
    was = QPointF(cloud.pos())
    edge = cloud.mapToScene(cloud.local_rect().topLeft() + QPointF(0, 30))
    drag(sheet.view, edge.x(), edge.y(), edge.x() + 80, edge.y() + 40)
    assert not cloud.still_theirs
    assert sheet.document.pages[0].frame.left_to_us() == (cloud.from_annotation,)
    sheet.undo_stack.undo()
    QApplication.instance().processEvents()
    cloud = by_kind(sheet, "cloud")
    assert cloud.pos() == was
    assert all_as_written(sheet), "back to however it was written"
    sheet.undo_stack.redo()
    assert not by_kind(sheet, "cloud").still_theirs


def test_restyling_one_makes_it_ours_and_undo_gives_it_back(sheet):
    cloud = by_kind(sheet, "cloud")
    sheet.view.scene().clearSelection()
    cloud.setSelected(True)
    sheet.refresh_selection()
    sheet.view.begin_snapshot()
    style = cloud.style.copy() if hasattr(cloud.style, "copy") else cloud.style
    style.stroke = "#0000ff"
    cloud.set_style(style) if hasattr(cloud, "set_style") else setattr(cloud, "style", style)
    cloud.touch()
    sheet.view.commit_snapshot("Style")
    assert not cloud.still_theirs
    sheet.undo_stack.undo()
    assert all_as_written(sheet)


def test_opening_a_text_box_and_leaving_it_unchanged_leaves_it_as_written(sheet):
    typed = by_kind(sheet, "typed")
    count = sheet.undo_stack.count()
    double_click(sheet.view, *_xy(centre(typed)))
    assert sheet.view.editing_item() is typed
    assert not typed.still_theirs, "being typed in, it is drawn here"
    sheet.view.setFocus()
    QTest.keyClick(sheet.view.viewport(), Qt.Key_Escape)
    typed = by_kind(sheet, "typed")
    assert sheet.view.editing_item() is None
    assert all_as_written(sheet), "nothing was changed, so nothing changed hands"
    assert sheet.undo_stack.count() == count


def test_retyping_a_text_box_makes_it_ours_and_undo_gives_it_back(sheet):
    typed = by_kind(sheet, "typed")
    double_click(sheet.view, *_xy(centre(typed)))
    editor = typed._editor
    cursor = editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    editor.setTextCursor(cursor)
    editor.textCursor().insertText(" (rev B)")
    sheet.view.end_item_edit()
    typed = by_kind(sheet, "typed")
    assert "rev B" in typed.text() and not typed.still_theirs
    sheet.undo_stack.undo()
    typed = by_kind(sheet, "typed")
    assert "rev B" not in typed.text()
    assert all_as_written(sheet)


def test_saving_untouched_keeps_their_annotations(sheet, tmp_path):
    import pymupdf
    cloud = by_kind(sheet, "cloud")
    cloud.setSelected(True)
    sheet.refresh_selection()
    path = str(tmp_path / "again.pdf")
    from tests.test_calc_saving import save_to
    save_to(sheet, path)
    with pymupdf.open(path) as saved:
        page = saved[0]
        annots = list(page.annots())
        kinds = sorted(a.type[1] for a in annots)
        info = {a.type[1]: a.info for a in annots}
    assert kinds == ["FreeText", "FreeText", "Square"]
    assert info["Square"]["title"] == "Sam" and info["Square"]["content"] == "check this dim"


def _xy(point):
    return point.x(), point.y()


@pytest.mark.skipif(not __import__("os").path.exists(
    __import__("tests.test_format", fromlist=["REFERENCE"]).REFERENCE),
    reason="the reference drawing is not here")
def test_a_real_bluebeam_drawing_opens_as_written_and_stays_so_when_picked(window):
    """Every markup on a drawing made in Bluebeam: opened, each clicked and
    shown in Properties — all still drawn by the file, nothing to save."""
    from tests.test_format import REFERENCE
    window.show()
    window.open_path(REFERENCE)
    window.rebuild_scenes()
    window.select_tool("select")
    QApplication.instance().processEvents()
    assert not window.document.modified
    found = 0
    for page in window.document.pages:
        theirs = [i for i in page.frame.markups() if i.from_annotation]
        assert all(i.still_theirs for i in theirs), page.uid
        for item in theirs:
            window.view.scene().clearSelection()
            item.setSelected(True)
            window.refresh_selection()
            found += 1
        QApplication.instance().processEvents()
        assert all(i.still_theirs for i in theirs) and page.frame.left_to_us() == ()
    assert found and window.undo_stack.count() == 0 and not window.document.modified


def test_the_screen_is_the_same_after_picking_one_out_and_letting_go(sheet):
    def shot():
        QApplication.instance().processEvents()
        sheet.view.viewport().repaint()
        return sheet.view.viewport().grab().toImage()

    before = shot()
    cloud = by_kind(sheet, "cloud")
    edge = cloud.mapToScene(cloud.local_rect().topLeft() + QPointF(0, 30))
    click(sheet.view, edge.x(), edge.y())
    assert shot() != before, "selected: its handles show"
    sheet.view.scene().clearSelection()
    assert shot() == before, "let go: the very same drawing, pixel for pixel"
