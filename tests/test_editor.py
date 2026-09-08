"""Tests for the PDF4Py page and markup editor."""
from __future__ import annotations

import pathlib

import pytest

pymupdf = pytest.importorskip("pymupdf")

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent

from pdf4py.document import DocumentError, PdfDocument
from pdf4py.ui.pageview import RECTANGLE, SELECT, HandleItem, MarkupItem

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


def build_marked_up(path) -> str:
    """A page with the markups that can be edited: a callout, two rectangles
    that can be grouped, and a sticky note that resizes into nothing."""
    doc = pymupdf.open()
    page = doc.new_page(width=400, height=600)
    callout = page.add_freetext_annot(pymupdf.Rect(200, 100, 360, 160),
                                      "Check this detail", fontsize=11, border_width=1)
    doc.xref_set_key(callout.xref, "CL", "[60 480 120 520 200 500]")
    doc.xref_set_key(callout.xref, "IT", "/FreeTextCallout")
    for box in (pymupdf.Rect(50, 300, 150, 360), pymupdf.Rect(170, 300, 270, 360)):
        square = page.add_rect_annot(box)
        square.set_border(width=2)
        square.update()
    page.add_text_annot((300, 400), "a note")
    doc.save(str(path))
    doc.close()
    return str(path)


@pytest.fixture
def marked_up(tmp_path):
    return build_marked_up(tmp_path / "marked-up.pdf")


@pytest.fixture
def rich(marked_up):
    doc = PdfDocument()
    doc.open(marked_up)
    yield doc
    doc.close()


def of_kind(document, subtype: str) -> list:
    return [m for m in document.markups(0) if m.subtype == subtype]


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


# --------------------------------------------------------- editing a markup


def test_a_markup_reports_what_can_be_done_to_it(rich):
    kinds = {m.subtype: m for m in rich.markups(0)}
    assert kinds["FreeText"].editable_text and kinds["FreeText"].resizable
    assert kinds["FreeText"].text == "Check this detail"
    assert kinds["Square"].resizable and not kinds["Square"].editable_text
    # A sticky note is an icon: stretching it only stretches the icon.
    assert not kinds["Text"].resizable and kinds["Text"].editable_text


def test_a_callout_reports_its_leader_line(rich):
    callout = of_kind(rich, "FreeText")[0].callout
    # Three points in display coordinates: arrow tip, hinge, text box.
    assert len(callout) == 3
    assert callout[0] == (60.0, 120.0)      # PDF y-up 480 on a 600pt page
    assert callout[1] == (120.0, 80.0)


def test_reshaping_a_callout_moves_only_the_point_that_was_dragged(rich):
    callout = of_kind(rich, "FreeText")[0]
    tip, hinge, tail = callout.callout
    moved = (hinge[0] + 30, hinge[1] + 45)
    assert rich.set_callout(0, callout.xref, [tip, moved, tail])
    assert of_kind(rich, "FreeText")[0].callout == (tip, moved, tail)
    assert rich.modified


def test_a_callout_needs_two_or_three_points(rich):
    callout = of_kind(rich, "FreeText")[0]
    assert not rich.set_callout(0, callout.xref, [(1.0, 2.0)])
    assert not rich.set_callout(0, callout.xref, [(1.0, 2.0)] * 4)


def test_rewriting_what_a_text_box_says(rich, tmp_path):
    callout = of_kind(rich, "FreeText")[0]
    assert rich.set_text(0, callout.xref, "REVISED: see detail 4")
    assert of_kind(rich, "FreeText")[0].text == "REVISED: see detail 4"
    target = tmp_path / "retitled.pdf"
    rich.save(str(target))
    reopened = PdfDocument()
    reopened.open(str(target))
    assert of_kind(reopened, "FreeText")[0].text == "REVISED: see detail 4"
    reopened.close()


def test_a_rectangle_cannot_have_its_text_rewritten(rich):
    assert not rich.set_text(0, of_kind(rich, "Square")[0].xref, "nope")


def test_resizing_is_exact_and_stays_exact(rich):
    square = of_kind(rich, "Square")[0]
    for _ in range(4):
        # Repeated because set_rect pads by the border width, which would creep
        # the markup a point larger on every drag if it were not compensated.
        assert rich.resize_markup(0, square.xref, (60.0, 320.0, 260.0, 420.0))
        assert of_kind(rich, "Square")[0].rect == (60.0, 320.0, 260.0, 420.0)


def test_a_sticky_note_is_not_resized(rich):
    note = of_kind(rich, "Text")[0]
    assert not rich.resize_markup(0, note.xref, (10.0, 10.0, 200.0, 200.0))
    assert of_kind(rich, "Text")[0].rect == note.rect


def test_a_markup_cannot_be_resized_to_nothing(rich):
    square = of_kind(rich, "Square")[0]
    assert not rich.resize_markup(0, square.xref, (60.0, 320.0, 61.0, 321.0))


# ----------------------------------------------------------------- grouping


def test_grouping_makes_markups_move_together(rich):
    first, second = (m.xref for m in of_kind(rich, "Square"))
    assert rich.group(0, [first, second])
    assert rich.group_members(0, second) == [first, second]
    assert rich.group_members(0, first) == [first, second]
    # The group hangs off its leader, which is how PDF says it should be done.
    assert {m.xref: m.leader for m in of_kind(rich, "Square")} == {first: 0, second: first}


def test_grouping_needs_more_than_one_markup(rich):
    assert not rich.group(0, [of_kind(rich, "Square")[0].xref])


def test_ungrouping_frees_every_member(rich):
    xrefs = [m.xref for m in of_kind(rich, "Square")]
    rich.group(0, xrefs)
    assert rich.ungroup(0, xrefs[1]) == 2
    assert all(m.leader == 0 for m in rich.markups(0))
    assert rich.group_members(0, xrefs[0]) == [xrefs[0]]


def test_ungrouping_something_that_is_not_grouped(rich):
    assert rich.ungroup(0, of_kind(rich, "Square")[0].xref) == 0


def test_a_group_survives_the_save(rich, tmp_path):
    xrefs = [m.xref for m in of_kind(rich, "Square")]
    rich.group(0, xrefs)
    target = tmp_path / "grouped.pdf"
    rich.save(str(target))
    reopened = PdfDocument()
    reopened.open(str(target))
    assert len(reopened.group_members(0, of_kind(reopened, "Square")[1].xref)) == 2
    reopened.close()


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


@pytest.fixture
def rich_editor(editor_window, marked_up):
    assert editor_window.load(marked_up)
    editor_window.view.set_zoom(1.0)
    return editor_window


def select_only(window, item) -> None:
    for other in window.view.markup_items():
        other.setSelected(False)
    item.setSelected(True)


def markup_of(window, item):
    """The document's record for the markup an item is showing."""
    return next(m for m in window.document.markups(window.view.index)
                if m.xref == item.xref)


def handle(window, role: str) -> HandleItem:
    return next(one for one in window.view._handles if one.role == role)


def drag_handle(window, role: str, to: QPointF) -> None:
    view = window.view
    grip = handle(window, role)
    view.begin_handle_drag(grip)
    view.drag_handle(to)
    view.finish_handle_drag(to)


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
    editor.view.commit_moves()
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


# ------------------------------------------------------- editing on the page


def test_a_selected_markup_grows_handles(rich_editor):
    square = item_for(rich_editor, "Square")
    select_only(rich_editor, square)
    assert sorted(one.role for one in rich_editor.view._handles) == [
        "e", "n", "ne", "nw", "s", "se", "sw", "w"]

    select_only(rich_editor, item_for(rich_editor, "FreeText"))
    roles = sorted(one.role for one in rich_editor.view._handles)
    # A callout gets a grab point per bend of its leader line as well.
    assert roles[:3] == ["callout0", "callout1", "callout2"]
    assert len(roles) == 11

    select_only(rich_editor, item_for(rich_editor, "Text"))
    assert rich_editor.view._handles == []      # a sticky note has no size


def test_dragging_a_handle_resizes_the_markup(rich_editor):
    square = item_for(rich_editor, "Square")
    select_only(rich_editor, square)
    before = markup_of(rich_editor, square)
    drag_handle(rich_editor, "se", QPointF(before.x1 + 60, before.y1 + 40))
    after = markup_of(rich_editor, square)
    assert (after.x0, after.y0) == (before.x0, before.y0)     # the far corner stays
    assert (after.x1, after.y1) == (before.x1 + 60, before.y1 + 40)
    assert rich_editor.document.modified


def test_dragging_a_callout_hinge(rich_editor):
    callout = item_for(rich_editor, "FreeText")
    select_only(rich_editor, callout)
    tip, hinge, tail = markup_of(rich_editor, callout).callout
    drag_handle(rich_editor, "callout1", QPointF(hinge[0] + 30, hinge[1] + 45))
    assert markup_of(rich_editor, callout).callout == (
        tip, (hinge[0] + 30, hinge[1] + 45), tail)


def test_a_group_is_selected_and_moved_as_one(rich_editor):
    squares = [i for i in rich_editor.view.markup_items() if i.subtype == "Square"]
    for item in squares:
        item.setSelected(True)
    rich_editor.group_markups()

    squares = [i for i in rich_editor.view.markup_items() if i.subtype == "Square"]
    for one in squares:
        # Whichever member is clicked — the leader or a follower — takes the
        # whole group with it, and a group is moved rather than reshaped.
        select_only(rich_editor, one)
        assert len(rich_editor.view.selected_items()) == 2
        assert rich_editor.view._handles == []

    before = {m.xref: (m.x0, m.y0) for m in of_kind(rich_editor.document, "Square")}
    for item in rich_editor.view.selected_items():
        item.setPos(item.pos() + QPointF(20, 15))
    rich_editor.view.commit_moves()
    after = {m.xref: (m.x0, m.y0) for m in of_kind(rich_editor.document, "Square")}
    assert all(after[x] == (before[x][0] + 20, before[x][1] + 15) for x in before)


def test_ungrouping_from_the_window_gives_the_handles_back(rich_editor):
    squares = [i for i in rich_editor.view.markup_items() if i.subtype == "Square"]
    for item in squares:
        item.setSelected(True)
    rich_editor.group_markups()
    rich_editor.ungroup_markups()
    square = [i for i in rich_editor.view.markup_items() if i.subtype == "Square"][0]
    select_only(rich_editor, square)
    assert len(rich_editor.view.selected_items()) == 1
    assert len(rich_editor.view._handles) == 8


def test_group_and_ungroup_follow_the_selection(rich_editor):
    assert not rich_editor.group_action.isEnabled()
    assert not rich_editor.ungroup_action.isEnabled()
    squares = [i for i in rich_editor.view.markup_items() if i.subtype == "Square"]
    for item in squares:
        item.setSelected(True)
    assert rich_editor.group_action.isEnabled()
    rich_editor.group_markups()
    select_only(rich_editor, [i for i in rich_editor.view.markup_items()
                              if i.subtype == "Square"][0])
    assert rich_editor.ungroup_action.isEnabled()


def test_editing_text_follows_the_selection(rich_editor):
    select_only(rich_editor, item_for(rich_editor, "FreeText"))
    assert rich_editor.text_action.isEnabled()
    select_only(rich_editor, item_for(rich_editor, "Square"))
    assert not rich_editor.text_action.isEnabled()


def test_double_clicking_a_text_box_asks_for_the_editor(rich_editor):
    asked = []
    rich_editor.view.text_edit_requested.connect(asked.append)
    callout = item_for(rich_editor, "FreeText")
    callout.mouseDoubleClickEvent(
        QMouseEvent(QEvent.MouseButtonDblClick, QPointF(1, 1), QPointF(1, 1),
                    Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
    assert asked == [callout.xref]


def test_zoom_holds_the_point_under_the_cursor(rich_editor):
    view = rich_editor.view
    view.set_zoom(3.0)                      # big enough that the page can scroll
    assert view.verticalScrollBar().maximum() > 0
    cursor = QPointF(view.viewport().width() * 0.7, view.viewport().height() * 0.3)

    def page_point():
        scene = view.mapToScene(cursor.toPoint())
        return round(scene.x() / view.zoom, 1), round(scene.y() / view.zoom, 1)

    before = page_point()
    view.zoom_by(1.25, cursor)
    assert page_point() == pytest.approx(before, abs=0.5)
    view.zoom_by(1.25, cursor)
    assert page_point() == pytest.approx(before, abs=0.5)
    view.zoom_by(1 / 1.25, cursor)
    assert page_point() == pytest.approx(before, abs=0.5)
    assert view.zoom > 3.0


def test_edits_reach_the_saved_file(editor, tmp_path):
    editor.set_mode(RECTANGLE)
    drag(editor.view, QPointF(100, 400), QPointF(240, 460))
    editor.insert_page()
    editor.show_page(0)
    item = item_for(editor, "Text")
    item.setPos(item.pos() + QPointF(10, 10))
    editor.view.commit_moves()

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
