"""The user, 2026-10-23: "Can't press delete to delete pages"; "Placed
markup disappear on a spreadsheet, and depending on what I click it comes
back and then disappears again"; "Could[n't] move the chart in the Excel I
added"; "Add charts to a normal sheet".
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox

from calcforge.items.chart import ChartItem
from calcforge.ui import sheetview
from tests.test_excel_footer_keys import at, click, sheet, shown_run  # noqa: F401
from tests.test_workbook_sections import pump, w  # noqa: F401

openpyxl = pytest.importorskip("openpyxl")
pytest.importorskip("PIL")

from tests.test_xlsx_drawings import imported  # noqa: E402

_ = w


def test_delete_in_thumbnails_deletes_the_pages_picked(w, monkeypatch):
    for _ in range(3):
        w.add_page()
        pump()
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: asked.append(a[2]) or QMessageBox.Yes))
    w.interactive_prompts = True
    strip = w.pages_panel.list
    QTest.mouseClick(strip.viewport(), Qt.LeftButton, Qt.NoModifier,
                     strip.visualItemRect(strip.item(2)).center())
    pump()
    QTest.mouseClick(strip.viewport(), Qt.LeftButton, Qt.ControlModifier,
                     strip.visualItemRect(strip.item(3)).center())
    pump()
    assert len(strip.selectedItems()) == 2
    QTest.keyClick(strip, Qt.Key_Delete)
    pump()
    assert asked == ["Delete these 2 pages?"], "asked first, as Revu does"
    assert len(w.document.pages) == 2
    # said no: nothing goes
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.No))
    strip.item(1).setSelected(True)
    QTest.keyClick(strip, Qt.Key_Delete)
    pump()
    assert len(w.document.pages) == 2


def chart_of(w):
    return next(c for f in w.scene.frames for c in f.markups()
                if isinstance(c, ChartItem) and c.spec["kind"] == "scatter")


def drag_by(w, item, dx, dy) -> None:
    view = w.view
    view.centerOn(item.mapToScene(item.local_rect().center()))
    pump()
    start = view.mapFromScene(item.mapToScene(item.local_rect().center()))
    port = view.viewport()
    QTest.mousePress(port, Qt.LeftButton, Qt.NoModifier, start)
    pump()
    for k in range(1, 7):
        QTest.mouseMove(port, start + QPoint(dx * k // 6, dy * k // 6))
        pump(2)
    QTest.mouseRelease(port, Qt.LeftButton, Qt.NoModifier, start + QPoint(dx, dy))
    pump()


def test_an_excel_charts_is_picked_and_moved_on_its_pages_and_alone(w, tmp_path):
    imported(w, tmp_path)
    chart = chart_of(w)
    # on the pages: on top of the next page it hangs over, picked and moved
    sp = chart.mapToScene(chart.rect.center())
    assert type(w.scene.items(sp)[0]) is ChartItem, "drawn over the page after its own"
    before = chart.scenePos()
    drag_by(w, chart, 120, 60)
    assert chart.isSelected()
    moved = chart.scenePos() - before
    assert moved.x() > 10 and moved.y() > 5
    # shown alone, its cells open under it: the chart is picked, not a cell
    run = next(m for f in w.scene.frames for m in f.markups()
               if type(m).__name__ == "SheetRunItem" and m.sheet.name == "Calculations")
    sheetview.enter(w, run.uid)
    pump()
    assert w.view.tables.item is run
    before = chart.scenePos()
    drag_by(w, chart, -90, -45)
    moved = chart.scenePos() - before
    assert chart.isSelected() and moved.x() < -10 and moved.y() < -5


def test_pages_stack_in_order_so_a_markup_hanging_over_the_next_shows(w):
    for _ in range(3):
        w.add_page()
        pump()
    frames = w.scene.frames
    zs = [f.zValue() for f in frames]
    assert zs == sorted(zs, reverse=True) and len(set(zs)) == len(zs), \
        "each page over the ones after it, never level"
    # rebuilt (undo of a page added), the order is the pages' again
    w.add_page(0)
    pump()
    w.undo_stack.undo()
    pump()
    zs = [f.zValue() for f in w.scene.frames]
    assert zs == sorted(zs, reverse=True) and len(set(zs)) == len(zs)


def test_a_chart_of_a_sheet_made_here_from_its_right_click(w, sheet):
    """Right-click ▸ Insert ▸ Chart on a sheet made here, as on Excel's."""
    run = sheet
    click(w, at(w, run, 0, 0))
    w.view.tables.select((0, 0), (9, 1))
    pump()
    menu = w.view.tables.cell_menu()
    insert = next(a.menu() for a in menu.actions() if a.text() == "Insert")
    charts = next(a.menu() for a in insert.actions() if a.text() == "Chart")
    assert [a.text() for a in charts.actions()] == ["XY Scatter", "Scatter with Lines", "Line", "Column"]
    next(a for a in charts.actions() if a.text() == "Column").trigger()
    pump()
    made = [i for i in w.view.scene().items() if isinstance(i, ChartItem)]
    assert len(made) == 1 and made[0].spec["kind"] == "column"
    ys = [series["y"] for series in made[0].spec["series"]]
    assert [y.split("!")[1] for y in ys] == ["$A$1:$A$10", "$B$1:$B$10"], "a column each"


def test_an_undo_snapshot_never_takes_another_pages_markups(w):
    """tools/qa/monkey.py, 2026-10-24: undoing a page deleted lost a markup,
    or brought back one never there. The snapshot kept each page's markups
    written last time by id(page) and its count of changes; a page made
    again by an undo took a freed one's id, and with each page's count
    starting at 0 a match wrote the wrong markups. Now the page's own layer
    must be the one the markups were written from."""
    import weakref

    from calcforge.items.shapes import RectItem
    w.add_page()
    pump()
    snapshot = w._structure_snapshot()
    old_layer = w.document.pages[0].frame.layer
    stale = (weakref.ref(old_layer), old_layer.generation, [])     # written: no markups
    w._restore_structure(snapshot)              # new Page objects, new frames, new layers
    pump()
    page = w.document.pages[0]
    assert page.frame.layer is not old_layer
    page.frame.add_markup(RectItem(), page.frame.page_rect().center())
    pump()
    page.frame.layer.generation = old_layer.generation   # its count happens to match
    again = w._structure_snapshot(reuse={id(page): stale})         # and it took the freed id
    types = [item.get("type") for item in again["pages"][0]["items"]]
    assert types == ["rect"], "the page's own markups, not another page's written before"


def test_a_markup_picked_while_cells_are_open_takes_delete(w, sheet):
    """tools/qa/monkey.py, 2026-10-24: a markup picked while the cells were
    open (from the Markups list) and Delete pressed cleared the cells and
    left the markup. Now the picked markup goes and the cells stay; a click
    on a cell afterwards gives the keys back to the cells."""
    from calcforge.items.shapes import RectItem
    from tests.test_excel_footer_keys import key, typed
    run = sheet
    click(w, at(w, run, 2, 1))
    assert w.view.tables.item is run
    frame = run.parentItem()
    rect = RectItem()
    frame.add_markup(rect, run.mapToItem(frame, run.cell_rect(12, 4).center()))
    pump()
    w.view.scene().clearSelection()
    rect.setSelected(True)                       # as the Markups list picks it
    w.refresh_selection()
    pump()
    before = run.sheet.input(2, 1)
    key(w, Qt.Key_Delete)
    assert rect.scene() is None, "the markup picked is the one deleted"
    assert run.sheet.input(2, 1) == before, "and the cells are left alone"
    # picked again, then a cell clicked: typing is the cell's
    w.undo_stack.undo()
    pump()
    again = next(m for m in frame.markups() if isinstance(m, RectItem))
    again.setSelected(True)
    pump()
    click(w, at(w, run, 3, 1))
    typed(w, "7")
    key(w, Qt.Key_Return)
    assert run.sheet.input(3, 1) == "7"
    assert again.scene() is not None


def test_a_click_with_the_stamp_tool_puts_a_stamp_down(w):
    """Revu puts a stamp down where it is clicked, at its own size. A click
    used to start a click-and-click box: the stamp waited half drawn, and a
    page turned to took it away (tools/qa/monkey.py, 2026-10-24)."""
    from calcforge.items.text import StampItem
    w.add_page()
    pump()
    w.go_to_page(0)
    pump()
    w.select_tool("stamp")
    page = w.document.pages[0].frame
    spot = w.view.mapFromScene(page.mapToScene(page.page_rect().center()))
    click(w, spot)
    stamps = [m for m in page.markups() if isinstance(m, StampItem)]
    assert len(stamps) == 1 and w.view._draft is None, "down, not waiting for a second click"
    size = stamps[0].local_rect()
    assert (round(size.width()), round(size.height())) == (190, 58)
    w.go_to_page(1)
    pump()
    assert stamps[0].scene() is not None, "still there after going to another page"
    # dragged, it is the size dragged
    w.select_tool("stamp")
    w.go_to_page(0)
    pump()
    from tests.test_excel_footer_keys import drag
    drag(w, spot + QPoint(-200, 150), spot + QPoint(-40, 230))
    stamps = [m for m in page.markups() if isinstance(m, StampItem)]
    assert len(stamps) == 2


def test_undoing_a_column_deleted_puts_back_the_other_sheets_formulas(w):
    """tools/qa/monkey.py, 2026-10-24: deleting a column wrote another
    sheet's =Sheet1!B1 as =Sheet1!#REF!, and Undo put back only the sheet
    the column came out of: the other kept #REF!. Excel's Undo puts back
    both. Moving cells and inserting rows are recorded the same way."""
    from calcforge.ui import sheetpages
    from tests.test_excel_footer_keys import at, click, key, shown_run, typed
    from tests.test_workbook_sections import pump
    sheetpages.insert_sheet_page(w, 0, new_sheet=True)
    pump()
    w.go_to_page(1)
    pump()
    first = shown_run(w)
    w.sheet_tabs.new_sheet()
    pump()
    second = shown_run(w)
    assert second is not first
    click(w, at(w, second, 0, 0))
    typed(w, f"={first.sheet.name}!B1")
    key(w, Qt.Key_Return)
    assert second.sheet.input(0, 0) == f"={first.sheet.name}!B1"
    from calcforge.ui import sheetview
    sheetview.enter(w, first.uid)
    pump()
    first = shown_run(w)
    click(w, at(w, first, 0, 1))
    w.view.tables.select((0, 1), (5, 1))
    w.view.tables.delete_cols()
    pump()
    assert second.sheet.input(0, 0) == f"={first.sheet.name}!#REF!"
    w.undo_stack.undo()
    pump()
    assert second.sheet.input(0, 0) == f"={first.sheet.name}!B1", "both sheets put back"
    w.undo_stack.redo()
    pump()
    assert second.sheet.input(0, 0) == f"={first.sheet.name}!#REF!"


def test_undo_while_a_markup_is_half_drawn_takes_back_only_that(w):
    """tools/qa/monkey.py, 2026-10-24: Undo with a measurement waiting for
    its second click undid the step before it and left the tool holding a
    markup no page had. Now Undo takes back the half-drawn markup first, as
    it takes back the typing first."""
    from calcforge.items.measure import MeasureItem
    from calcforge.items.shapes import RectItem
    page = w.document.pages[0].frame
    w.view.begin_snapshot([page])
    page.add_markup(RectItem(), page.page_rect().center())
    w.view.commit_snapshot("Add")                  # a step to stay done
    assert w.undo_stack.count() == 1
    w.select_tool("measure_length")
    where = page.mapToScene(page.page_rect().center()) + QPointF(-150, 100)
    w.view.centerOn(where)
    pump()
    click(w, w.view.mapFromScene(where))           # the first point only
    assert isinstance(w.view._draft, MeasureItem)
    steps = w.undo_stack.index()
    w.act_undo.trigger()
    pump()
    assert w.view._draft is None and w.view._mode == "idle"
    assert not [m for m in page.markups() if isinstance(m, MeasureItem)]
    assert w.undo_stack.index() == steps, "the step before it is still done"
    assert [m for m in page.markups() if isinstance(m, RectItem)]


def test_a_page_duplicated_while_a_blank_box_is_typed_never_brings_it_back(w):
    """tools/qa/monkey.py, 2026-10-24: a text box left blank goes when its
    typing ends; a page duplicated meanwhile took it into the step first,
    so Undo then Redo brought the blank box back."""
    from calcforge.items.text import TextItem
    from tests.test_excel_footer_keys import drag
    page = w.document.pages[0].frame
    w.select_tool("text")
    centre = w.view.mapFromScene(page.mapToScene(page.page_rect().center()))
    drag(w, centre, centre + QPoint(120, 40))
    assert w.view.editing_item() is not None
    w.duplicate_page(0)
    pump()
    boxes = lambda: [m for f in w.scene.frames for m in f.markups() if isinstance(m, TextItem)]
    assert not boxes() and len(w.document.pages) == 2
    w.undo_stack.undo()
    pump()
    w.undo_stack.redo()
    pump()
    assert not boxes(), "never back"


def test_a_callout_begun_without_a_move_first_is_quick(w):
    """tools/qa/monkey.py, 2026-10-24: the Callout tool pressed with no move
    before it (a workbook shown alone since, everything elsewhere) drew its
    leader from the last place a move was seen, ten million points away, and
    cut it into 200,000 pieces to repaint: seconds frozen. The press is where
    the pointer is; and a leader is cut into a few dozen pieces at most."""
    import time
    page = w.document.pages[0].frame
    w.select_tool("callout")
    where = page.mapToScene(page.page_rect().center())
    w.view.centerOn(where)
    pump()
    w.view._last_scene_pos = QPointF(-1e7, 0)      # a move seen long ago, far off
    started = time.perf_counter()
    click(w, w.view.mapFromScene(where))           # what it points at
    took = time.perf_counter() - started
    assert w.view._pending_anchor is not None
    rects = w.view._pointer_preview_rects()
    assert rects is not None and len(rects) < 200
    assert took < 1.0
    w.view._last_scene_pos = QPointF(-1e7, 0)      # a leader that long, even so
    assert len(w.view._pointer_preview_rects()) < 200


def test_ordering_a_markup_changes_its_own_page_only(w):
    """tools/qa/monkey.py, 2026-10-24: Bring to Front and Send to Back put a
    markup in order with every markup of every page, renumbering others'
    pages too, while Undo recorded only its own page: the others stayed
    renumbered. Order is each page's own."""
    from calcforge.items.shapes import RectItem
    w.add_page()
    pump()
    first, second = (p.frame for p in w.document.pages[:2])
    elsewhere = RectItem()
    first.add_markup(elsewhere, first.page_rect().center())
    elsewhere.setZValue(0.5)      # low: a renumbering moves it
    mine = RectItem()
    second.add_markup(mine, second.page_rect().center())
    mine.setZValue(1.0)
    pump()
    for mode in ("back", "front", "forward", "backward"):
        w.view.scene().clearSelection()
        mine.setSelected(True)
        w.reorder(mode)
        assert elsewhere.zValue() == 0.5, f"{mode}: another page's markup renumbered"
    w.reorder("back")
    z = mine.zValue()
    w.undo_stack.undo()
    pump()
    assert elsewhere.zValue() == 0.5
    assert w.undo_stack.canUndo()


def test_undoing_a_rename_that_changes_only_the_case(w, sheet):
    """tools/qa/monkey.py, 2026-10-24: Sheet1 renamed SHEET1 could not be
    undone: putting the sheet back, its old name was looked up regardless
    of case, found the sheet itself, and was refused."""
    run = sheet
    old = run.sheet.name
    assert w.view.tables.rename_to(run, old.upper())
    pump()
    assert run.sheet.name == old.upper()
    w.undo_stack.undo()
    pump()
    assert shown_run(w).sheet.name == old
    w.undo_stack.redo()
    pump()
    assert shown_run(w).sheet.name == old.upper()


def test_undoing_a_name_given_a_new_place_puts_it_back_where_it_was(w, sheet):
    """tools/qa/monkey.py, 2026-10-24: Z named on one sheet, then named
    again on another: Undo recorded only the second sheet, and Z was lost
    from the first, where it had been kept."""
    first = sheet
    first_name = first.sheet.name             # (put back, its item is made again)
    tables = w.view.tables
    click(w, at(w, first, 3, 1))
    assert tables.define_name("Z")
    pump()
    w.sheet_tabs.new_sheet()
    pump()
    second = shown_run(w)
    click(w, at(w, second, 5, 2))
    assert tables.define_name("Z")
    pump()
    wb = second.sheet.workbook
    second_name = second.sheet.name
    where = lambda: [dn.refers_to for dn in wb.names.values() if dn.name == "Z"]
    assert where() == [f"{second_name}!$C$6"]
    w.undo_stack.undo()
    pump()
    assert where() == [f"{first_name}!$B$4"], "back where it was"
    saved = [n for t in tables._all_tables() for n in t.serialize()["table"]["names"]]
    assert [n[1] for n in saved if n[0] == "Z"][:1] == [f"{first_name}!$B$4"]


def test_the_view_buttons_stay_on_a_spreadsheets_pages(w, sheet):
    """The user, 2026-10-24: "Spreadsheet page layout view, normal view etc
    don't work, also currently not greying out stuff not in the print area."
    Page Layout put Excel's view buttons away with the rest of its footer,
    so there was no way back to Normal or Page Break Preview but a click on
    a cell. They stay on a spreadsheet's pages, and each one works."""
    from calcforge.ui import sheetview
    buttons = w._sheet_status["buttons"]
    views = w._sheet_status["views"]

    def press(which):
        QTest.mouseClick(buttons[which], Qt.LeftButton)
        pump()
        pump()
    press("page_layout")
    assert not sheetview.is_on(w) and views.isVisible(), "still there on its pages"
    assert buttons["page_layout"].isChecked()
    press("break_preview")
    assert sheetview.is_on(w) and sheetview.current_view(w) == "break_preview"
    # outside the print area grey, inside white
    run = shown_run(w)
    area = run.sheet.page["print_area"]
    inside = at(w, run, area[0], area[1])
    outside = at(w, run, area[0], area[3] + 2)
    image = w.view.viewport().grab().toImage()
    ratio = image.devicePixelRatio()

    def shade(point):
        c = image.pixelColor(int((point.x() + 6) * ratio), int(point.y() * ratio))
        return c.red()
    assert shade(inside) > shade(outside) + 8, "what doesn't print is grey"
    press("page_layout")
    press("normal")
    assert sheetview.is_on(w) and sheetview.current_view(w) == "normal"
    # off the spreadsheet's pages they go
    sheetview.leave(w)
    pump()
    w.go_to_page(0)
    pump()
    pump()
    assert not views.isVisible()


def test_a_cell_reads_a_page_variable_and_says_why_a_lost_name_is_ref(w, sheet):
    """The user, 2026-10-24: "I had a variable height in a page then tried
    =height in a cell in a sheet but threw ref error (what's the proper way
    to refer to this)". =height reads an equation's height defined before the
    sheet — now written =CALC(height): a bare name in a cell is only ever an
    Excel name (the user, 2026-10-24). The Seismic Parts workbook has a name
    of its own, Height, which Excel keeps as Calculations!#REF! (its cells
    were deleted): the #REF! says so, and that CALC(height) reads the
    equation's."""
    from tests.test_calc_editing import type_line
    from tests.test_excel_footer_keys import key, typed
    from calcforge.ui import sheetview
    run = sheet
    sheetview.leave(w)
    w.go_to_page(0)
    pump()
    frame = w.document.pages[0].frame                  # a page before the sheet
    w.toggle_calc_mode(True)
    w.view.calc.place_cross(frame, QPointF(60, 80))
    type_line(w, "height:3.5'm")
    w.toggle_calc_mode(False)
    pump()
    sheetview.enter(w, run.uid)
    pump()
    run = shown_run(w)

    def put(r, text):
        click(w, at(w, run, r, 0))
        typed(w, text)
        key(w, Qt.Key_Return)
        pump()
        return run.sheet.cells[(r, 0)].value
    got = put(0, "=CALC(height)")
    assert "3.5" in str(got) and "m" in str(got), got
    got = put(3, "=height")
    assert str(got) == "#NAME?" and "CALC(height)" in got.reason, "bare: says how"
    # a broken name of the workbook's own, read bare, says what to do
    run.sheet.workbook.define_name("Height", "Gone!#REF!", home=run.sheet)
    got = put(1, "=height")
    assert str(got) == "#REF!"
    assert "CALC(height)" in got.reason and "deleted" in got.reason
    got = put(2, "=CALC(height)")
    assert "3.5" in str(got), got


def test_the_cells_variable_box_takes_typing_and_clicks_in_its_menu(w, sheet):
    """The user, 2026-10-24: "right click on a cell should let me direct type
    into the variable name, currently I can't even click on the variable name
    input without the context menu disappearing". On Windows the menu took the
    keyboard once it was on screen (the letters picked its entries) and a
    click on the box's row beside the box chose the row. The box is the
    menu's current entry with the keys once it shows; its whole row goes to
    the box."""
    from PySide6.QtWidgets import QApplication, QLabel
    run = sheet
    click(w, at(w, run, 2, 1))
    menu = w.view.tables.cell_menu()
    menu.popup(w.view.viewport().mapToGlobal(at(w, run, 2, 1)))
    menu.setFocus()                      # as the menu takes the keyboard on Windows
    pump()
    pump()
    field = w.view.tables.name_field
    assert menu.isVisible() and QApplication.focusWidget() is field, "the box has the keys"
    QTest.keyClicks(QApplication.focusWidget(), "PG")
    label = next(l for l in field.parentWidget().findChildren(QLabel) if l.text() == "Variable")
    QTest.mouseClick(label, Qt.LeftButton)       # beside the box, on its row
    pump()
    assert menu.isVisible(), "a click on the row keeps the menu"
    QTest.mouseClick(field, Qt.LeftButton)
    pump()
    assert menu.isVisible() and field.hasFocus()
    QTest.keyClicks(field, "A")
    QTest.keyClick(field, Qt.Key_Return)
    pump()
    assert not menu.isVisible()
    assert w.view.tables.selection_name().name == "PGA"
