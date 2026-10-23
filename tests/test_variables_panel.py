"""Phase 7 (decision 21): the Variables panel — every name the document
defines with its value, unit, page and error; clicking a row goes to it.
Driven through the real window."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from tests.test_calc_blocks import equations, settle, two_checks, v  # noqa: F401


def type_line(v, y, keys, x=36):
    v.type_at(x, y, "")
    v.keys(*(keys if isinstance(keys, tuple) else (keys,)))
    v.press(Qt.Key_Return)
    v.calc.leave()


def panel_rows(v):
    v.window.show_panel("dock_variables", True)
    settle(v.window)
    QApplication.instance().processEvents()
    panel = v.window.variables_panel
    panel.refresh()
    tree = panel.tree
    return [[tree.topLevelItem(i).text(c) for c in range(4)]
            for i in range(tree.topLevelItemCount())]


def tree_rows(v) -> list:
    """Every row at every depth: (indent and name, page column)."""
    tree = v.window.variables_panel.tree
    out = []

    def walk(node, depth):
        out.append(("  " * depth + node.text(0), node.text(3)))
        for i in range(node.childCount()):
            walk(node.child(i), depth + 1)
    for i in range(tree.topLevelItemCount()):
        walk(tree.topLevelItem(i), 0)
    return out


def test_the_variables_panel_is_on_the_rail(v):
    assert "dock_variables" in v.window.right_rail.order()
    v.window.show_panel("dock_variables", True)
    assert v.window.dock_variables.isVisible()


def test_it_lists_value_unit_page_and_error(v):
    type_line(v, 18, "M:12.5'kN")
    type_line(v, 54, "L:6'm")
    type_line(v, 90, ("f(t", Qt.Key_Right, ":t^2"))
    type_line(v, 126, "w:q*2")                                 # q is not defined
    rows = panel_rows(v)
    assert rows[0] == ["M", "12.5", "kN", "Page 1"]
    assert rows[1] == ["L", "6", "m", "Page 1"]
    assert rows[2][0] == "f(·)" and rows[2][1] == "function"
    assert rows[3][0] == "w" and "not defined" in rows[3][1]
    red = v.window.variables_panel.tree.topLevelItem(3).foreground(1).color().name()
    assert red == "#c92a2a"


def test_it_follows_the_calculation(v):
    type_line(v, 18, "x:2")
    assert panel_rows(v)[0][1] == "2"
    (item,) = equations(v.window)
    v.focus_item(item)
    item.editor.set_cursor(item.editor.root, len(item.editor.root))
    v.keys("5")
    v.press(Qt.Key_Return)
    assert panel_rows(v)[0][1] == "25"


def test_each_block_is_a_section_of_its_own_saying_whether_it_is_self_contained(v):
    """The user, 2026-10-24: "variable panel should clearly show what
    variables in a self contained block like a workbook section", then
    "each block should show as its own section" — where it comes in
    reading order (their pick), its heading saying whether it is
    self-contained."""
    block, outside, inside, after = two_checks(v)
    v.window.set_block_self_contained([block], True)
    rows = panel_rows(v)
    assert ["x", "1", "", "Page 1"] == rows[0]
    heading = "Block 1 · page 1 · self-contained (2 names)"
    assert [r[0] for r in rows] == ["x", heading], "the block's under its own heading"
    assert tree_rows(v) == [("x", "Page 1"), (heading, ""),
                            ("  y", "Page 1"), ("  x", "Page 1")]
    panel = v.window.variables_panel
    head = panel.group_node("block:" + block.uid)
    assert not head.isExpanded(), "closed to start"
    panel.go_to(head)                               # a click on it opens it
    assert head.isExpanded() and "block:" + block.uid in panel.opened
    panel.refresh()
    assert panel.group_node("block:" + block.uid).isExpanded(), "kept open"
    v.window.set_block_self_contained([block], False)
    panel_rows(v)
    assert [r[0] for r in tree_rows(v)][1] == "Block 1 · page 1 (2 names)"
    panel.toggle_group("block:" + block.uid)       # closed again
    panel.filter.setText("y")
    assert panel.group_node("block:" + block.uid).isExpanded(), "finding looks inside"
    panel.filter.setText("")


def test_clicking_a_row_goes_to_the_equation(v):
    type_line(v, 18, "x:2")
    type_line(v, 900, "z:x+1")
    panel_rows(v)
    tree = v.window.variables_panel.tree
    node = tree.topLevelItem(1)
    rect = tree.visualItemRect(node)
    QTest.mouseClick(tree.viewport(), Qt.LeftButton, pos=rect.center())
    chosen = v.window.selected_items()
    assert len(chosen) == 1 and chosen[0].text() == "z≔x+1"
    view = v.view
    assert view.mapToScene(view.viewport().rect()).boundingRect().contains(
        chosen[0].sceneBoundingRect().center())


def test_the_filter_finds_a_name(v):
    type_line(v, 18, "x:2")
    type_line(v, 54, "beam:3")
    panel_rows(v)
    panel = v.window.variables_panel
    panel.filter.setText("be")
    assert panel.tree.topLevelItemCount() == 1
    assert panel.tree.topLevelItem(0).text(0) == "beam"
