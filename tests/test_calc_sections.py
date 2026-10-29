"""Calc section breaks in the window (the user's request, 2026-10-11): a
break above a page starts the calculation afresh — variables, tables and
sheets — except what was made global (an equation by right-click or the
Variables panel, a table's cells by right-click), which every later section
reads. The break shows above its page, is undone, saved and reopened."""
from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

import tests.calc.test_calcforge_window as cw
from calcforge.ui import calcsections
from calcforge.ui.calcmenu import change
from tests.test_table_equations import answers, table_at


@pytest.fixture
def v(window):
    window.show()
    window.activateWindow()
    window.interactive_prompts = False
    return cw.Sheet(window)


def pump():
    for _ in range(3):
        QApplication.instance().processEvents()


def on_page(v, index, y_px, keys):
    v.frame = v.window.document.pages[index].frame
    v.type_at(36, y_px, "")
    v.keys(keys)
    v.press(Qt.Key_Return)
    v.calc.leave()
    pump()


def item_named(v, name):
    return next(i for i in v.items.values()
                if i.region.editor.root.text().split(":")[0].split("≔")[0] == name)


def error_of(v, text):
    """The error of the equation whose text starts *text*, or None."""
    from calcforge.items.calc import CalcItem
    for item in v.window.view.scene().items():
        if isinstance(item, CalcItem) and item.region is not None and \
                item.region.editor.root.text().startswith(text):
            return item.region.error.message if item.region.error else None
    raise LookupError(text)


def two_pages(v):
    v.window.add_page(0)
    pump()
    on_page(v, 0, 40, "a:2")
    on_page(v, 1, 40, "c:a*3")
    on_page(v, 1, 80, "c=")
    assert answers(v)["c"] == "6"


def test_a_section_break_starts_the_calculation_afresh(v):
    two_pages(v)
    calcsections.set_break(v.window, 1, True)
    pump()
    assert v.window.document.pages[1].section_break
    assert "not defined" in (answers(v)["c"] or "")
    # undo takes the break out again
    v.window.undo_stack.undo()
    pump()
    assert not v.window.document.pages[1].section_break
    assert answers(v)["c"] == "6"
    v.window.undo_stack.redo()
    pump()
    assert "not defined" in (answers(v)["c"] or "")
    # the first page always starts the first section
    calcsections.set_break(v.window, 0, True)
    assert not v.window.document.pages[0].section_break


def test_a_global_equation_carries_on_past_the_break(v):
    two_pages(v)
    calcsections.set_break(v.window, 1, True)
    pump()
    a = item_named(v, "a")
    change(v.window, [a], "Make global", lambda r: setattr(r, "is_global", True))
    pump()
    assert answers(v)["c"] == "6"
    # and it is undone like any setting
    v.window.undo_stack.undo()
    pump()
    assert "not defined" in (answers(v)["c"] or "")


def test_the_variables_panel_shows_sections_and_makes_variables_global(v):
    from calcforge.ui.variablespanel import VariablesPanel
    two_pages(v)
    calcsections.set_break(v.window, 1, True)
    pump()
    panel = VariablesPanel(v.window)
    panel.refresh()
    tree = panel.tree
    tops = [tree.topLevelItem(i).text(0).lstrip("§ ") for i in range(tree.topLevelItemCount())]
    assert tops[0].startswith("Section 1") and any(t.startswith("Section 2") for t in tops)
    row = next(r for r in panel.rows if r.name == "a")
    assert row.section == 1 and not row.is_global
    panel.set_global(row, True)
    pump()
    assert answers(v)["c"] == "6"
    row = next(r for r in panel.rows if r.name == "a")
    assert row.is_global and "global" in row.where
    tops = [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]
    assert any(t.startswith("🌐 a") for t in tops)


def test_tables_are_reset_too_unless_their_cells_are_global(v):
    v.window.add_page(0)
    pump()
    v.frame = v.window.document.pages[0].frame
    table_at(v, 40, [["Load"], ["5"]], name="Loads")
    pump()
    on_page(v, 1, 40, "w:Loads.A2*2")
    on_page(v, 1, 80, "w=")
    assert answers(v)["w"] == "10"
    calcsections.set_break(v.window, 1, True)
    pump()
    assert "earlier calculation section" in (error_of(v, "w≔") or "")
    # the cell made global (as by its right-click ▸ Make Global)
    table = next(t for t in v.window.view.tables._all_tables() if t.sheet.name == "Loads")
    calcsections.set_cells_global(v.window, table, [1, 0, 1, 0], True)
    pump()
    assert answers(v)["w"] == "10"
    assert calcsections.cells_global(table.sheet, [1, 0, 1, 0])
    calcsections.set_cells_global(v.window, table, [1, 0, 1, 0], False)
    pump()
    assert "earlier calculation section" in (error_of(v, "w≔") or "")


def test_a_sheet_reads_another_only_where_it_is_global(v):
    from calcforge.sheet.docbook import book_for
    v.window.add_page(0)
    pump()
    v.frame = v.window.document.pages[0].frame
    table_at(v, 40, [["7"]], name="First")
    v.frame = v.window.document.pages[1].frame
    table_at(v, 40, [["=First!A1*2"]], name="Second")
    pump()
    wb = book_for(v.window.document).workbook
    second = wb.sheet("Second")
    assert wb.value(second, 0, 0) == 14
    calcsections.set_break(v.window, 1, True)
    pump()
    second = wb.sheet("Second")
    assert getattr(wb.value(second, 0, 0), "code", None) == "#REF!"
    first = next(t for t in v.window.view.tables._all_tables() if t.sheet.name == "First")
    calcsections.set_cells_global(v.window, first, [0, 0, 0, 0], True)
    pump()
    assert wb.value(wb.sheet("Second"), 0, 0) == 14


def test_the_break_is_saved_shown_and_named(v, tmp_path):
    two_pages(v)
    calcsections.set_break(v.window, 1, True, "Footings")
    a = item_named(v, "a")
    change(v.window, [a], "Make global", lambda r: setattr(r, "is_global", True))
    pump()
    parts = calcsections.sections(v.window.document)
    assert [p.label for p in parts] == ["Section 1 (page 1)", "Section 2 · Footings (page 2)"]
    # shown above page 2 on the canvas: drawn in the gap, purple
    view = v.window.view
    frame = v.window.document.pages[1].frame
    view.centerOn(frame.mapToScene(frame.page_rect().topLeft()))
    pump()
    image = view.viewport().grab().toImage()
    top = view.mapFromScene(frame.mapToScene(frame.page_rect().topLeft()))
    band = [image.pixelColor(x, top.y() - 12) for x in range(max(0, top.x()), top.x() + 200)]
    assert any(c.red() > 90 and c.blue() > 150 and c.green() < 110 for c in band)
    # saved and opened again
    path = tmp_path / "sections.pdf"
    v.window.document.path = str(path)
    assert v.window.save_document()
    pump()
    v.window.open_path(str(path))
    pump()
    pages = v.window.document.pages
    assert pages[1].section_break and pages[1].section_title == "Footings"
    assert answers(v)["c"] == "6"
    from calcforge.items.calc import CalcItem
    assert any(i.region.is_global for i in v.window.view.scene().items()
               if isinstance(i, CalcItem) and i.region is not None)
