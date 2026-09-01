"""End-to-end exercises against a real main window (offscreen)."""
import os

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from calcforge.items.mathitem import MathItem
from calcforge.items.measure import CountItem, MeasureItem
from calcforge.items.tableitem import TableItem
from calcforge.items.text import TextItem
from calcforge.ui.tools import DRAG, FREE, POLY, TOOLS

# ---------------------------------------------------------------------------
# event helpers
# ---------------------------------------------------------------------------

def _event(view, kind, x, y, button=Qt.LeftButton, buttons=None, modifiers=Qt.NoModifier):
    local = view.mapFromScene(QPointF(x, y))
    globally = view.viewport().mapToGlobal(local)
    if buttons is None:
        buttons = button if kind != QEvent.MouseButtonRelease else Qt.NoButton
    return QMouseEvent(kind, QPointF(local), QPointF(globally), button, buttons, modifiers)


def press(view, x, y, modifiers=Qt.NoModifier):
    view.mousePressEvent(_event(view, QEvent.MouseButtonPress, x, y, modifiers=modifiers))


def move(view, x, y, modifiers=Qt.NoModifier):
    view.mouseMoveEvent(_event(view, QEvent.MouseMove, x, y, Qt.NoButton,
                               Qt.LeftButton, modifiers))


def release(view, x, y, modifiers=Qt.NoModifier):
    view.mouseReleaseEvent(_event(view, QEvent.MouseButtonRelease, x, y,
                                  modifiers=modifiers))


def double_click(view, x, y):
    view.mouseDoubleClickEvent(_event(view, QEvent.MouseButtonDblClick, x, y))


def key(view, code, text="", modifiers=Qt.NoModifier):
    view.keyPressEvent(QKeyEvent(QEvent.KeyPress, code, modifiers, text))


def drag(view, x0, y0, x1, y1):
    press(view, x0, y0)
    move(view, (x0 + x1) / 2, (y0 + y1) / 2)
    move(view, x1, y1)
    release(view, x1, y1)


def markups(window):
    """Markups in reading order, so tests can index them deterministically."""
    return window.view.scene().ordered_markups()


def editing_item(window):
    return getattr(window.view, "_editing_item", None)


# ---------------------------------------------------------------------------
# tools
# ---------------------------------------------------------------------------

DRAG_TOOLS = [t.key for t in TOOLS if t.mode == DRAG and t.key not in ("image", "calibrate")]
POLY_TOOLS = [t.key for t in TOOLS if t.mode == POLY]
FREE_TOOLS = [t.key for t in TOOLS if t.mode == FREE]


@pytest.mark.parametrize("tool_key", DRAG_TOOLS)
def test_drag_tools_create_a_markup(window, tool_key):
    window.select_tool(tool_key)
    before = len(markups(window))
    drag(window.view, 100, 120, 240, 220)
    assert len(markups(window)) == before + 1
    created = markups(window)[-1]
    assert created.local_rect().width() > 2 or getattr(created, "points", None)


@pytest.mark.parametrize("tool_key", POLY_TOOLS)
def test_polygon_tools_create_a_markup(window, tool_key):
    window.select_tool(tool_key)
    before = len(markups(window))
    for x, y in ((100, 120), (200, 120), (200, 240)):
        press(window.view, x, y)
        release(window.view, x, y)
        move(window.view, x + 10, y + 10)
    window.view.finish_poly()
    assert len(markups(window)) == before + 1


@pytest.mark.parametrize("tool_key", FREE_TOOLS)
def test_freehand_tools_record_a_stroke(window, tool_key):
    window.select_tool(tool_key)
    press(window.view, 80, 80)
    for step in range(12):
        move(window.view, 80 + step * 8, 80 + step * 4)
    release(window.view, 168, 128)
    created = markups(window)[-1]
    assert len(created.points) > 3


def test_count_tool_places_numbered_markers(window):
    window.select_tool("count")
    window.view.count_subject = "Doors"
    for index, x in enumerate((100, 160, 220)):
        press(window.view, x, 300)
        release(window.view, x, 300)
        window.select_tool("count")
    counts = sorted([i for i in markups(window) if isinstance(i, CountItem)],
                    key=lambda item: item.pos().x())
    assert [c.index for c in counts] == [1, 2, 3]


def test_tool_returns_to_select_after_drawing(window):
    window.select_tool("rect")
    drag(window.view, 60, 60, 160, 160)
    assert window.view.tool_key == "select"


def test_sticky_tool_keeps_drawing(window):
    window.act_sticky.setChecked(True)
    window.select_tool("rect")
    drag(window.view, 60, 60, 160, 160)
    assert window.view.tool_key == "rect"
    drag(window.view, 200, 60, 300, 160)
    assert len(markups(window)) == 2
    window.act_sticky.setChecked(False)


# ---------------------------------------------------------------------------
# selection and editing
# ---------------------------------------------------------------------------

def test_select_move_and_undo(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 200)
    rect = markups(window)[-1]
    origin = rect.pos()
    window.select_tool("select")
    press(window.view, 150, 150)
    move(window.view, 250, 250)
    release(window.view, 250, 250)
    assert rect.pos() != origin
    window.undo_stack.undo()
    moved = [i for i in markups(window) if i.TYPE == "rect"][0]
    assert moved.pos().x() == pytest.approx(origin.x(), abs=0.6)


def test_resize_with_a_handle(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 160)
    rect = markups(window)[-1]
    window.select_tool("select")
    rect.setSelected(True)
    corner = rect.mapToScene(rect.handle_points()["se"])
    press(window.view, corner.x(), corner.y())
    move(window.view, corner.x() + 80, corner.y() + 40)
    release(window.view, corner.x() + 80, corner.y() + 40)
    assert rect.local_rect().width() > 150


def test_rubber_band_selects_several(window):
    window.select_tool("rect")
    drag(window.view, 80, 80, 140, 140)
    window.select_tool("rect")
    drag(window.view, 180, 80, 240, 140)
    window.select_tool("select")
    press(window.view, 40, 40)
    move(window.view, 300, 200)
    release(window.view, 300, 200)
    assert len(window.selected_items()) == 2


def test_delete_copy_paste_and_duplicate(window):
    window.select_tool("ellipse")
    drag(window.view, 100, 100, 180, 160)
    window.select_tool("select")
    markups(window)[-1].setSelected(True)
    window.copy_selection()
    window.paste_items()
    assert len(markups(window)) == 2
    window.duplicate_selection()
    assert len(markups(window)) == 3
    window.select_all()
    window.delete_selection()
    assert markups(window) == []
    window.undo_stack.undo()
    assert len(markups(window)) == 3


def test_z_order_and_alignment(window):
    for x in (60, 200):
        window.select_tool("rect")
        drag(window.view, x, 60, x + 80, 140)
    window.select_tool("select")
    window.select_all()
    window.reorder("front")
    window.align_items("top")
    tops = {round(i.sceneBoundingRect().top(), 1) for i in window.selected_items()}
    assert len(tops) == 1


def test_lock_prevents_moving(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 200)
    rect = markups(window)[-1]
    window.select_tool("select")
    rect.setSelected(True)
    window.toggle_lock()
    origin = rect.pos()
    press(window.view, 150, 150)
    move(window.view, 260, 260)
    release(window.view, 260, 260)
    assert rect.pos() == origin


def test_nudge_with_arrow_keys(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 160, 160)
    rect = markups(window)[-1]
    window.select_tool("select")
    rect.setSelected(True)
    origin = rect.pos().x()
    key(window.view, Qt.Key_Right)
    assert rect.pos().x() > origin


# ---------------------------------------------------------------------------
# calculations
# ---------------------------------------------------------------------------

def test_math_block_editing_updates_variables(window):
    window.select_tool("math")
    drag(window.view, 80, 80, 380, 180)
    block = editing_item(window)
    assert isinstance(block, MathItem) and block.editing
    block._editor.setPlainText("L := 6 m\nw := 12 kN/m\nM := w*L^2/8 -> kN*m")
    window.view.end_item_edit()
    assert window.document.workspace.get("M").to("kN*m").magnitude == pytest.approx(54)
    assert window.variables_panel.table.rowCount() >= 3


def test_table_typing_and_navigation(window):
    window.select_tool("table")
    drag(window.view, 80, 80, 400, 240)
    table = window.view.active_table
    assert isinstance(table, TableItem)
    key(window.view, Qt.Key_A, "5")
    assert window.view._cell_editor is not None
    window.view._cell_editor.setText("5 kN")
    window.view.close_cell_editor(move=(1, 0))
    assert table.sheet.value(0, 0).to("kN").magnitude == pytest.approx(5)
    assert table.current == (1, 0)
    key(window.view, Qt.Key_A, "3")
    window.view._cell_editor.setText("=A1*2")
    window.view.close_cell_editor()
    assert table.sheet.value(1, 0).to("kN").magnitude == pytest.approx(10)
    key(window.view, Qt.Key_Escape)
    assert window.view.active_table is None


def test_table_reads_math_variables(window):
    window.select_tool("math")
    drag(window.view, 60, 60, 320, 130)
    block = editing_item(window)
    block._editor.setPlainText("gamma := 24 kN/m^3")
    window.view.end_item_edit()

    window.select_tool("table")
    drag(window.view, 60, 300, 380, 420)
    table = window.view.active_table
    table.set_cell(0, 0, "2 m^3")
    table.set_cell(0, 1, "=A1*gamma")
    window.recalculate()
    assert table.sheet.value(0, 1).to("kN").magnitude == pytest.approx(48)


def test_fill_down_translates_formulas(window):
    window.select_tool("table")
    drag(window.view, 60, 60, 400, 240)
    table = window.view.active_table
    table.set_cell(0, 0, "1")
    table.set_cell(1, 0, "2")
    table.set_cell(2, 0, "3")
    table.set_cell(0, 1, "=A1*10")
    table.current, table.anchor = (0, 1), (2, 1)
    window.view.fill_down()
    assert table.sheet.value(2, 1) == 30


def test_recalculation_order_handles_forward_references(window):
    window.select_tool("math")
    drag(window.view, 60, 400, 320, 470)
    editing_item(window)._editor.setPlainText("total := base * 2")
    window.view.end_item_edit()

    window.select_tool("math")
    drag(window.view, 60, 80, 320, 150)
    editing_item(window)._editor.setPlainText("base := 5 kN")
    window.view.end_item_edit()

    assert window.document.workspace.get("total").to("kN").magnitude == pytest.approx(10)


# ---------------------------------------------------------------------------
# measurement
# ---------------------------------------------------------------------------

def test_measurement_follows_the_page_scale(window):
    from calcforge.core.document import PageScale
    window.current_page().scale = PageScale.from_ratio(100)
    window.select_tool("measure_length")
    drag(window.view, 100, 400, 300, 400)
    measure = [i for i in markups(window) if isinstance(i, MeasureItem)][0]
    assert measure.value.to("m").magnitude == pytest.approx(7.0555, rel=2e-2)
    assert "m" in measure.value_text


def test_area_measurement_and_takeoff_totals(window):
    from calcforge.core.document import PageScale
    window.current_page().scale = PageScale.from_ratio(50)
    window.select_tool("measure_area")
    for x, y in ((100, 400), (300, 400), (300, 550), (100, 550)):
        press(window.view, x, y)
        release(window.view, x, y)
        move(window.view, x, y)
    window.view.finish_poly()
    window.recalculate()
    assert "Area" in window.markups_panel.totals.text()


# ---------------------------------------------------------------------------
# pages, files and export
# ---------------------------------------------------------------------------

def test_page_operations(window):
    window.add_page()
    assert len(window.document.pages) == 2
    window.duplicate_page()
    assert len(window.document.pages) == 3
    window.move_page(2, 0)
    assert window.current_index == 0
    window.undo_stack.undo()
    assert len(window.document.pages) == 3
    window.undo_stack.undo()
    assert len(window.document.pages) == 2


def test_page_setup_defaults_to_a4(window):
    setup = window.current_page().setup
    assert setup.size_name == "A4"
    assert setup.width_pt == pytest.approx(595.28, rel=1e-3)
    assert setup.height_pt == pytest.approx(841.89, rel=1e-3)


def test_save_and_reload_round_trip(window, tmp_path):
    window.select_tool("math")
    drag(window.view, 80, 80, 340, 160)
    block = [i for i in markups(window) if isinstance(i, MathItem)][0]
    block._editor.setPlainText("a := 3 m\nb := a*2")
    window.view.end_item_edit()
    window.select_tool("rect")
    drag(window.view, 80, 300, 200, 380)

    path = str(tmp_path / "doc.cfx")
    from calcforge.io import project as project_io
    project_io.save_document(window.document, path)

    from calcforge.core.document import Document
    reopened = Document()
    project_io.load_document(reopened, path)
    window.document = reopened
    window.rebuild_scenes()
    assert len(window.document.pages) == 1
    assert len(markups(window)) == 2
    assert window.document.workspace.get("b").to("m").magnitude == pytest.approx(6)


def test_export_pdf_and_images(window, tmp_path):
    window.load_sample()
    from calcforge.io import export as export_io
    pdf_path = str(tmp_path / "out.pdf")
    export_io.export_pdf(window.document, pdf_path)
    assert os.path.getsize(pdf_path) > 3000
    written = export_io.export_images(window.document, str(tmp_path), 96)
    assert len(written) == len(window.document.pages)
    assert all(os.path.getsize(p) > 1000 for p in written)


def test_export_csv_reports(window, tmp_path):
    window.load_sample()
    from calcforge.io import export as export_io
    markup_csv = str(tmp_path / "m.csv")
    assert export_io.export_markups_csv(window.document, markup_csv) > 0
    variable_csv = str(tmp_path / "v.csv")
    assert export_io.export_variables_csv(window.document, variable_csv) > 10


def test_sample_document_is_consistent(window):
    window.load_sample()
    workspace = window.document.workspace
    assert len(window.document.pages) == 3
    assert workspace.get("q_floor").to("kPa").magnitude == pytest.approx(5.87, rel=1e-3)
    assert workspace.get("util_b") == pytest.approx(0.3911, rel=1e-3)
    assert workspace.get("q").to("kPa").magnitude == pytest.approx(149.8, rel=1e-3)


def test_zoom_controls(window):
    window.view.set_zoom(1.0)
    window.view.zoom_in()
    assert window.view.zoom() > 1.0
    window.view.zoom_out()
    assert window.view.zoom() == pytest.approx(1.0, rel=1e-3)
    window.view.fit_page()
    assert 0.05 < window.view.zoom() < 4.0


def test_markups_panel_lists_everything(window):
    window.select_tool("rect")
    drag(window.view, 60, 60, 160, 160)
    window.select_tool("text")
    drag(window.view, 200, 60, 340, 110)
    window.view.end_item_edit()
    window.recalculate()
    assert window.markups_panel.tree.topLevelItem(0).childCount() == 2


def test_context_menu_insert_places_an_item(window):
    window.view.scene().clearSelection()
    window._insert_at("text", QPointF(120, 160))
    created = markups(window)
    assert len(created) == 1 and isinstance(created[0], TextItem)
    assert created[0].pos() == QPointF(120, 160)


def test_context_menu_is_built_for_both_targets(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 200)
    window.select_tool("select")
    item = markups(window)[0]
    on_item = window.build_context_menu(item, QPointF(150, 150))
    on_page = window.build_context_menu(None, QPointF(400, 400))
    assert [a.text() for a in on_item.actions() if a.text()]
    assert any("Insert here" in a.text() for a in on_page.actions() if a.text())


def test_hidden_layers_are_not_picked(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 200)
    item = markups(window)[0]
    item.layer = "Markups"
    assert window.view.markup_at(QPointF(150, 150)) is item
    window.document.layers[0].visible = False
    assert window.view.markup_at(QPointF(150, 150)) is None
    window.document.layers[0].visible = True


def test_undo_restores_a_table_edit(window):
    window.select_tool("table")
    drag(window.view, 80, 80, 400, 240)
    table = window.view.active_table
    window.view.begin_snapshot()
    table.set_cell(0, 0, "42")
    window.recalculate()
    window.view.commit_snapshot("Edit cell")
    assert table.sheet.raw(0, 0) == "42"
    window.undo_stack.undo()
    restored = [i for i in markups(window) if isinstance(i, TableItem)][0]
    assert restored.sheet.raw(0, 0) == ""
    window.undo_stack.redo()
    restored = [i for i in markups(window) if isinstance(i, TableItem)][0]
    assert restored.sheet.raw(0, 0) == "42"


def test_page_scale_change_updates_measurements(window):
    from calcforge.core.document import PageScale
    window.current_page().scale = PageScale.from_ratio(100)
    window.select_tool("measure_length")
    drag(window.view, 100, 400, 300, 400)
    measure = [i for i in markups(window) if isinstance(i, MeasureItem)][0]
    first = measure.value.to("m").magnitude
    window.current_page().scale = PageScale.from_ratio(200)
    window.current_page().scene.refresh_items()
    assert measure.value.to("m").magnitude == pytest.approx(first * 2, rel=1e-6)


def _pdf_printer(path):
    from PySide6.QtPrintSupport import QPrinter
    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(path)
    return printer


def test_printing_survives_repeated_repaints(window, tmp_path):
    """The print-preview dialog repaints the same printer more than once."""
    from calcforge.io import export as export_io
    window.load_sample()
    printer = _pdf_printer(str(tmp_path / "preview.pdf"))
    export_io.print_document(window.document, printer)
    export_io.print_document(window.document, printer)
    assert os.path.getsize(str(tmp_path / "preview.pdf")) > 3000


def test_printing_fits_mixed_page_sizes_onto_one_paper(window, tmp_path):
    from calcforge.core.document import PageSetup
    from calcforge.io import export as export_io, pdfio
    window.load_sample()
    window.document.pages[1].setup = PageSetup.from_name("A3")
    window.document.pages[1].setup.orientation = "landscape"
    path = str(tmp_path / "print.pdf")
    export_io.print_document(window.document, _pdf_printer(path))
    source = pdfio.PdfSource(path)
    try:
        sizes = {(round(source.page_info(i).width_pt), round(source.page_info(i).height_pt))
                 for i in range(source.page_count)}
    finally:
        source.close()
    assert sizes == {(595, 842)}


def test_export_keeps_each_page_at_its_own_size(window, tmp_path):
    from calcforge.core.document import PageSetup
    from calcforge.io import export as export_io, pdfio
    window.load_sample()
    window.document.pages[1].setup = PageSetup.from_name("A3")
    window.document.pages[1].setup.orientation = "landscape"
    path = str(tmp_path / "export.pdf")
    export_io.export_pdf(window.document, path)
    source = pdfio.PdfSource(path)
    try:
        second = source.page_info(1)
    finally:
        source.close()
    assert round(second.width_pt) == 1191 and round(second.height_pt) == 842


def test_print_range_is_honoured(window, tmp_path):
    from PySide6.QtPrintSupport import QPrinter
    from calcforge.io import export as export_io, pdfio
    window.load_sample()
    path = str(tmp_path / "range.pdf")
    printer = _pdf_printer(path)
    printer.setPrintRange(QPrinter.PageRange)
    printer.setFromTo(2, 3)
    assert len(export_io.pages_for_printer(window.document, printer)) == 2
    export_io.print_document(window.document, printer)
    assert pdfio.page_count(path) == 2


def test_properties_panel_leaves_no_stale_widgets(window):
    """Rebuilding the panel must unparent the old widgets, not just unlayout them."""
    from PySide6.QtWidgets import QLabel

    window.select_tool("math")
    drag(window.view, 70, 90, 400, 190)
    editing_item(window)._editor.setPlainText("# Beam check\nb := 300 mm")
    window.view.end_item_edit()

    block = [i for i in markups(window) if isinstance(i, MathItem)][0]
    window.view.scene().clearSelection()
    block.setSelected(True)
    window.refresh_selection()

    headings = [w for w in window.properties_panel.body.findChildren(QLabel)
                if w.parent() is not None and w.text().startswith("Calc")]
    assert [w.text() for w in headings] == [block.display_name()]

    window.view.scene().clearSelection()
    window.refresh_selection()
    assert not [w for w in window.properties_panel.body.findChildren(QLabel)
                if w.parent() is not None and w.text().startswith("Calc")]


def test_properties_panel_relayouts_when_the_selection_changes(window):
    """The scroll area must follow the new form, not the previous one."""
    window.select_tool("table")
    drag(window.view, 80, 80, 400, 240)
    window.select_tool("select")
    window.view.deactivate_table()
    table = [i for i in markups(window) if isinstance(i, TableItem)][0]
    window.view.scene().clearSelection()
    table.setSelected(True)
    window.refresh_selection()
    tall = window.properties_panel.body.sizeHint().height()

    window.select_tool("note")
    from calcforge.items.measure import MeasureItem
    measure = MeasureItem("length", [QPointF(0, 0), QPointF(100, 0)])
    window.view.scene().add_markup(measure, QPointF(120, 500))
    window.view.scene().clearSelection()
    measure.setSelected(True)
    window.properties_panel.verticalScrollBar().setValue(50)
    window.refresh_selection()

    assert window.properties_panel.verticalScrollBar().value() == 0
    assert window.properties_panel.body.sizeHint().height() != tall


def test_rebuilding_properties_leaves_no_floating_windows(window):
    """A visible widget given no parent becomes a top-level window."""
    from PySide6.QtWidgets import QApplication, QGroupBox

    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 200)
    window.select_tool("select")
    item = markups(window)[0]
    for _ in range(3):
        window.view.scene().clearSelection()
        window.refresh_selection()
        item.setSelected(True)
        window.refresh_selection()
    # Discarded group boxes sit parentless until deleteLater() runs; that is
    # harmless as long as none of them is *shown*, because a visible parentless
    # widget is a floating window on the user's desktop.
    floating = [w.title() for w in QApplication.topLevelWidgets()
                if isinstance(w, QGroupBox) and w.isVisible()]
    assert floating == []
