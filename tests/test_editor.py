"""Tests for the PDF4Py page and markup editor."""
from __future__ import annotations

import pathlib

import pytest

pymupdf = pytest.importorskip("pymupdf")

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent

from pdf4py.document import DocumentError, PdfDocument
from pdf4py.ui.pageview import RECTANGLE, SELECT, MarkupItem

SQUARE = (80.0, 200.0, 220.0, 280.0)


def build_pdf(path, rotation: int = 0) -> str:
    """A two page PDF with a square markup, a sticky note and a link on page 1."""
    doc = pymupdf.open()
    page = doc.new_page(width=400, height=600)
    page.insert_text((60, 80), "Sample document")
    annot = page.add_rect_annot(pymupdf.Rect(*SQUARE))
    annot.set_colors(stroke=(0, 0, 1))
    annot.set_border(width=2)
    annot.update()
    page.add_text_annot((300, 400), "a note")
    page.insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(20, 500, 120, 520),
                      "uri": "https://example.org"})
    page.set_rotation(rotation)
    doc.new_page(width=400, height=600)
    doc.save(str(path))
    doc.close()
    return str(path)


@pytest.fixture
def sample(tmp_path):
    return build_pdf(tmp_path / "sample.pdf")


@pytest.fixture
def document(sample):
    doc = PdfDocument()
    doc.open(sample)
    yield doc
    doc.close()


def square_of(doc: PdfDocument, index: int = 0):
    return next(m for m in doc.markups(index) if m.subtype == "Square")


# --------------------------------------------------------------------- opening


def test_open_reads_the_pages(document, sample):
    assert document.page_count == 2
    assert document.path == sample
    assert document.page_size(0) == (400.0, 600.0)
    assert not document.modified


def test_opening_something_that_is_not_a_pdf(tmp_path):
    broken = tmp_path / "broken.pdf"
    broken.write_text("this is not a PDF")
    with pytest.raises(DocumentError):
        PdfDocument().open(str(broken))


def test_saving_over_the_file_it_came_from(document, sample):
    document.add_rectangle(0, (10, 10, 60, 60))
    document.save()
    reopened = PdfDocument()
    reopened.open(sample)
    assert len(reopened.markups(0)) == 3


def damage(path) -> str:
    """Break the xref so MuPDF has to repair the file to open it."""
    data = bytearray(pathlib.Path(path).read_bytes())
    marker = data.rfind(b"startxref")
    end = data.find(b"\n", marker + 10)
    data[marker + 10:end] = b"999999999"
    pathlib.Path(path).write_bytes(bytes(data))
    return str(path)


def test_a_damaged_file_opens_repaired_and_quietly(sample, capfd):
    document = PdfDocument()
    document.open(damage(sample))
    out, err = capfd.readouterr()
    assert document.page_count == 2
    assert document.repaired
    assert "repair" in document.warnings
    # MuPDF's own complaints must not reach the console: a file missing a few
    # thousand objects prints a line for every one of them.
    assert err == "" and out == ""
    document.close()


def test_saving_appends_rather_than_rewriting(document, sample):
    before = pathlib.Path(sample).read_bytes()
    document.add_rectangle(0, (10, 10, 60, 60))
    assert document.save() is False        # no reload: the xrefs still stand
    after = pathlib.Path(sample).read_bytes()
    # An appended save leaves the original bytes untouched and adds to the end,
    # which is what makes saving a large document instant.
    assert after.startswith(before) and len(after) > len(before)


def test_a_repaired_file_is_rewritten_when_saved(sample, tmp_path):
    document = PdfDocument()
    document.open(damage(sample))
    document.add_rectangle(0, (10, 10, 60, 60))
    document.insert_page(1)
    assert document.save() is True         # a repaired file cannot be appended to
    document.close()

    reopened = PdfDocument()
    reopened.open(sample)
    assert reopened.page_count == 3
    assert not reopened.repaired           # the saved copy is sound
    assert len(reopened.markups(0)) == 3
    reopened.close()
    assert list(tmp_path.glob("*.pdf4py-part")) == []


def test_save_as_leaves_the_original_alone(document, sample, tmp_path):
    before = pathlib.Path(sample).read_bytes()
    document.add_rectangle(0, (10, 10, 60, 60))
    assert document.save(str(tmp_path / "copy.pdf")) is False
    assert pathlib.Path(sample).read_bytes() == before
    assert document.path == str(tmp_path / "copy.pdf")


# --------------------------------------------------------------------- markups


def test_links_and_popups_are_not_markups(document):
    subtypes = {markup.subtype for markup in document.markups(0)}
    assert subtypes == {"Square", "Text"}


def test_a_markup_is_rendered_where_the_model_says_it_is(document):
    square = square_of(document)
    raster = document.render_markup(0, square.xref, 2.0)
    assert (raster.x, raster.y) == (square.x0 * 2, square.y0 * 2)
    assert raster.alpha and raster.width and raster.height


def test_the_page_is_rendered_without_its_markups(document):
    square = square_of(document)
    page = document.render_page(0, 1.0)
    assert (page.width, page.height) == (400, 600)
    # The blue square would be the only blue on the page, so no blue means the
    # markups really were left out for the overlay to draw.
    stride, channels = page.stride, 3
    x = int(square.x0 + square.width / 2)
    blue = [page.samples[int(y) * stride + x * channels + 2]
            for y in range(int(square.y0), int(square.y1))]
    assert max(blue) == min(blue)


def test_the_overlay_is_built_in_one_walk_of_the_page(document):
    """Rendering markups one xref at a time re-walks the list for each and is
    quadratic; on a marked-up drawing sheet that is seconds per page."""
    drawn = document.markups_with_rasters(0, 1.0)
    assert [markup for markup, _ in drawn] == document.markups(0)
    assert all(raster is not None for _, raster in drawn)

    document._find = lambda *args: pytest.fail("the page was walked per markup")
    assert len(document.markups_with_rasters(0, 1.0)) == 2


def test_a_page_that_will_not_render_does_not_take_the_app_down(document, monkeypatch):
    import pymupdf

    def refuse(*args, **kwargs):
        raise RuntimeError("damaged page")

    monkeypatch.setattr(pymupdf.Page, "get_pixmap", refuse)
    assert document.render_page(0, 1.0) is None
    assert document.render_thumbnail(0) is None
    assert document.page_count == 2          # the document is still usable


def test_moving_a_markup_is_exact_and_does_not_creep(document):
    square = square_of(document)
    start = square_of(document)
    for _ in range(5):
        assert document.move_markup(0, square.xref, 10.0, -4.0)
    moved = square_of(document)
    assert (moved.x0, moved.y0) == (start.x0 + 50.0, start.y0 - 20.0)
    assert (moved.width, moved.height) == (start.width, start.height)
    assert document.modified


def test_a_move_survives_a_round_trip(document, tmp_path):
    square = square_of(document)
    document.move_markup(0, square.xref, 15.0, 25.0)
    expected = square_of(document)
    target = tmp_path / "moved.pdf"
    document.save(str(target))
    reopened = PdfDocument()
    reopened.open(str(target))
    assert square_of(reopened) == expected


def test_moving_a_markup_that_is_gone(document):
    assert not document.move_markup(0, 9999, 5.0, 5.0)


# ------------------------------------------------------------------ rectangles


def test_a_rectangle_lands_where_it_was_drawn(document):
    xref = document.add_rectangle(0, (100.0, 300.0, 240.0, 360.0))
    added = next(m for m in document.markups(0) if m.xref == xref)
    # The stored rectangle carries the border width around the drawn box.
    assert added.x0 == pytest.approx(100.0, abs=2.0)
    assert added.y0 == pytest.approx(300.0, abs=2.0)
    assert added.x1 == pytest.approx(240.0, abs=2.0)
    assert added.y1 == pytest.approx(360.0, abs=2.0)
    assert document.modified


def test_a_rectangle_is_normalised(document):
    xref = document.add_rectangle(0, (240.0, 360.0, 100.0, 300.0))
    added = next(m for m in document.markups(0) if m.xref == xref)
    assert added.x0 < added.x1 and added.y0 < added.y1


@pytest.mark.parametrize("rotation", [90, 180, 270])
def test_rotated_pages_use_the_coordinates_the_user_sees(tmp_path, rotation):
    doc = PdfDocument()
    doc.open(build_pdf(tmp_path / f"r{rotation}.pdf", rotation))
    width, height = doc.page_size(0)
    assert (width, height) == ((600.0, 400.0) if rotation in (90, 270) else (400.0, 600.0))
    xref = doc.add_rectangle(0, (100.0, 100.0, 200.0, 160.0))
    added = next(m for m in doc.markups(0) if m.xref == xref)
    assert added.x0 == pytest.approx(100.0, abs=2.0)
    assert added.y0 == pytest.approx(100.0, abs=2.0)
    doc.move_markup(0, xref, 20.0, 30.0)
    shifted = next(m for m in doc.markups(0) if m.xref == xref)
    assert (shifted.x0, shifted.y0) == (added.x0 + 20.0, added.y0 + 30.0)
    doc.close()


# ----------------------------------------------------------------------- pages


def test_inserting_a_blank_page(document):
    document.insert_page(1)
    assert document.page_count == 3
    assert document.page_size(1) == (400.0, 600.0)
    assert document.markups(1) == []
    assert document.modified


def test_deleting_a_page(document):
    document.delete_page(1)
    assert document.page_count == 1
    assert document.markups(0)          # page 1, with its markups, is the one left
    assert document.modified


def test_the_last_page_cannot_be_deleted(document):
    document.delete_page(1)
    with pytest.raises(DocumentError):
        document.delete_page(0)
    assert document.page_count == 1


# -------------------------------------------------------------------- the app


@pytest.fixture
def editor(editor_window, sample):
    assert editor_window.load(sample)
    editor_window.view.set_zoom(1.0)   # 1:1 keeps scene points and PDF points equal
    return editor_window


def markup_items(window) -> list[MarkupItem]:
    return [item for item in window.view.scene().items() if isinstance(item, MarkupItem)]


def item_for(window, subtype: str) -> MarkupItem:
    return next(item for item in markup_items(window) if item.subtype == subtype)


def drag(view, start: QPointF, end: QPointF) -> None:
    """Press, move and release on the view, in scene coordinates."""
    def event(kind, scene_point, button, buttons):
        local = QPointF(view.mapFromScene(scene_point))
        return QMouseEvent(kind, local, local, button, buttons, Qt.NoModifier)

    view.mousePressEvent(event(QEvent.MouseButtonPress, start, Qt.LeftButton, Qt.LeftButton))
    view.mouseMoveEvent(event(QEvent.MouseMove, end, Qt.NoButton, Qt.LeftButton))
    view.mouseReleaseEvent(event(QEvent.MouseButtonRelease, end, Qt.LeftButton, Qt.NoButton))


def test_the_strip_does_not_draw_every_page_up_front(qapp, tmp_path):
    """A two hundred page drawing set costs a second a sheet to draw, so the
    strip must fill in as you scroll rather than block the window."""
    from pdf4py.ui.mainwindow import MainWindow

    many = pymupdf.open()
    for _ in range(60):
        many.new_page(width=595, height=842)
    path = tmp_path / "many-pages.pdf"
    many.save(str(path))
    many.close()

    window = MainWindow()
    window.confirm_discard = lambda: True
    assert window.load(str(path))
    assert window.pages.count() == 60
    assert len(window.pages._drawn) == 0      # nothing drawn until it is on screen
    window.document.close()
    window.close()
    window.deleteLater()


def test_page_changes_only_touch_the_row_that_changed(editor):
    editor.pages._drawn = {0, 1}
    editor.insert_page()
    assert editor.pages.count() == 3
    assert [editor.pages.item(row).text() for row in range(3)] == ["1", "2", "3"]
    assert editor.pages._drawn == {0, 2}      # the old page 2 kept its thumbnail
    editor.pages.setCurrentRow(1)
    editor.delete_page()
    assert [editor.pages.item(row).text() for row in range(2)] == ["1", "2"]
    assert editor.pages._drawn == {0, 1}


def test_the_window_shows_the_document(editor):
    assert editor.pages.count() == 2
    assert editor.view.index == 0
    assert {item.subtype for item in markup_items(editor)} == {"Square", "Text"}
    assert "sample.pdf" in editor.windowTitle()


def test_choosing_a_page_changes_the_canvas(editor):
    editor.pages.setCurrentRow(1)
    assert editor.view.index == 1
    assert markup_items(editor) == []


def test_the_rectangle_tool_draws_into_the_document(editor):
    editor.set_mode(RECTANGLE)
    drag(editor.view, QPointF(100, 400), QPointF(240, 460))
    added = [m for m in editor.document.markups(0) if m.subtype == "Square"]
    assert len(added) == 2
    drawn = max(added, key=lambda m: m.y0)
    assert drawn.x0 == pytest.approx(100.0, abs=2.0)
    assert drawn.y1 == pytest.approx(460.0, abs=2.0)
    assert editor.windowTitle().startswith("sample.pdf*")


def test_a_click_without_a_drag_draws_nothing(editor):
    editor.set_mode(RECTANGLE)
    drag(editor.view, QPointF(100, 400), QPointF(101, 401))
    assert len(editor.document.markups(0)) == 2
    assert not editor.document.modified


def test_the_rectangle_tool_leaves_markups_alone(editor):
    editor.set_mode(RECTANGLE)
    assert all(not item.flags() & MarkupItem.ItemIsMovable for item in markup_items(editor))
    editor.set_mode(SELECT)
    assert all(item.flags() & MarkupItem.ItemIsMovable for item in markup_items(editor))


def test_dragging_a_markup_moves_it_in_the_document(editor):
    editor.set_mode(SELECT)
    item = item_for(editor, "Square")
    before = square_of(editor.document)
    item.setPos(item.pos() + QPointF(30, -25))
    editor.view.commit_move(item, QPointF(30, -25))
    after = square_of(editor.document)
    assert (after.x0, after.y0) == (before.x0 + 30.0, before.y0 - 25.0)
    assert item.home == item.pos()      # the drag is now the item's resting place


def test_a_markup_cannot_be_dragged_off_the_page(editor):
    item = item_for(editor, "Square")
    item.setPos(QPointF(-400, -400))
    assert item.pos() == QPointF(0, 0)
    width, height = editor.document.page_size(0)
    item.setPos(QPointF(width + 400, height + 400))
    assert item.pos().x() == pytest.approx(width - item.boundingRect().width())
    assert item.pos().y() == pytest.approx(height - item.boundingRect().height())


def test_inserting_a_page_from_the_window(editor):
    editor.insert_page()
    assert editor.document.page_count == 3
    assert editor.pages.count() == 3
    assert editor.view.index == 1
    assert editor.pages.currentRow() == 1


def test_deleting_a_page_from_the_window(editor):
    editor.pages.setCurrentRow(1)
    editor.delete_page()
    assert editor.document.page_count == 1
    assert editor.pages.count() == 1
    assert editor.view.index == 0
    assert editor.delete_action.isEnabled() is False


def test_edits_reach_the_saved_file(editor, tmp_path):
    editor.set_mode(RECTANGLE)
    drag(editor.view, QPointF(100, 400), QPointF(240, 460))
    editor.insert_page()
    editor.show_page(0)
    item = item_for(editor, "Text")
    item.setPos(item.pos() + QPointF(10, 10))
    editor.view.commit_move(item, QPointF(10, 10))

    target = tmp_path / "edited.pdf"
    editor.document.save(str(target))
    editor.update_title()
    assert not editor.document.modified
    assert "*" not in editor.windowTitle()

    reopened = PdfDocument()
    reopened.open(str(target))
    assert reopened.page_count == 3
    assert len(reopened.markups(0)) == 3
    reopened.close()
