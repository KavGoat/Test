"""Phase 7 (decision 23): equations and calculation blocks in tool sets and
My Tools — a preview while held, then they behave as if typed where they
are put down. Driven through the real window."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor

from calcforge.calc.docsheet import PT_PER_PX
from calcforge.items.calc import CalcBlockItem, CalcItem
from calcforge.ui import toolsets
from calcforge.ui.panels import entry_thumbnail
from tests.test_calc_blocks import blocks, equations, settle, shown, two_checks, v  # noqa: F401
from tests.test_usability import click


def keep(window, item, into=toolsets.MY_TOOLS):
    groups = toolsets.load_toolsets()
    group = next(g for g in groups if g.name == into)
    entry = toolsets.entry_for_block(item) if isinstance(item, CalcBlockItem) \
        else toolsets.entry_for(item, toolsets.COPY)
    group.entries.append(entry)
    toolsets.save_toolsets(groups)
    window.toolsets_panel.rebuild(keep=into)
    return entry


def put_down(v, entry, x_px, y_px):
    """Hold the tool and click the page there (the tool's bottom-left lands
    under the pointer)."""
    v.window.select_tool("select")
    v.window.use_tool_entry(entry)
    at = v.view.mapFromScene(v.scene_point(x_px, y_px))
    click(v.view, at.x(), at.y())
    settle(v.window)


def inked(pixmap) -> int:
    image = pixmap.toImage()
    return sum(1 for x in range(image.width()) for y in range(image.height())
               if QColor(image.pixel(x, y)).alpha() > 0
               and QColor(image.pixel(x, y)).lightness() < 160)


def a_kept_equation(v, keys):
    v.type_at(36, 18, "")
    v.keys(keys)
    v.press(0x01000004)                                   # Return
    v.calc.leave()
    (item,) = equations(v.window)
    return item


def test_a_kept_equation_has_a_picture_of_itself(v):
    item = a_kept_equation(v, "x*3=")
    entry = keep(v.window, item)
    assert inked(entry_thumbnail(entry)) > 20, "the row shows the equation, not a blank"
    held = v.view
    held.set_pending_stamp(entry)
    extent = held.pending_extent()
    assert extent.width() > 25 and extent.height() > 12, \
        "the held tool is the size of the equation it will put down"
    held.clear_pending_tool()


def test_a_kept_equation_calculates_where_it_is_put_down(v):
    x_def = a_kept_equation(v, "x:2")
    v.type_at(36, 90, "")
    v.keys("x*3=")
    v.press(0x01000004)
    v.calc.leave()
    use = next(i for i in equations(v.window) if i is not x_def)
    entry = keep(v.window, use)
    v.window.document.pages[0].frame.remove_markup(use)
    settle(v.window)

    put_down(v, entry, 90, 300)                            # below x:2
    below = [i for i in equations(v.window) if i is not x_def]
    assert len(below) == 1 and shown(below[0]) == "6"
    # on SMath's grid, as if typed there
    x, y = below[0].reading_position()
    assert x % 9 == pytest.approx(0) and y % 9 == pytest.approx(0)

    v.view.scene().clearSelection()
    x_def.setPos(QPointF(36 * PT_PER_PX, 600 * PT_PER_PX))   # now defined after it
    settle(v.window)
    assert "not defined" in shown(below[0])


def test_a_kept_block_comes_back_with_its_equations_ungrouped(v):
    block, outside, inside, after = two_checks(v)
    v.window.set_block_self_contained([block], True)
    entry = keep(v.window, block)
    assert entry.payload["type"] == toolsets.GROUP and len(entry.payload["items"]) == 4
    assert inked(entry_thumbnail(entry)) > 20

    put_down(v, entry, 400, 700)
    copies = [b for b in blocks(v.window) if b is not block]
    assert len(copies) == 1 and copies[0].self_contained
    members = copies[0].members()
    assert len(members) == 3
    assert all(not m.group for m in members + copies), \
        "a block holds its equations itself: they are not a markup group"
    by_text = {m.text(): m for m in members}
    assert shown(by_text["x+y="]) == "7"
