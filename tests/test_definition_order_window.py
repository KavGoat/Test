"""The user's report (2026-10-17), as the user did it, in the real window:
test:=5 kN typed on page 1 in Calc mode; a spreadsheet page put in after it
from the Thumbnails right-click menu; 2 typed into a cell and the cell named
test from its right-click Variable box (or the Name Box); test= typed on the
page at the end. It showed 5 kN: the sheet's names were only read when no
equation anywhere above defined the name. As in SMath, the latest
definition before an equation wins, page by page, top to bottom, whatever
defines it — so test= shows 2.

Typed with real keys, clicked and right-clicked where things are drawn."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from calcforge.calc.docsheet import sheet_for
from calcforge.calc.engine.display import display_text
from calcforge.items.sheetpage import SheetRunItem
from tests.test_smath_name_boxes import right_click, type_into_the_menu
from tests.test_tables import cell_scene, click, enter, type_text
from tests.test_usability import click as click_at

def pump(times=3):
    for _ in range(times):
        QApplication.instance().processEvents()


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.interactive_prompts = False
    window.view.set_zoom(1.0)
    return window


# -- doing it as a person does ------------------------------------------------------------------

def calc_mode(w):
    pump()
    w.view.setFocus()
    pump()
    QTest.keyClick(w.view.viewport(), Qt.Key_F12)
    pump()
    assert w.view.calc.mode == "calc"


def equation(w, page, y_pt, text, x_pt=72):
    """Click bare paper on *page* and type *text* with real keys; Enter, Esc."""
    w.go_to_page(page)
    pump()
    frame = w.document.pages[page].frame
    point = frame.mapToScene(QPointF(x_pt, y_pt))
    w.view.centerOn(point)
    pump()
    click_at(w.view, point.x(), point.y())
    pump()
    for ch in text:
        QTest.keyClicks(w.view.viewport(), ch)
    item = w.view.calc.item
    assert item is not None, f"typing {text!r} started an equation"
    QTest.keyClick(w.view.viewport(), Qt.Key_Return)
    QTest.keyClick(w.view.viewport(), Qt.Key_Escape)
    w.view.calc.leave()
    pump()
    return item


def shown(item):
    r = item.region
    return r.error.message if r.error is not None else display_text(r.display) if r.display else None


def click_through(path, seen):
    """When a menu is up: click each entry of *path* in turn with the mouse
    (a submenu's entry opens it)."""
    state = {"i": 0, "last": None, "tries": 0}

    def step():
        popup = QApplication.activePopupWidget()
        state["tries"] += 1
        if state["tries"] > 200:
            seen["stuck"] = path[state["i"]]
            if popup is not None:
                popup.close()
            return
        if popup is None or popup is state["last"]:
            QTimer.singleShot(30, step)
            return
        wanted = path[state["i"]]
        action = next((a for a in popup.actions() if a.text().replace("&", "") == wanted), None)
        if action is None:
            seen.setdefault("menus", []).append([a.text() for a in popup.actions()])
            QTimer.singleShot(30, step)
            return
        centre = popup.actionGeometry(action).center()
        QTest.mouseMove(popup, centre)
        QTest.mouseClick(popup, Qt.LeftButton, Qt.NoModifier, centre)
        seen.setdefault("clicked", []).append(wanted)
        state["last"] = popup
        state["i"] += 1
        if state["i"] < len(path):
            QTimer.singleShot(60, step)
    QTimer.singleShot(60, step)


def insert_sheet_page_after(w, page):
    """Thumbnails ▸ right-click the page ▸ Insert Spreadsheet Page ▸ After."""
    w.show_panel("dock_pages", True)
    pump()
    strip = w.pages_panel.list
    rect = strip.visualItemRect(strip.item(page))
    seen = {}
    click_through(["Insert Spreadsheet Page", "After"], seen)
    local = rect.center()
    QApplication.sendEvent(strip.viewport(), QContextMenuEvent(
        QContextMenuEvent.Mouse, local, strip.viewport().mapToGlobal(local)))
    pump(6)
    assert seen.get("clicked") == ["Insert Spreadsheet Page", "After"], seen
    run = next(i for i in w.view.scene().items() if isinstance(i, SheetRunItem))
    return run


def type_into_cell(w, run, a1, text):
    w.view.centerOn(cell_scene(run, a1))
    pump()
    click(w, cell_scene(run, a1))
    pump()
    assert w.view.tables.item is run
    type_text(w, text)
    enter(w)


def name_cell_from_its_menu(w, run, a1, name):
    """Right-click the cell ▸ the Variable box at the top ▸ type the name, Enter."""
    w.view.centerOn(cell_scene(run, a1))
    pump()
    click(w, cell_scene(run, a1))
    pump()
    seen = {}
    type_into_the_menu("cellVariable", list(name), seen)
    right_click(w.view, cell_scene(run, a1))
    pump()
    assert seen.get("text") == name, seen


def the_report(w):
    """Page 1: test:=5 kN. A sheet page after it, 2 in A1 named test. A page at the end."""
    w.add_page(0)                                  # the page at the end
    pump()
    calc_mode(w)
    first = equation(w, 0, 60, "test:5'kN")
    assert shown(first) is None and first.region.error is None
    run = insert_sheet_page_after(w, 0)
    assert len(w.document.pages) == 3
    assert run.parentItem().page is w.document.pages[1], "the sheet is page 2"
    type_into_cell(w, run, "A1", "2")
    name_cell_from_its_menu(w, run, "A1", "test")
    assert run.sheet.workbook.find_name("test", None) is not None
    return first, run


# -- the report, and its relatives -----------------------------------------------------------

def bold_rows(panel):
    """(name, source, page) of the rows drawn bold: the definitions in force."""
    tree = panel.tree
    nodes = (tree.topLevelItem(i) for i in range(tree.topLevelItemCount()))
    return [(r.name, r.source, r.page) for r in
            (panel.rows[n.data(0, Qt.UserRole)] for n in nodes
             if n.data(0, Qt.UserRole) is not None and n.font(0).bold())]


def test_the_named_cell_after_the_equation_wins(w):
    first, _run = the_report(w)
    asked = equation(w, 2, 60, "test=")
    assert shown(asked) == "2", "the sheet's test is the latest before test=: 2, no unit"
    # both definitions are in the Variables panel
    w.show_panel("dock_variables", True)
    panel = w.variables_panel
    panel.refresh()
    pump()
    assert [r.name for r in panel.rows].count("test") == 2
    # nothing picked: in force at the end of the document, the sheet's
    assert bold_rows(panel) == [("test", "Table", 2)]
    assert "end of the document" in panel.in_force_note.text()
    # click the test:=5 kN equation on page 1: in force there, its own
    w.go_to_page(0)
    pump()
    w.view.centerOn(first.sceneBoundingRect().center())
    pump()
    centre = first.sceneBoundingRect().center()
    click_at(w.view, centre.x(), centre.y())
    pump(6)
    assert w.view.calc.item is first
    assert bold_rows(panel) == [("test", "Equation", 1)]
    assert "selected equation" in panel.in_force_note.text()
    w.view.calc.leave()
    # click test= on page 3: it reads the sheet's
    w.go_to_page(2)
    pump()
    w.view.centerOn(asked.sceneBoundingRect().center())
    pump()
    centre = asked.sceneBoundingRect().center()
    click_at(w.view, centre.x(), centre.y())
    pump(6)
    assert bold_rows(panel) == [("test", "Table", 2)], "test= reads the sheet's"
    w.view.calc.leave()
    # a row clicked in the panel picks its equation, and the bold follows it
    tree = panel.tree
    node = next(tree.topLevelItem(i) for i in range(tree.topLevelItemCount())
                if tree.topLevelItem(i).data(0, Qt.UserRole) is not None
                and panel.rows[tree.topLevelItem(i).data(0, Qt.UserRole)].source == "Equation")
    QTest.mouseClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier,
                     tree.visualItemRect(node).center())
    pump(6)
    assert first.isSelected()
    assert bold_rows(panel) == [("test", "Equation", 1)]


def test_the_name_box_names_the_cell_too(w):
    w.add_page(0)
    pump()
    calc_mode(w)
    equation(w, 0, 60, "test:5'kN")
    run = insert_sheet_page_after(w, 0)
    type_into_cell(w, run, "B2", "2")
    click(w, cell_scene(run, "B2"))
    pump()
    box = w.formula_bar.name
    QTest.mouseClick(box, Qt.LeftButton, Qt.NoModifier, QPoint(10, box.height() // 2))
    box.selectAll()
    QTest.keyClicks(box, "test")
    QTest.keyClick(box, Qt.Key_Return)
    pump()
    dn = run.sheet.workbook.find_name("test", None)
    assert dn is not None and not dn.variable
    # the Name Box's name is the spreadsheet's own: read as Sheet.test, not
    # bare (the user, 2026-10-21) — test= reads the equation's
    asked = equation(w, 2, 60, "test=")
    assert shown(asked) == "5 kN"
    from calcforge.sheet.docbook import sheet_ident
    qualified = equation(w, 2, 120, f"{sheet_ident(run.sheet.name)}.test=")
    assert shown(qualified) == "2"


def test_an_equation_after_the_named_cell_wins(w):
    """The reverse: the cell named test above test:=5 kN."""
    w.add_page(0)
    pump()
    calc_mode(w)
    run = insert_sheet_page_after(w, 0)            # page 2 is the sheet
    type_into_cell(w, run, "A1", "2")
    name_cell_from_its_menu(w, run, "A1", "test")
    defined = equation(w, 2, 60, "test:5'kN")
    asked = equation(w, 2, 120, "test=")
    early = equation(w, 0, 60, "test*2=")    # test= alone would be test:= (SMath)
    assert shown(asked) == "5 kN"
    assert shown(early) == "test - not defined.", "only the sheet below defines it"
    assert defined.region.error is None


def test_redefinition_on_the_same_page(w):
    _first, _run = the_report(w)
    before = equation(w, 2, 60, "test=")
    equation(w, 2, 120, "test:7'm")
    after = equation(w, 2, 180, "test=")
    above = equation(w, 0, 120, "test=")
    assert [shown(above), shown(before), shown(after)] == ["5 kN", "2", "7 m"]


def test_a_self_contained_block_reads_the_latest_above_it(w):
    """A Self-contained block reads everything above it — the sheet's test
    included, being the latest — and keeps its own test inside."""
    from calcforge.items.calc import CalcBlockItem
    _first, _run = the_report(w)
    inside = [equation(w, 2, 120, "test="), equation(w, 2, 160, "test:8"),
              equation(w, 2, 200, "test=")]
    after = equation(w, 2, 400, "test=")
    w.view.scene().clearSelection()
    for item in inside:
        item.setSelected(True)
    w.block_self_contained_answer = False          # made not self-contained, then ticked
    w.create_block()
    (block,) = [i for i in w.view.scene().items() if isinstance(i, CalcBlockItem)]
    menu = w.build_context_menu(block, block.sceneBoundingRect().topLeft())
    (toggle,) = [a for a in menu.actions() if a.text() == "Self-Contained"]
    toggle.trigger()
    pump()
    sheet_for(w.document).settle()
    pump()
    assert block.self_contained
    assert [shown(inside[0]), shown(inside[2])] == ["2", "8"]
    assert shown(after) == "2", "the block's own test stays inside it"


def test_a_cell_reads_the_latest_equation_above_it(w):
    """A cell formula reading an equation variable sees the latest definition
    above its sheet."""
    w.add_page(0)
    pump()
    calc_mode(w)
    equation(w, 0, 60, "w:5'kN")
    equation(w, 0, 120, "w:3'kN")
    run = insert_sheet_page_after(w, 0)
    equation(w, 2, 60, "w:100'kN")
    type_into_cell(w, run, "A1", "=CALC(w)*2")
    pump(6)
    from calcforge.sheet.numfmt import format_value
    assert format_value(run.sheet.value(0, 0)).text == "6 kN"


def test_after_a_section_break_the_cell_must_be_global(w):
    from calcforge.ui import calcsections
    first, run = the_report(w)
    w.view.calc.leave()
    calcsections.set_break(w, 2, True)
    pump()
    asked = equation(w, 2, 60, "test=")
    assert shown(asked) == "test is in an earlier calculation section and not global."
    # the equation made global: it is read past the break, the sheet still is not
    from calcforge.ui.calcmenu import change
    change(w, [first], "Make global", lambda r: setattr(r, "is_global", True))
    pump(6)
    assert shown(asked) == "5 kN"
    # the cell made global too: it is the later definition
    calcsections.set_cells_global(w, run, (0, 0, 0, 0), True)
    pump(6)
    assert shown(asked) == "2"


def test_a_named_measurement_after_the_sheet_wins(w):
    """A measurement named test (its right-click Variable box) on the last
    page, above test=: the latest definition, so its length."""
    from calcforge.items.measure import LENGTH, MeasureItem
    _first, _run = the_report(w)
    frame = w.document.pages[2].frame
    measure = MeasureItem(LENGTH, [QPointF(0, 0), QPointF(200, 0)])
    w.view.begin_snapshot([frame])
    frame.add_markup(measure, QPointF(72, 40))
    w.view.commit_snapshot("Measure")
    w.go_to_page(2)
    w.view.centerOn(measure.sceneBoundingRect().center())
    pump()
    seen = {}
    type_into_the_menu("measureVariable", list("test"), seen)
    right_click(w.view, measure.sceneBoundingRect().center())
    pump(6)
    assert measure.variable == "test"
    asked = equation(w, 2, 200, "test=")
    above = equation(w, 2, 10, "test=")
    assert shown(above) == "2", "above the measurement: the sheet's"
    assert shown(asked) == "0.0706 m", "200 pt at 1:1, the measurement's length"


def test_a_sheet_below_is_not_defined_until_it_moves_above(w):
    """As in SMath (the user's answer, 2026-10-17): the sheet's test is
    below the equation, so test is not defined there — the red error under
    it; the sheet page moved above (Thumbnails ▸ right-click ▸ Move Up) and
    the error goes."""
    calc_mode(w)
    asked = equation(w, 0, 60, "test*2=")
    run = insert_sheet_page_after(w, 0)
    type_into_cell(w, run, "A1", "2")
    name_cell_from_its_menu(w, run, "A1", "test")
    pump(6)
    assert shown(asked) == "test - not defined.", "only the sheet below defines it"
    # Thumbnails: right-click the sheet's page ▸ Move Up
    strip = w.pages_panel.list
    rect = strip.visualItemRect(strip.item(1))
    seen = {}
    click_through(["Move Up"], seen)
    local = rect.center()
    QApplication.sendEvent(strip.viewport(), QContextMenuEvent(
        QContextMenuEvent.Mouse, local, strip.viewport().mapToGlobal(local)))
    pump(8)
    assert seen.get("clicked") == ["Move Up"], seen
    assert run.parentItem().page is w.document.pages[0], "the sheet is page 1 now"
    assert asked.region.error is None and shown(asked) == "4"
    # and back down with undo: not defined again
    w.undo_something()
    pump(8)
    again = next(i for i in sheet_for(w.document).items.values()
                 if i.region.editor.root.text().startswith("test"))
    assert shown(again) == "test - not defined."


def test_a_table_dragged_above_the_equation_defines_its_names(w):
    """A table on the same page, below the equation: its cell is not
    defined there; dragged above it with the mouse (Markup mode), it is."""
    from calcforge.calc.docsheet import PT_PER_PX
    from calcforge.items.table import TableItem
    from tests.test_usability import drag
    calc_mode(w)
    asked = equation(w, 0, 200, "T1.A1*2=")
    frame = w.document.pages[0].frame
    table = TableItem(2, 2)
    w.view.begin_snapshot([frame])
    frame.add_markup(table, QPointF(300 * PT_PER_PX, 400 * PT_PER_PX))
    table.sheet.workbook.set_input(table.sheet, 0, 0, "5")
    table.sheet.workbook.rename_sheet(table.sheet, "T1")
    w.view.commit_snapshot("table")
    pump(6)
    assert shown(asked) == "T1.A1 - not defined."
    QTest.keyClick(w.view.viewport(), Qt.Key_F12)          # Markup mode: a drag moves it
    pump()
    assert w.view.calc.mode == "markup"
    start = table.sceneBoundingRect().center()
    w.view.centerOn(start)
    pump()
    lift = frame.mapToScene(QPointF(300 * PT_PER_PX, 40 * PT_PER_PX)) - \
        frame.mapToScene(QPointF(300 * PT_PER_PX, 400 * PT_PER_PX))
    w.view.scene().clearSelection()
    table.setSelected(True)
    end = start + lift
    drag(w.view, start.x(), start.y(), end.x(), end.y())
    pump(8)
    assert table.pos().y() < 100, table.pos()
    assert asked.region.error is None and shown(asked) == "10"


def test_autocomplete_lists_a_sheets_name_only_below_it(w):
    """SMath lists only the names defined above: typing te above the sheet
    offers no test; below it, it does."""
    w.add_page(0)
    pump()
    calc_mode(w)
    run = insert_sheet_page_after(w, 0)
    type_into_cell(w, run, "A1", "2")
    name_cell_from_its_menu(w, run, "A1", "test")

    def offered(page):
        w.go_to_page(page)
        pump()
        point = w.document.pages[page].frame.mapToScene(QPointF(72, 300))
        w.view.centerOn(point)
        pump()
        click_at(w.view, point.x(), point.y())
        pump()
        QTest.keyClicks(w.view.viewport(), "te")
        pump()
        s = w.view.calc.suggestions
        texts = [e.text for e in s.entries()] if s.isVisible() else []
        QTest.keyClick(w.view.viewport(), Qt.Key_Escape)
        QTest.keyClick(w.view.viewport(), Qt.Key_Escape)
        w.view.calc.leave()
        pump()
        return texts

    assert "test" not in offered(0), "above the sheet"
    assert "test" in offered(2), "below it"
