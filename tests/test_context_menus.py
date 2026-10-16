"""Every right-click menu grouped and named as Revu, Excel or SMath name
them (QA round 4, 2026-10-15): Insert ▸ Insert Page Break on a sheet's cells,
Excel's short heading menus, a closed table's Edit Table, and in every menu
Title Case words and no separator at an end or two in a row."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtWidgets import QApplication, QMenu

from calcforge.items.measure import LENGTH, MeasureItem
from calcforge.items.shapes import PolyItem, RectItem
from calcforge.sheet.pagination import options
from calcforge.ui.menutidy import tidy, walk
from calcforge.ui.tools import TOOL_MAP
from tests.test_sheet_pages import runs, sheet_page, w  # noqa: F401
from tests.test_tables import cell_scene, make_table, pump


# -- the real right-click ------------------------------------------------------------------
def right_click_menu(w, scene_pos: QPointF, then=None) -> list:
    """Right-click the canvas at *scene_pos* through the real event path;
    the menu that pops up is read (and *then(menu)* run on it) and closed.
    Says the menu's entries as (path, text, enabled)."""
    view = w.view
    local = view.mapFromScene(scene_pos)
    seen: list = []

    def grab():
        menu = QApplication.activePopupWidget()
        if not isinstance(menu, QMenu):
            QTimer.singleShot(20, grab)
            return
        seen.extend((path, a.text(), a.isEnabled()) for path, a in walk(menu)
                    if not a.isSeparator())
        if then is not None:
            then(menu)
        menu.close()
    QTimer.singleShot(0, grab)
    QApplication.sendEvent(view.viewport(), QContextMenuEvent(
        QContextMenuEvent.Mouse, local, view.viewport().mapToGlobal(local)))
    pump()
    return seen


def find(menu: QMenu, *path):
    for title in path[:-1]:
        menu = next(a.menu() for a in menu.actions() if a.menu() is not None and a.text() == title)
    return next(a for a in menu.actions() if a.text() == path[-1])


def top_level(menu: QMenu) -> list:
    return [a.text() for a in menu.actions() if not a.isSeparator()]


# -- Insert ▸ Insert Page Break -----------------------------------------------------------------
def test_insert_page_break_from_a_real_right_click_on_a_sheet_cell(w):
    run = sheet_page(w)
    target = cell_scene(run, "A10")
    w.view.centerOn(target)
    pump()
    seen = right_click_menu(w, target,
                            then=lambda menu: find(menu, "Insert", "Insert Page Break").trigger())
    assert ((("Insert",), "Insert Page Break", True)) in seen
    assert (("Insert", "Chart"), "XY Scatter", True) in seen, "charts are under Insert ▸ Chart"
    assert not any(text == "Insert Chart" for _p, text, _e in seen)
    assert not any(path == ("Page Layout",) and "Page Break" in text and "Reset" not in text
                   for path, text, _e in seen), "the break is on Insert ▸, not Page Layout ▸"
    (run,) = runs(w)
    assert options(run.sheet)["breaks"] == [9], "a break above row 10, the cell right-clicked"
    # now the cell has one: Delete ▸ Remove Page Break takes it out again
    target = cell_scene(run, "A10")
    seen = right_click_menu(w, target,
                            then=lambda menu: find(menu, "Delete", "Remove Page Break").trigger())
    assert (("Delete",), "Remove Page Break", True) in seen
    (run,) = runs(w)
    assert options(run.sheet)["breaks"] == []
    w.undo_stack.undo()
    pump()
    (run,) = runs(w)
    assert options(run.sheet)["breaks"] == [9], "one undo puts it back"


# -- heading menus ---------------------------------------------------------------------------------
ROW_HEADING = ["Cut", "Copy", "Paste", "Paste Special", "Insert Rows Above", "Insert Rows Below",
               "Delete Rows", "Clear Contents", "Format Cells…", "Row Height…",
               "AutoFit Row Height", "Hide", "Unhide"]
COL_HEADING = ["Cut", "Copy", "Paste", "Paste Special", "Insert Columns Left",
               "Insert Columns Right", "Delete Columns", "Clear Contents", "Format Cells…",
               "Column Width…", "AutoFit Column Width", "Hide", "Unhide"]


def test_a_tables_row_and_column_headings_have_excels_short_menu(w):
    table = make_table(w)
    tabs = w.view.tables
    tabs.open(table, (0, 0))
    pump()
    rows, cols = table.size
    xs, ys = table.edges()
    # a right-click on row 3's number, outside the selection, picks out row 3
    heading = table.mapToScene(QPointF(-4, (ys[2] + ys[3]) / 2))
    seen = right_click_menu(w, heading)
    assert [text for path, text, _e in seen if not path] == ROW_HEADING
    assert tabs.selection() == (2, 0, 2, cols - 1)
    heading = table.mapToScene(QPointF((xs[1] + xs[2]) / 2, -4))
    seen = right_click_menu(w, heading)
    assert [text for path, text, _e in seen if not path] == COL_HEADING
    assert tabs.selection() == (0, 1, rows - 1, 1)


def test_a_sheets_headings_add_insert_page_break_and_it_works(w):
    run = sheet_page(w)
    tabs = w.view.tables
    tabs.open(run, (0, 0))
    menu = tabs.heading_menu("row", 4)
    assert top_level(menu) == ROW_HEADING + ["Insert Page Break"]
    assert tabs.selection()[0] == 4 and tabs.selection()[2] == 4
    find(menu, "Insert Page Break").trigger()
    pump()
    (run,) = runs(w)
    assert options(run.sheet)["breaks"] == [4]
    tabs.open(run, (0, 0))
    menu = tabs.heading_menu("row", 4)
    assert top_level(menu)[-2:] == ["Insert Page Break", "Remove Page Break"]
    menu = tabs.heading_menu("col", 3)
    assert top_level(menu) == COL_HEADING + ["Insert Page Break"]
    find(menu, "Insert Page Break").trigger()
    pump()
    (run,) = runs(w)
    assert options(run.sheet)["col_breaks"] == [3]


def test_the_sticky_headings_strip_gives_the_heading_menu(w):
    run = sheet_page(w)
    # scrolled down the sheet, its column letters stay along the top
    view = w.view
    w.view.set_zoom(1.5)
    pump()
    view.centerOn(cell_scene(run, "C40"))
    pump()
    strip = view.sheet_headings
    strip.refresh()
    hit = next(((kind, rect) for _r, kind, rect in strip._strips if kind == "col"), None)
    if hit is None:
        pytest.skip("the headings strip is not showing at this window size")
    point = QPoint(hit[1].center())
    seen = []

    def grab():
        menu = QApplication.activePopupWidget()
        if not isinstance(menu, QMenu):
            QTimer.singleShot(20, grab)
            return
        seen.extend(top_level(menu))
        menu.close()
    QTimer.singleShot(0, grab)
    QApplication.sendEvent(view.viewport(), QContextMenuEvent(
        QContextMenuEvent.Mouse, point, view.viewport().mapToGlobal(point)))
    pump()
    assert seen == COL_HEADING + ["Insert Page Break"]


# -- a closed table, a line ----------------------------------------------------------------------
def test_a_closed_table_offers_edit_table_and_no_outline(w):
    table = make_table(w)
    w.view.tables.close()
    w.view.scene().clearSelection()
    table.setSelected(True)
    menu = w.build_context_menu(table, table.sceneBoundingRect().center())
    labels = top_level(menu)
    assert labels[0] == "Edit Table"
    for gone in ("Control Point", "Convert to Polygon", "Arc Segment", "Round All Corners",
                 "This outline"):
        assert gone not in labels
    find(menu, "Edit Table").trigger()
    pump()
    assert w.view.tables.item is table and w.view.tables.active == (0, 0)


def _frame(w):
    return w.document.pages[0].frame


def test_a_two_point_line_cannot_be_rounded_or_arced(w):
    line = PolyItem("line", [QPointF(0, 0), QPointF(200, 30)])
    w.view.begin_snapshot([_frame(w)])
    _frame(w).add_markup(line, QPointF(100, 300))
    w.view.commit_snapshot("Line")
    menu = w.build_context_menu(line, line.mapToScene(QPointF(100, 15)))
    every = [a.text() for _p, a in walk(menu)]
    for gone in ("Round Corner", "Arc Segment", "Round All Corners"):
        assert gone not in every
    assert "Add Control Point" in [a.text() for a in find(menu, "Control Point").menu().actions()]


def test_the_markup_menu_is_in_revus_order(w):
    box = RectItem()
    box.set_local_rect(QRectF(0, 0, 120, 80))
    w.view.begin_snapshot([_frame(w)])
    _frame(w).add_markup(box, QPointF(100, 100))
    w.view.commit_snapshot("Box")
    w.view.scene().clearSelection()
    box.setSelected(True)
    menu = w.build_context_menu(box, box.mapToScene(QPointF(0, 0)))
    labels = top_level(menu)
    assert labels[:6] == ["Cut", "Copy", "Paste", "Multiply…", "Format Painter", "Delete"]
    assert find(menu, "Delete").shortcut().toString() == "Del"
    order = [labels.index(t) for t in ("Control Point", "Arc Segment", "Round All Corners",
                                       "Order", "Alignment", "Flatten", "Lock", "Hide",
                                       "Convert to Polygon", "Duplicate", "Add to Tool Chest",
                                       "Set as Default", "Apply to Pages…", "Properties")]
    assert order == sorted(order)
    points = [a.text() for a in find(menu, "Control Point").menu().actions()
              if not a.isSeparator()]
    assert points == ["Add Control Point", "Subtract Control Point", "Round Corner",
                      "Insert Break"]
    align = [a.text() for a in find(menu, "Alignment").menu().actions()]
    assert align == ["Align Left", "Align Centre", "Align Right", "Align Top", "Align Middle",
                     "Align Bottom"]
    # Round All Corners: every corner, one undo step
    before = w.undo_stack.count()
    find(menu, "Round All Corners").trigger()
    pump()
    shape = [i for i in _frame(w).markups() if isinstance(i, PolyItem)][-1]
    assert all(shape.is_rounded(v) for v in range(4))
    assert w.undo_stack.count() == before + 1


def test_the_shortcuts_shown_are_the_real_ones(w):
    box = RectItem()
    box.set_local_rect(QRectF(0, 0, 120, 80))
    _frame(w).add_markup(box, QPointF(100, 100))
    box.setSelected(True)
    menu = w.build_context_menu(box, box.mapToScene(QPointF(60, 40)))
    assert find(menu, "Multiply…").shortcut() == w.act_array.shortcut()
    assert find(menu, "Flatten").shortcut() == w.act_flatten.shortcut()
    page = w.build_context_menu(None, QPointF(5, 5))
    assert find(page, "Set Scale…").shortcut() == w.act_scale.shortcut()


# -- the other menus --------------------------------------------------------------------------------
def test_the_page_tab_and_sheet_tab_menus(w):
    labels = top_level(w.page_menu(0))
    assert labels[:5] == ["Page Setup…", "Set Scale…", "Cut Pages", "Copy Pages", "Paste Pages"]
    for wanted in ("Insert Blank Page", "Insert Pages", "Extract Pages…", "Delete Pages…",
                   "Rotate Pages", "Rename Page Label", "Reset All Page Labels",
                   "Print Pages…", "Flatten…"):
        assert wanted in labels
    # every way of putting pages in sits together, each Before or After
    inserts = ["Insert Blank Page", "Insert Spreadsheet Page", "Insert Pages",
               "Insert Image Page", "Insert Excel Workbook"]
    at = labels.index(inserts[0])
    assert labels[at:at + len(inserts)] == inserts, labels
    menu = w.page_menu(0)
    for title in inserts:
        sub = next(a.menu() for a in menu.actions() if a.text() == title)
        assert [a.text().rstrip("…") for a in sub.actions()] == ["Before", "After"], title
    assert "Spreadsheet After" not in labels
    assert labels.index("Flatten…") < labels.index("Go to Page"), \
        "CalcForge's own come after Revu's"
    menu = QMenu()
    w._tab_context_menu(w.document_tabs.tabRect(0).center(), menu)
    assert top_level(menu) == ["Close", "Close All", "Close Others", "Save", "Save As…",
                               "New Window", "Open in Split View", "Duplicate Tab"]
    sheet_page(w)
    w.sheet_tabs.refresh()
    assert top_level(w.sheet_tabs.build_menu(0)) == ["Insert Sheet", "Delete", "Rename…", "Go To"]


def test_calc_modes_page_menu_has_smaths_inserts(w):
    w.toggle_calc_mode(True)
    menu = w.build_context_menu(None, w.document.pages[0].frame.mapToScene(QPointF(80, 200)))
    labels = top_level(menu)
    for wanted in ("Insert Equation Here", "Text Region", "Calculation Block", "Plot"):
        assert wanted in labels
    find(menu, "Insert Equation Here").trigger()
    cross = w.view.calc.cross
    assert cross is not None and abs(cross[1].y() - 200) < 10
    w.toggle_calc_mode(False)
    assert "Insert Equation Here" not in top_level(w.build_context_menu(None, QPointF(80, 200)))


# -- every menu: separators and Title Case --------------------------------------------------------
def every_menu(w) -> dict:
    """The right-click menus of the window, by name."""
    frame = _frame(w)
    found = {}
    found["page (Markup)"] = w.build_context_menu(None, frame.mapToScene(QPointF(80, 200)))
    box = RectItem()
    box.set_local_rect(QRectF(0, 0, 120, 80))
    frame.add_markup(box, QPointF(100, 100))
    found["rectangle"] = w.build_context_menu(box, box.mapToScene(QPointF(0, 0)))
    line = PolyItem("line", [QPointF(0, 0), QPointF(200, 30)])
    frame.add_markup(line, QPointF(100, 300))
    found["line"] = w.build_context_menu(line, line.mapToScene(QPointF(100, 15)))
    shape = PolyItem("polygon", [QPointF(0, 0), QPointF(90, 0), QPointF(90, 60), QPointF(0, 60)])
    frame.add_markup(shape, QPointF(300, 100))
    found["polygon"] = w.build_context_menu(shape, shape.mapToScene(QPointF(90, 0)))
    for key in ("text", "callout"):
        tool = TOOL_MAP[key]
        made = tool.factory()
        made.set_local_rect(QRectF(0, 0, 120, 40))
        frame.add_markup(made, QPointF(100, 420))
        found[key] = w.build_context_menu(made, made.sceneBoundingRect().center())
    measure = MeasureItem(LENGTH, [QPointF(0, 0), QPointF(100, 0)])
    frame.add_markup(measure, QPointF(100, 500))
    found["measurement"] = w.build_context_menu(measure, measure.sceneBoundingRect().center())
    for item in (box, line, shape):
        item.setSelected(True)
    found["several"] = w.build_context_menu(box, box.sceneBoundingRect().center())
    w.view.scene().clearSelection()
    found["thumbnail"] = w.page_menu(0)
    tab = QMenu()
    w._tab_context_menu(w.document_tabs.tabRect(0).center(), tab)
    found["document tab"] = tab
    table = make_table(w, y=600)
    w.view.tables.close()
    found["table (closed)"] = w.build_context_menu(table, table.sceneBoundingRect().center())
    w.view.tables.open(table, (0, 0))
    found["table cell"] = w.view.tables.cell_menu()
    found["table row heading"] = w.view.tables.heading_menu("row", 1)
    found["table column heading"] = w.view.tables.heading_menu("col", 1)
    w.view.tables.close()
    run = sheet_page(w)
    w.view.tables.open(run, (4, 2))
    found["sheet cell"] = w.view.tables.cell_menu()
    found["sheet row heading"] = w.view.tables.heading_menu("row", 4)
    found["sheet column heading"] = w.view.tables.heading_menu("col", 2)
    w.view.tables.close()
    w.sheet_tabs.refresh()
    found["sheet tab"] = w.sheet_tabs.build_menu(0)
    w.toggle_calc_mode(True)
    found["page (Calc)"] = w.build_context_menu(None, frame.mapToScene(QPointF(80, 200)))
    from tests.test_calc_panels import an_equation
    equation = an_equation(w, "2/3=", 100, 700)
    w.view.scene().clearSelection()
    equation.setSelected(True)
    found["equation"] = w.build_context_menu(equation, equation.sceneBoundingRect().center())
    w.toggle_calc_mode(False)
    return found


def test_no_menu_has_a_stray_separator_or_a_lower_case_word_first(w):
    for name, menu in every_menu(w).items():
        menus = [((), menu)] + [(path + (a.text(),), a.menu()) for path, a in walk(menu)
                                if a.menu() is not None]
        for path, sub in menus:
            shown = [a for a in sub.actions() if a.isVisible()]
            where = f"{name} {' ▸ '.join(path)}"
            assert shown, f"{where}: an empty submenu"
            assert not shown[0].isSeparator(), f"{where}: starts with a separator"
            assert not shown[-1].isSeparator(), f"{where}: ends with a separator"
            for a, b in zip(shown, shown[1:]):
                assert not (a.isSeparator() and b.isSeparator()), f"{where}: two separators"
            for action in shown:
                text = action.text()
                if text and not action.isSeparator():
                    assert not text[0].islower(), f"{where}: {text!r} starts in lower case"


def test_tidy_strips_separators_and_empty_submenus(qapp):
    menu = QMenu()
    menu.addSeparator()
    menu.addAction("One")
    menu.addSeparator()
    menu.addSeparator()
    menu.addMenu("Empty")
    menu.addAction("Two")
    menu.addSeparator()
    tidy(menu)
    assert [("-" if a.isSeparator() else a.text()) for a in menu.actions()] == ["One", "-", "Two"]
