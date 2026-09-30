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


def test_pages_and_self_contained_blocks_are_shown(v):
    block, outside, inside, after = two_checks(v)
    v.window.set_block_self_contained([block], True)
    rows = panel_rows(v)
    assert ["x", "1", "", "Page 1"] == rows[0]
    assert rows[1][0] == "y" and rows[1][3] == "Page 1 · block"


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
