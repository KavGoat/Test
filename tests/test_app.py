"""End-to-end exercises against a real main window (offscreen)."""
import os

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication

from markforge.items.measure import CountItem, MeasureItem
from markforge.items.text import TextItem
from markforge.ui.tools import DRAG, FREE, POLY, TOOLS

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

def test_measurement_follows_the_page_scale(window):
    from markforge.core.document import PageScale
    window.current_page().scale = PageScale.from_ratio(100)
    window.select_tool("measure_length")
    drag(window.view, 100, 400, 300, 400)
    measure = [i for i in markups(window) if isinstance(i, MeasureItem)][0]
    assert measure.value.to("m").magnitude == pytest.approx(7.0555, rel=2e-2)
    assert "m" in measure.value_text


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


def test_a_page_excluded_from_print_is_grey_and_is_not_exported(window, tmp_path):
    from markforge.core.document import Document
    from markforge.io import export as export_io, pdfio, project as project_io

    window.add_page()
    window.add_page()
    menu = window.page_menu(1)
    include = next(action for action in menu.actions() if action.text() == "Print")
    assert include.isChecked()
    include.setChecked(False)                 # the real QAction signal path

    assert not window.document.pages[1].printable
    assert window.pages_panel.list.item(1).foreground().color().name() == "#8b929c"

    pdf_path = str(tmp_path / "included.pdf")
    export_io.export_pdf(window.document, pdf_path)
    assert pdfio.page_count(pdf_path) == 2
    assert len(export_io.export_images(window.document, str(tmp_path), 40)) == 2

    cfx_path = str(tmp_path / "included.cfx")
    project_io.save_document(window.document, cfx_path)
    reopened = Document()
    project_io.load_document(reopened, cfx_path)
    assert [page.printable for page in reopened.pages] == [True, False, True]


def test_zoom_controls(window):
    window.view.set_zoom(1.0)
    window.view.zoom_in()
    assert window.view.zoom() > 1.0
    window.view.zoom_out()
    assert window.view.zoom() == pytest.approx(1.0, rel=1e-3)
    window.view.fit_page()
    assert 0.05 < window.view.zoom() < 4.0


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


def test_page_scale_change_updates_measurements(window):
    from markforge.core.document import PageScale
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


def _type_on_canvas(window, text, x=140.0, y=180.0):
    from PySide6.QtCore import QPointF as _P
    window.select_tool("select")
    window.view.scene().clearSelection()
    window.view._last_scene_pos = _P(x, y)
    key(window.view, Qt.Key_unknown, text)


def test_slash_on_bare_canvas_starts_nothing(window):
    """Slash is division inside equations, not a second entry trigger."""
    _type_on_canvas(window, "/")
    assert editing_item(window) is None
    assert markups(window) == []


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


def test_bound_tool_letter_selects_its_tool(window):
    _type_on_canvas(window, "r")
    assert window.view.tool_key == "rect"
    window.select_tool("select")
    _type_on_canvas(window, "h")
    assert window.view.tool_key == "highlighter"


def test_shortcut_conflicts_are_detectable(window):
    manager = window.shortcuts
    assert manager.conflicts() == {}
    manager.set_sequence("tool.rect", '"')
    assert '"' in manager.conflicts()
    manager.reset()


def test_renumber_counts_closes_gaps(window):
    window.view.count_subject = "Doors"
    for x in (100, 200, 300):
        window.select_tool("count")
        press(window.view, x, 400)
        release(window.view, x, 400)
    window.select_tool("select")
    from markforge.items.measure import CountItem
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
    from markforge.items.shapes import RectItem

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
    from markforge.io import project as project_io
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
    from markforge.theme import CANVAS, DARK, LIGHT, tokens

    window.toggle_theme(True)
    assert tokens(DARK)["chrome"] in QApplication.instance().styleSheet()
    assert window.view.scene().backgroundBrush().color().name() == CANVAS[DARK]
    # the page itself stays paper-white
    image = window.current_page().frame.render_image(dpi=40, for_print=False)
    assert image.pixelColor(image.width() // 2, image.height() // 2).name() == "#ffffff"
    window.toggle_theme(False)
    assert tokens(LIGHT)["chrome"] in QApplication.instance().styleSheet()


def real_double_click(view, x, y):
    """The sequence Qt actually sends: press, release, double-click, release."""
    from PySide6.QtWidgets import QApplication
    for kind in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease,
                 QEvent.MouseButtonDblClick, QEvent.MouseButtonRelease):
        QApplication.sendEvent(view.viewport(), _event(view, kind, x, y))


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

def test_the_desk_behind_the_paper_is_actually_painted(window):
    """Overriding drawBackground loses Qt's own fill unless it is put back."""
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtCore import QRectF
    from markforge.theme import CANVAS, LIGHT

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
    from markforge.ui.tools import TOOLS

    from PySide6.QtWidgets import QToolBar

    for tool in TOOLS:
        assert tool.key in window.tool_actions, tool.key
        assert window.tool_actions[tool.key].isEnabled(), tool.key
    # File actions and markup tools sit on separate rows, so neither row has to
    # hide its last few buttons behind an overflow arrow.
    names = {bar.objectName() for bar in window.findChildren(QToolBar)}
    assert {"toolbar_main", "toolbar_tools", "toolbar_style"} <= names


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
    from markforge.ui import mainwindow as mw

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


def _press_into(editor, key, modifiers=Qt.NoModifier, text=""):
    from PySide6.QtGui import QKeyEvent
    QApplication.sendEvent(editor, QKeyEvent(QEvent.KeyPress, key, modifiers, text))


def test_the_manager_lists_every_binding_including_the_chords(window):
    from markforge.ui import dialogs

    dialog = dialogs.ShortcutManagerDialog(window.shortcuts, window)
    ids = set(dialog.editors)
    assert "tool.measure_dimension" in ids and "tool.measure_area" in ids
    assert "tool.rect" in ids and "insert.text" in ids
    assert dialog.editors["tool.measure_dimension"].text() == "Alt+M"
    assert dialog.editors["tool.rect"].text() == "R"
    dialog.deleteLater()


def test_pressing_keys_records_them(window):
    from markforge.ui import dialogs

    dialog = dialogs.ShortcutManagerDialog(window.shortcuts, window)
    editor = dialog.editors["tool.measure_dimension"]
    _press_into(editor, Qt.Key_D, Qt.ControlModifier | Qt.ShiftModifier)
    assert editor.text() == "Ctrl+Shift+D"

    plain = dialog.editors["tool.rect"]
    _press_into(plain, Qt.Key_J, Qt.NoModifier, "j")
    assert plain.text() == "j"           # a bare character stays a character
    dialog.deleteLater()


def test_backspace_clears_and_escape_puts_it_back(window):
    from markforge.ui import dialogs

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
    from markforge.ui import dialogs

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
    from markforge.ui import dialogs
    from markforge.ui.tools import TOOL_MAP

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
    from markforge.ui import dialogs

    dialog = dialogs.ShortcutManagerDialog(window.shortcuts, window)
    dialog.editors["tool.rect"].setText("z")
    dialog._reset_all()
    assert dialog.editors["tool.rect"].text() == "R"
    assert dialog.editors["tool.measure_area"].text() == "Shift+Alt+A"
    dialog.deleteLater()


def test_the_filter_narrows_the_list(window):
    from markforge.ui import dialogs

    dialog = dialogs.ShortcutManagerDialog(window.shortcuts, window)
    dialog.filter.setText("dimension")
    shown = [b for b in window.shortcuts.bindings()
             if not dialog.table.isRowHidden(dialog.rows[b.action_id])]
    assert [b.action_id for b in shown] == ["tool.measure_dimension"]
    dialog.filter.setText("")
    assert not dialog.table.isRowHidden(dialog.rows["tool.rect"])
    dialog.deleteLater()


def test_a_rebound_chord_is_still_silent_while_typing(window):
    from markforge.ui import dialogs
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
    from markforge.ui import dialogs

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
    from markforge.ui import dialogs

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
    from markforge.ui import dialogs

    window.document.settings.logo_key = window.document.add_asset(b"not-an-image", "png")
    dialog = dialogs.DocumentPropertiesDialog(window.document)
    dialog._clear_logo()
    dialog.apply()
    dialog.deleteLater()
    assert window.document.settings.logo_key == ""


def test_the_header_and_footer_have_a_menu_entry_of_their_own(window):
    from markforge.ui import dialogs

    assert window.act_header_footer.text() == "Header/footer…"
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


def _text_pdf(path, text="SELECTABLE SOURCE TEXT"):
    """A one-page PDF containing real text, not a raster image."""
    from pypdf import PdfWriter
    from pypdf.generic import (DecodedStreamObject, DictionaryObject,
                               NameObject)

    writer = PdfWriter()
    page = writer.add_blank_page(width=595, height=842)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({
            NameObject("/F1"): writer._add_object(font),
        }),
    })
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 18 Tf 100 700 Td ({text}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    with open(path, "wb") as handle:
        writer.write(handle)
    return path


def _ink(image) -> int:
    return sum(1 for y in range(0, image.height(), 5)
               for x in range(0, image.width(), 5)
               if image.pixel(x, y) & 0xFFFFFF != 0xFFFFFF)


def _import_pdf(window, monkeypatch, path, indices=(0,)):
    from markforge.ui import dialogs
    monkeypatch.setattr(dialogs.PdfImportDialog, "exec",
                        lambda self: dialogs.QDialog.Accepted)
    monkeypatch.setattr(dialogs.PdfImportDialog, "selection",
                        lambda self: (path, list(indices), "original", 150.0))
    window.insert_pdf()


def _open_pdf(window, monkeypatch, path):
    from PySide6.QtWidgets import QFileDialog

    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        lambda *args, **kwargs: (path, "PDF documents (*.pdf)"))
    window.act_open.trigger()
    QApplication.processEvents()


def test_an_inserted_pdf_page_carries_the_drawing(window, tmp_path, monkeypatch):
    path = _drawing_pdf(str(tmp_path / "plan.pdf"))
    _import_pdf(window, monkeypatch, path)

    assert len(window.document.pages) == 2
    page = window.document.pages[1]
    assert page.background_key
    assert window.document.asset(page.background_key)
    assert page.pdf_key
    assert window.document.asset(page.pdf_key).startswith(b"%PDF")
    assert page.pdf_page_index == 0
    assert _ink(page.frame.render_image(dpi=48.0)) > 100     # not a blank sheet


def test_pdf_review_snapshot_survives_edit_save_reopen_and_export(
        window, tmp_path, monkeypatch):
    from pypdf import PdfReader
    from markforge.core.document import Document
    from markforge.io import export as export_io, project as project_io
    from markforge.items.shapes import PolyItem
    from markforge.items.snapshot import SnapshotItem

    path = _drawing_pdf(str(tmp_path / "review.pdf"))
    _open_pdf(window, monkeypatch, path)
    frame = window.document.pages[0].frame
    drawing = [item for item in frame.markups() if item.layer == "Drawing"]
    assert drawing, "the imported PDF fixture supplied no vector drawing"

    QApplication.sendEvent(
        window.view, QKeyEvent(QEvent.KeyPress, Qt.Key_G, Qt.NoModifier, "g"))
    for kind, x, y, button, buttons in (
            (QEvent.MouseButtonPress, 40, 40, Qt.LeftButton, Qt.LeftButton),
            (QEvent.MouseMove, 500, 500, Qt.NoButton, Qt.LeftButton),
            (QEvent.MouseButtonRelease, 500, 500, Qt.LeftButton, Qt.NoButton)):
        QApplication.sendEvent(
            window.view.viewport(),
            _event(window.view, kind, x, y, button, buttons))
    assert window._clipboard and window._clipboard[0]["type"] == "snapshot"
    window.paste_items()
    shot = [item for item in frame.markups() if isinstance(item, SnapshotItem)]
    assert len(shot) == 1

    # Ordinary review work after the Snapshot must not disturb it.
    line = PolyItem("line", [QPointF(20, 20), QPointF(80, 20)])
    frame.add_markup(line)
    assert shot[0] in frame.markups()

    saved = str(tmp_path / "review.cfx")
    project_io.save_document(window.document, saved)
    reopened = Document()
    project_io.load_document(reopened, saved)
    snapshots = [entry for entry in reopened.pages[0]._pending_items
                 if entry.get("type") == "snapshot"]
    assert len(snapshots) == 1
    assert reopened.asset(snapshots[0]["asset"])

    exported = str(tmp_path / "review-export.pdf")
    export_io.export_pdf(window.document, exported, resolution=150)
    assert len(PdfReader(exported).pages) == 1


def test_an_inserted_pdf_page_survives_saving_and_reopening(window, tmp_path, monkeypatch):
    from markforge.core.document import Document
    from markforge.io import project as project_io

    path = _drawing_pdf(str(tmp_path / "plan.pdf"))
    _import_pdf(window, monkeypatch, path)
    saved = str(tmp_path / "job.cfx")
    project_io.save_document(window.document, saved)

    reopened = Document()
    project_io.load_document(reopened, saved)
    page = reopened.pages[1]
    assert page.background_key and reopened.asset(page.background_key)
    assert page.pdf_key and reopened.asset(page.pdf_key).startswith(b"%PDF")
    assert page.pdf_page_index == 0


def test_an_inserted_pdf_page_prints(window, tmp_path, monkeypatch):
    from markforge.io import export as export_io, pdfio

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


def test_an_inserted_pdf_keeps_selectable_text_when_exported(
        window, tmp_path, monkeypatch):
    from pypdf import PdfReader
    from markforge.io import export as export_io

    path = _text_pdf(str(tmp_path / "notes.pdf"))
    _import_pdf(window, monkeypatch, path)
    out = str(tmp_path / "out.pdf")
    export_io.export_pdf(window.document, out, resolution=150)

    reader = PdfReader(out)
    assert len(reader.pages) == 2
    assert "SELECTABLE SOURCE TEXT" in (reader.pages[1].extract_text() or "")


def test_undoing_an_insert_and_redoing_it_keeps_the_drawing(window, tmp_path, monkeypatch):
    path = _drawing_pdf(str(tmp_path / "plan.pdf"))
    _import_pdf(window, monkeypatch, path)
    window.undo_stack.undo()
    assert len(window.document.pages) == 1
    window.undo_stack.redo()
    assert _ink(window.document.pages[1].frame.render_image(dpi=48.0)) > 100


def test_a_huge_sheet_is_rendered_smaller_rather_than_coming_out_blank(window):
    """An A0 at 300 dpi is 140 megapixels; Qt will not allocate that."""
    from markforge.io.pdfio import MAX_PIXELS, PdfPageInfo, PdfSource

    a0 = PdfPageInfo(0, 2384.0, 3370.0)
    scale = PdfSource._scale_for(a0, 300.0)
    assert (a0.width_pt * scale) * (a0.height_pt * scale) <= MAX_PIXELS + 1
    # a normal sheet is untouched
    assert PdfSource._scale_for(PdfPageInfo(0, 595.0, 842.0), 150.0) == \
        pytest.approx(150.0 / 72.0)


def test_a_page_that_renders_but_cannot_be_stored_is_reported(window, tmp_path, monkeypatch):
    """An empty asset used to mean a blank page and no explanation."""
    from markforge.io import pdfio

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
    from markforge.ui import dialogs

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
    from markforge.ui import preferences

    monkeypatch.setattr(QSettings, "setValue", QSettings.setValue)
    prefs = preferences.Preferences(wheel=preferences.WHEEL_SCROLL,
                                    self_contained_blocks=True,
                                    check_spelling=False,
                                    recover_flattened=False)
    preferences.save(prefs)
    try:
        read = preferences.load()
        assert read.wheel == preferences.WHEEL_SCROLL
        assert read.self_contained_blocks is True
        assert read.check_spelling is False
        assert read.recover_flattened is False
    finally:
        preferences.save(preferences.Preferences())
        preferences.forget()


def test_the_import_dialog_does_not_ask_for_a_resolution(window):
    """There is no resolution to choose, so there is no question about one.

    Everything the file holds comes across as the file has it — the line work
    as real geometry, the rest as a picture behind it, made as good as the
    sheet allows. The only question left is one about this document: what size
    the imported pages should be.
    """
    from PySide6.QtWidgets import QLabel
    from markforge.ui import dialogs
    from markforge.io import pdfio

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
