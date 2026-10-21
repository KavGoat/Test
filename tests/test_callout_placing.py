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

And the rest of the gesture (the user, 2026-10-21: "still laggy", on a
canvas drawn with the graphics card): the click that placed the call-out, the
Escape that finished it and every change of selection repainted the whole
canvas; on the graphics card every frame was drawn whole, whatever changed;
the Markups List was built again (or every markup's row read again) for each
markup placed, finished or undone — a tenth of a second on a set of a
thousand; undo took every markup of the page apart and made it again; and the
Properties panel gave each old control a new parent before deleting it, which
had the style sheet worked out again for every one. Now each step repaints
what changed, on the card too (ui/cardsurface.py), the list puts in just the
rows that changed, undo makes again only what differs, and the panel's old
controls go at once.

Cloud+ is Revu's: press and drag for a rectangular cloud of that size, or
click its corners for a free-form one — closed by a double-click, by clicking
the first corner again, by Enter or by a right-click — and then a click for
where its words go. The cloud and the words are one markup, one undo step,
and it is saved and exported as it was.
"""
from __future__ import annotations

import os
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
    from tests.test_big_pdf_smooth import _settle
    _settle(QApplication.instance(), w.view)        # every square of it drawn
    # the pointer has been over the page with a tool in hand: its line work
    # has been read to snap to (once, the first time)
    w.select_tool("line")
    for x in range(200, 420, 20):
        move(w, page(w, x, 300))
    w.select_tool("select")
    _quiet(w)


def _quiet(w, seconds: float = 0.5, limit: float = 15.0, repaint: bool = True) -> None:
    """Until nothing has been painted for *seconds*: the page's markups put
    into its squares (markuplayer.py) once the window is idle repaint the
    squares as they go, and that is not what is being measured."""
    if repaint:
        # (and once its markups have been still a moment, a page tells Qt
        # they stay inside it — on its next paint, which is then drawn whole)
        time.sleep(0.6)
        vp(w).repaint()
    painted = _Painted(vp(w))
    deadline = time.monotonic() + limit
    still = time.monotonic()
    try:
        while time.monotonic() < deadline:
            seen = len(painted.shares)
            QApplication.processEvents()
            time.sleep(0.01)
            layers = [getattr(frame, "layer", None) for frame in w.view.scene().frames]
            settling = any(layer is not None and (layer.hot or layer.pending)
                           for layer in layers)
            if len(painted.shares) != seen or settling:
                still = time.monotonic()
            elif time.monotonic() - still > seconds:
                return
    finally:
        painted.viewport.removeEventFilter(painted)


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


# -- the whole gesture: the click, the words, finishing, undo -------------------

class _Steps:
    """The Callout gesture driven step by step as the user makes it, with
    what each step cost the window and what it repainted."""

    def __init__(self, w):
        self.w = w
        self.app = QApplication.instance()
        self.work: dict = {}
        self.shares: dict = {}

    def step(self, name: str, action) -> None:
        painted = _Painted(vp(self.w))
        took = _work(self.app, action)
        self.app.processEvents()
        painted.viewport.removeEventFilter(painted)
        self.work.setdefault(name, []).append(took)
        self.shares.setdefault(name, []).extend(painted.shares)

    def callout(self, at: QPointF, words: str = "Check this weld") -> None:
        w = self.w
        w.select_tool("callout")
        pump()
        self.step("point", lambda: click(w, at))
        for i in range(12):
            self.step("follow", lambda i=i: move(w, QPointF(at.x() + 12 * i, at.y() - 8 * i)))
        where = QPointF(at.x() + 150, at.y() - 100)
        self.step("place", lambda: click(w, where))
        for letter in words:
            self.step("type", lambda letter=letter: QTest.keyClick(
                QApplication.focusWidget() or vp(w), letter))
        self.step("finish", lambda: key(w, Qt.Key_Escape))

    def undo_and_redo(self) -> None:
        w = self.w
        self.step("undo", lambda: QTest.keyClick(vp(w), Qt.Key_Z, Qt.ControlModifier))
        self.step("redo", lambda: QTest.keyClick(vp(w), Qt.Key_Y, Qt.ControlModifier))


def _held(window):
    """The canvas as the window holds it — its pixels as last painted,
    partial repaints and all, not a fresh paint as a grab is."""
    from tests.test_big_pdf_smooth import _shown
    return _shown(window, window.view.viewport())


def _as_drawn_afresh(window):
    viewport = window.view.viewport()
    viewport.repaint()
    QApplication.processEvents()
    return _held(window)


def test_the_whole_callout_gesture_repaints_only_what_changes(w, tmp_path):
    """Pointing, placing, typing, finishing, undoing and redoing a call-out on
    a marked-up sheet each repaint a small part of the canvas — the call-out
    and the preview — not all of it, as the click, Escape, a selection
    changing and the pointer leaving used to; and what is left on the canvas
    is what a fresh paint of it draws."""
    _marked_up(w, tmp_path)
    steps = _Steps(w)
    steps.callout(page(w, 300, 300))
    steps.undo_and_redo()
    for name, covered in steps.shares.items():
        assert covered, f"{name}: nothing was repainted"
        assert max(covered) < 0.5, (
            f"{name}: a paint covered {max(covered):.0%} of the canvas")
    assert _held(w) == _as_drawn_afresh(w), "a piece of an earlier frame was left"

    typed = sorted(steps.work["type"])
    assert statistics.median(typed) < MEDIAN_BUDGET, \
        f"a key typed into the call-out is {statistics.median(typed):.1f} ms of work"


@pytest.mark.parametrize("tool", ["callout", "cloud_callout"])
def test_nothing_is_left_on_the_canvas_by_any_step(w, tool):
    """After each step of the gesture the canvas the window holds is the
    canvas drawn afresh: repainting less never leaves a leader, a cloud, a
    preview box, a caret or a selection behind."""
    w.select_tool(tool)
    point = page(w, 200, 300)
    if tool == "cloud_callout":
        drag(w, point, page(w, 260, 350))
    else:
        click(w, point)
    checks = []
    for i in range(12):
        move(w, page(w, 260 + 15 * i, 260 - 9 * i))
        pump()
    checks.append(("following", _held(w), _as_drawn_afresh(w)))
    click(w, page(w, 430, 160))
    pump()
    checks.append(("placed", _held(w), _as_drawn_afresh(w)))
    QTest.keyClicks(QApplication.focusWidget() or vp(w), "Weld")
    pump()
    checks.append(("typed", _held(w), _as_drawn_afresh(w)))
    key(w, Qt.Key_Escape)
    checks.append(("finished", _held(w), _as_drawn_afresh(w)))
    QTest.keyClick(vp(w), Qt.Key_Z, Qt.ControlModifier)
    pump()
    checks.append(("undone", _held(w), _as_drawn_afresh(w)))
    for name, held, fresh in checks:
        assert held == fresh, f"{name}: something was left on the canvas"


def test_the_markups_list_puts_in_only_the_rows_that_change(w, tmp_path):
    """Placing, finishing, undoing and redoing a call-out put its row into the
    Markups List and take it out again — the list is not built again, nor
    every markup's row read, on a set of any size — and what it shows is what
    building it afresh shows, in every order and grouping."""
    _marked_up(w, tmp_path)
    panel = w.markups_panel
    QApplication.processEvents()
    built = []
    plain = panel.rebuild
    panel.rebuild = lambda document: (built.append(1), plain(document))

    def state():
        tree = panel.tree
        rows = []
        for at in range(tree.topLevelItemCount()):
            top = tree.topLevelItem(at)
            rows.append((tuple(top.text(c) for c in range(tree.columnCount())),
                         tuple(tuple(top.child(k).text(c) for c in range(tree.columnCount()))
                               for k in range(top.childCount())),
                         top.isSelected()))
            rows.extend((None, tuple(top.child(k).text(c) for c in range(tree.columnCount())),
                         top.child(k).isSelected()) for k in range(top.childCount()))
        return rows

    def as_built_afresh():
        shown = state()
        signed = panel._shown_before
        plain(w.document)
        assert shown == state(), "the list as put together is not the list built afresh"
        assert signed == panel._shown_before, "nor is its reading of what it shows"

    steps = _Steps(w)
    steps.callout(page(w, 300, 300))
    steps.undo_and_redo()
    assert not built, "the list was built again for a markup placed, finished or undone"
    as_built_afresh()

    # sorted by another column, the other way, and in no groups
    panel.tree.sortByColumn(2, Qt.DescendingOrder)
    panel.group_by.setCurrentIndex(panel.group_by.findData("None"))
    QApplication.processEvents()
    built.clear()
    steps.callout(page(w, 520, 420), words="Second")
    steps.undo_and_redo()
    assert not built
    as_built_afresh()


def test_undoing_a_placed_callout_leaves_the_rest_of_the_page_alone(w, tmp_path):
    """Undo takes the call-out away and keeps every other markup of the page
    as it is — the same markups, not each one taken apart and made again."""
    _marked_up(w, tmp_path)
    frame = w.document.pages[0].frame
    others = {item.uid: item for item in frame.markups()}
    steps = _Steps(w)
    steps.callout(page(w, 300, 300))
    QTest.keyClick(vp(w), Qt.Key_Z, Qt.ControlModifier)
    pump()
    after = {item.uid: item for item in frame.markups()}
    assert set(after) == set(others), "only the call-out went"
    assert all(after[uid] is others[uid] for uid in others), "the others were made again"
    QTest.keyClick(vp(w), Qt.Key_Y, Qt.ControlModifier)
    pump()
    (callout,) = [i for i in frame.markups() if isinstance(i, CalloutItem)]
    assert callout.text() == "Check this weld"


def test_the_properties_panel_is_taken_apart_at_once_after_a_click(w):
    """The Properties panel built again for a markup placed or picked on the
    canvas takes its old controls apart there and then — giving each a new
    parent first had the application's style sheet worked out again for
    every control, half the time of building the panel."""
    import shiboken6
    from PySide6.QtWidgets import QWidget

    w.select_tool("callout")
    click(w, page(w, 200, 300))
    click(w, page(w, 350, 200))
    panel = w.properties_panel
    old = [panel.layout.itemAt(i).widget() for i in range(panel.layout.count())]
    old = [widget for widget in old if isinstance(widget, QWidget)]
    assert old
    key(w, Qt.Key_Escape)
    click(w, page(w, 360, 205))            # the call-out picked again
    QApplication.processEvents()
    assert not any(shiboken6.isValid(widget) for widget in old), \
        "the old panel's controls were left for later"
    font = panel.body.findChild(QWidget, "fontFamily")
    assert font is not None and font.isVisible(), "the Font list is back in its place"


# -- on the graphics card ----------------------------------------------------------

#: set in the child process that draws with the graphics card
CARD = "CALCFORGE_CALLOUT_ON_THE_CARD"


@pytest.mark.skipif(not os.environ.get(CARD), reason="run in its own process, on the card")
def test_on_the_card(w, tmp_path):
    """Drawn with OpenGL, each step repaints only what changed — the card
    used to draw the whole canvas for every move of the pointer — and the
    window shows what a fresh paint of the canvas shows."""
    from calcforge.ui import cardsurface
    from tests.test_text_flicker import _on_screen

    assert w.view.gpu, "drawing with the graphics card"
    _marked_up(w, tmp_path)
    drawn = []
    plain = cardsurface.CardSurface.to_draw

    def to_draw(surface, *args, **kwargs):
        region = plain(surface, *args, **kwargs)
        whole = surface.width() * surface.height()
        drawn.append(1.0 if region is None else cardsurface._area(region) / whole)
        return region
    cardsurface.CardSurface.to_draw = to_draw
    try:
        w.select_tool("callout")
        start = page(w, 300, 300)
        click(w, start)
        drawn.clear()
        for i in range(20):
            move(w, QPointF(start.x() + 10 * i, start.y() - 6 * i))
            pump()
        following = list(drawn)
        click(w, QPointF(start.x() + 200, start.y() - 120))
        QTest.keyClicks(QApplication.focusWidget() or vp(w), "Weld")
        pump()
        drawn.clear()
        QTest.keyClicks(QApplication.focusWidget() or vp(w), "s")
        pump()
        typing = list(drawn)
        key(w, Qt.Key_Escape)                # (the caret blinks: finished first)
        _quiet(w, repaint=False)             # (what the page does once idle, done)
        shown = _on_screen(w)
        w.view.viewport().ask_all()
        w.view.viewport().update()
        for _ in range(5):
            pump()
            time.sleep(0.02)
        fresh = _on_screen(w)
    finally:
        cardsurface.CardSurface.to_draw = plain
    assert following and max(sorted(following)[:len(following) * 9 // 10]) < 0.5, \
        f"the leader followed with whole frames drawn: {following}"
    assert typing and max(typing) < 0.5, f"a key typed drew {typing}"
    assert (shown == fresh).all(), "the card left something of an earlier frame"


def _opengl_under_x() -> bool:
    from tests.test_text_flicker import _opengl_under_x as probe
    return probe()


@pytest.mark.skipif(bool(os.environ.get(CARD)), reason="the child itself")
def test_placing_a_callout_on_the_graphics_card():
    """The same, in a window drawn with OpenGL (Preferences ▸ Draw with the
    graphics card, on by default), under a virtual X display."""
    import subprocess
    import sys

    if not _opengl_under_x():
        pytest.skip("no X display with OpenGL to draw on")
    env = dict(os.environ, QT_QPA_PLATFORM="xcb", **{CARD: "1"})
    done = subprocess.run(
        ["xvfb-run", "-a", "-s", "-screen 0 1600x1000x24", sys.executable, "-m", "pytest",
         "-p", "no:cacheprovider", "-q", "-rA", "-x", os.path.abspath(__file__),
         "-k", "test_on_the_card"],
        env=env, capture_output=True, text=True, timeout=600,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    tail = "\n".join(line for line in done.stdout.splitlines()
                     if "PASSED" in line or "FAILED" in line or "Error" in line
                     or "assert" in line)
    assert done.returncode == 0, tail
    assert done.stdout.count("PASSED ") == 1, tail


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
