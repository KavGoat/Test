"""A closed document lets go of everything it held.

The full suite lost a worker to the out-of-memory killer at 2.4 GB, and a
table of a window closed long before was still being drawn in later tests: a
document closed in its tab, replaced by File ▸ New or Open, or left behind by
a split turned off kept its canvas, its pages and markups, its undo history,
the squares its markups were drawn into and its calculation hooks — and its
tables went on being drawn into those squares.

Each test here opens and closes documents with a PDF page, a table, a
spreadsheet page and equations through the real window, and counts what is
still alive afterwards.
"""
from __future__ import annotations

import gc
import weakref

import pytest
import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QApplication

from calcforge.core.document import Document
from calcforge.items.base import MarkupItem
from calcforge.items.calc import CalcItem
from calcforge.items.table import TableItem
from calcforge.ui.scene import DocumentScene, PageFrame
from tests.test_calc_panels import an_equation
from tests.test_tables import enter, make_table, type_text

KINDS = (DocumentScene, PageFrame, MarkupItem, TableItem, CalcItem, QUndoStack)


def settle():
    app = QApplication.instance()
    for _ in range(4):
        app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    gc.collect()
    app.processEvents()


def live() -> dict:
    """How many of each are alive (in Qt, not only as Python wrappers)."""
    gc.collect()
    found = {kind.__name__: 0 for kind in KINDS}
    found["Document"] = 0
    for thing in gc.get_objects():
        if isinstance(thing, Document):
            found["Document"] += 1
            continue
        for kind in KINDS:
            if isinstance(thing, kind) and shiboken6.isValid(thing):
                found[kind.__name__] += 1
    return found


def rss_mb() -> float:
    with open("/proc/self/status") as status:
        for line in status:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    return 0.0


def a_pdf(path):
    import fitz
    document = fitz.open()
    for number in range(2):
        page = document.new_page(width=842, height=595)
        page.insert_text((40, 60), f"{path.stem} page {number + 1}")
        page.draw_rect((100, 100, 400, 300))
    document.save(str(path))
    document.close()
    return str(path)


def fill(window, pdf):
    """A PDF opened, with a table, two equations and a spreadsheet page."""
    window.open_from_command_line(pdf)
    settle()
    make_table(window)
    type_text(window, "12")
    enter(window)
    an_equation(window, "a:=2")
    an_equation(window, "a*3=", y=200)
    window.toggle_calc_mode(False)
    window.insert_sheet_page(0)
    settle()
    assert any(isinstance(i, TableItem) for i in window.scene.items())
    assert any(isinstance(i, CalcItem) for i in window.scene.items())


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.view.set_zoom(1.0)
    settle()
    return window


@pytest.fixture
def closed_paints(monkeypatch):
    """Every table drawn whose document has been closed."""
    closed = weakref.WeakSet()
    painted = []
    original = TableItem.paint

    def paint(item, painter, option, widget=None):
        frame = item._page_frame()
        document = getattr(frame, "document", None)
        if document is not None and document in closed:
            painted.append(item)
        return original(item, painter, option, widget)

    monkeypatch.setattr(TableItem, "paint", paint)
    return closed, painted


def test_closing_a_tab_twenty_times_lets_go_of_everything(w, tmp_path, closed_paints):
    closed, painted = closed_paints
    pdf = a_pdf(tmp_path / "drawing.pdf")

    def cycle():
        w.open_in_new_tab()
        fill(w, pdf)
        closed.add(w.document)
        w.close_document_tab(w._active_tab)
        settle()

    cycle()                 # fonts, render processes and the like, once
    baseline = live()
    memory = rss_mb()
    for _ in range(20):
        cycle()
        assert live() == baseline
    grown = rss_mb() - memory
    assert grown < 50, f"{grown:.0f} MB more after 20 tabs opened and closed"
    # what is still open is untouched, and draws
    w.view.viewport().repaint()
    settle()
    assert not painted, "a table of a closed document was drawn"
    assert w.document not in closed


def test_file_new_and_open_let_go_of_the_document_they_replace(w, tmp_path, closed_paints):
    closed, painted = closed_paints
    pdf = a_pdf(tmp_path / "drawing.pdf")
    fill(w, pdf)
    closed.add(w.document)
    w.new_document(confirm=False)
    settle()
    baseline = live()
    for _ in range(5):
        fill(w, pdf)                  # Open replaces the blank document
        closed.add(w.document)
        w.new_document(confirm=False)  # and New replaces this one
        settle()
        assert live() == baseline
    assert not painted


def test_turning_a_split_off_lets_go_of_what_only_it_showed(w, tmp_path, closed_paints):
    closed, painted = closed_paints
    pdf = a_pdf(tmp_path / "drawing.pdf")
    w.open_in_new_tab()
    w.switch_to_document(0)
    baseline = live()
    for _ in range(5):
        w.switch_to_document(1)
        fill(w, pdf)
        closed.add(w.document)
        pane = w.split_document()
        assert w.is_split and w._active_pane is pane
        w.toggle_split_view()            # off: its document comes across
        assert not w.is_split
        w.close_document_tab(w._active_tab)
        w.open_in_new_tab()
        w.switch_to_document(0)
        settle()
        assert live() == baseline
    assert not painted


def test_a_document_still_open_in_another_tab_is_kept(w, tmp_path):
    """Closing one of two tabs on the same document keeps the document, its
    canvas and its undo history."""
    pdf = a_pdf(tmp_path / "drawing.pdf")
    fill(w, pdf)
    document, scene, stack = w.document, w.scene, w.undo_stack
    assert stack.count() > 0
    w.open_same_document_tab()
    w.close_document_tab(w._active_tab)
    settle()
    assert w.document is document and w.scene is scene
    assert shiboken6.isValid(scene) and shiboken6.isValid(stack)
    assert any(isinstance(i, TableItem) for i in scene.items())
    assert stack.count() > 0
    w.undo_something()
    settle()


def test_a_closed_window_leaves_no_canvas_behind(qapp, tmp_path):
    from calcforge.ui.mainwindow import MainWindow

    pdf = a_pdf(tmp_path / "drawing.pdf")
    before = live()
    for _ in range(3):
        main = MainWindow()
        main.confirm_discard = lambda: True
        main.interactive_prompts = False
        main.resize(1280, 860)
        main.show()
        main.view.set_zoom(1.0)
        fill(main, pdf)
        main.document.modified = False
        main.close()
        main.deleteLater()
        del main
        settle()
    assert live() == before
