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

And the leader following the pointer to where the words go (the user,
2026-10-21: "when I am moving my cursor to place the text box part, that's
what is laggy"): each move made the call-out afresh (its style applied twice
over, its words measured), asked every markup of the page where it was to
snap, and the pointer's place in the status bar laid the bar out and painted
it whole — on the graphics card, a frame of its own between the canvas's.
Now the call-out is kept while its look is the same, the page's snapping
targets are read once while it does not change, the status bar's place is
written in the move's own frame and the rulers repaint only their marks.

And it was jittery (the user, 2026-10-21): the box was drawn under the
pointer while the words' click snapped — on a marked-up sheet the marker
hopped between line ends every few pixels and the box jumped to it as the
click went down — and the leader flipped from one side of the box to the
other and back as the pointer wavered along the diagonal where two sides face
its target equally. The words now go where the pointer is (on the grid when
it is snapped to), shown and placed alike, and the leader holds its side
until another is clearly better.

And the frame rate (the user, 2026-10-21: "it's like the fps is lowered"): on
Windows the repaint Qt posts waits while input waits, and a mouse reporting
hundreds of times a second nearly always has a move waiting, so frames came
late and unevenly; a frame drawn on the card also waited for the screen's
refresh, and one a little late waited for the next. Moves now put their frame
on the screen themselves, once a refresh, with the canvas's own changes in
it, and on Windows the card does not wait for the refresh.

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
from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QRegion
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


# -- the leader following the pointer to where the words go -------------------

#: the window's own work for one move while the leader follows the pointer
#: on a marked-up sheet: 3–4.5 ms (from 4–8 ms before the preview's call-out
#: and the page's snapping targets were kept from move to move, 2026-10-21)
FOLLOW_MEDIAN_BUDGET = 6.0
FOLLOW_P95_BUDGET = 20.0


class _Seen(QObject):
    """Every paint of *widgets* — the share of each it covered — and every
    frame the window put on the screen."""

    def __init__(self, window, widgets):
        super().__init__()
        self.window = window
        self.widgets = list(widgets)
        self.shares = {id(widget): [] for widget in self.widgets}
        self.frames = 0
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind == QEvent.UpdateRequest and watched is self.window:
            self.frames += 1
        elif kind == QEvent.Paint:
            for widget in self.widgets:
                if watched is widget:
                    whole = max(widget.width() * widget.height(), 1)
                    painted = sum(r.width() * r.height() for r in event.region())
                    self.shares[id(widget)].append(painted / whole)
        return False

    def of(self, widget) -> list:
        return self.shares[id(widget)]

    def stop(self) -> None:
        QApplication.instance().removeEventFilter(self)


def test_the_leader_follows_the_pointer_at_a_frames_cost(w, tmp_path, monkeypatch):
    """Between the click on what a call-out points at and the click that puts
    its words down, each move of the pointer is a few milliseconds of the
    window's work, painted in the same pass of the event loop as the move —
    one frame, not a timer's hop later — and it repaints the leader and the
    rulers' marks, nothing else: the call-out the preview is drawn from is
    not made again, no panel is built again, and the status bar is not laid
    out and painted whole for the pointer's place (the user, 2026-10-21: "when
    I am moving my cursor to place the text box part, that's what is laggy,
    while the leader is recalculating the hinge")."""
    import calcforge.ui.view as view_module

    _marked_up(w, tmp_path)
    app = QApplication.instance()
    view, rulers, bar = w.view, w.view.rulers, w.statusBar()
    w.select_tool("callout")
    pump()
    start = page(w, 300, 300)
    click(w, start)
    for i in range(4):                        # its look is worked out once
        move(w, QPointF(start.x() + 20 + 3 * i, start.y() - 2 * i))
        pump()

    made, rebuilt = [], []
    plain_callout = view_module.CalloutItem

    class Counted(plain_callout):
        def __init__(self, *args, **kwargs):
            made.append(1)
            super().__init__(*args, **kwargs)
    monkeypatch.setattr(view_module, "CalloutItem", Counted)
    for panel, name in ((w.properties_panel, "show_items"), (w.markups_panel, "refresh"),
                        (w.markups_panel, "rebuild")):
        plain = getattr(panel, name)
        monkeypatch.setattr(panel, name, lambda *a, _plain=plain, _name=name, **k: (
            rebuilt.append(_name), _plain(*a, **k))[1])
    seen = _Seen(w, [vp(w), rulers.top, rulers.left, bar])

    def follow(moves: int, first: int, pace: float = 0.0) -> tuple:
        work, at_once = [], 0
        for i in range(first, first + moves):
            point = QPointF(start.x() + 150 + 3 * i, start.y() - 2 * i)
            painted = len(seen.of(vp(w)))
            began = time.thread_time()
            move(w, point)
            app.processEvents()               # one pass of the event loop
            if len(seen.of(vp(w))) > painted:
                at_once += 1
            pump()
            work.append((time.thread_time() - began) * 1000.0)
            time.sleep(pace)
        return sorted(work), at_once

    try:
        work, at_once = follow(40, 0)
        # and with the rulers up, at a pointer's pace: what goes to the screen
        w.act_rulers.trigger()
        follow(2, 40)                         # (shown: drawn whole, once)
        seen.shares = {key: [] for key in seen.shares}
        seen.frames = 0
        _paced, paced_at_once = follow(30, 42, pace=0.012)
    finally:
        seen.stop()

    median, p95 = statistics.median(work), work[int(len(work) * 0.95)]
    assert median < FOLLOW_MEDIAN_BUDGET and p95 < FOLLOW_P95_BUDGET, (
        f"a move of the leader is {median:.1f} ms of work (median), {p95:.1f} ms (95th)")
    assert at_once >= 36 and paced_at_once >= 27, (
        f"only {at_once} of 40 and {paced_at_once} of 30 moves were painted in "
        f"the event loop's pass that took the move")
    assert not made, f"the call-out the preview is drawn from was made {len(made)} times"
    assert not rebuilt, f"a panel was built again as the pointer moved: {rebuilt}"
    canvas = sorted(seen.of(vp(w)))
    assert canvas and canvas[len(canvas) // 2] < 0.15, \
        f"a move repainted {canvas[len(canvas) // 2]:.0%} of the canvas"
    for ruler in (rulers.top, rulers.left):
        assert seen.of(ruler) and max(seen.of(ruler)) < 0.1, \
            f"a ruler was painted whole for the pointer's mark: {seen.of(ruler)}"
    assert all(share < 0.5 for share in seen.of(bar)), \
        "the status bar was painted whole for the pointer's place"
    assert seen.frames <= len(seen.of(vp(w))) + 3, (
        f"{seen.frames} frames for {len(seen.of(vp(w)))} paints of the canvas: "
        f"the pointer's place went to the screen in frames of its own")
    rulers_now = [_held_of(w, ruler) for ruler in (rulers.top, rulers.left)]
    for ruler in (rulers.top, rulers.left):
        ruler.repaint()
    assert rulers_now == [_held_of(w, ruler) for ruler in (rulers.top, rulers.left)], \
        "a ruler's mark left something of where it was"
    assert _held(w) == _as_drawn_afresh(w), "the leader left a piece of itself behind"
    key(w, Qt.Key_Escape)


def test_the_preview_is_the_call_out_that_lands(w):
    """The call-out the preview is drawn from is kept from move to move, and
    is still the one a click would put down: where it is, where its leader
    leaves the box and turns, and how it looks — the toolbar's look changed
    half way is the look it then has."""
    view = w.view
    w.select_tool("callout")
    pump()
    click(w, page(w, 200, 300))
    anchor = view._pending_anchor              # (as snapped)

    def fresh():
        item = CalloutItem("")
        w.apply_default_style(item)
        box = view._pending_callout_box()
        item.set_local_rect(QRectF(0, 0, box.width(), box.height()))
        item.setPos(box.topLeft())
        item.tip = item.mapFromScene(anchor)
        return item

    def same(preview, made) -> None:
        assert preview.pos() == made.pos() and preview.local_rect() == made.local_rect()
        assert preview.tip == made.tip and preview.elbow() == made.elbow()
        assert preview.side() == made.side() and preview.side_point() == made.side_point()
        assert preview.style == made.style

    previews = []
    for i, point in enumerate((page(w, 380, 220), page(w, 90, 330), page(w, 210, 120),
                               page(w, 230, 470))):
        if i == 2:
            w.default_style.stroke = "#1c7ed6"     # the toolbar's colour changed
        move(w, point)
        pump()
        preview = view._pending_callout()
        previews.append(preview)
        same(preview, fresh())
    assert previews[0] is previews[1], "the preview's call-out was made again for a move"
    assert previews[1] is not previews[2], "the new look did not make a new one"
    assert previews[3].style.stroke == "#1c7ed6"
    click(w, page(w, 230, 470))
    pump()
    (placed,) = markups(w, CalloutItem)
    assert placed.style.stroke == previews[3].style.stroke
    assert placed.mapToScene(placed.tip) == previews[3].mapToScene(previews[3].tip)
    key(w, Qt.Key_Escape)


class _Regions(QObject):
    """What each paint of the canvas covered."""

    def __init__(self, viewport):
        super().__init__()
        self.viewport = viewport
        self.regions: list = []
        viewport.installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched is self.viewport and event.type() == QEvent.Paint:
            self.regions.append(QRegion(event.region()))
        return False


def test_the_words_glide_with_the_pointer(w, tmp_path):
    """While the leader follows the pointer to where the words go, the box is
    where the pointer is on every move — on a marked-up sheet as on a blank
    one: not caught by the ends of lines and corners it passes, the marker
    hopping from one to the next while the box was drawn under the pointer
    and the click then put it down at the marker, a jump (the user,
    2026-10-21: "Callout placement still jittery, not smooth"). Each move
    repaints all of where the preview was and is; the click puts the box
    down where it was drawn."""
    _marked_up(w, tmp_path)
    view = w.view
    w.select_tool("callout")
    pump()
    click(w, page(w, 300, 300))
    assert view._pending_anchor is not None
    start = screen(w, page(w, 330, 320))
    painted = _Regions(vp(w))
    drawn_before = None
    try:
        for i in range(90):
            painted.regions.clear()
            at = QPoint(start.x() + 2 * i, start.y() - i + (i % 3))     # a hand's wobble
            QTest.mouseMove(vp(w), at)
            QApplication.processEvents()
            pointer = view.mapToScene(at)
            preview = view._pending_callout()
            box = preview.mapRectToScene(preview.local_rect())
            assert abs(box.left() - pointer.x()) < 0.01 \
                and abs(box.center().y() - pointer.y()) < 0.01, \
                f"move {i}: the box is off the pointer by {box.left() - pointer.x():.1f}, " \
                f"{box.center().y() - pointer.y():.1f}"
            assert view._snap_marker is None and not view._snap_guides, \
                f"move {i}: the words were caught by {view._snap_caught}"
            drawn = [view.mapFromScene(piece).boundingRect()
                     for piece in view._callout_pieces(preview)]
            if drawn_before is not None and drawn != drawn_before:
                covered = QRegion()
                for region in painted.regions:
                    covered += region
                need = QRegion()
                for rect in drawn + drawn_before:
                    if (rect in drawn) != (rect in drawn_before):     # (the rest stays)
                        need += rect.adjusted(1, 1, -1, -1)
                missing = need.intersected(QRegion(vp(w).rect())).subtracted(covered)
                assert missing.isEmpty(), \
                    f"move {i}: the repaint missed {missing.boundingRect()} of the preview"
            drawn_before = drawn
    finally:
        painted.viewport.removeEventFilter(painted)
    side = preview.side()
    QTest.mouseClick(vp(w), Qt.LeftButton, Qt.NoModifier, at)
    pump()
    placed = view.editing_item()
    assert isinstance(placed, CalloutItem)
    lands = placed.mapRectToScene(placed.local_rect())
    assert abs(lands.left() - box.left()) < 0.01 and abs(lands.top() - box.top()) < 0.01, \
        "the box jumped as the click put it down"
    assert placed.side() == side
    assert _held(w) == _as_drawn_afresh(w), "the preview left a piece of itself behind"
    key(w, Qt.Key_Escape)


def test_the_words_go_on_the_grid_when_it_is_snapped_to(w):
    """With the grid snapped to, the box steps from one grid point to the
    next as it follows the pointer — and lands on the one it showed."""
    from calcforge.ui.calcedit import GRID_PT

    w.document.settings.snap_to_grid = True
    view = w.view
    w.select_tool("callout")
    pump()
    click(w, page(w, 200, 300))
    frame = w.document.pages[0].frame
    for x in (331, 333, 338, 341):
        move(w, page(w, x, 207))
        pump()
        box = frame.mapRectFromScene(view._pending_callout().mapRectToScene(
            view._pending_callout().local_rect()))
        for value in (box.left(), box.center().y()):
            assert abs(value / GRID_PT - round(value / GRID_PT)) < 1e-6, \
                f"the box at {box.left()}, {box.center().y()} is off the grid"
    shown = view._pending_callout().mapRectToScene(view._pending_callout().local_rect())
    click(w, page(w, 341, 207))
    placed = view.editing_item()
    lands = placed.mapRectToScene(placed.local_rect())
    assert abs(lands.left() - shown.left()) < 0.01 and abs(lands.top() - shown.top()) < 0.01
    key(w, Qt.Key_Escape)


def test_the_leader_holds_its_side_near_the_diagonal(w):
    """Where two sides of the box face what the leader points at about as
    squarely, the leader keeps leaving by the side it was leaving by as the
    pointer wavers — the hinge used to jump across the box and back at every
    pixel — and moves over once another side is clearly better. The callout
    lands with the side it was drawn with."""
    view = w.view
    width, height = view.WORDS_SIZE
    w.select_tool("callout")
    pump()
    aim = QPointF(300, 400)
    click(w, page(w, aim.x(), aim.y()))

    def at(across: float, down: float) -> QPointF:
        # the pointer where the aim is *across* half-widths left of the box's
        # middle and *down* half-heights below it
        return QPointF(aim.x() - width / 2 + across * width / 2, aim.y() - down * height / 2)

    def side_after(point: QPointF) -> str:
        move(w, page(w, point.x(), point.y()))
        pump()
        return view._pending_callout().side()

    assert side_after(at(3.0, 1.5)) == "left"
    sides = [side_after(at(2.0 + (0.08 if i % 2 else -0.08), 2.0)) for i in range(24)]
    flips = sum(1 for a, b in zip(sides, sides[1:]) if a != b)
    assert flips == 0, f"the leader flipped sides {flips} times: {sides}"
    assert side_after(at(1.5, 3.0)) == "bottom", "a clearly better side is taken"
    sides = [side_after(at(2.0 + (0.08 if i % 2 else -0.08), 2.0)) for i in range(24)]
    assert set(sides) == {"bottom"}, f"the leader flipped back: {sides}"
    shown = view._pending_callout().mapToScene(view._pending_callout().elbow())
    point = at(2.08, 2.0)
    click(w, page(w, point.x(), point.y()))
    placed = view.editing_item()
    assert placed.side() == "bottom" and placed.mapToScene(placed.elbow()) == shown, \
        "the leader landed on another side than the one it was drawn on"
    key(w, Qt.Key_Escape)


def test_snapping_finds_a_markup_where_it_is_now(w):
    """What the pointer snaps to is read once while nothing on the page
    changes — and afresh once something has: a markup moved or resized is
    caught where it is, not where it was."""
    from calcforge.items.shapes import RectItem

    w.document.settings.snap_to_items = True
    w.select_tool("rect")
    drag(w, page(w, 140, 140), page(w, 260, 220))
    w.select_tool("select")
    (box,) = markups(w, RectItem)
    view = w.view
    corner = box.mapToScene(box.local_rect().normalized().topRight())
    assert view.snap_to_item(corner + QPointF(1, 1)) is not None
    box.setPos(box.pos() + QPointF(120, 60))
    moved = box.mapToScene(box.local_rect().normalized().topRight())
    caught = view.snap_to_item(moved + QPointF(1, 1))
    assert caught is not None and abs(caught.x() - moved.x()) < 0.01 \
        and abs(caught.y() - moved.y()) < 0.01, "the moved rectangle was not caught"
    # widened by its handle, as the user would
    view.scene().clearSelection()
    box.setSelected(True)
    pump()
    handle = box.mapToScene(box.local_rect().normalized().bottomRight())
    drag(w, handle, handle + QPointF(80, 0))
    wider = box.mapToScene(box.local_rect().normalized().topRight())
    assert wider.x() > moved.x() + 60, "the rectangle was widened"
    caught = view.snap_to_item(wider + QPointF(1, 1))
    assert caught is not None and abs(caught.x() - wider.x()) < 0.01, \
        "the widened rectangle was caught where its corner was"


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


def _held_of(window, widget):
    """*widget* as the window holds it, as last painted."""
    from tests.test_big_pdf_smooth import _shown
    return _shown(window, widget)


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


# -- frames at the screen's rate -----------------------------------------------------

#: how often a mouse reports, as many do on Windows (and how a gaming one does)
MOUSE_RATE = 1000.0


def _moved_as_windows_moves(w, start: QPoint, seconds: float, held=Qt.NoButton) -> int:
    """The pointer moving at an even speed, as Windows hands it over: the
    latest place each time the last move has been dealt with, and anything
    posted — the window's repaint among it — only once no move is waiting.
    How many moves were handed over."""
    from PySide6.QtGui import QMouseEvent

    viewport = vp(w)
    app = QApplication.instance()
    began = time.perf_counter()
    due, moves = 0.0, 0
    while True:
        now = time.perf_counter() - began
        if now > seconds:
            return moves
        if now >= due:
            at = QPointF(start.x() + int(300 * now), start.y() - int(120 * now))
            QApplication.sendEvent(viewport, QMouseEvent(
                QEvent.MouseMove, at, viewport.mapToGlobal(at), Qt.NoButton, held,
                Qt.NoModifier))
            moves += 1
            due = max(due + 1.0 / MOUSE_RATE, time.perf_counter() - began - 1.0 / MOUSE_RATE)
            if time.perf_counter() - began >= due:
                continue                      # the mouse has moved again meanwhile
        app.processEvents()


def _pacing(w, gesture: str, tmp_path) -> dict:
    """The frames the window put on the screen while the box of a call-out
    being placed followed the pointer, or a placed markup was dragged."""
    from calcforge.items.shapes import RectItem

    _marked_up(w, tmp_path)
    view = w.view
    # as on Windows, where it is needed (PageView.paces_its_frames)
    view.paces_its_frames = True
    if gesture == "callout":
        w.select_tool("callout")
        pump()
        click(w, page(w, 300, 300))
        start, held = screen(w, page(w, 330, 320)), Qt.NoButton
    else:
        w.select_tool("rect")
        drag(w, page(w, 250, 250), page(w, 350, 310))
        w.select_tool("select")
        pump()
        box = [item for item in w.document.pages[0].frame.markups()
               if isinstance(item, RectItem)][-1]           # the one just drawn
        rect = box.local_rect().normalized()
        edge = box.mapToScene(QPointF(rect.left() + rect.width() * 0.3, rect.top()))
        QTest.mousePress(vp(w), Qt.LeftButton, Qt.NoModifier, screen(w, edge))
        start, held = screen(w, edge), Qt.LeftButton
    _quiet(w, repaint=False)
    seen = _Seen(w, [vp(w)])
    times: list = []

    class _When(QObject):
        def eventFilter(self, watched, event):
            if watched is vp(w) and event.type() == QEvent.Paint:
                times.append(time.perf_counter())
            return False
    when = _When()
    vp(w).installEventFilter(when)
    try:
        moves = _moved_as_windows_moves(w, start, 1.2, held)
    finally:
        vp(w).removeEventFilter(when)
        seen.stop()
    if gesture == "drag":
        assert view._mode == "move", "the rectangle was being dragged"
        QTest.mouseRelease(vp(w), Qt.LeftButton, Qt.NoModifier, start)
    else:
        key(w, Qt.Key_Escape)
    gaps = [(b - a) * 1000.0 for a, b in zip(times, times[1:])]
    span = times[-1] - times[0] if len(times) > 1 else 1.0
    return {"moves": moves, "fps": (len(times) - 1) / span, "frames": seen.frames,
            "paints": len(times), "longest": max(gaps) if gaps else 1e9,
            "steady": sum(1 for gap in gaps if gap <= 17.0) / max(len(gaps), 1)}


def _keeps_pace(stats: dict, gesture: str, least_fps: float, steady: float,
                longest: float) -> None:
    assert stats["moves"] > 100, f"{gesture}: only {stats['moves']} moves handed over"
    assert stats["fps"] >= least_fps and stats["steady"] >= steady \
        and stats["longest"] <= longest, (
            f"{gesture}: {stats['fps']:.0f} frames a second, {stats['steady']:.0%} of them "
            f"within 17 ms, the longest wait {stats['longest']:.0f} ms")
    # every frame put on the screen has the canvas in it: a frame of
    # something else between two of the canvas's was one more wait for the
    # screen — half the frames
    assert stats["frames"] <= stats["paints"] + 2, (
        f"{gesture}: {stats['frames']} frames to the screen for {stats['paints']} "
        f"of the canvas")


@pytest.mark.parametrize("gesture", ["callout", "drag"])
def test_frames_keep_the_screens_pace(w, tmp_path, gesture):
    """While a call-out's box follows the pointer to where its words go, and
    while a placed markup is dragged, frames go to the screen at its rate as
    the mouse reports a thousand times a second — not only when the mouse
    pauses, as when every report was dealt with before the repaint Qt had
    posted (the user, 2026-10-21: "just moving the box around is not buttery
    smooth, it's like the fps is lowered")."""
    _keeps_pace(_pacing(w, gesture, tmp_path), gesture, least_fps=50.0, steady=0.85,
                longest=40.0)


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
        _quiet(w, repaint=False)             # (what the page does once idle, done)
        drawn.clear()
        seen = _Seen(w, [vp(w)])
        when = []
        try:
            for i in range(20):
                when.append(time.perf_counter())
                move(w, QPointF(start.x() + 10 * i, start.y() - 6 * i))
                pump()
                time.sleep(0.012)
        finally:
            seen.stop()
        # a pause longer than the status bar's 30 ms between two moves (a
        # loaded machine) has the pointer's last place written when the
        # pointer has stopped, as it should be: a frame of its own then
        stopped = sum(1 for a, b in zip(when, when[1:]) if b - a > 0.03)
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
    # one frame to the screen for each move: a frame of its own for the
    # pointer's place in the status bar, between the canvas's, was one more
    # wait for the card's next refresh
    assert seen.frames <= 20 + 1 + stopped, (
        f"{seen.frames} frames for 20 moves of the pointer ({stopped} pauses)")
    assert typing and max(typing) < 0.5, f"a key typed drew {typing}"
    assert (shown == fresh).all(), "the card left something of an earlier frame"



@pytest.mark.skipif(not os.environ.get(CARD), reason="run in its own process, on the card")
@pytest.mark.parametrize("gesture", ["callout", "drag"])
def test_frames_keep_pace_on_the_card(w, tmp_path, gesture):
    """The same on the card. Drawn here by a processor pretending to be one
    (every frame of the whole window takes it 12-20 ms), so the budget is
    what that allows: a frame for every one it can draw, none of them a frame
    without the canvas, none of them waiting long."""
    assert w.view.gpu, "drawing with the graphics card"
    _keeps_pace(_pacing(w, gesture, tmp_path), gesture, least_fps=35.0, steady=0.0,
                longest=70.0)


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
         "-k", "test_on_the_card or test_frames_keep_pace_on_the_card"],
        env=env, capture_output=True, text=True, timeout=600,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    tail = "\n".join(line for line in done.stdout.splitlines()
                     if "PASSED" in line or "FAILED" in line or "Error" in line
                     or "assert" in line)
    assert done.returncode == 0, tail
    assert done.stdout.count("PASSED ") == 3, tail


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
