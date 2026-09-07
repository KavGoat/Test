"""What a saved document is.

This is a PDF editor that can also do calculations, so a saved document is a
PDF: it opens in any reader, an imported drawing keeps the source PDF's own
page rather than a picture of it, and the calculations ride along inside the
file as a layer. ``.cfx`` and ``.pdf`` name the same kind of file — which one
a document is called depends on whether there are calculations in it.
"""
import os

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtPdf import QPdfDocument

from calcforge.core.document import Document
from calcforge.io import pdfbase, project as project_io


def _readable_pdf(path: str) -> QPdfDocument:
    document = QPdfDocument()
    assert document.load(path) == QPdfDocument.Error.None_, \
        f"{path} is not a readable PDF"
    return document


def test_a_saved_document_is_a_pdf_any_reader_can_open(window, tmp_path):
    path = str(tmp_path / "sheet.cfx")
    project_io.save_document(window.document, path)

    with open(path, "rb") as handle:
        assert handle.read(5) == b"%PDF-", "a saved document should be a PDF"
    assert _readable_pdf(path).pageCount() == len(window.document.pages)


def test_a_document_with_no_calculations_is_named_a_pdf(window, tmp_path):
    """Nothing calculated in it, so it is a PDF and is called one."""
    assert not pdfbase.has_calculations(window.document)
    project_io.save_document(window.document, str(tmp_path / "markup"))
    assert window.document.path.endswith(".pdf")


def test_putting_a_calculation_in_it_makes_it_a_cfx(window, tmp_path):
    _a_calculation_on(window)
    assert pdfbase.has_calculations(window.document)
    project_io.save_document(window.document, str(tmp_path / "beam"))
    assert window.document.path.endswith(".cfx")


def test_a_cfx_is_that_same_pdf_with_the_calculations_added(window, tmp_path):
    """Renaming a .cfx to .pdf loses nothing: it was a PDF all along."""
    _a_calculation_on(window)
    path = str(tmp_path / "beam.cfx")
    project_io.save_document(window.document, path)

    renamed = str(tmp_path / "beam.pdf")
    os.rename(path, renamed)
    assert _readable_pdf(renamed).pageCount() == len(window.document.pages)


def test_a_saved_document_comes_back_exactly(window, tmp_path):
    from calcforge.items.shapes import RectItem

    window.document.title = "Portal frame"
    frame = window.document.pages[0].frame
    frame.add_markup(RectItem(), QPointF(40, 40))
    _a_calculation_on(window)
    path = str(tmp_path / "frame.cfx")
    project_io.save_document(window.document, path)

    reopened = Document()
    project_io.load_document(reopened, path)
    assert reopened.title == "Portal frame"
    assert sorted(item["type"] for item in reopened.pages[0]._pending_items) \
        == ["math", "rect"]


def test_an_imported_page_keeps_the_source_pdfs_own_page(window, tmp_path):
    """Not a picture of the drawing — the drawing."""
    from calcforge.io import pdfio

    source = str(tmp_path / "drawing.pdf")
    _a_pdf_with_line_work(source)
    document = window.document
    document.pages = []
    pdfio.import_pages(document, source, [0], pdfio.FIT_ORIGINAL, 96.0, at=0)

    saved = str(tmp_path / "marked_up.cfx")
    project_io.save_document(document, saved)

    from pypdf import PdfReader
    text = PdfReader(saved).pages[0].extract_text()
    assert "GRID LINE" in text, \
        "the imported page's own text should still be in the saved file"


def test_a_pdf_that_is_not_a_document_is_not_opened_as_one(tmp_path):
    plain = str(tmp_path / "plain.pdf")
    _a_pdf_with_line_work(plain)
    assert not project_io.carries_a_document(plain)
    assert pdfbase.layer_in(plain) is None


def test_a_saved_document_is_recognised_whatever_it_is_called(window, tmp_path):
    """What decides is what the file holds, not the name it was given."""
    path = str(tmp_path / "misnamed.pdf")
    project_io.save_document(window.document, path)
    assert project_io.carries_a_document(path)


def test_documents_written_before_the_format_was_a_pdf_still_open(tmp_path):
    import json
    import zipfile

    path = str(tmp_path / "old.cfx")
    old = Document()
    old.title = "Written last year"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("document.json", json.dumps(old.to_dict()))
        archive.writestr("assets/asset_one.png", b"not really a png")

    reopened = Document()
    project_io.load_document(reopened, path)
    assert reopened.title == "Written last year"
    assert reopened.asset("asset_one.png") == b"not really a png"


def _a_calculation_on(window) -> None:
    from calcforge.items.mathitem import MathItem

    frame = window.document.pages[0].frame
    frame.add_markup(MathItem("a := 2 m"), QPointF(80, 100))


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
        "saving should have put the markup layer into that same PDF"
    from pypdf import PdfReader
    assert "GRID LINE" in PdfReader(source).pages[0].extract_text()


def test_a_calculation_moves_the_save_beside_the_pdf_as_a_cfx(window, tmp_path):
    source = str(tmp_path / "drawing.pdf")
    _a_pdf_with_line_work(source)
    window.open_path(source)
    window.rebuild_scenes()
    _a_calculation_on(window)

    assert window.save_document()
    assert window.document.path == str(tmp_path / "drawing.cfx")
    assert os.path.exists(source), "the drawing itself should be left alone"


def test_what_is_drawn_on_the_page_is_in_the_saved_pdf(window, tmp_path):
    """Any reader opening the file sees the markups, not an empty sheet."""
    from PySide6.QtCore import QRectF, QSize
    from PySide6.QtPdf import QPdfDocumentRenderOptions

    from calcforge.items.shapes import RectItem

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


def test_a_drawing_opened_for_review_can_be_calculated_on(window, tmp_path):
    """A PDF editor that can calculate: the drawing is one command away."""
    source = str(tmp_path / "drawing.pdf")
    _a_pdf_with_line_work(source)
    window.open_path(source)
    window.rebuild_scenes()
    window.apply_document_mode()

    assert not window.tool_actions["math"].isVisible()
    assert window.act_add_calculations.isVisible()

    window.act_add_calculations.trigger()
    assert window.document.mode == "worksheet"
    assert window.tool_actions["math"].isVisible()
    assert window.calculate_menu.menuAction().isVisible()
    assert not window.act_add_calculations.isVisible(), \
        "nothing left to turn on once the calculation tools are there"

    _a_calculation_on(window)
    assert window.save_document()
    assert window.document.path.endswith(".cfx")


def test_an_imported_pdf_brings_in_the_markups_somebody_else_made(window, tmp_path):
    """A marked-up drawing keeps its markups in annotations; bring them in.

    As markups — one thing to click on, in its own colour — and in the picture
    of the page as well, so nothing that was drawn on it goes missing.
    """
    from PySide6.QtCore import QRectF
    from calcforge.io import export as export_io, pdfio
    from calcforge.items.shapes import RectItem

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
    from calcforge.items.shapes import RectItem

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
        "and the calculation layer is still in there"


def test_a_marked_up_drawing_opens_as_markups_that_can_be_worked_with(
        window, tmp_path):
    """What somebody else drew is theirs to click on, not a picture of it."""
    from PySide6.QtCore import QRectF
    from calcforge.items.shapes import PolyItem, RectItem
    from calcforge.io import export as export_io

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
    came_in = [item for item in window.document.pages[0].frame.markups()
               if item.layer == "Markups"]
    kinds = [(type(item).__name__, getattr(item, "kind", "")) for item in came_in]
    assert ("RectItem", "rect") in kinds
    assert ("RectItem", "ellipse") in kinds
    assert ("PolyItem", "polyline") in kinds
    # A cloud has no annotation of its own in a PDF, so it travels as a stamp —
    # and comes back as one drawing to pick up, not as the segments of one.
    assert ("SketchItem", "") in kinds

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
    from calcforge.io import export as export_io

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
