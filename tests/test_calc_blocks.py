"""Phase 7: the calculation block — a markup of its own that holds
equations, and with Self-contained on keeps what they define to itself.
Driven through the real window."""
from __future__ import annotations

import pymupdf
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import tests.calc.test_calcforge_window as cw
from markforge.calc.docsheet import PT_PER_PX, sheet_for
from markforge.calc.engine.display import display_text
from markforge.items.calc import CalcBlockItem, CalcItem
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


def test_a_click_inside_the_block_starts_an_equation_there(v):
    block, outside, inside, after = two_checks(v)
    frame = v.frame
    inside_point = block.mapToScene(block.local_rect().bottomRight() - QPointF(30, 12))
    assert not block.contains(block.mapFromScene(inside_point)), \
        "the block is picked by its frame only"
    v.view.scene().clearSelection()
    v.calc.place_cross(frame, frame.mapFromScene(inside_point))
    v.keys("9=")
    v.press(Qt.Key_Return)
    assert len(equations(v.window)) == 7
    assert any(i.text() == "9=" for i in block.members())


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
    from markforge.items.calc import CalcDrawingItem
    block, outside, inside, after = two_checks(v)
    drawing = CalcDrawingItem.of(block)
    assert "<path" in drawing.stamp_svg or "<rect" in drawing.stamp_svg
