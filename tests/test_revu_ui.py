"""The app as Bluebeam Revu (the user's request, 2026-10-14): its menu bar,
its Properties panel and toolbar, its line ends, its selection handles."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtWidgets import QComboBox, QGroupBox, QLabel

from calcforge.items.base import ARROW_HEADS, ARROW_NAMES, FILLED_HEADS
from calcforge.items.shapes import PolyItem, RectItem
from tests.test_tables import pump


def select(window, item):
    window.view.scene().clearSelection()
    item.setSelected(True)
    window.refresh_selection()
    pump()


def test_the_menu_bar_is_revus_with_a_calculation_menu(window):
    titles = [a.text().replace("&", "") for a in window.menuBar().actions() if a.menu()]
    assert titles == ["Revu", "File", "Edit", "View", "Document", "Batch", "Tools",
                      "Calculation", "Window", "Help"]
    # nothing lost: every command that had a menu still has one
    in_menus = set()

    def walk(menu):
        for action in menu.actions():
            if action.menu():
                walk(action.menu())
            else:
                in_menus.add(action)
    for action in window.menuBar().actions():
        if action.menu():
            walk(action.menu())
    for name in ("act_preferences", "act_shortcuts", "act_doc_props", "act_color_processing",
                 "act_flatten_document", "act_export_markups", "act_insert_workbook",
                 "act_add_sheet_page", "act_import_toolset", "act_name_tags", "act_find_tool"):
        assert getattr(window, name) in in_menus, name
    assert window.act_header_footer.text() == "Headers && Footers…"


def test_properties_panel_has_revus_sections_and_names(window):
    frame = window.document.pages[0].frame
    cloud = RectItem("cloud", QRectF(0, 0, 120, 60))
    frame.add_markup(cloud, QPointF(100, 100))
    select(window, cloud)
    panel = window.properties_panel
    titles = [g.title() for g in panel.findChildren(QGroupBox) if not g.isHidden()]
    assert titles[:2] == ["General", "Appearance"] and "Layout" in titles and titles[-1] == "Options"
    labels = {label.text() for label in panel.findChildren(QLabel)}
    for name in ("Cloud Properties", "Subject:", "Color:", "Fill Color:", "Hatch:", "Scale:",
                 "Opacity:", "Fill Opacity:", "Line Width:", "Style:", "Size:", "X:", "Rotation:"):
        assert name in labels, name
    # a section folds by its title, and stays folded for the next markup
    general = next(g for g in panel.findChildren(QGroupBox) if g.title() == "General")
    general.setChecked(False)
    other = RectItem("rect", QRectF(0, 0, 50, 50))
    frame.add_markup(other, QPointF(300, 300))
    select(window, other)
    general = next(g for g in panel.findChildren(QGroupBox) if g.title() == "General")
    assert not general.isChecked()
    general.setChecked(True)


def test_line_ends_are_revus_and_go_out_as_the_pdfs(window, tmp_path):
    assert [ARROW_NAMES[k] for k in ARROW_HEADS[:10]] == [
        "None", "Open", "Closed", "Open (Reversed)", "Closed (Reversed)", "Butt",
        "Diamond", "Round", "Square", "Slash"]
    assert "open" not in FILLED_HEADS and "arrow" in FILLED_HEADS
    frame = window.document.pages[0].frame
    line = PolyItem("line", [QPointF(0, 0), QPointF(200, 0)])
    line.style.arrow_start, line.style.arrow_end = "butt", "closed_reversed"
    frame.add_markup(line, QPointF(100, 100))
    select(window, line)
    start = window.properties_panel.findChild(QComboBox, "arrowStart")
    assert start.currentText() == "Butt"
    start.setCurrentIndex(start.findData("open_reversed"))
    assert line.style.arrow_start == "open_reversed"
    from calcforge.io import export as export_io
    from tests.test_format import _annotations
    path = str(tmp_path / "ends.pdf")
    export_io.export_pdf(window.document, path)
    (mark,) = [m for m in _annotations(path) if str(m["/Subtype"]) == "/Line"]
    assert [str(e) for e in mark["/LE"]] == ["/ROpenArrow", "/RClosedArrow"]


def test_bluebeam_tool_set_line_ends_come_in_as_drawn():
    from calcforge.io.btx import ARROWS
    assert ARROWS["OpenArrow"] == "open" and ARROWS["Circle"] == "dot"
    assert set(ARROWS.values()) <= set(ARROW_HEADS)


def test_the_scale_box_scales_in_proportion_and_shift_frees_it(window):
    frame = window.document.pages[0].frame
    box = RectItem("rect", QRectF(0, 0, 100, 50))
    frame.add_markup(box, QPointF(100, 100))
    select(window, box)
    corners = box.scale_points()
    assert set(corners) == {"scale_nw", "scale_ne", "scale_se", "scale_sw"}
    assert box.handle_at(corners["scale_se"]) == "scale_se"
    outer = box.scale_box()
    # dragged out to twice the scale box's width: twice the size, both ways
    box.drag_handle("scale_se", QPointF(outer.left() + outer.width() * 2, outer.bottom()))
    rect = box.local_rect()
    assert rect.width() == pytest.approx(200, abs=0.5)
    assert rect.height() == pytest.approx(100, abs=0.5)
    # Shift: width only
    outer = box.scale_box()
    box.drag_handle("scale_se", QPointF(outer.right() + 50, outer.bottom()), keep_ratio=True)
    assert box.local_rect().height() == pytest.approx(100, abs=0.5)
    assert box.local_rect().width() > 200
    # a plain line has its two ends only
    line = PolyItem("line", [QPointF(0, 0), QPointF(50, 0)])
    assert line.scale_points() == {}


def test_drawing_a_markup_puts_its_look_in_recent_tools(window):
    """Bluebeam's Recent Tools: what was just drawn, newest first, one of each look."""
    from calcforge.ui import toolsets
    from tests.test_usability import drag, markups
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    window.select_tool("cloud")
    drag(window.view, 250, 100, 350, 160)
    sets = toolsets.load_toolsets()
    assert [g.name for g in sets][:2] == [toolsets.MY_TOOLS, toolsets.RECENT_TOOLS]
    recent = sets[1].entries
    assert [e.payload.get("kind") for e in recent[:2]] == ["cloud", "rect"]
    assert all(e.mode == toolsets.PROPERTIES for e in recent)
    window.select_tool("rect")
    drag(window.view, 100, 300, 200, 360)                 # the same look again
    recent = toolsets.load_toolsets()[1].entries
    assert [e.payload.get("kind") for e in recent[:2]] == ["rect", "cloud"]
    assert len(markups(window)) == 3


def test_manage_tool_sets_shows_hides_orders_and_renames(window):
    """Revu's Manage Tool Sets, and the Tool Chest menu's tick per set."""
    from PySide6.QtCore import Qt
    from calcforge.ui import toolsets
    sets = toolsets.load_toolsets()
    sets += [toolsets.ToolSet("Steel"), toolsets.ToolSet("Welds")]
    toolsets.save_toolsets(sets)
    window.toolsets_panel.rebuild()
    dialog = window.manage_toolsets()
    names = [dialog.list.item(i).data(Qt.UserRole) for i in range(dialog.list.count())]
    assert names[0] == toolsets.MY_TOOLS and names[-2:] == ["Steel", "Welds"]
    # My Tools can't be renamed, removed or moved
    dialog.list.setCurrentRow(0)
    assert not dialog.buttons["rename"].isEnabled() and not dialog.buttons["remove"].isEnabled()
    # unticked: kept, but the chest doesn't show it
    dialog.set_shown("Steel", False)
    assert next(g for g in toolsets.load_toolsets() if g.name == "Steel").hidden
    assert window.toolsets_panel.header_for("Steel").isHidden()
    menu = window.toolsets_panel.build_chest_menu()
    steel = next(a for a in menu.actions() if a.text() == "Steel")
    assert not steel.isChecked()
    steel.setChecked(True)                                   # ticked back from the menu
    assert not window.toolsets_panel.header_for("Steel").isHidden()
    assert "Manage Tool Sets…" in [a.text() for a in menu.actions()]
    # ordered, renamed, removed
    dialog.refill("Welds")
    dialog.move(-1)
    assert [g.name for g in toolsets.load_toolsets()][-2:] == ["Welds", "Steel"]
    dialog.rename("Weld Symbols")
    dialog.remove(ask=False)
    assert [g.name for g in toolsets.load_toolsets()][-1] == "Steel"
    # and it is in Revu's place: Tools ▸ Tool Chest
    tools = next(a.menu() for a in window.menuBar().actions() if a.text().replace("&", "") == "Tools")
    chest = next(a.menu() for a in tools.actions() if a.menu() and a.text() == "Tool Chest")
    assert window.act_manage_toolsets in chest.actions()


PAT = """;; from an AutoCAD acad.pat
*ANSI31, ANSI Iron, Brick, Stone masonry
45, 0,0, 0,.125
*ANSI37, ANSI Lead, Zinc, Magnesium
45, 0,0, 0,.125
135, 0,0, 0,.125
*STEEL, kept as the built-in one
45, 0,0, 0,.5
"""


def test_hatch_patterns_import_a_pat_file_and_are_kept(window, tmp_path):
    """Revu's hatch list ends in Manage…, which brings in AutoCAD .pat patterns."""
    from calcforge.items import hatches
    from calcforge.ui.hatchpatterns import MANAGE
    name, families = hatches.parse_pat(PAT)["ansi37"]
    assert name == "ANSI37" and [f[0] for f in families] == [45, 135]
    assert families[0][4] == pytest.approx(9.0)            # an eighth of an inch, in points
    assert window.hatch_combo.itemData(window.hatch_combo.count() - 1) == MANAGE
    path = tmp_path / "mine.pat"
    path.write_text(PAT)
    dialog = window.manage_hatches()
    assert dialog.import_file(str(path)) == ["ansi31", "ansi37"]   # STEEL stays the built-in
    dialog.done(0)
    assert window.hatch_combo.findData("ansi31") > 0
    assert window.hatch_combo.itemText(window.hatch_combo.findData("ansi31")) == "ANSI31"
    # on a markup, from the Properties panel
    frame = window.document.pages[0].frame
    box = RectItem("rect", QRectF(0, 0, 120, 60))
    box.style.fill = "#ffffff"
    frame.add_markup(box, QPointF(100, 100))
    select(window, box)
    combo = window.properties_panel.findChild(QComboBox, "hatchPattern")
    combo.setCurrentIndex(combo.findData("ansi37"))
    assert box.style.hatch == "ansi37"
    combo.setCurrentIndex(combo.findData(MANAGE))           # opens the dialog, keeps the hatch
    assert box.style.hatch == "ansi37" and combo.currentData() == "ansi37"
    # kept for the next session, and can be taken out again
    hatches.load_custom()
    assert "ansi31" in hatches.CUSTOM and "ansi31" in hatches.NAMES
    dialog = window.manage_hatches()
    dialog.refill("ansi31")
    assert dialog.buttons["remove"].isEnabled()
    dialog.remove()
    dialog.refill("steel")
    assert not dialog.buttons["remove"].isEnabled()
    dialog.done(0)
    hatches.load_custom()
    assert "ansi31" not in hatches.LIBRARY and "ansi37" in hatches.LIBRARY
    for key in list(hatches.CUSTOM):
        hatches.remove_pattern(key)
    hatches.save_custom()
