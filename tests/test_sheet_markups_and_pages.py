"""The user, 2026-10-23: "Can't press delete to delete pages"; "Placed
markup disappear on a spreadsheet, and depending on what I click it comes
back and then disappears again"; "Could[n't] move the chart in the Excel I
added"; "Add charts to a normal sheet".
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, Qt
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
