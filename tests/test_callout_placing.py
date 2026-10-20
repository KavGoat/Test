"""Placing a call-out, a text box or a Cloud+ keeps up with the pointer, and
Cloud+ is drawn as Revu draws it (the user, 2026-10-19, on Windows: "Placing a
callout is laggy." "Cloud+ (cloud with leader) doesn't let me drag a cloud, it
only places it.").

What the lag was, measured on a marked-up sheet: every move of the pointer
with a drawing tool in hand — before the first click and while the leader
followed the pointer to where the words go — repainted the whole canvas: the
page, its drawing and every markup on screen, for a preview a few hundred
pixels across (10–12 ms of the window's own work a move, against 2–4 ms for a
drag of a text box, which repaints only itself). The preview is now
repainted where it was and where it is, and nothing else; the Properties
panel, rebuilt for the markup just placed, no longer draws its line-style
samples afresh each time.

Cloud+ is Revu's: press and drag for a rectangular cloud of that size, or
click its corners for a free-form one — closed by a double-click, by clicking
the first corner again, by Enter or by a right-click — and then a click for
where its words go. The cloud and the words are one markup, one undo step,
and it is saved and exported as it was.
"""
from __future__ import annotations

import statistics
import time

import pytest
from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from calcforge.items.text import CalloutItem
from tests.test_markup_interaction_round6 import (click, drag, key, markups, move,
                                                  page, pump, screen, vp)
from tests.test_usability import double_click

#: the window's own work for one move of the pointer, in milliseconds of its
#: thread's time (generous, for a loaded test machine)
MEDIAN_BUDGET = 8.0
P95_BUDGET = 30.0


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.view.set_zoom(1.0)
    pump()
    return window


# -- keeping up with the pointer ------------------------------------------------

class _Painted(QObject):
    """The share of the canvas each paint covered."""

    def __init__(self, viewport):
        super().__init__()
        self.viewport = viewport
        self.shares: list = []
        viewport.installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched is self.viewport and event.type() == QEvent.Paint:
            whole = self.viewport.width() * self.viewport.height()
            painted = sum(r.width() * r.height() for r in event.region())
            self.shares.append(painted / max(whole, 1))
        return False


def _work(app, action) -> float:
    start = time.thread_time()
    action()
    app.processEvents()
    return (time.thread_time() - start) * 1000.0


def _marked_up(w, tmp_path):
    from tests.test_big_pdf_smooth import _heavy_set

    w.open_from_command_line(_heavy_set(tmp_path / "set.pdf", pages=2))
    w.view.set_zoom(1.0)
    w.view.centerOn(page(w, 400, 380))
    for _ in range(20):
        pump()
        time.sleep(0.01)


def _moves(w, tool: str) -> tuple[list, dict]:
    """Hover with *tool* in hand, then place it while the pointer moves:
    (the window's work for each move, {"hover"/"placing": the share of the
    canvas each paint covered})."""
    app = QApplication.instance()
    view = w.view
    w.select_tool(tool)
    pump()
    work = []
    painted = _Painted(vp(w))
    shares = {"hover": painted.shares}
    start = page(w, 300, 300)
    for i in range(30):                           # with the tool in hand
        point = QPointF(start.x() - 90 + 3 * i, start.y() - 30 + i)
        work.append(_work(app, lambda point=point: move(w, point)))
    if tool == "cloud_callout":                   # its cloud, dragged
        drag(w, start, QPointF(start.x() + 120, start.y() + 80))
    elif tool == "callout":                       # what it points at
        click(w, start)
    else:                                         # the box's first corner
        QTest.mousePress(vp(w), Qt.LeftButton, Qt.NoModifier, screen(w, start))
    painted.shares = shares["placing"] = []
    for i in range(40):                           # the leader, or the box, follows
        if tool == "text":
            point = QPointF(start.x() + 4 * i, start.y() + i)
        else:
            point = QPointF(start.x() + 150 + 3 * i, start.y() - 2 * i)
        work.append(_work(app, lambda point=point: move(w, point)))
    if tool == "text":
        QTest.mouseRelease(vp(w), Qt.LeftButton, Qt.NoModifier, screen(w, point))
    else:
        click(w, point)
    pump()
    assert view.editing_item() is not None, f"the {tool} was placed and is typed into"
    QTest.keyClicks(QApplication.focusWidget() or vp(w), "Check this weld")
    key(w, Qt.Key_Escape)
    painted.viewport.removeEventFilter(painted)
    return work, shares


@pytest.mark.parametrize("tool", ["callout", "text", "cloud_callout"])
def test_placing_keeps_up_with_the_pointer(w, tmp_path, tool):
    """Each move of the pointer while a call-out, a text box or a Cloud+ is
    put down on a marked-up sheet is a frame's work, not a repaint of it."""
    _marked_up(w, tmp_path)
    _moves(w, tool)                               # once to warm up
    work, shares = _moves(w, tool)

    work.sort()
    median, p95 = statistics.median(work), work[int(len(work) * 0.95)]
    assert median < MEDIAN_BUDGET and p95 < P95_BUDGET, (
        f"{tool}: the window's work per move is {median:.1f} ms (median), "
        f"{p95:.1f} ms (95th percentile)")
    # what it was: every move repainted all of the canvas
    for phase, covered in shares.items():
        typical = sorted(covered)[len(covered) // 2] if covered else 0.0
        assert typical < 0.5, (
            f"{tool}, {phase}: a move repainted {typical:.0%} of the canvas")


def test_a_callout_preview_leaves_nothing_behind(w):
    """Repainting only where the leader was and is still clears where it was:
    the canvas after the pointer has moved on is the canvas drawn afresh."""
    w.select_tool("callout")
    click(w, page(w, 200, 300))
    for i in range(12):
        move(w, page(w, 260 + 15 * i, 260 - 9 * i))
        pump()
    view = w.view
    shown = view.viewport().grab().toImage()
    view.viewport().repaint()
    fresh = view.viewport().grab().toImage()
    assert shown == fresh, "a piece of an earlier preview was left on the canvas"
    key(w, Qt.Key_Escape)


def test_a_line_style_sample_is_drawn_once():
    """The Properties panel's line-style list, filled again for each markup
    placed or picked, takes its samples as they were drawn."""
    from calcforge.ui.panels import _line_style_icon

    first = _line_style_icon("dashed", "#ff0000", 1.0)
    assert _line_style_icon("dashed", "#ff0000", 1.0).cacheKey() == first.cacheKey()
    assert _line_style_icon("dashed", "#0000ff", 1.0).cacheKey() != first.cacheKey()
    assert _line_style_icon("dashed", "#ff0000", 1.0, cloud=True).cacheKey() \
        != first.cacheKey()


# -- Cloud+, drawn as Revu draws it ---------------------------------------------

def _cloud_corners(callout) -> list:
    leader = callout.cloud_leader()
    assert leader is not None, "the Cloud+ has its cloud"
    frame = callout.parentItem()
    return [frame.mapFromItem(callout, point) for point in leader.cloud]


def _cloud_plus(w, text="Revised"):
    (callout,) = markups(w, CalloutItem)
    QTest.keyClicks(QApplication.focusWidget() or vp(w), text)
    key(w, Qt.Key_Escape)
    return callout


def test_a_dragged_cloud_plus_is_a_cloud_of_that_size(w):
    """Press, drag, let go: a rectangular cloud of the dragged size — then the
    click for the words, the leader joining the two."""
    key(w, Qt.Key_Q, Qt.ShiftModifier)
    assert w.view.tool_key == "cloud_callout"
    drag(w, page(w, 150, 200), page(w, 330, 320))
    assert markups(w, CalloutItem) == [], "nothing lands until the words are placed"
    move(w, page(w, 450, 140))
    click(w, page(w, 450, 140))
    callout = _cloud_plus(w)

    corners = _cloud_corners(callout)
    box = QRectF(corners[0], corners[2]).normalized()
    assert len(corners) == 4
    assert box.left() == pytest.approx(150, abs=1.5)
    assert box.top() == pytest.approx(200, abs=1.5)
    assert box.width() == pytest.approx(180, abs=1.5)
    assert box.height() == pytest.approx(120, abs=1.5)
    words = callout.mapRectToParent(callout.local_rect())
    assert words.left() == pytest.approx(450, abs=1.5), "the words where clicked"
    assert callout.text() == "Revised"
    assert callout.display_name() == "Cloud+"


@pytest.mark.parametrize("closing", ["double-click", "first corner", "enter"])
def test_a_clicked_cloud_plus_follows_its_corners(w, closing):
    """Click, click, click: a free-form cloud through those corners, closed
    by a double-click, the first corner again or Enter."""
    w.select_tool("cloud_callout")
    corners = [(150, 200), (330, 210), (300, 330), (170, 300)]
    for x, y in corners:
        move(w, page(w, x, y))
        click(w, page(w, x, y))
    assert w.view._mode == "draw_poly"
    if closing == "double-click":
        x, y = 140, 260
        corners.append((x, y))
        move(w, page(w, x, y))
        at = page(w, x, y)
        double_click(w.view, at.x(), at.y())      # press, release, double-click, release
        pump()
    elif closing == "first corner":
        move(w, page(w, 152, 202))
        click(w, page(w, 152, 202))
    else:
        key(w, Qt.Key_Return)
    assert w.view._mode != "draw_poly", "the cloud is closed"
    assert w.view._pending_cloud is not None, "and the words come next"
    move(w, page(w, 470, 150))
    click(w, page(w, 470, 150))
    callout = _cloud_plus(w)

    drawn = _cloud_corners(callout)
    assert len(drawn) == len(corners)
    for point, (x, y) in zip(drawn, corners):
        assert point.x() == pytest.approx(x, abs=1.5)
        assert point.y() == pytest.approx(y, abs=1.5)


def test_a_drawn_cloud_closes_on_its_first_corner_too(w):
    """The Cloud tool, clicked corner by corner, closes the same way."""
    from calcforge.items.shapes import PolyItem

    w.select_tool("cloud")
    for x, y in ((150, 200), (330, 210), (300, 330)):
        move(w, page(w, x, y))
        click(w, page(w, x, y))
    click(w, page(w, 151, 201))
    assert w.view._mode != "draw_poly"
    (cloud,) = markups(w, PolyItem)
    assert cloud.kind == "cloud" and len(cloud.points) == 3


def test_a_cloud_plus_is_one_undo_step_and_comes_back(w):
    w.select_tool("cloud_callout")
    drag(w, page(w, 150, 200), page(w, 330, 320))
    click(w, page(w, 450, 140))
    callout = _cloud_plus(w)
    corners = _cloud_corners(callout)

    w.undo_stack.undo()
    pump()
    assert markups(w, CalloutItem) == [], "one undo takes the cloud, leader and words"
    w.undo_stack.redo()
    pump()
    (again,) = markups(w, CalloutItem)
    assert again.text() == "Revised"
    assert [(round(p.x()), round(p.y())) for p in _cloud_corners(again)] == \
        [(round(p.x()), round(p.y())) for p in corners]


def test_a_dragged_cloud_plus_is_saved_and_exported_as_it_was(w, tmp_path):
    from pypdf import PdfReader

    from calcforge.io import export as export_io
    from tests.test_propbar_gaps import save_and_reopen

    w.select_tool("cloud_callout")
    drag(w, page(w, 150, 200), page(w, 330, 320))
    click(w, page(w, 450, 140))
    corners = [(round(p.x()), round(p.y())) for p in _cloud_corners(_cloud_plus(w))]

    save_and_reopen(w, tmp_path)
    (reopened,) = markups(w, CalloutItem)
    assert reopened.text() == "Revised"
    assert [(round(p.x()), round(p.y())) for p in _cloud_corners(reopened)] == corners

    path = str(tmp_path / "exported.pdf")
    export_io.export_pdf(w.document, path)
    pdf_page = PdfReader(path).pages[0]
    notes = [entry.get_object() for entry in pdf_page["/Annots"]]
    (note,) = [mark for mark in notes if str(mark.get("/IT", "")) == "/FreeTextCallout"]
    assert "Revised" in str(note.get("/Contents", ""))
    # the cloud is part of what it draws: its box takes in the clouded area
    left, bottom, right, top = (float(v) for v in note["/Rect"])
    height = float(pdf_page.mediabox.height)
    assert left <= 150 and right >= 450
    assert height - top <= 140 and height - bottom >= 320


def test_a_cloud_plus_from_a_tool_set_is_drawn_with_the_cloud_plus_tool(w):
    """A Cloud+ kept in a tool set to draw with its properties is drawn as a
    Cloud+ — a cloud dragged round, then the words — not as a plain call-out
    with no cloud."""
    from calcforge.ui import toolsets

    w.select_tool("cloud_callout")
    drag(w, page(w, 150, 200), page(w, 330, 320))
    click(w, page(w, 450, 140))
    kept = toolsets.entry_for(_cloud_plus(w), toolsets.PROPERTIES)
    w.select_tool("select")

    w.use_tool_entry(kept)
    assert w.view.tool_key == "cloud_callout"
    drag(w, page(w, 150, 450), page(w, 300, 560))
    click(w, page(w, 450, 420))
    callout = [c for c in markups(w, CalloutItem) if c.cloud_leader() is not None
               and _cloud_corners(c)[0].y() > 400]
    assert len(callout) == 1, "the second Cloud+ has a cloud of its own"
    box = QRectF(_cloud_corners(callout[0])[0], _cloud_corners(callout[0])[2]).normalized()
    assert box.width() == pytest.approx(150, abs=1.5)
    assert box.height() == pytest.approx(110, abs=1.5)
