"""The user's 2026-10-29 round, in a window: files dropped on the window
and the page; File ▸ New beside the document open; arrow keys never leave
half a cell under the headings; CF(x) and CALC(expression) in cells, never
the workbook's own cell; Sheet1.A1= answered before the sheet; a calc
section's purple band in Thumbnails and the Variables panel."""
from __future__ import annotations

import time

import pytest
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

pymupdf = pytest.importorskip("pymupdf")
openpyxl = pytest.importorskip("openpyxl")

from calcforge.items.sheetpage import SheetRunItem  # noqa: E402


def pump(seconds=0.0):
    end = time.monotonic() + seconds
    QApplication.processEvents()
    while time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.01)


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.interactive_prompts = False
    window.confirm_discard = lambda: True
    pump()
    return window


def a_pdf(path, pages=2) -> str:
    doc = pymupdf.open()
    for k in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), f"Dropped sheet {k + 1}")
    doc.save(str(path))
    return str(path)


def a_workbook(path) -> str:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Loads"
    ws["A1"], ws["B1"] = "Dead", 4.5
    wb.save(str(path))
    return str(path)


def a_picture(path) -> str:
    from PySide6.QtGui import QImage, QColor
    image = QImage(120, 80, QImage.Format_RGB32)
    image.fill(QColor("#4472C4"))
    image.save(str(path))
    return str(path)


def drop(widget, paths, at=QPoint(200, 200)):
    """Files dropped on *widget* (the window, or the view for a page): Qt
    delivers a drop only from a live drag, so the handlers take it here,
    after the drag-enter has said yes."""
    from PySide6.QtGui import QDragEnterEvent
    data = QMimeData()
    data.setUrls([QUrl.fromLocalFile(p) for p in paths])
    enter = QDragEnterEvent(at, Qt.CopyAction, data, Qt.LeftButton, Qt.NoModifier)
    widget.dragEnterEvent(enter)
    assert enter.isAccepted(), "the drag is welcome"
    event = QDropEvent(QPointF(at), Qt.CopyAction, data, Qt.LeftButton, Qt.NoModifier)
    widget.dropEvent(event)
    assert event.isAccepted()
    pump(0.3)
    return event


def tabs(w) -> int:
    return w.document_tabs.count()


def test_a_pdf_dropped_on_the_window_opens_in_its_own_tab(w, tmp_path):
    assert w.droppable(a_pdf(tmp_path / "set.pdf")) == "pdf"
    assert w.droppable(str(tmp_path / "notes.txt")) == ""
    w.quick_add_page(0)                                # the document is worked on
    pump(0.1)
    before = w.document
    drop(w, [str(tmp_path / "set.pdf")])
    assert w.document is not before, "opened beside it"
    assert len(w.document.pages) == 2 and w.document.path.endswith("set.pdf")
    assert tabs(w) == 2


def test_a_workbook_dropped_on_a_page_goes_in_after_it(w, tmp_path):
    path = a_workbook(tmp_path / "loads.xlsx")
    assert w.droppable(path) == "workbook"
    for _ in range(2):
        w.quick_add_page(len(w.document.pages) - 1)
    pump(0.1)
    assert len(w.document.pages) == 3
    w.go_to_page(1)
    pump(0.2)
    frame = w.scene.frames[1]
    where = w.view.mapFromScene(frame.mapToScene(frame.boundingRect().center()))
    drop(w.view, [path], where)
    assert len(w.document.pages) == 4
    assert w.document.pages[2].sheet is not None, "the sheet's page follows the one dropped on"
    assert w.document.pages[1].sheet is None and w.document.pages[3].sheet is None
    run = next(i for i in w.view.scene().items() if isinstance(i, SheetRunItem))
    assert run.sheet.name == "Loads"


def test_a_workbook_dropped_on_an_untouched_window_opens_as_its_document(w, tmp_path):
    path = a_workbook(tmp_path / "loads.xlsx")
    drop(w, [path])
    assert w.document.pages and all(p.sheet is not None for p in w.document.pages)


def test_a_picture_dropped_in_is_a_page(w, tmp_path):
    path = a_picture(tmp_path / "photo.png")
    assert w.droppable(path) == "image"
    w.quick_add_page(0)
    pump(0.1)
    drop(w, [path])
    assert len(w.document.pages) == 3
    assert any(p.background_key for p in w.document.pages), "a page drawn from the picture"


def test_file_new_opens_beside_the_document_being_worked_on(w):
    before = w.document
    w.quick_add_page(0)
    pump(0.1)
    assert not w._untouched()
    w.new_document()
    pump(0.2)
    assert w.document is not before
    assert tabs(w) == 2, "the old document kept in its tab"
    assert len(before.pages) == 2 and len(w.document.pages) == 1


def test_file_new_on_an_untouched_window_stays_in_place(w):
    assert w._untouched()
    w.new_document()
    pump(0.1)
    assert tabs(w) <= 1


def test_arrow_scrolling_never_leaves_half_a_cell_under_the_headings(w):
    """Scrolled by an arrow key, the sheet shown alone starts on a whole
    row (the user: "using arrows to scroll should never half scroll over a
    cell"), and editing a cell brings it into view."""
    from calcforge.items.table import HEADING_H
    from calcforge.ui.sheetview import _item, run_shown
    w.insert_spreadsheet(0)
    pump(0.3)
    run = next(i for i in w.view.scene().items() if isinstance(i, SheetRunItem))
    w.go_to_page(w.document.index_of(run.parentItem().page))
    from calcforge.ui import sheetview
    sheetview.enter(w, run.uid)
    pump(0.3)
    view = w.view
    run = _item(w, run_shown(view.scene()))
    assert run is not None, "the sheet alone in the view"
    view.set_zoom(2.0)
    pump(0.3)
    viewport = view.viewport()
    centre = view.mapFromScene(run.mapToScene(run.cell_rect(2, 1).center()))
    QTest.mouseClick(viewport, Qt.LeftButton, Qt.NoModifier, centre)
    pump(0.1)
    xs, ys = run.edges()
    moved = False
    for _ in range(60):
        before = view.verticalScrollBar().value()
        QTest.keyClick(viewport, Qt.Key_Down)
        pump(0.05)
        if view.verticalScrollBar().value() != before:
            moved = True
            seen = run.mapRectFromScene(view.mapToScene(viewport.rect()).boundingRect())
            top = seen.top() + HEADING_H
            nearest = min(ys, key=lambda y: abs(y - top))
            assert abs(nearest - top) < 0.75, f"the first row shown starts whole ({top} vs {nearest})"
    assert moved, "the arrows scrolled the sheet"
    # editing a cell far below scrolls it into view
    tables = view.tables
    tables.active = (40, 1)
    tables.begin_edit("5")
    pump(0.2)
    seen = run.mapRectFromScene(view.mapToScene(viewport.rect()).boundingRect())
    assert seen.contains(run.cell_rect(40, 1)), "the cell being edited is in sight"
    tables.cancel()


def equation(w, x, y, text):
    from tests.test_calc_editing import type_line
    frame = w.document.pages[0].frame
    w.toggle_calc_mode(True)
    w.view.calc.place_cross(frame, QPointF(x, y))
    type_line(w, text)
    w.toggle_calc_mode(False)
    pump(0.1)


def test_cf_and_calc_read_calcforge_expressions_and_never_the_workbooks_own_cell(w):
    equation(w, 60, 80, "height:3.5'm")
    equation(w, 60, 120, "ting:7")
    w.insert_spreadsheet(0)
    pump(0.3)
    run = next(i for i in w.view.scene().items() if isinstance(i, SheetRunItem))
    sheet, wb = run.sheet, run.sheet.workbook
    wb.set_input(sheet, 5, 0, "99")
    wb.define_name("ting", f"{sheet.name}!$A$6", variable=True)   # its own cell named ting
    asked = ["=CF(height)", "=CF(height*2)", "=CALC(height+1'm)", "=CF(ting)", "=CALC(ting)",
             "=ting", "=CF(zz)", "=CF()"]
    for r, text in enumerate(asked):
        wb.set_input(sheet, r, 1, text)
    wb.recalculate()
    pump(0.2)

    def shown(r):
        from calcforge.sheet.numfmt import format_value
        cell = sheet.cells.get((r, 1))
        st = wb.styles.get(cell.style)
        return format_value(cell.value, st.number_format, st.unit).text, cell.value
    assert shown(0)[0].startswith("3.5")
    assert shown(1)[0].startswith("7")
    assert shown(2)[0].startswith("4.5")
    assert shown(3)[0].startswith("7"), "CF(ting) is the equation's 7, never the cell named ting"
    assert shown(4)[0].startswith("7")
    assert shown(5)[0] == "#NAME?", "a Variable box's name is CalcForge's, not an Excel name"
    why = getattr(shown(6)[1], "reason", "")
    assert "no CalcForge variable zz" in why
    assert "takes a CalcForge variable or expression" in getattr(shown(7)[1], "reason", "")


def test_a_sheet_cell_asked_before_its_sheet_says_so(w):
    from calcforge.calc.docsheet import sheet_for
    w.insert_spreadsheet(0)                             # Sheet1 on page 2
    pump(0.2)
    run = next(i for i in w.view.scene().items() if isinstance(i, SheetRunItem))
    name = run.sheet.name
    run.sheet.workbook.set_input(run.sheet, 0, 0, "12")
    w.go_to_page(0)
    equation(w, 60, 80, f"{name}.A1=")
    pump(0.3)
    item = next(i for i in sheet_for(w.document).items.values()
                if i.region.editor.root.text().startswith(name))
    said = str(item.region.error or "")
    assert "comes after this equation" in said and "reads a sheet before it" in said


def test_a_calc_section_break_is_a_purple_band_in_thumbnails_and_the_variables_panel(w):
    from PySide6.QtGui import QColor
    from calcforge.ui import calcsections
    from calcforge.ui.panels import BREAK_ROLE
    for _ in range(2):
        w.quick_add_page(len(w.document.pages) - 1)
    pump(0.1)
    equation(w, 60, 80, "a:1")
    w.go_to_page(1)
    calcsections.set_break(w, 1, True, "Roof")
    pump(0.3)
    strip = w.pages_panel.list
    assert strip.item(1).data(BREAK_ROLE) == "Roof", "the band's tag on the page it starts"
    assert strip.item(0).data(BREAK_ROLE) in (None, "")
    panel = w.variables_panel
    panel.refresh()
    pump(0.2)
    tree = panel.tree

    def rows(parent):
        out = []
        for k in range(parent.childCount() if hasattr(parent, "childCount") else parent.topLevelItemCount()):
            child = parent.child(k) if hasattr(parent, "childCount") else parent.topLevelItem(k)
            out.append(child)
            out.extend(rows(child))
        return out
    banded = [h for h in rows(tree) if h.text(0).startswith("§ ")]
    assert banded, "the section's heading"
    assert banded[0].background(0).color() == QColor(calcsections.BAND)
