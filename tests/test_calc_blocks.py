"""Phase 7: the calculation block — a markup of its own that holds
equations, and with Self-contained on keeps what they define to itself.
Driven through the real window."""
from __future__ import annotations

import pymupdf
import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import tests.calc.test_calcforge_window as cw
from calcforge.calc.docsheet import PT_PER_PX, sheet_for
from calcforge.calc.engine.display import display_text
from calcforge.items.calc import CalcBlockItem, CalcItem
from tests.test_usability import drag


@pytest.fixture
def v(window):
    window.show()
    window.activateWindow()
    return cw.Sheet(window)


def shown(item):
    region = item.region
    if region.error is not None:
        return region.error.message
    return display_text(region.display) if region.display is not None else None


def blocks(window):
    return [i for i in window.view.scene().items() if isinstance(i, CalcBlockItem)]


def equations(window):
    return sorted((i for i in window.view.scene().items() if isinstance(i, CalcItem)),
                  key=lambda i: (i.pos().y(), i.pos().x()))


def settle(window):
    QApplication.instance().processEvents()
    sheet_for(window.document).settle()


def two_checks(v):
    """x:1 above; a block of y:x+1, x:5, x+y=; then x= and y= after it."""
    for y, keys in ((18, "x:1"), (108, "y:x+1"), (144, "x:5"), (180, "x+y="),
                    (360, "x="), (396, "y=")):
        v.type_at(36, y, "")
        v.keys(keys)
        v.press(Qt.Key_Return)
    v.calc.leave()
    made = {round(i.reading_position()[1]): i for i in equations(v.window)}
    inside = [made[108], made[144], made[180]]
    v.view.scene().clearSelection()
    for item in inside:
        item.setSelected(True)
    v.window.insert_block()
    (block,) = blocks(v.window)
    settle(v.window)
    return block, made[18], inside, [made[360], made[396]]


def test_block_on_the_toolbar_wraps_the_selected_equations(v):
    block, outside, inside, after = two_checks(v)
    assert [a.text() for a in v.window.calculation_bar.actions() if a.text() == "Block"]
    assert set(block.members()) == set(inside)
    assert block.isSelected() and block.TYPE == "calc_block"
    # a block of its own: not an equation, not in the Markups list
    assert block.region is None and block.display_name() == "Calculation block"
    assert shown(after[0]) == "5" and shown(after[1]) == "2", \
        "without Self-contained a block calculates as if it were not there"


def test_self_contained_keeps_the_blocks_names_inside_it(v):
    block, outside, inside, after = two_checks(v)
    menu = v.window.build_context_menu(block, block.sceneBoundingRect().topLeft())
    (toggle,) = [a for a in menu.actions() if a.text() == "Self-contained"]
    toggle.trigger()
    settle(v.window)
    assert block.self_contained
    assert shown(inside[2]) == "7", "inside: its own x (5), and y from the x above (1+1)"
    assert shown(after[0]) == "1", "after it, x is the x defined above the block"
    assert "not defined" in shown(after[1])
    v.window.undo_stack.undo()
    settle(v.window)
    (block,) = blocks(v.window)
    assert not block.self_contained
    assert shown(equations(v.window)[4]) == "5"


def test_editing_above_a_self_contained_block_updates_inside_it(v):
    block, outside, inside, after = two_checks(v)
    v.window.set_block_self_contained([block], True)
    settle(v.window)
    v.focus_item(outside)
    outside.editor.set_cursor(outside.editor.root, len(outside.editor.root))
    v.keys("0")                                       # x:10
    v.press(Qt.Key_Return)
    settle(v.window)
    assert shown(inside[2]) == "16"
    assert shown(after[0]) == "10"


def test_the_properties_panel_turns_self_contained_on(v):
    block, outside, inside, after = two_checks(v)
    v.view.scene().clearSelection()
    block.setSelected(True)
    v.window.refresh_selection()
    from PySide6.QtWidgets import QCheckBox
    box = v.window.properties_panel.findChild(QCheckBox, "blockSelfContained")
    assert box is not None
    box.setChecked(True)
    settle(v.window)
    assert block.self_contained and shown(after[0]) == "1"


def test_moving_the_block_moves_its_equations(v):
    block, outside, inside, after = two_checks(v)
    before = [QPointF(i.pos()) for i in inside]
    start = block.mapToScene(block.local_rect().topLeft() + QPointF(0, 30))
    drag(v.view, start.x(), start.y(), start.x() + 120, start.y())
    settle(v.window)
    moved = [i.pos() - p for i, p in zip(inside, before)]
    assert all(abs(d.x() - moved[0].x()) < 0.01 and abs(d.y()) < 0.01 for d in moved)
    assert moved[0].x() > 90
    assert outside.pos().x() == pytest.approx(36 * PT_PER_PX), "only its own equations"
    v.window.undo_stack.undo()
    assert [i.pos() for i in equations(v.window)[1:4]] == before


def test_arrow_keys_nudge_the_block_and_its_equations(v):
    block, outside, inside, after = two_checks(v)
    v.view.scene().clearSelection()
    block.setSelected(True)
    before = [QPointF(i.pos()) for i in inside], QPointF(block.pos())
    v.view.setFocus()
    QTest.keyClick(v.view.viewport(), Qt.Key_Right)
    step = block.pos().x() - before[1].x()
    assert step > 0
    assert all(i.pos().x() - p.x() == pytest.approx(step) for i, p in zip(inside, before[0]))


def at(v, scene_point):
    """The pointer helpers take scene coordinates."""
    return scene_point.x(), scene_point.y()


def open_by_double_click(v, block):
    """Double-click the page inside the block, clear of its equations."""
    from tests.test_usability import double_click
    box = block.local_rect()
    point = block.mapToScene(QPointF(box.right() - 30, box.bottom() - 12))
    double_click(v.view, *at(v, point))
    QApplication.instance().processEvents()
    return point


def test_one_click_on_a_blocks_equation_selects_the_block(v):
    """Like a text box: closed, a click anywhere on it is the block's."""
    from tests.test_usability import click
    block, outside, inside, after = two_checks(v)
    v.view.scene().clearSelection()
    click(v.view, *at(v, inside[1].mapToScene(inside[1].local_rect().center())))
    assert block.isSelected() and not inside[1].isSelected()
    assert not v.calc.editing(), "no caret: the equation is part of the closed block"
    assert v.calc.cross is None
    assert v.view.markup_at(inside[1].scenePos() + QPointF(4, 4)) is block
    # the empty paper inside it is the block's too
    box = block.local_rect()
    assert block.contains(QPointF(box.right() - 30, box.bottom() - 12))


def test_dragging_a_closed_block_by_an_equation_moves_it_all(v):
    block, outside, inside, after = two_checks(v)
    before = [QPointF(i.pos()) for i in inside], QPointF(block.pos())
    _drag_item(v, inside[0], 120, 0)
    step = block.pos().x() - before[1].x()
    assert step > 90
    assert all(i.pos().x() - p.x() == pytest.approx(step) for i, p in zip(inside, before[0]))


def test_double_click_opens_the_block_to_edit_an_equation_in_it(v):
    from tests.test_usability import double_click
    block, outside, inside, after = two_checks(v)
    v.view.scene().clearSelection()
    target = inside[1]                                   # x:5
    double_click(v.view, *at(v, target.mapToScene(target.local_rect().center())))
    assert block.opened and v.view.open_block() is block
    assert v.calc.editing() and v.calc.item is target
    target.editor.set_cursor(target.editor.root, len(target.editor.root))
    v.keys("0")
    v.press(Qt.Key_Return)
    settle(v.window)
    assert shown(inside[2]) == "52", "x:50, y = 1+1"


def test_an_open_block_takes_new_equations_and_clicks_on_its_own(v):
    from tests.test_usability import click
    block, outside, inside, after = two_checks(v)
    point = open_by_double_click(v, block)
    assert block.opened
    assert v.calc.cross is not None, "the red cross, where it was double-clicked"
    v.keys("9=")
    v.press(Qt.Key_Return)
    assert len(block.members()) == 4 and any(i.text() == "9=" for i in block.members())
    # open, one click on an equation in it puts the caret there
    v.calc.leave()
    click(v.view, *at(v, inside[0].mapToScene(inside[0].local_rect().center())))
    QApplication.instance().processEvents()
    assert v.calc.item is inside[0] and block.opened
    # the frame shows it is open on the screen, never in print
    assert not block.contains(block.local_rect().center()), "open: picked by its frame"
    del point


def test_a_click_outside_or_esc_closes_the_block(v):
    from tests.test_usability import click
    block, outside, inside, after = two_checks(v)
    open_by_double_click(v, block)
    assert block.opened
    far = after[1].mapToScene(after[1].local_rect().bottomRight() + QPointF(200, 60))
    click(v.view, *at(v, far))
    assert not block.opened and v.view.open_block() is None
    open_by_double_click(v, block)
    assert block.opened
    v.calc.leave()
    v.calc.clear_cross()
    v.view.setFocus()
    QTest.keyClick(v.view.viewport(), Qt.Key_Escape)
    assert not block.opened
    # closed again: a click on its equation is the block's
    click(v.view, *at(v, inside[0].mapToScene(inside[0].local_rect().center())))
    assert block.isSelected() and not v.calc.editing()


def test_the_open_frame_is_not_saved(v):
    block, outside, inside, after = two_checks(v)
    open_by_double_click(v, block)
    assert "opened" not in block.serialize()


def test_deleting_the_block_deletes_its_equations_and_undo_brings_them_back(v):
    block, outside, inside, after = two_checks(v)
    v.view.scene().clearSelection()
    block.setSelected(True)
    v.window.delete_selection()
    settle(v.window)
    assert blocks(v.window) == [] and len(equations(v.window)) == 3
    assert "not defined" in shown(equations(v.window)[2])      # y= after it
    v.window.undo_stack.undo()
    settle(v.window)
    assert len(blocks(v.window)) == 1 and len(equations(v.window)) == 6
    assert shown(equations(v.window)[5]) == "2"


def test_copying_the_block_brings_its_equations(v):
    block, outside, inside, after = two_checks(v)
    v.window.set_block_self_contained([block], True)
    v.view.scene().clearSelection()
    block.setSelected(True)
    v.window.duplicate_selection()
    settle(v.window)
    copies = [b for b in blocks(v.window) if b is not block]
    assert len(copies) == 1 and copies[0].self_contained
    assert len(equations(v.window)) == 9


def test_a_block_saves_as_page_drawing_and_comes_back(v, tmp_path):
    from tests.test_calc_saving import reopen, save_to
    block, outside, inside, after = two_checks(v)
    v.window.set_block_self_contained([block], True)
    settle(v.window)
    frame_box = block.mapRectToParent(block.local_rect())
    path = str(tmp_path / "block.pdf")
    save_to(v.window, path)
    with pymupdf.open(path) as saved:
        page = saved[0]
        assert not list(page.annots()), "never an annotation"
        rects = [d["rect"] for d in page.get_drawings()]
    assert any(abs(r.x0 - frame_box.left()) < 1 and abs(r.y1 - frame_box.bottom()) < 1
               for r in rects), "its frame is drawn into the page"
    reopen(v.window, path)
    settle(v.window)
    (block,) = blocks(v.window)
    assert block.self_contained and len(block.members()) == 3
    made = equations(v.window)
    assert shown(made[4]) == "1" and "not defined" in shown(made[5])


def test_a_snapshot_takes_the_block_as_line_work(v):
    from calcforge.items.calc import CalcDrawingItem
    block, outside, inside, after = two_checks(v)
    drawing = CalcDrawingItem.of(block)
    assert "<path" in drawing.stamp_svg or "<rect" in drawing.stamp_svg


# -- a block is a little page of its own: nothing is dragged in or out ----------------------

def _drag_item(v, item, dx, dy, opened=None):
    v.window.select_tool("select")
    v.calc.leave()
    v.view.scene().clearSelection()
    if opened is not None:
        open_by_double_click(v, opened)
        v.calc.leave()
        v.calc.clear_cross()
    start = item.mapToScene(item.local_rect().center())
    drag(v.view, start.x(), start.y(), start.x() + dx, start.y() + dy)
    settle(v.window)


def test_an_equation_cant_be_dragged_out_of_its_block(v):
    block, outside, inside, after = two_checks(v)
    member = inside[0]
    was = QPointF(member.pos())
    _drag_item(v, member, 0, 400, opened=block)      # far below the block
    assert block.scene_box().contains(member.scenePos()), "still in its block"
    assert member in block.members()
    assert member.pos().y() > was.y() + 20, "it did move: to the block's bottom edge"


def test_an_equation_cant_be_dragged_into_a_block(v):
    block, outside, inside, after = two_checks(v)
    before = QPointF(after[0].pos())
    target = block.scene_box().center()
    start = after[0].mapToScene(after[0].local_rect().center())
    seen = []
    v.view.statusMessage.connect(seen.append)
    _drag_item(v, after[0], target.x() - start.x(), target.y() - start.y())
    assert after[0].pos() == before, "back where it was"
    assert any("can't be dragged into a block" in m for m in seen)
    assert after[0] not in block.members() and len(block.members()) == 3


def test_moving_inside_the_block_is_fine(v):
    block, outside, inside, after = two_checks(v)
    member = inside[2]
    _drag_item(v, member, 40, 0, opened=block)
    assert member in block.members()
    assert member.pos().x() > inside[1].pos().x()


def test_a_block_cant_be_stretched_over_other_equations_or_shrunk_off_its_own(v):
    block, outside, inside, after = two_checks(v)
    rect = QRectF(block.local_rect())
    v.window.select_tool("select")
    v.view.scene().clearSelection()
    block.setSelected(True)
    corner = block.mapToScene(block.local_rect().bottomRight())
    drag(v.view, corner.x(), corner.y(), corner.x(), corner.y() + 300)   # over x= and y=
    settle(v.window)
    assert block.local_rect() == rect and len(block.members()) == 3
    corner = block.mapToScene(block.local_rect().bottomRight())
    drag(v.view, corner.x(), corner.y(), corner.x(), corner.y() - 80)    # off its own
    settle(v.window)
    assert block.local_rect() == rect and len(block.members()) == 3
    corner = block.mapToScene(block.local_rect().bottomRight())
    drag(v.view, corner.x(), corner.y(), corner.x() + 60, corner.y())    # wider is fine
    settle(v.window)
    assert block.local_rect().width() > rect.width()


def test_typing_inside_a_block_puts_the_equation_in_it(v):
    block, outside, inside, after = two_checks(v)
    open_by_double_click(v, block)
    box = block.local_rect()
    point = block.mapToParent(QPointF(box.right() - 40, box.bottom() - 14))
    v.calc.place_cross(v.frame, point)
    v.keys("9=")
    v.press(Qt.Key_Return)
    assert len(block.members()) == 4


def test_a_block_says_when_its_box_takes_in_more_than_was_selected(v):
    for y, keys in ((18, "x:1"), (60, "y:2"), (100, "z:3")):
        v.type_at(36, y, "")
        v.keys(keys)
        v.press(Qt.Key_Return)
    v.calc.leave()
    made = sorted(equations(v.window), key=lambda i: i.pos().y())
    v.view.scene().clearSelection()
    made[0].setSelected(True)
    made[2].setSelected(True)
    v.window.insert_block()
    assert "also holds 1 more" in v.window.status_hint.text()
    assert "y≔2" in v.window.status_hint.text()


def test_a_blocks_menu_and_properties_offer_what_applies_to_it(v):
    from PySide6.QtWidgets import QCheckBox, QLabel, QPushButton
    block, outside, inside, after = two_checks(v)
    menu = v.window.build_context_menu(block, block.sceneBoundingRect().center())
    texts = [a.text() for a in menu.actions() if a.text()]
    for wanted in ("Self-contained", "Select its equations", "Remove block, keep equations",
                   "Delete", "Properties"):
        assert wanted in texts, wanted
    for gone in ("Set default", "Format painter", "Hide", "Flatten selection", "Apply pages…"):
        assert gone not in texts, gone
    v.view.scene().clearSelection()
    block.setSelected(True)
    v.window.refresh_selection()
    panel = v.window.properties_panel
    assert panel.findChild(QLabel, "blockHolds").text() == "3 equations"
    assert panel.findChild(QCheckBox, "blockSelfContained") is not None
    panel.findChild(QPushButton, "blockRemove").click()
    settle(v.window)
    assert blocks(v.window) == [] and len(equations(v.window)) == 6, "the equations stay"
    v.window.undo_stack.undo()
    assert len(blocks(v.window)) == 1


def test_an_equation_has_no_markup_pen_in_properties(v):
    from PySide6.QtWidgets import QGroupBox
    block, outside, inside, after = two_checks(v)
    v.view.scene().clearSelection()
    inside[0].setSelected(True)
    v.window.refresh_selection()
    titles = [g.title() for g in v.window.properties_panel.findChildren(QGroupBox)]
    assert "Appearance" not in titles and "Equation" in " ".join(titles)
    menu = v.window.build_context_menu(inside[0], inside[0].sceneBoundingRect().center())
    texts = [a.text() for a in menu.actions() if a.text()]
    assert "Format painter" not in texts and "Hide" not in texts


def test_a_closed_blocks_equation_points_and_right_clicks_as_the_block(v):
    from tests.test_usability import hover
    block, outside, inside, after = two_checks(v)
    centre = inside[0].mapToScene(inside[0].local_rect().center())
    assert v.calc.hover_cursor(centre) is None, "not WebSMath's equation arrow"
    hover(v.view, centre.x(), centre.y())
    assert v.view.cursor().shape() != Qt.IBeamCursor
    menu = v.window.build_context_menu(v.view.markup_at(centre), centre)
    assert "Self-contained" in [a.text() for a in menu.actions()]
    open_by_double_click(v, block)
    assert v.calc.hover_cursor(centre) == Qt.ArrowCursor, "open: the equation's own"
