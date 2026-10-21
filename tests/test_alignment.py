"""Revu's alignment (the user, 2026-10-20: "Does the app have align items and
align toolbar similar to Bluebeam? Add if not, same stuff as Bluebeam").

Revu 21's Align Markups: Align Left, Centre, Right, Top, Middle and Bottom
to the *primary* markup (the first picked: yellow control points, the others
green; a click on a green-pointed one makes it the primary); Align Width,
Height and Size; Distribute Horizontally and Vertically; Centre in
Document; Flip Horizontal and Vertical. Reached from the Alignment toolbar
(Tools ▸ Toolbars ▸ Alignment), Edit ▸ Alignment and a selection's
right-click ▸ Alignment, and each can be given a key.

Driven as a person drives them: markups drawn and picked with the mouse,
the toolbar's buttons clicked, Ctrl+Z pressed.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from calcforge.items.shapes import PolyItem, RectItem
from calcforge.ui import alignment


def pump(times: int = 4) -> None:
    for _ in range(times):
        QApplication.processEvents()


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.view.set_zoom(1.0)
    window.alignment_bar.setVisible(True)
    pump()
    return window


def at(w, point: QPointF):
    return w.view.mapFromScene(point)


def page(w, x, y) -> QPointF:
    return w.document.pages[0].frame.mapToScene(QPointF(x, y))


def draw_rect(w, x0, y0, x1, y1):
    """A rectangle dragged out with its tool."""
    from tests.test_every_command_is_bindable import _draw
    before = {id(i) for i in w.view.scene().ordered_markups()}
    _draw(w, "rect", x0, y0, x1, y1)
    (made,) = [i for i in w.view.scene().ordered_markups() if id(i) not in before]
    return made


def box(item) -> QRectF:
    """The markup's own box on the canvas (what Revu lines up)."""
    return alignment.shape_rect(item)


def centre_of(item) -> QPointF:
    return box(item).center()


def pick(w, *items) -> None:
    """Click the first, then Shift+click each of the others, where they are."""
    w.select_tool("select")
    w.view.centerOn(centre_of(items[0]))
    pump()
    for number, item in enumerate(items):
        QTest.mouseClick(w.view.viewport(), Qt.LeftButton,
                         Qt.ShiftModifier if number else Qt.NoModifier,
                         at(w, centre_of(item)))
        pump()
    assert set(w.selected_items()) == set(items)


def press(w, key: str) -> None:
    """The Alignment toolbar's button for *key*, clicked."""
    action = getattr(w, f"act_{key}")
    button = w.alignment_bar.widgetForAction(action)
    assert button is not None and button.isVisible(), key
    assert action.isEnabled(), f"{key}: {action.toolTip()}"
    QTest.mouseClick(button, Qt.LeftButton)
    pump()


def undo(w) -> None:
    w.view.setFocus()
    QTest.keyClick(w.view, Qt.Key_Z, Qt.ControlModifier)
    pump()


def by_uid(w, uid):
    return next(i for i in w.view.scene().ordered_markups() if i.uid == uid)


@pytest.fixture
def three(w):
    """Three rectangles of different sizes, picked big, small, middle."""
    a = draw_rect(w, 100, 100, 220, 160)
    b = draw_rect(w, 300, 220, 340, 250)
    c = draw_rect(w, 180, 320, 260, 420)
    pick(w, a, b, c)
    return a, b, c


# ---------------------------------------------------------------------------
# the primary markup
# ---------------------------------------------------------------------------
def test_the_first_picked_is_the_primary_and_a_click_makes_another_one(w, three):
    a, b, c = three
    scene = w.view.scene()
    assert scene.primary_markup() is a
    assert not scene.is_secondary(a) and scene.is_secondary(b) and scene.is_secondary(c)
    # a plain click on a green-pointed markup: it is the primary, and all
    # three stay picked
    QTest.mouseClick(w.view.viewport(), Qt.LeftButton, Qt.NoModifier, at(w, centre_of(c)))
    pump()
    assert set(w.selected_items()) == {a, b, c}
    assert scene.primary_markup() is c and scene.is_secondary(a)
    press(w, "align_left")
    assert abs(box(a).left() - box(c).left()) < 0.01
    assert abs(box(b).left() - box(c).left()) < 0.01


def _ink(image, rect, test) -> int:
    count = 0
    for x in range(max(int(rect.left()), 0), min(int(rect.right()) + 1, image.width())):
        for y in range(max(int(rect.top()), 0), min(int(rect.bottom()) + 1, image.height())):
            if test(QColor(image.pixel(x, y))):
                count += 1
    return count


def _greenish(colour: QColor) -> bool:
    return colour.green() > 120 and colour.green() > colour.red() + 40 \
        and colour.green() > colour.blue() + 30


def _goldish(colour: QColor) -> bool:
    return colour.red() > 170 and colour.green() > 140 and colour.blue() < 110


def test_the_primarys_control_points_are_yellow_and_the_others_green(w, three):
    a, b, _c = three
    w.view.viewport().repaint()
    pump()
    picture = w.view.viewport().grab().toImage()

    def around(item):
        rect = w.view.mapFromScene(box(item)).boundingRect()
        return QRectF(rect).adjusted(-6, -6, 6, 6)
    assert _ink(picture, around(a), _goldish) > 4, "the primary's points are yellow"
    assert _ink(picture, around(a), _greenish) == 0
    assert _ink(picture, around(b), _greenish) > 4, "a secondary's points are green"
    assert _ink(picture, around(b), _goldish) == 0
    # one markup alone keeps its yellow points
    QTest.mouseClick(w.view.viewport(), Qt.LeftButton, Qt.NoModifier, at(w, centre_of(b)))
    pump()
    QTest.mouseClick(w.view.viewport(), Qt.LeftButton, Qt.NoModifier,
                     at(w, page(w, 500, 700)))
    QTest.mouseClick(w.view.viewport(), Qt.LeftButton, Qt.NoModifier, at(w, centre_of(b)))
    pump()
    w.view.viewport().repaint()
    picture = w.view.viewport().grab().toImage()
    assert _ink(picture, around(b), _goldish) > 4 and _ink(picture, around(b), _greenish) == 0


# ---------------------------------------------------------------------------
# each command, from the toolbar, one undo step
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("key, edge", [
    ("align_left", lambda r: r.left()), ("align_right", lambda r: r.right()),
    ("align_hcenter", lambda r: r.center().x()), ("align_top", lambda r: r.top()),
    ("align_bottom", lambda r: r.bottom()), ("align_vcenter", lambda r: r.center().y())])
def test_each_align_lines_up_with_the_primary_in_one_undo_step(w, three, key, edge):
    a, b, c = three
    before = {item.uid: QRectF(box(item)) for item in three}
    primary = edge(box(a))
    steps = w.undo_stack.count()
    press(w, key)
    assert w.undo_stack.count() == steps + 1
    for item in (b, c):
        assert abs(edge(box(item)) - primary) < 0.01, key
    assert box(a) == before[a.uid], "the primary stays where it is"
    undo(w)
    for uid, rect in before.items():
        assert box(by_uid(w, uid)) == rect


@pytest.mark.parametrize("key", ["align_width", "align_height", "align_size"])
def test_each_size_is_the_primarys(w, three, key):
    a, b, c = three
    corner = box(b).topLeft()
    height_before = box(b).height()
    width_before = box(b).width()
    press(w, key)
    for item in (b, c):
        if key in ("align_width", "align_size"):
            assert abs(box(item).width() - box(a).width()) < 0.6, key
        if key in ("align_height", "align_size"):
            assert abs(box(item).height() - box(a).height()) < 0.6, key
    if key == "align_width":
        assert abs(box(b).height() - height_before) < 0.01
    if key == "align_height":
        assert abs(box(b).width() - width_before) < 0.01
    assert (box(b).topLeft() - corner).manhattanLength() < 0.6, "its top left stays"
    undo(w)
    assert abs(box(by_uid(w, b.uid)).width() - width_before) < 0.01


def test_distribute_spaces_the_centres_equally(w):
    items = [draw_rect(w, x, 100 + n * 30, x + 40, 130 + n * 30)
             for n, x in enumerate((60, 140, 400, 470))]
    pick(w, *items)
    press(w, "distribute_horizontally")
    xs = sorted(centre_of(i).x() for i in items)
    gaps = [b - a for a, b in zip(xs, xs[1:])]
    assert max(gaps) - min(gaps) < 0.01
    assert abs(xs[0] - centre_of(items[0]).x()) < 0.01, "the outermost stay"
    press(w, "distribute_vertically")
    ys = sorted(centre_of(i).y() for i in items)
    gaps = [b - a for a, b in zip(ys, ys[1:])]
    assert max(gaps) - min(gaps) < 0.01


def test_centre_in_document_puts_each_on_the_middle_of_its_page(w):
    item = draw_rect(w, 60, 80, 140, 120)
    pick(w, item)
    press(w, "centre_in_document")
    frame = w.document.pages[0].frame
    middle = frame.mapRectToScene(frame.page_rect()).center()
    assert (centre_of(item) - middle).manhattanLength() < 0.01


def test_flip_mirrors_a_polygon_about_its_centre(w):
    from tests.test_every_command_is_bindable import _draw
    _draw(w, "polygon", 100, 100, 220, 180)
    (shape,) = [i for i in w.view.scene().ordered_markups() if isinstance(i, PolyItem)]
    pick(w, shape)
    middle = centre_of(shape)
    points = [shape.mapToScene(p) for p in shape.points]
    press(w, "flip_horizontal")
    flipped = [shape.mapToScene(p) for p in shape.points]
    for was, now in zip(points, flipped):
        assert abs(now.x() - (2 * middle.x() - was.x())) < 0.01 and abs(now.y() - was.y()) < 0.01
    assert (centre_of(shape) - middle).manhattanLength() < 0.01
    press(w, "flip_vertical")
    for was, now in zip(points, [shape.mapToScene(p) for p in shape.points]):
        assert abs(now.y() - (2 * middle.y() - was.y())) < 0.01
    undo(w)
    undo(w)
    again = by_uid(w, shape.uid)
    for was, now in zip(points, [again.mapToScene(p) for p in again.points]):
        assert (was - now).manhattanLength() < 0.01


def test_flip_mirrors_an_images_picture_and_a_stamp(w):
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QImage
    from calcforge.items.media import ImageItem
    from calcforge.items.text import StampItem
    picture = QImage(20, 10, QImage.Format_RGB32)
    picture.fill(QColor("#0000ff"))
    for y in range(10):
        for x in range(10):
            picture.setPixelColor(x, y, QColor("#ff0000"))      # red on the left
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    picture.save(buffer, "PNG")
    image = ImageItem(w.document.add_asset(bytes(data), ".png"), QRectF(0, 0, 100, 50))
    frame = w.document.pages[0].frame
    frame.add_markup(image, QPointF(100, 100))
    image.load_from_document(w.document)
    stamp = StampItem("APPROVED")
    frame.add_markup(stamp, QPointF(100, 300))
    w.refresh_lists()
    pump()
    where = box(stamp)
    pick(w, image, stamp)
    press(w, "flip_horizontal")
    shown = image.pixmap().toImage()
    assert QColor(shown.pixel(2, 5)).blue() > 200 and QColor(shown.pixel(18, 5)).red() > 200
    assert stamp.transform().m11() == -1.0
    assert (box(stamp).center() - where.center()).manhattanLength() < 0.01
    undo(w)
    image = next(i for i in w.view.scene().ordered_markups() if isinstance(i, ImageItem))
    assert QColor(image.pixmap().toImage().pixel(2, 5)).red() > 200


def test_flip_turns_a_group_over_as_one(w):
    a = draw_rect(w, 100, 100, 140, 140)
    from tests.test_every_command_is_bindable import _draw
    _draw(w, "polyline", 200, 100, 260, 160)
    line = [i for i in w.view.scene().ordered_markups() if isinstance(i, PolyItem)][-1]
    on_line = line.mapToScene((line.points[0] + line.points[1]) / 2)
    pick(w, a)
    QTest.mouseClick(w.view.viewport(), Qt.LeftButton, Qt.ShiftModifier, at(w, on_line))
    pump()
    assert set(w.selected_items()) == {a, line}
    w.view.setFocus()
    QTest.keyClick(w.view, Qt.Key_G, Qt.ControlModifier)        # Group
    pump()
    assert a.group and a.group == line.group
    whole = box(a).united(box(line))
    w.view.scene().clearSelection()
    QTest.mouseClick(w.view.viewport(), Qt.LeftButton, Qt.NoModifier, at(w, centre_of(a)))
    pump()
    assert set(w.selected_items()) == {a, line}, "a click on one picks the group"
    press(w, "flip_horizontal")
    assert abs(box(a).right() - whole.right()) < 0.6, "the rectangle went to the other side"
    assert abs(box(line).left() - whole.left()) < 0.6


# ---------------------------------------------------------------------------
# equations, tables and a mix, as the align commands always took
# ---------------------------------------------------------------------------
def test_equations_tables_and_markups_align_together(w):
    from tests.test_calc_panels import an_equation
    from tests.test_tables import make_table
    rect = draw_rect(w, 300, 100, 380, 140)
    equation = an_equation(w, "x:2", 120, 200)
    table = make_table(w, 150, 300)
    QTest.keyClick(w.view, Qt.Key_Escape)
    pump()
    w.select_tool("select")
    w.view.scene().clearSelection()
    # a drag round the three, from bare paper: picked together, the first in
    # reading order (the rectangle, highest) is the primary
    start, end = at(w, page(w, 90, 80)), at(w, page(w, 420, 400))
    viewport = w.view.viewport()
    QTest.mousePress(viewport, Qt.LeftButton, Qt.NoModifier, start)
    for step in (0.3, 0.6, 1.0):
        QTest.mouseMove(viewport, start + (end - start) * step)
    QTest.mouseRelease(viewport, Qt.LeftButton, Qt.NoModifier, end)
    pump()
    assert set(w.selected_items()) == {rect, equation, table}
    assert w.view.scene().primary_markup() is rect
    steps = w.undo_stack.count()
    press(w, "align_left")
    for item in (equation, table):
        assert abs(box(item).left() - box(rect).left()) < 0.01
    assert w.undo_stack.count() == steps + 1


def test_a_flip_is_saved(w, tmp_path):
    from calcforge.items.text import StampItem
    from tests.test_every_command_is_bindable import _draw
    from tests.test_propbar_gaps import save_and_reopen
    stamp = StampItem("APPROVED")
    w.document.pages[0].frame.add_markup(stamp, QPointF(100, 300))
    _draw(w, "polygon", 100, 100, 220, 180)
    shape = [i for i in w.view.scene().ordered_markups() if isinstance(i, PolyItem)][-1]
    pick(w, stamp)
    press(w, "flip_vertical")
    pick(w, shape)
    press(w, "flip_horizontal")
    points = [QPointF(p) for p in shape.points]
    save_and_reopen(w, tmp_path)
    (stamp,) = [i for i in w.view.scene().ordered_markups() if isinstance(i, StampItem)]
    (shape,) = [i for i in w.view.scene().ordered_markups() if isinstance(i, PolyItem)]
    assert stamp.transform().m22() == -1.0
    assert all((a - b).manhattanLength() < 0.01 for a, b in zip(points, shape.points))


# ---------------------------------------------------------------------------
# where they are reached, and what they say when too few are picked
# ---------------------------------------------------------------------------
def _labels(menu) -> list:
    return [a.text() if not a.isSeparator() else None for a in menu.actions()]


EXPECTED = [alignment.COMMANDS[key][0] if key else None for key in alignment.ORDER]


def test_the_toolbar_edit_menu_and_right_click_offer_every_command(w):
    bar = w.alignment_bar
    assert bar.windowTitle() == "Alignment"
    shown = [a.text() if not a.isSeparator() else None for a in bar.actions()]
    assert shown == EXPECTED
    for action in bar.actions():
        if not action.isSeparator():
            assert not action.icon().isNull(), action.text()
    toolbars = next(a.menu() for a in w.menuBar().actions() if a.text().replace("&", "") == "Tools")
    toolbars = next(a.menu() for a in toolbars.actions() if a.text() == "Toolbars")
    toggle = next(a for a in toolbars.actions() if a.text() == "Alignment")
    toggle.trigger()
    pump()
    assert not bar.isVisible()
    toggle.trigger()
    pump()
    assert bar.isVisible()
    edit = next(a.menu() for a in w.menuBar().actions() if a.text().replace("&", "") == "Edit")
    align = next(a.menu() for a in edit.actions() if a.text() == "Alignment")
    assert _labels(align) == EXPECTED
    item = draw_rect(w, 100, 100, 160, 160)
    pick(w, item)
    menu = w.build_context_menu(item, centre_of(item))
    sub = next(a.menu() for a in menu.actions() if a.text() == "Alignment")
    assert _labels(sub) == EXPECTED


def test_too_few_picked_leaves_a_command_off_and_says_why(w):
    item = draw_rect(w, 100, 100, 160, 160)
    pick(w, item)
    pump()
    assert not w.act_align_left.isEnabled()
    assert "select two markups or more" in w.act_align_left.toolTip()
    assert not w.act_distribute_horizontally.isEnabled()
    assert "three markups or more" in w.act_distribute_horizontally.toolTip()
    assert w.act_centre_in_document.isEnabled()
    # a rectangle is not one Revu flips
    assert not w.act_flip_horizontal.isEnabled()
    assert "text boxes do not" in w.act_flip_horizontal.toolTip()
    w.view.scene().clearSelection()
    pump()
    assert not w.act_centre_in_document.isEnabled()
    assert "one markup or more" in w.act_flip_vertical.toolTip()


def test_every_command_can_be_given_a_key(w, three):
    a, b, c = three
    known = {binding.action_id for binding in w.shortcuts.bindings()}
    for key in alignment.COMMANDS:
        assert f"command.{key}" in known, key
    try:
        w.shortcuts.set_sequence("command.align_top", "Ctrl+Shift+F6")
        w.apply_shortcuts()
        w.view.setFocus()
        QTest.keyClick(w.view, Qt.Key_F6, Qt.ControlModifier | Qt.ShiftModifier)
        pump()
        assert abs(box(b).top() - box(a).top()) < 0.01
    finally:
        w.shortcuts.reset("command.align_top")
        w.apply_shortcuts()


# ---------------------------------------------------------------------------
# greyed when it does not apply (the user, 2026-10-21: "Make sure the
# alignment thing greys out when not applicable")
# ---------------------------------------------------------------------------
def _strength(button) -> int:
    """How many of the button's pixels stand out from its background."""
    picture = button.grab().toImage()
    ground = QColor(picture.pixel(1, 1))
    count = 0
    for x in range(picture.width()):
        for y in range(picture.height()):
            if abs(QColor(picture.pixel(x, y)).lightness() - ground.lightness()) > 70:
                count += 1
    return count


WANTS = {"align_left": 2, "align_hcenter": 2, "align_right": 2, "align_top": 2,
         "align_vcenter": 2, "align_bottom": 2, "align_width": 2, "align_height": 2,
         "align_size": 2, "distribute_horizontally": 3, "distribute_vertically": 3,
         "centre_in_document": 1, "flip_horizontal": 1, "flip_vertical": 1}


def test_each_button_greys_until_enough_are_picked(w):
    from tests.test_every_command_is_bindable import _draw
    shapes = []
    for corners in ((100, 100, 200, 160), (260, 120, 340, 200), (140, 260, 260, 330)):
        before = {id(i) for i in w.view.scene().ordered_markups()}
        _draw(w, "polygon", *corners)
        shapes += [i for i in w.view.scene().ordered_markups() if id(i) not in before]
    assert len(shapes) == 3
    w.view.scene().clearSelection()
    pump()
    dim, lit = {}, {}
    for count in range(0, 4):
        if count:
            shape = shapes[count - 1]
            point = shape.mapToScene((shape.points[0] + shape.points[1]) / 2)
            QTest.mouseClick(w.view.viewport(), Qt.LeftButton,
                             Qt.ShiftModifier if count > 1 else Qt.NoModifier, at(w, point))
            pump()
        assert len(w.selected_items()) == count
        for key, least in WANTS.items():
            action = getattr(w, f"act_{key}")
            button = w.alignment_bar.widgetForAction(action)
            assert button.isEnabled() == (count >= least), (key, count)
            assert action.isEnabled() == (count >= least), (key, count)
            if count >= least:
                lit.setdefault(key, _strength(button))
            else:
                dim.setdefault(key, _strength(button))
    for key in WANTS:
        assert dim[key] * 2 < lit[key], f"{key}: greyed is plainly fainter"


def test_a_key_does_nothing_while_its_command_is_greyed(w):
    a = draw_rect(w, 100, 100, 160, 160)
    pick(w, a)
    where = box(a)
    try:
        w.shortcuts.set_sequence("command.align_left", "Ctrl+Shift+F6")
        w.apply_shortcuts()
        w.view.setFocus()
        QTest.keyClick(w.view, Qt.Key_F6, Qt.ControlModifier | Qt.ShiftModifier)
        pump()
        assert box(a) == where and not w.act_align_left.isEnabled()
    finally:
        w.shortcuts.reset("command.align_left")
        w.apply_shortcuts()


# ---------------------------------------------------------------------------
# what flips (the user, 2026-10-21: "Callouts are flippable in Revu, but the
# text is not flipped … Text box not flippable"; "Snapshot could not be
# flipped?")
# ---------------------------------------------------------------------------
def test_a_text_box_does_not_flip_and_is_left_alone_among_others(w):
    from calcforge.items.text import TextItem
    from tests.test_every_command_is_bindable import _draw
    words = TextItem("Note", QRectF(0, 0, 120, 40))
    w.document.pages[0].frame.add_markup(words, QPointF(100, 100))
    w.refresh_lists()
    pump()
    pick(w, words)
    assert not w.act_flip_horizontal.isEnabled() and not w.act_flip_vertical.isEnabled()
    _draw(w, "polyline", 300, 120, 380, 200)
    line = [i for i in w.view.scene().ordered_markups() if isinstance(i, PolyItem)][-1]
    pick(w, words)
    QTest.mouseClick(w.view.viewport(), Qt.LeftButton, Qt.ShiftModifier,
                     at(w, line.mapToScene((line.points[0] + line.points[1]) / 2)))
    pump()
    assert set(w.selected_items()) == {words, line}
    assert w.act_flip_horizontal.isEnabled()
    text_before = box(words)
    first = line.mapToScene(line.points[0])
    press(w, "flip_horizontal")
    assert box(words) == text_before, "the text box is left as it was"
    assert (line.mapToScene(line.points[0]) - first).manhattanLength() > 1, "the line flipped"


def test_a_callout_flips_its_box_and_leader_but_not_its_words(w):
    from calcforge.items.text import CalloutItem
    callout = CalloutItem("Check", QRectF(0, 0, 100, 40), [QPointF(-80, 90)])
    w.document.pages[0].frame.add_markup(callout, QPointF(300, 200))
    w.refresh_lists()
    pump()
    pick(w, callout)
    tip = callout.mapToScene(callout.tip)
    text_box = box(callout)
    assert tip.x() < text_box.left(), "the leader is on the left"
    words = callout.doc.toPlainText()
    press(w, "flip_horizontal")
    callout = next(i for i in w.view.scene().ordered_markups() if isinstance(i, CalloutItem))
    tip_now = callout.mapToScene(callout.tip)
    assert tip_now.x() > box(callout).right(), "the leader is on the right now"
    # mirrored about the middle of the lot: the box where the tip was, the
    # tip where the box's far side was
    assert abs(box(callout).left() - tip.x()) < 0.01, "the box went to the left"
    assert abs(tip_now.x() - text_box.right()) < 0.01
    assert abs(tip_now.y() - tip.y()) < 0.01 and abs(box(callout).top() - text_box.top()) < 0.01
    assert callout.transform().isIdentity(), "the words are not mirrored"
    assert callout.doc.toPlainText() == words
    undo(w)
    callout = next(i for i in w.view.scene().ordered_markups() if isinstance(i, CalloutItem))
    assert (callout.mapToScene(callout.tip) - tip).manhattanLength() < 0.01


def _a_snapshot(w):
    """A snapshot of part of the page with a red box at its left, pasted
    back and moved clear of it."""
    from calcforge.items.snapshot import SnapshotItem
    frame = w.document.pages[0].frame
    red = RectItem("rect", QRectF(0, 0, 40, 60))
    red.style.stroke = "#ff0000"
    red.style.fill = "#ff0000"
    red.style.fill_opacity = 1.0
    frame.add_markup(red, QPointF(110, 110))
    w.take_snapshot(frame, QRectF(100, 100, 160, 80))
    w.paste_items()
    pump()
    (shot,) = [i for i in w.view.scene().ordered_markups() if isinstance(i, SnapshotItem)]
    w.view.begin_snapshot()
    shot.setPos(QPointF(200, 400))
    w.view.commit_snapshot("Move")
    return next(i for i in w.view.scene().ordered_markups() if isinstance(i, SnapshotItem))


def _red_either_side(image, rect: QRectF) -> tuple:
    left = right = 0
    for x in range(int(rect.left()) + 2, int(rect.right()) - 2):
        for y in range(int(rect.top()) + 2, int(rect.bottom()) - 2):
            if not (0 <= x < image.width() and 0 <= y < image.height()):
                continue
            shade = QColor(image.pixel(x, y))
            if shade.red() > 200 and shade.green() < 90 and shade.blue() < 90:
                if x < rect.center().x():
                    left += 1
                else:
                    right += 1
    return left, right


def test_a_snapshot_flips_and_stays_flipped_saved_and_exported(w, tmp_path):
    import pymupdf
    from PySide6.QtGui import QImage
    from calcforge.items.snapshot import SnapshotItem
    from tests.test_propbar_gaps import save_and_reopen

    def snapshot():
        return next(i for i in w.view.scene().ordered_markups() if isinstance(i, SnapshotItem))

    def drawn():
        shot = snapshot()
        w.view.scene().clearSelection()
        w.view.centerOn(box(shot).center())
        pump()
        w.view.viewport().repaint()
        return _red_either_side(w.view.viewport().grab().toImage(),
                                QRectF(w.view.mapFromScene(box(shot)).boundingRect()))
    _a_snapshot(w)
    left, right = drawn()
    assert left > 50 and right == 0, "the red box is on the left"
    pick(w, snapshot())
    assert w.act_flip_horizontal.isEnabled()
    press(w, "flip_horizontal")
    left, right = drawn()
    assert right > 50 and left == 0, "flipped: on the right"
    path = save_and_reopen(w, tmp_path)
    assert snapshot().mirrored == (True, False)
    left, right = drawn()
    assert right > 50 and left == 0, "still flipped when opened again"
    # and as another reader draws the saved PDF
    zoom = 2.0
    pix = pymupdf.open(path)[0].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    image = QImage(pix.samples, pix.width, pix.height, pix.stride,
                   QImage.Format_RGB888).copy()
    where = w.document.pages[0].frame.mapRectFromScene(box(snapshot()))
    left, right = _red_either_side(image, QRectF(where.x() * zoom, where.y() * zoom,
                                                 where.width() * zoom, where.height() * zoom))
    assert right > 50 and left == 0, "MuPDF draws it flipped too"


def test_a_picked_snapshot_has_one_outline(w):
    shot = _a_snapshot(w)
    w.view.centerOn(box(shot).center())
    pick(w, shot)
    w.view.viewport().repaint()
    pump()
    image = w.view.viewport().grab().toImage()
    rect = w.view.mapFromScene(box(shot)).boundingRect()
    # down through its top edge a quarter of the way along: each blue line
    # crossed is an outline (the handles are at the corners and the middle)
    x = rect.left() + rect.width() // 4
    rows = []
    for y in range(rect.top() - 14, rect.top() + 6):
        shades = [QColor(image.pixel(x + dx, y)) for dx in range(0, 6)]
        if any(c.blue() > 150 and c.red() < 140 for c in shades):
            rows.append(y)
    lines = [y for n, y in enumerate(rows) if n == 0 or y - rows[n - 1] > 1]
    assert len(lines) == 1, f"one outline, not {len(lines)} ({rows})"
