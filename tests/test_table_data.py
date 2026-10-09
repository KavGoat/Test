"""Spreadsheet phase 3 in the real window: conditional formatting, sort,
filter, data validation, comments, Find & Replace, and the document Search."""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QKeyEvent
from PySide6.QtWidgets import QApplication

from calcforge.ui import datatools
from tests.test_tables import (cell_scene, enter, fill_column, key, make_table, pump, shown, tables,
                               type_text, typed, value, w)  # noqa: F401  (w is the fixture)


def colour_at(w, scene_pos) -> QColor:
    view = w.view
    image = view.viewport().grab().toImage()
    p = view.mapFromScene(scene_pos)
    return image.pixelColor(p.x(), p.y())


def table_with_loads(w):
    table = make_table(w, height=15 * 6, width=48 * 3)
    w.view.tables.select((0, 0))
    for text in ["Member", "B1", "B2", "C1", "C2"]:
        type_text(w, text)
        enter(w)
    w.view.tables.select((0, 1))
    for text in ["Load", "250 kN", "90 kN", "0.3 MN", "120 kN"]:
        type_text(w, text)
        enter(w)
    w.view.set_zoom(2.0)
    return table


def test_highlight_rule_paints_the_cells_and_undoes(w):
    table = table_with_loads(w)
    tabs = w.view.tables
    tabs.select((1, 1), (4, 1))
    dialog = datatools.cell_rule_dialog(tabs, "greater")
    dialog.a.setText("200 kN")
    dialog.accept()
    pump()
    tabs.select((5, 2))
    w.view.centerOn(cell_scene(table, "B2"))
    pump()
    corner = table.mapToScene(table.cell_rect(1, 1).topLeft() + QPointF(1.5, 1.5))
    assert colour_at(w, corner).name() == "#ffc7ce", "250 kN is over 200 kN"
    corner3 = table.mapToScene(table.cell_rect(2, 1).topLeft() + QPointF(1.5, 1.5))
    assert colour_at(w, corner3).name() == "#ffffff", "90 kN isn't"
    assert len(table.sheet.cond_rules) == 1
    w.undo_stack.undo()
    assert tables(w)[0].sheet.cond_rules == []


def test_data_bars_draw(w):
    table = table_with_loads(w)
    tabs = w.view.tables
    tabs.select((1, 1), (4, 1))
    datatools.add_rule(tabs, {"type": "databar", "color": "#638ec6"})
    tabs.select((5, 2))
    w.view.centerOn(cell_scene(table, "B4"))
    pump()
    left = table.mapToScene(table.cell_rect(3, 1).topLeft() + QPointF(3, 4))
    c = colour_at(w, left)
    assert c.blue() > c.red() + 40, "the biggest load has a long blue bar"


def test_sort_and_filter(w):
    table = table_with_loads(w)
    tabs = w.view.tables
    tabs.select((2, 1))
    datatools.quick_sort(tabs, False)
    assert [shown(table, f"B{i}") for i in range(2, 6)] == ["0.3 MN", "250 kN", "120 kN", "90 kN"]
    assert [typed(table, f"A{i}") for i in range(2, 6)] == ["C1", "B1", "C2", "B2"]
    datatools.toggle_filter(tabs)
    assert table.sheet.filter is not None and table.sheet.filter["range"][0] == 0
    menu = datatools.filter_menu(tabs, 0, None)
    assert "Choose Values…" in [a.text() for a in menu.actions()]
    dialog = datatools.values_dialog(tabs, 0)
    dialog.set_checked(["B1", "B2"])
    dialog.accept()
    assert table.sheet.filtered_rows == {1, 3}
    assert table.local_rect().height() == 15 * 4, "the filtered rows take no room"
    custom = datatools.custom_filter_dialog(tabs, 1)
    custom.op1.setCurrentIndex(2)              # greater than
    custom.v1.setText("100 kN")
    custom.accept()
    assert table.sheet.filtered_rows == {1, 3, 4}
    w.undo_stack.undo()
    w.undo_stack.undo()
    assert tables(w)[0].sheet.filtered_rows == set()


def test_validation_list_and_stop(w):
    table = table_with_loads(w)
    tabs = w.view.tables
    tabs.select((1, 2), (4, 2))
    dialog = datatools.validation_dialog(tabs)
    dialog.kind.setCurrentIndex(dialog.kind.findData("list"))
    dialog.source.setText("OK, NG")
    dialog.error.setText("OK or NG only")
    dialog.accept()
    tabs.select((1, 2))
    assert table.list_button() is not None
    menu = tabs.list_menu()
    assert [a.text() for a in menu.actions()] == ["OK", "NG"]
    menu.actions()[1].trigger()
    assert typed(table, "C2") == "NG"
    tabs.select((2, 2))
    type_text(w, "maybe")
    enter(w)
    assert tabs.editor is not None, "a Stop rule won't take it: the cell is still being typed"
    tabs.cancel()
    assert typed(table, "C3") == ""
    datatools.circle_invalid(tabs)
    assert table.circles == []


def test_comments(w):
    table = table_with_loads(w)
    tabs = w.view.tables
    tabs.select((1, 0))
    dialog = datatools.comment_dialog(tabs)
    dialog.text.setPlainText("Checked by KD")
    dialog.accept()
    assert table.sheet.cell(1, 0).comment == "Checked by KD"
    w.view.centerOn(cell_scene(table, "A2"))
    pump()
    tip = table.mapToScene(table.cell_rect(1, 0).topRight() + QPointF(-1, 1))
    assert colour_at(w, tip).red() > 180 and colour_at(w, tip).green() < 120, "a red triangle"
    datatools.set_comment(tabs, None)
    assert table.sheet.cell(1, 0).comment is None


def test_find_and_replace_in_tables(w):
    table = table_with_loads(w)
    tabs = w.view.tables
    dialog = datatools.find_dialog(tabs)
    dialog.what.setText("b*")
    assert len(dialog.find_all()) == 3, "Member, B1, B2 (Excel's Find matches inside the cell)"
    dialog.what.setText("C")
    dialog.with_.setText("Col ")
    dialog.whole.setChecked(False)
    dialog.case.setChecked(True)
    assert dialog.replace_all() == 2
    assert typed(table, "A4") == "Col 1"
    w.undo_stack.undo()
    assert typed(tables(w)[0], "A4") == "C1"


def test_document_search_finds_and_replaces_cells(w):
    table = table_with_loads(w)
    w.view.tables.close()
    panel = w.search_panel if hasattr(w, "search_panel") else None
    if panel is None:
        from calcforge.ui.searchpanel import SearchPanel
        panel = SearchPanel(w)
    panel.query.setText("B2")
    hits = panel.run()
    cell_hits = [h for h in hits if str(h.get("field", "")).startswith("cell:")]
    assert cell_hits and cell_hits[0]["item"] is table
    panel.replacement.setText("Beam 2")
    panel.replace_all()
    assert typed(tables(w)[0], "A3") == "Beam 2"


def test_ctrl_f_in_an_open_table_is_its_find(w):
    table = table_with_loads(w)
    w.interactive_prompts = False
    key(w, Qt.Key_F, mods=Qt.ControlModifier)
    assert isinstance(w._last_data_dialog, datatools.FindDialog)
