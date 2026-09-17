"""Regressions for the September 17 interactive review."""
import pymupdf
import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDoubleSpinBox, QSlider, QSpinBox

from markforge.items.shapes import PolyItem, RectItem
from markforge.items.base import build_item
from markforge.items.snapshot import SnapshotItem
from markforge.items.contents import ContentsItem
from markforge.items.measure import CountItem
from markforge.items.shapes import SketchItem
from markforge.items.text import FlagItem, StampItem
from markforge.ui.stylecaps import DASH, FONT, HATCH, OPACITY, capabilities
from markforge.io import export, project
from tests.test_usability import click, hover, drag, press_key, type_text


def test_pdf_content_snaps_without_vector_import(window, tmp_path):
    source = pymupdf.open()
    page = source.new_page(width=400, height=300)
    page.draw_line((40, 80), (180, 80))
    path = tmp_path / "snap.pdf"
    source.save(path)
    source.close()
    window.open_path(str(path))
    window.rebuild_scenes()
    window.view.set_zoom(1)
    window.document.settings.snap_to_content = True
    window.document.settings.snap_to_items = False
    window.select_tool("line")
    frame = window.view.frame()
    point = frame.mapToScene(QPointF(42, 82))
    hover(window.view, point.x(), point.y())
    assert window.view._snap_marker == frame.mapToScene(QPointF(40, 80))
    assert not frame.markups(), "snap geometry must not become document markups"
    first = frame.pdf_snap_items()
    assert frame.pdf_snap_items() is first


def test_second_point_does_not_snap_to_previous_draft_endpoint(window):
    window.select_tool("line")
    click(window.view, 100, 100)
    hover(window.view, 200, 160)
    hover(window.view, 204, 164)
    draft = window.view._draft
    assert draft is not None
    assert draft.mapToScene(draft.points[-1]) == QPointF(204, 164)
    press_key(window.view, Qt.Key_Escape)
    assert window.view._draft is None


def test_curve_bounds_include_live_bow(window):
    item = PolyItem("polygon", [QPointF(0, 0), QPointF(150, 0), QPointF(150, 100)])
    window.view.frame().add_markup(item, QPointF(100, 150))
    item.curve_segment(0, -150, 0.5)
    assert item.boundingRect().contains(item.build_path().boundingRect())
    item.setSelected(True)
    point = item.mapToScene(item.handle_points()["c0"])
    drag(window.view, point.x(), point.y(), point.x(), point.y() - 30)
    assert item.boundingRect().contains(item.build_path().boundingRect())


def test_snapshot_saved_outline_default_is_used(window):
    default = SnapshotItem()
    default.style.stroke = "#ff0000"
    default.style.width = 3
    window.set_as_default(default)
    frame = window.view.frame()
    frame.add_markup(RectItem(rect=QRectF(0, 0, 80, 60)), QPointF(50, 50))
    window.take_snapshot(frame, QRectF(40, 40, 100, 100))
    result = build_item(window._clipboard[0])
    assert result.style.stroke == "#ff0000"
    assert result.style.width == 3


def test_opacity_has_keyboard_and_step_buttons(window):
    item = RectItem()
    window.view.frame().add_markup(item, QPointF(100, 100))
    item.setSelected(True)
    window.refresh_selection()
    assert not window.properties_panel.findChildren(QSlider)
    controls = [spin for spin in window.properties_panel.findChildren(QSpinBox)
                if spin.suffix().strip() == "%"]
    assert controls
    spin = controls[0]
    before = spin.value()
    QTest.keyClick(spin, Qt.Key_Down)
    assert spin.value() == before - 1
    assert item.style.opacity == pytest.approx((before - 1) / 100)


def test_count_properties_expose_number_and_text_style(window):
    count = CountItem()
    window.view.frame().add_markup(count, QPointF(100, 100))
    count.setSelected(True)
    window.refresh_selection()
    assert FONT in capabilities(count)
    number = window.properties_panel.findChild(QSpinBox, "countNumber")
    size = window.properties_panel.findChild(QDoubleSpinBox, "countTextSize")
    assert number is not None and size is not None
    assert any(action.isVisible() for action in window._style_widgets[FONT]
               if action.defaultWidget() is window.font_spin)
    assert any(action.isVisible() for action in window._style_widgets[FONT]
               if action.defaultWidget() is window.font_family_combo)
    number.setValue(8)
    size.setValue(11)
    assert count.index == 8
    assert count.style.font_size == 11


def test_imported_drawing_offers_only_effective_opacity(window):
    drawing = SketchItem()
    assert capabilities(drawing) == {OPACITY}


def test_stamp_text_and_corners_are_editable_but_flag_has_no_false_dash(window):
    stamp = StampItem()
    assert FONT in capabilities(stamp)
    window.view.frame().add_markup(stamp, QPointF(100, 100))
    stamp.setSelected(True)
    window.refresh_selection()
    corners = window.properties_panel.findChild(QDoubleSpinBox, "stampCornerRadius")
    assert corners is not None
    corners.setValue(12)
    assert stamp.style.corner_radius == 12
    assert DASH not in capabilities(FlagItem())
    assert HATCH not in capabilities(FlagItem())


def test_sync_choice_propagates_and_zoom_preserves_source_anchor(window, qapp):
    other = window.open_same_document_window()
    other.confirm_discard = lambda: True
    try:
        window.show()
        qapp.processEvents()
        window.window_sync.setCurrentIndex(2)
        assert other.window_sync.currentIndex() == 2
        at = window.view.viewport().rect().center()
        before = window.view.mapToScene(at)
        window.view.set_zoom(2, at=at)
        assert other.view.zoom() == 2
        assert (window.view.mapToScene(at) - before).manhattanLength() < 2
        other.window_sync.setCurrentIndex(0)
        assert window.window_sync.currentIndex() == 0
    finally:
        other.document.modified = False
        other.close()


def test_export_does_not_paint_opaque_paper(window, tmp_path):
    window.document.settings.show_grid = False
    page = window.document.pages[0]
    page.grid = False
    path = tmp_path / "transparent.pdf"
    export.export_pdf(window.document, str(path))
    with pymupdf.open(path) as pdf:
        pix = pdf[0].get_pixmap(alpha=True, annots=False)
        assert pix.pixel(20, 20)[-1] == 0


def test_contents_links_survive_save_and_export_without_prior_paint(window, tmp_path):
    window.document.add_bookmark("Drawing", 0, 90)
    contents = ContentsItem(QRectF(0, 0, 300, 180))
    window.view.frame().add_markup(contents, QPointF(20, 20))
    for writer in (project.save_document, export.export_pdf):
        path = tmp_path / ("saved.pdf" if writer is project.save_document else "exported.pdf")
        writer(window.document, str(path))
        with pymupdf.open(path) as pdf:
            assert pdf[0].get_links(), "contents rows should be clickable in any PDF viewer"
            assert pdf.get_toc()[0][1] == "Drawing"


def test_add_pages_accepts_count_and_paper_size_in_one_undo(window, monkeypatch):
    from markforge.ui import dialogs
    window.interactive_prompts = True
    def choose(dialog):
        dialog.count.setValue(3)
        dialog.paper.setCurrentText("A3")
        dialog.orientation.setCurrentText("landscape")
        return dialogs.QDialog.Accepted
    monkeypatch.setattr(dialogs.NewPagesDialog, "exec", choose)
    before = len(window.document.pages)
    window.add_page()
    assert len(window.document.pages) == before + 3
    assert all(page.setup.size_name == "A3" and page.setup.orientation == "landscape"
               for page in window.document.pages[1:])
    window.undo_stack.undo()
    assert len(window.document.pages) == before


def test_break_controls_persist(window):
    item = PolyItem("line", [QPointF(0, 0), QPointF(200, 0)])
    item.break_segment(0)
    item.set_break_settings(0, 12, 0.7)
    restored = build_item(item.serialize())
    assert restored.break_settings(0) == (12, 0.7)
    assert "b0" in restored.handle_points() and "z0" in restored.handle_points()
    window.view.frame().add_markup(item, QPointF(100, 100))
    item.setSelected(True)
    window.refresh_selection()
    from PySide6.QtWidgets import QDoubleSpinBox
    assert window.properties_panel.findChild(QDoubleSpinBox, "breakSize0") is not None


def test_window_fits_standard_display_and_capture(window, qapp):
    window.show()
    window.select_tool("arrow")
    qapp.processEvents()
    assert window.minimumSizeHint().width() <= 1280
    import os
    folder = os.environ.get("MARKFORGE_REVIEW_IMAGES")
    if folder:
        os.makedirs(folder, exist_ok=True)
        window.grab().save(os.path.join(folder, "arrow-toolbar.png"))
    window.select_tool("rect")
    drag(window.view, 80, 80, 200, 160)
    window.select_tool("select")
    click(window.view, 140, 120)
    qapp.processEvents()
    from PySide6.QtWidgets import QGroupBox
    groups = window.properties_panel.findChildren(QGroupBox)
    assert all(group.height() >= group.sizeHint().height() - 2 for group in groups), [
        (group.title(), group.height(), group.sizeHint().height(), group.y()) for group in groups]
    ordered = sorted(groups, key=lambda group: group.y())
    assert all(right.y() >= left.y() + left.height() for left, right in zip(ordered, ordered[1:])), [
        (group.title(), group.y(), group.height()) for group in ordered]
    if folder:
        window.grab().save(os.path.join(folder, "rectangle-properties.png"))
    press_key(window.view, Qt.Key_Escape)
    window.select_tool("text")
    drag(window.view, 230, 110, 410, 180)
    type_text(window.view, "Beam revision")
    window.view.end_item_edit()
    window.select_tool("select")
    click(window.view, 270, 130)
    qapp.processEvents()
    assert window.minimumSizeHint().width() <= 1920
    if folder:
        window.grab().save(os.path.join(folder, "text-properties.png"))
    press_key(window.view, Qt.Key_Escape)
