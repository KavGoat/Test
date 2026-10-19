"""A file open in two tabs is two views of one document.

The user, 2026-10-19: "Tabs: if dragging a tab that already exists in the
window it should not consolidate into one." Asked whether the two tabs are
two views of one document or two copies: "Two views of one, this should be
the case if each tab is on its own window too tho." So the tabs showing a
file — in one window, or each in a window of its own — share one document:
an edit in one is in the other at once, there is one save, one undo history
and one modified state, while each tab keeps its own zoom, scroll, page and
tool. Only the last view of a modified document closing asks about saving.
"""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog

from tests.test_split_tabs import _pdf, _settle
from tests.test_tab_drag_windows import (_gone, _mark, _names, _onto_tabs, _rects,
                                         _released_none_of, _shows_its_documents,
                                         make)  # noqa: F401  (the fixture)
from tests.test_usability import drag


def _dirty(window, index):
    return window.document_tabs.tabText(index).endswith("•")


@pytest.fixture
def two_tabs(make, tmp_path):
    """Window *first* with a.pdf in two tabs: the second came from window
    *second*, which opened the file while *first* had it open (so it showed
    the same document) and then had its tab dragged across onto *first*."""
    a = _pdf(tmp_path / "a.pdf", pages=3)
    first = make(0, a)
    second = make(1040, a)
    assert second.document is first.document, "Open shows the live document"
    _onto_tabs(second, first)
    assert _gone(second)
    assert _names(first) == ["a.pdf", "a.pdf"]
    return first, a


def test_moving_a_tab_onto_a_window_with_its_document_adds_a_second_view(make, tmp_path):
    a = _pdf(tmp_path / "a.pdf", pages=3)
    first = make(0, a)
    second = make(1040, a)
    document, scene, stack = first.document, first.scene, first.undo_stack
    assert second.document is document and second.scene is scene
    assert second.undo_stack is stack
    second.view.set_zoom(2.0)
    second.go_to_page(2)
    second.view.horizontalScrollBar().setValue(40)
    first.view.set_zoom(0.5)
    first.go_to_page(0)
    second.move_document_to(0, first)
    _settle()
    assert _gone(second), "the window left with no tab closes"
    assert _names(first) == ["a.pdf", "a.pdf"]
    assert [first._state_for_tab(i)["document"] for i in range(2)] == [document, document]
    assert [first._state_for_tab(i)["scene"] for i in range(2)] == [scene, scene]
    assert [first._state_for_tab(i)["undo_stack"] for i in range(2)] == [stack, stack]
    # each tab where it was left: its own zoom, page and scroll
    assert first._active_tab == 1
    assert first.view.zoom() == pytest.approx(2.0)
    assert first.current_index == 2
    first.switch_to_document(0)
    assert first.view.zoom() == pytest.approx(0.5)
    assert first.current_index == 0
    first.switch_to_document(1)
    assert first.view.zoom() == pytest.approx(2.0)
    assert first.current_index == 2
    _shows_its_documents(first)
    _released_none_of(make.released, first)


def test_an_edit_in_one_tab_is_in_the_other_with_one_history_and_one_save(two_tabs):
    window, a = two_tabs
    window.switch_to_document(0)
    _mark(window)
    assert len(_rects(window)) == 1
    assert _dirty(window, 0) and _dirty(window, 1), "both tabs show the change unsaved"
    window.switch_to_document(1)
    assert len(_rects(window)) == 1, "the edit is in the other tab at once"
    assert window.act_undo.isEnabled()
    QTest.keyClick(window.view.viewport(), Qt.Key_Z, Qt.ControlModifier)
    _settle()
    assert not _rects(window), "undone from the other tab"
    window.switch_to_document(0)
    assert not _rects(window)
    assert not _dirty(window, 0) and not _dirty(window, 1)
    QTest.keyClick(window.view.viewport(), Qt.Key_Y, Qt.ControlModifier)
    _settle()
    assert len(_rects(window)) == 1
    assert _dirty(window, 0) and _dirty(window, 1)
    # one save, from either tab, saves the one document: both are clean
    window.switch_to_document(1)
    assert window.save_document()
    assert not _dirty(window, 0) and not _dirty(window, 1)
    assert window.undo_stack.isClean()


def test_file_open_in_another_window_shows_the_live_document(make, tmp_path):
    a = _pdf(tmp_path / "a.pdf")
    first = make(0, a)
    _mark(first)                                # not saved
    second = make(1040, _pdf(tmp_path / "c.pdf"))
    second.open_in_new_tab()
    second.open_from_command_line(str(a))
    _settle()
    assert _names(second) == ["c.pdf", "a.pdf"]
    assert second.document is first.document and second.scene is first.scene
    assert second.undo_stack is first.undo_stack
    assert len(_rects(second)) == 1, "the unsaved edit made in the first window"
    assert _dirty(second, 1) and first.windowTitle().startswith("a.pdf •")
    # one history: undone in the second window, it is undone in the first,
    # and both windows' Undo and Redo follow
    QTest.keyClick(second.view.viewport(), Qt.Key_Z, Qt.ControlModifier)
    _settle()
    assert not _rects(first)
    assert not first.act_undo.isEnabled() and first.act_redo.isEnabled()
    assert not second.act_undo.isEnabled() and second.act_redo.isEnabled()
    assert not _dirty(first, 0) and not _dirty(second, 1)
    QTest.keyClick(first.view.viewport(), Qt.Key_Y, Qt.ControlModifier)
    _settle()
    assert len(_rects(second)) == 1 and second.act_undo.isEnabled()
    # a save in one is the save of both
    assert second.save_document()
    assert not first.windowTitle().startswith("a.pdf •") and not _dirty(second, 1)
    _released_none_of(make.released, first, second)


def test_save_as_in_one_window_renames_the_tabs_of_every_window(make, tmp_path, monkeypatch):
    a = _pdf(tmp_path / "a.pdf")
    first = make(0, a)
    second = make(1040, _pdf(tmp_path / "c.pdf"))
    second.open_in_new_tab()
    second.open_from_command_line(str(a))
    renamed = tmp_path / "renamed.pdf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *args, **kw: (str(renamed), "")))
    assert first.save_document_as()
    assert renamed.exists()
    assert _names(first) == ["renamed.pdf"]
    assert _names(second) == ["c.pdf", "renamed.pdf"]
    second.switch_to_document(0)
    second.update_title()
    assert _names(second) == ["c.pdf", "renamed.pdf"]


def test_closing_one_of_two_tabs_does_not_ask_and_the_last_one_does(two_tabs):
    window, a = two_tabs
    asked = []
    window.confirm_discard = lambda: asked.append(window.document) or True
    _mark(window)
    document = window.document
    window.close_document_tab(0)
    _settle()
    assert not asked, "another tab still shows it: nothing is lost"
    assert _names(window) == ["a.pdf"] and window.document is document
    assert len(_rects(window)) == 1 and not window.undo_stack.isClean()
    window.close_document_tab(0)
    _settle()
    assert asked == [document], "the last view of the document asks"
    assert window.workspace_empty


def test_closing_a_window_asks_only_for_the_last_view(make, tmp_path):
    a = _pdf(tmp_path / "a.pdf")
    first = make(0, a)
    second = make(1040, a)
    asked = []
    for window in (first, second):
        window.confirm_discard = lambda w=window: asked.append(w) or True
    _mark(second)
    second.close()
    _settle()
    assert not asked and _gone(second)
    assert len(_rects(first)) == 1 and not first.undo_stack.isClean()
    _shows_its_documents(first)
    _released_none_of(make.released, first)
    first.close()
    _settle()
    assert asked == [first]


def test_split_view_in_one_of_two_tabs_of_a_document(two_tabs):
    window, a = two_tabs
    window.act_split_view.trigger()
    _settle()
    assert window.is_split
    left, right = window._panes
    assert right.view.scene() is left.view.scene() is window.scene
    window.select_tool("rect")
    drag(right.view, 120, 120, 240, 200)
    window.select_tool("select")
    _settle()
    assert len(_rects(window)) == 1
    assert left.view.scene() is window.scene
    window.act_split_view.trigger()
    _settle()
    assert not window.is_split
    assert _names(window) == ["a.pdf", "a.pdf"]
    for index in range(2):
        window.switch_to_document(index)
        assert len(_rects(window)) == 1
    window.undo_stack.undo()
    assert not _rects(window)
