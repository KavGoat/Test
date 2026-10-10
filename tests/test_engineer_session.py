"""What using the app as an engineer turned up (2026-10-10), through the real
window with mouse and keyboard: Excel's Tab-then-Enter, a spreadsheet's
headings kept in view, copied pages getting their own tables, table and
chart properties, the tables' names in equation autocomplete and in the
Variables panel, Search on spreadsheet pages, tables upright while open on a
rotated page, and Ctrl+drag box-select over a spreadsheet page."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QLabel

from calcforge.items.sheetpage import SheetRunItem
from calcforge.items.shapes import RectItem
from calcforge.items.table import TableItem
from tests.test_tables import cell_scene, click, enter, make_table, pump, type_text
from tests.test_usability import drag


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.view.set_zoom(1.0)
    window.resize(1500, 1000)
    return window


def tab(w):
    QApplication.sendEvent(w.view.tables.editor or w.view,
                           QKeyEvent(QEvent.KeyPress, Qt.Key_Tab, Qt.NoModifier))
    pump()


def sheet_page(w):
    w.insert_sheet_page(0)
    pump()
    pump()
    (run,) = [i for i in w.view.scene().items() if isinstance(i, SheetRunItem)]
    return run


def test_tab_then_enter_goes_back_under_where_the_tabs_began(w):
    table = make_table(w, width=48 * 4, height=15 * 4)
    w.view.tables.select((0, 1))
    for row in (("a", "b", "c"), ("d", "e", "f")):
        for text in row:
            type_text(w, text)
            tab(w)
        enter(w)
    assert w.view.tables.active == (2, 1), "Enter after Tabs: the next row, under B"
    inputs = {k: c.input for k, c in table.sheet.cells.items() if c.input}
    assert inputs == {(0, 1): "a", (0, 2): "b", (0, 3): "c", (1, 1): "d", (1, 2): "e", (1, 3): "f"}
    # an arrow key goes straight on (only Enter goes back under the start)
    w.view.tables.select((2, 0))
    type_text(w, "x")
    tab(w)
    type_text(w, "y")
    QApplication.sendEvent(w.view.tables.editor, QKeyEvent(QEvent.KeyPress, Qt.Key_Down, Qt.NoModifier))
    pump()
    assert w.view.tables.active == (3, 1)


def test_a_spreadsheets_headings_stay_in_view_and_select_whole_columns(w):
    run = sheet_page(w)
    w.view.centerOn(cell_scene(run, "A1"))
    pump()
    headings = w.view.sheet_headings
    headings.refresh()
    assert not any(kind == "col" for _r, kind, _rect in headings._strips)
    w.view.verticalScrollBar().setValue(w.view.verticalScrollBar().value() + 500)
    pump()
    assert headings.isVisible()
    (rect,) = [r for _r, kind, r in headings._strips if kind == "col"]
    assert rect.top() == 0, "the column letters along the top of the canvas"
    xs, _ys = run.edges()
    x = w.view.mapFromScene(run.mapToScene(QPointF((xs[2] + xs[3]) / 2, 0))).x()
    viewport = w.view.viewport()
    local = QPointF(x, rect.center().y())
    for kind in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
        QApplication.sendEvent(viewport, QMouseEvent(
            kind, local, viewport.mapToGlobal(local), Qt.LeftButton,
            Qt.LeftButton if kind == QEvent.MouseButtonPress else Qt.NoButton, Qt.NoModifier))
    pump()
    t, l, b, r = w.view.tables.selection()
    assert (l, r, t) == (2, 2, 0) and b >= 51, "clicking C selects the whole column"


def test_a_duplicated_page_gets_its_own_tables(w):
    table = make_table(w)
    table.sheet.workbook.set_input(table.sheet, 0, 0, "1")
    w.view.tables.close()
    w.duplicate_page(0)
    pump()
    tables = [i for i in w.view.scene().items() if type(i) is TableItem]
    assert len(tables) == 2 and len({id(t.sheet) for t in tables}) == 2
    assert len({t.uid for t in tables}) == 2
    copy = next(t for t in tables if t is not table)
    table.sheet.workbook.set_input(table.sheet, 0, 0, "99")
    assert copy.sheet.cells[(0, 0)].value == 1, "editing one leaves the copy alone"


def test_tables_and_charts_show_their_own_properties(w):
    table = make_table(w, width=48 * 2, height=15 * 4)
    wb = table.sheet.workbook
    for (r, c), v in {(0, 0): "x", (0, 1): "y", (1, 0): "1", (1, 1): "2", (2, 0): "2", (2, 1): "4"}.items():
        wb.set_input(table.sheet, r, c, v)
    w.view.tables.select((0, 0), (2, 1))
    chart = w.insert_chart("scatter")
    pump()
    texts = [label.text() for label in w.properties_panel.findChildren(QLabel)
             if label.isVisible()]
    assert "XY scatter" in texts, "the chart's own section, straight after inserting it"
    assert "Thickness" not in texts and "Fill" not in texts
    w.view.scene().clearSelection()
    table.setSelected(True)
    w.refresh_selection()
    pump()
    texts = [label.text() for label in w.properties_panel.findChildren(QLabel)
             if label.isVisible()]
    assert "Name" in texts and "Thickness" not in texts and "Fill" not in texts
    assert chart.scene() is not None


def test_equation_autocomplete_and_the_variables_panel_know_the_tables(w):
    from tests.test_calc_modes import typed
    from tests.test_usability import click as click_at
    from tests.test_usability import press_key
    table = make_table(w)
    wb = table.sheet.workbook
    wb.set_input(table.sheet, 0, 0, "Load (kN)")
    wb.set_input(table.sheet, 1, 0, "5 kN")
    wb.set_input(table.sheet, 2, 0, "7 kN")
    wb.define_name("W_total", f"{table.name}!$A$2:$A$3")
    w.view.tables.close()
    panel = w.variables_panel
    panel.refresh()
    rows = {r.name: (r.value, r.unit) for r in panel.rows}
    assert rows["W_total"] == ("5, 7", "kN")
    assert rows[f"{table.name}.Load"] == ("5, 7", "kN")
    node = next(panel.tree.topLevelItem(i) for i in range(panel.tree.topLevelItemCount())
                if panel.tree.topLevelItem(i).text(0) == "W_total")
    panel.go_to(node)
    pump()
    assert w.view.tables.item is table and w.view.tables.selection() == (1, 0, 2, 0)
    w.view.tables.close()
    w.toggle_calc_mode(True)
    p = table.parentItem().mapToScene(QPointF(80, 420))
    w.view.centerOn(p)
    pump()
    click_at(w.view, p.x(), p.y())
    typed(w, "s:W_t")
    suggestions = w.view.calc.suggestions
    assert suggestions.isVisible()
    assert suggestions.item(0).text() == "W_total"
    press_key(w.view, Qt.Key_Escape)
    typed(w, "+Table1.Lo")
    assert suggestions.item(0).text() == "Table1.Load"


def test_search_finds_words_on_a_spreadsheet_page(w):
    run = sheet_page(w)
    run.sheet.workbook.set_input(run.sheet, 4, 2, "Purlin P7")
    panel = w.search_panel if hasattr(w, "search_panel") else None
    if panel is None:
        from calcforge.ui.searchpanel import _searchable
        assert any("Purlin" in text for _f, text in _searchable(run))
        return
    from calcforge.ui.searchpanel import _searchable
    assert ("cell:4:2", "Purlin P7") in _searchable(run)


def test_a_table_on_a_rotated_page_is_upright_while_open(w):
    table = make_table(w)
    w.view.tables.close()
    w.rotate_page(0)
    pump()
    (table,) = [i for i in w.view.scene().items() if type(i) is TableItem]
    assert table.rotation() % 360 == 90
    w.view.tables.open(table, (1, 1))
    assert table.rotation() % 360 == 0, "upright to type in"
    assert table.serialize()["rotation"] % 360 == 90, "but kept turned in the record"
    type_text(w, "42")
    enter(w)
    (table,) = [i for i in w.view.scene().items() if type(i) is TableItem]
    assert table.sheet.cells[(1, 1)].value == 42
    w.view.tables.close()
    assert table.rotation() % 360 == 90, "turned with the page again"


def test_ctrl_drag_box_selects_markups_over_a_spreadsheet(w):
    run = sheet_page(w)
    frame = w.document.pages[1].frame
    boxes = []
    for row, col in ((2, 2), (4, 4)):
        box = RectItem()
        box.set_local_rect(QRectF(0, 0, 30, 12))
        frame.add_markup(box, frame.mapFromItem(run, run.cell_rect(row, col).topLeft()))
        boxes.append(box)
    a, z = cell_scene(run, "B2"), cell_scene(run, "H8")
    w.view.centerOn(a)
    pump()
    drag(w.view, a.x(), a.y(), z.x(), z.y())
    pump()
    assert w.view.tables.item is run and not any(b.isSelected() for b in boxes), \
        "a plain drag selects cells"
    w.view.tables.close()
    drag(w.view, a.x(), a.y(), z.x(), z.y(), Qt.ControlModifier)
    pump()
    assert all(b.isSelected() for b in boxes) and w.view.tables.item is None
    # a right-click on the cells is still the cells' menu
    click(w, cell_scene(run, "D10"))
    assert w.view.tables.item is run


def test_the_pointer_is_excels_over_cells_and_lets_go_of_them(w):
    """2026-10-10: the pointer stayed a cross everywhere once a table had set
    it (it was put on the view's viewport, which wins over the view). Over
    cells it is Excel's white plus, the arrow off them, in both modes."""
    from tests.test_usability import hover
    run = sheet_page(w)
    names = {}

    def shape_at(p):
        w.view.centerOn(p)
        pump()
        hover(w.view, p.x(), p.y())
        pump()
        return w.view.viewport().cursor().shape()

    for calc in (False, True):
        w.toggle_calc_mode(calc)
        assert shape_at(cell_scene(run, "C5")) == Qt.BitmapCursor, "the white plus, not yet open"
        w.view.tables.open(run, (0, 0))
        assert shape_at(cell_scene(run, "C5")) == Qt.BitmapCursor
        w.view.tables.close()
        desk = w.document.pages[0].frame.mapToScene(QPointF(-20, 100))
        assert shape_at(desk) == Qt.ArrowCursor, "and the arrow again off the cells"
        assert shape_at(w.document.pages[0].frame.mapToScene(QPointF(300, 600))) == Qt.ArrowCursor
    del names
