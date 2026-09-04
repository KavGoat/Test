"""End-to-end exercises against a real main window (offscreen)."""
import os

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication

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

# The cut-out tools take a bite out of an area that is already there rather
# than drawing anything of their own, so they are tested on their own terms in
# test_usability.py, not by "does dragging make a new markup".
NOT_NEW_MARKUPS = ("image", "calibrate", "cutout_ellipse", "cutout_polygon")
DRAG_TOOLS = [t.key for t in TOOLS if t.mode == DRAG and t.key not in NOT_NEW_MARKUPS]
POLY_TOOLS = [t.key for t in TOOLS if t.mode == POLY and t.key not in NOT_NEW_MARKUPS]
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
    block.local_scope = False        # publish to the document rather than keep local
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


def test_evaluation_is_strictly_top_to_bottom(window):
    """A value must be defined above whatever uses it — order is position."""
    window.select_tool("math")
    drag(window.view, 60, 400, 320, 470)
    lower = editing_item(window)
    lower._editor.setPlainText("total := base * 2")
    window.view.end_item_edit()

    window.select_tool("math")
    drag(window.view, 60, 80, 320, 150)
    editing_item(window)._editor.setPlainText("base := 5 kN")
    window.view.end_item_edit()

    assert window.document.workspace.get("total").to("kN").magnitude == pytest.approx(10)

    # Push the definition below its use and the reference stops resolving.
    lower.setPos(QPointF(lower.pos().x(), 40))
    window.recalculate()
    assert window.document.workspace.get("total") is None


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
    block = editing_item(window)
    block._editor.setPlainText("a := 3 m\nb := a*2")
    block.local_scope = False        # publish, so the reload can be checked by value
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
    # the footing block is self-contained, so its values are not document-wide
    assert workspace.get("q") is None
    footing = [i for i in window.document.pages[2].frame.markups()
               if isinstance(i, MathItem) and i.label == "Pad footing"][0]
    assert footing.local_values["q"].value.to("kPa").magnitude == pytest.approx(149.8,
                                                                               rel=1e-3)


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
    editing_item(window).set_text("a note")
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
    window.current_page().frame.refresh_items()
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
    window.view.frame().add_markup(measure, QPointF(120, 500))
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


def test_new_calculations_are_one_movable_line(window):
    window.select_tool("math")
    drag(window.view, 80, 80, 380, 180)
    block = editing_item(window)
    block._editor.setPlainText("b = 300 mm")
    window.view.end_item_edit()
    assert block.single_line
    # sized around its content, not around the rectangle that was dragged
    assert block.local_rect().height() < 40


def test_enter_opens_the_next_calculation_below(window):
    window.select_tool("math")
    drag(window.view, 80, 80, 200, 100)
    first = editing_item(window)
    first._editor.setPlainText("b = 300 mm")
    window.view._open_next_line()
    second = editing_item(window)
    assert isinstance(second, MathItem) and second is not first
    assert second.pos().y() > first.pos().y()
    second._editor.setPlainText("d = 2*b")
    window.view.end_item_edit()
    assert window.document.workspace.get("d").to("mm").magnitude == pytest.approx(600)


def test_empty_regions_are_discarded(window):
    window.select_tool("math")
    drag(window.view, 80, 80, 200, 100)
    window.view.end_item_edit()
    assert markups(window) == []


def test_evaluation_follows_position_not_creation_order(window):
    """Move a definition below its use and the reference should break."""
    window.select_tool("math")
    drag(window.view, 80, 100, 200, 120)
    upper = editing_item(window)
    upper._editor.setPlainText("base = 5 kN")
    window.view.end_item_edit()

    window.select_tool("math")
    drag(window.view, 80, 300, 200, 320)
    lower = editing_item(window)
    lower._editor.setPlainText("total = base*2")
    window.view.end_item_edit()
    assert window.document.workspace.get("total").to("kN").magnitude == pytest.approx(10)

    upper.setPos(QPointF(upper.pos().x(), 500))
    window.recalculate()
    assert window.document.workspace.get("total") is None
    assert any("not defined" in s.error for s in lower.statements if s.error)


def test_items_on_the_same_row_read_left_to_right(window):
    from calcforge.ui.scene import reading_order
    window.select_tool("math")
    drag(window.view, 300, 200, 380, 220)
    right = editing_item(window)
    right._editor.setPlainText("y = x*2")
    window.view.end_item_edit()

    window.select_tool("math")
    drag(window.view, 80, 202, 160, 222)
    left = editing_item(window)
    left._editor.setPlainText("x = 4 m")
    window.view.end_item_edit()

    assert reading_order([right, left]) == [left, right]
    assert window.document.workspace.get("y").to("m").magnitude == pytest.approx(8)


def test_split_and_merge_calculations(window):
    window.select_tool("math")
    drag(window.view, 80, 80, 300, 200)
    block = editing_item(window)
    block._editor.setPlainText("a = 2 m\nb = 3 m\nc = a*b")
    window.view.end_item_edit()
    block.setSelected(True)
    window.split_calculation()

    pieces = [i for i in markups(window) if isinstance(i, MathItem)]
    assert len(pieces) == 3
    assert window.document.workspace.get("c").to("m**2").magnitude == pytest.approx(6)

    window.view.scene().clearSelection()
    for piece in pieces:
        piece.setSelected(True)
    window.merge_calculations()
    merged = [i for i in markups(window) if isinstance(i, MathItem)]
    assert len(merged) == 1
    assert merged[0].source.split("\n") == ["a = 2 m", "b = 3 m", "c = a*b"]


def test_problems_panel_reports_undefined_names_and_unit_mismatches(window):
    from calcforge.core.problems import UNDEFINED, UNIT_MISMATCH

    window.select_tool("math")
    drag(window.view, 80, 100, 300, 120)
    editing_item(window)._editor.setPlainText("bad = nonexistent*2")
    window.view.end_item_edit()

    window.select_tool("math")
    drag(window.view, 80, 200, 300, 220)
    editing_item(window)._editor.setPlainText("clash = 1 m + 1 kg")
    window.view.end_item_edit()

    kinds = {p.kind for p in window.problems_panel._problems}
    assert kinds == {UNDEFINED, UNIT_MISMATCH}
    assert "2 problem" in window.status_problems.text()
    assert window.problems_panel.table.rowCount() == 2


def test_problems_panel_reports_bad_cells_by_reference(window):
    window.select_tool("table")
    drag(window.view, 80, 80, 400, 240)
    table = window.view.active_table
    table.set_cell(2, 1, "=missing_name*2")
    window.recalculate()
    problems = window.problems_panel._problems
    assert [p.where for p in problems] == ["cell B3"]


def test_problems_clear_once_the_document_evaluates(window):
    window.select_tool("math")
    drag(window.view, 80, 100, 300, 120)
    block = editing_item(window)
    block._editor.setPlainText("bad = nonexistent*2")
    window.view.end_item_edit()
    assert window.problems_panel._problems

    window.view.begin_item_edit(block)
    block._editor.setPlainText("good = 2 m")
    window.view.end_item_edit()
    assert window.problems_panel._problems == []
    assert window.status_problems.text() == "No problems"


def test_moving_a_definition_below_its_use_raises_a_problem(window):
    window.select_tool("math")
    drag(window.view, 80, 100, 300, 120)
    definition = editing_item(window)
    definition._editor.setPlainText("base = 5 kN")
    window.view.end_item_edit()

    window.select_tool("math")
    drag(window.view, 80, 300, 300, 320)
    editing_item(window)._editor.setPlainText("total = base*2")
    window.view.end_item_edit()
    assert window.problems_panel._problems == []

    definition.setPos(QPointF(definition.pos().x(), 600))
    window.recalculate()
    assert [p.kind for p in window.problems_panel._problems] == ["undefined"]


def _type_on_canvas(window, text, x=140.0, y=180.0):
    from PySide6.QtCore import QPointF as _P
    window.select_tool("select")
    window.view.scene().clearSelection()
    window.view._last_scene_pos = _P(x, y)
    key(window.view, Qt.Key_unknown, text)


def test_quote_starts_writing_where_the_cursor_is(window):
    """Both keys open the same thing: a line that is maths until it is prose.

    The quotation mark is what somebody expecting to write words reaches for
    and the slash is what somebody expecting to write maths reaches for.
    Having them open different things was only ever a way to pick wrong: what
    is typed decides, not which key started it.
    """
    _type_on_canvas(window, '"')
    item = editing_item(window)
    assert isinstance(item, MathItem)
    assert item.pos().x() == pytest.approx(140, abs=1)
    assert item.started_by_typing, "it can still turn out to be a sentence"
    item._editor.setPlainText("a note here")
    window.view.end_item_edit()
    assert len(markups(window)) == 1
    assert isinstance(markups(window)[0], TextItem), "and it did"


def test_slash_starts_a_calculation(window):
    """And it stays a calculation, because there is not a space in it.

    A calculation never contains a space — a unit goes straight after its
    number — so ``q=5kPa`` is what somebody types, and what used to be written
    here as ``q = 5 kPa`` is now a sentence and turns into one.
    """
    _type_on_canvas(window, "/")
    item = editing_item(window)
    assert isinstance(item, MathItem)
    item._editor.setPlainText("q=5kPa")
    window.view.end_item_edit()
    assert window.document.workspace.get("q").to("kPa").magnitude == pytest.approx(5)


def test_pipe_starts_a_table_and_at_starts_a_callout(window):
    _type_on_canvas(window, "|")
    assert isinstance(window.view.active_table, TableItem)
    window.view.deactivate_table()
    _type_on_canvas(window, "@", 320, 400)
    from calcforge.items.text import CalloutItem
    assert isinstance(editing_item(window), CalloutItem)


def test_an_unbound_key_starts_nothing_at_all(window):
    """Writing begins deliberately, so every other letter stays free.

    A bare letter used to open a calculation and put itself in it, which meant
    every letter on the keyboard was spoken for: a tool key not yet bound, or
    a keystroke meant for something that had just lost the focus, started a
    calculation instead of doing nothing.
    """
    _type_on_canvas(window, "5")
    assert window.view.editing_item() is None
    assert not markups(window)


def test_the_maths_key_starts_a_calculation(window):
    """"/" is what opens one, and it is on the shortcut list to be changed."""
    from calcforge.items.mathitem import MathItem

    _type_on_canvas(window, "/")
    item = window.view.editing_item()
    assert isinstance(item, MathItem)
    item._editor.setPlainText("5")
    window.view.end_item_edit()
    assert editing_item(window) is None


def test_bound_tool_letter_selects_its_tool(window):
    _type_on_canvas(window, "r")
    assert window.view.tool_key == "rect"
    window.select_tool("select")
    _type_on_canvas(window, "h")
    assert window.view.tool_key == "highlighter"


def test_typing_is_ignored_while_editing_or_in_a_table(window):
    window.select_tool("math")
    drag(window.view, 80, 80, 200, 100)
    block = editing_item(window)
    assert not window.view.idle_on_canvas()
    block._editor.setPlainText("a = 1 m")
    window.view.end_item_edit()

    window.select_tool("table")
    drag(window.view, 80, 300, 400, 420)
    assert not window.view.idle_on_canvas()


def test_shortcuts_can_be_rebound_and_reset(window):
    manager = window.shortcuts
    assert manager.sequence("insert.math") == "/"
    manager.set_sequence("insert.math", "!")
    window.apply_shortcuts()
    _type_on_canvas(window, "!")
    assert isinstance(editing_item(window), MathItem)
    window.view.end_item_edit()
    manager.reset("insert.math")
    assert manager.sequence("insert.math") == "/"


def test_shortcut_conflicts_are_detectable(window):
    manager = window.shortcuts
    assert manager.conflicts() == {}
    manager.set_sequence("tool.rect", "/")
    assert "/" in manager.conflicts()
    manager.reset()


def test_renumber_counts_closes_gaps(window):
    window.view.count_subject = "Doors"
    for x in (100, 200, 300):
        window.select_tool("count")
        press(window.view, x, 400)
        release(window.view, x, 400)
    window.select_tool("select")
    from calcforge.items.measure import CountItem
    counts = sorted([i for i in markups(window) if isinstance(i, CountItem)],
                    key=lambda i: i.pos().x())
    assert [c.index for c in counts] == [1, 2, 3]
    window.view.scene().clearSelection()
    counts[1].setSelected(True)
    window.delete_selection()
    window.renumber_counts()
    remaining = sorted([i for i in markups(window) if isinstance(i, CountItem)],
                       key=lambda i: i.pos().x())
    assert [c.index for c in remaining] == [1, 2]


def _make_table(window, x=80, y=80):
    window.select_tool("table")
    drag(window.view, x, y, x + 340, y + 160)
    return window.view.active_table


def test_copy_and_paste_a_cell_range(window):
    table = _make_table(window)
    table.sheet.resize(6, 4)
    for row, values in enumerate([["1", "2"], ["3", "4"]]):
        for col, value in enumerate(values):
            table.set_cell(row, col, value)
    table.set_cell(0, 2, "=A1+B1")
    table.set_cell(1, 2, "=A2+B2")
    window.recalculate()

    table.current, table.anchor = (0, 0), (1, 2)
    window.copy_selection()
    table.current = table.anchor = (3, 0)
    window.paste_items()

    assert table.sheet.raw(3, 0) == "1"
    assert table.sheet.raw(3, 2) == "=A4+B4"        # relative refs follow the paste
    assert table.sheet.value(4, 2) == 7


def test_cut_clears_the_source_cells(window):
    table = _make_table(window)
    table.set_cell(0, 0, "9")
    window.recalculate()
    table.current = table.anchor = (0, 0)
    window.cut_selection()
    assert table.sheet.raw(0, 0) == ""
    table.current = table.anchor = (2, 1)
    window.paste_items()
    assert table.sheet.raw(2, 1) == "9"


def test_paste_tab_separated_text_from_a_spreadsheet(window):
    from PySide6.QtWidgets import QApplication
    table = _make_table(window)
    QApplication.clipboard().setText("Item\tLoad\nSlab\t3.6 kPa\nScreed\t1.3 kPa")
    table.current = table.anchor = (0, 0)
    window.paste_items()
    window.recalculate()
    assert table.sheet.raw(0, 0) == "Item"
    assert table.sheet.value(1, 1).to("kPa").magnitude == pytest.approx(3.6)


def test_copied_cells_reach_the_system_clipboard_as_tsv(window):
    from PySide6.QtWidgets import QApplication
    table = _make_table(window)
    table.set_cell(0, 0, "a")
    table.set_cell(0, 1, "b")
    table.current, table.anchor = (0, 0), (0, 1)
    window.copy_selection()
    assert QApplication.clipboard().text() == "a\tb"


def test_paste_grows_the_table_when_needed(window):
    from PySide6.QtWidgets import QApplication
    table = _make_table(window)
    table.sheet.resize(2, 2)
    QApplication.clipboard().setText("1\t2\t3\n4\t5\t6\n7\t8\t9")
    table.current = table.anchor = (0, 0)
    window.paste_items()
    assert table.sheet.rows >= 3 and table.sheet.cols >= 3
    assert table.sheet.raw(2, 2) == "9"


def test_plot_draws_a_defined_function(window):
    from calcforge.items.plotitem import PlotItem, Series
    window.select_tool("math")
    drag(window.view, 60, 60, 300, 90)
    editing_item(window)._editor.setPlainText("L = 6 m")
    window.view.end_item_edit()
    window.select_tool("math")
    drag(window.view, 60, 120, 300, 150)
    editing_item(window)._editor.setPlainText("M(x) = 12 kN/m*x*(L-x)/2")
    window.view.end_item_edit()

    window.select_tool("plot")
    drag(window.view, 60, 300, 400, 520)
    plot = [i for i in markups(window) if isinstance(i, PlotItem)][0]
    plot.series = [Series("M")]
    plot.variable = "x"
    plot.x_from = "0 m"
    plot.x_to = "L"
    window.recalculate()
    assert len(plot.series[0].xs) > 50
    assert plot._y_display == "kN·m"
    assert max(plot.series[0].ys) == pytest.approx(54, rel=1e-2)


def test_plot_reports_a_curve_that_does_not_share_the_y_axis(window):
    from calcforge.items.plotitem import PlotItem, Series
    window.select_tool("math")
    drag(window.view, 60, 60, 300, 90)
    editing_item(window)._editor.setPlainText("f(x) = x*1 kN")
    window.view.end_item_edit()
    window.select_tool("math")
    drag(window.view, 60, 120, 300, 150)
    editing_item(window)._editor.setPlainText("g(x) = x*1 m")
    window.view.end_item_edit()

    window.select_tool("plot")
    drag(window.view, 60, 300, 400, 520)
    plot = [i for i in markups(window) if isinstance(i, PlotItem)][0]
    plot.series = [Series("f"), Series("g")]
    plot.x_from, plot.x_to = "0", "5"
    window.recalculate()
    assert plot.series[0].xs and not plot.series[1].xs
    assert "y axis" in plot.series[1].error


def test_hiding_a_layer_hides_and_deselects_its_markups(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 200)
    window.select_tool("select")
    item = markups(window)[0]
    item.setSelected(True)
    assert item.isVisible()

    window.document.layer("Markups").visible = False
    window.apply_layers()
    assert not item.isVisible()
    assert not item.isSelected()
    assert window.view.markup_at(QPointF(150, 150)) is None

    window.document.layer("Markups").visible = True
    window.apply_layers()
    assert item.isVisible()


def test_locking_a_layer_stops_its_markups_moving(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 200)
    window.select_tool("select")
    item = markups(window)[0]
    window.document.layer("Markups").locked = True
    window.apply_layers()
    origin = item.pos()
    press(window.view, 150, 150)
    move(window.view, 260, 260)
    release(window.view, 260, 260)
    assert item.pos() == origin


def test_non_printing_layers_are_left_out_of_output(window, tmp_path):
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 200)
    window.select_tool("select")
    scene = window.current_page().frame
    with_layer = scene.render_image(dpi=60, for_print=True)
    window.document.layer("Markups").printable = False
    without_layer = scene.render_image(dpi=60, for_print=True)
    assert with_layer != without_layer


def test_layers_panel_moves_the_selection(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 200)
    window.select_tool("select")
    item = markups(window)[0]
    item.setSelected(True)
    window.move_selection_to_layer("Calculations")
    assert item.layer == "Calculations"
    assert window.layers_panel.table.rowCount() == len(window.document.layers)


def test_renaming_a_layer_carries_its_markups(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 200)
    item = markups(window)[0]
    window.rename_layer("Markups", "Review")
    window.document.layers[0].name = "Review"
    assert item.layer == "Review"
    assert window.layer_visible("Review")


def test_applying_redactions_destroys_what_is_underneath(window, monkeypatch, tmp_path):
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QMessageBox
    from calcforge.items.shapes import RectItem

    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Yes)

    # a page background to redact, and two markups: one covered, one outside
    page = window.current_page()
    image = QImage(300, 425, QImage.Format_ARGB32)
    image.fill(0xFFFF0000)
    from PySide6.QtCore import QBuffer, QIODevice
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    page.background_key = window.document.add_asset(bytes(buffer.data()), "png")
    original_key = page.background_key
    page.frame.load_background()

    window.select_tool("text")
    drag(window.view, 120, 120, 200, 150)
    editing_item(window).set_text("secret")
    window.view.end_item_edit()

    window.select_tool("text")
    drag(window.view, 420, 500, 500, 530)
    editing_item(window).set_text("kept")
    window.view.end_item_edit()

    window.select_tool("redact")
    drag(window.view, 100, 100, 320, 260)
    window.select_tool("select")

    window.apply_redactions()

    assert page.background_key != original_key          # pixels rewritten
    remaining = [i for i in markups(window) if isinstance(i, TextItem)]
    assert [i.text() for i in remaining] == ["kept"]
    redaction = [i for i in markups(window) if isinstance(i, RectItem)][0]
    assert redaction.locked and redaction.style.fill_opacity == 1.0

    burnt = QImage()
    burnt.loadFromData(window.document.asset(page.background_key))
    scale = burnt.width() / page.width_pt
    assert burnt.pixelColor(int(200 * scale), int(180 * scale)).name() == "#000000"
    assert burnt.pixelColor(int(500 * scale), int(600 * scale)).name() == "#ff0000"


def test_applying_redactions_with_none_present_explains_itself(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    seen = {}
    monkeypatch.setattr(QMessageBox, "information",
                        lambda parent, title, text, *a, **k: seen.update(text=text))
    window.apply_redactions()
    assert "no redaction boxes" in seen["text"]


def test_autosave_writes_and_clears_a_recovery_copy(window, tmp_path):
    import os
    path = str(tmp_path / "doc.cfx")
    from calcforge.io import project as project_io
    project_io.save_document(window.document, path)
    window.document.path = path

    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 200)
    written = window.write_autosave()
    assert written == path + ".autosave"
    assert os.path.exists(written)
    assert window.document.path == path        # autosaving is not a save-as

    recovered = type(window.document)()
    project_io.load_document(recovered, written)
    assert len(recovered.pages[0]._pending_items) == 1

    window.save_document()
    assert not os.path.exists(written)


def test_autosave_does_nothing_when_there_is_nothing_to_save(window):
    window.document.modified = False
    window.undo_stack.setClean()
    assert window.write_autosave() is None


def test_dark_theme_switches_the_chrome_but_not_the_paper(window):
    from PySide6.QtWidgets import QApplication
    from calcforge.theme import CANVAS, DARK, LIGHT, tokens

    window.toggle_theme(True)
    assert tokens(DARK)["chrome"] in QApplication.instance().styleSheet()
    assert window.view.scene().backgroundBrush().color().name() == CANVAS[DARK]
    # the page itself stays paper-white
    image = window.current_page().frame.render_image(dpi=40, for_print=False)
    assert image.pixelColor(image.width() // 2, image.height() // 2).name() == "#ffffff"
    window.toggle_theme(False)
    assert tokens(LIGHT)["chrome"] in QApplication.instance().styleSheet()


def test_two_axis_index_addresses_a_rectangular_range(window):
    table = _make_table(window)
    table.sheet.resize(5, 4)
    for row, values in enumerate([["1", "2", "3"], ["4", "5", "6"]]):
        for col, value in enumerate(values):
            table.set_cell(row, col, value)
    table.set_cell(3, 0, "=INDEX(A1:C2,2,3)")
    window.recalculate()
    assert table.sheet.value(3, 0) == 6


def test_typing_still_works_with_something_selected(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 200)
    window.select_tool("select")
    markups(window)[0].setSelected(True)
    window.view._last_scene_pos = QPointF(300, 400)
    key(window.view, Qt.Key_unknown, "/")
    assert isinstance(editing_item(window), MathItem)


def test_successive_calculation_lines_do_not_overlap(window):
    """Enter must leave room for whatever was actually typed above."""
    window.select_tool("math")
    drag(window.view, 80, 80, 220, 100)
    sources = ["L = 7.2 m", "w = 12 kN/m", "M = w*L^2/8", "Z = 896 cm^3",
               "sigma = M/Z", "delta = 5*w*L^4/(384*205 GPa*14100 cm^4)"]
    editing_item(window)._editor.setPlainText(sources[0])
    for text in sources[1:]:
        window.view._open_next_line()
        editing_item(window)._editor.setPlainText(text)
    window.view.end_item_edit()

    blocks = [i for i in markups(window) if isinstance(i, MathItem)]
    assert len(blocks) == len(sources)
    blocks.sort(key=lambda i: i.pos().y())
    for upper, lower in zip(blocks, blocks[1:]):
        bottom = upper.pos().y() + upper.local_rect().height()
        assert lower.pos().y() >= bottom - 0.01, f"{upper.source!r} overlaps {lower.source!r}"


def test_using_a_stress_before_it_is_defined_warns_rather_than_inventing_a_unit(window):
    window.select_tool("math")
    drag(window.view, 80, 300, 300, 320)
    editing_item(window)._editor.setPlainText("util = sigma/(355 MPa)")
    window.view.end_item_edit()

    window.select_tool("math")
    drag(window.view, 80, 500, 300, 520)
    editing_item(window)._editor.setPlainText("sigma = 138 MPa")
    window.view.end_item_edit()

    assert [p.kind for p in window.problems_panel._problems] == ["undefined"]
    assert "'sigma' is not defined" in window.problems_panel._problems[0].message

    # move the definition above its use and it resolves
    definition = [i for i in markups(window) if isinstance(i, MathItem)
                  and i.source.strip().startswith("sigma")][0]
    definition.setPos(QPointF(80, 100))
    window.recalculate()
    assert window.problems_panel._problems == []
    assert window.document.workspace.get("util") == pytest.approx(0.3887, rel=1e-3)


def real_double_click(view, x, y):
    """The sequence Qt actually sends: press, release, double-click, release."""
    from PySide6.QtWidgets import QApplication
    for kind in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease,
                 QEvent.MouseButtonDblClick, QEvent.MouseButtonRelease):
        QApplication.sendEvent(view.viewport(), _event(view, kind, x, y))


def test_double_click_starts_editing_a_calculation(window):
    window.select_tool("math")
    drag(window.view, 100, 100, 260, 125)
    block = editing_item(window)
    block._editor.setPlainText("b = 300 mm")
    window.view.end_item_edit()
    window.select_tool("select")

    centre = block.mapToScene(block.local_rect().center())
    real_double_click(window.view, centre.x(), centre.y())
    assert editing_item(window) is block


def test_arrows_move_the_caret_while_editing_not_the_markup(window):
    window.select_tool("math")
    drag(window.view, 100, 100, 260, 125)
    block = editing_item(window)
    block._editor.setPlainText("b = 300 mm")
    window.view.end_item_edit()
    window.select_tool("select")
    centre = block.mapToScene(block.local_rect().center())
    real_double_click(window.view, centre.x(), centre.y())

    origin = block.pos()
    caret = block._editor.textCursor().position()
    key(window.view, Qt.Key_Left)
    assert block.pos() == origin
    assert block._editor.textCursor().position() == caret - 1


def test_typing_while_editing_reaches_the_text(window):
    from PySide6.QtWidgets import QApplication
    window.select_tool("math")
    drag(window.view, 100, 100, 260, 125)
    block = editing_item(window)
    from PySide6.QtGui import QTextCursor
    block._editor.setPlainText("b = 300")
    cursor = block._editor.textCursor()
    cursor.movePosition(QTextCursor.End)
    block._editor.setTextCursor(cursor)
    QApplication.sendEvent(window.view, QKeyEvent(QEvent.KeyPress, Qt.Key_X,
                                                  Qt.NoModifier, " mm"))
    assert block._editor.toPlainText() == "b = 300 mm"


def test_delete_while_editing_does_not_remove_the_markup(window):
    window.select_tool("math")
    drag(window.view, 100, 100, 260, 125)
    block = editing_item(window)
    block._editor.setPlainText("b = 300 mm")
    window.delete_selection()
    assert block in markups(window)


def test_clicking_outside_finishes_the_edit(window):
    window.select_tool("math")
    drag(window.view, 100, 100, 260, 125)
    editing_item(window)._editor.setPlainText("b = 300 mm")
    press(window.view, 500, 600)
    release(window.view, 500, 600)
    assert editing_item(window) is None
    assert window.document.workspace.get("b").to("mm").magnitude == pytest.approx(300)


def test_double_click_on_a_cell_opens_its_editor(window):
    window.select_tool("table")
    drag(window.view, 100, 300, 420, 430)
    table = window.view.active_table
    window.view.deactivate_table()
    window.select_tool("select")

    point = table.mapToScene(table.cell_rect(1, 1).center())
    real_double_click(window.view, point.x(), point.y())
    assert window.view.active_table is table
    assert window.view._cell_editor is not None
    assert table.current == (1, 1)


def test_arrows_move_the_cell_cursor_not_the_table(window):
    window.select_tool("table")
    drag(window.view, 100, 300, 420, 430)
    table = window.view.active_table
    origin = table.pos()
    key(window.view, Qt.Key_Down)
    key(window.view, Qt.Key_Right)
    assert table.pos() == origin
    assert table.current == (1, 1)


def test_activating_a_table_leaves_its_cells_where_they_were(window):
    window.select_tool("table")
    drag(window.view, 100, 300, 420, 430)
    table = window.view.active_table
    before = table.mapToScene(table.cell_rect(1, 1).center())
    window.view.deactivate_table()
    after_hidden = table.mapToScene(table.cell_rect(1, 1).center())
    window.view.activate_table(table)
    after_shown = table.mapToScene(table.cell_rect(1, 1).center())
    assert (before - after_hidden).manhattanLength() < 0.01
    assert (before - after_shown).manhattanLength() < 0.01


def test_a_table_saved_while_active_reopens_in_place(window):
    window.select_tool("table")
    drag(window.view, 100, 300, 420, 430)
    table = window.view.active_table
    window.view.deactivate_table()
    resting = table.pos()
    window.view.activate_table(table)
    data = table.serialize()
    assert data["x"] == pytest.approx(resting.x())
    assert data["y"] == pytest.approx(resting.y())


def test_a_block_defines_for_the_document_unless_told_otherwise(window):
    window.select_tool("math")
    drag(window.view, 80, 100, 300, 180)
    block = editing_item(window)
    block._editor.setPlainText("b_trib = 3 m\nw = 5 kPa*b_trib")
    window.view.end_item_edit()

    assert not block.local_scope
    workspace = window.document.workspace
    assert workspace.get("b_trib").to("m").magnitude == pytest.approx(3)
    assert workspace.get("w").to("kN/m").magnitude == pytest.approx(15)


def test_the_properties_panel_toggles_a_blocks_scope(window):
    from PySide6.QtWidgets import QCheckBox

    window.select_tool("mathblock")
    drag(window.view, 80, 100, 300, 180)
    block = editing_item(window)
    block._editor.setPlainText("x = 2 m\ny = x*3")
    window.view.end_item_edit()
    window.select_tool("select")
    block.setSelected(True)

    window.properties_panel.show_items([block])
    scope = [box for box in window.properties_panel.findChildren(QCheckBox)
             if box.text() == "Self-contained"][0]
    assert not scope.isChecked()  # a block starts open

    assert not block.local_scope
    assert window.document.workspace.get("y").to("m").magnitude == pytest.approx(6)

    scope.setChecked(True)
    assert block.local_scope
    assert window.document.workspace.get("y") is None


def test_a_block_keeps_its_values_to_itself(window):
    window.select_tool("math")
    drag(window.view, 80, 80, 300, 110)
    editing_item(window)._editor.setPlainText("q_floor = 5 kPa")
    window.view.end_item_edit()

    window.select_tool("mathblock")
    drag(window.view, 80, 200, 300, 300)
    block = editing_item(window)
    block._editor.setPlainText("b_trib = 3 m\nw = q_floor*b_trib\nR = w*6 m/2")
    window.view.end_item_edit()
    window.set_block_scope(True)                 # keep its names to itself
    block.setSelected(True)

    workspace = window.document.workspace
    assert workspace.get("q_floor").to("kPa").magnitude == pytest.approx(5)
    assert workspace.get("R") is None and workspace.get("b_trib") is None
    assert block.scoped
    assert block.local_values["R"].value.to("kN").magnitude == pytest.approx(45)


def test_a_block_can_read_globals_defined_above_it(window):
    window.select_tool("math")
    drag(window.view, 80, 80, 300, 110)
    editing_item(window)._editor.setPlainText("L = 6 m")
    window.view.end_item_edit()

    window.select_tool("mathblock")
    drag(window.view, 80, 200, 300, 280)
    block = editing_item(window)
    block._editor.setPlainText("w = 12 kN/m\nM = w*L^2/8")
    window.view.end_item_edit()
    block.setSelected(True)
    window.set_block_scope(True)

    assert [s.error for s in block.statements if s.error] == []
    assert block.local_values["M"].value.to("kN*m").magnitude == pytest.approx(54)


def test_a_later_line_cannot_see_inside_a_block(window):
    window.select_tool("mathblock")
    drag(window.view, 80, 100, 300, 180)
    first = editing_item(window)
    first._editor.setPlainText("a = 2 m\nb = 3 m")
    window.view.end_item_edit()
    first.setSelected(True)
    window.set_block_scope(True)

    window.select_tool("math")
    drag(window.view, 80, 400, 300, 430)
    after = editing_item(window)
    after._editor.setPlainText("c = a*2")
    window.view.end_item_edit()

    assert any("not defined" in s.error for s in after.statements if s.error)
    assert [p.kind for p in window.problems_panel._problems] == ["undefined"]


def test_a_single_line_region_always_defines_globally(window):
    window.select_tool("math")
    drag(window.view, 80, 80, 300, 110)
    line = editing_item(window)
    line._editor.setPlainText("b = 300 mm")
    window.view.end_item_edit()
    assert not line.scoped
    assert window.document.workspace.get("b").to("mm").magnitude == pytest.approx(300)


def test_a_block_can_be_opened_up_to_the_document(window):
    window.select_tool("mathblock")
    drag(window.view, 80, 100, 300, 180)
    block = editing_item(window)
    block._editor.setPlainText("x = 2 m\ny = x*3")
    window.view.end_item_edit()
    block.setSelected(True)
    window.set_block_scope(True)
    assert window.document.workspace.get("y") is None

    window.set_block_scope(False)
    assert window.document.workspace.get("y").to("m").magnitude == pytest.approx(6)


def test_block_locals_are_listed_for_reference(window):
    window.select_tool("mathblock")
    drag(window.view, 80, 100, 300, 180)
    block = editing_item(window)
    block._editor.setPlainText("x = 2 m\ny = x*3")
    window.view.end_item_edit()
    block.setSelected(True)
    window.set_block_scope(True)
    rows = [window.variables_panel.table.item(r, 0).text()
            for r in range(window.variables_panel.table.rowCount())]
    sources = [window.variables_panel.table.item(r, 2).text()
               for r in range(window.variables_panel.table.rowCount())]
    assert "y" in rows
    assert any("local" in source for source in sources)


def test_editing_a_calculation_starts_at_the_end_of_the_line(window):
    window.select_tool("math")
    drag(window.view, 100, 100, 260, 125)
    block = editing_item(window)
    block._editor.setPlainText("L = 6 m")
    window.view.end_item_edit()
    window.select_tool("select")

    centre = block.mapToScene(block.local_rect().center())
    real_double_click(window.view, centre.x(), centre.y())
    assert block._editor.textCursor().position() == len("L = 6 m")

    for _ in range(3):
        key(window.view, Qt.Key_Left)
    key(window.view, Qt.Key_unknown, "7")
    window.view.end_item_edit()
    assert window.document.workspace.get("L").to("m").magnitude == pytest.approx(76)


def test_editing_a_text_box_puts_the_caret_near_the_click(window):
    window.select_tool("text")
    drag(window.view, 100, 100, 320, 140)
    box = editing_item(window)
    box.set_text("the quick brown fox")
    window.view.end_item_edit()
    window.select_tool("select")

    rect = box.local_rect()
    point = box.mapToScene(QPointF(rect.left() + rect.width() * 0.45, rect.top() + 8))
    real_double_click(window.view, point.x(), point.y())
    assert editing_item(window) is box
    assert 0 < box._editor.textCursor().position() < len("the quick brown fox")


# ---------------------------------------------------------------------------
# published table cells
# ---------------------------------------------------------------------------

def _table_with_a_named_cell(window, name="q_floor"):
    window.select_tool("table")
    drag(window.view, 80, 80, 420, 240)
    table = window.view.active_table
    table.set_cell(0, 0, "Load")
    table.set_cell(0, 1, "Value")
    table.set_cell(1, 0, "Floor")
    table.set_cell(1, 1, "5 kPa")
    table.current = (1, 1)
    window.refresh_formula_bar(table)
    window.cell_name.setText(name)
    window.commit_cell_name()
    return table


def test_naming_a_cell_from_the_formula_bar_publishes_it(window):
    table = _table_with_a_named_cell(window)
    assert table.named_cells == {"q_floor": "B2"}
    assert table.name_for(1, 1) == "q_floor"
    value = window.document.workspace.get("q_floor")
    assert value.to("kPa").magnitude == pytest.approx(5)


def test_the_name_box_shows_what_the_current_cell_publishes(window):
    table = _table_with_a_named_cell(window)
    table.current = (0, 0)
    window.refresh_formula_bar(table)
    assert window.cell_name.text() == ""
    table.current = (1, 1)
    window.refresh_formula_bar(table)
    assert window.cell_name.text() == "q_floor"


def test_a_published_cell_is_tagged_on_the_sheet(window):
    table = _table_with_a_named_cell(window)
    window.view.deactivate_table()            # how the sheet is normally read
    assert table.show_names
    from PySide6.QtGui import QColor, QImage, QPainter
    image = QImage(400, 240, QImage.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    table.paint_content(painter)          # must not raise, and must draw the tag
    painter.end()
    tag = QColor("#2f7d4f").rgb()
    assert any(image.pixel(x, y) == tag
               for x in range(400) for y in range(240)), "no name tag was drawn"


def test_the_variables_panel_says_which_cell_a_value_came_from(window):
    _table_with_a_named_cell(window)
    window.recalculate()
    panel = window.variables_panel
    rows = {panel.table.item(r, 0).text(): panel.table.item(r, 2).text()
            for r in range(panel.table.rowCount())}
    assert "q_floor" in rows
    assert "B2" in rows["q_floor"]


def test_a_bad_cell_name_is_refused_and_the_box_reverts(window, monkeypatch):
    from calcforge.ui import mainwindow as mw
    table = _table_with_a_named_cell(window)
    warned = []
    monkeypatch.setattr(mw.QMessageBox, "warning",
                        lambda *args, **kwargs: warned.append(args[-1]))
    window.cell_name.setText("m")          # a unit
    window.commit_cell_name()
    assert warned and "unit" in warned[0]
    assert window.cell_name.text() == "q_floor"
    assert table.named_cells == {"q_floor": "B2"}


def test_clearing_the_name_box_stops_publishing(window):
    table = _table_with_a_named_cell(window)
    window.cell_name.setText("")
    window.commit_cell_name()
    assert table.named_cells == {}
    assert window.document.workspace.get("q_floor") is None


def test_a_named_cell_survives_a_save_and_reload(window, tmp_path):
    _table_with_a_named_cell(window)
    window.view.deactivate_table()
    path = str(tmp_path / "named.cfx")
    from calcforge.io import project as project_io
    from calcforge.core.document import Document
    project_io.save_document(window.document, path)
    reopened = Document()
    project_io.load_document(reopened, path)
    window.document = reopened
    window.rebuild_scenes()
    table = [i for i in window.view.scene().ordered_markups()
             if isinstance(i, TableItem)][0]
    assert table.named_cells == {"q_floor": "B2"}
    assert table.show_names
    assert window.document.workspace.get("q_floor").to("kPa").magnitude == pytest.approx(5)


def test_pasting_excel_cells_onto_the_page_makes_a_table(window):
    clipboard = QApplication.clipboard()
    clipboard.setText("Item\tThickness\tDensity\n"
                      "Slab\t150 mm\t24 kN/m^3\n"
                      "Screed\t60 mm\t22 kN/m^3")
    window.view._last_scene_pos = QPointF(120, 140)
    window.paste_items()

    tables = [i for i in markups(window) if isinstance(i, TableItem)]
    assert len(tables) == 1
    sheet = tables[0].sheet
    assert (sheet.rows, sheet.cols) == (3, 3)
    assert sheet.header_row                       # words over numbers
    assert sheet.raw(1, 0) == "Slab"
    assert sheet.value(1, 1).to("mm").magnitude == pytest.approx(150)
    assert sheet.value(2, 2).to("kN/m**3").magnitude == pytest.approx(22)


def test_a_pasted_table_can_be_calculated_against(window):
    clipboard = QApplication.clipboard()
    clipboard.setText("Layer\tt\tgamma\nSlab\t150 mm\t24 kN/m^3")
    window.view._last_scene_pos = QPointF(120, 140)
    table = window.paste_grid_as_table(clipboard.text())
    table.sheet.resize(2, 4)
    window.view.activate_table(table)
    table.set_cell(1, 3, "=B2*C2")
    table.current = (1, 3)
    window.refresh_formula_bar(table)
    window.cell_name.setText("q_slab")
    window.commit_cell_name()

    value = window.document.workspace.get("q_slab")
    assert value.to("kPa").magnitude == pytest.approx(3.6)


def test_pasting_a_single_value_still_pastes_markups_not_a_table(window):
    window.select_tool("rect")
    drag(window.view, 100, 100, 200, 200)
    window.select_tool("select")
    markups(window)[0].setSelected(True)
    window.copy_selection()
    window.paste_items()
    assert len([i for i in markups(window) if isinstance(i, TableItem)]) == 0
    assert len(markups(window)) == 2


def test_the_desk_behind_the_paper_is_actually_painted(window):
    """Overriding drawBackground loses Qt's own fill unless it is put back."""
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtCore import QRectF
    from calcforge.theme import CANVAS, LIGHT

    frame = window.current_page().frame
    scene = frame.scene()
    # A region of the canvas that reaches past the sheet on every side.
    area = frame.mapRectToScene(frame.page_rect()).adjusted(-60, -60, 60, 60)
    image = QImage(200, 200, QImage.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    scene.render(painter, QRectF(0, 0, 200, 200), area)
    painter.end()

    corner = image.pixelColor(3, 3).name()
    middle = image.pixelColor(100, 100).name()
    assert corner == CANVAS[LIGHT], "the desk was left transparent"
    assert middle == "#ffffff", "the paper is not white"


def test_every_markup_tool_is_reachable_from_the_toolbar(window):
    """A tool nobody can click is a tool that does not exist."""
    from calcforge.ui.tools import TOOLS

    from PySide6.QtWidgets import QToolBar

    for tool in TOOLS:
        assert tool.key in window.tool_actions, tool.key
        assert window.tool_actions[tool.key].isEnabled(), tool.key
    # File actions and markup tools sit on separate rows, so neither row has to
    # hide its last few buttons behind an overflow arrow.
    names = {bar.objectName() for bar in window.findChildren(QToolBar)}
    assert {"toolbar_main", "toolbar_tools", "toolbar_style"} <= names


# ---------------------------------------------------------------------------
# page operations must not touch what is on the other pages
# ---------------------------------------------------------------------------

def _page_counts(window):
    return [len(page.frame.markups()) for page in window.document.pages]


def _fill_three_pages(window):
    """Two markups on page 1, three on page 2, one on page 3."""
    from tests.test_usability import on_page

    for extra in range(2):
        window.add_page()
    for index, count in enumerate((2, 3, 1)):
        window.go_to_page(index)
        for number in range(count):
            window.select_tool("rect")
            x0, y0 = on_page(window, index, 60 + number * 80, 60)
            x1, y1 = on_page(window, index, 120 + number * 80, 120)
            drag(window.view, x0, y0, x1, y1)
    window.select_tool("select")
    assert _page_counts(window) == [2, 3, 1]


def test_adding_a_page_keeps_every_other_page(window):
    _fill_three_pages(window)
    window.go_to_page(0)
    window.add_page()
    assert _page_counts(window) == [2, 0, 3, 1]


def test_deleting_a_page_keeps_every_other_page(window, monkeypatch):
    from calcforge.ui import mainwindow as mw

    _fill_three_pages(window)
    monkeypatch.setattr(mw.QMessageBox, "question",
                        lambda *a, **k: mw.QMessageBox.Yes)
    window.go_to_page(1)
    window.delete_page()
    assert _page_counts(window) == [2, 1]


def test_duplicating_a_page_copies_it_and_leaves_the_rest(window):
    _fill_three_pages(window)
    window.go_to_page(1)
    window.duplicate_page()
    assert _page_counts(window) == [2, 3, 3, 1]


def test_undoing_a_page_insertion_puts_everything_back(window):
    _fill_three_pages(window)
    window.go_to_page(0)
    window.add_page()
    assert _page_counts(window) == [2, 0, 3, 1]
    window.undo_stack.undo()
    assert _page_counts(window) == [2, 3, 1]


def test_the_worked_example_survives_a_page_being_added(window):
    """The real thing: a document full of calculations, and a new page."""
    from calcforge.core.verify import verify_document

    window.load_sample()
    before = _page_counts(window)
    values = {name: info.value for name, info
              in window.document.workspace.variables.items()}
    assert sum(before) > 20

    window.add_page()
    assert _page_counts(window) == [before[0], 0] + before[1:]
    for name, value in values.items():
        assert window.document.workspace.get(name) is not None, f"{name} was lost"
    assert verify_document(window.document).ok


# ---------------------------------------------------------------------------
# the shortcut manager
# ---------------------------------------------------------------------------

def _press_into(editor, key, modifiers=Qt.NoModifier, text=""):
    from PySide6.QtGui import QKeyEvent
    QApplication.sendEvent(editor, QKeyEvent(QEvent.KeyPress, key, modifiers, text))


def test_the_manager_lists_every_binding_including_the_chords(window):
    from calcforge.ui import dialogs

    dialog = dialogs.ShortcutManagerDialog(window.shortcuts, window)
    ids = set(dialog.editors)
    assert "tool.measure_dimension" in ids and "tool.measure_area" in ids
    assert "tool.rect" in ids and "insert.math" in ids
    assert dialog.editors["tool.measure_dimension"].text() == "Alt+M"
    assert dialog.editors["tool.rect"].text() == "R"
    dialog.deleteLater()


def test_pressing_keys_records_them(window):
    from calcforge.ui import dialogs

    dialog = dialogs.ShortcutManagerDialog(window.shortcuts, window)
    editor = dialog.editors["tool.measure_dimension"]
    _press_into(editor, Qt.Key_D, Qt.ControlModifier | Qt.ShiftModifier)
    assert editor.text() == "Ctrl+Shift+D"

    plain = dialog.editors["tool.rect"]
    _press_into(plain, Qt.Key_J, Qt.NoModifier, "j")
    assert plain.text() == "j"           # a bare character stays a character
    dialog.deleteLater()


def test_backspace_clears_and_escape_puts_it_back(window):
    from calcforge.ui import dialogs

    dialog = dialogs.ShortcutManagerDialog(window.shortcuts, window)
    editor = dialog.editors["tool.cloud"]
    editor.focusInEvent(__import__("PySide6.QtGui", fromlist=["QFocusEvent"])
                        .QFocusEvent(QEvent.FocusIn))
    _press_into(editor, Qt.Key_Backspace)
    assert editor.text() == ""
    _press_into(editor, Qt.Key_Escape)
    assert editor.text() == "C"
    dialog.deleteLater()


def test_a_clash_is_flagged(window):
    from calcforge.ui import dialogs

    dialog = dialogs.ShortcutManagerDialog(window.shortcuts, window)
    dialog.editors["tool.cloud"].setText("R")        # already the rectangle
    dialog._check()
    assert "both on r" in dialog.warning.text().lower()
    assert "#c0392b" in dialog.editors["tool.rect"].styleSheet()
    dialog.editors["tool.cloud"].setText("C")
    dialog._check()
    assert dialog.warning.text() == ""
    dialog.deleteLater()


def test_a_changed_shortcut_reaches_the_action_and_the_canvas(window):
    from calcforge.ui import dialogs
    from calcforge.ui.tools import TOOL_MAP

    dialog = dialogs.ShortcutManagerDialog(window.shortcuts, window)
    dialog.editors["tool.measure_dimension"].setText("Ctrl+Shift+Y")
    dialog.editors["tool.rect"].setText("j")      # a key nothing else uses
    dialog.apply()
    window.shortcuts.save()
    window.apply_shortcuts()

    assert window.tool_actions["measure_dimension"].shortcut().toString() == "Ctrl+Shift+Y"
    # the bare key is the canvas's job, so the action carries none
    assert window.tool_actions["rect"].shortcut().isEmpty()
    window.view._last_scene_pos = QPointF(100, 100)
    assert window.run_typed_binding("j", Qt.NoModifier, QPointF(100, 100))
    assert window.view.current_tool().key == "rect"

    # …and the old key no longer does anything
    assert not window.run_typed_binding("r", Qt.NoModifier, QPointF(100, 100))


def test_reset_all_puts_the_defaults_back(window):
    from calcforge.ui import dialogs

    dialog = dialogs.ShortcutManagerDialog(window.shortcuts, window)
    dialog.editors["tool.rect"].setText("z")
    dialog._reset_all()
    assert dialog.editors["tool.rect"].text() == "R"
    assert dialog.editors["tool.measure_area"].text() == "Shift+Alt+A"
    dialog.deleteLater()


def test_the_filter_narrows_the_list(window):
    from calcforge.ui import dialogs

    dialog = dialogs.ShortcutManagerDialog(window.shortcuts, window)
    dialog.filter.setText("dimension")
    shown = [b for b in window.shortcuts.bindings()
             if not dialog.table.isRowHidden(dialog.rows[b.action_id])]
    assert [b.action_id for b in shown] == ["tool.measure_dimension"]
    dialog.filter.setText("")
    assert not dialog.table.isRowHidden(dialog.rows["tool.rect"])
    dialog.deleteLater()


def test_a_rebound_chord_is_still_silent_while_typing(window):
    from calcforge.ui import dialogs
    from tests.test_usability import drag as ui_drag, swallowed

    dialog = dialogs.ShortcutManagerDialog(window.shortcuts, window)
    dialog.editors["tool.measure_dimension"].setText("Alt+K")
    dialog.apply()
    window.apply_shortcuts()

    window.select_tool("text")
    ui_drag(window.view, 100, 100, 340, 150)
    assert window.view.is_editing()
    assert swallowed(window, Qt.Key_K, Qt.AltModifier)


def test_the_manager_refuses_to_save_a_key_bound_twice(window, monkeypatch):
    from calcforge.ui import dialogs

    warned = []
    monkeypatch.setattr(dialogs.QMessageBox, "warning",
                        lambda *args, **kwargs: warned.append(args[-1]))
    dialog = dialogs.ShortcutManagerDialog(window.shortcuts, window)
    dialog.editors["tool.cloud"].setText("R")
    dialog.accept()
    assert dialog.result() != dialogs.QDialog.Accepted
    assert warned and "more than one thing" in warned[0]

    dialog.editors["tool.cloud"].setText("C")
    dialog.accept()
    assert dialog.result() == dialogs.QDialog.Accepted


# ---------------------------------------------------------------------------
# Header, footer and logo, through the dialog
# ---------------------------------------------------------------------------

def test_choosing_a_logo_puts_it_in_the_document(window, tmp_path, monkeypatch):
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QFileDialog
    from calcforge.ui import dialogs

    path = str(tmp_path / "practice.png")
    QImage(80, 40, QImage.Format_ARGB32).save(path)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (path, ""))

    dialog = dialogs.DocumentPropertiesDialog(window.document)
    dialog._choose_logo()
    dialog.logo_slot.setCurrentIndex(dialog.logo_slot.findData("footer_right"))
    dialog.logo_height.setValue(14.0)
    dialog.apply()
    dialog.deleteLater()

    settings = window.document.settings
    assert settings.logo_key
    assert window.document.asset(settings.logo_key)
    assert settings.logo_slot == "footer_right"
    assert settings.logo_height_mm == pytest.approx(14.0)


def test_removing_the_logo_takes_it_off_every_page(window):
    from calcforge.ui import dialogs

    window.document.settings.logo_key = window.document.add_asset(b"not-an-image", "png")
    dialog = dialogs.DocumentPropertiesDialog(window.document)
    dialog._clear_logo()
    dialog.apply()
    dialog.deleteLater()
    assert window.document.settings.logo_key == ""


def test_the_header_and_footer_have_a_menu_entry_of_their_own(window):
    from calcforge.ui import dialogs

    assert window.act_header_footer.text() == "Header and footer…"
    dialog = dialogs.DocumentPropertiesDialog(window.document)
    dialog.show_tab("header")
    assert "Header" in dialog.tabs.tabText(dialog.tabs.currentIndex())
    dialog.deleteLater()


def test_a_logo_that_cannot_be_read_leaves_the_page_alone(window):
    """A file that is not an image must not stop the page drawing."""
    window.document.settings.logo_key = window.document.add_asset(b"rubbish", "png")
    window.document.settings.show_header = True
    frame = window.document.pages[0].frame
    frame.render_image(dpi=48.0)             # no exception is the point
    assert frame.load_logo() is None


# ---------------------------------------------------------------------------
# Inserting PDF pages
# ---------------------------------------------------------------------------

def _drawing_pdf(path, colour="#3366aa"):
    """A one-page PDF with something on it."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QPainter, QPdfWriter

    writer = QPdfWriter(path)
    writer.setResolution(150)
    painter = QPainter(writer)
    painter.fillRect(QRectF(200, 200, 800, 500), QColor(colour))
    painter.end()
    return path


def _ink(image) -> int:
    return sum(1 for y in range(0, image.height(), 5)
               for x in range(0, image.width(), 5)
               if image.pixel(x, y) & 0xFFFFFF != 0xFFFFFF)


def _import_pdf(window, monkeypatch, path, indices=(0,)):
    from calcforge.ui import dialogs
    monkeypatch.setattr(dialogs.PdfImportDialog, "exec",
                        lambda self: dialogs.QDialog.Accepted)
    monkeypatch.setattr(dialogs.PdfImportDialog, "selection",
                        lambda self: (path, list(indices), "original", 150.0))
    window.insert_pdf()


def test_an_inserted_pdf_page_carries_the_drawing(window, tmp_path, monkeypatch):
    path = _drawing_pdf(str(tmp_path / "plan.pdf"))
    _import_pdf(window, monkeypatch, path)

    assert len(window.document.pages) == 2
    page = window.document.pages[1]
    assert page.background_key
    assert window.document.asset(page.background_key)
    assert _ink(page.frame.render_image(dpi=48.0)) > 100     # not a blank sheet


def test_an_inserted_pdf_page_survives_saving_and_reopening(window, tmp_path, monkeypatch):
    from calcforge.core.document import Document
    from calcforge.io import project as project_io

    path = _drawing_pdf(str(tmp_path / "plan.pdf"))
    _import_pdf(window, monkeypatch, path)
    saved = str(tmp_path / "job.cfx")
    project_io.save_document(window.document, saved)

    reopened = Document()
    project_io.load_document(reopened, saved)
    key = reopened.pages[1].background_key
    assert key and reopened.asset(key)


def test_an_inserted_pdf_page_prints(window, tmp_path, monkeypatch):
    from calcforge.io import export as export_io, pdfio

    path = _drawing_pdf(str(tmp_path / "plan.pdf"))
    _import_pdf(window, monkeypatch, path)
    out = str(tmp_path / "out.pdf")
    export_io.export_pdf(window.document, out)

    source = pdfio.PdfSource(out)
    try:
        image = source.doc.render(1, source.doc.pagePointSize(1).toSize())
    finally:
        source.close()
    assert _ink(image) > 100


def test_undoing_an_insert_and_redoing_it_keeps_the_drawing(window, tmp_path, monkeypatch):
    path = _drawing_pdf(str(tmp_path / "plan.pdf"))
    _import_pdf(window, monkeypatch, path)
    window.undo_stack.undo()
    assert len(window.document.pages) == 1
    window.undo_stack.redo()
    assert _ink(window.document.pages[1].frame.render_image(dpi=48.0)) > 100


def test_a_huge_sheet_is_rendered_smaller_rather_than_coming_out_blank(window):
    """An A0 at 300 dpi is 140 megapixels; Qt will not allocate that."""
    from calcforge.io.pdfio import MAX_PIXELS, PdfPageInfo, PdfSource

    a0 = PdfPageInfo(0, 2384.0, 3370.0)
    scale = PdfSource._scale_for(a0, 300.0)
    assert (a0.width_pt * scale) * (a0.height_pt * scale) <= MAX_PIXELS + 1
    # a normal sheet is untouched
    assert PdfSource._scale_for(PdfPageInfo(0, 595.0, 842.0), 150.0) == \
        pytest.approx(150.0 / 72.0)


def test_a_page_that_renders_but_cannot_be_stored_is_reported(window, tmp_path, monkeypatch):
    """An empty asset used to mean a blank page and no explanation."""
    from calcforge.io import pdfio

    path = _drawing_pdf(str(tmp_path / "plan.pdf"))
    monkeypatch.setattr("PySide6.QtGui.QImage.save",
                        lambda self, *a, **k: False)
    source = pdfio.PdfSource(path)
    try:
        with pytest.raises(OSError, match="could not be stored"):
            source.render_png(0, 150.0)
    finally:
        source.close()


def test_the_import_dialog_previews_the_page_it_will_bring_in(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from calcforge.ui import dialogs

    path = _drawing_pdf(str(tmp_path / "plan.pdf"))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (path, ""))
    dialog = dialogs.PdfImportDialog(window)
    try:
        dialog.browse()
        assert dialog.preview.pixmap() is not None
        assert not dialog.preview.pixmap().isNull()
        assert dialog.preview.text() == ""
        dialog.pages.setText("9")                 # out of range
        assert dialog.preview.text() == "No pages in that range"
    finally:
        dialog.deleteLater()


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------

def test_preferences_survive_being_saved_and_read_back(qapp, tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings
    from calcforge.ui import preferences

    monkeypatch.setattr(QSettings, "setValue", QSettings.setValue)
    prefs = preferences.Preferences(wheel=preferences.WHEEL_SCROLL,
                                    self_contained_blocks=True,
                                    check_spelling=False)
    preferences.save(prefs)
    try:
        read = preferences.load()
        assert read.wheel == preferences.WHEEL_SCROLL
        assert read.self_contained_blocks is True
        assert read.check_spelling is False
    finally:
        preferences.save(preferences.Preferences())
        preferences.forget()


def test_a_new_block_shares_its_names_by_default(qapp):
    from calcforge.items.mathitem import MathItem
    from calcforge.ui import preferences

    preferences.forget()
    assert MathItem("x := 1", block=True).local_scope is False


def test_a_block_can_be_made_self_contained_by_default(qapp):
    from calcforge.items.mathitem import MathItem
    from calcforge.ui import preferences

    prefs = preferences.current()
    was = prefs.self_contained_blocks
    prefs.self_contained_blocks = True
    try:
        assert MathItem("x := 1", block=True).local_scope is True
    finally:
        prefs.self_contained_blocks = was


def test_the_import_dialog_does_not_ask_for_a_resolution(window):
    """There is no resolution to choose, so there is no question about one.

    Everything the file holds comes across as the file has it — the line work
    as real geometry, the rest as a picture behind it, made as good as the
    sheet allows. The only question left is one about this document: what size
    the imported pages should be.
    """
    from PySide6.QtWidgets import QLabel
    from calcforge.ui import dialogs
    from calcforge.io import pdfio

    dialog = dialogs.PdfImportDialog(window)
    try:
        assert not hasattr(dialog, "dpi"), "nobody is asked for a dpi"
        assert not hasattr(dialog, "vectors"), "the line work always comes"
        labels = [label.text() for label in dialog.findChildren(QLabel)]
        assert not any("Render at" in text for text in labels)
        _path, _pages, _fit, dpi, vectors = dialog.selection()
        assert dpi == pdfio.BEST_DPI
        assert vectors is True
    finally:
        dialog.deleteLater()
