"""A big marked-up PDF opens before its markups are built (the user,
2026-10-29: "opening files led to a crash" — a set of hundreds of sheets,
every markup of every page built before the window answered, until Ctrl+C).
As Revu: a page's markups are built when it is looked at or asked for, the
rest behind the first screen (scene.PageFrame.hold_items / load_held,
MainWindow._load_behind); a page still holding its markups draws as its file
draws it; a save before they are built keeps every one."""
from __future__ import annotations

import time

import pytest
from PySide6.QtWidgets import QApplication

pymupdf = pytest.importorskip("pymupdf")

PAGES, EACH = 24, 12


def pump(seconds=0.0):
    end = time.monotonic() + seconds
    QApplication.processEvents()
    while time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.01)


def marked_set(path) -> str:
    """PAGES pages with EACH annotations each: text boxes, rectangles,
    clouds and lines, as a reviewer's set comes."""
    doc = pymupdf.open()
    for p in range(PAGES):
        page = doc.new_page(width=842, height=595)
        for k in range(EACH):
            x, y = 40 + (k % 4) * 180, 40 + (k // 4) * 160
            if k % 4 == 0:
                note = page.add_freetext_annot(pymupdf.Rect(x, y, x + 150, y + 36),
                                               f"Note {p}-{k}", fontsize=10)
            elif k % 4 == 1:
                note = page.add_rect_annot(pymupdf.Rect(x, y, x + 120, y + 80))
            elif k % 4 == 2:
                note = page.add_polygon_annot([(x, y), (x + 100, y), (x + 100, y + 60), (x, y + 60)])
                note.set_border(width=1.5, clouds=2)
            else:
                note = page.add_line_annot((x, y), (x + 150, y + 40))
            note.set_info(title="Reviewer", content="check")
            note.update()
    doc.save(str(path))
    return str(path)


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.interactive_prompts = False
    return window


def built(w) -> int:
    return sum(len(frame.built_markups()) for frame in w.scene.frames)


def wait_until_loaded(w, limit=30.0) -> None:
    end = time.monotonic() + limit
    while w._loading_behind and time.monotonic() < end:
        pump(0.02)
    assert not w._loading_behind, "the pages' markups are all built in time"


def test_the_window_answers_before_the_markups_are_built_and_they_follow(w, tmp_path):
    w._open_chosen(marked_set(tmp_path / "set.pdf"))
    frames = w.scene.frames
    assert len(frames) == PAGES
    assert any(frame.holds() for frame in frames), "most pages still hold their markups"
    assert built(w) < PAGES * EACH
    assert w.document.modified is False
    # the first screen's page is built as soon as it is looked at
    pump(0.3)
    first = frames[0]
    assert not first.holds() and len(first.built_markups()) == EACH
    assert first.page.markup_annotations, "its annotations are now the page's markups"
    # and the rest behind it, the Markups List filling in once they are all here
    wait_until_loaded(w)
    assert built(w) == PAGES * EACH
    assert all(not frame.holds() for frame in frames)
    assert w.document.modified is False, "opening and building is not an edit"
    pump(0.2)
    assert len(w.markups_panel.all_rows(w.document)) == PAGES * EACH
    assert not w.status_hint.text().startswith("Loading markups")


def test_a_page_asked_for_its_markups_builds_them_and_a_held_page_draws_as_its_file(w, tmp_path):
    w._open_chosen(marked_set(tmp_path / "set.pdf"))
    far = w.scene.frames[PAGES - 3]
    assert far.holds()
    assert far.left_to_us() == () and far.markups_drawn_alone() == (), \
        "nothing taken over: the file draws every annotation of a page not built yet"
    assert far.page.markup_annotations == []
    got = far.markups()                     # asked for: built now
    assert len(got) == EACH and not far.holds()
    assert len(far.page.markup_annotations) == EACH
    assert all(getattr(item, "still_theirs", False) for item in got), "untouched: still the file's"


def test_a_save_before_the_markups_are_built_keeps_every_one(w, tmp_path, qapp):
    from calcforge.ui.mainwindow import MainWindow
    w._open_chosen(marked_set(tmp_path / "set.pdf"))
    assert any(frame.holds() for frame in w.scene.frames)
    out = tmp_path / "saved.pdf"
    w.document.path = str(out)
    assert w.save_document()
    # saving reads what was not read yet, without building it
    assert sum(1 for frame in w.scene.frames if frame.holds()) > PAGES // 2
    other = MainWindow()
    other.confirm_discard = lambda: True
    other.interactive_prompts = False
    try:
        other._open_chosen(str(out))
        assert any(frame.holds() for frame in other.scene.frames), "opened lazily again"
        count = sum(len(frame.markups()) for frame in other.scene.frames)
        assert count == PAGES * EACH, "every markup came through the save"
    finally:
        other.close()
        other.deleteLater()
        pump()
