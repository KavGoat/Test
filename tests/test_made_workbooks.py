"""A spreadsheet made here is a workbook as one brought in from Excel is
(the user, 2026-10-24: "inserting a spreadsheet, i cant right click and self
contain it or in property panel it default to sheet property no workbook
property ... make workbook self contained or not, not individual sheet ...
name manager can you make it for each workbook").

* Insert ▸ Spreadsheet Page makes a workbook (a Book), self-contained to
  start: its sheet tab's and its Thumbnails entry's right-click have
  Self-contained, and the Properties panel has its Workbook section.
* A workbook made before had no Book: it is given one as it comes in, not
  self-contained (as it was), its names its own; a table that read one of
  them bare goes on reading it as Sheet!Name.
* The Name Manager lists one workbook's names at a time, its own (Scope:
  Workbook) and its sheets' (Scope: the sheet), with a drop-down of the
  workbooks, the tables on pages and the CalcForge variables.
* A cell's drop-down list is a list box as Excel's, not a menu.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QCheckBox, QLabel

from calcforge.items.sheetpage import SheetRunItem
from calcforge.ui import names, sheetpages
from tests.test_tables import enter, make_table, type_text


def pump():
    for _ in range(3):
        QApplication.instance().processEvents()


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.interactive_prompts = False
    return window


def runs(w) -> list:
    return sorted((i for i in w.view.scene().items() if isinstance(i, SheetRunItem)),
                  key=lambda r: w.document.index_of(r.parentItem().page))


def put(w, run, row, col, text):
    w.view.tables.open(run, (row, col))
    type_text(w, text)
    enter(w)


def test_an_inserted_spreadsheet_is_a_self_contained_workbook(w):
    w.insert_spreadsheet(0)
    pump()
    (run,) = runs(w)
    sheet = run.sheet
    book = sheet.workbook.books[sheet.book]
    assert book.self_contained and book.file == "Workbook" and book.name == "Workbook"
    (section,) = sheetpages.sections(w.document)
    assert section.book == book.id and section.name == "Workbook"
    # its tab's right-click, and its Thumbnails entry's, have Self-contained
    w.go_to_page(w.document.index_of(run.parentItem().page))
    pump()
    labels = [a.text() for a in w.sheet_tabs.build_menu(0).actions()]
    assert "Self-contained" in labels
    tab = next(a for a in w.sheet_tabs.build_menu(0).actions() if a.text() == "Self-contained")
    assert tab.isCheckable() and tab.isChecked()
    tab.trigger()
    pump()
    assert not book.self_contained
    w.undo_stack.undo()
    pump()
    assert book.self_contained, "one undo step"
    # a second sheet of it shares it; another workbook beside it is its own
    w.sheet_tabs.new_sheet()
    pump()
    first, second = runs(w)
    assert second.sheet.book == book.id
    w.insert_spreadsheet(w.document.index_of(second.parentItem().page))
    pump()
    third = runs(w)[-1]
    assert third.sheet.book not in (None, book.id)
    assert [s.name for s in sheetpages.sections(w.document)] == ["Workbook", "Workbook (2)"]


def test_the_properties_panel_shows_the_workbook_and_the_worksheet(w):
    w.insert_spreadsheet(0)
    pump()
    (run,) = runs(w)
    w.view.scene().clearSelection()
    run.setSelected(True)
    w.properties_panel.show_items([run])
    pump()
    body = w.properties_panel.body
    assert body.findChild(QLabel, "workbookTitle").text() == "Workbook"
    assert body.findChild(QLabel, "workbookSheets").text().startswith("1 sheet · page")
    assert body.findChild(QLabel, "workbookFile") is None, "made here, not from a file"
    contained = body.findChild(QCheckBox, "workbookSelfContained")
    assert contained.isChecked()
    contained.setChecked(False)
    pump()
    assert not run.sheet.workbook.books[run.sheet.book].self_contained
    # Print for the whole workbook, and for the sheet
    prints = w.properties_panel.body.findChild(QCheckBox, "workbookPrint")
    assert prints.isChecked()
    prints.setChecked(False)
    pump()
    assert not sheetpages.sheet_prints(w.document, run.uid)
    sheet_print = w.properties_panel.body.findChild(QCheckBox, "sheetPrint")
    assert sheet_print is not None and not sheet_print.isChecked()
    sheet_print.setChecked(True)
    pump()
    assert sheetpages.sheet_prints(w.document, run.uid)


def test_a_workbook_made_before_is_given_its_record_and_keeps_its_names(w):
    """Sheets recorded before every workbook had its record: theirs, not
    self-contained; their names the workbook's own; a table on a page that
    read one bare reads it as Sheet!Name."""
    table = make_table(w)                 # (made first: make_table wants the only one)
    w.view.tables.close()
    w.insert_sheet_page(0)
    pump()
    (run,) = runs(w)
    put(w, run, 0, 0, "12")
    w.view.tables.close()
    record = w.document.pages[w.document.index_of(run.parentItem().page)].to_dict()
    # as recorded before: no book, the name the document's
    for payload in record["items"]:
        if payload.get("type") == "sheet_run":
            table_data = payload["table"]
            table_data.pop("book", None)
            table_data["names"] = [["Span", f"'{table_data['name']}'!$A$1", False, ""]]
    sheet_name = run.sheet.name
    page = w.document.index_of(run.parentItem().page)
    w.view.tables.open(table, (0, 0))
    type_text(w, "=Span*2")
    enter(w)
    w.view.tables.close()
    w.delete_page(page)
    pump()
    from calcforge.core.document import Page
    w.document.pages.insert(page, Page.from_dict(record))
    w.rebuild_scenes()
    pump()
    (run,) = runs(w)
    book = run.sheet.workbook.books[run.sheet.book]
    assert not book.self_contained and book.file == "Workbook"
    wb = run.sheet.workbook
    assert ("span", book.id) in wb.names and ("span", None) not in wb.names
    (table,) = [t for t in w.view.tables._all_tables() if not isinstance(t, SheetRunItem)]
    cell = table.sheet.cells[(0, 0)]
    assert cell.input == f"={sheet_name}!Span*2" and cell.value == pytest.approx(24)


def test_two_workbooks_each_with_a_name_load_stay_apart(w):
    w.insert_spreadsheet(0)
    pump()
    w.insert_spreadsheet(1)
    pump()
    one, two = runs(w)
    for run, value in ((one, "10"), (two, "20")):
        put(w, run, 0, 0, value)
        w.view.tables.open(run, (0, 0))
        assert w.view.tables.define_name("Load")
        put(w, run, 1, 0, "=Load*2")
    w.view.tables.close()
    assert one.sheet.cells[(1, 0)].value == pytest.approx(20)
    assert two.sheet.cells[(1, 0)].value == pytest.approx(40)


def test_the_name_manager_lists_one_workbook_at_a_time(w):
    w.insert_spreadsheet(0)
    pump()
    w.insert_spreadsheet(1)
    pump()
    one, two = runs(w)
    put(w, one, 0, 0, "10")
    w.view.tables.open(one, (0, 0))
    w.view.tables.define_name("Load")
    w.view.tables.open(one, (1, 0))
    assert names.define(w.view.tables, "Local", f"{one.sheet.name}!$A$1", scope=one.sheet) is None
    w.view.tables.select((2, 0))
    assert w.view.tables.name_selection("x_calc")          # a CalcForge variable
    put(w, two, 0, 0, "20")
    w.view.tables.open(two, (0, 0))
    w.view.tables.define_name("Load")
    # opened on the second workbook: only its names
    w.view.tables.open(two, (0, 0))
    names.name_manager(w.view.tables)
    manager = w._last_data_dialog
    shown = [manager.whose.itemText(i) for i in range(manager.whose.count())]
    assert shown == ["Workbook", "Workbook (2)", "CalcForge Variables"]
    assert manager.whose.currentText() == "Workbook (2)"

    def listed():
        return {manager.table.item(i, 0).text(): manager.table.item(i, 3).text()
                for i in range(manager.table.rowCount())}
    assert listed() == {"Load": "Workbook"}
    manager.whose.setCurrentIndex(0)
    assert listed() == {"Load": "Workbook", "Local": one.sheet.name,
                        "x_calc": "CalcForge variable"}
    manager.whose.setCurrentIndex(2)
    assert listed() == {"x_calc": f"Document ({one.sheet.name})"}
    # New… on the first workbook: a name of that workbook, its scope its sheets
    manager.whose.setCurrentIndex(0)
    manager.open_editor(None)
    editor = w._last_name_dialog
    assert [editor.scope.itemText(i) for i in range(editor.scope.count())] == \
        ["Workbook", one.sheet.name]
    editor.name.setText("Factor")
    editor.refers.setText("=1.5")
    assert manager.apply_editor(editor) is None
    wb = one.sheet.workbook
    assert wb.names[("factor", one.sheet.book)].book == one.sheet.book
    assert ("factor", two.sheet.book) not in wb.names
    # the Name Box's drop-down: the open sheet's workbook's names only
    from PySide6.QtWidgets import QMenu
    menu = QMenu()
    names.names_menu(w.view.tables, menu)
    assert sorted(a.text() for a in menu.actions()) == ["Load", "x_calc"]


def test_the_cells_drop_down_list_is_excels_list_box(w):
    from calcforge.ui import datatools
    from calcforge.ui.listpopup import ListPopup
    table = make_table(w)
    tabs = w.view.tables
    tabs.open(table, (1, 1))
    dialog = datatools.validation_dialog(tabs)
    dialog.kind.setCurrentIndex(dialog.kind.findData("list"))
    dialog.source.setText("Steel, Timber, Concrete, Stone")
    dialog.accept()
    tabs.select((1, 1))
    popup = tabs.list_menu()
    assert isinstance(popup, ListPopup)
    assert popup.choices() == ["Steel", "Timber", "Concrete", "Stone"]
    popup.fit(80)
    assert popup.height() == 4 * popup.row_height() + 2, "as many rows as choices, up to eight"
    from PySide6.QtTest import QTest
    QTest.keyClick(popup, Qt.Key_S)
    assert popup.currentItem().text() == "Stone", "a letter: the next choice starting with it"
    QTest.keyClick(popup, Qt.Key_Return)
    assert table.sheet.cells[(1, 1)].input == "Stone"
    popup = tabs.list_menu()
    assert popup.currentItem().text() == "Stone", "the cell's own value picked out"
    popup.pick("Timber")
    assert table.sheet.cells[(1, 1)].input == "Timber"
