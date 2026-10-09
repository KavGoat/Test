"""Tables on pages (spreadsheet phase 2), driven through the real window:
Insert Table by dragging, typing and formulas, Excel's keys, the fill
handle, copy and paste, formatting, undo, saving, and the equations."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from calcforge.items.table import TableItem
from calcforge.sheet.numfmt import format_value
from calcforge.sheet.refs import parse_cell
from tests.test_usability import _mouse, drag


def pump():
    QApplication.instance().processEvents()


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.view.set_zoom(1.0)
    return window


def frame(w):
    return w.document.pages[0].frame


def tables(w):
    return [i for i in w.view.scene().items() if isinstance(i, TableItem)]


def page_to_scene(w, x, y):
    return frame(w).mapToScene(QPointF(x, y))


def make_table(w, x=72, y=100, width=48 * 3, height=15 * 4):
    """Insert Table, then drag out a rectangle on the page (points)."""
    w.insert_table()
    a = page_to_scene(w, x, y)
    b = page_to_scene(w, x + width, y + height)
    w.view.centerOn(a)
    drag(w.view, a.x(), a.y(), b.x(), b.y())
    pump()
    (table,) = tables(w)
    return table


def key(w, k, text="", mods=Qt.NoModifier):
    QApplication.sendEvent(w.view, QKeyEvent(QKeyEvent.KeyPress, k, mods, text))
    pump()


def type_text(w, text):
    """Typing, as a keyboard would: into the canvas, then the cell editor."""
    for ch in text:
        target = w.view.tables.editor or w.view
        QApplication.sendEvent(target, QKeyEvent(QKeyEvent.KeyPress, 0, Qt.NoModifier, ch))
        pump()


def enter(w):
    target = w.view.tables.editor or w.view
    QApplication.sendEvent(target, QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))
    pump()


def cell_scene(table, a1):
    r = parse_cell(a1)
    return table.mapToScene(table.cell_rect(r.row, r.col).center())


def click(w, scene_pos, mods=Qt.NoModifier, double=False):
    from PySide6.QtCore import QEvent
    vp = w.view.viewport()
    QApplication.sendEvent(vp, _mouse(w.view, QEvent.MouseButtonPress, scene_pos.x(), scene_pos.y(),
                                      modifiers=mods))
    QApplication.sendEvent(vp, _mouse(w.view, QEvent.MouseButtonRelease, scene_pos.x(), scene_pos.y(),
                                      modifiers=mods))
    if double:
        QApplication.sendEvent(vp, _mouse(w.view, QEvent.MouseButtonDblClick, scene_pos.x(), scene_pos.y(),
                                          modifiers=mods))
        QApplication.sendEvent(vp, _mouse(w.view, QEvent.MouseButtonRelease, scene_pos.x(), scene_pos.y(),
                                          modifiers=mods))
    pump()


def value(table, a1):
    r = parse_cell(a1)
    return table.sheet.value(r.row, r.col)


def shown(table, a1):
    r = parse_cell(a1)
    st = table.sheet.workbook.style_of(table.sheet, r.row, r.col)
    return format_value(value(table, a1), st.number_format, st.unit).text


def typed(table, a1):
    r = parse_cell(a1)
    return table.sheet.input(r.row, r.col)


def fill_column(w, table, entries):
    """Type entries down from the active cell, Enter after each."""
    for text in entries:
        type_text(w, text)
        enter(w)


# -- inserting ---------------------------------------------------------------------------
def test_dragging_out_a_table_gives_rows_and_columns_for_its_size(w):
    table = make_table(w, width=48 * 5, height=15 * 7)
    assert table.size == (7, 5)
    assert table.opened and w.view.tables.item is table
    assert w.formula_bar.isVisible()
    st = table.sheet.workbook.style_of(table.sheet, 3, 2)
    assert st.left and st.right and st.top and st.bottom, "thin borders on every cell"
    w.undo_stack.undo()
    assert tables(w) == []


def test_a_click_with_the_tool_gives_four_by_three(w):
    w.insert_table()
    p = page_to_scene(w, 100, 100)
    w.view.centerOn(p)
    click(w, p)
    (table,) = tables(w)
    assert table.size == (4, 3)


# -- typing ------------------------------------------------------------------------------------
def test_typing_values_and_formulas(w):
    table = make_table(w)
    fill_column(w, table, ["5 kN", "200 N", "=A1+A2"])
    assert shown(table, "A3") == "5.2 kN"
    assert w.view.tables.active == (3, 0), "Enter moves down"
    key(w, Qt.Key_Up)
    assert w.formula_bar.edit.text() == "=A1+A2"
    assert w.formula_bar.name.text() == "A3"


def test_escape_throws_away_what_was_typed(w):
    table = make_table(w)
    fill_column(w, table, ["7"])
    key(w, Qt.Key_Up)
    type_text(w, "99")
    QApplication.sendEvent(w.view.tables.editor, QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
    pump()
    assert typed(table, "A1") == "7"


def test_each_entry_is_one_undo_step(w):
    table = make_table(w)
    fill_column(w, table, ["1", "2"])
    w.undo_stack.undo()
    table = tables(w)[0]
    assert typed(table, "A2") == "" and typed(table, "A1") == "1"
    w.undo_stack.redo()
    assert typed(tables(w)[0], "A2") == "2"


def test_tab_and_arrows_move_like_excel(w):
    table = make_table(w)
    type_text(w, "a")
    key(w, Qt.Key_Tab) if False else QApplication.sendEvent(
        w.view.tables.editor, QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Tab, Qt.NoModifier))
    pump()
    assert w.view.tables.active == (0, 1) and typed(table, "A1") == "a"
    type_text(w, "b")
    QApplication.sendEvent(w.view.tables.editor, QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Down, Qt.NoModifier))
    pump()
    assert w.view.tables.active == (1, 1), "an arrow ends typing and moves (Enter mode)"
    key(w, Qt.Key_Right)
    assert w.view.tables.active == (1, 2)
    key(w, Qt.Key_Left, mods=Qt.ControlModifier)
    assert w.view.tables.active == (1, 0)


def test_delete_clears_the_selection(w):
    table = make_table(w)
    fill_column(w, table, ["1", "2", "3"])
    w.view.tables.select((0, 0), (1, 0))
    key(w, Qt.Key_Delete)
    assert typed(table, "A1") == "" and typed(table, "A2") == "" and typed(table, "A3") == "3"


def test_point_mode_puts_clicked_cells_into_the_formula(w):
    table = make_table(w)
    fill_column(w, table, ["4", "6"])
    type_text(w, "=")
    click(w, cell_scene(table, "A1"))
    type_text(w, "*")
    click(w, cell_scene(table, "A2"))
    assert w.view.tables.editor.text() == "=A1*A2"
    enter(w)
    assert value(table, "A3") == 24


def test_f4_cycles_dollars(w):
    table = make_table(w)
    type_text(w, "=B2")
    QApplication.sendEvent(w.view.tables.editor, QKeyEvent(QKeyEvent.KeyPress, Qt.Key_F4, Qt.NoModifier))
    pump()
    assert w.view.tables.editor.text() == "=$B$2"


# -- Excel's tools -------------------------------------------------------------------------------
def test_fill_handle_continues_a_series(w):
    table = make_table(w, height=15 * 6)
    fill_column(w, table, ["1", "3"])
    tabs = w.view.tables
    tabs.select((0, 0), (1, 0))
    handle = table.mapToScene(table.fill_handle_rect().center())
    end = cell_scene(table, "A5")
    drag(w.view, handle.x(), handle.y(), end.x(), end.y())
    pump()
    assert [value(table, f"A{i}") for i in range(1, 6)] == [1, 3, 5, 7, 9]


def test_fill_handle_copies_formulas_relatively(w):
    table = make_table(w, height=15 * 4)
    tabs = w.view.tables
    fill_column(w, table, ["1", "2", "3"])
    tabs.select((0, 1))
    type_text(w, "=A1*10")
    enter(w)
    tabs.select((0, 1))
    handle = table.mapToScene(table.fill_handle_rect().center())
    end = cell_scene(table, "B3")
    drag(w.view, handle.x(), handle.y(), end.x(), end.y())
    pump()
    assert typed(table, "B3") == "=A3*10" and value(table, "B3") == 30


def test_copy_and_paste_with_relative_references(w):
    table = make_table(w)
    tabs = w.view.tables
    fill_column(w, table, ["2", "=A1*5"])
    tabs.select((1, 0))
    tabs.copy()
    tabs.select((1, 1))
    tabs.paste()
    assert typed(table, "B2") == "=B1*5"
    mime = QApplication.clipboard().mimeData()
    assert mime.text().strip() == "10"
    assert any("XML Spreadsheet" in f for f in mime.formats()), "Excel's own format, for its formulas"


def test_cut_and_paste_moves_and_readers_follow(w):
    table = make_table(w)
    tabs = w.view.tables
    fill_column(w, table, ["2", "=A1*5"])
    tabs.select((0, 0))
    tabs.copy(cut=True)
    tabs.select((0, 2))
    tabs.paste()
    assert typed(table, "A1") == "" and typed(table, "A2") == "=C1*5" and value(table, "A2") == 10


def test_formatting_keys(w):
    table = make_table(w)
    fill_column(w, table, ["x"])
    w.view.tables.select((0, 0))
    key(w, Qt.Key_B, mods=Qt.ControlModifier)
    st = table.sheet.workbook.style_of(table.sheet, 0, 0)
    assert st.bold and st.left is not None, "bold, and the borders kept"
    w.undo_stack.undo()
    table = tables(w)[0]
    assert not table.sheet.workbook.style_of(table.sheet, 0, 0).bold


def test_insert_and_delete_rows_keep_the_look(w):
    table = make_table(w)
    tabs = w.view.tables
    fill_column(w, table, ["1", "2", "=SUM(A1:A2)"])
    tabs.select((1, 0))
    tabs.insert_rows()
    assert table.size == (5, 3)
    assert typed(table, "A4") == "=SUM(A1:A3)"
    assert table.sheet.workbook.style_of(table.sheet, 1, 0).left is not None
    tabs.select((1, 0))
    tabs.delete_rows()
    assert table.size == (4, 3) and typed(table, "A3") == "=SUM(A1:A2)"


def test_distribute_columns_evenly(w):
    table = make_table(w)
    tabs = w.view.tables
    wb = table.sheet.workbook
    wb.set_widths(table.sheet, [0], 100)
    tabs.select((0, 0), (0, 2))
    tabs.distribute("col")
    widths = [table.sheet.width(c) for c in range(3)]
    assert widths[0] == widths[1] == widths[2] == pytest.approx((100 + 48 + 48) / 3)


def test_merge_and_center(w):
    table = make_table(w)
    tabs = w.view.tables
    fill_column(w, table, ["Title"])
    tabs.select((0, 0), (0, 2))
    tabs.merge("center")
    assert table.sheet.merges == [(0, 0, 0, 2)]
    assert table.sheet.workbook.style_of(table.sheet, 0, 0).h_align == "center"


def test_dragging_the_corner_adds_rows_and_columns(w):
    table = make_table(w)
    w.view.tables.close()
    w.view.calc.mode = "markup"
    table.setSelected(True)
    table.set_local_rect(table.local_rect().adjusted(0, 0, 48 * 2, 15 * 3))
    assert table.size == (7, 5)


# -- modes ---------------------------------------------------------------------------------------
def test_markup_mode_click_selects_and_double_click_opens(w):
    table = make_table(w)
    tabs = w.view.tables
    tabs.close()
    w.view.calc.mode = "markup"
    click(w, cell_scene(table, "B2"))
    assert table.isSelected() and not table.opened
    click(w, cell_scene(table, "B2"), double=True)
    assert table.opened and tabs.active == (1, 1)


def test_calc_mode_click_goes_to_the_cell(w):
    table = make_table(w)
    tabs = w.view.tables
    tabs.close()
    w.view.calc.mode = "calc"
    click(w, cell_scene(table, "C3"))
    assert table.opened and tabs.active == (2, 2)


def test_click_outside_closes(w):
    table = make_table(w)
    click(w, page_to_scene(w, 400, 600))
    assert not table.opened and not w.formula_bar.isVisible()


# -- the record --------------------------------------------------------------------------------------
def test_saving_and_reopening_keeps_everything(w, tmp_path):
    table = make_table(w)
    fill_column(w, table, ["5 kN", "=A1*2"])
    tabs = w.view.tables
    tabs.select((0, 0))
    tabs.format(bold=True, fill="#ffff00")
    tabs.close()
    path = str(tmp_path / "t.pdf")
    w.document.path = path
    assert w.save_document()
    import pymupdf
    with pymupdf.open(path) as doc:
        text = doc[0].get_text()
        assert "10 kN" in text and "5 kN" in text, "the table is on the page as real text"
        assert list(doc[0].annots()) == [], "page drawing, not an annotation"
    w.open_path(path)
    pump()
    (again,) = [t for t in tables(w) if t.scene() is w.view.scene()]
    assert shown(again, "A2") == "10 kN"
    st = again.sheet.workbook.style_of(again.sheet, 0, 0)
    assert st.bold and st.fill == "#ffff00"


def test_deleting_a_table_breaks_references_and_undo_brings_it_back(w):
    one = make_table(w)
    fill_column(w, one, ["3"])
    w.view.tables.close()
    w.insert_table()
    a = page_to_scene(w, 72, 300)
    b = page_to_scene(w, 72 + 96, 330)
    drag(w.view, a.x(), a.y(), b.x(), b.y())
    pump()
    two = [t for t in tables(w) if t is not one][0]
    type_text(w, f"={one.name}!A1*2")
    enter(w)
    assert value(two, "A1") == 6
    w.view.tables.close()
    w.view.scene().clearSelection()
    one.setSelected(True)
    w.delete_selection()
    pump()
    two = tables(w)[0]
    assert str(value(two, "A1")) == "#REF!"
    w.undo_stack.undo()
    pump()
    two = [t for t in tables(w) if t.name != "Table1"][0]
    assert value(two, "A1") == 6


# -- a table among the other markups ----------------------------------------------------------------
def test_a_picked_up_table_shows_in_the_panels_and_copies(w):
    table = make_table(w)
    fill_column(w, table, ["1", "=A1+1"])
    tabs = w.view.tables
    tabs.close()
    w.view.calc.mode = "markup"
    w.view.scene().clearSelection()
    table.setSelected(True)
    w.refresh_selection()
    pump()
    w.copy_selection()
    w.paste_items()
    pump()
    copies = tables(w)
    assert len(copies) == 2
    names = sorted(t.name for t in copies)
    assert names == ["Table1", "Table2"], "a copy gets a name of its own"
    other = next(t for t in copies if t.name == "Table2")
    assert typed(other, "A2") == "=A1+1" and value(other, "A2") == 2


def test_a_table_prints(w):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter
    table = make_table(w)
    fill_column(w, table, ["Hello"])
    w.view.tables.close()
    page = frame(w)
    image = QImage(595, 842, QImage.Format_RGB32)
    image.fill(Qt.white)
    painter = QPainter(image)
    page.render_page(painter, QRectF(image.rect()), for_print=True)
    painter.end()
    box = table.mapRectToParent(table.local_rect()).toRect()
    dark = sum(1 for x in range(box.left(), box.right()) for y in range(box.top(), box.bottom())
               if image.pixelColor(x, y).lightness() < 128)
    assert dark > 50, "borders and text are printed"
    # nothing of the screen-only chrome above it
    above = sum(1 for x in range(box.left(), box.right()) for y in range(box.top() - 25, box.top() - 3)
                if image.pixelColor(x, y).lightness() < 200)
    assert above == 0


# -- renaming, sizes, the toolbar, the dialog ---------------------------------------------------------
def test_renaming_in_the_properties_panel_updates_formulas(w):
    one = make_table(w)
    fill_column(w, one, ["4"])
    w.view.tables.close()
    w.insert_table()
    a, b = page_to_scene(w, 72, 300), page_to_scene(w, 168, 330)
    drag(w.view, a.x(), a.y(), b.x(), b.y())
    pump()
    two = [t for t in tables(w) if t is not one][0]
    type_text(w, "=Table1!A1*2")
    enter(w)
    w.view.tables.close()
    w.view.scene().clearSelection()
    one.setSelected(True)
    w.refresh_selection()
    pump()
    from PySide6.QtWidgets import QLineEdit
    box = w.findChild(QLineEdit, "tableName")
    assert box is not None and box.text() == "Table1"
    box.setText("Loads")
    box.editingFinished.emit()
    pump()
    two = [t for t in tables(w) if t.name != "Loads"][0]
    assert typed(two, "A1") == "=Loads!A1*2" and value(two, "A1") == 8
    w.undo_stack.undo()
    pump()
    assert sorted(t.name for t in tables(w)) == ["Table1", "Table2"]


def test_dragging_a_heading_border_resizes_and_double_click_fits(w):
    table = make_table(w)
    fill_column(w, table, ["a rather long piece of text"])
    xs, _ys = table.edges()
    edge = table.mapToScene(QPointF(xs[1], -6))
    drag(w.view, edge.x(), edge.y(), edge.x() + 30, edge.y())
    pump()
    assert table.sheet.width(0) == pytest.approx(48 + 30, abs=1)
    w.undo_stack.undo()
    table = tables(w)[0]
    assert table.sheet.width(0) == pytest.approx(48)
    w.view.tables.autofit("col", [0])
    assert table.sheet.width(0) > 100


def test_dragging_the_selection_border_moves_cells(w):
    table = make_table(w)
    fill_column(w, table, ["7", "=A1*2"])
    tabs = w.view.tables
    tabs.select((0, 0))
    box = table.block_rect(0, 0, 0, 0)
    start = table.mapToScene(QPointF(box.right(), box.center().y() - 2))
    end = table.mapToScene(table.cell_rect(0, 2).center() + QPointF(box.width() / 2, 0))
    drag(w.view, start.x(), start.y(), end.x(), end.y())
    pump()
    assert typed(table, "A1") == "" and typed(table, "A2") == "=C1*2" and value(table, "A2") == 14


def test_toolbar_controls_format_the_selection(w):
    table = make_table(w)
    fill_column(w, table, ["5000 N"])
    tabs = w.view.tables
    tabs.select((0, 0))
    controls = w.table_controls
    assert all(a.isVisible() for a in controls.actions[:3])
    controls.buttons["bold"].click()
    controls.unit.setText("kN")
    controls.unit.editingFinished.emit()
    controls._decimals(1)
    pump()
    st = table.sheet.workbook.style_of(table.sheet, 0, 0)
    assert st.bold and st.unit == "kN"
    assert shown(table, "A1") == "5.0 kN"
    tabs.close()
    assert not any(a.isVisible() for a in controls.actions)


def test_format_cells_dialog(w):
    table = make_table(w)
    fill_column(w, table, ["0.25"])
    tabs = w.view.tables
    tabs.select((0, 0), (1, 1))
    w.format_cells_dialog()
    dialog = w._last_format_dialog
    dialog.category.setCurrentRow(6)          # Percentage
    dialog.decimals.setValue(1)
    dialog.bold.setChecked(True)
    dialog.border_choices = ["outside"]
    dialog.accept()
    pump()
    assert shown(table, "A1") == "25.0%"
    sheet = table.sheet
    st = sheet.workbook.style_of(sheet, 1, 1)
    assert st.bold and st.right.style == "thin"


def test_format_painter(w):
    table = make_table(w)
    fill_column(w, table, ["1", "2"])
    tabs = w.view.tables
    tabs.select((0, 0))
    tabs.format(fill="#ff0000", bold=True)
    w.table_controls.painter.click()
    click(w, cell_scene(table, "B2"))
    st = table.sheet.workbook.style_of(table.sheet, 1, 1)
    assert st.fill == "#ff0000" and st.bold
    assert not w.table_controls.painter.isChecked()


def test_ctrl_d_fills_down_and_autosum(w):
    table = make_table(w, height=15 * 5)
    tabs = w.view.tables
    fill_column(w, table, ["1", "2", "3"])
    tabs.select((3, 0))
    key(w, Qt.Key_Equal, "=", Qt.AltModifier)
    assert tabs.editor.text() == "=SUM(A1:A3)"
    enter(w)
    assert value(table, "A4") == 6
    tabs.select((0, 1))
    type_text(w, "=A1*2")
    enter(w)
    tabs.select((0, 1), (2, 1))
    key(w, Qt.Key_D, mods=Qt.ControlModifier)
    assert typed(table, "B3") == "=A3*2" and value(table, "B3") == 6
