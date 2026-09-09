"""The PDF engine: MuPDF, and the things MarkForge asks it for.

What is tested here is the layer everything else stands on — opening a file,
measuring and drawing its pages, reading its objects and its line work, and
putting annotations, attachments, bookmarks and links back into it.

Two things it deliberately does *not* do. It does not test MuPDF: that a flate
stream decompresses is MuPDF's business and is not going to regress here. And
where it checks what was written, it reads it back with a different library —
pypdf — because a writer that only its own reader agrees with is not a writer.
"""
import glob
import os

import pymupdf
import pytest

from markforge.io import pdfvector
from markforge.pdf import engine
from markforge.pdf.engine import PdfError
from markforge.pdf.objects import Name, Ref

CORPUS = sorted(
    glob.glob("/home/user/stirling-tools/stirling-pdf/testing/**/*.pdf",
              recursive=True))


def a_drawing(width=400.0, height=800.0, rotation=0) -> bytes:
    """A small PDF with line work, an annotation and a page size we know."""
    document = pymupdf.open()
    page = document.new_page(width=width, height=height)
    shape = page.new_shape()
    shape.draw_line(pymupdf.Point(10, 10), pymupdf.Point(110, 60))
    shape.draw_rect(pymupdf.Rect(20, 100, 220, 300))
    shape.finish(color=(1, 0, 0), width=2)
    shape.commit()
    mark = page.add_rect_annot(pymupdf.Rect(30, 400, 230, 500))
    mark.set_colors(stroke=(0, 0, 1))
    mark.set_info(title="Sam", content="have a look", subject="RFI 12")
    mark.update()
    if rotation:
        page.set_rotation(rotation)
    return document.tobytes()


# ---------------------------------------------------------------------------
# Opening
# ---------------------------------------------------------------------------

def test_a_file_that_is_not_a_pdf_is_refused():
    with pytest.raises(PdfError):
        engine.open_bytes(b"<!DOCTYPE html>\n<html>not a drawing</html>")


def test_a_file_with_a_broken_cross_reference_is_still_opened():
    """A damaged drawing that opens is worth more than a correct refusal."""
    body = (b"%PDF-1.4\n"
            b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] >>\n"
            b"endobj\n"
            b"startxref\n999999\n%%EOF\n")          # an offset that goes nowhere
    document = engine.open_bytes(body)
    try:
        assert document.page_count == 1
        assert engine.page_size(document, 0) == (595.0, 842.0)
    finally:
        engine.close(document)


def test_what_mupdf_complains_about_is_kept_rather_than_printed():
    """A repaired file has something to say, and it is worth saying once."""
    engine.drain_messages()
    engine.close(engine.open_bytes(
        b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 10 10] >>\nendobj\n"
        b"startxref\n999999\n%%EOF\n"))
    assert isinstance(engine.drain_messages(), str)


# ---------------------------------------------------------------------------
# Pages, measured as they are drawn
# ---------------------------------------------------------------------------

def test_a_page_measures_the_way_it_is_drawn():
    """A page that says it is turned is the landscape sheet it is drawn as.

    This is the whole reason coordinates are display points. A reader that
    hands back the stored box measures an A1 sheet as a portrait one and puts
    every markup on it a quarter turn out.
    """
    for rotation, expected in ((0, (400.0, 800.0)), (90, (800.0, 400.0)),
                               (180, (400.0, 800.0)), (270, (800.0, 400.0))):
        document = engine.open_bytes(a_drawing(rotation=rotation))
        try:
            assert engine.page_size(document, 0) == expected
            assert engine.page_rotation(document, 0) == rotation
        finally:
            engine.close(document)


def test_a_missing_page_measures_as_paper_rather_than_raising():
    document = engine.open_bytes(a_drawing())
    try:
        assert engine.page_size(document, 99) == engine.A4_POINTS
    finally:
        engine.close(document)


def test_display_and_file_coordinates_are_each_other_s_way_back():
    """The transforms have to compose to nothing, or markups drift on a save."""
    for rotation in (0, 90, 180, 270):
        document = engine.open_bytes(a_drawing(rotation=rotation))
        try:
            page = document[0]
            for x, y in ((0.0, 0.0), (100.0, 250.0), (399.0, 799.0)):
                if x > page.rect.width or y > page.rect.height:
                    continue
                back = engine.display_point(page, *engine.pdf_point(page, x, y))
                assert abs(back[0] - x) < 0.01 and abs(back[1] - y) < 0.01
        finally:
            engine.close(document)


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

def test_a_page_draws_at_the_size_it_was_asked_for():
    document = engine.open_bytes(a_drawing())
    try:
        raster = engine.render_page(document, 0, 200, 400)
        assert raster is not None
        assert (raster.width, raster.height) == (200, 400)
        assert len(raster.samples) >= raster.stride * raster.height
    finally:
        engine.close(document)


def test_only_the_part_asked_for_is_drawn():
    """What makes a big sheet readable: the cost is the piece, not the page."""
    document = engine.open_bytes(a_drawing())
    try:
        piece = engine.render_region(document, 0, (0.0, 0.0, 100.0, 100.0), 2.0)
        assert piece is not None
        assert (piece.width, piece.height) == (200, 200)
        whole = engine.render_page(document, 0, 800, 1600)
        assert whole is not None
        assert len(piece.samples) < len(whole.samples) / 4
    finally:
        engine.close(document)


def test_a_region_off_the_page_draws_nothing_rather_than_failing():
    document = engine.open_bytes(a_drawing())
    try:
        assert engine.render_region(
            document, 0, (5000.0, 5000.0, 5100.0, 5100.0), 1.0) is None
    finally:
        engine.close(document)


# ---------------------------------------------------------------------------
# Reading objects
# ---------------------------------------------------------------------------

def test_an_object_reads_back_as_the_values_it_is_written_in():
    document = pymupdf.open()
    page = document.new_page(width=400, height=800)
    number = engine.add_object(document, {
        "Type": Name("Annot"), "Subtype": Name("Square"),
        "Rect": [1, 2.5, 3, 4], "P": Ref(page.xref), "Open": True,
        "T": "a (name)", "BE": {"S": Name("C"), "I": 2},
    })
    found = engine.object_at(document, number)
    assert found["Type"] == Name("Annot")
    assert isinstance(found["Type"], Name)
    assert found["Rect"] == [1, 2.5, 3, 4]
    assert found["P"] == Ref(page.xref)
    assert found["Open"] is True
    assert found["T"] == "a (name)"
    assert found["BE"] == {"S": Name("C"), "I": 2}
    engine.close(document)


def test_the_annotations_of_a_page_come_back_in_the_order_they_are_drawn_in():
    """Order is what decides which markup is on top of which."""
    document = engine.open_bytes(a_drawing())
    try:
        page = document[0]
        first = list(page.annots())[0].xref
        second = engine.add_object(document, {
            "Type": Name("Annot"), "Subtype": Name("Square"),
            "Rect": [0, 0, 10, 10]})
        engine.set_page_annotations(document, 0, [second, first])
        assert engine.annotation_xrefs(document, 0) == [second, first]
        engine.set_page_annotations(document, 0, [first, second])
        assert engine.annotation_xrefs(document, 0) == [first, second]
    finally:
        engine.close(document)


def test_a_page_can_be_left_with_no_annotations_at_all():
    document = engine.open_bytes(a_drawing())
    try:
        assert engine.annotation_xrefs(document, 0)
        engine.set_page_annotations(document, 0, [])
        assert engine.annotation_xrefs(document, 0) == []
    finally:
        engine.close(document)


# ---------------------------------------------------------------------------
# Writing objects
# ---------------------------------------------------------------------------

def test_an_object_is_written_the_way_a_pdf_writes_one():
    written = engine.serialize({"Type": Name("Annot"), "Rect": [1, 2.5],
                                "P": Ref(7), "T": "a (name)"})
    assert b"/Type /Annot" in written or b"/Type/Annot" in written
    assert b"[1 2.5]" in written
    assert b"7 0 R" in written
    assert rb"(a \(name\))" in written


def test_a_number_is_written_without_an_exponent():
    """``1e-05`` is not a PDF number, and a reader that meets one stops."""
    assert b"e" not in engine.serialize(0.00001)
    assert b"e" not in engine.serialize(1234567.0)
    assert engine.serialize(3.0) == b"3"


def test_a_name_with_a_space_in_it_is_escaped():
    assert engine.serialize(Name("A name")) == b"/A#20name"


def test_text_beyond_latin_1_goes_out_as_utf_16():
    """A markup written in another language has to survive the round trip.

    It comes back as the bytes a PDF text string is — the mark on the front
    and two bytes to the letter — because only the reader knows which strings
    are words. Turning those into words is
    :func:`markforge.io.pdfmarkups._readable`, and this checks the pair of them
    end to end.
    """
    from markforge.io.pdfmarkups import _readable

    said = "dwg — Ø12 café"
    assert engine.serialize(said).startswith(b"<feff")
    document = pymupdf.open()
    try:
        number = engine.add_object(document, {"Contents": said})
        assert _readable(engine.object_at(document, number)["Contents"]) == said
    finally:
        engine.close(document)


def test_something_that_is_not_a_pdf_object_is_refused():
    with pytest.raises(PdfError):
        engine.serialize(object())


# ---------------------------------------------------------------------------
# Adding to somebody else's file
# ---------------------------------------------------------------------------

def test_adding_a_markup_leaves_every_original_byte_alone(tmp_path):
    """An incremental update is the only honest way to add to somebody's file."""
    path = str(tmp_path / "drawing.pdf")
    original = a_drawing()
    open(path, "wb").write(original)

    document = engine.open_path(path)
    try:
        number = engine.add_object(document, {
            "Type": Name("Annot"), "Subtype": Name("Square"),
            "Rect": [72.0, 500.0, 300.0, 620.0], "F": 4,
            "T": "MarkForge", "Contents": "a cloud",
            "BE": {"S": Name("C"), "I": 2.0}})
        engine.set_page_annotations(
            document, 0, engine.annotation_xrefs(document, 0) + [number])
        assert engine.save_incremental(document, path)
    finally:
        engine.close(document)

    written = open(path, "rb").read()
    assert written[:len(original)] == original, \
        "the drawing that came in is untouched"
    assert len(written) - len(original) < 4000, "and what was added is small"


def test_what_we_write_is_readable_by_another_library(tmp_path):
    """A writer only its own reader agrees with is not a writer."""
    from pypdf import PdfReader

    path = str(tmp_path / "drawing.pdf")
    open(path, "wb").write(a_drawing())
    document = engine.open_path(path)
    try:
        number = engine.add_object(document, {
            "Type": Name("Annot"), "Subtype": Name("Square"),
            "Rect": [72.0, 500.0, 300.0, 620.0], "F": 4,
            "BE": {"S": Name("C"), "I": 2.0}})
        engine.set_page_annotations(
            document, 0, engine.annotation_xrefs(document, 0) + [number])
        engine.save_incremental(document, path)
    finally:
        engine.close(document)

    theirs = PdfReader(path)
    mark = theirs.pages[0]["/Annots"][-1].get_object()
    assert str(mark["/Subtype"]) == "/Square"
    assert str(mark["/BE"]["/S"]) == "/C"


def test_saving_over_a_file_lets_go_of_it_first(tmp_path):
    """Nothing may still hold a file when it is replaced.

    Most of these saves are over the very file the document was read from — an
    export having its markups added, an outline written onto a finished PDF.
    Windows refuses to rename over a file anything still has open: the save
    fails with a permission error and what is left beside the drawing is a
    ``.markforge-part`` file nobody asked for. Unix allows it and hides the
    whole thing, so the only way to keep it fixed is to check here.
    """
    path = str(tmp_path / "drawing.pdf")
    open(path, "wb").write(a_drawing())

    document = engine.open_path(path)
    other = engine.open_path(path)
    engine.save_as(document, path, also=(other,))
    assert document.is_closed, "the document written must be let go of"
    assert other.is_closed, "and so must anything else holding the file"
    assert not os.path.exists(path + ".markforge-part"), \
        "and nothing may be left lying beside it"
    engine.close(engine.open_path(path))               # still a readable PDF


def test_an_appearance_is_lifted_out_of_the_file_it_was_drawn_in(tmp_path):
    """A markup drawn on a scratch page becomes the form its annotation shows."""
    scratch = pymupdf.open()
    page = scratch.new_page(width=100, height=60)
    shape = page.new_shape()
    shape.draw_line(pymupdf.Point(5, 5), pymupdf.Point(95, 55))
    shape.finish(color=(0, 0, 1), width=3)
    shape.commit()
    scratch = engine.open_bytes(scratch.tobytes())

    target = engine.open_bytes(a_drawing())
    try:
        pages_before = target.page_count
        form = engine.form_from_page(target, scratch, 0, 100.0, 60.0)
        assert form is not None
        assert target.page_count == pages_before, \
            "the page it was carried in on is not left behind"
        number = engine.add_object(target, {
            "Type": Name("Annot"), "Subtype": Name("Square"),
            "Rect": [50.0, 50.0, 150.0, 110.0], "F": 4,
            "AP": {"N": Ref(form)}})
        engine.set_page_annotations(target, 0, [number])
        settled = engine.open_bytes(engine.to_bytes(target))
        try:
            # Writing the file whole renumbers its objects, so the annotation
            # is asked for by where it is rather than by what it was called.
            written = engine.annotation_xrefs(settled, 0)
            assert len(written) == 1
            assert engine.draws_something(settled, 0, written[0]), \
                "an appearance that draws nothing is a markup nobody can see"
        finally:
            engine.close(settled)
    finally:
        engine.close(target)
        engine.close(scratch)


# ---------------------------------------------------------------------------
# The record that rides along
# ---------------------------------------------------------------------------

def test_an_attachment_goes_in_and_comes_back_out():
    document = engine.open_bytes(a_drawing())
    try:
        engine.embed(document, "markups.json.zip", b"the record")
        settled = engine.open_bytes(engine.to_bytes(document))
        try:
            assert engine.embedded(settled, "markups.json.zip") == b"the record"
            assert engine.embedded(settled, "nothing.zip") is None
        finally:
            engine.close(settled)
    finally:
        engine.close(document)


def test_attaching_twice_leaves_one_record_and_it_is_the_new_one():
    """Two records would make reading one back a coin toss."""
    document = engine.open_bytes(a_drawing())
    try:
        engine.embed(document, "markups.json.zip", b"the first")
        engine.embed(document, "markups.json.zip", b"the second")
        settled = engine.open_bytes(engine.to_bytes(document))
        try:
            assert settled.embfile_names().count("markups.json.zip") == 1
            assert engine.embedded(settled, "markups.json.zip") == b"the second"
        finally:
            engine.close(settled)
    finally:
        engine.close(document)


# ---------------------------------------------------------------------------
# Line work
# ---------------------------------------------------------------------------

def test_the_line_work_of_a_page_is_read_as_geometry(tmp_path):
    path = str(tmp_path / "drawing.pdf")
    open(path, "wb").write(a_drawing())
    with pdfvector.PdfFile.open(path) as source:
        strokes = pdfvector.strokes_of_page(source, 0)
    assert strokes, "a drawing with lines on it should give lines back"
    assert any(stroke["stroke"] == "#ff0000" for stroke in strokes)
    assert all(stroke["width"] > 0 for stroke in strokes)
    points = [step[1:] for stroke in strokes for step in stroke["path"]
              if step[0] in ("m", "l")]
    assert [10.0, 10.0] in [list(p) for p in points]


def test_somebody_else_s_markups_are_not_read_as_the_page_s_own_lines(tmp_path):
    """A cloud read as sixty loose segments is not a cloud.

    MuPDF runs a page the way a renderer does, and a renderer draws the
    annotations too — so the line work has to be read with them off. Otherwise
    every markup on the sheet arrives twice: once as itself and once as a
    handful of locked segments underneath it.
    """
    path = str(tmp_path / "marked.pdf")
    document = pymupdf.open()
    page = document.new_page(width=400, height=800)
    shape = page.new_shape()
    shape.draw_line(pymupdf.Point(10, 10), pymupdf.Point(110, 60))
    shape.finish(color=(0, 1, 0), width=1)                # the building
    shape.commit()
    mark = page.add_rect_annot(pymupdf.Rect(200, 200, 300, 300))
    mark.set_colors(stroke=(1, 0, 0))                     # somebody's markup
    mark.update()
    document.save(path)

    with pdfvector.PdfFile.open(path) as source:
        strokes = pdfvector.strokes_of_page(source, 0)
        assert [stroke["stroke"] for stroke in strokes] == ["#00ff00"], \
            "the page's own lines, and not the markup drawn over them"
        # The markup is still there to be read — as a markup.
        assert len(source.annotations_of(0)) == 1


def test_what_an_annotation_draws_is_read_where_it_draws_it(tmp_path):
    """For a stamp nobody else has a name for, the appearance is the markup."""
    path = str(tmp_path / "stamped.pdf")
    document = pymupdf.open()
    page = document.new_page(width=400, height=800)
    mark = page.add_rect_annot(pymupdf.Rect(200, 200, 300, 300))
    mark.set_colors(stroke=(1, 0, 0))
    mark.update()
    document.save(path)

    with pdfvector.PdfFile.open(path) as source:
        annotation = source.annotations_of(0)[0]
        strokes = pdfvector.strokes_of_annotation(source, annotation)
    assert strokes, "an appearance that draws something should read as something"
    points = [tuple(step[1:]) for stroke in strokes for step in stroke["path"]
              if step[0] in ("m", "l")]
    assert all(195 <= x <= 305 and 195 <= y <= 305 for x, y in points), \
        "and it should land on the rectangle the annotation occupies"


def test_line_work_turns_with_a_page_that_is_turned(tmp_path):
    """Geometry read off a rotated page has to land where the page is drawn."""
    path = str(tmp_path / "turned.pdf")
    open(path, "wb").write(a_drawing(rotation=90))
    with pdfvector.PdfFile.open(path) as source:
        width, height = source.page_size(0)
        strokes = pdfvector.strokes_of_page(source, 0)
    assert (width, height) == (800.0, 400.0)
    points = [step[1:] for stroke in strokes for step in stroke["path"]
              if step[0] in ("m", "l")]
    assert points, "a turned page still has its lines"
    assert all(-1 <= x <= width + 1 and -1 <= y <= height + 1
               for x, y in points), "and every one of them is on the sheet"
    assert [10.0, 10.0] not in [list(p) for p in points], \
        "the corner point cannot still be where the unturned page had it"


def test_a_colour_reads_the_same_whichever_space_it_was_written_in():
    assert pdfvector._colour_of((0.5,)) == "#808080"
    assert pdfvector._colour_of((1, 0, 0)) == "#ff0000"
    assert pdfvector._colour_of((0, 1, 1, 0)) == "#ff0000"
    assert pdfvector._colour_of(None) == ""


# ---------------------------------------------------------------------------
# What a repaint is allowed to cost
# ---------------------------------------------------------------------------

def test_one_repaint_never_asks_for_the_whole_sheet(tmp_path):
    """A repaint asks for what is on screen, not for the page it is part of.

    An A1 sheet at eight times life size is a thousand tiles. Asked for all at
    once they arrive long after the zoom that wanted them has moved on, and the
    render thread grinds through every one of them first — which is what made
    zooming into a dense drawing take ten seconds and then fifteen.
    """
    from PySide6.QtCore import QRectF

    from markforge.io import pdftiles

    cache = pdftiles.TileCache()
    asked: list = []
    cache._ask = lambda key, data, page, sheet: asked.append(key)
    page = QRectF(0, 0, 2384, 1684)                    # A1
    # The whole sheet, at a zoom where it is a thousand squares.
    cache.tiles("a-drawing", b"%PDF-", 0, page, 8.0, page)
    assert asked, "it should ask for something"
    assert len(asked) <= pdftiles.MOST_TILES_AT_ONCE, len(asked)


def test_a_zoom_gives_up_on_the_zoom_before_it(tmp_path):
    """Squares of a page at a zoom nobody is looking at are not worth drawing."""
    from PySide6.QtCore import QRectF

    from markforge.io import pdftiles

    cache = pdftiles.TileCache()
    cache._ask = lambda key, data, page, sheet: cache._waiting.add(key)
    page = QRectF(0, 0, 2384, 1684)
    cache.tiles("a-drawing", b"%PDF-", 0, page, 2.0, page)
    coarse = {key for key in cache._waiting if getattr(key, "scale", 0) == 2.0}
    assert coarse, "the first zoom should have asked for squares"

    cache.tiles("a-drawing", b"%PDF-", 0, page, 8.0, page)
    assert not [key for key in cache._waiting
                if getattr(key, "scale", 0) == 2.0], \
        "and the zoom after it should have given up on them"


def test_a_page_is_drawn_at_every_zoom_including_right_out(tmp_path):
    """Zoomed out is drawn, not left as a small picture stretched over a sheet.

    The whole-page thumbnail is the gap filler while tiles come. Serving it as
    the answer at low zoom leaves a drawing permanently soft — it only sharpens
    when something makes it render, which is what zooming in does. A page has
    to be drawn at the resolution it is being shown at, at any zoom.
    """
    from PySide6.QtCore import QRectF

    from markforge.io import pdftiles

    cache = pdftiles.TileCache()
    asked: list = []
    cache._ask = lambda key, data, page, sheet: asked.append(key)
    page = QRectF(0, 0, 2384, 1684)                    # A1
    # Fitted to a window: well under the thumbnail's own sharpness.
    cache.tiles("a-drawing", b"%PDF-", 0, page, 0.25, page)
    assert [key for key in asked if isinstance(key, pdftiles.TileKey)], \
        "zoomed out still has to be drawn"


def test_a_page_is_drawn_at_the_real_pixels_of_the_screen_showing_it():
    """A screen at two hundred per cent gets twice the resolution, not the same.

    Qt keeps the device's pixel ratio on the paint device, not in the
    painter's transform, so a page asked for at "one to one" on such a screen
    is really being shown at two pixels to the point. Reading only the
    transform had every tile rendered at half the resolution it was drawn at
    and stretched to fit — a sheet that never came into focus at any zoom,
    on every laptop made in the last ten years.
    """
    from PySide6.QtGui import QImage, QPainter

    from markforge.ui.scene import _painted_scale

    sharpness = {}
    for ratio in (1.0, 2.0):
        canvas = QImage(64, 64, QImage.Format_RGB32)
        canvas.setDevicePixelRatio(ratio)
        painter = QPainter(canvas)
        sharpness[ratio] = _painted_scale(painter)
        painter.end()
    assert sharpness[2.0] == pytest.approx(sharpness[1.0] * 2.0), sharpness


def test_a_page_nobody_can_see_is_not_drawn():
    """Opening a forty-sheet set draws the sheets being read, not all forty."""
    from PySide6.QtCore import QRectF

    from markforge.io import pdftiles

    cache = pdftiles.TileCache()
    asked: list = []
    cache._ask = lambda key, data, page, sheet: (
        asked.append(key), cache._waiting.add(key))
    page = QRectF(0, 0, 595, 842)
    for index in range(40):
        cache.sheet("a-set", b"%PDF-", index, page)
    assert len(asked) <= pdftiles.MOST_SHEETS_AT_ONCE, len(asked)


# ---------------------------------------------------------------------------
# Real files
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not CORPUS, reason="no corpus of real PDFs here")
@pytest.mark.parametrize("path", CORPUS[:10], ids=os.path.basename)
def test_a_real_pdf_comes_apart_into_its_pages(path):
    document = engine.open_path(path)
    try:
        assert document.page_count >= 1
        width, height = engine.page_size(document, 0)
        assert width > 0 and height > 0
        assert engine.render_page(document, 0, 80, 80) is not None
    finally:
        engine.close(document)
