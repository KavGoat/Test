"""Clouds drawn as Revu's look, leaders that end on them, and Add Cloud Leader
drawn by hand (the user, 2026-10-20, on Windows against Revu 21: "Cloud no
longer looks like Bluebeam, in Cloud or Callout." "The cloud leader has
issues where the line leader terminates inside the cloud, not on the edge."
"Adding a cloud leader to an existing callout still placed a pre-sized box
instead of letting me size it by hand."; 2026-10-21, shown the clouds
CalcForge has drawn: "B with the corners are better than that").

B is fe32d28's cloud (14 Oct), a PDF reader's cloudy border (PDFBox's, after
Acrobat): circles of the Size's radius centred on the outline, about 1.66
radii apart, each scallop tucking its start behind the one before. Its
corners and the join where it closed were untidy — a corner curl begun
backwards and eased first scallops left tails crossing there. Now a scallop
is centred on every corner, the rest are spread evenly along each side, and
every scallop, the first and last included, is drawn by the same rule.
"""
from __future__ import annotations

import math

import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainterPath, QPolygonF

from calcforge.items.base import (CLOUD_PITCH, CLOUD_TAIL, _cloud_arcs, cloud_path,
                                  cloud_radius_for, cloud_steps)
from calcforge.items.shapes import RectItem
from calcforge.items.text import CalloutItem
from tests.test_markup_interaction_round6 import (click, drag, key, markups, move,
                                                  page, pump)
from tests.test_usability import double_click


def _box(rect: QRectF) -> QPolygonF:
    return QPolygonF([rect.topLeft(), rect.topRight(), rect.bottomRight(),
                      rect.bottomLeft()])


def _poly(*points) -> QPolygonF:
    return QPolygonF([QPointF(x, y) for x, y in points])


def _distance_to_polygon_edge(point: QPointF, polygon: QPolygonF) -> float:
    best = math.inf
    for i in range(len(polygon)):
        a, b = polygon[i], polygon[(i + 1) % len(polygon)]
        dx, dy = b.x() - a.x(), b.y() - a.y()
        if dx * dx + dy * dy < 1e-18:
            continue
        t = max(0.0, min(1.0, ((point.x() - a.x()) * dx + (point.y() - a.y()) * dy)
                         / (dx * dx + dy * dy)))
        best = min(best, math.hypot(point.x() - a.x() - t * dx, point.y() - a.y() - t * dy))
    return best


def _distance_to_path(point: QPointF, path: QPainterPath) -> float:
    best = math.inf
    for ring in path.toSubpathPolygons():
        best = min(best, _distance_to_polygon_edge(point, ring))
    return best


def _on_screen(x, y) -> QPointF:
    """A point worked out y up, as the cloud is, back on the page."""
    return QPointF(x, -y)


def _outline(arcs, steps=24) -> list:
    """The visible line round the cloud, scallop by scallop from cusp to
    cusp: a list of each scallop's points."""
    scallops = []
    for cx, cy, rho, start, sweep, _tail in arcs:
        scallops.append([_on_screen(cx + rho * math.cos(start + sweep * k / steps),
                                    cy + rho * math.sin(start + sweep * k / steps))
                         for k in range(steps + 1)])
    return scallops


def _crosses(a, b, c, d) -> bool:
    def side(p, q, r):
        return (q.x() - p.x()) * (r.y() - p.y()) - (q.y() - p.y()) * (r.x() - p.x())
    return (side(a, b, c) * side(a, b, d) < -1e-9) and (side(c, d, a) * side(c, d, b) < -1e-9)


def _simple(scallops, reach, near=8) -> bool:
    """Whether no scallop's line crosses another's within *near* of it
    round the cloud (further off, only a cloud too narrow for its scallops
    could), but where neighbours meet in their cusp."""
    count = len(scallops)
    for i in range(count):
        for k in range(1, min(near, count - 1) + 1):
            j = (i + k) % count
            first, other = scallops[i], scallops[j]
            if (first[len(first) // 2] - other[len(other) // 2]).manhattanLength() > 6 * reach:
                continue                          # too far apart to meet
            for m in range(len(first) - 1):
                for n in range(len(other) - 1):
                    if k == 1 and m == len(first) - 2 and n == 0:
                        continue                  # their shared cusp
                    if k == count - 1 and m == 0 and n == len(other) - 2:
                        continue
                    if _crosses(first[m], first[m + 1], other[n], other[n + 1]):
                        return False
    return True


SIZES = [(1.0, 1.0), (2.0, 1.0), (2.0, 2.0), (3.0, 2.0), (2.0, 4.0), (3.0, 4.0)]
RECTS = [QRectF(0, 0, 160, 90), QRectF(0, 0, 97, 61), QRectF(0, 0, 300, 24),
         QRectF(0, 0, 40, 220), QRectF(0, 0, 18, 14), QRectF(0, 0, 900, 600)]
POLYGONS = {
    "quad": _poly((0, 0), (150, 10), (120, 100), (20, 80)),
    "sharp 30°": _poly((0, 0), (160, 0), (160 - 160 * math.cos(math.radians(30)),
                                           160 * math.sin(math.radians(30)))),
    "obtuse": _poly((0, 0), (120, -30), (240, 0), (240, 90), (0, 90)),
    "notched": _poly((0, 0), (120, -20), (110, 100), (60, 50), (10, 100)),
}


def _shapes():
    for rect in RECTS:
        yield f"rect {rect.width():g}x{rect.height():g}", _box(rect)
    yield from POLYGONS.items()


# -- the cloud's shape -------------------------------------------------------

@pytest.mark.parametrize("size, width", SIZES)
@pytest.mark.parametrize("rect", RECTS, ids=lambda r: f"{r.width():g}x{r.height():g}")
def test_a_scallop_on_every_corner_and_the_rest_even(rect, size, width):
    """B's scallops — the Size's radius, about 1.66 radii apart — centred on
    each corner and spread evenly along each side, all the same on a side."""
    radius = cloud_radius_for(size, width)
    arcs = _cloud_arcs(_box(rect), radius)
    centres = [_on_screen(cx, cy) for cx, cy, *_rest in arcs]
    assert all(rho == radius for _x, _y, rho, *_rest in arcs), "B's size"
    for corner in _box(rect):
        assert min((c - corner).manhattanLength() for c in centres) < 1e-6, \
            "a scallop centred on the corner"
    expected = 2 * (cloud_steps(rect.width(), radius) + cloud_steps(rect.height(), radius))
    assert len(centres) == expected
    gaps = {round(math.hypot(b.x() - a.x(), b.y() - a.y()), 6)
            for a, b in zip(centres, centres[1:] + centres[:1])}
    assert gaps <= {round(rect.width() / cloud_steps(rect.width(), radius), 6),
                    round(rect.height() / cloud_steps(rect.height(), radius), 6)}, \
        "every side's scallops equal"
    for gap in gaps:
        assert gap < 2 * radius, "neighbours' circles cross"
    long_side = max(rect.width(), rect.height())
    if long_side > 6 * CLOUD_PITCH * radius:
        spacing = long_side / cloud_steps(long_side, radius)
        assert spacing == pytest.approx(CLOUD_PITCH * radius, rel=0.12), "B's spacing"


@pytest.mark.parametrize("size, width", SIZES)
@pytest.mark.parametrize("name, polygon", list(_shapes()), ids=[n for n, _ in _shapes()])
@pytest.mark.parametrize("inverted", [False, True], ids=["out", "inverted"])
def test_the_outline_is_clean_at_corners_and_where_it_closes(name, polygon, size, width,
                                                             inverted):
    """No tail or spur crossing out of the cloud, no scallop crossing
    another, nothing further out than a scallop, and the outline closes on a
    cusp like every other."""
    radius = cloud_radius_for(size, width)
    bounds = polygon.boundingRect()
    if inverted and min(bounds.width(), bounds.height()) < 2.5 * radius:
        pytest.skip("turned inward, scallops from facing sides meet across a cloud "
                    "narrower than they are")
    arcs = _cloud_arcs(polygon, radius, inverted=inverted)
    assert len(arcs) >= 3
    outline = _outline(arcs)
    assert _simple(outline, radius), "the outline never crosses itself"
    for cx, cy, rho, start, sweep, tail in arcs:
        assert sweep > 0
        assert 0 <= tail <= CLOUD_TAIL + 1e-9, "B's tail, no longer"
    # every tail tucked inside the scallop before it: hidden, never a spur
    for (px, py, prho, *_p), (cx, cy, rho, start, _sweep, tail) in zip(
            arcs[-1:] + arcs[:-1], arcs):
        for k in range(1, 9 if tail > 0 else 1):
            angle = start - tail * k / 8
            x, y = cx + rho * math.cos(angle), cy + rho * math.sin(angle)
            assert math.hypot(x - px, y - py) < prho, "the tail is behind its neighbour"
    # nothing further out than a scallop from the outline
    path = cloud_path(polygon, radius, inverted=inverted)
    for ring in path.toSubpathPolygons():
        for point in ring:
            assert _distance_to_polygon_edge(point, polygon) <= radius + 0.05
    # it closes where it began, on a cusp: the last scallop's end
    first = QPointF(path.elementAt(0).x, path.elementAt(0).y)
    last = path.elementAt(path.elementCount() - 1)
    assert (first - QPointF(last.x, last.y)).manhattanLength() < 1e-6
    cx, cy, rho, start, sweep, _tail = arcs[-1]
    end = _on_screen(cx + rho * math.cos(start + sweep), cy + rho * math.sin(start + sweep))
    assert (end - first).manhattanLength() < 1e-6, "the closing join is a cusp"
    # and that cusp is where both its scallops' circles cross, as every cusp is
    (ax, ay, *_a), (bx, by, *_b) = arcs[-1], arcs[0]
    for x, y in ((ax, ay), (bx, by)):
        assert math.hypot(first.x() - x, -first.y() - y) == pytest.approx(radius)


def test_invert_turns_the_scallops_inward_round_the_same_outline():
    rect = QRectF(0, 0, 120, 80)
    out = cloud_path(_box(rect), 10.0)
    inward = cloud_path(_box(rect), 10.0, inverted=True)
    assert out.boundingRect().contains(rect)
    assert rect.adjusted(-1e-6, -1e-6, 1e-6, 1e-6).contains(inward.boundingRect())


def test_a_drawn_cloud_is_stroked_with_round_joins_at_its_line_width(window):
    """The cusps have round joins, on screen and in the PDF alike, and the
    line is the cloud's own width."""
    from PySide6.QtGui import QImage, QPainter

    cloud = RectItem("cloud", QRectF(0, 0, 100, 60))
    cloud.style.width = 3.0
    seen = {}

    class Recorder(QPainter):
        def drawPath(self, path):
            seen["join"] = self.pen().joinStyle()
            seen["width"] = self.pen().widthF()
            super().drawPath(path)

    image = QImage(200, 200, QImage.Format_ARGB32)
    painter = Recorder(image)
    cloud.paint_content(painter)
    painter.end()
    assert seen == {"join": Qt.RoundJoin, "width": 3.0}


# -- the leader ends on the cloud --------------------------------------------

REGIONS = {
    "right": QRectF(160, -10, 110, 70),
    "left": QRectF(-200, -20, 120, 80),
    "below": QRectF(-30, 110, 150, 70),
    "above": QRectF(10, -150, 90, 80),
    "below right": QRectF(170, 90, 80, 90),
    "above left": QRectF(-170, -140, 100, 70),
}


@pytest.mark.parametrize("where", sorted(REGIONS))
@pytest.mark.parametrize("size, width", [(2.0, 1.0), (3.0, 2.5)])
def test_a_cloud_leader_ends_on_the_clouds_edge(where, size, width):
    call = CalloutItem("Note", QRectF(0, 0, 100, 40))
    call.leaders = []
    call.cloud_size = size
    call.style.width = width
    leader = call.add_cloud_leader(list(_box(REGIONS[where])))
    cloud = cloud_path(QPolygonF(list(leader.cloud)), call.cloud_radius)
    tip, elbow = call.tip_of(leader), call.elbow_of(leader)
    assert _distance_to_path(tip, cloud) <= width / 2, "the end is on the drawn cloud"
    # and nothing of the line before it is inside the cloud
    length = math.hypot(tip.x() - elbow.x(), tip.y() - elbow.y())
    for step in range(40):
        t = step / 40 * max(length - width / 2, 0.0) / max(length, 1e-9)
        point = QPointF(elbow.x() + (tip.x() - elbow.x()) * t,
                        elbow.y() + (tip.y() - elbow.y()) * t)
        assert not cloud.contains(point), "the line never runs inside the cloud"
    assert call.cloud_join() == tip


def test_the_callout_line_written_to_the_pdf_ends_on_the_cloud(window, tmp_path):
    from pypdf import PdfReader

    from calcforge.io import export as export_io

    call = CalloutItem("Note", QRectF(0, 0, 100, 40))
    call.leaders = []
    leader = call.add_cloud_leader(list(_box(QRectF(180, 70, 120, 70))))
    frame = window.document.pages[0].frame
    frame.add_markup(call, QPointF(100, 100))
    tip = call.mapToParent(call.tip_of(leader))
    path = str(tmp_path / "leader.pdf")
    export_io.export_pdf(window.document, path)
    pdf_page = PdfReader(path).pages[0]
    (note,) = [entry.get_object() for entry in pdf_page["/Annots"]
               if str(entry.get_object().get("/IT", "")) == "/FreeTextCallout"]
    line = [float(v) for v in note["/CL"]]
    height = float(pdf_page.mediabox.height)
    assert line[0] == pytest.approx(tip.x(), abs=0.6)
    assert height - line[1] == pytest.approx(tip.y(), abs=0.6)
    cloud = cloud_path(QPolygonF([call.mapToParent(p) for p in leader.cloud]),
                       call.cloud_radius)
    assert _distance_to_path(QPointF(line[0], height - line[1]), cloud) <= 0.6


# -- Add Cloud Leader, drawn by hand -----------------------------------------

@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.view.set_zoom(1.0)
    pump()
    return window


def _a_callout(w):
    """A call-out with its arrow, placed with the Callout tool."""
    w.select_tool("callout")
    move(w, page(w, 120, 120))
    click(w, page(w, 120, 120))
    move(w, page(w, 260, 90))
    click(w, page(w, 260, 90))
    key(w, Qt.Key_Escape)
    (callout,) = markups(w, CalloutItem)
    return callout


def _choose_add_cloud_leader(w, callout):
    at = callout.mapToScene(callout.local_rect().center())
    menu = w.build_context_menu(callout, at)
    (action,) = [a for a in menu.actions() if a.text() == "Add Cloud Leader"]
    action.trigger()
    pump()


def _clouds(callout) -> list:
    frame = callout.parentItem()
    return [[frame.mapFromItem(callout, p) for p in leader.cloud]
            for leader in callout.leaders if leader.clouds()]


def test_add_cloud_leader_is_dragged_to_size(w):
    callout = _a_callout(w)
    steps = w.undo_stack.count()
    _choose_add_cloud_leader(w, callout)
    assert not _clouds(callout), "nothing is put down before the drag"
    assert w.view._cloud_leader_preview() is None, "no cloud of a size of its own"
    drag(w, page(w, 330, 220), page(w, 470, 300))
    (callout,) = markups(w, CalloutItem)
    (corners,) = _clouds(callout)
    box = QPolygonF(corners).boundingRect()
    assert (box.left(), box.top(), box.width(), box.height()) == pytest.approx(
        (330, 220, 140, 80), abs=1.5), "the cloud is the rectangle dragged"
    assert len(callout.leaders) == 2, "joined to the note beside its arrow"
    assert w.undo_stack.count() == steps + 1, "one undo step"
    assert w.view.tool_key == "select"
    assert not [i for i in markups(w) if getattr(i, "kind", "") == "cloud"], \
        "the cloud is the leader's, not a Cloud markup of its own"
    w.undo_stack.undo()
    pump()
    (callout,) = markups(w, CalloutItem)
    assert not _clouds(callout)


def test_add_cloud_leader_clicked_corner_by_corner(w):
    callout = _a_callout(w)
    _choose_add_cloud_leader(w, callout)
    # clear of the note's own edges, which a corner would snap to
    corners = [(320, 220), (470, 230), (455, 335), (375, 312)]
    for x, y in corners:
        move(w, page(w, x, y))
        click(w, page(w, x, y))
    assert w.view._mode == "draw_poly", "a click, not a drag, starts a free-form cloud"
    assert not _clouds(callout), "and no box of a size of its own"
    x, y = 305, 270
    corners.append((x, y))
    move(w, page(w, x, y))
    at = page(w, x, y)
    double_click(w.view, at.x(), at.y())
    pump()
    (callout,) = markups(w, CalloutItem)
    (drawn,) = _clouds(callout)
    assert len(drawn) == len(corners)
    for point, (x, y) in zip(drawn, corners):
        assert (point.x(), point.y()) == pytest.approx((x, y), abs=1.5)


def test_escape_puts_add_cloud_leader_down_with_nothing_changed(w):
    callout = _a_callout(w)
    steps = w.undo_stack.count()
    before = callout.serialize()
    _choose_add_cloud_leader(w, callout)
    for x, y in ((330, 220), (470, 230)):
        move(w, page(w, x, y))
        click(w, page(w, x, y))
    key(w, Qt.Key_Escape)
    assert w.view._pending_cloud_leader is None and w.view._draft is None
    assert w.view.tool_key == "select"
    (callout,) = markups(w, CalloutItem)
    assert callout.serialize()["leaders"] == before["leaders"]
    assert w.undo_stack.count() == steps
    assert len(markups(w)) == 1
    # and a drag after it is a plain selection, not a cloud
    drag(w, page(w, 330, 220), page(w, 470, 300))
    (callout,) = markups(w, CalloutItem)
    assert not _clouds(callout)


def test_an_added_cloud_leader_is_saved_and_exported(w, tmp_path):
    from pypdf import PdfReader

    from calcforge.io import export as export_io
    from tests.test_propbar_gaps import save_and_reopen

    callout = _a_callout(w)
    _choose_add_cloud_leader(w, callout)
    drag(w, page(w, 330, 220), page(w, 470, 300))
    (callout,) = markups(w, CalloutItem)
    corners = [[(round(p.x()), round(p.y())) for p in c] for c in _clouds(callout)]
    save_and_reopen(w, tmp_path)
    (reopened,) = markups(w, CalloutItem)
    assert [[(round(p.x()), round(p.y())) for p in c] for c in _clouds(reopened)] == corners
    path = str(tmp_path / "exported.pdf")
    export_io.export_pdf(w.document, path)
    pdf_page = PdfReader(path).pages[0]
    (note,) = [entry.get_object() for entry in pdf_page["/Annots"]
               if str(entry.get_object().get("/IT", "")) == "/FreeTextCallout"]
    left, bottom, right, top = (float(v) for v in note["/Rect"])
    height = float(pdf_page.mediabox.height)
    assert right >= 470 and height - bottom >= 300, "its box takes in the cloud"
