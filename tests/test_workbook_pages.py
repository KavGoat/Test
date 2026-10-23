"""Workbooks and their pages, the user's third round (2026-10-22):

"The spreadsheet top-left corner is not like Excel. It should default to a
one-page-size print area on new sheet insert; currently it doesn't show the
print area at all. Setting Print to off did not update the page numbers in
the thumbnails; the background page number thing is lost."

"Duplicate Page on a workbook duplicates individual pages; it should insert
a whole new workbook." "There's no simple add page option."

* Excel's select-all corner: the headings' grey with a small triangle in
  its bottom right corner, darker under the pointer; a click picks the
  whole sheet — on a sheet's page, in the workbook view, and on the
  headings kept in sight as the sheet scrolls.
* A new sheet's print area is one page of cells from A1, outlined thin and
  solid in the workbook view (Excel's Normal view), the page breaks
  dashed. An imported sheet keeps its own; one with none prints the cells
  it uses.
* Pages are numbered as printed: one that doesn't print has no number and
  those after it move up — in Thumbnails and in the "Page N" mark on a
  sheet's paper, which shows in the workbook view too. The page box goes on
  counting every page.
* Duplicate Page on a workbook copies the whole workbook in after it,
  "Loads (2)", its formulas reading its own sheets; one undo step.
* Add Page: a blank page after this one (after the workbook), no dialog.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QMenu

openpyxl = pytest.importorskip("openpyxl")

from calcforge.items.sheetpage import BREAK_BLUE, CORNER_HOT, CORNER_MARK, SheetRunItem  # noqa: E402
from calcforge.items.table import HEADING_BG, HEADING_H, ROWNUM_W  # noqa: E402
from calcforge.sheet.pagination import options  # noqa: E402
from calcforge.ui import sheetpages  # noqa: E402
from tests.test_workbook_sections import (pump, sheet_pages, tab_menu_by_right_click,  # noqa: E402
                                          w, with_loads)
from tests.test_workbook_self_contained import results, type_equations  # noqa: E402
from tests.test_workbook_view import break_pens, click_thumbnail, paper_words  # noqa: E402

_ = w


def runs(w, name: str) -> SheetRunItem:
    return next(i for i in w.view.scene().items()
                if isinstance(i, SheetRunItem) and i.sheet is not None and i.sheet.name == name)


def captions(w) -> list:
    listed = w.pages_panel.list
    return [listed.item(row).text().split("\n")[0] for row in range(listed.count())]


@pytest.fixture
def wb(w, tmp_path):
    """Page 1, Loads.xlsx (Loads: four pages, Factors: one), a last page."""
    w.show_panel("dock_pages", True)
    pump()
    section = with_loads(w, tmp_path)
    w.go_to_page(0)
    w.activateWindow()
    QTest.qWaitForWindowActive(w)
    pump()
    return section


# -- Excel's select-all corner ---------------------------------------------------------------------
def corner_picture(item, hot=False) -> QImage:
    """The corner as the sheet draws it, at four times its size."""
    image = QImage(int(ROWNUM_W * 4), int(HEADING_H * 4), QImage.Format_ARGB32)
    image.fill(Qt.white)
    painter = QPainter(image)
    painter.scale(4, 4)
    painter.translate(ROWNUM_W, HEADING_H)
    item.corner_hot = hot
    try:
        item._paint_headings(painter, 0, 0)
    finally:
        painter.end()
        item.corner_hot = False
    return image


def corner_point(w, item) -> QPoint:
    return w.view.mapFromScene(item.mapToScene(item.corner_rect().center()))


def triangle_colour(image: QImage):
    """The colour near the corner's bottom right, inside its triangle."""
    return image.pixelColor(image.width() - int(image.width() * 0.2),
                            image.height() - int(image.height() * 0.22))


def test_the_corner_is_grey_with_a_triangle_pointing_bottom_right(w, wb):
    loads = runs(w, "Loads")
    picture = corner_picture(loads)
    assert picture.pixelColor(6, 6) == HEADING_BG, "the headings' grey"
    assert triangle_colour(picture) == CORNER_MARK, "the triangle, bottom right"
    # its top left corner is grey: a triangle pointing bottom right, not a box
    assert picture.pixelColor(int(picture.width() * 0.45), int(picture.height() * 0.45)) \
        == HEADING_BG
    assert triangle_colour(corner_picture(loads, hot=True)) == CORNER_HOT


def test_on_a_sheets_page_the_corner_lights_up_and_a_click_picks_the_whole_sheet(w, wb):
    loads = runs(w, "Loads")
    assert not loads.alone
    w.view.centerOn(loads.mapToScene(loads.corner_rect().center()))
    pump()
    at = corner_point(w, loads)
    QTest.mouseMove(w.view.viewport(), at + QPoint(0, 60))
    pump()
    assert not loads.corner_hot
    QTest.mouseMove(w.view.viewport(), at)
    pump()
    assert loads.corner_hot, "under the pointer it lights up"
    QTest.mouseMove(w.view.viewport(), at + QPoint(0, 60))
    pump()
    assert not loads.corner_hot
    QTest.mouseClick(w.view.viewport(), Qt.LeftButton, Qt.NoModifier, at)
    pump()
    if w.view.tables.item is not loads:       # a first click opens it, as on any table
        loads = runs(w, "Loads")
        QTest.mouseClick(w.view.viewport(), Qt.LeftButton, Qt.NoModifier, corner_point(w, loads))
        pump()
    rows, cols = loads.size
    assert w.view.tables.item is loads
    assert tuple(loads.selection) == (0, 0, rows - 1, cols - 1)
    assert loads.everything_picked()


def test_in_the_workbook_view_the_corner_and_the_kept_one_pick_the_whole_sheet(w, wb):
    click_thumbnail(w, wb.first)
    loads = runs(w, "Loads")
    assert loads.alone
    at = corner_point(w, loads)
    assert 0 <= at.x() < ROWNUM_W * w.view.zoom() and 0 <= at.y() < HEADING_H * w.view.zoom()
    QTest.mouseMove(w.view.viewport(), at)
    pump()
    assert loads.corner_hot
    QTest.mouseClick(w.view.viewport(), Qt.LeftButton, Qt.NoModifier, at)
    pump()
    rows, cols = loads.size
    assert tuple(loads.selection) == (0, 0, rows - 1, cols - 1)
    # scrolled down and across: the headings kept in sight, the corner with them
    w.view.tables.select((3, 3))
    pump()
    w.view.verticalScrollBar().setValue(w.view.verticalScrollBar().value() + 400)
    w.view.horizontalScrollBar().setValue(w.view.horizontalScrollBar().value() + 300)
    pump()
    w.view.sheet_headings.refresh()
    pump()
    kept = [kind for _run, kind, _rect in w.view.sheet_headings._strips]
    assert "corner" in kept
    point = QPoint(int(ROWNUM_W * w.view.zoom() / 2), int(HEADING_H * w.view.zoom() / 2))
    assert w.view.sheet_headings.hit(point) == (loads, ("corner",))
    QTest.mouseMove(w.view.viewport(), point + QPoint(0, 80))
    QTest.mouseMove(w.view.viewport(), point)
    pump()
    assert w.view.sheet_headings.corner_hot
    QTest.mouseClick(w.view.viewport(), Qt.LeftButton, Qt.NoModifier, point)
    pump()
    loads = runs(w, "Loads")
    rows, cols = loads.size
    assert tuple(loads.selection) == (0, 0, rows - 1, cols - 1)


# -- a new sheet's print area ----------------------------------------------------------------------
def outline_pen(item):
    """The pen the sheet draws round what it prints with."""
    pens = []

    class Listening(QPainter):
        def drawRect(self, *args):
            pens.append(QPainter.pen(self))
            return super().drawRect(*args)
    image = QImage(400, 400, QImage.Format_ARGB32)
    painter = Listening(image)
    item._paint_breaks(painter)
    painter.end()
    return pens[0]


def test_a_new_sheet_prints_one_page_from_a1_outlined_solid_in_the_workbook_view(w, tmp_path):
    w.show_panel("dock_pages", True)
    w.insert_sheet_page(0)
    pump()
    item = next(i for i in w.view.scene().items() if isinstance(i, SheetRunItem))
    area = options(item.sheet)["print_area"]
    assert area is not None and area[:2] == [0, 0]
    assert area[2] > 20 and area[3] > 4, "a page of cells, from A1"
    assert [p.sheet for p in w.document.pages].count(item.uid) == 1
    w.go_to_page(1)
    pump()
    item = next(i for i in w.view.scene().items() if isinstance(i, SheetRunItem))
    assert item.alone and item.normal_view
    edge = outline_pen(item)
    # the pages' blue line, to be dragged straight away (the user, 2026-10-22);
    # dashed in Normal view, its pages told by dashed lines on white (the
    # user, 2026-10-24: "Normal view has no grey, dashed lines to indicate page")
    assert edge.style() == Qt.DashLine and edge.isCosmetic() and edge.color() == BREAK_BLUE, \
        "Normal view: the print area's edge dashed blue"
    w.act_sheet_break_preview.trigger()
    pump()
    item = next(i for i in w.view.scene().items() if isinstance(i, SheetRunItem))
    edge = outline_pen(item)
    assert edge.style() == Qt.SolidLine and edge.color() == BREAK_BLUE, \
        "Page Break Preview: Excel's solid blue outline"
    w.act_sheet_normal_view.trigger()
    pump()
    item = next(i for i in w.view.scene().items() if isinstance(i, SheetRunItem))
    # the new sheet's paper says where it prints: its number on it
    assert paper_words(item) == ["Page 2"]
    # saved and opened: still its print area
    from tests.test_calc_saving import reopen, save_to
    saved = str(tmp_path / "new.pdf")
    save_to(w, saved)
    reopen(w, saved)
    pump()
    item = next(i for i in w.view.scene().items() if isinstance(i, SheetRunItem))
    assert options(item.sheet)["print_area"] == area


def test_an_imported_sheet_keeps_its_print_area_and_one_without_prints_its_cells(w, tmp_path):
    path = tmp_path / "Areas.xlsx"
    book = openpyxl.Workbook()
    ws = book.active
    ws.title = "Set"
    for r in range(1, 30):
        ws.cell(r, 1, r)
    ws.print_area = "A1:C12"
    free = book.create_sheet("Free")
    free["A1"] = 1
    book.save(path)
    assert w.insert_workbook(str(path), 0)
    pump()
    assert options(runs(w, "Set").sheet)["print_area"] == [0, 0, 11, 2]
    assert not options(runs(w, "Free").sheet)["print_area"]
    assert outline_pen(runs(w, "Set")).style() == Qt.SolidLine, "on its pages: solid"
    w.go_to_page(1)
    pump()
    assert outline_pen(runs(w, "Set")).style() == Qt.DashLine, "Normal view: dashed"
    bar = w.sheet_tabs.bar
    QTest.mouseClick(bar, Qt.LeftButton, Qt.NoModifier, bar.tabRect(1).center())
    pump()
    assert runs(w, "Free").alone
    assert outline_pen(runs(w, "Free")).style() == Qt.DashLine, \
        "no print area: what prints (its cells) outlined, as on the pages"
    assert all(p.style() == Qt.DashLine for p in break_pens(runs(w, "Free")))


# -- numbered as printed ---------------------------------------------------------------------------
def test_print_off_renumbers_thumbnails_and_the_page_marks_at_once(w, wb, tmp_path):
    """Loads 2–5, Factors 6, the last page 7; Factors off: the last page 6."""
    total = len(w.document.pages)
    assert captions(w)[0] == "1" and captions(w)[total - 1] == "7"
    assert w.document.printed_numbers() == [1, 2, 3, 4, 5, 6, 7]
    w.go_to_page(wb.first)
    pump()
    steps = w.undo_stack.count()
    seen = tab_menu_by_right_click(w, 1)       # Factors ▸ Print, off
    assert seen["checked"]
    pump()
    assert w.undo_stack.count() == steps + 1
    factors = sheet_pages(w, "Factors")[0]
    assert w.document.printed_numbers() == [1, 2, 3, 4, 5, None, 6]
    shown = captions(w)
    assert shown[factors] == "" and shown[total - 1] == "6", "the gap filled at once"
    tip = w.pages_panel.list.item(factors).toolTip()
    assert "No page number" in tip and f"Page {factors + 1} of the document's" in tip
    assert w.pages_panel.list.item(total - 1).toolTip().startswith("Page 6")
    assert paper_words(runs(w, "Factors")) == [], "no number on it"
    assert paper_words(runs(w, "Loads")) == ["Page 2", "Page 3", "Page 4", "Page 5"]
    assert runs(w, "Loads").alone, "and the marks show in the workbook view"
    head = w.pages_panel.list.item(wb.first).text()
    assert "pages 2–5" in head
    # undone: back at once
    w.undo_stack.undo()
    pump()
    assert captions(w)[total - 1] == "7" and captions(w)[factors] == "6"
    assert paper_words(runs(w, "Factors")) == ["Page 6"]
    w.undo_stack.redo()
    pump()
    # out of the workbook view: the pages say the same
    click_thumbnail(w, 0)
    assert w.scene.sheet_view is None
    assert paper_words(runs(w, "Loads")) == ["Page 2", "Page 3", "Page 4", "Page 5"]
    assert paper_words(runs(w, "Factors")) == []
    # the page box still counts every page
    w.go_to_page(total - 1)
    pump()
    assert w.current_index == total - 1
    # saved and opened
    from tests.test_calc_saving import reopen, save_to
    saved = str(tmp_path / "numbers.pdf")
    save_to(w, saved)
    reopen(w, saved)
    pump()
    w.show_panel("dock_pages", True)
    pump()
    assert w.document.printed_numbers() == [1, 2, 3, 4, 5, None, 6]
    assert captions(w)[total - 1] == "6" and captions(w)[factors] == ""


def test_header_and_footer_page_fields_count_the_printed_pages(w, wb):
    w.go_to_page(wb.first)
    pump()
    tab_menu_by_right_click(w, 1)
    pump()
    last = len(w.document.pages) - 1
    fields = w.document.field_values(last)
    assert fields["page"] == "6" and fields["pages"] == "6"


# -- Duplicate Page on a workbook ------------------------------------------------------------------
def test_duplicate_page_on_a_workbook_copies_the_whole_workbook_after_it(w, wb, tmp_path):
    last = len(w.document.pages) - 1
    type_equations(w, last, ["f:Factors.B2", "f=", "m:Loads.B3", "m="])
    w.go_to_page(wb.first)
    pump()
    tab_menu_by_right_click(w, 1)               # Factors doesn't print: the copy neither
    pump()
    before = len(w.document.pages)
    steps = w.undo_stack.count()
    w.duplicate_page(wb.first + 2)              # any of its pages
    pump()
    assert w.undo_stack.count() == steps + 1, "one undo step"
    assert len(w.document.pages) == before + 5
    sections = sheetpages.sections(w.document)
    assert [s.name for s in sections] == ["Loads", "Loads (2)"]
    copy = sections[1]
    assert copy.first == wb.last + 1, "right after it"
    assert w.current_index == copy.first
    assert w.scene.sheet_view == w.document.pages[copy.first].sheet, "the copy, shown"
    assert [name for _uid, name in w.sheet_tabs.entries] == ["Loads (2)", "Factors (2)"]
    copied = runs(w, "Loads (2)")
    assert copied.sheet.cells[(4, 1)].input == "=A5*'Factors (2)'!$B$2"
    assert copied.sheet.cells[(4, 1)].value == pytest.approx(7.5)
    assert not any(w.document.pages[i].printable for i in sheet_pages(w, "Factors (2)"))
    assert all(w.document.pages[i].printable for i in sheet_pages(w, "Loads (2)"))
    # its own: the copy's factor changed, the original and the equations not
    factors_copy = runs(w, "Factors (2)").sheet
    factors_copy.workbook.set_input(factors_copy, 1, 1, "2")
    w.view.scene().update()
    pump()
    assert runs(w, "Loads (2)").sheet.cells[(4, 1)].value == pytest.approx(10.0)
    assert runs(w, "Loads").sheet.cells[(4, 1)].value == pytest.approx(7.5)
    got = results(w)
    assert got["f="] == "1.5" and got["m="] == "4.5"
    # saved and opened
    from tests.test_calc_saving import reopen, save_to
    saved = str(tmp_path / "copied.pdf")
    save_to(w, saved)
    reopen(w, saved)
    pump()
    assert [s.name for s in sheetpages.sections(w.document)] == ["Loads", "Loads (2)"]
    assert runs(w, "Loads (2)").sheet.cells[(4, 1)].value == pytest.approx(10.0)


def test_duplicate_undone_in_one_step_and_an_ordinary_page_as_before(w, wb):
    before = len(w.document.pages)
    w.duplicate_page(wb.first)
    pump()
    assert len(w.document.pages) == before + 5
    w.undo_stack.undo()
    pump()
    assert len(w.document.pages) == before
    assert [s.name for s in sheetpages.sections(w.document)] == ["Loads"]
    w.duplicate_page(0)
    pump()
    assert len(w.document.pages) == before + 1, "an ordinary page: one copy of it"
    assert w.document.pages[1].sheet is None


def test_a_new_sheets_workbook_copy_has_its_own_sheet_names(w):
    w.insert_sheet_page(0)
    pump()
    w.duplicate_page(1)
    pump()
    names = sorted(i.sheet.name for i in w.view.scene().items() if isinstance(i, SheetRunItem))
    assert len(names) == 2 and names[1] == f"{names[0]} (2)"
    assert len(sheetpages.sections(w.document)) == 2


# -- Add Page ---------------------------------------------------------------------------------------
def no_dialog_opened(monkeypatch):
    opened = []
    monkeypatch.setattr(QDialog, "exec", lambda self: opened.append(self) or 0)
    return opened


def test_add_page_from_the_thumbnails_button_no_questions(w, wb, monkeypatch):
    opened = no_dialog_opened(monkeypatch)
    w.interactive_prompts = True
    w.document.pages[0].setup.orientation = "landscape"
    w.go_to_page(0)
    pump()
    before = len(w.document.pages)
    steps = w.undo_stack.count()
    button = w.pages_panel.page_buttons["quick_add_page"]
    assert w.pages_panel.page_buttons and list(w.pages_panel.page_buttons)[0] == "quick_add_page"
    QTest.mouseClick(button, Qt.LeftButton)
    pump()
    assert not opened, "no dialog"
    assert len(w.document.pages) == before + 1 and w.undo_stack.count() == steps + 1
    added = w.document.pages[1]
    assert added.sheet is None and added.setup.orientation == "landscape"
    assert added.setup.width_mm == w.document.pages[0].setup.width_mm
    assert w.current_index == 1
    w.undo_stack.undo()
    pump()
    assert len(w.document.pages) == before


def test_add_page_on_a_workbook_goes_after_the_whole_workbook(w, wb, monkeypatch):
    opened = no_dialog_opened(monkeypatch)
    w.interactive_prompts = True
    before = len(w.document.pages)
    menu = w.page_menu(wb.first + 1)
    add = next(a for a in menu.actions() if a.text() == "Add Page")
    assert menu.actions().index(add) < next(
        k for k, a in enumerate(menu.actions()) if a.text() == "Duplicate Page")
    add.trigger()
    pump()
    assert not opened
    assert len(w.document.pages) == before + 1
    assert w.document.pages[wb.last + 1].sheet is None, "after the whole workbook"
    assert sheetpages.sections(w.document)[0].pages == wb.pages
    assert w.current_index == wb.last + 1 and w.scene.sheet_view is None
    # the Document menu's: first in Insert, beside Blank Page…
    page_menu = w.menuBar().findChild(QMenu, "menuDocument")
    insert = next(a.menu() for a in page_menu.actions() if a.text() == "Insert")
    texts = [a.text() for a in insert.actions()]
    assert texts[:2] == ["Add Page", "Blank Page"], texts
    w.go_to_page(0)
    pump()
    w.act_quick_add_page.trigger()
    pump()
    assert len(w.document.pages) == before + 2 and w.current_index == 1


def test_add_page_is_bindable(w):
    from calcforge.ui.bindable_list import ALIASES
    assert ALIASES["thumbnails.add_page"] == "command.quick_add_page"
    assert ALIASES["page.add_page"] == "command.quick_add_page"
    assert w.act_quick_add_page.shortcut().isEmpty(), "no free key that makes sense"
