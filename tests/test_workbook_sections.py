"""A workbook is a section of the document (the user, 2026-10-21):

"Also spreadsheet imported tabs etc. are always showing at the bottom,
don't. Maybe treat spreadsheet workbooks as a section, and this is shown in
the thumbnail too instead of individual pages, maybe the section is pages
2–10 as the label for one section. Clicking in the section or scrolling to
it switches to the spreadsheet view mode and the sheet tab handle on the
bottom shows. Also on import of Excel let me select print or not print a
sheet individually; it should also allow me to easily choose inside the
spreadsheet view, so maybe right-click (long) on a tab chip has Print / No
Print. And grey out the tab or something if not printed."

* The sheet tabs (and the formula bar) show only while a workbook is in
  view: the page the page box shows is one of its pages, or one of its
  sheets is open. Scrolling off it turns them off a little past its edge.
* In Thumbnails a workbook is one entry, "▸ Loads" over "pages 2–7", that
  expands to its pages; picked, it stands for all its pages.
* Each sheet prints or not: chosen on import, and from its tab's
  right-click (or long press) Print; a sheet that doesn't print has a grey
  tab, greyed thumbnails, is left out of Print and Export and isn't written
  as pages of the saved PDF — CalcForge's record keeps it, and equations
  still read it.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QMenu

openpyxl = pytest.importorskip("openpyxl")

from calcforge.items.sheetpage import SheetRunItem  # noqa: E402
from calcforge.ui import sheetpages  # noqa: E402
from calcforge.ui.panels import NO_PRINT_ROLE, SECTION_ROLE  # noqa: E402
from calcforge.ui.sheettabs import HYSTERESIS_PX, LONG_PRESS_MS  # noqa: E402
from tests.test_workbook_self_contained import results, type_equations  # noqa: E402


def pump(times: int = 3) -> None:
    for _ in range(times):
        QApplication.instance().processEvents()


def loads_workbook(path) -> str:
    """Loads.xlsx: Loads (three pages of rows) and Factors (one page), the
    first reading the second."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Loads"
    ws["A1"], ws["B1"] = "Load", "Factored"
    for r in range(2, 150):
        ws.cell(r, 1, r)
        ws.cell(r, 2, f"=A{r}*Factors!$B$2")
    factors = wb.create_sheet("Factors")
    factors["A2"], factors["B2"] = "ULS", 1.5
    wb.save(path)
    return str(path)


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.interactive_prompts = False
    window.view.set_zoom(1.0)
    return window


def with_loads(w, tmp_path, no_print=()):
    """Page 1 a plain page, the workbook after it (its sheets chosen in the
    import window, *no_print* ticked off its Print column by the mouse), a
    plain page after it."""
    path = loads_workbook(tmp_path / "Loads.xlsx")

    def drive(chooser):
        chooser.dialog.show()
        pump()
        tree = chooser.tree
        for row in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(row)
            if item.data(0, Qt.UserRole) in no_print:
                QTest.mouseClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier,
                                 print_tick(tree, item))
                pump()
        QTest.mouseClick(chooser.buttons.button(QDialogButtonBox.Ok), Qt.LeftButton)
        pump()
    w.drive_workbook_chooser = drive
    try:
        assert w.insert_workbook(path, 0)
    finally:
        del w.drive_workbook_chooser
    pump()
    w.add_page(len(w.document.pages) - 1)
    pump()
    return sheetpages.sections(w.document)[0]


def print_tick(tree, item) -> QPoint:
    """Where the Print column's tick box of *item* is drawn."""
    from PySide6.QtWidgets import QStyle, QStyleOptionViewItem
    rect = tree.visualItemRect(item)
    left = tree.header().sectionPosition(1)
    width = tree.header().sectionSize(1)
    option = QStyleOptionViewItem()
    option.initFrom(tree)
    option.rect = rect.adjusted(left - rect.left(), 0, 0, 0)
    option.rect.setWidth(width)
    option.features |= QStyleOptionViewItem.HasCheckIndicator
    box = tree.style().subElementRect(QStyle.SE_ItemViewItemCheckIndicator, option, tree)
    return box.center() if box.isValid() else QPoint(left + 10, rect.center().y())


def sheet_pages(w, name: str) -> list:
    return [i for i, page in enumerate(w.document.pages)
            if page.sheet is not None and sheetpages.run_book(w.document, page.sheet)[2] == name]


def bar_shown(w) -> bool:
    return not w.formula_bar.isHidden()


# -- the tabs only while the workbook is in view --------------------------------------------
def test_the_tabs_show_only_while_the_workbook_is_in_view(w, tmp_path):
    section = with_loads(w, tmp_path)
    assert section.name == "Loads" and section.first == 1
    tabs = w.sheet_tabs
    w.go_to_page(0)
    pump()
    assert tabs.isHidden() and not bar_shown(w), "an ordinary page: no tabs, no formula bar"
    w.go_to_page(section.first)
    pump()
    assert tabs.isVisible() and bar_shown(w)
    assert [name for _uid, name in tabs.entries] == ["Loads", "Factors"]
    w.go_to_page(section.last + 1)
    pump()
    assert tabs.isHidden() and not bar_shown(w), "gone past it: off again"
    # the + adds a sheet to the workbook, at its end
    w.go_to_page(section.first)
    pump()
    tabs.add.click()
    pump()
    section = sheetpages.sections(w.document)[0]
    assert len(section.runs) == 3 and w.current_index == section.last
    added = next(i for i in w.view.scene().items()
                 if isinstance(i, SheetRunItem) and i.uid == section.runs[-1])
    assert added.sheet.book == section.book, "a sheet of the workbook, sharing its names"
    assert w.document.pages[section.last + 1].sheet is None


def test_scrolling_off_it_turns_the_view_off_past_the_edge_not_on_it(w, tmp_path):
    section = with_loads(w, tmp_path)
    tabs = w.sheet_tabs
    w.go_to_page(section.last)
    pump()
    assert tabs.isVisible()
    view = w.view
    bar = view.verticalScrollBar()
    edge = w.document.pages[section.last].frame.sceneBoundingRect().bottom()
    margin = tabs._middle()[1]             # HYSTERESIS_PX screen pixels, on the canvas
    assert margin == pytest.approx(HYSTERESIS_PX / view.transform().m11())

    def middle_y():
        return view.mapToScene(view.viewport().rect().center()).y()

    # a step at a time, as a scroll does, till the page box moves on
    while w.current_index == section.last:
        bar.setValue(bar.value() + 4)
        pump(1)
    assert w.current_index == section.last + 1
    assert middle_y() - edge < margin
    assert tabs.isVisible() and bar_shown(w), "just over the edge: still the spreadsheet view"
    while middle_y() - edge <= margin + 4:
        bar.setValue(bar.value() + 4)
        pump(1)
    assert tabs.isHidden() and not bar_shown(w), "well past it: off"
    # and back: on again only once well onto it
    while w.current_index != section.last:
        bar.setValue(bar.value() - 4)
        pump(1)
    assert tabs.isHidden(), "just onto it: not yet"
    while edge - middle_y() <= margin + 4:
        bar.setValue(bar.value() - 4)
        pump(1)
    assert tabs.isVisible() and bar_shown(w)


def test_a_click_on_a_sheet_turns_it_on_and_scrolling_right_off_puts_it_down(w, tmp_path):
    from tests.test_sheet_pages import open_at
    section = with_loads(w, tmp_path)
    w.go_to_page(0)
    pump()
    tabs = w.sheet_tabs
    assert tabs.isHidden()
    run = next(i for i in w.view.scene().items()
               if isinstance(i, SheetRunItem) and i.uid == section.runs[0])
    open_at(w, run, "A2")                  # a click on one of its cells
    pump()
    assert tabs.isVisible() and bar_shown(w) and w.view.tables.item is run
    w.go_to_page(len(w.document.pages) - 1)    # far off it
    pump()
    pump()
    assert w.view.tables.item is None, "the sheet is put down once off screen"
    assert tabs.isHidden() and not bar_shown(w)


# -- Thumbnails: one entry for the workbook --------------------------------------------------
def head_rect(w, section):
    listed = w.pages_panel.list
    return listed.visualItemRect(listed.item(section.first))


def test_thumbnails_show_the_workbook_as_one_entry_that_expands(w, tmp_path):
    section = with_loads(w, tmp_path)
    w.show_panel("dock_pages", True)
    pump()
    panel = w.pages_panel
    listed = panel.list
    assert len(section.pages) >= 3
    head = listed.item(section.first)
    assert head.text() == f"▸ Loads\npages 2–{section.last + 1}"
    assert head.data(SECTION_ROLE)["collapsed"]
    assert all(listed.isRowHidden(row) for row in section.pages[1:])
    assert not listed.isRowHidden(0) and not listed.isRowHidden(section.last + 1)
    # its picture goes to its first page
    w.go_to_page(0)
    pump()
    picture = listed.picture_rect(section.first)
    QTest.mouseClick(listed.viewport(), Qt.LeftButton, Qt.NoModifier, picture.center())
    pump()
    assert w.current_index == section.first and w.sheet_tabs.isVisible()
    # its name shows its pages, and hides them again
    words = listed.delegate.toggle_rect(head_rect(w, section))
    QTest.mouseClick(listed.viewport(), Qt.LeftButton, Qt.NoModifier, words.center())
    pump()
    assert not any(listed.isRowHidden(row) for row in section.pages)
    assert listed.item(section.first).text() == "▾ Loads\n2"
    assert listed.item(section.first + 1).data(SECTION_ROLE)["member"]
    menu = w.page_menu(section.first + 1)
    assert "Collapse Section" in [a.text() for a in menu.actions()]
    words = listed.delegate.toggle_rect(head_rect(w, section))
    QTest.mouseClick(listed.viewport(), Qt.LeftButton, Qt.NoModifier, words.center())
    pump()
    assert all(listed.isRowHidden(row) for row in section.pages[1:])
    menu = w.page_menu(section.first)
    expand = next(a for a in menu.actions() if a.text() == "Expand Section")
    expand.trigger()
    pump()
    assert not listed.isRowHidden(section.last)
    # page numbers elsewhere stay the document's
    assert w.page_spin.maximum() == len(w.document.pages)


def test_a_page_scrolled_to_inside_it_outlines_the_entry_and_picks_nothing(w, tmp_path):
    section = with_loads(w, tmp_path)
    panel = w.pages_panel
    w.go_to_page(section.first + 1)
    pump()
    assert panel.list.in_view_row == section.first
    assert w.selected_pages() == [], "going to one of its pages is not picking the workbook"
    assert w.pages_acted_on() == [section.first + 1]


def test_the_entry_picked_is_the_whole_workbook_deleted_and_moved(w, tmp_path):
    section = with_loads(w, tmp_path)
    w.show_panel("dock_pages", True)
    pump()
    listed = w.pages_panel.list
    total = len(w.document.pages)
    QTest.mouseClick(listed.viewport(), Qt.LeftButton, Qt.NoModifier,
                     listed.picture_rect(section.first).center())
    pump()
    assert w.selected_pages() == section.pages
    menu = w.page_menu(section.first)
    assert "Delete these" in next(a for a in menu.actions()
                                  if a.text().startswith("Delete Pages")).toolTip()
    w.delete_page(section.first, ask=False)
    pump()
    assert len(w.document.pages) == total - len(section.pages)
    assert not sheetpages.sections(w.document)
    w.undo_stack.undo()
    pump()
    section = sheetpages.sections(w.document)[0]
    assert len(section.pages) == len(sheetpages.sections(w.document)[0].pages)
    # dragged after the last page: the whole workbook goes
    w.pages_panel.move_rows(section.pages, len(w.document.pages))
    pump()
    moved = sheetpages.sections(w.document)[0]
    assert moved.last == len(w.document.pages) - 1 and len(moved.pages) == len(section.pages)
    # nothing goes between its sheets
    loads, factors = moved.runs[0], moved.runs[1]
    first_factors = sheetpages.run_pages(w.document, factors)[0]
    w.move_page(0, first_factors - 1)
    pump()
    assert w.document.pages[0].sheet is None, "refused"
    assert "workbook's sheets stay together" in w.status_hint.text()
    assert sheetpages.run_pages(w.document, loads)


# -- Print / Don't Print ------------------------------------------------------------------------
def test_the_import_window_chooses_print_for_each_sheet(w, tmp_path):
    section = with_loads(w, tmp_path, no_print=("Factors",))
    factors = sheet_pages(w, "Factors")
    loads = sheet_pages(w, "Loads")
    assert factors and loads
    assert not any(w.document.pages[i].printable for i in factors)
    assert all(w.document.pages[i].printable for i in loads)
    tabs = w.sheet_tabs
    w.go_to_page(section.first)
    pump()
    assert tabs.prints(0) and not tabs.prints(1)
    assert "doesn't print" in tabs.bar.tabToolTip(1)
    assert not tabs.bar.tabIcon(1).isNull() and tabs.bar.tabIcon(0).isNull()
    # the workbook's entry: some of it doesn't print
    head = w.pages_panel.list.item(section.first)
    assert head.data(NO_PRINT_ROLE) == 1
    w.pages_panel.set_expanded(section.key, True)
    assert w.pages_panel.list.item(factors[0]).data(NO_PRINT_ROLE) == 2


def test_the_import_windows_print_column_by_the_mouse(qapp, tmp_path):
    from calcforge.sheet.xlsx import read_workbook
    from calcforge.ui.xlsximport import SheetChooser
    chooser = SheetChooser(None, read_workbook(loads_workbook(tmp_path / "Loads.xlsx")))
    chooser.dialog.show()
    pump()
    tree = chooser.tree
    assert [tree.topLevelItem(i).text(1) for i in range(2)] == ["Print", "Print"]
    QTest.mouseClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier,
                     print_tick(tree, tree.topLevelItem(1)))
    pump()
    assert tree.topLevelItem(1).text(1) == "Don't Print"
    assert chooser.no_print() == ["Factors"]
    # and by the keys: to Loads' Print, Space
    tree.setFocus()
    tree.setCurrentItem(tree.topLevelItem(0), 0)
    QTest.keyClick(tree, Qt.Key_Right)
    QTest.keyClick(tree, Qt.Key_Space)
    pump()
    assert tree.topLevelItem(0).text(1) == "Don't Print"
    assert chooser.no_print() == ["Loads", "Factors"]
    chooser.dialog.close()


def tab_menu_by_right_click(w, index: int):
    """Right-click tab *index* where it is drawn; the menu that opens."""
    from PySide6.QtCore import QTimer
    bar = w.sheet_tabs.bar
    at = bar.tabRect(index).center()
    seen = {}

    def look():
        menu = QApplication.activePopupWidget()
        if isinstance(menu, QMenu):
            seen["actions"] = {a.text(): a for a in menu.actions()}
            seen["checked"] = seen["actions"]["Print"].isChecked()
            seen["actions"]["Print"].trigger()
            menu.close()
        else:
            QTimer.singleShot(20, look)
    QTimer.singleShot(50, look)
    QApplication.sendEvent(bar, QContextMenuEvent(QContextMenuEvent.Mouse, at,
                                                  bar.mapToGlobal(at)))
    pump()
    return seen


def test_a_tabs_right_click_print_is_one_undo_step(w, tmp_path):
    section = with_loads(w, tmp_path)
    w.go_to_page(section.first)
    pump()
    tabs = w.sheet_tabs
    steps = w.undo_stack.count()
    seen = tab_menu_by_right_click(w, 1)
    assert seen["checked"], "Factors printed to start"
    pump()
    assert w.undo_stack.count() == steps + 1
    assert not any(w.document.pages[i].printable for i in sheet_pages(w, "Factors"))
    assert not tabs.prints(1) and tabs.prints(0)
    w.undo_stack.undo()
    pump()
    assert all(w.document.pages[i].printable for i in sheet_pages(w, "Factors"))
    assert w.sheet_tabs.prints(1)


def test_a_long_press_on_a_tab_opens_its_menu(w, tmp_path):
    section = with_loads(w, tmp_path)
    w.go_to_page(section.first)
    pump()
    tabs = w.sheet_tabs
    bar = tabs.bar
    at = bar.tabRect(1).center()
    QTest.mousePress(bar, Qt.LeftButton, Qt.NoModifier, at)
    QTest.qWait(LONG_PRESS_MS + 200)
    menu = tabs.popup
    assert menu is not None and menu.isVisible()
    prints = next(a for a in menu.actions() if a.text() == "Print")
    assert prints.isCheckable() and prints.isChecked()
    prints.trigger()
    menu.close()
    QTest.mouseRelease(bar, Qt.LeftButton, Qt.NoModifier, at)
    pump()
    assert not tabs.prints(1)
    # a short press is a click, not the menu
    tabs.popup = None
    QTest.mouseClick(bar, Qt.LeftButton, Qt.NoModifier, bar.tabRect(0).center())
    QTest.qWait(LONG_PRESS_MS + 100)
    assert tabs.popup is None


def test_a_sheet_that_doesnt_print_is_left_out_of_print_export_and_the_pdfs_pages(
        w, tmp_path):
    import pymupdf

    from calcforge.io import export, printing
    from tests.test_calc_saving import reopen, save_to
    section = with_loads(w, tmp_path, no_print=("Factors",))
    last = len(w.document.pages) - 1
    type_equations(w, last, ["f:Factors.B2", "f=", "m:Loads.B3", "m="])
    got = results(w)
    assert got["f="] == "1.5" and got["m="] == "4.5"
    total = len(w.document.pages)
    factors = sheet_pages(w, "Factors")
    printed = printing.printable_pages(w.document, list(range(total)))
    assert len(printed) == total - len(factors)
    assert not any(page.sheet is not None and not page.printable for page in printed)
    out = str(tmp_path / "export.pdf")
    export.export_pdf(w.document, out)
    with pymupdf.open(out) as pdf:
        assert pdf.page_count == total - len(factors)
    saved = str(tmp_path / "saved.pdf")
    save_to(w, saved)
    with pymupdf.open(saved) as pdf:
        assert pdf.page_count == total - len(factors), "not written as pages"
    uids = [page.uid for page in w.document.pages]
    reopen(w, saved)
    pump()
    assert [page.uid for page in w.document.pages] == uids, "back where they were"
    assert not w.document.open_warnings, "not taken for pages deleted elsewhere"
    again = sheet_pages(w, "Factors")
    assert again == factors and not any(w.document.pages[i].printable for i in again)
    got = results(w)
    assert got["f="] == "1.5" and got["m="] == "4.5", "its cells still read"
    # saved again from the reopened file: still held back, still all there
    save_to(w, saved)
    reopen(w, saved)
    pump()
    assert [page.uid for page in w.document.pages] == uids
    with pymupdf.open(saved) as pdf:
        assert pdf.page_count == total - len(factors)
    # printing again: every page written once more, and back in the PDF
    w.go_to_page(section.first)
    pump()
    w.sheet_tabs.set_printing(1, True)
    save_to(w, saved)
    with pymupdf.open(saved) as pdf:
        assert pdf.page_count == total
