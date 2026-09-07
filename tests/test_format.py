"""What a saved document is.

A PDF, and nothing else. It opens in any reader; an imported drawing keeps the
source PDF's own page rather than a picture of it; every markup goes in as a
real annotation; and what a PDF cannot hold about a markup rides along inside
the same file as an embedded record.
"""
import os

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtPdf import QPdfDocument

from markforge.core.document import Document
from markforge.io import pdfbase, project as project_io


def _readable_pdf(path: str) -> QPdfDocument:
    document = QPdfDocument()
    assert document.load(path) == QPdfDocument.Error.None_, \
        f"{path} is not a readable PDF"
    return document


def test_a_saved_document_is_a_pdf_any_reader_can_open(window, tmp_path):
    path = str(tmp_path / "sheet.pdf")
    project_io.save_document(window.document, path)

    with open(path, "rb") as handle:
        assert handle.read(5) == b"%PDF-", "a saved document should be a PDF"
    assert _readable_pdf(path).pageCount() == len(window.document.pages)








def test_a_saved_document_comes_back_exactly(window, tmp_path):
    from markforge.items.shapes import RectItem

    from markforge.items.text import NoteItem

    window.document.title = "Portal frame"
    frame = window.document.pages[0].frame
    frame.add_markup(RectItem(), QPointF(40, 40))
    frame.add_markup(NoteItem("check this"), QPointF(200, 40))
    path = str(tmp_path / "frame.pdf")
    project_io.save_document(window.document, path)

    reopened = Document()
    project_io.load_document(reopened, path)
    assert reopened.title == "Portal frame"
    assert sorted(item["type"] for item in reopened.pages[0]._pending_items) \
        == ["note", "rect"]


def test_an_imported_page_keeps_the_source_pdfs_own_page(window, tmp_path):
    """Not a picture of the drawing — the drawing."""
    from markforge.io import pdfio

    source = str(tmp_path / "drawing.pdf")
    _a_pdf_with_line_work(source)
    document = window.document
    document.pages = []
    pdfio.import_pages(document, source, [0], pdfio.FIT_ORIGINAL, 96.0, at=0)

    saved = str(tmp_path / "marked_up.pdf")
    project_io.save_document(document, saved)

    from pypdf import PdfReader
    text = PdfReader(saved).pages[0].extract_text()
    assert "GRID LINE" in text, \
        "the imported page's own text should still be in the saved file"


def test_a_pdf_that_is_not_a_document_is_not_opened_as_one(tmp_path):
    plain = str(tmp_path / "plain.pdf")
    _a_pdf_with_line_work(plain)
    assert not project_io.carries_a_document(plain)
    assert pdfbase.record_in(plain) is None


def test_a_saved_document_is_recognised_whatever_it_is_called(window, tmp_path):
    """What decides is what the file holds, not the name it was given."""
    path = str(tmp_path / "misnamed.pdf")
    project_io.save_document(window.document, path)
    assert project_io.carries_a_document(path)


def test_documents_written_before_the_format_was_a_pdf_still_open(tmp_path):
    import json
    import zipfile

    path = str(tmp_path / "old.pdf")
    old = Document()
    old.title = "Written last year"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("document.json", json.dumps(old.to_dict()))
        archive.writestr("assets/asset_one.png", b"not really a png")

    reopened = Document()
    project_io.load_document(reopened, path)
    assert reopened.title == "Written last year"
    assert reopened.asset("asset_one.png") == b"not really a png"


def _a_pdf_with_line_work(path: str) -> None:
    """A small PDF with real text and a real line in it, written by hand."""
    body = (b"BT /F1 12 Tf 40 700 Td (GRID LINE 1) Tj ET\n"
            b"2 w 40 600 m 500 600 l S\n")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(body)).encode() + b" >>\nstream\n" + body + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += str(number).encode() + b" 0 obj\n" + obj + b"\nendobj\n"
    start = len(out)
    out += b"xref\n0 " + str(len(objects) + 1).encode() + b"\n"
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (b"trailer\n<< /Size " + str(len(objects) + 1).encode()
            + b" /Root 1 0 R >>\nstartxref\n" + str(start).encode() + b"\n%%EOF\n")
    with open(path, "wb") as handle:
        handle.write(bytes(out))


def test_opening_a_pdf_is_opening_a_document_not_converting_one(window, tmp_path):
    """Save writes the file back, the way a marked-up drawing is saved."""
    source = str(tmp_path / "drawing.pdf")
    _a_pdf_with_line_work(source)
    window.open_path(source)
    assert window.document.path == source, \
        "an opened PDF should be the document, not a source to convert"

    window.rebuild_scenes()
    assert window.save_document()
    assert project_io.carries_a_document(source), \
        "saving should have put the markup record into that same PDF"
    from pypdf import PdfReader
    assert "GRID LINE" in PdfReader(source).pages[0].extract_text()




def test_saving_a_marked_up_drawing_leaves_the_drawing_byte_for_byte(
        window, tmp_path):
    """The file that comes out starts with the file that went in.

    Not "the same drawing", not "the same pages" — the same bytes. That is
    what makes a save an addition to somebody else's document rather than a
    re-export of it: a signature over the original still covers the original,
    an embedded font is still the font that was embedded, and nothing has been
    quietly re-compressed on the way through.
    """
    from PySide6.QtCore import QRectF
    from markforge.items.shapes import RectItem

    source = str(tmp_path / "drawing.pdf")
    _a_pdf_with_line_work(source)
    with open(source, "rb") as handle:
        original = handle.read()

    window.open_path(source)
    window.rebuild_scenes()
    drawn = RectItem()
    drawn.set_local_rect(QRectF(0, 0, 200, 120))
    window.document.pages[0].frame.add_markup(drawn, QPointF(100, 100))

    saved = str(tmp_path / "marked.pdf")
    project_io.save_document(window.document, saved)
    with open(saved, "rb") as handle:
        written = handle.read()

    assert written[:len(original)] == original, \
        "the drawing that came in should still be there, exactly"
    assert len(written) > len(original), "and the markups appended after it"
    assert _readable_pdf(saved).pageCount() == 1


def test_an_updated_drawing_still_reads_as_a_pdf_everywhere(window, tmp_path):
    """An incremental update is a PDF, not a PDF with something stuck on it."""
    from PySide6.QtCore import QRectF
    from pypdf import PdfReader

    from markforge.items.shapes import RectItem

    source = str(tmp_path / "drawing.pdf")
    _a_pdf_with_line_work(source)
    window.open_path(source)
    window.rebuild_scenes()
    drawn = RectItem()
    drawn.set_local_rect(QRectF(0, 0, 200, 120))
    window.document.pages[0].frame.add_markup(drawn, QPointF(100, 100))
    saved = str(tmp_path / "marked.pdf")
    project_io.save_document(window.document, saved)

    reader = PdfReader(saved)
    assert len(reader.pages) == 1
    assert "GRID LINE" in reader.pages[0].extract_text(), \
        "the page's own words are still its own words"
    annotations = reader.pages[0].get("/Annots") or []
    assert len(annotations) == 1, "and the rectangle went in as an annotation"
    assert str(annotations[0].get_object()["/Subtype"]) == "/Square"
    assert project_io.carries_a_document(saved), \
        "the record rides along in the update, not only in a fresh write"


def test_saving_twice_leaves_one_record_to_read_back(window, tmp_path):
    """Each save appends. The record read back has to be the last one."""
    source = str(tmp_path / "drawing.pdf")
    _a_pdf_with_line_work(source)
    window.open_path(source)
    window.rebuild_scenes()
    saved = str(tmp_path / "marked.pdf")

    window.document.title = "First"
    project_io.save_document(window.document, saved)
    window.document.title = "Second"
    project_io.save_document(window.document, saved)

    reopened = Document()
    project_io.load_document(reopened, saved)
    assert reopened.title == "Second"


def test_a_page_the_update_cannot_describe_is_assembled_instead(window, tmp_path):
    """A drawing that has been dimmed is not the drawing that came in.

    The incremental path can only add to the source page; anything that
    changes the page itself has to be painted, and then the file is built
    rather than added to. It still has to be a correct PDF either way.
    """
    from markforge.io import pdfsave

    source = str(tmp_path / "drawing.pdf")
    _a_pdf_with_line_work(source)
    window.open_path(source)
    window.rebuild_scenes()
    assert pdfsave.source_bytes(window.document) is not None

    window.document.pages[0].background_opacity = 0.4
    assert pdfsave.source_bytes(window.document) is None, \
        "a dimmed page is not the source page"

    saved = str(tmp_path / "dimmed.pdf")
    project_io.save_document(window.document, saved)
    assert _readable_pdf(saved).pageCount() == 1
    assert project_io.carries_a_document(saved)


def test_what_is_drawn_on_the_page_is_in_the_saved_pdf(window, tmp_path):
    """Any reader opening the file sees the markups, not an empty sheet."""
    from PySide6.QtCore import QRectF, QSize
    from PySide6.QtPdf import QPdfDocumentRenderOptions

    from markforge.items.shapes import RectItem

    before = str(tmp_path / "before.pdf")
    project_io.save_document(window.document, before)

    drawn = RectItem()
    drawn.set_local_rect(QRectF(0, 0, 200, 120))
    window.document.pages[0].frame.add_markup(drawn, QPointF(100, 100))
    after = str(tmp_path / "after.pdf")
    project_io.save_document(window.document, after)

    def ink(path: str) -> int:
        # As a reader draws it: the markups are annotations, and a reader
        # draws those, so the flag is what "what somebody sees" means here.
        options = QPdfDocumentRenderOptions()
        options.setRenderFlags(QPdfDocumentRenderOptions.RenderFlag.Annotations)
        page = _readable_pdf(path).render(0, QSize(595, 842), options)
        return sum(1 for y in range(page.height()) for x in range(page.width())
                   if page.pixelColor(x, y).lightness() < 220)

    assert ink(after) > ink(before) + 200, \
        "the rectangle should be visible in the saved PDF"


def test_an_imported_pdf_brings_in_the_markups_somebody_else_made(window, tmp_path):
    """A marked-up drawing keeps its markups in annotations; bring them in.

    As markups — one thing to click on, in its own colour — and in the picture
    of the page as well, so nothing that was drawn on it goes missing.
    """
    from PySide6.QtCore import QRectF
    from markforge.io import export as export_io, pdfio
    from markforge.items.shapes import RectItem

    drawn = RectItem()
    drawn.set_local_rect(QRectF(0, 0, 180, 110))
    window.document.pages[0].frame.add_markup(drawn, QPointF(120, 150))
    marked = str(tmp_path / "marked.pdf")
    export_io.export_pdf(window.document, marked)

    # The rectangle comes back as a rectangle, where it was drawn, and not
    # as a picture of one or as the segments its outline is made of.
    found = pdfio.markups(marked, [0])
    assert [(item["type"], item.get("kind"), round(item["x"]), round(item["y"]))
            for item in found[0]] == [("rect", "rect", 120, 150)]

    # And the picture of the page shows it too.
    source = pdfio.PdfSource(marked)
    try:
        data, _info = source.render_png(0, 96.0)
    finally:
        source.close()
    from PySide6.QtGui import QImage
    picture = QImage()
    assert picture.loadFromData(data)
    inked = sum(1 for y in range(0, picture.height(), 2)
                for x in range(0, picture.width(), 2)
                if picture.pixelColor(x, y).lightness() < 200)
    assert inked > 50, "the markups should be in the picture of the page too"


def test_saving_leaves_the_markups_movable_in_another_editor(window, tmp_path):
    """Saved, not exported: the same file, and the same live markups."""
    from PySide6.QtCore import QRectF
    from markforge.items.shapes import RectItem

    drawn = RectItem()
    drawn.set_local_rect(QRectF(0, 0, 180, 110))
    window.document.pages[0].frame.add_markup(drawn, QPointF(120, 150))
    path = str(tmp_path / "saved.pdf")
    project_io.save_document(window.document, path)

    from pypdf import PdfReader
    reader = PdfReader(path)
    marks = reader.pages[0].get("/Annots")
    marks = [entry.get_object() for entry in marks.get_object()] if marks else []
    assert [str(mark["/Subtype"]) for mark in marks] == ["/Square"], \
        "a saved markup should still be a markup wherever the file is opened"
    assert "/AP" in marks[0]
    assert project_io.carries_a_document(path), \
        "and the markup record is still in there"


def test_a_marked_up_drawing_opens_as_markups_that_can_be_worked_with(
        window, tmp_path):
    """What somebody else drew is theirs to click on, not a picture of it."""
    from PySide6.QtCore import QRectF
    from markforge.items.shapes import PolyItem, RectItem
    from markforge.io import export as export_io

    frame = window.document.pages[0].frame
    box = RectItem()
    box.set_local_rect(QRectF(0, 0, 180, 110))
    box.style.stroke = "#2f9e44"
    box.author = "R. Kavanagh"
    box.comment = "Check this splice"
    frame.add_markup(box, QPointF(120, 150))
    oval = RectItem("ellipse")
    oval.set_local_rect(QRectF(0, 0, 90, 70))
    frame.add_markup(oval, QPointF(340, 150))
    run = PolyItem("polyline", [QPointF(0, 0), QPointF(60, 40), QPointF(120, 0)])
    frame.add_markup(run, QPointF(120, 400))
    cloud = RectItem("cloud")
    cloud.set_local_rect(QRectF(0, 0, 150, 90))
    frame.add_markup(cloud, QPointF(300, 400))

    theirs = str(tmp_path / "reviewed.pdf")
    export_io.export_pdf(window.document, theirs)

    window.open_path(theirs)
    window.rebuild_scenes()
    # Opening shows the drawing as the file has it. Replying to it is a
    # separate act, and this is it.
    assert not window.document.pages[0].frame.markups()
    window.make_markups_editable(0)
    came_in = [item for item in window.document.pages[0].frame.markups()
               if not item.from_drawing]
    kinds = [(type(item).__name__, getattr(item, "kind", "")) for item in came_in]
    assert ("RectItem", "rect") in kinds
    assert ("RectItem", "ellipse") in kinds
    assert ("PolyItem", "polyline") in kinds
    # A cloud is a square with a cloudy border, which the PDF has a way of
    # saying — so it comes back a cloud rather than a drawing of one.
    assert ("RectItem", "cloud") in kinds

    theirs_rect = next(i for i in came_in if getattr(i, "kind", "") == "rect")
    assert theirs_rect.pos().x() == pytest.approx(120, abs=1)
    assert theirs_rect.pos().y() == pytest.approx(150, abs=1)
    assert theirs_rect.style.stroke == "#2f9e44"
    assert theirs_rect.author == "R. Kavanagh"
    assert theirs_rect.comment == "Check this splice"
    assert not theirs_rect.locked, "their markup is there to be worked with"


def test_a_page_from_a_pdf_gets_sharper_as_it_is_zoomed_into(window, tmp_path):
    """Drawn from the file at the size it is shown, not enlarged from a picture."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QStyleOptionGraphicsItem
    from markforge.io import export as export_io

    source = str(tmp_path / "drawing.pdf")
    export_io.export_pdf(window.document, source)
    window.open_path(source)
    window.rebuild_scenes()
    frame = window.document.pages[0].frame

    def look_at(zoom: float, region: QRectF) -> float:
        canvas = QImage(300, 300, QImage.Format_ARGB32)
        canvas.fill(0)
        painter = QPainter(canvas)
        painter.scale(zoom, zoom)
        option = QStyleOptionGraphicsItem()
        option.exposedRect = region
        frame.paint(painter, option)
        painter.end()
        drawn = frame._sharp
        return drawn.width() / max(frame._sharp_region.width(), 1) if drawn else 0.0

    assert look_at(1.0, QRectF(0, 0, 595, 842)) == pytest.approx(1.0, abs=0.01)
    assert look_at(4.0, QRectF(100, 100, 150, 200)) == pytest.approx(4.0, abs=0.01)
    assert look_at(16.0, QRectF(120, 120, 40, 50)) == pytest.approx(16.0, abs=0.01), \
        "zoomed right in, the picture is drawn at the zoom, not blown up"


# ---------------------------------------------------------------------------
# Markups written as what they are, not as a picture of what they are
# ---------------------------------------------------------------------------

def _marked_up_page(window):
    """One of each markup a PDF has a real annotation for."""
    from PySide6.QtCore import QRectF
    from markforge.core.document import PageScale
    from markforge.items.measure import AREA, DIMENSION, MeasureItem
    from markforge.items.shapes import PolyItem, RectItem
    from markforge.items.text import CalloutItem, TypewriterItem

    page = window.document.pages[0]
    page.scale = PageScale.from_ratio(100)
    frame = page.frame
    boxed = RectItem("cloud")
    boxed.set_local_rect(QRectF(0, 0, 150, 90))
    frame.add_markup(boxed, QPointF(60, 60))
    frame.add_markup(PolyItem("cloud", [QPointF(0, 0), QPointF(100, 0),
                                        QPointF(100, 70)]), QPointF(250, 60))
    frame.add_markup(PolyItem("arrow", [QPointF(0, 0), QPointF(120, 60)]),
                     QPointF(60, 200))
    frame.add_markup(CalloutItem("see detail"), QPointF(250, 220))
    frame.add_markup(TypewriterItem("typed"), QPointF(60, 320))
    dimension = MeasureItem(DIMENSION, [QPointF(0, 0), QPointF(200, 0)])
    frame.add_markup(dimension, QPointF(60, 420))
    dimension.witness_reach = -30.0
    dimension.refresh(page=page)
    area = MeasureItem(AREA, [QPointF(0, 0), QPointF(120, 0), QPointF(120, 90)])
    frame.add_markup(area, QPointF(320, 420))
    area.refresh(page=page)


def _annotations(path: str) -> list:
    from pypdf import PdfReader

    found = PdfReader(path).pages[0].get("/Annots")
    return [entry.get_object() for entry in found.get_object()] if found else []


def test_a_cloud_goes_out_as_a_cloud_not_a_drawing_of_one(window, tmp_path):
    """A PDF says a cloud with a border effect; it does not draw one."""
    from markforge.io import export as export_io

    _marked_up_page(window)
    path = str(tmp_path / "clouds.pdf")
    export_io.export_pdf(window.document, path)

    cloudy = [mark for mark in _annotations(path)
              if "/BE" in mark and str(mark["/BE"].get("/S")) == "/C"]
    assert len(cloudy) == 2, "the boxed cloud and the polygon cloud"
    assert {str(mark["/Subtype"]) for mark in cloudy} == {"/Square", "/Polygon"}
    assert float(cloudy[0]["/BE"]["/I"]) > 0, "and it says how pronounced it is"


def test_a_call_out_goes_out_with_its_leader(window, tmp_path):
    """Free text with a callout line — the three-point form, knee and all."""
    from markforge.io import export as export_io

    _marked_up_page(window)
    path = str(tmp_path / "callout.pdf")
    export_io.export_pdf(window.document, path)

    callouts = [mark for mark in _annotations(path)
                if str(mark.get("/IT", "")) == "/FreeTextCallout"]
    assert len(callouts) == 1
    assert len(callouts[0]["/CL"]) == 6, "start, knee and end"
    typed = [mark for mark in _annotations(path)
             if str(mark.get("/IT", "")) == "/FreeTextTypeWriter"]
    assert len(typed) == 1, "and a typewriter says it is one"


def test_a_dimension_goes_out_as_a_dimension(window, tmp_path):
    """Every part of it already had a name in the specification."""
    from markforge.io import export as export_io

    _marked_up_page(window)
    path = str(tmp_path / "dimension.pdf")
    export_io.export_pdf(window.document, path)

    dimensions = [mark for mark in _annotations(path)
                  if str(mark.get("/IT", "")) == "/LineDimension"]
    assert len(dimensions) == 1
    mark = dimensions[0]
    assert str(mark["/Subtype"]) == "/Line"
    assert float(mark["/LL"]) == pytest.approx(30, abs=0.5), "the witness reach"
    assert float(mark["/LLE"]) > 0, "how far past the line they run"
    assert float(mark["/LLO"]) > 0, "and how far clear of the point they start"
    assert bool(mark["/Cap"]) and str(mark["/CP"]) == "/Inline", \
        "the value is written along the line"
    assert "/Measure" in mark, "and the scale travels with it"


def test_a_take_off_carries_the_scale_it_was_measured_against(window, tmp_path):
    """Otherwise the number means nothing in anybody else's reader."""
    from markforge.io import export as export_io

    _marked_up_page(window)
    path = str(tmp_path / "area.pdf")
    export_io.export_pdf(window.document, path)

    areas = [mark for mark in _annotations(path)
             if str(mark.get("/IT", "")) == "/PolygonDimension"]
    assert len(areas) == 1
    measure = areas[0]["/Measure"]
    assert str(measure["/Subtype"]) == "/RL"
    assert str(measure["/R"]), "the scale, written the way it is written on a drawing"


def test_every_markup_comes_back_as_what_it_went_out_as(window, tmp_path):
    """The round trip: out as a real annotation, in as the same markup."""
    from markforge.io import export as export_io

    _marked_up_page(window)
    path = str(tmp_path / "round.pdf")
    export_io.export_pdf(window.document, path)

    window.open_path(path)
    window.rebuild_scenes()
    window.make_markups_editable(0)
    came_back = [item for item in window.document.pages[0].frame.markups()
                 if not item.from_drawing]
    kinds = [(type(item).__name__, getattr(item, "kind", ""))
             for item in came_back]
    assert ("RectItem", "cloud") in kinds, "a cloud is still a cloud"
    assert ("PolyItem", "cloud") in kinds
    assert ("CalloutItem", "") in kinds
    assert ("TypewriterItem", "") in kinds
    assert ("MeasureItem", "dimension") in kinds
    assert ("MeasureItem", "area") in kinds

    dimension = next(i for i in came_back if getattr(i, "kind", "") == "dimension")
    assert dimension.witness_reach == pytest.approx(-30, abs=0.5), \
        "its witness lines come back where they were"
    callout = next(i for i in came_back if type(i).__name__ == "CalloutItem")
    assert callout.leaders, "and the call-out still points at something"


def test_an_arrow_keeps_its_head(window, tmp_path):
    from markforge.io import export as export_io

    _marked_up_page(window)
    path = str(tmp_path / "arrow.pdf")
    export_io.export_pdf(window.document, path)

    lines = [mark for mark in _annotations(path)
             if str(mark["/Subtype"]) == "/Line" and "/IT" not in mark]
    assert lines and "/LE" in lines[0]
    assert str(lines[0]["/LE"][1]) == "/ClosedArrow"
