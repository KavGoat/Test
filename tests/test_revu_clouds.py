"""Clouds drawn as Revu draws them, leaders that end on them, and Add Cloud
Leader drawn by hand (the user, 2026-10-20, on Windows against Revu 21:
"Cloud no longer looks like Bluebeam, in Cloud or Callout." "The cloud leader
has issues where the line leader terminates inside the cloud, not on the
edge." "Adding a cloud leader to an existing callout still placed a pre-sized
box instead of letting me size it by hand.").

Revu's revision cloud is a run of equal arcs along each side, standing on the
side and bulging outward, neighbours meeting in a sharp cusp on the outline
that points in; the first arc of a side starts at its corner and the last
ends at the next. Since 2026-10-14 the scallops had been a PDF reader's
cloudy border (PDFBox's, after Acrobat): shallow curls centred on the
outline, their cusps out beyond it — a flatter cloud, drawn round an outline
inside it, so a leader ended at the region's corner ended inside the cloud.
"""
from __future__ import annotations

import math

import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainterPath, QPolygonF

from calcforge.items.base import (CLOUD_SWEEP, cloud_arcs_for, cloud_path,
                                  cloud_radius_for)
from calcforge.items.shapes import RectItem
from calcforge.items.text import CalloutItem
from tests.test_markup_interaction_round6 import (click, drag, key, markups, move,
                                                  page, pump)
from tests.test_usability import double_click


def _box(rect: QRectF) -> QPolygonF:
    return QPolygonF([rect.topLeft(), rect.topRight(), rect.bottomRight(),
                      rect.bottomLeft()])


def _cusps(path: QPainterPath) -> list:
    """Where one scallop meets the next: the end of every second piece."""
    points = [QPointF(path.elementAt(0).x, path.elementAt(0).y)]
    for i in range(path.elementCount()):
        if path.elementAt(i).type == QPainterPath.CurveToElement:
            end = path.elementAt(i + 2)
            points.append(QPointF(end.x, end.y))
    return points[::2]


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


# -- the cloud's shape -------------------------------------------------------

@pytest.mark.parametrize("size, width", [(2.0, 1.0), (1.0, 1.0), (3.0, 2.0), (2.0, 4.0),
                                         (0.5, 0.5)])
@pytest.mark.parametrize("rect", [QRectF(0, 0, 160, 90), QRectF(0, 0, 97, 61),
                                  QRectF(0, 0, 300, 24)])
def test_scallops_stand_on_each_side_corner_to_corner(rect, size, width):
    """Arcs per side as the Size and line width make them, equal along each
    side, a cusp at every corner and between neighbours on the outline,
    each arc bulging outward and no further than the scallop radius."""
    radius = cloud_radius_for(size, width)
    polygon = _box(rect)
    path = cloud_path(polygon, radius)
    cusps = _cusps(path)
    expected = 2 * (cloud_arcs_for(rect.width(), radius)
                    + cloud_arcs_for(rect.height(), radius))
    assert len(cusps) == expected + 1, "one cusp after each arc, back to the first"
    assert (cusps[0] - cusps[-1]).manhattanLength() < 1e-6, "it closes where it began"
    for cusp in cusps:
        assert _distance_to_polygon_edge(cusp, polygon) < 1e-6, \
            "every cusp is on the outline, pointing in"
    for corner in polygon:
        assert min((cusp - corner).manhattanLength() for cusp in cusps) < 1e-6, \
            "each corner is a cusp: arcs start and end neatly there"
    # along each side the arcs are the same, and none is a sliver
    for length in (rect.width(), rect.height()):
        arcs = cloud_arcs_for(length, radius)
        chord = length / arcs
        assert chord <= 2 * radius * math.sin(CLOUD_SWEEP / 2) * 1.15 + 1e-9
        assert arcs == 1 or chord >= 2 * radius * math.sin(CLOUD_SWEEP / 2) * 0.5
    gaps = sorted(round(math.hypot(b.x() - a.x(), b.y() - a.y()), 6)
                  for a, b in zip(cusps, cusps[1:]))
    assert set(gaps) <= {round(rect.width() / cloud_arcs_for(rect.width(), radius), 6),
                         round(rect.height() / cloud_arcs_for(rect.height(), radius), 6)}
    # outward, and the arcs' height is the Size's
    bounds = path.boundingRect()
    assert bounds.contains(rect)
    reach = max(rect.top() - bounds.top(), bounds.bottom() - rect.bottom(),
                rect.left() - bounds.left(), bounds.right() - rect.right())
    assert 0.5 * radius < reach <= radius + 1e-6


def test_a_polygon_clouds_scallops_start_at_each_corner():
    corners = [QPointF(0, 0), QPointF(150, 10), QPointF(120, 100), QPointF(20, 80)]
    polygon = QPolygonF(corners)
    radius = cloud_radius_for(2.0, 1.0)
    cusps = _cusps(cloud_path(polygon, radius))
    for corner in corners:
        assert min((cusp - corner).manhattanLength() for cusp in cusps) < 1e-6
    for cusp in cusps:
        assert _distance_to_polygon_edge(cusp, polygon) < 1e-6
    sides = sum(cloud_arcs_for(math.hypot(b.x() - a.x(), b.y() - a.y()), radius)
                for a, b in zip(corners, corners[1:] + corners[:1]))
    assert len(cusps) == sides + 1


def test_invert_turns_the_arcs_inward_on_the_same_cusps():
    rect = QRectF(0, 0, 120, 80)
    out = cloud_path(_box(rect), 10.0)
    inward = cloud_path(_box(rect), 10.0, inverted=True)
    assert out.boundingRect().contains(rect)
    assert rect.adjusted(-1e-6, -1e-6, 1e-6, 1e-6).contains(inward.boundingRect())
    def spots(path):
        return sorted({(round(p.x(), 4) + 0.0, round(p.y(), 4) + 0.0) for p in _cusps(path)})
    assert spots(out) == spots(inward)


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
