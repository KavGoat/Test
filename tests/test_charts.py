"""Charts (spreadsheet phase 5), through the real window: inserted from the
cells picked out in a table, following their cells, edited in their dialog,
following renames and inserted rows, undone, saved and reopened, on a
spreadsheet page over its cells, and printed with the page."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter

from calcforge.items.chart import ChartItem
from calcforge.sheet.refs import parse_cell
from tests.test_tables import make_table, pump


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.view.set_zoom(1.0)
    return window


def put(table, a1, text):
    r = parse_cell(a1)
    table.sheet.workbook.set_input(table.sheet, r.row, r.col, text)


def charts(w):
    return [i for i in w.view.scene().items() if isinstance(i, ChartItem)]


def deflections(w):
    table = make_table(w, x=60, y=80, width=48 * 3, height=15 * 6)
    rows = [("Span", "Deflection", "Limit"), ("2 m", "1.2 mm", "5 mm"), ("3 m", "3.9 mm", "7.5 mm"),
            ("4 m", "9.1 mm", "10 mm"), ("5 m", "17.8 mm", "12.5 mm"), ("6 m", "30.5 mm", "15 mm")]
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            put(table, "ABC"[c] + str(r + 1), text)
    return table


def chart_of(w, table, kind="scatter", lines=False, markers=True, block=(0, 0, 5, 2)):
    w.view.tables.open(table, (0, 0))
    w.view.tables.select(block[:2], block[2:])
    chart = w.insert_chart(kind, lines, markers)
    pump()
    return chart


def ink(chart, colour=None):
    """Pixels of the chart (or of one colour) drawn at 2×."""
    import numpy as np
    image = QImage(int(chart.rect.width() * 2), int(chart.rect.height() * 2), QImage.Format_RGB32)
    image.fill(0xFFFFFFFF)
    p = QPainter(image)
    p.scale(2, 2)
    chart.paint_content(p)
    p.end()
    a = np.frombuffer(image.constBits(), np.uint8).reshape(
        image.height(), image.bytesPerLine() // 4, 4)[:, :image.width(), :3].astype(int)
    if colour is None:
        return (a.mean(axis=2) < 200).sum()
    r, g, b = int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16)
    return ((abs(a[:, :, 2] - r) < 30) & (abs(a[:, :, 1] - g) < 30) & (abs(a[:, :, 0] - b) < 30)).sum()


def test_insert_chart_reads_the_selection_as_excel_does(w):
    table = deflections(w)
    chart = chart_of(w, table)
    assert charts(w) == [chart]
    spec = chart.spec
    name = table.name
    assert spec["kind"] == "scatter"
    assert [s["y"] for s in spec["series"]] == [f"{name}!$B$2:$B$6", f"{name}!$C$2:$C$6"]
    assert all(s["x"] == f"{name}!$A$2:$A$6" for s in spec["series"])
    data = chart.data()
    assert [d.name for d in data] == ["Deflection", "Limit"]
    assert data[0].xs == [2, 3, 4, 5, 6] and data[0].y_unit == "mm" and data[0].x_unit == "m"
    # beside the table on its page, drawn in Office blue and orange
    box = table.mapRectToParent(table.local_rect())
    assert chart.parentItem() is table.parentItem()
    assert chart.pos().x() >= box.right()
    assert ink(chart, "#4472C4") > 100 and ink(chart, "#ED7D31") > 100
    # one undo step takes it away
    w.undo_stack.undo()
    pump()
    assert charts(w) == []


def test_a_chart_follows_its_cells(w):
    table = deflections(w)
    chart = chart_of(w, table)
    assert chart.data()[0].ys[-1] == 30.5
    put(table, "B6", "60 mm")
    assert chart.data()[0].ys[-1] == 60
    # rows inserted into the table: the ranges move with the cells
    w.view.tables.open(table, (2, 0))
    w.view.tables.select((2, 0))
    w.view.tables.insert_rows()
    pump()
    (chart,) = charts(w)
    assert chart.spec["series"][0]["y"].endswith("$B$2:$B$7")
    # a renamed table: the ranges follow
    assert w.view.tables.rename_to(table, "Deflections")
    (chart,) = charts(w)
    assert chart.spec["series"][0]["y"].startswith("Deflections!")
    assert chart.data()[0].name == "Deflection"


def test_the_dialog_changes_type_axes_series_error_bars_and_trendline(w):
    from calcforge.ui.chartdialog import ChartDialog, apply_dialog
    table = deflections(w)
    chart = chart_of(w, table)
    w.interactive_prompts = False
    w._edit_chart(chart)
    dialog = w._last_chart_dialog
    assert isinstance(dialog, ChartDialog)
    dialog.type.setCurrentIndex(1)                  # scatter with lines
    dialog.title.setText("Deflection check")
    dialog.axes["y_axis"]["log"].setChecked(True)
    dialog.axes["x_axis"]["max"].setText("8")
    dialog.series_list.setCurrentRow(0)
    dialog.e_type.setCurrentIndex(2)                # percentage
    dialog.e_value.setText("10")
    dialog.t_type.setCurrentIndex(2)                # polynomial
    dialog.t_order.setValue(2)
    dialog.t_eq.setChecked(True)
    dialog.t_r2.setChecked(True)
    dialog.series_list.setCurrentRow(1)
    dialog.remove_series()
    apply_dialog(w, chart, dialog)
    (chart,) = charts(w)
    spec = chart.spec
    assert spec["kind"] == "scatter" and spec["lines"] and spec["markers"]
    assert spec["title"] == "Deflection check"
    assert spec["y_axis"]["log"] and spec["x_axis"]["max"] == 8
    assert len(spec["series"]) == 1
    s = spec["series"][0]
    assert s["error"]["type"] == "percent" and s["error"]["value"] == 10
    assert s["trend"]["type"] == "poly" and s["trend"]["equation"] and s["trend"]["r2"]
    assert ink(chart) > 500
    w.undo_stack.undo()
    pump()
    (chart,) = charts(w)
    assert len(chart.spec["series"]) == 2 and not chart.spec["y_axis"]["log"]


def test_column_and_line_charts_use_categories(w):
    table = deflections(w)
    put(table, "A2", "B1")
    put(table, "A3", "B2")
    chart = chart_of(w, table, "column", block=(0, 0, 5, 1))
    assert chart.spec["kind"] == "column"
    data = chart.data()
    assert data[0].categories[:2] == ["B1", "B2"]
    assert ink(chart, "#4472C4") > 300
    line = chart_of(w, table, "line", lines=True, markers=False, block=(0, 0, 5, 2))
    assert line.data()[1].categories[:2] == ["B1", "B2"]


def test_charts_are_saved_and_printed_with_the_page(w, tmp_path):
    import pymupdf
    from tests.test_calc_saving import reopen, save_to
    table = deflections(w)
    chart = chart_of(w, table)
    spec = chart.spec
    spec["title"] = "SAVED CHART"
    chart.set_spec(spec)
    w.view.tables.close()
    path = str(tmp_path / "chart.pdf")
    save_to(w, path)
    with pymupdf.open(path) as doc:
        assert "SAVED CHART" in doc[0].get_text(), "the chart is drawn into the page"
        assert list(doc[0].annots()) == [], "and is not an annotation"
    reopen(w, path)
    pump()
    pump()
    (chart,) = charts(w)
    assert chart.spec["title"] == "SAVED CHART"
    assert chart.data()[0].ys[:2] == [1.2, 3.9]


def test_a_chart_on_a_sheet_page_sits_over_the_cells_and_moves_with_them(w):
    from calcforge.items.sheetpage import SheetRunItem
    w.insert_sheet_page(0)
    pump()
    (run,) = [i for i in w.view.scene().items() if isinstance(i, SheetRunItem)]
    wb = run.sheet.workbook
    for r, (x, y) in enumerate([("Span", "Load"), ("1", "3"), ("2", "5"), ("3", "4")]):
        wb.set_input(run.sheet, r, 0, x)
        wb.set_input(run.sheet, r, 1, y)
    w.view.tables.open(run, (0, 0))
    w.view.tables.select((0, 0), (3, 1))
    chart = w.insert_chart("scatter")
    pump()
    frame = w.document.pages[1].frame
    assert chart.parentItem() is frame
    where = run.mapFromScene(chart.scenePos())
    assert where.x() == pytest.approx(run.cell_rect(0, 1).right() + 12)
    # rows inserted above it: it moves down with its cells
    w.view.tables.open(run, (0, 0))
    w.view.tables.select((0, 0), (1, 0))
    w.view.tables.insert_rows()
    pump()
    (chart,) = [c for c in charts(w)]
    assert run.mapFromScene(chart.scenePos()).y() == pytest.approx(run.cell_rect(2, 0).top())
    # it prints on the sheet page's paper
    image = QImage(int(frame.page.width_pt), int(frame.page.height_pt), QImage.Format_RGB32)
    image.fill(0xFFFFFFFF)
    p = QPainter(image)
    frame.render_page(p, QRectF(0, 0, image.width(), image.height()), for_print=True)
    p.end()
    import numpy as np
    a = np.frombuffer(image.constBits(), np.uint8).reshape(
        image.height(), image.bytesPerLine() // 4, 4)[:, :image.width(), :3].astype(int)
    blue = ((abs(a[:, :, 2] - 0x44) < 30) & (abs(a[:, :, 1] - 0x72) < 30)
            & (abs(a[:, :, 0] - 0xC4) < 30)).sum()
    assert blue > 30, "the chart's series prints"


def test_double_click_opens_the_chart_dialog(w):
    from tests.test_tables import click
    table = deflections(w)
    chart = chart_of(w, table)
    w.view.tables.close()
    w.interactive_prompts = False
    pos = chart.mapToScene(chart.rect.center())
    w.view.centerOn(pos)
    pump()
    click(w, pos, double=True)
    assert getattr(w, "_last_chart_dialog", None) is not None
    assert w.view.tables.item is None
