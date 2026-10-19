"""Any run of page changes and markups undoes and redoes exactly.

The user's case (found 2026-10-19): add a page, draw a markup on the page
above it, Ctrl+Z twice, Ctrl+Y twice — the page came back but the markup did
not. The rectangle had gone onto the page pressed on while the page the
window calls current was the new one, and only the current page was
compared, so the drawing made no undo step at all: the first Ctrl+Z took the
page away and the rectangle with it, for good.

The property checked here, over seeded random runs of real commands (pages
added, deleted, moved, rotated, duplicated, resized and set up, a workbook
and a sheet page inserted, rectangles drawn with the mouse on any page,
markups deleted with the Delete key): every command that changes the
document is one undo step; each Ctrl+Z gives back exactly the document as it
was before that step, and each Ctrl+Y exactly the one after it.
"""
import json
import random

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest

from calcforge.items.shapes import RectItem
from tests.test_split_tabs import _pdf, _settle
from tests.test_usability import drag


def _state(window) -> str:
    return json.dumps(window.document.to_dict(), sort_keys=True, default=str)


def _key(window, key):
    QTest.keyClick(window.view.viewport(), key, Qt.ControlModifier)
    _settle()


def _draw_on(window, index, rng=None):
    """A rectangle dragged out with the mouse on page *index*."""
    frame = window.document.pages[index].frame
    box = frame.mapRectToScene(frame.page_rect())
    dx = rng.uniform(20, 120) if rng else 40
    dy = rng.uniform(20, 120) if rng else 40
    start = QPointF(box.left() + dx, box.top() + dy)
    window.select_tool("rect")
    drag(window.view, start.x(), start.y(), start.x() + 60, start.y() + 40)
    window.select_tool("select")
    _settle()


def _rects(page):
    return [item for item in page.frame.markups() if isinstance(item, RectItem)] \
        if page.frame is not None else []


@pytest.fixture
def opened(window, tmp_path):
    window.show()
    window.open_from_command_line(str(_pdf(tmp_path / "b.pdf", pages=2)))
    _settle()
    return window


@pytest.mark.parametrize("where", ["above the new page", "on the new page"])
def test_a_markup_drawn_after_a_page_is_added_comes_back_with_redo(opened, where):
    window = opened
    window.add_page(0)                            # after the first page: now page 2
    assert window.current_index == 1
    _draw_on(window, 0 if where == "above the new page" else 1)
    pages = window.document.pages
    drawn = pages[0] if where == "above the new page" else pages[1]
    assert len(_rects(drawn)) == 1
    assert window.undo_stack.count() == 2, "the drawing is a step of its own"
    after = _state(window)
    _key(window, Qt.Key_Z)
    assert len(window.document.pages) == 3 and not any(_rects(p) for p in window.document.pages)
    _key(window, Qt.Key_Z)
    assert len(window.document.pages) == 2
    _key(window, Qt.Key_Y)
    _key(window, Qt.Key_Y)
    assert len(window.document.pages) == 3
    assert sum(len(_rects(p)) for p in window.document.pages) == 1
    assert _state(window) == after


def test_markups_on_an_existing_and_a_new_page_both_come_back(opened):
    window = opened
    window.add_page(0)
    _draw_on(window, 1)                           # on the new page
    _draw_on(window, 0)                           # and on the one above it
    after = _state(window)
    for _ in range(3):
        _key(window, Qt.Key_Z)
    assert len(window.document.pages) == 2
    for _ in range(3):
        _key(window, Qt.Key_Y)
    assert _state(window) == after
    assert [len(_rects(p)) for p in window.document.pages] == [1, 1, 0]


def _workbook(path):
    from openpyxl import Workbook
    book = Workbook()
    sheet = book.active
    sheet.title = "Loads"
    sheet.append(["Load", "Span", "Total"])
    sheet.append([10, 4, "=SUM(A2,B2)"])
    book.save(path)
    return str(path)


def _commands(window, rng, tmp_path):
    from calcforge.ui.pagesetup import Plan
    pages = window.document.pages
    count = len(pages)
    page = rng.randrange(count)
    marked = [item for p in pages for item in _rects(p)]

    def delete_markup():
        window.view.scene().clearSelection()
        rng.choice(marked).setSelected(True)
        QTest.keyClick(window.view.viewport(), Qt.Key_Delete)
        _settle()

    choices = [
        ("draw", lambda: _draw_on(window, page, rng)),
        ("draw", lambda: _draw_on(window, page, rng)),
        ("draw", lambda: _draw_on(window, page, rng)),
        ("add page", lambda: window.add_page(page)),
        ("add page before", lambda: window.add_page(page, before=True)),
        ("duplicate page", lambda: window.duplicate_page(page)),
        ("rotate page", lambda: window.rotate_page(page, rng.random() < 0.5)),
        ("page size", lambda: window.set_page_size(page, rng.choice(["A3", "A4", "A5"]))),
        ("page setup", lambda: window.apply_page_setup(
            Plan(media=("A3", 420.0, 297.0, "landscape"), fit=True), [page])),
        ("sheet page", lambda: window.insert_sheet_page(page)),
        ("workbook", lambda: window.insert_workbook(
            _workbook(tmp_path / f"w{rng.randrange(10**6)}.xlsx"), page)),
    ]
    if count > 1:
        choices += [
            ("delete page", lambda: window.delete_page(page, ask=False)),
            ("move page", lambda: window.move_page(page, rng.randrange(count))),
        ]
    if marked:
        choices += [("delete markup", delete_markup)]
    return rng.choice(choices)


@pytest.mark.parametrize("seed", range(1, 9))
def test_any_run_of_page_changes_and_markups_undoes_and_redoes_exactly(opened, tmp_path, seed):
    window = opened
    window.view.set_zoom(0.5)
    rng = random.Random(seed)
    states = [_state(window)]
    done = []
    for _ in range(18):
        name, act = _commands(window, rng, tmp_path)
        steps = window.undo_stack.index()
        act()
        _settle()
        now = _state(window)
        taken = window.undo_stack.index() - steps
        if taken == 0:
            # changed nothing (a move onto itself, say): then nothing changed
            assert now == states[-1], f"{name} changed the document with no undo step"
            continue
        assert taken == 1, f"{name} made {taken} undo steps"
        done.append(name)
        states.append(now)
    assert len(done) >= 8
    for back in range(len(done), 0, -1):
        _key(window, Qt.Key_Z)
        assert _state(window) == states[back - 1], f"undo of {done[back - 1]}: {done}"
    for forward in range(1, len(done) + 1):
        _key(window, Qt.Key_Y)
        assert _state(window) == states[forward], f"redo of {done[forward - 1]}: {done}"
    # and every page is on the canvas with what it holds
    scene = window.view.scene()
    assert len(scene.frames) == len(window.document.pages)
    assert all(page.frame is not None and page.frame.scene() is scene
               for page in window.document.pages)
