"""The pointer over every handle and hover state on the canvas is Revu's.

The user, 2026-10-20: "Run a cursor check on all features, like how moving a
hinge on a leader has a weird cursor." What Revu shows, and so what each of
these must show:

- Revu's select arrow with a small move sign at its foot over anything a
  drag moves whole — a markup's body, a cloud leader's cloud, a measurement's
  words, a table's tab (the user's photos of Revu 21, 2026-10-20);
- the arrow with a copy sign while Ctrl is held over a markup: a click or a
  drag copies; with a "+", a "−" or an arc while Shift or Alt is held over a
  selected outline, for what the click does there;
- the size arrows over a resize handle, lying the way the handle pulls on
  the screen — turned with a turned markup;
- the point pointer (the thin crosshair) over a handle that moves one point:
  a polyline's or polygon's or cloud's corner, a line's end, an arc's bend, a
  measurement's end, a leader's arrow head and its hinge (callout, Cloud+,
  arrow leader, cloud leader), a Cloud+'s corners;
- Revu's curled arrow over a turning handle;
- the I-beam over words being typed; Excel's pointers over a table's cells,
  its headings and its edges, and over a sheet's print area and page breaks;
  WebSMath's over an equation;
- the open hand for the Hand tool, closed while it drags; each drawing tool
  its own crosshair; the no-entry sign over a locked markup.

Every hover here is a real QTest.mouseMove on the canvas's viewport.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from calcforge.items.base import POINT_CURSOR, rotate_cursor
from calcforge.items.shapes import RectItem
from calcforge.ui.tools import TOOLS
from calcforge.ui.cursors import ADD, BADGES, COPY, CURVE, MOVE, REMOVE, is_revu_cursor
from tests.probe_audit import make
from tests.test_markup_interaction_round6 import pump, screen, vp

ROTATE = "rotate"


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.view.set_zoom(1.0)
    pump()
    yield window
    for key in (Qt.Key_Shift, Qt.Key_Control):
        QTest.keyRelease(window.view, key)


def hover(w, point: QPointF) -> None:
    """The pointer to *point* (scene), by way of a pixel beside it."""
    at = screen(w, point)
    QTest.mouseMove(vp(w), at + type(at)(1, 1))
    QTest.mouseMove(vp(w), at)
    pump(1)


def shown(w):
    """What the canvas's pointer is: a Qt shape, or ROTATE / COPY / the
    cursor's own pixmap key for a drawn one."""
    cursor = vp(w).cursor()
    if cursor.shape() != Qt.BitmapCursor:
        return cursor.shape()
    key = cursor.pixmap().cacheKey()
    if key == rotate_cursor().pixmap().cacheKey():
        return ROTATE
    for badge in BADGES:
        if is_revu_cursor(cursor, badge):
            return badge
    return key


SIZE = {"nw": Qt.SizeFDiagCursor, "se": Qt.SizeFDiagCursor,
        "ne": Qt.SizeBDiagCursor, "sw": Qt.SizeBDiagCursor,
        "n": Qt.SizeVerCursor, "s": Qt.SizeVerCursor,
        "e": Qt.SizeHorCursor, "w": Qt.SizeHorCursor}


def revu(item, key: str):
    """The pointer Revu shows over *item*'s (upright) handle *key*."""
    if key in ("rot", "lblrot"):
        return ROTATE
    corner = key[len("scale_"):] if key.startswith("scale_") else key
    if corner in SIZE:
        return SIZE[corner]
    if key in ("lbl", "lbltext"):
        return MOVE                      # a measurement's words, moved whole
    if key[:1] == "l" and key[1:].isdigit():
        leader, _part = item.leader_at(key)
        if leader.clouds():
            return MOVE                  # a cloud leader's cloud travels whole
    if key[:1] == "b" and key[1:].isdigit():
        return MOVE                      # a break symbol, slid along its side
    return POINT_CURSOR                  # one point: a corner, an end, a hinge


def walk(w, item, label: str) -> list:
    """Hover each of *item*'s handles; what was wrong, as (where, got, wanted)."""
    w.select_tool("select")
    w.view.scene().clearSelection()
    item.setSelected(True)
    pump()
    wrong = []
    w.view.centerOn(item.mapToScene(item.local_rect().center()))
    pump()
    handles = list(item.handle_points().items()) + list(item.scale_points().items())
    assert handles, f"{label} has handles to walk"
    for key, local in handles:
        point = item.mapToScene(local)
        assert vp(w).rect().contains(screen(w, point)), f"{label} {key} is in view"
        hover(w, point)
        # where two handles meet, the nearer is the one under the pointer
        under = item.handle_at(item.mapFromScene(w.view.mapToScene(screen(w, point))))
        if under is None:
            continue
        got, wanted = shown(w), revu(item, under)
        if got != wanted:
            wrong.append((f"{label} {under}", got, wanted))
    return wrong


def body_of(item) -> QPointF:
    return item.mapToScene(item.local_rect().center())


# -- every handle of every kind of markup ------------------------------------------------

KINDS = ["rect", "ellipse", "polyline", "polygon", "cloud", "line", "arrow", "arc",
         "highlight", "text", "callout", "checkbox", "stamp", "measure_length",
         "measure_dimension", "measure_polylength", "measure_area", "measure_angle",
         "measure_radius", "sketch_rect"]


def test_every_handle_of_every_markup_has_revus_pointer(w):
    wrong = []
    for kind in KINDS:
        w.new_document()
        w.interactive_prompts = False
        w.view.set_zoom(1.0)
        pump()
        item = make(w, kind)
        assert item is not None, kind
        wrong += walk(w, item, kind)
    assert not wrong, "\n".join(f"{where}: {got} (wanted {wanted})"
                                for where, got, wanted in wrong)


def test_a_leaders_hinge_and_arrow_head_move_a_point(w):
    """Call-out, arrow leader, cloud leader and Cloud+: each arrow head and
    each hinge (the orange diamonds) is one point, and says so."""
    from calcforge.items.text import CalloutItem

    wrong = []
    # a call-out: what it points at, then its words
    call = make(w, "callout")
    wrong += walk(w, call, "callout")
    assert {"l0", "e0"} <= set(call.handle_points())
    hover(w, call.mapToScene(call.handle_points()["e0"]))
    assert shown(w) == POINT_CURSOR, "the hinge moves a point (the user's example)"

    # a text box given an arrow leader, then a cloud leader
    w.new_document()
    w.interactive_prompts = False
    box = make(w, "text")
    w.view.begin_arrow_leader(box)
    target = box.mapToScene(box.local_rect().bottomLeft()) + QPointF(-80, 120)
    hover(w, target)
    QTest.mouseClick(vp(w), Qt.LeftButton, Qt.NoModifier, screen(w, target))
    pump()
    # given a leader, the text box is a call-out: the same markup, its new state
    box = next(i for i in w.view.scene().ordered_markups() if isinstance(i, CalloutItem))
    assert len(box.leaders) == 1
    w.view.begin_cloud_leader(box)
    a = box.mapToScene(box.local_rect().topRight()) + QPointF(120, -40)
    QTest.mousePress(vp(w), Qt.LeftButton, Qt.NoModifier, screen(w, a))
    for step in (0.3, 0.6, 1.0):
        hover(w, a + QPointF(90 * step, 60 * step))
    QTest.mouseRelease(vp(w), Qt.LeftButton, Qt.NoModifier, screen(w, a + QPointF(90, 60)))
    pump()
    box = next(i for i in w.view.scene().ordered_markups() if isinstance(i, CalloutItem))
    assert len(box.leaders) == 2, "an arrow leader and a cloud leader"
    assert box.leaders[1].clouds()
    wrong += walk(w, box, "text box leaders")

    # Cloud+: a dragged cloud, then where its words go
    w.new_document()
    w.interactive_prompts = False
    w.select_tool("cloud_callout")
    start, end = QPointF(150, 150), QPointF(300, 250)
    QTest.mousePress(vp(w), Qt.LeftButton, Qt.NoModifier, screen(w, start))
    for step in (0.3, 0.6, 1.0):
        hover(w, start + (end - start) * step)
    QTest.mouseRelease(vp(w), Qt.LeftButton, Qt.NoModifier, screen(w, end))
    pump()
    words = QPointF(420, 120)
    hover(w, words)
    QTest.mouseClick(vp(w), Qt.LeftButton, Qt.NoModifier, screen(w, words))
    pump()
    w.view.end_item_edit()
    plus = next(i for i in w.view.scene().ordered_markups() if isinstance(i, CalloutItem))
    corners = [k for k in plus.handle_points() if k.startswith("c0_")]
    assert corners, "a Cloud+ has a handle on each corner of its cloud"
    wrong += walk(w, plus, "Cloud+")
    assert not wrong, "\n".join(f"{where}: {got} (wanted {wanted})"
                                for where, got, wanted in wrong)


def test_the_size_arrows_turn_with_a_turned_markup(w):
    w.select_tool("rect")
    a, b = QPointF(200, 200), QPointF(360, 280)
    QTest.mousePress(vp(w), Qt.LeftButton, Qt.NoModifier, screen(w, a))
    hover(w, (a + b) / 2)
    hover(w, b)
    QTest.mouseRelease(vp(w), Qt.LeftButton, Qt.NoModifier, screen(w, b))
    pump()
    box = next(i for i in w.view.scene().ordered_markups() if isinstance(i, RectItem))
    box.setTransformOriginPoint(box.local_rect().center())
    turned = {90: {"e": Qt.SizeVerCursor, "n": Qt.SizeHorCursor,
                   "ne": Qt.SizeFDiagCursor, "nw": Qt.SizeBDiagCursor},
              45: {"e": Qt.SizeFDiagCursor, "n": Qt.SizeBDiagCursor,
                   "ne": Qt.SizeHorCursor, "nw": Qt.SizeVerCursor}}
    w.select_tool("select")
    box.setSelected(True)
    for angle, wanted in turned.items():
        box.setRotation(angle)
        pump()
        for key, cursor in wanted.items():
            hover(w, box.mapToScene(box.handle_points()[key]))
            assert box.handle_at(box.mapFromScene(w.view.mapToScene(
                screen(w, box.mapToScene(box.handle_points()[key]))))) == key
            assert shown(w) == cursor, (angle, key, shown(w))


# -- the body of a markup, and the keys -------------------------------------------------

def test_moving_copying_and_a_locked_markup(w):
    box = make(w, "rect")
    w.select_tool("select")
    w.view.scene().clearSelection()
    pump()
    middle = body_of(box)
    hover(w, middle)
    assert shown(w) == MOVE, "a drag moves it"
    QTest.keyPress(w.view, Qt.Key_Control)
    pump()
    assert shown(w) == COPY, "Ctrl, pressed over it: a drag copies it"
    hover(w, middle + QPointF(3, 2))
    assert shown(w) == COPY
    QTest.keyRelease(w.view, Qt.Key_Control)
    pump()
    assert shown(w) == MOVE, "and moves it again once let go"
    QTest.keyPress(w.view, Qt.Key_Shift)
    hover(w, middle)
    assert shown(w) == MOVE, "Shift: still a move, kept straight"
    QTest.keyRelease(w.view, Qt.Key_Shift)
    hover(w, QPointF(700, 700))
    assert shown(w) == Qt.ArrowCursor, "bare paper"
    box.locked = True
    hover(w, middle)
    assert shown(w) == Qt.ForbiddenCursor, "a locked markup cannot be taken hold of"


def test_shift_alt_or_ctrl_over_a_selected_outline_says_what_a_click_does(w):
    shape = make(w, "polygon")
    w.select_tool("select")
    w.view.scene().clearSelection()
    shape.setSelected(True)
    start, end = shape.segment_ends(0)
    side = shape.mapToScene((start + end) / 2)
    corner = shape.mapToScene(shape.points[1])
    hover(w, corner)
    assert shown(w) == POINT_CURSOR, "a corner on its own moves that point"
    for key, wanted in ((Qt.Key_Shift, {"side": ADD, "corner": REMOVE}),
                        (Qt.Key_Alt, {"side": CURVE, "corner": CURVE}),
                        (Qt.Key_Control, {"side": COPY, "corner": COPY})):
        QTest.keyPress(w.view, key)
        for name, where in (("side", side), ("corner", corner)):
            hover(w, where)
            assert shown(w) == wanted[name], (key, name, shown(w))
        QTest.keyRelease(w.view, key)
        pump()
    hover(w, side)
    assert shown(w) == MOVE, "keys let go: the side moves the markup"


def test_words_being_typed_take_the_i_beam(w):
    box = make(w, "text")
    w.select_tool("select")
    w.view.scene().clearSelection()
    middle = body_of(box)
    hover(w, middle)
    QTest.mouseDClick(vp(w), Qt.LeftButton, Qt.NoModifier, screen(w, middle))
    pump()
    if QApplication.mouseButtons() & Qt.LeftButton:
        # QTest's double-click leaves its button down; a hand lets go of it
        QTest.mouseRelease(vp(w), Qt.LeftButton, Qt.NoModifier, screen(w, middle))
        pump()
    assert w.view.editing_item() is box, "a double-click opens it for typing"
    hover(w, body_of(box))
    assert shown(w) == Qt.IBeamCursor


# -- tables, sheets and equations --------------------------------------------------------

def test_a_tables_cells_headings_tab_and_edges(w):
    from tests.test_tables import cell_scene, make_table

    table = make_table(w)
    hover(w, cell_scene(table, "B2"))
    QTest.mouseClick(vp(w), Qt.LeftButton, Qt.NoModifier, screen(w, cell_scene(table, "B2")))
    pump()
    assert w.view.tables.item is table, "open for typing into"
    from calcforge.ui.view import excel_cursor
    hover(w, cell_scene(table, "B2"))
    assert shown(w) == excel_cursor("cell").pixmap().cacheKey(), "Excel's white plus"
    xs, ys = table.edges()
    heading = table.mapToScene(QPointF((xs[1] + xs[2]) / 2, -4))
    hover(w, heading)
    assert shown(w) == excel_cursor("col").pixmap().cacheKey(), "the arrow down a column"
    edge = table.mapToScene(QPointF(xs[1], -4))
    hover(w, edge)
    assert shown(w) == Qt.SplitHCursor, "a column's edge is dragged across"
    tab = table.mapToScene(table.tab_rect().center())
    hover(w, tab)
    assert shown(w) == MOVE, "the tab picks the whole table up to move it"


def test_a_sheets_print_area_and_its_cells(w):
    from tests.test_sheet_pages import cell_scene, sheet_page

    run = sheet_page(w)
    last = run.paging.last_col
    xs, ys = run.edges()
    edge = run.mapToScene(QPointF(xs[last + 1], ys[3]))
    w.view.centerOn(edge)
    pump()
    hover(w, edge)
    # Excel's plain double arrow over a page break or the print area's edge
    # (docs/qa/excel_audit.md, the pointers)
    assert shown(w) == Qt.SizeHorCursor, "the print area's edge"
    from calcforge.ui.view import excel_cursor
    hover(w, cell_scene(run, "B3"))
    assert shown(w) == excel_cursor("cell").pixmap().cacheKey()


def test_an_equation_shows_websmaths_pointers(w):
    from tests.test_calc_panels import an_equation

    item = an_equation(w, "a:=1", 100, 120)
    w.toggle_calc_mode(False)
    pump()
    hover(w, body_of(item))
    assert shown(w) == Qt.ArrowCursor, "WebSMath's arrow inside it"
    rect = item.local_rect()
    hover(w, item.mapToScene(QPointF(rect.center().x(), rect.top() + 0.5)))
    assert shown(w) == w.view.calc.move_cursor().pixmap().cacheKey() or \
        shown(w) == w.view.calc.move_cursor().shape(), "SMath's move cursor on its frame"


# -- the tools --------------------------------------------------------------------------

def test_the_hand_and_each_drawing_tool(w):
    w.select_tool("pan")
    hover(w, QPointF(300, 300))
    assert shown(w) == Qt.OpenHandCursor
    QTest.mousePress(vp(w), Qt.LeftButton, Qt.NoModifier, screen(w, QPointF(300, 300)))
    hover(w, QPointF(330, 320))
    assert shown(w) == Qt.ClosedHandCursor, "the hand closes on the page it drags"
    QTest.mouseRelease(vp(w), Qt.LeftButton, Qt.NoModifier, screen(w, QPointF(330, 320)))
    pump()
    assert shown(w) == Qt.OpenHandCursor
    for tool in TOOLS:
        if tool.key in ("select", "pan", "image", "crop_image"):
            continue
        w.select_tool(tool.key)
        pump()
        hover(w, QPointF(300, 300))
        wanted = w.view._cursor_for_tool(tool)
        assert vp(w).cursor().shape() == wanted.shape(), tool.key
        if wanted.shape() == Qt.BitmapCursor:
            assert vp(w).cursor().pixmap().cacheKey() == wanted.pixmap().cacheKey(), tool.key
        assert shown(w) not in (MOVE, COPY), (tool.key, "a tool is not a move")
        QTest.keyClick(vp(w), Qt.Key_Escape)
        pump()
