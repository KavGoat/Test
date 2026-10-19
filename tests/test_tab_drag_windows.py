"""A document's tab dragged from one window into another.

The user, 2026-10-19: "Had an issue where having two windows with the same
PDF then dragging it over to one window, but only [the] tab stayed." Then,
the same day: "if dragging a tab that already exists in the window it should
not consolidate into one" — asked whether the two tabs are two views of one
document or two copies: "Two views of one, this should be the case if each
tab is on its own window too tho." So a tab is never merged into another: a
tab of a document the other window already shows arrives as a second tab, a
second view of the same document (one canvas, one history), and a window
left with no tab closes. Two copies of one file read from the disk apart
(a recovered version beside the saved one) are not merged either: both are
kept, the one brought in marked "(2)". File ▸ Open of a file another window
has open shows that window's live document. A tab of another file moves with
its canvas, place, history and selection. Every drag here is a real press,
move and release on the tab bar.
"""
import pytest
import shiboken6
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog

from calcforge.items.shapes import RectItem
from calcforge.ui import release
from calcforge.ui.mainwindow import MainWindow
from tests.test_split_tabs import _drag_tab, _pdf, _settle
from tests.test_usability import drag


def _names(window):
    return [window.document_tabs.tabText(i).rstrip(" •")
            for i in range(window.document_tabs.count())]


def _gone(window):
    return (not shiboken6.isValid(window) or window not in MainWindow._windows
            or not window.isVisible())


def _rects(window):
    return [item for frame in window.view.scene().frames for item in frame.markups()
            if isinstance(item, RectItem)]


def _mark(window, x=120):
    """A rectangle drawn on the page with the mouse."""
    window.select_tool("rect")
    drag(window.view, x, 120, x + 120, 200)
    window.select_tool("select")
    _settle()


def _shows_its_documents(window):
    """Every tab of *window* has a live canvas with its pages on it."""
    here = window._active_tab
    for index in range(len(window._open_documents)):
        window.switch_to_document(index)
        scene = window.view.scene()
        assert scene is not None and shiboken6.isValid(scene), f"tab {index} is blank"
        assert scene is window.scene and scene.document is window.document
        assert len(scene.frames) == len(window.document.pages) >= 1
        assert all(shiboken6.isValid(frame) and frame.scene() is scene
                   for frame in scene.frames)
        assert shiboken6.isValid(window.undo_stack)
    window.switch_to_document(here)


@pytest.fixture
def make(window, monkeypatch):
    """Windows of one's own (the fixture's stays hidden and is only the
    factory), and a record of every canvas let go of."""
    released = []
    let_go_of = release.release_scene

    def recording(scene):
        released.append(scene)
        let_go_of(scene)
    monkeypatch.setattr(release, "release_scene", recording)
    window.hide()
    made = []

    def new(x, path=None):
        other = window.open_new_window()
        other.confirm_discard = lambda: True
        other.interactive_prompts = False
        other.setGeometry(x, 0, 1000, 700)
        if path is not None:
            other.open_from_command_line(str(path))
        _settle()
        made.append(other)
        return other
    new.released = released
    yield new
    for other in list(MainWindow._windows):
        if other is not window and shiboken6.isValid(other):
            other._closing_confirmed = True
            other.close()
    _settle()


def _released_none_of(released, *windows):
    """Nothing a window shows was let go of."""
    shown = {id(scene) for window in windows if not _gone(window)
             for _document, scene, _stack in window.shown_states() if scene is not None}
    assert not [scene for scene in released if id(scene) in shown]


def _onto_tabs(source, target, index=0):
    bar = target.document_tabs
    _drag_tab(source.document_tabs, index, bar, bar.tabRect(0).center())


# -- the same document in two windows (a tab's New Window) -----------------

@pytest.mark.parametrize("which", ["second onto first", "first onto second"])
def test_the_same_document_dragged_into_its_other_window_is_a_second_tab(make, tmp_path,
                                                                         which):
    a = _pdf(tmp_path / "a.pdf", pages=2)
    first = make(0, a)
    _mark(first)
    second = first.open_same_document_window()
    second.confirm_discard = lambda: True
    second.setGeometry(1040, 0, 1000, 700)
    _settle()
    assert second.document is first.document and _names(second) == ["a.pdf"]
    source, target = (second, first) if which == "second onto first" else (first, second)
    source.view.set_zoom(1.7)
    target.view.set_zoom(0.6)
    document, scene, stack = source.document, source.scene, source.undo_stack
    _onto_tabs(source, target)
    assert _gone(source), "the window left with no tab closes"
    # not merged: two tabs, two views of the one document
    assert _names(target) == ["a.pdf", "a.pdf"]
    assert all(target.document_tabs.tabText(i).endswith("•") for i in range(2)), \
        "both say the document has unsaved changes"
    assert "two tabs" in target.status_hint.text()
    assert not target.workspace_empty
    _shows_its_documents(target)
    zooms = []
    for index in range(2):
        target.switch_to_document(index)
        assert target.document is document and target.scene is scene
        assert target.undo_stack is stack
        zooms.append(round(target.view.zoom(), 2))
    assert sorted(zooms) == [0.6, 1.7], "each tab keeps its own zoom"
    assert len(_rects(target)) == 1
    target.undo_stack.undo()
    assert not _rects(target)
    target.undo_stack.redo()
    assert len(_rects(target)) == 1
    _released_none_of(make.released, target)


def test_a_new_window_of_the_document_shows_its_edits_and_closes_without_asking(make, tmp_path):
    first = make(0, _pdf(tmp_path / "a.pdf"))
    second = first.open_same_document_window()
    asked = []
    second.confirm_discard = lambda: asked.append(True) or True
    second.setGeometry(1040, 0, 1000, 700)
    _settle()
    _mark(first)
    # one document, one canvas, one history: an edit in either is in both
    assert second.view.scene() is first.view.scene()
    assert len(_rects(second)) == 1
    QTest.keyClick(second.view.viewport(), Qt.Key_Z, Qt.ControlModifier)
    _settle()
    assert not _rects(first)
    QTest.keyClick(first.view.viewport(), Qt.Key_Y, Qt.ControlModifier)
    _settle()
    assert len(_rects(second)) == 1
    # closing the second window loses nothing: the first still has it
    second.close()
    _settle()
    assert not asked and _gone(second)
    _shows_its_documents(first)
    assert len(_rects(first)) == 1 and not first.undo_stack.isClean()
    _released_none_of(make.released, first)


# -- two copies of one file, each read from the disk apart --------------------

def _separate_copy(make, x, path):
    """A window holding a copy of *path* read from the disk on its own, as
    a recovered version is: File ▸ Open no longer makes one (it shows the
    live document another window has open)."""
    other = make(x)
    assert other.open_path(str(path)) is not False
    other.current_index = 0
    other.rebuild_scenes()
    other.view.fit_page()
    other.update_title()
    other._let_go()
    _settle()
    return other


@pytest.mark.parametrize("changed", ["neither", "the one there", "the one brought in", "both"])
def test_two_copies_of_one_file_are_both_kept_not_merged(make, tmp_path, changed):
    a = _pdf(tmp_path / "a.pdf")
    first = make(0, a)
    second = _separate_copy(make, 1040, a)
    assert first.document is not second.document
    if changed in ("the one there", "both"):
        _mark(first)
    if changed in ("the one brought in", "both"):
        _mark(second)
        _mark(second, x=260)
    there, brought = first.document, second.document
    _onto_tabs(second, first)
    assert _gone(second)
    assert sorted(_names(first)) == ["a.pdf", "a.pdf (2)"]
    assert "(2)" in first.status_hint.text()
    _shows_its_documents(first)
    found = {}
    for index in range(2):
        first.switch_to_document(index)
        found[_names(first)[index]] = (first.document, len(_rects(first)),
                                       first.undo_stack.count())
    expected_there = 1 if changed in ("the one there", "both") else 0
    expected_brought = 2 if changed in ("the one brought in", "both") else 0
    assert found == {"a.pdf": (there, expected_there, expected_there),
                     "a.pdf (2)": (brought, expected_brought, expected_brought)}
    _released_none_of(make.released, first)
    # the first copy closed, the other is just a.pdf again
    plain = _names(first).index("a.pdf")
    first.close_document_tab(plain)
    _settle()
    assert _names(first) == ["a.pdf"]
    assert first.document is brought and len(_rects(first)) == expected_brought


# -- a tab of another file ---------------------------------------------------

def test_a_tab_of_another_file_moves_with_its_canvas_place_history_and_selection(make, tmp_path):
    first = make(0, _pdf(tmp_path / "a.pdf"))
    second = make(1040, _pdf(tmp_path / "b.pdf", pages=3))
    second.open_in_new_tab()
    second.open_from_command_line(str(_pdf(tmp_path / "c.pdf")))
    second.switch_to_document(0)
    _settle()
    _mark(second)
    rect = _rects(second)[0]
    second.view.scene().clearSelection()
    rect.setSelected(True)
    second.view.set_zoom(1.5)
    second.go_to_page(2)
    scene, stack, zoom = second.scene, second.undo_stack, second.view.zoom()
    _onto_tabs(second, first)
    assert not _gone(second), "a window keeping a tab stays"
    assert _names(second) == ["c.pdf"]
    assert sorted(_names(first)) == ["a.pdf", "b.pdf"]
    assert first.document.path.endswith("b.pdf")
    assert first.scene is scene and first.view.scene() is scene
    assert first.undo_stack is stack and stack.count() == 1
    assert first.view.zoom() == pytest.approx(zoom)
    assert first.current_index == 2
    assert [item for item in scene.selectedItems() if isinstance(item, RectItem)] == [rect]
    _shows_its_documents(first)
    _shows_its_documents(second)
    QTest.keyClick(first.view.viewport(), Qt.Key_Z, Qt.ControlModifier)
    _settle()
    assert not _rects(first)
    _released_none_of(make.released, first, second)


def test_a_last_tab_of_another_file_moves_and_its_window_closes(make, tmp_path):
    first = make(0, _pdf(tmp_path / "a.pdf"))
    second = make(1040, _pdf(tmp_path / "b.pdf"))
    _mark(second)
    _onto_tabs(second, first)
    assert _gone(second)
    assert sorted(_names(first)) == ["a.pdf", "b.pdf"]
    assert first.document.path.endswith("b.pdf") and len(_rects(first)) == 1
    _shows_its_documents(first)
    _released_none_of(make.released, first)


def test_the_history_brought_in_undoes_on_its_new_window(make, tmp_path):
    """Undo steps recorded in the window a document came from act on the
    window it is in now, even once the first window has closed: they used to
    call back into the window that recorded them (a crash once it had gone,
    and a page put back into whatever document it showed next)."""
    first = make(0, _pdf(tmp_path / "a.pdf"))
    second = make(1040, _pdf(tmp_path / "b.pdf"))
    _mark(second)                              # a markup drawn
    second.add_page()                          # and a page added: a change of structure
    assert len(second.document.pages) == 2
    _onto_tabs(second, first)
    assert _gone(second)
    assert first.document.path.endswith("b.pdf")
    QTest.keyClick(first.view.viewport(), Qt.Key_Z, Qt.ControlModifier)
    _settle()
    assert len(first.document.pages) == 1 and len(_rects(first)) == 1
    QTest.keyClick(first.view.viewport(), Qt.Key_Z, Qt.ControlModifier)
    _settle()
    assert not _rects(first)
    _shows_its_documents(first)
    QTest.keyClick(first.view.viewport(), Qt.Key_Y, Qt.ControlModifier)
    QTest.keyClick(first.view.viewport(), Qt.Key_Y, Qt.ControlModifier)
    _settle()
    assert len(first.document.pages) == 2 and len(_rects(first)) == 1
    first.switch_to_document(_names(first).index("a.pdf"))
    assert len(first.document.pages) == 1 and not _rects(first)
    _released_none_of(make.released, first)


def test_a_tab_dropped_on_the_other_windows_canvas_goes_there(make, tmp_path):
    first = make(0, _pdf(tmp_path / "a.pdf"))
    second = make(1040, _pdf(tmp_path / "b.pdf"))
    second.open_in_new_tab()
    second.open_from_command_line(str(_pdf(tmp_path / "c.pdf")))
    _settle()
    before = set(MainWindow._windows)
    viewport = first.view.viewport()
    _drag_tab(second.document_tabs, 1, viewport, viewport.rect().center())
    assert set(MainWindow._windows) <= before, "no third window laid over the first"
    assert sorted(_names(first)) == ["a.pdf", "c.pdf"]
    assert _names(second) == ["b.pdf"]
    _shows_its_documents(first)
    _shows_its_documents(second)
    _released_none_of(make.released, first, second)


def test_a_tab_dropped_on_an_empty_window_fills_it(make, tmp_path):
    first = make(0, _pdf(tmp_path / "a.pdf"))
    first.close_document_tab(0)
    _settle()
    assert first.workspace_empty
    second = make(1040, _pdf(tmp_path / "b.pdf"))
    second.open_in_new_tab()
    second.open_from_command_line(str(_pdf(tmp_path / "c.pdf")))
    _settle()
    _drag_tab(second.document_tabs, 0, first, first.rect().center())
    assert not first.workspace_empty
    assert _names(first) == ["b.pdf"]
    assert _names(second) == ["c.pdf"]
    _shows_its_documents(first)
    _released_none_of(make.released, first, second)


def test_a_tab_dragged_out_to_nowhere_still_makes_a_window(make, tmp_path):
    first = make(0, _pdf(tmp_path / "a.pdf"))
    first.open_in_new_tab()
    first.open_from_command_line(str(_pdf(tmp_path / "b.pdf")))
    _settle()
    before = set(MainWindow._windows)
    bar = first.document_tabs
    _drag_tab(bar, 1, bar, QPoint(bar.width() + 80, bar.height() + 80))
    made = [w for w in MainWindow._windows if w not in before]
    assert len(made) == 1 and made[0].document.path.endswith("b.pdf")
    assert _names(first) == ["a.pdf"]
    _shows_its_documents(made[0])
    _released_none_of(make.released, first, made[0])


# -- opening a file another window has open ----------------------------------

def test_opening_a_file_another_window_has_open_shows_the_same_live_document(make, tmp_path,
                                                                            monkeypatch):
    a, b = _pdf(tmp_path / "a.pdf"), _pdf(tmp_path / "b.pdf")
    first = make(0, a)
    first.open_in_new_tab()
    first.open_from_command_line(str(b))
    second = make(1040, _pdf(tmp_path / "c.pdf"))
    first.switch_to_document(0)
    _mark(first)                               # an unsaved change to a.pdf
    first.switch_to_document(1)
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *args, **kw: (str(a), "")))
    QTest.keyClick(second.view.viewport(), Qt.Key_O, Qt.ControlModifier)
    _settle()
    # a tab of its own here, on the document the first window has: its
    # unsaved change is here too, and nothing was read from the disk again
    assert _names(second) == ["c.pdf", "a.pdf"]
    assert second.document_tabs.tabText(1).endswith("•")
    first.switch_to_document(0)
    assert second.document is first.document and second.scene is first.scene
    assert second.undo_stack is first.undo_stack
    assert len(_rects(second)) == 1
    assert "same document" in second.status_hint.text()
    assert _names(first) == ["a.pdf", "b.pdf"], "the first window keeps its tabs"
    _shows_its_documents(second)
    _released_none_of(make.released, first, second)
