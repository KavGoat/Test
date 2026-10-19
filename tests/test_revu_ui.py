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
    assert titles == ["CalcForge", "File", "Edit", "View", "Document", "Batch", "Tools",
                      "Calculation", "Window", "Help"]
    # nothing lost: every command that had a menu still has one
    in_menus = set()

    def walk(menu):
        for action in menu.actions():
            # an insert command carries its own Before / After submenu
            in_menus.add(action)
            if action.menu():
                walk(action.menu())
    for action in window.menuBar().actions():
        if action.menu():
            walk(action.menu())
    for name in ("act_preferences", "act_shortcuts", "act_doc_props", "act_color_processing",
                 "act_flatten_document", "act_export_markups", "act_insert_workbook",
                 "act_add_sheet_page", "act_import_toolset", "act_name_tags", "act_find_tool"):
        assert getattr(window, name) in in_menus, name
    assert window.act_header_footer.text() == "Headers && Footers…"
    # every command the window has is somewhere to be found (the user,
    # 2026-10-15: "make sure you didn't delete anything"); the Markup | Calc
    # switch is its own button on the menu row
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QToolBar
    for bar in window.findChildren(QToolBar):
        in_menus.update(bar.actions())
    lost = [name for name, value in vars(window).items()
            if name.startswith("act_") and isinstance(value, QAction)
            and value not in in_menus and name != "act_calc_mode"]
    assert lost == []
    # Excel and the other imports beside Export, where they are looked for
    (file_menu,) = [a.menu() for a in window.menuBar().actions() if a.text() == "&File"]
    (imports,) = [a.menu() for a in file_menu.actions() if a.text() == "Import"]
    assert window.act_insert_workbook in imports.actions()
    assert window.act_insert_pdf in imports.actions()


def test_properties_panel_has_revus_sections_and_names(window):
    frame = window.document.pages[0].frame
    cloud = RectItem("cloud", QRectF(0, 0, 120, 60))
    frame.add_markup(cloud, QPointF(100, 100))
    select(window, cloud)
    panel = window.properties_panel
    titles = [g.title() for g in panel.findChildren(QGroupBox) if not g.isHidden()]
    assert titles[:2] == ["General", "Appearance"] and "Layout" in titles and titles[-1] == "Options"
    labels = {label.text() for label in panel.findChildren(QLabel)}
    for name in ("Cloud Properties", "Subject:", "Colour:", "Fill Colour:", "Hatch:", "Scale:",
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
    # the scale box's corner dragged to where it stands for a box twice as
    # wide: twice the size, both ways, about the shape's opposite corner,
    # which stays put (2026-10-19: scaled about the scale box's own corner,
    # a few points off the shape, the shape crept with every step)
    pad = outer.right() - box.local_rect().right()
    box.drag_handle("scale_se", QPointF(box.local_rect().left() + 200 + pad, outer.bottom()))
    rect = box.local_rect()
    assert rect.width() == pytest.approx(200, abs=0.5)
    assert rect.height() == pytest.approx(100, abs=0.5)
    assert rect.topLeft() == QPointF(0, 0)
    # Shift: width only
    outer = box.scale_box()
    box.drag_handle("scale_se", QPointF(outer.right() + 50, outer.bottom()), keep_ratio=True)
    assert box.local_rect().height() == pytest.approx(100, abs=0.5)
    assert box.local_rect().width() > 200
    # a plain line has its two ends only
    line = PolyItem("line", [QPointF(0, 0), QPointF(50, 0)])
    assert line.scale_points() == {}


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
    """Revu's hatch list opens with Manage… (the user's Revu, 2026-10-15), which
    brings in AutoCAD .pat patterns; then (None) and the patterns."""
    from calcforge.items import hatches
    from calcforge.ui.hatchpatterns import MANAGE
    name, families = hatches.parse_pat(PAT)["ansi37"]
    assert name == "ANSI37" and [f[0] for f in families] == [45, 135]
    assert families[0][4] == pytest.approx(9.0)            # an eighth of an inch, in points
    assert window.hatch_combo.itemData(0) == MANAGE
    assert window.hatch_combo.itemText(window.hatch_combo.findData("")) == "(None)"
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


def _a_chest(window):
    from calcforge.ui import toolsets
    frame = window.document.pages[0].frame
    sets = toolsets.load_toolsets()
    steel = toolsets.ToolSet("Steel")
    for i in range(7):
        box = RectItem("rect", QRectF(0, 0, 80, 40))
        frame.add_markup(box, QPointF(50, 50))
        sets[0].entries.append(toolsets.entry_for(box, toolsets.COPY, f"Box {i + 1}"))
    for i in range(3):
        line = PolyItem("line", [QPointF(0, 0), QPointF(60, 20)])
        frame.add_markup(line, QPointF(50, 200))
        steel.entries.append(toolsets.entry_for(line, toolsets.COPY, f"Beam {i + 1}"))
    toolsets.save_toolsets(sets + [steel])
    panel = window.toolsets_panel
    panel.rebuild()
    return panel


def test_the_tool_chest_fills_its_panel_and_shows_every_tool(window):
    """Symbol view: as wide as the panel, as many rows as its tools need
    (a set of seven showed three, with a gap down the right, 2026-10-14)."""
    window.show()
    window.show_panel("dock_toolsets", True)
    panel = _a_chest(window)
    pump()
    tree = panel.tree
    assert tree.columnWidth(0) == tree.viewport().width()
    for name in ("My Tools", "Steel"):
        bar = panel.headers[name]
        grid = bar.grid
        per_row = max(1, (grid.width() - 2 * grid.frameWidth() - 2) // grid.cell())
        rows = -(-grid.count() // per_row)
        assert grid.height() >= rows * grid.cell()
        assert tree.visualItemRect(panel.header_for(name)).height() >= bar.bar.height() + grid.height()
        assert bar.width() == tree.viewport().width()


def test_a_tool_set_has_revus_symbol_list_and_detail_views(window):
    from calcforge.ui import panels
    panel = _a_chest(window)
    header = panel.header_for("Steel")
    assert all(header.child(i).isHidden() for i in range(header.childCount()))
    panel.select_set("Steel")
    menu = panel.build_set_menu()
    names = [a.text() for a in menu.actions()][:3]
    assert names == ["Symbol", "List", "Detail"]
    next(a for a in menu.actions() if a.text() == "List").trigger()
    header = panel.header_for("Steel")
    assert not any(header.child(i).isHidden() for i in range(header.childCount()))
    assert header.child(0).data(0, panel.VIEW_ROLE) == panels.LIST
    assert panel.headers["Steel"].grid is None
    panel.set_view("Steel", panels.DETAIL)
    row = panel.header_for("Steel").child(0)
    assert row.data(0, panel.DESC_ROLE) == "Line · Drawing Mode"
    # kept for the next time the chest is opened
    again = panels.ToolSetsPanel(window)
    assert again.view_of("Steel") == panels.DETAIL and again.view_of("My Tools") == panels.SYMBOL


def test_a_tool_has_revus_modes_scale_order_and_copy(window):
    from calcforge.ui import toolsets
    panel = _a_chest(window)
    panel.select_entry(toolsets.MY_TOOLS, 1)
    labels = [a.text() for a in panel.build_menu().actions()]
    for wanted in ("Use Tool", "Drawing Mode", "Properties Mode", "Scale", "Move Up",
                   "Move Down", "Copy", "Paste", "Rename…", "Remove"):
        assert wanted in labels, wanted
    menu = panel.build_menu()
    drawing = next(a for a in menu.actions() if a.text() == "Drawing Mode")
    assert drawing.isChecked()
    next(a for a in menu.actions() if a.text() == "Properties Mode").trigger()
    assert panel.current_entry().mode == toolsets.PROPERTIES
    scale = next(a for a in panel.build_menu().actions() if a.text() == "Scale")
    assert not scale.isEnabled(), "a tool drawn fresh has nothing to scale"
    panel.set_mode(toolsets.COPY)
    panel.move_entry(-1)
    assert [e.label for e in toolsets.load_toolsets()[0].entries][:2] == ["Box 2", "Box 1"]
    panel.copy_entry()
    panel.select_set("Steel")
    panel.paste_entry()
    assert [e.label for e in next(g for g in toolsets.load_toolsets()
                                  if g.name == "Steel").entries][-1] == "Box 2"


def test_a_scaled_tool_keeps_its_real_size_on_a_page_of_another_scale(window):
    """Revu's Scale: kept off a 1:100 page, put down on a 1:50 one, twice
    the size on the paper — the same size in the world."""
    from calcforge.core.document import PageScale
    from calcforge.ui import toolsets
    window.add_page()
    first, second = window.document.pages[0], window.document.pages[1]
    first.scale = PageScale.from_ratio(100)
    second.scale = PageScale.from_ratio(50)
    box = RectItem("rect", QRectF(0, 0, 100, 40))
    first.frame.add_markup(box, QPointF(100, 100))
    entry = toolsets.entry_for(box, toolsets.COPY, "Desk")
    assert entry.mm_per_pt == pytest.approx(100 * 25.4 / 72, rel=1e-6)
    assert entry.size_on(second) == 1.0, "Scale off: as kept"
    entry.scaled = True
    assert entry.size_on(second) == pytest.approx(2.0)
    assert toolsets.ToolEntry.from_dict(entry.to_dict()).scaled
    view = window.view
    view.set_pending_stamp(entry)
    before = set(second.frame.markups())
    view.place_pending_stamp(second.frame.mapToScene(QPointF(300, 400)))
    (placed,) = [i for i in second.frame.markups() if i not in before]
    size = placed.mapRectToParent(placed.local_rect())
    assert size.width() == pytest.approx(200, abs=0.5)
    assert size.height() == pytest.approx(80, abs=0.5)
