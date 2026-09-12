"""Acceptance tests for the September 11 drawing-review report."""
import pytest
import pymupdf
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from markforge.io import pdfio, project
from markforge.items.base import build_item
from markforge.items.snapshot import SnapshotItem
from tests.test_usability import drag, click, press_key


def import_drawing(window, tmp_path, rotation=0):
    source = pymupdf.open()
    page = source.new_page(width=400, height=300)
    page.draw_rect(page.rect, color=None, fill=(0.8, 0.9, 1))
    page.draw_line((40, 80), (180, 80), color=(0, 0, 0), width=3)
    page.draw_bezier((40, 100), (70, 160), (120, 40), (180, 100), width=2)
    page.set_rotation(rotation)
    path = tmp_path / "source.pdf"
    source.save(path)
    source.close()
    pdfio.import_pages(window.document, str(path), [0], at=0)
    window.rebuild_scenes()
    window.go_to_page(0)
    window.view.set_zoom(1)
    return window.document.pages[0].frame


def replay(item):
    rect = item.local_rect()
    image = QImage(int(rect.width()), int(rect.height()), QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    item.paint_content(painter)
    painter.end()
    return image


def test_pdf_snapshot_repeated_capture_paste_and_reopen(window, tmp_path):
    frame = import_drawing(window, tmp_path)
    for _ in range(2):
        window.select_tool("snapshot")
        a = frame.mapToScene(QPointF(20, 20))
        b = frame.mapToScene(QPointF(200, 180))
        drag(window.view, a.x(), a.y(), b.x(), b.y())
        assert window._clipboard, window.status_hint.text()
        payload = window._clipboard[0]
        assert any(p["type"] == "pdf_path" for p in payload["source_items"])
        window.paste_items()
        pasted = [i for i in frame.markups() if isinstance(i, SnapshotItem)]
        assert pasted
        image = replay(pasted[-1])
        assert image.pixelColor(60, 60).alpha() > 0
        assert image.pixelColor(10, 10).alpha() == 0
        press_key(window.view, Qt.Key_Escape)
    saved = tmp_path / "snapshot.pdf"
    project.save_document(window.document, str(saved))
    with pymupdf.open(saved) as pdf:
        assert list(pdf[0].annots()), "snapshots remain PDF annotations"
        assert not pdf[0].get_images(full=True), "vector snapshots must not become page bitmaps"
    from markforge.core.document import Document
    reopened = Document()
    project.load_document(reopened, str(saved))
    from markforge.ui.scene import DocumentScene
    scene = DocumentScene(reopened)
    for page in reopened.pages:
        page.frame = scene.add_frame(page)
        page.frame.load_items(page._pending_items)
    snapshots = [i for i in reopened.pages[0].frame.markups() if isinstance(i, SnapshotItem)]
    assert snapshots and replay(snapshots[-1]).pixelColor(60, 60).alpha() > 0


def test_pdf_snapshot_recolours_curves_without_losing_source(window, tmp_path):
    from markforge.io.recolour import colourise_lines
    frame = import_drawing(window, tmp_path)
    window.take_snapshot(frame, QRectF(20, 20, 180, 160))
    item = build_item(window._clipboard[0])
    item.load_from_document(window.document)
    sources = item.source_markups()
    assert any(any(c[0] == "c" for c in i.commands) for i in sources)
    colourise_lines(sources, QColor("#ff0000"))
    item.redraw_from(sources)
    assert replay(item).pixelColor(60, 60).red() > 200
    assert replay(item).pixelColor(10, 10).alpha() == 0


def test_whiteout_preserves_outside_vectors_and_undo(window, tmp_path):
    frame = import_drawing(window, tmp_path)
    original = frame.page.pdf_key
    window.select_tool("whiteout")
    a, b = frame.mapToScene(QPointF(70, 60)), frame.mapToScene(QPointF(120, 90))
    drag(window.view, a.x(), a.y(), b.x(), b.y())
    page = window.document.pages[0]
    assert page.pdf_key != original
    with pymupdf.open(stream=window.document.asset(page.pdf_key), filetype="pdf") as source:
        pix = source[0].get_pixmap()
        assert pix.pixel(90, 80)[:3] == (255, 255, 255)
        assert max(pix.pixel(50, 80)[:3]) < 30
        assert max(pix.pixel(160, 80)[:3]) < 30
    window.undo_stack.undo()
    assert window.document.pages[0].pdf_key == original
    window.undo_stack.redo()
    assert window.document.pages[0].pdf_key != original
    saved = tmp_path / "whiteout.pdf"
    project.save_document(window.document, str(saved))
    with pymupdf.open(saved) as source:
        pix = source[0].get_pixmap()
        assert pix.pixel(90, 80)[:3] == (255, 255, 255)
        assert max(pix.pixel(50, 80)[:3]) < 30


def test_hatch_scale_controls_and_undo(window):
    from markforge.items.shapes import RectItem
    from PySide6.QtWidgets import QDoubleSpinBox
    item = RectItem()
    item.style.fill, item.style.hatch = "#000000", "cross"
    window.view.frame().add_markup(item, QPointF(100, 100))
    item.setSelected(True)
    window.refresh_selection()
    window.hatch_scale_spin.setValue(2.5)
    assert item.style.hatch_scale == 2.5
    assert item.style.brush().transform().m11() == 2.5
    prop = window.properties_panel.findChild(QDoubleSpinBox, "hatchScale")
    assert prop.value() == 2.5
    prop.setValue(3)
    assert item.style.hatch_scale == 3
    window.undo_stack.undo()
    restored = next(i for i in window.view.frame().markups() if i.uid == item.uid)
    assert restored.style.hatch_scale == 2.5
    assert build_item(restored.serialize()).style.hatch_scale == 2.5


def test_line_snaps_to_callout_edge_between_handles(window):
    from markforge.items.text import CalloutItem
    from markforge.items.shapes import PolyItem
    frame = window.view.frame()
    box = CalloutItem("Note")
    box.set_local_rect(QRectF(0, 0, 150, 150))
    frame.add_markup(box, QPointF(300, 250))
    window.document.settings.snap_to_items = True
    window.document.settings.snap_to_alignment = False
    window.document.settings.snap_to_grid = False
    window.select_tool("line")
    drag(window.view, 150, 280, 302, 280)
    line = next(i for i in frame.markups() if isinstance(i, PolyItem))
    assert line.mapToScene(line.points[-1]).x() == pytest.approx(300, abs=0.6)


def test_tab_drag_preview_and_return_to_existing_window(window):
    from PySide6.QtTest import QTest
    from PySide6.QtCore import QEvent, QPoint
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    window.show()
    window.move(0, 0)
    first = window.document
    other = window.open_new_window()
    other.move(500, 300)
    try:
        QApplication.processEvents()
        bar = window.document_tabs
        start = bar.tabRect(0).center()
        QTest.mousePress(bar, Qt.LeftButton, Qt.NoModifier, start)
        local = start + QPoint(0, 100)
        QApplication.sendEvent(bar, QMouseEvent(QEvent.MouseMove, QPointF(local),
            QPointF(bar.mapToGlobal(local)), Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
        assert bar._preview is not None and bar._preview.isVisible()
        point = other.document_tabs.mapToGlobal(other.document_tabs.tabRect(0).center())
        QTest.mouseRelease(bar, Qt.LeftButton, Qt.NoModifier, bar.mapFromGlobal(point))
        assert bar._preview is None
        assert other.document is first
        assert window.document is not first
        other.move_document_to(other._active_tab, window)
        assert window.document is first
        assert window.document_tabs.isVisible()
    finally:
        other.confirm_discard = lambda: True
        other.close()
        other.deleteLater()


def test_two_pdf_views_do_not_cancel_each_others_resolution(qapp):
    from markforge.io.pdftiles import TileCache
    from PySide6.QtWidgets import QWidget
    cache = TileCache()
    cache._ask = lambda key, *a, **kw: cache._waiting.add(key)
    close, overview = QWidget(), QWidget()
    page = QRectF(0, 0, 1000, 1000)
    cache.tiles("pdf", b"pdf", 0, page, 4, page, consumer=close)
    cache.tiles("pdf", b"pdf", 0, page, 0.25, page, consumer=overview)
    assert {k.scale for k in cache._waiting} == {4, 0.25}
    cache.tiles("pdf", b"pdf", 0, page, 8, page, consumer=close)
    assert {k.scale for k in cache._waiting} == {8, 0.25}


def test_pdf_thumbnail_cache_has_a_memory_ceiling(qapp, monkeypatch):
    from markforge.io import pdftiles
    cache = pdftiles.TileCache()
    monkeypatch.setattr(pdftiles, "SHEET_CACHE_BYTES", 40000)
    image = QImage(100, 100, QImage.Format_ARGB32)
    for page in range(12):
        cache._sheet_arrived(pdftiles.SheetKey("pdf", page, True), image)
    assert cache._sheet_bytes <= 40000
    assert len(cache._sheets) == 1


def test_snap_only_expands_geometry_near_pointer(window, monkeypatch):
    from markforge.items.shapes import PolyItem
    frame = window.view.frame()
    for row in range(100):
        item = PolyItem("polyline")
        item.points = [QPointF(x, 0) for x in range(100)]
        frame.add_markup(item, QPointF(1000, row * 10))
    calls = []
    original = window.view.named_points_of
    monkeypatch.setattr(window.view, "named_points_of", lambda item: (calls.append(item), original(item))[1])
    window.view.named_snap_targets(frame, near=QPointF(50, 50), reach=10)
    assert calls == []


def test_whiteout_is_also_absent_from_pdf_snapshot(window, tmp_path):
    frame = import_drawing(window, tmp_path)
    window.whiteout_region(frame, QRectF(70, 60, 50, 30))
    frame = window.document.pages[0].frame
    window.take_snapshot(frame, QRectF(20, 20, 180, 160))
    item = build_item(window._clipboard[0])
    item.load_from_document(window.document)
    image = replay(item)
    assert image.pixelColor(70, 60).alpha() == 0
    assert image.pixelColor(30, 60).alpha() > 0


def test_format_painter_stays_armed_until_escape(window):
    from markforge.items.shapes import RectItem
    frame = window.view.frame()
    made = []
    for x in (100, 300, 500):
        item = RectItem()
        item.set_local_rect(QRectF(0, 0, 80, 80))
        frame.add_markup(item, QPointF(x, 200))
        made.append(item)
    made[0].style.stroke = "#0000ff"
    made[0].setSelected(True)
    window.format_painter()
    for item in made[1:]:
        point = item.mapToScene(item.local_rect().center())
        click(window.view, point.x(), point.y())
        assert item.style.stroke == "#0000ff"
        assert window.holding_a_format()
    press_key(window.view, Qt.Key_Escape)
    assert not window.holding_a_format()


def test_format_painter_stops_when_another_tool_is_chosen(window):
    from tests.test_usability import _a_rectangle
    item = _a_rectangle(window)
    item.setSelected(True)
    window.format_painter()
    window.select_tool("line")
    assert not window.holding_a_format()


def test_multiple_has_a_working_shortcut(window, monkeypatch, qapp):
    from PySide6.QtTest import QTest
    from markforge.ui import dialogs
    from tests.test_usability import _a_rectangle, _show_for_shortcut
    item = _a_rectangle(window)
    window.select_tool("select")
    item.setSelected(True)
    monkeypatch.setattr(dialogs.ArrayDialog, "exec", lambda self: dialogs.QDialog.Accepted)
    monkeypatch.setattr(dialogs.ArrayDialog, "offsets", lambda self: ("10 mm", "0", 2, True))
    _show_for_shortcut(window, qapp)
    count = len(window.view.frame().markups())
    QTest.keyClick(window.view, Qt.Key_D, Qt.ControlModifier | Qt.ShiftModifier)
    qapp.processEvents()
    assert len(window.view.frame().markups()) == count + 2


def test_wheel_scrolls_the_canvas_in_small_steps(window):
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QApplication
    from markforge.ui import preferences
    window.show()
    preferences.current().wheel_mode = "scroll"
    window.view.scroll_mode = "continuous"
    bar = window.view.verticalScrollBar()
    bar.setValue((bar.minimum() + bar.maximum()) // 2)
    before = bar.value()
    point = window.view.viewport().rect().center()
    # Ctrl scrolls when the preference has a plain wheel zooming.
    mods = Qt.ControlModifier if preferences.current().wheel_zooms() else Qt.NoModifier
    event = QWheelEvent(QPointF(point), QPointF(window.view.viewport().mapToGlobal(point)),
                        QPoint(), QPoint(0, -120), Qt.NoButton, mods, Qt.NoScrollPhase, False)
    QApplication.sendEvent(window.view.viewport(), event)
    assert bar.value() - before == 30


def test_rotated_pdf_capture_keeps_linework_and_transparency(window, tmp_path):
    frame = import_drawing(window, tmp_path, rotation=90)
    window.take_snapshot(frame, QRectF(180, 20, 100, 180))
    item = build_item(window._clipboard[0])
    item.load_from_document(window.document)
    image = replay(item)
    assert image.pixelColor(40, 60).alpha() > 0
    assert image.pixelColor(90, 10).alpha() == 0


def test_snapshot_failure_can_be_followed_by_a_fresh_capture(window, tmp_path, monkeypatch):
    frame = import_drawing(window, tmp_path)
    original = frame.picture_items
    def fail(_region):
        raise ValueError("unreadable source path")
    monkeypatch.setattr(frame, "picture_items", fail)
    window.select_tool("snapshot")
    a, b = frame.mapToScene(QPointF(20, 20)), frame.mapToScene(QPointF(200, 180))
    drag(window.view, a.x(), a.y(), b.x(), b.y())
    assert "Snapshot failed" in window.status_hint.text()
    assert window.view._draft is None
    press_key(window.view, Qt.Key_Escape)
    monkeypatch.setattr(frame, "picture_items", original)
    window.select_tool("snapshot")
    drag(window.view, a.x(), a.y(), b.x(), b.y())
    assert window._clipboard and window._clipboard[0]["source_items"]


def test_snapshot_recolour_undo_does_not_change_other_copies(window, tmp_path, monkeypatch):
    from markforge.ui import dialogs
    from markforge.io.recolour import colourise_lines
    frame = import_drawing(window, tmp_path)
    window.take_snapshot(frame, QRectF(20, 20, 180, 160))
    window.paste_items()
    window.paste_items()
    first, second = [i for i in frame.markups() if isinstance(i, SnapshotItem)]
    old_key = first.asset_key
    monkeypatch.setattr(dialogs.RecolourDialog, "exec", lambda self: dialogs.QDialog.Accepted)
    monkeypatch.setattr(dialogs.RecolourDialog, "apply_to_lines",
                        lambda self, source: colourise_lines(source, QColor("#ff0000")))
    window.recolour_snapshot(first)
    assert first.asset_key != old_key
    assert replay(first).pixelColor(60, 60).red() > 200
    assert replay(second).pixelColor(60, 60).red() < 30
    window.undo_stack.undo()
    restored = [i for i in frame.markups() if isinstance(i, SnapshotItem)]
    assert all(replay(item).pixelColor(60, 60).red() < 30 for item in restored)


def test_snapshot_includes_pdf_font_outlines_and_scan_without_paper(window, tmp_path):
    from PySide6.QtCore import QBuffer, QIODevice
    from markforge.io.recolour import swap_line_colour
    pdf = pymupdf.open()
    page = pdf.new_page(width=200, height=150)
    page.draw_rect(page.rect, fill=(.8, .9, 1), color=None)
    page.insert_text((20, 40), 'Captured text', fontsize=18)
    scan = QImage(40, 40, QImage.Format_ARGB32)
    scan.fill(Qt.white)
    painter = QPainter(scan)
    painter.fillRect(QRectF(10, 10, 20, 20), Qt.black)
    painter.end()
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    scan.save(buffer, 'PNG')
    page.insert_image(pymupdf.Rect(20, 60, 60, 100), stream=bytes(buffer.data()))
    path = tmp_path / 'text-scan.pdf'
    pdf.save(path)
    pdf.close()
    pdfio.import_pages(window.document, str(path), [0], at=0)
    window.rebuild_scenes()
    frame = window.document.pages[0].frame
    window.take_snapshot(frame, QRectF(0, 0, 180, 120))
    payload = window._clipboard[0]
    snapshot = build_item(payload)
    snapshot.load_from_document(window.document)
    image = replay(snapshot)
    assert image.pixelColor(5, 5).alpha() == 0
    assert image.pixelColor(22, 62).alpha() == 0
    assert image.pixelColor(40, 80).alpha() == 255
    assert any(image.pixelColor(x, y).alpha() > 100 for x in range(20, 150) for y in range(20, 42))
    source = snapshot.source_markups(window.document)
    assert swap_line_colour(source, QColor('black'), QColor('red')) > 0
    snapshot.redraw_from(source)
    tinted = replay(snapshot)
    assert tinted.pixelColor(40, 80) == QColor("red")
    assert tinted.pixelColor(22, 62).alpha() == 0
    assert any(tinted.pixelColor(x, y).red() > 200 and tinted.pixelColor(x, y).alpha() > 100
               for x in range(20, 150) for y in range(20, 42))
    restored = build_item(snapshot.serialize())
    restored.redraw_from(restored.source_markups(window.document))
    assert replay(restored) == tinted


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_whiteout_removes_geometry_instead_of_hiding_it(window, tmp_path, rotation):
    frame = import_drawing(window, tmp_path, rotation)
    with pymupdf.open(stream=window.document.asset(frame.page.pdf_key), filetype='pdf') as original:
        native = pymupdf.Rect(70, 65, 120, 95)
        box = native * original[0].rotation_matrix
    window.whiteout_region(frame, QRectF(box.x0, box.y0, box.width, box.height))
    page = window.document.pages[0]
    with pymupdf.open(stream=window.document.asset(page.pdf_key), filetype='pdf') as changed:
        edited = changed[0]
        pix = edited.get_pixmap()
        assert pix.pixel(int(box.x0 + box.width/2), int(box.y0 + box.height/2))[:3] == (255, 255, 255)
        # Removing all PDF clipping operations must not resurrect erased ink.
        drawings = edited.get_drawings()
        from markforge.io.pdfsnapshot import _commands, path_from
        for drawing in drawings:
            shape = path_from(_commands(drawing, edited.rotation_matrix), drawing.get('even_odd', False))
            assert not shape.contains(QPointF(box.x0 + box.width/2, box.y0 + box.height/2))
        outside = pymupdf.Point(50, 80) * edited.rotation_matrix
        assert max(pix.pixel(int(outside.x), int(outside.y))[:3]) < 30


def test_whiteout_can_clear_a_whole_page(window, tmp_path):
    frame = import_drawing(window, tmp_path)
    window.whiteout_region(frame, frame.page_rect())
    assert 'failed' not in window.status_hint.text().lower()
    page = window.document.pages[0]
    with pymupdf.open(stream=window.document.asset(page.pdf_key), filetype='pdf') as changed:
        assert not changed[0].get_drawings()


def test_escape_cancels_canvas_tool_when_toolbar_has_focus(window):
    from PySide6.QtTest import QTest
    window.select_tool('line')
    window.hatch_scale_spin.setFocus()
    QTest.keyClick(window.hatch_scale_spin, Qt.Key_Escape)
    assert window.view.tool_key == 'select'


def test_switching_tools_abandons_half_placed_callout(window):
    window.select_tool('callout')
    click(window.view, 150, 150)
    assert window.view._pending_anchor is not None
    window.select_tool('line')
    assert window.view._pending_anchor is None
    window.select_tool('callout')
    click(window.view, 240, 210)
    assert window.view._pending_anchor == QPointF(240, 210)
    press_key(window.view, Qt.Key_Escape)
    assert window.view.tool_key == 'select'


def test_whiteout_text_and_scan_survive_outside_erased_region(window, tmp_path):
    from PySide6.QtCore import QBuffer, QIODevice
    pdf = pymupdf.open()
    page = pdf.new_page(width=200, height=150)
    page.insert_text((15, 30), 'Keep', fontsize=18)
    page.insert_text((115, 30), 'Erase', fontsize=18)
    scan = QImage(160, 60, QImage.Format_RGB32)
    scan.fill(Qt.black)
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    scan.save(buffer, 'PNG')
    page.insert_image(pymupdf.Rect(20, 60, 180, 120), stream=bytes(buffer.data()))
    path = tmp_path / 'whiteout-mixed.pdf'
    pdf.save(path)
    pdf.close()
    pdfio.import_pages(window.document, str(path), [0], at=0)
    window.rebuild_scenes()
    frame = window.document.pages[0].frame
    window.whiteout_region(frame, QRectF(100, 0, 100, 150))
    assert 'failed' not in window.status_hint.text().lower()
    saved = tmp_path / 'erased-mixed.pdf'
    project.save_document(window.document, str(saved))
    with pymupdf.open(saved) as result:
        edited = result[0]
        pix = edited.get_pixmap()
        assert pix.pixel(50, 80)[:3] == (0, 0, 0)
        assert pix.pixel(140, 80)[:3] == (255, 255, 255)
        assert any(max(pix.pixel(x, y)[:3]) < 80 for x in range(15, 60) for y in range(12, 32))
        assert all(pix.pixel(x, y)[:3] == (255, 255, 255) for x in range(110, 170) for y in range(12, 32))
        assert 'Erase' not in edited.get_text()
        assert 'Keep' in edited.get_text()


def test_whiteout_does_not_flatten_source_annotations(window, tmp_path):
    pdf = pymupdf.open()
    page = pdf.new_page(width=200, height=150)
    page.draw_line((10, 20), (190, 20), color=(0, 0, 0))
    annot = page.add_rect_annot(pymupdf.Rect(30, 60, 80, 100))
    annot.set_colors(stroke=(1, 0, 0), fill=(1, 0, 0))
    annot.update()
    path = tmp_path / 'annotated-whiteout.pdf'
    pdf.save(path)
    pdf.close()
    pdfio.import_pages(window.document, str(path), [0], at=0)
    window.rebuild_scenes()
    frame = window.document.pages[0].frame
    window.whiteout_region(frame, QRectF(100, 0, 30, 40))
    data = window.document.asset(window.document.pages[0].pdf_key)
    with pymupdf.open(stream=data, filetype='pdf') as changed:
        assert list(changed[0].annots())
        pix = changed[0].get_pixmap(annots=False)
        assert pix.pixel(50, 80)[:3] == (255, 255, 255)


def test_snapshot_keeps_independent_pdf_fill_and_stroke_opacity(window, tmp_path):
    pdf = pymupdf.open()
    page = pdf.new_page(width=150, height=150)
    page.draw_rect(pymupdf.Rect(20, 20, 100, 100), color=(0, 0, 0), fill=(1, 0, 0),
                   stroke_opacity=0, fill_opacity=1)
    path = tmp_path / 'independent-alpha.pdf'
    pdf.save(path)
    pdf.close()
    pdfio.import_pages(window.document, str(path), [0], at=0)
    window.rebuild_scenes()
    frame = window.document.pages[0].frame
    window.take_snapshot(frame, QRectF(0, 0, 120, 120))
    snapshot = build_item(window._clipboard[0])
    snapshot.load_from_document(window.document)
    assert replay(snapshot).pixelColor(50, 50).alpha() == 255


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_whiteout_preserves_searchable_rotated_labels(window, tmp_path, rotation):
    pdf = pymupdf.open()
    page = pdf.new_page(width=200, height=150)
    page.insert_text((30, 120), 'Vertical', fontsize=12, rotate=90)
    page.insert_text((70, 30), 'Horizontal', fontsize=12)
    page.set_rotation(rotation)
    box = pymupdf.Rect(150, 70, 190, 140) * page.rotation_matrix
    path = tmp_path / 'searchable-whiteout.pdf'
    pdf.save(path)
    pdf.close()
    pdfio.import_pages(window.document, str(path), [0], at=0)
    window.rebuild_scenes()
    window.whiteout_region(window.document.pages[0].frame, QRectF(box.x0, box.y0, box.width, box.height))
    data = window.document.asset(window.document.pages[0].pdf_key)
    with pymupdf.open(stream=data, filetype='pdf') as edited:
        assert 'Vertical' in edited[0].get_text()
        assert 'Horizontal' in edited[0].get_text()
        vertical = edited[0].search_for('Vertical')
        assert vertical and vertical[0].x0 < 35
